# External-simulator agent experiment

**Latest completed repair study:** [corrected physics and final AI comparison](../../../docs/case_studies/model-repair-continuous-20261028/report.md). 1,151/1,152 sessions scored;49 regression checks passed, one known full-batch failure retained. Current-source kinetic fitting, observed-state SMPL initialization, source admission, and continuous oxygen-state handling were corrected. Average effects favored physics in all six comparisons, but the all-three meaningful-effect criterion was not met. Earlier reports below retain their original configurations and results.

**Latest executed study:** [new operating challenges](../../../docs/case_studies/operating-challenges-20261028/report.md),
with a separately retained [original batch](../../../docs/case_studies/operating-challenges-initial-20261028/report.md)
and one paired connection-recovery pass. Physical models and calibration values
were kept fixed. This is exploratory simulation evidence; the all-three benefit
criterion was not established. See [execution methods](../../../docs/research/operating-challenges-execution-20261028.md).

**28 October follow-up:** source-only physical oxygen calibration, a fresh
72-case simulator experiment (three AI repetitions,432 attempts), and a separate
real CHO batch forecast (16 cultures/eight held-out conditions,64 attempts).
See [the new report](../../../docs/case_studies/physics-improvements-20261028/report.md)
and [CHO protocol](../../../docs/research/cho-real-prediction-protocol-audit.md).
The230h viscosity failure is diagnosed and retained, not repaired by clipping.
Signed net heat Q is allowed by the corrected admission guard; physical negative
material/viscosity states are still rejected. Failed generations are preserved.

The following sections describe the earlier24-packet pilot. Its additive oxygen
calibration and case counts do not describe the October28 follow-up. Reports and
frozen protocol files identify the exact treatment and datasets for each run.

**Current primary comparison: the same AI with a physics-model tool versus
without any supplied physics model.** The corrected runs are named
`clean-ai-physics-comparison-*`. Earlier runs gave model specifications to both
arms and answered the narrower executable-access question; do not use their
numbers as the answer to the no-supplied-model comparison.

This tests whether a research agent benefits from an executable nominal process
model when predicting, selecting operating changes, and adapting a recipe to a
changed receiving operating plan. All process outcomes in this experiment are
**simulated**, including the prediction targets. Real CHO measurements are not
used in this particular experiment.

Use the final dataset and final comparison named in the executed report. Earlier
directories preserve development failures and superseded comparisons; they are
not additional successful trials to pool with the final result.

## Job, decisions and limitations

The user's job is to understand whether model access helps an otherwise matched
agent, with receipts that a beginner or reviewer can inspect. We reuse Prime's
existing SDK/provider, numeric sandbox and saved model, and add no production
route qualification, equipment writer, UI replacement or system of record.

The simple alternative was to expose prepared model-result tables. The chosen
final implementation executes the external nominal simulator in a fresh worker
on every physics query, then checks its output against the frozen nominal record.
The more ambitious alternative is a prospective laboratory comparison and true
source/receiving plant validation. Neither is claimed here.

Easy to Start: one isolated dependency environment and repeatable commands.
Easy to Trust: source commits, hashes, exact units, withheld evaluator outcomes,
failed receipts and explicit limitations. Easy to Act: submitted operating actions
are replayed in the virtual process, with measured simulated consequences.
Easy to Adopt: existing agent/provider boundaries are reused. The trade-off is a
small, carefully bounded development benchmark rather than industrial validation.
Observable measures are forecast error, objective change, side effects, completion,
tool/model calls and wall time. Human effort and plant outcomes are unmeasured.

## What actually runs

* **IndPenSim via PenSimPy:** original external equations/controllers through the
  pinned Python/C++ port, with the documented native cube-root correction and
  exact control-clock endpoints. The scored horizon is **96 hours**, including
  a decision at 80 hours. It is **not a complete 230-hour batch**.
* **SMPL/mAbEnv upstream core:** the original, unmodified `UpModelHelper` class
  for the **17-state reactor/separator** subsystem, integrated for **24 hours**.
  The class is loaded from its AST to avoid unrelated RL/MPC dependencies. This
  does not run the full 1,970-state downstream environment.

Source links:

* [Original IndPenSim author distribution](https://www.mathworks.com/matlabcentral/fileexchange/49041-industrial-scale-penicillin-simulationv2)
* [PenSimPy source](https://github.com/smpl-env/PenSimPy)
* [Original IndPenSim paper](https://www.sciencedirect.com/science/article/pii/S0168165614009377)
* [SMPL source](https://github.com/Mohan-Zhang-u/smpl)
* [SMPL mAb equations/documentation](https://smpl-env.github.io/smpl-document/mabenv.html)
* [SMPL paper](https://arxiv.org/abs/2206.08851)

## Fair comparison

Two initial-condition seeds and two receiving operating factors in each process
produce four process/regime combinations per simulator. Each supplies three task
packets and two agent arms: **24 packets / 48 attempts**. Tasks and regimes reuse
underlying seeds and are correlated; they are not 24 independent plant cases.
This is a small descriptive pilot, not a powered or untouched confirmatory trial.

A and B receive byte-identical process-evidence packets, the same AI/reasoning
setting and ceilings, and fresh memory-free sessions. Arm order is counterbalanced.
Both have general numerical Python. **A gets no supplied equations, model
coefficients, model initialization, model-derived calibration, model predictions
or simulator access. B additionally gets the live physical-model tool.** Its
model specification and calibration stay behind that typed tool. Both receive
the same actual operating schedules, settings, units, actions and observations.
A can reason using its learned knowledge or derive calculations from data;
"without a supplied model" does not mean it knows no physics. Installed process
simulator imports and host model-configuration files are blocked in numerical
Python. Equal request ceilings do not make native solver compute identical to
ordinary numerical Python compute.

The nominal model uses fully declared initialization. PenSim's nominal future
disturbances are disabled (`Dis=0`); no private nominal disturbance trajectory is
given to B. SMPL's nominal initial state is explicitly published without random
perturbations. Actual evaluation batches have separate seeds/initial conditions.
Product predictions use a multiplicative source-endpoint calibration and the
process indicator uses an additive source-endpoint calibration. Those calibration
values and their rule are internal to B's model tool. A receives the source
measurements themselves, with no model-derived calibration. A completed source batch's history is
available before receiving time zero; it is not a receiving-future observation.

**Prediction:** receiving observations through 80 h (PenSim) or 6 h (SMPL), then
predict the declared endpoint under KEEP.

**Outcome:** same observation cutoff; select one bounded action and replay it in
the external actual-realization process. Predict KEEP separately, even when
selecting another action, so forecast scoring is not confused with action choice.

**Simulated recipe transfer:** completed source history plus a receiving plan with
nominal aeration/throughput at 95% or 90% of source. No receiving observations.
Predict KEEP and choose a bounded receiving action starting at time zero. Strain,
geometry and material realization are held the same across source and receiving.
This is an optimistic operating-plan transfer test, **not demonstrated site
transfer, different-vessel scale-up, or receiving-site readiness**. SMPL has no
oxygen-transfer/mixing-gradient state. PenSim's vessel geometry is hardcoded.

## Endpoints and units

* PenSim: predict product **g/L** and dissolved oxygen **mg/L** at 96 h. Maximize
  product concentration at that partial horizon, never call it yield or economics.
  Temperature is K. Report DO floors/minima and volume alongside the objective.
* SMPL: predict reactor mAb **mg/L** and viable cells **cells/L** at 24 h. Its
  equations use **minutes**, so integrate the physical separator concentration
  times external product-outlet flow (`x[14] * u[3]`, mg/min) over minutes. Exclude
  reactor/recycle internal streams. The outcome horizon is the remaining 18 h;
  transfer begins at zero and uses 24 h. Do not compare their raw masses as though
  the horizons were equal. Do not use the stock mixed-unit productivity reward.

Actions are the frozen four-option grid. PenSim offers ±1% sugar feed or +1%
aeration; SMPL offers ±1% balanced throughput or coolant −0.5°C. These bounds are
pilot assumptions, not experimentally qualified manufacturing safety limits.
Objective improvement is reported separately from side effects; no product-quality
or safety certification follows from a larger objective.

## Numerical evidence and retained failures

Repeated trajectories must match, tighter tolerances and alternate solvers must
agree within the frozen 0.5% endpoint tolerance, and a changed control must change
the process objective. Native PenSim derivatives are checked against the original
Python equations on recorded states. Raw nonfinite or materially negative states
are rejected before upstream clipping can hide them. Passing these checks proves
numerical consistency in this envelope, **not independent physical accuracy**.

The complete 230 h PenSimPy trial failed with a negative raw viscosity state.
The failure remains in `pilot-20261027-v1`; full-batch optimization is unqualified.
Earlier stock-code probes also exposed a C++ `1/3` integer-division discrepancy
and a supplied long draw-off schedule. The audit/build receipt records the native
correction and the explicit two-hour pilot draw-off recipe; all scored 96 h runs
end before the first draw-off at 100 h. Initial zero product is still subject to
the upstream 0.001 floor and is counted. No DO floor event may be concealed.

The first completed agent comparison used incompletely shared nominal assumptions
and cached results. Its `audit-notice.json` marks it superseded. It is retained
for transparency and excluded from final comparisons. The next 47/48-submission
comparison supplied equations and model-derived calibration to both arms; it
therefore did not provide the requested no-model baseline. Its correction notice
identifies the replacement clean A/B run. Actual corrected inputs are frozen in
the **run's `common-inputs/` and each attempt's `agent-input/`**, not the legacy
dataset `public/` model-specification files. No corrected metric pools earlier
runs. Non-AI controls are optional diagnostics, not a replacement primary arm.
The underlying simulator outcomes, seeds and scoring rules are reused unchanged.
The corrected **run protocol** defines the A/B treatment and records every common
packet hash before inference; older dataset-generation treatment text remains
historical metadata, not the corrected agents' actual inputs.

The forward model and evaluator share upstream equations. Good performance shows
usefulness inside those model families, not independent experimental validation.
Synthetic observations are idealized; actual receiving faults, imperfect assays,
plant uncertainty and scientific adjudication are outside this pilot.

## Reproduce

From repository root, create a separate Python 3.11 environment and install
`backend/benchmarks/external_simulators/requirements.txt`. Clone the source
repositories at the exact commits in the recorded protocol. Build the native
adapter (requires a C++ compiler and Boost headers):

```sh
PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.native \
  --source /private/tmp/biodemo-fastodeint-source \
  --output /private/tmp/biodemo-audited-native \
  --boost-include /Users/tejas/anaconda3/include

PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.experiment \
  --output backend/results/external-simulators/NEW-DATASET \
  --pensim /private/tmp/biodemo-pensimpy-source \
  --smpl /private/tmp/biodemo-smpl-source --native /private/tmp/biodemo-audited-native

cd backend
/private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.run_agents \
  --dataset results/external-simulators/NEW-DATASET \
  --output results/external-simulators/NEW-COMPARISON --workers 2
```

Use fresh output directories. macOS must permit applying the nested OS sandbox;
the runner fails before inference if isolation probes fail. The saved Prime SDK
and research-provider authentication are reused; no credentials enter packets.
Create `STOP` in the comparison output to stop queued pairs and end active attempts.
Inference billing is unknown unless independently measured, even if an SDK ledger
shows zero. Results retain failure denominators and do not claim real time savings.

Run integrity tests with:

```sh
PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m pytest \
  backend/tests/test_external_simulator_experiment.py backend/tests/test_indpensim_simulator.py -q
```

## Reproduce the October 28 follow-up

Use a new output directory for each generation/run; do not replace existing
receipts. Restore archived historical inputs via their asset descriptors if needed.
The raw CHO asset descriptor is `backend/benchmarks/assets/cho-raw.json`.

```sh
PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.experiment \
  --corrected --seeds 3001 3002 3003 3004 3005 3006 3007 3008 3009 3010 3011 3012 \
  --output /private/tmp/NEW-FRESH-DATASET \
  --pensim /private/tmp/biodemo-pensimpy-source --smpl /private/tmp/biodemo-smpl-source \
  --native /private/tmp/biodemo-audited-native

PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.run_agents \
  --dataset /private/tmp/NEW-FRESH-DATASET --output /private/tmp/NEW-FRESH-AGENTS --workers 6 --repeats 3

PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.cho_real \
  --raw /private/tmp/biodemo-cho-raw/workbooks --paths-from /private/tmp/NEW-FRESH-DATASET/protocol.json \
  --output /private/tmp/NEW-CHO-DATASET

PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.run_agents \
  --dataset /private/tmp/NEW-CHO-DATASET --output /private/tmp/NEW-CHO-AGENTS --workers 6 --repeats 2
```

The executed agent model/budgets and source snapshots are in each run's
`protocol.json` and `runner-source/`. Repeated AI sessions use separate
`repeat-NN/A` and `repeat-NN/B` directories; their sample size is clustered by
underlying seed/experimental condition. No failure is silently retried as a new
successful trial. An expected-failure regression records the unresolved complete
batch model defect. It is not counted as a passed physical validation.
