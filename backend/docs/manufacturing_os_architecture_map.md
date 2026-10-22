# Manufacturing OS implementation map

This document maps each box in [the draw.io architecture](manufacturing_agent_architecture.drawio)
to the code that implements it. The path is functional end to end for an ingested
package. It prepares an investigation for human review; it does not execute a
regulated manufacturing action or establish a scientifically proven root cause.

## Data to agent

| Architecture stage | Code | What it does |
| --- | --- | --- |
| Raw CHO / Fresenius files | `benchmarks/cho/raw/workbooks/`, `benchmarks/fresenius/raw_package/` | Independent source packages for the two benchmarks. The general pipeline also accepts unfamiliar folders and ZIPs. |
| CocoIndex + parsers | `src/manufacturing_data/cocoindex_app.py`, `ingest.py`, `__main__.py` | Incremental file inventory and checksum-based parsing. Each file or ZIP member is routed independently: structured parsers, text parser, Docling for printed PDFs, and Chandra-first extraction for forms/scans/images, with recorded fallbacks. Originals are preserved. |
| ManufacturingStore | `src/manufacturing_data/store.py`, `models.py` | SQLite relationships and provenance, immutable source-byte copies, Parquet numeric shards, access scope and availability timestamps. |
| Ten Manufacturing Data Tools | `src/manufacturing_data/tools.py` | `inspect_data`, `infer_schema`, `reconcile_entities`, `normalize_measurements`, `query_data`, `search_evidence`, `verify_evidence`, `extract_region`, `get_process_context`, `get_state_at`. |
| RolloutEngine role | `src/prime_runtime/harness.py`, `sdk_runner.mjs` | Starts or resumes one scoped SDK investigation and records its session, usage, and validated report. This is an adapter, not a second RLM implementation. |
| Time-scoped agent view | `src/manufacturing_data/session.py` | Adapts visible observations to the RLM evidence contract. Hidden scopes and future records cannot be supplied as seeds. |
| Prime runtime | `src/prime_runtime/sdk_runner.mjs`, `harness.py`, `bridge.py`, `prime_skills/manufacturing_os/` | Hosts a saved Prime SDK session, native Python kernel, and child-agent runtime. The scoped bridge exposes ten read tools and validates final citations. |
| Application wiring | `benchmark/application/api.py` | `BIODEMO_MANUFACTURING_STORE` enables Prime investigations; `BIODEMO_MANUFACTURING_SCOPE` fixes tenant scope. Without a store the separate retrospective UI remains available, but the Manufacturing OS rollout route is unavailable. |

## Investigation and review

| Architecture stage | Code | What it does |
| --- | --- | --- |
| Lead Manufacturing RLM | Adjacent Prime Agent SDK `AgentSession`; `src/prime_runtime/sdk_runner.mjs`; `src/prime_runtime/harness.py`; `prime_skills/manufacturing_os/` | The Node SDK host creates and resumes Prime sessions. Prime owns the model loop and persistent Python kernel. The skill exposes scoped manufacturing evidence and report submission. |
| Recursive Workers + Tool Registry | Prime Agent native `rlm.spawn`; `src/prime_runtime/bridge.py`; `src/manufacturing_data/tools.py` | Prime child sessions investigate independent questions; the bridge allowlists ten tools and enforces a per-run call budget. |
| Persistent Blackboard | `src/state/blackboard.py` | Atomic JSON state per incident: cited evidence, open questions, tasks, requests, rollout history, and human-recorded outcomes. The app separates stores/scopes into different Blackboard directories. |
| Causal Hypothesis Graph | `src/state/causal_hypothesis_graph.py` | Stores competing explanations, support, contradiction, unknowns, and discriminating tests. Validates cited evidence IDs. |
| Decision Graph | `src/state/decision_graph.py` | Stores conditional branches and evidence dependencies separately from causal beliefs. |
| Deviation Detection / Investigation | `src/workflows/manufacturing.py` (`_signal`, `_related_status_ids`, `record_rollout`) | Finds explicit categorical alert/action/fail/critical statuses in cited evidence and in other time-visible status fields for entities already in RLM scope. Each signal retains its exact source reference and validation status. Raw numerical outliers do not become GMP deviations without a supplied specification. |
| RCA Hypotheses + Evidence Testing | `src/workflows/manufacturing.py` (`_test_hypotheses`) | Reopens cited source locations with `verify_evidence`, records support and contradiction, and labels unresolved source checks. Every hypothesis remains a candidate; `root_cause_confirmed` is false until a human establishes it. |
| L1 / L2 / L3 Triage | `src/workflows/manufacturing.py` (`_triage`) | Assigns provisional L1 for a reliable explicit signal, L2 for action statuses across at least two linked entities, and L3 for an explicit critical/fail status. No signal yields `unclassified`. Site SOP must determine final triage. |
| Tasks / Evidence Requests / Approvals | `src/workflows/proposals.py`, `src/workflows/manufacturing.py` | Persists proposed tasks, supports task status changes and source-backed request fulfillment, and requires role-based human review. Report approval does **not** execute batch disposition, release, CAPA, or other regulated actions. |
| Investigation Update + Outcome Tracking | `src/workflows/manufacturing.py` (`record_rollout`, `record_outcome`, `close`, `history`) | Stores each rollout and human update in SQLite. QA records a source-cited outcome; closure requires completed tasks, resolved evidence requests, and the required review. The Blackboard receives fulfilled evidence and outcomes. |

## How to run and review

First ingest a raw package using the scope that the API will expose:

```bash
python3 -m src.manufacturing_data ingest /path/to/raw_package \
  --store /path/to/private_store --scope demo-cdmo
```

Start the application with the ingested store:

```bash
BIODEMO_MANUFACTURING_STORE=/path/to/private_store \
BIODEMO_MANUFACTURING_SCOPE=demo-cdmo \
PRIME_AGENT_BUNDLE_ROOT=/path/to/prime-agent-bio \
python3 -m uvicorn benchmark.application.api:create_app --factory
```

Call `POST /api/manufacturing-os/rollouts` with an incident ID, objective,
and `as_of` timestamp. `new_evidence_ids` is optional on this path. The response
includes `workflow`, and the following routes read or update that case:

| API route | Purpose |
| --- | --- |
| `GET /api/manufacturing-os/investigations/{incident_id}` | Current report, signals, hypothesis checks, triage, tasks, requests, decisions, outcomes. |
| `GET /api/manufacturing-os/investigations/{incident_id}/history` | Append-only update history. |
| `POST /api/manufacturing-os/investigations/{incident_id}/review` | Required human review decision. |
| `POST /api/manufacturing-os/investigations/{incident_id}/tasks/{task_id}` | Update a proposed task. |
| `POST /api/manufacturing-os/investigations/{incident_id}/evidence-requests/{request_id}/fulfill` | Attach newly available source evidence and update the Blackboard dependency. |
| `POST /api/manufacturing-os/investigations/{incident_id}/outcomes` | QA records a source-cited outcome. |
| `POST /api/manufacturing-os/investigations/{incident_id}/close` | QA closes a reviewed, complete investigation. |

The API's default identity headers are a development adapter. A production
deployment must replace them with verified identity claims and configure each
site's approved triage and approval policy. The source-data store must remain
outside unrestricted agent filesystem access.

### Runtime boundary

The Manufacturing OS has one RLM runtime: Prime Agent SDK. The application
does not contain a second Python lead, worker scheduler, or model provider.
`benchmarks/baselines/` contains standalone extraction and single-pass
comparison programs; neither is the investigation runtime. The model's
causal claims remain hypotheses; graph validation checks citation availability,
not scientific truth. [The Prime integration note](prime_agent_reuse.md)
describes the SDK host and isolation limits.

## Verification and limits

`tests/test_manufacturing_data.py` and `tests/test_prime_runtime.py` cover raw
ingestion, tool access, historical and scope isolation, SDK-host wiring,
source-backed triage, evidence checking, review roles, tasks, evidence
fulfillment, outcome recording, and controlled closure. The full repository
test command is `pytest -q` with the dependencies in `pyproject.toml`.

The evidence checks establish whether a cited value can be reproduced from
its source file. They do not prove that the measurement is biologically or
manufacturing-wise correct. OCR text may remain unverified. L1/L2/L3 rules
are a conservative demonstration policy and require site validation. The
workflow has no automatic physical sampling, product release, batch
disposition, external notification, or CAPA execution. The previous CHO and
Fresenius ingestion accuracy results are in [the data-layer report](manufacturing_data_layer.md);
they do not measure the quality of these new investigation decisions.
