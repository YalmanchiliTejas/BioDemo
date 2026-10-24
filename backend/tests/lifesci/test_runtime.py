from datetime import timedelta

from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.ids import iso, utc_now
from src.lifesci.quality import CaseService
from src.lifesci.store import RecordStore


def setup():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role("T", "owner", "supervisor", site_id="S1")
    ctx = p.identity.context_for("T", "owner")
    m = p.missions.start_or_resume(ctx, objective="Watch records", owner_id="owner",
        scope={"site_ids": ["S1"]}, subscriptions=[{"type": "evidence.", "site_id": "S1"}])
    return p, ctx, m["mission_id"]


def test_api_ingestion_routes_subscribed_events_without_manual_delivery():
    p, ctx, mid = setup()
    c = TestClient(create_app(p))
    r = c.post("/v1/evidence", headers={"X-Tenant-Id": "T", "X-Actor-Id": "owner"},
        json={"source_system": "LIMS", "source_record_id": "r1", "content_text": "reading", "site_id": "S1"})
    assert r.status_code == 201
    assert len(p.missions.get(ctx, mid)["pending_event_ids"]) == 1
    p.runtime.tick()
    assert p.missions.get(ctx, mid)["pending_event_ids"] == []
    assert p.missions.get(ctx, mid)["attempts"] == 1


def test_runtime_executes_repeating_calculation_and_saves_reviewable_draft():
    p, ctx, mid = setup()
    p.missions.add_obligation(ctx, mid, description="Compute OEE", due_at=iso(utc_now()-timedelta(seconds=1)),
        every_minutes=60, task_kind="statistics", payload={"method": "oee", "params": {
            "planned_time": 480, "run_time": 432, "ideal_cycle_time": 1, "total_count": 400, "good_count": 392}})
    p.runtime.tick()
    ob = p.missions.get(ctx, mid)["obligations"][0]
    assert len(ob["completions"]) == 1
    assert ob["runtime_status"] == "completed" and ob["status"] == "open"
    artifact = p.store.read().require("T", "draft_artifact", ob["completions"][0]["artifact"]["id"])
    assert artifact.state["review_state"] == "draft_requires_review"
    assert artifact.state["sections"]["result"]["result"]["oee"] > .8
    p.runtime.tick()
    assert len(p.missions.get(ctx, mid)["obligations"][0]["completions"]) == 1


def test_runtime_generates_case_artifact_but_never_submits_it():
    p, ctx, mid = setup()
    CaseService(p.store, p.identity).open(ctx, "C1", "owner", "qa", "S1")
    p.missions.add_obligation(ctx, mid, description="Draft deviation", due_at=iso(utc_now()-timedelta(seconds=1)),
                             artifact_kind="deviation", case_id="C1")
    p.runtime.tick()
    ob = p.missions.get(ctx, mid)["obligations"][0]
    assert ob["status"] == "done"
    assert len(p.store.read().list("T", "draft_artifact")) == 1
    assert p.store.read().list("T", "action_intent") == []


def test_unqualified_model_obligation_remains_blocked_and_visible():
    p, ctx, mid = setup()
    p.missions.add_obligation(ctx, mid, description="Summarize", due_at=iso(utc_now()-timedelta(seconds=1)),
                             task_kind="short_summary")
    p.runtime.tick()
    ob = p.missions.get(ctx, mid)["obligations"][0]
    assert ob["runtime_status"] == "blocked" and ob["runtime_issues"]
    assert ob["completions"] == [] and ob["status"] == "open"


def test_restart_recovers_events_missed_by_commit_listener(monkeypatch, tmp_path):
    from src.lifesci.evidence import EvidenceService
    from src.lifesci.identity import IdentityService
    url = f"sqlite:///{tmp_path / 'runtime.db'}"
    store = RecordStore(url)
    p = Platform(store, providers={})
    p.identity.assign_role("T", "owner", "supervisor", site_id="S1")
    ctx = p.identity.context_for("T", "owner")
    m = p.missions.start_or_resume(ctx, objective="Recover source changes", owner_id="owner",
        scope={"site_ids": ["S1"]}, subscriptions=[{"type": "evidence."}])
    # Another process commits while the API listener is absent.
    external = RecordStore(url)
    EvidenceService(external, IdentityService(external)).ingest(ctx, source_system="LIMS", source_record_id="r1",
        content=b"changed", media_type="text/plain", site_id="S1", event_time=None)
    monkeypatch.setenv("LIFESCI_TENANTS", "T")
    restarted = Platform(RecordStore(url), providers={})
    restarted.runtime.tick()
    result = restarted.missions.get(ctx, m["mission_id"])
    assert result["attempts"] == 1 and result["pending_event_ids"] == []
