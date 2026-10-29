"""Bounded numerical pipeline runner; reasoning supplies a validated plan.

Training, holdout observations and visual artifacts remain separate. Models do
not choose their own grading data or infer a 3D temperature field from a scalar.
"""
from __future__ import annotations

from copy import deepcopy
import math
import platform
from time import perf_counter

import numpy as np
import scipy
from scipy.optimize import minimize_scalar

from ..ids import content_hash
from ..lyophilization.model import geometry


class BudgetExceeded(RuntimeError):
    pass


class SolverBudget:
    def __init__(self, calls, seconds):
        self.maximum, self.seconds, self.calls = calls, seconds, 0
        self.started = perf_counter()

    def run(self, adapter, config):
        if self.calls >= self.maximum or perf_counter()-self.started >= self.seconds:
            raise BudgetExceeded("physical pipeline solver-call or wall-time admission budget exhausted")
        self.calls += 1
        return adapter.run(config)


def visible_rows(rows, cutoff):
    fields = ("time_h", "available_at_h", "product_temperature_c")
    out = []
    for row in rows:
        if row["time_h"] <= cutoff and row.get("available_at_h", row["time_h"]) <= cutoff:
            out.append({k: row[k] for k in fields if k in row})
    return sorted(out, key=lambda row: row["time_h"])


def temperature_evaluation(result, observations, observable):
    trajectory = result["trajectory"]
    pairs = []
    for observed in observations:
        t = observed["time_h"]
        if trajectory and trajectory[0]["time_h"] <= t <= trajectory[-1]["time_h"]:
            prediction = float(np.interp(t, [r["time_h"] for r in trajectory], [r[observable] for r in trajectory]))
            pairs.append({"time_h": t, "observed_c": observed["product_temperature_c"], "predicted_c": prediction,
                          "residual_c": prediction-observed["product_temperature_c"]})
    return {"observable": observable, "pairs": pairs, "points": len(pairs),
            "rmse_c": float(np.sqrt(np.mean([r["residual_c"]**2 for r in pairs]))) if pairs else None,
            "coverage": len(pairs)/len(observations) if observations else None,
            "interpretation": "Discrepancy on designated holdout observations; no qualification or calibrated correctness claim."}


def calibrate(adapter, config, training, observable, budget):
    if len(training) < 3:
        raise ValueError("Kv calibration needs at least three training observations")
    cfg = deepcopy(config)
    end = max(r["time_h"] for r in training)
    cfg["duration_h"] = end
    cfg["schedule"] = [s for s in cfg["schedule"] if s["time_h"] <= end]
    def loss(value):
        c = deepcopy(cfg)
        c["equipment"]["kv_scale"] = float(value)
        result = budget.run(adapter, c)
        evaluated = temperature_evaluation(result, training, observable)
        if result["numerical_status"] != "completed" or evaluated["coverage"] != 1.:
            return 1e8
        return evaluated["rmse_c"]**2
    fit = minimize_scalar(loss, bounds=(.5, 1.5), method="bounded", options={"xatol": .01, "maxiter": 12})
    if not fit.success or fit.fun >= 1e8:
        raise ValueError("training fit did not converge; calibrated prediction withheld")
    out = deepcopy(config)
    out["equipment"]["kv_scale"] = float(fit.x)
    return out, {"parameter": "equipment.kv_scale", "bounds": [.5, 1.5], "estimate": float(fit.x),
                 "training_points": len(training), "training_until_h": end, "training_rmse_c": float(math.sqrt(fit.fun)),
                 "scope": "temperature-only fit on training window; not a causal diagnosis; Rp, pressure and mass-rate discrepancies remain unfit"}


def sampling(adapter, config, count, seed, budget):
    rng, runs = np.random.default_rng(seed), []
    for _ in range(count):
        c = deepcopy(config)
        for block, key, rsd in [("equipment", "kv_scale", c["equipment"].get("kv_rsd", .151)), ("product", "rp_scale", .211)]:
            sigma = math.sqrt(math.log1p(rsd**2))
            c[block][key] = c[block].get(key, 1.)*float(rng.lognormal(-sigma*sigma/2, sigma))
        runs.append(budget.run(adapter, c))
    complete = [r["completion_time_h"] for r in runs if r["completion_time_h"] is not None]
    return {"seed": seed, "samples": count, "method": "independent positive lognormal Kv/Rp multipliers; common seed across models",
            "category": "synthetic_assumption", "completion_p05_p50_p95_h": np.quantile(complete, [.05, .5, .95]).tolist() if complete else None,
            "failed_samples": sum(r["numerical_status"] != "completed" for r in runs),
            "not_completed_samples": len(runs)-len(complete),
            "constraint_sample_frequency": sum(bool(r["violations"]) for r in runs)/count if count else None,
            "interpretation": "Outcomes under assumed distributions, not calibrated real-world failure probabilities."}


def review_geometry(config, result):
    _, _, height = geometry(config["product"])
    return {"kind": "representative_vial_cutaway", "inner_diameter_m": config["product"]["inner_diameter_m"],
            "outer_diameter_m": config["product"]["outer_diameter_m"], "frozen_fill_height_m": height,
            "critical_temperature_c": config["product"]["critical_temperature_c"],
            "geometry_provenance": "published vial diameters; fill height derived from published formulation geometry",
            "reconstructed_details": ["glass body height and shelf depiction are schematic", "dried layer is rendered using the modeled planar front"],
            "color_encoding": "uniform model interface temperature; no spatial temperature interpolation",
            "frames": [{k: r[k] for k in ("time_h", "interface_temperature_c", "dried_layer_m", "remaining_ice_kg_per_vial", "critical_margin_c")} for r in result["trajectory"]]}


def execute(plan, catalog):
    spec, source = plan["spec"], plan["source_snapshot"]
    observations = visible_rows(source["observations"], spec["evidence_cutoff_h"])
    training = [r for r in observations if r["time_h"] <= spec["calibration_until_h"]]
    holdout = [r for r in observations if r["time_h"] > spec["calibration_until_h"]]
    budget = SolverBudget(spec["max_solver_calls"], spec["max_wall_seconds"])
    outputs, stages = [], [{"step": "validate_sources_and_models", "status": "completed"}]
    for choice in plan["pinned_models"]:
        adapter = catalog.get(choice["id"])
        config = deepcopy(source["config"])
        status = adapter.applicability(config)
        if not status["applicable"]:
            outputs.append({"model_id": adapter.id, "status": "blocked_missing_inputs", "applicability": status, "rationale": choice["rationale"]})
            continue
        try:
            calibration = {"status": "not_requested", "scope": "uses supplied coefficients unchanged"}
            if spec["calibration"] == "kv_scale":
                config, calibration = calibrate(adapter, config, training, spec["temperature_observable"], budget)
            result = budget.run(adapter, config)
            evaluation_prediction = None
            if holdout:
                # Compare against actually observed source controls. Prospective
                # interventions were not executed and cannot be graded as observations.
                history = deepcopy(config)
                history["schedule"] = [s for s in source["history_config"]["schedule"] if s["time_h"] <= spec["evidence_cutoff_h"]]
                history["load_vials"] = source["history_config"]["load_vials"]
                history["duration_h"] = spec["evidence_cutoff_h"]
                evaluation_prediction = budget.run(adapter, history)
            evaluation = temperature_evaluation(evaluation_prediction or result, holdout, spec["temperature_observable"])
            uncertainty = sampling(adapter, config, spec["samples"], spec["seed"], budget) if spec["samples"] else None
            outputs.append({"model_id": adapter.id, "version": adapter.version, "implementation_digest": adapter.digest,
                "status": "completed" if result["numerical_status"] == "completed" else "numerical_failure",
                "rationale": choice["rationale"], "config": config, "calibration": calibration, "prediction": result,
                "holdout_evaluation": evaluation, "evaluation_prediction": evaluation_prediction, "uncertainty": uncertainty,
                "geometry": review_geometry(config, result) if "vial_3d" in spec["views"] else None})
        except (ValueError, RuntimeError) as exc:
            outputs.append({"model_id": adapter.id, "status": "budget_exhausted" if isinstance(exc, BudgetExceeded) else "failed", "error": str(exc), "rationale": choice["rationale"]})
    eligible = [r for r in outputs if r["status"] == "completed" and r["holdout_evaluation"]["points"] >= 3 and r["holdout_evaluation"]["coverage"] == 1]
    rank = sorted(eligible, key=lambda r: r["holdout_evaluation"]["rmse_c"])
    for stage in plan["steps"][1:]:
        skipped = ((stage["id"] == "calibrate_training_window" and spec["calibration"] == "none") or
                   (stage["id"] == "sample_uncertainty" and not spec["samples"]) or
                   (stage["id"] == "evaluate_holdout" and not holdout))
        stages.append({"step": stage["id"], "status": "not_requested_or_unavailable" if skipped else "completed" if all(r["status"] == "completed" for r in outputs) else "partial_or_blocked"})
    return {"models": outputs, "stages": stages, "ranking": [r["model_id"] for r in rank],
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "random_generator": "NumPy default_rng / PCG64"},
            "ranking_basis": "Lowest temperature RMSE on distinct cutoff-visible holdout times; synthetic / unverified observations do not validate a model.",
            "observation_provenance": source["observation_provenance"], "training_observations": training, "holdout_observations": holdout,
            "data_partition_hash": content_hash({"train": training, "holdout": holdout}),
            "resource_usage": {"solver_calls": budget.calls, "maximum_solver_calls": budget.maximum, "runtime_seconds": perf_counter()-budget.started,
                               "wall_time_policy": "admission checked before each bounded solver call; not a hard process-kill deadline"},
            "execution_status": "completed" if all(r["status"] == "completed" for r in outputs) else "partial_or_blocked",
            "review_state": "requires_engineering_review", "warnings": ["No model is automatically qualified by ranking or added complexity.",
                "Evaluation uses the selected temperature observable only; rate/pressure and final product quality require separate evaluation.",
                "3D geometry shows modeled ice-front progression and scalar temperature, not CFD/FEM results."]}
