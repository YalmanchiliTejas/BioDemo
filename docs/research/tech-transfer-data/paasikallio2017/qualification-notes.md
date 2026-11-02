# Qualification of the paired Trichoderma gas records

Checked 1 November 2026 against the unchanged workbook and primary full-text articles. This supports an offline preparation exercise; no paid model runs, manufacturing action, or predictive validation occurred. Public articles/data may have appeared in model pretraining. This is not an independently blinded evaluation.

**Decision:** qualify recorded gas-channel trajectories, sampling times and explicitly defined dimensionless signal transformations. Do not qualify absolute gas exchange, oxygen transfer, product prediction, or causal scale effects from these sources alone.

## Sources and identity

- [Zenodo 5846028](https://zenodo.org/records/5846028): `Paasikallio2017_CO2_data.xlsx`; unchanged local file and hashes in `source-manifest.json`. Its Description explicitly assigns one culture to each sheet and links to Paasikallio 2017. This is **T. reesei D-161646**, not the marine T2/D-221704 strain in the repository title. Other workbooks are separate experiments.
- [Paasikallio, Huuskonen and Wiebe (2017)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5504852/), DOI [10.1186/s12934-017-0736-3](https://doi.org/10.1186/s12934-017-0736-3), especially Methods/bioreactor cultivation, Results/scaled production, Fig. 3 and Table 3.
- [Tamminen et al. (2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9279543/), DOI [10.1186/s13568-022-01436-4](https://doi.org/10.1186/s13568-022-01436-4), especially Discussion linking previously unpublished gas records to the earlier 1/250 L cultures. It reports CO2-based specific growth rates of 0.40 h⁻¹ (1 L) and 0.340 h⁻¹ (250 L), without specifying reproducible fitting windows or a calculation method for these two records. Its ambr250 conditions and results must not be assigned to the older cultures.

Unchanged Europe PMC XML copies of both articles are archived here; `qualification-source-manifest.json` records URLs, licenses and hashes. Both articles specify CC BY 4.0. Cite the authors and source when redistributing; derived notes are an interpretation.

## Measurement basis and sampling

The workbook contains Time (h), Nitrogen, Oxygen, Argon, Carbon Dioxide and Ethanol in A:F, plus static Air input references in I:M. No gas unit appears in headers, descriptions, comments, formulas or workbook descriptive properties. All sheets are visible; no formulas or cell comments are present. I2:M2 are reference levels; I3:M3 are smaller unlabeled values, **not a confirmed standard deviation/SEM, calibration uncertainty, or second inlet operating condition**. There is no inlet flow trajectory.

Paasikallio Methods identifies continuous gas-concentration analysis by a Prima Pro Process mass spectrometer. Calibration mixtures contain specified percentages of CO2, O2, Ar and ethanol in N2/Ar. This plus air-like numerical magnitudes supports a concentration interpretation, but neither article nor workbook explicitly fixes mole versus volume percent, wet versus dry basis, sample conditioning, normalization, gas-flow reference pressure/temperature, or time alignment/transport lag.

Direct workbook checks:

| Property | 1 L | 250 L |
|---|---:|---:|
| Complete numeric measurement rows | 4,389 | 3,294 |
| Recorded time (h) | 0–215.7002777777 | 0–171.8227777777 |
| Median interval (min) | 3.0333333 | 3.0333333 |
| Interval range (min) | 2.0833333–4.4000000 | 2.5166667–4.4333333 |
| Sum of five channel values, range | 99.9854–100.0002 | 99.9960–100.0002 |
| CO2 channel range | 0.0433–1.1510 | 0.0460–1.4094 |
| O2 channel range | 19.7877–20.8246 | 19.3689–20.8272 |

Time is strictly increasing; the channels are complete numeric observations. Near-exact closure at 100 is evidence consistent with percent normalization, **not proof of independent calibration accuracy or measurement basis**. Retain raw labels as recorded gas-channel units unspecified. Do not silently divide by 100 and advertise verified mole fractions. Sampling is irregular despite the common median; integrate with actual time differences and state any interpolation. Formatted empty rows are not measurements. Individual observations are not independent experimental batches.

## Equipment and operating context

Paasikallio Methods maps the 1 L culture to Biostat Q (1 L maximum working volume) and the pilot to New Brunswick Scientific IF400 (350 L maximum working volume). Narrative references to a 300 L reactor and a 256 L final broth coexist with the 250 L culture label. Preserve these distinctions; 250 L is not a verified constant liquid volume or geometric vessel capacity.

Both used 35 °C, pH 4 controlled with 2–4 M NaOH or 1 M H3PO4, approximately 0.5 vvm, and the same Meridianstar Rapid Set pectin. Agitation ranges were 350–500 rpm (1 L) and 125–200 rpm (pilot); these are reported ranges, not measured time courses. The 10 L experiment used Sigma pectin and is not a matched third scale.

The Meridianstar batch medium contained 9 g/L lactose, 11 g/L pectin and 3 g/L yeast extract; its feed contained 78 g/L pectin and 1 g/L yeast extract, with enzymatic prehydrolysis. Feed was nominally constant after at least 5 g/L biomass. In the 1 L culture, feeding waited until lactose was exhausted; in the pilot it started with about 2 g/L lactose remaining. Sterile enzyme was added after sterilization at 1 L, while pilot enzyme was added before sterilization. Pilot inoculum came through a 32 L BioFlo reactor; 1 L inoculum came from flasks. These process differences preclude a controlled scale-only causal claim.

Actual feed rates/timestamps, liquid-volume history, agitation history, inlet molar flow, gas reference conditions, pressure, sample humidity, DO trajectory, impeller/sparger geometry, broth rheology, kLa and power are not supplied here. Approximate 0.5 vvm cannot replace those measurements for a quantitative mechanistic model.

## Endpoint and clock conflicts to retain

Paasikallio Table 3 reports 1/250 L durations 215/168 h, whereas the gas records continue to 215.7003/171.8228 h. No source explicitly reconciles gas-record endpoint with harvest/product-sampling time. A preregistered 168 h pilot scoring horizon may be selected as an evaluation convention; it is not proof of sample alignment. Preserve the full raw record.

Table 3 gives 1 L product 18 g/L but the Results text gives 19 g/L. Pilot product is 15 g/L in Table 3 versus 14 g/L in abstract/Results (the latter says 256 L). Pilot galacturonate yield is 0.8 g/g in the table versus 0.77 g/g in narrative. Recovery is 77% in the abstract versus 73% in Table 3/Results, with approximately 2.8 kg recovered. Some numbers may reflect rounding or processing stages, but the sources do not fully reconcile them. The authors discuss crystal retention with biomass/filtering and incomplete downstream recovery; they do not establish oxygen limitation as the explanation for lost product yield. Fig. 3/Table 3 biomass errors at these scales represent duplicate or 2–3 measurements, not replicated paired batches.

## Qualified targets and mechanistic limits

| Target | Qualification |
|---|---|
| Raw receiver gas-channel profiles, timestamps, extrema or time-weighted errors in the recorded units | Qualified as observed signals; one receiver batch, with channel basis unresolved. Choose endpoint/window/interpolation before viewing scored data. |
| Same-channel dimensionless normalization `s_g(t)/a_g`, or excess `(s_g(t)-a_g)/a_g`, where `a_g` is that sheet's I2:M2 reference for the same gas | Qualified as explicit signal transformations if numerator and reference share the same channel calibration. No mole-percent assumption needed. These are relative signals, not molar yields or rates. CO2's small air baseline makes excess ratios baseline-sensitive; retain denominator and raw source lineage. |
| CO2 log-slope during an explicitly chosen early-growth window | Qualified only as an apparent exponential gas-signal slope (h⁻¹); background subtraction and window matter. Interpreting it as biomass growth needs proportional respiration, stable gas dilution and negligible changing maintenance/metabolism. Published 0.40/0.340 h⁻¹ values are contextual summaries, not exact reproducible scoring ground truth. |
| Cross-gas CO2/O2 or CO2/N2 ratios | Mathematically computable signal ratios. Physical concentration-ratio interpretation requires compatible channel calibration/basis; a common percent multiplier cancels but unknown channel gains/offsets do not. |
| Nitrogen-corrected gas exchange, RQ, CER, OUR | Only conditional model-derived quantities until measurement basis, tracer conservation, flow and gas handling are qualified; not reference measured endpoints. |
| OTR, kLa, oxygen limitation, product titer/yield or biomass trajectory | Blocked as quantitative mechanistic ground truth from this workbook. Offgas oxygen depletion is not a direct OTR or DO measurement. Published product summaries remain conflicting paper observations, not raw held-out product trajectories. |
| Transfer generalization or superiority across sites/scales | Blocked by one paired run, confounded feeding/inoculum/process differences, and public-source exposure. Thousands of samples do not supply batch replication. |

For clarity, the nitrogen relation below is an engineering mass-balance derivation, **not a claim that these prerequisites were verified**. With common-basis molar fractions `y`, inert nitrogen, negligible nitrogen accumulation/dissolution change, no unmeasured gas paths/leaks and representative synchronized inlet/outlet sampling:

`F_out/F_in = y_N2,in / y_N2,out`.

Then net O2 disappearance per mole of inlet gas is `y_O2,in - (y_N2,in/y_N2,out)*y_O2,out`, and net CO2 appearance is `(y_N2,in/y_N2,out)*y_CO2,out - y_CO2,in`. Their ratio is a conditional gas-phase RQ and cancels inlet flow. The same algebra with percent numbers requires compatible common scaling; it does not prove that compatibility. A dimensionless normalized depletion can also divide the O2 expression by inlet O2, but remains subject to the tracer/basis assumptions. Changing humidity, dissolved-gas storage, headspace dynamics, calibration drift, normalization, gas switching and residence-time lag can break simple interpretations. CO2 dissolution/pH effects additionally separate outlet appearance from biological production. O2 disappearance only approaches liquid oxygen uptake with a closed, corrected gas balance and suitable accumulation assumptions; OTR additionally concerns gas–liquid transfer and cannot be independently established here. Absolute rates require qualified molar flow; per-liquid-volume rates require contemporaneous volume. Nitrogen and argon can support diagnostics, not certify the missing conditions.

For preparatory packaging, favor raw trajectories plus same-channel dimensionless profiles; keep physical formulas as explicitly conditional audit questions. This reduces setup effort while preserving source uncertainty and a concrete next step: request original instrument export/basis, flow/volume/feed/agitation histories and reconciled product sampling/harvest records before promoting mechanistic endpoints.
