# Reading guide: deviation agent architecture

Researched 2026-10-23 against the linked primary sources. This guide supports the [agreed workflow](../product/deviation-workflow-discovery.md) under [the governing product principles](../../Main_Culture_andETHOS.md). It does not select a vendor, establish pharmaceutical performance, or demonstrate compliance.

## Working architectural hypothesis

Our inference from these sources and the agreed requirements is to start with durable case coordination, explicit permissions and approval gates, reproducible data tools, and a bounded investigation agent. The workflow owns deadlines, review state, and consequential transitions. The agent can choose evidence searches and propose interpretations within its authorized task. Introduce independent agents only where measured investigation quality or elapsed time justifies their coordination and operating cost.

That is a hypothesis to test against the existing implementation and representative cases, rather than a conclusion established by a vendor article. The architecture must support ambiguous investigations without giving a model sole authority over the case lifecycle.

## Read in this order

### 1. Understand where agents belong

[Building effective agents — Anthropic, December 19, 2024](https://www.anthropic.com/research/building-effective-agents)

The authors distinguish predefined code paths from agents that dynamically choose their next steps. They explain routing, parallelization, orchestrator/worker, and evaluator/optimizer patterns, and recommend increasing complexity only when simpler solutions fall short. The page now warns that tooling has changed since publication; use it for architectural distinctions rather than a current framework comparison.

**Apply here:** Keep notification deadlines, authorization checks, status transitions, and form validation explicit. Use adaptive reasoning for deciding what evidence to inspect next, identifying gaps, and developing hypotheses.

**Decision:** Which steps truly require model-directed planning, and which have an executable rule or reliable calculation?

### 2. Separate memory from durable state

[Agent memory and state — Temporal documentation](https://docs.temporal.io/ai/featured/memory-state-stripe)

This worked example separates current model context, cross-run memory, execution progress, and externally owned effect state. Its crash demonstration shows why recovering past knowledge does not establish where execution stopped or whether an external action happened. It provides source code and labels its offline stand-ins and optional live paths.

**Apply here:** Prior-investigation retrieval, the current case record, pending approvals, and receipts from existing systems have different owners and lifecycles. A summary of a previous case cannot replace the case's actual decisions or observed outcomes.

**Decision:** After a worker dies, what tells a new worker that owner approval is pending, that QA was notified, or that a submission actually reached the QMS?

**Limit:** This is a support/refund example; its recovery demonstration does not validate manufacturing integrations.

### 3. Design human pauses and recovery together

[Interrupts — LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/interrupts)

The guide shows durable pauses awaiting external input, checkpoint/thread identifiers, and resumption. Crucially, an interrupted node runs again when resumed, so preceding side effects require care: separate them into their own steps or make them idempotent. A pause primitive is an execution mechanism; application code still needs to authenticate the respondent and verify their authority.

**Apply here:** Request owner approval for a particular prior investigation and proposed reuse. Independently authorized evidence collection can continue while that branch waits. Tie the response to the exact proposal being reviewed; changes to material inputs need application-level reassessment.

**Decision:** What is paused, what may continue, who can resume it, and how will an outdated approval be detected?

**Limit:** A checkpoint or interrupt does not by itself implement the product's evidence, authorization, or official-record requirements.

### 4. Make retries safe at integration boundaries

[What is idempotency? And why it matters for durable systems — Temporal, February 27, 2024](https://temporal.io/blog/idempotency-and-durable-execution)

The article explains why retried activities can execute more than once, and demonstrates idempotency keys and database uniqueness checks. Durable orchestration does not make every remote API effect occur exactly once; the external operation's behavior remains relevant.

**Apply here:** Give each intended notification or official submission a stable operation identity and record provider receipts. If a timeout leaves the result unknown, reconcile with the destination or require resolution before a dangerous retry. That reconciliation policy is our application design implication, not a guarantee supplied by the article.

**Decision:** How will each connector distinguish failed, completed, and unknown outcomes without duplicating a quality record or notification?

**Limit:** The examples do not establish that a particular MES, LIMS, or QMS supports idempotency keys or reliable lookup.

### 5. Retrieve evidence with its context intact

[Introducing Contextual Retrieval — Anthropic, September 19, 2024](https://www.anthropic.com/research/contextual-retrieval)

The authors combine contextualized chunks, lexical retrieval, embeddings, and reranking. Exact identifiers are one reason semantic search alone can miss relevant records. Their measured retrieval gains concern their datasets and configuration; they are not expected results for our product.

**Apply here:** Preserve document identity, revision, section, and scope alongside retrieved passages. Use structured filters for authorization and applicable versions before relevance ranking. Evaluate exact batch/equipment identifiers and terminology alongside semantic questions. An apparently relevant SOP passage still requires applicability checks.

**Decision:** For a given event date, site, process, and user, how do we retrieve the right approved procedure and retain enough surrounding context to interpret it?

**Limit:** Retrieval improvements do not establish procedural authority, causal correctness, or permission enforcement. Those are separate application responsibilities.

### 6. Evaluate behavior and actual outcomes

[Demystifying evals for AI agents — Anthropic, January 9, 2026](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)

The article distinguishes tasks, repeated trials, graders, transcripts, and resulting environment state. It discusses combining automated and human evaluation, investigating failures, and maintaining evaluation suites as systems evolve. A persuasive final answer is different from a correct change in the environment.

**Apply here:** Compare architectures on the same cases: missing data, conflicting procedures, unapproved historical reuse, reviewer correction, duplicate events, and a worker crash. Grade source support and actual approval/submission state, alongside reviewer effort, elapsed time, and cost. Use domain experts for interpretation judgments; deterministic assertions can check explicit permissions and state invariants.

**Decision:** What evidence would convince us that adding a specialist agent improves the QA package rather than merely producing a longer explanation?

**Limit:** Good engineering evals support product decisions; they do not establish customer validation or regulatory compliance.

### 7. Decide whether multiple agents earn their complexity

[How we built our multi-agent research system — Anthropic, June 13, 2025](https://www.anthropic.com/research/multi-agent-research-system)

This describes a lead agent delegating parallel searches, context separation, effort scaling, and production coordination challenges. The authors report strongest fit for independent breadth-first research, with substantial token overhead. Its comparisons use their research system and evaluations; they do not show that multiple agents are inherently better for deviation investigations.

**Apply here:** Candidate parallel tasks include independent laboratory, environmental, and equipment evidence searches. Workers should return source-linked findings and gaps into shared case records. Contradiction resolution and authorization still need explicit ownership. Different prompts or professional role names do not alone justify separate agents.

**Decision:** Can the work be divided into independent questions with clear evidence contracts? Does parallel execution improve coverage or time enough to offset duplicate work, disagreement, and cost?

**Limit:** Research performance is not evidence of validated root-cause analysis. Begin with a controlled comparison against a single investigation agent using the same tools and evidence budget.

### 8. Put boundaries outside the model

[How we contain Claude across products — Anthropic, May 25, 2026](https://www.anthropic.com/research/how-we-contain-claude)

The authors discuss containment across model behavior, execution environments, and external content. An authorized connector can still return hostile content; model-level safeguards do not provide a complete access boundary. They also explain that subagents can isolate content but can introduce risk if their outputs receive unjustified trust.

**Apply here:** SOPs, historical narratives, attachments, and connector responses are content to interpret. They must not acquire authority to change permissions, expose another site's records, or approve submissions. Enforce connector scopes and consequential action gates in application services. Keep credentials outside model-generated code environments.

**Decision:** If a retrieved document instructs the agent to bypass review or send data elsewhere, which enforced boundary prevents the action?

**Limit:** These are lessons from Anthropic's products, not a ready-made manufacturing threat model or assurance claim.

## Architecture decision worksheet

Use the articles to answer these with a small executable comparison, preserving the same evidence and test cases across alternatives:

| Choice | Simpler starting option | More ambitious option | Evidence needed to expand |
|---|---|---|---|
| Investigation reasoning | One bounded investigation agent with deterministic tools | Coordinator with independent specialist agents | Better evidence coverage or reviewer effort/time at acceptable cost |
| Coordination | Persisted case transitions and durable work scheduling | Dedicated workflow engine and richer agent graph | Recovery, timer, handoff, and deployment needs that justify operational complexity |
| Procedure handling | Source-linked interpretation of scoped approved documents, with explicit execution checks | Reusable structured procedure plans with version-aware dependencies | Correctness across ambiguous/conflicting procedures and reduced setup effort |
| Knowledge access | Metadata-filtered document and structured-record retrieval | Contextual hybrid retrieval and reranking | Retrieval evaluation showing relevant omissions or poor precision |

Across every choice, measure all four pillars jointly: preparation and time to useful work; provenance correctness and reviewer correction effort; successful handoffs and observed outcomes; connector setup and organizational adoption burden. Set targets after measuring a baseline. Do not optimize agent latency alone or require users to create procedure maps before beginning.

Keep framework selection separate from the domain model: connectors, evidence, procedures, approvals, and outcomes should retain clear contracts even if the orchestration library or model changes. Select implementation technology after inspecting the repository's existing foundations and running the recovery/approval comparison.
