# Deviation signals, alerts and the agent that responds

Status: **design and build plan, 2026-11-05.** Governing direction: [the four pillars](../../Main_Culture_andETHOS.md). Extends the [proactive assistant contract](../product/proactive-assistant-architecture.md).

## 1. Job and current state

QA and production need to learn about a possible deviation as soon as the data shows it, with the evidence gathered and the next step ready, without watching screens. Verified in code (2026-11-05):

- **No automatic raising.** Deviation `case` records are opened only by a person (`POST /v1/quality/cases`).
- **Detectors stop at a flag:**
  - Step-execution out-of-limit creates `exec_exception` / `exec.exception` (`execution.py:341-375`, `lab.py:214`), and nothing consumes it.
  - Lab `limit_evaluation` is not in the `lab.result_recorded` payload.
  - QMS deviations imported by connectors become plain evidence (`evidence.ingested` carries no source or record type).
  - CMO `RANGE` checks are physical-plausibility checks, not GMP specifications.
- **No specification store for live data.** Only procedure step limits and per-result lab limits are enforced. `science.detect_emerging_concern` (Western Electric, EWMA, CUSUM) exists but nothing calls it with stored limits.
- **Alerting is built but unwired.** `collab.py` has `TriggerService`, `NotificationService` and Slack/Teams/email/SMS adapters, tested but not created by the container. There are no routes, no recipients or preferences, and no in-app inbox.
- **The agent can be woken** by mission subscriptions (`missions.deliver_events`, 1 s runtime pump) and assistant responsibilities. No event is turned into a responsibility automatically.

## 2. Principles applied

- **A system detects; a person declares.** Detection creates a **deviation signal** with its evidence. Opening a formal deviation case stays a human decision: one click, pre-filled. This keeps the QMS as the system of record (Adopt) and the human authorization explicit (Trust).
- **Early warning is distinct from out-of-spec.** Trend rules (EWMA/CUSUM/run rules) raise `warning`. A value beyond a specification limit raises `action`. Critical limits or QMS-recorded deviations raise `critical`. Labels say which rule fired; there are no confidence scores.
- **Alerts go to people through channels an organization admin configured.** That configuration is the standing authorization. Agents never send messages; they propose.
- **One assistant, many capabilities.** It is the same agent, memory, rules and permissions. Capabilities are packs of tools and instructions selected by the task and the user's role, not separate agents.

## 3. Design

### 3.1 Specifications (new `specification` records)
`{spec_id, site_id, parameter, unit, product_id?, equipment_id?, low?, high?, critical_low?, critical_high?, trend_rules: bool, source (procedure|document|manual), approved_by, version, effective_from}`. Created by a person with `approve`. They can be seeded from procedure step limits. Versioned; a signal records the spec version it used.

### 3.2 Detection → `deviation_signal` records
Sources, all feeding one `SignalService.raise_signal(ctx, source, site_id, kind, severity, subject, evidence_refs, details)`:
1. `exec.exception` events (step execution out of limit) → `action`, or `critical` when the step had `hold_on_out_of_limit`.
2. `lab.result_recorded` where `limit_evaluation` fails (the payload is enriched with the outcome) → `action`.
3. Live intake: historian/LIMS values matched to a specification by parameter, site and equipment. Above `high` or below `low` → `action`; beyond critical → `critical`; trend rules on the recent series → `warning`.
4. Connector QMS records whose record type is deviation/nonconformance → `critical`, linked to the external record id (the QMS stays the record).
5. CMO delivery values against specifications, at verification → `action`.

**Coalescing:** one open signal per `(site, parameter, subject [batch/equipment], rule)` within 24 h. Repeats append evidence and bump `occurrences`; they don't re-alert unless severity rises. The lifecycle is `open → acknowledged → case_opened | dismissed (reason required)`. Events: `signal.raised`, `signal.escalated`, `signal.updated`.

### 3.3 Alerts
- **Channels** (`alert_channel` records, admin-only): in-app (always on), email (SMTP), Slack webhook, Teams webhook. SMS/WhatsApp adapters exist but are left out of v1. Secrets are stored encrypted with the existing connector credential key.
- **Routing** (`alert_route` records, admin-only): `{site_id|all, min_severity, roles[], channels[]}`. Default: `critical` and `action` go to the site's `qa` and `supervisor` in-app; email/Slack once configured.
- **Delivery** uses the existing `NotificationService` (idempotency key = signal id + severity + recipient + channel; retries; receipts). An inbox (`notification` records per recipient, read/unread) feeds a bell in the app header.
- **Alert body:** severity, what fired (rule, value, limit, spec version), subject, time, a link to the signal, and the assistant's triage once ready. External channels carry IDs and a link only, never document text.

### 3.4 The assistant responds (auto-triage)
- **Trigger.** On `signal.raised` or `signal.escalated` at or above the site's `auto_triage_min_severity` (default `action`), the system starts a **background triage turn** with the single assistant. It owns a site-level responsibility (`triage` mission) in a dedicated conversation per signal, owned by the routed QA person.
- **What it does: read-only.**
  - It follows entity links (batch, lot, equipment, materials) and pulls the series around the event.
  - It checks trend context, finds similar closed cases and lists missing evidence.
  - It writes a triage note: observations, competing hypotheses, unknowns.
  - It **proposes** next steps: open a deviation case (pre-filled), start a multi-agent investigation, request evidence. A person decides each one.
- **Limits:** a per-site daily cap on auto-triage runs (default 20), the existing tool and time budgets, and a `paused` switch per site. When a cap is hit, the signal says "triage skipped: daily limit" instead of silently not running.
- Alerts are sent immediately and updated with "triage ready" when it finishes, so nobody waits on the model.

### 3.5 One agent, capability packs
A registry (`capabilities.py`) of packs, each holding `{id, description, operators[], instructions, required_permission}`:

| Pack | Covers (Apprentice equivalents) | Tools |
| --- | --- | --- |
| `quality` | Quality and Quality Systems | signals, cases (read, propose open, timeline), claims, QA package, similar cases, investigations |
| `process` | MSAT and Engineering | entity links, series and trends, physics/bioprocess models, tech transfer |
| `operations` | Operator and Supervisor | procedures (read SOP steps), execution status, shift summary of signals |
| `materials` | Supply chain | lots, reconciliation from connectors |
| `equipment` | Maintenance | equipment history from links and signals |

The planner gets the packs relevant to the request, the user's role and the attached context; the always-on core is search, read and rules. It's one conversation, one mission and one audit trail. If a task needs a pack the user lacks permission for, the assistant says so.

## 4. Build split (no overlapping files)

| Part | Owns | Exposes |
| --- | --- | --- |
| A. Detection | new `lifesci/specifications.py`, `lifesci/signals.py`; event enrichment in `execution.py`, `lab.py`, `integrations.py`, `source_verification.py`, `evidence.py` (payload only); CMO spec check | `SpecificationService`, `SignalService`, `register_signal_listeners(platform)`; routes via `signal_routes(app, platform, ctx_dep)` |
| B. Alerts | new `lifesci/alerts.py` (wires `collab.NotificationService`, channels, routes, inbox); frontend bell + inbox + admin settings page | `AlertService.on_signal(signal)`, `alert_routes(app, platform, ctx_dep)` |
| C. Agent | `process_engineering/*`, new `lifesci/capabilities.py`, `responsibilities.py`; frontend signal and triage views in chat and on a Signals page | `TriageService.on_signal(signal)` |

Container, API and runtime wiring (`container.py`, `api.py`, `runtime.py`) is done once at integration. A signal is raised, then `AlertService.on_signal`, then `TriageService.on_signal`, all through the store event subscription and runtime tick, idempotently.

## 5. Measures

Time from data arriving to signal; to first alert delivered; to triage ready. Signals per site per day and the dismissal rate (noise). The share of signals that become cases. Duplicate alerts, which should be 0. Auto-triage runs and tokens per day.

## 6. Shared contract

`deviation_signal` record state:
- **Identity:** `signal_id`, `site_id`.
- **What fired:**
  - `kind`: step_exception | lab_oos | spec_excursion | trend | qms_deviation | delivery_excursion
  - `severity`: warning | action | critical
  - `rule`: human-readable, e.g. "DO 24 % < low 30 % (spec SPEC-DO-1 v2)"
  - `parameter?`, `value?`, `unit?`, `limit {low?, high?, critical_low?, critical_high?}?`, `spec_ref {spec_id, version}?`
- **Subject and evidence:** `subject {kind, id}` (batch, equipment, lot or sample), `evidence_refs[]`, `source {system, record_id}?`.
- **History:** `occurrences`, `first_at`, `last_at`, `status` (open | acknowledged | case_opened | dismissed), `dismiss_reason?`, `case_id?`.
- **Follow-up:**
  - `alerts {sent: n, last_at}` (written by AlertService)
  - `triage {status: pending|running|ready|skipped|failed, reason?, conversation_id?, turn_id?}` (written by TriageService)

Events `signal.raised` / `signal.escalated` / `signal.updated` carry `{signal_id, site_id, severity, kind}`. Routes: `GET /v1/signals?site_id=&status=&min_severity=`, `GET /v1/signals/{id}`, `POST /v1/signals/{id}/acknowledge`, `POST /v1/signals/{id}/dismiss {reason}`, `POST /v1/signals/{id}/open-case {owner_id, qa_reviewer_id}` (person; calls `CaseService.open`, links the case), `GET/POST /v1/specifications`. Alerts: `GET /v1/notifications` (mine), `POST /v1/notifications/{id}/read`, `GET/POST /v1/alert-channels`, `GET/POST /v1/alert-routes` (admin), `POST /v1/alert-channels/{id}/test`.
