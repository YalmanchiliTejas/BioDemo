"""Host-side scenario construction, noisy observations and intervention replay."""
from __future__ import annotations

from copy import deepcopy

import numpy as np

from src.lifesci.lyophilization.reference import operation_config

from .lyo_reference import reference as lyo_reference
from .oxygen_reference import reference as oxygen_reference

DOMAIN_FAMILIES = {
    "oxygen": ("nominal", "low_transfer", "high_demand", "sensor_bias", "mixed", "gas_lag"),
    "freeze_drying": ("nominal", "high_heat_transfer", "high_resistance", "sensor_bias", "mixed", "low_capacity"),
}
TASKS = ("diagnosis", "optimization", "resolution", "pretransfer")


def make_case(domain: str, family: str, rng) -> tuple[dict, dict, dict]:
    """All new variation is synthetic; historical published inputs are unchanged."""
    if domain == "oxygen":
        config = {"duration_h": 24., "kla_h_inv": float(rng.uniform(17., 19.)),
                  "ambient_kpa": 101.325, "air_saturation_mg_l": 8., "broth_factor": 1.,
                  "minimum_do_mg_l": 1.5, "air_nm3_h": 36.,
                  "electricity_usd_kwh": .12, "oxygen_usd_nm3": .20,
                  "maximum_pressure_gauge_kpa": 120.,
                  "schedule": [{"time_h": 0., "pressure_gauge_kpa": 50., "oxygen_fraction": .2095, "our_mg_l_h": 80.},
                               {"time_h": 8., "pressure_gauge_kpa": 50., "oxygen_fraction": .2095, "our_mg_l_h": 160.}]}
        mechanism = {"kla_scale": 1., "our_scale": 1., "gas_time_constant_h": .04, "sensor_bias": 0.}
        if family in ("low_transfer", "mixed"):
            mechanism["kla_scale"] = float(rng.uniform(.48, .58))
        if family in ("high_demand", "mixed"):
            mechanism["our_scale"] = float(rng.uniform(1.5, 1.7))
        if family == "sensor_bias":
            mechanism["sensor_bias"] = -3.
        if family == "gas_lag":
            mechanism["gas_time_constant_h"] = .8
            config["schedule"][1].update(pressure_gauge_kpa=100., our_mg_l_h=245.)
        source = deepcopy(config)
        source["schedule"] = [deepcopy(config["schedule"][0])]
        source["duration_h"] = 6.
    else:
        # Reuse the earlier operations benchmark's -18 C planned step. This
        # preserves a nominal control while exposing shifted thermal mechanisms.
        config = operation_config(future_shelf_c=-18.)
        config["load_vials"] = int(rng.integers(7500, 8501))
        config["product"]["fill_m3"] *= float(rng.uniform(.96, 1.04))
        mechanism = {"kv_scale": 1., "rp_scale": 1., "capacity_scale": 1., "sensor_bias": 0.}
        if family in ("high_heat_transfer", "mixed"):
            mechanism["kv_scale"] = float(rng.uniform(1.4, 1.55))
        if family in ("high_resistance", "mixed"):
            mechanism["rp_scale"] = float(rng.uniform(1.5, 1.7))
        if family == "sensor_bias":
            mechanism["sensor_bias"] = 3.
        if family == "low_capacity":
            # This transfer mismatch is visible in the receiving specification.
            # It is not a hidden fault guessed from nonexistent receiving traces.
            config["equipment"]["vapor_capacity_kg_h"] = float(rng.uniform(.52, .62))
        source = deepcopy(config)
        source["load_vials"] = 800
        source["equipment"]["vapor_capacity_kg_h"] = .4
        source["schedule"] = [deepcopy(config["schedule"][0])]
        source["duration_h"] = 6.
    return config, mechanism, source


def run_reference(domain: str, config: dict, mechanism: dict) -> dict:
    if domain == "oxygen":
        return oxygen_reference(config, mechanism)
    return lyo_reference(config, mechanism)


def nominal_mechanism(domain: str) -> dict:
    return ({"kla_scale": 1., "our_scale": 1., "gas_time_constant_h": .04, "sensor_bias": 0.}
            if domain == "oxygen" else
            {"kv_scale": 1., "rp_scale": 1., "capacity_scale": 1., "sensor_bias": 0.})


def observe(domain: str, result: dict, mechanism: dict, rng) -> list[dict]:
    """Generate once, then share byte-identical observations across arms/cutoffs."""
    rows = []
    for raw in result["trajectory"]:
        row = {"time_h": raw["time_h"], "available_at_h": raw["time_h"]}
        if domain == "oxygen":
            row.update(dissolved_oxygen_mg_l=raw["dissolved_oxygen_mg_l"] + mechanism["sensor_bias"] + float(rng.normal(0, .08)),
                       pressure_gauge_kpa=raw["pressure_gauge_kpa"], oxygen_fraction=raw["oxygen_fraction"],
                       feed_demand_mg_l_h=raw["feed_demand_mg_l_h"])
        else:
            row.update(product_temperature_c=raw["product_temperature_c"] + mechanism["sensor_bias"] + float(rng.normal(0, .12)),
                       chamber_pressure_pa=raw["chamber_pressure_pa"] + float(rng.normal(0, .03)))
        rows.append(row)
    return rows


def actions(domain: str, *, pretransfer: bool = False) -> list[dict]:
    if domain == "oxygen":
        return [{"id": "keep", "description": "Keep the planned schedule", "changes": {}},
                {"id": "pressure", "description": "Use 100 kPa gauge air", "changes": {"pressure_gauge_kpa": 100.}},
                {"id": "enrich", "description": "Use oxygen mole fraction 0.32", "changes": {"oxygen_fraction": .32}},
                {"id": "reduce_feed", "description": "Reduce oxygen-demand feed proxy to 70%", "changes": {"feed_factor": .7}}]
    result = [{"id": "keep", "description": "Keep the planned schedule", "changes": {}},
              {"id": "cool", "description": "Use shelf -28 degrees C", "changes": {"shelf_temperature_c": -28.}},
              {"id": "colder", "description": "Use shelf -32 degrees C", "changes": {"shelf_temperature_c": -32.}}]
    if pretransfer:
        result += [{"id": "half_load", "description": "Use half the planned load and shelf -28 degrees C",
                    "changes": {"load_factor": .5, "shelf_temperature_c": -28.}}]
    return result


def apply_action(domain: str, config: dict, action: dict, time_h: float, *, pretransfer=False) -> dict:
    if not 0 <= time_h < config["duration_h"]:
        raise ValueError("intervention must precede the end of the batch")
    result = deepcopy(config)
    change = action["changes"]
    if not change:
        return result
    if "load_factor" in change:
        if not pretransfer or time_h != 0:
            raise ValueError("loading cannot be changed during a batch")
        result["load_vials"] = int(result["load_vials"] * change["load_factor"])
    old = config["schedule"]
    current = next(s for s in reversed(old) if s["time_h"] <= time_h)
    future = [dict(current, time_h=time_h)] + [deepcopy(s) for s in old if s["time_h"] > time_h]
    for row in future:
        for key, value in change.items():
            if key not in ("load_factor", "feed_factor"):
                row[key] = value
        if "feed_factor" in change:
            row["requested_our_mg_l_h"] = row["our_mg_l_h"]
            row["our_mg_l_h"] *= change["feed_factor"]
    result["schedule"] = [deepcopy(s) for s in old if s["time_h"] < time_h] + future
    return result


def outcome(domain: str, result: dict, config: dict, decision_h: float) -> dict:
    complete = result["completion_time_h"]
    events = [v for v in (result["first_critical_h"], result["first_capacity_h"]) if v is not None]
    first = min(events) if events else None
    feasible = complete is not None and not events
    # We do not describe correction of a later trajectory as rescue of prior damage.
    return {"completed": complete is not None, "completion_time_h": complete,
            "thermal_or_oxygen_onset_h": result["first_critical_h"],
            "capacity_onset_h": result["first_capacity_h"], "first_issue_h": first,
            "issue_precedes_decision": first is not None and first < decision_h,
            "feasible_full_batch": feasible,
            "objective_name": "partial_utility_cost_plus_synthetic_feed_penalty_usd" if domain == "oxygen" else "negative_primary_drying_throughput_vials_h",
            "objective_value": result["objective_value"] if domain == "oxygen" else (-config["load_vials"] / complete if complete else None),
            "classification": "synthetic_outcome_not_real_batch_failure"}


def measurement_catalog(domain: str) -> list[dict]:
    if domain == "oxygen":
        names = [("sensor_check", 1., "Independent dissolved-oxygen probe calibration"),
                 ("uptake_assay", 2., "Independent oxygen-demand assay"),
                 ("transfer_test", 2., "Independent kLa characterization"),
                 ("gas_response_test", 2., "Gas response characterization")]
    else:
        names = [("sensor_check", 1., "Independent thermometry calibration"),
                 ("gravimetry", 2., "Independent batch mass-loss measurement"),
                 ("edge_thermometry", 2., "Additional edge-vial thermometry"),
                 ("capacity_test", 3., "Receiving vapor-capacity characterization")]
    return [{"id": name, "turnaround_h": hours, "human_work_minutes": 15.,
             "description": desc, "classification": "synthetic_experiment_cost_assumption"}
            for name, hours, desc in names]


def measure(case: dict, name: str, at_h: float, *, pretransfer=False) -> dict:
    """Host-owned experiment result; never put every result in an initial packet."""
    domain, config, mechanism = case["domain"], case["config"], case["mechanism"]
    if name not in {m["id"] for m in measurement_catalog(domain)}:
        raise ValueError("unknown measurement")
    if at_h > config["duration_h"]:
        raise ValueError("measurement arrives after the simulated batch")
    if name == "sensor_check":
        value = {"sensor_bias": mechanism["sensor_bias"], "unit": "mg/L" if domain == "oxygen" else "degrees C"}
    elif name == "uptake_assay":
        row = next(r for r in reversed(config["schedule"]) if r["time_h"] <= at_h)
        value = {"oxygen_demand_mg_l_h": row["our_mg_l_h"] * mechanism["our_scale"]}
    elif name == "transfer_test":
        value = {"kla_h_inv": config["kla_h_inv"] * mechanism["kla_scale"]}
    elif name == "gas_response_test":
        value = {"gas_time_constant_h": mechanism["gas_time_constant_h"]}
    elif name == "capacity_test":
        value = {"vapor_capacity_kg_h": config["equipment"]["vapor_capacity_kg_h"] * mechanism["capacity_scale"]}
    else:
        raw = next(r for r in reversed(case["reference"]["trajectory"]) if r["time_h"] <= at_h)
        value = ({"sublimation_kg_h": raw["sublimation_kg_h"]} if name == "gravimetry" else
                 {"active_edge_temperature_c": raw["active_max_temperature_c"]})
    return {"measurement": name, "available_at_h": at_h, "values": value,
            "classification": "synthetic_assay_exact_in_this_pilot",
            "limitation": "Ideal assay; measurement noise is present in routine traces only."}
