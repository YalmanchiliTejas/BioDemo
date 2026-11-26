"""Fit lyophilization temperatures/endpoints with whole-batch validation."""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch

from .artifact import save_artifact, sha256, write_json
from .config import LyoModelConfig, LyoTrainConfig, seed_everything
from .loss import lyophilization_loss
from .lyo_data import (
    LyoBatch, LyoDataset, load_dataset, load_simulation_dataset, make_dataset, save_dataset,
    validate_splits,
)
from .model import HybridLyophilizationUDE, LyophilizationSolver


def data_fingerprint(batches: tuple[LyoBatch, ...]) -> str:
    """Hash measured inputs/masks/endpoints, including tensor shapes and order.

    Synthetic truth is deliberately excluded: it never participates in fitting.
    Missing-value payloads are canonicalized; availability remains in obs_mask.
    """
    digest = hashlib.sha256()
    for b in batches:
        digest.update(json.dumps([b.batch_id, b.duration_s, b.fault], allow_nan=False).encode())
        for tensor in (b.times, b.y0, b.process_args,
                       torch.where(b.obs_mask, b.observations, 0.), b.obs_mask, b.primary_mask):
            value = tensor.detach().cpu().contiguous()
            digest.update(str((str(value.dtype), tuple(value.shape))).encode())
            digest.update(value.numpy().tobytes())
    return digest.hexdigest()


def minibatches(batches: tuple[LyoBatch, ...], size: int, rng=None):
    """Bucket ragged times AND control layouts; never pad or resample assays."""
    buckets = defaultdict(list)
    order = range(len(batches)) if rng is None else rng.permutation(len(batches))
    for i in order:
        b = batches[i]
        buckets[(len(b.times), len(b.process_args))].append(b)
    for group in buckets.values():
        for start in range(0, len(group), size):
            yield group[start:start+size]


def solve_batches(solver: LyophilizationSolver, batches: list[LyoBatch]):
    """Always solve the full window: endpoint supervision needs the late times."""
    return solver.solve(torch.stack([b.y0 for b in batches]),
                        torch.stack([b.times for b in batches]),
                        torch.stack([b.process_args for b in batches]))


def gradient_norm(parameters) -> float:
    return math.sqrt(sum(float(p.grad.detach().square().sum())
                         for p in parameters if p.grad is not None))


def _validation(model, solver, batches, config):
    sums, count = defaultdict(float), 0
    with torch.no_grad():
        for group in minibatches(batches, config.batch_size):
            terms = lyophilization_loss(model, solve_batches(solver, group), group, config)
            for name, value in terms.items():
                sums[name] += float(value)*len(group)
            count += len(group)
    result = {name: value/count for name, value in sums.items()}
    if not all(math.isfinite(value) for value in result.values()):
        raise RuntimeError("Nonfinite validation objective")
    return result


def train(data: LyoDataset, output: Path, config: LyoTrainConfig | None = None,
          model_config: LyoModelConfig | None = None) -> Path:
    config = config or LyoTrainConfig()
    if not isinstance(config, LyoTrainConfig):
        config = LyoTrainConfig.model_validate(config.model_dump())
    validate_splits(data)
    model_config = model_config or LyoModelConfig(
        completion_remaining_fraction=data.completion_remaining_fraction)
    if model_config.completion_remaining_fraction != data.completion_remaining_fraction:
        raise ValueError("Model and observed endpoint definitions must use the same completion fraction")
    seed_everything(config.seed)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Snapshot actual observations/splits so evaluation never regenerates a
    # different dataset or reads a synthetic plant as an experimental source.
    save_dataset(data, output / "dataset.json")
    model = HybridLyophilizationUDE(model_config)
    solver = LyophilizationSolver(model)
    optimizer = torch.optim.Adam([
        {"params": model.physics_core.parameters(), "lr": config.physics_lr, "weight_decay": 0.},
        {"params": model.residual_mlp.parameters(), "lr": config.residual_lr, "weight_decay": 0.},
    ])
    rng = np.random.default_rng(config.seed)
    history, best, stale = [], float("inf"), 0
    checkpoint = output / "best.safetensors"
    warmup_epochs = int(config.epochs*config.warmup_fraction)
    with (output / "training_metrics.csv").open("w", newline="") as metrics_file:
        metrics = csv.DictWriter(
            metrics_file, ("epoch", "phase", "train_loss", "val_loss", "physics_lr", "residual_lr"),
            extrasaction="ignore",
        )
        metrics.writeheader()
        metrics_file.flush()
        for epoch in range(config.epochs):
            warmup = epoch < warmup_epochs
            # Physics-first warmup preserves full trajectories and duration targets.
            model.residual_mlp.requires_grad_(not warmup)
            model.train()
            physics_lr, residual_lr = (group["lr"] for group in optimizer.param_groups)
            sums, count = defaultdict(float), 0
            grad_phys, grad_mlp, nfes = [], [], []
            for group in minibatches(data.train, config.batch_size, rng):
                optimizer.zero_grad(set_to_none=True)
                solution = solve_batches(solver, group)
                terms = lyophilization_loss(model, solution, group, config)
                if not all(torch.isfinite(value).all() for value in terms.values()):
                    raise RuntimeError("Nonfinite lyophilization training objective")
                terms["total"].backward()
                grad_phys.append(gradient_norm(model.physics_core.parameters()))
                grad_mlp.append(gradient_norm(model.residual_mlp.parameters()))
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
                optimizer.step()
                if not all(torch.isfinite(p).all() for p in model.parameters()):
                    raise RuntimeError("Nonfinite model parameters after optimizer step")
                for name, value in terms.items():
                    sums[name] += float(value.detach())*len(group)
                count += len(group)
                nfes.extend(solution.stats["n_f_evals"].tolist())
            model.eval()
            validation = _validation(model, solver, data.val, config)
            row = {"epoch": epoch, "phase": "physics_only" if warmup else "hybrid",
                   "train": {name: value/count for name, value in sums.items()}, "validation": validation,
                   "train_loss": sums["total"]/count, "val_loss": validation["total"],
                   "physics_lr": physics_lr, "residual_lr": residual_lr,
                   "grad_norm_phys": float(np.mean(grad_phys)), "grad_norm_mlp": float(np.mean(grad_mlp)),
                   "mean_n_f_evals": float(np.mean(nfes))}
            history.append(row)
            metrics.writerow(row)
            metrics_file.flush()
            print(f"epoch={epoch} phase={row['phase']} train_loss={row['train_loss']:.7g} "
                  f"val_loss={row['val_loss']:.7g} physics_lr={physics_lr:g} "
                  f"residual_lr={residual_lr:g} nfe={row['mean_n_f_evals']:.1f}", flush=True)
            if row["val_loss"] < best-config.min_delta:
                best, stale = row["val_loss"], 0
                save_artifact(model, checkpoint, {
                    "train": config.model_dump(), "dataset_seed": data.seed, "split_ids": data.split_ids(),
                    "data_sha256": {name: data_fingerprint(getattr(data, name)) for name in data.split_ids()},
                    "dataset_file": "dataset.json", "dataset_sha256": sha256(output / "dataset.json"),
                    "data_provenance": data.provenance, "best_epoch": epoch, "val_loss": best,
                    "objective": "equal-vial normalized temperature/layer/endpoint + validity/coverage/residual penalties",
                    "initial_state_source": "explicit supplied initial dried-layer state",
                    "warmup": "freeze residual network; always solve full time window",
                })
            elif not warmup:
                stale += 1
            if stale >= config.patience:
                break
    write_json(output / "training_history.json", history)
    return checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--data", type=Path, help="SI lyophilization dataset JSON")
    source.add_argument("--simulation-dir", type=Path, help="Split files generated by biocore.simulation")
    parser.add_argument("--output", type=Path, default=Path("artifacts/lyophilization"))
    parser.add_argument("--epochs", type=int, help="Maximum epochs (default: 120, or 5 in smoke mode)")
    parser.add_argument("--smoke", action="store_true", help="Use one batch from each available split")
    parser.add_argument("--seed", type=int, default=2023)
    args = parser.parse_args()
    epochs = args.epochs if args.epochs is not None else (5 if args.smoke else 120)
    config = LyoTrainConfig(seed=args.seed, epochs=epochs)
    if args.simulation_dir:
        data = load_simulation_dataset(args.simulation_dir)
    elif args.data:
        data = load_dataset(args.data)
    else:
        data = make_dataset(args.seed)
    if args.smoke:
        data = replace(data, train=data.train[:1], val=data.val[:1], test=data.test[:1], faults=data.faults[:1])
    path = train(data, args.output, config)
    print(f"Lyophilization checkpoint: {path}")


if __name__ == "__main__":
    main()
