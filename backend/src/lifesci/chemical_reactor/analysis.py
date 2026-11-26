"""Evidence-labelled calibration, sensitivity and explicit yield comparison."""
from copy import deepcopy

import numpy as np
from scipy.optimize import least_squares

from ..ids import content_hash
from .model import VERSION, simulate, validate

FIT_FIELDS = {"heat_transfer_coefficient_w_m2_k": "equipment",
              "product_rate_ref_s_inv": "chemistry"}


def _observations(rows):
    if not rows:
        raise ValueError("observations must not be empty")
    for row in rows:
        if set(row) != {"time_s", "temperature_k", "source_ref"}:
            raise ValueError("observations require time_s, temperature_k and source_ref only")
        if not row["source_ref"] or not isinstance(row["source_ref"], str):
            raise ValueError("each observation requires a source_ref")
        if any(isinstance(row[k], bool) or not isinstance(row[k], (int, float)) or
               not np.isfinite(row[k]) for k in ("time_s", "temperature_k")):
            raise ValueError("observation values must be finite numeric SI values")
        if row["time_s"] < 0 or not 250 < row["temperature_k"] < 450:
            raise ValueError("observation outside time/temperature envelope")
    if any(a["time_s"] >= b["time_s"] for a, b in zip(rows, rows[1:])):
        raise ValueError("observation times must strictly increase")


def fit_parameters(config, observations, *, fields, bounds, training_until_s):
    """Only cutoff-visible rows enter optimization; later rows are holdout diagnostics.

    Bounds are explicit engineering hypotheses, not a posterior or validated range.
    Local Jacobian rank is a diagnostic, not proof of global identifiability.
    """
    c = validate(config).model_dump()
    _observations(observations)
    if not fields or len(set(fields)) != len(fields) or any(f not in FIT_FIELDS for f in fields):
        raise ValueError("choose distinct supported fit fields")
    if not isinstance(training_until_s, (int, float)) or isinstance(training_until_s, bool) or not np.isfinite(training_until_s):
        raise ValueError("training cutoff must be finite")
    if not 0 < training_until_s < c["recipe"]["duration_s"]:
        raise ValueError("training cutoff must be inside the requested run")
    if observations[-1]["time_s"] > c["recipe"]["duration_s"]:
        raise ValueError("observations exceed run duration")
    train = [r for r in observations if r["time_s"] <= training_until_s]
    holdout = [r for r in observations if r["time_s"] > training_until_s]
    if len(train) < len(fields) + 2 or not holdout:
        raise ValueError("need at least fitted-parameter-count + 2 training points and a later holdout")
    if set(bounds) != set(fields):
        raise ValueError("supply bounds for every fitted field only")
    for f in fields:
        lo, hi = bounds[f]
        if not 0 < lo < hi or not np.isfinite([lo, hi]).all():
            raise ValueError("positive finite increasing parameter bounds required")
        for value in (lo, hi):
            trial = deepcopy(c)
            trial[FIT_FIELDS[f]][f] = float(value)
            validate(trial)
        if not lo <= c[FIT_FIELDS[f]][f] <= hi:
            raise ValueError("initial parameter must be inside fit bounds")

    def configured(log_values):
        candidate = deepcopy(c)
        for f, v in zip(fields, np.exp(log_values)):
            candidate[FIT_FIELDS[f]][f] = float(v)
        return candidate

    calls = 0

    def residual(log_values):
        nonlocal calls
        calls += 1
        candidate = configured(log_values)
        candidate["recipe"]["duration_s"] = float(training_until_s)
        result = simulate(candidate)
        if result["status"] != "completed":
            raise ValueError("calibration candidate left the model/task envelope; revise bounds or evidence")
        times = [r["time_s"] for r in result["trajectory"]]
        temperatures = [r["temperature_k"] for r in result["trajectory"]]
        return np.interp([r["time_s"] for r in train], times, temperatures) - [r["temperature_k"] for r in train]

    fitted = least_squares(residual, np.log([c[FIT_FIELDS[f]][f] for f in fields]),
                           bounds=(np.log([bounds[f][0] for f in fields]), np.log([bounds[f][1] for f in fields])),
                           max_nfev=50, ftol=1e-9, xtol=1e-9, gtol=1e-9)
    if not fitted.success:
        raise ValueError("parameter fitting failed: " + fitted.message)
    selected = configured(fitted.x)
    result = simulate(selected)
    if result["status"] != "completed":
        raise ValueError("fitted model cannot complete the requested forecast")
    t = [r["time_s"] for r in result["trajectory"]]
    temp = [r["temperature_k"] for r in result["trajectory"]]
    errors = np.interp([r["time_s"] for r in holdout], t, temp) - [r["temperature_k"] for r in holdout]
    rank = int(np.linalg.matrix_rank(fitted.jac))
    singular = np.linalg.svd(fitted.jac, compute_uv=False)
    at_bound = bool(np.any(fitted.active_mask))
    if rank < len(fields) or singular[-1] <= 1e-8:
        diagnostic = "weak_or_rank_deficient"
    else:
        diagnostic = "locally_full_rank_not_global_identifiability"
    return {"model_version": VERSION, "fitted_config": selected,
            "estimates": {f: selected[FIT_FIELDS[f]][f] for f in fields},
            "training_rows": len(train), "holdout_rows": len(holdout), "training_until_s": training_until_s,
            "training_rmse_k": float(np.sqrt(np.mean(fitted.fun**2))),
            "holdout_rmse_k": float(np.sqrt(np.mean(errors**2))), "solver_calls": calls+1,
            "jacobian_rank": rank, "identifiability_diagnostic": diagnostic,
            "jacobian_condition_number": float(singular[0]/singular[-1]) if singular[-1] > 0 else None,
            "at_bound": at_bound, "data_hash": content_hash(observations),
            "training_data_hash": content_hash(train), "holdout_data_hash": content_hash(holdout),
            "evidence_classification": c["evidence_classification"],
            "scope": "Temperature-only fit conditional on other supplied kinetics/properties; not validation of yield or real chemistry"}


def compare_sites(donor, receiver, *, allowed_yield_loss_fraction):
    if isinstance(allowed_yield_loss_fraction, bool) or not isinstance(allowed_yield_loss_fraction, (float, int)) or not np.isfinite(allowed_yield_loss_fraction) or not 0 <= allowed_yield_loss_fraction <= 1:
        raise ValueError("yield tolerance must be an absolute fraction in [0,1]")
    d, r = validate(donor), validate(receiver)
    if d.chemistry != r.chemistry or d.recipe.initial_a_mol_m3 != r.recipe.initial_a_mol_m3:
        raise ValueError("site comparison requires identical chemistry and initial concentration")
    source, target = simulate(d), simulate(r)
    loss = source["product_yield_fraction"] - target["product_yield_fraction"] if source["status"] == target["status"] == "completed" else None
    passed = loss is not None and source["within_declared_constraints"] and target["within_declared_constraints"] and loss <= allowed_yield_loss_fraction
    return {"donor": source, "receiver": target, "yield_loss_fraction_points": loss,
            "allowed_yield_loss_fraction_points": allowed_yield_loss_fraction,
            "assessment": "conditional_model_screen_pass" if passed else "not_demonstrated",
            "interpretation": "Comparison of deterministic model scenarios, not statistical noninferiority or manufacturing authorization"}


def sensitivity(config, *, fractional_change=.1):
    if isinstance(fractional_change, bool) or not isinstance(fractional_change, (int, float)) or not 0 < fractional_change < 1:
        raise ValueError("fractional sensitivity change must be in (0,1)")
    c = validate(config).model_dump()
    out = []
    for block, field in (("equipment", "heat_transfer_coefficient_w_m2_k"),
                         ("chemistry", "product_rate_ref_s_inv"), ("chemistry", "impurity_rate_ref_s_inv")):
        for multiplier in (1-fractional_change, 1+fractional_change):
            trial = deepcopy(c)
            trial[block][field] *= multiplier
            result = simulate(trial)
            out.append({"parameter": f"{block}.{field}", "multiplier": multiplier,
                        "status": result["status"], "product_yield_fraction": result["product_yield_fraction"],
                        "maximum_temperature_k": result["maximum_temperature_k_at_returned_points"],
                        "violations": result["violations"]})
    return {"classification": "one_at_a_time_assumption_sensitivity_not_probability", "rows": out,
            "limitation": "No joint parameter uncertainty, statistical intervals or guaranteed experiment ranking"}
