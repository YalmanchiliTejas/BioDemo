# Primary sources for the life-sciences platform architecture

Researched 2026-10-23. Governing direction: [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md). This supports the [long-horizon proposal](../product/long-horizon-manufacturing-agents.md). Public documentation establishes component behavior and limitations; it does not establish Apprentice's proprietary implementation or BioDemo's production readiness. Recommendations below are engineering inferences, not validated manufacturing outcomes. No code or infrastructure was changed by this research.

## A01 — Keep sessions independent of workers and sandboxes

[Anthropic: Scaling Managed Agents, April 8, 2026](https://www.anthropic.com/research/managed-agents)

The architecture separates a durable session log, agent harness, and tool execution environments. A replacement harness can retrieve session events; compacted context can be revisited from durable history. Credentials are separated from generated-code environments.

**Design implication:** Persist mission state, source references and progress outside a Prime subprocess. Allow each execution to be bounded, isolated and replaceable. Resume from authoritative state and retrievable history. This does not require buying that managed service or adopting its internal implementation.

**Limit:** Infrastructure patterns do not prove coherent multiweek scientific reasoning. Recovery, permission changes and stale results still need domain tests.

## A02 — Context needs recoverability and deliberate selection

[LangChain: Context Engineering with Deep Agents, October 14, 2026](https://www.langchain.com/blog/context-engineering-deep-agents-remember)

The harness uses offloading, recoverable summarization, on-demand skills, separate worker contexts and file-backed memory. Raw information can remain accessible outside the active context window.

**Design implication:** Pass goals, current evidence versions, changes and open questions to a resumed agent; load large historian traces and detailed procedures on demand. Memory consolidation must retain evidence pointers and correction history. Compare this behavior with extending the existing Prime context/session mechanisms before migrating.

**Limit:** An editable memory file does not enforce procedure authority, scientific correctness or access revocation. Those remain application contracts.

## A03 — PostgreSQL row security complements application authorization

[PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

Enabled row security defaults to denial without an applicable policy. Owners usually bypass it; superusers and `BYPASSRLS` roles bypass it. `FORCE ROW LEVEL SECURITY` can subject an owner to policy. Some whole-table operations are outside row security.

**Design implication:** Use distinct migration and runtime identities, explicit tenant/project/site scopes and least-privilege grants. Test exports, background jobs, partner sharing and privileged paths, not only API reads. Apply authorization to evidence objects and memory as well as relational records.

**Limit:** RLS is not a complete tenancy system and does not protect object-store access automatically. The repository's runtime-role SQL already separates roles, but its current cloud tables do not establish a full RLS implementation.

## A04 — Commit business state and delivery intent together

[AWS Prescriptive Guidance: Transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

The outbox pattern addresses failure between a database change and event publication. The state change and outbox entry share a database transaction; a publisher delivers later. Duplicate delivery and ordering require consumer handling.

**Design implication:** Atomically store a recommendation revision, audit event and notification/action intent. Deliver asynchronously with stable operation IDs, deduplication, destination acknowledgment and reconciliation of unknown outcomes. Use aggregate sequence/version checks to avoid stale updates.

**Limit:** Outbox delivery does not make arbitrary external actions exactly once, even when a broker supplies deduplication. Existing separate `DigitalThread` service calls require transaction-boundary inspection before claiming this guarantee.

## A05 — Durable workflows need an explicit upgrade strategy

[Temporal: Worker Versioning](https://docs.temporal.io/worker-versioning), [Workflow Definition](https://docs.temporal.io/workflow-definition)

Temporal distinguishes pinned workflows from auto-upgrade workflows; auto-upgrade requires replay-safe changes. Workflow code must preserve deterministic command behavior against history. Model calls and external I/O belong in activities rather than nondeterministic replay logic.

**Design implication:** For multi-day missions, version orchestration contracts and persist evidence/model/prompt/tool versions separately. Keep scientific state and large artifacts outside workflow history. Test changes with in-flight approvals and paused tasks. Select explicit migration behavior rather than assuming deployment upgrades every running mission safely.

**Limit:** Temporal adds a service and operational/versioning discipline. Existing PostgreSQL jobs can support the first bounded slice, but do not automatically supply durable timers, message-driven waiting or workflow evolution.

## A06 — Retry policy is part of each tool contract

[Temporal: Idempotency and durable execution, February 27, 2024](https://temporal.io/blog/idempotency-and-durable-execution)

Activities can execute more than once. Stable keys and uniqueness checks can prevent repeated effects where the destination supports that pattern.

**Design implication:** Every write connector declares whether it is idempotent, how success is verified, and how an unknown result is reconciled. Read retries, model retries and manufacturing-record submissions need different budgets and policies. Preserve a human approval's operation/payload binding across recovery.

**Limit:** A local deduplication record cannot determine whether an external request succeeded after a connection timeout. Destination lookup or responsible resolution is needed before repeating an uncertain consequential effect.

## A07 — Plant subscriptions need gap detection and backfill

[OPC Foundation: OPC UA Part 4, subscription model, v1.05.07](https://reference.opcfoundation.org/specs/OPC-10000-4/5.14.1)

Notifications use sequence numbers and acknowledgments. Retransmission queues are bounded and may be optional under some profiles; older messages can be dropped on overflow. Republish retrieves retained notifications. Durable subscriptions for longer interruptions are optional server capabilities.

**Design implication:** Edge connectors should preserve source/server timestamps, quality status, sequence checkpoints and durable local spooling; detect gaps and use supported historian backfill. Test each server's capabilities. Coalesce routine high-frequency data into analysis windows while preserving raw evidence and urgent events.

**Limit:** OPC UA support alone does not imply lossless collection, historian retention or permission to write to control systems. Keep physical control on its existing authorized execution path.

## A08 — Pin AI observability conventions and keep an application cost ledger

[OpenTelemetry GenAI conventions repository](https://github.com/open-telemetry/semantic-conventions-genai), [current GenAI overview](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/README.md), [model spans](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-spans.md)

The former website page now redirects readers to a separate repository. The inspected overview and model-span specifications are marked **Development**. They describe model/tool/retrieval/memory operations and usage attributes.

**Design implication:** Pin an instrumentation/convention revision. Trace mission, execution, tool and model calls with source/decision references; retain a separate reconciled usage ledger covering children, retries, cached inputs and provider billing units. Record latency, errors, queue delay and accepted-result cost. Restrict sensitive content capture; keep source payloads in controlled artifact storage.

**Limit:** A trace standard neither enforces permissions nor guarantees accurate billing. Do not label every GenAI attribute stable or treat token totals as equal across providers.

## A09 — Scientific optimization needs an experimental contract

[NIST/SEMATECH e-Handbook: Steps of design of experiments](https://www.itl.nist.gov/div898/handbook/pri/section1/pri13.htm)

The guidance covers objectives, variables, design, execution, checking assumptions, interpretation and follow-up. It emphasizes measurement capability, feasibility, drift awareness, ownership and preserving raw data.

**Design implication:** An agent can assemble a proposed study or optimization comparison, but numerical tools should calculate results with explicit variables, constraints, assumptions and lineage. Preserve batch/site/stage differences and available-time boundaries when constructing evaluation cohorts. Require qualified assessment of causal claims and proposed interventions.

**Limit:** This is established statistical guidance, not an agent evaluation or permission to change a manufacturing process. Historical correlation alone cannot prove an intervention improved yield.

## A10 — Database-backed queues need bounded claims and measured capacity

[PostgreSQL: SELECT locking clauses](https://www.postgresql.org/docs/current/sql-select.html)

`SKIP LOCKED` can avoid contention for multiple consumers of a queue-like table, but provides an inconsistent view unsuitable for general-purpose reads. `LIMIT` needs appropriate ordering when selecting predictable subsets.

**Design implication:** Use explicit ordered claims, short transactions, leases/fencing, per-tenant capacity and bounded batches for PostgreSQL jobs. Keep agent inference outside database transactions. Index the pending-job selection path and measure claim latency, queue age and lock contention. Move transport or partitioning when measured workload justifies it.

**Limit:** This is not a benchmark of unlimited PostgreSQL throughput. Queue fairness, retries, cancellation and reconciliation are application responsibilities; do not advertise a fixed tenant or event capacity without load tests.

## Practical stack recommendation grounded in this repository

These are proposed choices for the architecture decision log. They preserve existing useful work while addressing the broader offering.

| Choice | Simple path | Expansion when justified | Evidence and trade-off |
| --- | --- | --- | --- |
| Application | Modular FastAPI/Python domain services and existing frontend | Extract independently scaling or independently deployed domains | `backend/pyproject.toml` already supplies FastAPI, scientific libraries and cloud dependencies. Microservices add failure and delivery boundaries. |
| Authority/state | PostgreSQL domain records, revisions, decisions and transactional outbox | Tenant/site partitioning or dedicated deployments for contractual isolation | A03–A04; existing `cloud_backend/schema.sql` has job idempotency and audit patterns, not the full domain model. |
| Artifacts/analysis | Versioned object storage plus existing columnar/scientific tools | Separate analytical store when query volume or retention requires it | Keep bulky sources outside mutable OLTP rows and agent prompts; retain source versions and transformation lineage. |
| Execution | Existing fenced cloud jobs for bounded work; persistent missions outside workers | Temporal when long waits, timers and cross-service recovery justify it | `store.py` contains claim/fence logic; `dispatcher.py` tracks attempts and deadlines. A05–A06 show additional obligations for multi-day orchestration. |
| Agent harness | Existing Prime behind a stable mission/tool interface | Replace or augment after representative continuity evaluation | A01–A02 support decoupling, not an automatic rewrite. Current persistent session capability is useful but not proof of full batch supervision. |
| Plant data | Permission-aware edge ingestion and historian/API adapters | Dedicated streaming transport at measured volume | A07; server capabilities, timestamp quality and recovery behavior matter more than connector labels. |
| Telemetry/evaluation | OTel traces plus application usage ledger, deterministic checks and domain review | Larger evaluation suites and specialized graders as task coverage grows | A08–A09; measure cost per accepted result and human correction effort, not token cost alone. |

## Gaps to keep explicit

- No examined source establishes Apprentice's internal orchestration, model routing, ontology or evaluation results. Those require our own design and tests.
- No primary source selects one universally best stack. The recommended baseline should be measured against actual tenant count, source volume, latency, deployment and retention requirements.
- A critical validation suite must cover late/corrected measurements, stale advice withdrawal, revoked permissions, worker failure, uncertain external writes, duplicated events and in-flight upgrades.
- Model routing and current model/provider pricing are documented separately by the main architecture task; they were deliberately outside this research slice.
- No speed, cost, scale, yield or compliance claim has been validated by this document. All four governing pillars must be measured together.
