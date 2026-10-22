# Manufacturing OS

This directory is the backend project root. Run the commands below from
`backend/` (`cd backend` from the repository root). The frontend lives in
`../frontend/`, with its own Vite commands and design documentation. The local
`.venv` shortcut uses the shared repository Python environment.

This repository contains a batch manufacturing data layer, a Prime Agent SDK
investigation integration, and two separate data benchmarks. The Fresenius
records are a synthetic reconstruction anchored to public FDA findings; CHO
uses authentic published laboratory measurements.

## Pharmaceutical investigation MVP (active build)

The [shared case workspace README](docs/pharma_mvp/README.md) tracks the new
[implementation brief](docs/pharma_mvp/INSTRUCTIONS.md), working intake/review/
descriptive-analysis/handoff slice, exact commands, tests and remaining gaps.
Open `http://127.0.0.1:5180/?tab=cases` with the existing API and Vite running.
The Prime SDK smoke run encountered a provider billing error; deterministic
case calculations are explicitly labeled and are not claimed as an agent run.

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

The UI has two pages: `/` is an evidence workspace and `/benchmark` is a visual evaluation dashboard. The Fresenius case uses selectable time-valid checkpoints, an upstream signal chart, and expandable synthetic source records (including deviations, release tests and field complaints) to explain the proposed investigation scope. CHO starts with raw workbook excerpts and conventional preparation results, then lets viewers inspect descriptive reactor-pair trajectories from publication-aligned evaluation references. These reference observations are not agent discoveries. Older landing and comparison links redirect to the demo.

The benchmark dashboard charts task-level critical-signal citation coverage and citation validity for the recorded retrieval + LLM baseline, CHO reconstruction agreement with explicit missing/error counts, and person-time by phase when complete reviewed effort logs exist. Missing values are hatched and never plotted as zero. It keeps modeled campaign results and detailed methodology in expandable supporting sections. These baseline scores are separate from Prime OS quality; measured productivity remains pending.

Each case has a **Run agent** button. Clicking it starts a real Prime SDK investigation in the background; Fresenius uses the selected evidence checkpoint's time-valid snapshot and CHO uses the raw workbooks. The page polls progress and displays the submitted report. Refreshing reconnects to the saved run. Reports and run status are saved under `runs/demo-agent/`; live output does not overwrite benchmark scores. Configure the Prime SDK and model credentials as described above before running. Loading the page, selecting checkpoints or inspecting trajectories does not launch the agent.

The incident workspace shows time-valid source evidence, recorded case actions and a proposed connected investigation. The demo shows measured productivity as pending until reviewed work and human-effort logs exist; simulated delay and effort reductions are explained in the benchmark rather than presented as measured savings. Regenerating `python -m benchmark.case_comparison.report` also refreshes `demo-story.json`, allowing the updated presentation to load while an older server finishes an active investigation.

The governing evaluation design is [README_benchmarks.md](README_benchmarks.md). V2 reports **quality-qualified investigation rate**, **all-attempt human hours per qualified case**, and **paired human-effort reduction** only for matching qualified outcomes under an independently approved noninferiority policy. Seven stages include setup, preparation, investigation, verification, corrections, coordination and ongoing configuration. Draft quality/routing policies and missing human studies keep qualification and savings unmeasured. Older accepted-work/hour and simulation scores remain supporting diagnostics.

The [benchmark commands](benchmarks/README.md) now default to frozen case evaluations. `--legacy-tasks` preserves the previous task runner. The raw `full_rlm` adapter uses the existing Prime SDK and manufacturing data layer; it does not introduce another runtime. Source snapshots and migration details are recorded in [the migration audit](docs/benchmark_evaluation_migration.md).

### One-command pilot comparison

With the Prime SDK configured, run the conventional parser and the real Prime
investigation on the same raw folder or ZIP:

```bash
python3 -m src.prime_runtime.compare /path/to/raw_package \
  --objective "Investigate the available manufacturing evidence" \
  --output runs/my-comparison
```

Open `runs/my-comparison/comparison.md` for a side-by-side summary,
`agent_report.json` for the full investigation, and `cited_evidence.json` for
the source-backed observations it cited. The command builds an
isolated temporary store, runs the parser without an agent, then runs Prime on
the ingested copy. The parser provides no investigation conclusions. This is
a pilot comparison, not a held-out benchmark score.

To calculate labor value, first time a human doing the case without Prime and
then record human review and correction time with Prime. Supply those observed
values and your total agent cost:

```bash
python3 -m src.prime_runtime.compare /path/to/raw_package \
  --objective "Investigate the available manufacturing evidence" \
  --baseline-human-minutes 90 --assisted-human-minutes 30 \
  --loaded-hourly-rate-usd 120 --total-agent-cost-usd 5 \
  --output runs/my-comparison
```

The dollar result is omitted unless all four cost inputs are provided. Prime's
reported inference cost currently covers only the root SDK session; include
child worker, OCR, and other costs in `--total-agent-cost-usd`. For historical
replays, pass `--as-of` with a timezone and use a source snapshot whose files
were actually available at that timestamp.

The [benchmark guide](benchmarks/README.md) documents source validation,
generation, leakage audits, and baseline scoring for CHO and Fresenius. The
conventional and single-pass baselines are separate comparison groups. The v2
`full_rlm` mode runs the existing Prime SDK on the same authorized raw evidence.

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

## CMO data ingestion: IndPenSim and Sanofi

The [ingestion demonstration guide](docs/cmo_ingestion/README.md) covers data
acquisition, reproducible packages, source review, confirmed template reuse,
optional inference settings in `.env.local`, and the local API/UI workflow.
Open `http://127.0.0.1:5180/?tab=ingestion` after starting the existing API and
Vite server. Docker is optional.

[Executed ingestion results](results/cmo_ingestion/report.md) include failures
and unavailable configurations. Sanofi operational records are synthetic;
human-time savings have not been established.

## Secure cloud backend (DigitalOcean pilot)

The [backend and deployment runbook](docs/security/cloud-backend.md) describes the
separate authenticated API, encrypted artifacts, durable PostgreSQL job queue,
isolated autonomous agent containers, Terraform and backup operations. This
foundation has not been deployed or approved for PHI and does not establish SOC 2
or HIPAA compliance. Existing demo routes remain local demonstration endpoints.
