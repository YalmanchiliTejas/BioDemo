# Pharmaceutical model library: executable baseline release

**Scope:** 16 new reduced models across seven additional workstreams, plus reuse
of existing batch reaction, fermentation, CHO and freeze-drying code. This release
provides learning and model-development coverage, not every pharmaceutical mechanism
or experimentally qualified digital twins.

Open [the all-models notebook](02_pharmaceutical_model_library.ipynb). Detailed
inputs, units, equations and limitations are in [the model passports](CATALOG.md).

## Run the entire library today

After applying the supplied patch to BioDemo, from `backend/`:

```sh
python -m pip install -e '.[process-demo]'
python -m src.lifesci.process_models examples --output /tmp/pharma-models-01
python -m src.lifesci.process_models list
python -m unittest discover -s tests/lifesci -p test_process_model_library.py -v
python -m unittest discover -s tests/lifesci -p test_chemical_reactor.py -v
```

The examples command writes all input packages, full result receipts, a manifest,
an overview figure, shared calibration/site-comparison examples, and a connected
purification-train assessment. Use a new output directory for each run.
No agent, provider account or API inference is involved.

Run one model or use the supplied example requests:

```sh
python -m src.lifesci.process_models run powder.two_bin_mill /tmp/pharma-models-01/inputs/powder.two_bin_mill.json --output /tmp/mill-02.json
python -m src.lifesci.process_models fit /tmp/pharma-models-01/calibration-request.json --output /tmp/fit-02.json
python -m src.lifesci.process_models compare /tmp/pharma-models-01/comparison-request.json --output /tmp/comparison-02.json
```

`sensitivity` accepts a JSON request with `model_id`, `config`, `parameter`, explicit
`values`, and top-level output `metrics`. Failed scenarios remain in the result.

## Coverage and boundaries

| Family | Executable coverage | Type | What it cannot establish |
|---|---|---|---|
| Chemical synthesis | Semi-batch fed reaction, feed enthalpy/volume; existing batch model | Conservation + assumed reaction kinetics | Arbitrary chemistry, solvent phases or mixing limitations |
| Crystallisation | Prescribed cooling, nucleation/growth, four population moments | Reduced mechanistic | Full PSD, polymorphs, agglomeration, dissolution or chiller feasibility |
| API isolation | Constant-pressure filtration, mixed-pore wash and lumped solvent drying | Mechanistic/semimechanistic | Cake compressibility, channeling, solvent/temperature spatial fields |
| Powder processing | Continuous blender, two-bin mill and constant-kernel granule aggregation | Ideal balances/lumped kinetics | Individual-dose uniformity, segregation or full granule PSD |
| Tablets | Heckel density/empirical strength, coating mass, shrinking-area dissolution | Empirical and reduced mechanistic | Dwell-time/capping, coat uniformity, bioequivalence or a validated process-to-dissolution link |
| Downstream biologics | Batch equilibrium capture, ideal UF and constant-volume DF | Equilibrium/material balances | Dynamic chromatography, competition/purity, membrane fouling or protein damage |
| Equipment/utilities | Turbulent impeller power and gas-load pump-down | Restricted engineering screens | CFD/local shear, gas dispersion, real pump curves or shared utilities |
| Existing families reused | Batch reactor, fermentation characterisation, freeze-drying | Existing implementations | Their prior validation limits continue to apply |

Do not describe an empirical compaction relation as a physics-complete tablet twin,
a resin equilibrium screen as a chromatography-column model, or a two-bin model
as a full particle distribution. Those distinctions are reflected in result metadata.

## Shared scientific foundation implemented

- Explicit SI field names, required parameters and evidence labels; no silent scientific defaults.
- A model passport identifies equations, units, model kind, scope and required inputs.
- Existing ModelCatalog discovers each new family; no new agent harness or record store.
- Shared curve fitting: one scalar at a time, explicit bounds, training/later holdout split,
  source references and local sensitivity diagnostics. It supports time/pressure curves;
  scalar equilibrium/equipment screens require separate multi-experiment fitting.
- Site comparisons report actual changed inputs and differences; incomplete endpoints stay null.
- Explicit parameter-scenario sweeps preserve failures and do not claim calibrated probabilities.
- Connected crystallisation -> filtration -> washing -> drying with checked mass handoffs,
  API-loss accounting and downstream blocking after an incomplete upstream operation.
- Existing fermentation/freeze-drying are executed through their original calculation code.
  External PenSim/SMPL workers are inventoried but not provisioned or executed in this release.

The purification train assumes shared material identity and supplied solvent density/holdup.
It tracks crystal-derived API separately from dissolved mother-liquor API. It does not
invent reprecipitation, final assay purity or a chemistry-to-crystallisation bridge.
In the supplied connected example, the numerical stages complete but the residual-solvent
target is missed; final isolated API is therefore withheld. This is an intentional visible
assessment outcome, not a silently accepted complete transfer.

## Learn all families without waiting for a serial course

The notebook lets you execute every family immediately. Use the same questions for each:

1. What inventory or relationship is represented? Which part is conservation versus assumption?
2. Which inputs describe the material, equipment and operating recipe?
3. What actually changes between sites? Which coefficient needs a new experiment?
4. Does a limiting case produce the expected result? Does the relevant inventory close?
5. What unrepresented mechanism could invalidate the prediction?

Compare filter area, membrane area, blender holdup and reactor volume in separate exercises.
Then inspect the integrated purification train to see why independent unit-operation
yield percentages cannot simply be multiplied without compatible material bases.

## Commercial-readiness gates

| Gate | Current evidence | Required next evidence |
|---|---|---|
| Executable model coverage | Authored input package and executed example per new model | Expand only within an identified customer's intended use |
| Numerical verification | Limiting cases, inventories, stop conditions, fitting leakage and integration checks | Additional boundary/numerical convergence checks for actual intended conditions |
| Experimental calibration | Synthetic teaching data only for the new models | Independent kinetics, property and equipment characterisation with units/uncertainty |
| Receiver prediction | Conditional equipment/input comparisons | Precommitted predictions on withheld receiver experiments |
| Uncertainty | Explicit scenario sensitivity only | Parameter/measurement uncertainty plus structural discrepancy and coverage checks |
| Product/quality decision | Defined model outputs and failure states | Product-specific assay/impurity/quality criteria and process-expert review |
| Operational twin | No online updating/deployment added | Validated sensors/state updates, existing evidence/permissions and controlled model changes |
| Workload reduction | Not measured | Observed matched preparation, analysis, review and correction effort |

Each customer's process needs a reviewed intended-use decision and model applicability
assessment. Public equations and passing numerical tests do not establish transferable
accuracy, safety, GMP validation or yield noninferiority.

## Hybrid modelling and the paper

The library supplies the physical baselines, fitting and comparison surfaces. A separate,
opt-in hybrid layer now exists for two adapters: bounded learned rate multipliers in
`chemical.parallel_batch` and a bounded kLa multiplier in `fermentation.oxygen_transfer`.
It includes source-to-receiver adaptation with negative-transfer detection, solver-propagated
ensembles and a separate split-conformal calibration step. Every other adapter reports that
hybrid adaptation is unsupported. Adding a neural network to every family by default would
not establish general transferability.

This layer has been exercised only on synthetic data. It does not reproduce the yeast
transfer study, and its intervals stay `uncalibrated` until independent measured batches
exist. Read [HYBRID_AND_UNCERTAINTY.md](HYBRID_AND_UNCERTAINTY.md) and run
[notebook 03](03_hybrid_adaptation_and_uncertainty.ipynb).

## Sources and reuse

- PharmaPy unit-operation documentation: https://pharmapy.readthedocs.io/en/latest/docstrings/unit_operations.html
- Integrated purification study: https://pmc.ncbi.nlm.nih.gov/articles/PMC11225065/
- Particulate modelling context: https://doi.org/10.3390/pr1020067
- Tablet flowsheet context: https://doi.org/10.3390/pr7040234
- Dissolution modelling study: https://pubmed.ncbi.nlm.nih.gov/16421665/
- Manufacturer diafiltration guide: https://www.merckmillipore.com/deepweb/assets/sigmaaldrich/product/documents/272/805/rf1159en-ms.pdf
- Hybrid transfer paper: https://doi.org/10.1002/bit.70385

These sources provide modelling context. The new equations are small transparent
implementations of stated balances/closures, not numerical reproductions or extracted
parameter sets from those papers. All new example parameter values are authored synthetic
assumptions; no upstream code was copied into this library.

## Engineering decision

Job: broad modelling coverage today with inspectable equations for a beginner and reusable
configuration boundaries for later customer work. A small common model contract and
restricted reduced models were selected over installing a large flowsheet/CFD stack.
This is easier to run and verify, but sacrifices spatial resolution and broad physical scope.
Existing source/evidence ownership, human approvals and manufacturing systems are unchanged.
No scientific result is published as a qualified customer recommendation.

For review, judge preparation and verification effort, not model count alone. Commercial
onboarding should bind this calculation layer to the existing evidence and review services.
