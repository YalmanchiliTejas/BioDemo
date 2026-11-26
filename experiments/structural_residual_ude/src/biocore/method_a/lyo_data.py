"""SI lyophilization observations and an independent synthetic NumPy plant.

The plant is for software checks, not experimental validation. No torch model,
neural parameters, or benchmark truth is used by the training data loader.
"""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path

import numpy as np
import torch

from .config import DTYPE

UNITS = {"time": "s", "temperature": "K", "pressure": "Pa", "length": "m"}
CHANNELS = ("bottom_temperature_k", "dried_layer_m")
PLANT_COEFFICIENTS = {"Kc": 2.8, "Kp": 2.45, "Kd": .031,
                      "Rp0": 7500., "A1": 2.9e8, "A2": 460.}
COMPLETION_FRACTION = 1e-4


@dataclass(frozen=True)
class LyoBatch:
    batch_id: str
    times: torch.Tensor  # [time], seconds; y0 is the state at times[0].
    y0: torch.Tensor  # [1], dried thickness in metres.
    process_args: torch.Tensor  # [2/3/4/5], documented constant/ramp controls.
    observations: torch.Tensor  # [time,2]: bottom temperature K, dried thickness m.
    obs_mask: torch.Tensor  # Actual measurement availability, not model validity.
    primary_mask: torch.Tensor  # [time], independently designated primary-drying samples.
    duration_s: float | None = None  # Absolute endpoint timestamp, not elapsed from times[0].
    fault: bool = False  # Evaluation-only benchmark annotation.
    truth: torch.Tensor | None = None  # Synthetic scoring/debugging only.


@dataclass(frozen=True)
class LyoDataset:
    train: tuple[LyoBatch, ...]
    val: tuple[LyoBatch, ...]
    test: tuple[LyoBatch, ...]
    faults: tuple[LyoBatch, ...] = ()
    seed: int = 2023
    provenance: dict = field(default_factory=dict)
    completion_remaining_fraction: float = COMPLETION_FRACTION

    def split_ids(self) -> dict[str, list[str]]:
        return {name: [b.batch_id for b in getattr(self, name)]
                for name in ("train", "val", "test", "faults")}


def validate_batch(batch: LyoBatch) -> None:
    if not isinstance(batch, LyoBatch):
        raise ValueError("Training/evaluation requires LyoBatch, not fermentation data")
    if not isinstance(batch.batch_id, str) or not batch.batch_id:
        raise ValueError("batch_id must be nonempty")
    if type(batch.fault) is not bool:
        raise ValueError("fault must be a boolean evaluation annotation")
    n = len(batch.times)
    for tensor in (batch.times, batch.y0, batch.process_args, batch.observations):
        if tensor.dtype != DTYPE or tensor.device.type != "cpu":
            raise ValueError("The fitting pipeline requires CPU float64 tensors in SI units")
    if (batch.times.shape != (n,) or n < 2 or not torch.isfinite(batch.times).all()
            or (batch.times < 0).any() or not (batch.times[1:] > batch.times[:-1]).all()):
        raise ValueError("Batch timestamps must be finite increasing nonnegative seconds")
    if batch.y0.shape != (1,) or not torch.isfinite(batch.y0).all() or (batch.y0 < 0).any():
        raise ValueError("Initial dried layer must be a finite nonnegative [1] metre state")
    if (batch.process_args.ndim != 1 or len(batch.process_args) not in (2, 3, 4, 5)
            or not torch.isfinite(batch.process_args).all()):
        raise ValueError("Controls must have 2/3/4/5 finite SI entries")
    if batch.observations.shape != (n, 2) or batch.obs_mask.shape != (n, 2) or batch.obs_mask.dtype != torch.bool:
        raise ValueError("Observations/mask must be [time,2] with boolean mask")
    if batch.primary_mask.shape != (n,) or batch.primary_mask.dtype != torch.bool:
        raise ValueError("primary_mask must be boolean [time]")
    if batch.obs_mask.device.type != "cpu" or batch.primary_mask.device.type != "cpu":
        raise ValueError("Observation masks must be on CPU")
    if not torch.isfinite(batch.observations[batch.obs_mask]).all():
        raise ValueError("Observed measurements must be finite; missing entries must be masked")
    if batch.duration_s is not None:
        if (type(batch.duration_s) not in (int, float) or not math.isfinite(batch.duration_s)
                or not float(batch.times[0]) <= batch.duration_s <= float(batch.times[-1])):
            raise ValueError("Observed endpoint must be finite seconds within the batch time range")
    if not ((batch.obs_mask[:, 0] & batch.primary_mask).any()
            or batch.obs_mask[:, 1].any() or batch.duration_s is not None):
        raise ValueError("Batch has no usable temperature, layer, or endpoint observations")


def validate_splits(data: LyoDataset) -> None:
    if not isinstance(data, LyoDataset):
        raise ValueError("Expected a lyophilization dataset")
    if not 0 < data.completion_remaining_fraction < 1:
        raise ValueError("Dataset completion fraction must lie between zero and one")
    groups = [data.train, data.val, data.test, data.faults]
    ids = [b.batch_id for group in groups for b in group]
    if any(not group for group in groups[:3]) or len(ids) != len(set(ids)):
        raise ValueError("Train/val/test must be nonempty and all batch IDs disjoint")
    if any(b.fault for group in groups[:3] for b in group):
        raise ValueError("Fault annotations are evaluation-only")
    for group in groups:
        for batch in group:
            validate_batch(batch)


def _plant(t: float, z: float, args: np.ndarray, fault: bool):
    """Independent scalar heat/mass root via bisection; fixed-step RK4 caller."""
    ts0, pc, ts1, ramp, height = args
    ts = ts0 + (ts1-ts0)*min(1., max(0., t/ramp))
    width = .001*height
    remaining = width*float(np.logaddexp(0., z))
    ld = max(0., min(height, height-remaining))
    remaining = height-ld
    gate = -math.expm1(-remaining/width)
    c = PLANT_COEFFICIENTS
    kv = c["Kc"]+c["Kp"]*pc/(1+c["Kd"]*pc)
    rp = (c["Rp0"]+c["A1"]*ld/(1+c["A2"]*ld))*(1.35 if fault else 1.)
    ap, av = math.pi*.020**2/4, math.pi*.022**2/4
    conductance = av*kv/(1+av*kv*gate*remaining/(ap*2.4))
    low, high = 173.15, min(ts, 273.16)
    for _ in range(40):
        ti = (low+high)/2
        pi = math.exp(9.550426-5723.265/ti+3.53068*math.log(ti)-.00728332*ti)
        mdot = ap*(pi-pc)/rp
        if conductance*(ts-ti) > mdot*2.84e6:
            low = ti
        else:
            high = ti
    front = mdot/(918.*.897*ap)
    tb = ti+gate*mdot*2.84e6*remaining/(ap*2.4)
    return -front/width, tb, ld


def simulate_plant(times: np.ndarray, args: np.ndarray, fault: bool = False,
                   dt: float = 300.) -> tuple[np.ndarray, float | None]:
    """RK4 in the depletion coordinate, with exact step boundaries at ramp end."""
    ratio = 1000.
    z, time = ratio+math.log(-math.expm1(-ratio)), 0.
    threshold_ratio = COMPLETION_FRACTION/.001
    threshold = threshold_ratio+math.log(-math.expm1(-threshold_ratio))
    endpoint, rows = None, []
    for target in times:
        while time < target:
            h = min(dt, float(target)-time)
            if time < args[3] < time+h:
                h = args[3]-time
            k1 = _plant(time, z, args, fault)[0]
            k2 = _plant(time+h/2, z+h*k1/2, args, fault)[0]
            k3 = _plant(time+h/2, z+h*k2/2, args, fault)[0]
            k4 = _plant(time+h, z+h*k3, args, fault)[0]
            new_z = z+h*(k1+2*k2+2*k3+k4)/6
            if endpoint is None and z > threshold >= new_z:
                endpoint = time+h*(z-threshold)/(z-new_z)
            z, time = new_z, time+h
        _, tb, ld = _plant(time, z, args, fault)
        rows.append((tb, ld))
    return np.asarray(rows, dtype=np.float64), endpoint


def make_dataset(seed: int = 2023, split_sizes=(15, 10, 15, 10)) -> LyoDataset:
    """Ragged synthetic temperatures/endpoints, varied ramps/fill heights.

    No dried-layer measurements are fabricated as available assays. Plant
    states are retained separately as truth for software checks only.
    """
    if len(split_sizes) != 4 or any(type(n) is not int or n < 0 for n in split_sizes) or any(n == 0 for n in split_sizes[:3]):
        raise ValueError("split_sizes requires positive train/val/test counts and nonnegative faults")
    rng, batches = np.random.default_rng(seed), []
    for i in range(sum(split_sizes)):
        fault = i >= sum(split_sizes[:3])
        args = np.array([rng.uniform(235., 241.), rng.uniform(6., 10.),
                         rng.uniform(247., 252.), rng.uniform(1800., 5400.), rng.uniform(.006, .009)])
        n = int(rng.integers(12, 16))
        times = np.linspace(0., 240000., n)
        times[1:-1] += rng.uniform(-2000., 2000., n-2)
        truth, endpoint = simulate_plant(times, args, fault)
        if endpoint is None:
            raise RuntimeError("Synthetic fixture failed to complete within its horizon")
        duration = float(np.clip(endpoint+rng.normal(0., 180.), 1., times[-1]))
        # Include the measured endpoint so duration supervision need not interpolate
        # across a large sparse interval. All rows remain strictly increasing.
        times = np.sort(np.append(times, duration))
        truth, _ = simulate_plant(times, args, fault)
        primary = times < endpoint
        observed = truth.copy()
        observed[:, 0] += rng.normal(0., .15, len(times))
        mask = np.zeros(observed.shape, dtype=bool)
        mask[:, 0] = primary & (rng.random(len(times)) >= .1)
        observed[~mask] = np.nan
        tensor = lambda x: torch.tensor(x, dtype=DTYPE)
        batches.append(LyoBatch(f"{'resistance-fault' if fault else 'normal'}-{i:03d}", tensor(times),
                                tensor([0.]), tensor(args), tensor(observed),
                                torch.tensor(mask), torch.tensor(primary), duration, fault, tensor(truth)))
    # Normal batch split membership is shuffled once; faults never train.
    normal = [batches[i] for i in rng.permutation(sum(split_sizes[:3]))]
    a, b, c, _ = split_sizes
    data = LyoDataset(tuple(normal[:a]), tuple(normal[a:a+b]), tuple(normal[a+b:a+b+c]),
                      tuple(batches[a+b+c:]), seed,
                      {"kind": "synthetic", "generator": "numpy-rk4-bisection-lyo-v1",
                       "plant_coefficients": PLANT_COEFFICIENTS, "sensor_noise_sd_k": .15,
                       "endpoint_noise_sd_s": 180., "fault": "35% higher cake resistance"})
    validate_splits(data)
    return data


def save_dataset(data: LyoDataset, path: Path) -> None:
    """Interoperable JSON; missing measurements are null, never NaN."""
    validate_splits(data)
    def row(b):
        return {"batch_id": b.batch_id, "times_s": b.times.tolist(),
                "initial_dried_layer_m": float(b.y0[0]), "controls": b.process_args.tolist(),
                "observations": [[float(v) if b.obs_mask[i, j] else None for j, v in enumerate(r)]
                                 for i, r in enumerate(b.observations)],
                "primary_mask": b.primary_mask.tolist(), "duration_s": b.duration_s, "fault": b.fault}
    document = {"schema_version": 1, "units": UNITS, "channels": list(CHANNELS),
                "seed": data.seed, "provenance": data.provenance,
                "completion_remaining_fraction": data.completion_remaining_fraction,
                "splits": {name: [row(b) for b in getattr(data, name)] for name in data.split_ids()}}
    Path(path).write_text(json.dumps(document, indent=2, allow_nan=False)+"\n")


def load_dataset(path: Path) -> LyoDataset:
    document = json.loads(Path(path).read_text())
    if (document.get("schema_version") != 1 or document.get("units") != UNITS
            or document.get("channels") != list(CHANNELS)):
        raise ValueError("Expected SI lyophilization dataset schema, units and channels")
    def batch(r):
        if not isinstance(r["primary_mask"], list) or any(type(v) is not bool for v in r["primary_mask"]):
            raise ValueError("primary_mask JSON entries must be boolean")
        observations = torch.tensor([[float("nan") if v is None else v for v in row]
                                     for row in r["observations"]], dtype=DTYPE)
        return LyoBatch(r["batch_id"], torch.tensor(r["times_s"], dtype=DTYPE),
                        torch.tensor([r["initial_dried_layer_m"]], dtype=DTYPE),
                        torch.tensor(r["controls"], dtype=DTYPE), observations,
                        torch.tensor([[v is not None for v in row] for row in r["observations"]]),
                        torch.tensor(r["primary_mask"], dtype=torch.bool), r.get("duration_s"), r.get("fault", False))
    data = LyoDataset(**{name: tuple(batch(r) for r in document["splits"].get(name, []))
                         for name in ("train", "val", "test", "faults")},
                      seed=document["seed"], provenance=document["provenance"],
                      completion_remaining_fraction=document["completion_remaining_fraction"])
    validate_splits(data)
    return data
