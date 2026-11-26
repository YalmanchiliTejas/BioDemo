# Chemical reactor learning run

Synthetic inputs and measurements; no customer or experimental validation.

| Scenario | Status | Yield (%) | Impurity (%) | Peak returned T (°C) |
|---|---|---:|---:|---:|
| Donor | completed | 90.72 | 5.96 | 39.68 |
| Receiver | stopped_or_failed | withheld | withheld | 71.85 |
| cooler_coolant_hypothesis | stopped_or_failed | withheld | withheld | 71.85 |
| improved_U_characterization_hypothesis | completed | 88.29 | 11.70 | 67.15 |
| alternate_receiver_geometry_hypothesis | completed | 90.72 | 5.96 | 39.68 |

Source U fit: 349.98 W/(m² K).
Training RMSE: 0.0550 K; later holdout RMSE: 0.0990 K.
The synthetic truth uses U=350 W/(m² K). Recovery tests code consistency, not real-world identifiability or prediction accuracy.

Next: replace assumptions with independently reviewed kinetics, calorimetry, heat-transfer measurements and product/impurity assays.
No proposed utility or U change is a qualified manufacturing recommendation.
