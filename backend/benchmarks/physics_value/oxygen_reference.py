"""Synthetic oxygen evaluator; not organism kinetics or experimental validation.

Unlike the agent's steady balance, this integrates oxygen storage, a gas actuator,
oxygen-limited uptake and fluctuating transfer. No yield or batch-release model.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.integrate import solve_ivp

from src.lifesci.fermentation.model import compression_kw

VERSION = "synthetic-oxygen-storage-actuator-1"


def setting(config: dict, time_h: float) -> dict:
    return next(row for row in reversed(config["schedule"]) if row["time_h"] <= time_h)


def reference(config: dict, mechanism: dict) -> dict:
    """Full synthetic trajectory, including evaluator-only physical channels."""
    duration = config["duration_h"]
    kla = config["kla_h_inv"] * mechanism["kla_scale"]
    ambient = config["ambient_kpa"]
    tau = mechanism["gas_time_constant_h"]

    def saturation(row):
        return config["air_saturation_mg_l"] * config["broth_factor"] * (
            (ambient + row["pressure_gauge_kpa"]) / ambient
        ) * row["oxygen_fraction"] / .2095

    def rhs(t, state):
        row = setting(config, t)
        do = max(0., state[0])
        potential_our = row["our_mg_l_h"] * mechanism["our_scale"]
        uptake = potential_our * do / (.05 + do)
        transfer = kla * (1 + .04 * math.sin(.7 * t)) * (state[1] - do)
        return [transfer - uptake, (saturation(row) - state[1]) / tau]

    initial_star = saturation(config["schedule"][0])
    # Positive equilibrium of kLa(Cstar-C) = OUR*C/(K+C).
    our = config["schedule"][0]["our_mg_l_h"] * mechanism["our_scale"]
    b = kla * (.05 - initial_star) + our
    initial_do = (-b + math.sqrt(b*b + 4*kla*kla*.05*initial_star)) / (2*kla)
    state = [initial_do, initial_star]
    rows = []
    bounds = sorted({0., duration, *(r["time_h"] for r in config["schedule"])})
    for left, right in zip(bounds, bounds[1:]):
        # Restart at discontinuities; do not let future commands enter old steps.
        def local_rhs(t, y):
            return rhs(min(t, np.nextafter(right, left)), y)
        grid = np.unique(np.r_[left, np.arange(left, right, .25), right])
        sol = solve_ivp(local_rhs, (left, right), state, t_eval=grid,
                        rtol=1e-8, atol=1e-10, max_step=.02)
        if not sol.success or not np.isfinite(sol.y).all() or sol.y[0].min() < -1e-6:
            raise RuntimeError("invalid synthetic oxygen trajectory: " + sol.message)
        for t, y in zip(sol.t[:-1], sol.y.T[:-1]):
            rows.append(_row(config, mechanism, float(t), y, kla))
        state = sol.y[:, -1]
    rows.append(_row(config, mechanism, duration, state, kla))
    bad = [r for r in rows if r["dissolved_oxygen_mg_l"] < config["minimum_do_mg_l"]]
    # Utility cost is a declared synthetic partial objective, not total COGS.
    cost = 0.
    feed_penalty = 0.
    for a, z in zip(rows, rows[1:]):
        command = setting(config, a["time_h"])
        kw = compression_kw(config["air_nm3_h"], command["pressure_gauge_kpa"], ambient, .65)
        oxygen = config["air_nm3_h"] * max(0., command["oxygen_fraction"]-.2095) / max(1e-9, 1-command["oxygen_fraction"])
        dt = z["time_h"] - a["time_h"]
        cost += dt * (kw * config["electricity_usd_kwh"] + oxygen * config["oxygen_usd_nm3"])
        feed_penalty += dt * max(0., command.get("requested_our_mg_l_h", command["our_mg_l_h"]) - command["our_mg_l_h"]) * .05
    return {"reference_version": VERSION, "trajectory": rows,
            "completion_time_h": duration, "first_critical_h": bad[0]["time_h"] if bad else None,
            "first_capacity_h": None, "partial_utility_cost_usd": cost,
            "synthetic_feed_curtailment_penalty_usd": feed_penalty,
            "objective_value": cost + feed_penalty,
            "oxygen_deficit_mg_h_l": float(np.trapezoid(
                [max(0., config["minimum_do_mg_l"]-r["dissolved_oxygen_mg_l"]) for r in rows],
                [r["time_h"] for r in rows])),
            "classification": "synthetic_evaluation_only"}


def _row(config, mechanism, time_h, state, kla):
    row = setting(config, time_h)
    return {"time_h": time_h, "available_at_h": time_h,
            "dissolved_oxygen_mg_l": float(max(0., state[0])),
            "gas_saturation_mg_l": float(state[1]),
            "actual_kla_h_inv": kla * (1 + .04 * math.sin(.7 * time_h)),
            "potential_our_mg_l_h": row["our_mg_l_h"] * mechanism["our_scale"],
            "pressure_gauge_kpa": row["pressure_gauge_kpa"],
            "oxygen_fraction": row["oxygen_fraction"], "feed_demand_mg_l_h": row["our_mg_l_h"]}
