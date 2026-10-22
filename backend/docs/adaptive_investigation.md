# Adaptive investigation execution

This revision addresses the recorded FRE-02 run
`8d8e1ebbeb564f799eaf7ddee8902bb8`. It does not claim a new completed live run.

## What changed

- A shared queue prioritizes unread source files, including narrative-only
  maintenance and operator records, followed by validation repairs, priority
  candidates and remaining source/entity units. Assigning work never hides it.
- Evidence packets retrieve 1–8 bounded selectors in one admitted call. Each
  selector returns at most 32 numeric or text observations, source coordinates
  and pagination. Exact repeated packets use a per-run cache with recorded hits.
- The lead can transfer reserved calls to specialists for named open tasks.
  Adaptive execution starts with 48 active calls and permits explicit increments
  up to a hard cap of 72. Extensions cannot enter the 90-second finalization
  reserve or change the deadline. The interactive harness has a 900-second
  deadline. Existing frozen cases retain their original fixed budgets.
- Saved report sections are keyed updates, retaining omitted findings. Specialist
  checkpoints are imported explicitly; conflicts require a lead decision.
  Assembly adds no reviewed dispositions or invented evidence. Preflight creates
  targeted repair tasks; child preflight cannot overwrite the lead draft.
- Every priority candidate requires an explicit marginal-value stopping decision
  in adaptive runs. Available evidence that may change the action keeps the work
  open. Missing external evidence needs retained questions and evidence requests.
  Operational convergence remains an agent-authored judgment requiring review.
- Explicit timezone-qualified timestamp cells can establish record chronology.
  They do not establish process alignment, event onset or causation. Process
  clocks retain their strict entity, clock-cell and ambiguity checks.
- Claims can declare display precision for referenced computed metrics. Only
  that rounding of recomputed arithmetic is accepted. Sentence-ending numerical
  literals are now checked; timestamp components and record IDs are excluded.
- Root call timing and persisted child usage remain recorded. New child activity
  receipts show activity/staleness and duration snapshots without source prose.
  Child snapshots are not additive token counts or per-call timing measurements.

## Evidence from the saved run

The original run took 565.361 seconds and ended incomplete. It admitted 44 of
48 tools, rejected three specialist attempts at the lead reserve, and left
four source/entity units unresolved (307/311 reviewed by the agent). These
are historical observations, not measurements of the new implementation.

Offline replay of the unchanged report verifies 992/997 source values and all
five structured metrics. All source hashes match. Five source-value checks
remain unavailable: two OCR observations and three JSON manifest lines. This is
not 100% source verification. Four explicit timestamp comparisons now receive
record-order receipts. A fifth remains rejected: the five-minute difference is
smaller than the claim's six-minute ordering tolerance. Two rounded derived
claims still need explicit display-precision declarations in a newly authored
report. Original reports, case inputs and evaluator labels remain unchanged.

Replay artifacts: `results/verification/adaptive-v1-replay/`. The original report
remains incomplete; replay is not a new live benchmark attempt or scientific
qualification. No runtime improvement or completion-rate improvement is yet
measured. Modal authentication was checked without making a provider request;
the required proxy credential is unavailable in this execution environment.

## Run matched trials

Regression record: the affected Python suite passed 122 tests with 2 skipped;
the adaptive/comparison subset passed 50 tests with one existing missing-pilot
fixture failure (`ChoCaseTests.test_recorded_prime_pilot_is_wired` requires
`runs/cho-comparison`). All seven provider configuration tests passed. The
dashboard's deleted-run crash and stale generated comparison report were fixed.
The additional historical-visibility regression passed (1 test). Both adaptive
case package audits passed (12 CHO files and 14 Fresenius files); isolated worker
permission probes still belong to the subsequent live trials.

Set `BIODEMO_MODAL_PROXY_TOKEN` in the launching shell to your valid Modal proxy
credential. The provider is selected explicitly below; there is no Prime fallback.

```sh
.venv/bin/python -m scripts.run_publication_trials \
  --cases CHO-04 FRE-02 --methods full_rlm --repeats 5 \
  --model modal/zai-org/GLM-5.3 --execution-policy adaptive --wall-clock-seconds 1800
```

This creates separate `*-raw-adaptive-v1-1800s` frozen manifests. Their source packages,
references and quality policies match their parent cases. The manifest binds the
new runtime policy and hard budget. Repeating the command reuses that immutable
variant; inconsistent variants are rejected. Run the same command with
`--execution-policy fixed` to measure the original 48-call control. Keep fixed
and adaptive results in separate cohorts by case specification hash. Do not
change code between repetitions. Include all actual attempts and report total
provider usage and unknown costs explicitly.

Do not claim reliability targets, faster convergence, scientific qualification,
human-effort savings or manufacturing improvements until those measurements and
reviews exist. Fresenius remains a synthetic manufacturing reconstruction
informed by publicly available FDA-related materials.

The publication runner now defaults to 1800 seconds per trial. Standard Fresenius
`full_rlm` runs also default to 1800 seconds when no explicit manifest is supplied.
Use `--wall-clock-seconds 900` for the original deadline comparison. Explicit
manifests preserve their frozen deadline unless a deadline override is supplied.
The original 900-second manifests and historical timeout records are unchanged.
