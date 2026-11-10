"""Pre-transfer equipment check: what changes between the sites, and whether the receiving equipment can do what the
process needs. Needs come from the sending-site run (the recipe as it actually behaves); capacities from the
receiving site's configured equipment. Model-based, conditional on the model's equations; not a qualification.
"""
from __future__ import annotations

import math

from .uncertainty import physical_domain


def changes(donor_config, receiver_config):
    """Every numeric input that differs between the two configurations, with its relative change."""
    d, r = physical_domain(donor_config), physical_domain(receiver_config)
    out = []
    for key in sorted(set(d) | set(r)):
        a, b = d.get(key), r.get(key)
        if a == b:
            continue
        rel = (b - a) / abs(a) if a not in (None, 0) and b is not None else None
        out.append({"input": key, "sending": a, "receiving": b, "relative_change": rel})
    return out


def _heat_removal(donor_config, donor_result, receiver_config, receiver_result):
    from ..chemical_reactor.model import rates, validate

    d, r = validate(donor_config), validate(receiver_config)
    rows = donor_result.get("trajectory") or []
    if not rows:
        return []
    # Peak heat released per m3 along the sending-site run. At the receiving site a hotter batch reacts faster,
    # so this is a lower bound on the receiving need, never an overstatement of it.
    peak = 0.0
    for row in rows:
        kb, ki = rates(row["temperature_k"], d.chemistry)
        conc = row["a_mol"] / d.equipment.working_volume_m3
        peak = max(peak, (-d.chemistry.product_enthalpy_j_mol * kb - d.chemistry.impurity_enthalpy_j_mol * ki) * conc)

    def side(c):
        need = peak * c.equipment.working_volume_m3
        capacity = c.equipment.heat_transfer_area_m2 * c.equipment.heat_transfer_coefficient_w_m2_k * (
            c.recipe.temperature_limit_k - c.equipment.coolant_temperature_k)
        return need, capacity

    (dn, dc), (rn, rc) = side(d), side(r)
    margin = rc / rn - 1 if rn > 0 else None
    return [{
        "capability": "Heat removal at peak reaction heat",
        "unit": "W",
        "sending_need": dn, "sending_capacity": dc,
        "receiving_need": rn, "receiving_capacity": rc,
        "receiving_margin_fraction": margin,
        "status": "short" if margin is not None and margin < 0 else "sufficient" if margin is not None else "unknown",
        "how": "Need: peak heat released per m3 in the sending-site run x receiving volume (a lower bound: a hotter "
               "batch reacts faster). Capacity: U x A x (temperature limit - coolant temperature).",
        "drivers": ["equipment.working_volume_m3", "equipment.heat_transfer_area_m2",
                    "equipment.heat_transfer_coefficient_w_m2_k", "equipment.coolant_temperature_k",
                    "recipe.temperature_limit_k"],
    }]


# Family-specific need-versus-capacity checks. Families without one still get the run-to-completion check below.
CHECKS = {"chemical.parallel_batch": _heat_removal}


def capabilities(adapter, donor_config, donor_result, receiver_config, receiver_result):
    out = []
    check = CHECKS.get(adapter.id)
    if check:
        try:
            out.extend(check(donor_config, donor_result, receiver_config, receiver_result))
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            out.append({"capability": "Family capability check", "status": "unknown", "reason": str(exc)})
    for label, result in (("sending", donor_result), ("receiving", receiver_result)):
        done = result.get("status", result.get("numerical_status", "completed")) == "completed"
        violations = list(result.get("violations") or [])
        stopped_at = result.get("completed_duration_s")
        out.append({
            "capability": f"Recipe runs to completion at the {label} site",
            "status": "sufficient" if done and not violations else "short" if violations else "unknown",
            "violations": violations,
            **({"stopped_at_s": stopped_at} if not done and isinstance(stopped_at, (int, float)) and math.isfinite(stopped_at) else {}),
        })
    return {
        "checks": out,
        "family_check": "implemented" if check else "not_available_for_this_model: only the run-to-completion check applies",
        "scope": "Model-based screen of the configured equipment; not equipment qualification or a safety assessment.",
    }


if __name__ == "__main__":
    from ..chemical_reactor.demo import example, receiver_example
    from .catalog import ModelCatalog

    a = ModelCatalog(None).get("chemical.parallel_batch")
    donor, receiver = example(), receiver_example(example())
    report = capabilities(a, donor, a.run(donor), receiver, a.run(receiver))
    heat = report["checks"][0]
    assert heat["status"] == "short" and heat["sending_capacity"] > heat["sending_need"], heat
    assert {c["input"] for c in changes(donor, receiver)} == {"equipment.working_volume_m3", "equipment.heat_transfer_area_m2",
                                                             "equipment.heat_transfer_coefficient_w_m2_k"}
    print("ok", round(heat["receiving_need"]), round(heat["receiving_capacity"]))
