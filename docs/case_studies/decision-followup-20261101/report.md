# GLM-5.3 + mechanistic model: fresh constrained-decision evaluation

**Verdict: supports the prespecified simulated decision hypothesis.**

The same Modal GLM-5.3 agent receives identical measured-in-simulation evidence. Only B has the source-calibrated mechanistic tool. Both use the same feasibility-first policy. No submitted action is silently overridden.

24 prespecified independent simulated scenarios; 48 planned agent sessions. 24 scenarios have complete menu adjudication. Failures are retained. Half include continuing oxygen-transfer decay absent from the step-only prediction model.

| Outcome | Agent alone A | Agent + model B | Conventional model-only selector |
|---|---:|---:|---:|
| Completed decisions | 24 | 24 | 24 |
| Correct constrained decisions | 10 | 23 | 23 |
| Constraint-violating operating decisions | 14 | 1 | 1 |
| Correct stops | 0 | 12 | 12 |
| Unnecessary stops | 0 | 0 | 0 |
| Mean simulated product inventory (kg) | 323.451 | 266.482 | 277.593 |
| Mean constraint-feasible inventory (kg) | 219.213 | 255.628 | 266.739 |

Correct means feasible operation when available, or stopping when no menu plan is feasible. Failed submissions count incorrect. Constraint-feasible inventory counts zero for a violation or stop; it is not measured product quality or released yield.

## Paired differences, B minus A

| Metric | Mean | Descriptive 95% interval |
|---|---:|---|
| correct | 0.5417 | [0.3333, 0.7500] |
| violating_operation | -0.5417 | [-0.7500, -0.3333] |
| mass_kg | -56.9688 | [-105.6728, -4.4053] |
| feasible_mass_kg | 36.4151 | [7.3190, 71.2002] |

Intervals resample scenarios, not calls. They are unadjusted exploratory estimates, not calibrated physical confidence or industry-wide reliability.

## Prespecified subgroups

| Group | Scenarios | Correct A | Correct B | Violating A | Violating B |
|---|---:|---:|---:|---:|---:|
| normal | 8 | 8 | 8 | 0 | 0 |
| moderate_loss | 8 | 2 | 7 | 6 | 1 |
| severe_loss | 8 | 0 | 8 | 8 | 0 |
| step_only | 12 | 6 | 12 | 6 | 0 |
| continued_decay | 12 | 4 | 11 | 8 | 1 |

## Provenance, cost and limitations

- Endpoint-reported models: zai-org/GLM-5.3. Configured model: modal/zai-org/GLM-5.3.
- Forwarded model requests: 98; usage settled: 98; denied: 0.
- Token-rate estimate plus unresolved full reservations: $5.6351; admission cap $10.00. This is not a verified invoice or account-wide spending total.
- Known central-model-infeasible operating selections by B: 0. Remaining failures are not hidden.
- Predictor and evaluator share a mechanistic equation family; parameter mismatch and added transfer decay do not establish independent biological validity.
- Source fitting was reused unchanged. The earlier real CHO agent comparison remains negative; the CHO model was not promoted to a qualified intervention model.
- Earlier trials informed policy development. The new scenario seeds and analysis were frozen before inference; this remains an exploratory synthetic follow-up.
- A model-only selector is a diagnostic comparator, not a measured human workflow. No engineer-time savings or manufacturing outcomes were measured.
- The full 230-hour PenSim process remains unqualified; this study ends at 96 hours.

Machine-readable analysis, every failed session, packet hashes, actual SDK model events and request-admission ledger are retained with the run.
