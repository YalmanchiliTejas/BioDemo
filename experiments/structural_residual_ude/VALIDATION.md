# Recorded synthetic experiment

Historical fermentation run: the results below predate the lyophilization
conversion. They do not validate the current lyophilization model, trainer,
losses, evaluator, or their experimental accuracy. See README.md for the current
pipeline and its software checks. The original figures are retained as evidence
of that earlier experiment.

Executed on Python 3.11.16, macOS arm64 CPU, torch 2.15.0, torchode 1.0.1,
using `requirements-tested.txt`, seed 2023. Editable package installation succeeded.
All work and output are confined to this experiment; dependencies were installed
in `/private/tmp/biocore-method-a-env`.

The 120-epoch training budget stopped after epoch 67 (zero-based), with the best
full-trajectory validation checkpoint at epoch 42. No test or fault batches were
used for fitting, scaling, checkpoint selection, or hyperparameter tuning.

| Held-out normal assay | RMSE (g/L) | R² |
| --- | ---: | ---: |
| Biomass X | 0.15933 | 0.999386 |
| Glucose S | 0.53801 | 0.999182 |
| Titer P | 0.02421 | 0.999867 |

The y0-only Day-5 titer RMSE was 0.04976 g/L on 13 observed endpoints;
the separately scored synthetic-truth RMSE was 0.03950 g/L on all 15 test batches.
Mean/max solver NFE were 44/44. The normal-test physics-hijack ratio was 0.01177.

Fault qP AUROC was **1.00** across 15 normal and 10 fault batches. Mean absolute
mu deviations were 1.45% / 1.62% of true mu_max on normal / fault batches;
qS deviations were 3.76% / 3.04% of true qS_max. All passed the predeclared
15% near-zero criterion. These diagnostic estimates use observed-minus-predicted
amount balances; they do not access true plant rates or fault labels.

| Physical constant | Learned | Ground truth |
| --- | ---: | ---: |
| mu_max | 0.026531 | 0.028 |
| Ks | 2.349386 | 2.0 |
| qS_max | 0.055689 | 0.055 |
| qP_max | 0.007707 | 0.008 |

Independent 40-epoch fits using 3 / 7 / 15 training batches gave synthetic-truth
Day-5 RMSEs of **0.02236 / 0.04049 / 0.02380 g/L**. This single-seed scaling
check did **not** show monotonically improving error (log-log slope +0.05096).
The observation is retained without selecting a favorable rerun. It does not
establish a few-shot scaling law; more seeds and controlled optimization budgets
would be needed for that claim.

Final verification: **10 passed in 5.20 seconds**. The pytest suite covers the four mandatory checks plus whole-batch split
protection, train-only scaling, data reproducibility, weight/config tampering,
float64 validation, failed-solver handling, and repeatable training through
frozen evaluation. Bitwise replay is checked with nonzero neural residuals,
reversed batch ordering, and an actually trained/reloaded checkpoint.

Generated outputs are in `artifacts/main/` and `artifacts/evaluation/` (ignored
by git to avoid committing disposable runs). The selected weights SHA-256 is
`9bbd0a570e1756f7f2a4520e6e3dd890e57b4159707ce1e989067b934c0aba50`.
These results validate this synthetic experiment only; they do not establish
GMP compliance, cross-platform bitwise replay, or causal attribution in real LIMS data.
