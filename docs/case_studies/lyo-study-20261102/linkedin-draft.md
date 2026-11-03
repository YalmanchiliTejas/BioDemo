# LinkedIn draft

We compared two freeze-drying model approaches and AI agents with different tool access in a reproducible synthetic study.

Exploratory synthetic comparison with shared constitutive physics. Reference completion and subsequent thermal outcomes are censored after equipment capacity exceedance. These are not plant measurements or plant validation.



AI A receives no prebuilt physical model and can derive its own simulator in Python. B and C receive prepared legacy and population models, respectively.

Forecast results:
- Model B (legacy): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 0.37 h on those predictions; 22 feasible and 2 unsafe synthetic selections; 0 characterize choices.
- Model C (population): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 0.45 h on those predictions; 23 feasible and 1 unsafe synthetic selections; 0 characterize choices.
- AI A (no prebuilt model): 1/24 attempts completed; 1/24 eligible completion forecasts; MAE 7.80 h on those predictions; 1 feasible and 0 unsafe synthetic selections; 0 characterize choices.
- AI B (legacy tool): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 0.37 h on those predictions; 22 feasible and 2 unsafe synthetic selections; 0 characterize choices.
- AI C (population tool): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 0.44 h on those predictions; 24 feasible and 0 unsafe synthetic selections; 0 characterize choices.

Pretransfer results:
- Model B (legacy): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 2.57 h on those predictions; 19 feasible and 5 unsafe synthetic selections; 0 characterize choices.
- Model C (population): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 1.86 h on those predictions; 19 feasible and 5 unsafe synthetic selections; 0 characterize choices.
- AI A (no prebuilt model): 3/24 attempts completed; 3/24 eligible completion forecasts; MAE 51.09 h on those predictions; 1 feasible and 0 unsafe synthetic selections; 2 characterize choices.
- AI B (legacy tool): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 2.57 h on those predictions; 20 feasible and 4 unsafe synthetic selections; 0 characterize choices.
- AI C (population tool): 24/24 attempts completed; 24/24 eligible completion forecasts; MAE 1.86 h on those predictions; 20 feasible and 3 unsafe synthetic selections; 1 characterize choices.

The useful distinction is between producing a forecast and knowing when the model no longer applies. We report prediction coverage, warning abstentions, action feasibility and execution failures alongside error. A model can have a smaller error on fewer cases without being more useful overall. Lower completion MAE does not establish an action-selection gain. The observed comparisons above must be read separately for error, coverage and feasibility.

Budget-exhausted attempts remain in the results. A can spend its limited calls constructing a simulator; any benefit from a prepared tool is conditional on the recorded budget of 4 model calls and 120 seconds per attempt. A benchmark throughput score gives zero credit to failed or unsafe choices and abstention; it is not real plant throughput.

This does not demonstrate plant validation, real failure prevention, or realized manufacturing gains. The next evidence would need independent experimental or plant data with a defined intended use. The full local report includes per-case results, model-only comparisons and the limits of this experiment.
