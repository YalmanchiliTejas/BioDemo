"""Frozen-model scoring and label-blind mass-balance innovations for Method B."""
import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch

from .artifact import load_artifact, sha256, write_json
from .config import ASSAYS, DTYPE, TrainConfig, seed_everything
from .loss import physics_hijack_ratio
from .model import BioprocessSolver, HybridBioprocessUDE
from .synthetic import Batch, Dataset, FAULT_TIME, GROUND_TRUTH, make_dataset


def auroc(normal_scores: list[float], fault_scores: list[float]) -> float:
    # Pairwise Mann–Whitney statistic, including half credit for ties.
    normal, fault = np.asarray(normal_scores), np.asarray(fault_scores)
    if not len(normal) or not len(fault):
        raise ValueError("AUROC requires both classes")
    return float(((fault[:, None] > normal).astype(float) +
                  .5*(fault[:, None] == normal)).mean())


def rate_residuals(batch: Batch, prediction: torch.Tensor) -> dict:
    """Interval-integrated observed-minus-predicted kinetic rates.

    In amount coordinates, d(XV)=mu XV dt, d(SV)=F Sin dt-qS XV dt,
    d(PV)=qP XV dt. Subtract identical finite differences of model amounts
    to cancel feed and common quadrature bias. No true rates or fault labels
    enter this estimator. Sparse X is linearly interpolated only to estimate
    biomass exposure; assay deviations require two genuinely observed endpoints.
    """
    t, obs, mask = batch.times.numpy(), batch.observations.numpy(), batch.obs_mask.numpy()
    pred = prediction.detach().numpy()
    volume = float(batch.y0[3]) + float(batch.process_args[0])*t
    x_valid = mask[:, 0]
    if x_valid.sum() < 2:
        raise ValueError(f"{batch.batch_id}: insufficient biomass assays for rate inference")
    x = np.interp(t, t[x_valid], obs[x_valid, 0])
    intervals, numerators, exposures = [], [[], [], []], [[], [], []]
    for k in range(len(t)-1):
        exposure = .5*(x[k]*volume[k]+x[k+1]*volume[k+1])*(t[k+1]-t[k])
        row = {"t_start_h": float(t[k]), "t_end_h": float(t[k+1]),
               "biomass_exposure_g_h": float(exposure),
               "biomass_interpolated": bool(not (x_valid[k] and x_valid[k+1]))}
        for j, name in enumerate(("delta_mu", "delta_qS", "delta_qP")):
            value = None
            if mask[k, j] and mask[k+1, j] and exposure > 1e-8:
                innovation = ((obs[k+1, j]-pred[k+1, j])*volume[k+1] -
                              (obs[k, j]-pred[k, j])*volume[k])
                innovation *= -1 if j == 1 else 1
                value = float(innovation/exposure)
                # Fixed Day-2 window for every batch, independent of its class.
                if t[k] >= FAULT_TIME:
                    numerators[j].append(innovation)
                    exposures[j].append(exposure)
            row[name] = value
        intervals.append(row)
    summary = {name: (float(sum(numerators[j])/sum(exposures[j])) if exposures[j] else None)
               for j, name in enumerate(("delta_mu", "delta_qS", "delta_qP"))}
    summary["valid_post_day2_intervals"] = [len(v) for v in exposures]
    trajectories = []
    for k, time in enumerate(t):
        trajectories.append({"time_h": float(time), **{
            assay: {"observed": float(obs[k, j]) if mask[k, j] else None,
                    "predicted": float(pred[k, j]), "observed_mask": bool(mask[k, j]),
                    "residual": float(obs[k, j]-pred[k, j]) if mask[k, j] else None}
            for j, assay in enumerate(ASSAYS)}})
    return {"batch_id": batch.batch_id, "summary": summary,
            "rate_intervals": intervals, "trajectory": trajectories}


@torch.no_grad()
def score_model(model: HybridBioprocessUDE, batches: tuple[Batch, ...]) -> dict:
    solver = BioprocessSolver(model)
    errors, actual, nfes, priors, residuals, handoff, per_batch = [[] for _ in range(7)]
    for batch in batches:
        solution = solver.solve(batch.y0[None], batch.times[None], batch.process_args[None])
        prediction = solution.ys[0]
        errors.append(prediction - torch.nan_to_num(batch.observations))
        actual.append(batch.observations)
        nfes.extend(solution.stats["n_f_evals"].tolist())
        p, r = model.rates(prediction)
        priors.append(p)
        residuals.append(r)
        row = rate_residuals(batch, prediction)
        for k, trajectory_row in enumerate(row["trajectory"]):
            trajectory_row["prior_rates"] = dict(zip(("mu", "qS", "qP"), p[k].tolist()))
            trajectory_row["learned_inner_correction"] = dict(zip(
                ("delta_mu", "delta_qS", "delta_qP"), r[k].tolist()))
        handoff.append(row)
        per_batch.append({"batch_id": batch.batch_id,
                          "n_f_evals": int(solution.stats["n_f_evals"][0]),
                          "rmse": {name: float((prediction[:, j][batch.obs_mask[:, j]] -
                                    batch.observations[:, j][batch.obs_mask[:, j]]).square().mean().sqrt())
                                   if batch.obs_mask[:, j].any() else None
                                   for j, name in enumerate(ASSAYS[:3])}})
    errors, actual = torch.cat(errors), torch.cat(actual)
    metrics = {}
    for j, name in enumerate(ASSAYS[:3]):
        valid = torch.isfinite(actual[:, j])
        y, e = actual[valid, j], errors[valid, j]
        sst = (y-y.mean()).square().sum()
        metrics[name] = {"rmse": float(e.square().mean().sqrt()),
                         "r2": float(1-e.square().sum()/sst) if sst > 0 else None,
                         "n_observed": int(valid.sum())}
    return {"assays": metrics, "per_batch": per_batch, "n_f_evals_mean": float(np.mean(nfes)),
            "n_f_evals_max": int(max(nfes)),
            "physics_hijack_ratio": float(physics_hijack_ratio(torch.cat(priors), torch.cat(residuals))),
            "handoff": handoff}


@torch.no_grad()
def early_forecast(model: HybridBioprocessUDE, batches: tuple[Batch, ...]) -> dict:
    solver = BioprocessSolver(model)
    errors, truth_errors = [], []
    for b in batches:
        times = torch.tensor([[0., 120.]], dtype=DTYPE)
        pred = solver.solve(b.y0[None], times, b.process_args[None]).ys[0, -1, 2]
        truth_errors.append(float(pred-b.truth[-1, 2]))
        if b.obs_mask[-1, 2]:
            errors.append(float(pred-b.observations[-1, 2]))
    return {"conditioning": "known y0 only; no post-inoculation assays",
            "day5_titer_rmse_observed": float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            "n_observed_endpoints": len(errors),
            "day5_titer_rmse_synthetic_truth": float(np.sqrt(np.mean(np.square(truth_errors))))}


@torch.no_grad()
def evaluate(path: Path, data: Dataset, output: Path, strict: bool = True) -> dict:
    model, document = load_artifact(path)
    seed_everything(document["metadata"]["train"]["seed"])
    from .train import data_fingerprint, validate_splits
    validate_splits(data)
    meta = document["metadata"]
    if data.seed != meta["dataset_seed"] or data.split_ids() != meta["split_ids"]:
        raise ValueError("Dataset seed/splits differ from frozen training provenance")
    if data_fingerprint(data.train) != meta["train_data_sha256"] or data_fingerprint(data.val) != meta["val_data_sha256"]:
        raise ValueError("Training/validation data differ from frozen provenance")
    normal, faults = score_model(model, data.test), score_model(model, data.faults)
    normal_rows, fault_rows = normal.pop("handoff"), faults.pop("handoff")
    # The estimator above never sees these benchmark labels.
    for rows, label in ((normal_rows, "normal_test"), (fault_rows, "qP_fault")):
        for row in rows:
            row["benchmark_label"] = label
    if any(r["summary"]["delta_qP"] is None for r in normal_rows+fault_rows):
        raise ValueError("Insufficient qP observations to score every held-out batch")
    auc = auroc([-r["summary"]["delta_qP"] for r in normal_rows],
                [-r["summary"]["delta_qP"] for r in fault_rows])
    isolation = {}
    for name, constant in (("delta_mu", "mu_max"), ("delta_qS", "qS_max")):
        for label, rows in (("normal", normal_rows), ("fault", fault_rows)):
            values = [abs(r["summary"][name]) for r in rows if r["summary"][name] is not None]
            isolation[f"{label}_{name}_mean_abs_fraction_of_true_max"] = float(np.mean(values))/GROUND_TRUTH[constant]
    isolation_ok = all(v < .15 for v in isolation.values())
    report = {"artifact_sha256": sha256(Path(path)), "normal_test": normal,
              "fault_test": faults, "early_oot": early_forecast(model, data.test),
              "physical_constants": {name: {"learned": float(v), "ground_truth": GROUND_TRUTH[name]}
                                     for name, v in model.biology_core.constants().items()},
              "fault_qP_auroc": auc, "fault_qP_auroc_pass": auc > .90,
              "rate_isolation": isolation, "rate_isolation_pass": isolation_ok,
              "near_zero_definition": "mean absolute per-batch deviation <15% of true maximal rate",
              "limitations": ["Synthetic benchmark, not GMP validation or causal proof",
                              "Sparse noisy finite differences are interval averages, not instantaneous rates",
                              "Physical constants and neural correction may not be separately identifiable"]}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "method_b_handoff.json", {
        "schema_version": 1, "artifact_sha256": report["artifact_sha256"],
        "method": "amount-balance observed-minus-predicted interval innovations",
        "summary_window_start_h": FAULT_TIME,
        "units": {"delta_mu": "1/h", "delta_qS": "g_substrate/(g_biomass*h)",
                  "delta_qP": "g_product/(g_biomass*h)"},
        "batches": normal_rows + fault_rows})
    write_json(output / "evaluation.json", report)
    if strict and (auc <= .90 or not isolation_ok):
        raise RuntimeError("Fault diagnostic acceptance failed; inspect evaluation.json")
    return report


def few_shot_scaling(data: Dataset, output: Path, epochs: int = 40) -> dict:
    """Independent 3/7/15-batch fits with identical validation and test sets."""
    from .train import train
    results = []
    for n in (3, 7, 15):
        subset = replace(data, train=data.train[:n])
        path = train(subset, output / f"n{n}", TrainConfig(seed=data.seed, epochs=epochs))
        model, _ = load_artifact(path)
        score = score_model(model, data.test)
        results.append({"n_train_batches": n, "artifact_sha256": sha256(path),
                        "assays": score["assays"], "early_oot": early_forecast(model, data.test)})
    rmse = [r["early_oot"]["day5_titer_rmse_synthetic_truth"] for r in results]
    report = {"results": results, "same_epochs_per_fit": epochs,
              "day5_error_nonincreasing": all(b <= a for a, b in zip(rmse, rmse[1:])),
              "log_log_day5_rmse_slope": float(np.polyfit(np.log([3, 7, 15]), np.log(np.maximum(rmse, 1e-12)), 1)[0]),
              "interpretation": "Single-seed learning curve; trend is reported, not guaranteed"}
    write_json(output / "few_shot_scaling.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation"))
    parser.add_argument("--few-shot-epochs", type=int, default=40,
                        help="Independent fits at 3/7/15 batches; 0 skips this expensive check")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    _, document = load_artifact(args.artifact)
    data = make_dataset(document["metadata"]["dataset_seed"])
    report = evaluate(args.artifact, data, args.output, strict=not args.report_only)
    if args.few_shot_epochs:
        report["few_shot_scaling"] = few_shot_scaling(data, args.output / "few_shot", args.few_shot_epochs)
        write_json(args.output / "evaluation.json", report)
    print(f"qP AUROC={report['fault_qP_auroc']:.4f}; rate isolation={report['rate_isolation_pass']}")


if __name__ == "__main__":
    main()
