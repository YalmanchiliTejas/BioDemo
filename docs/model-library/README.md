# Learn and develop pharmaceutical process models

For the complete multi-family baseline, open [the library overview](LIBRARY.md) and
[the all-models notebook](02_pharmaceutical_model_library.ipynb).
The [reactor learning notebook](01_jacketed_reactor.ipynb) remains the detailed first-principles lesson.
For neural hybrid terms, site adaptation and interval calibration, read
[HYBRID_AND_UNCERTAINTY.md](HYBRID_AND_UNCERTAINTY.md) and run
[notebook 03](03_hybrid_adaptation_and_uncertainty.ipynb).
Run it from a local BioDemo checkout in Jupyter, VS Code or another notebook editor.
It discovers the checkout root and imports the same backend module used by the CLI.

## What has been built

An experimental, transparent constant-volume chemical batch reactor with competing
desired-product and impurity pathways. It adds a chemical model family alongside
existing fermentation, CHO and freeze-drying work; it does not replace them.

| Component | Status |
|---|---|
| Material/energy balances and Arrhenius rates | Implemented and numerically checked |
| Temperature-limit termination; final yield withheld after termination | Implemented |
| Donor/receiver comparison and explicit absolute yield-loss tolerance | Implemented deterministic screen |
| Temperature-based U or product-rate fitting; cutoff/later holdout separation | Implemented; synthetic exercise only |
| One-at-a-time sensitivity | Implemented; not a statistical uncertainty interval |
| Existing ModelCatalog registration | Implemented under `chemical_batch_reaction` |
| Existing agent/UI, platform evidence persistence and approvals | Connected through the model-library service; see [HYBRID_AND_UNCERTAINTY.md](HYBRID_AND_UNCERTAINTY.md) |
| Real reaction/property/receiver validation | Not done |
| Hybrid neural rate model and source-to-receiver adaptation | Implemented, experimental; synthetic checks only ([notebook 03](03_hybrid_adaptation_and_uncertainty.ipynb)) |
| Interval calibration | Implemented; stays `uncalibrated` until independent measured batches exist |
| Online state updates or deployed digital twin | Not implemented |

## Today: learn the model (about 3–4 hours, at your pace)

1. **Understand the balances.** Work through notebook sections 1–3. Explain why a
   large vessel needs its own heat-removal characterisation, and why higher
   conversion is not necessarily higher desired-product yield.
2. **Run and challenge.** Plot donor/receiver temperature, product and impurity.
   Change one equipment property at a time. Explain the thermal stop rather than
   treating partial-run yield as a forecast.
3. **Fit a parameter.** Estimate U from the provided synthetic temperatures. Alter
   the holdout rows: the fitted value must stay unchanged, while forecast error changes.
4. **Write your interpretation.** Which fact would you measure before trusting a
   receiver prediction? Why is fitting temperature insufficient to validate product yield?

For the scripted exercise, from `backend/`:

```sh
python -m pip install -e '.[process-demo]'
python -m src.lifesci.chemical_reactor.demo --output /tmp/reactor-learning-01
python -m unittest discover -s tests/lifesci -p test_chemical_reactor.py -v
```

Use a new empty output directory for each run. Outputs include a report, plots,
JSON receipts and the synthetic observations. No provider account or inference is needed.
To open the notebook, install Jupyter in your development environment if needed.

## Equations and assumptions

The illustrative chemistry is `A -> B` and `A -> I`; both are irreversible,
first-order, one-to-one molar pathways. B is desired product, I is impurity.

`rB = kB(T) NA`, `rI = kI(T) NA` (mol/s).

`dNA/dt = -rB-rI`; `dNB/dt=rB`; `dNI/dt=rI`.

`rho V Cp dT/dt = (-dHB)rB + (-dHI)rI - U Aht (T-Tcoolant)`.

`k(T) = kref exp[-Ea/R (1/T - 1/Tref)]`.

Negative reaction enthalpy denotes an exothermic reaction. U is an effective,
measured/fitted coefficient in W/(m² K), not a knob that the equipment can necessarily
achieve. Area is the effective wetted heat-transfer area at the working volume.
The coolant boundary is prescribed, not evidence of available utility capacity.

The example conserves A-equivalent moles. Real material balance requires actual
stoichiometry, molecular weights, density changes and any feeds/losses. All example
kinetics, properties, limits and geometry are authored synthetic assumptions.
No drug, chemistry, cooling rating or published experimental outcome is represented.

Desired-product yield is `NB/NA0`; impurity is `NI/NA0`; conversion is `1-NA/NA0`.
The screen's 0.02 tolerance is **two absolute yield percentage points**, not a 2%
relative decrease and not an empirically justified commercial acceptance criterion.
Numerical input ranges are guardrails, not physical validation domains.

## Reusable model passport

| Item | Contract |
|---|---|
| Inputs | Chemistry, equipment, recipe, evidence classification and source references |
| Measured/calibrated site terms | Working volume, wetted area, effective U, coolant boundary |
| Chemistry terms | Temperature-dependent rates, enthalpies, density, heat capacity |
| Outputs | Temperatures, conversion, desired-product molar yield, impurity and violations |
| Fit scope | U and/or desired-product kref within supplied bounds; other properties held fixed |
| Missing physics | Imperfect mixing, diffusion, feed dynamics, solvent evaporation, jacket/chiller dynamics, phase changes |
| Numerical evidence | Closed-form isothermal chemistry, no-reaction cooling, adiabatic energy balance, stop/partition tests |
| Experimental evidence | None supplied |
| Permitted use now | Learning, model development, explicitly conditional simulation studies |

Temperature fitting alone can confound heat transfer, kinetics, heat of reaction and
sensor response. A full-rank local fit Jacobian does not prove global identifiability.
No fitted U is automatically approved for another batch or site.

## Your path to customer readiness

| Gate | You need to do | Evidence required before claiming completion |
|---|---|---|
| 1. Scientific scope | Pick one customer's operation and decision; agree yield, quality and acceptable loss | Reviewed intended-use and metric definitions |
| 2. Material/equipment package | Obtain reaction/concentration histories, calorimetry, coolant/reactor temperatures, working volume, area and instrumentation details | Source-linked inputs; explicit missing facts and units |
| 3. Calibration | Fit only identifiable terms using designated donor/characterisation runs | Fit diagnostics, parameter bounds, residuals and measurement uncertainty |
| 4. Independent prediction | Freeze the model and predict separate runs and receiver conditions | Product/impurity assays plus temperature trajectories; predeclared error/constraint criteria |
| 5. Uncertainty | Test parameter uncertainty, structural mismatch and interval coverage | Independent coverage/error evidence; include failed/incomplete predictions |
| 6. Workflow pilot | Compare manual work with assisted preparation/calculation/review | Observed total engineer hours, corrections and comparable reviewed quality |
| 7. Deployment | Connect versioned evidence, permissions, approval and operating ownership | Intended-use qualification, customer review and controlled change process |

No universal number of batches or universal accuracy threshold is asserted here.
Set the required evidence with a qualified process expert for the particular decision.
The module intentionally contains no live equipment or manufacturing write path.

## Grow the library without building everything at once

| Order | Family | Reuse | Learn/build next |
|---|---|---|---|
| Now | Chemical batch reaction | This module, SciPy and existing catalogue | Balances, calibration, independent checks |
| Added baseline | Semi-batch reaction | Rate/energy components | Feed species/enthalpy and changing volume; wetted area remains prescribed |
| Added baseline | Mixing/utility characterisation | Equipment configuration and site comparisons | Turbulent power and ideal vacuum; geometry applicability needs measurements |
| Added baseline | Crystallisation | Balances and fitting discipline | Cooling growth/nucleation and population moments |
| Added baseline | Filtration/washing/drying | Property/equipment contracts | Cake resistance, wash loss and lumped solvent drying; explicit mass handoffs |
| Added baseline | Oral solid dose | Same validation/evidence discipline | Ideal blending, lumped milling/aggregation, empirical compaction, coating and dissolution |
| Continue | Fermentation/freeze-drying | Existing implementations | Extend calibration/validation, not rebuild |

For learning, implement a small equation set yourself. For customer work compare
against suitable established implementations rather than assuming your new code is superior.

## Where the hybrid paper fits

After the physical baseline can be fitted and independently tested, investigate whether
an uncertain rate needs a learned state-dependent correction. Keep balances intact,
constrain learned rates, adapt with receiver measurements, and compare against a simple
mechanistic refit at equal data budgets. A neural correction cannot identify missing
chemistry or equipment behaviour without informative data.

This reactor now has that layer: bounded learned rate multipliers inside the unchanged
balances, whole-batch partitions, adaptation with negative-transfer detection, and a
separate interval-calibration step. [HYBRID_AND_UNCERTAINTY.md](HYBRID_AND_UNCERTAINTY.md)
explains it and lists the departures from the paper. It has been exercised only on
synthetic data and does not reproduce the paper's yeast results.

## Engineering decision and trade-off

Job: help a beginner understand a transfer-relevant model while preserving a reusable
scientific component. A small explicit solver plus notebook was selected over a broad
flowsheet framework or new agent/UI: easier to start and audit, but initially narrower.
Existing ModelCatalog and content hashes are reused. The standalone module itself writes
nothing to platform stores; product use goes through the model-library service, which
records configurations, datasets and results as evidence. Calculations cannot become approvals. Customer deployment must
use existing evidence/action services, not a second system of record.
Measure time to first understood result during learning; measure preparation, review,
correction and experiment effort during a customer pilot. Neither is measured by this build.

## Sources for further study

- SciPy ODE solver: https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html
- SciPy bounded fitting: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html
- Modular process modelling: https://idaes-pse.readthedocs.io/en/stable/explanations/concepts.html
- PharmaPy: https://pharmapy.readthedocs.io/en/latest/
- Hybrid/transfer-learning paper discussed: https://doi.org/10.1002/bit.70385

Sources describe methods/tools; they do not supply this exercise's synthetic chemistry.
