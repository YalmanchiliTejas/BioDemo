# SMPL upstream: a defensible partial-observation benchmark

Primary-source audit, 2026-10-29. This is a proposed synthetic measurement contract, not evidence that all SMPL states are physically measured or that the model predicts a manufacturing site accurately. No model or harness changes were made for this note.

## Job, alternatives and evidence boundary

The job is to forecast and compare bounded upstream mAb operating plans using the information a process team could plausibly have: operating records, limited online signals, and intermittent laboratory assays. Apply [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md) jointly: reuse ordinary data without demanding new sensors (Start), distinguish observation from estimation (Trust), connect plans to measurable external output and constraints (Act), and retain systems of record and human authorization (Adopt). Useful observable measures are forecast error by measured target, inventory violations, waiting time for assays, extra assay requests, and decision regret; no real-world effort reduction has been measured here.

The simple option is an unchanged SMPL process with an explicit observation mask, sparse assays and declared uncertainty. The ambitious alternative is a validated observer combining calibrated Raman/capacitance, sampling-port characterization and uncertain flow delivery. The ambitious option requires calibration evidence and hardware absent from this repository's SMPL experiment. Start with the simple option and publish its assumptions; do not hide a full-state restart behind an apparently sparse agent packet.

## Inspected model and its limits

The executed source is [SMPL revision c816917](https://github.com/smpl-env/smpl/tree/c816917eebfde59d525e325b56d16db07e499531), specifically [UpModelHelper](https://github.com/smpl-env/smpl/blob/c816917eebfde59d525e325b56d16db07e499531/smpl/envs/helpers/mab_helpers.py). It has **17 states**: seven reactor concentrations, reactor volume, seven separator concentrations, separator volume, and reactor temperature. The seven commands are four flows, inlet glucose/glutamine concentrations, and coolant temperature. It has no DO, oxygen-transfer, pH, spatial mixing or product-quality state. A physically measured DO or pH signal cannot be added as if this helper predicts it.

The [original SMPL paper](https://arxiv.org/html/2206.08851), Appendix A.3, describes a mechanistic continuous reactor/separator model and an hourly controller interval. That is simulation/control sampling, not validation of an hourly 17-channel sensor panel. The paper describes a 15-state formulation, a glutamine constant and a pH-dependent production expression that differ from this pinned helper's implemented state count/constant-production structure. Preserve the pinned code as the executable contract and disclose paper/code differences rather than silently replacing its equations. The public [environment implementation](https://github.com/smpl-env/smpl/blob/c816917eebfde59d525e325b56d16db07e499531/smpl/envs/mabenv.py) exposes a full simulated vector through its observation space; this is an RL interface, not a list of experimentally measured states.

| State indices, zero-based | Meaning / native units | Defensible information status |
|---|---|---|
| 0, 1 | Reactor viable and total cells, cells/L | Offline counting/viability panel. VCD and viability can imply total cells with propagated, correlated uncertainty; do not count all three as independent evidence. |
| 2–5 | Reactor glucose, glutamine, lactate, ammonia, mM | Offline biochemical assays in the baseline; an online soft sensor would require separate calibration. |
| 6 | Reactor mAb, mg/L | Offline titer assay. |
| 7 | Reactor volume, L | Initial fill/level/weight plus flow accounting, explicitly declared measured or derived. |
| 8–14 | Separator viable/total cells, four metabolites and mAb | Latent in the baseline. A sampled separator or harvest titer is possible only as an expressly declared sampling-port/assay assumption. |
| 15 | Separator volume, L | Characterized holdup/level plus inventory balance; uncertainty retained. |
| 16 | Reactor temperature, °C | Online sensor plausible; published SMPL controller cadence does not establish its instrument precision. |

## What physical measurement publications establish

[Tomažič and Škrjanc (2023), *Halfway to Automated Feeding of Chinese Hamster Ovary Cells*](https://doi.org/10.3390/s23146618), report four CHO-S batches with offline references once or twice daily and Raman spectra every half-hour. Their modeled analytes include cell concentration, glucose, glutamine, lactate and ammonium. This supports an **intermittent reactor panel** and distinguishes reference assays from calibrated soft-sensor predictions. It does not establish SMPL separator measurements, universal instrument errors, or universal laboratory turnaround.

[Malinov et al., *Pseudo Perfusion of CHO Cells…*](https://doi.org/10.1002/bit.70190), describes actual perfusion/continuous-culture-related experiments with daily offline sampling, trypan-blue viable-cell measurements, metabolite analysis and antibody analysis; sampling before and after intermittent bleed is explicitly distinguished. The [public manuscript](https://pmc.ncbi.nlm.nih.gov/articles/PMC12687770/) provides a closer process-mode analogue than fed-batch alone. Daily sampling does not mean that the sample's result was available instantaneously.

[NIST SP 1200-32 (2026)](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1200-32.pdf), §§7.3–7.4 and 9.4, describes cytometer quality control, cell concentration/viability measurement and recording sample identity/time and process additions. It lists VCD, viability, diameter, pH and glucose as a minimum applicable record; its endpoint titer determination does **not** demonstrate continuous titer sensing. The stated pH re-standardization criterion is not a temperature or metabolite error specification.

These sources support the **kinds of measurements and approximate daily/twice-daily cadence**, not a physical validation of this specific synthetic process. The [acquired physical NISTCHO feeding dataset](../../backend/benchmarks/assets/nistcho-feeding-2026/acquisition.json) remains an independent experiment: its culture outcomes must not calibrate SMPL while simultaneously serving as held-out physical validation.

## Proposed frozen observation contract

All following exact schedule/turnaround choices are **benchmark assumptions informed by the measurement categories above**.

1. Publish command histories, planned inlet compositions and their units. Treat recipes as declared inputs; distinguish delivered-flow measurements from commands. For a simple first benchmark, assume exact command delivery and disclose that idealization.
2. Publish temperature every **60 min**. Publish reactor/separator volume estimates every **60 min** if level or fill/flow reconciliation is assumed; otherwise provide characterized initial holdups plus cumulative flow records. Mark estimates as derived. Hourly publication is a benchmark logging choice, not a universal sensor cadence.
3. Sample reactor VCD/viability, glucose, glutamine, lactate and ammonia every **1,440 min (24 h)**; release results **120 min** after collection. Sample reactor mAb every **1,440 min**, release **240 min** later. The 2-h/4-h release delays are explicit assumptions; neither is inherited from IndPenSim's penicillin assay design. Include a **720-min** assay-cadence sensitivity condition, grounded in twice-daily reference practice.
4. Keep separator cell/metabolite concentrations and separator mAb latent by default. An additional harvest/port mAb assay may be purchased/requested only if its sampling location, finite volume, cost and assumed release delay are frozen beforehand. Do not label an internal separator compartment reading as a measurement of a physically different vessel or line.
5. At decision time expose only records with `available_at <= decision_time`, with sample time, release time, units, method, source and uncertainty. Missing rows remain missing, not zero or interpolated observations. A completed source history can contain released old results; it does not reveal receiving latent states.
6. A 24-h receiving horizon with daily assays may yield no new titer result before the end. Preserve that limitation or choose a longer **separately admitted** horizon; do not accelerate biological time or retrofit future assays. A source-history window of at least 48 h is a useful proposed design choice but requires its own numerical admission.

The model-facing initial condition must be estimated from these permitted records and declared priors. A private true state can initialize the evaluator, but it must not initialize the model tool, populate hidden packet fields, or be revealed through a helper endpoint. Maintain an explicitly labeled full-state/no-noise oracle comparison if useful; do not pool it with the partial-observation task.

## Uncertainty ranges: assumptions, not empirical accuracy claims

The pinned environment defaults to `initial_state_deviation_ratio=0.1` and samples a uniform box around steady state. That supports reproducing an **upstream simulator initialization convention**; it is not an experimentally fitted population distribution. It is also inappropriate to transfer ±10% blindly to absolute temperature or to sample viable and total cells independently without enforcing viable ≤ total.

For a reproducible pilot, the following are reasonable **declared sensitivity settings**, not measured sensor or receiver confidence intervals:

| Component | Base assumed setting | Predeclared sensitivity |
|---|---|---|
| Concentration assay error | 5% multiplicative CV for metabolites and mAb | 0%, 2%, 10% CV |
| Cell-count assay error | 10% multiplicative CV | 0%, 5%, 15% CV |
| Viability error | 2 percentage-point SD, bounded to 0–100% with declared treatment | 0 and 5 percentage points |
| Temperature measurement | 0.1 °C SD | 0 and 0.2 °C |
| Holdup/volume estimate | 1% relative SD | 0 and 2% |
| Unknown initial latent concentrations | Nominal × [0.9, 1.1], uniform, positive/physical constraints | [0.8, 1.2] as explicitly broader stress only |
| Biological mismatch, if added | Growth/productivity factors 0.9–1.1; death factor 0.8–1.2 | Broader intervals require separate declaration/admission |

An explicitly parameterized lognormal observation error can preserve positive concentrations, with variance set from the chosen CV; state whether its mean or median equals truth. Near-zero analytes need a frozen detection-limit/floor model rather than hiding an arbitrary additive constant. Correlate VCD/viability/total-count errors consistently with the chosen counting representation. Do not interpret between-culture biological variation in the physical NISTCHO data as assay precision. Drift, missed samples, batchwise assay bias and flow-delivery error should be separate scenario factors rather than silently rolled into independent white noise.

No inspected primary source supplies empirical confidence intervals for **SMPL's** receiver growth/productivity/death mismatch. The proposed factors above are robustness tests. Source-only fitting cannot automatically identify all kinetic coefficients, latent initial states and measurement biases from a few daily samples; use a small fixed parameter subset, sensitivity/profile checks and held-out source-time prediction. Report nonidentifiability and propagate it to action outcomes. Exact recovery in a same-equation simulation is not experimental parameter validation.

## Preserve units, flow linkage and inventory

The pinned helper integrates in **minutes**. Flows are **L/min**, metabolites **mmol/L (mM)**, cells **cells/L**, mAb **mg/L**, volumes **L**, temperatures **°C**. Keep rate constants as implemented, including explicit `/60` conversions. A plotted hour is 60 solver minutes; a published hourly controller sample is `dt_spl=60`, not a one-minute step. Paper/table unit inconsistencies, including thermal coefficients, are model limitations to disclose; this research does not authorize a constitutive repair.

Maintain `dV1/dt = Fin + Fr − F1` and `dV2/dt = F1 − F2 − Fr`. Constant holdup requires **Fin = F2** and **F1 = Fin + Fr**. Check both inventories and all physical constraints throughout the trajectory. A concentration increase from draining a vessel must not masquerade as productive improvement.

External harvested mAb is `integral(F2 * mAb_separator dt_minutes)` in **mg**. The reactor outlet and recycle are internal transfers and must not be counted again as external product. Total upstream mAb inventory is `V1*mAb1 + V2*mAb2`; track its change, modeled production and external harvest together. Preserve an external-flow/harvest measurement interpretation separately from the latent simulator score. Known truth may score forecasts without becoming an agent measurement.

Record input conversions: cells/mL ×1,000 gives cells/L; µg/mL and mg/L have equal numerical values; a metabolite mass concentration needs its molecular-weight conversion before comparison with mM. Mark inferred or reconciled amounts as calculated. The current local [upstream wrapper](../../benchmarks/external_simulators/upstream.py) already converts simulation minutes to displayed hours and integrates external product mass over solver minutes; preserve this accounting when adding observation masks.

## Qualification before comparative inference

Freeze measured/latent channel lists, schedule, delays, error model, initialization method and source-only priors before selecting test cases or inspecting agent advantage. Verify that the model tool cannot recover private states, that assay release is causal, and that partial-observation reconstruction remains physical. Retain numerical/model failures and compare against simple last-value/trend, nominal-state and observation-driven estimation baselines. Report results by uncertainty/cadence condition and measured outcome; do not claim factory transfer, quality improvement, new sensor validation or demonstrated engineering savings from these synthetic tests.
