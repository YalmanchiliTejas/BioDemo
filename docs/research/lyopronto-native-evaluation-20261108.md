# Native LyoPRONTO agent evaluation: source audit and proposed protocol

Research date: 2026-11-08 (UTC). Proposal, not an executed agent evaluation. No inference, publication, or equipment action was performed for this note.

## Decision and intended use

Evaluate whether our agent can use **Purdue LyoHUB LyoPRONTO correctly to deliver a reviewable primary-drying calculation or recipe recommendation**. The evaluator's numerical world is the pinned upstream model, in its native units. This replaces the evaluation design; it is not another tool arm inside the old synthetic benchmark and is not a comparison of BioDemo simulation accuracy with Purdue. A pass establishes bounded tool-use performance, not experimental accuracy, product safety, or manufacturing authorization.

The existing `benchmarks/lyohub_study/README.md` explicitly reuses the original public synthetic cases and separately executed BioDemo reference. That design answers a different question and should remain historical. Do not reuse its synthetic parameter conversion, remaining-ice calibration target, hidden population shifts, simulator-comparison arms, or reference scorer in the new evaluation.

Start with finite candidate recipe selection and correct calculation, then add continuous optimization as a separately qualified task. This is simpler and more auditable than claiming globally optimal dynamic profiles from an optimizer whose failure status is not consistently surfaced. The trade-off is a narrower initial optimization claim. It satisfies the governing principles jointly: existing native YAML reduces setup; pinned inputs and outputs aid verification; a concrete constrained recommendation is actionable; a read-only tool boundary preserves existing records and approvals. Measure manual input requests, unsupported claims, reviewable successful decisions, tool/runtime effort, and recovery from incomplete evidence. Do not substitute UI clicks or token count for task success.

## Primary sources and pin

Inspect and execute only `LyoHUB/LyoPRONTO` commit `c6a9225a9e551ae4e7c11c1ef056b67c6204afbd`, audited locally at `/private/tmp/lyohub-rerun-source`. Its package declares version 1.2.0 and broad minimum dependencies; a reproducible benchmark must additionally lock Python/NumPy/SciPy/ruamel.yaml versions and retain source and environment hashes. Upstream licensing is GPL-3.0-or-later; preserve attribution and license when distributing upstream software. [Pinned package metadata](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/pyproject.toml), [official repository](https://github.com/LyoHUB/LyoPRONTO).

The original paper describes distinct freezing and primary-drying calculators, parameter estimation, design space, and optimization. The freezing model is lumped-capacitance; primary drying is quasi-steady heat/mass transfer. Published comparisons concern the authors' experiments and historical implementation, not validation of this pinned software on a new benchmark. The paper's experimentally observed nucleation/freezing temperatures are required freezing inputs, not primary-drying holdout measurements. [Original authors' article](https://link.springer.com/article/10.1208/s12249-019-1532-7).

## Exact native inputs and outputs

`lyopronto.execute_simulation(inputs)` accepts a Python dictionary, with YAML loading through `read_inputs`. There is no general input validator providing a documented scientifically valid operating envelope. Use a strict benchmark adapter schema before calling upstream. The adapter must not silently supply missing product or equipment facts. [Dispatcher](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/high_level.py), [native input specification](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/docs/yaml_inputs.md).

The known-Rp forward mode requires:

```yaml
sim: {tool: Primary Drying Calculator, Kv_known: true, Rp_known: true}
vial: {Av: 3.8, Ap: 3.14, Vfill: 2.0}
product: {cSolid: 0.05, R0: 1.4, A1: 16.0, A2: 0.0}
ht: {KC: 0.000275, KP: 0.000893, KD: 0.46}
Pchamber: {setpt: [0.15], dt_setpt: [1800.0], ramp_rate: 0.5}
Tshelf: {init: -35.0, setpt: [20.0], dt_setpt: [1800.0], ramp_rate: 1.0}
dt: 0.01
```

This is the upstream example, not a validated commercial process. `vial.Av` and `Ap` are cm²; `Vfill` is mL; `cSolid` is documented g/mL; R0 is cm²·hr·Torr/g, A1 cm·hr·Torr/g, A2 cm⁻¹. `KC` is cal/(s·K·cm²), `KP` cal/(s·K·cm²·Torr), `KD` Torr⁻¹. Pressure inputs are **Torr**, durations **minutes**, temperature **°C**, time step **hours**. `Kv = KC + KP*P/(1+KD*P)` and `Rp = R0 + A1*L/(1+A2*L)`. Some test comments give inconsistent units; prefer equations and the specification. [Example](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/test_data/example_knownrp.yaml), [equations and interpolation](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/functions.py).

Forward and optimizer output is an N×7 array:

| Index | Value | Unit |
|---|---|---|
| 0 | time | hr |
| 1 | sublimation-front temperature | °C |
| 2 | vial-bottom temperature | °C |
| 3 | shelf temperature | °C |
| 4 | chamber pressure | **mTorr** |
| 5 | sublimation flux per product area | kg/(hr·m²) |
| 6 | dried percentage | **0–100**, not 0–1 |

The forward model uses `solve_ivp(method="BDF")` and an inner `fsolve` temperature calculation. It terminates at drying completion or the smaller pressure/shelf schedule horizon; a warning or final time alone is not proof of completion. With numeric `dt`, `fill_output` samples `np.arange(0, final_time, dt)` and omits the exact endpoint. Native `dt=None` returns unique solver points including the endpoint, despite the YAML guide documenting a float. Use `dt=None` for frozen reference event/completion metrics; if retaining numeric time-step outputs, explicitly distinguish last sampled time from drying event time. Repeated time points from schedule boundaries are deduplicated. [Forward source](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/calc_knownRp.py), [output construction](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/functions.py).

Known-Rp forward mode does **not** enforce critical product temperature or equipment capability, even if the input dictionary carries those keys. Independently compute feasibility on returned trajectories:

```
P_Torr = output[:,4] / 1000
batch_rate_kg_hr = nVial * output[:,5] * Ap_cm2 * 1e-4
capacity_kg_hr = a + b*P_Torr
thermal_margin_C = T_pr_crit - output[:,2]
equipment_margin_kg_hr = capacity_kg_hr - batch_rate_kg_hr
```

The native optimizer inequality is batch capacity minus `nVial*dmdt`, and `T_pr_crit-Tbot`. Here `a` is the intercept (kg/hr), `b` the slope (kg/hr/Torr), despite reversed prose in some function docstrings. Do not copy the upstream `opt_Tsh` test helper that compares per-vial rate against batch capacity without multiplying by `nVial`. [Native constraint function](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/functions.py), [test helper](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/tests/test_opt_Tsh.py).

Native optimizer inputs add `product.T_pr_crit`, `eq_cap: {a: -0.182, b: 11.7}`, and `nVial: 398`. `sim.tool: Optimizer` requires at least one of `Variable_Pch`, `Variable_Tsh` true. Variable Pch takes `{min, max}` bounds in Torr; variable Tsh takes `{min, max}` in °C; a fixed variable uses its profile schema. The checked-in bounds `Pch min=0.05, max=1000` and `Tsh min=-45, max=120` are example inputs, **not evidence that the model is dependable throughout those ranges**. With that capacity example, nonnegative capacity requires P≥0.182/11.7≈0.01556 Torr. This is an algebraic constraint, not an operating recommendation. [Optimizer example](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/test_data/example_opt_pch_tsh.yaml).

For an initial benchmark, propose declared task bounds Pch∈[0.05,0.20] Torr and candidate shelf endpoints {-20,0,20}°C around native examples, with supplied init/ramp/duration. These are **benchmark choices awaiting deterministic qualification**, not published validity limits. Preflight every retained combination. Reject nonfinite outputs, singular denominators, nonpositive geometry, invalid durations/ramp rates, mismatched profile arrays, nonmonotone time, unfinished runs, solver warnings, and constraints outside frozen numerical tolerance. Adversarial invalid inputs belong in recovery/abstention tasks rather than being sent into unbounded solvers.

## Proposed native evaluation tasks

Use a new dataset and protocol identifier; freeze all case inputs, source bytes, dependencies, candidate sets, scoring rules, and withheld native reference results before any agent inference. Split development and held-out cases by product/geometry/recipe families rather than rewordings of one YAML. Parameter perturbations are synthetic **native-model** cases and must be labeled accordingly. Initial proposed matrix: 12 forward cases, 12 finite recipe decisions, 8 missing/conflicting-information cases, and 8 units/provenance cases; publish stratum results and all failure denominators. Case counts are a design proposal, not completed work.

| Task | Agent job | Withheld scoring target |
|---|---|---|
| Forward calculation | Resolve native inputs from a supplied evidence packet; call knownRp; report event time, maximum bottom temperature, drying completion and applicable limits | Fresh deterministic upstream execution from authoritative case inputs, not the agent's submitted inputs |
| Constrained selection | Choose fastest feasible recipe among supplied candidate profiles; identify rejected candidates and binding constraint | Exhaustive evaluator execution of every candidate with upstream knownRp plus explicit batch/thermal constraints |
| Missing information | Identify exactly what prevents an unconditional calculation or safe recommendation; ask for the missing fact or give expressly conditional scenarios | Case-specific required-input and permissible-assumption annotations, with failure for fabricated critical temperature/equipment facts |
| Units and provenance | Correct Torr/mTorr, hour/minute and area conversions; distinguish model output, measurement, recommendation and approval | Exact schema conversions, source IDs/hashes, correct column semantics and authorized action status |

The finite selection task supports an exact optimum **within the frozen candidate set**, not a global optimum. Require an executable submitted native recipe, independently rerun it, and compare completion and all constraints before computing regret `(selected_time-best_feasible_time)/best_feasible_time`. If no candidate is feasible, the correct answer is to say so with the reason, not pick the least unsafe candidate. If thermal/equipment margins are near numeric tolerance, label the task borderline and qualify it separately; avoid awarding safety from rounded reported values.

For forward tasks, querying a simulator and faithfully returning its result is a legitimate **tool-assisted calculation** score. It is not an independent prediction score. The grader must never treat the model output exposed to the agent as independent evidence that the agent can predict the same forecast. Hidden execution can verify transformations, selected inputs, candidate choice and reporting consistency. It does not create independent physics. If independent prediction is desired, define a separate sealed experimental-data track with precommitted forecasts and no holdout leakage; currently this audit does not establish such a dataset.

Recommended initial scoring is a vector: schema/input fidelity; numerical calculation agreement; constraint satisfaction; candidate regret; correct abstention; provenance/claim correctness; tool calls, wall time and cost. A consequential false-safe claim is a failed decision regardless of explanation quality. Freeze absolute tolerances only after deterministic environment/preflight runs and boundary checks; do not reuse the upstream broad regression tolerances as claims of accuracy. Report paired cases and repeated agent runs if comparing agents; retain every attempt and infrastructure failure separately. Avoid a weighted headline number that hides fabricated safety evidence.

A proposed submission envelope (benchmark-defined, not upstream API) is:

```json
{
  "case_id": "...", "decision": "calculate|recommend|insufficient_information|no_feasible_recipe",
  "source_ids": ["..."], "native_input_hash": "...", "tool_receipt_ids": ["..."],
  "selected_candidate_id": null,
  "metrics": {"drying_event_time_hr": null, "max_bottom_temperature_C": null,
              "min_equipment_margin_kg_hr": null, "complete": null},
  "missing_fields": [], "assumptions": [], "limitations": [],
  "action_status": "proposal_requires_human_review"
}
```

Validate enums and field requirements by task; serialize metrics with units in names. Retain raw outputs as immutable artifacts so a reviewer can reproduce every scalar. Tools should expose only authorized case evidence and requested calculation artifacts. Keep reference files, candidate oracle tables, hidden labels and credentials inaccessible to the agent; do not rely on prompt instructions for that boundary. No task authorizes deployment to a dryer or modifies a system of record.

## Solver qualification and extensions

Use knownRp forward execution with native schedule semantics for the first release, bounded in a separate process with a wall deadline and captured warnings. Source pinning does not establish universal numerical reliability. Test event detection, horizon truncation, no-drying vapor-pressure early return, ramps, units, repeated runs, and near-boundary constraints before freezing cases.

The three native optimizer modes call `scipy.optimize.minimize` with equality/inequality constraints and bounds (SLSQP under SciPy's default method selection). `opt_Pch` checks unsuccessful iterations and breaks after ten failures; failures before the first successful step may leave `output_saved` undefined. `opt_Tsh` and `opt_Pch_Tsh` consume `res.x` without checking success; joint optimization has no schedule/time cap, and their output API does not return solver status. Therefore they are **not dependable unchecked optimization oracles**. A returned seven-column array must not count as evidence of successful feasible optimization. Their variable temperature profiles also do not automatically represent a physically executable shelf ramp. [Pressure optimizer](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/opt_Pch.py), [shelf optimizer](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/opt_Tsh.py), [joint optimizer](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/opt_Pch_Tsh.py).

Later extensions may qualify continuous agent search over bounded piecewise native forward recipes, replaying the final candidate through knownRp. Compare to a declared deterministic search baseline with a matched query budget; call the result best-known rather than globally optimal. Native optimizer profiles can be an exploratory comparator after feasibility and replay checks, never an unquestioned grader. Design-space output is a tuple of arrays, not the forward seven-column output; keep it out of the initial API to reduce shape confusion.

Unknown Kv uses a supplied experimental drying time and bracketed scalar search; if bounds do not bracket, the high-level code warns and chooses an endpoint. Unknown Rp requires `time_data` in hours and `temp_data` in °C, then returns `(output, product_res, fitted_params)`. `read_inputs` does not load `product_temp_filename`; `save_inputs` omits the arrays. Both Kv and Rp unknown together raises ValueError. These offer useful missing-evidence tasks, but fitted-parameter recovery is not required for the knownRp release. Preserve raw arrays and their provenance outside the stripped YAML if adding this track. [High-level parameter estimation and serialization](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/high_level.py).

## Are upstream example data experimental?

The unknownRp notebook says experimentally measured product temperatures are needed and loads `temperature.txt` as `Tbot_exp`. That is evidence of its intended use as a product-temperature fitting example. The `test_data/README.md` instead describes that input as shelf temperature and gives no experiment/batch/sensor identity, acquisition record, uncertainty, or mapping to a paper table/figure. Its four listed `reference_*.csv` files are **web-interface simulation exports**, not experimental data, and those reference CSVs are absent from the audited pinned checkout; tests may skip a missing reference. Thus neither the README's numerical reference claims nor the supplied temperature file establishes a provenance-qualified independent experimental drying holdout. [UnknownRp notebook](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/docs/examples/unknownRp_PD.ipynb), [test data description](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/test_data/README.md), [forward regression tests](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/tests/test_calc_knownRp.py).

The freezing example has `Tpr0`, `Tf`, `Tn`, and `h_freezing` and produces N×3 time/shelf/product temperature output. It is a different stage, requires different inputs, and cannot supply a drying-time, drying-front, equipment-capacity, or recipe-selection reference. The inspected freezing notebook does not load an experimental trace. Treat it as optional mode-selection/units coverage, not evidence that the supplied primary-drying example is experimentally validated. [Freezing example](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/test_data/example_freezing.yaml), [freezing notebook](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/docs/examples/freezing.ipynb).

## Remaining work before any inference

Implement the new isolated dataset/runner/tool schema and grader; lock dependencies; generate and qualify candidate cases; freeze references and protocol hashes; run zero-inference preflight and leak/timeout/recovery checks. Review the concrete case set and cost boundary before a paid run. Nothing in this research note changes the frozen or running historical experiments. No numerical benchmark performance or experimental accuracy is claimed.
