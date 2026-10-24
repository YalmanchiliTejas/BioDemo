from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.lifesci.api import create_app  # noqa: E402
from src.lifesci.container import Platform  # noqa: E402
from src.lifesci.ownership import Ownership  # noqa: E402
from src.lifesci.store import RecordStore  # noqa: E402

T = "tenant-a"


def test_derived_list_checks_every_source_and_quarantine(api):
    from src.lifesci.evidence import EvidenceRef
    client, h, p = api
    _ingest(client, h)
    p.evidence.record_derived(p.identity.context_for(T, "op1"), kind="summary", payload={"text": "secret"},
                              inputs=[EvidenceRef("evidence", "LIMS:R1", 1, "S1")], produced_by={})
    assert client.get("/v1/records/summary", headers=h("op2")).json()["items"] == []
    assert len(client.get("/v1/records/summary", headers=h("op1")).json()["items"]) == 1
    p.evidence.quarantine_from(p.identity.context_for(T, "op1"), "evidence", "LIMS:R1", "withdrawn")
    assert client.get("/v1/records/summary", headers=h("op1")).json()["items"] == []


def test_record_detail_supports_source_identifiers_with_slashes(api):
    client, h, _ = api
    _ingest(client, h, rid="plant/bioreactor/pH")
    r = client.get("/v1/records/evidence/LIMS:plant/bioreactor/pH", headers=h("op1"))
    assert r.status_code == 200 and r.json()["state"]["source_record_id"] == "plant/bioreactor/pH"
    assert client.get("/v1/records/evidence/LIMS:plant/bioreactor/pH", headers=h("op2")).status_code == 403


@pytest.fixture
def api():
    p = Platform(RecordStore(), providers={})
    for a, r in [("op1", "operator"), ("sup1", "supervisor"), ("msat1", "msat")]:
        p.identity.assign_role(T, a, r, site_id="S1")
    p.identity.assign_role(T, "op2", "operator", site_id="S2")
    p.ownership.assign(T, Ownership("place_hold", "S1", "external", "MES", ("place_hold",)), by="a", reason="c")
    client = TestClient(create_app(p))
    h = lambda actor, **extra: {"X-Tenant-Id": T, "X-Actor-Id": actor, **extra}  # noqa: E731
    return client, h, p


def _ingest(client, h, rid="R1", text="pH=7.1", key=None):
    headers = h("op1", **({"Idempotency-Key": key} if key else {}))
    return client.post("/v1/evidence", headers=headers, json={"source_system": "LIMS", "source_record_id": rid,
                                                             "content_text": text, "site_id": "S1"})


def test_LS042_idempotency_and_schema_errors(api):
    client, h, _ = api
    a = _ingest(client, h, key="key-00000001")
    b = _ingest(client, h, key="key-00000001")
    assert a.status_code == 201 and a.json() == b.json()
    assert _ingest(client, h, text="different", key="key-00000001").status_code == 409
    bad = client.post("/v1/evidence", headers=h("op1"), json={"source_system": "", "content_text": 3})
    assert bad.status_code == 422
    assert client.post("/v1/evidence", headers={}, json={}).status_code in (401, 422)


def test_roles_come_from_store_not_headers(api):
    client, h, _ = api
    _ingest(client, h)
    basis = [{"kind": "evidence", "id": "LIMS:R1", "revision": 1, "site_id": "S1"}]
    p = client.post("/v1/proposals", headers=h("op1"), json={
        "target_system": "MES", "operation": "place_hold", "target_id": "B1", "basis": basis,
        "rationale": "r", "expected_result": "e", "owner_id": "sup1", "site_id": "S1"}).json()
    spoof = client.post(f"/v1/proposals/{p['proposal_id']}/decisions", headers=h("op2", **{"X-Roles": "supervisor"}),
                        json={"expected_revision": 1, "decision": "approved", "role": "supervisor"})
    assert spoof.status_code == 403
    agent = client.post(f"/v1/proposals/{p['proposal_id']}/decisions", headers=h("sup1", **{"X-Actor-Kind": "agent"}),
                        json={"expected_revision": 1, "decision": "approved", "role": "supervisor"})
    assert agent.status_code == 403
    stale = client.post(f"/v1/proposals/{p['proposal_id']}/decisions", headers=h("sup1"),
                        json={"expected_revision": 9, "decision": "approved", "role": "supervisor"})
    assert stale.status_code == 409
    ok = client.post(f"/v1/proposals/{p['proposal_id']}/decisions", headers=h("sup1"),
                     json={"expected_revision": 1, "decision": "approved", "role": "supervisor"})
    assert ok.status_code == 200 and ok.json()["intent"]["status"] == "queued"


def test_pagination_and_site_filtering(api):
    client, h, p = api
    for i in range(5):
        _ingest(client, h, rid=f"R{i}")
    p.identity.assign_role(T, "op2", "operator", site_id="S2")
    first = client.get("/v1/records/evidence?limit=2", headers=h("op1")).json()
    second = client.get(f"/v1/records/evidence?limit=2&cursor={first['next_cursor']}", headers=h("op1")).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 2
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})
    assert client.get("/v1/records/evidence", headers=h("op2")).json()["items"] == []
    assert client.get("/v1/records/evidence/LIMS:R1", headers=h("op2")).status_code == 403
    assert client.get("/v1/records/grant", headers=h("op1")).status_code == 404


def test_mission_stream_replay_and_events(api):
    client, h, _ = api
    m = client.post("/v1/missions", headers=h("msat1"), json={"objective": "watch titer", "owner_id": "msat1",
                                                               "scope": {"site_ids": ["S1"]}}).json()
    s1 = client.get(f"/v1/missions/{m['mission_id']}/stream", headers=h("msat1")).json()
    client.post(f"/v1/missions/{m['mission_id']}/corrections", headers=h("msat1"), json={"text": "sensor fault"})
    s2 = client.get(f"/v1/missions/{m['mission_id']}/stream?after={s1['cursor']}", headers=h("msat1")).json()
    assert [e["type"] for e in s2["events"]] == ["mission.corrected"]
    assert s2["snapshot"]["corrections"][0]["text"] == "sensor fault"
    ev = client.get("/v1/events?after=0", headers=h("op1")).json()
    assert ev["cursor"] >= s2["cursor"]


def test_deterministic_task_and_health(api):
    client, h, _ = api
    health = client.get("/v1/health").json()
    assert health["models_available"] is False and "authorization" in health["continuing"]
    r = client.post("/v1/tasks", headers=h("msat1"), json={"task_kind": "statistics", "payload": {
        "method": "oee", "params": {"planned_time": 480, "run_time": 432, "ideal_cycle_time": 1.0,
                                                 "total_count": 400, "good_count": 392}}}).json()
    assert r["status"] == "completed", r["issues"]
    assert r["route"]["tier"] == "C0" and r["cost_usd"] == 0
    assert abs(r["output"]["result"]["oee"] - 0.9 * (400 / 432) * 0.98) < 1e-9
    blocked = client.post("/v1/tasks", headers=h("msat1"), json={"task_kind": "short_summary", "prompt": "x"}).json()
    assert blocked["status"] in ("unresolved", "blocked") and blocked["output"] is None


def test_ui_endpoints_me_missions_notes_proposals_outcomes():
    from src.lifesci.devseed import TENANT, seed
    p = Platform(RecordStore(), providers={})
    first, again = seed(p), seed(p)
    assert first["mission_id"] == again["mission_id"]  # idempotent seed
    client = TestClient(create_app(p))
    h = lambda actor: {"X-Tenant-Id": TENANT, "X-Actor-Id": actor}  # noqa: E731
    me = client.get("/v1/me", headers=h("quinn")).json()
    assert me["roles"] == ["qa"] and me["auth_mode"] == "development_headers"
    missions = client.get("/v1/missions", headers=h("priya")).json()["items"]
    mid = missions[0]["mission_id"]
    assert len(missions) == 1 and missions[0]["objective"].startswith("SYNTHETIC")
    assert client.get("/v1/missions", headers=h("stranger")).json()["items"] == []
    note = client.post(f"/v1/missions/{mid}/notes", headers=h("priya"), json={"body": "Check feed timing"}).json()
    assert client.get(f"/v1/missions/{mid}", headers=h("priya")).json()["notes"][0]["note_id"] == note["note_id"]
    basis = [first["evidence"][2]]
    prop = client.post("/v1/proposals", headers=h("priya"), json={
        "target_system": "QMS", "operation": "submit_deviation", "target_id": "F-2408", "basis": basis,
        "rationale": "Feed 2 started late", "expected_result": "deviation opened", "owner_id": "quinn",
        "follow_up_measure": "deviation_number", "site_id": "NF1", "mission_id": mid}).json()
    listed = client.get(f"/v1/missions/{mid}/proposals", headers=h("quinn")).json()["items"]
    assert listed[0]["proposal_id"] == prop["proposal_id"] and listed[0]["can_decide"] == ["qa"]
    assert client.get(f"/v1/missions/{mid}/proposals", headers=h("priya")).json()["items"][0]["can_decide"] == []
    client.post(f"/v1/proposals/{prop['proposal_id']}/decisions", headers=h("quinn"),
                json={"expected_revision": 1, "decision": "approved", "role": "qa"})
    after = client.get(f"/v1/missions/{mid}/proposals", headers=h("quinn")).json()["items"][0]
    assert after["status"] == "approved" and after["approvals"][0]["actor_id"] == "quinn" and after["can_decide"] == []
    out = client.post(f"/v1/proposals/{prop['proposal_id']}/outcomes", headers=h("quinn"), json={
        "observation": "QMS shows DEV-1", "measure": "deviation_number", "observed_value": "DEV-1",
        "evidence": basis, "attribution_limits": "record existence only"})
    assert out.status_code == 201


def test_stream_carries_proposal_events_and_proposal_reads():
    from src.lifesci.devseed import TENANT, seed
    p = Platform(RecordStore(), providers={})
    s = seed(p)
    client = TestClient(create_app(p))
    h = lambda actor, **x: {"X-Tenant-Id": TENANT, "X-Actor-Id": actor, **x}  # noqa: E731
    assert client.get("/v1/me", headers=h("typo-person")).status_code == 403
    mid = s["mission_id"]
    cursor = client.get(f"/v1/missions/{mid}/stream", headers=h("priya")).json()["cursor"]
    prop = client.post("/v1/proposals", headers=h("priya"), json={
        "target_system": "QMS", "operation": "submit_deviation", "target_id": "F-2408", "basis": [s["evidence"][1]],
        "rationale": "titer below spec", "expected_result": "deviation opened", "owner_id": "quinn",
        "site_id": "NF1", "mission_id": mid}).json()
    body = {"expected_revision": 1, "decision": "approved", "role": "qa"}
    first = client.post(f"/v1/proposals/{prop['proposal_id']}/decisions", headers=h("quinn", **{"Idempotency-Key": "decide-0001"}), json=body)
    again = client.post(f"/v1/proposals/{prop['proposal_id']}/decisions", headers=h("quinn", **{"Idempotency-Key": "decide-0001"}), json=body)
    assert first.status_code == 200 and again.json() == first.json()  # retried click does not double-decide
    types = [e["type"] for e in client.get(f"/v1/missions/{mid}/stream?after={cursor}", headers=h("priya")).json()["events"]]
    assert "action.proposed" in types and "action.approved" in types and "action.intent_queued" in types
    one = client.get(f"/v1/proposals/{prop['proposal_id']}", headers=h("priya")).json()
    assert one["status"] == "approved" and one["approvals"][0]["role"] == "qa" and one["can_decide"] == []
    listed = client.get(f"/v1/proposals?status=approved", headers=h("priya")).json()["items"]
    assert [x["proposal_id"] for x in listed] == [prop["proposal_id"]]
    assert client.get(f"/v1/missions", headers=h("priya")).json()["items"][0]["updated_at"]
