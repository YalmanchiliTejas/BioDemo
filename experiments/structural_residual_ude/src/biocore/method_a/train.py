"""Explicit Adam loop; validation and early stopping use whole held-out batches."""
import argparse
import hashlib
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from .artifact import save_artifact, write_json
from .config import ModelConfig, TrainConfig, seed_everything
from .loss import fit_state_scale, masked_trajectory_mse, physics_hijack_ratio
from .model import BioprocessSolver, HybridBioprocessUDE
from .synthetic import Batch, Dataset, make_dataset


def data_fingerprint(batches: tuple[Batch, ...]) -> str:
    digest = hashlib.sha256()
    for b in batches:
        digest.update(b.batch_id.encode())
        for t in (b.times, b.y0, b.process_args, b.observations, b.obs_mask):
            digest.update(t.numpy().tobytes())
    return digest.hexdigest()


def minibatches(batches: tuple[Batch, ...], size: int, rng=None):
    # Ragged trajectories are bucketed by observation count, never padded with fake times.
    buckets = defaultdict(list)
    order = range(len(batches)) if rng is None else rng.permutation(len(batches))
    for i in order:
        buckets[len(batches[i].times)].append(batches[i])
    for group in buckets.values():
        for start in range(0, len(group), size):
            yield group[start:start+size]


def solve_batches(solver: BioprocessSolver, batches: list[Batch], warmup=False):
    n = max(2, len(batches[0].times)//2) if warmup else len(batches[0].times)
    solution = solver.solve(torch.stack([b.y0 for b in batches]),
                            torch.stack([b.times[:n] for b in batches]),
                            torch.stack([b.process_args for b in batches]))
    observations = torch.stack([b.observations[:n] for b in batches])
    mask = torch.stack([b.obs_mask[:n] for b in batches])
    return solution, observations, mask


def gradient_norm(parameters) -> float:
    return math.sqrt(sum(float(p.grad.detach().square().sum())
                         for p in parameters if p.grad is not None))


def validate_splits(data: Dataset) -> None:
    groups = [data.train, data.val, data.test, data.faults]
    ids = [b.batch_id for group in groups for b in group]
    if len(set(ids)) != len(ids) or any(not group for group in groups):
        raise ValueError("Splits must be nonempty and batch_id-disjoint")
    if any(b.fault for group in groups[:3] for b in group):
        raise ValueError("Fault batches are evaluation-only")


def train(data: Dataset, output: Path, config: TrainConfig | None = None,
          model_config: ModelConfig | None = None) -> Path:
    config = config or TrainConfig()
    validate_splits(data)
    seed_everything(config.seed)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    scale = fit_state_scale(data.train)
    model_config = (model_config or ModelConfig()).model_copy(
        update={"state_scale": tuple(scale.tolist())})
    model = HybridBioprocessUDE(model_config)
    solver = BioprocessSolver(model)
    optimizer = torch.optim.Adam([
        {"params": model.biology_core.parameters(), "lr": 1e-2, "weight_decay": 0.},
        {"params": model.residual_mlp.parameters(), "lr": 1e-3, "weight_decay": 1e-3},
    ])
    rng = np.random.default_rng(config.seed)
    history, best, stale = [], float("inf"), 0
    checkpoint = output / "best.safetensors"
    for epoch in range(config.epochs):
        warmup = epoch < int(config.epochs*config.warmup_fraction)
        model.train()
        train_sum, count = 0., 0
        grad_phys, grad_mlp, nfes = [], [], []
        for group in minibatches(data.train, config.batch_size, rng):
            optimizer.zero_grad(set_to_none=True)
            solution, observed, mask = solve_batches(solver, group, warmup)
            loss = masked_trajectory_mse(solution.ys, observed, mask, scale)
            if not torch.isfinite(loss):
                raise RuntimeError("Nonfinite training loss")
            loss.backward()
            grad_phys.append(gradient_norm(model.biology_core.parameters()))
            grad_mlp.append(gradient_norm(model.residual_mlp.parameters()))
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0,
                                          error_if_nonfinite=True)
            optimizer.step()
            n = int(mask.sum())
            train_sum += float(loss.detach())*n
            count += n
            nfes.extend(solution.stats["n_f_evals"].tolist())
        model.eval()
        with torch.no_grad():
            val_sum, val_count, priors, residuals = 0., 0, [], []
            for group in minibatches(data.val, config.batch_size):
                solution, observed, mask = solve_batches(solver, group)
                n = int(mask.sum())
                val_sum += float(masked_trajectory_mse(solution.ys, observed, mask, scale))*n
                val_count += n
                p, r = model.rates(solution.ys)
                priors.append(p.reshape(-1, 3))
                residuals.append(r.reshape(-1, 3))
            val_loss = val_sum/val_count
            hijack = float(physics_hijack_ratio(torch.cat(priors), torch.cat(residuals)))
        row = {"epoch": epoch, "window": "half" if warmup else "full",
               "train_loss": train_sum/count, "val_loss": val_loss,
               "grad_norm_phys": float(np.mean(grad_phys)),
               "grad_norm_mlp": float(np.mean(grad_mlp)),
               "mean_n_f_evals": float(np.mean(nfes)), "physics_hijack_ratio": hijack}
        history.append(row)
        print(" ".join(f"{k}={v:.7g}" if isinstance(v, float) else f"{k}={v}"
                       for k, v in row.items()), flush=True)
        if val_loss < best-config.min_delta:
            best, stale = val_loss, 0
            save_artifact(model, checkpoint, {
                "train": config.model_dump(), "dataset_seed": data.seed,
                "split_ids": data.split_ids(), "best_epoch": epoch, "val_loss": best,
                "train_data_sha256": data_fingerprint(data.train),
                "val_data_sha256": data_fingerprint(data.val),
                "initial_state_source": "known synthetic inoculation/setpoint, not LIMS assays",
            })
        elif not warmup:
            stale += 1
        if stale >= config.patience:
            break
    write_json(output / "training_history.json", history)
    return checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/main"))
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--seed", type=int, default=2023)
    args = parser.parse_args()
    train(make_dataset(args.seed), args.output, TrainConfig(seed=args.seed, epochs=args.epochs))


if __name__ == "__main__":
    main()
