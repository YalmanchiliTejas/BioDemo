# Reading guide: persistent manufacturing agents

Researched 2026-10-23. This updates the emphasis of the [earlier reading guide](deviation-agent-architecture-reading.md) in response to the user's clarification: agents should carry context across long-running batch work, incorporate new information, and proactively propose yield and quality improvements. The [governing product direction](../../Main_Culture_andETHOS.md) still applies. This is architectural research, not proof of manufacturing effectiveness or a vendor selection.

## What changes in the design question

The central question is how an agent maintains an evolving objective and understanding across many activations, with new measurements, corrections, pending decisions, and outcomes. An individual deviation case is one piece of that work. A recoverable long-lived agent need not keep one model request, process, or context window open for the entire batch.

Our design inference is to preserve durable session history and source evidence, maintain a current versioned understanding with links to that evidence, and reconstruct a focused working context whenever the agent resumes. Arrival of relevant data, a schedule, or a human decision can trigger reassessment. Dependencies should identify which earlier recommendations need revision. These are proposed application requirements; the sources below do not supply a complete manufacturing implementation.

## Read in this order

### 1. Separate agent lifetime from process lifetime

[Scaling Managed Agents: Decoupling the brain from the hands — Anthropic, April 8, 2026](https://www.anthropic.com/research/managed-agents)

The article separates session history, the model/tool harness, and execution environments. Context can be interrogated from a durable event log even after compaction; recovery does not depend on a particular harness process surviving. It also describes keeping credentials outside generated-code environments.

**Apply here:** Give an ongoing manufacturing objective a durable identity and recoverable history. Keep batch evidence and pending work available when workers restart or models change. Do not couple all continuity to one sandbox.

**Decision:** Which pieces survive a restart, and how does a fresh worker reconstruct the latest state and unfinished intent?

**Limit:** This is first-party infrastructure experience, not a manufacturing performance result. The [current overview](https://platform.claude.com/docs/en/managed-agents/overview) labels Managed Agents beta; dreaming and MCP tunnels are more limited research previews. The same docs describe tasks running minutes or hours, so a weeks-long batch mission requires explicit lifecycle design and evaluation beyond that claim. Assess deployment and data-retention terms directly before adopting a managed service.

### 2. Keep context recoverable and selective

[Context Engineering: How Deep Agents Remember — LangChain, October 14, 2026](https://www.langchain.com/blog/context-engineering-deep-agents-remember)

This current harness walkthrough combines large-result offloading, recoverable summarization, on-demand skills, isolated subagent context, and file-backed long-term memory. It describes ownership of memory outside the model provider and customizable context-management behavior.

**Apply here:** Large historian traces and old intermediate drafts should remain queryable without entering every inference. Carry compact current objectives, unresolved questions, evidence references, decisions, and relevant changes into the next reasoning step. Fetch original detail when needed.

**Decision:** What belongs in immediate context, what is loaded on demand, and what must remain recoverable after repeated compaction?

**Limit:** File-backed memory supplies a storage mechanism. Manufacturing authority, provenance, access revocation, scientific correctness, and correction dependencies remain application responsibilities. An agent-editable instruction file must not silently override an approved procedure.

### 3. Treat cross-session memory as an observable subsystem

[Built-in memory for Claude Managed Agents — Anthropic, April 23, 2026](https://claude.com/resources/articles/claude-managed-agents-memory)

This product announcement describes file-based memory shared across sessions, scoped permissions, exported memory, change attribution, audit logs and rollback. It labels memory public beta and reports customer/internal results.

**Apply here:** Separate memories about a particular batch from reusable organizational knowledge. Retain the origin, scope, revision, and review status of a memory. A human correction should change future context, while prior claims remain traceable.

**Decision:** Which knowledge may the agent update itself, which requires review, and how is incorrect or revoked knowledge removed from future use?

**Limit:** Customer percentages are reported by the vendor and do not predict batch yield or correctness. Memory availability does not establish that retained lessons are true. Previously agreed owner approval before prior-investigation acceleration still applies.

### 4. Evaluate memory formation, not just recall

[Evaluating Memory in Production Agents — Letta, July 28, 2026](https://www.letta.com/blog/evaluating-memory-in-production-agents/)

The authors distinguish using existing memory from creating and repairing it. Their private Context-Bench V2 uses production-inspired profiles and synthetic scenarios to examine retrieval, adherence, generalization, and memory hygiene. It highlights stale, duplicated and contradictory memory as long-lived-agent failure modes.

**Apply here:** Test whether corrected identifiers, superseded procedures and revised interpretations actually change later recommendations. Check that a failed intervention is not remembered as successful. Evaluate what survives several cycles of consolidation and model replacement.

**Decision:** Can the agent improve from reviewed outcomes without turning one local observation into an unjustified general operating rule?

**Limit:** This is a vendor's private benchmark with simulated interactions and model judging. Use its evaluation dimensions, not its model ranking, as the basis for our own domain evaluation. The related [Memory Models: Towards Agents That Learn](https://www.letta.com/blog/towards-agents-that-learn/) (June 25, 2026) discusses token-space learning and memory rot; its future architecture claims are research hypotheses.

### 5. Understand proactive computation between interactions

[Sleep-time Compute: Beyond Inference Scaling at Test-time — Lin et al., April 17, 2025](https://arxiv.org/abs/2504.13171)

The paper studies offline reasoning about context before a query arrives, amortizing preparation across related future questions. Its demonstrations use modified mathematical tasks and a software-engineering case study.

**Apply here:** During authorized background work, an agent could maintain relevant comparison cohorts, update data-quality checks, organize fresh evidence, and prepare questions for a batch owner. New source revisions should invalidate affected prepared artifacts. Precomputation has a budget and a measurable purpose.

**Decision:** Which preparation is likely to help the next real decision, and when should the agent wait rather than spend more compute?

**Limit:** This is not evidence of predictive control or yield optimization. Preparation may become stale, and benefit depends on the predictability of future queries. A background hypothesis remains a hypothesis until supported and reviewed as required.

### 6. Study progress across context boundaries

[Effective harnesses for long-running agents — Anthropic, November 26, 2025](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)

This coding-focused experiment uses an initial setup, explicit work state, incremental progress and persistent handoff artifacts to continue across context windows. It describes premature completion, unclear handoffs and inadequate verification; compaction alone did not solve them.

**Apply here:** After each activation, retain what changed, the evidence inspected, open hypotheses, blocked decisions, next useful work, and conditions that should wake the agent again. Define success over an ongoing objective rather than treating report generation as mission completion.

**Decision:** After three shifts and a context reset, can a new agent activation explain what is known, what changed, what remains uncertain, and what it intends to do next?

**Limit:** Do not copy the initializer/coding-agent split as a required manufacturing topology. The April 2026 Managed Agents article explicitly notes that some older harness accommodations became unnecessary as models improved. Re-evaluate mechanisms against current models and the manufacturing job.

## Architecture comparisons these readings enable

| Choice | Simpler option | More ambitious option | Test that should decide |
| --- | --- | --- | --- |
| Agent continuity | Persistent mission state, event-triggered resumptions, current context reconstruction | Coordinated persistent specialists with shared and private memories | Better investigation/recommendation quality and less reviewer effort across the same long replay |
| Context management | Source-linked state plus recoverable history and explicit change sets | Automated memory consolidation and learned context management | Retention of corrections, contradictions and critical details after repeated compaction |
| Proactive work | Scheduled/relevant-event reassessment with bounded tools | Background exploration and reusable skill/memory proposals | Useful lead time and accepted recommendations versus wasted computation and alert burden |
| Runtime | Extend existing Prime harness behind stable domain interfaces | Adopt another stateful harness or managed runtime | Recovery, context fidelity, sandbox controls, integration effort and maintainability in comparable tests |

Our manufacturing evaluation should replay a batch timeline in order, with delayed and corrected measurements, rejected hypotheses, new procedure revisions, denied/revoked access, restarts and human decisions. Measure recommendation freshness, evidence support, missed changes, stale recommendation withdrawal, recovery, reviewer effort and alert burden. Compare proposed yield improvements with actual observed outcomes only when an authorized intervention and suitable evidence exist; do not attribute causation from correlation.

All four pillars remain joint constraints: automatically gathering usable context reduces preparation; recoverable evidence and explicit uncertainty aid verification; durable recommendations and outcomes support action; existing-system integration and portable state support adoption. Persistent agents add storage, compute, memory-maintenance and oversight costs. Those costs should earn their place through reduced total organizational effort and better supported decisions.
