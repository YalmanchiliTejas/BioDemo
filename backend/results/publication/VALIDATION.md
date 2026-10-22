# Engineering and publication validation

This is an engineering preview with explicitly pending publication gates. It is
not a scientifically qualified manufacturing benchmark.

## Changes made in this execution

- `src/prime_runtime/bridge.py`, `harness.py`, `sdk_runner.mjs`: reserve time for
  finalization; close exploratory tools near the deadline; return actionable
  budget-exhaustion responses without spending additional retrieval calls;
  checkpoint and request final synthesis, allowing an explicit partial report.
  Specialist/lead separation and the original coverage/checkpoint system already
  existed and were regression-tested, not claimed as newly invented here.
- `benchmarks/common/isolated_runner.py`: recover durable checkpoints and host
  logs when the outer worker timeout prevents its `finally` block from running.
- `src/workflows/claim_verification.py`, `report_verification.py`: claim-local
  source/numerical checks, required classifications, uncertainties and missing
  information; reject unreviewed `verified_cause` labels and uncalibrated claim
  probabilities. Citation existence does not establish semantic entailment.
- `investigation_review.py`: accept the benchmark's `follow_up_actions` field.
  Meaningful missing-information arrays are accepted without relaxing the
  obligation to supply missing information or an explicit limitation.
- `src/manufacturing_data/analysis.py`: expose bounded original-source anchors
  for narrative-only sources; these anchors do not count as completed review.
- `benchmarks/baselines/investigation.py`: matched deterministic preparation,
  conventional fixed descriptive assembly, one-pass LLM synthesis, original
  source verification, explicit coverage groups, lossless evidence aliases and
  durable invalid/partial reports. Hidden labels are not inputs.
- `benchmarks/common/objective_scores.py`: batch source-coordinate reads with
  caches confined to one evaluation; preserve source hashes and reject source
  changes. Separate location validity from claim support.
- `src/prime_runtime/telemetry.py`, `benchmarks/common/usage.py`: preserve usage
  on failed reports and extract persisted child-session receipts without copying
  prompts/credentials or double-counting child attributions. Interrupted calls,
  child start times and complete prices remain incompletely measured.
- `case_runner.py`, `case_report.py`, `human_work.py`: code/prompt/skill and
  environment fingerprints; all-attempt cohorts; canonical-coordinate citation
  overlap; unknown costs; equivalent baseline eligibility; richer blinded review
  packets with claims, calculations, candidate dispositions and coverage.
- `scripts/build_publication.py`, trial/replay/review exporters, application API:
  reproducible report artifacts, a responsive dashboard and allowlisted public
  source/artifact downloads. Historical run files and frozen labels are unchanged.

## Tests and source checks

Final combined regression log: `results/publication/test-results.txt`.
**163 passed, 2 skipped, 1 failed**. The failing test is
`ChoCaseTests.test_recorded_prime_pilot_is_wired`, requiring the unavailable
`runs/cho-comparison` recorded pilot. No replacement result was fabricated.
Four localhost integration failures in the sandbox passed when rerun with socket
permission; the sandbox log is retained as `test-results-sandbox.txt`.

Desktop/mobile browser checks passed, with no horizontal overflow or browser
errors. Invalid source filenames returned 404. Screenshots are in this directory.
JavaScript syntax and `git diff --check` passed.

The new evaluator reproduced **all four** final development baseline score sets
exactly: `evaluator-replay.json`. Those are scorer replays, not new agent trials.
Measured scoring times were 27.44/30.69 seconds for the two CHO outputs and
0.34/0.24 seconds for the Fresenius outputs. These timings are not proof of an
end-to-end RLM speedup.

`results/verification/publication-source-audit/summary.json` records a fresh
offline audit of the historical CHO investigation: **76/76 source checks**,
**7 structured calculations**, **12/12 source hashes**. The report remains
incomplete under the newer coverage audit, with numerical prose requiring review.

## Actual baseline trials

Final development outputs before the scorer-only optimization:

| Case / method | Investigation status | Selected fields | Citation locations | Worker runtime | Benchmark wall time | Input / output tokens |
|---|---|---|---|---:|---:|---:|
| CHO-04 conventional `6efaaa88` | Technical structure complete; science pending | 1300/1300 | 72/72 | 81.75 s | 113.91 s | 0 / 0 |
| CHO-04 single-pass `2d55a826` | Incomplete | 1300/1300 | 190/190 | 147.19 s | 228.13 s | 35946 / 8962 |
| FRE-02 conventional `27aadbed` | Incomplete | 214/214 | 99.36%, 622 checked | 16.07 s | 21.14 s | 0 / 0 |
| FRE-02 single-pass `20a0c926` | Incomplete | 214/214 | 99.23%, 651 checked | 93.34 s | 98.55 s | 146077 / 9744 |

Conventional uses fixed rules and assembly; its scientific adequacy is unscored.
Single-pass used the provider-reported `gpt-6-luna`. Historical full OS runs used
GLM providers. This is not a quality-qualified comparison or a demonstrated win
for any method. All earlier failures remain in BENCHMARK_RESULTS.json.

The earlier single-pass development inputs were 63453 CHO and 345667 Fresenius
tokens. Later inputs were 35946 and 146077 after aliasing/packet changes. Output
and prompt details changed between development runs: do not treat these as a
frozen scientific quality or latency comparison. Alias round-trip integrity was
tested independently.

Single-pass inference prices and all complete costs remain unknown. Conventional
made no model calls, so its inference cost is zero; compute cost is unmeasured.

## Remaining gates

- Full OS provider access/funding blocks a completed current reliability series.
  The five-trial target remains unachieved; see the final run records for the
  actual attempts and provider errors, not invented skipped results.
- Incomplete scope, narrative verification and claim issues remain in baseline
  reports. Source transcription accuracy cannot replace an investigation.
- Semantic claim support, scientific plausibility, critical-evidence relevance
  and contradiction adequacy require independent domain assessment.
- The scientific rubric/thresholds are drafts; no independent blinded review,
  adjudication or scientific approval has been collected. Exported review forms
  are blank and bound to exact output/policy hashes.
- Manual/incumbent observations, total human effort, complete costs and untouched
  held-out generalization remain unmeasured. Provider backend revisions and
  sampling are not fully pinned; child-call timing/usage coverage is incomplete.

Use `BENCHMARK_RESULTS.json` for final all-attempt counts, including an explicitly
separate trace-only record whose execution/method/outcome is unknown.
