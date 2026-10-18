# Manufacturing data layer

This package adds batch source ingestion and evidence tools to the existing Lead
RLM. It does not run an investigation or create another agent.

## Install and run

Python 3.11+ is required. Install the batch pipeline and, if needed, Docling:

```bash
python3 -m pip install -e '.[manufacturing-data,manufacturing-documents]'
python3 -m src.manufacturing_data ingest /path/to/raw_package --store /path/to/private_store --workers 4
python3 -m src.manufacturing_data tool inspect_data --store /path/to/private_store
python3 -m src.manufacturing_data tool search_evidence --store /path/to/private_store --args '{"query":"bioburden"}'
python3 -m src.manufacturing_data tool query_data --store /path/to/private_store --args '{"sql":"SELECT name, avg(value_number) FROM observations GROUP BY name"}'
```

`ingest` accepts folders and ZIPs. The default CocoIndex stage inventories files
incrementally; the parser then uses source checksums and pipeline version to
skip unchanged files. To run where CocoIndex cannot initialize its local
runtime, select `--orchestrator checksum` explicitly. CocoIndex inventory is a
source stage; parsing and storage are owned by this package.
The CLI disables CocoIndex usage telemetry for manufacturing packages.

`--document-backend auto` routes **each file independently**, including each ZIP
member. CSV/Excel/Parquet use structured parsers; text and logs use the text
parser; printed PDFs prefer Docling; scanned PDFs, handwritten notes, forms,
and images prefer Chandra. Automatic routing uses PDF text coverage, PDF form
fields, and generic filename hints. It is a heuristic, so the route is stored
with the source and can be reviewed. A failed optional backend falls through
to the next candidate: PaddleOCR-VL, Docling, or pypdf/Tesseract as applicable.
If all candidates fail, the source is preserved with `extraction_status=error`;
it is not silently marked as extracted. `--document-backend docling`,
`chandra`, `paddleocr-vl`, or `pypdf` forces one document backend when needed;
structured and plain-text files still use their native parsers.

The `ingest` result contains a `routes` entry for every file. The same route,
selected backend, extraction methods, fallback attempts, and errors are stored
in SQLite `sources.routing_json` and returned by `inspect_data`. Chandra and
PaddleOCR-VL need separate model/runtime installation. OCR/VLM statements
remain `unverified` until checked against the original source.

`--scope TENANT` marks all ingested evidence with an access scope. Tool calls
accept `--scope TENANT` and `--as-of ISO_TIMESTAMP`. Historical access is
conservative for undated documents; a source package created later does not
become visible just because its ZIP member has an old timestamp. The caller
must place the private store outside the agent's filesystem allowlist and
grant access only through these tools.

## Data model and tool calls

Structured ingestion uses up to four workbook workers (`--workers N`). Excel
is read with fastexcel/Calamine; CSV and Parquet use Polars. Each sheet's headers
and column counts are checked, blank rows retain their original coordinates,
and duplicate headers produce an explicit ingestion error. Numeric Excel cells
retain native precision; mixed columns preserve numeric XML values and actual
text identifiers. Each stored partition has an integrity checksum.

Workers write wide sheet rows directly as Arrow batches to compressed Parquet
in `measurements/`. These rows include measurements, other source values, row
numbers, timestamps, candidate entity IDs, and field publication times. SQLite
holds source checksums, sheet manifests, column schemas, candidate entities,
and compact relationships. Structured cells are never inserted into SQLite.
Original bytes are copied by SHA-256 into a private directory. Document and
legacy observations remain supported in SQLite.

DuckDB builds a lazy `observations` view over authorized sheet partitions.
It expands cells into the existing evidence shape only while querying;
source locations and evidence IDs are derived from sheet, physical row, and
column. Scope, source availability, and per-field time cutoffs apply before
results reach the RLM. Numeric `query_data` queries retain their existing
contract. Inspection and entity tools aggregate in DuckDB, and the bridge
validates only returned evidence IDs rather than loading every cell into Python.
External access is disabled except for the exact authorized partition paths;
agent SQL can reference only the public `observations` relation.

The pipeline signature is now `0.6.0-verified-columnar`. Reingesting an existing
store rebuilds changed/old-format structured sources. New structured evidence
IDs use `b1:<source>:<sheet-index>:<row>:<column>`; existing legacy evidence IDs
remain readable until that source is reindexed. Start a new investigation after
migration rather than resuming a report containing old structured IDs. The
existing ten tool names are unchanged; three deterministic analysis tools are added.

The Prime bridge exposes `inspect_data`, `infer_schema`,
`reconcile_entities`, `normalize_measurements`, `query_data`,
`search_evidence`, `verify_evidence`, `extract_region`,
`get_process_context`, and `get_state_at` from a scoped `ManufacturingStore`.
Task and evidence-request proposals are handled by the review workflow.
Tool inputs are validated with Pydantic. Entity links and schema mappings are
candidates until corroborated; no benchmark-specific mappings are embedded.

## Run the RLM from ingested files

Set `BIODEMO_MANUFACTURING_STORE` to an **already ingested** store before
starting the application. The `/api/manufacturing-os/rollouts` endpoint runs
Prime SDK against scoped, time-filtered observations.
Set `BIODEMO_MANUFACTURING_SCOPE` to the scope used at ingestion; the request's
tenant header must match it. If no evidence ID is
supplied, the rollout searches the objective for initial evidence and falls
back to the first visible observations. Explicit IDs must be visible at
`as_of` in the configured scope. Without a configured store, this route is
unavailable; the separate retrospective UI replay remains available.

```bash
BIODEMO_MANUFACTURING_STORE=/path/to/private_store \
BIODEMO_MANUFACTURING_SCOPE=demo-cdmo \
python3 -m uvicorn benchmark.application.api:create_app --factory
```

Example request:

```json
{"incident_id":"run-001","problem":"Investigate the available batch evidence","as_of":"2026-10-13T00:00:00Z"}
```

This activates the existing RLM and its Blackboard, hypothesis graph, and
decision graph. The post-RLM workflow stores source-backed deviation signals,
tests cited evidence against original files, assigns provisional L1/L2/L3
triage, and exposes review, task, evidence-request, outcome, and closure routes.
See [the architecture map](../../docs/manufacturing_os_architecture_map.md)
for the exact files, API paths, and limits. The application still uses
development identity headers; production deployments need a trusted identity
boundary before exposing tenant-scoped manufacturing evidence.

`search_evidence` uses lexical retrieval by default. `mode="semantic"` uses
the existing optional `semantic` extra and a local FastEmbed model for document
lines. That path has not been benchmarked here and may download model weights.

## Validation

```bash
python3 -m pytest -q tests/test_manufacturing_data.py
python3 -m src.manufacturing_data ingest benchmarks/cho/raw/workbooks --store /private/tmp/cho-data --orchestrator checksum --max-rows-per-file 20
python3 -m src.manufacturing_data ingest benchmarks/fresenius/raw_package --store /private/tmp/fres-data --orchestrator checksum
python3 -m benchmarks.data_layer_evaluate --cho-store /private/tmp/cho-data --fresenius-store /private/tmp/fres-data --output results/manufacturing_data_layer.json
```

The evaluator is separate from the agent tools and reads hidden benchmark
references only after extraction. [Measured results](../../results/manufacturing_data_layer.json)
and [limitations](../../docs/manufacturing_data_layer.md) describe the current
coverage. No RLM investigation or decision workflow was run for these results.

## Full CHO ingestion measurement

The full dataset (12 workbooks, 192 sheets, 3,251,506 rows, 25,195,350
populated cells) ingested into a fresh store in 23.239 seconds with four
workers. Repeating unchanged ingestion took 0.295 seconds. SQLite contained
192 sheet manifests, 36 candidate entities, 24 relationships, and zero
structured observations/records. Sheet Parquet files occupied 102,997,071 bytes.
A numeric aggregate took 3.814 seconds, inspection took 7.094 seconds, and a
batch lookup of 1,000 evidence IDs took 0.240 seconds. These measurements cover
`ingest_package` and tool execution; they exclude optional CocoIndex inventory
and agent investigation. Tests ran concurrently during the repeat timing.
See [the recorded result](../../results/columnar_ingestion.json) for versions,
source checksums, and per-workbook timings.

To reproduce full ingestion with the command-line interface:

```bash
python3 -m src.manufacturing_data ingest benchmarks/cho/raw/workbooks \
  --store /private/tmp/cho-columnar-store --orchestrator checksum --workers 4
```


## Deterministic investigation verification

`summarize_series`, `calculate_metrics` and `align_series` complement the
existing scoped tools. The runtime prepares source-backed statistics and anomaly
patterns before model inference and verifies structured numerical claims before
submission. Reports separate facts, calculations, interpretations and hypotheses.
See [verification behavior, policy configuration and migration](../../docs/deterministic_verification.md).
