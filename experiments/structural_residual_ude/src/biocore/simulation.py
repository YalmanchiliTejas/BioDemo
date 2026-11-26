"""Generate a deterministic 50-batch conventional lyophilization dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import torch

DTYPE = torch.float64
COMPLETION_REMAINING_FRACTION = 0.001
SPLIT_SEEDS = {"train": 101, "val": 202, "test_normal": 303, "test_fault": 404}

# Calibrated Purdue REVO 6R baseline (SI: W, m, kg, s, K, Pa)
PLANT = {
    "Kc": 11.04,
    "Kp": 1.03,
    "Kd": 0.0273,
    "Rp0": 1.0e5,
    "A1": 2.0e7,
    "A2": 100.0,
    "vial_area": 3.8e-4,
    "product_area": 3.14e-4,
    "side_area": 4.15e-4,      # pi * 22mm * 6mm wetted vial wall
    "frozen_height": 0.006,    # 6 mm initial frozen cake
    "k_ice": 2.3,
    "rho_ice": 917.0,
    "porosity": 0.95,
    "latent_heat": 2.838e6,
    "sigma_sb": 5.670374419e-8,
    "t_wall_k": 293.15,        # 20 C chamber wall (unmodeled by LyoPhysicsCore)
    "eps_rad_normal": 0.25,    # ~15-20% unmodeled radiative heat flux
}


def ice_pressure(t_k: torch.Tensor) -> torch.Tensor:
    return torch.exp(
        9.550426 - 5723.265 / t_k + 3.53068 * t_k.log() - 0.00728332 * t_k
    )


def true_plant_balance(
    ld: torch.Tensor,
    ts: torch.Tensor,
    pc: torch.Tensor,
    kv_mult: torch.Tensor,
    rp_mult: torch.Tensor,
    eps_rad: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Solve true shelf + wall-radiation energy balance via 10 Newton steps."""
    p = PLANT
    ld_c = ld.clamp(0.0, p["frozen_height"])
    frozen = (p["frozen_height"] - ld_c).clamp(min=0.0)

    kv = kv_mult * (p["Kc"] + p["Kp"] * pc / (1.0 + p["Kd"] * pc))
    rp = rp_mult * (p["Rp0"] + p["A1"] * ld_c / (1.0 + p["A2"] * ld_c))

    cond = (p["vial_area"] * kv) / (
        1.0 + p["vial_area"] * kv * frozen / (p["product_area"] * p["k_ice"])
    )
    rad_coeff = p["sigma_sb"] * eps_rad * p["side_area"]
    t_wall4 = p["t_wall_k"] ** 4

    ti = torch.full_like(ts, 273.16).minimum(ts + 10.0).clamp(max=273.16)
    for _ in range(10):
        pi = ice_pressure(ti)
        q_in = cond * (ts - ti) + rad_coeff * (t_wall4 - ti.pow(4))
        q_sub = p["product_area"] * (pi - pc) / rp * p["latent_heat"]
        mismatch = q_in - q_sub
        dpi = pi * (5723.265 / ti.square() + 3.53068 / ti - 0.00728332)
        slope = (
            -cond
            - 4.0 * rad_coeff * ti.pow(3)
            - p["product_area"] * dpi / rp * p["latent_heat"]
        )
        ti = (ti - mismatch / slope).clamp(150.0, 273.16)

    pi = ice_pressure(ti)
    mass_rate = (p["product_area"] * (pi - pc) / rp).clamp(min=0.0)
    active = ld < p["frozen_height"]
    mass_rate = torch.where(active, mass_rate, torch.zeros_like(mass_rate))

    q_shelf = cond * (ts - ti)
    tb = ti + q_shelf * frozen / (p["product_area"] * p["k_ice"])
    front_rate = mass_rate / (p["rho_ice"] * p["porosity"] * p["product_area"])
    return front_rate, tb, kv, rp


def simulate_split(
    n_batches: int,
    fault_modes: list[str],
    seed: int,
    n_points: int = 12,
    dt_sec: float = 60.0,
    max_steps: int = 3000,
) -> dict[str, object]:
    """Simulate a whole-batch split with irregular timestamps and sensor noise."""
    gen = torch.Generator().manual_seed(seed)

    # Diverse conventional shelf-heated operating conditions
    ts = 243.15 + 20.0 * torch.rand((n_batches,), generator=gen, dtype=DTYPE)
    pc = 8.0 + 14.0 * torch.rand((n_batches,), generator=gen, dtype=DTYPE)
    process_args = torch.stack((ts, pc), dim=-1)

    kv_mult = torch.ones((n_batches,), dtype=DTYPE)
    rp_mult = torch.ones((n_batches,), dtype=DTYPE)
    eps_rad = torch.full((n_batches,), PLANT["eps_rad_normal"], dtype=DTYPE)

    for i, mode in enumerate(fault_modes):
        if mode == "kv_edge_fault":
            kv_mult[i] = 1.45
            eps_rad[i] = 0.45
        elif mode == "rp_collapse_fault":
            rp_mult[i] = 0.60

    # Vectorized RK4 forward integration on a fine 60s grid
    ld = torch.zeros((n_batches,), dtype=DTYPE)
    ld_hist = torch.empty((n_batches, max_steps + 1), dtype=DTYPE)
    ld_hist[:, 0] = ld
    h = PLANT["frozen_height"]

    for step in range(1, max_steps + 1):
        k1, *_ = true_plant_balance(ld, ts, pc, kv_mult, rp_mult, eps_rad)
        k2, *_ = true_plant_balance(ld + 0.5 * dt_sec * k1, ts, pc, kv_mult, rp_mult, eps_rad)
        k3, *_ = true_plant_balance(ld + 0.5 * dt_sec * k2, ts, pc, kv_mult, rp_mult, eps_rad)
        k4, *_ = true_plant_balance(ld + dt_sec * k3, ts, pc, kv_mult, rp_mult, eps_rad)
        ld = (ld + (dt_sec / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)).clamp(0.0, h)
        ld_hist[:, step] = ld

    # Locate drying completion per batch (must finish inside max_steps)
    done_mask = ld_hist >= ((1.0 - COMPLETION_REMAINING_FRACTION) * h)
    if not done_mask.any(dim=1).all():
        raise RuntimeError("Increase max_steps: at least one batch did not finish drying")
    end_idx = done_mask.to(torch.int64).argmax(dim=1)
    t_end_sec = end_idx.to(DTYPE) * dt_sec

    # Irregular per-batch timestamps strictly within [0, 0.90 * t_end]
    base_frac = torch.linspace(0.0, 0.90, n_points, dtype=DTYPE).unsqueeze(0).repeat(n_batches, 1)
    jitter = (torch.rand((n_batches, n_points - 2), generator=gen, dtype=DTYPE) - 0.5) * 0.04
    frac = base_frac.clone()
    frac[:, 1:-1] = (frac[:, 1:-1] + jitter).clamp(0.02, 0.88)
    frac, _ = torch.sort(frac, dim=1)
    t_eval = frac * t_end_sec.unsqueeze(1)

    # Interpolate exact ld_true at t_eval
    pos = t_eval / dt_sec
    idx0 = pos.floor().to(torch.int64).clamp(0, max_steps - 1)
    alpha = pos - idx0.to(DTYPE)
    ld0 = torch.gather(ld_hist, 1, idx0)
    ld1 = torch.gather(ld_hist, 1, idx0 + 1)
    ld_true = ld0 + alpha * (ld1 - ld0)

    # Evaluate exact ground-truth Tb, Kv, Rp at sampled timestamps
    _, tb_true, kv_true, rp_true = true_plant_balance(
        ld_true,
        ts[:, None],
        pc[:, None],
        kv_mult[:, None],
        rp_mult[:, None],
        eps_rad[:, None],
    )

    # Thermocouple noise (+/- 0.4 K) and sparse endpoint-only Ld observation
    tb_obs = tb_true + 0.4 * torch.randn(tb_true.shape, generator=gen, dtype=DTYPE)
    ld_mask = torch.zeros((n_batches, n_points), dtype=torch.bool)
    ld_mask[:, 0] = True
    ld_mask[:, -1] = True
    ld_noisy = (ld_true + 5e-5 * torch.randn(ld_true.shape, generator=gen, dtype=DTYPE)).clamp(0.0, h)
    ld_noisy[:, 0] = 0.0
    ld_obs = torch.where(ld_mask, ld_noisy, torch.full_like(ld_noisy, float("nan")))

    return {
        "y0": torch.zeros((n_batches, 1), dtype=DTYPE),
        "t_eval": t_eval,                # [N, 12] seconds
        "process_args": process_args,    # [N, 2]  [ts_k, pc_pa]
        "tb_obs_k": tb_obs,              # [N, 12] noisy thermocouple (K)
        "tb_true_k": tb_true,            # [N, 12] clean ground truth (K)
        "ld_obs_m": ld_obs,              # [N, 12] NaN on interior points
        "ld_mask": ld_mask,              # [N, 12] bool
        "ld_true_m": ld_true,            # [N, 12] clean ground truth (m)
        "kv_true": kv_true,              # [N, 12]
        "rp_true": rp_true,              # [N, 12]
        "t_end_sec": t_end_sec,          # [N]
        "fault_modes": fault_modes,
    }


def generate_all(out_dir: str | Path = "data/lyo_synthetic") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    splits = {
        "train": simulate_split(20, ["normal"] * 20, seed=SPLIT_SEEDS["train"]),
        "val": simulate_split(10, ["normal"] * 10, seed=SPLIT_SEEDS["val"]),
        "test_normal": simulate_split(10, ["normal"] * 10, seed=SPLIT_SEEDS["test_normal"]),
        "test_fault": simulate_split(
            10, ["kv_edge_fault"] * 5 + ["rp_collapse_fault"] * 5, seed=SPLIT_SEEDS["test_fault"]
        ),
    }

    summary = {
        "plant_constants": PLANT,
        "completion_remaining_fraction": COMPLETION_REMAINING_FRACTION,
        "split_seeds": SPLIT_SEEDS,
        "splits": {},
    }
    for name, data in splits.items():
        torch.save(data, out / f"{name}.pt")
        t_hrs = data["t_end_sec"] / 3600.0
        tb = data["tb_true_k"]
        summary["splits"][name] = {
            "n_batches": len(data["y0"]),
            "t_end_hours_min_max": [round(t_hrs.min().item(), 2), round(t_hrs.max().item(), 2)],
            "tb_k_min_max": [round(tb.min().item(), 2), round(tb.max().item(), 2)],
            "fault_counts": {m: data["fault_modes"].count(m) for m in set(data["fault_modes"])},
        }

    (out / "metadata.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/lyo_synthetic"))
    generate_all(parser.parse_args().output)
