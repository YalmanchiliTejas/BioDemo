"""Synthetic evaluator, never returned in an agent's evidence packet.

Independent transient two-population reference: temperature is a state, heat
capacity is finite, vial populations have different Kv and Rp, and chamber
pressure responds to vapor load above a flow ceiling. This is deliberately
structurally richer than the quasi-steady tool. It is NOT experimental truth.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

REFERENCE_VERSION = "two-population-thermal-pressure-2-equilibrium-start"


def reference(config: dict, *, kv_scale=1., rp_scale=1., capacity_scale=1.) -> dict:
    p, e = config["product"], config["equipment"]
    ap, av = math.pi*p["inner_diameter_m"]**2/4, math.pi*p["outer_diameter_m"]**2/4
    h0 = p["fill_m3"]*(1-p["porosity"]+p["porosity"]*1000/918)/ap
    mass0 = h0*918*p["porosity"]*ap
    weights = np.array([.8, .2])
    # Heterogeneous edge heat and pore structure; finite vial/product heat capacity.
    kf, rf = np.array([.96, 1.18])*kv_scale, np.array([1.04, .92])*rp_scale
    schedule = config["schedule"]
    def conditions(t):
        s = schedule[max(0, np.searchsorted([s["time_h"] for s in schedule], t/3600, side="right")-1)]
        return s["shelf_temperature_c"], s["chamber_pressure_pa"]
    def vapor(t):
        tk = np.clip(np.asarray(t)+273.15, 173.15, 273.15)
        return np.exp(9.550426-5723.265/tk+3.53068*np.log(tk)-.00728332*tk)
    def flux(y):
        m = np.maximum(y[:2], 0)
        ld = (mass0-m)/(918*p["porosity"]*ap)
        resistance = (p["rp0_m_s"]+p["rp1_per_s"]*ld/(1+p["rp2_per_m"]*ld))*rf
        rate = ap*np.maximum(vapor(y[2:4])-max(y[4], .1), 0)/resistance
        return np.where(m > 1e-9, rate, 0.)
    def rhs(t, y):
        ts, command = conditions(t)
        pc = max(y[4], .1)
        kv = (e["kv_a_w_m2_k"]+e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc))*kf
        rate = flux(y)
        m = np.maximum(y[:2], 0)
        conductance = av*kv/(1+av*kv*(m/(918*p["porosity"]*ap))/(ap*2.4))
        dtemp = (conductance*(ts-y[2:4])-rate*2.84e6)/(3.+2100*m)
        batch_kg_h = float(weights@rate)*config["load_vials"]*3600
        # Synthetic pressure regulator response; no choked-flow claim.
        ceiling = e["vapor_capacity_kg_h"]*capacity_scale
        target_pc = command+max(0., batch_kg_h/ceiling-1.)*10.
        return [*-rate, *dtemp, (target_pc-y[4])/90.]
    initial_pc = schedule[0]["chamber_pressure_pa"]
    # Primary drying is initialized at the sending steady operating state,
    # rather than imposing an arbitrary -40°C node with unrealistically high
    # initial vapor flux. Solve thermal and pressure-control equilibrium for
    # both populations independently of the tool's algebraic implementation.
    def initial_temperatures(pc):
        ts = schedule[0]["shelf_temperature_c"]
        kv = (e["kv_a_w_m2_k"]+e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc))*kf
        conductance = av*kv/(1+av*kv*h0/(ap*2.4))
        return np.array([brentq(lambda temp: conductance[i]*(ts-temp)-
                              ap*max(0., float(vapor(temp))-pc)/(p["rp0_m_s"]*rf[i])*2.84e6,
                              -100., min(ts, 0.)) for i in range(2)])
    def pressure_balance(pc):
        temps = initial_temperatures(pc)
        y = np.array([mass0, mass0, *temps, pc])
        batch_rate = float(weights@flux(y))*config["load_vials"]*3600
        return pc-initial_pc-max(0., batch_rate/(e["vapor_capacity_kg_h"]*capacity_scale)-1)*10.
    initial_pc_actual = brentq(pressure_balance, initial_pc, 100.)
    state = np.array([mass0, mass0, *initial_temperatures(initial_pc_actual), initial_pc_actual])
    all_t, all_y = [], []
    boundaries = sorted(set([0., config["duration_h"], *[s["time_h"] for s in schedule]]))
    for left, right in zip(boundaries, boundaries[1:]):
        times = np.unique(np.r_[left*3600, np.arange(left*3600, right*3600, 900), right*3600])
        out = solve_ivp(rhs, (left*3600, right*3600), state, t_eval=times, method="LSODA", rtol=2e-6, atol=1e-9, max_step=120.)
        if not out.success:
            raise RuntimeError(out.message)
        all_t.extend(out.t[:-1].tolist())
        all_y.extend(out.y[:, :-1].T.tolist())
        state = out.y[:, -1]
    all_t.append(boundaries[-1]*3600)
    all_y.append(state.tolist())
    rows = []
    for t, values in zip(all_t, all_y):
        y = np.array(values)
        active = y[:2] > 1e-8
        # Monitoring channels are mixture mean thermometry and batch mass loss.
        rows.append({"time_h": t/3600, "available_at_h": t/3600,
                     "product_temperature_c": float(weights@y[2:4]),
                     "sublimation_kg_h": float(weights@flux(y))*config["load_vials"]*3600,
                     "chamber_pressure_pa": float(y[4]),
                     "remaining_ice_kg_per_vial": float(weights@np.maximum(y[:2], 0)),
                     "active_max_temperature_c": float(np.max(y[2:4][active])) if active.any() else None})
    complete = next((r["time_h"] for r in rows if r["remaining_ice_kg_per_vial"] <= mass0*1e-4), None)
    first_critical = next((r["time_h"] for r in rows if r["active_max_temperature_c"] is not None and
                           r["active_max_temperature_c"] >= p["critical_temperature_c"]), None)
    first_capacity = next((r["time_h"] for r in rows if r["sublimation_kg_h"] > e["vapor_capacity_kg_h"]*capacity_scale), None)
    return {"reference_version": REFERENCE_VERSION, "classification": "synthetic_evaluation_only",
            "trajectory": rows, "completion_time_h": complete, "first_critical_h": first_critical,
            "first_capacity_h": first_capacity,
            "limitation": "Synthetic unvalidated reference with shared constitutive laws; errors are not experimental validation."}


def operation_config(*, future_shelf_c: float = -18.) -> dict:
    from .case import receiving_config
    c = receiving_config(shelf_c=-28., load_vials=8000, capacity_kg_h=1.49)
    c["schedule"].append({"time_h": 8., "shelf_temperature_c": future_shelf_c, "chamber_pressure_pa": 8.})
    return c


def demo_observations() -> list[dict]:
    from .workflows import visible_measurements
    return visible_measurements(reference(operation_config(), kv_scale=1.25)["trajectory"], 6.)
