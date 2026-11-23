# Method A: structurally constrained residual UDE

An isolated Python 3.11/3.12 experiment for fitting irregular, partly missing LIMS
trajectories. It does not import or modify the application or its systems of record.

From this directory:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m biocore.method_a.train --epochs 120 --output artifacts/main
.venv/bin/python -m biocore.method_a.evaluate artifacts/main/best.safetensors --output artifacts/evaluation
```

Evaluation defaults to three additional independent 40-epoch fits on 3, 7, and 15
training batches. Use `--few-shot-epochs 0` for frozen inference only, or
`--report-only` to write failing diagnostic results without raising an error.
The fully pinned `requirements-tested.txt` records the environment used for the
included validation. CPU float64 is the tested replay target.

The job is to learn small kinetic departures from a known balance and hand
reviewable rate deviations to a later diagnostic method. A physical-only fit is
the simpler alternative; a direct neural derivative is more flexible but would
lose the requested structural constraint. This implementation uses a bounded
inner correction with exact dilution/feed terms. A zero-initialized network is
exactly the physical-only baseline at initialization.

This applies all four governing principles: a generated dataset and two commands
reduce setup; disjoint batch IDs, missingness masks, hashes, and measured checks
support review; the Method B export supplies actionable evidence; a standalone
package and JSON avoid application migration. The trade-offs are CPU cost for
float64, fixed one-row neural evaluations for bitwise replay, and weak separate
identifiability of learned physical constants versus neural corrections. Useful
measures are held-out assay error, Day-5 forecast error, fault AUROC, rate isolation,
solver work, and the observed learning curve. These are experimental findings,
not approvals to change manufacturing operations.

Implementation map:

| Module | Responsibility |
| --- | --- |
| `synthetic.py` | Independent NumPy RK4 plant, noisy 8–10-point trajectories, individual assay masks, fixed whole-batch splits |
| `model.py` | Positive log-space Monod parameters, 3→16→16→3 smooth residual, exact four-state balance, torchode Dopri5 |
| `loss.py` | Train-only max scales, mask-before-subtract MSE, physics-hijack ratio |
| `train.py` | Explicit dual-group Adam, half-window warmup, clipping, full-validation early stopping |
| `artifact.py` | Safetensors + JSON configuration/provenance + SHA-256 manifest, frozen reload |
| `evaluate.py` | Per-assay/per-batch metrics, y0-only forecasting, rate inference, fault acceptance, few-shot fits |
| `config.py` | Pydantic configuration and explicit deterministic seeding |

The generator uses 40 normal batches (15 train / 10 validation / 15 test) and
10 evaluation-only faults. It knows the inoculation state independently of
assays. Volume follows the exact known feed program; concentration assays have
heteroscedastic noise. Roughly 10% of all assay entries are missing. All plant
parameters remain identical across fault and normal batches, except qP drops
35% at hour 24 (the start of Day 2). Hidden biomass-associated inhibition changes
growth kinetics without making the qP intervention alter growth or uptake.
Ground-truth trajectories are benchmark targets only; training never reads them.

Every model tensor, ODE state, process input, and time is float64. torchode receives
separate time rows and process arguments for each batch. Ragged minibatches are
bucketed by observation count without interpolating observations or padding time.
The residual MLP uses fixed one-row evaluations to prevent batch-size-dependent
matrix kernels from spoiling exact replay. No batch normalization, dropout, or
shared adaptive error norm is used. Tests cover both batch ordering and composition
with nonzero neural weights. This is deterministic replay on the tested software
and CPU platform; it is not evidence of GMP compliance or cross-platform equality.

The default first 20% of epochs uses the first half of each timestamp sequence.
Validation always uses complete trajectories, and checkpoint selection uses only
validation loss. Group 1 uses lr=0.01 and no weight decay; group 2 uses lr=0.001
and weight decay=0.001. Gradient norms are measured before global clipping at 1.
Loss weights individual observed entries equally after per-state normalization.

Artifacts and evidence:

- `best.safetensors`: tensors only, with no executable serialization.
- `best.json`: model/scales, training configuration, exact dependency versions,
  split membership, train/validation data fingerprints, best epoch and loss.
- `best.sha256.json`: weight and sidecar hashes, verified before loading.
- `training_history.json`: every epoch's losses, group gradients, solver work,
  curriculum window, and physics-hijack ratio.
- `evaluation.json`: pooled and individual batch RMSE, pooled R², Day-5 titer
  forecast RMSE, solver NFE, learned constants, fault AUROC and isolation checks.
- `method_b_handoff.json`: all 25 held-out batches with assay-level observed masks,
  predictions and errors; physical prior and learned correction; interval rate
  innovations, exposure/interpolation flags, units and batch-level summaries.
- `few_shot/few_shot_scaling.json`: independent fits, learning-curve slope and
  whether errors decrease monotonically. Failure to improve is reported honestly.

Hashes detect inconsistent or damaged files; they do not authenticate the publisher.
Keep the artifact and manifest together. The loader rejects incomplete/mismatched
bundles, nonfinite or non-float64 tensors, and inconsistent state scales. Existing
output folders are reused; use a new output directory for each preserved run.

Rate deviations use amount balances rather than naive concentration differences:
subtract finite differences of predicted amounts from observed amounts, reverse
the substrate sign, then divide by trapezoidal biomass exposure. The identical
feed contribution cancels. Each assay requires two genuinely observed endpoints;
biomass alone may be interpolated for exposure, with this fact exported. Batch
summaries weight valid intervals starting at or after hour 24 by exposure. The
same estimator and window are used for both classes without labels. A negative
delta_qP signals lost productivity. Benchmark labels are attached only afterward
for AUROC. The learned inner correction is exported separately from these observed
deviations, so the two should not be confused.

The default acceptance is qP fault AUROC >0.90 and mean absolute batch-level mu/qS
deviation <15% of each true maximal rate, separately on normal and fault batches.
These are explicit synthetic benchmark thresholds, not calibrated clinical or
manufacturing limits. Sparse finite differences are noisy interval estimates;
missing endpoints can make a rate unidentifiable. Forecasts use only y0 and the
known feed program. Their primary score uses observed Day-5 assays, excluding
missing endpoints; a separately named synthetic-truth score uses all test batches.
No Day-1/2 observations are required. The few-shot comparison uses the same
validation/test sets and reports a single-seed trend without asserting monotonic
improvement or adjusting hyperparameters using test scores.

The mechanistic skeleton implements the equations in the requested Pinto-style
specification; this is not a numerical reproduction of an identified Pinto
dataset/paper. The inner learned correction follows the UDE formulation in
[Rackauckas et al. (2020)](https://arxiv.org/abs/2001.04385).
Solver assembly follows the official torchode documentation for
[extra arguments](https://torchode.readthedocs.io/en/latest/extra-args/) and
[Dopri5](https://torchode.readthedocs.io/en/latest/torchdiffeq/).
