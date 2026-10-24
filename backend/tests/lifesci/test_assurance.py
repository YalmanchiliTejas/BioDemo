from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from src.lifesci.assurance import AssuranceService
from src.lifesci.evidence import EvidenceService
from src.lifesci.identity import IdentityService
from src.lifesci.missions import MissionService
from src.lifesci.store import RecordStore

T = "tenant-a"
KEY = b"k" * 32


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    idn.assign_role(T, "qa1", "qa", site_id="S1")
    idn.assign_role(T, "admin", "admin")
    idn.assign_role(T, "op1", "operator", site_id="S1")
    ev = EvidenceService(s, idn)
    a = AssuranceService(s, idn)
    ctx = lambda x: idn.context_for(T, x)  # noqa: E731
    ev.ingest(ctx("op1"), source_system="LIMS", source_record_id="R1", content=b"original-bytes",
              media_type="text/plain", site_id="S1", event_time=None)
    ev.ingest(ctx("op1"), source_system="LIMS", source_record_id="R1", content=b"corrected-bytes",
              media_type="text/plain", site_id="S1", event_time=None)
    m = MissionService(s, idn)
    mission = m.start_or_resume(ctx("qa1"), objective="o", owner_id="qa1", scope={"site_ids": ["S1"]})
    w = m.activate(ctx("qa1"), mission["mission_id"], "w")
    m.checkpoint(w, progress={"step": 1})
    return SimpleNamespace(s=s, idn=idn, ev=ev, a=a, m=m, ctx=ctx, mid=mission["mission_id"])


def test_LS082_export_restore_records_originals_sessions_decisions(env):
    bundle = env.a.export(env.ctx("qa1"), signing_key=KEY)
    assert env.a.verify_export(bundle, KEY) == []
    target = RecordStore()
    stats = AssuranceService.restore(bundle, target, KEY)
    assert stats["blobs"] >= 3
    tx = target.read()
    ev = tx.get(T, "evidence", "LIMS:R1")
    assert ev.revision == 2 and tx.revision(T, "evidence", "LIMS:R1", 1).state["digest"] != ev.state["digest"]
    assert tx.get_blob(T, tx.revision(T, "evidence", "LIMS:R1", 1).state["digest"]) == b"original-bytes"
    restored_idn = IdentityService(target)
    restored = MissionService(target, restored_idn)
    assert restored.resume_point(restored_idn.context_for(T, "qa1"), env.mid)["progress"] == {"step": 1}
    assert [a.actor_id for a in tx.audit(T, "evidence", "LIMS:R1")][0] == "op1"
    with pytest.raises(ValueError, match="already holds"):
        AssuranceService.restore(bundle, target, KEY)


def test_export_tamper_detection_and_permission(env):
    bundle = env.a.export(env.ctx("qa1"), signing_key=KEY)
    bad = copy.deepcopy(bundle)
    bad["body"]["revisions"][0]["state"]["tampered"] = True
    assert env.a.verify_export(bad, KEY)
    assert env.a.verify_export(bundle, b"wrong" * 8) == ["manifest signature mismatch"]
    with pytest.raises(PermissionError):
        env.a.export(env.ctx("op1"), signing_key=KEY)


def test_retention_and_legal_hold_block_purge(env):
    assert env.a.purge_allowed(T, "evidence", "LIMS:R1") == (False, "no retention policy configured; purge denied by default")
    env.a.set_retention(env.ctx("admin"), "evidence", min_days=3650, reason="GMP retention")
    assert env.a.purge_allowed(T, "evidence", "LIMS:R1")[0] is False
    env.a.set_retention(env.ctx("admin"), "evidence", min_days=0, reason="test")
    assert env.a.purge_allowed(T, "evidence", "LIMS:R1")[0] is True
    env.a.legal_hold(env.ctx("admin"), "evidence", "LIMS:R1", reason="inspection")
    assert env.a.purge_allowed(T, "evidence", "LIMS:R1") == (False, "legal hold active")


JUNIT = """<testsuite><testcase name="test_LS002_signature_binds_exact_revision"/>
<testcase name="test_LS062_read_default_and_explicit_write_scope"/>
<testcase name="test_broken"><failure message="x"/></testcase></testsuite>"""


def test_LS046_qualification_trace_links_requirements_to_executed_evidence(env):
    a, admin = env.a, env.ctx("admin")
    a.define_requirement(admin, "URS-1", text="Signatures bind content", risk="high",
                         tests=["test_LS002_signature_binds_exact_revision"], intended_use="eBR review")
    a.define_requirement(admin, "URS-2", text="Writes need ownership", risk="high",
                         tests=["test_LS062_read_default_and_explicit_write_scope", "test_broken"], intended_use="x")
    a.define_requirement(admin, "URS-3", text="Untested", risk="low", tests=["test_missing"], intended_use="x")
    run = a.record_test_run(admin, JUNIT, build="abc123", environment={"python": "3.14"})
    trace = a.qualification_trace(T, run)
    status = {r["req_id"]: r["status"] for r in trace["requirements"]}
    assert status == {"URS-1": "evidenced", "URS-2": "gap", "URS-3": "gap"}
    assert "not itself a qualification" in trace["note"]


def test_LS048_LS049_deployment_plan_and_controlled_release(env):
    plan = env.a.deployment_plan(env.ctx("admin"), site_id="S1", process_scope="mAb DS", owners={"site_lead": "a",
                                 "qa_owner": "b", "it_owner": "", "process_owner": "c"},
                                 training=[{"role": "operator", "completed": True}, {"role": "qa", "completed": False}],
                                 qualification_refs=["trace-1"])
    assert not plan["ready"] and plan["missing_owners"] == ["it_owner"] and plan["untrained_roles"] == ["qa"]
    with pytest.raises(ValueError, match="evaluations"):
        env.a.release_notice(env.ctx("admin"), version="1.4.0", changes=["route update"], impact={},
                             affected_task_kinds=["short_summary"], effective_at="2026-11-01")
    env.a.release_notice(env.ctx("admin"), version="1.4.0", changes=["route update"],
                         impact={"evaluations": ["eval-short_summary-haiku"]}, affected_task_kinds=["short_summary"],
                         effective_at="2026-11-01")
    iid = env.a.incident(env.ctx("admin"), title="provider outage", severity="sev2", affected=["gateway"])
    env.a.resolve_incident(env.ctx("admin"), iid, resolution="failover verified")
    assert env.s.read().get(T, "incident", iid).state["status"] == "resolved"
