# IndPenSim source verification and simulator feasibility

Research and execution date: 2026-10-24. **Historical data verified; simulator gate failed. Optimization is `not_evaluated`.** A control change produced a measurable numerical response before failure, but no valid complete baseline or optimization improvement was established.

## Sources and historical dataset

Stephen Goldrick, *100 simulated industrial penicillin fermentation batches*, Mendeley Data version 2, published 2019-10-08, DOI [10.17632/pdnjz7zz5x.2](https://doi.org/10.17632/pdnjz7zz5x.2). The [publisher record](https://data.mendeley.com/datasets/pdnjz7zz5x/2) licenses the dataset under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Preserve this attribution, identify projections/transformations, and do not imply publisher endorsement. Local publisher metadata: `backend/benchmarks/cmo_ingestion/provenance/mendeley-v2.json`.

The verified existing download is `backend/benchmarks/cmo_ingestion/raw/100_Batches_IndPenSim.zip`: **503,792,426 bytes**, SHA-256 `bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00`. It contains:

| Archive member | Uncompressed bytes |
|---|---:|
| `Mendeley_data/100_Batches_IndPenSim_V3.csv` | 2,566,827,626 |
| `Mendeley_data/100_Batches_IndPenSim_Statistics.csv` | 3,904 |

The publisher describes simulated 100,000 L batches: 1–30 recipe-controlled, 31–60 operator-controlled, 61–90 APC/Raman-controlled, 91–100 faulty. **These historical groups are not randomized matched experiments.** No synthetic replacements were made to the measurements. The existing author [analysis notebook](https://github.com/StephenGoldie/indpensim-notebook) is useful provenance, not a replacement for the versioned source record.

Actual CSV inspection found a malformed header: 2,239 comma-separated header fields versus 2,237 numeric fields per row. The three fragments at zero-based header positions 33–35 belong to one PAT label; joining those fragments restores alignment without altering numeric records. The normalized schema contains 37 process/context columns followed by 2,200 Raman wavenumber columns. The existing `backend/benchmarks/cmo_ingestion/generate.py:freeze_indpensim` already implements this correction and preserves physical row references. Reuse this parser knowledge rather than creating another ingestion framework.

Important fields include elapsed time (h), aeration and liquid feed rates (source labels include L/h), pressure (bar), temperature (K), dissolved oxygen (mg/L), pH, substrate/biomass/penicillin concentrations (g/L), vessel volume (L), campaign/control metadata and Raman spectra. **One-based normalized column 32 (`Fault reference`) and column 37 (`Fault flag`) are evaluator labels:** exclude them and statistics-file fault labels from agent-accessible fault investigations. The statistics field `Penicllin_yield_total (kg)` contains values around millions, so its units require clarification; retain the source value/label and do not reinterpret it as a verified yield metric.

## Simulator sources and install evidence

| Component | Pinned source | License / state |
|---|---|---|
| PenSimPy 1.2.5 | [e08fc71fef193448f3ee9a304187dc92b88f3acc](https://github.com/Mohan-Zhang-u/PenSimPy/tree/e08fc71fef193448f3ee9a304187dc92b88f3acc) | MIT; installed and executed |
| fastodeint | [7d683eb7d9a13827eeddff40452710dbd9d929f0](https://github.com/Mohan-Zhang-u/fastodeint/tree/7d683eb7d9a13827eeddff40452710dbd9d929f0) | BSD-style upstream license; native source built locally |
| MATLAB IndPenSim candidate | [45c3d8c53ba423671acfb63de5855ecd4c8aa9d4](https://github.com/Lemniscabio/IndPenSim/tree/45c3d8c53ba423671acfb63de5855ecd4c8aa9d4) | Not executed: neither MATLAB nor Octave installed; license not established for code reuse |

Standard PenSimPy dependency installation failed because its required `fastodeint` distribution was unavailable from PyPI. Its original README-linked Quarticai repository returned 404. The accessible Mohan-Zhang-u fork was cloned and its **unmodified C++ source** built using modern pybind11 headers and the existing Anaconda Boost headers. This changes the build frontend, not simulator equations or native solver source. Upstream's vendored pybind11 is an old v2.2.0 checkout; avoid describing this as a successful standard upstream installation.

All installation was isolated in `/private/tmp/biodemo-indpensim-env`; the application's `.venv` was not changed. Verified environment: Python 3.11.4, macOS arm64, clang 16, numpy 1.26.4, pandas 2.3.3, scipy 1.17.1, pybind11 3.1.0. Source checkouts reside under `/private/tmp/biodemo-pensimpy-research`, `/private/tmp/biodemo-fastodeint-supported`, and `/private/tmp/biodemo-indpensim-matlab-research`.

Reproduction of this host-specific installation (network access and existing Anaconda headers required):

```sh
git clone https://github.com/Mohan-Zhang-u/PenSimPy /private/tmp/biodemo-pensimpy-research
git -C /private/tmp/biodemo-pensimpy-research checkout e08fc71fef193448f3ee9a304187dc92b88f3acc
git clone https://github.com/Mohan-Zhang-u/fastodeint /private/tmp/biodemo-fastodeint-supported
git -C /private/tmp/biodemo-fastodeint-supported checkout 7d683eb7d9a13827eeddff40452710dbd9d929f0
/Users/tejas/anaconda3/bin/python -m venv /private/tmp/biodemo-indpensim-env
/private/tmp/biodemo-indpensim-env/bin/python -m pip install numpy==1.26.4 pandas==2.3.3 scipy==1.17.1 pybind11==3.1.0 wheel cmake==3.31.10
/private/tmp/biodemo-indpensim-env/bin/python - <<'PY'
import pathlib, subprocess, sysconfig, pybind11
target = pathlib.Path(sysconfig.get_paths()['purelib']) / ('fastodeint' + sysconfig.get_config_var('EXT_SUFFIX'))
subprocess.run(['/usr/bin/clang++', '-O3', '-shared', '-std=c++11', '-undefined', 'dynamic_lookup',
    '-I' + pybind11.get_include(), '-I' + sysconfig.get_paths()['include'],
    '-I/Users/tejas/anaconda3/include', '/private/tmp/biodemo-fastodeint-supported/src/main.cpp',
    '-o', str(target)], check=True)
PY
/private/tmp/biodemo-indpensim-env/bin/python -m pip install --no-deps --no-build-isolation /private/tmp/biodemo-pensimpy-research
```

## Executed feasibility gate

First, the **unmodified published** `pensimpy.examples.batch_generation.run()` was executed. It completed 1,150 intervals/230 h in 1.225 s with an 18-column dataframe, but process fields became nonfinite at 134.2 h. The source converts invalid volume and penicillin to zero with `nan_to_num`; the returned reward 1542.0399 therefore **is not a valid improvement or successful baseline**. A direct `fast=False` alternate-solver attempt emitted an ODE integration warning and raised `OverflowError: math range error` in the unmodified evaporation calculation. These exploratory runs motivated the explicit gate below, rather than silently repairing model equations.

The implemented `backend/benchmarks/autonomous/simulator.py` then ran 12 serial, process-isolated episodes: seeds 1 and 2, native and SciPy solvers, published recipe, exact-repeat recipe, and one controlled intervention each. Baseline and intervention share seed, initial conditions, disturbances, solver and recipe, except sugar feed `Fs` was increased 1% for interval 100 (20 h). This is a **fixed feasibility intervention, not an agent optimization policy**. Each process had a 12 s wall budget.

| Solver / seed | Valid completed intervals before failure | Baseline / changed elapsed s | Repeat trace identical | Control response observed | Full baseline valid |
|---|---:|---:|---|---|---|
| fastodeint / 1 | 670 / 670 | 6.377 / 4.185 | Yes, valid prefix | Yes | No: invalid numerical state at 134.2 h |
| fastodeint / 2 | 676 / 676 | 3.383 / 3.100 | Yes, valid prefix | Yes | No: invalid numerical state at 135.4 h |
| scipy odeint / 1 | unknown, process timed out | 12.011 / 12.010 | not evaluated | not evaluated | No: 12 s budget exceeded |
| scipy odeint / 2 | unknown, process timed out | 12.016 / 12.060 | not evaluated | not evaluated | No: 12 s budget exceeded |

The two repeated SciPy episodes also timed out. Trace equality applies to successfully observed prefixes only; it does not establish valid full-batch reproducibility. Runtime varies with local load; isolated worker startup is excluded from per-episode internal timing but included for timeout results. **0/12 episodes produced an accepted full-batch result.** All terminal concentration outputs are `null`; no paired outcome improvement is reported. Model calls = 0 and inference API cost = $0 for these deterministic gate experiments; total infrastructure/energy cost was not measured. The gate failed, and optimization remains `not_evaluated`.

For seed 1, the interval-100 intervention changed `Fs` from 75 to 75.75 L/h; current dissolved oxygen changed from 11.18296119 to 11.17108214 mg/L, temperature from 298.10419639 to 298.10515650 K, and weight from 63979.30695813 to 63979.51402196 Kg. These are observed numerical responses at 20 h, not improvement metrics. The response check compares process variables, excluding actuator readback alone.

Machine-readable artifacts, outside Git:

- `/private/tmp/biodemo-indpensim-simulator-results/summary.json`: gate status, paired configuration, errors, timings and exact artifact paths.
- `/private/tmp/biodemo-indpensim-simulator-results/environment.json`: source commits, dependency versions, module SHA-256 and command/budget manifest.
- `/private/tmp/biodemo-indpensim-simulator-results/{fast,scipy}-seed-{1,2}-{baseline,repeat,changed}.json`: twelve complete episode records; native runs include every successfully observed interval. Timeout records explicitly report unknown completed-step count and no recovered trajectory.

From repository root:

```sh
PYTHONPATH=backend /private/tmp/biodemo-indpensim-env/bin/python -m benchmarks.autonomous.simulator --output /private/tmp/biodemo-indpensim-simulator-results --timeout-seconds 12
cd backend
.venv/bin/python -m pytest -q tests/test_indpensim_simulator.py
```

Five automated tests passed: numeric/action bounds, next-interval enforcement, observable-only policy payloads, invalid-state closure, matched-seed failure reporting, and hard-timeout reporting (some checks share tests). These are boundary tests with a controlled simulator substitute; the separate 12 real simulator executions above establish the actual numerical failure.

## Observation and intervention boundary

The [upstream observation function](https://github.com/Mohan-Zhang-u/PenSimPy/blob/e08fc71fef193448f3ee9a304187dc92b88f3acc/pensimpy/utils.py) returns exactly 15 current values: `Foil, Fw, Fs, Fa, Fb, Fc, Fh, Fg, Wt, discharge, DO2, T, O2, pressure, pH`. The adapter whitelists these, with elapsed time and episode status. Flow units are source L/h, weight Kg, dissolved oxygen mg/L, temperature K, off-gas oxygen %, pressure bar, and pH. Current penicillin, biomass, true kinetic parameters/disturbances and future arrays are excluded. The terminal objective is predefined as **penicillin concentration in g/L**, retrieved only by an evaluator after a valid completed batch.

Legitimate source controls are `Fs, Foil, Fg, pressure, discharge, Fw, Fpaa`; source recipe ranges are 8–150, 22–35, 30–75, 0.6–1.1, 0–4000, 0–500 and 0–10 respectively, in source flow/pressure units. Our conservative envelope permits at most ±1% of the current known recipe command, following the relative-action scale in the [upstream RL example](https://github.com/Mohan-Zhang-u/PenSimPy/blob/e08fc71fef193448f3ee9a304187dc92b88f3acc/pensimpy/examples/reinforcement_learning_boilerplate.py). Zero commands remain zero. This is a demo constraint, not a validated operational safety envelope. Unknown variables, booleans, strings, nonfinite/negative/out-of-bounds values and out-of-order intervals are rejected. Invalid process values close the session rather than hiding the failure. The wrapper uses recipe time in **hours** (`step * 0.2`), following the published batch example; the upstream RL boilerplate's minutes-based recipe lookup should not be copied.

The private Python session object is **not a security sandbox**: expose only serialized `observe`/`advance` outputs to model tools, never the session object, arbitrary Python, raw batch state or `evaluator_outcome`. PenSimPy returns preallocated future arrays from reset/step and fastodeint uses process-global parameters. Episodes therefore execute in distinct processes with hard deadlines, not simultaneous threads. No physical equipment or external manufacturing system is controlled.

## Product trade-offs and next work

The job is to establish whether this optional simulator is a defensible experimental instrument while historical ingestion proceeds independently. Reusing the existing historical archive/parser and adding a narrow optional simulator boundary keeps setup/adoption limited; explicit source/trace records support trust; a failed gate yields the actionable next step of numerical verification rather than an unsupported recommendation. A new optimization framework would add complexity without resolving invalid equations/integration, so it was deferred.

Priorities: (1) diagnose the native trajectory failure against the reference MATLAB model and pinned numerical tolerances; (2) establish a supported portable dependency build and longer-budget SciPy diagnostics; (3) validate full baseline biology and repeatability across seeds before any controller comparison; (4) only then connect bounded Prime policy tools and evaluate observed matched outcomes, including degradation. The historical investigation benchmark can operate now and does not require the simulator gate to pass. Neither historical correlations nor these simulations establish real GMP manufacturing improvements.
