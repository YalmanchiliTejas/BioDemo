# Liu et al. (2016): source-grounded Pichia transfer and oxygen-cost case

Research acquisition and manual extraction, 2026-10-26. This is a research/data record, not an implemented solver or a claim that a model predicts the biological outcomes.

## Primary sources and acquisition

Liu, W.-C., Gong, T., Wang, Q.-H., Liang, X., Chen, J.-J., and Zhu, P. (2016), *Scaling-up Fermentation of Pichia pastoris to demonstration-scale using new methanol-feeding strategy and increased air pressure instead of pure oxygen supplement*. Scientific Reports 6, 18439. [DOI](https://doi.org/10.1038/srep18439), [publisher PDF](https://www.nature.com/articles/srep18439.pdf), [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC4726300/), [Europe PMC full-text XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC4726300/fullTextXML).

The article is explicitly CC BY 4.0. The lawful archived PDF, HTML and XML are in `pichia/`; `article.txt` is a local XML text extraction. SHA-256, retrieval URLs and media types are recorded in `pichia/source-manifest.json`. The publisher HTML redirected to its identity endpoint in the web tool, but the publisher PDF and PMC HTML/Europe PMC XML were accessible via ordinary downloads. The archived XML/PMC page list **no supplementary-material attachment** and no deposited machine-readable raw fermentation dataset. This is an availability finding, not proof that no additional author-held data exist. Figure curves are published plots, not raw numerical trajectories. No figure digitization was performed.

## What was actually compared

The strain is recombinant *P. pastoris* GS115-3.5K-P1-2 (Mut+), producing intracellular glycoside hydrolase LXYL-P1-2. Biological outputs are enzyme activities and derived enzyme mass, not pharmaceutical drug yield or viability. Methods, “Strain, Media and Fermenters”, “Biomass Measurement and Enzyme Assay”.

The **direct pure-oxygen versus pressure comparison is a 30-L experiment using DO-stat** (Results, “Elimination of Pure Oxygen Supplement by Increasing Air Pressure”, Figure 1 and Table 1). Np-Ox uses 0.05 MPa **super-atmospheric pressure (gauge)** and supplemental pure oxygen. Ip-Air uses 0.10 ± 0.05 MPa **gauge**, without supplemental pure oxygen. Do not label this pair as the 10-L scale-up experiment.

The subsequent program changed methanol feeding, induction DO and initial induction biomass sequentially, then transferred the optimized process from 10 L to 100 L and 1,000 L. Therefore improvements across the complete program cannot be attributed exclusively to pressure. Methods, “HCDF Optimization and Scaling Up”; Results, Table 1 and Table 2.

## Equipment and process inputs

[Methods, “Strain, Media and Fermenters”, “Fed-batch HCDF”, “HCDF Optimization and Scaling Up”](https://pmc.ncbi.nlm.nih.gov/articles/PMC4726300/).

| Nominal vessel | Manufacturer/type reported | Reported aeration range (L/min) | Reported agitation range (rpm) | Medium/seed/harvest information |
|---|---|---:|---:|---|
| 10 L | 10S, Shanghai Gaoji Bioengineering | 2–10 | 100–680 | Initial working volume 3.5 L; inoculum 10% v/v |
| 30 L | 30S, Yangzhong Weikete Bioengineering Equipment | Not tabulated | Not tabulated | Initial working volume 10.5 L; inoculum 5% v/v |
| 100 L | 100S, Shanghai Gaoji Bioengineering | 20–100 | 50–400 | Methods: 3.5 L seed added to 35 L medium; Results: approximately 55 L harvested, called 35 L initial volume |
| 1,000 L | 30/200/1,000-L type, Zhenjiang Dongfang Bioengineering and Biotechnology | 200–1,000 | 20–280 | Methods: 100 L seed added to 400 L medium; Results: approximately 650 L harvested, called 400 L initial volume |

Those are **observed operating envelopes**, not certified vessel limits. No vessel maximum allowable working pressure, impeller diameter/type/count, sparger dimensions, broth density/viscosity, shaft torque, motor rating or measured power draw is supplied. The initial-volume wording does not consistently say whether inoculum is included: do not silently equate nominal vessel volume, initial medium charge, inoculated broth volume, induction volume and harvest volume. Airflow reference conditions (standard-volume versus actual compressed-volume flow) are not specified. Hence vvm and compressor mass flow need an explicit volume/reference-condition assumption.

Optimized transfer conditions are temperature 28–30 °C, pH 5, gauge air pressure 0.10 ± 0.05 MPa, no supplemental pure oxygen, induction DO 1%, initial induction biomass 100 g DCW/L and biomass-stat methanol feed 0.035 mL/(g DCW·h). S1/S2 DO is 20%; baseline induction DO was 5%. The DO sensor’s calibration/reference convention at varying pressure is not sufficiently specified to turn percent DO into absolute dissolved concentration without an assumption. Initial glycerol is 40 g/L in FM22; the glycerol fed-batch feed is 50% v/v glycerol at 18 mL/(L·h). Methanol stock is 100% plus 12 mL/L PTM4 salts.

The manuscript writes `v = V/m/t` and describes `m` as biomass density g/L. For a total feed in mL/h, a dimensionally consistent interpretation is `F_methanol = v × X × V_broth` where `X` is g DCW/L and `V_broth` is L. This is an **interpretation**, not an independently measured feeding trajectory. The authors stress real-time cell-density measurement. Do not integrate methanol use from endpoint biomass and assume that it is the observed total.

## Published outcomes usable as evaluator references

[Table 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC4726300/#t1), printed PDF p. 3. Uncertainty below is the displayed ±SD of three parallel measurements/assays, not demonstrated independent fermenter-run replication. The methods confusingly say “standard error (SD)”; retain the table’s SD label and disclose this ambiguity.

| 30-L direct pressure/oxygen arm | Activity U/L | Biomass activity U/g | Enzyme production mg/L | Specific production mg/(g·h) | Table endpoint h | Biomass g DCW/L |
|---|---:|---:|---:|---:|---:|---:|
| Np-Ox, 0.05 MPa gauge | (1.5 ± 0.3) × 10^7 | (1.5 ± 0.2) × 10^5 | 290 ± 20 | 0.022 ± 0.001 | 80 | 97.5 |
| Ip-Air, 0.10 ± 0.05 MPa gauge | (2.1 ± 0.2) × 10^7 | (1.9 ± 0.1) × 10^5 | 420 ± 30 | 0.023 ± 0.002 | 156 | 107.5 |

The narrative gives Ip-Air activity maximum at 160 h whereas Table 1 says 156 h. Store Table 1 endpoint as 156 h with a conflict flag. Table 1 rounds Np-Ox production to 290 mg/L; the narrative says 294 mg/L. Similarly, biomass values at activity peak versus maximum over the entire trajectory are not interchangeable. Longer Ip-Air cultivation can consume more methanol and occupancy time even though oxygen purchases are removed.

[Table 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC4726300/#t2), printed PDF p. 7. The entire table uses the optimized conditions stated above.

| Nominal scale | Activity U/L | Biomass activity U/g | Enzyme production mg/L | Biomass production mg/g | Mean specific production mg/(g·h) | Reported time h | Biomass g DCW/L |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10 L | (3.2 ± 0.2) × 10^7 | (3.7 ± 0.1) × 10^5 | 640 ± 10 | 7.4 ± 0.3 | 0.025 ± 0.001 | 176 | 85 |
| 100 L | (3.0 ± 0.4) × 10^7 | (3.4 ± 0.3) × 10^5 | 600 ± 20 | 6.8 ± 0.4 | 0.028 ± 0.004 | 168 | 85 |
| 1,000 L | (4.5 ± 0.3) × 10^7 | (4.7 ± 0.5) × 10^5 | 900 ± 30 | 9.4 ± 0.3 | 0.081 ± 0.003 | 112 | 95 |

The **1,000-L 112-h reference is not a measured peak or harvest**: Table 2 footnotes explicitly except this scale. At 136 h fermentation ended with roughly 650 L broth, 62 kg dry cells, 4.6 × 10^7 U/L and 4.8 × 10^5 U/g, while activity had still been increasing (Results scale-up section, Figure 5). Narrative enzyme-production values are 642, 595 and 898 mg/L, respectively; Table 2 rounds them to 640, 600 and 900. A Discussion sentence says “898 g/L”, conflicting with Results and Table 2; treat that as an unresolved unit typo and use the table’s mg/L. The assay conversion is 5 × 10^4 U/mg purified enzyme (Methods, “Other Calculations and Statistical Analysis”). Conversion from activity to enzyme mass is a dimensional consistency calculation, not independent biological validation.

## What the physical model can and cannot establish

The article contains **no kLa measurements, OUR measurements, quantified inlet pure-oxygen flow, exhaust composition or calibrated broth oxygen-solubility measurements**. It supplies no fermentation-specific oxygen/biomass/product kinetic fit. It therefore cannot independently validate an absolute OTR prediction or a mechanistic prediction of enzyme productivity from agitation, pressure and airflow. The mechanistic implementation can credibly calculate **conditional** oxygen solubility/driving-force ratios and OTR/OUR margins for explicitly supplied characterization inputs, then identify what must be measured. Do not reuse IndPenSim penicillin kinetics to invent Pichia production predictions.

With the same temperature, inlet oxygen mole fraction, medium and kLa, Henry-law saturation scales with **absolute oxygen partial pressure**. For dry gas and assumed ambient pressure 101.325 kPa, raising gauge pressure from 50 to 100 kPa gives `C*_high/C*_normal = 201.325/151.325 ≈ 1.3304`. The published 50–150 kPa gauge operating band gives ratios approximately 1.0–1.6608, **not** a statistical pressure uncertainty distribution. Water vapour, medium salting-out, hydrostatic pressure, exhaust depletion and pressure-dependent kLa can change this calculation; include them only with characterized/assumed parameters clearly tagged. Never use `100/50 = 2` as the solubility ratio. At a target DO, apply `OTR = kLa(C*−C)`, but absolute `C`, `C*`, kLa and OUR remain required inputs.

A technically reviewable strategy is to evaluate air-only operation in the reported gauge-pressure band, below a separately verified vessel/sterile-filter/relief-system rating, and compare OTR capacity to a measured OUR envelope. Reported successful culture does not certify a new receiving vessel. Recommended follow-up measurements: receiver kLa at proposed RPM/flow/pressure in process-relevant broth, calibrated DO reference, pressure ratings, actual/normal gas-flow basis, exhaust O2/CO2 and OUR, motor/torque/headspace/filter margins, methanol residual and feed integral, assay productivity over replicated runs.

## Cost comparison boundaries

The paper reports a qualitative claim that additional methanol was cheaper than the oxygen used in Np-Ox, but supplies neither oxygen consumption nor prices or a full accounting (Discussion, printed PDF p. 8). It does not provide measured dollars or measured energy savings.

Compare scenarios at an explicitly declared common functional basis: equal operating duration and broth volume for an oxygen-delivery sensitivity calculation, or cost per unit measured enzyme activity/product while accounting for each actual duration. Treat oxygen flow/fraction, normal-flow basis, compressor inlet conditions, efficiency and staging, pressure drop, electricity price, oxygen unit price/delivery basis, agitation power, methanol feed history/price, cooling, downstream recovery and occupancy/capital as editable assumptions or missing values. Air compression should use absolute pressure ratios; additional compression energy must offset any avoided pure-oxygen purchase. A break-even oxygen price is useful when consumption/price are unknown. A result excluding methanol/occupancy is a **partial oxygen-delivery operating-cost estimate**, not total batch COGS or experimentally observed savings.

## Leakage-safe evaluation proposal

The full article contains answers in tables, narrative, captions and figures. **Do not mount these full source archives or this research note in the evaluated agent container.** Public availability does not make them permitted inputs to a blinded benchmark.

A defensible split is to supply Methods operating envelopes, reactor identities, pressure interpretation and the 10-L calibration observations, then withhold **all 100-L and 1,000-L biological outcomes**, Table 2, scale-up Results paragraphs, Figure 5/6 values and their narrative repeats. Keep reference outputs in an evaluator-only manifest outside the agent filesystem. Verify the agent prompt, tool responses, retrieval index and accessible files contain none of the withheld values. Extraction/parameter reconciliation may be scored against a separate evaluator manifest; science scoring must label productivity as **not mechanistically predictable from the available data** when no calibrated biological model is available. The physical model’s conditional pressure/OTR calculation is separate from observed productivity, and missing-characterization detection is a legitimate benchmark result.

A simple constant-productivity transfer baseline fitted to 10-L data can be reported as an **empirical baseline** and independently tested at larger scales, but it must not be described as fermentation kinetics or causal pressure prediction. No observed human engineering timing was acquired in this research; no time savings or eliminated experiments are established.
