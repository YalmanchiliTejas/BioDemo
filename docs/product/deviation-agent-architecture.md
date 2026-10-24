# Deviation agent architecture proposal

Scope update: the user subsequently requested long-horizon manufacturing agents with persistent context, evolving evidence, and proactive yield/quality suggestions. See the [revised broader proposal](long-horizon-manufacturing-agents.md). This document remains a deviation-capability reference; its case-centered framing and workflow-engine preference are not a settled product-wide architecture.

Status: recommended baseline for the user's architecture decision, 2026-10-23. This document does not record user acceptance, change the running application, or claim deployment readiness.

Governing direction: [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md). Product requirements: [confirmed discovery](deviation-workflow-discovery.md). Supporting sources: [reading guide](../research/deviation-agent-architecture-reading.md).

## Job and context

An investigation owner needs an event turned into a source-backed investigation and editable QA package, with timely notifications, explicit decisions, corrections, and follow-up. Existing manufacturing and quality systems retain their record responsibilities. The broader product can reuse these capabilities for other jobs; this first workflow does not define the whole product.

## Recommended shape

Use an event-driven, durable case workflow containing bounded agent investigations. Start with one lead investigation agent; permit scoped workers for independent questions when measurements justify their cost. Application services enforce authority and record case transitions. The model chooses investigation steps within those boundaries.

```text
Existing systems / documents / human reports
                    |
          Permission-aware connectors
                    |
       Evidence ingestion + event deduplication
                    |
      Durable case workflow + procedure context
         |              |                 |
   notification     agent activity     human decisions
   activities       and tool gateway    and corrections
                        |
                lead investigator
                  /          \
        scoped worker     scoped worker
            (only useful independent questions)
                        |
          checked claims + editable form draft
                        |
               QA review + follow-up
                        |
        authorized external record operations

Shared application services: evidence/provenance, case records,
permissions, procedure versions, prior cases, audit, evaluations.
```

This is a logical topology, not a requirement to create a microservice for every box. Begin with a modular application, separate background workers, and isolated agent execution. Connectors, reasoning, durable execution, and the UI should evolve independently.

## Responsibilities and contracts

| Component | Owns | Important boundary |
| --- | --- | --- |
| Connectors and intake | Authorized reads, source IDs/revisions, cursors, availability, deduplication | A failed or incomplete sync is visible; it does not imply absence of evidence. Existing event sources initiate the first workflow. |
| Evidence service | Originals, extraction, normalized values, transformations, entity mappings, source access checks | Separate observations, calculations, interpretations, and approved decisions. Enforce tenant/site permissions before search, retrieval, agent access, memory access, and export. |
| Procedure service | Applicable controlled revisions, effective dates, authority, section references, extracted instructions and form mappings | Extracted steps are derived interpretations with citations. An unrelated document or supplied map cannot grant authority or silently override an approved SOP. Follow clear applicable instructions; isolate ambiguity for clarification without blanket first-use approval. |
| Case workflow | Case lifecycle, work dependencies, timers, pending decisions, retries, notifications, review and outcome tasks | Code enforces permitted transitions and authorization. Waiting for one decision blocks dependent work; independent gathering and required notifications continue. |
| Investigation runtime | Adaptive evidence gathering, proposed tests, competing hypotheses, source-linked draft findings | Bounded by tools, scope, time, cost, and cancellation. It cannot approve itself or execute consequential actions through an unrestricted channel. |
| Form and review service | Versioned editable field values, source/claim links, unresolved markers, review corrections | An unreviewed hypothesis cannot populate a field representing an approved root cause. Render the required format separately from the agent's narrative. |
| Action gateway | Authorized delivery and external writes, target-system acknowledgment and reconciliation | Approval is specific to an operation and its payload/version. A timeout is an unknown outcome until reconciled, not permission to repeat the action blindly. |
| Prior-case service | Retrieval of earlier evidence, conclusions, decisions, actions, observed outcomes and applicability | Similarity proposes a candidate; it does not grant permission to accelerate or establish successful resolution. |

Tools should return structured evidence references, freshness, scope, and errors. Agent outputs should identify supporting and contradictory sources, unresolved questions, proposed tasks, and dependencies. Output validation establishes structure and source consistency; it does not establish scientific truth.

## Procedure execution remains adaptive

Do not attempt to convert every customer's documentation into a complete executable process at onboarding. Resolve available applicable procedures at the point of work. Represent clear requirements as traceable obligations: preconditions, permitted operations, evidence needed, owner, deadline, approval requirement, and completion evidence. Keep uncertain interpretations explicit.

The case lifecycle is stable; the investigation's task graph can change as evidence arrives. Requirements such as notification timing and human authorization are enforced independently of the agent's plan. Pin the procedure revision used for each decision; detect newly effective revisions and reassess applicability explicitly rather than silently changing an active investigation.

## Human decisions and previous-case reuse

1. Retrieve and assess a potential prior case under the current user's permissions.
2. Present the investigation owner with its summary, similarities, differences, procedure/version differences, outcome status, and exactly what reuse is proposed.
3. Persist a pending reuse decision. Continue independent authorized work, but exclude reuse-dependent shortcuts and conclusions until explicit approval.
4. Bind approval to the current case/evidence snapshot and proposed reuse. Material changes require reassessment and, when they change what was approved, renewed authorization.
5. Save who decided, what they saw, the scope of approval, and when. Retain proposed, approved, executed, and observed-effective states separately.

QA corrections create new revisions; dependency links identify affected findings, calculations, form fields, and approvals for reassessment. Retain previous revisions. The authorized person or system closes the case after required work; report generation alone cannot close it.

## Persistence and recovery

Maintain distinct persistence concerns: case records and decisions; workflow execution checkpoints; agent session checkpoints; original evidence; derived artifacts; and prior-case retrieval indexes. One database technology may host several concerns, but an agent transcript is not the case record, and workflow history is not a substitute for the organization's quality record.

Use optimistic concurrency for case edits and explicit run IDs for agent work. Accept results only if their source/case versions remain applicable. Persist an action intent before delivery, use a stable idempotency key where supported, retain the external acknowledgment, and reconcile uncertain results. Notification delivery needs the same care. Do not claim exactly-once external execution from a workflow engine alone.

Model calls, document extraction, network I/O, and external actions belong in retry-aware activities outside deterministic workflow replay. Decide retry policy per operation; retain completed activity results and checkpoint long investigations to avoid unnecessary model reruns. Persisted SDK sessions alone do not supply reliable multi-day timers, cross-process coordination, or external-action reconciliation.

## Fit with the existing repository

Inspection found these foundations; their presence does not prove a live integration or end-to-end production behavior:

- `backend/src/manufacturing_data/`: source preservation, scoped tools, normalization, retrieval and verification. Retain this boundary.
- `backend/src/prime_runtime/harness.py`, `sdk_runner.mjs`, `bridge.py`, `coordination.py`: the existing Prime lead/worker runtime, saved sessions, tool budgets and scoped bridge. Keep it behind a domain activity interface instead of introducing a competing agent loop.
- `backend/src/workflows/manufacturing.py`: SQLite case/report updates, human review, tasks and closure. Extend toward the confirmed workflow; do not assume current demonstration triage rules are approved site policy. Its distinct-reviewer enforcement also needs reconciliation with the agreed allowance for one person to hold owner and QA responsibilities where organizational policy permits.
- `backend/benchmark/knowledge/digital_thread.py`: controlled-document revision and source-byte foundations, case version checks and outbox abstractions. Reuse useful contracts; establish transaction and delivery guarantees before treating separate writes as atomic.
- `backend/benchmark/application/connector_monitor.py`: generic polling and event-to-case behavior, not evidence of native MES/LIMS/QMS integration.
- `backend/src/cloud_backend/schema.sql`: existing job idempotency and audit patterns. Evaluate reuse before introducing another queue/store. This job layer is not by itself a complete long-running case workflow.

These currently separate paths need integration. Avoid adding another parallel case store or duplicating their responsibilities. Prime's local process/kernel is not an isolation boundary; confidential deployments need enforced filesystem/network/tool isolation and verified identity, beyond scope filters in a prompt or bridge.

## Architecture alternatives

| Option | Advantage | Cost / limitation | Recommendation |
| --- | --- | --- | --- |
| Database-backed case state + job workers + existing Prime runtime | Smallest extension; quickest supervised vertical slice | Application must implement reliable waiting, deadlines, retries, concurrency and reconciliation | Suitable demonstration baseline; test failure recovery explicitly. |
| Durable workflow engine + case services + existing Prime runtime | Explicit long waits, resumable work, timers and activity coordination | Additional operational component, replay/versioning discipline and integration work | Recommended target for real multi-day workflows. Temporal is the first candidate to evaluate. |
| Agent graph owns case lifecycle and reasoning | Convenient agent-state and human-interrupt primitives | Risks conflating reasoning state with domain authority; side effects still need authorization, idempotency and reconciliation | LangGraph is a valid candidate when its graph model simplifies the implementation; assess against retaining Prime, not as an automatic additional layer. |
| Autonomous multi-agent organization per department | Parallel specialist exploration | More coordination, context fragmentation, cost and authority boundaries; no demonstrated need here | Defer until a controlled comparison shows benefit for specific independent subtasks. |

These recommendations are our engineering judgment informed by the sources below, not published evidence that one framework is best for pharmaceutical manufacturing. Temporal and LangGraph are not equivalent products: the former can coordinate the full durable business workflow; the latter offers agent graph execution/persistence. They can coexist, but that is additional complexity requiring a measured reason.

## Initial stack recommendation and decision gate

Keep the current FastAPI/Python domain and evidence code, existing Prime runtime, and current local stores for the first supervised slice. For a shared deployment, evaluate the existing PostgreSQL/job infrastructure for authoritative coordination records and object storage for original/versioned artifacts. SQL relationships and filtered text search are a sufficient initial retrieval baseline; add vectors/reranking when retrieval evaluation demonstrates improvement. A separate knowledge-graph database, Kafka cluster, or model fine-tuning is not a prerequisite for this workflow.

Choose Temporal as the leading durable-execution candidate, but keep that dependency provisional until a small technical comparison demonstrates:

- waiting for an owner decision across worker restart without blocking independent work;
- correct escalation/notification timers during missing evidence and review;
- handling a worker failure after an external system accepted a write but before acknowledgment was persisted;
- rejecting stale agent output after a reviewer correction or procedure change;
- cancellation, access revocation, and exclusion of unapproved prior-case reuse;
- migration of an in-flight case when application workflow code changes.

Compare the same scenarios using the current database/job foundations. This is an engineering experiment, not another broad product interview. Choose the implementation with the lowest total development, operation, and reviewer effort that satisfies the required behavior. Do not install or migrate infrastructure merely to complete this document.

## Four-pillar assessment and acceptance measures

| Pillar | Architectural contribution | Trade-off and observable measure |
| --- | --- | --- |
| Easy to Start | Existing sources, incremental ingestion, useful partial results | Track configuration effort, manual preparation, and time to first useful source-backed package. Procedure ambiguity can slow a dependent step; it should not halt unrelated work. |
| Easy to Trust | Typed claims, source/version links, enforced authority, correction dependencies | More metadata and validation work. Track unsupported/incorrect claims, source verification correctness, approval bypass attempts, and reviewer correction time. |
| Easy to Act | Durable tasks, notifications, review, authorized delivery and outcomes | More state handling. Track timely handoffs, duplicate/missed deliveries, task completion, and whether outcomes are actually recorded. |
| Easy to Adopt | Modular connectors, retained systems of record, replaceable model/runtime adapters | Integration and deployment still require real work. Track setup, permissions, training, maintenance and customer validation effort; do not substitute token cost alone. |

Evaluate one lead against bounded workers on identical evidence, tools, tasks, and budgets; measure evidence coverage, claim quality, contradiction handling, correction effort, latency and cost. Add missing/conflicting evidence, malicious document instructions, stale SOPs, denied access, misleading prior similarity, unresolved prior outcomes and crash/retry scenarios. Deterministic checks cover invariants and numerical/source consistency; qualified human assessment covers scientific and procedural adequacy. No numerical benefit or compliance claim has been validated here.

## Primary sources supporting the design comparison

- [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) distinguishes predefined workflows from model-directed investigation and discusses starting with simple composable patterns.
- [Anthropic: Multi-agent research system](https://www.anthropic.com/research/multi-agent-research-system) describes lead/worker research and its coordination/cost trade-offs; its reported results do not establish pharmaceutical performance.
- [Temporal: Workflow execution](https://docs.temporal.io/workflow-execution), [Python message passing](https://docs.temporal.io/develop/python/workflows/message-passing), and [Activity execution](https://docs.temporal.io/activity-execution) document durable orchestration, external messages, and activity lifecycle/retries.
- [LangGraph: Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) document checkpoint/store distinctions, human waits and replay-related side-effect concerns.
