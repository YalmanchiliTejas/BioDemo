# Life-sciences platform engineering plan

Prepared 2026-10-23 from public Apprentice material, current primary technical documentation, and the BioDemo checkout. It began as a researched architecture specification and is now implemented in `backend/src/lifesci/` (see the [implementation guide](implementation.md)). It does not claim to reproduce Apprentice's private implementation. 63 of 77 capabilities are implemented and verified by automated tests against their acceptance conditions; 14 are partial with stated gaps; that is development verification, not customer qualification.

## Start here

0. [Implementation guide](implementation.md): what was built, how to run it, measurements and known gaps.
1. [Architecture](architecture.md): recommended system, domain modules, persistent agents, integration contracts and scaling.
2. [Capability checklist](capability-checklist.md): individual capabilities, current code, acceptance criteria and delivery stage. [CSV](capability-checklist.csv) is the canonical tracking data.
3. [Model routing](model-routing.md): deterministic/small/balanced/frontier routing, cost controls, accuracy gates and current model candidates.
4. [Decision log](decision-log.md): choices, alternatives, trade-offs, evidence and conditions for revisiting them.
5. [Delivery and verification](delivery-and-verification.md): dependency-ordered implementation, workload assumptions and release evidence.

## Scope and evidence

The baseline includes manufacturing/recipe execution, laboratory/sample workflows, scientific data and analysis, quality, equipment and materials context, network/partner coordination, digital instructions, remote assistance, integrations, agent work, identity/signatures/audit, and deployment/validation support. Support clinical, commercial and distributed production with site-specific configurations. Long-lived batch/campaign missions and revision-aware recommendations span these capabilities.

The governing source is [Main_Culture_andETHOS.md](../../../Main_Culture_andETHOS.md). Requirements from [discovery](../deviation-workflow-discovery.md) remain in force. This package develops the [long-horizon proposal](../long-horizon-manufacturing-agents.md) into a broader platform design. Earlier runtime preferences are historical; the decisions in this package state the current recommendation, not a completed migration.

Evidence inputs:

- [Official offering inventory](../../research/apprentice-life-sciences-source-inventory.md): source/feature IDs and unknowns.
- [Code inventory](../../research/life-sciences-codebase-inventory.md): implemented primitives versus demonstrators and integration gaps; referenced tests were not executed in that inventory.
- [Primary architecture sources](../../research/life-sciences-architecture-sources.md).
- [Long-horizon research](../../research/long-horizon-agent-reading.md).

Every capability has separate research, design, implementation and verification status. A completed research or design checkbox never implies a functioning feature. Existing reusable code is described as a foundation until the complete acceptance scenario is demonstrated. Quantified vendor deployment/benefit claims are tracked as unverified claims, not performance requirements we promise to reproduce.

## Recommended baseline

Keep React/Vite, FastAPI/Python, Prime's scoped investigation adapter, and the existing ingestion/scientific tools. Build a modular domain application with PostgreSQL coordination records, versioned object storage, independently scalable workers, and durable mission orchestration. Use Temporal for multi-day mission execution and timers, with Prime for adaptive reasoning; the case/procedure/evidence records remain owned by domain services. Use code first, smaller models for well-bounded tasks, balanced models for routine synthesis, and frontier reasoning for difficult synthesis. Select concrete model versions through evaluated, policy-constrained routing.

Integrate existing systems of record by default. Native procedure/lab execution is a separately enabled module with explicitly assigned record ownership, intended use and qualification; a connector acknowledgment or agent draft cannot silently become an official record. Build the broad domain contracts from the start, then deliver tested slices in dependency order.

## Completion of this architecture task

- [x] Inspect public offering and mark unpublished details unknown.
- [x] Inspect existing implementation and preserve usable foundations.
- [x] Map the inventory to capabilities, modules, acceptance criteria and delivery stages.
- [x] Specify persistent agent context, new-evidence updates and outcome learning.
- [x] Specify small-model routing, cost accounting, latency and accuracy controls.
- [x] Specify scale, failure recovery, access boundaries and operational ownership.
- [x] Record architectural decisions and alternatives.
- [x] Implement the shared contracts, gateway, missions and all eleven domain modules (`backend/src/lifesci/`).
- [ ] Integrate every checklist capability — in progress: 63/77 fully, 14 partial (devices, live vendor systems, UI, durable orchestrator); see the checklist evidence column.
- [x] Execute automated acceptance tests (269 passing, incl. PostgreSQL RLS and an end-to-end scenario) and a single-process load smoke.
- [ ] Execute workload tests at the documented profiles, scientific method review, model task evaluations on labeled data, and customer qualification.
- [ ] Product/QA sign-off of the 11 assessment records.

No live deployment, external account configuration, production database migration, or manufacturing operation has been performed. No model task kind is qualified by default; routes become available only after recorded evaluations.
