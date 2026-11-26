# LinkedIn draft

We compared two freeze-drying model approaches and AI agents with different tool access in a reproducible synthetic study.

Exploratory synthetic comparison with shared constitutive physics. Reference completion and subsequent thermal outcomes are censored after equipment capacity exceedance. These are not plant measurements or plant validation.

Protocol scope: Post-hoc motivated, prospectively frozen same-case subset; joint budget and submission-policy change; not independent confirmation. Recorded completion policy: Final eighth provider turn exposes only submit_decision with forced function choice, identically across all three arms; earlier submission allowed; eight host calls include submission.

AI A receives no prebuilt physical model and can derive its own simulator in Python. B and C receive prepared legacy and population models, respectively.

Forecast results:
- Model B (legacy): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 0.15 h on those predictions; 6 feasible and 0 unsafe synthetic selections; 0 characterize choices.
- Model C (population): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 0.25 h on those predictions; 6 feasible and 0 unsafe synthetic selections; 0 characterize choices.
- AI A (no prebuilt model): 4/6 attempts completed; 4/6 eligible completion forecasts; MAE 53.99 h on those predictions; 3 feasible and 0 unsafe synthetic selections; 1 characterize choices.
- AI B (legacy tool): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 0.16 h on those predictions; 6 feasible and 0 unsafe synthetic selections; 0 characterize choices.
- AI C (population tool): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 0.25 h on those predictions; 6 feasible and 0 unsafe synthetic selections; 0 characterize choices.

Pretransfer results:
- Model B (legacy): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 1.75 h on those predictions; 5 feasible and 1 unsafe synthetic selections; 0 characterize choices.
- Model C (population): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 1.81 h on those predictions; 5 feasible and 1 unsafe synthetic selections; 0 characterize choices.
- AI A (no prebuilt model): 4/6 attempts completed; 4/6 eligible completion forecasts; MAE 9.05 h on those predictions; 3 feasible and 1 unsafe synthetic selections; 0 characterize choices.
- AI B (legacy tool): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 1.75 h on those predictions; 5 feasible and 1 unsafe synthetic selections; 0 characterize choices.
- AI C (population tool): 6/6 attempts completed; 6/6 eligible completion forecasts; MAE 1.81 h on those predictions; 5 feasible and 1 unsafe synthetic selections; 0 characterize choices.

The useful distinction is between producing a forecast and knowing when the model no longer applies. We report prediction coverage, warning abstentions, action feasibility and execution failures alongside error. A model can have a smaller error on fewer cases without being more useful overall. Lower completion MAE does not establish an action-selection gain. The observed comparisons above must be read separately for error, coverage and feasibility.

Budget-exhausted attempts remain in the results. A can spend its limited calls constructing a simulator; any benefit from a prepared tool is conditional on the recorded budget of 8 model calls and 240 seconds per attempt. A benchmark throughput score gives zero credit to failed or unsafe choices and abstention; it is not real plant throughput.

This does not demonstrate plant validation, real failure prevention, or realized manufacturing gains. The next evidence would need independent experimental or plant data with a defined intended use. The full local report includes per-case results, model-only comparisons and the limits of this experiment.
