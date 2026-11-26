"""Frozen lyophilization scoring with coverage, endpoint censoring and provenance."""
import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch

from .artifact import load_artifact, sha256, write_json
from .config import DTYPE, LyoTrainConfig, seed_everything
from .loss import drying_duration_loss
from .lyo_data import LyoBatch, LyoDataset, load_dataset, validate_batch, validate_splits
from .model import HybridLyophilizationUDE, LyophilizationSolver


def auroc(normal_scores: list[float], fault_scores: list[float]) -> float:
    """Pairwise rank statistic; callers must report the scored cohort sizes."""
    normal, fault = np.asarray(normal_scores), np.asarray(fault_scores)
    if not len(normal) or not len(fault):
        raise ValueError("AUROC requires both classes")
    return float(((fault[:, None] > normal).astype(float) + .5*(fault[:, None] == normal)).mean())


def _metrics(errors, observations):
    if not errors:
        return {"rmse": None, "mae": None, "r2": None, "n_observed": 0}
    e, obs = np.asarray(errors), np.asarray(observations)
    sst = float(np.square(obs-obs.mean()).sum())
    return {"rmse": float(np.sqrt(np.square(e).mean())), "mae": float(np.abs(e).mean()),
            "r2": float(1-np.square(e).sum()/sst) if sst > 0 else None, "n_observed": len(e)}


def _completion(solution):
    """Sampled endpoint time, with explicit left/right censoring."""
    ratio = solution.ts.new_tensor(solution.completion_remaining_fraction/solution.depletion_fraction)
    threshold = ratio+torch.log(-torch.expm1(-ratio))
    z, times = solution.drying_coordinate[0, :, 0], solution.ts[0]
    if solution.initially_dry[0] or z[0] <= threshold:
        return None, "left_censored", None
    crossed = torch.nonzero(z <= threshold).flatten()
    if not len(crossed):
        return None, "right_censored", None
    j = int(crossed[0])
    fraction = (z[j-1]-threshold)/(z[j-1]-z[j])
    time = times[j-1]+fraction*(times[j]-times[j-1])
    return float(time), "observed_crossing", float(times[j]-times[j-1])


@torch.no_grad()
def score_model(model: HybridLyophilizationUDE, batches: tuple[LyoBatch, ...]) -> dict:
    """Open-loop y0 + controls only. No observations/labels enter prediction.

    All supplied primary-temperature observations count toward coverage, even
    if predicted completion or a melt bound excludes them from RMSE. Endpoint
    failures are censored explicitly rather than omitted as successful runs.
    """
    if not isinstance(model, HybridLyophilizationUDE):
        raise ValueError("Lyophilization evaluation requires a lyophilization model")
    solver = LyophilizationSolver(model)
    errors, observed = [[], []], [[], []]
    eligible, rejected, melt_rows, nfes = 0, 0, 0, []
    duration_errors, duration_actual, per_batch, handoff, corrections = [], [], [], [], []
    for batch in batches:
        validate_batch(batch)
        # Report endpoint resolution explicitly. The extra grid improves endpoint
        # interpolation without using the measured endpoint to condition the model.
        grid = torch.unique(torch.cat((batch.times, torch.linspace(
            float(batch.times[0]), float(batch.times[-1]), 257, dtype=DTYPE))), sorted=True)
        solution = solver.solve(batch.y0[None], grid[None], batch.process_args[None])
        indices = torch.searchsorted(grid, batch.times)
        pred_state = solution.ys[:, indices]
        times = batch.times[None]
        d = {key: value[0] for key, value in model.diagnostics(pred_state, batch.process_args[None], times).items()}
        prior, correction = model.rates(pred_state, batch.process_args[None], times)
        corrections.append((correction/prior).abs().reshape(-1, 2))
        prediction = torch.stack((d["bottom_temperature_k"], pred_state[0, :, 0]), dim=-1)
        available = batch.obs_mask.clone()
        available[:, 0] &= batch.primary_mask
        valid = available.clone()
        valid[:, 0] &= d["temperature_defined"]
        eligible += int(available[:, 0].sum())
        rejected += int((available[:, 0] & ~d["temperature_defined"]).sum())
        melt_rows += int((batch.primary_mask & ~d["balance_valid"]).sum())
        local_metrics = {}
        for j, name in enumerate(("bottom_temperature_k", "dried_layer_m")):
            e = (prediction[:, j][valid[:, j]]-batch.observations[:, j][valid[:, j]]).tolist()
            obs = batch.observations[:, j][valid[:, j]].tolist()
            errors[j].extend(e)
            observed[j].extend(obs)
            local_metrics[name] = _metrics(e, obs)
        endpoint, censoring, resolution = _completion(solution)
        duration_error = None
        if batch.duration_s is not None and endpoint is not None:
            duration_error = endpoint-batch.duration_s
            duration_errors.append(duration_error)
            duration_actual.append(batch.duration_s)
        anomaly_score = None
        if batch.duration_s is not None and not solution.initially_dry.any():
            anomaly_score = float(drying_duration_loss(solution, torch.tensor([batch.duration_s], dtype=DTYPE)).sqrt())
        nfe = int(solution.stats["n_f_evals"][0])
        nfes.append(nfe)
        row = {"batch_id": batch.batch_id, "metrics": local_metrics, "n_f_evals": nfe,
               "eligible_temperature_count": int(available[:, 0].sum()),
               "scored_temperature_count": int(valid[:, 0].sum()),
               "invalid_primary_balance_count": int((batch.primary_mask & ~d["balance_valid"]).sum()),
               "observed_endpoint_s": batch.duration_s, "predicted_endpoint_s": endpoint,
               "endpoint_error_s": duration_error, "endpoint_status": censoring,
               "endpoint_interpolation_interval_s": resolution, "endpoint_anomaly_score": anomaly_score}
        per_batch.append(row)
        trajectory = []
        for k, time in enumerate(batch.times):
            observed_values = {name: float(batch.observations[k, j]) if batch.obs_mask[k, j] else None
                               for j, name in enumerate(("bottom_temperature_k", "dried_layer_m"))}
            trajectory.append({
                "time_s": float(time), "observations": observed_values,
                "observation_mask": batch.obs_mask[k].tolist(), "primary_mask": bool(batch.primary_mask[k]),
                "observed_minus_predicted": {
                    name: float(batch.observations[k, j]-prediction[k, j]) if valid[k, j] else None
                    for j, name in enumerate(("bottom_temperature_k", "dried_layer_m"))},
                "dried_layer_m": float(pred_state[0, k, 0]),
                "bottom_temperature_k": float(d["bottom_temperature_k"][k]) if d["temperature_defined"][k] else None,
                "interface_temperature_k": float(d["interface_temperature_k"][k]) if d["temperature_defined"][k] else None,
                "temperature_defined": bool(d["temperature_defined"][k]), "balance_valid": bool(d["balance_valid"][k]),
                "melt_excess_k": float(d["melt_excess_k"][k]),
                "remaining_ice_fraction": float(d["remaining_ice_fraction"][k]),
                "heat_w": float(d["heat_w"][k]), "mass_rate_kg_s": float(d["mass_rate_kg_s"][k]),
                "prior_coefficients": dict(zip(("Kv_w_m2_k", "Rp_m_s"), prior[0, k].tolist())),
                "relative_learned_correction": dict(zip(("Kv", "Rp"), (correction/prior)[0, k].tolist())),
            })
        handoff.append({**row, "trajectory": trajectory})
    relative = torch.cat(corrections).mean(0).tolist() if corrections else [None, None]
    return {"metrics": {name: _metrics(errors[j], observed[j])
                        for j, name in enumerate(("bottom_temperature_k", "dried_layer_m"))},
            "temperature_coverage": {"eligible": eligible, "scored": eligible-rejected, "rejected": rejected,
                                     "fraction": (eligible-rejected)/eligible if eligible else None},
            "endpoint_metrics_s": _metrics(duration_errors, duration_actual),
            "endpoints": {"with_observation": sum(b.duration_s is not None for b in batches),
                          "predicted_crossings": sum(r["endpoint_status"] == "observed_crossing" for r in per_batch),
                          "right_censored": sum(r["endpoint_status"] == "right_censored" for r in per_batch),
                          "left_censored": sum(r["endpoint_status"] == "left_censored" for r in per_batch)},
            "invalid_primary_balance_count": melt_rows,
            "n_f_evals_mean": float(np.mean(nfes)) if nfes else None,
            "n_f_evals_max": max(nfes) if nfes else None,
            "mean_abs_relative_correction": dict(zip(("Kv", "Rp"), relative)),
            "per_batch": per_batch, "handoff": handoff}


@torch.no_grad()
def evaluate(path: Path, data: LyoDataset, output: Path, strict: bool = True) -> dict:
    model, document = load_artifact(path)
    if not isinstance(model, HybridLyophilizationUDE):
        raise ValueError("This evaluator accepts lyophilization artifacts; fermentation artifacts retain their own model type")
    validate_splits(data)
    from .train import data_fingerprint
    meta = document["metadata"]
    seed_everything(meta["train"]["seed"])
    if (data.seed != meta["dataset_seed"] or data.split_ids() != meta["split_ids"]
            or data.provenance != meta["data_provenance"]
            or data.completion_remaining_fraction != model.config.completion_remaining_fraction):
        raise ValueError("Dataset provenance, split IDs or endpoint definition differs from frozen training")
    if any(data_fingerprint(getattr(data, name)) != meta["data_sha256"][name] for name in data.split_ids()):
        raise ValueError("Dataset observations/controls/endpoints differ from frozen provenance")
    normal = score_model(model, data.test)
    faults = score_model(model, data.faults)
    normal_rows, fault_rows = normal.pop("handoff"), faults.pop("handoff")
    # Labels are attached only after each label-blind prediction/score.
    for rows, label in ((normal_rows, "normal_test"), (fault_rows, "fault_evaluation")):
        for row in rows:
            row["benchmark_label"] = label
    normal_scores = [r["endpoint_anomaly_score"] for r in normal_rows if r["endpoint_anomaly_score"] is not None]
    fault_scores = [r["endpoint_anomaly_score"] for r in fault_rows if r["endpoint_anomaly_score"] is not None]
    auc = auroc(normal_scores, fault_scores) if normal_scores and fault_scores else None
    report = {
        "schema_version": 2, "model_type": "lyophilization", "artifact_sha256": sha256(Path(path)),
        "data_provenance": data.provenance, "normal_test": normal, "fault_test": faults,
        "forecast_conditioning": "supplied initial dried layer and known controls only; no observations assimilated",
        "physical_constants": {name: float(v) for name, v in model.physics_core.constants().items()},
        "completion_remaining_fraction": model.config.completion_remaining_fraction,
        "fault_endpoint_auroc": auc, "auroc_cohort_sizes": {"normal": len(normal_scores), "fault": len(fault_scores)},
        "physical_validity_pass": normal["invalid_primary_balance_count"] == 0 and faults["invalid_primary_balance_count"] == 0,
        "limitations": ["Synthetic data, when used, are software checks, not experimental process validation",
                        "Post-drying thermocouple rise, freezing, and secondary drying are not modeled",
                        "Temperature RMSE is conditional on validity; coverage and censored endpoints are reported separately",
                        "Endpoint estimates interpolate saved coordinates; each crossing includes its sample interval",
                        "Fault AUROC is descriptive, not a calibrated manufacturing risk or acceptance threshold",
                        "Transfer constants and neural corrections may not be separately identifiable"],
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "method_b_handoff.json", {
        "schema_version": 2, "model_type": "lyophilization", "artifact_sha256": report["artifact_sha256"],
        "method": "observed temperature/layer/endpoint discrepancies with primary-drying validity",
        "units": {"time": "s", "temperature": "K", "length": "m", "heat": "W", "sublimation": "kg/s per vial"},
        "batches": normal_rows+fault_rows})
    write_json(output / "evaluation.json", report)
    if strict and not report["physical_validity_pass"]:
        raise RuntimeError("Invalid primary-drying heat/mass balances; inspect evaluation.json")
    return report


def few_shot_scaling(data: LyoDataset, output: Path, epochs: int = 40) -> dict:
    """Independent fits; no monotonic-learning or fault-acceptance assumption."""
    from .train import train
    counts = sorted({min(n, len(data.train)) for n in (3, 7, 15)})
    results = []
    for n in counts:
        path = train(replace(data, train=data.train[:n]), Path(output)/f"n{n}",
                     LyoTrainConfig(seed=data.seed, epochs=epochs))
        model, _ = load_artifact(path)
        score = score_model(model, data.test)
        results.append({"n_train_batches": n, "artifact_sha256": sha256(path),
                        "metrics": score["metrics"], "endpoint_metrics_s": score["endpoint_metrics_s"],
                        "temperature_coverage": score["temperature_coverage"], "endpoints": score["endpoints"]})
    report = {"results": results, "same_epochs_per_fit": epochs,
              "interpretation": "Single-seed learning curve; errors, coverage and censoring must be read jointly"}
    Path(output).mkdir(parents=True, exist_ok=True)
    write_json(Path(output)/"few_shot_scaling.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--data", type=Path, help="Defaults to the hashed dataset.json beside the checkpoint")
    parser.add_argument("--output", type=Path, default=Path("artifacts/lyophilization-evaluation"))
    parser.add_argument("--few-shot-epochs", type=int, default=0)
    parser.add_argument("--report-only", action="store_true", help="Write melt-bound diagnostics without a strict physical-validity error")
    args = parser.parse_args()
    _, document = load_artifact(args.artifact)
    path = args.data or args.artifact.parent/"dataset.json"
    if args.data is None and sha256(path) != document["metadata"]["dataset_sha256"]:
        raise ValueError("Saved dataset snapshot SHA-256 mismatch")
    data = load_dataset(path)
    report = evaluate(args.artifact, data, args.output, strict=not args.report_only)
    if args.few_shot_epochs > 0:
        report["few_shot_scaling"] = few_shot_scaling(data, args.output/"few_shot", args.few_shot_epochs)
        write_json(args.output/"evaluation.json", report)
    print(f"Temperature metrics: {report['normal_test']['metrics']['bottom_temperature_k']}")
    print(f"Endpoint metrics (s): {report['normal_test']['endpoint_metrics_s']}")


if __name__ == "__main__":
    main()
