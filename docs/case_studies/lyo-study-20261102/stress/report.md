# Supplementary freeze-drying factorial challenge

Post hoc motivated by limited event support in the primary study; this complete grid was prospectively frozen before its numerical outcomes. Its results are separate from the primary study and agent campaign. No AI calls or manufacturing actions were performed.

The 32 cases cross shelf temperatures −28/−24/−20/−16 °C, loads 4,000/11,000 vials, capacities 0.40/1.49 kg/h, and hidden receiving Kv multipliers 1/1.25. All use a constant shelf setpoint from time zero, 8 Pa prescribed pressure, 90 h horizon, and equilibrium initialization. These are idealized conditions, not realistic startup sequences.

B and C receive the same nominal public characterization and no receiving observations. The effective Kv multiplier is hidden and cannot be identified from these inputs. Rp and capacity multipliers equal one. Both models use the existing pretransfer KEEP predictor without fitting and the same applicability gate.

| Model | Planned | Numerical failures | Completion eligible | Predicted | Coverage | Completion MAE (h) |
| --- | --- | --- | --- | --- | --- | --- |
| B | 32 | 0 | 12 | 12 | 1.0000 | 2.2412 |
| C | 32 | 0 | 12 | 12 | 1.0000 | 2.3132 |

## Thermal warnings

| Model | Truth positive | Truth negative | Truth censored | TP | TN | FP | FN | Abstain | Censored | Model failure | Reference failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B | 1 | 11 | 20 | 0 | 11 | 0 | 1 | 0 | 20 | 0 | 0 |
| C | 1 | 11 | 20 | 0 | 11 | 0 | 1 | 0 | 20 | 0 | 0 |

## Capacity warnings

| Model | Truth positive | Truth negative | Truth censored | TP | TN | FP | FN | Abstain | Censored | Model failure | Reference failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B | 20 | 12 | 0 | 18 | 12 | 0 | 2 | 0 | 0 | 0 | 0 |
| C | 20 | 12 | 0 | 18 | 12 | 0 | 2 | 0 | 0 | 0 | 0 |

## Interpretation

Completion error is conditional on a reference-valid completed trajectory and a numerical prediction; coverage divides predictions by all reference-eligible cases, including model failures. Thermal outcomes at or after capacity overload are censored. Reference failures remain separate from negative outcomes. Diagnostic post-overload trajectories are retained as raw evidence, not physical forecast targets.

The evaluator and models share constitutive laws. Its invented pressure response cannot validate post-overload physics. This challenge expands behavioral coverage; it does not establish manufacturing prevalence, independent physical validation, agent benefit, general superiority, or process effectiveness. Hidden Kv shifts can cause forecast misses through unavailable characterization. No tuning follows these results. No statistical significance or manufacturing risk probability is inferred.

Reference numerical failures: 0/32. Per-case results include errors, predictions and scores. Full reference curves are in `evaluator/`; `case-plan.json` contains every frozen input and evaluator mechanism. `summary.json` also separates the two hidden-Kv strata.
