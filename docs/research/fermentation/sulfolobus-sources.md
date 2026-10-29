# Sulfolobus scale-up: source acquisition and usable evidence

Research acquisition and manual curation, 2026-10-27 UTC. This note is a research artifact, not evidence that an agent independently discovered the published settings or that a scale-up model has been validated.

## Primary sources acquired

Rastädter K., Wurm D. J., Spadiut O., Quehenberger J. (2023), *kLa based scale-up cultivation of the extremophilic archaeon Sulfolobus acidocaldarius: from benchtop to pilot scale*, Frontiers in Bioengineering and Biotechnology 11:1160012. [Publisher full text](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2023.1160012/full), [DOI](https://doi.org/10.3389/fbioe.2023.1160012).

The full article HTML and PDF are saved in [sulfolobus/](sulfolobus/). The official supplement was found through the [publisher's Figshare collection](https://api.figshare.com/v2/collections/6777603/articles), [article 23897628](https://api.figshare.com/v2/articles/23897628), supplementary DOI `10.3389/fbioe.2023.1160012.s001`. The [downloaded DOCX](https://ndownloader.figshare.com/files/41897316) is 563,784 bytes and matches the official MD5 `548f3155d6f54b8021dfd58b988a9133`. It contains Table S1 plus figure images, not a raw measurement workbook. The publisher and supplement identify the work as CC BY 4.0; retain attribution.

[source-manifest.json](sulfolobus/source-manifest.json) records URLs, retrieval timestamp, license, byte counts and SHA-256 hashes. [measurements.json](sulfolobus/measurements.json) is manually curated summary data, with per-row source locations and evidence classifications. [supplement-extracted.txt](sulfolobus/supplement-extracted.txt) contains the Word paragraph/table text; image data were not converted into purported raw measurements.

## Published equipment and characterization

Main article §2.1 identifies the vessels; supplementary Table S1 identifies the impellers. Working and total vessel volumes differ.

| Working volume | Total volume | Vessel | Submerged impellers | Impeller type / blades | Diameter | Blade height |
|---|---|---|---:|---|---:|---:|
| 2 L | 3 L | Sartorius Biostat A-plus | 2 | Rushton / 6 | 52 mm | 10 mm |
| 20 L | 30 L | Infors HT Techfors S | 3 | Rushton / 6 | 95 mm | 13.22 mm |
| 200 L | 300 L | Heinrich Frings Proreact 20P | 4 | Rushton / 6 | 200 mm | 40 mm |

Main Table 2 provides the following values. The kLa values are experimentally determined water-characterization measurements. Aerated power density is **author-calculated**, using Junker (2004), rather than a motor-power measurement. Agitation, airflow and sparger type are studied settings. They are **not** rated maximum operating limits.

| Working volume | Sparger | Agitation | Airflow | kLa | Aerated power density | Tip speed |
|---|---|---:|---:|---:|---:|---:|
| 2 L | Micro | 355 rpm | 0.51 L/min | 38.8 h⁻¹ | 0.25 kW/m³ | 0.97 m/s |
| 2 L | Ring | 355 rpm | 0.51 L/min | 32.6 h⁻¹ | 0.25 kW/m³ | 0.97 m/s |
| 2 L | Ring | 500 rpm | 0.51 L/min | 38.8 h⁻¹ | 0.63 kW/m³ | 1.36 m/s |
| 20 L | Ring | 285 rpm | 5.1 L/min | 40.5 h⁻¹ | 0.25 kW/m³ | 1.42 m/s |
| 200 L | Ring | 117 rpm | 37.5 L/min | 41.1 h⁻¹ | 0.13 kW/m³ | 1.23 m/s |

Table 2 also reports reactor diameter / total reactor volume ratios of 40.8, 7.96 and 1.57 at the three scales. Its header does not state the units. Preserve these as reported ratios; do not silently transform them into authoritative vessel diameters. A diameter inferred by multiplying a chosen volume unit is a reconstructed quantity with an explicit unit assumption.

§2.1.1: each kLa was obtained from a nitrogen-to-air dynamic DO transition in **deionized water at 75°C**. DO was calibrated with nitrogen and pressurized air at the corresponding agitation and gas-flow conditions. The paper does not publish raw transition traces or a repeat-measurement table. §3.2 reports an overall mean measurement standard deviation of **±1.17 h⁻¹**. This is not a per-row 95% confidence interval and does not quantify cross-vessel predictive uncertainty.

§2.1 and §3.2: cultivation uses *S. acidocaldarius* DSM 639 at 75°C, pH 3.0, chemostat dilution rate 0.03 h⁻¹. The 20 L and 200 L cultivations used slight overhead pressure in the range 0.1–0.3 bar; exact per-vessel pressure is not specified. Table 2 does not explicitly state the reference temperature/pressure of its gas volumes. Do not claim an exact compressed-gas molar flow without documenting that convention.

## Biological observations and important absences

Main §3.1 reports that the 2 L ring sparger at 355 rpm gave DO below 20%, requiring oxygen supplementation. Raising agitation to 500 rpm increased its kLa to the micro-sparger value, permitted omission of extra oxygen and was associated with an almost 6 percentage-point viability improvement. The study discusses a **possible** oxygen-sensitivity mechanism; it does not identify a calibrated toxicity-dose or viability response model for arbitrary gas compositions.

§3.2.1 reports DCW increasing from 3.77 g/L at 2 L to 4.16 g/L at 200 L, and viability around 91% at the 2 L and 20 L scales. The text does not supply an exact numeric 20 L DCW mean. Table 1 reports 200 L biomass space-time yield 0.125 g/L/h, consistent with 4.16 × 0.03 = 0.1248 before rounding. These are published summary values, not full trajectories.

**200 L viability was not measured.** §2.2 explicitly says FCM was not performed at the Fraunhofer cultivation site. §3.2.1 repeats that limitation. Furthermore, faulty O2/CO2 off-gas measurements at 200 L prevented calculation of qO2, qCO2, RQ, CO2 yield and carbon balance. Do not impute these outputs from the 2 L or 20 L results and call them experimentally measured.

Figure 2 contains biological bars with error bars; captions describe variability across steady-state sampling points, rather than independent replicate fermentation batches. No figure digitization was performed here. If a later implementation digitizes figures, label values as approximate digitized summaries and record digitization uncertainty. Never synthesize replicate trajectories from bars.

## Available equations and model applicability

The fundamental oxygen balance is `dC/dt = kLa(C* − C) − OUR`; a non-consuming water reoxygenation experiment uses `OUR=0`, and its approach to saturation permits determination of kLa. The paper references [Kager's dynamic oxygen-transport implementation](https://gitlab.com/juliankager/kla_determination) for that determination. This equation does not, by itself, predict how kLa changes with vessel size, agitation, flow and sparger geometry.

The article cites Junker (2004), *Scale-up methodologies for Escherichia coli and yeast fermentation processes*, [DOI 10.1016/S1389-1723(04)70218-2](https://doi.org/10.1016/S1389-1723(04)70218-2), for calculated aerated power. Rastädter's supplement gives impeller dimensions but does not provide a new validated kLa correlation across these vessels. Do not attribute arbitrary exponents, Newton numbers, gassed-power corrections, Henry coefficients or motor efficiencies to Rastädter et al.

A conventional empirical expression `kLa = A (Pg/V)^alpha us^beta` may be implemented only with separately documented parameter sources and applicability limits. The source table supplies two ring-sparger points at one airflow and one geometry. Thus:

- An agitation-only power-law fit has two observations and two fitted parameters, hence zero residual degrees of freedom. It estimates an exponent of approximately 0.50836 from the rounded published points, with no empirical prediction interval.
- Treating the author-calculated power density as the independent variable gives an exponent of approximately 0.188 from those same two points.
- The gas-flow exponent, geometry correction, sparger-orifice effect and receiving-vessel gassed-power relationship are **not identifiable** from those two points.
- The micro-sparger point at otherwise identical conditions establishes that sparger configuration matters; it is not an additional ring-sparger gas-flow characterization point.
- Water kLa at 75°C is not a validated broth kLa model. Medium composition, viscosity, foaming and antifoam need applicability checks.
- Oxygen solubility at 75°C and the relevant pressure/composition must come from a separate cited physical-property model or an explicitly declared user assumption. Biomass-dependent OUR needs validated qO2 evidence, not penicillin kinetics.

## Defensible withheld split and remaining work

A strict transfer benchmark can expose the three 2 L characterization rows plus receiver **equipment specifications** from §2.1 and Table S1, then hold out both receiving kLa values and the published receiving agitation/airflow choices. Fit only on the two ring-source points; use the micro-source point to test sparger applicability. Keep 20 L/200 L biology and chosen operating settings out of agent prompts and retrieval as well as out of calibration.

**Full article PDFs/HTML and the supplement include answers.** Merely omitting a JSON `target` key is insufficient if the agent can read those files or search the full paper during evaluation. Stage calibration-only evidence in the existing scoped evidence registry, pin hashes, and run the existing external filesystem isolation boundary. Evaluation-only records can contain the complete publication and measurements. A separate unblinded research/reconstruction demonstration may use full-text retrieval, but its outputs cannot be scored as blind prediction of information it already retrieved.

With source-only data the scientifically valid result may be a conditional envelope and a requirement for receiving-vessel characterization, rather than a uniquely justified rpm/airflow recommendation. Required follow-up measurements include receiver kLa versus agitation and gas flow at 75°C, representative broth/antifoam effects, exact gas reference conditions, pressure and air composition, calibrated oxygen solubility, motor/torque limits and reliable OUR/off-gas measurements. The published 285/117 rpm settings must be compared only **after** model/recommendation outputs are frozen.

The article's data-availability statement offers raw data from the authors without undue reservation. No publicly downloadable raw measurement workbook was located in the article, official supplement collection or Figshare article. This research did not contact the authors. Document that absence; do not create a raw-data-looking surrogate.

No commercial utility cost accounting, measured engineering-workflow timing, motor ratings or demonstrated eliminated experiments are supplied by this publication. Any power/energy or labor cost estimates need separate assumptions or observed timings and must remain distinct from measured experimental savings.
