# Proactive assistant architecture contract

Status: product requirement recorded 2026-11-02; integration design and acceptance criteria, not a claim of implemented or validated behavior. Governing direction: [the four pillars](../../Main_Culture_andETHOS.md). This makes the assistant requirement explicit within the [existing long-horizon proposal](long-horizon-manufacturing-agents.md); it does not replace the product's other entry points or systems of record.

Implementation update, 2026-11-02: a local implementation now connects permission-checked workspace tools, bounded plan/tool/observe rounds, persistent mission responsibilities, source-event and scheduled follow-up, and owner controls. See the [implementation and verification record](../research/proactive-assistant-implementation-20261102.md) for demonstrated behavior and limits. The broader requirements below remain acceptance criteria, not a claim that every scenario or domain has been validated.

## Job and reference

A manufacturing user should be able to give the assistant an ongoing responsibility, obtain useful work from authorized existing context, inspect the evidence and proposed actions, and return later without reconstructing the task. The assistant should also respond to relevant changes while the user is away. Its work may concern investigations, deviations, scheduling, ingestion, technology transfer, or another supported objective.

The user confirmed [OpenAI Dots](https://chatgpt.com/features/dots/) as a reference. Its public description establishes ongoing responsibilities, connected tools, work between conversations, and owner review and control. [Official task and memory documentation](https://learn.chatgpt.com/docs/dots/tasks-and-memory) informs the separation of tasks, context, and saved memory. These behaviors motivate our requirements; they do not establish Dots' internal implementation. The user also named Muse, but has not confirmed which Muse product. Keep that identity provisional; see the [reference and code audit](../research/proactive-assistant-reference-audit-20261102.md).

## Architecture to extend

Use one durable mission as the responsibility boundary. A conversation, source change, timer, or human correction can activate it. Reuse the existing scheduler and coordinator for execution, and extend Prime through a versioned production task interface for open-ended reasoning. Keep deterministic tasks on their existing paths. [ADR 0003](../adr/0003-persistent-missions-and-runtime-boundaries.md) remains proposed; this contract does not claim a production Temporal deployment exists.

Current implementation choice: extend the existing Python conversation/gateway/FlowService execution path into bounded iterative work and reuse mission scheduling. This runs within the current deployment's Python dependency boundary. Prime remains a specialized investigation harness; its general production task interface and worker packaging are not implemented by this change. This chooses a smaller deployable integration over immediately migrating the assistant into the separate Node/SDK runtime. The resulting tool set is bounded to registered capabilities, with no general browser, terminal, or private vendor harness parity claim.

| Boundary | Required behavior | Existing seam and remaining work |
| --- | --- | --- |
| Mission | Persist owner, objective, scope, constraints, plan, unresolved work, corrections, decisions, and stop conditions. | `lifesci/missions.py` has persistent mission state and fenced activations; connect assistant responsibilities to it. |
| Discovery and tools | Search and inspect authorized records before requesting uploads. Retrieve originals and related evidence as the task requires. | Current conversation sources are attachment-oriented. Extend discovery across current platform services with tenant, site, record, and owner checks. Prime's legacy scope string alone is insufficient authorization. |
| Reasoning harness | Plan, call bounded tools, inspect results, revise, checkpoint, and resume against a versioned evidence snapshot. | Generalize Prime's incident/report contract for production mission tasks; its evaluation-only `task_answer` is not a production interface. Keep the gateway responsible for routing, usage, and budget enforcement. |
| Events and waiting | Wake for subscribed changes or due work, coalesce noisy events, retain unhandled events, and survive retry or worker replacement. | Existing runtime and scheduler provide the execution boundary. General event-driven reasoning is not currently wired into it. |
| Memory | Separate current working context, durable task state, episode history, and reviewed reusable knowledge. Recheck access on retrieval. | Mission context and checkpoints are starting points. Preserve originals, corrections, source versions, and the existing prior-investigation reuse approval gate. |
| Scientific work | Choose applicable statistical or mechanistic tools, compare alternatives, retain assumptions and counterevidence. | Reuse registered tools and typed workflows. Model output must distinguish observations, calculations, hypotheses, recommendations, and unknowns. |
| Action and follow-up | Produce exact reviewable proposals; track approval, execution receipts, and observed outcomes separately. | Use existing action and evidence services. Enforce authority at the host boundary and revalidate evidence before committing or dispatching. |
| User control and artifacts | Show activity, blocked/waiting state, next decision, and inspectable results; accept correction, pause, or stop. | Extend current views with durable mission state. Prefer charts, tables, timelines, source views, and action cards where useful; keep conversational summaries concise. |

Prime's Node/compiled SDK, writable session storage, tools, and provider configuration must be available to the worker that runs it. The current Lambda image does not establish that deployment contract. Choose and verify the worker boundary before enabling background reasoning; neither a new prompt nor an added timer supplies the missing harness integration.

## Activation and authority contract

1. Persist the initiating request or event with owner, tenant/site scope, source revision, event time, availability time, and delivery identity. A connection alone is not a standing monitoring responsibility.
2. Acquire the existing fenced mission activation. Derive current authority from the owner; revoked permissions apply to stored memory as well as new reads.
3. Assemble bounded context from the objective, corrections, unresolved work, relevant changes, and authorized history. Report omissions, unavailable sources, and stale evidence. Source text remains untrusted data.
4. Perform deterministic work directly or invoke the bounded reasoning harness through the gateway. Persist tool results and progress. Apply request, tool, time, and spend limits; unknown hosted billing remains unknown rather than zero.
5. Validate evidence versions, claim support, tool outputs, and action authority before persisting a finding or proposal. A replaced worker or changed basis cannot commit an authoritative result.
6. Publish a useful artifact or decision request, continue authorized work, or persist an explicit wait and wake condition. Mark an event handled only after its outcome or actionable blocked state is durably recorded. Retry deduplication must cover findings, notifications, and external side effects as well as event delivery.
7. Reassess affected recommendations when evidence changes. Follow up on outcomes without treating a subsequent improvement as proof of causation.

Standing permission for scoped reads, analysis, and drafts should remove repetitive setup. Consequential manufacturing operations, external communications, and system-of-record changes retain their applicable explicit human authorization. The host enforces this independently of model instructions. Owners must be able to inspect and change responsibilities, subscriptions, notification behavior, and budgets.

## Concrete acceptance example: latest deviation

For “What is the latest deviation and why did it happen?”, search authorized deviation cases and related evidence before asking for a file. Identify the ordering basis: occurrence time when reliably available, or explicitly state that only case-opened time is known. Do not substitute conversation-save time for deviation time. Handle missing dates and ties explicitly.

Show a short result with the case, chronology, evidence links, documented findings, competing hypotheses, and next useful action. If the cause is not established, say what is known and what would discriminate among hypotheses. Saved synthetic assay reviews may be discoverable as demonstrations but must remain labeled as such; their presence in a “Deviations” UI tab does not make them formal deviation records. A successful search with no accessible case should report that result and the scoped gap before requesting more context.

This example tests general discovery and investigation. It must not become a special-case handler standing in for the general harness.

## Alternatives and trade-offs

| Option | Benefit | Limit or cost |
| --- | --- | --- |
| Add authorized discovery to the existing one-shot conversation planner | Removes manual attachment friction with a small integration. | Does not provide iterative investigation, persistent responsibility, or background follow-up. Useful foundation only. |
| Connect missions, scoped tools, Prime, and existing scheduling | Supports the requested ongoing responsibility and multi-step work while preserving platform records. | Requires a general production task contract, permission-aware tool bridge, worker packaging, and recovery testing. This is the target integration. |
| Replace the harness or add broad standing discovery immediately | Might supply additional runtime capabilities. | Adds migration, operation, noise, and spend before existing seams are exercised. Evaluate only against measured gaps in the target integration. |

Across all four pillars: discovery reduces user preparation (Start); provenance and current authorization make findings reviewable (Trust); durable proposals and outcome tracking make work useful (Act); existing connectors, records, and modular workers reduce migration (Adopt). Background discovery adds inference cost and attention burden, so wake for meaningful changes and measure useful outcomes per activation. Idle waiting should not consume continuous inference.

## Evidence required before claiming completion

Run contract tests and bounded live-model scenarios separately. Contract doubles establish host behavior, not model accuracy. Record the actual provider, returned model identity, tool trace, source revisions, outputs, failures, usage, and billing coverage for live runs. Preserve failed runs and identify local versus deployed verification.

| Scenario | Pass evidence |
| --- | --- |
| New question without attachments | Discovers permitted relevant records; reports latest using the correct timestamp basis; no invented cause. |
| Multiple domains | Investigation, scheduling, ingestion, and transfer tasks use the same responsibility/tool interfaces; outputs match the job. |
| New evidence and correction | Resumes the mission, updates affected findings, preserves contrary evidence and corrections, and withdraws stale proposals. |
| Restart, duplicate delivery, worker replacement | Recovers unfinished work without losing events, duplicating side effects, or accepting a stale worker's commit. |
| Revoked access and injected source instructions | Host blocks unauthorized retrieval/action; source instructions cannot grant authority or expose another owner's private conversations. |
| Approval, pause, and budget boundaries | Stops or waits at the correct boundary; pause survives restart; exhausted or unavailable inference produces a visible recoverable state. |
| Proactive follow-up | A relevant subscribed change produces one useful update without a new chat message; irrelevant or duplicate events do not repeatedly notify. |

Measure retrieval recall and precision against a labeled corpus, supported-claim rate, appropriate abstention, decision quality under qualified review, duplicate/missed updates, user preparation and review time, end-to-end p90/p99 latency with sample counts, and cost per useful outcome. Set task-specific thresholds before evaluation. Do not infer reliable tail latency from a few demo runs or claim that this contract itself validates the product hypothesis.
