# Long-horizon manufacturing agents

Status: revised architecture proposal, 2026-10-23. The user requested persistent context, long-running tasks, current-information updates, and proactive suggestions to improve yield and batch correctness. This expands the prior deviation-focused architecture. Details below are recommendations, not recorded user acceptance or implemented behavior.

Follow-on: the user's request to re-engineer the full life-sciences offering is developed in the [platform engineering plan](life-sciences-platform/README.md). That package contains the current detailed stack recommendation, decisions and capability checklist; this document retains the long-horizon rationale.

Governing source: [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md). Preserve the [confirmed deviation requirements](deviation-workflow-discovery.md) within this broader direction. Current research: [long-horizon reading guide](../research/long-horizon-agent-reading.md).

## Architectural correction

The primary abstraction should be an ongoing manufacturing mission with persistent state and context. Deviation cases, procedure-driven tasks, and QA packages are activities within or linked to that mission. A mission can span a batch or campaign and continue learning from authorized outcomes across batches. Its exact scope and retention are organizational configuration, not an assumption that every entity needs a separate autonomous agent.

Durable execution remains useful infrastructure. It does not by itself supply persistent scientific understanding, evidence revision, or useful optimization. Do not select a workflow engine and treat that selection as the agent architecture. Likewise, a larger context window or indefinitely running process does not establish reliable memory or good recommendations.

## Proposed components

| Component | Responsibility |
| --- | --- |
| Persistent mission | Objective, scope, accountable owner, permitted operations, constraints, pending questions, plans, stop conditions, and explicit handoff/archive rules. |
| Event intake and scheduler | Subscribe to authorized source changes and timers; deduplicate, order where possible, detect gaps, coalesce noisy events, wake appropriate missions and schedule substantive background analysis. |
| Durable evidence and session history | Retain source revisions and relevant reasoning/tool/decision artifacts outside disposable workers. Distinguish source event time from when information became available. Preserve corrections rather than overwriting history. |
| Current manufacturing state | A versioned projection of what is known about the batch/process/equipment: observations, calculations, uncertain mappings, open hypotheses, contradictions and pending results. This is a sourced interpretation, not a replacement official record or proven digital twin. |
| Context assembly | Construct each reasoning session from mission goals, current state, new information, unresolved work and relevant authorized history. Keep raw history retrievable. Summary compaction is an index into evidence, not the sole surviving record. |
| Agent harness | Resume work, plan dynamically, call tools, delegate scoped questions, save progress, observe budgets, handle cancellation, and schedule follow-up. Separate the harness from persistent storage and isolated tool environments. |
| Scientific and optimization tools | Reproducible normalization, process comparisons, trajectories, statistical checks, applicable predictive/process models and constrained candidate evaluation. The language model coordinates these tools and explains their outputs. |
| Recommendation and outcome service | Versioned proposals with evidence, assumptions, trade-offs, authority requirements, expiration/reassessment conditions and measurable outcomes. Track rejected, revised and unsuccessful advice as well as successful outcomes. |
| Authority and integration gateway | Enforce access, source applicability, prior-case reuse approvals, notification policy and consequential-action approval independently of model instructions. Record external action receipts and reconcile uncertain delivery. |

These are logical responsibilities. Start with modular services and workers around existing code; they do not each require their own database or deployment.

## Continuous reasoning loop

1. Receive new evidence, a timer, a human correction, or a relevant outcome.
2. Persist the event with scope, source version, event time and availability time. Update the current-state projection and identify dependent claims or proposals affected by the change.
3. Wake the mission with a context package explaining what changed and what remains open. Apply current access checks to retained memory and retrieved history as well as new data.
4. Let the agent choose useful work: retrieve evidence, run checks, compare trajectories, explore hypotheses, delegate independent questions, or wait for a discriminating result. If a source is disconnected, represent the gap explicitly.
5. Validate calculations, citations, proposal constraints and authority. Persist progress and recommendation revisions. Reject or rebase stale worker output when relevant state changed during its run.
6. Deliver a meaningful update, request an authorized decision, schedule a check, or suspend until new information. A session ending does not complete the mission.
7. Compare later observations with the recommendation's stated expectations. Incorporate qualified feedback with provenance; do not infer causal effectiveness merely because a later batch did better.

Logical continuity can span days or weeks across many reasoning sessions. Heavy analysis can run for hours when useful; waiting for a lab result should not require continuous model inference. Use explicit statuses such as analyzing, waiting for evidence, waiting for approval, interrupted, or paused by the owner. Persistent responsibility must remain visible and controllable.

## Context and memory need distinct treatment

- **Working context:** the bounded inputs for the current reasoning session; refresh when important evidence arrives.
- **Mission state:** current objectives, versioned assessment, plan, questions, dependencies, and pending decisions. Recoverable across restarts and context compaction.
- **Episodic history:** what was observed, proposed, decided, executed and subsequently measured, with source and actor references.
- **Reusable knowledge:** authorized procedure versions, confirmed mappings, process context, and reviewed lessons whose applicability and provenance remain inspectable.

Background consolidation may prepare summaries, indexes, contradiction checks and possible lessons. It must retain links to originals and mark unreviewed interpretations. It cannot silently turn a failed investigation into a successful precedent, change an SOP, grant permission, or update model weights. Experience storage, runtime context changes, model retraining and approved procedural change are different operations.

Pin each analysis to an evidence/version snapshot while allowing the mission to advance to newer snapshots. When new evidence contradicts a prior interpretation, mark affected advice as stale, revised or withdrawn, and notify recipients where material. A late-arriving result can change today's assessment without rewriting what was knowable yesterday.

Keep the agreed prior-investigation reuse gate: the owner receives the previous investigation summary, similarities, differences and proposed acceleration, and explicitly approves before reuse-dependent work proceeds. General memory retrieval is not a permission bypass. Reassess applicability under changed processes, procedures, evidence or outcomes.

## Yield and batch quality are explicit objectives

Use "batch correctness" provisionally to mean conformance to applicable specifications/procedures plus evidence and record consistency. The exact quality attributes, yield definition, process stage and available interventions require site/process-specific definition before optimization. Do not collapse them into one unqualified score.

An agent should be able to identify an emerging issue before a deviation exists, investigate why yield is trending differently, propose the next useful measurement or analysis, and suggest a supported intervention for review. The first recommendation may be a data-quality correction or a targeted evidence request rather than a process adjustment.

Each proposal should record the objective, current evidence, applicable process stage, alternatives including continuing the current plan, expected effect and basis, uncertainty, quality trade-offs, feasibility within approved bounds, responsible owner, required approval, and outcome measures. A numeric predicted yield gain requires an appropriate evaluated model or supporting evidence; the language model must not invent it.

Use historical comparisons carefully: differences in materials, equipment, stage, recipes, sampling and operating conditions can confound apparent improvement. An observational association supports investigation, not a proven causal intervention. Predictive models, simulations, optimization algorithms or digital twins should be added where relevant data and verification justify them, with their validity range exposed.

Recommendations may update as evidence changes. Consequential manufacturing changes retain explicit human authorization and applicable system controls. Broader standing permission for gathering, analysis, drafts and configured routing remains intact; do not add approval to every reasoning step.

## Existing code: extend rather than restart

Inspection during this revision found saved Prime sessions and scope/as-of parameters in `backend/src/prime_runtime/harness.py`, context compaction policy in `compaction_policy.mjs`, lead/worker progress and finalization in `investigation_lifecycle.mjs`, and candidate hypothesis storage in `backend/src/state/causal_hypothesis_graph.py`.

Those are useful capabilities, but the current harness starts with an incident objective and ends on report submission. Its default finite run deadline, saved session file and summary policy do not establish continuous batch supervision, proactive scheduling, new-evidence invalidation or multi-day outcome learning. Do not simply remove the deadline and call it a long-horizon architecture.

Wrap the existing runtime behind a mission execution interface. Generalize incident-bound context into mission scope with linked cases. Preserve finite budgets for each execution, shared progress and scoped tools, while making mission continuity independent of any subprocess. Reuse existing evidence, review, jobs and audit contracts where suitable, and integrate competing state paths rather than adding another disconnected store.

## Runtime options to compare

| Option | Why consider it | What remains to demonstrate |
| --- | --- | --- |
| Extend existing Prime runtime | Already integrated with manufacturing tools, citations, scoped access and saved investigations | Mission/session separation, incremental updates, context recovery, isolated execution, proactive wakeups and recommendation/outcome tracking. |
| Evaluate a current long-horizon harness, such as Deep Agents | Current context management and persistent execution abstractions may reduce custom harness work | Tool/permission compatibility, migration cost, memory correctness and behavior on manufacturing tasks. |
| Evaluate managed long-horizon sessions, such as Claude Managed Agents | Separates session storage, harness and tool environments; may reduce runtime operations | Current beta limitations, deployment/data constraints, integration behavior and portability. |
| Evaluate a stateful-agent runtime, such as Letta | Explicit persistent memory and background context preparation are relevant patterns | Memory revision, evidence fidelity, concurrent access, authorized reuse and performance on the same tasks. |

These are evaluation candidates, not an instruction to combine all four. Compare continuity, evidence updates, useful suggestions and operating effort rather than publication date alone. Temporal or an existing durable scheduler may support wakeups, timers and delivery underneath any chosen harness; neither defines the reasoning architecture by itself.

## Test the long horizon directly

Replay a staged synthetic batch with evidence revealed according to availability time, not all supplied at once. Include normal progress, emerging yield concern, missing/late lab data, a corrected reading, reviewer disagreement, misleading historical similarity, a procedure revision, access revocation, a worker crash and a result arriving after a proposal was drafted. Continue through an authorized decision and observed outcome.

Compare a simple persistent mission using the current runtime against one candidate harness before expanding the stack. Evaluate whether it remembers unresolved obligations, revises only affected claims, retrieves originals after compaction, avoids repeating work, withdraws stale advice, respects approvals, and produces scientifically supportable recommendations. Use qualified review for process and quality judgments.

Across the four pillars measure preparation and time to first useful insight; source correctness, staleness and reviewer effort; useful next steps and observed outcomes; integration, operator attention and maintenance burden. Persistent monitoring can increase noise, memory errors and cost: use event coalescing, user-visible ownership, budgets and escalation rules. Do not report validated yield improvement or quality benefit without evidence. Numerical targets remain unset.

## Sources for the revised abstraction

- [Anthropic, April 8, 2026: Scaling Managed Agents](https://www.anthropic.com/research/managed-agents) motivates independent session history, harness and execution environments. This proposal's manufacturing mission model is our inference, not a feature established by that article.
- [Anthropic, November 26, 2025: Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) discusses progress across context windows and the limits of compaction alone in a software-development demonstration.
- [LangChain, October 14, 2026: Context engineering with Deep Agents](https://www.langchain.com/blog/context-engineering-deep-agents-remember) describes current strategies for moving information outside active context while retaining access.
- [Sleep-time Compute, 2025 paper](https://arxiv.org/abs/2504.13171) explores preparatory inference over context; it is a research motivation for background consolidation, not evidence of manufacturing optimization.

All sources inform engineering choices. None establishes batch-quality correctness, safe process optimization or manufacturing readiness for BioDemo.
