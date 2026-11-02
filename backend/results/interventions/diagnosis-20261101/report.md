# Retained-failure and real CHO diagnosis

Recorded model-informed infeasible operating choices: **26**. This is the red baseline; old decisions are unchanged.

CHO model outputs were recomputed and matched their frozen predictions. Previously inspected cases remain development data.

| Method | Target | MAE | Mean signed error |
|---|---|---:|---:|
| mechanistic | viable_cells_million_per_ml | 1.7698 | -1.6170 |
| mechanistic | glucose_g_per_l | 0.7368 | 0.6199 |
| last_value | viable_cells_million_per_ml | 5.4482 | -5.4482 |
| last_value | glucose_g_per_l | 3.3392 | 3.3392 |
| linear_prefix | viable_cells_million_per_ml | 3.0386 | -3.0386 |
| linear_prefix | glucose_g_per_l | 2.4427 | 2.4091 |

Units: million viable cells/mL and g glucose/L. No causal attribution to a particular omitted mechanism is established.
The prior negative agent A/B result is retained. Numerical consistency does not qualify this model as a decision authority.
