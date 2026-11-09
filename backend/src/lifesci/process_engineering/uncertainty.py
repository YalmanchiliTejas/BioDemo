"""Solver-propagated ensembles plus a DISTINCT whole-run interval calibrator.

Empirical bands target the declared measured observable/basis. Exchangeability
of independent calibration/test batches is an assumption, never inferred from
many time points or from the names assigned to batches.
"""

from copy import deepcopy
import math

import numpy as np

from ..ids import content_hash
from .contracts import predict, set_value
from .hybrid import run_hybrid

VERSION = "group-split-intervals-1"


def physical_domain(config, prefix=""):
    out = {}
    if isinstance(config, dict):
        for key, value in config.items():
            if key in ("source_refs", "evidence_classification") or key.endswith("_id"):
                continue
            out.update(physical_domain(value, prefix + "." + key if prefix else key))
    elif type(config) in (int, float) and math.isfinite(config):
        out[prefix] = float(config)
    return out


def ensemble(
    adapter, config, observations, *, checkpoint=None, mode="physics", samples=8, seed=1, distributions=(), budget=None
):
    if not 2 <= samples <= 32:
        raise ValueError("2..32 solver-propagated samples required")
    if mode not in ("physics", "refit", "hybrid"):
        raise ValueError("Unknown prediction mode")
    if mode != "physics" and not checkpoint:
        raise ValueError("A fitted checkpoint is required for learned/refitted predictions")
    rng = np.random.default_rng(seed)
    predictions = []
    physical_predictions = []
    failures = []
    violations = 0
    ood = 0
    output_std = np.array([r.get("measurement_std", 0.0) for r in observations])
    if not np.isfinite(output_std).all() or np.any(output_std < 0):
        raise ValueError("Finite nonnegative output measurement uncertainty required")
    components = {k: [] for k in ("measurement", "parameter", "learned_model")}
    for d in distributions:
        if d["category"] not in ("measurement", "parameter") or not math.isfinite(d["std"]) or d["std"] < 0:
            raise ValueError("Explicit nonnegative uncertainty std and category required")
        from .contracts import value_at

        if not math.isfinite(float(value_at(config, d["path"]))):
            raise ValueError("Uncertain input must be a finite physical value")
        from .contracts import input_units

        if input_units(adapter).get(d["path"]) != d.get("unit"):
            raise ValueError("Uncertain input path/unit not declared by adapter")

    def once(c, index):
        def runner(cfg):
            work = lambda: (
                adapter.run(cfg)
                if mode == "physics"
                else run_hybrid(adapter, cfg, checkpoint, member_index=index, mode=mode)
            )
            return budget.call(work) if budget else work()

        p, result = predict(adapter, c, observations, runner=runner)
        return p, result

    for index in range(samples):
        trial = deepcopy(config)
        try:
            for d in distributions:
                from .contracts import value_at

                set_value(trial, d["path"], float(value_at(config, d["path"]) + rng.normal(0, d["std"])))
            p, result = once(trial, index)
            physical_predictions.append(p.tolist())
            predictions.append(p + rng.normal(0, output_std))
            violations += bool(result.get("violations"))
            ood += bool(result.get("hybrid", {}).get("out_of_domain"))
        except (ValueError, KeyError, RuntimeError, ArithmeticError) as exc:
            failures.append({"sample": index, "error": str(exc), "kind": type(exc).__name__})
    if not predictions:
        return {
            "status": "failed",
            "failed_predictions": len(failures),
            "failures": failures,
            "risk_probability": None,
            "calibration_status": "uncalibrated",
        }
    a = np.asarray(predictions)
    # Component-only propagation uses the same physical solver; no fabricated
    # variance decomposition when components are nonlinear or unspecified.
    for category in components:
        subset = [d for d in distributions if d["category"] == category]
        if category == "learned_model":
            if mode != "hybrid":
                continue
        elif not subset and not (category == "measurement" and np.any(output_std)):
            continue
        for index in range(min(samples, 4)):
            trial = deepcopy(config)
            for d in subset:
                from .contracts import value_at

                set_value(trial, d["path"], float(value_at(config, d["path"]) + rng.normal(0, d["std"])))
            try:
                p, _ = once(trial, index if category == "learned_model" else 0)
                if category == "measurement":
                    p = p + rng.normal(0, output_std)
                components[category].append(p.tolist())
            except (ValueError, KeyError, RuntimeError, ArithmeticError):
                components[category].append(None)
    return {
        "status": "partial" if failures else "completed",
        "predictions": a.tolist(),
        "physical_predictions": physical_predictions,
        "measurement_target": "Future measured observable; declared output noise is applied after the conserved physical solve",
        "mean": a.mean(0).tolist(),
        "lower": np.quantile(a, 0.1, axis=0).tolist(),
        "upper": np.quantile(a, 0.9, axis=0).tolist(),
        "basis": _basis(observations),
        "ensemble_band": "10th..90th sample quantiles, NOT calibrated intervals",
        "seed": seed,
        "samples_requested": samples,
        "successful_predictions": len(predictions),
        "failed_predictions": len(failures),
        "failures": failures,
        "constraint_violating_predictions": violations,
        "out_of_domain_predictions": ood,
        "abstention": bool(failures or ood),
        "calibration_status": "uncalibrated",
        "risk_probability": None,
        "uncertainty_components": {
            "measurement": {
                "component_predictions": components["measurement"] or "not_specified",
                "declared_output_std": output_std.tolist(),
                "input_distributions": [d for d in distributions if d["category"] == "measurement"],
            },
            "parameter": components["parameter"]
            or ("bootstrap constant-rate fits" if mode == "refit" else "not_specified"),
            "learned_model": components["learned_model"] or "not_applicable",
            "structural_discrepancy": "not quantified; ensemble cannot identify omitted physical mechanisms",
        },
        "component_note": "Component-only sample trajectories, not additive independent variances.",
    }


def _basis(observations):
    return [(r["observable"], r["unit"], r["coordinate"]) for r in observations]


def calibrate_intervals(
    adapter,
    runs,
    *,
    checkpoint=None,
    mode="physics",
    alpha=0.1,
    samples=8,
    seed=1,
    distributions=(),
    budget=None,
    minimum_groups=9,
):
    if not 0.01 <= alpha <= 0.5:
        raise ValueError("alpha must be in [.01,.5]")
    used = set()
    scores = []
    failures = []
    basis = None
    synthetic = False
    training = (
        set(
            checkpoint.get(
                "development_run_ids", checkpoint.get("training_run_ids", []) + checkpoint.get("selection_run_ids", [])
            )
        )
        if checkpoint
        else set()
    )
    training_groups = (
        {tuple(g) for g in checkpoint.get("development_groups", checkpoint.get("training_batches", []))}
        if checkpoint
        else set()
    )
    for run in runs:
        group = (run["site_id"], run["batch_id"])
        if (
            run["role"] != "calibration"
            or run.get("augmented")
            or run["run_id"] in training
            or group in training_groups
        ):
            raise ValueError("Interval calibration must use disjoint, original whole calibration batches")
        if group in used:
            raise ValueError(
                "Time points/replicate summaries cannot be counted as separate independent calibration batches"
            )
        used.add(group)
        synthetic |= run["evidence_classification"].startswith("synthetic")
        current = _basis(run["observations"])
        if basis is None:
            basis = current
        if basis != current or [r.get("scale", 1.0) for r in run["observations"]] != [
            r.get("scale", 1.0) for r in runs[0]["observations"]
        ]:
            raise ValueError("Calibration requires compatible observable, unit, fixed scale and prediction grid")
        predicted = ensemble(
            adapter,
            run["config"],
            run["observations"],
            checkpoint=checkpoint,
            mode=mode,
            samples=samples,
            seed=seed,
            distributions=distributions,
            budget=budget,
        )
        if predicted["status"] != "completed" or predicted.get("abstention"):
            failures.append({"run_id": run["run_id"], "reason": "failed_or_out_of_domain"})
            continue
        actual = np.asarray([r["value"] for r in run["observations"]])
        lo = np.asarray(predicted["lower"])
        hi = np.asarray(predicted["upper"])
        # Normalized whole-run nonconformity across potentially different units.
        scales = np.asarray([r.get("scale", 1.0) for r in run["observations"]])
        if np.any(scales <= 0) or not np.isfinite(scales).all():
            raise ValueError("Positive fixed calibration scales required")
        scores.append(float(np.max(np.maximum.reduce([lo - actual, actual - hi, np.zeros_like(actual)]) / scales)))
    # Synthetic perturbations and published aggregate summaries are not real
    # independent calibration batches, however many IDs they carry.
    eligible = all(
        r["evidence_classification"] in ("measured_unverified", "published_experimental", "measured")
        and bool(r.get("independence_basis"))
        for r in runs
    )
    development_n = len(scores)
    n = development_n if eligible else 0
    k = math.ceil((n + 1) * (1 - alpha))
    status = "uncalibrated"
    q = None
    if n >= minimum_groups and k <= n and not failures:
        q = float(sorted(scores)[k - 1])
        status = "calibrated_synthetic_only" if synthetic else "empirically_calibrated_conditional"
    domains = [physical_domain(r["config"]) for r in runs]
    domain = (
        {
            key: [min(d[key] for d in domains), max(d[key] for d in domains)]
            for key in set.intersection(*(set(d) for d in domains))
        }
        if domains
        else {}
    )
    return {
        "input_support": domain,
        "version": VERSION,
        "model_id": adapter.id,
        "adapter_digest": adapter.digest,
        "checkpoint_hash": content_hash(checkpoint) if checkpoint else None,
        "mode": mode,
        "alpha": alpha,
        "status": status,
        "q": q,
        "independent_calibration_groups": n,
        "required_order_statistic": k,
        "minimum_groups": minimum_groups,
        "basis": basis,
        "scales": [r.get("scale", 1.0) for r in runs[0]["observations"]] if runs else [],
        "calibration_groups": [list(g) for g in sorted(used)],
        "calibration_run_ids": [r["run_id"] for r in runs],
        "calibration_scores": scores,
        "development_diagnostic_groups": development_n,
        "independence_eligible": eligible,
        "failed_predictions": failures,
        "samples": samples,
        "seed": seed,
        "distributions": list(distributions),
        "measurement_scope": "Predicts future measured observables; calibration residuals include measurement error and model discrepancy without identifying their causes.",
        "coverage_assumptions": [
            "Independent exchangeable calibration/test batches on the same measurement basis and operating population.",
            "Training, model selection and augmentation completed before these calibration observations were used.",
            "No missing/failed/OOD calibration predictions silently excluded; whole-run maximum scores target simultaneous grid coverage.",
            "Synthetic-only calibration is an executable algorithm check, not a real-world coverage claim.",
        ],
        "risk_probability": None,
        "reason": "Insufficient original independently supported measured batches, or unsupported/failed predictions"
        if q is None
        else "Finite-sample split-conformal order statistic under stated assumptions",
    }


def interval_prediction(adapter, config, observations, calibration, *, checkpoint=None, budget=None):
    if (
        calibration["model_id"] != adapter.id
        or calibration["adapter_digest"] != adapter.digest
        or calibration["checkpoint_hash"] != (content_hash(checkpoint) if checkpoint else None)
    ):
        raise ValueError("Calibration belongs to a different physical/learned model version")
    if _basis(observations) != [tuple(r) for r in (calibration["basis"] or [])]:
        raise ValueError("Prediction measurement basis differs from interval calibration")
    result = ensemble(
        adapter,
        config,
        observations,
        checkpoint=checkpoint,
        mode=calibration["mode"],
        samples=calibration["samples"],
        seed=calibration["seed"],
        distributions=calibration["distributions"],
        budget=budget,
    )
    current = physical_domain(config)
    outside = [
        k
        for k, (lo, hi) in calibration.get("input_support", {}).items()
        if k not in current
        or current[k] < lo - max(0.1 * (hi - lo), 1e-9)
        or current[k] > hi + max(0.1 * (hi - lo), 1e-9)
    ]
    result["unsupported_input_conditions"] = outside
    if outside:
        result["abstention"] = True
    valid = calibration["q"] is not None and result["status"] == "completed" and not result.get("abstention")
    result["calibration_status"] = calibration["status"] if valid else "uncalibrated"
    result["calibrated_lower"] = (
        (np.array(result["lower"]) - calibration["q"] * np.array(calibration["scales"])).tolist() if valid else None
    )
    result["calibrated_upper"] = (
        (np.array(result["upper"]) + calibration["q"] * np.array(calibration["scales"])).tolist() if valid else None
    )
    result["coverage_assumptions"] = calibration["coverage_assumptions"]
    result["risk_probability"] = None
    return result


def evaluate_intervals(adapter, runs, calibration, *, checkpoint=None, budget=None):
    rows = []
    covered = []
    widths = []
    errors = []
    per_field = {}
    forbidden = set(calibration["calibration_run_ids"])
    if checkpoint:
        forbidden.update(
            checkpoint.get("development_run_ids", checkpoint["training_run_ids"] + checkpoint["selection_run_ids"])
        )
    forbidden_groups = {tuple(g) for g in calibration["calibration_groups"]}
    if checkpoint:
        forbidden_groups.update(tuple(g) for g in checkpoint.get("development_groups", checkpoint["training_batches"]))
    for run in runs:
        if (
            run["role"] != "test"
            or run.get("augmented")
            or run["run_id"] in forbidden
            or (run["site_id"], run["batch_id"]) in forbidden_groups
        ):
            raise ValueError("Final evaluation must use untouched independent test batches")
        p = interval_prediction(
            adapter, run["config"], run["observations"], calibration, checkpoint=checkpoint, budget=budget
        )
        observed = np.array([r["value"] for r in run["observations"]])
        entry = {
            "run_id": run["run_id"],
            "status": p["status"],
            "calibration_status": p["calibration_status"],
            "failed_predictions": p["failed_predictions"],
            "constraint_violations": p.get("constraint_violating_predictions", 0),
            "abstained": p.get("calibrated_lower") is None,
        }
        if p.get("mean"):
            residual = np.array(p["mean"]) - observed
            errors.extend(residual.tolist())
            for i, obs in enumerate(run["observations"]):
                item = per_field.setdefault(
                    obs["observable"], {"unit": obs["unit"], "errors": [], "widths": [], "covered": []}
                )
                item["errors"].append(float(residual[i]))
                if p.get("calibrated_lower") is not None:
                    lo = p["calibrated_lower"][i]
                    hi = p["calibrated_upper"][i]
                    item["widths"].append(hi - lo)
                    item["covered"].append(lo <= obs["value"] <= hi)
        if p.get("calibrated_lower") is not None:
            lo = np.array(p["calibrated_lower"])
            hi = np.array(p["calibrated_upper"])
            ok = bool(np.all((lo <= observed) & (observed <= hi)))
            covered.append(ok)
            widths.extend((hi - lo).tolist())
            entry["whole_run_covered"] = ok
        rows.append(entry)
    per_observable = {
        key: {
            "unit": v["unit"],
            "rmse": float(np.sqrt(np.mean(np.array(v["errors"]) ** 2))),
            "mean_interval_width": float(np.mean(v["widths"])) if v["widths"] else None,
            "point_coverage": float(np.mean(v["covered"])) if v["covered"] else None,
        }
        for key, v in per_field.items()
    }
    mixed = len({v["unit"] for v in per_field.values()}) > 1
    return {
        "per_observable": per_observable,
        "runs": rows,
        "planned_test_batches": len(runs),
        "scored_coverage_batches": len(covered),
        "whole_run_coverage": float(np.mean(covered)) if covered else None,
        "mean_interval_width": float(np.mean(widths)) if widths and not mixed else None,
        "rmse": float(np.sqrt(np.mean(np.array(errors) ** 2))) if errors and not mixed else None,
        "coverage_interpretation": "Empirical only; report denominator, abstentions, failures and the stated exchangeability assumptions. Mixed-unit width/RMSE require per-observable review.",
        "abstentions": sum(r["abstained"] for r in rows),
        "failed_predictions": sum(r["failed_predictions"] for r in rows),
        "constraint_violations": sum(r["constraint_violations"] for r in rows),
    }
