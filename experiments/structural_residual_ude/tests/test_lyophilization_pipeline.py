"""End-to-end fitting and evidence contracts for the lyophilization pipeline."""
import csv
from dataclasses import replace
import json

import pytest
import torch

from biocore.method_a.artifact import load_artifact, save_artifact, sha256, write_json
from biocore.method_a.config import DTYPE, LyoModelConfig, LyoTrainConfig, seed_everything
from biocore.method_a.evaluate import checkpoint_validation_loss, evaluate, few_shot_scaling, score_model
from biocore.method_a.loss import lyophilization_loss
from biocore.method_a.lyo_data import (
    load_dataset, load_simulation_dataset, make_dataset, save_dataset, validate_splits,
)
from biocore.method_a.model import HybridLyophilizationUDE, LyophilizationSolver
from biocore.method_a.train import data_fingerprint, minibatches, solve_batches, train, validation_terms, warm_start


@pytest.fixture(scope="module")
def data():
    return make_dataset(2023, (3, 2, 2, 2))


@pytest.fixture(autouse=True)
def deterministic():
    seed_everything(2023)


def test_dataset_roundtrip_and_provenance(data, tmp_path):
    path = tmp_path/"input.json"
    save_dataset(data, path)
    assert "NaN" not in path.read_text()
    restored = load_dataset(path)
    assert restored.split_ids() == data.split_ids()
    assert restored.provenance == data.provenance
    for name in data.split_ids():
        assert data_fingerprint(getattr(restored, name)) == data_fingerprint(getattr(data, name))
    assert all(b.truth is None for b in restored.train)
    assert data.provenance["kind"] == "synthetic"
    with pytest.raises(ValueError, match="disjoint"):
        validate_splits(replace(data, val=(data.train[0],)))
    with pytest.raises(ValueError, match="evaluation-only"):
        validate_splits(replace(data, train=(replace(data.train[0], fault=True),)))


def test_simulation_splits_keep_sparse_observations_and_endpoint(tmp_path):
    write_json(tmp_path / "metadata.json", {"plant_constants": {"frozen_height": .006}})
    source = {
        "y0": torch.zeros((1, 1), dtype=DTYPE),
        "t_eval": torch.tensor([[0., 250., 810.]], dtype=DTYPE),
        "process_args": torch.tensor([[251., 13.]], dtype=DTYPE),
        "tb_obs_k": torch.tensor([[240., 241., 242.]], dtype=DTYPE),
        "ld_obs_m": torch.tensor([[0., float("nan"), .005]], dtype=DTYPE),
        "ld_mask": torch.tensor([[True, False, True]]),
        "t_end_sec": torch.tensor([900.], dtype=DTYPE),
    }
    modes = {"train": "normal", "val": "normal", "test_normal": "normal",
             "test_fault": "kv_edge_fault"}
    for name, mode in modes.items():
        torch.save(dict(source, fault_modes=[mode]), tmp_path / f"{name}.pt")

    imported = load_simulation_dataset(tmp_path)
    assert imported.split_ids() == dict(train=["train-000"], val=["val-000"],
                                        test=["test_normal-000"], faults=["test_fault-000"])
    assert imported.completion_remaining_fraction == .001
    assert imported.faults[0].fault
    assert imported.provenance["fault_modes"] == {"test_fault-000": "kv_edge_fault"}
    assert imported.provenance["source_splits"]["train"]["sha256"] == sha256(tmp_path / "train.pt")
    batch = imported.train[0]
    assert batch.times.tolist() == [0., 250., 810., 900.]
    assert batch.duration_s == 900.
    assert batch.process_args.tolist() == [251., 13., .006]
    assert batch.primary_mask.tolist() == [True, True, True, False]
    assert batch.obs_mask.tolist() == [[True, True], [True, False], [True, True], [False, False]]
    assert batch.observations[batch.obs_mask].tolist() == [240., 0., 241., 242., .005]


@pytest.mark.parametrize("corruption", ["units", "nonfinite", "mask", "mask_type", "endpoint"])
def test_dataset_rejects_invalid_measurements(data, tmp_path, corruption):
    path = tmp_path/"input.json"
    save_dataset(data, path)
    doc = json.loads(path.read_text())
    row = doc["splits"]["train"][0]
    if corruption == "units":
        doc["units"]["time"] = "h"
    elif corruption == "nonfinite":
        row["observations"][0][0] = float("inf")
    elif corruption == "mask":
        row["primary_mask"] = [True]
    elif corruption == "mask_type":
        row["primary_mask"][0] = "true"
    else:
        row["duration_s"] = -1.
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        load_dataset(path)


def test_bucketing_preserves_ragged_times_and_mixed_controls(data):
    b = data.train[0]
    a = replace(b, batch_id="constant", process_args=torch.tensor([249.15, 8.], dtype=DTYPE))
    c = replace(b, batch_id="short", times=b.times[:-1], observations=b.observations[:-1],
                obs_mask=b.obs_mask[:-1], primary_mask=b.primary_mask[:-1], duration_s=None)
    groups = list(minibatches((b, a, c), 8))
    assert len(groups) == 3
    assert sum(map(len, groups)) == 3
    for group in groups:
        assert len({(len(x.times), len(x.process_args)) for x in group}) == 1


def test_composite_loss_masks_nan_channels_and_never_reads_truth(data):
    model = HybridLyophilizationUDE()
    b = data.train[0]
    group = [b]
    solution = solve_batches(LyophilizationSolver(model), group)
    terms = lyophilization_loss(model, solution, group, LyoTrainConfig())
    changed = replace(b, truth=torch.full_like(b.truth, float("nan")))
    repeated = lyophilization_loss(model, solution, [changed], LyoTrainConfig())
    assert all(torch.equal(terms[key], repeated[key]) for key in terms)
    assert float(terms["state"].detach()) == 0.  # No fabricated layer measurements.
    terms["total"].backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


def test_optional_layer_data_and_missing_endpoints(data):
    b = data.train[0]
    model = HybridLyophilizationUDE()
    solution = solve_batches(LyophilizationSolver(model), [b])
    observations, mask = b.observations.clone(), b.obs_mask.clone()
    observations[:, 1] = solution.ys[0, :, 0].detach()+1e-4
    mask[:, 1] = True
    b = replace(b, observations=observations, obs_mask=mask, duration_s=None)
    terms = lyophilization_loss(model, solution, [b], LyoTrainConfig())
    assert float(terms["duration"].detach()) == 0.
    assert float(terms["state"].detach()) == pytest.approx((1e-4/float(solution.height[0, 0]))**2)
    assert all(torch.isfinite(value) for value in terms.values())


def test_premature_completion_cannot_hide_temperature_supervision(data):
    # A very thin vial finishes long before the supplied primary observations.
    b = data.train[0]
    args = b.process_args.clone()
    args[-1] = .0001
    b = replace(b, process_args=args, primary_mask=torch.ones_like(b.primary_mask))
    model = HybridLyophilizationUDE()
    solution = solve_batches(LyophilizationSolver(model), [b])
    terms = lyophilization_loss(model, solution, [b], LyoTrainConfig())
    assert float(terms["coverage"].detach()) > 0
    assert float(terms["duration"].detach()) > 0
    (terms["duration"]+terms["coverage"]).backward()
    assert abs(float(model.physics_core.log_Kc.grad)) > 1e-8


def test_versioned_lyophilization_artifact_and_frozen_replay(data, tmp_path):
    model = HybridLyophilizationUDE()
    with torch.no_grad():
        model.residual_mlp[-1].weight.normal_(0, .002)
    path = tmp_path/"model.safetensors"
    save_artifact(model, path, {"purpose": "lyophilization roundtrip"})
    frozen, doc = load_artifact(path)
    assert doc["schema_version"] == 2 and doc["model_type"] == "lyophilization"
    assert doc["units"]["time"] == "s"
    assert not any(p.requires_grad for p in frozen.parameters())
    assert all(torch.equal(value, frozen.state_dict()[key]) for key, value in model.state_dict().items())
    b = data.test[0]
    with torch.no_grad():
        original = solve_batches(LyophilizationSolver(model), [b]).ys
        restored = solve_batches(LyophilizationSolver(frozen), [b]).ys
    assert torch.equal(original, restored)
    # A hash-consistent but unknown model type must still fail schema validation.
    doc["model_type"] = "unknown"
    write_json(path.with_suffix(".json"), doc)
    write_json(path.with_suffix(".sha256.json"), {path.name: sha256(path),
               path.with_suffix(".json").name: sha256(path.with_suffix(".json"))})
    with pytest.raises(ValueError, match="model_type"):
        load_artifact(path)


def test_temperature_coverage_and_endpoint_censoring_are_explicit(data):
    b = data.test[0]
    # A short, still-wet prefix cannot produce a completed-endpoint prediction.
    prefix = replace(b, times=b.times[:3], observations=b.observations[:3],
                     obs_mask=b.obs_mask[:3], primary_mask=b.primary_mask[:3], duration_s=None)
    score = score_model(HybridLyophilizationUDE(), (prefix,))
    assert score["endpoints"]["right_censored"] == 1
    assert score["endpoint_metrics_s"]["n_observed"] == 0
    assert score["per_batch"][0]["predicted_endpoint_s"] is None
    assert score["temperature_coverage"]["eligible"] >= score["temperature_coverage"]["scored"]
    assert score["metrics"]["dried_layer_m"]["rmse"] is None
    assert "qP" not in json.dumps(score)


def test_evaluation_is_label_and_truth_blind(data):
    b = data.test[0]
    changed = replace(b, truth=torch.full_like(b.truth, 1e9), fault=True)
    model = HybridLyophilizationUDE()
    score = score_model(model, (b,))
    repeated = score_model(model, (changed,))
    assert score == repeated


def test_training_provenance_warmup_and_evaluation(data, tmp_path):
    config = LyoTrainConfig(epochs=3, warmup_fraction=.34, batch_size=2)
    path = train(data, tmp_path/"run", config)
    history = json.loads((path.parent/"training_history.json").read_text())
    with (path.parent/"training_metrics.csv").open(newline="") as metrics_file:
        metrics = list(csv.DictReader(metrics_file))
    assert len(metrics) == len(history) == config.epochs
    for metric, row in zip(metrics, history):
        assert int(metric["epoch"]) == row["epoch"]
        assert metric["phase"] == row["phase"]
        for key in ("train_loss", "val_loss", "physics_lr", "residual_lr"):
            assert float(metric[key]) == row[key]
        for split, history_key in (("train", "train"), ("val", "validation")):
            contributions = {
                name: float(metric[f"{split}_{name}_loss"])
                for name in row[history_key] if name != "total"
            }
            assert sum(contributions.values()) == pytest.approx(row[f"{split}_loss"])
            assert contributions["duration"] == row[history_key]["duration"] * config.duration_weight
        assert row["physics_lr"] == config.physics_lr
        assert row["residual_lr"] == config.residual_lr
    assert history[0]["phase"] == "physics_only" and history[0]["grad_norm_mlp"] == 0.
    assert history[1]["phase"] == "hybrid" and history[1]["grad_norm_mlp"] > 0.
    assert {"temperature", "duration", "coverage", "operating", "residual", "state", "total"} == set(history[0]["train"])
    assert all(row["grad_norm_phys"] > 0 for row in history)
    breakdown = checkpoint_validation_loss(path, load_dataset(path.parent/"dataset.json"))
    best = history[breakdown["checkpoint_epoch"]]
    assert breakdown["recorded_validation_loss"] == best["val_loss"]
    assert breakdown["recomputed_validation_loss"] == pytest.approx(best["val_loss"])
    assert breakdown["weighted_components"] == pytest.approx({
        name: float(metrics[best["epoch"]][f"val_{name}_loss"])
        for name in best["validation"] if name != "total"
    })
    report = evaluate(path, data, tmp_path/"eval")
    assert report["model_type"] == "lyophilization"
    assert report["checkpoint_epoch"] == best["epoch"]
    assert report["checkpoint_validation_loss"] == best["val_loss"]
    model, _ = load_artifact(path)
    test_objective = validation_terms(model, LyophilizationSolver(model), data.test, config)
    test_loss = report["normal_test"]["loss"]
    assert test_loss["total"] == pytest.approx(test_objective["total"])
    assert sum(test_loss["weighted_components"].values()) == pytest.approx(test_loss["total"])
    assert report["auroc_cohort_sizes"] == {"normal": 2, "fault": 2}
    assert report["normal_test"]["endpoint_metrics_s"]["rmse"] is not None
    handoff = json.loads((tmp_path/"eval"/"method_b_handoff.json").read_text())
    assert handoff["units"]["time"] == "s"
    assert any(not r["temperature_defined"] and r["bottom_temperature_k"] is None
               for b in handoff["batches"] for r in b["trajectory"])
    assert "titer" not in json.dumps(report)
    # Endpoint observations are covered by the fingerprint, not just trajectory arrays.
    changed = replace(data, test=(replace(data.test[0], duration_s=data.test[0].duration_s+1.), *data.test[1:]))
    with pytest.raises(ValueError, match="provenance"):
        evaluate(path, changed, tmp_path/"bad")
    with pytest.raises(ValueError, match="endpoint definitions"):
        train(data, tmp_path/"wrong-endpoint", config, LyoModelConfig(completion_remaining_fraction=.01))


def test_fitting_ignores_all_benchmark_truth(data, tmp_path):
    one = replace(data, train=data.train[:1], val=data.val[:1], test=data.test[:1], faults=())
    changed = replace(one, train=tuple(replace(b, truth=None) for b in one.train),
                      val=tuple(replace(b, truth=None) for b in one.val))
    a = train(one, tmp_path/"a", LyoTrainConfig(epochs=1))
    b = train(changed, tmp_path/"b", LyoTrainConfig(epochs=1))
    model_a, document_a = load_artifact(a)
    model_b, document_b = load_artifact(b)
    assert document_a == document_b
    assert all(torch.equal(value, model_b.state_dict()[key]) for key, value in model_a.state_dict().items())


def test_warm_start_keeps_source_checkpoint_as_baseline(data, tmp_path):
    small = replace(data, train=data.train[:1], val=data.val[:1], test=data.test[:1], faults=())
    config = LyoTrainConfig(epochs=1, min_delta=1e6)
    source = train(small, tmp_path/"source", config)
    with pytest.raises(ValueError, match="separate"):
        warm_start(source, source.parent, 2)
    target = warm_start(source, tmp_path/"target", 2)
    _, source_doc = load_artifact(source)
    _, target_doc = load_artifact(target)
    parent, result = source_doc["metadata"], target_doc["metadata"]
    assert target_doc["weights_sha256"] == source_doc["weights_sha256"]
    assert result["best_epoch"] == -1
    assert result["val_loss"] == pytest.approx(parent["val_loss"])
    assert result["split_ids"] == parent["split_ids"]
    assert result["dataset_sha256"] == parent["dataset_sha256"]
    assert result["warm_start"]["source_best_epoch"] == parent["best_epoch"]
    assert result["train"] == {**parent["train"], "epochs": 2, "warmup_fraction": 0.}
    history = json.loads((target.parent/"training_history.json").read_text())
    assert len(history) == 2
    assert all(row["phase"] == "hybrid" and row["grad_norm_mlp"] > 0 for row in history)


def test_few_shot_reports_actual_subset_sizes_without_inventing_a_trend(data, tmp_path):
    tiny = replace(data, train=data.train[:1], val=data.val[:1], test=data.test[:1], faults=())
    report = few_shot_scaling(tiny, tmp_path/"few-shot", epochs=1)
    assert len(report["results"]) == 1
    assert report["results"][0]["n_train_batches"] == 1
    assert report["results"][0]["temperature_coverage"]["eligible"] > 0
