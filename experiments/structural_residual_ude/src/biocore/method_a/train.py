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

from .artifact import load_artifact, save_artifact, sha256, write_json
from .config import LyoModelConfig, LyoTrainConfig, seed_everything
from .loss import LOSS_COMPONENTS, lyophilization_loss, weighted_loss_components
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


def validation_terms(
    model: HybridLyophilizationUDE, solver: LyophilizationSolver,
    batches: tuple[LyoBatch, ...], config: LyoTrainConfig,
) -> dict[str, float]:
    """Evaluate the frozen validation objective with the training aggregation."""
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
    seed_everything(config.seed)
    return _fit(data, Path(output), config, HybridLyophilizationUDE(model_config))


def warm_start(checkpoint: Path, output: Path, epochs: int, seed: int | None = None) -> Path:
    """Fit the original dataset starting from a verified checkpoint's weights."""
    checkpoint, output = Path(checkpoint), Path(output)
    if output.resolve() == checkpoint.parent.resolve():
        raise ValueError("Choose an output directory separate from the input checkpoint")
    model, document = load_artifact(checkpoint)
    if not isinstance(model, HybridLyophilizationUDE):
        raise ValueError("Warm starts require a lyophilization checkpoint")
    metadata = document["metadata"]
    snapshot = checkpoint.parent / "dataset.json"
    if sha256(snapshot) != metadata["dataset_sha256"]:
        raise ValueError("Saved dataset snapshot SHA-256 mismatch")
    data = load_dataset(snapshot)
    settings = {**metadata["train"], "epochs": epochs, "warmup_fraction": 0.}
    if seed is not None:
        settings["seed"] = seed
    config = LyoTrainConfig.model_validate(settings)
    seed_everything(config.seed)
    model.requires_grad_(True)
    initialization = {
        "source_checkpoint_sha256": document["weights_sha256"],
        "source_best_epoch": metadata["best_epoch"],
        "source_validation_loss": metadata["val_loss"],
    }
    return _fit(data, output, config, model, initialization)


def _fit(data: LyoDataset, output: Path, config: LyoTrainConfig,
         model: HybridLyophilizationUDE, initialization: dict | None = None) -> Path:
    if model.config.completion_remaining_fraction != data.completion_remaining_fraction:
        raise ValueError("Model and observed endpoint definitions must use the same completion fraction")
    output.mkdir(parents=True, exist_ok=True)
    # Snapshot actual observations/splits so evaluation never regenerates a
    # different dataset or reads a synthetic plant as an experimental source.
    save_dataset(data, output / "dataset.json")
    solver = LyophilizationSolver(model)
    optimizer = torch.optim.Adam([
        {"params": model.physics_core.parameters(), "lr": config.physics_lr, "weight_decay": 0.},
        {"params": model.residual_mlp.parameters(), "lr": config.residual_lr, "weight_decay": 0.},
    ])
    rng = np.random.default_rng(config.seed)
    history, best, stale = [], float("inf"), 0
    checkpoint = output / "best.safetensors"
    split_ids = data.split_ids()
    metadata = {
        "train": config.model_dump(), "dataset_seed": data.seed, "split_ids": split_ids,
        "data_sha256": {name: data_fingerprint(getattr(data, name)) for name in split_ids},
        "dataset_file": "dataset.json", "dataset_sha256": sha256(output / "dataset.json"),
        "data_provenance": data.provenance,
        "objective": "equal-vial normalized temperature/layer/endpoint + validity/coverage/residual penalties",
        "initial_state_source": "explicit supplied initial dried-layer state",
        "warmup": "freeze residual network; always solve full time window",
    }
    if initialization is not None:
        metadata.update(warm_start=initialization, warmup="skip warmup; load fitted weights")
        best = validation_terms(model, solver, data.val, config)["total"]
        save_artifact(model, checkpoint, {**metadata, "best_epoch": -1, "val_loss": best})
        print(f"warm_start_validation_loss={best:.7g}", flush=True)
    warmup_epochs = int(config.epochs*config.warmup_fraction)
    metrics_columns = ("epoch", "phase", "train_loss", "val_loss", "physics_lr", "residual_lr")
    component_columns = tuple(f"{split}_{name}_loss" for split in ("train", "val") for name in LOSS_COMPONENTS)
    with (output / "training_metrics.csv").open("w", newline="") as metrics_file:
        metrics = csv.DictWriter(metrics_file, metrics_columns + component_columns, extrasaction="ignore")
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
            validation = validation_terms(model, solver, data.val, config)
            row = {"epoch": epoch, "phase": "physics_only" if warmup else "hybrid",
                   "train": {name: value/count for name, value in sums.items()}, "validation": validation,
                   "train_loss": sums["total"]/count, "val_loss": validation["total"],
                   "physics_lr": physics_lr, "residual_lr": residual_lr,
                   "grad_norm_phys": float(np.mean(grad_phys)), "grad_norm_mlp": float(np.mean(grad_mlp)),
                   "mean_n_f_evals": float(np.mean(nfes))}
            history.append(row)
            contributions = {
                f"{split}_{name}_loss": value
                for split, terms in (("train", row["train"]), ("val", validation))
                for name, value in weighted_loss_components(terms, config).items()
            }
            metrics.writerow({**row, **contributions})
            metrics_file.flush()
            print(f"epoch={epoch} phase={row['phase']} train_loss={row['train_loss']:.7g} "
                  f"val_loss={row['val_loss']:.7g} physics_lr={physics_lr:g} "
                  f"residual_lr={residual_lr:g} nfe={row['mean_n_f_evals']:.1f}", flush=True)
            if row["val_loss"] < best-config.min_delta:
                best, stale = row["val_loss"], 0
                save_artifact(model, checkpoint, {**metadata, "best_epoch": epoch, "val_loss": best})
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
    source.add_argument("--init-from", type=Path, help="Warm-start from a checkpoint and its saved dataset")
    parser.add_argument("--output", type=Path, default=Path("artifacts/lyophilization"))
    parser.add_argument("--epochs", type=int, help="Maximum epochs (default: 120, or 5 in smoke mode)")
    parser.add_argument("--smoke", action="store_true", help="Use one batch from each available split")
    parser.add_argument("--seed", type=int, help="Training seed (default: source checkpoint seed or 2023)")
    args = parser.parse_args()
    epochs = args.epochs if args.epochs is not None else (5 if args.smoke else 120)
    if args.init_from:
        if args.smoke:
            parser.error("--smoke cannot be used with --init-from; the checkpoint's full split is reused")
        path = warm_start(args.init_from, args.output, epochs, args.seed)
    else:
        config = LyoTrainConfig(seed=2023 if args.seed is None else args.seed, epochs=epochs)
        if args.simulation_dir:
            data = load_simulation_dataset(args.simulation_dir)
        elif args.data:
            data = load_dataset(args.data)
        else:
            data = make_dataset(config.seed)
        if args.smoke:
            data = replace(data, train=data.train[:1], val=data.val[:1], test=data.test[:1], faults=data.faults[:1])
        path = train(data, args.output, config)
    print(f"Lyophilization checkpoint: {path}")


if __name__ == "__main__":
    main()
