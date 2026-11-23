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
