# Mission evaluation implementation audit

2026-11-02. Target: local `main`, isolated worktree `/private/tmp/biodemo-main-evals`.
Specification: `Sievance_Agent_Evaluation_Complete_README.md` supplied in the research checkout.
This audit precedes adding evaluation dependencies.

## Existing entry points and boundaries

- User messages: `process_engineering/api.py` calls `EngineeringConversationService.create/enqueue/run_turn`. The service executes bounded, persisted gateway/FlowService rounds; it is the evaluation target, not Prime's separate research harness.
- Ingestion: `EvidenceService.ingest` preserves bytes, metadata and versions and emits committed `evidence.ingested/corrected` events. Case, batch and laboratory services also emit events.
- Background: `Runtime._committed` delivers committed events to mission subscriptions; `Runtime.tick` polls connectors, replays events and runs the local mission coordinator. `AssistantResponsibilities.run` initiates actual background conversation turns. No evaluation-owned reasoning loop is necessary.
- Scheduling: mission obligations and `Runtime.tick` share `ids.utc_now`. A context-local clock provider can control their comparisons and recorded timestamps without replacing the scheduler. Monotonic elapsed-time budgets must remain real.
- Tool completion: FlowService persists results. General external tool-completion subscriptions are not currently exposed by the assistant: NOT_IMPLEMENTED until a concrete production event mapping exists.

## State, retrieval and tools

- RecordStore uses SQLite/Postgres with transactional outbox, audit, inbox, leases and versioned records. File-backed SQLite permits a fresh worker process with only persisted state.
- Missions retain objective, constraints, corrections, rejected hypotheses, pending decisions, remaining work, subscriptions and checkpoints.
- Conversations currently create a new mission each time. Add an authorized optional mission association for a genuinely new conversation; do not simulate sessions by relabeling one transcript.
- WorkspaceTools searches authorized typed records using literal queries and descending timestamps. It returns record-level ranked IDs, not embedding chunks. Report record Recall@5; chunk recall is NOT_TESTABLE on this path.
- `workspace_read` checks tenant/site/owner/current revision and fetches original evidence. Saved assistant answers are labeled interpretations. Action drafts require sources inspected in the current turn.
- Tools are registered typed operators: workspace search/read/proposal and existing numerical/bioprocess operations. No general terminal or arbitrary code. Existing ActionService keeps proposals, approvals, intents and dispatch distinct.
- Cross-session memory currently has searchable private prior turns and durable corrections, but not a reviewed fact-memory retirement store. Test these separately; do not claim fact consolidation from a good answer.
- Background turns currently publish an in-app reply for every admitted source event. Selective notification/materiality is a product gap to expose through negative controls. Existing NotificationService requires explicit authority for external delivery. Evaluation must never send email/Slack.

## Observability and isolation

- Existing model_run, data_flow_run and evidence artifacts record gateway attempts, tool inputs/results and lineage. No Langfuse/DeepEval dependency or duplicate OTel instrumentation was found in this path.
- Add optional application telemetry with local structured observations and supported Langfuse observation APIs. Persist queue correlation; actual remote IDs/URLs only when SDK export is configured. No raw model reasoning is logged. Synthetic content may be captured only with explicit evaluation configuration; production telemetry defaults to metadata.
- Each case/variant/repetition uses a fresh SQLite database and synthetic tenant/site, roles and sink-only evaluation artifacts. No production URL or connector configuration is inherited. Hidden YAML expectations stay outside ingestion, provider prompts and tool-accessible records.
- Default CLI uses real providers if configured; otherwise reports NOT_TESTABLE, never a scripted provider pass. Scripted providers are confined to pytest contract tests and labeled accordingly.

## Decision and trade-offs

Job: make the actual assistant's persistent work, choices and failures measurable across sessions and simulated days.
Use a thin Python adapter over current services rather than adding orchestration/memory infrastructure. This reduces setup (Start), preserves source/state evidence (Trust), grades durable progress (Act), and reuses storage and permission boundaries (Adopt). Controlled synthetic worlds improve repeatability but do not establish scientific validity, usability in a factory, or compliance.

Langfuse and DeepEval are optional evaluation dependencies, not required application imports. Missing credentials/export/judges are explicit coverage gaps. Keep deterministic hard gates authoritative and allow valid alternative tool trajectories. Detailed execution evidence and outstanding work are written by the CLI, not assumed by this audit.

## Integration hardening after the frozen campaign

The live campaign was frozen at `9127ad6`. Later contract tests exposed two integration issues in the new checkpoint path: overloading compaction's textual `summary`, and replacing unrelated `remaining_work`. The implementation now uses `assistant_assessment_ref`, replaces only its own previous next action, and retains finding history for the existing compactor. Both issues have focused regression tests. Grader hardening bounds numeric recall, avoids treating a negated causal claim as an affirmative one, examines the new approval answer, counts artifact-only in-app publications, and accepts multiple legitimate durable progress artifacts. Replays label these grader changes without claiming new model trials.
