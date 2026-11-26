from dataclasses import replace

import pytest
import torch

from biocore.method_a.artifact import load_artifact, save_artifact
from biocore.method_a.config import DTYPE, LyoTrainConfig, ModelConfig, seed_everything
from biocore.method_a.evaluate import auroc, evaluate
from biocore.method_a.loss import fit_state_scale, masked_trajectory_mse
from biocore.method_a.model import BioprocessSolver, HybridBioprocessUDE
from biocore.method_a.synthetic import make_dataset
from biocore.method_a.lyo_data import make_dataset as make_lyo_dataset, load_dataset
from biocore.method_a.model import HybridLyophilizationUDE, LyophilizationSolver
from biocore.method_a.train import train, validate_splits


@pytest.fixture(autouse=True)
def deterministic():
    seed_everything(2023)


@pytest.fixture(scope="module")
def data():
    return make_dataset(2023)


def inputs():
    y = torch.tensor([[2., 20., 0., 2.], [1.7, 24., .1, 2.2]], dtype=DTYPE)
    t = torch.tensor([[0., 11.7, 35.1, 61.2, 120.], [0., 20.4, 55., 70.3, 120.]], dtype=DTYPE)
    a = torch.tensor([[.015, 200.], [.019, 230.]], dtype=DTYPE)
    return y, t, a


def test_epoch_zero_pure_physics():
    model = HybridBioprocessUDE()
    y, t, args = inputs()
    raw = model.residual_mlp(y[:, :3]/model.state_scale[:3])
    prior, residual = model.rates(y)
    assert torch.equal(raw, torch.zeros_like(raw))
    assert torch.equal(residual, torch.zeros_like(residual))
    mu, qs, qp = prior.unbind(-1)
    x, s, p, v = y.unbind(-1)
    f, s_in = args.unbind(-1)
    expected = torch.stack((mu*x-f/v*x, -qs*x+f/v*(s_in-s), qp*x-f/v*p, f), -1)
    assert torch.equal(model(t[:, 0], y, args), expected)
    assert all(p.dtype == DTYPE for p in model.parameters())


def test_zero_biomass_invariance():
    model = HybridBioprocessUDE()
    # Nonzero neural rates must still be multiplied by exactly zero biomass.
    with torch.no_grad():
        model.residual_mlp[-1].bias.fill_(.1)
    y, t, a = inputs()
    y[:, 0] = 0.
    result = BioprocessSolver(model).solve(y, t, a)
    assert torch.equal(result.ys[..., 0], torch.zeros_like(result.ys[..., 0]))
    assert torch.allclose(result.ys[..., 3], y[:, 3, None]+a[:, 0, None]*t, atol=1e-12, rtol=0)


def test_frozen_gmp_replay_bitwise_independent_of_batch(tmp_path):
    model = HybridBioprocessUDE()
    # Exercise nonzero residuals, not just the trivially zero-initialized MLP.
    with torch.no_grad():
        model.residual_mlp[-1].weight.normal_(0, .002)
        model.residual_mlp[-1].bias.normal_(0, .001)
    path = tmp_path / "model.safetensors"
    save_artifact(model, path, {"purpose": "replay test"})
    frozen, _ = load_artifact(path)
    assert not any(p.requires_grad for p in frozen.parameters())
    solver = BioprocessSolver(frozen)
    y, t, a = inputs()
    with torch.no_grad():
        alone = solver.solve(y[:1], t[:1], a[:1]).ys[0]
        paired = solver.solve(y, t, a).ys[0]
        reversed_batch = solver.solve(y.flip(0), t.flip(0), a.flip(0)).ys[1]
    assert torch.equal(alone, paired)
    assert torch.equal(alone, reversed_batch)


def test_masked_nan_backward():
    prediction = torch.ones(2, 4, dtype=DTYPE, requires_grad=True)
    observed = torch.tensor([[1., float("nan"), 2., 4.],
                             [float("nan"), 3., 2., 4.]], dtype=DTYPE, requires_grad=True)
    mask = torch.isfinite(observed)
    loss = masked_trajectory_mse(prediction, observed, mask, torch.ones(4, dtype=DTYPE))
    loss.backward()
    assert torch.isfinite(prediction.grad).all() and torch.isfinite(observed.grad).all()
    assert torch.equal(prediction.grad[~mask], torch.zeros_like(prediction.grad[~mask]))
    assert torch.equal(observed.grad[~mask], torch.zeros_like(observed.grad[~mask]))
    # Also exercise the ODE-to-parameter backward path with missing assays.
    model = HybridBioprocessUDE()
    y, t, a = inputs()
    pred = BioprocessSolver(model).solve(y, t, a).ys
    obs = pred.detach().clone() + .01
    obs[:, 1, 1] = float("nan")
    masked_trajectory_mse(pred, obs, torch.isfinite(obs), model.state_scale).backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


def test_synthetic_splits_masks_and_train_only_scaling(data):
    # The converted trainer must reject legacy fermentation data explicitly.
    with pytest.raises(ValueError, match="lyophilization"):
        validate_splits(data)
    assert [len(getattr(data, name)) for name in ("train", "val", "test", "faults")] == [15, 10, 15, 10]
    for group in (data.train, data.val, data.test, data.faults):
        for batch in group:
            assert 8 <= len(batch.times) <= 10
            assert (batch.times[1:] > batch.times[:-1]).all()
            assert batch.times.dtype == batch.observations.dtype == DTYPE
            assert torch.equal(torch.isnan(batch.observations), ~batch.obs_mask)
    scale = fit_state_scale(data.train)
    changed = replace(data, test=tuple(replace(b, observations=b.observations*1e6) for b in data.test))
    assert torch.equal(scale, fit_state_scale(changed.train))
    repeated = make_dataset(2023)
    assert repeated.split_ids() == data.split_ids()
    assert torch.equal(repeated.train[0].truth, data.train[0].truth)


@pytest.mark.parametrize("target", ["weights", "config"])
def test_hash_tamper_detection(tmp_path, target):
    path = tmp_path / "model.safetensors"
    save_artifact(HybridBioprocessUDE(), path, {})
    candidate = path if target == "weights" else path.with_suffix(".json")
    with candidate.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        load_artifact(path)


def test_solver_input_validation_and_clamping():
    model = HybridBioprocessUDE()
    y, t, a = inputs()
    assert torch.isfinite(model(t[:, 0], -torch.ones_like(y), a)).all()
    with pytest.raises(ValueError, match="float64"):
        BioprocessSolver(model).solve(y.float(), t, a)
    with pytest.raises(ValueError, match="increasing"):
        BioprocessSolver(model).solve(y, t.flip(1), a)
    solver = BioprocessSolver(HybridBioprocessUDE(ModelConfig(max_steps=1)))
    with pytest.raises(RuntimeError, match="ODE solve failed"):
        solver.solve(y, t, a)


def test_auroc_ties():
    assert auroc([0., 0.], [0., 0.]) == .5
    assert auroc([0., 1.], [2., 3.]) == 1.


def test_training_artifact_evaluation_and_repeatability(tmp_path):
    small = make_lyo_dataset(2023, (2, 1, 1, 1))
    config = LyoTrainConfig(epochs=2, warmup_fraction=.5)
    path_a = train(small, tmp_path / "a", config)
    path_b = train(small, tmp_path / "b", config)
    model_a, doc_a = load_artifact(path_a)
    model_b, doc_b = load_artifact(path_b)
    assert isinstance(model_a, HybridLyophilizationUDE)
    assert all(torch.equal(v, model_b.state_dict()[k]) for k, v in model_a.state_dict().items())
    assert doc_a == doc_b
    batch = small.test[0]
    with torch.no_grad():
        solver = LyophilizationSolver(model_a)
        assert torch.equal(solver.solve(batch.y0[None], batch.times[None], batch.process_args[None]).ys,
                           LyophilizationSolver(model_b).solve(batch.y0[None], batch.times[None], batch.process_args[None]).ys)
    report = evaluate(path_a, load_dataset(path_a.parent/"dataset.json"), tmp_path / "eval")
    assert report["model_type"] == "lyophilization"
    assert report["normal_test"]["endpoint_metrics_s"]["n_observed"] == 1
    assert report["normal_test"]["temperature_coverage"]["eligible"] > 0
    assert report["physical_validity_pass"]
    assert (tmp_path / "eval" / "method_b_handoff.json").exists()
