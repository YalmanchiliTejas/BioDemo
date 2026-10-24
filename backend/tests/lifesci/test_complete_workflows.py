"""Acceptance journeys through the public API and process boundaries."""
import json
import time
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.ownership import Ownership
from src.lifesci.store import RecordStore


def h(actor="designer"):
    return {"X-Tenant-Id": "T", "X-Actor-Id": actor}


def post(c, path, data=None, actor="designer"):
    r = c.post(path, json=data, headers=h(actor))
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.fixture
def world():
    p = Platform(RecordStore(), providers={})
    for actor, role, site in [("designer", "manufacturing_systems", None), ("op", "operator", "S1"),
                              ("qa", "qa", "S1"), ("receiver", "qa", "S2"), ("third", "operator", "S3"),
                              ("admin", "admin", None)]:
        p.identity.assign_role("T", actor, role, site_id=site)
    for kind in ("batch_record", "lab_record", "procedure", "recipe_instance", "result"):
        p.ownership.assign("T", Ownership(kind, "S1", "native", None, (), True, "test", "test-only"), by="fixture", reason="test")
    c = TestClient(create_app(p))
    post(c, "/v1/manufacturing/batches", {"batch_id": "B1", "product": "product", "modality": "mAb", "site_id": "S1"})
    return p, c


def publish(c, pid, definition, category="recipe", site="S1"):
    post(c, "/v1/procedures", {"procedure_id": pid, "name": pid, "category": category, "site_id": site, "definition": definition})
    prop = post(c, f"/v1/procedures/{pid}/submit", {"rationale": "review exact definition"})
    post(c, f"/v1/proposals/{prop['proposal_id']}/decisions", {"decision": "approved", "role": "qa", "expected_revision": 1,
         "authentication": {"method": "test_reauth"}}, "qa")
    post(c, f"/v1/procedures/{pid}/publish", {"approved_proposal_id": prop["proposal_id"]})


def test_advanced_recipe_parallel_branch_and_signature_journey(world):
    p, c = world
    definition = {"steps": [
        {"step_id": "check", "title": "pH", "kind": "data_entry", "parameters": [{"name": "ph", "unit": "pH", "low": 6, "high": 8}],
         "branch": {"condition": "ph > 7", "true_next": "hi", "false_next": "lo"}},
        {"step_id": "parallel", "title": "Parallel check", "kind": "instruction", "parallel_group": "prep"},
        {"step_id": "hi", "title": "High path", "kind": "instruction", "depends_on": ["check"]},
        {"step_id": "lo", "title": "Low path", "kind": "instruction", "depends_on": ["check"]},
        {"step_id": "sign", "title": "Sign", "kind": "signature", "depends_on": ["hi", "lo", "parallel"], "required_signatures": ["performed", "verified"]}]}
    publish(c, "ADV", definition)
    inst = post(c, "/v1/manufacturing/instances", {"procedure_id": "ADV", "batch_id": "B1", "site_id": "S1"}, "op")
    root = f"/v1/manufacturing/instances/{inst['instance_id']}"
    post(c, root + "/start", actor="op")
    for sid, values in [("check", {"ph": 7.2}), ("parallel", {}), ("hi", {}), ("sign", {})]:
        post(c, root + f"/steps/{sid}", {"values": values}, "op")
    post(c, root + "/steps/sign/sign", {"meaning": "performed", "authentication": {"method": "local_poc_confirmation"}}, "op")
    assert c.post(root + "/steps/sign/sign", json={"meaning": "verified", "authentication": {"method": "test"}}, headers=h("op")).status_code == 403
    post(c, root + "/steps/sign/sign", {"meaning": "verified", "authentication": {"method": "test"}}, "qa")
    record = c.get(root + "/batch-record", headers=h("qa")).json()
    assert record["instance_status"] == "completed"
    assert next(s for s in record["steps"] if s["step_id"] == "lo")["status"] == "skipped_branch"


def test_full_lab_method_to_plate_to_independent_result_release(world):
    _, c = world
    sample = post(c, "/v1/laboratory/samples", {"batch_id": "B1", "sample_type": "QC", "idempotency_key": "sample-0001", "volume": 10}, "op")
    sid = sample["sample_id"]
    children = post(c, f"/v1/laboratory/samples/{sid}/aliquots", {"n": 2, "volume": 1}, "op")
    assert len(children) == 2
    post(c, "/v1/laboratory/plates", {"plate_id": "P1", "plate_format": 96, "positions": {"A1": children[0]["sample_id"], "A2": children[1]["sample_id"]}}, "op")
    post(c, "/v1/laboratory/instruments/I1", {"site_id": "S1", "instrument_class": "meter", "calibration_due": "2999-01-01", "status": "ready"})
    definition = {"requires": {"instruments": [{"instrument_class": "meter"}]}, "steps": [
        {"step_id": "measure", "title": "Assay", "kind": "data_entry", "parameters": [{"name": "concentration", "unit": "mg/L", "low": 0, "high": 20}],
         "calculation": {"name": "corrected", "expr": "concentration * 2", "unit": "mg/L", "low": 0, "high": 40}}]}
    publish(c, "ASSAY", definition, "lab_method")
    run = post(c, "/v1/laboratory/runs", {"method_id": "ASSAY", "site_id": "S1", "instruments": ["I1"], "sample_ids": [sid]}, "op")
    post(c, f"/v1/laboratory/runs/{run['instance_id']}/steps/measure", {"values": {"concentration": 7}}, "op")
    result = post(c, f"/v1/laboratory/runs/{run['instance_id']}/results", {"sample_id": sid, "calculation": "corrected"}, "op")
    rid = result["result_id"]
    assert result["value"] == 14
    assert c.post(f"/v1/laboratory/results/{rid}/review", headers=h("op"), json={"decision": "approved"}).status_code == 403
    post(c, f"/v1/laboratory/results/{rid}/review", {"decision": "approved"}, "qa")
    released = post(c, f"/v1/laboratory/results/{rid}/release", actor="qa")
    assert released["status"] == "released"
    assert c.post(f"/v1/laboratory/samples/{sid}/results", headers=h("op"), json={"analyte": "corrected", "value": 99, "unit": "mg/L"}).status_code == 403


def test_transfer_receipt_gaps_revision_and_site_isolation(world):
    _, c = world
    publish(c, "REC", {"steps": [{"step_id": "one", "title": "Observe", "kind": "instruction"}]})
    transfer = post(c, "/v1/network/transfers", {"sending_site": "S1", "receiving_site": "S2", "product_id": "P", "procedure_refs": [
        {"kind": "procedure_revision", "id": "REC@1", "revision": 1}], "material_mapping": {"source": "destination"}})
    pid = transfer["package_id"]
    assert not c.get("/v1/network/transfers", headers=h("third")).json()["items"]
    assert c.get(f"/v1/records/transfer_package/{pid}", headers=h("third")).status_code == 403
    received = post(c, f"/v1/network/transfers/{pid}/receive", actor="receiver")
    gap = post(c, f"/v1/network/transfers/{pid}/readiness", {}, "receiver")
    assert gap["readiness"] == "not_ready"
    assert c.post(f"/v1/network/transfers/{pid}/approve", headers=h("receiver"), json={"role": "recipient", "expected_revision": received["revision"], "inventory": {}}).status_code == 400
    approved = post(c, f"/v1/network/transfers/{pid}/approve", {"role": "recipient", "expected_revision": received["revision"], "inventory": {"materials": ["destination"]}}, "receiver")
    post(c, f"/v1/network/transfers/{pid}/revisions", {"expected_revision": approved["revision"], "changes": {"parameters": {"temperature": 37}}})
    check = post(c, f"/v1/network/transfers/{pid}/readiness", {"materials": ["destination"]}, "receiver")
    assert not check["recipient_approved"]


def test_partner_login_grant_feedback_and_revocation(world):
    _, c = world
    post(c, "/v1/partners/members/external", {"partner_org_id": "CDMO"}, "admin")
    grant = post(c, "/v1/partners/batches/B1/grants", {"partner_org_id": "CDMO", "mode": "interactive", "expires_at": "2099-01-01T00:00:00Z"}, "qa")
    assert c.get("/v1/me", headers=h("external")).json()["actor_kind"] == "partner"
    assert c.get("/v1/partners/batches/B1", headers=h("external")).status_code == 200
    feedback = post(c, "/v1/partners/batches/B1/reviews", {"decision": "approve", "comment": "Reviewed"}, "external")
    assert feedback["effect"] == "recorded_feedback_only"
    assert not c.get("/v1/records/batch", headers=h("external")).json()["items"] == []
    post(c, f"/v1/partners/grants/{grant['grant_id']}/revoke", {"reason": "contract ended"}, "qa")
    assert c.get("/v1/partners/batches/B1", headers=h("external")).status_code == 403


def test_edge_restart_lost_ack_and_signed_receipt(world, tmp_path, monkeypatch):
    from src.lifesci.edge import EdgeAgent
    p, c = world
    monkeypatch.setenv("EDGE_TEST_SECRET", "long-secret-only-in-environment")
    monkeypatch.setenv("LIFESCI_CONNECTOR_FILE_ROOT", str(tmp_path))
    exports = tmp_path / "exports"; exports.mkdir()
    (exports / "data.json").write_text(json.dumps([{"id": "R1", "timestamp": "2026-10-24T00:00:00Z", "value": 7}]))
    post(c, "/v1/edge/gateways", {"gateway_id": "G", "site_id": "S1", "secret_env": "EDGE_TEST_SECRET"})
    config = {"gateway_id": "G", "tenant_id": "T", "site_id": "S1", "server_url": "http://127.0.0.1", "secret_env": "EDGE_TEST_SECRET", "state_path": str(tmp_path / "edge.db"),
              "connectors": [{"connector_id": "files", "family": "LIMS", "transport": "file", "options": {"directory": str(exports)}}]}
    lost = True
    def transport(data, headers):
        nonlocal lost
        r = c.post("/v1/edge/T/G/records", content=data, headers=headers)
        assert r.status_code == 200, r.text
        if lost:
            lost = False
            raise OSError("ack lost after server commit")
        return r.json()
    agent = EdgeAgent(config, transport)
    first = agent.tick()
    assert first["pending"] == 1 and first["error"]
    agent.close()
    restarted = EdgeAgent(config, transport)
    retry = restarted.tick()
    assert retry["pending"] == 0 and retry["captured"] == 0
    assert len(p.store.read().list("T", "evidence")) == 1
    assert c.post("/v1/edge/T/G/records", content=b"{}", headers={"X-Edge-Timestamp": str(int(time.time())), "X-Edge-Signature": "forged"}).status_code == 401
    restarted.close()


def test_livekit_room_api_and_token_scope(monkeypatch):
    import jwt
    from src.lifesci.media import LiveKitProvider
    provider = LiveKitProvider("ws://127.0.0.1:7880", "test-key", "test-secret-at-least-32-characters")
    calls = []
    monkeypatch.setattr(provider, "_call", lambda method, payload, grants: calls.append((method, payload, grants)) or {})
    room = provider.create_room("opaque-session")["room_id"]
    token = provider.join_token(room, "person@example.test", {"publish": True, "subscribe": True})
    claims = jwt.decode(token, provider.secret, algorithms=["HS256"], issuer=provider.key)
    assert claims["video"]["room"] == room and claims["video"]["roomJoin"]
    assert "@" not in claims["sub"] and not claims["video"]["canPublishData"]
    provider.remove_participant(room, "person@example.test")
    provider.close_room(room)
    assert [x[0] for x in calls] == ["CreateRoom", "RemoveParticipant", "DeleteRoom"]


def test_queued_flow_runs_in_a_restarted_worker(world):
    from src.lifesci.data_worker import tick
    p, c = world
    post(c, "/v1/intelligence/flows/F", {"site_id": "S1", "nodes": [{"node_id": "summary", "task_kind": "short_summary"}]})
    r = post(c, "/v1/intelligence/flows/F/runs", {"inputs": []})
    response = c.post(f"/v1/intelligence/runs/{r['run_id']}/queue", headers=h())
    assert response.status_code == 202
    assert p.store.read().require("T", "data_flow_run", r["run_id"]).state["queued"]
    assert tick(p, ["T"]) == 1
    state = p.store.read().require("T", "data_flow_run", r["run_id"]).state
    assert not state["queued"] and state["status"] == "blocked"
    assert tick(p, ["T"]) == 0


def test_media_access_monitor_removes_revoked_participant(world):
    from src.lifesci.collab import FakeMediaProvider
    p, c = world
    class Provider(FakeMediaProvider):
        removed = []
        def remove_participant(self, room, actor):
            self.removed.append((room, actor))
    provider = Provider()
    p.media_providers["test-media"] = provider
    post(c, "/v1/quality/cases", {"case_id": "C", "owner_id": "op", "qa_reviewer_id": "qa", "site_id": "S1"}, "op")
    session = post(c, "/v1/collaboration/sessions", {"case_id": "C", "participants": ["op", "qa"], "media_provider": "test-media"}, "op")
    p.identity.revoke_role("T", "qa", "qa", site_id="S1")
    p.remote_sessions.enforce_access("T")
    assert provider.removed == [(session["room_id"], "qa")]
    assert c.post(f"/v1/collaboration/sessions/{session['session_id']}/join", headers=h("qa")).status_code == 403


def test_synthetic_seed_preserves_edits_and_keeps_approval_manual():
    from src.lifesci.suite_seed import seed_suite
    p = Platform(RecordStore(), providers={})
    first = seed_suite(p)
    assert first["tenant"] == "demo-suite" and first["synthetic"]
    proposals = p.store.read().list("demo-suite", "proposal")
    assert len(proposals) == 2 and all(r.state["status"] == "proposed" for r in proposals)
    assert not p.store.read().list("demo-suite", "approval")
    before = p.store.read().require("demo-suite", "procedure", "SYNTHETIC-RECIPE").revision
    assert seed_suite(p)["already_seeded"]
    assert p.store.read().require("demo-suite", "procedure", "SYNTHETIC-RECIPE").revision == before


def test_unconfirmed_media_creation_and_end_remain_recoverable(world):
    from src.lifesci.media import MediaUnavailable
    p, c = world
    class FlakyMedia:
        create_calls = 0
        end_calls = 0
        def create_room(self, sid):
            self.create_calls += 1
            if self.create_calls == 1:
                raise MediaUnavailable("creation acknowledgement lost")
            return {"room_id": "bd-" + sid}
        def close_room(self, rid):
            self.end_calls += 1
            if self.end_calls == 1:
                raise MediaUnavailable("closure acknowledgement lost")
    p.media_providers["flaky"] = FlakyMedia()
    post(c, "/v1/quality/cases", {"case_id": "C", "owner_id": "op", "qa_reviewer_id": "qa", "site_id": "S1"}, "op")
    response = c.post("/v1/collaboration/sessions", headers=h("op"), json={"case_id": "C", "participants": ["op"], "media_provider": "flaky"})
    assert response.status_code == 503
    rec = p.store.read().list("T", "remote_session")[0]
    assert rec.state["status"] == "creation_unknown"
    active = post(c, f"/v1/collaboration/sessions/{rec.id}/reconcile", actor="op")
    assert active["status"] == "active"
    assert c.post(f"/v1/collaboration/sessions/{rec.id}/end", headers=h("op")).status_code == 503
    assert p.store.read().require("T", "remote_session", rec.id).state["status"] == "ending_unknown"
    p.remote_sessions.enforce_access("T")
    assert p.store.read().require("T", "remote_session", rec.id).state["status"] == "ended"
