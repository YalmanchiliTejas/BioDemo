from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.gateway import FakeProvider
from src.lifesci.gateway.registry import Qualification
from src.lifesci.lyophilization.case import source_config
from src.lifesci.lyophilization.model import simulate, state_at
from src.lifesci.process_engineering import transient
from src.lifesci.process_engineering.catalog import ModelCatalog
from src.lifesci.process_engineering.engine import execute, visible_rows
from src.lifesci.process_engineering.schemas import PipelineSpec
from src.lifesci.store import RecordStore


@pytest.fixture
def env():
    p = Platform(RecordStore(), providers={})
    seed(p)
    ctx = p.identity.context_for(TENANT, "priya")
    source = p.process_models.run(ctx, audience="cdmo_operation", samples=2)
    return p, ctx, source


def specification(source, **changes):
    spec = {
        "simulation_id": source["id"], "candidate_index": 3,
        "objective": "Compare model scope, held-out discrepancy and future operating changes",
        "models": [
            {"model_id": "lyo.kv_rp", "rationale": "Fast screening baseline with explicit neglected thermal storage"},
            {"model_id": "lyo.transient_lumped", "rationale": "Assess finite thermal response under declared input assumptions"},
        ],
        "thermal_assumptions": {"vial_heat_capacity_j_k": 3., "initial_temperature_c": -43.},
        "calibration": "kv_scale", "samples": 2, "seed": 19,
    }
    spec.update(changes)
    return spec


def test_catalog_applicability_and_no_automatic_reference_exposure():
    catalog = ModelCatalog()
    config = source_config()
    assert catalog.get("lyo.kv_rp").applicability(config)["applicable"]
    missing = catalog.get("lyo.transient_lumped").applicability(config)
    assert not missing["applicable"]
    assert "thermal.initial_temperature_c" in missing["missing_inputs"]
    assert len(catalog.snapshot()) == 2
    assert all("reference" not in m["id"] for m in catalog.snapshot())
    with pytest.raises(ValueError, match="unregistered"):
        catalog.get("python.os.system")
    config["thermal"] = {"vial_heat_capacity_j_k": -1, "initial_temperature_c": -43}
    assert not catalog.get("lyo.transient_lumped").applicability(config)["applicable"]


def test_transient_mass_balance_and_quasi_steady_limit():
    config = source_config()
    config["thermal"] = {"vial_heat_capacity_j_k": .1, "initial_temperature_c": state_at(config, 0., 0.)["interface_temperature_c"]}
    output = transient.simulate(config)
    baseline = simulate(config)
    assert output["numerical_status"] == "completed"
    assert output["completion_time_h"] == pytest.approx(baseline["completion_time_h"], abs=.15)
    rows = output["trajectory"]
    mass = np.trapezoid([r["rate_kg_s_per_vial"] for r in rows], [r["time_h"]*3600 for r in rows])
    assert mass == pytest.approx(output["initial_ice_kg_per_vial"], rel=.005)
    assert rows[-1]["remaining_ice_kg_per_vial"] < 1e-9
    assert all(r["remaining_ice_kg_per_vial"] >= 0 for r in rows)
    assert any(abs(r["sensible_heat_w_per_vial"]) > 1e-8 for r in rows)
    # An intentionally large thermal capacity makes stored sensible energy
    # material, so this catches a model that silently drops the storage term.
    thermal = deepcopy(config)
    thermal["thermal"]["vial_heat_capacity_j_k"] = 50.
    energy = transient.simulate(thermal)
    rows = energy["trajectory"]
    supplied = np.trapezoid([r["heat_w_per_vial"] for r in rows], [r["time_h"]*3600 for r in rows])
    stored = np.trapezoid([50.+transient.ICE_CP_J_KG_K*r["remaining_ice_kg_per_vial"] for r in rows], [r["interface_temperature_c"] for r in rows])
    latent = transient.H_SUB*energy["initial_ice_kg_per_vial"]
    assert supplied == pytest.approx(latent+stored, rel=.003)


def test_transient_initial_conditions_and_failure_regions():
    cold = source_config()
    cold["thermal"] = {"vial_heat_capacity_j_k": 50., "initial_temperature_c": -60.}
    warm = deepcopy(cold)
    warm["thermal"]["initial_temperature_c"] = -43.
    assert transient.simulate(cold)["completion_time_h"] > transient.simulate(warm)["completion_time_h"]
    with pytest.raises(ValueError, match="initial_temperature"):
        transient.simulate({**source_config(), "thermal": {"vial_heat_capacity_j_k": 3.}})


def test_pipeline_holdout_isolation_reproducibility_and_prospective_history(env):
    p, ctx, source = env
    service = p.process_models.analysis
    plan = service.prepare(ctx, specification(source))
    assert plan["authored_by"]["kind"] == "person"
    assert plan["source_snapshot"]["prior_diagnostic_fits_reused"] is False
    assert "rp_scale" not in plan["source_snapshot"]["config"]["product"]
    assert "kv_scale" not in plan["source_snapshot"]["config"]["equipment"]
    first = service.execute(ctx, plan["id"])
    second = service.execute(ctx, plan["id"])
    assert first["execution_status"] == "completed"
    assert len(first["models"]) == 2
    for a, b in zip(first["models"], second["models"]):
        assert a["calibration"] == b["calibration"]
        assert a["prediction"] == b["prediction"]
        assert a["uncertainty"] == b["uncertainty"]
        assert a["geometry"]["frames"] == b["geometry"]["frames"]
        assert a["holdout_evaluation"]["coverage"] == 1.
    assert all(r["time_h"] <= 3 for r in first["training_observations"])
    assert all(3 < r["time_h"] <= 6 for r in first["holdout_observations"])
    row = first["models"][0]
    history_endpoint = row["holdout_evaluation"]["pairs"][-1]["predicted_c"]
    forecast_endpoint = next(r["interface_temperature_c"] for r in row["prediction"]["trajectory"] if r["time_h"] == 6)
    assert abs(history_endpoint-forecast_endpoint) > 1
    changed = deepcopy(plan)
    for observation in changed["source_snapshot"]["observations"]:
        if observation["time_h"] > 3:
            observation["product_temperature_c"] += 10
    alternate = execute(changed, service.catalog)
    for a, b in zip(first["models"], alternate["models"]):
        assert a["calibration"]["estimate"] == b["calibration"]["estimate"]
        assert a["holdout_evaluation"]["rmse_c"] != b["holdout_evaluation"]["rmse_c"]


def test_missing_inputs_and_budget_failures_remain_explicit(env):
    p, ctx, source = env
    service = p.process_models.analysis
    missing = service.prepare(ctx, specification(source, thermal_assumptions=None, calibration="none", samples=0))
    output = service.execute(ctx, missing["id"])
    assert output["execution_status"] == "partial_or_blocked"
    assert output["models"][0]["status"] == "completed"
    assert output["models"][1]["status"] == "blocked_missing_inputs"
    limited = service.prepare(ctx, specification(source, calibration="none", max_solver_calls=2, samples=4))
    output = service.execute(ctx, limited["id"])
    assert output["execution_status"] == "partial_or_blocked"
    assert output["resource_usage"]["solver_calls"] <= 2
    assert any(m["status"] == "budget_exhausted" for m in output["models"])


@pytest.mark.parametrize("changes", [
    {"models": [{"model_id": "unknown.simulator", "rationale": "Unreviewed generated code"}]},
    {"samples": 1},
    {"import_path": "os.system"},
    {"calibration_until_h": 6.},
    {"evidence_cutoff_h": 9.},
])
def test_unregistered_code_bad_partitions_and_cutoff_expansion_rejected(env, changes):
    p, ctx, source = env
    with pytest.raises(ValueError):
        p.process_models.analysis.prepare(ctx, specification(source, **changes))


def test_model_revision_and_input_revision_invalidate_results_and_reviews(env):
    p, ctx, source = env
    service = p.process_models.analysis
    plan = service.prepare(ctx, specification(source, calibration="none", samples=0))
    result = service.execute(ctx, plan["id"])
    review = service.propose_review(ctx, result["id"], "priya")
    assert review["execution_status"] == "not_started"
    assert review["required_roles"] == ["engineering"]
    current = service.catalog.get("lyo.kv_rp")
    service.catalog.adapters[current.id] = replace(current, version=current.version+"-changed")
    with pytest.raises(ValueError, match="no longer current|changed"):
        service.execute(ctx, plan["id"])
    assert service.get_plan(ctx, plan["id"])["status"] == "stale"
    assert service.get_result(ctx, result["id"])["status"] == "stale"
    assert p.store.read().require(TENANT, "proposal", review["proposal_id"]).state["status"] == "stale"
    with pytest.raises(ValueError):
        service.propose_review(ctx, result["id"], "priya")


def test_hidden_channels_and_delayed_availability_are_excluded():
    rows = [{"time_h": i, "available_at_h": i, "product_temperature_c": -35., "hidden_cause": "secret"} for i in range(9)]
    rows[4]["available_at_h"] = 7
    output = visible_rows(rows, 6)
    assert "secret" not in json.dumps(output)
    assert all(r["time_h"] <= 6 for r in output)
    assert 4 not in [r["time_h"] for r in output]


def test_api_uses_existing_permissions_and_idempotency(env):
    p, ctx, source = env
    client = TestClient(create_app(p))
    headers = {"X-Tenant-Id": TENANT, "X-Actor-Id": "priya", "Idempotency-Key": "physical-plan-key"}
    body = specification(source, calibration="none", samples=0)
    response = client.post("/v1/process-model/pipelines", headers=headers, json=body)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert client.post("/v1/process-model/pipelines", headers=headers, json=body).json()["id"] == plan["id"]
    assert client.post("/v1/process-model/pipelines", headers=headers, json={**body, "objective": "Changed engineering objective"}).status_code == 409
    execute_headers = {**headers, "Idempotency-Key": "physical-execute-key"}
    result = client.post(f"/v1/process-model/pipelines/{plan['id']}/execute", headers=execute_headers)
    assert result.status_code == 200, result.text
    rid = result.json()["id"]
    assert client.post(f"/v1/process-model/pipelines/{plan['id']}/execute", headers=execute_headers).json()["id"] == rid
    p.identity.assign_role(TENANT, "other", "msat", site_id="OTHER")
    forbidden = {"X-Tenant-Id": TENANT, "X-Actor-Id": "other"}
    assert client.get(f"/v1/process-model/analyses/{rid}", headers=forbidden).status_code == 403
    assert client.post("/v1/process-model/pipelines", headers=forbidden, json=body).status_code == 403
    assert client.post("/v1/process-model/pipelines", headers=headers, json={**body, "python": "arbitrary()"}).status_code == 422


def test_actual_agent_route_failure_is_not_replaced_with_a_plan(env):
    p, ctx, source = env
    result = p.process_models.analysis.agent_plan(ctx, {"simulation_id": source["id"], "objective": "Choose models for engineering review"})
    assert result["status"] == "agent_unavailable" and result["plan"] is None
    assert result["gateway_run"]["status"] == "unresolved"
    assert result["gateway_run"]["issues"]


def test_agent_selection_contract_and_invalid_model_rejection_with_test_provider(env):
    p, ctx, source = env
    fake = FakeProvider(name="anthropic")
    p.gateway.providers["anthropic"] = fake
    registry = p.gateway.registry
    registry.qualify(Qualification("investigation_planning", "anthropic-opus", "unit-test-only", True,
        {"contract": 1.}, {"contract": 1.}, "mock contract testing only; not scientific qualification", "test"))
    model_name = registry.profiles["anthropic-opus"].model
    fake.scripts[model_name] = [json.dumps({"models": [{"model_id": "lyo.kv_rp", "rationale": "Screening is sufficient with the available characterized inputs"}], "calibration": "none", "samples": 0})]
    request = {"simulation_id": source["id"], "objective": "Choose models for a physical analysis"}
    result = p.process_models.analysis.agent_plan(ctx, request)
    assert result["status"] == "plan_created"
    assert result["plan"]["authored_by"]["kind"] == "agent"
    assert result["plan"]["pinned_models"][0]["id"] == "lyo.kv_rp"
    fake.scripts[model_name] = [json.dumps({"models": [{"model_id": "unregistered.code", "rationale": "An unsupported arbitrary solver attempt"}]})]
    rejected = p.process_models.analysis.agent_plan(ctx, request)
    assert rejected["status"] == "invalid_agent_plan" and rejected["plan"] is None


def test_agent_tools_use_time_scopes_and_record_agent_authorship(env):
    p, ctx, source = env
    service = p.process_models.analysis
    tools = service.agent_tools(ctx)
    assert set(tools) == {"physical_models_catalog", "physical_analysis_prepare", "physical_analysis_execute", "physical_analysis_read", "physical_model_propose_adapter"}
    with pytest.raises(PermissionError, match="cutoff"):
        tools["physical_models_catalog"](simulation_id=source["id"], as_of="2000-01-01T00:00:00Z")
    plan = tools["physical_analysis_prepare"](spec=specification(source, calibration="none", samples=0), as_of="2100-01-01T00:00:00Z")["plan"]
    assert plan["authored_by"]["kind"] == "agent"
    output = tools["physical_analysis_execute"](plan_id=plan["id"], as_of="2100-01-01T00:00:00Z")
    assert output["analysis"]["execution_status"] == "completed"


def test_new_adapter_proposal_never_registers_or_executes_code(env):
    p, ctx, source = env
    service = p.process_models.analysis
    proposal = service.propose_adapter(ctx, {
        "simulation_id": source["id"], "model_id": "lyo.distributed_pde", "title": "Distributed primary drying model",
        "governing_equations": "Conservation of energy with Fourier conduction and interface sublimation.",
        "required_inputs_and_units": ["Frozen conductivity W/(m K)", "Vial geometry m", "Temperature field K"],
        "source_and_license": "Original implementation proposed; source/license review required.",
        "verification_and_validation_plan": "Verify limiting behavior, mesh/time convergence and balances; validate against independent thermometry.",
        "intended_use_and_limits": "Investigate spatial temperature gradients; qualification requires independent experimental evidence.",
        "owner_id": "priya",
    })
    assert proposal["status"] == "proposed" and proposal["execution_status"] == "not_started"
    assert proposal["payload"]["registry_status"] == "not_registered"
    assert proposal["required_roles"] == ["engineering"]
    assert "lyo.distributed_pde" not in service.catalog.adapters


def test_agent_assessment_is_separate_derived_interpretation_and_unavailability_is_honest(env):
    p, ctx, source = env
    service = p.process_models.analysis
    plan = service.prepare(ctx, specification(source, calibration="none", samples=0))
    result = service.execute(ctx, plan["id"])
    unavailable = service.interpret(ctx, result["id"])
    assert unavailable["status"] == "agent_unavailable" and unavailable["interpretation"] is None
    fake = FakeProvider(name="anthropic")
    p.gateway.providers["anthropic"] = fake
    registry = p.gateway.registry
    registry.qualify(Qualification("comparison_explanation", "anthropic-opus", "unit-test-only", True,
        {"contract": 1.}, {"contract": 1.}, "mock contract test only", "test"))
    model_name = registry.profiles["anthropic-opus"].model
    fake.scripts[model_name] = [json.dumps({"explanation": "Both calculations need independent characterization.", "source_refs": [{"id": result["id"]}],
        "model_tradeoffs": ["Thermal storage adds uncharacterized parameters."], "limitations": ["Synthetic holdout data does not validate either model."],
        "verification_experiments": ["Use independent temperature and vapor-rate measurements."]})]
    interpreted = service.interpret(ctx, result["id"])
    assert interpreted["status"] == "interpretation_created"
    artifact = interpreted["interpretation"]
    assert artifact["review_state"] == "draft_requires_review"
    assert artifact["inputs"][0]["id"] == result["id"]
    assert service.get_result(ctx, result["id"])["review_state"] == "requires_engineering_review"


def test_model_selection_starts_from_inputs_without_running_preset_model(env, monkeypatch):
    p, ctx, _ = env
    monkeypatch.setattr(p.process_models, "run", lambda *a, **k: pytest.fail("input preparation must not execute preset comparisons"))
    source = p.process_models.context(ctx, audience="cdmo_operation", samples=2)
    assert source["classification"] == "analysis_inputs_not_predictions"
    assert "prediction" not in source and source["has_observations"]
    service = p.process_models.analysis
    plan = service.prepare(ctx, specification(source, candidate_index=0, calibration="none", samples=0))
    assert plan["inputs"][0]["kind"] == "physical_analysis_context"
    output = service.execute(ctx, plan["id"])
    assert output["execution_status"] == "completed"
    assert len(output["models"]) == 2
    review = service.propose_review(ctx, output["id"], "priya")
    p.process_models.context(ctx, audience="cdmo_operation", cdmo_future_shelf_c=-16., samples=2)
    assert service.get_plan(ctx, plan["id"])["status"] == "stale"
    assert service.get_result(ctx, output["id"])["status"] == "stale"
    assert p.store.read().require(TENANT, "proposal", review["proposal_id"]).state["status"] == "stale"


def test_no_observations_means_no_reported_validation_error_or_ranking(env):
    p, ctx, _ = env
    source = p.process_models.context(ctx, audience="technology_transfer", samples=2)
    service = p.process_models.analysis
    plan = service.prepare(ctx, specification(source, candidate_index=0, calibration="none", samples=0))
    output = service.execute(ctx, plan["id"])
    assert output["ranking"] == []
    assert all(m["holdout_evaluation"]["rmse_c"] is None for m in output["models"])
    assert next(s for s in output["stages"] if s["step"] == "evaluate_holdout")["status"] == "not_requested_or_unavailable"
    with pytest.raises(ValueError, match="training observations"):
        service.prepare(ctx, specification(source, candidate_index=0, calibration="kv_scale"))

