# Delivery and verification

This is a build sequence for the complete [capability checklist](capability-checklist.md). Phase labels express dependencies rather than promised dates. Each row retains implementation and verification evidence separately. Existing code references are foundations, not proof that the full capability is complete.

## Phase 0 — Shared contracts and production foundations

Define record ownership, canonical identifiers/revisions, permission scopes, task/context envelopes, action intents and approval binding. Extend PostgreSQL domain/outbox schemas and authenticated API paths; add isolation policies and source/object access checks. Implement the model gateway's routing, metering, budgets and version registry. Persist mission/session artifacts independently of workers. Configure durable orchestration and run a crash/recovery test before integrating operational workflows.

Reuse `backend/src/cloud_backend`, `src/manufacturing_data`, `src/prime_runtime` and useful `benchmark/knowledge`/`application` contracts through adapters. Do not make the benchmark/simulation package a production authority. Consolidate overlapping case/state stores with an explicit migration and reconciliation plan; preserve legacy evidence IDs and source mappings. Keep browser drafts recoverable while moving shared work to server records.

**Exit evidence:** cross-tenant/site/partner denial tests; transaction/outbox rollback test; durable checkpoint after worker loss; routed task traces including child costs; idempotency and stale-version tests. Domain calculations and required notifications still function when model providers are unavailable.

## Phase 1 — Connected batch mission and scientific evidence

Connect one documented source through a real adapter in an authorized test environment and use explicit simulators for unavailable systems. Implement the batch/sample/equipment/material/procedure context, incremental ingestion, typed evidence and persistent mission. Wire the existing work surface to server execution and recoverable progress. Deliver meaningful scientific comparisons and evidence requests with unit/time/source checks.

**Exit evidence:** staged synthetic batch replay covering late results, correction, missing source, process drift, invalid mapping, restart, compaction and resumed work. Show an emerging concern before a formal deviation, a supported next action and later reassessment. No future data leakage. Verify actual connector acknowledgment separately from simulation.

## Phase 2 — Quality work, editable records and handoffs

Implement editable field-level forms, versioned QA packages, owner/QA roles, explicit prior-case reuse approval, review-by-exception coverage, evidence requests, notifications and QMS submission reconciliation. Handle corrections, approval invalidation, CAPA/task status and observed outcomes. Add shift handoff scheduling and delivery acknowledgment.

**Exit evidence:** approved reuse versus rejected/silent/stale approval; QA returns one field and dependent outputs are refreshed; a late result withdraws prior advice; external submission succeeds but response is lost; delivery retries never silently duplicate a known operation. An agent cannot approve itself or release/close a record outside assigned authority.

## Phase 3 — Procedures, production and lab execution

Build source-linked authoring, parameterized templates, branches/parallel work, publication/versioning and simulation. Support external execution coordination first. Implement optional native production steps and lab methods with required evidence, calculations, resource checks and signature binding. Add sample custody/aliquots/plates, instrument readiness and lab-to-batch dependencies. Verify modality-specific constraints including individualized product identity where applicable.

**Exit evidence:** approved recipe/method pinning, controlled mid-run revision, conflict with a supplied map, N/A/redline reasons, duplicate sample prevention, custody correction, invalid unit/limit rejection, concurrent edits and signature-content binding. Device workflows are tested on the intended platforms. Customer qualification is required before native live operation.

## Phase 4 — Network operations and broader optimization

Implement partner grants, site variants, transfer packages, readiness checks, campaign/resource/material constraints, scientific modules and comparative analysis across authorized sites. Add scheduling/optimization tools with explicit objectives/constraints and uncertainty; preserve site/process comparability limits. Evaluate reviewed lessons and recommendation outcomes across batches.

**Exit evidence:** receiving-site transfer gap blocks readiness; revoked partner loses retrieval/export/memory access; concurrent site updates do not silently overwrite controlled content; incomplete availability cannot produce a feasible schedule claim; predictive/scientific methods reproduce reference calculations and expose validity limits. Measured improvement requires suitable outcome evidence, not a persuasive explanation.

## Phase 5 — Collaboration, modalities and qualified scale

Integrate remote media, equipment-view assistance, reviewed transcripts/annotations and optional wearables. Complete tenant provisioning, deployment/upgrade procedures, training/support, qualification artifacts, disaster recovery, retention/export and performance tests. Expand connector and device matrices by actual supported versions. Offer additional modalities through qualified templates and method packages.

**Exit evidence:** session permissions/recording consent, device compatibility, signed/audited export integrity, restored evidence/records/mission checkpoints, in-flight workflow upgrade, regional deployment constraints and workload tests. Vendor certifications and deployment timelines are not adopted as product claims.

## Acceptance traceability

Each capability row has a unique ID, source refs, module owner, phase, code foundation and concrete acceptance condition. Before checking Implemented, link the code/change set and integrated scenario. Before checking Verified, link the executed result, environment/build/model/policy versions and scope of verification. Customer qualification is separately tracked; automated testing does not imply it.

The checklist includes vendor claims/unknowns as explicit assessment tasks. Completing their assessment means deciding what evidence is required or rejecting an unsupported assumption. It does not mean implementing a marketing claim. Runtime internals are our design; private Apprentice behavior remains unknown.

## Shared verification suite

| ID | Scenario | Required observation |
| --- | --- | --- |
| V01 | Cross-tenant/site and partner access, cached results and retained memory | Current authorization enforced on every path; no unauthorized content in artifacts or outputs. |
| V02 | Original source through transformation to claim/form | Correct location/version, reproducible calculation, uncertainty and source gaps retained. |
| V03 | Worker/container dies during a mission | Goals, progress, decisions and evidence recovered; completed work not needlessly repeated. |
| V04 | Duplicate/out-of-order event, lost cursor and schema change | Idempotent intake, gap visibility, controlled mapping and correct recomputation. |
| V05 | Corrected/late evidence after draft or approval | Affected outputs stale/revised; changed approval cannot authorize a different action. |
| V06 | Contradictory SOP/map, superseded procedure and missing applicability | Affected step paused; unrelated authorized work and required notification continue. |
| V07 | Prior-case similarity with unresolved or failed outcome | Explicit owner gate; no fabricated success or unapproved acceleration. |
| V08 | External write accepted before connection loss | Unknown outcome reconciled; no blind consequential duplicate. |
| V09 | Model timeout/rate limit, malformed output, budget depletion | Bounded retries, saved progress, honest status; required deterministic operations remain available. |
| V10 | Injection in documents/tool output, sandbox escape/egress attempt | Content cannot grant tool authority; credentials inaccessible; denied actions recorded. |
| V11 | Source availability timeline and repeated compaction | No future leakage; obligations, corrections and recoverable originals survive. |
| V12 | Model/prompt/tool/workflow upgrade with waiting approvals | Versioned evaluations and replay/migration checks; stable approval binding. |
| V13 | Scientific/optimization task with confounding, noisy data or infeasible constraints | Appropriate calculations and uncertainty; no unsupported causal benefit or feasible-action claim. |
| V14 | Authoring/execution/signature concurrent revisions | Enforced sequence/limits and version conflicts; signatures bind reviewed content. |
| V15 | Restoration, retention and export | Recoverable records and evidence; protected historical versions; complete scoped export. |
| V16 | High load plus slow tenant/provider/source | Fair queues, source backpressure, urgent delivery capacity and visible lag. |

## Workload and latency hypotheses

The following are synthetic test configurations, not current capacity, contractual requirements or validated targets. Adjust using source rates, active work, customer needs and cost baseline. Raw telemetry stays in source/analytical storage and is not one model call per event.

| Test profile | Sites | Active missions | Raw observations/sec | Relevant mission events/sec | Purpose |
| --- | ---: | ---: | ---: | ---: | --- |
| Pilot | 1 | 20 | 100 | 1 | Functional isolation, progress and latency baseline. |
| Multi-site | 10 | 500 | 1,000 | 10 | Pool fairness, event coalescing, notification priority and analyst load. |
| Expansion | 100 | 5,000 | 10,000 | 100 | Partition/index pressure, queue retention and need for dedicated streaming/analytics. |

Initial test hypotheses: p95 ordinary internal metadata reads below 300 ms; durable work acceptance below 1 second; supported first partial result within 10 seconds for eligible bounded tasks. Full analysis latency depends on task, source availability and model; record distributions rather than promising a universal deadline. Alerts follow their configured SOP timing; choose engineering capacity with margin against that requirement.

Measure end-to-end latency including queue wait, source reads, inference, verification and reviewer work. Simulate spikes, large documents, busy tenants, rate limits and outages. Autoscale on queue age and service capacity, not only CPU. Define minimum/maximum instances and a spend ceiling; no unbounded fan-out. Sample high-cost traces while retaining audit/action/cost completeness.

## Quality and economics

Create labeled examples for extraction, retrieval, procedure applicability, data normalization, numerical analysis, hypothesis handling and form fields. Separate source correctness from scientific interpretation. Use qualified reviewers for consequential interpretation and evaluate repeated trials. Match workloads when comparing routes and record both improvement and regression.

Promote a small-model route only when it meets the intended-use quality gate at lower total cost or latency; retain critical-case tests and monitor production correction signals. Monitor false negatives and unsupported claims rather than only average accuracy. Cost includes all descendants/retries/tool calls and reviewer effort. No claimed percentage improvement is established by this plan.

## Operational readiness and unresolved deployment inputs

Before live deployment establish: target site/process/modality, source/vendor/version/access, official record ownership, notification rules, owner/QA authority, critical quality attributes and yield definition, retention/residency, availability/recovery objectives, intended devices, validated methods and acceptable cost/latency envelopes. These do not block the generic architecture or synthetic build; they determine deployment configuration and evidence.

Select RPO/RTO by record class with the customer, configure encrypted backups and test restoration across domain records, evidence, sessions and orchestration. Document rollback/roll-forward of schemas and running workflow versions. Keep provider/model availability and data-handling eligibility current. Maintain support ownership, incident response, connector health, training and change notices alongside feature delivery.

## Current task verification

The checker validates document links, inventory coverage, unique IDs, foundation paths and that every checked I/V box carries evidence. The implementation is verified by `backend/tests/lifesci/` (269 tests on 2026-10-23, JUnit at `backend/results/lifesci/junit-2026-10-23.xml`), which covers V01, V02, V03, V04, V05, V07, V08, V09, V11 (corrections through compaction and availability cutoffs), V13, V14, V15 and V16 at development scale. V03 also holds for the Temporal orchestrator (worker replacement, continue-as-new). V12 is partially covered: recorded workflow histories replay against current code (`verify_replay`), but no versioned workflow change with waiting approvals has been exercised. V06, V10 (sandbox/egress) and the workload profiles above are not yet executed. See the [implementation guide](implementation.md).
