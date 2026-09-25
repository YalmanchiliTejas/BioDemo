# Biopharma Factory Benchmark

A deterministic, discrete-event MVP for benchmarking operating models in a small
biologics factory. The current milestone intentionally implements only the shared
factory/environment and the **Traditional** operating model. It does not contain
an LLM or agentic controller.

## What is modeled

- One product, one upstream train, one downstream train, one QC lab
- Twelve scheduled batches over a 30-day campaign
- Five major assets, material lots, workforce qualifications, and maintenance
- Eight simulated systems of record: MES/eBR, historian, LIMS, QMS, CMMS, ERP,
  scheduler, and LMS
- Twelve deterministic failure scenarios with explicit ground-truth causes
- A Traditional controller with information-retrieval, meeting, escalation,
  investigation, approval, and manual replanning delays
- Complete JSONL event logs plus a JSON baseline summary
- Fault evidence in historian/LIMS records, time-gated deviations and QC results,
  consumed material inventory, and explicit QC/material/QA release gates

The physical model and scenario manifest are controller-independent. Future
controllers must consume the same `CampaignDefinition` and `ScenarioManifest`.

## Run

Requires Python 3.11+ and has no runtime dependencies.

```bash
python -m benchmark run --mode traditional --seed 20250921 --output runs/baseline
python -m benchmark replay runs/baseline/events.jsonl
python -m unittest discover -s tests -v
```

The run command writes:

- `campaign.json`: immutable campaign and scenario manifest
- `events.jsonl`: replayable audit/event log
- `summary.json`: released product, manufacturing, quality, and MSAT metrics

## Scope boundary

`point_ai` and `agentic` modes are reserved but deliberately unavailable. This
prevents later decision layers from silently changing factory physics, failures,
materials, staffing, or quality limits before the Traditional baseline is stable.

This simulator is a benchmark abstraction, **not a validated GMP system or a
mechanistic bioprocess model**. The metrics are illustrative, not estimates of
real-plant performance or agent uplift. See [the fidelity assessment](docs/FIDELITY.md)
for explicit assumptions, remaining gaps, and the calibration evidence needed
before comparing operating models. `benchmark/factory/process.py` exposes the
narrow process-model interface where BIOPRO-Sim, PenSimPy, or another physical
model can later be connected without changing controllers or systems-of-record APIs.

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

The repository includes the human workflow and experience layers: investigation
timelines, batch and shift consoles, science and quality views, a policy-driven
approval inbox, human tasks, and an authorization audit trail. Agent, model-router,
and tool-executor ports are present but intentionally unconfigured.

```bash
python3 -m pip install -e '.[app]'
python3 -m benchmark serve
```

Open `http://127.0.0.1:8000`. The default development runtime uses seeded local
data and in-memory stores so the UI can be reviewed without infrastructure.
Set `APP_MODE=production` to use the PostgreSQL workflow/action stores and the
configured Neo4j, MongoDB, MinIO, and optional Qdrant services.
See [the operations application guide](docs/OPERATIONS_APPLICATION.md) for API,
identity, runtime-mode, and agent-extension contracts.
