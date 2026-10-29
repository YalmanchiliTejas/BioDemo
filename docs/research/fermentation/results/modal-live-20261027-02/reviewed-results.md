# Hosted Modal run: results and engineering interpretation

Both cases executed through the existing Prime SDK with `modal/zai-org/GLM-5.3`. Authentication succeeded. The agent invoked the registered deterministic fermentation tool and saved source-linked investigation reports. No manufacturing equipment was controlled.

These were exploratory research runs using three reviewed calibration-side files per case. They do not demonstrate autonomous extraction from original publications or qualify as blinded agent-uplift trials.

## Execution and verification

| Case | Agent wall time | Recorded solver calls | Staged citation checks | Saved report |
|---|---:|---:|---:|---|
| Sulfolobus | 552.5 s / 9.2 min | 3 | 126 passed | Partial investigation; incomplete |
| Pichia | 593.9 s / 9.9 min | 5 | 69 passed | Complete for available evidence; independent scientific review pending |

All eight saved solver calls were replayed using their exact recorded assumptions and the frozen implementation. Every result matched. Source and implementation hashes matched. Citation checks concern staged source bytes and locations; they do not establish the correctness of every interpretation. The generic report ledger verified **zero calculated metrics**, because the staged numeric inputs were ingested as text and model outputs were not connected to that ledger. The separate computational replay establishes reproducibility of those eight tool outputs, not full report verification.

Root-session telemetry records 127 and 111 model calls respectively. Provider billing and complete child-session cost coverage are unavailable. These call counts and runtimes show substantial orchestration/reporting overhead; no efficiency improvement is established. The matched physics-only API executions took about 0.018 and 0.016 seconds, excluding unobserved human input preparation. Comparing machine wall times alone cannot establish an engineering-time advantage.

The first two-minute attempts both timed out. Their traces showed that the shared harness reserved 90 seconds for finalization, leaving only about 30 seconds for investigation. Those failures remain in `../modal-live-20261027-01/`. The successful research attempts used a ten-minute cap per case and the unchanged 48-call host-tool budget. The numerical solver and experimental validation inputs were not changed to improve results.

## Sulfolobus: source-only knowledge does not uniquely determine the receiving recipe

The evaluator applied the source-fitted correlation at the published receiving settings, without supplying receiving answers to the agent:

| Receiver | Published setting | Predicted kLa | Measured kLa | Relative error |
|---|---|---:|---:|---:|
| 20 L | 285 rpm; 5.1 L/min | 35.53 h⁻¹ | 40.5 h⁻¹ | −12.27% |
| 200 L | 117 rpm; 37.5 L/min | 25.41 h⁻¹ | 41.1 h⁻¹ | −38.17% |

These are water-characterization results at 75°C, not validated broth oxygen-capacity or biological predictions. Source: [Rastädter et al., Methods 2.1.1 and Table 2](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2023.1160012/full).

The model fits two rounded source points at the same airflow. It cannot identify the gas-flow exponent or statistical prediction uncertainty. Receiver impeller count, diameter and sparger response challenge constant-power-number and simple specific-aeration scaling. Copying source rpm does not preserve power per volume; oxygen capacity also needs solubility, absolute DO and oxygen uptake.

The nominal search selects 275 rpm / 7 L/min at 20 L and 150 rpm / 70 L/min at 200 L. Their predicted kLa values are 40.80 and 39.95 h⁻¹. These are characterization candidates, not established recommendations: neither survives the declared sensitivity range, and certified equipment limits are missing. The receiving prediction errors undermine adopting these settings directly. The agent appropriately called for receiving-vessel characterization instead of certifying a recipe.

No 200 L viability result was invented. The paper explicitly states that viability was not measured at that scale.

## Pichia: a conditional cost advantage, with an important feasibility check

At constant temperature and gas composition, increasing air pressure from 50 to 100 kPa gauge raises calculated oxygen saturation by **33.04%**, using 101.325 kPa ambient. This comparison is air versus air; it is not a 33% advantage over oxygen-enriched gas.

Under the recorded assumptions:

| Strategy | Gauge pressure | Calculated OTR | Compression power | Partial oxygen-delivery cost |
|---|---:|---:|---:|---:|
| Supplemental oxygen | 50 kPa | 157.96 mg/L/h | 0.694 kW | $0.4833/h |
| Pressurized air | 100 kPa | 178.63 mg/L/h | 1.188 kW | $0.1425/h |

Inputs include 36 Nm³/h air, 2 Nm³/h supplemental oxygen for the first strategy, compressor efficiency 0.65, electricity $0.12/kWh, oxygen $0.20/Nm³, assumed kLa 20 h⁻¹, broth solubility factor 0.7, DO 1.5 mg/L and OUR 50 mg/L/h. Gas-flow reference conditions and actual broth characterization remain unverified.

The modeled difference is **$0.3407/h, or $40.89 over a common 120-hour basis**. This is not measured commercial savings or complete batch cost. It excludes cooling, agitation energy, occupancy, capital, downstream recovery and unprovided methanol consumption. The break-even oxygen price is approximately $0.0296/Nm³ under these assumptions.

The agent tested increased electricity price and increased oxygen demand. At $0.30/kWh the modeled advantage falls to $30.22 per 120 hours. At assumed OUR 180 mg/L/h, pressurized air has a **−1.37 mg/L/h oxygen-capacity margin**; the nominally cheaper strategy becomes oxygen-limited. The baseline assumptions also predict that ordinary air at normal pressure already meets OUR, whereas the published direct comparison required supplemental oxygen. This supports the conclusion that the assumed characterization does not calibrate the actual high-density process.

Published production outcomes remain distinct from pressure predictions. The 100 L and 1,000 L summaries are 600±20 and 900±30 mg/L; the constant 10 L endpoint comparator is 640 mg/L, with errors +6.67% and −28.89%. This is an empirical comparator, not mechanistic productivity validation. Feeding, DO and duration differ; the direct oxygen-versus-pressure comparison is at 30 L. Source: [Liu et al., Results and Tables 1–2](https://pmc.ncbi.nlm.nih.gov/articles/PMC4726300/).

## Review findings: do not accept the raw agent narrative uncritically

Targeted review identified four interpretation issues; this is not an exhaustive unsupported-claim score:

1. **Sulfolobus reference basis:** the agent overstated a conflict between the micro-sparger target and ring-sparger calibration points. Table 2 legitimately contains both. The complete micro-sparger record should accompany the target, but the experiment itself is not contradictory.
2. **Unused Sulfolobus pressure default:** the agent gave significance to a pressure setting that its selected adapter does not consume.
3. **Unused Pichia receiver defaults:** the agent treated shared-schema 20 L / rpm / vvm defaults as an actual receiving-vessel specification. Those fields belong to the Sulfolobus calculation and are not consumed by the Pichia pressure-cost adapter.
4. **Overstated airflow robustness:** one Pichia test changed airflow, supplemental oxygen and pressure together and returned zero cost difference. It does not establish a positive cost ranking robust to airflow basis.

The most useful findings are therefore the defensible physical limitations and conditional sensitivity results. The reports need these corrections before engineering acceptance. Structural completion and source-location checks are not scientific approval.

## What this demonstrates—and what remains

Hosted Prime can retrieve the prepared evidence, invoke the same physical model, explore scenarios, identify missing characterization and persist reviewable reports. Its useful contributions include identifying unidentifiable scale-up parameters and showing that oxygen-cost and oxygen-feasibility rankings can diverge.

Incremental engineering-time savings, autonomous raw-publication extraction accuracy, experimental elimination and blinded agent uplift remain unmeasured. The runs also exposed real product work: provide family-specific applicable inputs, connect typed parameters and deterministic model receipts to the existing report-verification ledger, and reduce schema-discovery/report-assembly overhead. Receiver characterization and certified equipment ratings remain experimental requirements.

Original artifacts: [results.json](results.json), [freeze-manifest.json](freeze-manifest.json), and [computational-review.json](computational-review.json). These retain actual outputs, assumptions, hashes, review flags, failed-run context and coverage limitations.
