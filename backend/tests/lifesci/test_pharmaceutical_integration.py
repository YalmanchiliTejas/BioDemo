"""Scientific and production integration contracts, not customer validation."""

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from src.lifesci.evidence import EvidenceRef
from src.lifesci.process_engineering.catalog import ModelCatalog
from src.lifesci.process_engineering import hybrid, uncertainty, decisions
from src.lifesci.process_engineering.contracts import predict
from src.lifesci.process_engineering.engine import SolverBudget
from src.lifesci.process_engineering.library_examples import synthetic_runs, interval_rows
from src.lifesci.process_models.examples import examples


@pytest.fixture
def env():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role("pharma", "engineer", "msat", site_id="NF1")
    ctx = p.identity.context_for("pharma", "engineer")
    yield p, ctx
    p.runtime.close()
    p.store.release_connections()


def source(p, ctx, data, rid="packet", site="NF1"):
    e = p.evidence.ingest(
        ctx,
        source_system="pharma-test",
        source_record_id=rid,
        content=json.dumps(data, sort_keys=True).encode(),
        media_type="application/json",
        site_id=site,
        event_time=None,
        metadata={"classification": "synthetic_test_fixture"},
    )
    return {"kind": "evidence", "id": e["evidence_id"], "revision": e["revision"], "site_id": site}


def configured(p, ctx, mid="powder.two_bin_mill"):
    c = examples()[mid]
    ref = source(p, ctx, {"config": c})
    request = {
        "model_id": mid,
        "site_id": "NF1",
        "label": "Evidence-backed synthetic configuration",
        "config": c,
        "basis": [ref],
        "classification": "synthetic_assumption",
        "assumptions": ["Authored development fixture, no customer measurements"],
    }
    record = p.process_models.analysis.create_configuration(ctx, request)
    return record, ref, request


def spec(context, operation="simulate", **kw):
    return {
        "mode": "model_library",
        "simulation_id": context["id"],
        "model_id": context["model_id"],
        "objective": "Evaluate a family-specific evidence-backed model calculation",
        "operation": operation,
        "max_solver_calls": 96,
        **kw,
    }


def test_single_catalogue_reuses_legacy_models_and_declares_hybrid_limits():
    c = ModelCatalog(None)
    assert len(c.adapters) == 22
    assert len(ModelCatalog().adapters) == 2
    snapshot = c.snapshot()
    assert sum(d["hybrid_adaptation"]["supported"] for d in snapshot) == 2
    assert c.get("tablet.heckel_compaction").describe()["model_kind"] == "empirical"
    assert c.get("cho.monod_batch").describe()["model_kind"] == "semimechanistic"
    assert c.get("powder.two_bin_mill") is not None


def test_actual_service_persists_family_units_and_invalidates_on_source_change(env):
    p, ctx = env
    context, ref, request = configured(p, ctx)
    service = p.process_models.analysis
    plan = service.prepare(ctx, spec(context))
    result = service.execute(ctx, plan["id"])
    assert result["execution_status"] == "completed" and "vial" not in result["output"]
    assert result["model_manifest"][0]["analysis_contract"]["axis"] == "time_s"
    c = deepcopy(request["config"])
    c["breakage_rate_s_inv"] *= 2
    source(p, ctx, {"config": c})
    stale = p.store.read().require(ctx.tenant_id, "physical_analysis_result", result["id"])
    assert stale.state["status"] == "stale"
    old = service.get_result(ctx, result["id"])
    assert old["status"] == "stale" and "output" not in old
    fresh = service.refresh_configuration(ctx, context["id"])["context"]
    assert fresh["input_bundle"]["config"]["breakage_rate_s_inv"] == c["breakage_rate_s_inv"]
    new = service.execute(ctx, service.prepare(ctx, spec(fresh))["id"])
    assert new["execution_status"] == "completed"


def test_configuration_values_cannot_be_fabricated_and_cross_site_denied(env):
    p, ctx = env
    context, ref, request = configured(p, ctx)
    request["config"] = deepcopy(request["config"])
    request["config"]["breakage_rate_s_inv"] *= 3
    with pytest.raises(ValueError, match="differs"):
        p.process_models.analysis.create_configuration(ctx, request)
    p.identity.assign_role("pharma", "other", "msat", site_id="NF2")
    other = p.identity.context_for("pharma", "other")
    service = p.process_models.analysis
    result = service.execute(ctx, service.prepare(ctx, spec(context))["id"])
    with pytest.raises(PermissionError):
        service.get_result(other, result["id"])
    with pytest.raises(PermissionError):
        p.process_models.analysis._library_record(other, "physical_analysis_context", context["id"])


def test_library_api_uses_existing_pipeline_and_catalogue(env):
    p, ctx = env
    context, _, _ = configured(p, ctx)
    client = TestClient(create_app(p))
    headers = {"X-Tenant-Id": "pharma", "X-Actor-Id": "engineer"}
    response = client.get("/v1/process-model/catalog", headers=headers)
    assert response.status_code == 200 and len(response.json()["models"]) == 22
    prepared = client.post("/v1/process-model/pipelines", json=spec(context), headers=headers)
    assert prepared.status_code == 200, prepared.text
    result = client.post("/v1/process-model/pipelines/" + prepared.json()["id"] + "/execute", headers=headers)
    assert result.status_code == 200 and result.json()["execution_status"] == "completed"


def test_observable_units_and_solver_budget_are_enforced(env):
    p, ctx = env
    c = ModelCatalog(None).get("powder.two_bin_mill")
    cfg = examples()[c.id]
    with pytest.raises(ValueError, match="unit"):
        predict(c, cfg, [{"coordinate": 1.0, "observable": "coarse_mass_fraction", "unit": "K", "value": 1.0}])
    context, _, _ = configured(p, ctx)
    plan = p.process_models.analysis.prepare(
        ctx,
        spec(
            context,
            "sensitivity",
            max_solver_calls=1,
            options={
                "parameter": "breakage_rate_s_inv",
                "values": [0.001, 0.002],
                "observations": [
                    {"coordinate": 30.0, "observable": "coarse_mass_fraction", "unit": "mass fraction", "value": 0.8}
                ],
            },
        ),
    )
    result = p.process_models.analysis.execute(ctx, plan["id"])
    assert result["resource_usage"]["solver_calls"] == 1
    assert any(r["status"] == "failed" for r in result["output"]["scenarios"])


def test_whole_batch_site_and_augmentation_leakage_rejected():
    runs = synthetic_runs("chemical.parallel_batch")
    leaked = deepcopy(runs)
    leaked[-1]["batch_id"] = leaked[0]["batch_id"]
    with pytest.raises(ValueError, match="Batch leakage"):
        hybrid.partition(leaked)
    with pytest.raises(ValueError, match="site leaked"):
        hybrid.partition(runs, site_holdout=True)
    bad = deepcopy(runs)
    bad[-1].update(augmented=True, origin_run_id=bad[0]["run_id"])
    with pytest.raises(ValueError, match="Augmentation"):
        hybrid.partition(bad)
    bad = deepcopy(runs)
    bad[0]["evidence_cutoff"] = 1.0
    with pytest.raises(ValueError, match="unavailable"):
        hybrid.partition(bad)


@pytest.fixture(scope="module")
def trained():
    adapter = ModelCatalog(None).get("chemical.parallel_batch")
    runs = synthetic_runs(adapter.id)
    checkpoint = hybrid.train(adapter, runs, ensemble_size=2)
    return adapter, runs, checkpoint


def test_hybrid_preserves_conservation_bounds_and_physics_baseline(trained):
    a, runs, cp = trained
    c = runs[0]["config"]
    raw = a.run(c)
    learned = hybrid.run_hybrid(a, c, cp)
    n0 = c["recipe"]["initial_a_mol_m3"] * c["equipment"]["working_volume_m3"]
    for row in learned["trajectory"]:
        assert row["a_mol"] + row["product_mol"] + row["impurity_mol"] == pytest.approx(n0, rel=1e-7)
        assert min(row["a_mol"], row["product_mol"], row["impurity_mol"]) >= -1e-7
    for features in ([320.0, 0.5, 12.0, 200.0, 320.0], [1e4, -10.0, 500.0, 1e5, 1e4]):
        factors, outside = hybrid.factors(cp["members"][0], features)
        assert np.all((factors >= 0.25) & (factors <= 4.0))
    assert a.run(c) == raw
    zero = deepcopy(c)
    zero["chemistry"].update(product_rate_ref_s_inv=0.0, impurity_rate_ref_s_inv=0.0)
    out = hybrid.run_hybrid(a, zero, cp)
    assert out["product_yield_fraction"] == 0 and out["conversion_fraction"] == 0


def test_holdout_and_calibration_values_never_choose_neural_weights(trained):
    adapter, runs, checkpoint = trained
    changed = deepcopy(runs)
    for run in changed:
        if run["role"] in ("calibration", "test"):
            for row in run["observations"]:
                row["value"] += 100000
    other = hybrid.train(adapter, changed, ensemble_size=2)
    assert other["members"] == checkpoint["members"] and other["selected_model"] == checkpoint["selected_model"]
    assert "final_evaluation" not in checkpoint
    missing = deepcopy(runs)
    for r in missing:
        r["observations"] = [o for o in r["observations"] if o["observable"] == "temperature_k"]
    with pytest.raises(ValueError, match="Identifiable"):
        hybrid.train(adapter, missing, ensemble_size=2)


def test_adaptation_keeps_source_and_adapted_checkpoints_separate(trained):
    a, runs, cp = trained
    old = deepcopy(cp)
    receiver = synthetic_runs(a.id, seed=44, receiver=True)
    adapted = hybrid.train(a, receiver, parent=cp, ensemble_size=2)
    assert cp == old and adapted["source_checkpoint_hash"]
    assert all(m["source_penalty"] > 0 for m in adapted["members"])
    assert isinstance(adapted["negative_transfer"], bool)
    assert adapted["members"] != cp["members"]


def test_insufficient_and_synthetic_calibration_remain_uncalibrated(trained):
    a, runs, cp = trained
    cal = [deepcopy(r) for r in runs if r["role"] == "calibration"]
    for r in cal:
        r["observations"] = interval_rows(r)
    result = uncertainty.calibrate_intervals(a, cal, samples=2)
    assert result["status"] == "uncalibrated" and result["q"] is None and result["independent_calibration_groups"] == 0
    result = uncertainty.calibrate_intervals(a, cal[:2], checkpoint=cp, mode="hybrid", samples=2)
    assert result["q"] is None and result["risk_probability"] is None


def test_empirical_interval_order_statistic_and_disjoint_evaluation_contract(trained):
    # Metadata fixtures exercise the conditional measured-data contract; these
    # values are generated test fixtures and are NOT reported as real calibration.
    a, runs, _ = trained
    cal = [deepcopy(r) for r in runs if r["role"] == "calibration"]
    for r in cal:
        r["observations"] = interval_rows(r)
        r["evidence_classification"] = "measured_unverified"
        r["independence_basis"] = "Test fixture for an asserted independent experiment record"
    result = uncertainty.calibrate_intervals(a, cal, samples=2)
    assert result["status"] == "empirically_calibrated_conditional"
    assert result["q"] == sorted(result["calibration_scores"])[9]
    with pytest.raises(ValueError, match="independent calibration batches"):
        uncertainty.calibrate_intervals(a, cal + [cal[0]], samples=2)
    with pytest.raises(ValueError, match="untouched"):
        uncertainty.evaluate_intervals(a, cal, result)


def test_transfer_decision_never_substitutes_conversion_or_missing_quality():
    a = ModelCatalog(None).get("chemical.parallel_batch")
    c = synthetic_runs(a.id)[0]["config"]
    r = a.run(c)
    with pytest.raises(ValueError, match="conversion"):
        decisions.transfer_assessment(
            a,
            r,
            r,
            [
                {
                    "metric": "conversion_fraction",
                    "unit": "fraction",
                    "basis": "charged reactant",
                    "role": "yield",
                    "operator": ">=",
                    "limit": 0.5,
                }
            ],
        )
    q = decisions.transfer_assessment(
        a,
        r,
        r,
        [
            {
                "metric": "potency",
                "unit": "mg/g",
                "basis": "dry isolated API",
                "role": "quality",
                "operator": ">=",
                "limit": 0.9,
            }
        ],
    )
    assert q["conclusion"] == "withheld_missing_quality_evidence"
    q = decisions.transfer_assessment(
        a,
        r,
        r,
        [
            {
                "metric": "product_yield_fraction",
                "unit": "fraction",
                "basis": "desired_product_mol_per_initial_reactant_mol",
                "role": "yield",
                "method": "noninferiority",
                "operator": ">=",
                "margin": 0.05,
            }
        ],
    )
    assert q["checks"][0]["status"] == "indicative_only" and q["conclusion"] == "inconclusive_uncertainty"  # no ranges, no verdict


def test_independent_public_oxygen_data_are_retained_without_fake_replicates():
    base = Path(__file__).resolve().parents[2] / "src/lifesci/fermentation/data"
    assert (base / "oxygen_transfer_darus_5953.csv").is_file()
    doc = json.loads((base / "oxygen_transfer_darus_5953.provenance.json").read_text())
    assert "5953" in json.dumps(doc)


def test_checkpoint_and_calibration_round_trip_through_existing_evidence_service(env):
    p, ctx = env
    mid = "chemical.parallel_batch"
    runs = synthetic_runs(mid)
    train = [r for r in runs if r["role"] == "train"][:2]
    selection = [r for r in runs if r["role"] == "selection"][:1]
    calibration = [r for r in runs if r["role"] == "calibration"][:2]
    test = [r for r in runs if r["role"] == "test"][:1]
    for r in calibration + test:
        r["observations"] = interval_rows(r)
    selected = train + selection + calibration + test
    ref = source(p, ctx, {"config": train[0]["config"], "runs": selected}, "study")
    s = p.process_models.analysis
    context = s.create_configuration(
        ctx,
        {
            "model_id": mid,
            "site_id": "NF1",
            "label": "Synthetic reaction study",
            "config": train[0]["config"],
            "basis": [ref],
            "classification": "synthetic_assumption",
        },
    )
    dataset = s.import_runs(ctx, {"site_id": "NF1", "label": "Explicit whole synthetic run partitions", "source": ref})
    result = s.execute(
        ctx, s.prepare(ctx, spec(context, "train_hybrid", dataset_id=dataset["id"], options={"ensemble_size": 2}))["id"]
    )
    assert result["execution_status"] == "completed", result.get("error")
    checkpoint = next(a for a in result["artifacts"] if a["kind"] == "physical_model_checkpoint")
    stored = s._library_record(ctx, checkpoint["kind"], checkpoint["id"])
    assert stored["checkpoint"]["training_run_ids"] == [r["run_id"] for r in train]
    result = s.execute(
        ctx,
        s.prepare(
            ctx,
            spec(
                context,
                "calibrate_intervals",
                dataset_id=dataset["id"],
                checkpoint_id=checkpoint["id"],
                options={"samples": 2},
            ),
        )["id"],
    )
    assert result["execution_status"] == "completed", result.get("error")
    assert result["output"]["interval_calibration"]["status"] == "uncalibrated"
    calibration_id = next(a["id"] for a in result["artifacts"] if a["kind"] == "physical_interval_calibration")
    final = s.execute(
        ctx,
        s.prepare(
            ctx,
            spec(
                context,
                "evaluate_intervals",
                dataset_id=dataset["id"],
                checkpoint_id=checkpoint["id"],
                calibration_id=calibration_id,
            ),
        )["id"],
    )
    assert final["execution_status"] == "completed", final.get("error")
    assert final["output"]["abstentions"] == 1 and final["output"]["whole_run_coverage"] is None
    # Correcting the original packet invalidates source/adapted weights and bands too.
    source(p, ctx, {"config": train[0]["config"], "runs": selected, "correction": "new assay revision"}, "study")
    assert (
        p.store.read().require(ctx.tenant_id, "physical_model_checkpoint", checkpoint["id"]).state["status"] == "stale"
    )
    assert (
        p.store.read().require(ctx.tenant_id, "physical_interval_calibration", calibration_id).state["status"]
        == "stale"
    )


def test_negative_transfer_detects_measured_selection_degradation_and_blocks_use(env):
    p, ctx = env
    a = ModelCatalog(None).get("fermentation.oxygen_transfer")
    runs = synthetic_runs(a.id)
    cp = hybrid.train(a, runs, ensemble_size=2)
    receiver = synthetic_runs(a.id, seed=44, receiver=True)
    adapted = hybrid.train(a, receiver, parent=cp, ensemble_size=2)
    alternatives = [
        v["rmse_scaled"]
        for k, v in adapted["selection"].items()
        if k != "hybrid" and v["rmse_scaled"] is not None and not v["failed_predictions"]
    ]
    expected = adapted["selection"]["hybrid"]["rmse_scaled"] > min(alternatives) * 1.01 + 1e-8
    assert adapted["negative_transfer"] == expected and expected
    assert adapted["promotion"] == "withheld_negative_transfer"
    from src.lifesci.process_engineering.library_schemas import LibraryPipelineSpec

    request = LibraryPipelineSpec(
        simulation_id="context", model_id=a.id, objective="Reject harmful receiver adaptation", operation="simulate"
    )
    with pytest.raises(ValueError, match="Negative transfer"):
        p.process_models.analysis._library_compute(
            request,
            {"config": receiver[0]["config"], "checkpoint_id": {"checkpoint": adapted}},
            a,
            SolverBudget(10, 30),
        )


def test_feasible_experiments_are_ranked_for_an_explicit_decision():
    a = ModelCatalog(None).get("powder.two_bin_mill")
    c = examples()[a.id]
    candidates = [
        {
            "measurement": "Coarse mass fraction at 900 s",
            "measurement_resolution": 0.01,
            "cost": 1.0,
            "conditions": {"breakage_rate_s_inv": v},
        }
        for v in (0.0015, 0.004, -0.001)
    ]
    decision = {
        "observable": "coarse_mass_fraction",
        "unit": "mass fraction",
        "coordinate": 900.0,
        "threshold": 0.2,
        "distributions": [{"category": "parameter", "path": "breakage_rate_s_inv", "unit": "1/s", "std": 0.0002}],
    }
    ranked = decisions.rank_experiments(a, c, candidates, decision)
    assert ranked["ranked"][0]["conditions"]["breakage_rate_s_inv"] == 0.0015
    assert ranked["rejected"] and "not calibrated" in ranked["ranked"][0]["limitations"]


def test_cho_adapter_calls_existing_solver_without_rewriting_equations():
    from src.lifesci.bioprocess import cho

    adapter = ModelCatalog(None).get("cho.monod_batch")
    params = dict(zip(cho.NAMES, cho.STARTS[0]))
    config = {"parameters": params, "initial_viable_cell_density": 1.0, "initial_glucose": 8.0, "duration_h": 24.0}
    result = adapter.run(config)
    expected = cho.integrate(list(params.values()), [1.0, 8.0], 0.0, np.linspace(0, 24, 121))
    assert result["trajectory"][-1]["glucose"] == pytest.approx(expected[-1, 1])
    assert result["trajectory"][-1]["viable_cell_density"] == pytest.approx(expected[-1, 0])


def test_current_native_agent_tool_loop_configures_prepares_and_executes(env, monkeypatch):
    from src.lifesci.gateway.providers import Completion
    from src.lifesci.gateway.registry import Qualification

    p, ctx = env
    cfg = examples()["powder.two_bin_mill"]
    ref = source(p, ctx, {"config": cfg})

    class Provider:
        name = "anthropic"
        n = 0

        def chat(self, **kw):
            self.n += 1
            names = {t["function"]["name"] for t in kw["tools"]}
            assert "model_library_prepare" in names
            if self.n == 1:
                name = "model_library_configure"
                args = {
                    "model_id": "powder.two_bin_mill",
                    "site_id": "NF1",
                    "label": "Native-loop synthetic source",
                    "config": cfg,
                    "basis": [ref],
                    "classification": "synthetic_assumption",
                }
            elif self.n == 2:
                context = p.store.read().list("pharma", "physical_analysis_context")[-1]
                name = "model_library_prepare"
                args = spec({"id": context.id, "model_id": "powder.two_bin_mill"}, max_solver_calls=8)
            elif self.n == 3:
                plan = p.store.read().list("pharma", "physical_analysis_plan")[-1]
                name = "model_library_execute"
                args = {"plan_id": plan.id}
            else:
                return Completion("The model calculation is saved as an unvalidated draft.", 1, 1)
            return Completion(
                "", 1, 1, tool_calls=({"id": "native" + str(self.n), "name": name, "arguments": json.dumps(args)},)
            )

    monkeypatch.setenv("ASSISTANT_LOOP", "tools")
    provider = Provider()
    p.gateway.providers["anthropic"] = provider
    p.gateway.registry.qualify(
        Qualification(
            "investigation_planning",
            "anthropic-opus",
            "unit-contract",
            True,
            {"host": 1.0},
            {"host": 1.0},
            "Scripted host check, not AI validation",
            "test",
        )
    )
    thread = p.engineering_conversations.create(ctx, {"site_id": "NF1"})
    queued = p.engineering_conversations.enqueue(
        ctx,
        thread["id"],
        {
            "text": "Configure and simulate the pharmaceutical milling model from the recorded source.",
            "expected_revision": thread["revision"],
        },
    )
    p.engineering_conversations.run_turn(ctx, thread["id"], queued["turn_ids"][-1])
    view = p.engineering_conversations.get(ctx, thread["id"])
    turn = view["turns"][-1]
    assert turn["status"] == "completed", turn.get("issues")
    results = p.store.read().list("pharma", "physical_analysis_result")
    assert len(results) == 1 and results[0].state["execution_status"] == "completed"
    assert turn["solver_calls_used"] == 1
    assert all(s["status"] == "completed" for s in turn["steps"])
    assert not p.store.read().list("pharma", "action_intent")
    # The generic records endpoint cannot bypass private conversation ancestry.
    p.identity.assign_role("pharma", "another", "msat", site_id="NF1")
    other = p.identity.context_for("pharma", "another")
    with pytest.raises(PermissionError):
        p.process_models.analysis.get_result(other, results[0].id)
    client = TestClient(create_app(p))
    headers = {"X-Tenant-Id": "pharma", "X-Actor-Id": "another"}
    response = client.get("/v1/records/physical_analysis_result/" + results[0].id, headers=headers)
    assert response.status_code == 403


def test_fenced_worker_cannot_commit_scientific_result_after_cancellation(env):
    p, ctx = env
    context, _, _ = configured(p, ctx)
    s = p.process_models.analysis
    plan = s.prepare(ctx, spec(context))

    def cancelled(tx):
        raise PermissionError("Worker was cancelled or replaced")

    with pytest.raises(PermissionError):
        s.execute(ctx, plan["id"], commit_guard=cancelled)
    assert not p.store.read().list("pharma", "physical_analysis_result")


def test_existing_mission_reassesses_changed_equipment_without_new_user_message(env, monkeypatch):
    from src.lifesci.gateway.providers import Completion
    from src.lifesci.gateway.registry import Qualification
    from src.lifesci.roles import agent_context_for
    from src.lifesci.runtime import run_coordinator
    from src.lifesci.ids import iso, utc_now

    p, ctx = env
    context, ref, request = configured(p, ctx)
    service = p.engineering_conversations
    thread = service.create(ctx, {"site_id": "NF1"})
    thread = p.assistant_responsibilities.configure(
        ctx,
        thread["id"],
        {
            "enabled": True,
            "kinds": ["evidence"],
            "objective": "Keep this pharmaceutical milling assessment current after evidence corrections.",
            "expected_revision": thread["revision"],
            "acknowledge_inference": True,
            "max_runs": 1,
        },
    )

    class Provider:
        name = "anthropic"
        n = 0

        def chat(self, **kw):
            self.n += 1
            if self.n == 1:
                name, args = "model_library_refresh", {"context_id": context["id"]}
            elif self.n == 2:
                fresh = p.store.read().list("pharma", "physical_analysis_context")[-1]
                name, args = (
                    "model_library_prepare",
                    spec({"id": fresh.id, "model_id": context["model_id"]}, max_solver_calls=8),
                )
            elif self.n == 3:
                plan = p.store.read().list("pharma", "physical_analysis_plan")[-1]
                name, args = "model_library_execute", {"plan_id": plan.id}
            else:
                return Completion(
                    "The affected assessment was recalculated from the corrected source as a draft.", 1, 1
                )
            return Completion(
                "", 1, 1, tool_calls=({"id": "followup" + str(self.n), "name": name, "arguments": json.dumps(args)},)
            )

    monkeypatch.setenv("ASSISTANT_LOOP", "tools")
    p.gateway.providers["anthropic"] = Provider()
    p.gateway.registry.qualify(
        Qualification(
            "investigation_planning",
            "anthropic-opus",
            "mission-contract",
            True,
            {"host": 1.0},
            {"host": 1.0},
            "Test double only",
            "test",
        )
    )
    changed = deepcopy(request["config"])
    changed["breakage_rate_s_inv"] *= 1.5
    source(p, ctx, {"config": changed})
    p.missions.deliver_events(ctx.tenant_id)
    delegated = agent_context_for(ctx, p.identity)
    activation = p.missions.activate(delegated, thread["mission_id"], "pharma-test-worker")
    run_coordinator(p, delegated, activation, ["events"], iso(utc_now()))
    p.missions.release(activation)
    updated = service.get(ctx, thread["id"])
    assert len(updated["turns"]) == 1 and updated["turns"][0]["origin"] == "background"
    assert updated["turns"][0]["status"] == "completed", updated["turns"][0].get("issues")
    result = p.store.read().list("pharma", "physical_analysis_result")[-1]
    assert result.state["execution_status"] == "completed"
    assert (
        p.store.read()
        .list("pharma", "physical_analysis_context")[-1]
        .state["input_bundle"]["config"]["breakage_rate_s_inv"]
        == changed["breakage_rate_s_inv"]
    )


def test_measurement_and_parameter_uncertainty_propagate_without_changing_balances(trained):
    a, runs, cp = trained
    c = runs[0]["config"]
    obs = interval_rows(runs[0])
    obs = deepcopy(obs)
    obs[0]["measurement_std"] = 1.0
    result = uncertainty.ensemble(
        a,
        c,
        obs,
        samples=4,
        distributions=[
            {"category": "parameter", "path": "chemistry.product_rate_ref_s_inv", "unit": "1/s", "std": 0.00001}
        ],
    )
    assert (
        result["status"] == "completed"
        and result["calibration_status"] == "uncalibrated"
        and result["risk_probability"] is None
    )
    assert len(set(v[0] for v in result["physical_predictions"])) > 1
    assert result["uncertainty_components"]["measurement"]["declared_output_std"] == [1.0]
    assert result["uncertainty_components"]["parameter"]
    with pytest.raises(ValueError, match="path/unit"):
        uncertainty.ensemble(
            a,
            c,
            obs,
            samples=2,
            distributions=[
                {"category": "parameter", "path": "chemistry.product_rate_ref_s_inv", "unit": "K", "std": 0.00001}
            ],
        )


def test_ood_and_failed_predictions_never_produce_calibrated_risk(trained):
    a, runs, cp = trained
    c = deepcopy(runs[0]["config"])
    c["equipment"]["heat_transfer_coefficient_w_m2_k"] = 1000.0
    p = uncertainty.ensemble(a, c, interval_rows(runs[0]), checkpoint=cp, mode="hybrid", samples=2)
    assert p["out_of_domain_predictions"] and p["abstention"] and p["risk_probability"] is None
    c["recipe"]["initial_temperature_k"] = 500.0
    p = uncertainty.ensemble(a, c, interval_rows(runs[0]), checkpoint=cp, mode="hybrid", samples=2)
    assert p["status"] == "failed" and p["failed_predictions"] == 2 and p["risk_probability"] is None


def extension_request(context, result, revision=1, **overrides):
    request = {
        "context_id": context["id"],
        "model_id": context["model_id"],
        "basis": [
            {"kind": "physical_analysis_result", "id": result["id"], "revision": revision, "site_id": "NF1"}
        ],
        "mechanism_change": "Add attrition of fines into a third size class observed in receiving-site sieve data.",
        "affected_equations": "dm_fines/dt = k_att * m_fine; dm_fine/dt gains -k_att * m_fine; total mass unchanged.",
        "new_parameters": [
            {
                "name": "attrition_rate_s_inv",
                "unit": "1/s",
                "lower_bound": 0.0,
                "upper_bound": 0.01,
                "identifying_measurement": "Sieve fractions below 45 um at three residence times",
            }
        ],
        "conservation_impact": "Sum of the three size-class masses remains equal to the charged mass.",
        "limiting_case": "With attrition_rate_s_inv = 0 the extended model reproduces the current two-bin mill.",
        "verification_plan": "Mass closure unit test, zero-rate equivalence test, then held-out sieve batches.",
        "owner_id": "engineer",
    }
    return {**request, **overrides}


def test_mechanism_change_creates_review_proposal_without_changing_registered_model(env):
    p, ctx = env
    context, _, _ = configured(p, ctx)
    service = p.process_models.analysis
    result = service.execute(ctx, service.prepare(ctx, spec(context))["id"])
    revision = p.store.read().require("pharma", "physical_analysis_result", result["id"]).revision
    adapter = service.catalog.get(context["model_id"])
    digest, version = adapter.digest, adapter.version
    proposal = service.propose_model_extension(ctx, extension_request(context, result, revision))
    assert proposal["operation"] == "review_model_extension" and proposal["status"] == "proposed"
    assert proposal["payload"]["registry_status"] == "unchanged"
    assert proposal["payload"]["execution_permission"] == "none"
    assert proposal["payload"]["current_model"]["implementation_digest"] == digest
    assert "engineering" in proposal["required_roles"]
    # The registered equations and their digest are untouched; the result stays current.
    assert service.catalog.get(context["model_id"]).digest == digest and adapter.version == version
    assert service.get_result(ctx, result["id"])["execution_status"] == "completed"
    assert not p.store.read().list("pharma", "action_intent")


def test_mechanism_proposal_rejects_refits_mismatches_and_foreign_evidence(env):
    p, ctx = env
    context, _, _ = configured(p, ctx)
    service = p.process_models.analysis
    result = service.execute(ctx, service.prepare(ctx, spec(context))["id"])
    refit = extension_request(context, result)
    refit["new_parameters"] = [{**refit["new_parameters"][0], "name": "breakage_rate_s_inv"}]
    with pytest.raises(ValueError, match="refitted"):
        service.propose_model_extension(ctx, refit)
    with pytest.raises(ValueError, match="target the model"):
        service.propose_model_extension(ctx, extension_request(context, result, model_id="tablet.heckel_compaction"))
    foreign = extension_request(context, result)
    foreign["basis"][0]["site_id"] = "NF2"
    with pytest.raises(PermissionError):
        service.propose_model_extension(ctx, foreign)
    p.identity.assign_role("pharma", "other", "msat", site_id="NF2")
    with pytest.raises(PermissionError):
        service.propose_model_extension(p.identity.context_for("pharma", "other"), extension_request(context, result))


def test_mechanism_proposal_api_route(env):
    p, ctx = env
    context, _, _ = configured(p, ctx)
    service = p.process_models.analysis
    result = service.execute(ctx, service.prepare(ctx, spec(context))["id"])
    client = TestClient(create_app(p))
    headers = {"X-Tenant-Id": "pharma", "X-Actor-Id": "engineer"}
    response = client.post(
        "/v1/process-model/model-extension-proposals", json=extension_request(context, result), headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["operation"] == "review_model_extension"


def test_library_prepare_names_the_existing_context_and_preserves_legacy_api():
    from src.lifesci.process_engineering.library_schemas import LibraryPipelineSpec
    base = {'model_id': 'chemical.parallel_batch', 'objective': 'Simulate an existing saved source', 'operation': 'simulate'}
    schema = LibraryPipelineSpec.model_json_schema()
    assert 'context_id' in schema['required'], 'The agent must choose a saved configuration, not invent a new simulation name'
    current = LibraryPipelineSpec.model_validate({**base, 'context_id': 'existing-source-record'})
    legacy = LibraryPipelineSpec.model_validate({**base, 'simulation_id': 'existing-source-record'})
    assert current.simulation_id == legacy.simulation_id == 'existing-source-record'
    assert current.model_dump() == legacy.model_dump()
    with pytest.raises(ValueError, match='context_id'):
        LibraryPipelineSpec.model_validate({**base, 'context_id': 'right-record', 'simulation_id': 'invented-run-name'})


def test_native_library_read_can_back_memory_without_an_extra_workspace_read(env, monkeypatch):
    from src.lifesci.gateway.providers import Completion
    from src.lifesci.gateway.registry import Qualification
    p, ctx = env
    context, _, _ = configured(p, ctx)
    plan = p.process_models.analysis.prepare(ctx, spec(context, max_solver_calls=4))
    result = p.process_models.analysis.execute(ctx, plan['id'])

    class Provider:
        name = 'anthropic'
        n = 0
        def chat(self, **kw):
            self.n += 1
            if self.n == 1:
                name, args = 'model_library_read', {'kind':'physical_analysis_result', 'record_id':result['id']}
            elif self.n == 2:
                name, args = 'remember', {'text':'This authored synthetic calculation remains conditional and requires review.',
                    'kind':'warning', 'basis':'calculated', 'sources':[{'kind':'physical_analysis_result','id':result['id']}]}
            else:
                return Completion('The inspected synthetic result is saved as a conditional warning.',1,1)
            return Completion('',1,1,tool_calls=({'id':'read-memory-'+str(self.n),'name':name,'arguments':json.dumps(args)},))
    monkeypatch.setenv('ASSISTANT_LOOP','tools')
    p.gateway.providers['anthropic'] = Provider()
    p.gateway.registry.qualify(Qualification('investigation_planning','anthropic-opus','host-memory-test',True,
        {'host':1.0},{'host':1.0},'Scripted host verification, not AI qualification','test'))
    service = p.engineering_conversations
    thread = service.create(ctx, {'site_id':'NF1'})
    queued = service.enqueue(ctx,thread['id'],{'text':'Inspect the saved model result and remember its synthetic limitation.', 'expected_revision':thread['revision']})
    service.run_turn(ctx,thread['id'],queued['turn_ids'][-1])
    view = service.get(ctx,thread['id'])
    assert all(step['status']=='completed' for step in view['turns'][-1]['steps']), view['turns'][-1]['steps']
    notes = p.agent_memory.notes(ctx)
    assert len(notes)==1 and notes[0]['sources'][0]['id']==result['id']
    # A receipt is tied to the inspected revision; it must not bless a later edit.
    with p.store.transaction(ctx.actor_id) as tx:
        prior = tx.require(ctx.tenant_id,'physical_analysis_result',result['id'])
        tx.put(ctx.tenant_id,prior.kind,prior.id,{**prior.state,'warnings':['Updated after inspection']},
               expected_revision=prior.revision,action='test_changed_inspected_result')
    with pytest.raises((ValueError, PermissionError)):
        p.agent_memory.remember(ctx,view,view['turns'][-1]['id'],text='This changed result has not been inspected again.',
            kind='warning',basis='calculated',sources=[{'kind':'physical_analysis_result','id':result['id']}])


def _yield_band(result, lower, upper, status="empirically_calibrated_conditional"):
    end = result["trajectory"][-1]["time_s"]
    return {"basis": [["product_yield_fraction", "fraction", end]], "calibrated_lower": [lower],
            "calibrated_upper": [upper], "calibration_status": status}


YIELD = {"metric": "product_yield_fraction", "unit": "fraction", "role": "yield", "operator": ">=",
         "basis": "desired_product_mol_per_initial_reactant_mol"}


def test_a_transfer_verdict_needs_the_whole_calibrated_range_on_one_side_of_the_limit():
    a = ModelCatalog(None).get("chemical.parallel_batch")
    r = a.run(synthetic_runs(a.id)[0]["config"])
    limit = r["product_yield_fraction"] - 0.001  # the single estimate clears the limit by a hair
    crit = [{**YIELD, "limit": limit}]
    alone = decisions.transfer_assessment(a, r, r, crit)
    assert alone["checks"][0]["status"] == "indicative_only" and alone["conclusion"] == "inconclusive_uncertainty"
    synthetic = decisions.transfer_assessment(a, r, r, crit, receiver_interval=_yield_band(r, limit + .01, limit + .05, "calibrated_synthetic_only"))
    assert synthetic["checks"][0]["status"] == "indicative_only"
    cases = {(limit + .01, limit + .05): "conditional_pass", (limit - .02, limit + .02): "inconclusive", (limit - .05, limit - .01): "fails_criterion"}
    for (lo, hi), expected in cases.items():
        assert decisions.transfer_assessment(a, r, r, crit, receiver_interval=_yield_band(r, lo, hi))["checks"][0]["status"] == expected
    # A range that stops before the end of the run says nothing about the end-of-run yield.
    early = {**_yield_band(r, limit + .01, limit + .05), "basis": [["product_yield_fraction", "fraction", 1.0]]}
    assert decisions.transfer_assessment(a, r, r, crit, receiver_interval=early)["checks"][0]["status"] == "indicative_only"


def test_noninferiority_uses_the_difference_of_calibrated_ranges_in_the_stated_direction():
    a = ModelCatalog(None).get("chemical.parallel_batch")
    r = a.run(synthetic_runs(a.id)[0]["config"])
    crit = [{**YIELD, "method": "noninferiority", "margin": 0.05}]
    donor = _yield_band(r, .60, .62)
    status = lambda lo, hi: decisions.transfer_assessment(a, r, r, crit, donor_interval=donor,
                                                          receiver_interval=_yield_band(r, lo, hi))["checks"][0]["status"]
    assert status(.58, .63) == "conditional_pass"  # worst case .58 - .62 = -.04 >= -.05
    assert status(.55, .63) == "inconclusive"
    assert status(.50, .54) == "fails_criterion"  # even the best case, .54 - .60 = -.06, is worse than -.05


def test_interval_calibration_spends_solver_calls_only_on_the_bands_and_never_extrapolates():
    a = ModelCatalog(None).get("chemical.parallel_batch")
    cal = [r for r in synthetic_runs(a.id) if r["role"] == "calibration"]
    for r in cal:
        r["evidence_classification"] = "measured"
        r["independence_basis"] = "Test fixture for an asserted independent experiment record"
    budget = SolverBudget(512, 120)
    result = uncertainty.calibrate_intervals(a, cal, samples=3, budget=budget)
    assert budget.calls == 3 * len(cal)  # no per-source diagnostic solves inside calibration
    key, (lo, hi) = next((k, v) for k, v in result["input_support"].items() if v[1] > v[0])
    config = deepcopy(cal[0]["config"])
    from src.lifesci.process_engineering.contracts import set_value
    set_value(config, key, hi + 0.01 * (hi - lo))  # 1 % beyond what calibration covered
    p = uncertainty.interval_prediction(a, config, cal[0]["observations"], result)
    assert key in p["unsupported_input_conditions"] and p["calibrated_lower"] is None
def test_only_uncertain_terms_are_fittable_never_sizes_charges_or_set_points():
    from src.lifesci.process_engineering.contracts import FITTABLE, contract, fit_runs
    catalog = ModelCatalog(None)
    for mid, names in FITTABLE.items():
        assert set(names) <= set(catalog.get(mid).inputs), mid
        assert set(contract(catalog.get(mid))["fit_parameters"]) == set(names), mid
    with pytest.raises(ValueError, match="not designated"):
        fit_runs(catalog.get("isolation.cake_filter"), [], "filter_area_m2", [0.1, 1.0], SolverBudget(4, 5))


# --- pre-transfer check: equipment capability and model-based verdicts --------------------------------------------

def _transfer_demo(p, ctx):
    from src.lifesci.demo_seed import library_examples
    ids = {}
    for mid, label, config in library_examples():
        if mid == "chemical.parallel_batch":
            ref = source(p, ctx, {"config": config}, rid=label)
            ids[label] = p.process_models.analysis.create_configuration(ctx, {
                "model_id": mid, "site_id": "NF1", "label": label, "config": config, "basis": [ref],
                "classification": "synthetic_assumption", "assumptions": ["Authored transfer example"]})["id"]
    sending = next(i for k, i in ids.items() if "receiving" not in k)
    a, b = (next(i for k, i in ids.items() if f"option {x}" in k) for x in "AB")
    return sending, a, b


CRITERIA = [{**YIELD, "limit": 0.85}, {"metric": "impurity_fraction", "unit": "fraction", "role": "quality", "operator": "<=",
                                      "basis": "impurity_mol_per_initial_reactant_mol", "limit": 0.08}]
U_UNMEASURED = {"path": "equipment.heat_transfer_coefficient_w_m2_k", "unit": "W/(m2 K)", "low": 245.0, "high": 455.0,
                "basis": "engineering_assumption", "source": "Receiving jacket U not measured; vendor value +-30 %"}


def _check(p, ctx, sending, receiver, tolerances=()):
    s = p.process_models.analysis
    plan = s.prepare(ctx, {"mode": "model_library", "context_id": sending, "receiver_context_id": receiver,
                           "model_id": "chemical.parallel_batch", "objective": "Pre-transfer check, 10 L to 100 L",
                           "operation": "assess_transfer", "options": {"criteria": CRITERIA, "tolerances": list(tolerances)}})
    result = s.execute(ctx, plan["id"])
    assert result["execution_status"] == "completed", result["error"]
    return result["output"]


def test_pre_transfer_check_catches_the_vessel_that_cannot_remove_the_reaction_heat(env):
    p, ctx = env
    sending, option_a, option_b = _transfer_demo(p, ctx)
    out = _check(p, ctx, sending, option_a)
    heat = next(c for c in out["equipment_capability"]["checks"] if c["capability"].startswith("Heat removal"))
    assert heat["status"] == "short" and heat["receiving_capacity"] < heat["receiving_need"]
    assert heat["sending_capacity"] > heat["sending_need"]  # the 10 L reactor copes: the gap is the new vessel's
    assert {c["status"] for c in out["checks"]} == {"model_based_fail"} and out["conclusion"] == "criteria_not_met"
    assert "temperature_limit_reached" in out["checks"][0]["reason"]
    assert {c["input"] for c in out["what_changes"]} >= {"equipment.working_volume_m3", "equipment.heat_transfer_coefficient_w_m2_k"}
    # Option B: one nominal estimate is not a verdict; over the unmeasured U, yield clears 0.85 everywhere, impurity does not.
    assert {c["status"] for c in _check(p, ctx, sending, option_b)["checks"]} == {"indicative_only"}
    out = _check(p, ctx, sending, option_b, [U_UNMEASURED])
    by = {c["metric"]: c for c in out["checks"]}
    assert by["product_yield_fraction"]["status"] == "model_based_pass" and by["product_yield_fraction"]["receiver_range"][0] >= 0.85
    lo, hi = by["impurity_fraction"]["receiver_range"]
    assert by["impurity_fraction"]["status"] == "inconclusive" and lo <= 0.08 <= hi
    assert out["conclusion"] == "inconclusive_uncertainty" and out["tolerances"][0]["source"]


def test_a_stop_within_tolerance_is_at_risk_and_tolerances_must_be_sourced_and_bracket_the_value(env):
    p, ctx = env
    sending, _, option_b = _transfer_demo(p, ctx)
    low_u = {**U_UNMEASURED, "low": 60.0}  # a badly fouled jacket: the batch overheats at that corner
    out = _check(p, ctx, sending, option_b, [low_u])
    assert out["conclusion"] == "at_risk_within_tolerances"
    assert out["checks"][0]["stopping_corners"][0]["tolerances"] == {"equipment.heat_transfer_coefficient_w_m2_k": 60.0}
    s = p.process_models.analysis
    for bad in ({**U_UNMEASURED, "source": ""}, {**U_UNMEASURED, "low": 400.0}, {**U_UNMEASURED, "unit": "W/K"},
                {**U_UNMEASURED, "path": "recipe.duration_s", "unit": "s"}):
        with pytest.raises(ValueError):  # refused when the plan is prepared, before any execution is spent
            s.prepare(ctx, {"mode": "model_library", "context_id": sending, "receiver_context_id": option_b,
                            "model_id": "chemical.parallel_batch", "objective": "Pre-transfer check, invalid tolerance",
                            "operation": "assess_transfer", "options": {"criteria": CRITERIA, "tolerances": [bad]}})
    with pytest.raises(ValueError, match="numeric limit"):
        s.prepare(ctx, {"mode": "model_library", "context_id": sending, "receiver_context_id": option_b,
                        "model_id": "chemical.parallel_batch", "objective": "Pre-transfer check, missing limit",
                        "operation": "assess_transfer", "options": {"criteria": [{**CRITERIA[0], "limit": None}]}})


def test_library_options_sent_as_json_text_are_accepted_and_garbage_is_refused():
    from src.lifesci.process_engineering.library_schemas import LibraryPipelineSpec
    base = {"context_id": "phys_x", "model_id": "chemical.parallel_batch", "objective": "Pre-transfer check", "operation": "assess_transfer"}
    assert LibraryPipelineSpec.model_validate({**base, "options": '{"criteria": []}'}).options == {"criteria": []}
    with pytest.raises(ValueError):
        LibraryPipelineSpec.model_validate({**base, "options": "criteria: yield >= 0.85"})
