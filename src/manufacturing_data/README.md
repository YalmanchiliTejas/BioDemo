# Manufacturing data layer

This package adds batch source ingestion and evidence tools to the existing Lead
RLM. It does not run an investigation or create another agent.

## Install and run

Python 3.11+ is required. Install the batch pipeline and, if needed, Docling:

```bash
python3 -m pip install -e '.[manufacturing-data,manufacturing-documents]'
python3 -m src.manufacturing_data ingest /path/to/raw_package --store /path/to/private_store
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

SQLite holds sources, sheets/columns, source records, observations, candidate
entities, relationships, timestamps, validation states, and exact source
locations. Original bytes are copied by SHA-256 into a private directory.
Polars writes numerical observations as Parquet shards. DuckDB executes bounded
read-only SQL over only the shards visible to the current scope and time. Pint
converts units and Pandera validates numerical conversion and Parquet export.

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
