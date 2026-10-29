"""Two audiences, one model; bounded candidates and cutoff-limited diagnosis."""
from __future__ import annotations

from copy import deepcopy
from time import perf_counter

import numpy as np
from scipy.optimize import minimize_scalar

from .case import receiving_config, source_config
from .model import simulate, uncertainty


def summarize(label: str, config: dict, result: dict) -> dict:
    return {"label": label, "config": config, "result": result,
            "feasible": result["numerical_status"] == "completed" and not result["violations"],
            "load_vials": config["load_vials"], "shelf_temperature_c": config["schedule"][-1]["shelf_temperature_c"],
            "completion_time_h": result["completion_time_h"],
            "critical_margin_c": result["minimum_critical_margin_c"],
            "capacity_margin_kg_h": result["minimum_capacity_margin_kg_h"],
            "throughput_vials_h": result["primary_drying_throughput_vials_h"]}


def verification_plan() -> dict:
    return {"responsible_reviewer": "Assigned MSAT process owner and independent QA reviewer",
            "experiments": [
                {"experiment": "Water sublimation / pressure-rise characterization at 5, 8 and 12 Pa; representative load",
                 "acceptance_criteria": "Measured batch vapor rate remains below characterized capacity with >=10% headroom; pressure stays within approved control tolerance."},
                {"experiment": "Gravimetric Kv characterization of center and edge vials; product-specific Rp characterization",
                 "acceptance_criteria": "Characterization intervals cover modeled coefficients; otherwise revise inputs and rerun."},
                {"experiment": "Instrumented verification batch with center/edge thermocouples and independent primary-drying endpoint indication",
                 "acceptance_criteria": "All monitored product temperatures below -28°C; endpoint precedes the proposed hold end; target endpoint error <=20% and temperature error <=2°C (proposed engineering criteria, subject to reviewer approval)."}],
            "release_boundary": "Secondary drying, residual moisture, appearance and potency require separate approved tests. No release decision is supported here."}


def transfer(*, shelf_c: float = -24., load_vials: int = 11000, capacity_kg_h: float = .65,
             samples: int = 8, seed: int = 2025) -> dict:
    start = perf_counter()
    sending = source_config()
    base = receiving_config(shelf_c=shelf_c, load_vials=load_vials, capacity_kg_h=capacity_kg_h)
    options = [summarize("Source pilot reconstruction", sending, simulate(sending)),
               summarize("Direct transfer / no change", base, simulate(base))]
    # Bounds fixed before comparisons; reduce load or lower heat input, no unbounded optimizer.
    for offset, fraction in [(-4., 1.), (-8., 1.), (0., .5), (-4., .5), (-8., .5)]:
        c = deepcopy(base)
        c["schedule"][0]["shelf_temperature_c"] = max(-36., shelf_c+offset)
        c["load_vials"] = max(1, round(load_vials*fraction))
        options.append(summarize(f"{c['schedule'][0]['shelf_temperature_c']:g}°C · {c['load_vials']} vials", c, simulate(c)))
    feasible = [(i, o) for i, o in enumerate(options[1:], 1) if o["feasible"]]
    selected = max(feasible, key=lambda pair: pair[1]["throughput_vials_h"])[0] if feasible else None
    recommendation = None
    if selected is not None:
        chosen = options[selected]
        chosen["uncertainty"] = uncertainty(chosen["config"], samples=samples, seed=seed)
        recommendation = {"candidate_index": selected, "what_changes": chosen["label"],
                          "why": "Highest nominal primary-drying throughput among the bounded candidates with no sampled constraint violation.",
                          "predicted_effect": {k: chosen[k] for k in ("completion_time_h", "critical_margin_c", "capacity_margin_kg_h", "throughput_vials_h")},
                          "tradeoffs": "Lower heat input increases hold time; lower loading reduces vials per batch. Nominal feasibility does not establish robust performance.",
                          "verification": verification_plan(), "status": "requires_human_review"}
    return {"audience": "technology_transfer", "options": options, "recommended_index": selected,
            "recommendation": recommendation, "candidate_bounds": {"shelf_offset_c": [-8, 0], "load_fraction": [.5, 1]},
            "objective": "maximize nominal completed-primary-drying vials/hour subject to temperature, vapor and ice-capacity constraints",
            "runtime_seconds": perf_counter()-start}


def visible_measurements(measurements: list[dict], cutoff_h: float) -> list[dict]:
    """Only allow known channels and records available by BOTH clocks."""
    allowed = ("time_h", "available_at_h", "product_temperature_c", "sublimation_kg_h", "chamber_pressure_pa")
    result = []
    for row in measurements:
        if not isinstance(row, dict) or not {"time_h", "product_temperature_c"} <= row.keys():
            raise ValueError("each measurement requires time_h and product_temperature_c")
        if not isinstance(row["time_h"], (float, int)) or not np.isfinite(row["time_h"]):
            raise ValueError("measurement time_h must be finite")
        if row["time_h"] <= cutoff_h and row.get("available_at_h", row["time_h"]) <= cutoff_h:
            clean = {k: row[k] for k in allowed if k in row}
            if any(not isinstance(v, (float, int)) or not np.isfinite(v) for v in clean.values()):
                raise ValueError("measurements must be finite numeric observations")
            result.append(clean)
    if len(result) < 3 or len({r["time_h"] for r in result}) < 3:
        raise ValueError("at least three distinct cutoff-visible measurement times required")
    return sorted(result, key=lambda r: r["time_h"])


def diagnose(config: dict, measurements: list[dict], cutoff_h: float) -> dict:
    visible = visible_measurements(measurements, cutoff_h)
    hypotheses = []
    for name, block, key, bounds in [
        ("changed_heat_transfer", "equipment", "kv_scale", (.5, 1.7)),
        ("changed_product_resistance", "product", "rp_scale", (.5, 1.8)),
        ("reduced_vapor_capacity", "equipment", "vapor_capacity_kg_h", (.25, config["equipment"]["vapor_capacity_kg_h"]))]:
        def loss(factor):
            c = deepcopy(config)
            c[block][key] = float(factor)
            c["duration_h"] = max(cutoff_h, .01)
            c["schedule"] = [s for s in c["schedule"] if s["time_h"] <= cutoff_h]
            out = simulate(c, sample_step_h=.25)
            if out["numerical_status"] != "completed" or not out["trajectory"]:
                return 1e9
            rows = out["trajectory"]
            pred = np.interp([r["time_h"] for r in visible], [r["time_h"] for r in rows], [r["interface_temperature_c"] for r in rows])
            # Temperature-only likelihood surrogate. Capacity cannot be inferred
            # from temperature with prescribed chamber pressure: explicitly unidentifiable.
            return float(np.mean((pred-np.array([r["product_temperature_c"] for r in visible]))**2))
        fit = minimize_scalar(loss, bounds=bounds, method="bounded", options={"xatol": .005})
        c = deepcopy(config)
        c[block][key] = float(fit.x)
        identifiable = name != "reduced_vapor_capacity"
        hypotheses.append({"hypothesis": name, "parameter": f"{block}.{key}", "estimate": float(fit.x) if identifiable else None,
                           "temperature_rmse_c": float(np.sqrt(fit.fun)), "identifiable": identifiable,
                           "config": c if identifiable else deepcopy(config),
                           "interpretation": "Temperature fit alone is not causal proof." if identifiable else
                           "Capacity is not identifiable in a prescribed-pressure model. Pressure-control and sublimation-rate characterization required; estimate withheld."})
    ranked = sorted([h for h in hypotheses if h["identifiable"]], key=lambda h: h["temperature_rmse_c"])
    plausible = [h["hypothesis"] for h in ranked if h["temperature_rmse_c"] <= ranked[0]["temperature_rmse_c"]+.5]
    return {"hypotheses": hypotheses, "best_temperature_fit": ranked[0]["hypothesis"], "plausible_temperature_explanations": plausible,
            "diagnostic_config": ranked[0]["config"], "evidence_cutoff_h": cutoff_h, "observations": visible,
            "ambiguity": "Kv/Rp can compensate; thermal lag, vial position and sensor bias are alternative explanations. Reduced capacity is not ruled out.",
            "discriminating_experiment": "Pair gravimetric sublimation rate with center/edge product thermometry; independently characterize pressure control and condenser capacity at a controlled vapor load."}


def operations(config: dict, measurements: list[dict], *, cutoff_h: float = 6.) -> dict:
    start = perf_counter()
    diagnosis = diagnose(config, measurements, cutoff_h)
    fitted = diagnosis["diagnostic_config"]
    options = [summarize("No-change forecast", fitted, simulate(fitted))]
    for shelf in (-28., -24., -20.):
        c = deepcopy(fitted)
        # History is identical through cutoff. Candidate changes only future schedule.
        c["schedule"] = [s for s in c["schedule"] if s["time_h"] < cutoff_h]
        c["schedule"].append({"time_h": cutoff_h, "shelf_temperature_c": shelf,
                              "chamber_pressure_pa": c["schedule"][-1]["chamber_pressure_pa"]})
        options.append(summarize(f"At {cutoff_h:g} h → {shelf:g}°C", c, simulate(c)))
    past_damage = any(r["product_temperature_c"] >= config["product"]["critical_temperature_c"] for r in diagnosis["observations"])
    feasible = [(i, r) for i, r in enumerate(options) if r["feasible"]]
    selected = min(feasible, key=lambda item: item[1]["completion_time_h"])[0] if feasible and not past_damage else None
    return {"audience": "cdmo_operation", "evidence_cutoff_h": cutoff_h, "diagnosis": diagnosis, "options": options,
            "recommended_index": selected, "irreversible_damage_possible": past_damage,
            "intervention_boundary": "No rescue claim. Prior critical-temperature excursion requires quality assessment." if past_damage else
            "Conditional forecasts from t=0 using cutoff-fitted parameters; not a validated state estimator. Changes apply only after cutoff.",
            "verification": verification_plan(), "runtime_seconds": perf_counter()-start}
