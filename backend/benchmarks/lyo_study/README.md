# Freeze-drying model and agent study

This additive research package tests whether explicit vial populations and finite
thermal storage improve forecasts and decisions compared with the existing
representative-vial model. Both model arms receive the same applicability gate:
predictions after equipment overload are diagnostic, not valid pressure-controlled
forecasts. Historical models and results are preserved.

The [study specification and implementation plan](https://github.com/YalmanchiliTejas/BioDemo/issues/1)
records the job, alternatives, four product pillars, design and limitations.

## What the comparison means

24 new authored synthetic cases span six deliberately balanced families. Each has
a forecast/operating-decision task at 6 h and a pretransfer task at 0 h. The same
saved Prime SDK model runs in three fresh restricted-tool sessions:

- A: common process characterization, observations and numerical Python.
- B: the same evidence and tools, plus the legacy physical model.
- C: the same evidence and tools, plus the heterogeneous transient model.

Common characterization includes numerical physical coefficients; A has no
supplied executable process model, but is allowed to derive its own calculations.
This does not remove physics knowledge from A. Only B/C receive host model fits
and outputs. A fixed decision policy using each model separately provides the
model-only controls. KEEP is the unchanged planned schedule.

The two model arms fit effective Kv and Rp multipliers from the same early weighted
thermal-node and remaining-ice observations, with identical bounds and objective.
Pretransfer has no receiving observations and no fit. Half-hourly remaining-ice
observations are synthetic instrumentation, not ordinary plant historian data.
Thermal measurements are not bottom-vial thermometry. Parameter fits do not prove
unique causal identification; the policy is nominal, not robust optimization.

The evaluator is the existing separately executed event-safe two-population
reference. It shares physical laws and thermal/population assumptions with the new
model; its pressure controller is an illustrative empirical law. Completion and
thermal targets after actual capacity failure are censored. Same-sample thermal
and capacity onsets are not accepted as pre-overload thermal evidence. Synthetic
population structure is close to the new model and favors its applicability.
Unknown receiving shifts and sensor bias remain. This is an exploratory shared-
physics benchmark, not independent experimental or industrial validation.

## Reproduce

From repository root, using the existing `.venv` (NumPy, SciPy, pytest and
Matplotlib), generate a fresh dataset and run numerical controls:

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyo_study.study generate --output backend/results/lyo-study-NEW/frozen
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyo_study.study models --dataset backend/results/lyo-study-NEW/frozen --output backend/results/lyo-study-NEW/model-only
```

Existing output directories are rejected. Protocol/source hashes are written
before generation, and input/source hashes verified before execution. A changed
implementation requires a new version and output directory; never overwrite a
frozen result. The original six-case development smoke dataset uses seed 1001 and
is excluded from the 24-case comparison.

The agent runner requires the existing adjacent Prime SDK bundle, saved Modal
research model/authentication, Node, and macOS `sandbox-exec`. No production model
route is auto-qualified. The normal production agent workflow is not evaluated:
this is a deliberately restricted tool-access experiment using its SDK/provider.

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyo_study.run_agents --dataset backend/results/lyo-study-NEW/frozen --output backend/results/lyo-study-NEW/preflight --preflight
mkdir -p backend/results/lyo-study-NEW/campaign
PYTHONPATH=backend .venv/bin/python -m scripts.run_bounded_agent_benchmark --suite backend/results/lyo-study-NEW/campaign --budget-usd 10 --max-requests 700 --command .venv/bin/python -m benchmarks.lyo_study.run_agents --dataset backend/results/lyo-study-NEW/frozen --output backend/results/lyo-study-NEW/agents --workers 2
```

Preflight verifies numerical-tool denial of private files and network and checks
SDK tool allowlists/authentication without sending inference. The admission gate
caps conservatively reserved spending; its estimates are not invoices. Local
socket/process sandbox permissions may be required. Preserve all timeouts, errors,
admission refusals and malformed submissions; do not retry scored failures for a
headline. `--resume` only fills unattempted slots under identical frozen inputs.

## Evaluation and reporting

The agent forecasts KEEP independently of its chosen action. Every proposed shelf
change preserves the past; pretransfer changes start at zero. No load change or
equipment command is executed. Prior excursions prevent whole-batch rescue claims.

Report forecast errors with reference eligibility and prediction coverage,
thermal/capacity confusion with abstentions and censored labels, execution failures,
feasible and unsafe selections, selection coverage, and achieved feasible
primary-drying throughput. Characterization earns zero operating throughput, but
is not automatically incorrect when an oracle knows a feasible action exists.
Hindsight feasibility is not evidence that an unknown shift was predictable.

Comparison with model-only controls separates model value from agent value.
Repeated tool calls are not physical replication. Confidence intervals are
descriptive paired case resampling, not proof of generalization across plants.
There is no residual-moisture, potency, sterility, release, full-cycle throughput,
energy, avoided-batch-loss or observed human-time-saving endpoint.

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyo_study.report --dataset backend/results/lyo-study-NEW/frozen --models backend/results/lyo-study-NEW/model-only --agents backend/results/lyo-study-NEW/agents --output docs/case_studies/lyo-study-NEW
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_lyo_study.py backend/tests/test_lyo_study_agents.py backend/tests/test_lyo_study_report.py backend/tests/lifesci/test_lyo_heterogeneous.py backend/tests/lifesci/test_lyophilization.py backend/tests/lifesci/test_process_engineering.py -q
```

Generated raw artifacts stay outside Git. Share only reviewed reports/plots and
sanitized public inputs/results, preserving their source hashes and exclusions.

## Supplemental analyses and infrastructure provenance

`development.py` replays the four previously inspected development examples. It
is a mechanism illustration, not fresh validation. `stress.py` freezes and runs
a separate 32-condition pretransfer equipment-capacity grid. This supplement was
motivated by discovering that the primary KEEP schedules contained no actual
capacity violations; it cannot retroactively change the primary protocol.

The 2026-11-02 primary run encountered a macOS process-group cleanup error after
some successful submissions. `recovery.py` preserves original artifacts,
reconstructs only submissions supported by matching accepted-tool and finished
journals, retains inconsistent attempts as infrastructure failures, and runs only
slots whose original attempt directory never existed. It neither retries nor
replaces scored failures. Its separate bounded proxy must fit the remainder of
the original $10 total admission budget.

`sensitivity.py` prepares a separate six-case, 36-session comparison: the smallest
opaque case identifier in each family, both tasks and all three arms. It uses
eight model calls and 240 seconds, with a final submission-only provider turn.
This is a post-hoc motivated, prospectively frozen joint budget/submission-policy
sensitivity on reused cases, not independent confirmation or a pure budget
effect. Its preflight makes no model calls. Its execution checks the combined
primary, continuation and sensitivity admission budgets against $10. The
primary SDK script, public inputs and scientific model sources remain unchanged.

These modules default to preparing a protocol without inference. Execution
requires explicit `--execute` and the corresponding local bounded proxy. See
each module's `--help` and the issue's dated protocol comments for exact inputs.

After the primary continuation and sensitivity have finished, `supplement.py`
joins original and sensitivity results on the exact same six cases, reports
coverage and common-prediction errors separately, checks actual final-turn tool
journals, and combines all three cost ledgers without treating unknown usage as
free. It performs no simulation or inference:

```sh
PYTHONPATH=backend .venv/bin/python -m benchmarks.lyo_study.supplement --base backend/results/lyo-study-20261102 --output docs/case_studies/lyo-study-20261102
```

Supply `--cost-ledger` explicitly when generating a continuation or sensitivity
report. The default discovery path refers only to the original campaign. The
recovered primary report uses a combined original/continuation ledger with
campaign-prefixed request ordinals; the sensitivity report uses its own incremental
ledger. The supplement records the combined total and original ledger hashes.

## Public case-study page

The static Next page at `/case-studies/freeze-drying/` compares agent A with agent
C. The follow-up is the default view, explicitly labeled as a post-hoc motivated
sensitivity. The primary cohort remains selectable; accuracy graphs use the
intersection of numerical predictions and display coverage. The revised-model-only
control remains available in the evidence section.

Export the reviewed archive into the frontend without running inference:

```sh
python3 frontend/scripts/export_lyo_study.py
node frontend/scripts/check_lyo_study.cjs --data-only
```

The exporter reads `docs/case_studies/lyo-study-20261102/`, copies reviewed reports,
PDFs, CSVs and source code, and records source/download hashes. The illustrative
trajectories are a separate, provenance-linked export from the frozen evaluator.
Build from `frontend/` with `npm run build`. Serve `frontend/dist` locally and run
`node frontend/scripts/check_lyo_study.cjs http://127.0.0.1:5186` from the repository
root for responsive, interaction, keyboard, source-data and download checks.
The browser check uses the existing agent-browser installation; its path can be
overridden using `AGENT_BROWSER_BIN`.
