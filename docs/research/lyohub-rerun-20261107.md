# LyoHUB modeling-tool rerun: source and integration findings

Inspected 7 November 2026. This is integration research, not a numerical result or manufacturing validation. Read alongside [the existing source boundary](freeze-drying-sources.md) and [the prior study protocol](../../backend/benchmarks/lyo_study/README.md). The user's clarified request is to give agents LyoPRONTO as a modeling tool; it is **not** a replacement evaluation reference.

## Source pin and scientific scope

The official repository HEAD retrieved through the [GitHub commit API](https://api.github.com/repos/LyoHUB/LyoPRONTO/commits/HEAD) is **c6a9225a9e551ae4e7c11c1ef056b67c6204afbd**, committed 11 August 2026. This is the same commit inspected in the October source note. Record this immutable pin and dependency versions in the new protocol. [Pinned metadata](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/pyproject.toml) identifies package version 1.2.0.

The [original 2019 paper](https://doi.org/10.1208/s12249-019-1532-7) describes a quasi-steady one-dimensional primary-drying model. Its reported experimental performance applies to its own experiments; it does not validate BioDemo's BSA/sucrose reconstruction, synthetic receiving shifts or agent choices. LyoPRONTO is an externally maintained implementation, not independent experimental ground truth. The existing evaluator remains synthetic and shares heat/mass-transfer laws with both supplied models. Giving agents another solver tests tool utility on those cases, not industrial generalization or independent scientific validation.

## Executable API and unit boundary

Use the public `from lyopronto import calc_knownRp; output = calc_knownRp.dry(vial, product, ht, Pchamber, Tshelf, dt=None)`. The [pinned implementation](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/calc_knownRp.py) and [official worked example](https://lyohub.github.io/LyoPRONTO/dev/examples/knownRp_PD/) define the arguments. These are ordinary dictionaries; no GUI is required.

| Argument | Required units / meaning |
|---|---|
| `vial.Av`, `vial.Ap`, `vial.Vfill` | Vial and product areas in cm²; liquid fill in mL |
| `product.cSolid` | Solute concentration in g/mL according to source docstrings; tutorial loosely calls it a fraction |
| `product.R0`, `A1`, `A2` | cm²·h·Torr/g; cm·h·Torr/g; cm⁻¹, with `Rp=R0+A1*L/(1+A2*L)` and cake length L in cm |
| `ht.KC`, `KP`, `KD` | cal/(s·cm²·K); cal/(s·cm²·K·Torr); Torr⁻¹, with `Kv=KC+KP*P/(1+KD*P)` |
| `Pchamber` | `setpt` Torr; `dt_setpt` minutes; `ramp_rate` Torr/min; optional `init` Torr |
| `Tshelf` | `setpt` and optional `init` °C; `dt_setpt` minutes; `ramp_rate` °C/min |
| `dt` | Output spacing in hours; `None` preserves solver nodes and exact terminal row |

These dimensional conversions are derived from the [pinned functions](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/functions.py) and [constants](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/constant.py):

```text
P_Torr = P_Pa / 133.322368
area_cm2 = area_m2 * 10000
fill_mL = fill_m3 * 1000000
KC = kv_a / 41840
KP = kv_b * 133.322368 / 41840
KD = kv_c * 133.322368
D = 1e-4 * 3600 * 133.322368 / 1e-3 = 47996.05248
R0 = rp0_m_s / D
A1 = rp1_per_s * .01 / D
A2 = rp2_per_m * .01
```

`cSolid` cannot be taken as `1-porosity` without an explicit approximation. Upstream fixes solution, ice and solute densities at 1.0, 0.918 and 1.5 g/mL, and derives initial frozen height/ice content from concentration. BioDemo derives them from porosity using a different expression. State the chosen mapping, and record both initial frozen height and initial ice mass discrepancies; matching one does not automatically match the other. This is a model-structure assumption, not just unit conversion.

## Schedules, endpoints and observables

The pinned `RampInterpolator` counts ramp time **inside** each `dt_setpt` by default. Without `init`, the first setpoint holds from t=0; with `init`, the initial ramp starts immediately. If a requested stage is too short for its ramp, upstream warns and extends that stage by clamping hold time to zero. Convert the existing instantaneous schedule changes explicitly and record the finite-ramp approximation. Both shelf and pressure schedules should cover the same horizon. Preserve warnings and numerical failures.

The seven returned columns are time [h], sublimation-front temperature [°C], bottom temperature [°C], shelf temperature [°C], chamber pressure [mTorr], sublimation flux [kg/(h·m²)] and percent dried. Convert flux to vial mass rate by multiplying product area in m². The solver stops when cake length reaches initial frozen length; it also stops at the schedule horizon if unfinished. **With numeric `dt`, `fill_output` uses `arange(0, final_time, dt)` and omits the terminal row. Use `dt=None` before identifying completion.** Treat unfinished runs as censored, not as completed at their last timestamp. Output temperature and flux are reconstructed/interpolated from solver nodes; no rigorous maximum-between-nodes guarantee is provided. [Source](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/functions.py)

The known-Rp path accepts neither initial partial cake nor a transient thermal state; replay from t=0 for a 6 h decision and expose the appropriate forecast segment. It has no finite thermal-storage state. Its front/bottom temperatures do not represent the prior study's weighted transient thermal-node observation. Do not silently relabel bottom temperature as that observation. [Known-Rp source](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/calc_knownRp.py)

## Constraint boundary

Known-Rp forward simulation does **not** enforce the supplied critical temperature or equipment capacity: neither is an argument used in that path. Its prescribed chamber pressure is not a pressure-controller prediction after overload. The separate [design-space module](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/lyopronto/design_space.py) uses `eq_cap.a + eq_cap.b*P_Torr` in kg/h: `a` is the intercept despite a reversed docstring description. That expression does not implement BioDemo's condenser plateau, accumulating ice capacity or overload response.

For agent use, report a separately labeled BioDemo constraint assessment beside upstream trajectory output: active-product temperature criterion, batch flux versus the declared vapor ceiling, and integrated batch ice versus condenser storage. Stop pressure-controlled applicability at overload. Distinguish this augmentation from upstream functionality. A caller must choose explicitly whether its thermal guard uses front or bottom temperature; the prior study's metric has another observable and cannot be represented as an upstream measurement.

## Recommended bounded experiment

Retain the existing frozen synthetic cases and evaluator, add LyoPRONTO as a prepared modeling-tool arm, and keep the original numerical-only and heterogeneous-model arms. Replay old sessions only as historical context; a newly exposed tool requires fresh model sessions. Freeze source hashes, allowed inputs, mapping assumptions, observation cutoff, time/call/cost limits, error handling and tools before inference. Preserve the distinction between operating suggestions and manufacturing authorization.

For fitted Kv/Rp, replay from t=0 and fit only observations available by 6 h, never hidden mechanisms, future trajectories or scored targets. A defensible common fit uses remaining ice only, with identical multiplier bounds and residual weights in both supplied models. This changes the original C fitting objective and therefore needs a new, labeled protocol. Alternatively retain historical C and give B an ice-only fit, but disclose that calibration objectives differ. Do not use upstream bottom temperature in the old weighted-node thermal residual. Pretransfer has no receiving observations and must remain unfitted. Compare against each model alone to separate tool physics from agent choices. These are integration recommendations, not upstream claims.

This simple extension minimizes setup and preserves existing results (Easy to Start/Adopt), exposes source/mapping/error evidence (Easy to Trust), and produces reviewable comparisons rather than plant commands (Easy to Act). A more ambitious redesign using matched thermometry and independently held-out experimental trajectories would improve scientific interpretation but requires new evidence. Measure coverage, constraint errors, decision feasibility, tool failures, reviewer-verifiable provenance and cost; no human-time saving is established by runtime alone. Publish under a separate research/benchmark destination as requested, with no claim of real manufacturing validation.

## License and distribution boundary

The [pinned README](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/README.md) and [license](https://github.com/LyoHUB/LyoPRONTO/blob/c6a9225a9e551ae4e7c11c1ef056b67c6204afbd/LICENSE.txt) specify GPL-3.0-or-later and disclaim warranty. LGPL is offered only by separate request/permission. Do not describe it as permissively licensed or presume LGPL permission.

Run it in an isolated external benchmark environment, retain the exact upstream pin, license notices and reproducibility instructions, and avoid bundling upstream code into the production product. Process isolation is an engineering boundary, not a legal conclusion that distribution obligations disappear. Review the actual package/container and any copied/derived code before distribution. Publishing numerical research results does not itself establish rights to sublicense upstream code. No author contact or special permission was obtained in this research.

Outstanding uncertainty: `cSolid` mapping and temperature-observable alignment require declared assumptions; equipment augmentation is local; exact original experimental datasets remain unavailable; public cases cannot establish model training independence. None prevents an honestly labeled synthetic tool-use comparison.

## Implemented adapter source cross-check

The frozen [issue #28](https://github.com/YalmanchiliTejas/BioDemo/issues/28) implementation was subsequently inspected in `backend/benchmarks/lyohub_study/{upstream_worker,models,campaign}.py` against the pinned upstream source above. This is a source/integrity check, not additional scientific validation; the frozen implementation was not changed.

The implemented mapping `cSolid=1.5*(1-eps)` g/mL exactly preserves BioDemo's initial frozen height under the upstream fixed densities:

```text
L_upstream = (V/Ap) * [1-(1-eps)*(1-.918)]/.918
           = (V/Ap) * [1-eps + eps/.918] = L_local
ice0_upstream = 1000 * V_m3 * eps                  [kg/vial]
ice0_local   = V_m3 * eps * (918 + 82*eps)         [kg/vial]
```

At the frozen cases' `eps=.897`, native upstream initial ice is **0.851794% higher** than local initial ice, despite equal frozen height. The wrapper retains that native inventory, uses `ice0_upstream*(1-percent_dried/100)` for remaining ice, and converts upstream flux to batch rate using product area and load. Those inventory and rate conversions are consistent with upstream's cake-growth equation. Rp and Kv conversions match the dimensional equations above. This is an effective surrogate composition, not evidence that the physical formulation contains `cSolid` of solute. In absolute remaining-ice calibration, effective Kv/Rp multipliers may partly absorb this inventory mismatch and other structural discrepancies.

Both tools now use the same early remaining-ice residual, bounds, robust loss and optimizer budget; neither uses thermal observations as an equivalent thermometer. Packet validation rejects observations whose sample or availability time exceeds the cutoff. Fitting truncates the simulation horizon and known schedule at the cutoff; pretransfer remains nominal. The prepared tool returns only public-input-derived action predictions, not the model-control selector, scored outcomes or hidden evaluator trajectories. Inspection found no future-outcome leakage in these paths. The known future schedule is a public plan, not a future observation.

The implemented B thermal guard explicitly uses the representative **front temperature**; C uses its hottest active transient population. This difference must remain visible in results and prevents interpreting thermal-warning performance as a matched sensor comparison. B capacity checks are wrapper calculations at upstream adaptive solver nodes; C uses its own event/check grids. Neither a sampled margin minimum nor the absence of a sampled thermal crossing guarantees a continuous-time extremum. The selected large finite ramp rate approximates instantaneous setpoint changes; it does not reproduce an actual dryer ramp.

The 96 saved model-control records were read during this bounded check. Saved B raw trajectories contained no upstream warnings and no increasing remaining-ice segment at a 1e-10 kg tolerance. This check does not establish solver convergence rigor or validate the physical predictions. Reporting should preserve optimizer `iteration_limit` statuses when present; the supplied policy permits such effective fits and must not describe every fit as converged.
