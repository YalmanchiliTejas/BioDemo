# Life-sciences capability checklist

Generated from [the canonical CSV](capability-checklist.csv). Update the CSV, then run `python3 docs/product/life-sciences-platform/check_plan.py --render`.

Sources: [official offering inventory](../../research/apprentice-life-sciences-source-inventory.md) and [code inventory](../../research/life-sciences-codebase-inventory.md). Design: [architecture](architecture.md), [decisions](decision-log.md), [model policy](model-routing.md), [delivery and verification](delivery-and-verification.md).

## Status and evidence

89 tracked items: 77 capabilities and 12 assessments. R = researched/mapped; D = design specified; I = integrated implementation; V = executed verification. R/D do not imply I/V. Related code and simulation fixtures are foundations only. Checking I or V requires linked evidence in the CSV. Qualification for a customer's intended use is separate.

Source IDs map to the official inventory. USER identifies requested behavior; DESIGN identifies engineering requirements derived in this proposal. Assessment rows track vendor claims/unknowns without promising those claims or private implementation parity. Acceptance is conjunctive: all listed behavior, applicable devices/adapters/methods and shared verification controls must pass; a single illustrative test does not complete a bundled capability.

## CORE

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-062 · capability | Existing systems retain record ownership; write scope is explicit and reversible | USER | 0 | [backend/src/cloud_backend/auth.py](../../../backend/src/cloud_backend/auth.py) | An adapter defaults to read access and rejects a write without configured ownership and approval. | [x] / [x] / [x] / [x] |
| LS-068 · capability | Multi-tenant, partner, and revoked-access checks cover retrieval, cache, memory, and output | DESIGN | 0 | [backend/src/cloud_backend/auth.py](../../../backend/src/cloud_backend/auth.py) | A revoked grant blocks current retrieval and retained/cached output access. | [x] / [x] / [x] / [x] |
| LS-081 · capability | Isolated tool execution and credential separation | DESIGN | 0 | [backend/src/cloud_backend/dispatcher.py](../../../backend/src/cloud_backend/dispatcher.py) | Generated code cannot access domain credentials or unauthorized network/files; tool scopes and cancellation remain enforced. | [x] / [x] / [ ] / [ ] |
| LS-085 · capability | Derived memory inherits source restrictions | DESIGN | 0 | None identified | Revoking one contributing source blocks mixed-source summaries, cached exports and context until authorized regeneration. | [x] / [x] / [x] / [x] |

## INT

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-004 · capability | Enterprise source integration | LS04 | 1 | [backend/benchmark/integration/connectors.py](../../../backend/benchmark/integration/connectors.py) | Each claimed ERP/QMS/historian/equipment adapter passes authorized read, identity, version, mapping and gap scenarios. | [x] / [x] / [ ] / [ ] |
| LS-023 · capability | Plant and enterprise connectivity | A1-03 | 1 | [backend/benchmark/integration/connectors.py](../../../backend/benchmark/integration/connectors.py) | Exercise each supported plant/enterprise transport including REST/webhooks/MQTT/OPC UA/files; expose gaps and prohibit unapproved control writes. | [x] / [x] / [ ] / [ ] |
| LS-029 · capability | Instrument and research connectivity | GAN02 | 1 | [backend/src/manufacturing_data/ingest.py](../../../backend/src/manufacturing_data/ingest.py) | Two source types ingest incrementally and expose gaps and source timestamps. | [x] / [x] / [x] / [x] |
| LS-032 · assessment | Unpublished data-cloud interface assessment | GAN05 | 0 | None identified | A reviewed interface decision records known boundaries and unanswered vendor questions. | [x] / [x] / [x] / [ ] |
| LS-041 · capability | Connector configuration experience | INT01 | 1 | [backend/benchmark/integration/connectors.py](../../../backend/benchmark/integration/connectors.py) | An administrator configures a connector through templates, previews mappings and tests capture, material and maintenance context without code. | [x] / [x] / [ ] / [ ] |
| LS-042 · capability | Public API and subscriptions | INT02 | 0 | [backend/src/cloud_backend/api.py](../../../backend/src/cloud_backend/api.py) | Documented versioned API handles authorized reads/commands, pagination, idempotency, schema errors and replayable signed subscriptions. | [x] / [x] / [x] / [x] |
| LS-043 · capability | ERP exchange and materials | INT03 | 1 | [backend/benchmark/integration/connectors.py](../../../backend/benchmark/integration/connectors.py) | Reconcile ERP master data, runs, lots/expiry, consumption and status; consequential writes use assigned authority and unknown-outcome recovery. | [x] / [x] / [x] / [x] |
| LS-044 · assessment | Connector contract assessment | INT04 | 0 | [backend/benchmark/integration/catalog.py](../../../backend/benchmark/integration/catalog.py) | A versioned connector contract lists operations, limits, error semantics, and owner. | [x] / [x] / [x] / [x] |
| LS-063 · capability | Data corrections, units, timestamps, lineage, and source gaps remain inspectable | USER | 1 | [backend/src/manufacturing_data/analysis.py](../../../backend/src/manufacturing_data/analysis.py) | A normalized value links to original source, units, time basis, and transformation version. | [x] / [x] / [x] / [x] |

## PROC

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-001 · capability | Therapy and lifecycle context | LS01 | 1 | [backend/src/manufacturing_data/models.py](../../../backend/src/manufacturing_data/models.py) | A batch context links an authorized development record to its manufacturing use. | [x] / [x] / [x] / [x] |
| LS-003 · assessment | Modality flexibility assessment | LS03 | 3 | None identified | A reviewed requirements decision records supported variants and unresolved modality constraints. | [x] / [x] / [x] / [ ] |
| LS-006 · capability | Recipe authoring and validation | MES01 | 3 | None identified | Author, preview and publish a recipe with branches, parallel steps and enforcement; invalid dependencies are rejected. | [x] / [x] / [x] / [x] |
| LS-007 · capability | Parameterized recipes and controlled amendments | MES02 | 3 | None identified | Parameterize multiple products; amend an active run through review; retain redlines, N/A reasons and completed-step history. | [x] / [x] / [x] / [x] |
| LS-033 · capability | Instruction authoring and distribution | DWI01 | 3 | None identified | Publishing a changed instruction creates a new revision without changing active runs. | [x] / [x] / [x] / [x] |
| LS-034 · capability | Document-to-instruction interpretation | DWI02 | 3 | None identified | Interpret PDF/paper with source spans; review controlled publication; exercise prompts, images/video and supported tablet/wearable guidance. | [x] / [x] / [ ] / [ ] |

## EXEC

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-008 · capability | Multi-device guided execution | MES03 | 5 | None identified | For each supported web/mobile/hands-free device, execute guided steps, capture data, calculate results and deliver exceptions. | [x] / [x] / [ ] / [ ] |
| LS-073 · capability | Production order, lot and equipment context | INT03;MES03 | 3 | None identified | Project or natively manage authorized order/lot/equipment status; prevent missing or ineligible resources from completing a required step. | [x] / [x] / [x] / [x] |
| LS-074 · capability | Maintenance readiness and fault preparation | A1-04;INT01 | 4 | None identified | Prepare evidence-linked maintenance work from fault history/manuals/spares; show qualification and unavailable-resource gaps. | [x] / [x] / [x] / [x] |
| LS-079 · capability | Native production execution and controlled pause | MES03;DESIGN | 3 | None identified | Complete typed procedure steps with approved limits, resource evidence and signatures; loss of authority pauses dependent execution. | [x] / [x] / [x] / [x] |
| LS-083 · capability | Offline observation and reconnect reconciliation | DESIGN | 3 | None identified | Offline drafts stay provisional; no authoritative browser-local signatures; reconnect resolves versions before dependent work resumes. | [x] / [x] / [x] / [x] |

## LAB

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-011 · capability | Laboratory method authoring and execution | LES01 | 3 | None identified | Author a method with media and calculations; execute assay/protocol fixtures; reject invalid units, parameters and limits. | [x] / [x] / [x] / [x] |
| LS-012 · capability | Samples, plates and custody | LES02 | 3 | None identified | Track collection-to-result with IDs, aliquots and plate positions; duplicate retries are idempotent and custody corrections auditable. | [x] / [x] / [x] / [x] |
| LS-013 · capability | Laboratory resource collaboration | LES03 | 3 | None identified | Link instrument/material readiness to lab work; authorized concurrent users collaborate while outside-scope reads are denied. | [x] / [x] / [x] / [x] |
| LS-014 · capability | Method versions and site adaptation | LES04 | 3 | None identified | A site adaptation retains its parent method revision and local approval state. | [x] / [x] / [x] / [x] |

## QUAL

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-059 · capability | External actions are proposals, approvals, intents, delivery, reconciliation, and outcomes | USER | 2 | [backend/src/workflows/proposals.py](../../../backend/src/workflows/proposals.py) | A consequential action cannot occur until the authorized actor approves its exact version. | [x] / [x] / [x] / [x] |
| LS-060 · capability | Observed outcomes stay separate from predicted benefit and recommendation | USER | 2 | [backend/src/state/decision_graph.py](../../../backend/src/state/decision_graph.py) | An outcome record reports observation and attribution limits separately from expected effect. | [x] / [x] / [x] / [x] |
| LS-064 · capability | Reviewer sees observations, calculations, hypotheses, unknowns, and counterevidence | USER | 2 | [backend/src/workflows/report_verification.py](../../../backend/src/workflows/report_verification.py) | A claim view exposes evidence basis, contradiction, uncertainty, and unresolved items. | [x] / [x] / [x] / [x] |
| LS-065 · capability | Recommendation records rationale, owner, approval, constraints, and follow-up measure | USER | 2 | [backend/src/workflows/proposals.py](../../../backend/src/workflows/proposals.py) | A recommendation cannot be marked effective before the named outcome evidence is recorded. | [x] / [x] / [x] / [x] |
| LS-070 · capability | Prior-investigation reuse approval | USER | 2 | [backend/src/workflows/proposals.py](../../../backend/src/workflows/proposals.py) | Show summary, similarities, differences and intended reuse; approval enables only that reuse; silence/rejection does not. | [x] / [x] / [x] / [x] |
| LS-071 · capability | Editable forms and QA correction dependencies | USER | 2 | [backend/src/workflows/manufacturing.py](../../../backend/src/workflows/manufacturing.py) | Populate cited fields with unresolved markers; return a field for correction and invalidate all affected conclusions and approvals. | [x] / [x] / [x] / [x] |
| LS-078 · capability | Electronic batch records and exception review | MES03;LS01 | 3 | None identified | Link execution evidence and required reviews; distinguish checked/unchecked scope; no exception list alone authorizes release. | [x] / [x] / [x] / [x] |
| LS-086 · capability | Pre-dispatch freshness and approval checks | DESIGN | 2 | [backend/benchmark/application/execution.py](../../../backend/benchmark/application/execution.py) | A queued intent with changed evidence/authority cannot dispatch; already-sent operations record outcomes and trigger appropriate reassessment. | [x] / [x] / [x] / [x] |

## SCI

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-028 · capability | Scientific ingestion and standardization | GAN01 | 1 | [backend/src/manufacturing_data/ingest.py](../../../backend/src/manufacturing_data/ingest.py) | An ingested result retains original bytes, digest, source revision, and mapping version. | [x] / [x] / [x] / [x] |
| LS-030 · capability | Scientific analysis modules | GAN03 | 4 | [backend/src/manufacturing_data/analysis.py](../../../backend/src/manufacturing_data/analysis.py) | Curve fitting, qPCR and chromatography each reproduce reference results; workflow configuration and source-linked visualization are exercised. | [x] / [x] / [ ] / [ ] |
| LS-031 · capability | Process and equipment analytics | GAN04 | 4 | [backend/src/manufacturing_data/analysis.py](../../../backend/src/manufacturing_data/analysis.py) | DOE, batch/control-chart, liquid-handler, plate-assay and OEE modules each expose inputs, validity limits and reference calculations. | [x] / [x] / [x] / [x] |
| LS-056 · capability | Deterministic calculations precede model reasoning where reliable | USER | 1 | [backend/src/manufacturing_data/analysis.py](../../../backend/src/manufacturing_data/analysis.py) | A numeric comparison is reproducible without model-generated arithmetic. | [x] / [x] / [x] / [x] |
| LS-076 · capability | Authorized cross-site yield comparison | GAN04;CMN01 | 4 | [backend/src/manufacturing_data/analysis.py](../../../backend/src/manufacturing_data/analysis.py) | Compare process-stage-compatible authorized cohorts; disclose confounders, missing data and unsupported causal conclusions. | [x] / [x] / [x] / [x] |
| LS-077 · capability | Process drift and improvement recommendations | GAN04;A1-04 | 1 | [backend/src/manufacturing_data/analysis.py](../../../backend/src/manufacturing_data/analysis.py) | Detect a sourced emerging concern before formal deviation; update a supported recommendation as new data changes its basis. | [x] / [x] / [x] / [x] |
| LS-089 · capability | Model and method drift monitoring | DESIGN | 4 | None identified | Monitor corrected findings and shifted input distributions; suspend an unsuitable profile and assess replacements without silently changing approved work. | [x] / [x] / [ ] / [ ] |

## NET

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-009 · capability | Site rollout and QMS alignment | MES04 | 4 | None identified | A site rollout records configuration differences and reconciles a linked QMS reference. | [x] / [x] / [x] / [x] |
| LS-015 · capability | Multi-site operational visibility | CMN01 | 4 | [backend/benchmark/knowledge/domain.py](../../../backend/benchmark/knowledge/domain.py) | A user sees only site records granted by current membership and resource scope. | [x] / [x] / [x] / [x] |
| LS-016 · capability | Global templates and local parameters | CMN02 | 4 | None identified | A site override identifies template revision and validates allowed parameters. | [x] / [x] / [x] / [x] |
| LS-017 · capability | Technology-transfer packages | CMN03 | 4 | None identified | A recipient checklist exposes missing mappings before transfer readiness. | [x] / [x] / [x] / [x] |
| LS-018 · capability | Sponsor and partner collaboration | CMN04 | 4 | [backend/benchmark/application/control.py](../../../backend/benchmark/application/control.py) | Revoking a partner grant removes access to current and cached batch evidence. | [x] / [x] / [x] / [x] |
| LS-019 · capability | Product lifecycle readiness | CMN05 | 4 | [backend/src/workflows/manufacturing.py](../../../backend/src/workflows/manufacturing.py) | A lifecycle summary links each readiness status to current source revisions. | [x] / [x] / [x] / [x] |
| LS-075 · capability | Campaign, capacity and scheduling proposals | A1-04;CMN05 | 4 | None identified | Produce a constraint-checked schedule proposal from resources/materials/quality holds; expose infeasibility and require authorized changes. | [x] / [x] / [x] / [x] |

## COLLAB

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-022 · capability | Triggers and communication channels | A1-02 | 2 | [backend/benchmark/integration/runner.py](../../../backend/benchmark/integration/runner.py) | Exercise event, schedule, alarm and file-change triggers; each enabled email/SMS/WhatsApp/Slack/Teams adapter records delivery outcomes. | [x] / [x] / [ ] / [ ] |
| LS-037 · capability | Remote assistance sessions | VRC01 | 5 | None identified | A session checks participant access and records session/case linkage. | [x] / [x] / [x] / [x] |
| LS-038 · capability | Annotations and communication tools | VRC02 | 5 | None identified | Each enabled drawing/AR pointer/transcription/walkie-talkie/chat tool works on supported devices with session authority and recording controls. | [x] / [x] / [ ] / [ ] |
| LS-039 · capability | External expert assistance | VRC03 | 5 | [backend/src/cloud_backend/auth.py](../../../backend/src/cloud_backend/auth.py) | An external participant sees only the authorized case and permitted media. | [x] / [x] / [x] / [x] |
| LS-061 · capability | Notifications retain owner, payload revision, delivery attempts, and unknown result | DESIGN | 2 | [backend/benchmark/integration/runner.py](../../../backend/benchmark/integration/runner.py) | A lost provider response is reconciled without silently duplicating consequential delivery. | [x] / [x] / [x] / [x] |
| LS-072 · capability | Procedure-timed initial and follow-up notifications | USER | 2 | None identified | Missing evidence cannot delay required initial notice; follow-up findings and review package have separate delivery states. | [x] / [x] / [x] / [x] |

## ASSURE

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-002 · capability | Signatures and record controls | LS02 | 0 | [backend/src/cloud_backend/schema.sql](../../../backend/src/cloud_backend/schema.sql) | Signature actor/time/meaning bind exact content; audit changes remain inspectable; roles and qualification artifacts are tested. | [x] / [x] / [x] / [x] |
| LS-010 · assessment | Deployment timing claim assessment | MES05 | 0 | None identified | A documented deployment estimate states scope, assumptions, evidence, and uncertainty. | [x] / [x] / [x] / [ ] |
| LS-020 · assessment | Transfer-speed claim assessment | CMN06 | 0 | None identified | A transfer-effort claim is either supported by measured evidence or marked unverified. | [x] / [x] / [x] / [ ] |
| LS-025 · capability | Administrative AI and human authority | A1-05 | 0 | [backend/benchmark/application/control.py](../../../backend/benchmark/application/control.py) | Agent credentials cannot approve their own consequential proposal. | [x] / [x] / [x] / [x] |
| LS-026 · assessment | Availability and model claim assessment | A1-06 | 0 | None identified | Availability and quality claims are tied to measured environment and evaluation evidence. | [x] / [x] / [x] / [ ] |
| LS-035 · capability | Step records and signatures | DWI03 | 3 | None identified | A signature binds to the exact approved procedure and execution content. | [x] / [x] / [x] / [x] |
| LS-036 · assessment | Authoring benefit claim assessment | DWI04 | 0 | None identified | Measured task outcomes distinguish baseline, sample, reviewer effort, and uncertainty. | [x] / [x] / [x] / [ ] |
| LS-040 · assessment | Collaboration benefit claim assessment | VRC04 | 0 | None identified | A benefit statement is supported by observed workflow outcomes or labeled unverified. | [x] / [x] / [x] / [ ] |
| LS-045 · assessment | Certification claim assessment | SEC01 | 5 | None identified | A reviewer records current authoritative evidence, applicable scope, and expiry. | [x] / [x] / [x] / [ ] |
| LS-046 · capability | Audit, access and qualification support | SEC02 | 0 | [backend/src/cloud_backend/schema.sql](../../../backend/src/cloud_backend/schema.sql) | Audit, access and administrative AI controls pass denial/correction cases; qualification artifacts trace requirements to execution evidence. | [x] / [x] / [x] / [x] |
| LS-047 · assessment | Deployment security assessment | SEC03 | 5 | [backend/src/cloud_backend/runtime_roles.sql](../../../backend/src/cloud_backend/runtime_roles.sql) | A deployment evidence packet covers tenant controls, restore, residency, and retention. | [x] / [x] / [x] / [ ] |
| LS-048 · capability | Deployment and training services | SVC01 | 5 | None identified | A deployment plan names site/process scope, owners, training, and qualification evidence. | [x] / [x] / [x] / [x] |
| LS-049 · capability | Support and controlled releases | SVC02 | 5 | None identified | Publish searchable guides and support escalation; exercise an incident, controlled release notice, in-flight upgrade and recovery. | [x] / [x] / [ ] / [ ] |
| LS-050 · assessment | Service-timeline claim assessment | SVC03 | 0 | None identified | A delivery estimate exposes assumptions, customer dependencies, and evidence basis. | [x] / [x] / [x] / [ ] |
| LS-080 · capability | Provider outage without loss of required controls | DESIGN | 0 | None identified | With all models unavailable, deterministic authorization, required alerts and record retrieval continue; agent work reports blocked progress. | [x] / [x] / [x] / [x] |
| LS-082 · capability | Evidence retention, export and restoration | SEC03;SEC02 | 5 | [backend/src/cloud_backend/backup.py](../../../backend/src/cloud_backend/backup.py) | Restore records, originals, sessions and decisions under agreed recovery objectives; exported revisions remain readable and attributable. | [x] / [x] / [ ] / [ ] |
| LS-088 · capability | Targeted adapter and device qualification matrix | INT04;MES03;VRC01 | 5 | None identified | Every advertised connector/device version has executed scenarios and explicit limits; unsupported variants remain marked unavailable. | [x] / [x] / [ ] / [ ] |

## AGENT

| ID / kind | Capability | Source | Phase | Existing foundation | Acceptance | R / D / I / V |
| --- | --- | --- | --- | --- | --- | --- |
| LS-005 · capability | Role-scoped assistance | LS05 | 1 | [backend/src/prime_runtime/system_prompt.md](../../../backend/src/prime_runtime/system_prompt.md) | Role-specific task scopes cannot grant permissions beyond the actor's current scope. | [x] / [x] / [x] / [x] |
| LS-021 · capability | Configurable agent work and editable artifacts | A1-01 | 1 | [backend/src/prime_runtime/harness.py](../../../backend/src/prime_runtime/harness.py) | Execute configured repeatable obligations, generate editable deviation/CAPA/report artifacts and retain sources and review state. | [x] / [x] / [x] / [x] |
| LS-024 · capability | Operational role skills | A1-04 | 1 | [backend/src/prime_runtime/system_prompt.md](../../../backend/src/prime_runtime/system_prompt.md) | Each named role has a scoped scenario, tools, artifacts and authority boundaries; every scenario passes its own acceptance fixture. | [x] / [x] / [ ] / [ ] |
| LS-027 · assessment | Unpublished AI design assessment | A1-07 | 0 | [backend/src/prime_runtime/harness.py](../../../backend/src/prime_runtime/harness.py) | A versioned design record specifies observable grounding, failure, and escalation behavior. | [x] / [x] / [x] / [ ] |
| LS-051 · capability | Persistent mission retains objective, owner, scope, status, obligations, and decisions | USER | 0 | [backend/src/prime_runtime/harness.py](../../../backend/src/prime_runtime/harness.py) | After worker loss, the same mission resumes with unresolved decisions and current status. | [x] / [x] / [x] / [x] |
| LS-052 · capability | Mission event cursor and evidence dependencies support targeted recomputation | DESIGN | 0 | [backend/src/state/decision_graph.py](../../../backend/src/state/decision_graph.py) | A corrected source marks dependent outputs stale while unrelated work remains current. | [x] / [x] / [x] / [x] |
| LS-053 · capability | User corrections and rejected hypotheses persist across compaction | DESIGN | 0 | [backend/src/prime_runtime/compaction_policy.mjs](../../../backend/src/prime_runtime/compaction_policy.mjs) | After compaction, a prior correction remains linked to its source and affected claim. | [x] / [x] / [x] / [x] |
| LS-054 · capability | New evidence invalidates dependent outputs and changed approvals | DESIGN | 0 | [backend/src/workflows/claim_verification.py](../../../backend/src/workflows/claim_verification.py) | A changed evidence revision invalidates dependent advice and its prior approval. | [x] / [x] / [x] / [x] |
| LS-055 · capability | Model routing selects eligible route by task, risk, evidence, scope, and budget | DESIGN | 0 | [backend/src/prime_runtime/provider_config.mjs](../../../backend/src/prime_runtime/provider_config.mjs) | A high-risk task cannot be routed to an unqualified lower-cost model. | [x] / [x] / [x] / [x] |
| LS-057 · capability | Routing records model/prompt/tool versions, usage, cost, and outcome | DESIGN | 0 | [backend/src/prime_runtime/telemetry.py](../../../backend/src/prime_runtime/telemetry.py) | A mission trace aggregates descendant calls, retries, route reason, and measured usage. | [x] / [x] / [x] / [x] |
| LS-058 · capability | Budgets, retries, and escalation are bounded; exhaustion preserves progress | DESIGN | 0 | [backend/src/prime_runtime/harness.py](../../../backend/src/prime_runtime/harness.py) | Budget exhaustion pauses with progress and reports remaining work without lowering controls. | [x] / [x] / [x] / [x] |
| LS-066 · capability | Performance and cost include queueing, retries, tool calls, and reviewer effort | DESIGN | 0 | [backend/src/prime_runtime/telemetry.py](../../../backend/src/prime_runtime/telemetry.py) | A task report includes end-to-end latency and total descendant/reviewer cost inputs. | [x] / [x] / [x] / [x] |
| LS-067 · capability | Quality routing and model upgrades require task-specific evaluation and versioned replay | DESIGN | 0 | [backend/src/evaluation/leakage_audit.py](../../../backend/src/evaluation/leakage_audit.py) | A changed model profile cannot activate without recorded task evaluation and impact scope. | [x] / [x] / [x] / [x] |
| LS-069 · capability | Long-running work streams status and recovers from missed client events | DESIGN | 0 | [backend/src/prime_runtime/harness.py](../../../backend/src/prime_runtime/harness.py) | A reconnecting client resumes from cursor and receives a consistent state snapshot. | [x] / [x] / [x] / [x] |
| LS-084 · capability | Mission concurrency and fenced checkpoints | DESIGN | 0 | [backend/src/cloud_backend/store.py](../../../backend/src/cloud_backend/store.py) | Overlapping attempts cannot publish stale state or replace a newer checkpoint; child findings merge against explicit basis versions. | [x] / [x] / [x] / [x] |
| LS-087 · capability | Tenant fairness, backpressure and resource ceilings | DESIGN | 0 | [backend/src/cloud_backend/store.py](../../../backend/src/cloud_backend/store.py) | A busy tenant cannot starve urgent work; queue lag is visible, fan-out bounded and backfill never silently drops evidence. | [x] / [x] / [x] / [x] |
