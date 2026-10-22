# Benchmark design and implemented scope

## Shared contract

`run_investigation(input_package, objective, as_of, configuration)` accepts a directory of agent-visible source files. The worker returns extracted records with source locations, files and columns, optional analysis, and execution usage. The scored runner creates an OS-sandboxed worker process on macOS. It explicitly denies read access to the frozen canonical data, hidden labels, aligned CHO references, source maps and prior results. A denial probe must fail before the worker runs. Package-level checks reject symlinks, disclosing filenames and future CSV fields.

## CHO

The published ZIP is retained unchanged and checked against the record's MD5. Its 12 original workbooks are agent input. The 48 aligned CSVs, an exact-header structural map, and descriptive numeric summaries for 24 cultivations are evaluator-only. The inventory streams every sheet and CSV to count rows, missing cells, duplicate records, and timestamp order; it found 3,251,506 raw data rows, 6,539 empty cells, zero exact duplicate rows, and 231 backward timestamp steps. The conventional parser reads all workbook sheets. A separate fixed-format source-only normalization reconstructs 24 cultivations using sheet names and a one-minute inline grid. The first numerical check compares source and publication-aligned values at inoculation time with relative tolerance `1e-6` and absolute tolerance `1e-8`. The full-series check compares values at matching timestamps with normalized absolute error `abs(estimate-reference)/max(reference channel range, abs(reference), 1e-6)` and tolerance `0.01`. It does not assume bitwise equality after alignment. The aligned CSVs are not independent biological ground truth.

Task definitions CHO-01 through CHO-05 are in `benchmarks/cho/tasks/tasks.json`. CHO-03 and CHO-04 have no verified causal truth and require evidence/contradiction scoring, not root-cause accuracy. CHO-05 uses one deterministic, labeled synthetic workbook perturbation with a hidden manifest; extraction is run, while semantic consistency remains unscored.

The one-pass baseline computes per-sheet numeric count, range, mean, and first/last values from raw workbook rows, retaining row locations for those statistics. Retrieval balances source sheets across all 12 workbooks and caps the model input at 96 sheets per task. Source-citation validity is measured against the extracted sheets. No causal correctness score is assigned without a defensible reference.

## Fresenius

The frozen v1.1 data are reused; no 100-batch regeneration occurs. The existing `TemporalFactoryStore` handles record and field availability. Package v2.1 renders time-valid CSV, XLSX, text PDF, image-only scanned lab-review PDF and discrete process-event charts. A duplicate LIMS CSV uses aliased columns, fixed UTC-07 timestamps and numerical ratios displayed as percent of their stated limit; validation checks that the instant and value are preserved. Each CSV field, spreadsheet cell, PDF summary line, scan region and chart point maps back to a canonical record in an evaluation-only JSON file. Duplicate laboratory and maintenance exports are intentional and preserve the same observations. The scan noise uses recorded seed 417; no random manufacturing values are generated. A data-only validator rebuilds all five historical snapshots and checks provenance, source checksums, byte-for-byte output determinism and leakage without running an agent.

FRE-02 starts at the first action-limit observation in the incident family. FRE-03 advances through later action-limit observations. FRE-05 uses an unrelated action-limit batch. Incident labels select evaluation checkpoints only; they do not appear in objectives or agent source files. The baseline currently scores extraction, identity, grounding and critical lab record recovery. It does not score diagnostic hypotheses because it makes none.

## Existing agent reuse

The repository already contains a structured-record RLM with Blackboard, causal graph, decision graph, budgets and temporal tools under `src/`. It has not been connected to raw workbook/PDF/CSV packages. The `full_rlm` mode therefore raises a clear error instead of claiming its structured-record runs are comparable to raw-source baselines.

## Fairness and reporting

All modes must receive the same staged source files for a given task and the same `as_of`. Results record runtime and token usage. Runtime is not converted to human labor savings. Baseline B is available only with a configured model provider, and no score is reported when unavailable. Model conclusions need repeated runs and uncertainty intervals before claims of consistency or generalization.

`benchmarks/configs/scenario_splits.json` records prospective development/evaluation partitions. CHO partitions whole experiments, keeping both reactors together. Fresenius partitions task checkpoints but all share one underlying simulation. Earlier baseline runs covered every case, so neither partition is an untouched historical holdout; do not use the current results to claim held-out generalization. `python -m benchmarks.common.validate_splits` checks disjointness and coverage.
