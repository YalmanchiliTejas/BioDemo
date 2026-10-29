"""Event-safe extension of the existing synthetic two-population evaluator.

The original reference clips each population's flux abruptly at a mass threshold.
Some new parameter/action combinations chatter at that discontinuity. Here each
population's ice-depletion event ends a smooth solve, then its flux is disabled
before restarting. Constitutive laws remain shared and unvalidated. Historical
reference code and frozen outputs are deliberately not changed.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

VERSION = "two-population-event-safe-synthetic-1"


def reference(config: dict, mechanism: dict) -> dict:
    p, e = config["product"], config["equipment"]
    ap = math.pi * p["inner_diameter_m"]**2 / 4
    av = math.pi * p["outer_diameter_m"]**2 / 4
    height = p["fill_m3"] * (1-p["porosity"]+p["porosity"]*1000/918) / ap
    mass0 = height * 918 * p["porosity"] * ap
    weights = np.array([.8, .2])
    kf = np.array([.96, 1.18]) * mechanism["kv_scale"]
    rf = np.array([1.04, .92]) * mechanism["rp_scale"]
    ceiling = e["vapor_capacity_kg_h"] * mechanism["capacity_scale"]
    schedule = config["schedule"]
    active = np.array([True, True])
    calls = 0

    def vapor(temp):
        tk = np.clip(np.asarray(temp)+273.15, 173.15, 273.15)
        return np.exp(9.550426-5723.265/tk+3.53068*np.log(tk)-.00728332*tk)

    def flux(y):
        mass = np.maximum(y[:2], 0.)
        layer = (mass0-mass) / (918*p["porosity"]*ap)
        resistance = (p["rp0_m_s"]+p["rp1_per_s"]*layer/(1+p["rp2_per_m"]*layer))*rf
        return np.where(active, ap*np.maximum(vapor(y[2:4])-max(y[4], .1), 0.)/resistance, 0.)

    initial_pressure = schedule[0]["chamber_pressure_pa"]
    def initial_temps(pc):
        ts = schedule[0]["shelf_temperature_c"]
        kv = (e["kv_a_w_m2_k"]+e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc))*kf
        conductance = av*kv/(1+av*kv*height/(ap*2.4))
        return np.array([brentq(lambda temp: conductance[i]*(ts-temp)-ap*max(0., float(vapor(temp))-pc)/(p["rp0_m_s"]*rf[i])*2.84e6,
                              -100., min(ts, 0.)) for i in range(2)])

    def pressure_balance(pc):
        y = np.array([mass0, mass0, *initial_temps(pc), pc])
        rate = float(weights@flux(y))*config["load_vials"]*3600
        return pc-initial_pressure-max(0., rate/ceiling-1.)*10.

    pc = brentq(pressure_balance, initial_pressure, 100.)
    state = np.array([mass0, mass0, *initial_temps(pc), pc])
    times, states, complete_times = [], [], []
    boundaries = sorted({0., config["duration_h"], *(r["time_h"] for r in schedule)})
    for left, right in zip(boundaries, boundaries[1:]):
        command = next(s for s in reversed(schedule) if s["time_h"] <= left)
        def rhs(t, y):
            nonlocal calls
            calls += 1
            if calls > 150000:
                raise RuntimeError("synthetic reference exceeded 150000 RHS evaluations")
            pc = max(y[4], .1)
            kv = (e["kv_a_w_m2_k"]+e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc))*kf
            rate = flux(y)
            mass = np.maximum(y[:2], 0.)
            conductance = av*kv/(1+av*kv*(mass/(918*p["porosity"]*ap))/(ap*2.4))
            dtemp = (conductance*(command["shelf_temperature_c"]-y[2:4])-rate*2.84e6)/(3.+2100*mass)
            batch_rate = float(weights@rate)*config["load_vials"]*3600
            target = command["chamber_pressure_pa"]+max(0., batch_rate/ceiling-1.)*10.
            return [*-rate, *dtemp, (target-y[4])/90.]

        cursor, stop = left*3600, right*3600
        while cursor < stop-1e-7:
            ids = [i for i in range(2) if active[i]]
            events = []
            for index in ids:
                def dry(_t, y, i=index):
                    return y[i]-1e-9
                dry.terminal = True
                dry.direction = -1
                events.append(dry)
            sol = solve_ivp(rhs, (cursor, stop), state, dense_output=True, events=events or None,
                            method="LSODA", rtol=2e-6, atol=1e-10, max_step=120.)
            if not sol.success or not np.isfinite(sol.y).all():
                raise RuntimeError("invalid synthetic drying reference: " + sol.message)
            end = float(sol.t[-1])
            grid = np.unique(np.r_[cursor, np.arange(math.ceil(cursor/900)*900, end, 900), end])
            for t in grid:
                y = sol.sol(t)
                # Rows are evaluated before changing active flags at the endpoint.
                value = {"time_h": float(t/3600), "available_at_h": float(t/3600),
                         "product_temperature_c": float(weights@y[2:4]),
                         "sublimation_kg_h": float(weights@flux(y))*config["load_vials"]*3600,
                         "chamber_pressure_pa": float(y[4]),
                         "remaining_ice_kg_per_vial": float(weights@np.maximum(y[:2], 0.)),
                         "active_max_temperature_c": float(np.max(y[2:4][active])) if active.any() else None}
                if times and abs(times[-1]-t) < 1e-6:
                    states[-1] = value
                else:
                    times.append(float(t))
                    states.append(value)
            state = sol.y[:, -1].copy()
            ended = [ids[j] for j, event in enumerate(sol.t_events or []) if len(event)]
            for index in ended:
                active[index] = False
                state[index] = 0.
                complete_times.append(end/3600)
            if end <= cursor+1e-8 and not ended:
                raise RuntimeError("synthetic reference made no progress")
            cursor = end
    rows = states
    completion = max(complete_times) if len(complete_times) == 2 else None
    critical = next((r["time_h"] for r in rows if r["active_max_temperature_c"] is not None and r["active_max_temperature_c"] >= p["critical_temperature_c"]), None)
    capacity = next((r["time_h"] for r in rows if r["sublimation_kg_h"] > ceiling), None)
    return {"reference_version": VERSION, "classification": "synthetic_evaluation_only",
            "trajectory": rows, "completion_time_h": completion,
            "first_critical_h": critical, "first_capacity_h": capacity,
            "rhs_evaluations": calls,
            "limitation": "Unvalidated two-population reference derived from existing equations; event times and sampled constraint times have different resolutions."}
