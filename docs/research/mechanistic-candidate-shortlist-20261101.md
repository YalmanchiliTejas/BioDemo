# Mechanistic-first research shortlist: recent reports and measured failures

Research date: 2026-11-01. Research only. Governing direction: `Main_Culture_andETHOS.md`. This follow-up screens actual process mechanisms rather than treating any CMC setback as a simulator use case. No product implementation or paid inference was performed.

## Conclusion

The strongest new **scale-up investigation narrative** is a firsthand BDO report published April 2024 describing interacting oxygen/CO2 control loops, poor culture viability and harvest filtration failure. The strongest **quantitative experimental benchmark lead** is a November 2024 mRNA TFF study with measured losses, mass balances and fouling-model equations. A June 2024 penicillin oxygen-oscillation study is another promising experimental benchmark. These are different evidence categories.

None establishes the complete original combination: a named, dated 2023–2024 commercial transfer/scale-up failure, disclosed millions lost/invested in that episode, and enough independent public measurements to validate a prevention claim. Recent publication dates are not incident dates. Do not substitute general batch costs or company R&D for incident losses.

## 1. BDO 2024: coupled gassing failure followed by blocked harvest filters

**Source:** Michael Smargon, BioProcess Technology Group, [April 5, 2024 firsthand report](https://www.bdo.com/insights/industries/life-sciences/benefits-of-using-real-time-in-process-data-in-mammalian-cell-culture), [original two-page PDF](https://www.bdo.com/getmedia/b9b875aa-8645-4d74-b6e1-0bc719172688/LS-Using-Real-Time-Cell-Culture-Data-Article-3-24.pdf?ext=.pdf).

**Observed/reported:** At the first run at proposed clinical manufacturing scale, second-stage filters clogged after only **20% of culture volume** was processed. Harvest viability was below **50%**, versus above **70%** in development runs. The investigation described uncapped oxygen flow driving CO2 stripping and compensating CO2 addition, which displaced oxygen and increased oxygen demand from the controller. The authors propose earlier flow limits/microsparging as corrective measures. Client, incident year, raw traces and incident-specific dollar loss are not disclosed; general statements that batches can cost millions do not price this event. The proposed rescue was not a published paired successful run.

**Our mechanistic hypothesis:** Couple oxygen and CO2 mass balances, pH/buffer chemistry and both controllers. Test whether the receiving configuration enters the reported mutually escalating gas-flow regime. Estimating subsequent cell death and filtration loss additionally needs validated cell-response and debris/filter models; it cannot be inferred from gas balances alone.

**Agent's job:** Reconcile source versus receiving spargers, gas-flow limits, controller settings and development acceptance ranges; run the relevant calculations and attach evidence to each discrepancy.

**Data gate:** Receiving geometry/kLa, liquid volume, off-gas and pH/DO/flow time series, controller logic, buffer chemistry, cell measurements and filter characteristics. No quantitative replay is presently justified by this two-page narrative alone.

## 2. Nourafkan et al. 2024: mRNA loss and membrane fouling

**Source:** [Original article, DOI 10.1002/biot.202400473](https://doi.org/10.1002/biot.202400473), [university-hosted published PDF](https://eprints.whiterose.ac.uk/id/eprint/219513/1/Biotechnology%20Journal%20-%202024%20-%20Nourafkan%20-%20An%20Experimental%20and%20Modeling%20Approach%20to%20Study%20Tangential%20Flow%20Filtration.pdf). Version of record November 8, 2024.

**Observed:** Figure 1C reports **26.1% and 33.4% mRNA loss** during concentration/diafiltration in two replicates. The study supplies experimental conditions, pressure/flux plots, a mass-balance model and a combined pore-blocking/cake fouling model with fitted parameters. This is laboratory process research, not a disclosed commercial batch failure or financial-loss case. Underlying data are available from the corresponding author on reasonable request; no public raw-data repository was verified. Figure 1C was visually checked against the PDF, rather than relying on search-extracted numbers.

**Our benchmark hypothesis:** Assess predictions of transmembrane pressure, impurity clearance, duration and product recovery under changed conditions. The fouling model is not automatically a complete mRNA-recovery model: adsorption, holdup and washing need explicit mass accounting. Use the paper's equations as a baseline; reserve independent conditions for testing. Reported model fitting is not automatically evidence of held-out predictive accuracy.

**Agent's job:** Extract membrane/operating specifications, check units and mass-balance consistency, select the applicable equations, expose unidentifiable parameters and produce a pressure/throughput/recovery comparison with reviewable recommendations.

**Data gate:** Request raw runs or clearly label measurements digitized from figures. Avoid presenting reconstructed traces as original data. Check whether enough independent experimental conditions exist before splitting calibration and evaluation.

## 3. Wang et al. 2024: loss of penicillin productivity under oxygen cycling

**Source:** [Original study, DOI 10.1002/bit.28782](https://doi.org/10.1002/bit.28782), [TU Delft institutional record](https://repository.tudelft.nl/record/uuid%3A158259da-dab5-4d60-964c-d0dfdcfb9ef7). First online June 22, 2024; October issue.

**Observed:** Controlled **150-second dissolved-oxygen feast/famine cycles** in glucose-limited Penicillium chrysogenum chemostats reduced penicillin productivity. The setup was designed to mimic industrial spatial oxygen variation. It is a real scale-down experiment, not evidence of a named 2024 commercial failure or million-dollar loss.

**Our benchmark hypothesis:** A dynamic oxygen-transfer/uptake and product-formation model can be tested against constant versus fluctuating exposure. An average-DO-only calculation may miss exposure-history effects, but that limitation must be measured, not assumed. Organism-specific kinetics and response/adaptation parameters are necessary. Metabolic mechanisms in the study should not be replaced with a generic monotonic oxygen penalty fitted only to the outcome.

**Agent's job:** Compare circulation/exposure assumptions with measured culture response, identify which scale-up invariants fail to preserve the relevant exposure, and propose an additional scale-down experiment.

**Data gate:** Inspect full measurement/supplement coverage and licensing before committing. This screen verified the original study and experimental purpose; a reusable raw-data set and calibrated model were not established.

## 4. Wang et al. 2024: bispecific-antibody precipitation at CMC scale

**Source:** [Original paper, DOI 10.1093/abt/tbae013](https://doi.org/10.1093/abt/tbae013), [PubMed record](https://pubmed.ncbi.nlm.nih.gov/39036070/), [published correction](https://pmc.ncbi.nlm.nih.gov/articles/PMC11384148/). First online May 29, 2024. Original full text was inspected through the Europe PMC XML service after browser access failed.

**Observed:** A molecule appearing acceptable during discovery showed agitation-induced precipitation in **15 L CMC production**. Structural/analytical work and sequence engineering improved manufacturability. Incident date, commercial loss and a quantitative operating-scale aggregation model are not disclosed. Expression host and production scale changed; do not identify volume alone as the cause.

**Our assessment:** A real mechanism-rich case, but weaker fit to the current platform than the gas-control or filtration examples. A predictive reconstruction would require protein-specific aggregation kinetics and interfacial exposure data; generic mixing/shear calculations cannot determine sequence-specific precipitation. Useful for evidence-guided hypothesis/experiment selection, conditional on those inputs.

## Stronger commercial physics cases with date limitations

[Pfizer-affiliated vial-breakage research](https://pubmed.ncbi.nlm.nih.gov/36372227/) reports commercial breakage after cycle changes and a measured improvement after changing freezing conditions. Its issue date is April 2023, but first online publication was November 2022 and incident dates are unspecified. This needs thermo-mechanical stress modeling in addition to the platform's drying calculations.

[Amgen/UW vaccine process-development research](https://doi.org/10.1016/j.procbio.2023.03.014) reports major scale-dependent filtration-capacity/yield deterioration. Published 2023, the work supports clinical trials starting in 2021, so it cannot be called a 2023 incident. Underlying data are confidential. See the [detailed primary-source screen](recent-mechanistic-failure-evidence-20261101.md) for quantitative findings and exclusions.

## Fit and next research decision

Existing inspected fermentation models provide oxygen/pressure calculations; they are not already validated dynamic O2/CO2-controller or penicillin-kinetic models. No inspected ready mRNA-fouling, protein-aggregation or vial-stress model was established. This shortlist identifies applicable model families, not functionality already demonstrated by Sievance.

For the job of making scale-up risks testable, the simple alternative is a rules-based transfer-envelope comparison. The ambitious alternative couples the agent to a case-specific predictive model. Compare both with model-only and agent-only baselines on the same records. Measure physical prediction error, missed/false risk flags, source correctness, appropriate abstention and reviewer effort; no avoided-dollar claim follows from fitting a paper's curve.

**Recommendation:** First complete a data-sufficiency review of the **2024 mRNA TFF paper** and the **2024 penicillin oxygen-cycling study**. Retain **BDO's 2024 scale-up narrative** as the closest investigation example, conditional on access to actual run records. Treat these as complementary research leads; do not merge their evidence into a fictitious historical demonstration.

Across all four product pillars, start from authorized existing records; preserve source/parameter uncertainty; produce a proposed measurement, experiment or action for review; retain manufacturing systems as records of approved decisions. No automatic process changes are implied.
