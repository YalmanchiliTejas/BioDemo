"""Validated, JSON-serializable configuration and explicit reproducibility setup."""
import random

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field

DTYPE = torch.float64
ASSAYS = ("X", "S", "P", "V")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    eps: float = Field(default=0.1, ge=0, le=1)
    mu_max: float = Field(default=0.026, gt=0)
    Ks: float = Field(default=2.4, gt=0)
    qS_max: float = Field(default=0.052, gt=0)
    qP_max: float = Field(default=0.0075, gt=0)
    atol: float = Field(default=1e-6, gt=0)
    rtol: float = Field(default=1e-4, gt=0)
    max_steps: int = Field(default=4096, gt=0)
    state_scale: tuple[float, float, float, float] = (10., 30., 2., 4.)


class TrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    seed: int = 2023
    epochs: int = Field(default=120, ge=1)
    batch_size: int = Field(default=5, ge=1)
    patience: int = Field(default=25, ge=1)
    warmup_fraction: float = Field(default=0.2, ge=0, lt=1)
    min_delta: float = Field(default=1e-8, ge=0)


class LyoModelConfig(BaseModel):
    """Primary drying in SI units; defaults are the documented pilot example.

    Kc/Kp/Kd parameterize Kv(Pc); Rp0/A1/A2 parameterize Rp(Ld).
    Geometry and material properties are fixed, not neural fit parameters.
    """
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    Kc: float = Field(default=2.57, gt=0)  # W/(m² K)
    Kp: float = Field(default=2.33, gt=0)  # W/(m² K Pa)
    Kd: float = Field(default=0.03, gt=0)  # 1/Pa
    Rp0: float = Field(default=7000., gt=0)  # m/s
    A1: float = Field(default=2.77e8, gt=0)  # 1/s
    A2: float = Field(default=451., gt=0)  # 1/m
    product_area: float = Field(default=3.141592653589793 * .020**2 / 4, gt=0)
    vial_area: float = Field(default=3.141592653589793 * .022**2 / 4, gt=0)
    frozen_height: float = Field(default=.0086, gt=0)  # m, rounded example
    porosity: float = Field(default=.897, gt=0, lt=1)
    rho_ice: float = Field(default=918., gt=0)  # kg/m³
    k_ice: float = Field(default=2.4, gt=0)  # W/(m K), constant approximation
    latent_heat: float = Field(default=2.84e6, gt=0)  # J/kg, constant approximation
    depletion_fraction: float = Field(default=1e-3, gt=0, le=.01)
    completion_remaining_fraction: float = Field(default=1e-4, gt=0, lt=1)
    eps: float = Field(default=.1, ge=0, le=1)  # maximum log-coefficient correction
    atol: float = Field(default=1e-10, gt=0)  # dried-layer metres
    rtol: float = Field(default=1e-6, gt=0)
    max_steps: int = Field(default=4096, gt=0)


class LyoTrainConfig(TrainConfig):
    """Full-window fitting; warmup freezes the residual, not the time window."""
    physics_lr: float = Field(default=1e-4, gt=0)
    residual_lr: float = Field(default=1e-3, gt=0)
    temperature_scale_k: float = Field(default=1., gt=0)
    temperature_weight: float = Field(default=1., gt=0)
    duration_weight: float = Field(default=10., gt=0)
    state_weight: float = Field(default=1., ge=0)
    operating_weight: float = Field(default=10., gt=0)
    coverage_weight: float = Field(default=10., gt=0)
    residual_weight: float = Field(default=1e-3, ge=0)
