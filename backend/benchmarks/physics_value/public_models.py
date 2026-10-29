"""B-arm forward tools. This module never imports the dataset or evaluator.

Both arms receive equations and nominal inputs. B additionally receives these
executables; no tool returns a causal label or selects the best intervention.
"""
from __future__ import annotations

from copy import deepcopy
import math

from src.lifesci.fermentation.model import compression_kw
from src.lifesci.lyophilization.model import simulate

VERSION = "physics-value-public-forward-1"


def notes(domain: str) -> dict:
    return {"version": VERSION, "domain": domain,
            "classification": "unqualified_synthetic_pilot_model",
            "equations": (["Cstar = air_saturation * broth_factor * P_absolute/P_ambient * yO2/0.2095",
                           "OTR = kLa * (Cstar - dissolved_oxygen)",
                           "steady dissolved_oxygen = Cstar - OUR/kLa",
                           "isothermal compression work proportional to flow * log(P_absolute/P_ambient)/efficiency"]
                          if domain == "oxygen" else
                          ["heat input = Kv * vial_area * (shelf_temperature - vial_bottom_temperature)",
                           "sublimation rate = product_area * (ice_vapor_pressure - chamber_pressure)/Rp",
                           "heat input = sublimation rate * latent_heat; frozen layer conducts heat",
                           "integrate remaining ice; compare thermal, vapor and condenser limits"]),
            "limitations": (["Steady uniform liquid; no gas response, sensor error, oxygen-limited uptake or time-varying kLa.",
                             "No growth, viability, product titer or validated cost-of-goods prediction."]
                            if domain == "oxygen" else
                            ["Quasi-steady representative vial, no population or pressure-control dynamics.",
                             "No residual moisture, potency, final product release or rescue prediction."]),
            "parameter_rule": "Nominal characterization is supplied to both arms; revised parameters need cited measurements or explicit assumptions.",
            "selection_rule": "Forward calculation only; agent chooses hypotheses, measurements and actions."}


def predict(packet: dict, action_id: str = "keep", *, parameter_overrides: dict | None = None) -> dict:
    domain = packet["domain"]
    action = next((a for a in packet["allowed_actions"] if a["id"] == action_id), None)
    if action is None:
        raise ValueError("action not available for this task")
    # Public-only schedule editing. Do not import host-side domains/reference.
    config = deepcopy(packet["receiving_configuration"])
    at = packet["decision_time_h"]
    change = action["changes"]
    if "load_factor" in change:
        if packet["task"] != "pretransfer":
            raise ValueError("load changes require a pretransfer decision")
        config["load_vials"] = int(config["load_vials"] * change["load_factor"])
    if change:
        current = next(s for s in reversed(config["schedule"]) if s["time_h"] <= at)
        future = [dict(current, time_h=at)] + [deepcopy(s) for s in config["schedule"] if s["time_h"] > at]
        for row in future:
            row.update({k: v for k, v in change.items() if k not in ("load_factor", "feed_factor")})
            if "feed_factor" in change:
                row["our_mg_l_h"] *= change["feed_factor"]
        config["schedule"] = [s for s in config["schedule"] if s["time_h"] < at] + future
    overrides = parameter_overrides or {}
    allowed = {"kla_h_inv", "our_scale", "broth_factor"} if domain == "oxygen" else {"kv_scale", "rp_scale"}
    if set(overrides) - allowed:
        raise ValueError("unsupported physical parameter")
    for key, value in overrides.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("physical parameter must be positive and finite")
        if domain == "oxygen":
            if key != "our_scale":
                config[key] = value
        else:
            config["equipment" if key == "kv_scale" else "product"][key] = value
    if domain == "freeze_drying":
        result = simulate(config, sample_step_h=.25)
    elif domain == "oxygen":
        rows = []
        for command in config["schedule"]:
            cstar = config["air_saturation_mg_l"] * config["broth_factor"] * (
                (config["ambient_kpa"] + command["pressure_gauge_kpa"]) / config["ambient_kpa"]
            ) * command["oxygen_fraction"] / .2095
            do = cstar - command["our_mg_l_h"] * overrides.get("our_scale", 1.) / config["kla_h_inv"]
            kw = compression_kw(config["air_nm3_h"], command["pressure_gauge_kpa"], config["ambient_kpa"], .65)
            rows.append({"time_h": command["time_h"], "steady_do_mg_l": do,
                         "oxygen_margin_mg_l": do-config["minimum_do_mg_l"], "compression_kw": kw})
        result = {"classification": "steady_prediction_not_observation", "schedule_predictions": rows}
    else:
        raise ValueError("unknown process domain")
    return {"tool_version": VERSION, "action_id": action_id, "parameters": overrides,
            "result": result, "applicability": notes(domain)["limitations"]}
