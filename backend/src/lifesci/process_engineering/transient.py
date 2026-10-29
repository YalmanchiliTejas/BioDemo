"""Experimental lumped thermal model; independent of evaluator-only reference.

C_eff dTi/dt = Av Kv (Ts-Ti)/(1+Av Kv Lice/(Ap kice)) - mdot Hsub
dm_ice/dt = -Ap max(Pice(Ti)-Pc,0)/Rp(Ld).
The thermal node approximates the frozen product/interface, not a resolved
temperature field. Vial heat capacity and initial temperature need provenance.
Pressure remains prescribed: equipment overload is a diagnostic extrapolation.
"""
from __future__ import annotations

import numpy as np
import scipy
from scipy.integrate import solve_ivp

from ..ids import content_hash
from ..lyophilization.model import H_SUB, K_ICE, RHO_ICE, conditions, geometry, ice_pressure, validate, _finite

VERSION = "lumped-thermal-primary-drying-1.0.0"
ICE_CP_J_KG_K = 2100.  # constant approximation, not locally characterized


def simulate(config: dict) -> dict:
    validate(config)
    thermal = config.get("thermal", {})
    capacity = _finite(thermal.get("vial_heat_capacity_j_k"), "thermal.vial_heat_capacity_j_k", .1, 100.)
    initial_t = thermal.get("initial_temperature_c")
    if initial_t is None:
        raise ValueError("thermal.initial_temperature_c requires an explicit measured or assumed initial state")
    initial_t = _finite(initial_t, "thermal.initial_temperature_c", -65., -1.)
    p, e = config["product"], config["equipment"]
    ap, av, height = geometry(p)
    initial_mass = height*(1-config.get("initial_dried_fraction", 0))*RHO_ICE*p["porosity"]*ap
    y = [initial_mass, initial_t]
    rows, completion, error = [], 0. if initial_mass <= 0 else None, None
    def fields(t, state):
        mass, ti = max(0., float(state[0])), float(state[1])
        ld = height-mass/(RHO_ICE*p["porosity"]*ap)
        ts, pc = conditions(config, t/3600)
        kv = (e["kv_a_w_m2_k"]+e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc))*e.get("kv_scale", 1.)
        rp = (p["rp0_m_s"]+p["rp1_per_s"]*max(0, ld)/(1+p["rp2_per_m"]*max(0, ld)))*p.get("rp_scale", 1.)
        mdot = ap*max(0., ice_pressure(ti)-pc)/rp if mass > 0 else 0.
        q = av*kv*(ts-ti)/(1+av*kv*mass/(RHO_ICE*p["porosity"]*ap)/(ap*K_ICE))
        return {"time_h": t/3600, "dried_layer_m": min(height, max(0., ld)),
                "remaining_ice_kg_per_vial": mass, "interface_temperature_c": ti,
                "bottom_temperature_c": ti+q*mass/(RHO_ICE*p["porosity"]*ap)/(ap*K_ICE),
                "shelf_temperature_c": ts, "chamber_pressure_pa": pc,
                "rate_kg_s_per_vial": mdot, "sublimation_kg_h": mdot*3600*config["load_vials"],
                "heat_w_per_vial": q, "sensible_heat_w_per_vial": q-mdot*H_SUB,
                "critical_margin_c": p["critical_temperature_c"]-ti,
                "capacity_margin_kg_h": e["vapor_capacity_kg_h"]-mdot*3600*config["load_vials"],
                "condenser_margin_kg": e["condenser_capacity_kg"]-(initial_mass-mass)*config["load_vials"]}
    boundaries = sorted(set([0., config["duration_h"], *[s["time_h"] for s in config["schedule"]]]))
    for left, right in zip(boundaries, boundaries[1:]):
        if completion is not None:
            break
        def rhs(t, state):
            r = fields(min(t, np.nextafter(right*3600, left*3600)), state)
            return [-r["rate_kg_s_per_vial"], r["sensible_heat_w_per_vial"]/(capacity+max(0., state[0])*ICE_CP_J_KG_K)]
        def complete(t, state):
            return state[0]
        complete.terminal, complete.direction = True, -1
        try:
            out = solve_ivp(rhs, (left*3600, right*3600), y, method="BDF", events=complete,
                            dense_output=True, rtol=1e-6, atol=[1e-11, 1e-6], max_step=300.)
            if not out.success:
                error = out.message
                break
            stop = float(out.t[-1]/3600)
            for h in sorted(set([left, stop, *np.arange(left, stop, .25).tolist()])):
                row = fields(h*3600, out.sol(h*3600))
                if rows and abs(rows[-1]["time_h"]-h) < 1e-9:
                    rows[-1] = row
                else:
                    rows.append(row)
            y = out.y[:, -1]
            if len(out.t_events[0]):
                completion = float(out.t_events[0][0]/3600)
        except (ValueError, RuntimeError, OverflowError) as exc:
            error = str(exc)
            break
    violations = []
    for field, name in [("critical_margin_c", "critical_temperature"), ("capacity_margin_kg_h", "vapor_capacity"), ("condenser_margin_kg", "condenser_ice_capacity")]:
        bad = [r for r in rows if r[field] <= 0]
        if bad:
            violations.append({"constraint": name, "first_time_h": bad[0]["time_h"], "minimum_margin": min(r[field] for r in bad), "timing_resolution_h": .25})
    if completion is None and error is None:
        violations.append({"constraint": "incomplete_primary_drying", "first_time_h": config["duration_h"]})
    warnings = ["Experimental, unqualified lumped thermal model; no spatial temperature field or pressure dynamics.",
                "Forward sublimation only; deposition during cold starts is excluded. Ice specific heat is approximated as 2100 J/(kg K).",
                "Thermal capacity and initial temperature are additional inputs requiring characterization.",
                "No residual moisture, potency, energy-system consumption or product release prediction."]
    if any(v["constraint"] in ("vapor_capacity", "condenser_ice_capacity") for v in violations):
        warnings.append("Capacity exceeded: prescribed-pressure trajectory is an invalid-control diagnostic extrapolation.")
    return {"model_version": VERSION, "classification": "calculated_prediction", "inputs_hash": content_hash(config),
            "solver": {"library": "scipy", "version": scipy.__version__, "integrator": "BDF", "rtol": 1e-6, "max_step_s": 300.},
            "numerical_status": "failed" if error else "completed", "numerical_error": error,
            "completion_time_h": completion, "trajectory": rows, "violations": violations,
            "initial_ice_kg_per_vial": initial_mass, "warnings": warnings,
            "additional_constants": {"ice_specific_heat": {"value": ICE_CP_J_KG_K, "unit": "J/(kg K)", "category": "synthetic_assumption", "source": "constant physical-property approximation"}},
            "minimum_critical_margin_c": min((r["critical_margin_c"] for r in rows), default=None),
            "minimum_capacity_margin_kg_h": min((r["capacity_margin_kg_h"] for r in rows), default=None)}
