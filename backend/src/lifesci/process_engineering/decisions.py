"""Explicit measurement-basis decisions; no conversion/yield substitution."""

from copy import deepcopy
import math
from .contracts import value_at, completed
from .uncertainty import ensemble

MEASUREMENT_BASES = {
    "chemical.parallel_batch": {
        "product_yield_fraction": "desired_product_mol_per_initial_reactant_mol",
        "impurity_fraction": "impurity_mol_per_initial_reactant_mol",
    },
    "chemical.semi_batch": {
        "product_yield_fraction": "desired_product_mol_per_total_charged_reactant_mol",
        "impurity_fraction": "impurity_mol_per_total_charged_reactant_mol",
    },
    "isolation.cake_dryer": {"final_solvent_kg_kg_dry": "solvent_mass_per_dry_solids_mass"},
    "tablet.shrinking_area_dissolution": {"dissolved_fraction": "dissolved_drug_mass_per_initial_drug_mass"},
}


REAL = "empirically_calibrated_conditional"


def _band(adapter, interval, metric, unit, result):
    """The calibrated range for a metric's end-of-run value, from an interval prediction, or why there is none."""
    if not interval:
        return None, "No interval calibration attached; a single model estimate cannot pass or fail a criterion"
    if interval.get("calibrated_lower") is None:
        reasons = interval.get("unsupported_input_conditions") or []
        return None, ("Outside the calibrated operating range: " + ", ".join(reasons)) if reasons else (
            "Interval prediction abstained or failed; no calibrated range")
    rows = [(i, r) for i, r in enumerate(interval["basis"]) if r[0] == metric and r[1] == unit]
    from .contracts import contract

    axis = contract(adapter)["axis"]
    end = 0.0 if axis == "none" else (result.get("trajectory") or [{}])[-1].get(axis)
    if not rows:
        return None, "The interval calibration does not cover this metric"
    i, row = max(rows, key=lambda x: x[1][2])
    if end is None or abs(float(row[2]) - float(end)) > 1e-6 * max(1.0, abs(float(end))):
        return None, "The interval calibration does not cover the end-of-run value this criterion uses"
    return {"lower": interval["calibrated_lower"][i], "upper": interval["calibrated_upper"][i],
            "calibration_status": interval["calibration_status"]}, None


def transfer_assessment(adapter, donor, receiver, criteria, *, donor_interval=None, receiver_interval=None):
    """Screen explicit criteria. A pass or fail needs the whole calibrated range on one side of the limit (or margin);
    a single model estimate, a synthetic-only calibration or a range straddling the limit is never a verdict."""
    if not criteria:
        raise ValueError("Explicit acceptance criteria required")
    from .contracts import contract

    checks = []
    for criterion in criteria:
        if set(criterion) - {"metric", "unit", "basis", "operator", "limit", "margin", "role", "method"}:
            raise ValueError("Unknown criterion fields")
        metric = criterion["metric"]
        role = criterion.get("role", "quality")
        method = criterion.get("method", "absolute")
        if not criterion.get("basis") or not criterion.get("unit"):
            raise ValueError("Explicit unit and compatible measurement basis required")
        if role == "yield" and ("conversion" in metric or "conversion" in criterion["basis"].lower()):
            raise ValueError("Reactant conversion cannot serve as desired-product yield")
        if method not in ("absolute", "noninferiority"):
            raise ValueError("Only explicit absolute or difference-interval noninferiority criteria supported")
        operator = criterion.get("operator")
        if operator not in (">=", "<="):
            raise ValueError("Operator >= (higher is better) or <= (lower is better) required")
        if method == "absolute" and not math.isfinite(criterion.get("limit", float("nan"))):
            raise ValueError("Finite threshold required")
        if method == "noninferiority" and (not math.isfinite(criterion.get("margin", float("nan"))) or criterion["margin"] < 0):
            raise ValueError("Nonnegative noninferiority margin required")
        declared = adapter.describe().get("supported_outputs", {})
        declared = contract(adapter)["observables"] | declared if isinstance(declared, dict) else contract(adapter)["observables"]
        if metric not in declared or declared[metric] != criterion["unit"]:
            checks.append({"metric": metric, "status": "withheld",
                           "reason": "Model does not predict this required quality attribute on the requested unit/basis"})
            continue
        expected_basis = MEASUREMENT_BASES.get(adapter.id, {}).get(metric)
        if expected_basis is None or criterion["basis"] != expected_basis:
            checks.append({"metric": metric, "status": "withheld", "required_basis": expected_basis,
                           "reason": "Measurement basis is unsupported or differs from the model-defined quantity"})
            continue
        if not completed(donor) or not completed(receiver):
            checks.append({"metric": metric, "status": "withheld", "reason": "Solver did not complete"})
            continue
        try:
            a, b = float(value_at(donor, metric)), float(value_at(receiver, metric))
        except (KeyError, TypeError, ValueError):
            checks.append({"metric": metric, "status": "withheld", "reason": "Required summary observable unavailable"})
            continue
        if not math.isfinite(a + b):
            raise ValueError("Nonfinite decision metric")
        higher = operator == ">="
        entry = {"metric": metric, "unit": criterion["unit"], "basis": criterion["basis"], "method": method,
                 "operator": operator, "donor_estimate": a, "receiver_estimate": b}
        r_band, r_why = _band(adapter, receiver_interval, metric, criterion["unit"], receiver)
        d_band, d_why = (_band(adapter, donor_interval, metric, criterion["unit"], donor) if method == "noninferiority" else (None, None))
        why = r_why or d_why
        if why or r_band["calibration_status"] != REAL or (d_band and d_band["calibration_status"] != REAL):
            # Shown for orientation only: which side of the limit the single estimate lands on is not evidence.
            checks.append({**entry, "status": "indicative_only",
                           "reason": why or "Calibrated on synthetic data only; not a real-world coverage claim"})
            continue
        if method == "absolute":
            limit = criterion["limit"]
            lo, hi = r_band["lower"], r_band["upper"]
            entry.update(receiver_range=[lo, hi], limit=limit)
            ok, bad = (lo >= limit, hi < limit) if higher else (hi <= limit, lo > limit)
        else:
            # receiver - donor, from simultaneous ranges; joint coverage >= 1 - 2*alpha by the union bound.
            margin = criterion["margin"]
            diff = [r_band["lower"] - d_band["upper"], r_band["upper"] - d_band["lower"]]
            entry.update(difference_range=diff, margin=margin, coverage_note="Each range covers at 1-alpha; jointly at least 1-2*alpha")
            ok, bad = (diff[0] >= -margin, diff[1] < -margin) if higher else (diff[1] <= margin, diff[0] > margin)
        entry["status"] = "conditional_pass" if ok else "fails_criterion" if bad else "inconclusive"
        if entry["status"] == "inconclusive":
            entry["reason"] = "The calibrated range straddles the limit; more data or a measurement is needed to decide"
        checks.append(entry)
    statuses = {c["status"] for c in checks}
    conclusion = ("criteria_not_met" if "fails_criterion" in statuses
                  else "withheld_missing_quality_evidence" if "withheld" in statuses
                  else "conditional_model_criteria_met" if statuses == {"conditional_pass"}
                  else "inconclusive_uncertainty")
    return {
        "checks": checks,
        "conclusion": conclusion,
        "authorization": "draft_requires_engineering_review",
        "risk_probability": None,
        "limitation": "Conditional model-based screen, not approved process transfer or measured yield protection.",
    }


def rank_experiments(adapter, config, candidates, decision, *, checkpoint=None, budget=None):
    """Decision-focused threshold ambiguity reduction proxy, not causal EVSI."""
    if (
        not decision.get("observable")
        or not decision.get("unit")
        or not math.isfinite(decision.get("threshold", float("nan")))
    ):
        raise ValueError("Identified transfer decision observable, unit and threshold required")
    if not 1 <= len(candidates) <= 12:
        raise ValueError("1..12 feasible candidate designs required")
    ranked = []
    rejected = []
    for candidate in candidates:
        if not candidate.get("measurement") or not candidate.get("conditions") or candidate.get("cost", 0) <= 0:
            raise ValueError("Experiment needs measurement, physical conditions and positive relative cost")
        c = deepcopy(config)
        from .contracts import set_value

        for path, value in candidate["conditions"].items():
            set_value(c, path, value)
        try:
            if not adapter.applicability(c)["applicable"]:
                raise ValueError("outside declared model applicability")
            obs = [
                {
                    "coordinate": decision.get("coordinate", 0.0),
                    "observable": decision["observable"],
                    "unit": decision["unit"],
                    "value": 0.0,
                }
            ]
            p = ensemble(
                adapter,
                c,
                obs,
                checkpoint=checkpoint,
                mode="hybrid" if checkpoint else "physics",
                samples=3,
                distributions=decision.get("distributions", ()),
                budget=budget,
            )
            if p["status"] != "completed" or p.get("abstention") or p["constraint_violating_predictions"]:
                raise ValueError("unsupported, incomplete or constraint-violating candidate")
            values = [r[0] for r in p["predictions"]]
            threshold = decision["threshold"]
            width = max(values) - min(values)
            straddles = min(values) <= threshold <= max(values)
            if width <= 1e-12:
                raise ValueError(
                    "No modeled decision uncertainty; supply characterized parameter/measurement variation before ranking experiments"
                )
            declared_resolution = candidate.get("measurement_resolution")
            if not isinstance(declared_resolution, (int, float)) or declared_resolution <= 0:
                raise ValueError("Positive measurement resolution in observable units required")
            utility = (width / (width + declared_resolution)) * (1.0 if straddles else 0.1) / candidate["cost"]
            ranked.append(
                {
                    **candidate,
                    "decision_observable": decision["observable"],
                    "unit": decision["unit"],
                    "utility_proxy": utility,
                    "predicted_range": [min(values), max(values)],
                    "threshold_straddled": straddles,
                    "rationale": "Prioritize feasible measurements whose modeled spread can change this threshold decision relative to resolution and stated cost.",
                    "limitations": "Heuristic decision-discrimination proxy; not calibrated expected information gain, intervention benefit or validated experiment feasibility.",
                }
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            rejected.append({"candidate": candidate, "reason": str(exc)})
    return {
        "ranked": sorted(ranked, key=lambda r: r["utility_proxy"], reverse=True),
        "rejected": rejected,
        "decision": decision,
        "approval": "proposal_only",
    }
