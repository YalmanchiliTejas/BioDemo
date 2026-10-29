# PenSim source-fit baseline diagnostic on development seeds

28 October 2026. Recorded before any AI inference on the 9001–9048 study cases. No study evaluator file, receiving outcome or AI score was read. The frozen protocol documents and hashed study code are unchanged.

## Why this was run

In the frozen 9001–9048 fits, 14/48 growth factors sit at the upper bound 1.3. Compared against the seed-defined PenSimPy parameters, fitted factors track kLa (r=0.81) but barely track growth (r=0.19) or production (r=0.33). The fitter's "nominal" baseline is the PenSimPy seed-0 reset, whose initial inoculum (biomass 0.29) is at the 3rd percentile of the seed population (mean 0.50, sd 0.11). The PenSimPy growth-inhibition overwrite of the growth parameter was checked and does not fire in these runs.

## Method

`backend/benchmarks/external_simulators/fit_identifiability.py`, seeds 9501–9524 (disjoint from every study suite). Each source is generated exactly as in the study (feed 1, air 1.15 after 60 h, continuous oxygen, source admission). Three fits use the frozen bounds, loss and optimizer settings:

1. `seed0`: the frozen fitter, unchanged.
2. `population_mean`: the same three factors, with every random reset draw at its expected value.
3. `population_mean_inoculum`: as in 2, plus an initial-inoculum factor with bounds [0.6, 1.4].

Each fit then predicts eight receiving plans: feed 0.85–1.15 at air 1.15, and feed 0.85 or 1.0 at air 1.0. Predictions are compared with the actual seeded runs at the six study targets. Decision scores use the study scoring rule over all 24 scenario cells of the frozen grid. The 95% intervals come from 20,000 paired bootstrap draws over seeds. Artifacts are in `backend/results/external-simulators/fit-identifiability-dev-20261028/`.

## Results (24 seeds)

| | seed0 (frozen) | population mean | + inoculum factor |
|---|---|---|---|
| Growth factor at bound | 14/24 | 10/24 | 6/24 |
| Recovery r: production / growth / kLa | 0.23 / 0.48 / 0.74 | 0.11 / 0.47 / 0.74 | 0.11 / 0.47 / 0.73 |
| Inoculum factor at bound, recovery r | — | — | 16/24, 0.14 |
| Challenge-KEEP forecast error (normalized) | 0.042 [0.034, 0.049] | 0.036 [0.029, 0.043] | 0.035 |
| Decision score | 0.979 | 0.979 | 0.979 |

- The population-mean baseline reduces challenge-KEEP forecast error by 6.5% relative (95% CI −9% to +21%). This is not a clear improvement. Decision scores were identical in 480 of 576 cells, and the mean is unchanged.
- The inoculum factor is not identifiable from P, DO and S after 20 h (16/24 at a bound).
- Growth and production remain weakly identified under every baseline. The likely reason is that time-varying seeded disturbances (for example the filtered growth-rate disturbance) cannot be represented by constant factors. This is a limit of the model structure, not of the baseline choice.

Conclusion: under the frozen decision rule ("amend only if a fix clearly helps"), the fit is not amended. The weak identifiability of growth and production is a disclosed limitation of the tool.

## Benchmark-structure findings

- **Ordinary-case KEEP equals the source.** Since the source-admission addendum, the source plan (feed 1, air 1.15 after 60 h) equals KEEP in the 12 ordinary PenSim seeds, and source and receiver use the same seed. The receiving KEEP trajectory is therefore identical to the completed source. That source is given to both arms and contains the 96 h targets exactly, with points at 66.2 h and 72.2 h. This was verified numerically on every development seed. The `standard` plan equals the source in every case.
- **Copying the source beats every physics fit at forecasting.** For challenge KEEP plans (feed 0.9, 1.05 or 1.1), interpolating the completed source gives a normalized error of 0.022 [0.020, 0.025]. The population-mean physics fit gives 0.036, which is worse by 0.014 [0.007, 0.021]. Copying wins in 19/24 seeds. The receiver shares the source's disturbance realization, while the nominal tool has no disturbances.
- **Little outcome signal across plans.** The 96 h product differs across the eight plans by a mean of 5.2% of the median (maximum 10.3%). Decisions are dominated by explicit resource and oxygen feasibility.

These findings bear on what the frozen A/B comparison can show. Same-seed receivers make the completed source a near-oracle for forecasting, which disadvantages a disturbance-free tool and compresses decision contrasts. They affect both arms equally, so they do not bias the arms differently, but they must be reported. Changing the receiver design (for example, independent receiver disturbance realizations) would be a new protocol, not an amendment to this one.

The single admitted source with low raw-oxygen intervals (seed 9014, continuous policy) should also be disclosed. Under the continuous-oxygen policy, `admit_source` checks only that oxygen is nonnegative and finite.
