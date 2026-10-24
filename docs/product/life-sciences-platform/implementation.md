# Implementation guide

Built 2026-10-23 in `backend/src/lifesci/`. This explains what exists, how to run it, how it maps to the [architecture](architecture.md), what was measured, and what is still missing. Decisions D29–D44 in the [decision log](decision-log.md) record the implementation choices; per-capability status and evidence are in the [checklist](capability-checklist.md).

## Review follow-up — 2026-10-24

The repository review identified cross-site evidence updates, derived-list access,
site-specific approval revocation, unchecked outcome evidence, missing runtime
event routing, unexecuted configured obligations, and hidden approval payloads.
These paths now have fixes and regression coverage. The runtime routes committed
events and recovers missed delivery through tenant-scoped polling; configured
obligations generate reviewable drafts or report blocked work. This does not
enable unqualified model routes or authorize manufacturing actions.

Configured connector support and the connected Sources page now cover REST,
file exports, signed webhooks, MQTT and OPC UA, with family mappings for existing
systems. See [connection setup, contracts and limits](connectors.md). Vendor/device
qualification remains separate, so the capability completion counts below are
not increased by these transport additions. The test count below records the
original 2026-10-23 baseline; the follow-up suite adds security, runtime and real
client protocol regression tests.

## Status at a glance (2026-10-23 baseline)

For the subsequent suite API, connected UI and versioned flow expansion, see
[the suite baseline](suite-baseline.md). Its documented gaps remain separate from
the historical capability acceptance counts below.

| | Count |
| --- | ---: |
| Capabilities implemented **and** verified against their full acceptance condition | 63 / 77 |
| Capabilities with partial implementation (unchecked; gap stated in the evidence column) | 14 / 77 |
| Assessment records written ([assessments](assessments.md)) | 12 / 12 |
| Assessment records verified (LS-044 by test; others await product/QA sign-off) | 1 / 12 |
| Tests in `backend/tests/lifesci/` (all passing; includes 4 against a real local PostgreSQL 16, 5 against Temporal's time-skipping server and 1 cross-module end-to-end scenario) | 269 |

"Verified" means an automated test in this repository demonstrates the acceptance condition in a development environment. It is **not** customer qualification, validated accuracy, or a compliance claim. Simulated systems (fake REST server, in-memory MQTT/OPC UA clients, fake media provider, fake model provider) are named in each row's evidence.

## Run it

Local configuration lives in `backend/.env.local` (git-ignored; copy `backend/.env.local.example`). The CLI loads it automatically, and real environment variables override it. Set `LIFESCI_ENV_FILE` to load a different file.

```bash
cd backend
.venv/bin/python -m pytest tests/lifesci -q          # includes connector/runtime regressions; PostgreSQL tests auto-skip without initdb/pg_ctl
.venv/bin/python scripts/lifesci_load_smoke.py       # single-process latency smoke (see below)
.venv/bin/python -m src.lifesci serve --seed-demo --port 8100   # synthetic tenant demo-northfield
# Durable missions: start a Temporal server, then
#   TEMPORAL_ADDRESS=127.0.0.1:7233 .venv/bin/python -m src.lifesci worker
#   TEMPORAL_ADDRESS=127.0.0.1:7233 .venv/bin/python -m src.lifesci serve
# (both processes share LIFESCI_DATABASE_URL; install with `pip install -e '.[orchestration]'`)
# Local PostgreSQL (default for the current development setup):
#   createdb biodemo_lifesci
#   # fill the owner and runtime URLs in backend/.env.local (see .env.local.example)
#   .venv/bin/python -m src.lifesci db-migrate
#   .venv/bin/python -m src.lifesci seed-demo
# db-migrate creates/updates the non-owner app role, applies schema, RLS and triggers,
# and verifies the runtime connection. Set LIFESCI_DB_MIGRATE=0 so the app never
# attempts DDL. PostgreSQL binds to localhost only in the development setup.
# Model providers are enabled only when ANTHROPIC_API_KEY / OPENAI_API_KEY are set, and a task kind is
# routable only after an evaluation is recorded with ModelRegistry.qualify(...).
```

Development API calls send `X-Tenant-Id` and `X-Actor-Id`; roles always come from stored assignments (`IdentityService.assign_role`). With `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `DEPLOYMENT_TENANT` set, the API uses the existing `cloud_backend.auth.Verifier` instead.

### Local PostgreSQL (current development setup)

The running development app uses PostgreSQL 16 on `127.0.0.1:5432`, bound to localhost only:

- Database `biodemo_lifesci`, owned by the local PostgreSQL user.
- Runtime role `lifesci_app` (`LOGIN`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`, `NOBYPASSRLS`), so row-level security applies.
- `backend/.env.local` holds `LIFESCI_MIGRATION_DATABASE_URL`, `LIFESCI_DATABASE_URL`, `LIFESCI_APP_ROLE=lifesci_app` and `LIFESCI_DB_MIGRATE=0`. It is git-ignored and holds the app password.
- `db-migrate` applies the schema, RLS policies and append-only triggers, then verifies the runtime connection.
- `seed-demo` writes the clearly labelled synthetic tenant `demo-northfield` (one mission, three evidence records, people and ownership configuration).

To recreate the database from scratch:

```bash
dropdb biodemo_lifesci && createdb biodemo_lifesci
# keep the existing runtime password or set a new one in backend/.env.local
cd backend && .venv/bin/python -m src.lifesci db-migrate && .venv/bin/python -m src.lifesci seed-demo
```

The previous SQLite file (`.cache/lifesci-dev.db`) is untouched and remains an offline fallback; point `LIFESCI_DATABASE_URL` at `sqlite:///.cache/lifesci-dev.db` to use it. No database is exposed beyond localhost.

## Module map

| Module | Architecture section | Responsibility |
| --- | --- | --- |
| `store.py` | Data ownership | Versioned aggregates, append-only revisions and audit, transactional outbox/inbox, leases with fencing tokens, dependency edges, secondary indexes, content-addressed originals. SQLite or PostgreSQL (RLS + append-only triggers). Nested transactions join the outer one. |
| `identity.py` | CORE | Role policy, revocable role assignments, explicit expiring grants (partners), derived-artifact authorization over every contributing source; agents cannot take consequential actions. |
| `ownership.py` | CORE / ADR 0001 | Record-ownership registry: external / native / projection per record class and site; write scope and approval reference enforced before any write. |
| `records.py` | ASSURE | Signatures bound to record revision + content hash with authentication method; verification and required-signature checks. |
| `evidence.py` | INT / AGENT | Original bytes + digest + source revision + mapping version; normalized values with lineage; derived artifacts with input manifests; transitive invalidation with per-kind rules; quarantine. |
| `actions.py` | QUAL / Easy to Act | Proposal → version-bound approval → action intent → fenced dispatch with preflight (content, basis, approver authority, ownership) → reconciliation of unknown outcomes → observed outcome → effectiveness assessment gated on the named follow-up measure. |
| `gateway/` | AGENT / model routing | Registry (profiles, task policies, evaluation-gated qualifications), router, hierarchical budgets, provider adapters (Anthropic, OpenAI, fake), gateway run loop with validation, repair, escalation, circuit breaker, cache with permission/freshness recheck, and descendant-aware traces. |
| `orchestration/` | AGENT / D09, D45 | Temporal workflow per mission (signals, durable obligation timers, continue-as-new), delegated-agent activities, `TemporalScheduler` port implementation with backlog, `verify_replay` upgrade gate. |
| `devseed.py` | Development | Clearly labelled synthetic tenant for running the UI against the real API. |
| `missions.py` | AGENT / ADR 0003 | Persistent missions, obligations, decisions, corrections, fenced checkpoints, child merges, budget pause, bounded context, compaction, cursor stream. |
| `workqueue.py` | Speed and scale | Urgent lane, tenant-fair scheduling, ceilings, fan-out limits, backpressure, restart recovery, queue-age metrics. |
| `roles.py` | AGENT | Nine operational role skills; effective scope = skill ∩ person ∩ agent limits. |
| `prime_adapter.py` | AGENT / D08 | Existing Prime harness receives its model from the router; cost recorded in the same budget/trace. |
| `procedures.py` | PROC | Shared procedure engine (recipes, instructions, lab methods): validation, safe calculations, branches/parallel, templates, review-gated publication, pinned instances, amendments with redlines and N/A, site adaptations, document interpretation drafts with source spans. |
| `execution.py` | EXEC | Orders, lots, equipment readiness, guided step execution with limits/calculations/signatures, authority-loss pause, offline provisional drafts, eBR with review-by-exception coverage, release only via proposal, maintenance preparation. |
| `lab.py` | LAB | Lab methods, idempotent sample registration, aliquots, plate maps, chain of custody with auditable corrections, result release lock, instrument/reagent readiness. |
| `integrations.py` | INT | Versioned connector contracts and qualification matrix, incremental intake with cursors/gaps/late data/schema drift, mapping templates and preview, webhook HMAC intake, MQTT/OPC UA adapters over a transport port (control writes prohibited), site collector spool, ERP reconciliation and write-back via intents, signed replayable subscriptions. |
| `science.py` | SCI | I-MR/Western Electric/EWMA/CUSUM, emerging-concern detection, cohort comparison with stage compatibility and confounders, yield, OEE, 4PL, qPCR, chromatography, DOE, liquid-handler CV, Z′, PSI drift monitoring; registered as C0 gateway handlers. |
| `quality.py` | QUAL | Claims by class with counterevidence status, editable cited forms, QA field return with dependent invalidation, prior-investigation reuse approval, QA review package bound to content hash, coverage, draft artifacts. |
| `network.py` | NET | Site-scoped views, rollout diffs and QMS reconciliation, template distribution, transfer packages with recipient checklist, partner sharing with revocation and export quarantine, lifecycle readiness linked to source revisions, constraint-checked scheduling proposals. |
| `collab.py` | COLLAB | Event/schedule/alarm/file-change triggers, channel adapters, notification delivery records with unknown-outcome reconciliation, procedure-timed initial and follow-up notices, remote sessions with access checks, consent and annotations. |
| `assurance.py` | ASSURE | Signed scoped export, verified restore, retention and legal hold, requirement→test qualification trace from JUnit, deployment plans, release notices, incidents, degraded-mode report. |
| `api.py`, `container.py`, `__main__.py` | Interface contracts | `/v1` HTTP API with idempotency keys, cursor pagination, explicit error mapping, event replay; composition root. |

## How a request flows (example: drift → recommendation → action)

1. A historian window arrives through `integrations.IntakeService.sync` → `evidence.ingest` (original bytes, digest, cursor committed after the batch).
2. A mission subscribed to `evidence.` events is woken by `missions.deliver_events` (coalesced; event ids kept).
3. The coordinator activates (lease + fencing token), calls `gateway.run(task_kind="statistics")` → C0 `science.detect_emerging_concern` (no model, zero model cost).
4. For explanation it calls `gateway.run(task_kind="comparison_explanation")`, which routes to the cheapest **qualified** profile; output must cite only supplied sources.
5. The result becomes a derived artifact and an `actions.propose(...)` recommendation with rationale, owner, follow-up measure and basis revisions. Agents cannot approve it.
6. A qualified person approves the exact revision; an intent is queued. If the historian value is later corrected, the proposal turns stale and the queued intent moves to `awaiting_reassessment` before dispatch.
7. Dispatch passes preflight, claims a fencing token, writes through the owning system's connector; a lost response is reconciled by idempotency key, never blindly resent.
8. The observed outcome is recorded separately; effectiveness can be assessed only once evidence for the named measure exists.

## Measured (not capacity claims)

`scripts/lifesci_load_smoke.py --n 2000`, single process, in-memory SQLite, developer laptop, 2026-10-23:

| Operation | Before D33 index | After |
| --- | ---: | ---: |
| Evidence ingest p50 / p95 | 0.22 / 0.85 ms | 0.16 / 0.27 ms |
| Partner grant check with 2,000 grants p50 / p95 | 35.4 / 60.6 ms | 3.6 / 5.6 ms |
| Propose + approve p50 / p95 | 1.98 / 5.42 ms | 1.01 / 1.63 ms |
| Correction invalidating 202 dependents | 43.8 ms | 29.2 ms |

These show relative behavior of code paths only. They do not include network, PostgreSQL latency, concurrency, or model inference, and they do not establish the workload targets in [delivery and verification](delivery-and-verification.md).

## Known gaps (also tracked as unchecked rows)

- **Durable orchestration (D45):** Temporal is implemented and tested against the SDK's time-skipping server and a local dev server. The runtime now replays the backlog for configured tenants. Not yet done: a production Temporal deployment (cluster or Temporal Cloud), TLS/namespace configuration, and replay checks wired into CI with recorded production histories.
- **Multi-process dispatch (D41):** the work queue's selection index is per process.
- **Devices and live systems:** no mobile/hands-free execution, vendor MQTT broker, vendor OPC UA server, ERP, QMS, LIMS, media transport, or messaging provider has been qualified (LS-004, LS-008, LS-022, LS-023, LS-038, LS-088). Real MQTT/OPC UA clients now have local protocol/server tests; these do not establish vendor interoperability.
- **UI:** the React workspace now has a connected mode on `/v1` (missions, notes, proposals, role-gated approvals with exact payloads, outcomes, recurring-work status, health notice and connector setup/preview/sync in Sources; see `frontend/docs/design/connected-mode.md`) alongside sample mode. Not yet in the UI: corrections, answering mission decisions, proposal revision, effectiveness assessment and scientific visualization (LS-030). Connector mappings support advanced JSON configuration; a visual mapping editor and qualification administration remain future work (LS-041). Sign-in is development headers until OIDC is configured.
- **Model qualification:** no task kind is qualified by default. Real evaluations against labeled data are required before any model route is enabled in production; the router refuses otherwise.
- **Prime cost coverage:** Prime child-session usage remains incomplete (`prime_root_session_only`).
- **Recovery objectives, support guides, in-flight upgrades:** LS-049, LS-082 need customer RPO/RTO and operational artifacts.
- **Assessments:** 11 records await product/QA sign-off.
- **Pre-existing failures outside this package:** `tests/test_case_comparison.py` has 2 failures that need a recorded pilot under `backend/runs/cho-comparison`, which is empty in this checkout. They are unrelated to `lifesci`.
