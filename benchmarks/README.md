# Manufacturing OS evaluation

The governing specification is [README_benchmarks.md](../README_benchmarks.md).
The v2 evaluation asks whether the same Manufacturing OS produces equivalent or
better **correct, reviewable investigation outcomes with fewer total human-hours**.
It preserves the existing data layer, SDK runtime, datasets and legacy scores.

The primary outputs are quality-qualified-case rate, total observed human-hours
per qualified case (all attempts included), and paired human-effort reduction
only for matching, qualified outcomes that meet a predeclared noninferiority
margin. Model runtime is a separate machine diagnostic.

## What is implemented

- Case manifests freeze source allowlists, file hashes, objectives, conditions,
  cutoffs, references, budgets, seeds, deliverables and quality policies.
- Raw, historical, filename-challenge and Fresenius CSV-only structured
  diagnostic packages use the existing sources and field-aware renderer.
- One `InvestigationInput` interface dispatches the conventional parser,
  retrieval + single-pass model, and the existing Prime SDK via a raw-ingestion
  adapter. No alternative model loop or RLM implementation is introduced.
- Isolated case workers deny hidden references, original archives, public
  outcomes, other trial data and a cross-tenant canary. Their children inherit
  the policy. Historical audit independently rebuilds and compares every file,
  including scan/PDF bytes and metadata. Unknown historical availability fails
  closed. Originals are hashed again after execution.
- Objective scorers check emitted field values against independent references,
  critical-signal coverage, original citation locations/versions, reviewed
  scope/negative-control labels, and approved routing labels with a confusion
  matrix and under-escalation rate. Missing labels produce N/A.
- Review templates enforce independent blinded review, all deliverables,
  integrity gates, disagreement adjudication and frozen minimum quality policy.
- Traces record ingestion, scoped tools, mapping, verification, report/triage,
  proposed coordination, model usage, errors, budgets and artifact references.
  Human timers distinguish active work from pauses and machine waiting.
- Seven-stage human ledgers include failed attempts, retries, corrections,
  coordination and ongoing configuration. Shared setup is allocated across
  declared actual attempts; first-case and repeat-case costs remain separate.
- An updated Fresenius SDK trial can resume an earlier completed isolated trial
  with `--prior-run`, retaining the existing store, Blackboard and SDK session.

## Commands

Run from the repository root with the project environment (`.venv/bin/python`
in this workspace). Dependencies are in `.[benchmarks,manufacturing-data,app]`.

```sh
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action freeze
python -m benchmarks.common.benchmark_runner --benchmark cho --action inventory
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action cases --case FRE-02
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action audit --case FRE-02
python -m benchmarks.common.benchmark_runner --benchmark cho --mode conventional --case CHO-01 --condition raw
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode conventional --case FRE-02 --condition raw
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode conventional --case FRE-02 --condition held_out
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode conventional --case FRE-02 --condition clean
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode retrieval_llm --case FRE-02 --condition raw
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode full_rlm --case FRE-02 --condition raw
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode full_rlm --case FRE-03 --condition updated --prior-run results/evaluation/EARLIER_RUN_ID/run.json
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action evaluate --run-id RUN_ID --review reviewed-output.json
python -m benchmarks.common.benchmark_runner --benchmark all --action report --human-logs observed-human-work.json
```

`--mode retrieval_llm` requires `OPENAI_API_KEY`. `full_rlm` requires the existing
built Prime checkout and model credentials. The default SDK budget is 48 scoped
tool calls in original frozen cases. New Fresenius `full_rlm` runs default to
1800 wall-clock seconds (30 minutes), recorded in a separate frozen deadline
variant; explicit manifests retain their own deadlines unless overridden with
`--wall-clock-seconds 1800`. The publication trial script also defaults to 1800
seconds and supports this override. Original 900-second cases and results remain
intact. MacOS `sandbox-exec` is currently required
for publication-eligible execution. `--no-isolation` is development-only and
withholds scores. An unavailable system is never replaced with a surrogate.
Scored SDK trials pin the existing installed kernel interpreter through Prime's
supported `PRIME_AGENT_KERNEL_PYTHON` setting. They do not auto-bootstrap or
modify a shared user environment. Runtime installation/setup still belongs in
the observed setup ledger; a preinstalled environment is not zero human effort.

`--mode manual` and `--mode incumbent` record `not_tested` rather than inventing a
human investigation or competitor output. Collect actual workflows with the
human-study protocol before publishing comparisons. Existing human estimates
in pilot reports are not migrated into v2 timing measurements.

Each run writes `results/evaluation/RUN_ID/run.json`, `output.json` when execution
succeeds, `trace.jsonl`, a frozen quality policy, and human/review capture
templates. Reports include `summary.json`, `benchmark_comparison.md`,
`failure_analysis.md` and the existing `/benchmark` chart dashboard. Failed
attempts remain visible; failed audits withhold technical scores.

## Conditions and limitations

`raw` is primary. `historical`, `held_out`, `clean` and `updated` are separate
cohorts. The filename challenge renames copied source files without changing
measurements, with a hidden transformation manifest. It is a newly frozen
**format challenge on previously seen observations**, not proof of untouched
biological/incident generalization. Freeze new approved case versions before
model execution; do not retune on those results.

CHO clean/updated packages are currently `not_tested` unless an appropriately
frozen manifest is supplied. Its original values and publication-aligned
references support numerical checks, not causal truth. Empty raw cells are
reported as unavailable comparisons rather than predictions of interpolated
publisher values. Fresenius is synthetic, not confidential internal records.
Neither dataset currently supports independently established internal RCA
accuracy or a claim of recall prevention.

The investigation and triage policies in `benchmarks/rubrics/` are **drafts**.
Independent domain reviewers must approve the quality threshold,
noninferiority margin and routing labels before v2 investigations can qualify.
There are no measured human-study savings or hands-on competitor results.
Root-session Prime costs do not include child or OCR usage unless separately
captured; unknown costs remain unknown.

## Legacy compatibility and source preservation

The existing task runner remains available with `--legacy-tasks`. For example:

```sh
python -m benchmarks.common.benchmark_runner --benchmark fresenius --mode baseline --legacy-tasks --task FRE-02
python -m benchmarks.common.benchmark_runner --benchmark cho --action validate
python -m benchmarks.common.benchmark_runner --benchmark fresenius --action validate
python -m benchmarks.common.benchmark_runner --benchmark cho --action normalize
python -m benchmarks.common.benchmark_runner --benchmark cho --action compare
```

The original validated assets, references, source workbooks/archive, scores and
code were copied read-only before migration into
`benchmarks/snapshots/pre-evaluation-v2/`. Its manifest records SHA-256 checksums;
`--action freeze` verifies that snapshot without rewriting it. Large source
snapshots, frozen case packages and SDK trial stores stay local and ignored by
Git. Do not delete original sources as part of generated-output cleanup.

The five-phase `engineering_work.py` ledger remains a legacy diagnostic.
It is not silently mapped to the new seven stages or used to claim measured v2
productivity. The migration audit is in
[docs/benchmark_evaluation_migration.md](../docs/benchmark_evaluation_migration.md).


## Deterministic analysis and verified reports

The full RLM adapter now runs source-clock reconstruction, descriptive statistics
and anomaly checks before starting model inference. New tools calculate and
verify structured metrics and align offline/inline measurements without row-index
time proxies. Nested citations are preserved and batched; routine instrument
statuses no longer create an unbounded citation expansion. Facts, calculations,
interpretations and hypotheses remain separate in the saved report.

`--operational-triage-policy PATH` supplies versioned operational routing rules,
recorded with the run separately from hidden evaluation labels. Draft defaults
remain explicit and missing categorical signals produce UNKNOWN severity. This
does not approve a manufacturing policy or establish causal truth. Details and
saved-run verification are in [the verification note](../docs/deterministic_verification.md).
