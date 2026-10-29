"""SI Kv–Rp moving-front reconstruction of Vanbillemont et al. (2025).

Heat: q = Av Kv (Ts - Ti) / (1 + Av Kv Lice/(Ap kice)).
Mass: mdot = Ap (pice(Ti)-Pc)/Rp(Ld); q = mdot Hsub.
Front: dLd/dt = mdot/(rhoice porosity Ap). Frozen-layer conduction
is retained; sensible heat and transient chamber/condenser dynamics are omitted.
Pressure is a prescribed boundary: above equipment capacity, trajectories are
diagnostic extrapolations, NOT a forecast of controlled chamber performance.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from ..ids import content_hash

MODEL_VERSION = "kv-rp-si-1.0.0"
PAPER = "https://doi.org/10.1186/s41120-025-00115-5"
RHO_ICE = 918.0
RHO_WATER = 1000.0
H_SUB = 2.84e6  # J/kg, constant approximation over primary drying
K_ICE = 2.4  # W/(m K), constant approximation


def ice_pressure(temp_c: float) -> float:
    """Murphy & Koop (2005), Eq. 7, Pa; 110 K < T <= 273.16 K."""
    t = temp_c + 273.15
    if not 110 < t <= 273.16:
        raise ValueError("ice vapor pressure outside 110–273.16 K")
    return math.exp(9.550426 - 5723.265 / t + 3.53068 * math.log(t) - .00728332 * t)


def _finite(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric SI input")
    if not low <= value <= high:
        raise ValueError(f"{name} must be in [{low}, {high}]")
    return float(value)


def validate(config: dict) -> None:
    if not isinstance(config, dict) or not {"product", "equipment", "load_vials", "duration_h", "schedule"} <= config.keys():
        raise ValueError("config requires product, equipment, load_vials, duration_h and schedule")
    p, e = config["product"], config["equipment"]
    if not isinstance(p, dict) or not {"fill_m3", "inner_diameter_m", "outer_diameter_m", "porosity", "critical_temperature_c", "rp0_m_s", "rp1_per_s", "rp2_per_m"} <= p.keys():
        raise ValueError("product geometry, formulation resistance and critical temperature are required in SI")
    if not isinstance(e, dict) or not {"kv_a_w_m2_k", "kv_b_w_m2_k_pa", "kv_c_per_pa", "vapor_capacity_kg_h", "condenser_capacity_kg", "max_vials"} <= e.keys():
        raise ValueError("equipment heat transfer, capacity and loading limits are required in SI")
    for key, bounds in {"fill_m3": (1e-8, 1e-3), "inner_diameter_m": (.001, .1),
                        "outer_diameter_m": (.001, .12), "porosity": (.01, .999),
                        "critical_temperature_c": (-65, -1), "rp0_m_s": (1, 1e8),
                        "rp1_per_s": (0, 1e12), "rp2_per_m": (0, 1e6)}.items():
        _finite(p[key], key, *bounds)
    if p["outer_diameter_m"] < p["inner_diameter_m"]:
        raise ValueError("outer diameter must be >= inner diameter")
    _finite(p.get("rp_scale", 1.), "rp_scale", .05, 10.)
    _finite(e.get("kv_scale", 1.), "kv_scale", .05, 10.)
    _finite(e.get("kv_rsd", .151), "kv_rsd", 0, 1.)
    for key, bounds in {"kv_a_w_m2_k": (0, 200), "kv_b_w_m2_k_pa": (0, 100),
                        "kv_c_per_pa": (0, 10), "vapor_capacity_kg_h": (.001, 1e5),
                        "condenser_capacity_kg": (.001, 1e6), "max_vials": (1, 1e7)}.items():
        _finite(e[key], key, *bounds)
    if type(config["load_vials"]) is not int or not 1 <= config["load_vials"] <= e["max_vials"]:
        raise ValueError("load_vials must be an integer within equipment loading limit")
    _finite(config["duration_h"], "duration_h", .01, 150)
    _finite(config.get("initial_dried_fraction", 0), "initial_dried_fraction", 0, 1)
    schedule = config["schedule"]
    if not isinstance(schedule, list) or any(not isinstance(s, dict) or not {"time_h", "shelf_temperature_c", "chamber_pressure_pa"} <= s.keys() for s in schedule):
        raise ValueError("schedule requires time_h, shelf_temperature_c and chamber_pressure_pa for each knot")
    if not schedule or schedule[0]["time_h"] != 0:
        raise ValueError("schedule must start at time_h=0")
    previous = -1.0
    for s in schedule:
        t = _finite(s["time_h"], "schedule.time_h", 0, config["duration_h"])
        if t <= previous:
            raise ValueError("schedule knots must increase strictly")
        previous = t
        _finite(s["shelf_temperature_c"], "shelf_temperature_c", -65, 20)
        _finite(s["chamber_pressure_pa"], "chamber_pressure_pa", .5, 100)
    if config.get("schedule_mode", "step") not in ("step", "linear"):
        raise ValueError("schedule_mode must be step or linear")


def conditions(config: dict, time_h: float) -> tuple[float, float]:
    schedule = config["schedule"]
    times = [s["time_h"] for s in schedule]
    idx = max(0, int(np.searchsorted(times, time_h, side="right")) - 1)
    if config.get("schedule_mode", "step") == "linear":
        return tuple(float(np.interp(time_h, times, [s[k] for s in schedule]))
                     for k in ("shelf_temperature_c", "chamber_pressure_pa"))
    return schedule[idx]["shelf_temperature_c"], schedule[idx]["chamber_pressure_pa"]


def geometry(product: dict) -> tuple[float, float, float]:
    ap = math.pi * product["inner_diameter_m"] ** 2 / 4
    av = math.pi * product["outer_diameter_m"] ** 2 / 4
    height = product["fill_m3"] * (1-product["porosity"] + product["porosity"]*RHO_WATER/RHO_ICE) / ap
    return ap, av, height


def state_at(config: dict, time_h: float, dried_m: float) -> dict:
    p, e = config["product"], config["equipment"]
    ap, av, height = geometry(p)
    ts, pc = conditions(config, time_h)
    kv = (e["kv_a_w_m2_k"] + e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc)) * e.get("kv_scale", 1.)
    if not kv > 0:
        raise ValueError("zero heat transfer: no finite drying solution")
    rp = (p["rp0_m_s"] + p["rp1_per_s"]*max(0, dried_m)/(1+p["rp2_per_m"]*max(0, dried_m))) * p.get("rp_scale", 1.)
    if not rp > 0:
        raise ValueError("nonpositive mass-transfer resistance")
    if ice_pressure(min(ts, 0.)) <= pc:
        # Deposition/freezing is outside this forward-sublimation model.
        raise ValueError(f"no sublimation driving force at {time_h:.3f} h: shelf below frost point")
    conductance = av*kv/(1+av*kv*max(0, height-dried_m)/(ap*K_ICE))
    def balance(ti):
        return conductance*(ts-ti) - ap*(ice_pressure(ti)-pc)/rp*H_SUB
    ti = brentq(balance, -100., min(ts, 0.), xtol=1e-9)
    rate = ap*(ice_pressure(ti)-pc)/rp
    return {"interface_temperature_c": ti,
            "bottom_temperature_c": ti+rate*H_SUB*max(0, height-dried_m)/(ap*K_ICE),
            "shelf_temperature_c": ts, "chamber_pressure_pa": pc,
            "sublimation_kg_h": rate*3600*config["load_vials"],
            "heat_w_per_vial": rate*H_SUB, "rate_kg_s_per_vial": rate,
            "critical_margin_c": p["critical_temperature_c"]-ti,
            "capacity_margin_kg_h": e["vapor_capacity_kg_h"]-rate*3600*config["load_vials"]}


def simulate(config: dict, *, sample_step_h: float = .25) -> dict:
    """Piecewise integration; explicit completion event and structured solver failure."""
    validate(config)
    _finite(sample_step_h, "sample_step_h", .01, 2)
    p, e = config["product"], config["equipment"]
    ap, _, height = geometry(p)
    initial = height*config.get("initial_dried_fraction", 0)
    initial_ice = (height-initial)*RHO_ICE*p["porosity"]*ap
    end = config["duration_h"]
    points, solutions, completion, failure = [], [], None, None
    dried = initial
    bounds = sorted(set([0., end, *[s["time_h"] for s in config["schedule"]]]))
    if initial >= height:
        completion = 0.
    for left, right in zip(bounds, bounds[1:]):
        if completion is not None:
            break
        def rhs(t, y):
            # Evaluate left schedule up to the right boundary; restart at each knot.
            h = min(t/3600, np.nextafter(right, left))
            return [state_at(config, h, y[0])["rate_kg_s_per_vial"]/(RHO_ICE*p["porosity"]*ap)]
        def complete(_t, y):
            return y[0]-height
        complete.terminal = True
        complete.direction = 1
        try:
            sol = solve_ivp(rhs, (left*3600, right*3600), [dried], events=complete,
                            dense_output=True, rtol=1e-7, atol=1e-11, max_step=300.)
            if not sol.success:
                failure = sol.message
                break
            solutions.append(sol)
            stop = float(sol.t[-1]/3600)
            grid = sorted(set([left, stop, *np.arange(left, stop, sample_step_h).tolist()]))
            for h in grid:
                ld = min(height, max(initial, float(sol.sol(h*3600)[0])))
                # At a knot the following segment replaces this point.
                row = {"time_h": h, "dried_layer_m": ld,
                       "remaining_ice_kg_per_vial": max(0., (height-ld)*RHO_ICE*p["porosity"]*ap),
                       **state_at(config, h, ld)}
                row["condenser_margin_kg"] = e["condenser_capacity_kg"]-(initial_ice-row["remaining_ice_kg_per_vial"])*config["load_vials"]
                if points and abs(points[-1]["time_h"]-h) < 1e-9:
                    points[-1] = row
                else:
                    points.append(row)
            dried = float(sol.y[0, -1])
            if len(sol.t_events[0]):
                completion = float(sol.t_events[0][0]/3600)
        except (ValueError, RuntimeError, OverflowError) as exc:
            failure = str(exc)
            break
    violations = []
    for key, name in [("critical_margin_c", "critical_temperature"),
                      ("capacity_margin_kg_h", "vapor_capacity"), ("condenser_margin_kg", "condenser_ice_capacity")]:
        bad = [r for r in points if r[key] <= 0]
        if bad:
            violations.append({"constraint": name, "first_time_h": bad[0]["time_h"],
                               "last_time_h": bad[-1]["time_h"], "minimum_margin": min(r[key] for r in bad),
                               "timing_resolution_h": sample_step_h})
    if completion is None and failure is None:
        violations.append({"constraint": "incomplete_primary_drying", "first_time_h": end})
    warnings = ["Reconstruction, not numerical reproduction or a qualified process model.",
                "No residual moisture, potency, release suitability, energy or biological yield is predicted.",
                "Quasi-steady representative vial; no pressure dynamics, edge-vial population or sensible-heat model.",
                "Constraint onset is sampled; the reported resolution bounds warning-time precision."]
    if any(not 5 <= s["chamber_pressure_pa"] <= 25 for s in config["schedule"]):
        warnings.append("Pressure outside published Kv characterization range 5–25 Pa.")
    if any(v["constraint"] in ("vapor_capacity", "condenser_ice_capacity") for v in violations):
        warnings.append("Equipment limit exceeded: imposed-pressure trajectory is an invalid-control diagnostic extrapolation.")
    if failure:
        warnings.append(f"Numerical/operating failure: {failure}")
    return {"model_version": MODEL_VERSION, "classification": "calculated_prediction", "inputs_hash": content_hash(config),
            "solver": {"library": "scipy", "version": scipy.__version__, "integrator": "RK45", "algebraic": "brentq",
                       "rtol": 1e-7, "atol_m": 1e-11, "max_step_s": 300},
            "numerical_status": "failed" if failure else "completed", "numerical_error": failure,
            "completion_time_h": completion, "trajectory": points, "violations": violations,
            "minimum_critical_margin_c": min((r["critical_margin_c"] for r in points), default=None),
            "minimum_capacity_margin_kg_h": min((r["capacity_margin_kg_h"] for r in points), default=None),
            "initial_ice_kg_per_vial": initial_ice,
            "primary_drying_throughput_vials_h": config["load_vials"]/completion if completion and not violations else None,
            "calibration_scope": "Published pilot Kv/Rp characterization only; no fitting to withheld outcomes.",
            "warnings": warnings}


def uncertainty(config: dict, *, samples: int = 16, seed: int = 2025) -> dict:
    if type(samples) is not int or not 2 <= samples <= 128 or type(seed) is not int or seed < 0:
        raise ValueError("uncertainty requires 2..128 samples and a nonnegative integer seed")
    rng = np.random.default_rng(seed)
    runs = []
    for _ in range(samples):
        c = deepcopy(config)
        # Synthetic positive lognormal distributions using published RSDs.
        for block, key, rsd in [("equipment", "kv_scale", c["equipment"].get("kv_rsd", .151)),
                                ("product", "rp_scale", .211)]:
            sigma = math.sqrt(math.log1p(rsd*rsd))
            c[block][key] = c[block].get(key, 1.)*float(rng.lognormal(-sigma*sigma/2, sigma))
        c["product"]["fill_m3"] *= float(rng.normal(1, .09/2.5))
        runs.append(simulate(c, sample_step_h=.5))
    complete = [r["completion_time_h"] for r in runs if r["completion_time_h"] is not None]
    grid = np.arange(0, config["duration_h"]+.01, 1.)
    bands = []
    for h in grid:
        values = []
        for run in runs:
            rows = run["trajectory"]
            if rows and rows[0]["time_h"] <= h <= rows[-1]["time_h"]:
                values.append(float(np.interp(h, [r["time_h"] for r in rows], [r["interface_temperature_c"] for r in rows])))
        if values:
            bands.append({"time_h": float(h), "temperature_c_p05_p50_p95": np.quantile(values, [.05, .5, .95]).tolist(), "active_samples": len(values)})
    return {"method": "independent lognormal Kv/Rp and normal fill; synthetic distribution choice", "seed": seed,
            "samples": samples, "distribution_provenance": "synthetic_assumption", "rsd_source": PAPER+" CMAs variability / Optimal cycle",
            "active_temperature_intervals": bands,
            "completion_time_h_p05_p50_p95_conditional_on_completion": np.quantile(complete, [.05, .5, .95]).tolist() if complete else None,
            "not_completed_samples": samples-len(complete), "failed_solver_samples": sum(r["numerical_status"] == "failed" for r in runs),
            "constraint_sample_frequency": sum(bool(r["violations"]) for r in runs)/samples,
            "interpretation": "Sampling frequency under assumed distributions; not a calibrated real-world failure probability."}
