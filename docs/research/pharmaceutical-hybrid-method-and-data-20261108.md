# Hybrid method and independent experimental data

Research date: 2026-11-08. Scope: establish what DOI 10.1002/bit.70385 actually does, and identify experimental evidence compatible with existing BioDemo models. No model training, inference, installation, or manufacturing operation was performed for this note.

## Published method

[Al-Ramadhan et al., sections 2–3](https://analyticalsciencejournals.onlinelibrary.wiley.com/doi/10.1002/bit.70385) describe:

- Bounded ODE-constrained normalized least squares; TVPs have an additional squared adjacent-interval difference penalty and change every eight hours, estimated separately per laboratory experiment.
- An ANN maps biomass, glucose, carotenoids, astaxanthin and feed concentration × feed/volume to TVPs; time is excluded. The simple backbone learns four TVPs with 24/16 hidden units; the complex backbone learns three with 12/8 units.
- Original observations are split before Gaussian augmentation; five-fold validation is reported. Original experimental counts are 41 laboratory observations, 17 pilot, 17 industrial. Augmentation does not create independent experiments.
- Pilot TVPs are re-estimated within source-informed bounds. ANN adaptation penalizes absolute changes in source weights/biases; selected transfer penalty is 0.01. Pilot fitting precedes industrial prediction.
- Ensemble spread estimates hybrid uncertainty; it is not demonstrated calibrated coverage. Fixed-parameter uncertainty uses identifiability screening and local Hessian covariance.
- Raw supporting data require reasonable request to the corresponding author. The article alone supplies no downloadable trajectories or complete reproduction package.

Implementation implication: time-indexed interpolation or constant parameter calibration alone cannot be described as implementing the state-dependent neural mapping. Missing observations must not be supplied as invented measured states.

## Existing model fit and methodological boundaries

The inspected [fermentation model](../../backend/src/lifesci/fermentation/model.py) implements kLa/power scaling and pressure/oxygen/cost characterization. It explicitly has no organism kinetics or validated yield/viability model. Its current source exponent uses two rounded published summaries with zero residual degrees of freedom. A neural correction to its transport relationship is an **algebraic transport hybrid**, a deliberate departure from the paper's kinetic ODE/TVP procedure. Biomass/glucose/product data cannot directly validate this existing model.

The inspected [chemical model](../../backend/src/lifesci/chemical_reactor/model.py) implements constant-volume A→B and A→I, irreversible first-order 1:1 pathways, Arrhenius rates and a lumped thermal balance. Learning bounded positive rate multipliers inside those balances preserves their configured mathematical conservation; it does not establish the reaction mechanism or thermal validity experimentally. No directly compatible independently measured A/B/I and thermal/coolant dataset was verified in this search. Generic aldol, combustion or cell-culture datasets must not be relabeled into those observables.

## Usable public oxygen-transfer data

**Verified public download:** [Rautenbach, DaRUS dataset 10.18419/DARUS-5953, V1](https://doi.org/10.18419/DARUS-5953). It supplies experimental oxygen-transfer and torque data; metadata describes dynamic gassing-out analysis over 20–80% saturation and power from torque/speed. Data are CC BY 4.0; software is MIT. This is independent of BioDemo's Sulfolobus literature case, but does not establish independent sites or scales.

Original files now preserved locally:

- [CSV](../../backend/src/lifesci/fermentation/data/oxygen_transfer_darus_5953.csv): original BOM, semicolons and CRLF bytes preserved. [Direct source](https://darus.uni-stuttgart.de/api/access/datafile/532318). SHA-256 `c3081221da4aee0bbbe2b4e2605372b25ddb467ba1f469850d57da9809fd278c`; MD5 matches repository `3dfc246e8d9bce26e4caddca0762370a`.
- [Provenance](../../backend/src/lifesci/fermentation/data/oxygen_transfer_darus_5953.provenance.json): source URLs, citation, license, hash, retrieval time, original dataset metadata blocks and selected file records, unit evidence, grouping and limits.

The [downloaded summary CSV](https://darus.uni-stuttgart.de/api/access/datafile/532318) has six operating-condition rows: 0.05/0.15 vvm × 100/200/300 rpm. Four configuration prefixes each provide `*_avg`, `*_std`, and `*_P_V`: `RT_RT_co_current`, `RT_PBT_co_current`, `RT_RT_counter_current`, `RT_PBT_counter_current`. Wide-to-long conversion yields 24 configuration/condition means, **not 24 independently established batches**. Keep every mean and its standard deviation together; the standard deviation is not a second sample or a standard error.

Author [analysis code `RR_van_riet.py`](https://darus.uni-stuttgart.de/api/access/datafile/532620) confirms working volume 30 L, reactor diameter 0.289 m, kLa in h⁻¹, P/V in W/m³, and a separate Van't Riet fit per configuration. Thus:

```text
read with encoding=utf-8-sig, delimiter=;
kla_h_inv = <configuration>_avg
kla_reported_sd_h_inv = <configuration>_std
power_w_m3 = <configuration>_P_V
airflow_l_min = vvm * 30
power_kw_m3 = power_w_m3 / 1000
V_m3 = 30 / 1000
gas_m3_s = vvm * V_m3 / 60
superficial_gas_velocity_m_s = gas_m3_s / (pi * 0.289**2 / 4)
```

The [configuration README](https://darus.uni-stuttgart.de/api/access/datafile/532635) explains IDs and repeats, including that `_3` denotes a third experiment. The [dataset API](https://darus.uni-stuttgart.de/api/datasets/:persistentId/?persistentId=doi:10.18419/DARUS-5953) lists trial-labelled processed workbooks and raw measurement files. These support actual repeat measurements, but this research did not reconstruct the exact replicate count or dependence underlying each published mean. Do not invent run identifiers or calculate independent-replicate confidence intervals from the summary.

Numeric impeller diameter/spacing, complete fluid properties and temperature were not verified from the summary or inspected code. Retain configuration labels as published categorical arrangements; do not fabricate geometric features. One 30 L apparatus cannot establish a learned volume effect or real scale-up accuracy. Measured P/V can assess a kLa-versus-P/V relationship, but does not independently validate BioDemo's geometry-based P/V prediction.

## Experimental calibration and evaluation requirements

These are proposed design requirements, not claims about achieved performance:

1. Preserve original observations and hashes; record each conversion and actual configuration/operating-condition key. Count observed means and source trials separately.
2. Freeze calibration/holdout groups before fitting. Keep all derived values and augmentations of a shared original observation in the same fold. A complete configuration holdout assesses arrangement transfer within one apparatus; a complete condition holdout assesses operating-condition prediction. Neither establishes scale-up.
3. Compare a constant multiplier and a simple log-linear transport correlation with the ANN correction. Twenty-four summary points provide little support for a large network or a highly flexible geometry model. Source-informed bounds and regularization must be selected without consulting held-out targets.
4. Learn a bounded positive kLa correction only from measured kLa. Do not pass measured held-out kLa, its uncertainty, or future outcomes as input features. Keep measured P/V distinct from P/V predicted by the existing equipment algebra.
5. Report MAE in h⁻¹, grouped errors and bound/failure counts. Treat uncertainty coverage as unvalidated until tested on independent observations. Include both improvement and deterioration relative to the uncorrected model.
6. Real receiving-site calibration still needs sufficiently varied, characterized receiving observations. This public experiment can support a narrow transport check; it cannot validate organism kinetics, product yield, clinical/API quality, plant safety or regulatory compliance.

The simple option is a transparent, bounded constant correction with an explicit applicability limit. The ambitious option adds state/condition-dependent neural correction and grouped validation. The trade-off is additional fitting and review burden against flexibility that this small dataset may not justify. Easy to Start means reusing source bytes/mappings; Easy to Trust means preserving measured/model distinctions; Easy to Act means a reviewable characterization experiment; Easy to Adopt means retaining the existing adapter and evidence interfaces. Measure preparation/review effort and held-out errors, not just training fit.

## Other accessible data and exclusions

[CHO-K1 dataset 10.5281/zenodo.20829178](https://zenodo.org/records/20829178) is openly listed with a downloadable 227.6 MB archive of 24 cultures, raw Excel files and aligned CSVs. It is suitable for a separately specified cell-culture model. It is not direct kLa/power or A/B/I thermal validation. Preserve original measurement timestamps if used; aligned values are processed data. This dataset has already been used elsewhere in this repository, so it should not be presented as newly untouched evidence.

[MORF000175](https://morf-db.org/projects/My-Projects/MORF000175) did not expose usable data through the fetched public HTML; no file accessibility or usable schema was established here. The DOI paper's own data remain request-only. No inaccessible or incompatible source has been counted as a completed real-data validation.
