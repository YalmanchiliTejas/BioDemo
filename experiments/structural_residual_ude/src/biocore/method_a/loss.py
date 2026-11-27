"""Primary-drying objectives and explicitly retained legacy loss utilities."""
import torch

from .config import DTYPE, LyoTrainConfig
from .synthetic import Batch
from .model import HybridLyophilizationUDE, LyophilizationSolution
from .lyo_data import LyoBatch


LOSS_COMPONENTS = ("temperature", "state", "duration", "operating", "coverage", "residual")


def weighted_loss_components(terms, config: LyoTrainConfig):
    """Return each term's contribution to the total objective."""
    return {name: terms[name]*getattr(config, f"{name}_weight") for name in LOSS_COMPONENTS}


def fit_state_scale(batches: tuple[Batch, ...]) -> torch.Tensor:
    """Legacy fermentation-only scaling; not used by lyophilization fitting."""
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
    """Legacy biological-rate diagnostic; lyo compares Kv/Rp relatively instead."""
    return residual.abs().mean() / (prior.abs() + 1e-8).mean()


def thermocouple_mse(diagnostics: dict[str, torch.Tensor], observed: torch.Tensor,
                     mask: torch.Tensor | None = None) -> torch.Tensor:
    """Kelvin² loss on observed, physically valid primary-drying points only.

    Completed/depleted or melt-bound rows never enter the subtraction. No
    observations remaining returns a differentiable zero; use duration loss
    as well, so early predicted completion cannot win by masking all points.
    """
    predicted = diagnostics["bottom_temperature_k"]
    if observed.shape != predicted.shape or (mask is not None and mask.shape != observed.shape):
        raise ValueError("Thermocouple observations/mask must match diagnostic temperatures")
    if mask is not None and mask.dtype != torch.bool:
        raise ValueError("Thermocouple mask must be boolean")
    valid = diagnostics["temperature_defined"] & torch.isfinite(observed)
    if mask is not None:
        valid = valid & mask
    return (predicted[valid] - observed[valid]).square().sum() / valid.sum().clamp(min=1)


def drying_duration_loss(solution: LyophilizationSolution,
                         observed_duration_s: torch.Tensor,
                         remaining_fraction: float | None = None,
                         mask: torch.Tensor | None = None) -> torch.Tensor:
    """Supervise endpoint time using the nonsaturating drying coordinate.

    Match z at each observed endpoint to the operational remaining-ice
    threshold, using piecewise-linear interpolation between saved times. The
    resulting dimensionless loss remains differentiable when physical ys has
    rounded to full dryness. Sample near endpoints for accurate interpolation.
    Exact zero ice occurs only asymptotically; specify the endpoint definition.
    """
    if remaining_fraction is None:
        remaining_fraction = solution.completion_remaining_fraction
    if not 0 < remaining_fraction < 1:
        raise ValueError("remaining_fraction must lie strictly between zero and one")
    if (observed_duration_s.shape != solution.ts.shape[:1]
            or observed_duration_s.dtype != DTYPE
            or observed_duration_s.device != solution.ts.device):
        raise ValueError("Observed durations must be finite float64 seconds, one per vial on the solve device")
    if mask is None:
        mask = torch.ones_like(observed_duration_s, dtype=torch.bool)
    if mask.shape != observed_duration_s.shape or mask.dtype != torch.bool:
        raise ValueError("Duration mask must be boolean [batch]")
    if not torch.isfinite(observed_duration_s[mask]).all():
        raise ValueError("Observed durations must be finite seconds")
    if not mask.any():
        return solution.drying_coordinate.sum()*0.
    if solution.initially_dry[mask].any():
        raise ValueError("Duration supervision requires initially ice-containing vials")
    times, observed = solution.ts[mask], observed_duration_s[mask]
    if ((observed < times[:, 0]) | (observed > times[:, -1])).any():
        raise ValueError("Observed durations must be within the solved timestamp range")
    index = torch.searchsorted(times.contiguous(), observed[:, None].contiguous(), right=True)
    index = index.clamp(1, times.shape[1]-1)
    left = times.gather(1, index-1).squeeze(1)
    right = times.gather(1, index).squeeze(1)
    z = solution.drying_coordinate[mask, :, 0]
    z_left, z_right = z.gather(1, index-1).squeeze(1), z.gather(1, index).squeeze(1)
    fraction = (observed-left)/(right-left)
    z_observed = z_left + fraction*(z_right-z_left)
    ratio = z.new_tensor(remaining_fraction/solution.depletion_fraction)
    z_threshold = ratio + torch.log(-torch.expm1(-ratio))
    return ((z_observed-z_threshold)*solution.depletion_fraction).square().mean()


def lyophilization_loss(model: HybridLyophilizationUDE, solution: LyophilizationSolution,
                        batches: list[LyoBatch], config: LyoTrainConfig) -> dict[str, torch.Tensor]:
    """Equal-vial objective; missing channels require no fabricated scales.

    Physical temperatures use an explicit kelvin error scale, layer observations
    use each vial's fill height, and endpoints use the nonsaturating coordinate.
    Coverage penalties prevent early predicted depletion hiding known primary
    observations. Ground-truth trajectories and fault labels are never read.
    """
    args = torch.stack([b.process_args for b in batches])
    diagnostics = model.diagnostics(solution.ys, args, solution.ts)
    prior, correction = model.rates(solution.ys, args, solution.ts)
    ratio = solution.ys.new_tensor(model.config.completion_remaining_fraction / model.config.depletion_fraction)
    threshold = ratio + torch.log(-torch.expm1(-ratio))
    terms = {name: [] for name in LOSS_COMPONENTS}
    for i, batch in enumerate(batches):
        d = {key: value[i] for key, value in diagnostics.items()}
        temperature_mask = batch.obs_mask[:, 0] & batch.primary_mask
        terms["temperature"].append(thermocouple_mse(d, batch.observations[:, 0], temperature_mask)
                                     / config.temperature_scale_k**2)
        state_mask = batch.obs_mask[:, 1]
        state_error = (solution.ys[i, :, 0][state_mask]-batch.observations[:, 1][state_mask])/solution.height[i, 0]
        terms["state"].append(state_error.square().sum()/state_mask.sum().clamp(min=1))
        duration_mask = torch.zeros(len(batches), dtype=torch.bool)
        duration_mask[i] = batch.duration_s is not None
        durations = solution.ts[:, 0].clone()
        if batch.duration_s is not None:
            durations[i] = batch.duration_s
        terms["duration"].append(drying_duration_loss(solution, durations, mask=duration_mask))
        terms["operating"].append((d["melt_excess_k"].square()*d["active_fraction"]).mean())
        premature = (threshold-solution.drying_coordinate[i, :, 0][temperature_mask]).clamp(min=0.)
        terms["coverage"].append((premature*solution.depletion_fraction).square().sum()
                                  / temperature_mask.sum().clamp(min=1))
        # A relative correction per coefficient avoids mixing Kv and Rp units.
        terms["residual"].append((correction[i]/prior[i]).square().mean())
    result = {name: torch.stack(values).mean() for name, values in terms.items()}
    result["total"] = sum(weighted_loss_components(result, config).values())
    return result
