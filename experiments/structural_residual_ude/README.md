# Method A: lyophilization residual UDE

An isolated CPU float64 experiment for fitting **primary drying** from irregular,
partly missing thermocouple observations, endpoint timestamps, and optional
measured dried-layer thickness. Training, evaluation and CLI entry points now use
`HybridLyophilizationUDE`. No application or system-of-record change is required.

## Run training and evaluation

From this directory, using Python 3.11/3.12:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m biocore.method_a.train --epochs 120 --output artifacts/lyophilization
.venv/bin/python -m biocore.method_a.evaluate artifacts/lyophilization/best.safetensors --output artifacts/lyophilization-evaluation
```

Without `--data`, training uses explicitly labeled **synthetic software-test
data**, not measured product data. For supplied observations use
`train --data input.json --epochs 120 --output artifacts/my-fit`. Evaluation
reads the hashed `dataset.json` snapshot beside the artifact by default; it
never regenerates observations. `evaluate --data input.json` accepts an explicit
snapshot but still enforces frozen split/input provenance. For inference on a
new cohort, call `score_model(frozen_model, batches)` directly.

Optional `evaluate --few-shot-epochs 40` performs independent 3/7/15-vial fits,
capped at the available training count. It reports actual subset sizes, errors,
coverage and censoring; it does not assert monotonic improvement. The default is
zero extra fits. `--report-only` writes melt-bound diagnostics without raising
the strict physical-validity error. Solver/nonfinite failures still raise.

### Smoke test with the simulator

From this directory, after installing the experiment, generate the split files once
and run a five-epoch check using one batch from each split.

```bash
.venv/bin/python -m biocore.simulation --output artifacts/simulated
.venv/bin/python -m biocore.method_a.train --simulation-dir artifacts/simulated --smoke --output artifacts/smoke
cat artifacts/smoke/training_metrics.csv
.venv/bin/python -m biocore.method_a.evaluate artifacts/smoke/best.safetensors --output artifacts/smoke-evaluation
```

`--simulation-dir` uses the simulator's 20 training, 10 validation, 10 normal
test and 10 fault test batches. It keeps the irregular timestamps and sparse layer
observations and extends the solve window to the recorded endpoint with a masked
sensor row. The endpoint is the first simulator grid sample with at most 0.1% of
the layer remaining. The run records the source split seeds and hashes.

### Submit to Slurm

The Slurm launcher loads Anaconda, activates the existing `rl` Conda environment
and installs the experiment and its runtime dependencies from `pyproject.toml`.
The environment needs Python 3.11 or 3.12. To generate the splits on the cluster
before submitting the smoke job, run these commands from this directory.

```bash
module load anaconda
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate rl
python -m pip install -e .

SIM_DATA="$SCRATCH/biocore-lyo/simulation"
python -m biocore.simulation --output "$SIM_DATA"
SBATCH_TIMELIMIT=00:15:00 ./slurm.sh --simulation-dir "$SIM_DATA" --smoke
```

The launcher defaults to Purdue Scholar's `scholar` account, `cpu` partition,
and `normal` QoS. It requests one CPU and 4 GB of memory. Set `SBATCH_ACCOUNT`,
`SBATCH_PARTITION`, or `SBATCH_QOS` to override those scheduler settings.
It writes job logs to
`$SCRATCH/biocore-lyo/slurm-<jobid>.out` and `.err`, and training artifacts to
`$SCRATCH/biocore-lyo/run-<jobid>/`. Set `BIOCORE_RUN_ROOT` to use a different
shared output directory.

After checking the smoke job's CSV and checkpoint, reuse the same split files
for a full run.

```bash
./slurm.sh --simulation-dir "$SIM_DATA" --epochs 120
```

### Plot loss and learning rates

From this directory, with your Python environment activated, install Matplotlib
and replace `12345` with the job ID.

```bash
python -m pip install matplotlib
JOB_ID=12345
RUN_DIR="$SCRATCH/biocore-lyo/run-${JOB_ID}"
python plot_training.py "$RUN_DIR"
```

Open `$RUN_DIR/training_curves.png` to see the training and validation loss,
both optimizer learning rates, and where hybrid training begins. The residual
group's logged learning rate is its optimizer setting. Its parameters are frozen
during the physics-only warmup. Rerun the command to refresh the plot after more
epochs finish. For a local smoke test, use `python plot_training.py artifacts/smoke`.

## Observations and SI data contract

`lyo_data.py` defines `LyoBatch` and `LyoDataset`. A batch has:

- A unique `batch_id`, strictly increasing `times` in seconds, and `y0=[Ld0]` in
  metres, known at the first timestamp.
- Known `process_args`, using the layouts below.
- `observations[time,2]`: bottom temperature in K and dried-layer thickness in m.
  `obs_mask` records actual measurement availability. Neither channel must be
  complete; no missing layer assay is manufactured from a thermocouple reading.
- `primary_mask[time]`: independently designated primary-drying temperature
  samples. It is distinct from both measurement availability and model validity.
- Optional `duration_s`: the observed **absolute endpoint timestamp** in seconds.
  It must lie within the solve window. Its residual-ice definition must match
  `completion_remaining_fraction` (default 1e-4).
- Optional synthetic `truth` and evaluation-only `fault` annotation. Training
  never reads truth, and faults cannot enter training/validation/normal test.

| Control shape | Columns (SI units) |
| --- | --- |
| `[batch,2]` | shelf K, chamber Pa; config fill height |
| `[batch,3]` | shelf K, chamber Pa, frozen fill height m |
| `[batch,4]` | initial shelf K, chamber Pa, final shelf K, ramp duration s |
| `[batch,5]` | initial shelf K, chamber Pa, final shelf K, ramp duration s, frozen fill height m |

Shelf ramps start at absolute t=0, change linearly, then hold. Pressure is
constant. Optional fill heights affect geometry, normalization, depletion and
solver tolerances per vial; other geometry/material constants remain in config.
All timestamps and ramp durations are **seconds**, not hours.

Use `save_dataset(data, path)` / `load_dataset(path)` for an interoperable JSON
snapshot. The JSON envelope requires `schema_version: 1`, `units` equal to
`{"time":"s","temperature":"K","pressure":"Pa","length":"m"}`,
`channels: ["bottom_temperature_k","dried_layer_m"]`, `seed`, `provenance`,
`completion_remaining_fraction`, and `splits` with train/val/test/faults arrays.
Each batch record uses `batch_id`, `times_s`, `initial_dried_layer_m`, `controls`,
`observations` (missing values are `null`), `primary_mask`, optional `duration_s`
and optional `fault`. Train/val/test must be nonempty and all IDs disjoint;
faults may be empty for experimental data. Include source identifiers, revisions
and the origin of the primary mask/endpoint definition in `provenance`.

The default synthetic generator uses an independent NumPy RK4 plant with scalar
bisection for the heat/mass balance. Defaults: 15 train, 10 validation, 15 normal
test and 10 evaluation-only 35%-higher-cake-resistance cases; variable fill heights,
shelf ramps, 12–15 irregular timestamps plus a measured endpoint, 0.15 K sensor
noise, 180 s endpoint noise, and missing temperature observations. Layer states
are retained only as benchmark truth, not supplied as measured assays. The
plant coefficients/noise/fault are labeled synthetic in provenance. Whole-batch
splits are fixed before fitting. These fixtures establish software behavior,
not experimental process accuracy or real fault-detection performance.

## Physics and numerical assumptions

```text
Kv(Pc) = Kc + Kp Pc / (1 + Kd Pc)                 [W/(m² K)]
Rp(Ld) = Rp0 + A1 Ld / (1 + A2 Ld)               [m/s]
Pice(Ti) = exp(9.550426 - 5723.265/Ti
                + 3.53068 ln(Ti) - .00728332 Ti) [Pa; Ti in K]
R = H-Ld; delta = depletion_fraction*H            [m]
g = 1 - exp(-R/delta)                            [smooth active fraction]
G = 1 / [1/(g Av Kv) + R/(Ap kice)]              [W/K]
G (Ts-Ti) = mdot Hsub
mdot = g Ap [Pice(Ti)-Pc] / Rp                    [kg/s per vial]
dLd/dt = mdot / (rhoice porosity Ap)              [m/s]
```

The interface temperature is an algebraic unknown, not a second ODE state.
Frozen-layer conduction relates interface and bottom temperature. Geometry,
porosity, ice density, conductivity and latent heat are explicit config values.
The six coefficients retain the initial edit's names: Kc/Kp/Kd map to Kv A/B/C;
Rp0/A1/A2 map to Rp A/B/C. They are strictly positive log-space fit parameters;
exact zero coefficients are not supported by this parameterization.

The 3→16→16→2 network takes dried fraction and normalized shelf/pressure inputs.
Its factors `exp(eps*tanh(raw))` keep Kv/Rp positive and bound relative changes.
Zero initialization makes the initial network correction exactly zero.
Corrections enter the coupled balances, not arbitrary neural state derivatives.

The depletion gate is a disclosed numerical approximation with default width
0.1% of fill height, applied to both heat and mass transfer. The root equation
is divided by g to retain its finite limit at depletion. Operational completion
is remaining fraction <=1e-4; exact zero is asymptotic. The solver integrates
`z=log(expm1(R/delta))`, so `R=delta*softplus(z)` and
`dz/dt=-ungated_front_rate/delta`. This avoids a hard cutoff and endpoint
stiffness over long post-drying windows. Public `solution.ys` remains dried
metres; `solution.drying_coordinate` retains a nonsaturating duration-learning
signal. Metre `atol=1e-10` maps to per-vial coordinate tolerance
`min(atol/delta, rtol)`, with zero controller relative tolerance on unbounded z.
Here rtol is an absolute coordinate-error cap, relative to depletion width.

Newton runs under no_grad, stopping independently per vial. A single attachment
provides first-order implicit gradients `dTi/dtheta=-F_theta/F_T`; higher-order
implicit derivatives are unsupported. Melt-bound equilibria are capped at
273.16 K and flagged with `balance_valid=False`, `melt_excess_k`, and
`heat_balance_excess_w`. This differentiable continuation permits optimizer
recovery; it is not a valid physical prediction. Nonfinite/unconverged solves
still fail explicitly.

Default coefficients describe the documented pilot example. Height 8.6 mm is
rounded, Hsub=2.84e6 J/kg and kice=2.4 W/(m K) are constant approximations.
See [the source audit](../../docs/research/freeze-drying-sources.md),
[Vanbillemont et al. (2025)](https://doi.org/10.1186/s41120-025-00115-5), and
[Murphy & Koop (2005), Eq. 7](https://doi.org/10.1256/qj.04.94), including the
missing exponential in the 2025 paper's printed pressure equation. No freezing,
secondary desorption, transient sensible heat, chamber/condenser dynamics or
equipment-capacity model is included. Accepted shelf -65..20 C (supplied in K)
and pressure 0.5..100 Pa are input bounds, not qualification; published Kv
characterization was 5..25 Pa. Non-sublimating schedules are rejected.

## Loss and training decisions

`lyophilization_loss` weights vials equally, then combines:

| Term | Definition and reason |
| --- | --- |
| Temperature | Observed, independently primary, model-valid thermocouple MSE divided by `temperature_scale_k²`. Missing values are selected out before subtraction. |
| Layer state | Optional measured thickness error divided by that vial's fill height. No four-assay max scaling or synthetic truth is required. |
| Duration | Match z at the measured endpoint to the completion threshold. Remains differentiable after physical ys rounds to full dryness. Missing endpoints contribute zero. |
| Coverage | Penalize premature predicted depletion at observed primary temperatures using z, preventing the model from winning by hiding temperature observations. |
| Operating | Melt-bound violation squared, weighted by active fraction. Supplies recovery gradients while excluding post-drying thermal claims. |
| Residual | Mean squared relative Kv/Rp correction. Each coefficient is normalized separately so incompatible physical units are not pooled. |

Defaults in `LyoTrainConfig`: physics lr=1e-4, residual lr=1e-3, temperature scale
1 K; temperature/state weights 1, duration/coverage/operating weights 10, residual
weight 1e-3. These scales/weights are declared fitting choices, not calibrated
measurement uncertainties. Physical/neural parameters can be weakly identifiable.
Use independently measured material/equipment information when available.

Adam uses separate parameter groups and clips the global gradient norm to 1.
The first `warmup_fraction` of epochs freezes the zero-initialized neural
correction. It always solves **full trajectories**, preserving duration targets.
Ragged batches are bucketed by timestamp count and control layout without padding
or resampling observations. Full held-out validation selects checkpoints and
controls early stopping. Fault/test values never enter the training objective,
normalization, checkpoint selection or hyperparameter updates. The output
snapshot and hashes include held-out evidence solely to detect later changes.

`thermocouple_mse` excludes depleted and melt-bound temperatures; it returns a
differentiable zero if no points remain. Use endpoint/coverage supervision with
it. `drying_duration_loss` interpolates the internal coordinate at observed
endpoints, so sample near those timestamps. The completion-fraction definition
must agree with the experiment. A thermocouple elbow is not a direct measurement
of exact residual ice. The post-drying thermocouple rise is **not fitted**;
`temperature_defined=False` makes those limiting values unsuitable as predictions.

## Evaluation and artifacts

`score_model` is open-loop from known y0/controls. It reports measured-temperature
and optional layer RMSE/MAE/R², eligible/scored/rejected temperature counts,
endpoint RMSE/MAE in seconds, left/right-censored endpoint counts, solver work,
relative neural corrections, and primary-drying balance validity. Endpoint
crossings interpolate a uniform reporting grid plus observation times; each
estimate reports its interpolation interval. Conditional temperature RMSE must
be read alongside coverage and endpoint censoring. Missing metrics are null.

Optional fault AUROC ranks the magnitude of the label-blind endpoint-coordinate
residual, with scored cohort sizes. Labels attach only after prediction. There
is no qP/titer metric, biological rate-isolation test, manufactured acceptance
threshold, or claim of calibrated fault probability. Strict evaluation rejects
melt-bound primary predictions after writing the diagnostic report; it does not
declare process accuracy based on synthetic thresholds.

| File | Contents |
| --- | --- |
| `best.safetensors` | Data-only weights. |
| `best.json` | Schema v2, model type, SI units, model/training config, software versions, best validation epoch, source provenance, split IDs and fingerprints. |
| `best.sha256.json` | Weight/sidecar integrity hashes. Hashes detect changes, not publisher authenticity. |
| `dataset.json` | Actual observed input snapshot; no synthetic truth. Its hash is frozen in artifact metadata. |
| `training_metrics.csv` | Flushed after each epoch. Contains train/validation loss, phase and both Adam learning rates. The residual group is frozen during `physics_only`. |
| `training_history.json` | Written at the end of training. Contains loss components, phase, learning rates, gradient norms and solver work. |
| `evaluation.json` | Held-out metrics, coverage/censoring, coefficient values, physical-validity diagnostics and limitations. |
| `method_b_handoff.json` | Schema v2 SI trajectories with observed masks, discrepancies, heat/sublimation, Kv/Rp priors/corrections, endpoint status and validity flags. Undefined temperatures are null. |

`load_artifact` dispatches by model type and validates config, units, hashes,
finite float64 tensors and exact weight structure. Old schema-v1 fermentation
weights and new tagged fermentation artifacts still reload as fermentation
models. They are explicitly rejected by the lyophilization evaluator. Legacy
model classes, `synthetic.py` and their generic loss utilities remain for
historical replay; the default train/evaluate commands have been converted.
The old [VALIDATION.md](VALIDATION.md) records historical fermentation results
and must not be interpreted as evidence for this new pipeline.

## Function changes and verification

| Module/function | Responsibility and reason for the conversion |
| --- | --- |
| `lyo_data.LyoBatch/LyoDataset`, `validate_batch/validate_splits` | Explicit SI measurements, endpoint/primary masks and whole-vial holdout boundaries. |
| `lyo_data.simulate_plant/make_dataset` | Independent NumPy primary-drying fixture; replaces fermentation data in CLI execution. |
| `lyo_data.save_dataset/load_dataset` | Reusable JSON inputs and exact observed-data snapshots. |
| `loss.lyophilization_loss` | Combines the six physically relevant, missing-data-aware fitting terms. |
| `loss.thermocouple_mse/drying_duration_loss` | Fit only valid thermal observations and explicitly supervise endpoints; duration loss now accepts missing-endpoint masks. |
| `train.data_fingerprint` | Covers timestamp/state/control shapes, observations, primary/availability masks and endpoints; excludes synthetic truth. |
| `train.minibatches/solve_batches` | Preserves ragged times and mixed control layouts; always solves complete drying windows. |
| `train.gradient_norm/_validation/train` | Conservative physics optimizer, neural warmup, finite checks, full validation, provenance and component-level history. |
| `artifact.save_artifact/load_artifact` | Tagged schema-v2 lyo weights and units with legacy schema-v1 replay. |
| `evaluate._metrics/_completion/score_model` | Temperature/layer/endpoint scoring with missing metrics, censoring, validity and reporting resolution. |
| `evaluate.evaluate/few_shot_scaling/main` | Frozen evidence checks, SI diagnostic export, descriptive fault/few-shot reports and snapshot-based CLI. |

The job is a reviewable primary-drying fit. A physics-only fit is the simpler
baseline (zero residual or eps=0); a multi-stage transient model needs additional
properties and observations and is outside this change. Easy to Start: generated
example plus explicit input schema. Easy to Trust: independent fixture, masks,
provenance, numerical/gradient tests and honest invalid/censored outputs. Easy to
Act: SI discrepancy/validity exports for review. Easy to Adopt: standalone Python,
JSON, existing torchode dependencies and legacy artifact replay. Trade-offs are
the depletion approximation, first-order-only implicit gradients, user-supplied
primary/endpoint definitions, and no post-drying temperature prediction.

Tests cover conservation, independent constant/ramp calculations, endpoint
continuity and long windows, gradients, replay, mixed fill heights, malformed
inputs, masked losses, no truth/label leakage, warmup, deterministic training,
artifact integrity, provenance changes, censoring and end-to-end evaluation.
No synthetic fit constitutes experimental accuracy, process qualification,
manufacturing approval or GMP compliance.
