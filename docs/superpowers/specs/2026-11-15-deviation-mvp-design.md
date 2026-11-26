# End-to-end deviation and investigation MVP

Binding request: the user's 2026-11-15 implementation prompt, sections 1–14 and acceptance scenarios A–F. This document records implementation choices, not a new request for design approval. The user explicitly directed inspection followed by implementation. Governing source: `Main_Culture_andETHOS.md`.

## Job and constraints

Engineers need to move from observed manufacturing risk to inspectable scientific work. MSAT needs evidence, hypotheses, model results and impact assessment. QA needs controlled local review and a complete handoff to its actual quality system. Existing services and direct controls remain available; chat is optional.

Preserve existing features, authentication, permissions, local data and benchmark artifacts. Do not touch configured customer databases or manufacturing controls. Tests use isolated stores and clearly synthetic data. No outside messages, deployment, commits or pushes during this task. No invented citations, default scientific inputs, simulated external approvals, or compliance claims.

## Existing implementation

The preceding read-only audit traced event-driven SignalService, specifications, alerts/triage, connectors, versioned evidence, Workbench/Trends, EngineeringConversationService, Prime executor, model catalog/library, minimal CaseService and quality artifacts. Gaps: signal units/time windows; no integrated case review lifecycle; sparse associations; impact/actions absent from workspace; model tools not wired into normal investigations; QA transfer drops evidence links; investigation list response mismatch; citation inspector uses fixtures. Baseline targeted quality/signal/investigation tests: 54 passed.

## Approach and trade-offs

Chosen: extend existing `case` records with a versioned local workflow, references to existing evidence/claims/model runs, and dedicated API/UI orchestration. Use RecordStore transactions, revisions, audit/outbox, missions and runtime. No new database or parallel case identity.

Alternative: only repair the investigation report screen. Smaller but cannot meet impact, triage, review/return or recurrence requirements. Alternative: replace execution with a new workflow stack. Rejected because existing runtime, numerical tools, evidence and permissions provide the needed foundations and replacement threatens working features.

Start: standard buttons and existing data discovery. Trust: immutable review snapshots, explicit gaps and source revisions. Act: named actions, review outcomes and pending handoff. Adopt: existing auth, source systems, chart/viewer components and routes; local review is never official eQMS approval. Added workflow state increases surface area, so enforce transitions centrally and exercise role/retry/version boundaries.

## Domain and execution

- Signals remain distinct from quality events and formal deviations. A person records triage: no formal deviation with reason, more evidence, local deviation preparation, or reference to an existing external quality record.
- Extend `case` with discovery source, category, priority, scope, batch/equipment/product/material associations, initial risk, immediate actions, owner/reviewer/deadline and local workflow state. Legacy cases remain readable. Generic legacy closure cannot bypass controls for a managed case.
- Persist evidence requests, hypotheses, impact drafts, corrective actions, review submissions/decisions and activity as versioned records linked to the same case. Approved local snapshots cannot silently change; source corrections require fresh review.
- Deterministic assembly retrieves only authorized local records and configured connector status. Missing records remain gaps with a responsible person. Build chronology and extent-of-condition from explicit identifiers; ambiguous relations are candidates, not established impacts. Preserve source revisions/originals. Bound query output and label truncation.
- Reuse a durable mission for background case preparation and follow-up. Work is permission checked and idempotent; meaningful source changes queue fresh drafts while retaining reviewed versions. No inference while waiting. Existing task runner/runtime drives work independent of browser sessions.
- Structured science: evidence/timeline, hypotheses with support/counterevidence/assumptions, applicable registered models, observed-versus-predicted comparison, unresolved/technical assessment. Models run only with explicit source-backed configuration. User/agent hypotheses are not automatically confirmed. Retain Prime for open-ended work, human start approval and pinned snapshot.
- Impact draft lists matched batches/products/equipment/materials, quality results, distribution status and unknowns. Human assessment/disposition is distinct from automatic candidates.
- Corrective actions distinguish immediate correction from CAPA, with owner/due date/evidence/change control/status/review history. Recurrence creates an effectiveness concern, never an automatic conclusion of failure/success or new formal deviation.
- Local workflow: awaiting triage / investigation assigned / in progress / waiting for evidence / technical review / QA review / returned / handoff pending / handed off. No official GMP-approved label. Local QA review binds to a complete content fingerprint and records actor/reason. External completion requires a real authorized receipt, otherwise export remains pending external approval.

## UI

Add a connected Quality workspace using existing shell/navigation and role context. Engineer: risk/event queue and chart links. MSAT: timeline, hypotheses, source/model inspection and impact. QA: assignment, completeness, returns/review, actions and export. One case workspace with role-appropriate emphasis and enforced backend permissions, not three duplicate apps.

Connect signal and chart context to manual case/investigation initiation. Preserve all old routes and capabilities. Replace fixture lookup on real investigation citations with authorized source retrieval. Keep synthetic examples labeled.

## Validation

All six scenarios run through real services/API with isolated synthetic data: A excursion→handoff; B OOS preliminary lab review→expanded investigation; C cross-batch deterioration without automatic deviation; D missing calibration→request→new evidence→resume; E QA return→new revision→resubmission with immutable prior review; F recurrence→prior action/effectiveness concern. Include unauthorized roles, stale snapshots, duplicate delivery/retry, late observations, unit mismatch and unknown external outcomes. Browser verification uses actual local API, not fulfilled responses. Live LLM calls, if needed, are separately bounded and reported; deterministic acceptance does not establish model accuracy or customer qualification.
