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
MODEL_BASED = ("Model-based range: the physics run at every combination of the stated tolerances. Conditional on the "
               "model's equations and on the tolerances being right; not calibrated and not a probability.")


def _model_based(entry, criterion, metric, a, b, donor_corners, receiver_corners):
    """Verdict from the corner runs. A corner where the run stops means the process can fail within tolerance."""
    def spread(corners, nominal):
        stops = [c for c in corners if c["status"] != "completed"]
        values = [nominal, *[float(value_at(c, metric)) for c in corners if c["status"] == "completed"]]
        return min(values), max(values), stops

    r_lo, r_hi, r_stops = spread(receiver_corners, b)
    entry = {**entry, "basis_of_range": MODEL_BASED, "corner_runs": len(receiver_corners) + len(donor_corners)}
    if r_stops:
        worst = r_stops[0]
        return {**entry, "status": "at_risk", "stopping_corners": [
            {"tolerances": c["assignment"], "violations": c.get("violations") or [c.get("error", "solver failure")]} for c in r_stops],
            "reason": f"Within the stated tolerances the receiving run stops ({', '.join(worst.get('violations') or ['solver failure'])}) "
                      f"at {', '.join(f'{k}={v:g}' for k, v in worst['assignment'].items())}"}
    higher = criterion["operator"] == ">="
    if criterion.get("method", "absolute") == "absolute":
        limit = criterion["limit"]
        entry.update(receiver_range=[r_lo, r_hi], limit=limit)
        ok, bad = (r_lo >= limit, r_hi < limit) if higher else (r_hi <= limit, r_lo > limit)
    else:
        d_lo, d_hi, d_stops = spread(donor_corners, a)
        if d_stops:
            return {**entry, "status": "indicative_only", "reason": "The sending-site run stops within its stated tolerances"}
        margin = criterion["margin"]
        diff = [r_lo - d_hi, r_hi - d_lo]
        entry.update(difference_range=diff, margin=margin)
        ok, bad = (diff[0] >= -margin, diff[1] < -margin) if higher else (diff[1] <= margin, diff[0] > margin)
    status = "model_based_pass" if ok else "model_based_fail" if bad else "inconclusive"
    return {**entry, "status": status, **({"reason": "The model-based range straddles the limit; measure the most "
                                                     "uncertain term to narrow it"} if status == "inconclusive" else {})}


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


def check_criteria(adapter, criteria):
    """Validate criteria before any solver runs; errors name the criterion and say what to send instead."""
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("Explicit acceptance criteria required: a list of {metric, unit, operator, limit}")
    out = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise ValueError("Each criterion is an object: {metric, unit, operator, limit}")
        metric = criterion.get("metric") or "?"
        where = f"Criterion {metric}: "
        extra = set(criterion) - {"metric", "unit", "basis", "operator", "limit", "margin", "role", "method"}
        if extra:
            raise ValueError(where + f"unknown fields {sorted(extra)}; allowed: metric, unit, basis, operator, limit, margin, role, method")
        role, method, operator = criterion.get("role", "quality"), criterion.get("method", "absolute"), criterion.get("operator")
        if not criterion.get("unit"):
            raise ValueError(where + "unit required")
        # Omitted basis means the model's own defined quantity, stated back in the result; a different one is withheld.
        basis = criterion.get("basis") or MEASUREMENT_BASES.get(adapter.id, {}).get(metric) or ""
        if not basis:
            raise ValueError(where + "explicit compatible measurement basis required")
        if role == "yield" and ("conversion" in metric or "conversion" in basis.lower()):
            raise ValueError(where + "reactant conversion cannot serve as desired-product yield")
        if method not in ("absolute", "noninferiority"):
            raise ValueError(where + "method is 'absolute' (with limit) or 'noninferiority' (with margin)")
        if operator not in (">=", "<="):
            raise ValueError(where + "operator '>=' (higher is better) or '<=' (lower is better) required")
        number = lambda k: isinstance(criterion.get(k), (int, float)) and not isinstance(criterion.get(k), bool) and math.isfinite(criterion[k])
        if method == "absolute" and not number("limit"):
            raise ValueError(where + f"absolute criteria need a numeric limit in {criterion['unit']} (got {criterion.get('limit')!r}); "
                                     "to compare with the sending site use method 'noninferiority' with a margin")
        if method == "noninferiority" and (not number("margin") or criterion["margin"] < 0):
            raise ValueError(where + f"noninferiority needs a numeric margin >= 0 (got {criterion.get('margin')!r})")
        out.append({**criterion, "basis": basis, "role": role, "method": method})
    return out


def transfer_assessment(adapter, donor, receiver, criteria, *, donor_interval=None, receiver_interval=None,
                        donor_corners=(), receiver_corners=()):
    """Screen explicit criteria. A verdict needs a range wholly on one side of the limit (or margin):
    - calibrated: from an empirical interval calibration on real batches (conditional_pass / fails_criterion);
    - model-based: the physics run at every combination of stated tolerances (model_based_pass / model_based_fail),
      conditional on the model's equations, never a probability;
    otherwise indicative_only. A single model estimate or a range straddling the limit is never a verdict."""
    from .contracts import contract

    checks = []
    for criterion in check_criteria(adapter, criteria):
        metric, role, method, operator = criterion["metric"], criterion["role"], criterion["method"], criterion["operator"]
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
        if not completed(donor):
            checks.append({"metric": metric, "status": "withheld",
                           "reason": "The sending-site run does not complete: " + ", ".join(donor.get("violations") or ["solver failure"])})
            continue
        if not completed(receiver):
            if receiver.get("violations"):  # the receiving equipment cannot run the recipe: a finding, not a gap
                checks.append({"metric": metric, "status": "model_based_fail", "violations": receiver["violations"],
                               "stopped_at_s": receiver.get("completed_duration_s"),
                               "reason": "At the receiving site's nominal values the run stops: " + ", ".join(receiver["violations"])})
            else:
                checks.append({"metric": metric, "status": "withheld", "reason": "Receiving-site solver did not complete"})
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
        calibrated = not why and r_band["calibration_status"] == REAL and (not d_band or d_band["calibration_status"] == REAL)
        if not calibrated and receiver_corners:
            checks.append(_model_based(entry, criterion, metric, a, b, donor_corners, receiver_corners))
            continue
        if not calibrated:
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
    conclusion = ("criteria_not_met" if statuses & {"fails_criterion", "model_based_fail"}
                  else "withheld_missing_quality_evidence" if "withheld" in statuses
                  else "at_risk_within_tolerances" if "at_risk" in statuses
                  else "conditional_model_criteria_met" if statuses == {"conditional_pass"}
                  else "model_based_criteria_met" if statuses <= {"conditional_pass", "model_based_pass"}
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
