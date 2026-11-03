"""Experimental population-wise lumped thermal primary-drying model.

Each explicit population has independent ice mass and temperature, scaled Kv/Rp,
and a shared prescribed chamber pressure. C_eff dT/dt = q - mdot Hsub, with
C_eff = vial_heat_capacity + ice_mass * cp_ice. Exhausted populations stop
sublimating and continue warming; critical margins concern active populations.
This is neither a resolved temperature field nor a pressure-control model.
Capacity exceedance invalidates prediction; continued curves are diagnostics.
"""
from __future__ import annotations

import math

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from ..ids import content_hash
from .model import H_SUB, K_ICE, RHO_ICE, _finite, conditions, geometry, ice_pressure, validate

MODEL_VERSION = "heterogeneous-lumped-primary-drying-1.0.0"
ICE_CP_J_KG_K = 2100.


def _inputs(config):
    validate(config)
    populations = config.get("populations")
    if not isinstance(populations, list) or not 1 <= len(populations) <= 20:
        raise ValueError("populations requires 1..20 explicit weighted Kv/Rp populations")
    for population in populations:
        if not isinstance(population, dict):
            raise ValueError("each population requires weight, kv_scale and rp_scale")
        for key in ("weight", "kv_scale", "rp_scale"):
            value = _finite(population.get(key), f"populations.{key}", 0., float("inf"))
            if value <= 0:
                raise ValueError(f"populations.{key} must be positive")
    if not math.isclose(sum(p["weight"] for p in populations), 1., rel_tol=0, abs_tol=1e-9):
        raise ValueError("population weights must sum to one")
    thermal = config.get("thermal")
    if not isinstance(thermal, dict):
        raise ValueError("thermal inputs require explicit heat capacity and initialization")
    capacity = _finite(thermal.get("vial_heat_capacity_j_k"), "thermal.vial_heat_capacity_j_k", .1, 100.)
    equilibrium = thermal.get("initial_equilibrium", False)
    if type(equilibrium) is not bool:
        raise ValueError("thermal.initial_equilibrium must be a boolean assumption")
    initial_t = thermal.get("initial_temperature_c")
    if equilibrium and initial_t is not None:
        raise ValueError("choose either initial_temperature_c or initial_equilibrium")
    if not equilibrium:
        initial_t = _finite(initial_t, "thermal.initial_temperature_c", -65., -1.)
    return populations, capacity, initial_t, equilibrium


def simulate(config: dict, *, sample_step_h: float = .25, rtol: float = 1e-6,
             max_step_s: float = 300.) -> dict:
    """Integrate independent thermal nodes, restarting at drying/schedule events.

    `completion_time_h` and margin extrema describe the diagnostic numerical
    trajectory. Use `valid_completion_time_h` and `prediction_valid_until_h`
    when assessing applicability. Even applicable results remain unqualified.
    """
    populations, capacity, initial_t, equilibrium = _inputs(config)
    _finite(sample_step_h, "sample_step_h", .001, 2.)
    _finite(rtol, "rtol", 1e-10, 1e-3)
    _finite(max_step_s, "max_step_s", .01, 3600.)
    p, e = config["product"], config["equipment"]
    ap, av, height = geometry(p)
    mass_per_length = RHO_ICE*p["porosity"]*ap
    initial_mass = height*(1-config.get("initial_dried_fraction", 0))*mass_per_length
    weights = np.array([pop["weight"] for pop in populations])
    kv_scales = np.array([pop["kv_scale"] for pop in populations])*e.get("kv_scale", 1.)
    rp_scales = np.array([pop["rp_scale"] for pop in populations])*p.get("rp_scale", 1.)
    n = len(populations)
    active = np.full(n, initial_mass > 0)
    completions = [None if initial_mass > 0 else 0. for _ in populations]
    y = np.zeros(2*n)
    y[:n] = initial_mass
    end = float(config["duration_h"])
    points, checks = {}, []
    capacity_onsets = {}
    failure = None

    def physics(time_h, state, active_mask):
        masses = np.clip(state[:n], 0., initial_mass)
        temperatures = state[n:]
        dried = np.maximum(0., height-masses/mass_per_length)
        ts, pc = conditions(config, time_h)
        kv = (e["kv_a_w_m2_k"]+e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc))*kv_scales
        rp = (p["rp0_m_s"]+p["rp1_per_s"]*dried/(1+p["rp2_per_m"]*dried))*rp_scales
        conductance = av*kv/(1+av*kv*masses/mass_per_length/(ap*K_ICE))
        # A terminal melting event bounds use of the ice correlation. Clipping
        # permits solver trial stages beyond the event, not ice above melting.
        vapor = np.array([ice_pressure(min(float(t), 0.)) if a else 0.
                          for t, a in zip(temperatures, active_mask)])
        rates = np.where(active_mask, ap*np.maximum(0., vapor-pc)/rp, 0.)
        heat = conductance*(ts-temperatures)
        return masses, temperatures, rates, heat, ts, pc

    def fields(time_h, state, active_mask):
        masses, temperatures, rates, heat, ts, pc = physics(time_h, state, active_mask)
        batch_rate = float(weights@rates)*3600*config["load_vials"]
        mass = float(weights@masses)
        hottest = float(max(temperatures[active_mask])) if any(active_mask) else None
        return {"time_h": float(time_h), "product_temperature_c": float(weights@temperatures),
                "active_max_temperature_c": hottest,
                "remaining_ice_kg_per_vial": mass, "sublimation_kg_h": batch_rate,
                "shelf_temperature_c": ts, "chamber_pressure_pa": pc,
                "critical_margin_c": p["critical_temperature_c"]-hottest if hottest is not None else None,
                "capacity_margin_kg_h": e["vapor_capacity_kg_h"]-batch_rate,
                "condenser_margin_kg": e["condenser_capacity_kg"]-(initial_mass-mass)*config["load_vials"],
                "populations": [{"weight": float(weights[i]), "active": bool(active_mask[i]),
                                 "temperature_c": float(temperatures[i]),
                                 "remaining_ice_kg_per_vial": float(masses[i]),
                                 "rate_kg_s_per_vial": float(rates[i]),
                                 "heat_w_per_vial": float(heat[i])} for i in range(n)]}

    if equilibrium:
        ts, pc = conditions(config, 0.)
        for i in range(n):
            if not active[i]:
                y[n+i] = ts
                continue
            if ice_pressure(min(ts, 0.)) <= pc:
                raise ValueError("initial equilibrium requires a sublimation driving force")
            def balance(temperature):
                candidate = y.copy()
                candidate[n:] = temperature
                _, _, rates, heat, _, _ = physics(0., candidate, active)
                return heat[i]-rates[i]*H_SUB
            y[n+i] = brentq(balance, -100., min(ts, 0.), xtol=1e-10)
    else:
        y[n:] = initial_t

    def check(row):
        checks.append(row)
        for key, name in (("capacity_margin_kg_h", "vapor_capacity"),
                          ("condenser_margin_kg", "condenser_ice_capacity")):
            if row[key] <= 0:
                capacity_onsets[name] = min(capacity_onsets.get(name, end), row["time_h"])

    boundaries = sorted(set([0., end, *[s["time_h"] for s in config["schedule"]]]))
    for left, right in zip(boundaries, boundaries[1:]):
        t = left*3600
        while t < right*3600:
            segment_active = active.copy()
            start = t
            row = fields(start/3600, y, segment_active)
            points[start/3600] = row
            check(row)

            def eval_h(seconds):
                return min(seconds/3600, np.nextafter(right, left))

            def rhs(seconds, state):
                masses, _, rates, heat, _, _ = physics(eval_h(seconds), state, segment_active)
                return np.concatenate([-rates, (heat-rates*H_SUB)/(capacity+masses*ICE_CP_J_KG_K)])

            events, event_names = [], []
            for i in np.flatnonzero(segment_active):
                def exhausted(_seconds, state, index=i):
                    return state[index]
                exhausted.terminal, exhausted.direction = True, -1
                events.append(exhausted)
                event_names.append(("dry", int(i)))
                def melting(_seconds, state, index=i):
                    return state[n+index]
                melting.terminal, melting.direction = True, 1
                events.append(melting)
                event_names.append(("melting", int(i)))
            for key, name in (("capacity_margin_kg_h", "vapor_capacity"),
                              ("condenser_margin_kg", "condenser_ice_capacity")):
                def capacity_crossing(seconds, state, field=key):
                    return fields(eval_h(seconds), state, segment_active)[field]
                capacity_crossing.direction = -1
                capacity_crossing.terminal = False
                events.append(capacity_crossing)
                event_names.append((name, None))
            try:
                solution = solve_ivp(rhs, (start, right*3600), y, method="BDF",
                                     events=events, dense_output=True, rtol=rtol,
                                     atol=[1e-12]*n+[1e-7]*n, max_step=max_step_s)
                if not solution.success:
                    failure = solution.message
                    break
                stop = float(solution.t[-1])
                for seconds in solution.t:
                    check(fields(eval_h(seconds), solution.sol(seconds), segment_active))
                for event_name, times in zip(event_names, solution.t_events):
                    name, index = event_name
                    if len(times) and name not in ("dry", "melting"):
                        capacity_onsets[name] = min(capacity_onsets.get(name, end), float(times[0]/3600))
                    if len(times) and name == "melting":
                        failure = f"active population {index} reached melting temperature; model no longer applies"
                grid = sorted(set([start/3600, stop/3600,
                                   *np.arange(start/3600, stop/3600, sample_step_h).tolist()]))
                for h in grid:
                    # Store right-continuous scheduled pressure; temperature and
                    # mass are continuous across a schedule boundary.
                    row = fields(h, solution.sol(h*3600), segment_active)
                    points[h] = row
                    check(row)
                y = solution.y[:, -1].copy()
                t = stop
                dried_now = segment_active & (y[:n] <= 1e-12)
                for i in np.flatnonzero(dried_now):
                    y[i] = 0.
                    active[i] = False
                    completions[i] = stop/3600
                points[stop/3600] = fields(stop/3600, y, active)
                if failure:
                    break
                if stop <= start:
                    failure = "integration made no progress"
                    break
            except (ValueError, RuntimeError, OverflowError, FloatingPointError) as exc:
                failure = str(exc)
                break
        if failure:
            break

    rows = [points[h] for h in sorted(points)]
    completion = max(completions) if all(t is not None for t in completions) else None
    valid_until = min(capacity_onsets.values(), default=end)
    if failure:
        valid_until = min(valid_until, rows[-1]["time_h"] if rows else 0.)
    for row in rows:
        row["prediction_valid"] = row["time_h"] < valid_until if capacity_onsets or failure else True
    violations = []
    for field, name in (("critical_margin_c", "critical_temperature"),
                        ("capacity_margin_kg_h", "vapor_capacity"),
                        ("condenser_margin_kg", "condenser_ice_capacity")):
        bad = [r for r in checks if r[field] is not None and r[field] <= 0]
        if bad or name in capacity_onsets:
            violations.append({"constraint": name,
                               "first_time_h": capacity_onsets.get(name, min(r["time_h"] for r in bad) if bad else None),
                               "minimum_margin": min((r[field] for r in checks if r[field] is not None), default=None),
                               "onset_method": "solver_event_or_schedule_boundary" if name in capacity_onsets else "solver_mesh_and_output_samples"})
    if completion is None and failure is None:
        violations.append({"constraint": "incomplete_primary_drying", "first_time_h": end})
    applicable_completion = completion if completion is not None and completion <= valid_until and not capacity_onsets and not failure else None
    warnings = ["Experimental, unqualified lumped population model; no spatial temperature field or pressure dynamics.",
                "Population weights and Kv/Rp factors are explicit assumptions unless independently characterized.",
                "Forward sublimation only; deposition is excluded. Ice heat capacity is a constant 2100 J/(kg K).",
                "Dry-vial temperature uses the declared vial heat capacity; desorption and dry-cake heat storage are omitted.",
                "Thermal margin extrema use solver mesh and output samples; they are not certified continuous extrema.",
                "No residual moisture, potency, release suitability or biological yield is predicted."]
    if equilibrium:
        warnings.append("Initial temperatures assume per-population quasi-steady thermal equilibrium; not measured states.")
    if capacity_onsets:
        warnings.append("Equipment capacity exceeded: curves after prediction_valid_until_h are diagnostic extrapolations; prescribed pressure is not physically assured.")
    if failure:
        warnings.append(f"Numerical/operating failure: {failure}")
    if any(not 5 <= s["chamber_pressure_pa"] <= 25 for s in config["schedule"]):
        warnings.append("Pressure outside published Kv characterization range 5–25 Pa.")
    return {"model_version": MODEL_VERSION, "classification": "calculated_prediction",
            "inputs_hash": content_hash(config),
            "solver": {"library": "scipy", "version": scipy.__version__, "integrator": "BDF",
                       "rtol": rtol, "atol_mass_kg": 1e-12, "atol_temperature_c": 1e-7, "max_step_s": max_step_s},
            "numerical_status": "failed" if failure else "completed", "numerical_error": failure,
            "completion_time_h": completion, "valid_completion_time_h": applicable_completion,
            "population_completion_time_h": completions, "trajectory": rows, "violations": violations,
            "prediction_valid_until_h": valid_until,
            "applicability_status": "invalid_after_capacity_exceedance" if capacity_onsets else "numerical_or_operating_failure" if failure else "within_declared_model_scope",
            "diagnostic_trajectory": bool(capacity_onsets or failure),
            "initial_ice_kg_per_vial": initial_mass,
            "minimum_critical_margin_c": min((r["critical_margin_c"] for r in checks if r["critical_margin_c"] is not None), default=None),
            "minimum_capacity_margin_kg_h": min((r["capacity_margin_kg_h"] for r in checks), default=None),
            "primary_drying_throughput_vials_h": config["load_vials"]/applicable_completion if applicable_completion and not violations else None,
            "additional_constants": {"ice_specific_heat": {"value": ICE_CP_J_KG_K, "unit": "J/(kg K)", "category": "synthetic_assumption"}},
            "warnings": warnings}
