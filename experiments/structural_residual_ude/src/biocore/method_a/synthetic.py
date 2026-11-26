"""Legacy fermentation NumPy plant. Current CLI fixtures live in lyo_data.py."""
from dataclasses import dataclass

import numpy as np
import torch

from .config import DTYPE

GROUND_TRUTH = {"mu_max": 0.028, "Ks": 2.0, "qS_max": 0.055, "qP_max": 0.008}
FAULT_TIME = 24.0  # Beginning of Day 2; 35% productivity loss thereafter.


@dataclass(frozen=True)
class Batch:
    batch_id: str
    times: torch.Tensor
    y0: torch.Tensor  # Known inoculation/setpoint state, independent of LIMS missingness.
    process_args: torch.Tensor  # [F_in (L/h), S_in (g/L)]
    observations: torch.Tensor
    obs_mask: torch.Tensor
    truth: torch.Tensor  # Benchmark scoring only, never used by the fitter.
    fault: bool = False


@dataclass(frozen=True)
class Dataset:
    train: tuple[Batch, ...]
    val: tuple[Batch, ...]
    test: tuple[Batch, ...]
    faults: tuple[Batch, ...]
    seed: int

    def split_ids(self) -> dict[str, list[str]]:
        return {name: [b.batch_id for b in getattr(self, name)]
                for name in ("train", "val", "test", "faults")}


def plant_rhs(t: float, y: np.ndarray, args: np.ndarray, fault: bool) -> np.ndarray:
    x, s, p, v = np.maximum(y, 0.)
    f, s_in = args
    monod = s / (GROUND_TRUTH["Ks"] + s)
    # Hidden density/byproduct inhibition, independent of product secretion:
    # a qP intervention therefore does not also intervene on mu or qS.
    mu = GROUND_TRUTH["mu_max"] * monod * (1 - 0.12 * x / (8 + x))
    qs = GROUND_TRUTH["qS_max"] * monod
    qp = GROUND_TRUTH["qP_max"] * monod
    if fault and t >= FAULT_TIME:
        qp *= 0.65
    dilution = f / max(v, 1e-12)
    return np.array([mu*x - dilution*x, -qs*x + dilution*(s_in-s),
                     qp*x - dilution*p, f], dtype=np.float64)


def simulate_plant(times: np.ndarray, y0: np.ndarray, args: np.ndarray,
                   fault: bool = False, dt: float = 0.1) -> np.ndarray:
    """RK4 with a step boundary at the fault, avoiding discontinuity smearing."""
    y = np.array(y0, dtype=np.float64, copy=True)
    t = 0.
    result = []
    for target in times:
        while t < target - 1e-12:
            h = min(dt, float(target) - t)
            if t < FAULT_TIME < t + h:
                h = FAULT_TIME - t
            # At a step ending at the switch, use its left limit for k4.
            end = np.nextafter(t+h, t) if t < FAULT_TIME else t+h
            k1 = plant_rhs(t, y, args, fault)
            k2 = plant_rhs(t+h/2, y+h*k1/2, args, fault)
            k3 = plant_rhs(t+h/2, y+h*k2/2, args, fault)
            k4 = plant_rhs(end, y+h*k3, args, fault)
            y = y + h*(k1 + 2*k2 + 2*k3 + k4)/6
            t += h
        result.append(y.copy())
    return np.asarray(result, dtype=np.float64)


def make_dataset(seed: int = 2023) -> Dataset:
    rng = np.random.default_rng(seed)
    batches = []
    for i in range(50):
        fault = i >= 40
        n = int(rng.integers(8, 11))
        times = np.linspace(0., 120., n)
        times[1:-1] += rng.uniform(-4., 4., n-2)
        args = np.array([rng.uniform(.012, .020), rng.uniform(180., 240.)])
        y0 = np.array([rng.uniform(1.5, 2.5), rng.uniform(16., 24.), 0., rng.uniform(1.8, 2.2)])
        truth = simulate_plant(times, y0, args, fault)
        sigma = np.maximum(truth * np.array([.01, .01, .008, 0.]), [.01, .05, .003, 0.])
        observed = np.maximum(truth + rng.normal(size=truth.shape)*sigma, 0.)
        mask = rng.random(truth.shape) >= .10
        observed[~mask] = np.nan
        tensor = lambda a: torch.tensor(a, dtype=DTYPE)
        batches.append(Batch(f"{'fault' if fault else 'normal'}-{i:03d}", tensor(times),
                             tensor(y0), tensor(args), tensor(observed),
                             torch.tensor(mask, dtype=torch.bool), tensor(truth), fault))
    # Randomization is at batch level, never at timestamp level.
    order = rng.permutation(40)
    normal = [batches[i] for i in order]
    return Dataset(tuple(normal[:15]), tuple(normal[15:25]), tuple(normal[25:]),
                   tuple(batches[40:]), seed)
