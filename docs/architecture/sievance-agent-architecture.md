# Sievance agent architecture

Code audit: 2026-11-07. Open [the editable seven-page draw.io diagram](sievance-agent-architecture.drawio) in diagrams.net or the draw.io desktop app. The [overview SVG](sievance-agent-architecture-overview.svg) provides a quick preview. Every diagram node has a source-file tooltip and `sourceFiles` metadata.

This describes checked-in implementations, not a deployment or model-performance audit. It introduces no new architecture. Existing design documents may describe earlier targets; this map follows current code where those differ.

## Product context

The job is to communicate pharmaceutical manufacturing intelligence and show how evidence reaches an inspectable result and a safe next step. The frontend uses CDMO in user-facing copy. Existing `/cmo` routes, API field names, authentication headers and storage keys remain compatibility contracts. Source-value matching remains a specific data-review capability, not the product identity or proof of manufacturing quality.

Across the four governing pillars: existing sources and discovery reduce preparation (Start); revisions, source references and visible gaps support review (Trust); proposals and explicit human decisions support next steps (Act); existing systems retain record ownership (Adopt). This change improves wording and documentation rather than adding a new workflow. A larger brand or interface redesign would increase review and adoption effort without being necessary to correct the message. Observable review criteria are correct terminology, removal of the blanket “verified CMO data” identity, clear demo limits and the ability to trace each architecture box to source; no measured usability improvement is claimed.

## Reading the diagram

Teal: implemented code. Blue: durable data/evidence. Amber: optional or configuration-dependent. Purple: human authority and assurance. Solid arrows show request/data flow; dashed arrows show optional paths or feedback. Source paths are relative to the repository root.

### 01 · Agent system overview

Three connected execution paths: interactive assistant, durable responsibilities, and explicitly started multi-agent investigations.

| Component | Implementation source |
| --- | --- |
| People and workspace UI | [`frontend/components/process/EngineeringChat.tsx`](../../frontend/components/process/EngineeringChat.tsx) |
| Platform API and identity | [`backend/src/lifesci/api.py`](../../backend/src/lifesci/api.py), [`backend/src/lifesci/identity.py`](../../backend/src/lifesci/identity.py), [`backend/src/lifesci/capabilities.py`](../../backend/src/lifesci/capabilities.py) |
| Platform record store | [`backend/src/lifesci/store.py`](../../backend/src/lifesci/store.py), [`backend/src/lifesci/container.py`](../../backend/src/lifesci/container.py) |
| Interactive workspace assistant | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py), [`backend/src/lifesci/process_engineering/tool_loop.py`](../../backend/src/lifesci/process_engineering/tool_loop.py) |
| Durable manufacturing missions | [`backend/src/lifesci/missions.py`](../../backend/src/lifesci/missions.py) |
| Background runtime | [`backend/src/lifesci/runtime.py`](../../backend/src/lifesci/runtime.py), [`backend/src/lifesci/workqueue.py`](../../backend/src/lifesci/workqueue.py) |
| Model gateway | [`backend/src/lifesci/gateway/gateway.py`](../../backend/src/lifesci/gateway/gateway.py), [`backend/src/lifesci/gateway/router.py`](../../backend/src/lifesci/gateway/router.py) |
| Investigation service | [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |
| Separate investigation executor | [`backend/src/cloud_backend/api.py`](../../backend/src/cloud_backend/api.py), [`backend/src/cloud_backend/dispatcher.py`](../../backend/src/cloud_backend/dispatcher.py), [`backend/src/cloud_backend/agent.py`](../../backend/src/cloud_backend/agent.py) |
| Registered scientific/workspace tools | [`backend/src/lifesci/process_engineering/workspace.py`](../../backend/src/lifesci/process_engineering/workspace.py), [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py) |
| Evidence and outputs | [`backend/src/lifesci/evidence.py`](../../backend/src/lifesci/evidence.py), [`backend/src/lifesci/process_engineering/grounding.py`](../../backend/src/lifesci/process_engineering/grounding.py) |
| Human review and action boundary | [`backend/src/lifesci/actions.py`](../../backend/src/lifesci/actions.py), [`backend/src/lifesci/ownership.py`](../../backend/src/lifesci/ownership.py) |

Implemented in source ≠ enabled in this deployment ≠ validated manufacturing performance. Amber marks configuration-dependent execution. Blue marks durable data; purple marks human authority.

### 02 · Interactive assistant execution

Native tool loop and typed planner share authorization, operators, evidence and durable conversation records.

| Component | Implementation source |
| --- | --- |
| 1 · Accept and enqueue turn | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py) |
| 2 · Claim and check current authority | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py), [`backend/src/lifesci/workqueue.py`](../../backend/src/lifesci/workqueue.py) |
| 3 · Assemble bounded context | [`backend/src/lifesci/process_engineering/tool_loop.py`](../../backend/src/lifesci/process_engineering/tool_loop.py), [`backend/src/lifesci/agent_memory.py`](../../backend/src/lifesci/agent_memory.py) |
| 4 · Select harness | [`backend/src/lifesci/process_engineering/tool_loop.py`](../../backend/src/lifesci/process_engineering/tool_loop.py) |
| 5A · Native model/tool loop | [`backend/src/lifesci/process_engineering/tool_loop.py`](../../backend/src/lifesci/process_engineering/tool_loop.py), [`backend/src/lifesci/gateway/gateway.py`](../../backend/src/lifesci/gateway/gateway.py) |
| 5B · Typed workflow planner | [`backend/src/lifesci/process_engineering/conversation_schemas.py`](../../backend/src/lifesci/process_engineering/conversation_schemas.py), [`backend/src/lifesci/flows.py`](../../backend/src/lifesci/flows.py) |
| 6 · Execute authorized operator | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py), [`backend/src/lifesci/process_engineering/workspace.py`](../../backend/src/lifesci/process_engineering/workspace.py) |
| 7 · Save result and progress | [`backend/src/lifesci/process_engineering/tool_loop.py`](../../backend/src/lifesci/process_engineering/tool_loop.py), [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py) |
| 8 · Enforce native-loop limits | [`backend/src/lifesci/process_engineering/tool_loop.py`](../../backend/src/lifesci/process_engineering/tool_loop.py) |
| 9 · Check provenance and basis | [`backend/src/lifesci/process_engineering/grounding.py`](../../backend/src/lifesci/process_engineering/grounding.py), [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py) |
| 10 · Publish inspectable result | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py), [`frontend/components/process/EngineeringChat.tsx`](../../frontend/components/process/EngineeringChat.tsx) |
| Human authorization stays external | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py), [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |

Limits shown are the checked-in native-loop constants, not a latency guarantee. Planner and native loop are alternative harnesses; the workspace assistant does not spawn Prime child agents.

### 03 · Durable responsibilities and follow-up

Waiting is persisted state; relevant events or due obligations cause bounded work, not continuous model inference.

| Component | Implementation source |
| --- | --- |
| 1 · Owner configures responsibility | [`backend/src/lifesci/process_engineering/responsibilities.py`](../../backend/src/lifesci/process_engineering/responsibilities.py) |
| 2 · Mission + conversation state | [`backend/src/lifesci/missions.py`](../../backend/src/lifesci/missions.py), [`backend/src/lifesci/process_engineering/responsibilities.py`](../../backend/src/lifesci/process_engineering/responsibilities.py) |
| 3 · Source commit or due time | [`backend/src/lifesci/process_engineering/responsibilities.py`](../../backend/src/lifesci/process_engineering/responsibilities.py), [`backend/src/lifesci/store.py`](../../backend/src/lifesci/store.py) |
| 4 · Runtime event pump | [`backend/src/lifesci/runtime.py`](../../backend/src/lifesci/runtime.py) |
| 5 · Mission scheduler | [`backend/src/lifesci/missions.py`](../../backend/src/lifesci/missions.py), [`backend/src/lifesci/runtime.py`](../../backend/src/lifesci/runtime.py) |
| 6 · Fenced activation | [`backend/src/lifesci/missions.py`](../../backend/src/lifesci/missions.py), [`backend/src/lifesci/roles.py`](../../backend/src/lifesci/roles.py) |
| 7 · Coordinator chooses work | [`backend/src/lifesci/runtime.py`](../../backend/src/lifesci/runtime.py) |
| 8 · Follow-up admission | [`backend/src/lifesci/process_engineering/responsibilities.py`](../../backend/src/lifesci/process_engineering/responsibilities.py) |
| 9 · Reuse assistant harness | [`backend/src/lifesci/process_engineering/responsibilities.py`](../../backend/src/lifesci/process_engineering/responsibilities.py), [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py) |
| 10 · Durable checkpoint | [`backend/src/lifesci/missions.py`](../../backend/src/lifesci/missions.py), [`backend/src/lifesci/runtime.py`](../../backend/src/lifesci/runtime.py) |
| 11 · Explicit waiting/control | [`backend/src/lifesci/process_engineering/responsibilities.py`](../../backend/src/lifesci/process_engineering/responsibilities.py) |
| Optional Temporal adapter | [`backend/src/lifesci/orchestration/temporal.py`](../../backend/src/lifesci/orchestration/temporal.py), [`backend/src/lifesci/orchestration/temporal_workflows.py`](../../backend/src/lifesci/orchestration/temporal_workflows.py) |

Pause/stop controls and finite admissions are explicit. Temporal source exists but is not wired by the default composition root; this diagram does not assert a live Temporal deployment.

### 04 · Multi-agent investigation execution plane

The browser stays on the platform API; the execution service receives only an authorized pinned evidence snapshot.

| Component | Implementation source |
| --- | --- |
| 1 · Person presses Start | [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |
| 2 · Freeze authorized evidence | [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |
| 3 · Service-to-service submission | [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py), [`backend/src/cloud_backend/auth.py`](../../backend/src/cloud_backend/auth.py) |
| 4 · Executor control plane | [`backend/src/cloud_backend/api.py`](../../backend/src/cloud_backend/api.py), [`backend/src/cloud_backend/store.py`](../../backend/src/cloud_backend/store.py) |
| 5 · Dispatcher admission | [`backend/src/cloud_backend/dispatcher.py`](../../backend/src/cloud_backend/dispatcher.py) |
| 6 · Isolated agent attempt | [`backend/src/cloud_backend/dispatcher.py`](../../backend/src/cloud_backend/dispatcher.py), [`backend/src/cloud_backend/agent.py`](../../backend/src/cloud_backend/agent.py) |
| 7 · Prime harness + lead/children | [`backend/src/cloud_backend/agent.py`](../../backend/src/cloud_backend/agent.py), [`backend/src/prime_runtime/harness.py`](../../backend/src/prime_runtime/harness.py) |
| 8 · Progress event stream | [`backend/src/prime_runtime/investigation_events.py`](../../backend/src/prime_runtime/investigation_events.py), [`backend/src/cloud_backend/dispatcher.py`](../../backend/src/cloud_backend/dispatcher.py) |
| 9 · Seal result | [`backend/src/cloud_backend/agent.py`](../../backend/src/cloud_backend/agent.py), [`backend/src/cloud_backend/crypto.py`](../../backend/src/cloud_backend/crypto.py) |
| 10 · Platform synchronizes | [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py), [`backend/src/lifesci/runtime.py`](../../backend/src/lifesci/runtime.py) |
| 11 · Validate report envelope | [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |
| 12 · Await human review | [`frontend/components/process/InvestigationCard.tsx`](../../frontend/components/process/InvestigationCard.tsx), [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |

Executor is implemented but requires approved image, provider configuration, keys, database, object store and worker deployment. No deployment/compliance claim. Current constants override older design-doc budget examples.

### 05 · Prime recursive investigation internals

Specialized investigation harness: the lead coordinates bounded independent questions, merges evidence and submits the final report.

| Component | Implementation source |
| --- | --- |
| 1 · Python harness preparation | [`backend/src/prime_runtime/harness.py`](../../backend/src/prime_runtime/harness.py) |
| 2 · Node SDK session | [`backend/src/prime_runtime/sdk_runner.mjs`](../../backend/src/prime_runtime/sdk_runner.mjs), [`backend/src/prime_runtime/compaction_policy.mjs`](../../backend/src/prime_runtime/compaction_policy.mjs) |
| 3 · Lead investigator | [`backend/src/prime_runtime/system_prompt.md`](../../backend/src/prime_runtime/system_prompt.md), [`backend/src/prime_runtime/harness.py`](../../backend/src/prime_runtime/harness.py) |
| 4 · Recursive child agents | [`backend/src/prime_runtime/sdk_runner.mjs`](../../backend/src/prime_runtime/sdk_runner.mjs), [`backend/src/prime_runtime/bridge.py`](../../backend/src/prime_runtime/bridge.py) |
| 5 · Authenticated local tool bridge | [`backend/src/prime_runtime/bridge.py`](../../backend/src/prime_runtime/bridge.py) |
| 6 · Evidence + deterministic analysis | [`backend/src/manufacturing_data/tools.py`](../../backend/src/manufacturing_data/tools.py), [`backend/src/manufacturing_data/analysis.py`](../../backend/src/manufacturing_data/analysis.py) |
| 7 · InvestigationCoordinator | [`backend/src/prime_runtime/coordination.py`](../../backend/src/prime_runtime/coordination.py) |
| 8 · Durable investigation working state | [`backend/src/state/blackboard.py`](../../backend/src/state/blackboard.py), [`backend/src/state/causal_hypothesis_graph.py`](../../backend/src/state/causal_hypothesis_graph.py), [`backend/src/state/decision_graph.py`](../../backend/src/state/decision_graph.py), [`backend/src/prime_runtime/harness.py`](../../backend/src/prime_runtime/harness.py) |
| 9 · Lead synthesis + repair | [`backend/src/prime_runtime/coordination.py`](../../backend/src/prime_runtime/coordination.py), [`backend/src/prime_runtime/bridge.py`](../../backend/src/prime_runtime/bridge.py) |
| 10 · submit_report, lead only | [`backend/src/prime_runtime/bridge.py`](../../backend/src/prime_runtime/bridge.py), [`backend/src/workflows/investigation_review.py`](../../backend/src/workflows/investigation_review.py) |
| 11 · Execution telemetry | [`backend/src/prime_runtime/telemetry.py`](../../backend/src/prime_runtime/telemetry.py), [`backend/src/prime_runtime/investigation_events.py`](../../backend/src/prime_runtime/investigation_events.py) |
| 12 · Report returns for review | [`backend/src/prime_runtime/harness.py`](../../backend/src/prime_runtime/harness.py), [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |

Prime may spawn recursive workers; the interactive Python assistant is a separate harness. Bridge scope is bounded evidence access, not a substitute for platform tenant/site authorization. Worker replacement/reboot recovery depends on persisted runtime storage.

### 06 · Evidence, memory and action authority

Separate original evidence, calculated artifacts, model interpretation, human decisions and execution receipts.

| Component | Implementation source |
| --- | --- |
| Authorized sources | [`backend/src/manufacturing_data/cmo/intake.py`](../../backend/src/manufacturing_data/cmo/intake.py), [`backend/src/lifesci/connectors.py`](../../backend/src/lifesci/connectors.py) |
| Ingestion and source review | [`backend/src/manufacturing_data/cmo/pipeline.py`](../../backend/src/manufacturing_data/cmo/pipeline.py), [`backend/src/manufacturing_data/source_review.py`](../../backend/src/manufacturing_data/source_review.py) |
| Versioned evidence store | [`backend/src/lifesci/evidence.py`](../../backend/src/lifesci/evidence.py), [`backend/src/lifesci/cmo_datasets.py`](../../backend/src/lifesci/cmo_datasets.py) |
| Permission-aware discovery | [`backend/src/lifesci/process_engineering/workspace.py`](../../backend/src/lifesci/process_engineering/workspace.py), [`backend/src/lifesci/memory.py`](../../backend/src/lifesci/memory.py) |
| Assistant memory layers | [`backend/src/lifesci/agent_memory.py`](../../backend/src/lifesci/agent_memory.py), [`backend/src/lifesci/embeddings.py`](../../backend/src/lifesci/embeddings.py), [`backend/src/lifesci/memory.py`](../../backend/src/lifesci/memory.py) |
| Registered scientific work | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py), [`backend/src/lifesci/science.py`](../../backend/src/lifesci/science.py), [`backend/src/lifesci/lyophilization/service.py`](../../backend/src/lifesci/lyophilization/service.py) |
| Reviewable proposal | [`backend/src/lifesci/actions.py`](../../backend/src/lifesci/actions.py), [`backend/src/workflows/investigation_review.py`](../../backend/src/workflows/investigation_review.py) |
| Approval of exact version | [`backend/src/lifesci/actions.py`](../../backend/src/lifesci/actions.py), [`backend/src/lifesci/records.py`](../../backend/src/lifesci/records.py) |
| Approved action intent | [`backend/src/lifesci/actions.py`](../../backend/src/lifesci/actions.py), [`backend/src/lifesci/ownership.py`](../../backend/src/lifesci/ownership.py) |
| Configured authorized writer | [`backend/src/lifesci/actions.py`](../../backend/src/lifesci/actions.py), [`backend/src/lifesci/integrations.py`](../../backend/src/lifesci/integrations.py) |
| Owning system of record | [`backend/src/lifesci/ownership.py`](../../backend/src/lifesci/ownership.py), [`backend/src/lifesci/actions.py`](../../backend/src/lifesci/actions.py) |
| Observed outcome + follow-up | [`backend/src/lifesci/actions.py`](../../backend/src/lifesci/actions.py), [`backend/src/lifesci/missions.py`](../../backend/src/lifesci/missions.py) |

IdentityService, evidence validation and host authority checks apply across all paths. Saved assistant answers are not manufacturing occurrence records. Native execution requires explicit assigned ownership and qualification; source matching does not establish regulatory compliance.

### 07 · Runtime boundaries and operational limits

Source-backed deployment map and limitations; operational configuration and live deployment were not audited for this artifact.

| Component | Implementation source |
| --- | --- |
| Browser frontend | [`frontend/app/layout.tsx`](../../frontend/app/layout.tsx), [`frontend/lib/process-api.ts`](../../frontend/lib/process-api.ts) |
| Platform Python process | [`backend/src/lifesci/container.py`](../../backend/src/lifesci/container.py), [`backend/src/lifesci/api.py`](../../backend/src/lifesci/api.py), [`backend/src/lifesci/aws_lambda.py`](../../backend/src/lifesci/aws_lambda.py) |
| Platform persistence | [`backend/src/lifesci/store.py`](../../backend/src/lifesci/store.py) |
| Interactive model providers | [`backend/src/lifesci/gateway/providers.py`](../../backend/src/lifesci/gateway/providers.py), [`backend/src/lifesci/gateway/router.py`](../../backend/src/lifesci/gateway/router.py) |
| Investigation executor service | [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py), [`backend/src/cloud_backend/api.py`](../../backend/src/cloud_backend/api.py) |
| Prime worker packaging | [`backend/src/cloud_backend/dispatcher.py`](../../backend/src/cloud_backend/dispatcher.py), [`backend/src/prime_runtime/sdk_runner.mjs`](../../backend/src/prime_runtime/sdk_runner.mjs) |
| Executor DB + object storage | [`backend/src/cloud_backend/store.py`](../../backend/src/cloud_backend/store.py), [`backend/src/cloud_backend/crypto.py`](../../backend/src/cloud_backend/crypto.py) |
| Optional external scheduler | [`backend/src/lifesci/orchestration/temporal.py`](../../backend/src/lifesci/orchestration/temporal.py) |
| Alternative Prime gateway adapter | [`backend/src/lifesci/prime_adapter.py`](../../backend/src/lifesci/prime_adapter.py), [`backend/src/lifesci/container.py`](../../backend/src/lifesci/container.py) |
| Observable failure states | [`backend/src/lifesci/process_engineering/conversation.py`](../../backend/src/lifesci/process_engineering/conversation.py), [`backend/src/lifesci/investigations.py`](../../backend/src/lifesci/investigations.py) |
| Recovery and assurance limits | [`backend/src/prime_runtime/harness.py`](../../backend/src/prime_runtime/harness.py), [`backend/src/lifesci/process_engineering/grounding.py`](../../backend/src/lifesci/process_engineering/grounding.py) |
| Useful operational measures | [`Main_Culture_andETHOS.md`](../../Main_Culture_andETHOS.md) |

Legend: teal = implemented source path; blue = persisted evidence/state; amber = optional/configuration-dependent; purple = human control/assurance. Solid arrows = request/data flow; dashed arrows = optional path or feedback.

## Material distinctions and limits

- The interactive assistant has two selectable harnesses: native tool calling and typed workflow planning. It does not implicitly run Prime child agents. `ASSISTANT_LOOP` selects behavior; unset defaults to tools for demo tenants and planner otherwise.
- Standing responsibilities use the same mission/event and conversation services, with finite admission and owner controls. They produce in-app work; they do not authorize manufacturing actions.
- Multi-agent investigations use an explicit person-started executor job. The current service defaults are 30 calls, 10 minutes and one active run per tenant, rather than the older design document’s example limits.
- The executor/streaming implementation now exists despite the older multi-agent design document’s “nothing implemented” heading. Configuration, enabled paid plan, worker packaging and actual deployment still need environment evidence.
- Temporal implements an optional scheduler port; the default Platform composition does not establish a running Temporal deployment. The gateway Prime adapter is another optional path, separate from the HTTP investigation executor.
- Deterministic grounding checks source support and numbers; they do not prove semantic correctness or causation. A source-matched CDMO delivery does not establish batch release or process quality.
- Prime’s local session/checkpoint resume depends on retained runtime files. A persisted job record alone does not guarantee a model session survives a host reboot.
- External writers and native execution depend on configured integrations and assigned authority; the existence of ActionService does not mean a manufacturing write integration is enabled.
- No live provider run, deployment audit, regulatory compliance assessment or manufacturing validation was performed for this diagram.
