import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.gateway import TaskRequest
from src.lifesci.lyophilization import model
from src.lifesci.lyophilization.case import manifest, receiving_config, source_config
from src.lifesci.lyophilization.comparison import attempt_agent, public_packet
from src.lifesci.lyophilization.workflows import visible_measurements
from src.lifesci.store import RecordStore


@pytest.fixture(scope="module")
def pilot():
    return model.simulate(source_config())


def test_pressure_units_and_heat_mass_balance(pilot):
    assert model.ice_pressure(0.) == pytest.approx(611.15, rel=.002)
    config = source_config()
    ap, av, height = model.geometry(config["product"])
    assert height == pytest.approx(.0086, abs=.0001)
    p, e = config["product"], config["equipment"]
    for row in pilot["trajectory"]:
        ts, pc = row["shelf_temperature_c"], row["chamber_pressure_pa"]
        kv = e["kv_a_w_m2_k"]+e["kv_b_w_m2_k_pa"]*pc/(1+e["kv_c_per_pa"]*pc)
        assert av*kv*(ts-row["bottom_temperature_c"]) == pytest.approx(row["rate_kg_s_per_vial"]*model.H_SUB, rel=1e-6)
        assert row["heat_w_per_vial"] == pytest.approx(row["rate_kg_s_per_vial"]*model.H_SUB)
        assert row["remaining_ice_kg_per_vial"] >= 0
    rows = pilot["trajectory"]
    mass = np.trapezoid([r["rate_kg_s_per_vial"] for r in rows], [r["time_h"]*3600 for r in rows])
    assert mass == pytest.approx(pilot["initial_ice_kg_per_vial"], rel=.003)


@pytest.mark.parametrize("path,value", [
    (("product", "fill_m3"), -1.), (("product", "porosity"), 1.),
    (("product", "rp0_m_s"), 0.), (("product", "rp_scale"), float("nan")),
    (("equipment", "vapor_capacity_kg_h"), 0.), (("equipment", "kv_a_w_m2_k"), float("inf")),
    (("load_vials",), True), (("load_vials",), 1.2), (("duration_h",), 0.),
])
def test_validation_rejects_invalid_units_and_numeric_regions(path, value):
    config = source_config()
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        model.simulate(config)


def test_completion_limiting_behavior_and_mass_conservation(pilot):
    assert pilot["numerical_status"] == "completed"
    assert 20 < pilot["completion_time_h"] < 50
    assert pilot["trajectory"][-1]["remaining_ice_kg_per_vial"] < 1e-10
    c = source_config(); c["equipment"]["kv_scale"] = 1.5
    assert model.simulate(c)["completion_time_h"] < pilot["completion_time_h"]
    c = source_config(); c["product"]["rp_scale"] = 1.5
    out = model.simulate(c)
    assert out["completion_time_h"] > pilot["completion_time_h"]
    assert out["minimum_critical_margin_c"] < pilot["minimum_critical_margin_c"]
    c = source_config(); c["initial_dried_fraction"] = 1.
    dry = model.simulate(c)
    assert dry["completion_time_h"] == 0. and dry["trajectory"] == []


def test_piecewise_schedules_and_incompletion():
    c = source_config(); c["duration_h"] = 12
    c["schedule"].append({"time_h": 4, "shelf_temperature_c": -28., "chamber_pressure_pa": 10.})
    out = model.simulate(c)
    assert out["numerical_status"] == "completed" and out["completion_time_h"] is None
    assert out["violations"][-1]["constraint"] == "incomplete_primary_drying"
    assert next(r for r in out["trajectory"] if r["time_h"] == 4)["shelf_temperature_c"] == -28
    c["schedule_mode"] = "linear"
    assert model.conditions(c, 2) == (-26., 9.)
    c["schedule"][1]["time_h"] = 0
    with pytest.raises(ValueError, match="increase"):
        model.simulate(c)


def test_constraint_detection_and_invalid_control_warning():
    c = receiving_config()
    out = model.simulate(c)
    assert next(v for v in out["violations"] if v["constraint"] == "vapor_capacity")["first_time_h"] == 0.
    assert any("invalid-control" in w for w in out["warnings"])
    c["equipment"]["condenser_capacity_kg"] = 1.
    assert any(v["constraint"] == "condenser_ice_capacity" for v in model.simulate(c)["violations"])
    c = receiving_config(shelf_c=-5., capacity_kg_h=2.)
    assert any(v["constraint"] == "critical_temperature" for v in model.simulate(c)["violations"])


def test_zero_heat_no_driving_force_and_solver_failure(monkeypatch):
    c = source_config(); c["equipment"].update(kv_a_w_m2_k=0, kv_b_w_m2_k_pa=0)
    out = model.simulate(c)
    assert out["numerical_status"] == "failed" and out["completion_time_h"] is None
    c = source_config(); c["schedule"][0]["shelf_temperature_c"] = -65
    assert "no sublimation driving force" in model.simulate(c)["numerical_error"]
    monkeypatch.setattr(model, "solve_ivp", lambda *a, **k: SimpleNamespace(success=False, message="injected solver failure"))
    out = model.simulate(source_config())
    assert out["numerical_status"] == "failed" and "injected" in out["numerical_error"]
    assert not out["trajectory"]


def test_reproducible_uncertainty_and_no_quality_overclaim():
    c = source_config(); c["duration_h"] = 45
    a = model.uncertainty(c, samples=3, seed=9)
    assert a == model.uncertainty(c, samples=3, seed=9)
    assert a != model.uncertainty(c, samples=3, seed=10)
    assert "not a calibrated" in a["interpretation"]
    assert "residual_moisture" not in model.simulate(c)
    with pytest.raises(ValueError):
        model.uncertainty(c, samples=1)


def test_provenance_categories_and_manifest_coverage():
    config = receiving_config()
    rows = manifest(config)
    assert set(r["category"] for r in rows) <= {"published", "experimentally estimated", "digitized", "synthetic_assumption"}
    for block in ("product", "equipment"):
        for key, value in config[block].items():
            if isinstance(value, (float, int)):
                assert any(r["parameter"] == f"{block}.{key}" and r["unit"] for r in rows)
    capacity = next(r for r in rows if r["parameter"] == "equipment.vapor_capacity_kg_h")
    assert capacity["category"] == "synthetic_assumption"


def test_hidden_outcome_and_delayed_availability_isolation():
    rows = [{"time_h": t, "available_at_h": t, "product_temperature_c": -35+t*.1, "hidden_label": "secret"} for t in range(10)]
    rows[4]["available_at_h"] = 9
    packet = public_packet(source_config(), rows, 6)
    assert all(r["time_h"] <= 6 and r["available_at_h"] <= 6 for r in packet["measurements"])
    assert "secret" not in json.dumps(packet)
    assert 4 not in [r["time_h"] for r in packet["measurements"]]
    with pytest.raises(ValueError):
        visible_measurements(rows, 1)
    with pytest.raises(ValueError, match="requires"):
        visible_measurements([{"time_h": 1}], 6)


def test_reference_starts_at_thermal_equilibrium_and_history_is_causal():
    from src.lifesci.lyophilization.reference import operation_config, reference
    first = reference(operation_config())
    other = reference(operation_config(future_shelf_c=-14.))
    initial = first["trajectory"][0]
    assert initial["sublimation_kg_h"] < operation_config()["equipment"]["vapor_capacity_kg_h"]
    # A future scheduled control cannot affect observations before its start.
    assert visible_measurements(first["trajectory"], 6) == visible_measurements(other["trajectory"], 6)
    assert first["first_capacity_h"] is None
    assert first["completion_time_h"] != other["completion_time_h"]


@pytest.mark.parametrize("config", [{}, {"product": {}, "equipment": {}, "load_vials": 1, "duration_h": 10, "schedule": []}])
def test_missing_scientific_fields_raise_input_error(config):
    with pytest.raises(ValueError):
        model.simulate(config)


@pytest.fixture
def platform():
    p = Platform(RecordStore(), providers={})
    seed(p)
    return p, p.identity.context_for(TENANT, "priya")


def test_gateway_registered_solver_preserves_normal_analytics(platform):
    p, ctx = platform
    request = TaskRequest("primary_drying_simulation", ctx, payload={"config": source_config()})
    a, b = p.gateway.run(request), p.gateway.run(request)
    assert a.status == "completed" and a.output == b.output and a.cost_usd == 0
    assert a.route["tier"] == "C0" and a.requires_human_review
    assert "statistics" in p.gateway.handlers


def test_api_proposal_lineage_invalidation_and_permissions(platform):
    p, ctx = platform
    client = TestClient(create_app(p))
    headers = {"X-Tenant-Id": TENANT, "X-Actor-Id": "priya", "Idempotency-Key": "simulation-test-key"}
    body = {"samples": 2}
    response = client.post("/v1/process-model/runs", headers=headers, json=body)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["workspace"]["recommended_index"] is not None
    assert client.post("/v1/process-model/runs", headers=headers, json=body).json()["id"] == run["id"]
    assert client.post("/v1/process-model/runs", headers=headers, json={"samples": 3}).status_code == 409
    proposal = client.post(f"/v1/process-model/runs/{run['id']}/recommendation", headers={**headers, "Idempotency-Key": "propose-test-key"}, json={"owner_id": "priya"}).json()
    assert proposal["required_roles"] == ["qa", "msat"] and proposal["execution_status"] == "not_started"
    assert client.post("/v1/process-model/runs", headers=headers, json={"load_vials": -1}).status_code == 422
    p.identity.assign_role(TENANT, "outside", "msat", site_id="OTHER")
    outsider = {"X-Tenant-Id": TENANT, "X-Actor-Id": "outside"}
    assert client.get(f"/v1/process-model/runs/{run['id']}", headers=outsider).status_code == 403
    assert client.post("/v1/process-model/runs", headers=outsider, json=body).status_code == 403
    ref = run["source_revision_manifest"][0]
    original = json.loads(p.evidence.original(ctx, ref["id"]))
    original["config"]["equipment"]["revision"] = "2"
    original["config"]["equipment"]["vapor_capacity_kg_h"] = .4
    record = p.store.read().require(TENANT, "evidence", ref["id"])
    changed = p.evidence.ingest(ctx, source_system=record.state["source_system"], source_record_id=record.state["source_record_id"],
        content=json.dumps(original).encode(), media_type="application/json", site_id="NF1", event_time=None)
    assert f"process_simulation:{run['id']}" in changed["invalidated"]
    assert p.process_models.get(ctx, run["id"])["status"] == "stale"
    assert p.store.read().require(TENANT, "proposal", proposal["proposal_id"]).state["status"] == "stale"
    assert client.post(f"/v1/process-model/runs/{run['id']}/recommendation", headers=headers, json={"owner_id": "priya"}).status_code == 400


def test_unavailable_agent_attempt_is_recorded_without_mock(platform, tmp_path):
    p, ctx = platform
    observations = [{"time_h": t, "product_temperature_c": -35+t*.1} for t in range(7)]
    packet = public_packet(source_config(), observations, 6)
    protocol = json.loads(Path(model.__file__).with_name("protocol.json").read_text())
    result = attempt_agent(p, ctx, packet, tmp_path, protocol, "A")
    assert result["adapter_result"]["status"] == "unresolved"
    assert not result["measured_ai_performance"] and result["scientific_scores"] is None
    assert result["gateway_record"]["issues"] and not result["gateway_record"]["attempts"]


def test_host_tools_share_existing_prime_budget_and_cannot_override_evidence(tmp_path):
    from src.manufacturing_data import ManufacturingStore
    from src.prime_runtime.bridge import ManufacturingBridge
    from src.state import BlackboardStore
    from src.workflows import ManufacturingInvestigationWorkflow
    store = ManufacturingStore(tmp_path/"store")
    boards = BlackboardStore(tmp_path/"boards")
    workflow = ManufacturingInvestigationWorkflow(tmp_path/"workflow", store, scope="demo", blackboards=boards)
    calls = []
    def handler(**args):
        calls.append(args)
        return {"evidence_ids": [], "classification": "calculated_prediction"}
    bridge = ManufacturingBridge(store=store, blackboards=boards, workflow=workflow, scope="demo", incident_id="test",
        objective="test", as_of="2026-10-26T06:00:00Z", seed_ids=[], max_tool_calls=8, additional_tools={"physics": handler})
    assert bridge.tool("physics", {})["classification"] == "calculated_prediction"
    assert bridge.tool_calls == 1 and calls[0]["scopes"] == ["demo"]
    bridge.additional_tools = {"search_evidence": handler}
    with pytest.raises(ValueError, match="override"):
        bridge.tool("search_evidence", {})

