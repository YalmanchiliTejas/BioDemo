# Decision evaluation: rationale and boundaries

The job is to test the user's product hypothesis: does adding a mechanistic model improve the same agent's outcomes and decisions? The present executable study tests a bounded simulated version of that hypothesis. It does not require a famous historical failure or a fabricated industrial loss figure.

## What changed and what did not

The retained October intervention results exposed 26 model-informed operating recommendations whose central predictions were infeasible. Both arms now receive the same explicit priority: respect the assumed oxygen constraint, stop when no action is supported as feasible, then optimize inventory. This is prompt/policy clarification; the evaluator does not override the agent's submitted choice. Consequently any residual violations remain failures. Comparing this cohort with October does not isolate the causal effect of the prompt change; the causal A/B question is model access within the new cohort.

The source-calibrated mechanistic model, its parameter-fitting method, sensitivity set and action menu are unchanged. Lossless dictionary/column tables replace repeated-key observation objects in both agent packets. Exact row round trips were checked. A source-model wrapper decodes the same representation; neither arm loses measurements.

The simple alternative was only rerunning the old cases after a prompt edit. Instead, the study uses new seeded cases and includes a declared continuing-transfer-loss mechanism absent from the predictor. This tests one limited form of mismatch, not arbitrary unknown plant physics.

## Frozen final study

- Protocol: `backend/results/interventions/decision-followup-final-20261101/protocol.json`.
- 24 scenarios; 48 planned GLM-5.3 agent sessions; one session per arm per scenario. Three disturbance strata have eight scenarios each, split evenly between step-only and continued-decay conditions.
- The same Modal endpoint, GLM model, reasoning setting, evidence, tools other than the mechanistic tool, and resource ceilings apply to both arms. Arm order is counterbalanced. A conventional finite-grid model selector is a separate diagnostic comparator.
- Source fitting uses only completed source observations. Receiving observations honor their collection/availability clocks. The tool does not receive true receiving parameters or future outcomes. Actions are fixed before hidden receiving outcomes are replayed.
- Primary: paired difference in correct constrained decisions. A feasible operating action is correct when available; stopping is correct when no menu action is feasible. Failed agent submissions count incorrect.
- Secondary: violating operations, correct/unnecessary stops, inventory, explicitly defined constraint-feasible inventory, completion and model-only comparison. Inventory is not product quality or released yield.
- Paired descriptive bootstrap resamples scenarios. Repeated calls are not independent experiments. The 24 scenarios are conditional on one shared source calibration, equation family and synthetic parameter distribution; the bootstrap does not incorporate uncertainty across different source models or real plants.
- The frozen support rule requires a positive lower descriptive95% bound on primary benefit, no increase in violating-operation rate, complete scenario adjudication and intact evidence/source checks. This is not a familywise confirmatory manufacturing test.

## Cost-pilot exclusion

The initially frozen 48-scenario/96-session study was stopped after observed token costs projected beyond its $10 admission cap. The decision and new cohort size/seeds were recorded before inspecting comparative scores. That pilot is retained at `backend/results/interventions/decision-followup-20261101-v2`, not pooled into the final analysis. Startup/preflight attempts with zero paid calls are also retained. The final study has its own $10 gate. Unsettled pilot requests retain full worst-case reservations; no zero SDK price is interpreted as free usage.

## Real-data diagnosis

The old CHO model forecasts were independently recomputed from the frozen observation packets and reproduced. On these already inspected cultures the model systematically underpredicted viable cells and overpredicted glucose on average. It beat elementary last-value/linear-prefix numerical baselines, but the prior actual-agent A/B result remained worse with model access. That distinction is retained: model-only behavior is not the same experiment as agent-with-model behavior.

The current evidence does not uniquely identify which omitted biological or operating mechanism explains the bias. No new model was selected on those test outcomes and relabeled externally validated. The CHO model is not admitted as a qualified real manufacturing intervention authority. Cached packet reproduction does not constitute a fresh re-audit of the archived original workbooks.

## Engineering checks and product principles

Local regression checks cover actual recorded policy failures, evidence-table reversibility, future-data rejection, backward-compatible simulator behavior, stopping/feasibility accounting, and provider-response model/usage parsing. An additional native-versus-independent-solver check covers continued transfer decay. Passing these checks establishes bounded implementation consistency, not biological truth.

All four governing pillars apply: reuse existing authorized evidence (Start); preserve versions, uncertainty, failed attempts and model identity (Trust); evaluate specific reviewable actions and their distinct outcomes (Act); retain source-system records and human authorization for manufacturing operations (Adopt). No equipment, production account, release decision, email delivery or public deployment is changed by this study.

## Interpretation

A positive result can support model-assisted GLM decisions within this declared simulator setting. It cannot erase the negative CHO finding, prove additional agent value beyond conventional modeling, demonstrate actual customer effort savings, establish scale-up across geometries/sites, or substantiate an avoided-loss claim. A negative/inconclusive result must remain such in the report, email draft and LinkedIn draft.
