# Offload runtime data to DagsHub

The optional setup uses `.tools/benchmark-offload/`, separate from the benchmark
environment. Nothing has been uploaded or removed. The CLI uses DagsHub's
S3-compatible repository bucket; it does not put runtime data into Git.

## First-time setup

Create a **private** repository on DagsHub, for example `YOUR_USER/BioDemo-data`.
Check that its storage quota can hold the archive. The uploader checks that the
repository is private before transferring data. Then run from the project root:

```sh
cd /Users/tejas/Desktop/BioDemo
.tools/benchmark-offload/bin/dagshub login
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py configure \
  --repo YOUR_USER/BioDemo-data
```

Authentication stays in the DagsHub client's credential store. The project config
contains only the repository name and storage prefix, under ignored `.offload/`.
Credentials, environment files, bridge tokens, locks and known temporary/cache
directories are excluded from snapshots. Complete runtime archives may still
contain source data, conversations and internal paths, hence the private bucket.

## Preview

```sh
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py plan \
  --include-unrecorded
```

The plan is also written to `results/offload/plan.json`. It reports files from
owned runtime workspaces and skips active evaluation locks. `--include-unrecorded`
includes historical workspaces whose matching result record is missing; they are
preserved as unrecorded workspaces, never counted as fabricated benchmark attempts.
Without this option, only workspaces with finished result records are eligible.

## Upload and recover disk space

To free space after verification, run:

```sh
mkdir -p results/background-logs
nohup caffeinate -i .tools/benchmark-offload/bin/python -u \
  scripts/offload_benchmarks.py upload --include-unrecorded --prune-local \
  > results/background-logs/offload.log 2>&1 < /dev/null &
```

It runs separately from VS Code. Keep the Mac powered on, connected, and its lid
open. Watch progress with:

```sh
tail -f results/background-logs/offload.log
```

For upload only, omit `--prune-local`; that does **not** recover local disk space.
For one workspace, add `--workspace benchmark-case-RUN_ID`. No single giant local
archive is created. The process reads existing files directly and uploads unique
SHA-256-addressed objects. Identical files share one remote object. Every required
remote object is read back and SHA-256/size checked before its workspace can be
removed. This verification uses download bandwidth but does not create a second
local dataset copy. Workspace files are checked again before removal to detect
changes during upload. An upload error, changed snapshot or checksum failure
retains that workspace locally. Previously verified-and-pruned workspaces remain
archived even if a later workspace fails. Re-running resumes from existing objects.

Only the explicitly selected owned workspace under `benchmarks/runtime/` is
removed. Source datasets, frozen case packages, `results/` and the restore catalog
stay local. No failure result is changed to a pass, and available result records
are included in the remote snapshot. Runtime workspaces are offloaded this way;
case inputs use the checksum store described below.

## Case inputs

Frozen cases list each input file with its SHA-256. Each distinct input is kept
once in `.cache/benchmark-inputs/<sha256>` and hard-linked into every case's
`agent_input/`. Hard links are ordinary files, so the package audit is unchanged.
The same files are stored remotely under `biodemo-archives/v1/blobs/<sha256>`.

```sh
# Upload any inputs not yet stored remotely, then read every one back and verify it.
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py push-inputs
# Replace duplicate local copies with links to one cached file.
.venv/bin/python -m benchmarks.common.input_store deduplicate
.venv/bin/python -m benchmarks.common.input_store status
```

A benchmark run calls `materialize` before its package audit. Missing inputs are
linked from the cache, or downloaded from DagsHub, checksum-verified and cached.
To remove local inputs that are verified remotely (`results/offload/inputs.json`):

```sh
.venv/bin/python -m benchmarks.common.input_store evict [--include-cache]
```

Evicted inputs return on the next run, which then needs network access and the
DagsHub login. Set `BIODEMO_INPUT_CACHE` to move the cache.

## Restore for evidence rechecks

```sh
.tools/benchmark-offload/bin/python scripts/offload_benchmarks.py restore \
  --workspace benchmark-case-RUN_ID
```

The restore downloads only that snapshot, verifies each file and restores the
workspace at its original relative path. Existing workspaces or changed result
records are never overwritten. Unknown-source checks and scientific-review
statuses are unchanged. Restore into the original BioDemo location: retained
SQLite metadata and SDK sessions can contain absolute paths. Running citation
audits against an offloaded workspace requires this restoration first.

Keep `results/offload/catalog.json`: it records repository, remote manifest key,
manifest hash, verification time and local-removal status. It contains no tokens
and is suitable for versioning with project results. Manifests and data also live
in the remote bucket under `biodemo-archives/v1/`; retain the catalog separately
if relocating the project. Failed or incomplete archive operations never remove
their local source data based solely on a successful upload response or S3 ETag.

## Reinstall and test

```sh
python3 -m venv .tools/benchmark-offload
.tools/benchmark-offload/bin/python -m pip install -r scripts/offload-requirements.txt
.venv/bin/python -m pytest -q tests/test_benchmark_offload.py
```

Official interfaces:
- https://dagshub.com/docs/feature_guide/dagshub_storage/
- https://dagshub.com/docs/client/reference/repo_bucket
- https://dagshub.com/docs/client/reference/cli
