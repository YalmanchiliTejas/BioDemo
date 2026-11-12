"""Bounded constitutive learning inside existing balances, never a state residual.

Two-stage integrated rate estimation is an explicit departure from the paper's
full nonlinear trajectory TVP fit. The existing fermentation model is algebraic
oxygen-transfer characterization, not an organism growth/production model.
"""

from copy import deepcopy
import math

import numpy as np
from scipy.optimize import lsq_linear, minimize
from scipy.special import expit

from ..ids import content_hash
from .contracts import predict
from .engine import BudgetExceeded

VERSION = "bounded-hybrid-1"
SUPPORTED = ("chemical.parallel_batch", "fermentation.oxygen_transfer")
FEATURES = {
    SUPPORTED[0]: [
        "temperature_k",
        "reactant_fraction",
        "area_per_volume_m_inv",
        "heat_transfer_w_m2_k",
        "coolant_temperature_k",
    ],
    SUPPORTED[1]: ["log_power_w_m3", "log_vvm", "log_working_volume_l", "impeller_diameter_m", "submerged_impellers"],
}


def capabilities(mid):
    if mid not in SUPPORTED:
        return {"supported": False, "reason": "No reviewed learned constitutive term for this adapter"}
    return {
        "supported": True,
        "version": VERSION,
        "features": FEATURES[mid],
        "terms": (
            ["product_rate_multiplier", "impurity_rate_multiplier"] if mid == SUPPORTED[0] else ["kla_multiplier"]
        ),
        "output_unit": "dimensionless multiplier; physical rates retain 1/s or 1/h",
        "bounds": [0.25, 4.0],
        "invariants": "Original species/energy equations or oxygen-transfer/power algebra unchanged",
        "limitations": "No new pathways or organism/yield kinetics; synthetic examples do not validate these terms",
    }


def chemistry_features(state, c):
    eq = c.equipment
    n0 = c.recipe.initial_a_mol_m3 * eq.working_volume_m3
    return [
        float(state[3]),
        float(state[0] / n0),
        eq.heat_transfer_area_m2 / eq.working_volume_m3,
        eq.heat_transfer_coefficient_w_m2_k,
        eq.coolant_temperature_k,
    ]


def fermentation_features(power, vvm, equipment):
    return [
        math.log(max(power, 1e-15)),
        math.log(vvm),
        math.log(equipment["working_volume_l"]),
        equipment["impeller_diameter_mm"] / 1000.0,
        equipment["submerged_impellers"],
    ]


def partition(runs, *, site_holdout=False):
    """Whole independent batches, including all aliases/augmentations, stay together."""
    if not 1 <= len(runs) <= 128:
        raise ValueError("1..128 runs required")
    roles = {"train": [], "selection": [], "calibration": [], "test": []}
    seen = {}
    sites = {}
    ids = set()
    for run in runs:
        for k in (
            "run_id",
            "batch_id",
            "site_id",
            "role",
            "config",
            "observations",
            "source_refs",
            "evidence_classification",
        ):
            if k not in run:
                raise ValueError("Missing run field " + k)
        if any(
            not isinstance(run[k], str) or not run[k]
            for k in ("run_id", "batch_id", "site_id", "evidence_classification")
        ) or not isinstance(run["config"], dict):
            raise ValueError("Typed run identity, physical configuration and evidence classification required")
        if run["role"] not in roles or run["run_id"] in ids:
            raise ValueError("Unique run IDs and four explicit partition roles required")
        ids.add(run["run_id"])
        group = (run["site_id"], run["batch_id"])
        if group in seen and seen[group] != run["role"]:
            raise ValueError("Batch leakage between partitions")
        seen[group] = run["role"]
        sites.setdefault(run["site_id"], set()).add(run["role"])
        if run.get("augmented") and (run["role"] != "train" or not run.get("origin_run_id")):
            raise ValueError("Augmentation belongs to training original runs only")
        if not run["observations"] or len(run["observations"]) > 2000:
            raise ValueError("1..2000 observations required per run")
        if not run["source_refs"]:
            raise ValueError("Run provenance required")
        for row in run["observations"]:
            if any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k]) for k in ("coordinate", "value")):
                raise ValueError("Finite observation coordinates and values required")
            if (
                row["coordinate"] < 0
                or row["coordinate"] > run.get("evidence_cutoff", float("inf"))
                or row.get("available_at_coordinate", row["coordinate"]) > run.get("evidence_cutoff", float("inf"))
            ):
                raise ValueError("Observation is unavailable at evidence cutoff")
            if not row.get("unit") or not row.get("observable"):
                raise ValueError("Explicit family observable and unit required")
            if (
                type(row.get("measurement_std", 0)) not in (int, float)
                or not math.isfinite(row.get("measurement_std", 0))
                or row.get("measurement_std", 0) < 0
            ):
                raise ValueError("Nonnegative finite measurement uncertainty required")
            if (
                type(row.get("scale", 1.0)) not in (int, float)
                or not math.isfinite(row.get("scale", 1.0))
                or row.get("scale", 1.0) <= 0
            ):
                raise ValueError("Positive finite fixed observation scale required")
        roles[run["role"]].append(run)
    originals = {r["run_id"]: r for r in runs if not r.get("augmented")}
    for run in runs:
        if run.get("augmented"):
            origin = originals.get(run["origin_run_id"])
            if (
                not origin
                or origin["role"] != "train"
                or (origin["site_id"], origin["batch_id"]) != (run["site_id"], run["batch_id"])
            ):
                raise ValueError("Augmentation must retain original training batch and site")
    # Shared source-run aliases cannot cross a partition even under renamed batch IDs.
    for key in ("origin_run_id", "independent_run_ref"):
        provenance = {}
        for r in runs:
            value = r.get(key)
            if value and value in provenance and provenance[value] != r["role"]:
                raise ValueError("Source-run alias leakage")
            if value:
                provenance[value] = r["role"]
    if site_holdout and any("test" in v and len(v) > 1 for v in sites.values()):
        raise ValueError("Final evaluation site leaked into development")
    if not roles["train"] or not roles["selection"]:
        raise ValueError("Separate training and model-selection batches required")
    return roles


def estimate_terms(mid, runs):
    xs = []
    ys = []
    groups = []
    if mid not in SUPPORTED:
        raise ValueError("Hybrid adaptation unsupported for " + mid)
    for run in runs:
        if run.get("augmented"):  # still grouped with original; not an independent batch
            group = (run["site_id"], run["batch_id"])
        else:
            group = (run["site_id"], run["batch_id"])
        if mid == SUPPORTED[0]:
            from ..chemical_reactor.model import validate, rates

            c = validate(run["config"])
            wide = {}
            for r in run["observations"]:
                expected = {"a_mol": "mol", "product_mol": "mol", "impurity_mol": "mol", "temperature_k": "K"}
                if r["observable"] in expected:
                    if r["unit"] != expected[r["observable"]]:
                        raise ValueError("Chemical observation unit mismatch")
                    if r["observable"] in wide.setdefault(r["coordinate"], {}):
                        raise ValueError("Duplicate chemical observation")
                    wide[r["coordinate"]][r["observable"]] = r["value"]
            times = sorted(wide)
            if len(times) < 4 or any(set(wide[t]) != set(expected) for t in times):
                raise ValueError(
                    "Identifiable kinetics require A, desired product, impurity and temperature at four or more matched times"
                )
            targets = []
            features = []
            weights = []
            for left, right in zip(times, times[1:]):
                a, b = wide[left], wide[right]
                dt = right - left
                ka = np.array(rates(a["temperature_k"], c.chemistry))
                kb = np.array(rates(b["temperature_k"], c.chemistry))
                # Reactant falls exponentially between samples, so its time integral is the log-mean amount times
                # the interval. A trapezoid overstates it and biases the multiplier low as sampling gets coarser.
                na, nb = a["a_mol"], b["a_mol"]
                if na <= 0 or nb <= 0:
                    raise ValueError("Reactant amount must stay positive to estimate kinetic multipliers")
                mean_amount = na if abs(na - nb) <= 1e-12 * na else (na - nb) / math.log(na / nb)
                exposure = 0.5 * (ka + kb) * dt * mean_amount
                delta = np.array([b["product_mol"] - a["product_mol"], b["impurity_mol"] - a["impurity_mol"]])
                if np.any(exposure < 1e-10):
                    raise ValueError("Kinetic pathway is unexcited; neural terms unidentifiable")
                targets.append(delta / exposure)
                weights.append(exposure / np.maximum(np.max(exposure), 1e-12))
                state = [0.5 * (a["a_mol"] + b["a_mol"]), 0, 0, 0.5 * (a["temperature_k"] + b["temperature_k"])]
                features.append(chemistry_features(state, c))
            # Bounded, regularized interval-effective rates; no test labels used.
            z = np.asarray(targets)
            n = len(z)
            smooth = np.diff(np.eye(n), axis=0)
            fitted = []
            for j in range(2):
                w = np.sqrt(np.maximum(np.array(weights)[:, j], 0.05))
                design = np.vstack([np.diag(w), 0.12 * smooth, 0.04 * np.eye(n)])
                target = np.r_[w * z[:, j], np.zeros(n - 1), 0.04 * np.ones(n)]
                fit = lsq_linear(design, target, bounds=(0.25, 4.0), max_iter=100)
                if not fit.success:
                    raise ValueError("Bounded kinetic estimation failed")
                fitted.append(fit.x)
            xs.extend(features)
            ys.extend(np.array(fitted).T.tolist())
            groups.extend([group] * n)
        else:
            from ..fermentation.model import sulfolobus

            base = sulfolobus(run["config"])["selected_scenario"]
            p = run["config"]["project"]
            eq = next(e for e in p["equipment"] if e["working_volume_l"] == base["receiver_l"])
            rows = [r for r in run["observations"] if r["observable"] == "selected_scenario.predicted_kla_h_inv"]
            if len(rows) != 1 or rows[0]["coordinate"] != 0 or rows[0]["unit"] != "1/h":
                raise ValueError("One independently characterized kLa (1/h) endpoint per transport run required")
            if rows[0]["value"] <= 0:
                raise ValueError("kLa characterization must be positive")
            target = rows[0]["value"] / base["predicted_kla_h_inv"]
            xs.append(fermentation_features(base["power_w_m3"], base["vvm"], eq))
            ys.append([float(np.clip(target, 0.25, 4.0))])
            groups.append(group)
    return np.asarray(xs), np.asarray(ys), groups


def unpack(weights, n, o, h=6):
    weights = np.asarray(weights, dtype=float)
    a = n * h
    b = a + h
    c = b + h * o
    if weights.shape != (c + o,) or not np.isfinite(weights).all():
        raise ValueError("Invalid neural checkpoint shape/weights")
    return weights[:a].reshape(n, h), weights[a:b], weights[b:c].reshape(h, o), weights[c:]


def network(weights, x, n, o):
    a, b, c, d = unpack(weights, n, o)
    hidden = np.tanh(x @ a + b)
    s = expit(hidden @ c + d)
    return 0.25 + 3.75 * s, hidden, s


def learn(x, y, groups, *, parent=None, regularization=0.002, source_penalty=0.01, seed=1):
    n, o = x.shape[1], y.shape[1]
    rng = np.random.default_rng(seed)
    center = np.asarray(parent["center"]) if parent else x.mean(axis=0)
    scale = (
        np.asarray(parent["scale"]) if parent else np.maximum(x.std(axis=0), np.maximum(np.abs(center) * 0.01, 1e-3))
    )
    z = (x - center) / scale
    size = n * 6 + 6 + 6 * o + o
    initial = np.array(parent["weights"]) if parent else rng.normal(0, 0.12, size)
    if parent is None:
        initial[-o:] = np.log((1.0 - 0.25) / (4.0 - 1.0))
    counts = {g: groups.count(g) for g in set(groups)}
    w = np.array([1 / counts[g] for g in groups])
    w /= w.sum()
    anchor = initial.copy()

    def objective(theta):
        p, h, s = network(theta, z, n, o)
        error = p - y
        loss = float(np.sum(w[:, None] * error**2) / o + regularization * np.mean(theta**2))
        grad_out = 2 * w[:, None] * error / o * 3.75 * s * (1 - s)
        a, b, c, d = unpack(theta, n, o)
        gh = (grad_out @ c.T) * (1 - h * h)
        gradient = (
            np.r_[(z.T @ gh).ravel(), gh.sum(0), (h.T @ grad_out).ravel(), grad_out.sum(0)]
            + 2 * regularization * theta / size
        )
        if parent:
            # Smooth L1 distance approximates paper's source-weight anchoring.
            delta = theta - anchor
            distance = np.sqrt(delta**2 + 1e-8)
            loss += source_penalty * float(distance.mean())
            gradient += source_penalty * delta / distance / size
        return loss, gradient

    fitted = minimize(objective, initial, jac=True, method="L-BFGS-B", options={"maxiter": 2000, "ftol": 1e-10})
    if not np.isfinite(fitted.fun):
        raise ValueError("Neural optimization failed")
    return {
        "weights": fitted.x.tolist(),
        "center": center.tolist(),
        "scale": scale.tolist(),
        "input_size": n,
        "output_size": o,
        "hidden_units": 6,
        "regularization": regularization,
        "source_penalty": source_penalty if parent else 0.0,
        "optimizer_converged": bool(fitted.success),
        "domain_min": np.minimum(x.min(0), parent["domain_min"]).tolist() if parent else x.min(0).tolist(),
        "domain_max": np.maximum(x.max(0), parent["domain_max"]).tolist() if parent else x.max(0).tolist(),
    }


def factors(member, features):
    x = np.asarray(features, dtype=float)
    if not np.isfinite(x).all() or len(x) != member["input_size"]:
        raise ValueError("Invalid physical features")
    p, _, _ = network(
        member["weights"],
        (x - np.array(member["center"])) / member["scale"],
        member["input_size"],
        member["output_size"],
    )
    low = np.asarray(member["domain_min"])
    high = np.asarray(member["domain_max"])
    slack = np.maximum((high - low) * 0.15, np.asarray(member["scale"]) * 0.15)
    return p, bool(np.any(x < low - slack) or np.any(x > high + slack))


def run_hybrid(adapter, config, checkpoint, *, member_index=0, mode="hybrid"):
    mid = adapter.id
    if mode not in ("hybrid", "refit"):
        raise ValueError("Hybrid runner requires hybrid or refit mode")
    if mid not in SUPPORTED or checkpoint["model_id"] != mid:
        raise ValueError("Hybrid checkpoint incompatible with adapter")
    if checkpoint["adapter_digest"] != adapter.digest or checkpoint["version"] != VERSION:
        raise ValueError("Model/checkpoint implementation changed")
    member = checkpoint["members"][member_index % len(checkpoint["members"])]
    ood = False

    def mapped(features):
        nonlocal ood
        if mode == "refit":
            return np.asarray(
                checkpoint.get("constant_ensemble", [checkpoint["constant_terms"]])[
                    member_index % len(checkpoint.get("constant_ensemble", [checkpoint["constant_terms"]]))
                ]
            )
        output, outside = factors(member, features)
        ood |= outside
        return output

    if mid == SUPPORTED[0]:
        from ..chemical_reactor.model import simulate

        result = simulate(config, kinetic_model=lambda state, c: mapped(chemistry_features(state, c)))
    else:
        from ..fermentation.model import sulfolobus, transfer_point

        result = sulfolobus(config)
        scenario = result["selected_scenario"]
        result["selected_scenario"] = transfer_point(
            config["project"],
            scenario["receiver_l"],
            scenario["rpm"],
            scenario["vvm"],
            config.get("assumptions", {}).get("gas_exponent", 0.5),
            kla_model=lambda power, vvm, eq: float(mapped(fermentation_features(power, vvm, eq))[0]),
        )
        result["recommendations"] = []
        result["hybrid_grid_scope"] = (
            "Only selected_scenario is hybrid; grid rows retain unchanged physics and no hybrid recommendation is inferred."
        )
    result["hybrid"] = {
        "checkpoint_hash": content_hash(checkpoint),
        "mode": mode,
        "out_of_domain": ood,
        "learned_terms": capabilities(mid)["terms"],
        "risk_probability": None,
        "structural_discrepancy": "not_quantified",
        "status": "unsupported_operating_conditions" if ood else "within_observed_feature_support",
    }
    return result


def score(adapter, runs, checkpoint=None, mode="physics", budget=None):
    errors = []
    failed = 0
    violations = 0
    ood = 0
    for run in runs:
        try:
            operation = lambda c: adapter.run(c) if mode == "physics" else run_hybrid(adapter, c, checkpoint, mode=mode)
            prediction, result = predict(
                adapter,
                run["config"],
                run["observations"],
                runner=lambda c: budget.call(lambda: operation(c)) if budget else operation(c),
            )
            scale = np.array([r.get("scale", max(abs(r["value"]), 1.0)) for r in run["observations"]])
            errors.extend(((prediction - [r["value"] for r in run["observations"]]) / scale).tolist())
            violations += bool(result.get("violations"))
            ood += bool(result.get("hybrid", {}).get("out_of_domain"))
        except BudgetExceeded:
            raise  # running out of solver budget says nothing about the model being scored
        except (ValueError, KeyError, RuntimeError, FloatingPointError):
            failed += 1
    return {
        "rmse_scaled": float(np.sqrt(np.mean(np.array(errors) ** 2))) if errors else None,
        "failed_predictions": failed,
        "constraint_violating_runs": violations,
        "out_of_domain_runs": ood,
        "runs": len(runs),
        "points": len(errors),
    }


def train(adapter, runs, *, parent=None, seed=1, ensemble_size=3, site_holdout=False, budget=None):
    roles = partition(runs, site_holdout=site_holdout)
    if not 2 <= ensemble_size <= 8:
        raise ValueError("2..8 whole-batch bootstrap members required")
    if parent and (parent["model_id"] != adapter.id or parent["adapter_digest"] != adapter.digest):
        raise ValueError("Source checkpoint has incompatible physical model")
    x, y, groups = estimate_terms(adapter.id, roles["train"])
    if len(set(groups)) < 2:
        raise ValueError("At least two independently identified training batches required")
    if len(x) > 4096:
        raise ValueError("At most 4096 effective kinetic/transport training rows")
    parent_member = parent["members"][0] if parent else None
    candidates = []
    for regularization in (0.002, 0.02):
        member = learn(x, y, groups, parent=parent_member, regularization=regularization, seed=seed)
        cp = {
            "version": VERSION,
            "model_id": adapter.id,
            "adapter_digest": adapter.digest,
            "features": FEATURES[adapter.id],
            "members": [member],
            "constant_terms": np.average(y, axis=0, weights=[1 / groups.count(g) for g in groups]).tolist(),
        }
        measured = score(adapter, roles["selection"], cp, "hybrid", budget)
        candidates.append(
            (
                float("inf")
                if measured["failed_predictions"] or measured["rmse_scaled"] is None
                else measured["rmse_scaled"],
                cp,
            )
        )
    _, checkpoint = min(candidates, key=lambda c: c[0])
    checkpoint["constant_ensemble"] = [checkpoint["constant_terms"]]
    rng = np.random.default_rng(seed)
    unique = sorted(set(groups))
    for index in range(1, ensemble_size):
        chosen = rng.choice(len(unique), len(unique), replace=True)
        indices = [i for j in chosen for i, g in enumerate(groups) if g == unique[j]]
        # Bootstrap whole independent batches. Keep source normalization fixed on adaptation.
        member = learn(
            x[indices],
            y[indices],
            [groups[i] for i in indices],
            parent=parent_member,
            regularization=checkpoint["members"][0]["regularization"],
            seed=seed + index,
        )
        checkpoint["members"].append(member)
        checkpoint["constant_ensemble"].append(
            np.average(y[indices], axis=0, weights=[1 / groups.count(groups[i]) for i in indices]).tolist()
        )
    checkpoint.update(
        training_batches=[list(g) for g in sorted(set(groups))],
        training_run_ids=[r["run_id"] for r in roles["train"]],
        selection_batches=[list(g) for g in sorted({(r["site_id"], r["batch_id"]) for r in roles["selection"]})],
        selection_run_ids=[r["run_id"] for r in roles["selection"]],
        source_checkpoint_hash=content_hash(parent) if parent else None,
        seed=seed,
        data_partition_hash=content_hash({k: [r["run_id"] for r in v] for k, v in roles.items()}),
        classification="synthetic_development_only"
        if any(r["evidence_classification"].startswith("synthetic") for r in roles["train"])
        else "unvalidated_empirical_fit",
        method="bounded regularized interval-effective constitutive estimates -> tanh/sigmoid ANN -> original solver",
        methodological_departures=[
            "Chemical estimation uses integrated species balances with measured temperatures, not full nonlinear TVP trajectory optimization.",
            "Transport adapter learns algebraic kLa factors, not fermentation organism kinetics.",
            "Six hidden units, smooth L1 source-weight regularization, whole-batch bootstrap; no paper-results reproduction claim.",
        ],
    )
    checkpoint["development_groups"] = [
        list(g)
        for g in sorted(
            set(
                map(
                    tuple,
                    checkpoint["training_batches"]
                    + checkpoint["selection_batches"]
                    + (parent.get("development_groups", []) if parent else []),
                )
            )
        )
    ]
    checkpoint["development_run_ids"] = sorted(
        set(
            checkpoint["training_run_ids"]
            + checkpoint["selection_run_ids"]
            + (parent.get("development_run_ids", []) if parent else [])
        )
    )
    comparisons = {m: score(adapter, roles["selection"], checkpoint, m, budget) for m in ("physics", "refit", "hybrid")}
    if parent:
        comparisons["source"] = score(adapter, roles["selection"], parent, "hybrid", budget)
    available = {
        k: v["rmse_scaled"]
        for k, v in comparisons.items()
        if v["rmse_scaled"] is not None and not v["failed_predictions"]
    }
    if not available:
        raise ValueError("No candidate completes model-selection runs")
    best = min(available, key=available.get)
    checkpoint["selection"] = comparisons
    checkpoint["selected_model"] = best
    reference = min((v for k, v in available.items() if k != "hybrid"), default=float("inf"))
    # Applies to a model trained from scratch as much as to an adapted one: a learned term that does worse than
    # the alternatives without it is not used for prediction.
    checkpoint["negative_transfer"] = bool(
        comparisons["hybrid"]["failed_predictions"]
        or comparisons["hybrid"]["rmse_scaled"] is None
        or comparisons["hybrid"]["rmse_scaled"] > reference * 1.01 + 1e-8
    )
    checkpoint["negative_transfer_rule"] = (
        "Hybrid selection RMSE exceeds the best source/physics/refit alternative by >1% plus 1e-8; heuristic, not a significance test."
    )
    unconverged = [i for i, m in enumerate(checkpoint["members"]) if not m.get("optimizer_converged", True)]
    checkpoint["unconverged_members"] = unconverged
    checkpoint["promotion"] = (
        "withheld_negative_transfer" if checkpoint["negative_transfer"]
        else "withheld_optimizer_not_converged" if unconverged
        else "draft_requires_review"
    )
    # Final evaluation is a separate operation after interval calibration is frozen.
    return checkpoint
