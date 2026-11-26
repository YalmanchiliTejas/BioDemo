"""Independent balance checks for the differentiable primary-drying model."""
import math

import pytest
import torch

from biocore.method_a.config import DTYPE, LyoModelConfig, seed_everything
from biocore.method_a.loss import drying_duration_loss, thermocouple_mse
from biocore.method_a.model import (
    HybridLyophilizationUDE, LyophilizationSolver, ice_pressure,
)


def inputs():
    return (torch.tensor([[0.], [.001]], dtype=DTYPE),
            torch.tensor([[0., 1800., 7200.], [0., 2200., 6800.]], dtype=DTYPE),
            torch.tensor([[249.15, 8.], [245.15, 10.]], dtype=DTYPE))


def reference_rate(ld, ts, pc, c):
    """Scalar bisection, independent of the model's Newton implementation."""
    kv = c.Kc + c.Kp * pc / (1 + c.Kd * pc)
    rp = c.Rp0 + c.A1 * ld / (1 + c.A2 * ld)
    g = 1 / (1 / (c.vial_area * kv) + (c.frozen_height-ld) / (c.product_area*c.k_ice))
    low, high = 173.15, min(ts, 273.16)
    for _ in range(80):
        mid = (low + high) / 2
        pressure = math.exp(9.550426 - 5723.265/mid + 3.53068*math.log(mid) - .00728332*mid)
        mdot = c.product_area*(pressure-pc)/rp
        if g*(ts-mid) > mdot*c.latent_heat:
            low = mid
        else:
            high = mid
    return mdot / (c.rho_ice*c.porosity*c.product_area), mid


def test_pressure_and_zero_initialized_physics():
    seed_everything(2023)
    model = HybridLyophilizationUDE()
    y, _, args = inputs()
    assert float(ice_pressure(torch.tensor(273.15, dtype=DTYPE))) == pytest.approx(611.1536, rel=1e-6)
    prior, correction = model.rates(y, args)
    assert torch.equal(correction, torch.zeros_like(correction))
    assert list(model.physics_core.constants()) == ["Kc", "Kp", "Kd", "Rp0", "A1", "A2"]
    actual = model.diagnostics(y, args)
    for i in range(2):
        rate, temperature = reference_rate(float(y[i, 0]), *args[i].tolist(), model.config)
        assert float(actual["front_rate_m_s"][i].detach()) == pytest.approx(rate, rel=1e-10)
        assert float(actual["interface_temperature_k"][i].detach()) == pytest.approx(temperature, abs=1e-9)
    assert (prior > 0).all()


def test_neural_correction_preserves_energy_mass_and_positive_coefficients():
    model = HybridLyophilizationUDE()
    with torch.no_grad():
        model.residual_mlp[-1].bias.copy_(torch.tensor([100., -100.], dtype=DTYPE))
    y, _, args = inputs()
    prior, correction = model.rates(y, args)
    factors = (prior+correction)/prior
    assert (factors >= math.exp(-model.config.eps)-1e-14).all()
    assert (factors <= math.exp(model.config.eps)+1e-14).all()
    d = model.diagnostics(y, args)
    c = model.config
    assert torch.allclose(d["heat_w"], c.vial_area*d["kv_w_m2_k"]*(args[:, 0]-d["bottom_temperature_k"]), atol=1e-12)
    assert torch.allclose(d["heat_w"], d["mass_rate_kg_s"]*c.latent_heat, atol=1e-12)
    assert torch.allclose(d["front_rate_m_s"]*c.rho_ice*c.porosity*c.product_area, d["mass_rate_kg_s"], atol=1e-18)


def test_trajectory_matches_independent_rk4():
    model = HybridLyophilizationUDE()
    y, times, args = inputs()
    with torch.no_grad():
        actual = LyophilizationSolver(model).solve(y, times, args).ys
    for i in range(2):
        ld, previous = float(y[i, 0]), 0.
        for j, target in enumerate(times[i].tolist()):
            while previous < target:
                h = min(30., target-previous)
                rhs = lambda l: reference_rate(l, *args[i].tolist(), model.config)[0]
                k1 = rhs(ld)
                k2 = rhs(ld+h*k1/2)
                k3 = rhs(ld+h*k2/2)
                k4 = rhs(ld+h*k3)
                ld += h*(k1+2*k2+2*k3+k4)/6
                previous += h
            assert float(actual[i, j, 0]) == pytest.approx(ld, abs=2e-9)


def test_solver_backward_matches_finite_difference():
    seed_everything(2023)
    model = HybridLyophilizationUDE()
    y, times, args = inputs()
    solver = LyophilizationSolver(model)
    loss = solver.solve(y, times, args).ys[:, -1].sum()
    loss.backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
    p = model.physics_core.log_Kc
    analytical = float(p.grad)
    delta = 1e-4
    with torch.no_grad():
        original = p.clone()
        p.copy_(original+delta)
        plus = solver.solve(y, times, args).ys[:, -1].sum()
        p.copy_(original-delta)
        minus = solver.solve(y, times, args).ys[:, -1].sum()
        p.copy_(original)
    assert analytical == pytest.approx(float((plus-minus)/(2*delta)), rel=1e-3)


def test_completion_and_batch_independence():
    seed_everything(2023)
    model = HybridLyophilizationUDE()
    with torch.no_grad():
        model.residual_mlp[-1].weight.normal_(0, .002)
        model.residual_mlp[-1].bias.fill_(.01)
        y, times, args = inputs()
        solver = LyophilizationSolver(model)
        alone = solver.solve(y[:1], times[:1], args[:1]).ys[0]
        paired = solver.solve(y, times, args).ys[0]
        reverse = solver.solve(y.flip(0), times.flip(0), args.flip(0)).ys[1]
        assert torch.equal(alone, paired)
        assert torch.equal(alone, reverse)
        result = solver.solve(y[:1], torch.tensor([[0., 250000., 300000.]], dtype=DTYPE), args[:1])
        assert torch.equal(result.ys[0, 1:], torch.full((2, 1), model.config.frozen_height, dtype=DTYPE))
        d = model.diagnostics(result.ys[:, -1], args[:1])
        assert not d["temperature_defined"].any()
        assert torch.equal(d["mass_rate_kg_s"], torch.zeros(1, dtype=DTYPE))
        assert torch.equal(d["heat_w"], torch.zeros(1, dtype=DTYPE))
        dry = torch.full_like(y, model.config.frozen_height)
        assert torch.equal(solver.solve(dry, times, args).ys, dry[:, None].expand(-1, 3, -1))


@pytest.mark.parametrize("change,match", [
    ("dtype", "float64"), ("shape", "batch,1"), ("time", "increasing"),
    ("height", "dried layer"), ("celsius", "controls"),
    ("pressure", "controls"), ("frost", "driving force"),
])
def test_invalid_inputs(change, match):
    y, times, args = inputs()
    if change == "dtype":
        y = y.float()
    elif change == "shape":
        y = y.expand(-1, 4)
    elif change == "time":
        times = times.flip(1)
    elif change == "height":
        y[0, 0] = .1
    elif change == "celsius":
        args[0, 0] = -24.
    elif change == "pressure":
        args[0, 1] = -1.
    elif change == "frost":
        args[0] = torch.tensor([208.15, 100.], dtype=DTYPE)
    with pytest.raises(ValueError, match=match):
        LyophilizationSolver(HybridLyophilizationUDE()).solve(y, times, args)


def test_configuration_and_solver_failures():
    with pytest.raises(ValueError):
        LyoModelConfig(Kc=float("nan"))
    with pytest.raises(ValueError):
        LyoModelConfig(Rp0=0.)
    y, times, args = inputs()
    with pytest.raises(RuntimeError, match="ODE solve failed"):
        LyophilizationSolver(HybridLyophilizationUDE(LyoModelConfig(max_steps=1))).solve(y, times, args)


def test_diagnostics_broadcasts_full_trajectory_and_preserves_vial_axis():
    model = HybridLyophilizationUDE()
    y, times, args = inputs()
    result = LyophilizationSolver(model).solve(y, times, args)
    actual = model.diagnostics(result.ys, args)
    explicit = model.diagnostics(result.ys, args[:, None, :])
    assert actual["bottom_temperature_k"].shape == times.shape
    for key in actual:
        assert torch.equal(actual[key], explicit[key])
    # Also guard the silent wrong-axis case where batch == time.
    for i in range(2):
        alone = model.diagnostics(result.ys[i, :2], args[i])
        paired = model.diagnostics(result.ys[:, :2], args)
        assert torch.allclose(alone["mass_rate_kg_s"], paired["mass_rate_kg_s"][i], atol=1e-20)


def test_completion_field_is_continuous_and_preserves_gated_heat_balance():
    model = HybridLyophilizationUDE()
    h = model.config.frozen_height
    args = torch.tensor([[249.15, 8.]]*3, dtype=DTYPE)
    y = torch.tensor([[h-1e-12], [h], [h-h*1e-3]], dtype=DTYPE, requires_grad=True)
    d = model.diagnostics(y, args)
    assert abs(float((d["front_rate_m_s"][0]-d["front_rate_m_s"][1]).detach())) < 1e-12
    assert 0 < float(d["active_fraction"][2].detach()) < 1
    shelf_heat = model.config.vial_area*d["kv_w_m2_k"]*d["active_fraction"]*(args[:, 0]-d["bottom_temperature_k"])
    assert torch.allclose(d["heat_w"], shelf_heat, atol=1e-12)
    d["front_rate_m_s"].sum().backward()
    assert torch.isfinite(y.grad).all()


def test_long_post_completion_solve_and_duration_gradient():
    model = HybridLyophilizationUDE(LyoModelConfig(max_steps=256))
    y, _, args = inputs()
    times = torch.tensor([[0., 150000., 300000., 1e7]], dtype=DTYPE)
    solution = LyophilizationSolver(model).solve(y[:1], times, args[:1])
    assert int(solution.stats["n_steps"][0]) < 256
    assert float(solution.ys[0, -1, 0].detach()) == model.config.frozen_height
    # Duration supervision retains a signal even when reported thickness saturates.
    loss = drying_duration_loss(solution, torch.tensor([300000.], dtype=DTYPE))
    loss.backward()
    assert torch.isfinite(model.physics_core.log_Kc.grad)
    assert abs(float(model.physics_core.log_Kc.grad)) > 1e-8


def test_ramp_controls_and_mixed_fill_height_replay():
    seed_everything(2023)
    model = HybridLyophilizationUDE()
    y = torch.zeros((2, 1), dtype=DTYPE)
    args = torch.tensor([[233.15, 8., 258.15, 3600., .006],
                         [238.15, 10., 253.15, 5400., .009]], dtype=DTYPE)
    times = torch.tensor([[0., 1800., 3600., 7200.], [0., 1800., 5400., 7200.]], dtype=DTYPE)
    with pytest.raises(ValueError, match="timestamps"):
        model.diagnostics(y, args)
    conditions = model.conditions(y[:, None].expand(-1, 4, -1), args, times)
    assert torch.allclose(conditions[0, :, 0], torch.tensor([233.15, 245.65, 258.15, 258.15], dtype=DTYPE), atol=1e-12, rtol=0)
    solver = LyophilizationSolver(model)
    with torch.no_grad():
        solution = solver.solve(y, times, args)
        alone = solver.solve(y[:1], times[:1], args[:1])
        assert torch.equal(solution.ys[0], alone.ys[0])
        d = model.diagnostics(solution.ys, args, solution.ts)
        assert d["bottom_temperature_k"].shape == times.shape
        assert (solution.ys[:, -1, 0] > 0).all()
        assert (solution.ys[:, -1, 0] < args[:, -1]).all()
        held_cold = torch.stack((args[:, 0], args[:, 1], args[:, -1]), dim=-1)
        cold_solution = solver.solve(y, times, held_cold)
        assert (solution.ys[:, -1, 0] > cold_solution.ys[:, -1, 0]).all()


def test_ramp_trajectory_matches_independent_time_dependent_rk4():
    model = HybridLyophilizationUDE()
    args = torch.tensor([[233.15, 8., 258.15, 3600.]], dtype=DTYPE)
    times = torch.tensor([[0., 1800., 3600., 7200.]], dtype=DTYPE)
    with torch.no_grad():
        actual = LyophilizationSolver(model).solve(torch.zeros((1, 1), dtype=DTYPE), times, args).ys
    ld, time = 0., 0.
    for j, target in enumerate(times[0].tolist()):
        def rhs(t, l):
            ts = 233.15 + 25.*min(1., t/3600.)
            return reference_rate(l, ts, 8., model.config)[0]
        while time < target:
            h = min(10., target-time)
            k1 = rhs(time, ld)
            k2 = rhs(time+h/2, ld+h*k1/2)
            k3 = rhs(time+h/2, ld+h*k2/2)
            k4 = rhs(time+h, ld+h*k3)
            ld += h*(k1+2*k2+2*k3+k4)/6
            time += h
        assert float(actual[0, j, 0]) == pytest.approx(ld, abs=2e-9)


def test_implicit_temperature_gradient_for_states_and_controls():
    model = HybridLyophilizationUDE()
    y = torch.tensor([[.002]], dtype=DTYPE, requires_grad=True)
    args = torch.tensor([[249.15, 8., .006]], dtype=DTYPE, requires_grad=True)
    assert torch.autograd.gradcheck(
        lambda state, control: model.diagnostics(state, control)["interface_temperature_k"],
        (y, args), eps=1e-6, atol=1e-4, rtol=1e-3)


def test_warm_shelf_melt_boundary_is_flagged_with_recovery_gradient():
    model = HybridLyophilizationUDE(LyoModelConfig(Kc=1e4, Rp0=1e12))
    y = torch.zeros((1, 1), dtype=DTYPE)
    args = torch.tensor([[293.15, 8.]], dtype=DTYPE)
    d = model.diagnostics(y, args)
    assert not d["balance_valid"].any()
    assert not d["temperature_defined"].any()
    assert float(d["interface_temperature_k"][0].detach()) == 273.16
    assert (d["melt_excess_k"] > 0).all()
    # An optimizer can respond to this violation instead of losing the whole run.
    d["melt_excess_k"].square().mean().backward()
    assert torch.isfinite(model.physics_core.log_Rp0.grad)
    assert float(model.physics_core.log_Rp0.grad) > 0
    with torch.no_grad():
        solution = LyophilizationSolver(model).solve(y, torch.tensor([[0., 600.]], dtype=DTYPE), args)
        assert torch.isfinite(solution.ys).all()


def test_thermocouple_loss_masks_completion_melt_and_missing_values():
    predicted = torch.tensor([[240., 241., 250., 260.]], dtype=DTYPE, requires_grad=True)
    d = {"bottom_temperature_k": predicted,
         "temperature_defined": torch.tensor([[True, True, False, False]])}
    observations = torch.tensor([[241., float("nan"), 270., 280.]], dtype=DTYPE)
    loss = thermocouple_mse(d, observations)
    assert float(loss.detach()) == 1.
    loss.backward()
    assert torch.equal(predicted.grad, torch.tensor([[-2., 0., 0., 0.]], dtype=DTYPE))
    empty = thermocouple_mse(d, observations, torch.zeros_like(observations, dtype=torch.bool))
    assert float(empty.detach()) == 0.
    assert empty.requires_grad


@pytest.mark.parametrize("args", [
    [[233.15, 8., 258.15, 0.]], [[249.15, 8., -.001]],
    [[233.15, 8., 300., 3600.]], [[233.15, 8., 258.15, -10., .006]],
])
def test_ramp_and_height_validation(args):
    with pytest.raises(ValueError):
        LyophilizationSolver(HybridLyophilizationUDE()).solve(
            torch.zeros((1, 1), dtype=DTYPE),
            torch.tensor([[0., 7200.]], dtype=DTYPE), torch.tensor(args, dtype=DTYPE))
