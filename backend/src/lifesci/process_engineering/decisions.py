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


def transfer_assessment(adapter, donor, receiver, criteria, *, receiver_intervals=None):
    if not criteria:
        raise ValueError("Explicit acceptance criteria required")
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
        declared = adapter.describe().get("supported_outputs", {})
        from .contracts import contract

        declared = (
            contract(adapter)["observables"] | declared
            if isinstance(declared, dict)
            else contract(adapter)["observables"]
        )
        # Root summary metrics need explicit units, never a caller-created quality label.
        summary_units = {
            "chemical.parallel_batch": {"product_yield_fraction": "fraction", "impurity_fraction": "fraction"},
            "chemical.semi_batch": {"product_yield_fraction": "fraction", "impurity_fraction": "fraction"},
            "isolation.cake_dryer": {"final_solvent_kg_kg_dry": "kg/kg dry solids"},
        }.get(adapter.id, {})
        declared = {**declared, **summary_units}
        if metric not in declared or declared[metric] != criterion["unit"]:
            checks.append(
                {
                    "metric": metric,
                    "status": "withheld",
                    "reason": "Model does not predict this required quality attribute on the requested unit/basis",
                }
            )
            continue
        expected_basis = MEASUREMENT_BASES.get(adapter.id, {}).get(metric)
        if expected_basis is None or criterion["basis"] != expected_basis:
            checks.append(
                {
                    "metric": metric,
                    "status": "withheld",
                    "reason": "Measurement basis is unsupported or differs from the model-defined quantity",
                    "required_basis": expected_basis,
                }
            )
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
        if method == "noninferiority":
            # A p-value or point estimate is never noninferiority evidence.
            band = (receiver_intervals or {}).get(metric)
            if (
                not band
                or band.get("status") != "empirically_calibrated_conditional"
                or band.get("basis") != criterion["basis"]
                or band.get("unit") != criterion["unit"]
                or "difference_lower" not in band
            ):
                checks.append(
                    {
                        "metric": metric,
                        "status": "withheld",
                        "reason": "Independent compatible calibrated donor-receiver difference interval required; nonsignificance and marginal bands are insufficient",
                    }
                )
                continue
            margin = criterion["margin"]
            if not math.isfinite(margin) or margin < 0:
                raise ValueError("Nonnegative noninferiority margin required")
            passed = band["difference_lower"] >= -margin
        elif method == "absolute":
            limit = criterion["limit"]
            operator = criterion["operator"]
            if not math.isfinite(limit) or operator not in (">=", "<="):
                raise ValueError("Finite threshold and supported operator required")
            passed = b >= limit if operator == ">=" else b <= limit
        else:
            raise ValueError("Only explicit absolute or difference-interval noninferiority criteria supported")
        checks.append(
            {
                "metric": metric,
                "status": "conditional_pass" if passed else "fails_criterion",
                "donor": a,
                "receiver": b,
                "unit": criterion["unit"],
                "basis": criterion["basis"],
                "method": method,
            }
        )
    return {
        "checks": checks,
        "conclusion": "withheld_missing_quality_evidence"
        if any(c["status"] == "withheld" for c in checks)
        else "conditional_model_criteria_met"
        if all(c["status"] == "conditional_pass" for c in checks)
        else "criteria_not_met",
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
