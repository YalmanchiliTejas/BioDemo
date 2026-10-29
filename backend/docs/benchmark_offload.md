# DagsHub data storage and execution

Bulk benchmark inputs, generated corpora, model weights, retained workspaces and
large result payloads live in the **private `YalmanchiliTejas/BioDemo` DagsHub
repository bucket**. Small checksum descriptors and result summaries stay in Git.
Commands below run from `backend/`.

## Execute without keeping datasets locally

```sh
cd backend
.venv/bin/python -m benchmarks.autonomous.run dagshub:case-synthetic-100 \
  /private/tmp/manufacturing-results-NEW --questions microbiological \
  --modes linked_rules --seconds 180
```

Use `case-synthetic-1000` or `case-synthetic-10000` for the stored scaling corpora.
The resolver downloads into a temporary execution directory, verifies SHA-256 and
size, and deletes the working copy when execution exits, including on exceptions.
There is no persistent dataset cache in this path. Network access and an authorized
DagsHub login are required. Abrupt process termination can leave temporary files;
remove them only after confirming the owning execution is no longer running.

The scored harness alone reads evaluator truth. The isolated investigation worker
receives only the historical evidence snapshot, never DagsHub credentials or the
evaluator directory. The operational Sanofi-style records remain fictional.

The same directory investigation interface accepts a remote raw-data subpath:

```sh
.venv/bin/python -m benchmarks.common.investigate_directory \
  dagshub:case-synthetic-100/raw \
  'Investigate recurring bioreactor failures across these campaigns.' \
  /private/tmp/investigation-NEW.json --mode linked_rules --seconds 180
```

Its follow-up workspace is uploaded and verified before local pruning. On archive
failure the receipt reports `archive_error` and keeps the sole local copy.

## Generate and analyze remote artifacts

```sh
# Use a new immutable asset ID for new output.
.venv/bin/python -m benchmarks.autonomous.generate dagshub:synthetic-NEW \
  --count 1000 --seed 417 --scenario-seed 718
.venv/bin/python -m benchmarks.autonomous.generate dagshub:scaled-NEW \
  --base dagshub:case-synthetic-100 --count 10000 --seed 912
.venv/bin/python -m benchmarks.autonomous.indpensim project \
  dagshub:indpensim-archive dagshub:projection-NEW
.venv/bin/python -m benchmarks.autonomous.indpensim investigate \
  dagshub:indpensim-historical dagshub:analysis-NEW
```

Producers use temporary local working space, publish the result, verify a complete
remote readback, then prune. If publication fails, new data is retained in ignored
`.offload/failed-publications/` and the operation fails explicitly. Existing asset
IDs cannot be replaced with different contents: choose a new versioned ID.
Explicit local input paths remain supported and are never deleted merely because
they were supplied to a command. Local output paths intentionally retain outputs;
use a `dagshub:` output to publish large new datasets remotely.

For tools accepting a data path, use the generic execution wrapper:

```sh
.venv/bin/python -m benchmarks.common.artifact_store dagshub:ASSET_ID -- \
  YOUR_EXECUTABLE YOUR_SCRIPT '{data}'
```

`{data}` expands to the temporary verified path. A file asset preserves its original
filename and suffix. Archived manufacturing stores rebind relocated measurement
partitions only after verifying the recorded Parquet checksums.

## Existing case studies, API and document models

CHO raw/aligned reference readers, Fresenius provenance readers, and frozen-case
execution use the same remote descriptors or existing input blob store. Frozen
inputs are materialized in a temporary case and evicted after execution; previous
case manifests and task/reference definitions remain intact. Completed SDK runtime
workspaces of at least 10 MiB are archived using the existing owned-workspace
catalog and restored when required. `BIODEMO_KEEP_RUNTIME=1` is an explicit local
debugging override.

Set `BIODEMO_MANUFACTURING_STORE=dagshub:ASSET_ID/path/to/store` when starting the
existing application API. It resolves the store for the application's lifetime
and removes the temporary copy on normal shutdown. Access-scope and source-package
checks continue to apply. Keep the service running while follow-up questions use
that store.

Docling's 701 MB model directory is also remote. Explicit
`document_backend='docling'` ingestion hydrates it for that ingestion, then cleans
up. Automatic parsing uses available native fallbacks rather than silently
installing a persistent model cache. OCR/extraction failures remain visible.

Large saved `run.json` files now have small local metadata stubs with
`remote_payload` and the original SHA-256. The report/evaluation readers load the
original on demand. Large `output.json` and evaluator source maps have registered
remote descriptors. Retain **all** `benchmarks/assets/*.json` and
`results/offload/{catalog,inputs}.json` for recovery. Six byte-identical source-map
aliases share one remote object; original JSON bytes are preserved, but unknown
original filesystem mtimes on reconstructed aliases are explicitly recorded as
unknown.

## Authentication and recovery

### Experiment artifact archives, 2026-10-28

Completed `results/physics-value` artifacts are stored as
`dagshub:physics-value-artifacts-20261028`. Completed external-simulator runs have
individual assets named `external-simulators-RUN_DIRECTORY-archive-20261028`.
Their original paths are recorded in `benchmarks/assets/*.json`; the full list,
verified file counts and archive checksums are in
`results/offload/experiment-artifacts-20261028.json`.

The active `results/external-simulators/improvements-20261027` generation was
left local so cleanup does not interrupt the ongoing experiment. That directory
is not covered by the completed-run archives. Both bulk output directories are
excluded from Git; small scientific reports under `docs/case_studies` and all
recovery descriptors remain available for version control. Newly generated runs
still need archival after completion; Git exclusions do not upload anything.

Use `asset_path('dagshub:ASSET_ID/subdirectory')` for temporary access, or
`mounted_assets(ORIGINAL_PATH)` for code requiring the original directory paths.
Direct filesystem readers require one of these contexts or an explicit restore.
For example, from `backend/`, this lists an archived physics-value run without
retaining its data locally:

```sh
.venv/bin/python -m benchmarks.common.artifact_store \
  dagshub:physics-value-artifacts-20261028/pilot-20261027-final -- ls '{data}'
```

### Spreadsheet cleanup, 2026-10-27

The remaining spreadsheet packages were uploaded to the private bucket, read back
in full and verified before their local files were removed. Recovery descriptors
are in `benchmarks/assets/`:

| Asset ID | Original package |
|---|---|
| `fresenius-raw-package-20261027` | `benchmarks/fresenius/raw_package` |
| `cmo-ingestion-generated-20261027` | `benchmarks/cmo_ingestion/generated` |
| `demo-source-5c1de2c54e0141dd86a0b5616b9e66ee` | corresponding `runs/demo-agent/.../source` |
| `demo-source-8391b6c6b9514103ad583b34299c1e1a` | corresponding `runs/demo-agent/.../source` |
| `demo-source-b2151b00e1bd4aeb94f5fc9c04022634` | corresponding `runs/demo-agent/.../source` |
| `case-study-download-sources-20261027` | `frontend/public/case-study-results/sources` |

Fresenius validation/reporting and the ingestion evaluator hydrate their missing
packages for the duration of execution. Other direct filesystem consumers must
use `asset_path`, `mounted_assets`, or the generic execution wrapper above. The
website's archived source downloads need materialization when packaging a site
that exposes those downloads; they are no longer permanently stored in `public`.
Existing source URLs must not be assumed available without that packaging step.

The receipts are `results/offload/spreadsheet-cleanup-20261027.json` and
`results/offload/rebuildable-cleanup-20261027.json`. Only rebuildable frontend
caches and a duplicate static export were discarded without archival. Scientific
results, failed runs, provenance records, source code and dependencies were retained.

The isolated transport environment keeps DagsHub dependencies out of the app:

```sh
python3.11 -m venv .tools/benchmark-offload
.tools/benchmark-offload/bin/python -m pip install -r scripts/offload-requirements.txt
.tools/benchmark-offload/bin/dagshub login
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py configure \
  --repo YalmanchiliTejas/BioDemo
```

The existing authorized login is already configured on this machine. Credentials
stay in the DagsHub client's credential store; ignored `.offload/config.json`
contains only repository and prefix. Uploads verify repository privacy. Credentials,
locks and excluded configuration files are not included in data snapshots.

For an explicit persistent restore (debugging/recovery only):

```sh
.tools/benchmark-offload/bin/python -m scripts.data_artifacts fetch \
  benchmarks/assets/indpensim-archive.json /PATH/TO/NEW/100_Batches_IndPenSim.zip
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py restore \
  --workspace benchmark-case-RUN_ID
```

To publish an additional existing dataset and remove it after verification:

```sh
.tools/benchmark-offload/bin/python -m scripts.data_artifacts publish \
  /PATH/TO/DATA benchmarks/assets/dataset-VERSION.json --prune-local
```

For frozen inputs and owned SDK workspaces, retain the established offloader:

```sh
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py push-inputs
.venv/bin/python -m benchmarks.common.input_store evict --include-cache
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py upload \
  --include-unrecorded --prune-local
```

Full remote bytes are read back and checked before deletion. Changed local files,
failed uploads and checksum failures retain their local originals. Run upload
operations sequentially; the existing operation lock prevents concurrent mutation.

## Verified scope and trade-offs

The migration covered benchmark datasets, the IndPenSim publisher archive, CHO
references, frozen evaluation assets, model weights, owned retained workspaces,
large result payloads and evaluator maps. The cutoff for individual large result
and metadata files was 5 MiB; complete dataset directories were moved regardless
of individual file size. Small receipts, code, installed dependencies and Git
history remain local. This does not rewrite Git history or remove historical Git
objects. Logical source sizes are not a measurement of physical disk savings.

Reusing the existing private offloader minimizes setup; content checks and retained
receipts preserve trust; executable remote references support action; existing
case paths and interfaces preserve adoption. The trade-off is network/authentication
and download latency on cold execution. Active execution necessarily needs temporary
local working bytes. The implementation uses the existing S3-compatible bucket,
not a mounted filesystem or a second ingestion pipeline.

See [measured storage results](../../docs/case_studies/storage.md) and
`results/offload/storage-migration.json`. Official interfaces:
[DagsHub storage](https://dagshub.com/docs/feature_guide/dagshub_storage/) and
[repository bucket client](https://dagshub.com/docs/client/reference/repo_bucket).
