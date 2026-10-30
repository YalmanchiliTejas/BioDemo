# Published oxygen correction: retrospective summary replay

One Sulfolobus acidocaldarius case from Rastadter et al.(2023), DOI10.3389/fbioe.2023.1160012. This is summary evidence from an earlier physical experiment, not a new laboratory intervention or a raw-data causal replay. The prior exposure/pretraining risk prevents calling it an untouched blinded test.

## Evidence sequence

1. Published source characterization:2L ring sparger355rpm,0.51L/min, water at75C, kLa32.6/h. Micro sparger at the same settings:38.8/h.
2. Published cultivation problem:DO below20% and oxygen supplementation needed. No raw DO curve, OUR or certified equipment ratings in the public packet.
3. Both agents received those summaries and the conditional355/500rpm options. The published500rpm corrective result remained outside the packet until commitment. B had access to a conditional power-law sensitivity tool; its exponents were declared assumptions, not calibrated from the withheld correction.

## Actual recommendations

| Approach | Recommendation | Physics tool called? |
|---|---|---|
| AI alone | characterize_before_action | No |
| AI + physics available | characterize_before_action | No |

Both agents recommended broth characterization and equipment review before changing operation. Neither invoked the physics tool; neither requested an invented assay. This case therefore shows no observed added value from model access. Their deferrals are not scored as experimentally wrong simply because a published conditional adjustment later worked.

## Published correction revealed after commitment

The authors increased ring-sparger agitation355→500rpm at the same airflow. Water characterization kLa increased32.6→38.8/h (approximately19%). Extra oxygen could be omitted, with an almost6percentage-point viability improvement reported in the text. Those are published summaries, not new agent-executed outcomes. Broth kLa, raw trajectories, replicate-level correction data and matched product mass remain unavailable.

## Interpretation

The system can produce a reviewable recommendation while recognizing missing physical inputs. This small reconstruction does not establish forecasting accuracy, agent superiority, safe operating ratings, product-mass improvement or a newly prevented failed batch. It does not validate PenSim biology for Sulfolobus.

The report preserves both recommendations rather than choosing an example where physics appears favorable. A conditional forward calculation would use assumed exponents and author-calculated power, not experimentally identified broth parameters.

Source: [Rastadter et al.(2023)](https://doi.org/10.3389/fbioe.2023.1160012). Underlying locally acquired source manifest: docs/research/fermentation/sulfolobus/source-manifest.json. Complete frozen packets, tool events and submissions: backend/results/interventions/physical-oxygen-summary-20261029/.

## AI alone rationale

The packet only provides water kLa characterization (Rastadter2023 Table2: 32.6–38.8 /h at 355 rpm, 0.51 L/min, 75 °C) and a qualitative observation of oxygen limitation (section3.1: DO below 20%, oxygen supplementation required). Water kLa is explicitly not validated broth kLa, and OUR, broth kLa response, rated rpm/torque limits, raw DO/viability trajectories, and matched product mass are all missing. Raising to 500 rpm would raise calculated specific power from 0.25 to 0.63 kW/m3 (~2.5x) for an assumed power-law kLa gain whose exponents are not fitted to any broth data; mechanical limits and shear effects on the culture are unverifiable from the public record. A conditional adjustment to 500 rpm or continued 355 rpm operation cannot be justified without broth kLa/OUR characterization or an equipment review. Therefore the defensible next action is characterization before any change; no unique validated setting can be claimed.

Uncertainty: High: no broth kLa, OUR, mechanical ratings, or DO trajectories exist in the public packet, so neither 355 nor 500 rpm can be shown adequate or safe; power-law sensitivity exponents are assumed, not fitted, so the projected benefit of 500 rpm is unvalidated. This is a retrospective summary reconstruction only — no new assay, receiving trajectory, product mass, or equipment execution is claimed.

## AI + physics rationale

Only water kLa at 75 °C is available (32.6/38.8 h⁻¹, Table2) and is explicitly not validated broth kLa. The culture shows oxygen limitation (DO <20%, section3.1), but OUR, broth kLa response, equipment rated rpm/torque, and matched product mass are missing. A 500 rpm conditional action would more than double calculated power (0.25 → 0.63 kW/m³) with unquantified shear/viability risk and no validated benefit; keeping 355 rpm leaves documented limitation unaddressed. Broth characterization plus equipment review is needed before any rpm change. This is retrospective summary reconstruction; no new experiment is performed and no unique validated operating point is claimed.

Uncertainty: High: no broth kLa, OUR, equipment rating, or raw DO trajectory in the public record; power values are author-calculated; the withheld corrective outcome cannot be used to fit or validate any action.
