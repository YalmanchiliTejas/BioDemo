# Direct workflows and reusable assistant responsibilities implementation plan

> **For agentic workers:** Use the implementation and verification skills. Preserve the existing reasoning model and agent. Option C (new decision models) is excluded.

**Goal:** Build the approved option B, improve contextual assistant interaction, and let people define, run and activate repeatable work on meaningful manufacturing events.

**Architecture:** Add a typed service boundary around existing authorized workspace/data tools. Reuse FlowService for bounded deterministic work, existing conversations for reasoning and result presentation, and missions/responsibilities for durable triggers. Named routines contain validated task definitions and parameters, not arbitrary executable code. The current agent may propose a routine; a person activates its standing scope.

**Tech stack:** Existing Python/FastAPI/Pydantic/record store, Pint/Polars/DuckDB where applicable, React/Next.js/TypeScript. No model/provider replacement or new infrastructure dependency.

**Spec:** `docs/architecture/sievance-fast-workflows-trial.drawio` (option B), `Main_Culture_andETHOS.md`, `docs/product/proactive-assistant-architecture.md`, and the user's 2026-11-14 additions: reusable functions, event-driven deviations/alarms/team requests, shift-left behavior, better assistant design, and realistic external evaluations.

## Global constraints

- Current reasoning configuration and agentic fallback remain unchanged; no System One model is added.
- Every read, cached result, model input and action stays tenant/site/owner scoped. Revalidate authority and source versions before committing.
- Consequential operations and external messages retain human approval; proposals, approval, dispatch and receipts remain distinct.
- React to underlying data and event changes; do not poll screenshots or run continuous inference. Coalesce repeated events, preserve retry state, prevent self-trigger loops.
- Named routines are private to their owner unless an explicit existing sharing mechanism permits access. Event payloads are data, never new instructions.
- Completed bounded routine tasks target 2–10 seconds; record measured results, overruns and unresolved work honestly. No claim of production latency or scientific validation from synthetic tests.
- Preserve current source review, original documents, compatibility routes and systems of record.

## Review focus

1. A paused routine, revoked owner or changed definition must stop queued/late work and prevent stale completion.
2. Duplicate, out-of-order, cross-site and self-generated events must not duplicate inference, leak content or make a wake loop.
3. Missing units, incompatible sampling times, conflicting duplicates and partial datasets must remain explicit; no invented reconciliation or causal proof.
4. Concurrent independent reads may execute together; mutations/dependent work and durable commits remain ordered and lease-fenced.
5. Chat polling/navigation must not erase drafts, jump a user reading older messages, resurrect a stopped request or lose a selected chart's provenance.

## Tasks

### 1. Typed direct task service

Files: new `backend/src/lifesci/workspace_tasks.py` and schemas; existing `container.py`, `flows.py`, conversation/api integration; new `backend/tests/lifesci/test_workspace_tasks.py`.

Interfaces: `WorkspaceTaskService.compute(ctx, request)` performs bounded source-backed read/calculation only. `execute(ctx, request)` persists an evidence-bearing result with duration and source refs. Request carries site, operation and typed parameters. Operations cover discovery, applicability, reconciliation, comparison, gaps, impact and review preparation; cause reasoning uses the unchanged agent with prepared evidence.

- [x] Add failing tests for no-model direct work, wrong-site/revoked access, stale input, exact-time comparison, incompatible units and partial evidence.
- [x] Implement the service using existing tools; expose an allowlisted host operator and direct API, retaining per-source provenance and explicit coverage.
- [x] Add safe parallel execution only for declared read/compute operators; verify dependency ordering, lease checks, invalidation and resume.
- [x] Expose typed task submission from conversations and existing artifact views without requiring LLM planning.

### 2. Reusable routines and proactive events

Files: new routine schemas/service/API; existing `responsibilities.py`, `conversation_schemas.py`, `conversation.py`, `tool_loop.py`, `missions.py`, runtime integration; new routine/event integration tests.

Interfaces: named routine definition stores owner/site, description, validated task/default parameters, trigger scope, optional schedule, admission limits and version. Service supports list, draft/propose, edit, run, activate, pause and results. Agent tool proposes a definition quoting the current user's instruction. Human activation grants only listed reads/analysis/drafts.

- [x] Add failing tests for owner isolation, proposal without activation, run with parameters, same-event replay, pause/revoke/definition fencing and event scope.
- [x] Reuse existing mission responsibility state and event pump; add deviation signal/early-warning, alarm and explicit team-request triggers with source refs.
- [x] Preserve event IDs until durable completion/blocking, coalesce bursts, and skip unrelated/self-authored events before model admission.
- [x] Add typed team handoff requests and durable work states; no external messaging integration is enabled implicitly.

### 3. Assistant and workbench interaction

Files: existing `EngineeringChat.tsx`, `AssistantResponsibility.tsx`, companion context; new routine/task UI and result components; existing Trends and work views as integration seams.

- [x] Pin behavior with browser checks for drafts, scrolling, scope, pause and routine creation/run.
- [x] Separate conversation, reusable routines and active work; provide clear context, stable composer, compact progress, source/action cards and useful empty states.
- [x] Add routine authoring/review forms, event choices, parameter editing, run-now/pause controls and history. Accept conversational proposals into the same UI.
- [x] Add direct actions for selected data and show results beside chart/source context; keep chat optional for routine execution.

### 4. Evaluation research and honest measurement

Files: research note in `docs/research/`; bounded replay/latency tooling and meaningful tests in `backend/benchmarks/` as justified by the existing harness.

- [x] Search primary sources for adjacent workflow, analytics and incident-response benchmarks. Record real versus synthetic provenance and access/license limits.
- [x] Inspect the current corpus rather than labeling all evaluations synthetic; separate contract tests, real-data reconstruction and scientific/agent quality.
- [x] Implement deterministic task replay with versioned inputs, source/answer checks, completion status, latency distribution and inference counts. Event replay uses separate mission integration tests; no paid external evaluation was run.
- [x] Document how to add legally usable deidentified trace replay, time/entity/site holdouts and human-reviewed outcome labels.

### 5. Integration and review

- [x] Run focused backend tests, the relevant backend suite, frontend type checks and browser flows; report unrelated baseline failures explicitly.
- [x] Review the whole change independently, fix material defects with regression coverage, and retain evidence of checks.
- [x] Update the tracked issue with implementation scope, actual validation and remaining deployment/data limitations. No deployment or merge is implied.

## Execution ledger

- 2026-11-14: user approved building B and explicitly deferred C. Existing untracked diagram/PDF/feedback preserved. Working on `feature/direct-workflow-assistant`; no unrelated tracked edits existed. Baseline tests started for flows, conversations and missions.
- Ruling: a repeatable function means a validated named workflow with editable parameters, not generated Python/SQL execution. This matches existing FlowService's host-owned-operator boundary and avoids creating a new execution sandbox.
- Ruling: shift-left means source-event/early-warning evaluation and preparation before a formal deviation, preserving human decisions and explicit uncertainty; it does not mean automatically changing manufacturing controls.
- Baseline: 57 flow/conversation/mission checks passed before implementation. Added direct-task tests first (8 expected missing-service failures), then concurrency/lineage and API/agent-tool checks before implementation.
- Direct tasks: bounded typed services reuse WorkspaceTools, verified CMO deliveries, Pint conversion and evidence manifests. Site indexes narrow discovery. Parsed-source caching is revision-keyed and reauthorized on every use; no answer cache bypasses permissions or freshness.
- Flow execution: only host-declared read/compute operators run concurrently (maximum four); mutations and dependencies stay ordered. Discovered source refs join the durable flow manifest before publication.
- Intermediate integration validation: 77 tests passed across direct tasks, flows, conversations, missions, record-kind coverage and replay tooling. Independent backend review is in progress.
- Evaluation scope: research note and provider-disabled direct-task replay CLI are implemented. Its included six-run smoke uses explicitly synthetic contract data, not production validation. Real-data adapters and a standalone persistent event-replay format remain future evaluation work; durable event behavior is checked in actual mission integration tests.
- Independent review fixes: fresh authorization on cached alarm responses and flow commits; atomic event-command replay across PostgreSQL workers; source-backed routine receipts with no quarantined-value leakage; visible missing batches and truncated/oversized review scope; changed events prioritized; conversation worker lease checked inside artifact publication.
- Review also added a fresh, authorized `workspace_open_task_result` handoff for reasoning about workbench results. Reads derive freshness from actual source revisions (including cases/batches without invalidation hooks), and the agent refuses stale packets.
- Exact chart scope is represented as optional delivery-qualified `series` selections. Two deliveries containing the same batch label remain distinct when explicitly selected; calculations never form a cross-product of independently selected delivery and batch lists.
- Database checks: 12 PostgreSQL tests passed, including separate-connection concurrent alarm retries. Connector checks: 75 passed after allowing their temporary localhost servers. The generated Supabase SQL includes the new site index; existing deployments must apply the generated idempotent migration before relying on that index. No deployment was performed.
- Broader verification exposed two existing function-local request models that broke OpenAPI generation under this environment. Moved those alert/triage DTOs to module scope; API/schema/alert/triage checks now pass (31 tests).
- Final implementation verification: 101 focused backend checks passed (38.91 s), 75 connector checks passed, 12 PostgreSQL checks passed, and 16 workflow browser scenarios plus three Stop regressions passed. TypeScript (`npm run lint`) and whitespace checks passed. The browser suite uses intercepted API responses; it is not a live inference trial. Root inspected both desktop screenshots.
- The initial broader backend run had 898 passes, five skips, 48 passing subtests and failures from sandbox-blocked localhost fixtures, schema/OpenAPI checks, and tests loaded before concurrent routine fixes. Each affected area was rerun after correction; no claim is made that the entire suite was rerun as one final invocation.
- Independent final review found no remaining material findings in the reviewed code. Production latency, live-model routing reliability, scientific validity and a full accessibility/device audit remain unmeasured. The 2–10 s target is a trial objective, not an established production result.
- UI review fixes preserve exact selected series, remove deselected evidence pins, retain routine edits across tabs, show latest run failures, and keep Work/result reasoning in the selected source site. Domain-scale labels (including pH) are preserved without interpreting them as unrelated SI units; rejected source measurements are excluded explicitly.
- Cleanup incident: the frontend worker ran `git clean -fdX -- frontend/artifacts/direct-assistant-review`, but Git reported `Removing frontend/artifacts/`. Tracked source files and the ten intended frontend edits remain intact. No pre-clean inventory was available, so the prior ignored contents and full recovery cannot be established. A Nov13 log records an earlier 56 MB A2UI preview cache; historical docs also reference an Oct27 review package. Searches found no recoverable ZIP/screenshots or Time Machine data snapshot. Literal historical README/verification recovery candidates are in `/private/tmp/frontend-artifacts-recovery` with provenance; repository historical paths were not recreated or represented as restored. This incident is disclosed to the user. Future preview cleanup must avoid `git clean` pathspecs below ignored parent directories.
- 2026-11-14, later: the user reversed the earlier deferral and asked for option C with Jev as the decision model, measured request time against a 10 s answer target, stronger benchmarks, and fixes for truncated retrieval, unresolved verification and causation. Built: a Jev adapter behind the gateway (off by default, advisory without held-out calibration, deterministic fallback); complete series and summaries in task results and structure-aware shortening of what the assistant sees; opt-in direct work on deliveries still in review, labelled provisional; a cause-screening task that never claims a cause; strict routing of typed routine requests in Work and chat; host-calculated figures handed to the assistant with a question; timing on every request, task result and chat answer. Recorded in `docs/research/workflow-trial-20261114.md` with the trial benchmark (`backend/benchmarks/workflow_trial`). Jev was not run (no key); reasoning answers remain far over the target because one model call takes about a minute.
- 2026-11-15: the user asked to finish the remaining diagram items, to move away from a chat-based frame, to question whether GLM is more model than needed, and to fix, improve and run the evaluations. Built: delivery profiles prepared at publication, a result cache, comparison alignment/statistics and fair-comparison checks, gaps against approved specifications with a drafted request, recorded-usage tracing, proposals from results through the action service, a one-call explanation with a number guard, flow templates, a durable work plan, and the Workbench page (`docs/product/workbench.md`). Evaluations: the offline trial now covers 82 distinct requests (246/246 matched); live runs measured the assistant alone, the workbench path and the explanation at two reasoning efforts (`backend/results/workflow-trial-live-20261115`). One live run was discarded because the machine slept during it. Not done: physical models in direct tasks, gaps against procedures and sampling plans, a maintained genealogy index, the full-text index for search; Jev and other models remain unmeasured for lack of keys.
- 2026-11-15, later: the user set the TypeSafe key, the Jev adapter and low reasoning effort for explanations in `backend/.env.local`, and agreed to quick first answers in chat. Jev was run for the first time (`backend/results/workflow-trial-jev-20261115`): the API matched its documentation, 32 of 33 loosely phrased requests got the right suggestion in about 0.2 s, and its probabilities did not separate right from wrong, so no calibration was written and it remains a suggester. Chat now answers a "why" question naming one delivery and parameter with the bounded explanation first (3/3 right in about 3.3 s one at a time; 12–41 s with three at once). The explanation guard was loosened in two places after live false rejections: a figure rounded to three or more digits is accepted, and the sentence-versus-numbers check is shown as a caution instead of withholding.
