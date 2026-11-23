"""Learn kinetics inside an exact fed-batch mass-balance skeleton."""
import torch
from torch import nn
import torchode as to

from .config import DTYPE, ModelConfig


class BiologyCore(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        for name in ("mu_max", "Ks", "qS_max", "qP_max"):
            self.register_parameter(f"log_{name}", nn.Parameter(
                torch.tensor(getattr(config, name), dtype=DTYPE).log()))

    def constants(self) -> dict[str, torch.Tensor]:
        return {name.removeprefix("log_"): parameter.exp()
                for name, parameter in self.named_parameters()}

    def forward(self, y: torch.Tensor) -> torch.Tensor:
        s = y[..., 1].clamp(min=0.)
        c = self.constants()
        saturation = s / (c["Ks"] + s)
        return saturation.unsqueeze(-1) * torch.stack(
            [c["mu_max"], c["qS_max"], c["qP_max"]])


class HybridBioprocessUDE(nn.Module):
    def __init__(self, config: ModelConfig | None = None):
        super().__init__()
        self.config = config or ModelConfig()
        scale = torch.tensor(self.config.state_scale, dtype=DTYPE)
        if not torch.isfinite(scale).all() or (scale <= 0).any():
            raise ValueError("state_scale must contain four finite positive scales")
        self.register_buffer("state_scale", scale)
        self.biology_core = BiologyCore(self.config)
        self.residual_mlp = nn.Sequential(
            nn.Linear(3, 16, dtype=DTYPE), nn.Tanh(),
            nn.Linear(16, 16, dtype=DTYPE), nn.Tanh(), nn.Linear(16, 3, dtype=DTYPE))
        nn.init.zeros_(self.residual_mlp[-1].weight)
        nn.init.zeros_(self.residual_mlp[-1].bias)

    def rates(self, y: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        safe_y = y.clamp(min=0.)
        prior = self.biology_core(safe_y)
        normalized = safe_y[..., :3] / self.state_scale[:3]
        # Fixed one-row GEMMs avoid BLAS kernel changes when batch composition changes.
        flat = normalized.reshape(-1, 3)
        raw = torch.stack([self.residual_mlp(row) for row in flat]).reshape(prior.shape)
        residual = self.config.eps * torch.tanh(raw)
        return prior, residual

    def forward(self, t: torch.Tensor, y: torch.Tensor,
                args: torch.Tensor) -> torch.Tensor:
        prior, residual = self.rates(y)
        mu, qs, qp = (prior + residual).unbind(-1)
        x, s, p, v = y.clamp(min=0.).unbind(-1)
        f, s_in = args.unbind(-1)
        dilution = f / v.clamp(min=1e-12)
        return torch.stack((mu*x-dilution*x, -qs*x+dilution*(s_in-s),
                            qp*x-dilution*p, f), dim=-1)

    def ode_func(self, t: torch.Tensor, y: torch.Tensor,
                 args: torch.Tensor) -> torch.Tensor:
        return self(t, y, args)


class BioprocessSolver:
    """Independent adaptive ODEs, no shared error norm or timestamp resampling."""
    def __init__(self, model: HybridBioprocessUDE):
        self.model = model
        term = to.ODETerm(model.ode_func, with_args=True)
        step_method = to.Dopri5(term=term)
        controller = to.IntegralController(atol=model.config.atol,
                                          rtol=model.config.rtol, term=term)
        self.solver = to.AutoDiffAdjoint(step_method, controller,
                                        max_steps=model.config.max_steps).to(dtype=DTYPE)

    def solve(self, y0: torch.Tensor, t_eval: torch.Tensor,
              process_args: torch.Tensor) -> to.Solution:
        for name, tensor in (("y0", y0), ("t_eval", t_eval), ("process_args", process_args)):
            if tensor.dtype != DTYPE or not torch.isfinite(tensor).all():
                raise ValueError(f"{name} must be finite torch.float64")
        if any(p.dtype != DTYPE for p in self.model.parameters()):
            raise ValueError("All model parameters must be torch.float64")
        if y0.ndim != 2 or y0.shape[1] != 4 or t_eval.ndim != 2:
            raise ValueError("Expected y0 [batch,4] and t_eval [batch,time]")
        if process_args.shape != (len(y0), 2) or len(t_eval) != len(y0):
            raise ValueError("process_args must be [batch,2] and batch dimensions must agree")
        if t_eval.shape[1] < 2 or not (t_eval[:, 1:] > t_eval[:, :-1]).all():
            raise ValueError("Each batch requires at least two strictly increasing timestamps")
        if (y0 < 0).any() or (y0[:, 3] <= 0).any() or (process_args < 0).any():
            raise ValueError("Initial states/inputs must be nonnegative with positive volume")
        problem = to.InitialValueProblem(y0=y0, t_eval=t_eval)
        solution = self.solver.solve(problem, args=process_args)
        if (solution.status != 0).any() or not torch.isfinite(solution.ys).all():
            raise RuntimeError(f"ODE solve failed: status={solution.status.tolist()}")
        return solution
