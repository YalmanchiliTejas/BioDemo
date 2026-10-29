# Remote data and execution

Large benchmark artifacts have been uploaded to the private DagsHub repository
`YalmanchiliTejas/BioDemo`, read back in full, checksum-verified and pruned locally.
The application now fetches registered data for execution and cleans up its
working copies afterward. Keep the small descriptors in
`backend/benchmarks/assets/` and the existing offload catalogs.

Read [setup, execution and recovery commands](../../backend/docs/benchmark_offload.md)
for authentication, generation, existing case studies, API stores and failure
recovery. Run commands from `backend/`:

```sh
.venv/bin/python -m benchmarks.autonomous.run dagshub:case-synthetic-100 \
  /private/tmp/results-NEW --questions microbiological --modes linked_rules --seconds 180
```

## What moved

| Artifact group | Storage behavior |
| --- | --- |
| Fictional 100 / 1,000 / 10,000-file corpora | Immutable remote collections; evaluator truth stays outside worker access |
| IndPenSim publisher ZIP, historical projection and investigation store | Original bytes preserved; remote input/output adapters |
| CHO raw workbooks and aligned reference, frozen evaluation assets | Legacy paths hydrate only while the consuming operation runs |
| Docling model weights | Explicit Docling ingestion hydrates registered models temporarily |
| Retained ingestion/agent workspaces | Existing owned-workspace archive plus collection descriptors |
| Large result JSON and evaluator provenance maps | Small metadata stubs/pointers; readers recover original payloads on demand |
| Frozen case inputs | 67 verified remote blobs; 371 case links and 67 persistent cached copies evicted |

The collection descriptors reference **109 unique payload objects totaling
2,606,467,019 bytes**, through 116 descriptors including aliases. This excludes
the existing owned-workspace archive and frozen-input blob store. It is a remote
payload inventory, not a claim about physical disk space recovered.

The wider project scan also moved the original 10.95 MB design image, legacy demo
store and large demo source maps. Optimized frontend images remain local. The
original image is recoverable as `dagshub:design-original-perplex-30` and the store
as `dagshub:legacy-demo-store`.

Individual results/maps above 5 MiB were moved; whole dataset directories were
moved regardless of file size. Code, small receipts, installed dependencies and
Git history remain local. Working bytes exist locally during execution. Explicit
local output arguments remain a debugging option; use remote output arguments
for large generated data. Failed uploads preserve the sole local result and
report an error rather than deleting unverified data.

## Actual cold execution checks

| Check | Measured result |
| --- | --- |
| Private DagsHub 100-file corpus → isolated ingestion → investigation → scoring | Completed in 31.61 s total; worker 25.57 s |
| Critical file / span recall | 1.0 / 1.0 |
| Counterevidence recall / future citations | 1.0 / 0 |
| Retrieval precision / affected-scope precision | 0.286 / 0.5 |
| Tool calls / model calls | 18 / 0, rules baseline |
| Ingestion | 94 of 96 historical sources indexed; 1 corrupt, 1 unsupported |
| Authenticated CHO frozen-case cold fetch and audit | 1 passed in 65.54 s; temporary inputs cleaned |
| Focused storage/ingestion/runtime regressions | 78 passed, 1 remote-only test skipped; that remote test separately passed above |
| Final storage, document parsing and demo-launch regressions | 41 passed in 20.14 s |

The [complete cold-run summary](results/storage-cold-execution.json) preserves
all measured metrics, including hypothesis coverage of zero. Storage success
does not establish causal or model investigation quality. Earlier benchmark and
simulator failures remain documented in [results](results.md).

The broader regression run passed 152 tests, skipped one opt-in remote test and
failed three. Its Docling mock failure was corrected and the document suite then
passed (25 tests); the final combined 41-test run includes that fix and the new
temporary-model edge-case test. Two pre-existing failures remain: the absent
recorded CHO pilot and a stale committed comparison HTML report. Neither was
replaced with invented results. The broad suite was not rerun after the targeted
fixes.

The migration inventory is
[storage-migration.json](../../backend/results/offload/storage-migration.json).
Full remote readback preceded every prune. Immutable descriptors reject replacement
by different bytes. Source-map aliases with unavailable filesystem mtimes explicitly
record that limitation; original JSON bytes remain unchanged.

## Implementation map

| File | Responsibility |
| --- | --- |
| `backend/scripts/data_artifacts.py` | Existing private bucket transport, deterministic collection archive, full hash/size verification, safe extraction and prune |
| `backend/scripts/migrate_large_data.py` | Scoped inventory and migration of datasets, owned workspaces, large results/maps |
| `backend/benchmarks/common/artifact_store.py` | Temporary URI/path resolution, legacy mounts, remote JSON readers, model hydration and workspace archives |
| `backend/benchmarks/common/input_store.py` | Frozen execution inputs and temporary checksum cache |
| `backend/benchmarks/common/case_runner.py` | Execution lifecycle and remote result re-evaluation |
| `backend/benchmarks/autonomous/{run,generate,indpensim,export_demo}.py` | Remote data at existing benchmark and producer entry points |
| `backend/benchmarks/common/investigate_directory.py` | Remote directory input and verified follow-up workspace retention |
| `backend/src/manufacturing_data/store.py` | Checksum-verified relocation of measurement partitions |
| `backend/benchmark/application/api.py` | Remote manufacturing store for application lifetime |
| `backend/tests/test_data_artifacts.py` | Round trip, failure retention, unsafe archives, temporary cleanup, relocation and directory-workspace tests |

The existing offloader, input manifests, ingestion, retrieval, Prime harness and
case definitions are reused. No mounted filesystem or parallel ingestion stack
was introduced. Cold executions trade download time and network availability for
lower persistent local storage. A process killed without cleanup can leave a
temporary working directory; identify its owner before removing it.
