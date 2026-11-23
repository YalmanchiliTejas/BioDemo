"""Missing assays never participate in subtraction or gradient computation."""
import torch

from .config import DTYPE
from .synthetic import Batch


def fit_state_scale(batches: tuple[Batch, ...]) -> torch.Tensor:
    scales = []
    for assay in range(4):
        values = torch.cat([b.observations[:, assay][b.obs_mask[:, assay]] for b in batches])
        if not len(values) or not torch.isfinite(values).all():
            raise ValueError("Training data must have finite observed values in every assay")
        scales.append(values.abs().max().clamp(min=1e-6))
    return torch.stack(scales).to(DTYPE)


def masked_trajectory_mse(prediction: torch.Tensor, observed: torch.Tensor,
                          mask: torch.Tensor, scale: torch.Tensor) -> torch.Tensor:
    if prediction.shape != observed.shape or mask.shape != observed.shape or mask.dtype != torch.bool:
        raise ValueError("Prediction/observation/mask shapes must match; mask must be boolean")
    if not mask.any():
        raise ValueError("No observed assays in loss window")
    if not torch.isfinite(observed[mask]).all():
        raise ValueError("An assay marked observed is nonfinite")
    # Select *before* subtracting: NaN * 0 after subtraction is not masking.
    expanded_scale = scale.expand_as(prediction)
    return (((prediction[mask] - observed[mask]) / expanded_scale[mask]) ** 2).mean()


def physics_hijack_ratio(prior: torch.Tensor, residual: torch.Tensor) -> torch.Tensor:
    return residual.abs().mean() / (prior.abs() + 1e-8).mean()
