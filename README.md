# Biopharma Factory Benchmark

A deterministic factory benchmark plus a tenant-scoped operations application for
reviewing cases, running bounded specialist workflows, and controlling regulated
actions. The simulation supports a **Traditional** baseline and an inspectable
**Agent-assisted** operating-model projection. The latter is scenario analysis,
not empirical evidence of AI performance; the operations application remains a
separate control-plane reference implementation and does not change benchmark physics.

## What is modeled

- One product, one upstream train, one downstream train, one QC lab
- Twelve scheduled batches over a 30-day campaign
- Five major assets, material lots, workforce qualifications, and maintenance
- Eight simulated systems of record: MES/eBR, historian, LIMS, QMS, CMMS, ERP,
  scheduler, and LMS
- Twelve deterministic failure scenarios with explicit ground-truth causes
- Traditional and agent-assisted controllers over identical seeded faults
- A scored investigation rubric covering cause accuracy, required evidence,
  traceability, counter-evidence, and approval compliance
- Complete JSONL event logs plus a JSON baseline summary
- Fault evidence in historian/LIMS records, time-gated deviations and QC results,
  consumed material inventory, and explicit QC/material/QA release gates

The physical model and scenario manifest are controller-independent. Both
controllers consume the same `CampaignDefinition` and `ScenarioManifest`.

## Run

Requires Python 3.11+ and has no runtime dependencies.

```bash
python -m benchmark run --mode traditional --seed 20250921 --output runs/baseline
python -m benchmark run --mode agent_assisted --seed 20250921 --output runs/agent-assisted
python -m benchmark compare --runs 30 --output runs/comparison
python -m benchmark replay runs/baseline/events.jsonl
python -m unittest discover -s tests -v
```

The run command writes:

- `campaign.json`: immutable campaign and scenario manifest
- `events.jsonl`: replayable audit/event log
- `summary.json`: released product, manufacturing, quality, and MSAT metrics

## Scope boundary

Both controllers consume the same campaign and fault manifest. The agent-assisted
controller changes only explicit response, labor, evidence, and documentation
assumptions; it cannot change the faults, quality limits, or release gates.

This simulator is a benchmark abstraction, **not a validated GMP system or a
mechanistic bioprocess model**. The metrics are illustrative projections, not
estimates of real-plant performance or measured agent uplift. See [the fidelity assessment](docs/FIDELITY.md)
for explicit assumptions, remaining gaps, and the calibration evidence needed
before comparing operating models. `benchmark/factory/process.py` exposes the
narrow process-model interface where BIOPRO-Sim, PenSimPy, or another physical
model can later be connected without changing controllers or systems-of-record APIs.
Use the [prospective validation study](docs/VALIDATION_STUDY.md) to convert the
modeled business case into evidence for external time-saving and quality claims.

## Dynamic knowledge base

The optional CDMO digital-thread layer uses Neo4j, MongoDB, PostgreSQL, MinIO,
Qdrant, and Redpanda. It supports evidence-first ingestion, tenant-scoped event
timelines, controlled document revisions, decisions and approvals, working cases,
human tasks, hybrid retrieval with citations, and a durable outbox. In-memory
adapters keep the complete application contract testable without services.

```bash
python3 -m pip install -e '.[knowledge,semantic,eventbus,documents]'
docker compose -f docker-compose.knowledge.yml up -d
AWS_ACCESS_KEY_ID=biopharma AWS_SECRET_ACCESS_KEY=biopharma-dev \
  python3 -m benchmark knowledge-ingest runs/baseline/events.jsonl \
  --tenant sponsor-a --site site-01
```

Connection settings default to the local Compose services and can be overridden
with `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`,
`MONGODB_URI`, and `MONGODB_DATABASE`. The retrieval entry point is
`KnowledgeBase.context(...)`; it returns structured events, applicable rules,
source documents, and the latest event id for each requested entity. This stable
contract feeds the agent runtime without coupling retrieval or model-framework
behavior to factory physics. The optional semantic adapter uses local FastEmbed
embeddings and Qdrant; lexical and graph retrieval remain available independently.

See [the knowledge-base architecture](docs/KNOWLEDGE_BASE.md) for storage
responsibilities, security boundaries, graph relationships, and production
validation requirements.

The [full application architecture](docs/APPLICATION_ARCHITECTURE.md) includes
the connector runtime and the closed source-system-to-knowledge feedback loop.

## Operations application

The repository includes the complete base architecture: investigation
timelines, batch and shift consoles, science and quality views, a policy-driven
approval inbox, human tasks, and an authorization audit trail. The case-orchestrator
routes four specialist families and retains the Prime Agent deviation RLM when a
compatible checkout is available. Other specialists use the same context and human
gate contracts with deterministic jobs until an external model harness is configured.
A source-connector monitor can continuously ingest canonical records
from MES, LIMS, QMS, historian, and other HTTP systems, open deduplicated deviation
cases, and trigger the agent according to connector policy. The model router ships
with SPC, robust anomaly, and full-factorial DOE providers behind an allow-listed
tool gateway. Approved actions cross a separate execution gateway; production mode
fails closed until an authoritative write adapter is configured.

```bash
python3 -m pip install -e '.[app]'
python3 -m benchmark serve
```

Open `http://127.0.0.1:8000`. The default development runtime uses seeded local
data and in-memory stores so the UI can be reviewed without infrastructure.
Set `BIODEMO_DYNAMIC_AGENT_COMMAND` or `BIODEMO_DYNAMIC_AGENT_URL` to enable the
provider-neutral dynamic specialist runtime for every agent route; without one, the
control plane reports and uses the bounded deterministic fallback.
Set `APP_MODE=production` to use the PostgreSQL workflow/action stores and the
configured Neo4j, MongoDB, MinIO, and optional Qdrant services.
See [the operations application guide](docs/OPERATIONS_APPLICATION.md) for API,
identity, runtime-mode, and agent-extension contracts.
