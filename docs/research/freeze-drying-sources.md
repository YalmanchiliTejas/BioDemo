# Freeze-drying source acquisition and reconstruction boundary

Acquired 26 October 2026. This note supports a process-engineering demonstration, not a qualified manufacturing model. The governing product direction is [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md).

## Primary case and retained sources

Vanbillemont B, Arsiccio A, Menzen T and Hawe A (2025), *Optimization and transfer of robust primary drying protocols for biopharmaceuticals through lyophilization process modeling*, AAPS Open 11:13, published 16 June 2025. [Version of record](https://link.springer.com/article/10.1186/s41120-025-00115-5), [DOI](https://doi.org/10.1186/s41120-025-00115-5).

The full HTML and PDF, [uncertainty table](https://link.springer.com/article/10.1186/s41120-025-00115-5/tables/1), [equipment table](https://link.springer.com/article/10.1186/s41120-025-00115-5/tables/2), and [supplement](https://media.springernature.com/original/springer-static/esm/art%3A10.1186%2Fs41120-025-00115-5/MediaObjects/41120_2025_115_MOESM1_ESM.pdf) are retained in [freeze-drying-sources/](freeze-drying-sources/). The article states CC BY 4.0; the authors retain attribution and the [license](https://creativecommons.org/licenses/by/4.0/) applies subject to individual third-party credit lines. `article.txt` and `supplement-1.txt` are text extracted with pypdf; `article-readable.txt` uses BeautifulSoup; `table-*.json` preserves cell text, including source notation. These are extractions, not numeric digitizations or measurements. PDF equation rendering and Figure 5 were also visually inspected using pdftoppm. File hashes and retrieval URLs are in [manifest.json](freeze-drying-sources/manifest.json).

## What is reproducible

The publication supplies vial geometry, formulation porosity and critical temperature, final heat/mass-transfer regressions, operating points and equipment summary sufficient for a transparent **mechanistic reconstruction**. It does not supply the original implementation, complete empirical vial heat-transfer distributions or raw experimental trajectories. Its Data availability section explicitly says the experimental datasets are not public because of their proprietary format and may be requested from the corresponding author. The sole supplement is one page illustrating cake-image processing; it contains no numerical time series or missing coefficient tables. No author contact or request has been sent.

Consequently, exact reproduction of its Monte Carlo failure frequencies, its plots, or independent numerical prediction error against the actual pilot/commercial measurements is unavailable in this demonstration. Reported completion **before 50 h** is an experimental upper bound, not a measured completion time of 50 h. A model output can be checked for consistency with that bound, but an RMSE against a fabricated 50 h observation would be invalid. The reported final resistance regression uses the optimal pilot cycle itself; comparing to that cycle would additionally be a calibration check, not an independent validation. Public retrospective cases cannot establish that an LLM has never encountered their outcomes.

## Numerical inventory and provenance

Category convention: `published` means directly reported by this paper, including estimates originally obtained experimentally by its authors. `experimentally estimated` is reserved for a new local estimate from actual measurements; none were made here. `digitized` requires numerical coordinates and a documented extraction error; no curve was digitized here. Inferences, consistency repairs, replacement distributions and unmeasured receiving-site details must be `synthetic_assumption`.

| Input | Value and units | Category | Exact source and interpretation |
|---|---|---|---|
| Formulation | 10 mM Tris, pH 7.3; 225 mM sucrose; 25 mg/mL BSA; 0.01% PS20 | published | Materials, PDF p6 |
| Dried-state porosity | 0.897 | published | Materials; estimated by original authors |
| Critical interface temperature | −28 °C | published | Constraints estimations, PDF p12; freeze-drying microscopy result |
| Vial | 6R type I glass, inner diameter 20.0 mm, outer diameter 22.0 mm | published | CMAs variability; Abbreviations, PDF p18 |
| Diameter standard deviations | inner 0.13 mm; outer 0.10 mm | published | CMAs variability, PDF p11; Table 1 assumes normal distributions |
| Fill | 2.50 mL; standard deviation 0.09 mL | published | CMAs variability; gravimetric variability |
| Frozen thickness | 8.6 mm (rounded) | published | Abbreviations; prefer computing from Eq7 rather than using rounded value |
| Ice / water density | 918.0 / 1000.0 kg/m³ | published | Abbreviations, PDF p19 |
| Water molar mass | 0.01801528 kg/mol | published | Abbreviations, PDF p18 |
| Shelf / pressure variability | target ±1 °C / ±1 Pa, uniform | published | Input variability estimation; Table 1 |
| Pilot Kv coefficients | A=2.57 W/(m² K), B=2.33 W/(m² K Pa), C=0.03 Pa⁻¹ | published | CMAs variability, PDF p12; Eq9 |
| Commercial Kv coefficients | A=8.83 W/(m² K), B=0.60 W/(m² K Pa), C=0.00 Pa⁻¹ | published | Same section |
| Kv relative SD | pilot 0.151; commercial 0.110 | published | Same section; **empirical distribution**, not Gaussian |
| Final Rp coefficients | A=7.00×10³ m/s; B=2.77×10⁸ s⁻¹; C=451 m⁻¹ | published | Optimal cycle, PDF p17; Eq11 |
| Rp relative SD | 0.211 | published | Same section; Table 1 describes normal variability |
| Pilot dryer | Martin Christ Epsilon 2-10D, 4 shelves, total 0.56 m², maximum 1,028 6R vials | published | Table 2; period in `1.028` is a thousands separator |
| Commercial dryer | Martin Christ Epsilon 2-65D, 10 shelves, total 5.40 m², maximum 11,000 6R vials | published | Table 2; period in `11.000` is a thousands separator |
| Equipment arrangement | pilot duct to condenser behind chamber; commercial condenser below stoppering plate | published | Table 2 |
| Sensors | pilot 8 wireless WTM; commercial 4 wired PT100 | published | Table 2 |
| Choked-flow intercepts | pilot 0.10 kg/h; commercial 0.03 kg/h | published | Constraints estimations, PDF p13 |
| Choked-flow slopes, literal | pilot **0.33** kg/(h Pa); commercial 0.60 kg/(h Pa) | published | Same section and Abbreviations; pilot value conflicts with Figure 5 and text, see below |
| Condenser deposition capacity | pilot 0.33 kg/h; commercial 1.49 kg/h | published | Same section; pilot manufacturer specification, commercial experimentally estimated |
| Claimed regime transition | pilot ~19 Pa; commercial ~2.5 Pa | published | Same section |
| Pressure characterization range | 5–25 Pa | published | Kv characterization and process transfer sections |
| Conservative operating point | shelf −28 °C, chamber 10 Pa, about 68 h primary drying | published | Conservative cycle and Optimal cycle; detailed initial ramp below |
| Pilot optimal operating point | shelf −24 °C, chamber 8 Pa, 50 h primary drying | published | Optimal cycle, PDF p16 |
| Commercial transfer operating point | shelf −22 °C, chamber 8 Pa, 50 h primary drying | published | Process transfer, PDF p17; experimental transfer used **one full shelf**, not all 11,000 vials |
| Edge protocols | (−22 °C,6 Pa,45 h); (−25 °C,12 Pa,50 h); (−25 °C,6 Pa,50 h) | published | DSp verification, PDF pp13–15; sequential Rp fitting means these are not independent of final calibration |
| Empirical Kv replacement | e.g. lognormal or Gaussian matched only to reported moments | synthetic_assumption | Full empirical CDF unavailable; must disclose replacement and cannot reproduce tail risk |
| Pilot flow slope consistency repair | (0.33−0.10)/19 = 0.0121053 kg/(h Pa) | synthetic_assumption | Algebraic reconstruction from stated transition and plateau; **not a source value or digitization** |
| One-shelf commercial load | 1,100 vials if inferred as maximum/10 | synthetic_assumption | Exact experimental load count not explicitly reported; equal shelf allocation is an inference |
| Local site names, revisions, utilities, degraded capacity, parameter shifts, cutoff, sensor noise | scenario-specific | synthetic_assumption | No geographic or facility utility characterization supplied by paper |

The conservative cycle's reported freezing ramp is 1 °C/min to −45 °C followed by 2 h hold. Primary drying starts with 30 min vacuum ramp to 10 Pa at −45 °C, then shelf ramp at 1 °C/min to −28 °C, held for 67 h. Secondary drying subsequently ramps 0.12 °C/min to 30 °C and holds 8 h. Those later stages are outside a primary-drying-only model. If optimization runs are approximated with constant controls from t=0, label that schedule simplification explicitly.

## Equations, units and source conflicts

The paper gives a quasi-steady vial heat/mass balance in Eqs1–7, pressure-dependent vial heat transfer in Eq9 and evolving dried-layer resistance in Eq11:

```text
Kv(Pc) = A_Kv + B_Kv Pc / (1 + C_Kv Pc)
Rp(Ld) = A_Rp + B_Rp Ld / (1 + C_Rp Ld)
mdot = Ap [Pice(Ti) - Pc] / Rp(Ld)             [kg/s]
q = Av Kv (Ts - Tb) = mdot Hsub(Ti)/M         [W]
Tb = Ti + DeltaT
dLd/dt = mdot / (rho_ice porosity Ap)         [m/s]
Lt = Vfill [(1-porosity)+porosity rho_water/rho_ice] / Ap
```

All lengths must be in metres, areas in m², pressure in Pa, time in seconds and temperatures in kelvin inside material equations. Resistance m/s gives the mass flux units above. Hsub is **molar** J/mol in this paper and must be divided by molar mass for J/kg. Integrate only while ice remains; remove dried vials from sublimation and temperature-risk statistics. Observed probes measure the bottom and subsequently dried product, not directly the sublimation interface.

**Pressure equation error:** Eq2 lacks the exponential in both HTML and the actual PDF p4. Its printed RHS yields ln(P/Pa), not P. [Murphy and Koop (2005), Eq7](https://patarnott.com/atms360/pdf_atms360/class2017/VaporPressureIce_SupercooledH20_Murphy.pdf), DOI [10.1256/qj.04.94](https://doi.org/10.1256/qj.04.94), explicitly gives:

```text
Pice = exp(9.550426 - 5723.265/T + 3.53068 ln(T) - .00728332 T) Pa
Hsub = 46782.5 + 35.8925 T - .07414 T² + 541.5 exp(-(T/123.75)²) J/mol
```

These are the primary source's Eqs7 and5 respectively, with T in kelvin (pressure formula T>110 K). The 2025 paper rounds some constants, printing 5723.2658 rather than 5723.265 and rounded latent-heat constants. Choose and version the coefficients; do not silently claim an exact transcription. At 273.15 K the vapor pressure is about 611 Pa, which is a useful implementation check.

**Pilot flow coefficient conflict:** literal `min(.10 + .33 Pc, .33)` reaches the condenser plateau at 0.697 Pa. The article instead says the pilot transition is 19 Pa. Figure 5B, visually inspected, plots shelf-area-normalized capacity with pilot plateau approximately 0.59 kg/(m² h), consistent with 0.33 kg/h /0.56 m². Therefore changing the condenser limit to 6.37 kg/h to accommodate the literal slope would contradict the plot. The commercial coefficients yield transition (1.49−.03)/.60=2.43 Pa, consistent with the reported 2.5 Pa. Retain the literal pilot coefficients and flag the contradiction, or use the explicitly labeled reconstructed pilot slope above. Neither choice constitutes exact reproduction. Get author clarification or equipment characterization before engineering use.

**Uncertainty:** the original study sampled 4,096 vials; nominal integration step was predicted duration/500. Those are original numerical settings, not a requirement or validation for a new solver. The empirical Kv distribution is skewed and bimodal, with edge-vial tailing, so replacing it by a normal distribution cannot recover the reported 0.1% boundary. A 16- or 32-sample demonstration does not have resolution to estimate such a small frequency. Label Monte Carlo frequencies as outcomes under chosen parameter distributions, never as calibrated manufacturing failure probabilities.

## Published observations available only as summaries

The paper reports safe temperature and completion before 50 h for the optimal transfer run, pressure control in that run, a 26% reduction in selected pilot primary-drying duration (68 to50 h), and measured cake appearance and residual water after the full cycle. These are the authors' experimental findings, not new BioDemo results. Residual moisture and cake measurements are not predicted by a model that merely removes primary-drying ice. The commercial design space beyond the selected normal operating range was not fully experimentally verified. No commercial yield, potency, avoided failures, energy consumption or local process qualification can be inferred from this demonstration.

## LyoPRONTO inspection and dependency decision

Inspected [LyoHUB/LyoPRONTO](https://github.com/LyoHUB/LyoPRONTO) at commit **c6a9225a9e551ae4e7c11c1ef056b67c6204afbd**, retrieved 26 October2026. Its [pinned package metadata](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/pyproject.toml) declares version1.2.0, Python≥3.8, and NumPy, SciPy, Matplotlib and ruamel.yaml dependencies; development status Beta. The [pinned README](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/README.md) documents `read_inputs(yaml_path)`, `execute_simulation(inputs)`, `save_inputs`, `save_csv` and `generate_visualizations`; these exports were verified in its package initializer. It includes freezing, known/unknown resistance calculations, design-space and shelf/pressure optimization modules. This makes it a relevant research reference, but it is a different implementation rather than the authors' 2025 source code.

The [license](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/LICENSE.txt) and package metadata are **GPL-3.0-or-later**. The README offers LGPL distribution only upon separate request and permission; that is not an automatically granted alternative license. The focused demonstration should implement the published equations independently rather than copy or import its code under an assumed permissive license. Retained README/license/metadata are research artifacts only; implementation source was inspected without vendoring it. Application code must not import those artifacts. No claim of scientific qualification follows from use of this package or from qualification of an LLM route.

## Next evidence to obtain

1. Obtain the raw pilot/commercial temperature and comparative-pressure trajectories plus exact batch loading and timing from the corresponding author in an interoperable format; freeze an independent holdout before calibration.
2. Clarify the pilot choked-flow slope and obtain actual receiving-dryer minimal-controllable-pressure and condenser deposition tests.
3. Characterize receiving-site Kv by loss-in-weight at several calibrated pressures and retain per-vial empirical distributions, especially edge vials.
4. Verify critical formulation temperature and Rp for the actual formulation/freezing protocol; do not apply BSA/sucrose coefficients to another drug without evidence.
5. Execute an instrumented transfer verification with prespecified thermal, pressure-control and endpoint criteria and qualified reviewers; assess final product attributes experimentally after the full cycle.
