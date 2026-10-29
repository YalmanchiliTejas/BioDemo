# Operating-challenges execution record

28 October 2026. This implements the selected experiment families in a separate benchmark, following the user's request for a new report with model updates deferred. It does not delete or selectively hide results of previous experiments.

Job: make a reviewable comparison of the same AI with and without a supplied physics tool for transient forecasts, constrained operating-plan choices, and receiving-recipe adaptation. Reuse the current source/runtime/measurement boundaries; make each committed action's consequences inspectable; do not alter production workflows or manufacturing records. Report computational effort, completions and error/decision measures; human or manufacturing savings are unmeasured.

The simpler alternative was repeating the earlier four-action endpoint-only experiment. The selected extension adds six forecast targets and multiple larger plans, explicit operating/resource limits, and an abstain choice. A more ambitious alternative would add missing physics or repair the model's qualified domain; that is deferred under the user's instruction. The extension changes benchmark inputs, presentation, state initialization and scoring, not differential equations, kinetic parameters, source controllers, solver corrections or the earlier fitted calibration values. Source hashes are checked before and after.

- Fresh simulated cases: seeds7001–7048 for each process, balanced deterministic scenario cycling, no performance-dependent selection or replacement. Every fourth case is an ordinary control. Three tasks and two fresh AI sessions per arm yield288 task packets and1,152 planned attempts.
- Models frozen: physical implementations and earlier calibration values are recorded in dataset/protocol.json. The calibration is deterministically the first prior prediction case in catalogue order for each process. It is not refit for the new case. This deliberately limits the claim to the behavior of these frozen configurations. Raw source-reference history is available identically to both agents.
- PenSim: scenarios change sugar-feed/air plans after60h; forecasts are requested at64,72,96h. Larger options follow the development audit. Low-air/rich-feed combinations that already triggered flooring in development are not added to the grid. Every selected test case and every failed/unqualified grid action is retained; qualified KEEP is required to have scorable forecast truth.
- SMPL: source/receiving inoculum state is explicitly shared and observable; changes to initial observed states are scenario inputs, not coefficient fitting. Flows remain balanced. Forecasts are at8,12,24h; decisions start6h and transfer plans start0h. Fixed per-case nutrient/pump/state requirements make feasibility explicit. This remains optimistic fixed-geometry dynamics, with saturated nutrient terms and possible easy action rankings.
- Limits describe permitted plans and resource/state requirements. They do not add an actuator-saturation law. A KEEP forecast violating these requirements is a counterfactual plan forecast, not measured production from an executable or approved plan. The report must explain that distinction and call transfer a simulated adaptation proxy.
- Physics tool: fresh credential-free host worker, nominal PenSim future disturbances disabled; no receiving future, actual seed or outcome ranking. Tool predictions checked against frozen nominal records. Both arms receive the same common observations, source-reference observations, schedules, bounds, actions, units, numerical tool and inference ceilings. Hidden-file/network/simulator-import probes apply.
- Scoring: forecasts always target KEEP, even when another action is chosen. All six variables/times are retained. Decision scoring respects resource/state feasibility and raw model-domain qualification. Apparent product gains with oxygen floors cannot count as successful actions. Correct abstention is relative to the finite tested grid and produces no product; it is not proof that every possible process plan is infeasible.
- Analysis: fixed useful-effect thresholds and case count recorded before generation. The detailed analysis addendum was recorded after inference started but before inspection of new A/B scores. This is exploratory and not independently preregistered or prospectively power-qualified. No extension until favorable. Paired bootstrap keeps AI repetitions inside case clusters; repeated synthetic regimes do not become new biological experiments.

Protocol/inputs and complete submissions: backend/results/external-simulators/challenges-20261028. Source, numerical clock and observation isolation checks passed before inference; zero initial KEEP coverage failures among288 packets. A separate report will use only the new set in its result tables, retain all its outcomes, and link historical studies without asserting that new simulation evidence replaces earlier empirical findings.

Reproduce from the repository root with the isolated Python3.11 environment and pinned upstream checkouts:

```sh
PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.challenges \
  --output /private/tmp/NEW-CHALLENGE-DATASET \
  --prior-dataset backend/results/external-simulators/improvements-20261027/fresh-dataset-v2 --cases 48

PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.challenge_verify \
  --dataset /private/tmp/NEW-CHALLENGE-DATASET --output /private/tmp/NEW-CHALLENGE-PREFLIGHT.json

PYTHONPATH=backend /private/tmp/biodemo-external-sim-env/bin/python -m benchmarks.external_simulators.run_agents \
  --dataset /private/tmp/NEW-CHALLENGE-DATASET --output /private/tmp/NEW-CHALLENGE-AGENTS --workers 8 --repeats 2
```

Preserve the exact frozen analysis-plan.json beside the agent directory before analyzing. Use fresh destinations for reproduction; archived prior datasets can be restored through their asset descriptors when necessary. No earlier run needs to be overwritten.
