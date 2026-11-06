# Multi-agent investigations in the deployed product

Status: **design, 2026-11-05. Nothing here is implemented or validated.** Governing direction: [the four pillars](../../Main_Culture_andETHOS.md). Extends the [proactive assistant contract](../product/proactive-assistant-architecture.md) and the [DigitalOcean worker pilot](../../backend/docs/security/cloud-backend.md); interacts with [ADR 0003](../adr/0003-persistent-missions-and-runtime-boundaries.md) (§9).

**Decisions recorded 2026-11-05 (product owner):** execution runs on the **DigitalOcean pilot** (`cloud_backend`). V1 spend limits are tool-call, wall-time and token caps. Anyone with `propose` on the case/site may start a run; default budget 60 tool calls / 20 minutes / ≤2 concurrent per tenant. The fermentation "agent assessment" moves onto this job model in Phase 1.

## 1. Job to be done

An investigation owner asks "why did DEV-31 happen?" and wants a thorough, cited investigation of the authorized evidence. That takes 5–30 minutes and parallel lines of inquiry: process data, materials, equipment history, precedent cases. They want to watch it, steer or stop it, and receive a reviewable report. They should not have to wait in front of one blocking request or trust a black box.

## 2. What exists today (verified in code)

| Piece | State |
| --- | --- |
| Deployed chat | Plans ≤10 sequential steps (`conversation.py` → `flows.py`). No sub-agents. Runs on AWS Lambda with Supabase Postgres. |
| Prime multi-agent harness | Real: the lead spawns children with `rlm.spawn` (`harness.py:121`). Bridge tools, budgets, `allocate_work`, `submit_subreport` and `investigation-checkpoint.json` exist (`bridge.py`). |
| Child telemetry | `sdk_runner.mjs:96-105` emits `child_activity` with `child_id`, `parent_id`, `status`, current `tool`, `tool_use_count`, `token_count` and timestamps. It is **captured until exit** (`subprocess.run(capture_output=True)`, `harness.py:164`), so it is not live. |
| Child attribution of tool calls | The bridge only knows `RLM_DEPTH`, not which child called (`bridge.py:719`). |
| Deployed access to Prime | Only the fermentation "agent assessment", a single blocking ≤600 s request. Nothing in the UI shows children. |
| DigitalOcean worker (`cloud_backend/`) | Implemented and locally verified, **not deployed** (runbook status). It has a job API, Postgres jobs, and a dispatcher that reconciles every 5 s, admits 2 runs, and gives each job a deadline and fencing token. It runs one hardened Docker container per attempt, with no DB or Spaces credentials and egress only through a CONNECT proxy. Results are sealed (AES-256-GCM) in versioned Spaces. Identity is verified RS256 tokens from a configured issuer/JWKS with `tenant_id` and `projects` claims (`auth.py`). It does **not** stream progress. |

## 3. Shape: one front door, a separate execution plane

The UI keeps talking only to the existing Lambda API. Supabase stays the system of record for users, permissions, runs, events and review. The DigitalOcean backend is used **only to execute**: it receives a sealed evidence snapshot, runs Prime in a container, collects its progress and returns a sealed report. Browsers never call DigitalOcean.

This keeps one login, one permission model and one audit trail visible to users (Adopt and Trust). The cost of the chosen runtime falls on infrastructure (§7), not on people.

```
Browser ──► Lambda API (existing) ── Supabase Postgres: investigation_run, investigation_event (RLS)
   ▲ poll 2 s     │  service token (RS256, minted by Lambda)     ▲
   │              ▼                                               │ Lambda pulls events + result
   │        DigitalOcean API (cloud_backend) ── DO Postgres: jobs, job_events
   │              │ dispatcher (existing): launch, reconcile, cancel, tail container stdout
   │              ▼
   │        Docker container per attempt: Prime harness + SDK + bridge, sealed snapshot
   │        egress only via existing CONNECT proxy → model provider, Spaces
   └── report ◄── Lambda verifies + stores in Supabase ◄── sealed result (Spaces)
```

## 4. Design

### 4.1 Records

**Supabase, the platform store, holds the system of record.** These are new record kinds, not a new database.
- `investigation_run`:
  - Identity and links: `run_id`, `tenant_id`, `site_id`, `owner_id`, `case_id?`, `conversation_id?`, `turn_id?`, `mission_id`.
  - Request: `objective`, `as_of`, `evidence_snapshot {sha256, items[], taken_at}`, `budget {max_tool_calls, deadline, max_tokens?}`.
  - Lifecycle: `status` (`queued → submitted → running → finalizing → awaiting_review | blocked | failed | cancelled`), `do_job {project, job_id}`, `events_cursor`, `usage {model_calls, tokens, cost_status}`, `report_ref?`, `revision`.
- `investigation_event`: an append-only copy of DigitalOcean events, `(run_id, seq)`, with `kind`, `at`, `agent_id`, `parent_id`, `payload`. Kinds: `phase`, `agent_started`, `agent_activity`, `agent_finished`, `allocation`, `subreport_saved`, `budget`, `error`.
- The final report enters the existing investigation review flow (`workflows/investigation_review.py`) as **requires human review**; findings stay hypotheses until reviewed.

**DigitalOcean (execution only)** keeps its existing `jobs` table, plus a new `job_events (job_id, attempt, seq, at, kind, payload)` table. It is a working buffer, not the record. It is retained per the pilot's backup policy.

### 4.2 Identity between Lambda and DigitalOcean (no change to `cloud_backend/auth.py`)

- Lambda acts as the **issuer**. It holds an RS256 private key in AWS Secrets Manager and publishes the public key at `GET https://<api>/.well-known/investigation-jwks.json`.
- Per call, Lambda mints a ≤5-minute token: `sub=platform-service`, `aud=<do-api>`, `tenant_id=<deployment tenant>`, `projects={<tenant>:<operator>}`. The DigitalOcean verifier is configured with this issuer, JWKS URL and audience.
- Lambda authorizes the *user* before minting. DigitalOcean authorizes the *service* for that tenant. A leaked token lasts minutes, and only for the job API.

### 4.3 Start

1. **Proposal, then the owner presses Start.** The assistant may propose "Run a full investigation". The card shows objective, evidence, time limit and tool-call budget. Starting requires `propose` on the case/site and a person, never an agent. Nothing starts automatically in v1, because runs spend money.
2. **Evidence snapshot.** Lambda gathers authorized evidence (verified delivery datasets and their originals, case records, linked records), re-checking permission *at this moment*. It builds a ZIP (≤64 MiB, the DigitalOcean input limit), hashes it and records the item list on the run. It then uploads it with the existing `PUT /v1/projects/{p}/inputs/{sha256}`.
3. **Submit** with the existing `POST /v1/projects/{p}/jobs` and an idempotency key equal to `run_id`. The manifest carries objective, `as_of`, deadline and `max_tool_calls`; it is extended with `max_tokens`. The dispatcher's existing admission control, deadlines, fencing and container limits apply unchanged.

### 4.4 Live progress

These are the main code changes.
- **Agent container** (`agent.py`, `harness.py`):
  - Switch the harness to `Popen` and read SDK stdout line by line.
  - A **metadata allow-list** prints one JSON line per event to container stdout: `child_activity`, `model_start/end` (timing and usage only), phase changes, and bridge events. Bridge events cover `allocate_work` (task ids, owner role, reason), `submit_subreport` (subreport id, assessment, counts, evidence ids) and budget changes.
  - It never prints message text, source text or provider errors; this extends the existing rule in `agent.py:main` and `sdk_runner.mjs:97`.
- **Dispatcher** (`dispatcher.py`, already holds the Docker socket):
  - For each running container it follows `docker logs` from the last read offset.
  - It parses only lines that are valid allow-listed JSON and appends them to `job_events` with the attempt's fencing token. Anything else is dropped.
  - The container still has no DB credentials and needs no callback endpoint.
- **DigitalOcean API:** new `GET /v1/projects/{p}/jobs/{id}/events?after=seq`, with the same authorization as `GET /jobs/{id}`.
- **Lambda:** reads `GET /jobs/{id}` and `/events?after=cursor` on a schedule. A per-minute EventBridge rule covers running runs, and reads also happen on demand when someone is viewing, rate-limited to once every 2 s per run. It copies them into `investigation_event` and folds them into the run state.
- **Child attribution (open question §11.1).** `child_activity` already carries the SDK `child_id`. Tool calls and subreports reach the bridge with depth only. Preferred fix: pass the SDK child id into the child kernel's environment beside `RLM_DEPTH` and send it as `_caller.agent_id`. If the SDK can't, attribute by `(depth, activity window)` and label it "approximate" in the UI.

### 4.5 Read API (Lambda; polling, because Lambda can't hold long streams)

- `GET /v1/investigation-runs/{id}`: run state plus an **agent tree** folded from events: per agent `{id, parent, role, question, status, current_tool, tool_calls, tokens, started_at, last_activity_at, subreports[]}` and budget used/remaining.
- `GET /v1/investigation-runs/{id}/events?after=seq`: incremental events for the timeline.
- `POST …/stop`: owner only. Sets `cancelled` and calls the existing DigitalOcean `POST /jobs/{id}/cancel`, whose fencing makes late completion ineligible.
- `GET …/report`: available once Lambda has fetched `GET /jobs/{id}/result`, validated it (run id, input SHA, `requires_human_review`) and stored it. Only people with access to the case can read it.

## 5. UI

### 5.1 In the conversation (default view: small)

```
┌ Investigation · DEV-31 foaming ─────────────────── running · 6 min ┐
│ ● Lead           planning next checks                               │
│ ├ ● Process data   reading DO/pH series     12 tool calls          │
│ ├ ✓ Materials      L-8812 CoA checked       1 finding              │
│ └ ○ Precedents     waiting                                         │
│ Budget ███████░░░ 41/60 tool calls · 6/20 min · cost: unknown      │
│ [Open investigation]                                   [Stop]      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Investigation view (`/investigations/{run_id}`, replacing today's hardcoded demo page)

- **Left: agent tree.** Lead plus investigators, with status and the one-line question each was given. Click an agent to filter the page to it.
- **Centre: what's happening.**
  - A timeline of phases, allocations, saved subreports and agent start/finish, newest first.
  - Each subreport is a card: assessment, counts, and links to cited evidence (opens the existing evidence drawer).
  - A "Now" strip shows the tools running at this moment.
- **Right: budget and control.**
  - Tool calls, time and tokens; cost shows as "unknown" when the provider doesn't report it, never $0.
  - The pinned evidence snapshot (items, as-of time) and **Stop**.
- **On completion.** The view becomes the review package: report, findings marked *hypothesis / supported / unknown*, conflicts and gaps, then **Send for QA review**. Approval stays in the existing review flow.
- **Honesty rules.**
  - Children are labelled "investigator", not given personas.
  - "Approximate" is shown where attribution falls back.
  - A failed or stopped run shows exactly what finished.
  - Nothing reads "complete" until the report validated.
  - Progress shown is up to ~2 s behind, and the UI says "updated Ns ago".

## 6. Failure, retry and stop

| Situation | Behaviour |
| --- | --- |
| Container fails or exceeds its deadline | The existing dispatcher marks the job failed or timed out (it does not retry). Lambda copies the status. The run keeps all events and subreports and offers **Run again** (new job, new snapshot). |
| Dispatcher or Droplet restarts | The existing reconciliation rediscovers containers. A host reboot loses the model session (documented pilot limit). Event tailing resumes from the last stored offset; any gap is recorded as an `error` event, not hidden. |
| DigitalOcean unreachable from Lambda | The run shows "execution service unreachable since …". Nothing is marked failed until DigitalOcean reports it or the deadline + 5 min passes. |
| Stop pressed | `cancelled` in the UI at once, then DigitalOcean cancel. Late events or results are ignored by fencing on both sides. |
| Duplicate event delivery | Keyed by `(job, attempt, seq)`; copied once. |
| Evidence changes mid-run | The run stays on its pinned snapshot. The UI shows "basis changed since start", and the report is flagged stale for review. |

## 7. Security, data boundaries and cost of the chosen runtime

- **Data leaves AWS/Supabase.** Evidence snapshots and reports transit to and are stored in DigitalOcean (SFO3), encrypted at the application layer. The runbook states the pilot is **not SOC 2 examined or approved for PHI**. Before customer data is used, the deploying organization must approve this data path. The product must not claim compliance.
- **Customer isolation.** One Droplet per customer is the runbook's baseline. Containers share the host kernel, so this is not VM-grade isolation between mutually untrusted tenants. Use one DigitalOcean stack per customer, as the runbook says.
- **Two stacks to operate.** Droplet, volume, Spaces, Caddy, backups and a second Postgres sit beside AWS. The Droplet runs continuously, so it has an idle cost, unlike per-run containers. Terraform exists; no apply has been run.
- **Model budget (accepted trade-off).** Prime calls the provider directly, so gateway budget enforcement is bypassed. The limits are tool calls, wall time and a token cap. Reported cost stays "unknown" where the provider doesn't return it.
- **Source text is untrusted.** The existing bridge rules apply, and events carry metadata only. The dispatcher drops any non-allow-listed log line.

## 8. What v1 deliberately does not do

- It does not resume a lost model session. Recovery is a new run; saved events and subreports remain visible.
- No automatic or background-triggered investigations until manual runs are measured.
- No scaling beyond the Droplet's capacity: the dispatcher admits 2 concurrent runs, and the queue is shown to users.

## 9. Relation to ADR 0003

ADR 0003 (proposed) chooses Temporal for mission scheduling, durable waits and recovery. This design does **not** introduce Temporal. A single investigation is a bounded job, and `cloud_backend`'s jobs, fencing and reconciliation cover it. If 0003 is accepted, the Lambda-side poller becomes a Temporal workflow; the records, events, API and UI stay the same. 0003 should note that investigation execution does not depend on it.

## 10. Plan and evidence for completion

| Phase | Scope | Exit evidence |
| --- | --- | --- |
| 0. Spike (≈2 d) | Build the agent image with Prime SDK + skills; run one investigation **locally in Docker** through `cloud_backend` on `scripts/make_sample_delivery.py` output; confirm SDK child id exposure (§11.1). Then the owner provisions the Droplet (Terraform + runbook) and the same run is repeated there. | Recorded runs (local and DigitalOcean) with provider and model identity, child events, report, image size and time to first child event. |
| 1. Backend (≈4–5 d) | Lambda issuer + JWKS; run records; snapshot builder; start/stop/read API; poller; streaming harness and bridge events; dispatcher log tailing + `job_events` + events API; fermentation assessment moved onto it. | Contract tests: start → events → report; stop; container failure; dispatcher restart mid-run; duplicate events; stale fencing rejected; revoked access blocks reads; non-allow-listed log lines dropped. |
| 2. UI (≈2 d) | Chat card, investigation view, review hand-off. | Screenshots and accessibility check against fixture events; one live run watched end to end. |
| 3. Hardening (≈2–3 d) | Egress test, quotas, cost display, evaluation on labelled cases. | A blocked host fails; p50/p90 time to first child event and run duration over ≥10 runs; supported-claim rate under qualified review. |

Measures: time from **Start** to first visible child activity; share of runs ending in a validated report within the deadline; stop latency; events lost or duplicated; reviewer time to verify; tokens per run. Set thresholds before Phase 3.

## 11. Open questions

1. **Child identity.** Can the Prime SDK pass its child id into the child kernel environment? Phase 0 answers it; the fallback is §4.4.
2. **Model provider and key** for the agent image (the runbook bakes provider configuration into an approved image).
3. **Data-path approval.** Who approves sending customer evidence to DigitalOcean (§7) before pilot use with real data?
4. **Droplet sizing** for 2 concurrent runs (the runbook limits are 2 CPU / 2 GiB per container); confirm after the Phase 0 measurements.

## 12. Interface contract (implementation reference)

### 12.1 Agent → dispatcher (container stdout, one JSON object per line)

`{"type":"investigation_event","local_seq":int,"at":ISO-8601,"kind":K,"agent_id":str|null,"parent_id":str|null,"payload":{...}}`

Only these kinds and payload keys pass; the dispatcher drops anything else, oversized lines (>8 KiB) and unknown keys. Strings are truncated as listed.

| kind | payload keys |
| --- | --- |
| `phase` | `phase` (planning \| investigating \| finalizing \| submitted) |
| `agent_started` / `agent_finished` | `depth`, `status`, `question` (≤300) |
| `agent_activity` | `status`, `tool`, `tool_use_count`, `token_count`, `model` |
| `allocation` | `task_ids` (≤16), `owner` (≤80), `reason` (≤300), `calls` |
| `subreport_saved` | `subreport_id` (≤80), `assessment` (≤500), `fact_count`, `claim_count`, `open_question_count`, `evidence_ids` (≤50) |
| `budget` | `tool_calls_used`, `tool_calls_limit`, `elapsed_seconds`, `tokens` |
| `error` | `code` (≤80) |

### 12.2 DigitalOcean API (added to `cloud_backend/api.py`)

`GET /v1/projects/{project}/jobs/{id}/events?after={seq}` → `{"events":[{"seq","attempt","at","kind","agent_id","parent_id","payload"}],"next":seq}` (≤500 per page; same authorization as `GET /jobs/{id}`). Job manifest gains optional `max_tokens`.

### 12.3 Platform API (Lambda)

| Route | Behaviour |
| --- | --- |
| `GET /.well-known/investigation-jwks.json` | Public RS256 key(s) for the executor's verifier |
| `POST /v1/investigation-runs` | `{objective, site_id, case_id?, conversation_id?, proposal_id?, dataset_ids?, record_refs?, budget?}`; a person with `propose`; builds snapshot, submits; returns run |
| `GET /v1/investigation-runs?case_id=&conversation_id=` | Owner/case-visible runs |
| `GET /v1/investigation-runs/{id}` | Run + `agents[]` + `budget` + `sync {updated_at, reachable, lag_seconds}`; syncs from the executor at most every 2 s |
| `GET /v1/investigation-runs/{id}/events?after=` | Timeline events |
| `POST /v1/investigation-runs/{id}/stop` | Owner; cancels |
| `GET /v1/investigation-runs/{id}/report` | Validated report, `review_status: requires_human_review` |

Run `status`: `queued | submitted | running | finalizing | awaiting_review | blocked | failed | cancelled`. Agent item: `{agent_id, parent_id, role: lead|investigator, question, status: running|waiting|done|failed, current_tool, tool_calls, tokens, started_at, last_activity_at, subreports[], attribution: exact|approximate}`. Budget: `{tool_calls_used, tool_calls_limit, elapsed_seconds, deadline_seconds, tokens, token_limit, cost_status}`.

Configuration (Lambda): `INVESTIGATION_EXECUTOR_URL`, `INVESTIGATION_EXECUTOR_AUDIENCE`, `INVESTIGATION_EXECUTOR_PROJECT`, `INVESTIGATION_SIGNING_KEY` (PEM), `INVESTIGATION_SIGNING_KEY_ID`, `INVESTIGATION_ISSUER`. When unset, `POST` returns 409 "Investigation execution is not configured" and the UI says so; nothing is simulated.

Chat: new operator `workspace_propose_investigation {objective, case_id?, rationale}` creates an `investigation_proposal` artifact. Only a person pressing **Start** calls `POST /v1/investigation-runs` with its `proposal_id`; the artifact then shows the run card.
