"""Meaningful pilot integrity checks: leakage, fair arms and intervention outcomes."""
import json

import numpy as np
import pytest

from benchmarks.physics_value.domains import actions, apply_action, make_case, run_reference
from benchmarks.physics_value.evaluate import (SimulationSession, load_case,
                                               load_packet, score_submission, stage)
from benchmarks.physics_value.generate import generate
from benchmarks.physics_value.public_models import predict


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    directory = tmp_path_factory.mktemp("physics-value") / "dataset"
    generate(directory, seed=71, replicates=1, plots=False)
    return directory


def catalogue(dataset):
    return json.loads((dataset / "evaluator/catalogue.json").read_text())


def find_case(dataset, domain="oxygen", family="nominal"):
    return next(c["case_id"] for c in catalogue(dataset) if c["domain"] == domain and c["family"] == family)


def test_generation_has_four_tasks_and_explicit_unmeasured_agent_results(dataset):
    summary = json.loads((dataset / "evaluator/simulation-summary.json").read_text())
    assert summary["case_count"] == 12
    assert summary["task_packet_count"] == 48
    assert summary["agent_runs_executed"] is False
    assert summary["agent_uplift"] is None
    assert json.loads((dataset / "generation-status.json").read_text())["status"] == "complete"
    with pytest.raises(ValueError, match="fresh"):
        generate(dataset)


def test_future_and_mechanisms_are_not_in_any_agent_packet(dataset):
    forbidden = {"mechanism", "family", "reference", "counterfactuals", "causes", "actual_kla_h_inv", "potential_our_mg_l_h", "active_max_temperature_c"}
    def inspect(value):
        if isinstance(value, dict):
            assert not forbidden & value.keys()
            for nested in value.values():
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)
    for path in (dataset / "public").glob("PV-*/*/packet.json"):
        packet = json.loads(path.read_text())
        inspect(packet)
        assert all(r["time_h"] <= packet["decision_time_h"] and r["available_at_h"] <= packet["decision_time_h"] for r in packet["receiving_observations"])
        if packet["task"] == "pretransfer":
            assert packet["receiving_observations"] == []
            assert packet["source_observations"]


def test_paired_inputs_are_identical_and_staging_excludes_other_tasks(dataset, tmp_path):
    case_id = find_case(dataset)
    a = stage(dataset, case_id, "pretransfer", "A", tmp_path / "a")
    b = stage(dataset, case_id, "pretransfer", "B", tmp_path / "b")
    assert a["common_input_sha256"] == b["common_input_sha256"]
    assert (tmp_path / "a/packet.json").read_bytes() == (tmp_path / "b/packet.json").read_bytes()
    assert not json.loads((tmp_path / "a/tools.json").read_text())["additional_host_tools"]
    assert json.loads((tmp_path / "b/tools.json").read_text())["additional_host_tools"]
    assert sorted(p.name for p in (tmp_path / "b").iterdir()) == ["packet.json", "source-traces.csv", "staging-receipt.json", "tools.json"]
    with pytest.raises(ValueError, match="outside"):
        stage(dataset, case_id, "diagnosis", "A", dataset / "agent")


def test_seed_reproduces_packets_truth_and_counterfactuals(dataset, tmp_path):
    second = tmp_path / "second"
    generate(second, seed=71, replicates=1, plots=False)
    first_manifest = json.loads((dataset / "manifest.json").read_text())
    second_manifest = json.loads((second / "manifest.json").read_text())
    assert first_manifest["files_sha256"] == second_manifest["files_sha256"]


def test_dataset_corruption_is_rejected(dataset, tmp_path):
    import shutil
    copied = tmp_path / "corrupt"
    shutil.copytree(dataset, copied)
    case_id = find_case(copied)
    target = copied / f"evaluator/cases/{case_id}.json"
    target.write_text(target.read_text().replace('"our_scale": 1.0', '"our_scale": 9.0'))
    with pytest.raises(ValueError, match="checksum"):
        load_case(copied, case_id)
    with pytest.raises(ValueError, match="identifier"):
        load_case(dataset, "../evaluator")


def test_oxygen_reference_positive_and_bad_cases_not_forced_feasible(dataset):
    for record in catalogue(dataset):
        case = load_case(dataset, record["case_id"])
        if case["domain"] == "oxygen":
            assert min(r["dissolved_oxygen_mg_l"] for r in case["reference"]["trajectory"]) >= 0
    nominal = load_case(dataset, find_case(dataset))
    mixed = load_case(dataset, find_case(dataset, family="mixed"))
    assert nominal["counterfactuals"]["optimization"]["keep"]["feasible_full_batch"]
    assert not mixed["counterfactuals"]["optimization"]["keep"]["feasible_full_batch"]


@pytest.mark.parametrize("domain", ["oxygen", "freeze_drying"])
def test_interventions_do_not_change_physical_history(domain):
    config, mechanism, _ = make_case(domain, "nominal", np.random.default_rng(4))
    original = run_reference(domain, config, mechanism)
    action = actions(domain)[1]
    changed = run_reference(domain, apply_action(domain, config, action, 6.), mechanism)
    key = "dissolved_oxygen_mg_l" if domain == "oxygen" else "product_temperature_c"
    old = [r[key] for r in original["trajectory"] if r["time_h"] < 6.]
    new = [r[key] for r in changed["trajectory"] if r["time_h"] < 6.]
    assert old == pytest.approx(new, abs=.002)


def test_loading_changes_are_only_pretransfer():
    config, _, _ = make_case("freeze_drying", "nominal", np.random.default_rng(3))
    action = next(a for a in actions("freeze_drying", pretransfer=True) if a["id"] == "half_load")
    assert apply_action("freeze_drying", config, action, 0., pretransfer=True)["load_vials"] < config["load_vials"]
    with pytest.raises(ValueError, match="loading"):
        apply_action("freeze_drying", config, action, 6.)


def test_event_safe_drying_conserves_ice_and_agrees_with_legacy_nominal():
    from src.lifesci.lyophilization.reference import reference as legacy
    config, mechanism, _ = make_case("freeze_drying", "nominal", np.random.default_rng(9))
    actual = run_reference("freeze_drying", config, mechanism)
    original = legacy(config)
    assert actual["completion_time_h"] == pytest.approx(original["completion_time_h"], abs=.3)
    ice = np.array([r["remaining_ice_kg_per_vial"] for r in actual["trajectory"]])
    assert np.min(ice) >= 0
    assert np.max(np.diff(ice)) <= 1e-9
    after = [r for r in actual["trajectory"] if r["time_h"] > actual["completion_time_h"]]
    assert after and all(r["sublimation_kg_h"] == 0 and r["active_max_temperature_c"] is None for r in after)
    assert actual["rhs_evaluations"] < 150000


def test_failed_generation_has_a_failed_receipt_not_a_complete_manifest(tmp_path, monkeypatch):
    from benchmarks.physics_value import generate as module
    def fail(*_args):
        raise RuntimeError("deliberate invalid reference")
    monkeypatch.setattr(module, "run_reference", fail)
    output = tmp_path / "failure"
    with pytest.raises(RuntimeError, match="invalid reference"):
        generate(output, seed=71, replicates=1, plots=False)
    status = json.loads((output / "generation-status.json").read_text())
    assert status["status"] == "failed" and status["completed_cases"] == 0
    assert not (output / "manifest.json").exists()


def test_public_models_are_forward_only_and_do_not_know_hidden_fault(dataset):
    for domain in ("oxygen", "freeze_drying"):
        case_id = find_case(dataset, domain, "sensor_bias")
        packet = load_packet(dataset, case_id, "optimization")
        value = predict(packet)
        assert "causes" not in value and "recommended_action" not in value
        with pytest.raises(ValueError, match="unsupported"):
            predict(packet, parameter_overrides={"hidden_scenario_id": 1})
        with pytest.raises(ValueError, match="finite"):
            predict(packet, parameter_overrides={"kla_h_inv" if domain == "oxygen" else "kv_scale": float("nan")})


def test_counterfactual_score_does_not_turn_infeasible_action_into_good_regret(dataset):
    case_id = find_case(dataset, family="mixed")
    result = score_submission(dataset, case_id, "optimization", {"hypotheses": ["low_transfer", "high_demand"], "action_id": "keep"})
    assert not result["independently_replayed_outcome"]["feasible_full_batch"]
    assert result["feasible_objective_regret"] is None
    assert result["authored_cause_coverage"] == 1
    assert result["hypothesis_set_size"] == 2
    assert result["unique_cause_identifiability"] == "not_established"
    with pytest.raises(ValueError, match="SimulationSession"):
        score_submission(dataset, case_id, "resolution", {})


def test_pretransfer_abstention_and_false_alarm_are_distinct(dataset):
    case_id = find_case(dataset)
    base = {"action_id": "keep", "hypotheses": ["nominal"]}
    abstain = score_submission(dataset, case_id, "pretransfer", base)
    false_alarm = score_submission(dataset, case_id, "pretransfer", dict(base, warn_before_transfer=True))
    assert abstain["warning_result"] == "abstained"
    assert false_alarm["warning_result"] == "FP"
    assert false_alarm["prevented_real_batches"] is None


def test_pretransfer_can_request_characterization_without_guessing_an_action(dataset):
    case_id = find_case(dataset, family="mixed")
    result = score_submission(dataset, case_id, "pretransfer", {
        "decision": "characterize", "requested_measurements": ["transfer_test"],
        "hypotheses": [], "warn_before_transfer": None})
    assert result["action_not_committed"]
    assert result["independently_replayed_outcome"] is None
    assert result["characterization_usefulness_review"] is None
    with pytest.raises(ValueError, match="requires"):
        score_submission(dataset, case_id, "pretransfer", {"decision": "characterize"})


def test_sequential_assays_advance_clock_reuse_results_and_verify_after_endpoint(dataset):
    case_id = find_case(dataset, family="sensor_bias")
    session = SimulationSession(dataset, case_id)
    assay = session.request_measurement("sensor_check")
    assert assay["current_time_h"] == 7.
    assert assay["result"]["values"]["sensor_bias"] == -3.
    assert all(r["available_at_h"] <= 7. for r in assay["observations"])
    with pytest.raises(ValueError, match="reuse"):
        session.request_measurement("sensor_check")
    result = session.commit("keep", hypotheses=["sensor_bias"])
    assert result["verification_available_at_h"] == 25.
    assert result["verified_process_constraint_resolution_h"] == 19.
    assert result["authored_cause_set_covered"]
    assert result["synthetic_human_work_minutes"] == 30.
    assert result["observed_engineer_time_saved"] is None
    assert result["real_manufacturing_action_executed"] is False
    with pytest.raises(ValueError, match="committed"):
        session.commit("pressure", hypotheses=[])


def test_session_does_not_erase_prior_oxygen_excursion(dataset):
    case_id = find_case(dataset, family="mixed")
    session = SimulationSession(dataset, case_id)
    session.request_measurement("uptake_assay")  # t=8
    session.request_measurement("sensor_check")  # t=9, after high demand starts
    result = session.commit("enrich", hypotheses=["low_transfer", "high_demand"])
    assert result["outcome"]["issue_precedes_decision"]
    assert result["verified_process_constraint_resolution_h"] is None
