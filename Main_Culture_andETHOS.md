# Product Design & Architecture Principles

> **Purpose:** Persistent instructions for anyone (human or coding agent) designing, implementing, or evaluating our pharmaceutical manufacturing AI product.
>
> **Scope:** Applies to **every** interaction, feature, service, integration, agent, data pipeline, and architectural decision. These are **product-wide principles**, not a prescribed workflow, UI template, go-to-market strategy, or feature roadmap.

## Product intent

Build software that makes sophisticated pharmaceutical manufacturing intelligence **simple to begin using, easy to verify, useful for taking the next step, and practical to introduce into real organizations**.

The system may support investigation, analysis, data preparation, monitoring, collaboration, decision support, and other future capabilities. **Do not constrain the product to any one task, user persona, competitor, interface pattern, or stage of an existing workflow.** Choose designs based on the problem being solved and the four principles below.

## The four pillars

### 1. Easy to Start
**Turn existing, messy data into useful work with minimal preparation.**

**Design implications**
- Let users begin with a goal, a question, an event, or existing context; don't force them through complex setup first.
- Prefer automatic discovery and retrieval from authorized connected systems over asking users to collect, export, reformat, or upload information manually.
- Ask only for information the system genuinely cannot determine, and ask at the moment it becomes necessary.
- Show useful progress and intermediate results; handle incomplete data rather than failing silently.
- Reuse prior context, confirmed mappings, permissions, and completed work instead of asking for the same setup repeatedly.

**Architecture implications**
- Design connectors and ingestion as reusable capabilities, separate from particular UIs or workflows.
- Support messy, partial, multimodal, and inconsistent data while preserving source context.
- Make operations resumable, incremental, observable, and safe to retry.
- Prefer deterministic methods where reliable, with model-based methods for ambiguity or open-ended reasoning.
- Avoid adding mandatory prerequisites that do not directly contribute to user value.

**Test:** How much user preparation and how many manual steps are required before the first meaningful result?

### 2. Easy to Trust
**Make findings traceable, verifiable, and explicit about uncertainty.**

**Design implications**
- Clearly distinguish observations, calculated results, hypotheses, recommendations, and unknowns.
- Make it easy to inspect the underlying source, transformation, assumptions, and counterevidence without overwhelming the default view.
- Display gaps, conflicts, stale data, failed checks, and permission limits rather than hiding them.
- Allow people to challenge, correct, and review the system's conclusions.
- Avoid presenting confidence numbers as probabilities of correctness unless they are properly calibrated and validated.

**Architecture implications**
- Preserve source identifiers, versions, timestamps, transformation lineage, and retrieval context.
- Make important calculations reproducible and use explicit validations where possible.
- Separate raw evidence, derived data, agent interpretations, and approved decisions.
- Record relevant actions, model/tool versions, corrections, and human review in an auditable trail.
- Enforce authorization and data boundaries throughout retrieval, processing, memory, and output.

**Test:** Can a qualified reviewer efficiently verify where a claim came from, what supports or contradicts it, and what remains uncertain?

### 3. Easy to Act
**Turn findings into reviewable decisions, next steps, and measurable outcomes.**

**Design implications**
- Present the implication and available next steps, not just an analysis report.
- Make proposed actions specific: rationale, expected result, constraints, owner, required approval, and what evidence would change the recommendation.
- Fit decisions into users' existing work instead of making them reconstruct the plan elsewhere.
- Keep the status of a recommendation distinct from its approval, execution, and observed effectiveness.
- Support follow-up and learning from outcomes, not just generation of one-off answers.

**Architecture implications**
- Represent proposed actions, decisions, approvals, tasks, and outcome measures as distinct, durable objects.
- Support workflow handoffs, notifications, and authorized integrations where appropriate.
- Enable ongoing, resumable agent work when it serves the user, with clear state, ownership, and checkpoints.
- Preserve human authorization for regulated, safety-critical, or irreversible operations. Never imply that an agent's proposal is an approved manufacturing action.
- Capture what happened after an action so outcomes can be compared with expectations.

**Test:** Can the user understand what to do next, review it safely, and later determine whether it helped?

### 4. Easy to Adopt
**Fit into existing systems and workflows with minimal setup, training, or migration.**

**Design implications**
- Meet users in their current working context; avoid demanding that they learn an entirely new operating model.
- Prefer familiar interactions where helpful, and introduce novel agent experiences only when they remove real friction.
- Use progressive disclosure: simple by default, powerful when needed.
- Support different entry points and roles without multiplying disconnected experiences.
- Make onboarding, explanations, error states, permissions, and recovery paths understandable to non-developers.

**Architecture implications**
- Treat existing MES, LIMS, QMS, historians, enterprise systems, and approved repositories as systems of record unless explicitly authorized otherwise.
- Build modular, permission-aware integration boundaries, with read-only paths and reversible changes as sensible defaults.
- Avoid requiring wholesale migration, reimplementation of existing platforms, or a specific vendor stack.
- Keep models, connectors, orchestration, and UI sufficiently decoupled that each can evolve independently.
- Design for enterprise security, deployment constraints, validation requirements, and maintainability without falsely claiming regulatory compliance.

**Test:** What must a real organization change, approve, install, train, or migrate before the product becomes useful?

## How the pillars work together

These principles are **joint constraints**, not four isolated features. An improvement in one pillar must not quietly undermine another.

Examples:
- Faster output that is difficult to audit is **not** a complete improvement.
- An impressive agent that requires extensive configuration is **not** easy to start or adopt.
- An accurate report with no usable follow-up is **not** easy to act on.
- Background automation without clear permissions, status, and control is **not** trustworthy.

Aim to reduce **total user and organizational effort from intent to a trustworthy outcome**—including setup, data preparation, verification, action, and follow-up. Do not optimize model latency or UI clicks in isolation.

## Interaction philosophy: adaptive, not prescriptive

- The product may provide proactive agents, direct manipulation, scientific workspaces, contextual views, notifications, and conventional tools. **Do not force every task into a chat, dashboard, upload flow, or fixed sequence of screens.**
- Let user intent and task complexity determine the interface. Surface the minimum necessary information first; make deeper evidence and controls readily accessible.
- An agent may carry out authorized multi-step work and retain task context. It should communicate progress, request decisions at meaningful checkpoints, and make it easy for users to inspect and redirect the work.
- An AI-first experience must not eliminate useful domain-specific tools: plots, comparisons, tables, source viewers, and structured approvals remain valuable where appropriate.
- Design for both responsive immediate tasks and longer-running, resumable work; don't pretend that work completed when it hasn't.

## Engineering decision rules

Before implementing any meaningful feature or redesign:

1. **Define the job to be done:** Who needs what outcome, and in what context? Avoid prescribing the solution prematurely.
2. **Check all four pillars:** What friction are we removing? What new friction or risk might we introduce?
3. **Explore alternatives:** Compare at least a simple option and a more ambitious option when the design trade-off is significant. Don't default to an existing dashboard, agent chat, or previous example.
4. **Preserve interoperability and evidence:** Specify source access, permissions, provenance, error behavior, review/approval boundaries, and reversibility.
5. **Measure real-world effort:** Define observable success metrics, not just a feature-completion checklist.
6. **State trade-offs:** If a feature compromises one pillar for another, surface that decision explicitly rather than hiding it.

### Suggested review checklist

| Pillar | Review question | Example measures |
|---|---|---|
| Easy to Start | How quickly can users get an actually useful result? | Setup time; manual inputs; time to first useful outcome |
| Easy to Trust | How readily can claims and decisions be checked? | Evidence coverage; provenance correctness; review time; unsupported claims |
| Easy to Act | Does the result connect to a safe next step and observable outcome? | Decision completion; follow-up completion; outcome tracking |
| Easy to Adopt | How much organizational change is required? | Integration effort; onboarding time; training; validation effort; migration burden |

These are **examples, not mandatory universal KPIs**. Choose measures appropriate to the task. Do not fabricate results or optimize for a metric at the expense of the user's actual outcome.

## Guardrails for coding and design agents

**Do:**
- Use these pillars as a lens for requirements, prototypes, architecture, implementation, and review.
- Inspect the existing codebase and constraints before recommending replacements.
- Challenge unnecessary complexity, duplicated configuration, hidden assumptions, and preventable manual work.
- Be creative about interaction patterns and implementation approaches while remaining evidence-driven.
- Preserve safety, permissions, provenance, and explicit human control for consequential operations.

**Do not:**
- Turn this document into a mandate to target one narrow use case, replace a named competitor, or follow a fixed growth or switching strategy.
- Assume the solution is always a chatbot, a dashboard, a specific agent framework, a specific integration, or a four-screen workflow.
- Add extra features solely because competitors have them, or reject an idea solely because competitors also offer it.
- Introduce migrations, heavyweight configuration, speculative autonomy, or hidden complexity without a clear user benefit.
- Claim validated accuracy, time savings, regulatory compliance, or competitive superiority without supporting evidence.

## North star

> **Make it effortless for pharmaceutical manufacturing teams to begin useful work, verify the reasoning and evidence, take appropriate action, and adopt the product within their existing environment.**

**These pillars determine _how we build_, not _how narrowly we think_.** They should expand the range of excellent product designs we consider—not lock us into a particular feature, workflow, competitor strategy, or interface.
