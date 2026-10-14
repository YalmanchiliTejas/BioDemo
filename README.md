# Manufacturing OS

This repository contains a batch manufacturing data layer, a Prime Agent SDK
investigation integration, and two separate data benchmarks. The Fresenius
records are a synthetic reconstruction anchored to public FDA findings; CHO
uses authentic published laboratory measurements.

## Current architecture

```text
CHO / Fresenius source files
  → CocoIndex and format-specific parsers
  → ManufacturingStore (SQLite metadata, Parquet measurements)
  → 10 scoped ManufacturingTools
  → Prime Agent SDK AgentSession and native recursive workers
  ↔ Blackboard, Causal Hypothesis Graph, Decision Graph
  → ManufacturingInvestigationWorkflow
  → human review, evidence requests, tasks, and outcomes
```

The Manufacturing OS has **one investigation runtime**: Prime Agent's
TypeScript SDK, hosted by a local Node process because the application is
Python. `src/prime_runtime/` supplies the SDK host and a scoped evidence bridge.
The app does not implement its own RLM lead, worker scheduler, or model loop.
The separate `/api/cases/{id}/agent` route is a deterministic UI case demo;
it is not a Manufacturing OS investigation.

| Directory | Purpose |
| --- | --- |
| `src/manufacturing_data/` | Ingestion, store, provenance, and ten data tools |
| `src/prime_runtime/`, `prime_skills/` | Prime SDK host and scoped skill bridge |
| `src/state/`, `src/workflows/` | Blackboard, graphs, investigation review and outcomes |
| `benchmarks/` | CHO and Fresenius benchmark tasks, isolated inputs, baselines, scoring |
| `benchmark/` | Retrospective web demo and its older synthetic simulation |
| `data/v1.1/` | Frozen synthetic records and hidden benchmark reference files |

See [architecture and code map](docs/manufacturing_os_architecture_map.md),
[Prime SDK integration](docs/prime_agent_reuse.md), and
[data layer commands](src/manufacturing_data/README.md).

## Setup

Requires Python 3.11+, Node, and an adjacent Prime Agent checkout with a built
`packages/coding-agent/dist/index.js` and installed Node dependencies.

```bash
python3 -m pip install -e '.[app,manufacturing-data]'
python3 -m src.manufacturing_data ingest /path/to/raw_package --store /path/to/store --scope demo-cdmo
BIODEMO_MANUFACTURING_STORE=/path/to/store BIODEMO_MANUFACTURING_SCOPE=demo-cdmo \
  PRIME_AGENT_BUNDLE_ROOT=/path/to/prime-agent-bio python3 -m benchmark serve
```

`POST /api/manufacturing-os/rollouts` starts or resumes an SDK investigation.
Set `BIODEMO_PRIME_MODEL=provider/model` to select a model. A scoped store is
required; the route does not silently switch to a different agent.

To inspect the retrospective UI without a manufacturing store, run
`python3 -m benchmark serve`. The UI replay is a synthetic demonstration.

## Benchmarks and tests

The [benchmark guide](benchmarks/README.md) documents source validation,
generation, leakage audits, and baseline scoring for CHO and Fresenius. The
benchmark baselines are separate from the Prime runtime. They do not run Prime
unless a future SDK benchmark adapter is explicitly added.

```bash
python3 -m pytest -q
python3 -m benchmarks.common.benchmark_runner --benchmark cho --action validate
python3 -m benchmarks.common.benchmark_runner --benchmark fresenius --action validate
```

Source provenance and limits are documented in
[dataset provenance](docs/dataset_provenance.md) and
[benchmark limitations](docs/benchmark_limitations.md). No benchmark result
establishes performance on confidential commercial records or prevention of a
real manufacturing failure.
