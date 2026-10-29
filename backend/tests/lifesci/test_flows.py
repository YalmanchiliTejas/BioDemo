import pytest

from src.lifesci.container import Platform
from src.lifesci.flows import node_order
from src.lifesci.store import RecordStore, ConflictError


def env():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role("T", "msat", "msat", site_id="S1")
    return p, p.identity.context_for("T", "msat")


def nodes():
    return [{"node_id": "oee", "task_kind": "statistics", "payload": {"method": "oee", "params": {
        "planned_time": 480, "run_time": 432, "ideal_cycle_time": 1, "total_count": 400, "good_count": 392}}},
        {"node_id": "followup", "task_kind": "statistics", "depends_on": ["oee"], "payload": {"method": "oee", "params": {
            "planned_time": 480, "run_time": {"$node": "oee", "path": ["result", "availability"]},
            "ideal_cycle_time": 1, "total_count": 400, "good_count": 392}}}]


def test_pinned_definition_dependency_binding_and_resume():
    p, ctx = env()
    p.flows.save(ctx, "F", site_id="S1", nodes=nodes())
    run = p.flows.create_run(ctx, "F", inputs=[])
    p.flows.save(ctx, "F", site_id="S1", nodes=nodes()[:1], expected_revision=1)
    done = p.flows.run(ctx, run["run_id"])
    assert done["status"] == "completed" and done["flow_revision"] == 1
    assert len(done["results"]) == 2
    assert done["results"]["oee"]["output"]["result"]["availability"] == .9
    old_results = done["results"]
    assert p.flows.run(ctx, run["run_id"])["results"] == old_results
    assert not p.store.read().list("T", "action_intent")
    with pytest.raises(ConflictError):
        p.flows.save(ctx, "F", site_id="S1", nodes=nodes(), expected_revision=1)


def test_blocked_route_does_not_execute_downstream_and_scope_is_enforced():
    p, ctx = env()
    p.flows.save(ctx, "F", site_id="S1", nodes=[
        {"node_id": "model", "task_kind": "short_summary"},
        {"node_id": "later", "task_kind": "statistics", "depends_on": ["model"]}])
    run = p.flows.create_run(ctx, "F", inputs=[])
    result = p.flows.run(ctx, run["run_id"])
    assert result["status"] == "blocked" and "later" not in result["results"]
    p.identity.assign_role("T", "other", "msat", site_id="S2")
    with pytest.raises(PermissionError):
        p.flows.run(p.identity.context_for("T", "other"), run["run_id"])


def test_graph_errors_and_invalid_binding_are_explicit():
    with pytest.raises(ValueError, match="cycle"):
        node_order([{"node_id": "a", "depends_on": ["b"]}, {"node_id": "b", "depends_on": ["a"]}])
    with pytest.raises(ValueError, match="unknown dependency"):
        node_order([{"node_id": "a", "depends_on": ["missing"]}])
    p, ctx = env()
    bad = nodes()
    bad[1]["depends_on"] = []
    p.flows.save(ctx, "F", site_id="S1", nodes=bad)
    run = p.flows.create_run(ctx, "F", inputs=[])
    result = p.flows.run(ctx, run["run_id"])
    assert result["status"] == "blocked" and "explicit dependency" in result["issues"][0]


def test_corrected_source_blocks_replay():
    p, ctx = env()
    p.evidence.ingest(ctx, source_system="file", source_record_id="R", content=b"source", site_id="S1", media_type="text/plain", event_time=None)
    p.flows.save(ctx, "F", site_id="S1", nodes=nodes()[:1])
    run = p.flows.create_run(ctx, "F", inputs=[{"kind": "evidence", "id": "file:R", "revision": 1}])
    p.evidence.ingest(ctx, source_system="file", source_record_id="R", content=b"corrected source", site_id="S1", media_type="text/plain", event_time=None)
    with pytest.raises((PermissionError, ValueError)):
        p.flows.run(ctx, run["run_id"])


def test_checkpoint_survives_process_restart(tmp_path):
    path = str(tmp_path / "flows.db")
    p = Platform(RecordStore(path), providers={})
    p.identity.assign_role("T", "msat", "msat", site_id="S1")
    ctx = p.identity.context_for("T", "msat")
    definition = [nodes()[0], {"node_id": "summary", "task_kind": "short_summary", "depends_on": ["oee"]}]
    p.flows.save(ctx, "F", site_id="S1", nodes=definition)
    run = p.flows.create_run(ctx, "F", inputs=[])
    partial = p.flows.run(ctx, run["run_id"])
    assert partial["status"] == "blocked"
    first_task = partial["results"]["oee"]["run_id"]
    restarted = Platform(RecordStore(path), providers={})
    replay = restarted.flows.run(restarted.identity.context_for("T", "msat"), run["run_id"])
    assert replay["status"] == "blocked"
    assert replay["results"]["oee"]["run_id"] == first_task
    assert replay["results"]["summary"]["run_id"] != partial["results"]["summary"]["run_id"]


def test_quarantine_propagates_to_flow_outputs():
    p, ctx = env()
    p.evidence.ingest(ctx, source_system="file", source_record_id="R", content=b"source", site_id="S1", media_type="text/plain", event_time=None)
    p.flows.save(ctx, "F", site_id="S1", nodes=nodes()[:1])
    run = p.flows.create_run(ctx, "F", inputs=[{"kind": "evidence", "id": "file:R", "revision": 1}])
    p.flows.run(ctx, run["run_id"])
    p.evidence.quarantine_from(ctx, "evidence", "file:R", "withdrawn")
    assert p.store.read().require("T", "data_flow_run", run["run_id"]).state["status"] == "quarantined"
    with pytest.raises(ValueError, match="invalidated"):
        p.flows.run(ctx, run["run_id"])


def test_invalidation_during_computation_cannot_be_overwritten(monkeypatch):
    p, ctx = env()
    p.evidence.ingest(ctx, source_system="file", source_record_id="R", content=b"source", site_id="S1", media_type="text/plain", event_time=None)
    p.flows.save(ctx, "F", site_id="S1", nodes=nodes()[:1])
    run = p.flows.create_run(ctx, "F", inputs=[{"kind": "evidence", "id": "file:R", "revision": 1}])
    original = p.gateway.run
    def withdraw(request):
        result = original(request)
        p.evidence.quarantine_from(ctx, "evidence", "file:R", "withdrawn during computation")
        return result
    monkeypatch.setattr(p.gateway, "run", withdraw)
    with pytest.raises(PermissionError, match="invalidated"):
        p.flows.run(ctx, run["run_id"])
    assert p.store.read().require("T", "data_flow_run", run["run_id"]).state["status"] == "quarantined"


def test_host_operator_versions_are_pinned_and_context_is_preserved():
    p, ctx = env()
    calls = []
    def calculate(context, payload):
        calls.append((context.actor_id, payload))
        return {'status': 'completed', 'output': {'answer': payload['value']*2}, 'issues': []}
    p.flows.register_operator('test.domain', 'v1', calculate)
    p.flows.save(ctx, 'domain', site_id='S1', nodes=[{'node_id': 'calculate', 'task_kind': 'test.domain', 'payload': {'value': 21}}])
    first = p.flows.create_run(ctx, 'domain', inputs=[])
    done = p.flows.run(ctx, first['run_id'])
    assert done['results']['calculate']['output']['answer'] == 42
    assert calls == [('msat', {'value': 21})]
    second = p.flows.create_run(ctx, 'domain', inputs=[])
    p.flows.operators['test.domain'] = ('v2', calculate)
    blocked = p.flows.run(ctx, second['run_id'])
    assert blocked['status'] == 'blocked' and 'operator changed' in blocked['issues'][0]
    assert len(calls) == 1
    with pytest.raises(ValueError, match='already registered'):
        p.flows.register_operator('test.domain', 'v3', calculate)
