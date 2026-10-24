from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.lifesci.evidence import EvidenceService
from src.lifesci.gateway import FakeProvider, ModelGateway, TaskRequest, default_registry
from src.lifesci.gateway.registry import Qualification
from src.lifesci.identity import IdentityService
from src.lifesci.missions import MissionService
from src.lifesci.roles import SKILLS, agent_context_for, effective_scope
from src.lifesci.store import ConflictError, LeaseError, RecordStore
from src.lifesci.workqueue import Backpressure, QueuePolicy, WorkQueue

T = "tenant-a"


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    for a, r in [("msat1", "msat"), ("qa1", "qa"), ("op1", "operator"), ("sup1", "supervisor")]:
        idn.assign_role(T, a, r, site_id="S1")
    idn.assign_role(T, "outsider", "msat", site_id="S2")
    m = MissionService(s, idn)
    ev = EvidenceService(s, idn)
    ctx = lambda a: idn.context_for(T, a)  # noqa: E731
    mission = m.start_or_resume(ctx("msat1"), objective="Keep campaign C7 within expected titer",
                                owner_id="msat1", scope={"site_ids": ["S1"], "campaign": "C7"},
                                constraints=["no parameter change without QA approval"],
                                subscriptions=[{"type": "evidence.", "site_id": "S1"}])
    return SimpleNamespace(s=s, idn=idn, m=m, ev=ev, ctx=ctx, mid=mission["mission_id"])


def ingest(env, rid, content=b"x", site="S1"):
    return env.ev.ingest(env.ctx("op1"), source_system="HIST", source_record_id=rid, content=content,
                         media_type="text/plain", site_id=site, event_time=None)


def test_LS051_worker_loss_resumes_same_mission_with_unresolved_state(env):
    env.m.add_obligation(env.ctx("msat1"), env.mid, description="daily trend review", due_at="2026-01-01T00:00:00+00:00",
                         every_minutes=1440, task_kind="statistics")
    d = env.m.request_decision(env.ctx("msat1"), env.mid, question="Extend sampling?", options=["yes", "no"],
                               decider_role="qa", basis=[])
    w1 = env.m.activate(env.ctx("msat1"), env.mid, "worker-1")
    env.m.checkpoint(w1, progress={"step": 3, "done": ["load", "trend"]}, remaining_work=["compare cohorts"])
    # worker-1 dies; a new worker takes over
    w2 = env.m.takeover(env.ctx("msat1"), env.mid, "worker-2")
    assert w2.token > w1.token
    resumed = env.m.start_or_resume(env.ctx("msat1"), objective="ignored", owner_id="x", scope={}, mission_id=env.mid)
    assert resumed["resumed"] and resumed["objective"].startswith("Keep campaign")
    assert resumed["remaining_work"] == ["compare cohorts"]
    assert [x["decision_id"] for x in resumed["pending_decisions"] if x["status"] == "pending"] == [d["decision_id"]]
    assert env.m.resume_point(env.ctx("msat1"), env.mid)["progress"]["step"] == 3
    assert env.m.due_obligations(env.ctx("msat1"), env.mid)
    with pytest.raises(LeaseError):  # obsolete worker cannot publish
        env.m.checkpoint(w1, progress={"step": 99})
    assert env.m.resume_point(env.ctx("msat1"), env.mid)["progress"]["step"] == 3


def test_LS084_single_coordinator_and_child_basis_merge(env):
    w = env.m.activate(env.ctx("msat1"), env.mid, "w1")
    with pytest.raises(LeaseError):
        env.m.activate(env.ctx("msat1"), env.mid, "w2")
    e = ingest(env, "T1")
    basis = [{"kind": "evidence", "id": e["evidence_id"], "revision": e["revision"]}]
    assert env.m.merge_child_finding(w, {"finding_id": "f1", "basis": basis})["merged"]
    ingest(env, "T1", b"corrected")
    res = env.m.merge_child_finding(w, {"finding_id": "f2", "basis": basis})
    assert not res["merged"] and res["stale"]


def test_wakeups_coalesce_without_dropping_events(env):
    for i in range(3):
        ingest(env, f"E{i}")
    ingest(env, "OTHER", site="S1")
    assert env.m.deliver_events(T)[env.mid] == 4
    assert env.m.deliver_events(T) == {}  # cursor advanced; no re-delivery
    mission = env.m.get(env.ctx("msat1"), env.mid)
    assert len(mission["pending_event_ids"]) == 4 and len(set(mission["pending_event_ids"])) == 4
    assert env.m.scheduler.wakeups.count((T, env.mid, "events")) == 1
    w = env.m.activate(env.ctx("msat1"), env.mid, "w1")
    env.m.checkpoint(w, progress={}, consumed_event_ids=list(w.pending_event_ids[:2]))
    assert len(env.m.get(env.ctx("msat1"), env.mid)["pending_event_ids"]) == 2


def test_LS053_corrections_survive_compaction(env):
    w = env.m.activate(env.ctx("msat1"), env.mid, "w1")
    env.m.checkpoint(w, progress={}, findings=[{"finding_id": f"f{i}", "text": f"finding {i}"} for i in range(30)])
    corr = env.m.record_correction(env.ctx("qa1"), env.mid, text="Run 12 temperature was a sensor fault",
                                   source_ref={"kind": "evidence", "id": "HIST:run12"},
                                   claim_ref={"kind": "finding", "id": "f4"}, rejects_hypothesis="feed temperature drift")
    compacted = env.m.compact(env.ctx("msat1"), env.mid, keep_recent_findings=5)
    assert len(compacted["findings"]) == 5 and compacted["history_refs"]
    assert compacted["corrections"][0]["correction_id"] == corr["correction_id"]
    assert compacted["corrections"][0]["claim_ref"]["id"] == "f4"
    assert compacted["rejected_hypotheses"][0]["hypothesis"] == "feed temperature drift"
    assert len(env.m.history(env.ctx("msat1"), env.mid)) == 30  # originals recoverable
    ctx = env.m.assemble_context(env.ctx("msat1"), env.mid, evidence=[], token_budget=50)
    assert ctx["corrections"] and ctx["constraints"] and ctx["truncated_counts"].get("recent_findings")


def test_context_withholds_unauthorized_evidence(env):
    s1 = ingest(env, "A")
    env.idn.assign_role(T, "op1", "operator", site_id="S2")
    s2 = ingest(env, "B", site="S2")
    refs = [{"kind": "evidence", "id": s1["evidence_id"], "site_id": "S1"},
            {"kind": "evidence", "id": s2["evidence_id"], "site_id": "S2"}]
    ctx = env.m.assemble_context(env.ctx("msat1"), env.mid, evidence=refs)
    assert ctx["evidence_manifest"] == [refs[0]] and ctx["withheld_unauthorized"] == 1
    with pytest.raises(PermissionError):
        env.m.get(env.ctx("outsider"), env.mid)


def test_LS058_budget_pause_reports_remaining_work(env):
    w = env.m.activate(env.ctx("msat1"), env.mid, "w1")
    out = env.m.pause_for_budget(w, completed=["trend"], remaining_work=["cohort comparison", "report"],
                                 reason="mission budget exhausted")
    assert out["status"] == "paused_budget" and out["remaining_work"] == ["cohort comparison", "report"]
    assert out["constraints"] == ["no parameter change without QA approval"]


def test_LS058_gateway_budget_exhaustion_pauses_mission(env):
    reg = default_registry()
    reg.qualify(Qualification("short_summary", "anthropic-haiku", "e", True, {"r": 1}, {"r": 0.9}, "task", "p"))
    gw = ModelGateway(env.s, env.idn, reg, {"anthropic": FakeProvider(name="anthropic")})
    gw.budgets.set_limit(T, f"mission:{env.mid}", 1e-9)
    r = gw.run(TaskRequest("short_summary", env.ctx("msat1"), prompt="x" * 1000, mission_id=env.mid))
    assert r.status == "budget_exhausted"
    w = env.m.activate(env.ctx("msat1"), env.mid, "w1")
    assert env.m.pause_for_budget(w, completed=[], remaining_work=["summary"], reason=r.issues[0])["status"] == "paused_budget"


def test_LS069_reconnect_from_cursor_gets_consistent_snapshot(env):
    first = env.m.stream(env.ctx("msat1"), env.mid)
    cursor = first["cursor"]
    env.m.add_obligation(env.ctx("msat1"), env.mid, description="weekly report")
    env.m.request_decision(env.ctx("msat1"), env.mid, question="q", options=["a"], decider_role="qa", basis=[])
    again = env.m.stream(env.ctx("msat1"), env.mid, after_seq=cursor)
    assert [e["type"] for e in again["events"]] == ["mission.decision_requested"]
    assert again["snapshot"]["revision"] > first["snapshot"]["revision"] and again["cursor"] > cursor
    assert env.m.stream(env.ctx("msat1"), env.mid, after_seq=again["cursor"])["events"] == []


def test_decisions_answered_only_by_named_role(env):
    d = env.m.request_decision(env.ctx("msat1"), env.mid, question="q", options=["yes", "no"], decider_role="qa",
                               basis=[])
    with pytest.raises(PermissionError):
        env.m.answer_decision(env.ctx("msat1"), env.mid, d["decision_id"], "yes")
    out = env.m.answer_decision(env.ctx("qa1"), env.mid, d["decision_id"], "yes")
    assert out["pending_decisions"][0]["answer"] == "yes"


def test_LS021_repeatable_obligation_reschedules(env):
    ob = env.m.add_obligation(env.ctx("msat1"), env.mid, description="shift summary", every_minutes=720,
                              due_at="2026-10-23T06:00:00+00:00", task_kind="short_summary")
    out = env.m.complete_obligation(env.ctx("sup1"), env.mid, ob["obligation_id"],
                                    artifact_ref={"kind": "shift_summary", "id": "s1"})
    o = out["obligations"][0]
    assert o["status"] == "open" and o["due_at"] == "2026-10-23T18:00:00+00:00" and o["completions"]


# --- work queue -------------------------------------------------------------------------
def test_LS087_busy_tenant_cannot_starve_others_or_urgent(env):
    q = WorkQueue(env.s, QueuePolicy(max_running_per_tenant=100))
    for i in range(50):
        q.submit("busy", task="analysis", lane="normal")
    q.submit("quiet", task="analysis", lane="normal")
    q.submit("busy", task="required_notice", lane="urgent")
    order = [q.next() for _ in range(4)]
    assert order[0][1]["lane"] == "urgent"
    assert "quiet" in [t for t, _ in order[1:3]]


def test_LS087_running_ceiling_fanout_and_backpressure(env):
    q = WorkQueue(env.s, QueuePolicy(max_queued_per_tenant=3, max_running_per_tenant=1, max_children_per_mission=2))
    a = q.submit("t", task="x")
    q.submit("t", task="y")
    assert q.next()[1]["item_id"] == a
    assert q.next() is None  # ceiling reached
    q.submit("t", task="urgent", lane="urgent")
    assert q.next()[1]["task"] == "urgent"  # urgent bypasses the analysis ceiling
    q.submit("t", task="z")
    q.submit("t", task="w")  # 3 queued normal items = limit
    with pytest.raises(Backpressure):
        q.submit("t", task="overflow")
    q2 = WorkQueue(env.s, QueuePolicy(max_children_per_mission=2))
    q2.submit("t2", task="c", mission_id="m", parent_item_id="p")
    q2.submit("t2", task="c", mission_id="m", parent_item_id="p")
    with pytest.raises(Backpressure, match="fan-out"):
        q2.submit("t2", task="c", mission_id="m", parent_item_id="p")
    m = q.metrics()["t"]
    assert m["running"] == 2 and m["lanes"]["normal"]["depth"] == 3


def test_queue_recovers_after_restart_without_loss(env):
    q = WorkQueue(env.s)
    ids = {q.submit("t", task=f"job{i}") for i in range(3)}
    q.next()
    restarted = WorkQueue(env.s)
    assert restarted.recover(["t"]) == 3
    got = {restarted.next()[1]["item_id"] for _ in range(3)}
    assert got == ids


# --- role skills --------------------------------------------------------------------------
def test_LS024_every_named_role_has_scoped_skill():
    named = {"operator", "qa", "msat", "supervisor", "engineering", "maintenance", "supply_chain",
             "manufacturing_systems", "quality_systems"}
    assert named <= set(SKILLS)
    for skill in SKILLS.values():
        assert skill.task_kinds and skill.tools and skill.scenario


def test_LS005_skill_never_exceeds_person_scope(env):
    op = env.ctx("op1")
    assert effective_scope("qa", op).task_kinds == frozenset()  # not held
    s = effective_scope("operator", op)
    assert "approve" not in s.actions and "execute" not in s.actions and "sign" not in s.actions
    qa_scope = effective_scope("qa", env.ctx("qa1"))
    assert "release" not in qa_scope.actions and "close_deviation" in qa_scope.may_propose
    assert "release" in effective_scope("qa", env.ctx("qa1"), as_agent=False).actions
    agent = agent_context_for(env.ctx("qa1"), env.idn)
    assert agent.actor_kind == "agent" and agent.delegated_from == "qa1"
    assert not env.idn.check(agent, "approve", "proposal", site_id="S1")
    assert not env.idn.check(agent, "read", "batch", site_id="S2")


def test_revoked_person_delegates_nothing(env):
    env.idn.revoke_role(T, "msat1", "msat", site_id="S1")
    agent = agent_context_for(env.ctx("msat1"), env.idn)
    assert agent.roles == frozenset() and not env.idn.check(agent, "read", "mission", env.mid, site_id="S1")
    assert not env.idn.check(agent, "read", "batch", site_id="S2")
