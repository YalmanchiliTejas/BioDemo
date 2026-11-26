"""Differentiable primary-drying physics and a bounded inner residual UDE.

The original fermentation classes remain explicit legacy entry points for the
existing dataset/training/artifact tools. Use HybridLyophilizationUDE with
LyophilizationSolver for freeze drying; fermentation data are not interchangeable.
"""
import torch
from torch import nn
import torchode as to

from .config import DTYPE, LyoModelConfig, ModelConfig


def ice_pressure(temperature_k: torch.Tensor) -> torch.Tensor:
    """Murphy & Koop (2005), Eq. 7: equilibrium ice vapor pressure in Pa.

    Caller must supply kelvin within 110 < T <= 273.16 K.
    """
    return torch.exp(9.550426 - 5723.265 / temperature_k
                     + 3.53068 * temperature_k.log() - .00728332 * temperature_k)


def _lyo_fields(y: torch.Tensor, args: torch.Tensor, default_height: float):
    """Align per-vial resolved controls with states, including full trajectories."""
    if y.ndim == 3 and args.ndim == 2:
        args = args[:, None, :]
    height = args[..., 2] if args.shape[-1] == 3 else y.new_tensor(default_height)
    ld, ts, pc, height = torch.broadcast_tensors(y[..., 0], args[..., 0], args[..., 1], height)
    return torch.minimum(ld.clamp(min=0.), height), ts, pc, height


class LyoPhysicsCore(nn.Module):
    """Quasi-steady representative vial, with a moving sublimation front.

    State: [dried_layer_m]. Controls: [shelf_temperature_K, chamber_pressure_Pa].
    Kv = Kc + Kp Pc/(1 + Kd Pc); Rp = Rp0 + A1 Ld/(1 + A2 Ld).
    Frozen-layer conduction and latent heat couple heat and mass transfer.
    See docs/research/freeze-drying-sources.md for provenance and limitations.
    """
    def __init__(self, config: LyoModelConfig):
        super().__init__()
        self.config = config
        # Stable ordering is necessary for reproducible initialization/artifacts.
        for name in ("Kc", "Kp", "Kd", "Rp0", "A1", "A2"):
            self.register_parameter(f"log_{name}", nn.Parameter(
                torch.tensor(getattr(config, name), dtype=DTYPE).log()))

    def constants(self) -> dict[str, torch.Tensor]:
        """Expose positive, trainable physical coefficients in their SI units."""
        return {name.removeprefix("log_"): parameter.exp()
                for name, parameter in self.named_parameters()}

    def forward(self, y: torch.Tensor, args: torch.Tensor) -> torch.Tensor:
        """Return [Kv, Rp]; no biological rates or feed/dilution terms."""
        c = self.constants()
        ld, _, pc, _ = _lyo_fields(y, args, self.config.frozen_height)
        kv = c["Kc"] + c["Kp"] * pc / (1 + c["Kd"] * pc)
        rp = c["Rp0"] + c["A1"] * ld / (1 + c["A2"] * ld)
        return torch.stack((kv, rp), dim=-1)

    def balance(self, y: torch.Tensor, args: torch.Tensor,
                coefficients: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        """Detached root solve with a first-order implicit-function gradient.

        A smooth active-area approximation gates BOTH heat and mass transfer.
        At melt bounds, report an invalid balance and differentiable penalty
        instead of throwing during an optimizer step. Such rows are diagnostic
        continuations, not physical predictions. No post-drying temperature fit.
        """
        c = self.config
        kv, rp = (self(y, args) if coefficients is None else coefficients).unbind(-1)
        ld, ts, pc, height = _lyo_fields(y, args, c.frozen_height)
        frozen = height - ld
        gate = -torch.expm1(-frozen / (c.depletion_fraction * height))
        # Balance divided by gate, retaining a finite limit at zero remaining ice.
        conductance = c.vial_area * kv / (
            1 + c.vial_area * kv * gate * frozen / (c.product_area * c.k_ice))

        def equation(ti):
            pi = ice_pressure(ti)
            f = conductance*(ts-ti) - c.product_area*(pi-pc)/rp*c.latent_heat
            dpi = pi*(5723.265/ti.square() + 3.53068/ti - .00728332)
            slope = -conductance - c.product_area*dpi/rp*c.latent_heat
            return f, slope

        upper = ts.clamp(max=273.16)
        upper_f, _ = equation(upper)
        melting = upper_f > 0
        with torch.no_grad():
            root = upper.clone()
            # Newton from the warm side. No iterative autograd graph is retained.
            for _ in range(20):
                f, slope = equation(root)
                converged = (f.abs() <= 1e-12 + 1e-10*conductance.abs()) | melting
                update = torch.minimum((root-f/slope).clamp(min=110.0001), upper)
                root = torch.where(converged, root, update)
                if converged.all():
                    break
        f, slope = equation(root)
        # Forward value remains the detached root; backward is -F_theta/F_T.
        implicit = root - (f-f.detach()) / slope.detach()
        ti = torch.where(melting, upper, implicit)
        raw_mass = c.product_area*(ice_pressure(ti)-pc)/rp
        if (not torch.isfinite(ti).all() or not torch.isfinite(raw_mass).all()
                or (raw_mass < 0).any()
                or ((f.abs() > 1e-9 + 1e-7*(raw_mass*c.latent_heat).abs()) & ~melting).any()):
            raise RuntimeError("Primary-drying heat/mass balance has no converged sublimation solution")
        mass_rate = gate * raw_mass
        heat = mass_rate * c.latent_heat
        return {"interface_temperature_k": ti,
                "temperature_defined": (frozen / height > c.completion_remaining_fraction) & ~melting,
                "balance_valid": ~melting,
                "melt_excess_k": upper_f.clamp(min=0.) / conductance,
                "heat_balance_excess_w": upper_f.clamp(min=0.) * gate,
                "remaining_ice_fraction": frozen / height,
                "active_fraction": gate,
                "bottom_temperature_k": ti + heat * frozen / (c.product_area * c.k_ice),
                "mass_rate_kg_s": mass_rate, "heat_w": heat,
                "ungated_front_rate_m_s": raw_mass / (c.rho_ice * c.porosity * c.product_area),
                "front_rate_m_s": mass_rate / (c.rho_ice * c.porosity * c.product_area),
                "kv_w_m2_k": kv, "rp_m_s": rp}


class BiologyCore(nn.Module):
    """Legacy fermentation prior used by the existing fermentation benchmark."""
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


class HybridLyophilizationUDE(nn.Module):
    """Learn bounded Kv/Rp corrections while retaining both physical balances."""
    def __init__(self, config: LyoModelConfig | None = None):
        super().__init__()
        self.config = config or LyoModelConfig()
        self.physics_core = LyoPhysicsCore(self.config)
        self.residual_mlp = nn.Sequential(
            nn.Linear(3, 16, dtype=DTYPE), nn.Tanh(),
            nn.Linear(16, 16, dtype=DTYPE), nn.Tanh(), nn.Linear(16, 2, dtype=DTYPE))
        nn.init.zeros_(self.residual_mlp[-1].weight)
        nn.init.zeros_(self.residual_mlp[-1].bias)

    def conditions(self, y: torch.Tensor, args: torch.Tensor,
                   t: torch.Tensor | None = None) -> torch.Tensor:
        """Resolve constant/ramped shelf controls, in K/Pa/s/metres.

        Layouts: [Ts,Pc], [Ts,Pc,H], [Ts0,Pc,Ts1,ramp_s], or
        [Ts0,Pc,Ts1,ramp_s,H]. Ramps start at absolute t=0 seconds.
        Trajectory diagnostics insert the per-vial time axis automatically.
        """
        if args.shape[-1] not in (2, 3, 4, 5):
            raise ValueError("Expected 2/3 constant or 4/5 ramp controls")
        if y.ndim == 3 and args.ndim == 2:
            args = args[:, None, :]
        ts, pc = args[..., 0], args[..., 1]
        if args.shape[-1] >= 4:
            if t is None:
                raise ValueError("Ramped controls require timestamps in seconds")
            if y.ndim == 3 and t.ndim == 1 and len(t) == len(y):
                t = t[:, None]
            fraction = (t / args[..., 3]).clamp(0., 1.)
            ts = ts + (args[..., 2]-ts)*fraction
        height = args[..., -1] if args.shape[-1] in (3, 5) else y.new_tensor(self.config.frozen_height)
        _, ts, pc, height = torch.broadcast_tensors(y[..., 0], ts, pc, height)
        return torch.stack((ts, pc, height), dim=-1)

    def rates(self, y: torch.Tensor, args: torch.Tensor,
              t: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor]:
        """Return physical [Kv,Rp] and additive corrections in matching SI units.

        Relative correction factors are exp(eps*tanh(raw)); coefficients remain
        positive, regardless of neural weights. Inputs include known controls.
        """
        args = self.conditions(y, args, t)
        ld, ts, pc, height = _lyo_fields(y, args, self.config.frozen_height)
        features = torch.stack((ld / height,
                                (ts - 243.15) / 30., pc / 10.), dim=-1)
        prior = self.physics_core(y, args)
        raw = torch.stack([self.residual_mlp(row) for row in features.reshape(-1, 3)])
        log_factor = self.config.eps * torch.tanh(raw.reshape(prior.shape))
        return prior, prior * torch.expm1(log_factor)

    def diagnostics(self, y: torch.Tensor, args: torch.Tensor,
                    t: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        """Calculate temperatures, sublimation, and heat for reviewer inspection."""
        args = self.conditions(y, args, t)
        prior, correction = self.rates(y, args)
        return self.physics_core.balance(y, args, prior + correction)

    def forward(self, t: torch.Tensor, y: torch.Tensor, args: torch.Tensor) -> torch.Tensor:
        """dLd/dt = mdot/(rho_ice*porosity*Ap), with time in seconds.

        Controls may include a shelf ramp evaluated at t in seconds.
        """
        return self.diagnostics(y, args, t)["front_rate_m_s"].unsqueeze(-1)

    def ode_func(self, t: torch.Tensor, y: torch.Tensor, args: torch.Tensor) -> torch.Tensor:
        return self(t, y, args)


class LyophilizationSolution(to.Solution):
    """Physical trajectories plus a nonsaturating coordinate for duration loss."""
    def __init__(self, raw: to.Solution, ys: torch.Tensor, height: torch.Tensor,
                 depletion_fraction: float, completion_remaining_fraction: float,
                 initially_dry: torch.Tensor):
        super().__init__(raw.ts, ys, raw.stats, raw.status)
        self.drying_coordinate = raw.ys
        self.height = height
        self.depletion_fraction = depletion_fraction
        self.completion_remaining_fraction = completion_remaining_fraction
        self.initially_dry = initially_dry


class LyophilizationSolver:
    """Integrate z=log(expm1(remaining_height/depletion_width)).

    remaining_height = width*softplus(z) gives gate = sigmoid(z). Therefore
    dz/dt = -ungated_front_rate/width, removing the stiff endpoint time scale
    as well as the hard switch. Public ys remains dried thickness in metres.
    Local tolerance for z is min(atol_metres/width, rtol), an absolute bound
    in the dimensionless coordinate (not relative to its unbounded magnitude).
    """
    def __init__(self, model: HybridLyophilizationUDE):
        self.model = model
        term = to.ODETerm(self._coordinate_rhs, with_args=True)
        step_method = to.Dopri5(term=term)
        # Per-vial absolute tolerances are configured in solve, once H is known.
        controller = to.IntegralController(atol=model.config.atol,
                                          rtol=0., term=term)
        self.solver = to.AutoDiffAdjoint(step_method, controller,
                                        max_steps=model.config.max_steps).to(dtype=DTYPE)

    def _coordinate_rhs(self, t: torch.Tensor, z: torch.Tensor,
                        args: torch.Tensor) -> torch.Tensor:
        controls, initially_dry, height = args[:, :-2], args[:, -2].bool(), args[:, -1:]
        width = self.model.config.depletion_fraction * height
        y = height - width * torch.nn.functional.softplus(z)
        rate = self.model.diagnostics(y, controls, t)["ungated_front_rate_m_s"][:, None]
        return torch.where(initially_dry[:, None], 0., -rate / width)

    def solve(self, y0: torch.Tensor, t_eval: torch.Tensor,
              process_args: torch.Tensor) -> LyophilizationSolution:
        """Validate metres/seconds/kelvin/Pa and reject unsupported conditions."""
        for name, tensor in (("y0", y0), ("t_eval", t_eval), ("process_args", process_args)):
            if tensor.dtype != DTYPE or not torch.isfinite(tensor).all():
                raise ValueError(f"{name} must be finite torch.float64")
        parameters = list(self.model.parameters())
        if any(p.dtype != DTYPE or not torch.isfinite(p).all() for p in parameters):
            raise ValueError("All model parameters must be finite torch.float64")
        if any(t.device != y0.device for t in (t_eval, process_args, *parameters)):
            raise ValueError("Model, states, timestamps and controls must share a device")
        if y0.ndim != 2 or y0.shape[0] == 0 or y0.shape[1] != 1 or t_eval.ndim != 2:
            raise ValueError("Expected nonempty y0 [batch,1] and t_eval [batch,time]")
        if (process_args.ndim != 2 or process_args.shape[0] != len(y0)
                or process_args.shape[1] not in (2, 3, 4, 5) or len(t_eval) != len(y0)):
            raise ValueError("process_args must be [batch,2/3/4/5] and batch dimensions must agree")
        if (t_eval.shape[1] < 2 or (t_eval < 0).any()
                or not (t_eval[:, 1:] > t_eval[:, :-1]).all()):
            raise ValueError("Each batch requires at least two nonnegative strictly increasing timestamps")
        if process_args.shape[-1] >= 4 and (process_args[:, 3] <= 0).any():
            raise ValueError("Shelf ramp duration must be positive seconds")
        height = self.model.conditions(y0, process_args, t_eval[:, 0])[:, 2:3]
        if (height <= 0).any():
            raise ValueError("Per-vial frozen_height must be positive metres")
        if (y0 < 0).any() or (y0 > height).any():
            raise ValueError("Initial dried layer must lie between zero and frozen_height in metres")
        start = self.model.conditions(y0, process_args, t_eval[:, 0])
        end = self.model.conditions(y0, process_args, t_eval[:, -1])
        ts = torch.stack((start[:, 0], end[:, 0]), dim=-1)
        pc = process_args[:, 1:2]
        if (ts < 208.15).any() or (ts > 293.15).any() or (pc < .5).any() or (pc > 100).any():
            raise ValueError("Primary-drying controls require shelf 208.15..293.15 K and pressure 0.5..100 Pa")
        if (ice_pressure(ts.clamp(max=273.16)) <= pc).any():
            raise ValueError("No sublimation driving force: shelf temperature is below the frost point")
        width = self.model.config.depletion_fraction * height
        initially_dry = (y0 == height).squeeze(-1)
        ratio = ((height-y0)/width).clamp(min=1e-12)
        z0 = ratio + torch.log(-torch.expm1(-ratio))
        args = torch.cat((process_args, initially_dry[:, None].to(DTYPE), height), dim=-1)
        # |d remaining/dz| <= width. Per-vial tolerances preserve independence
        # of batch composition; a relative tolerance on unbounded z would loosen
        # metre accuracy at the start and long after completion.
        self.solver.step_size_controller.atol = torch.minimum(
            self.model.config.atol / width.detach(), width.new_tensor(self.model.config.rtol))
        solution = self.solver.solve(to.InitialValueProblem(y0=z0, t_eval=t_eval), args=args)
        if (solution.status != 0).any() or not torch.isfinite(solution.ys).all():
            raise RuntimeError(f"ODE solve failed: status={solution.status.tolist()}")
        ys = height[:, None] - width[:, None]*torch.nn.functional.softplus(solution.ys)
        ys = torch.where(initially_dry[:, None, None], height[:, None], ys)
        return LyophilizationSolution(solution, ys, height, self.model.config.depletion_fraction,
                                      self.model.config.completion_remaining_fraction, initially_dry)
