from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.lifesci.actions import ActionService
from src.lifesci.evidence import EvidenceService
from src.lifesci.execution import (AuthorityLost, DeviceNotQualified, ExecutionService, ResourceIneligible, StepBlocked)
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.ownership import Ownership, OwnershipRegistry, OwnershipViolation
from src.lifesci.procedures import ProcedureService
from src.lifesci.records import SignatureService
from src.lifesci.store import RecordStore

T = "tenant-a"
AUTH = {"method": "sso_reauth"}
GOOD = {"ph": 7.1, "temp": 37.0}
RES = {"lots": [{"lot_id": "LOT-1", "quantity": 10}], "equipment": ["EQ-1"]}


def exec_recipe():
    return {"constants": {"k": 2.0}, "steps": [
        {"step_id": "charge", "title": "Charge medium", "kind": "material_check", "depends_on": [],
         "resources": {"materials": [{"material_id": "MED-1", "quantity": 10, "unit": "L"}], "equipment": [{"role": "bioreactor"}]}},
        {"step_id": "par", "title": "Prepare sampling", "kind": "instruction", "depends_on": ["charge"], "parallel_group": "g",
         "authority_scope": "other"},
        {"step_id": "ph", "title": "Record pH and temperature", "kind": "data_entry", "depends_on": ["charge"], "authority_scope": "mes",
         "parameters": [{"name": "ph", "unit": "pH", "low": 6.8, "high": 7.2}, {"name": "temp", "unit": "degC", "low": 36.5, "high": 37.5}],
         "calculation": {"name": "feed", "expr": "temp * k", "unit": "mL", "low": 0, "high": 100},
         "branch": {"condition": "ph > 7.0", "true_next": "hi", "false_next": "lo"}},
        {"step_id": "hi", "title": "High pH path", "kind": "instruction", "depends_on": ["ph"]},
        {"step_id": "lo", "title": "Low pH path", "kind": "instruction", "depends_on": ["ph"]},
        {"step_id": "fin", "title": "Final verification", "kind": "signature", "depends_on": ["hi", "lo", "par"],
         "required_signatures": ["performed", "verified"]}]}


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    for actor, role, site in [("eng1", "engineering", "S1"), ("qa1", "qa", None), ("msat1", "msat", None), ("op1", "operator", "S1"),
                              ("op2", "operator", "S1"), ("sup1", "supervisor", "S1"), ("msys", "manufacturing_systems", "S1"),
                              ("msys_all", "manufacturing_systems", None), ("maint1", "maintenance", "S1"),
                              ("op_s2", "operator", "S2"), ("msys3", "manufacturing_systems", "S3")]:
        idn.assign_role(T, actor, role, site_id=site)
    idn.assign_role(T, "bot", "agent", actor_kind="agent")
    own = OwnershipRegistry(s)
    own.assign(T, Ownership("batch_record", "S1", "native", None, (), True, "pilot guided execution", "IQ-1"), by="admin", reason="pilot")
    own.assign(T, Ownership("batch_record", "S3", "external", "MES", ("release_batch",)), by="admin", reason="external")
    act = ActionService(s, idn, own)
    ps = ProcedureService(s, idn, act, EvidenceService(s, idn))
    sigs = SignatureService(s, idn)
    ex = ExecutionService(s, idn, own, ps, sigs)
    e = SimpleNamespace(s=s, idn=idn, own=own, act=act, ps=ps, sigs=sigs, ex=ex, ctx=lambda a, kind="person": idn.context_for(T, a, actor_kind=kind))
    setup_world(e)
    return e


def setup_world(e):
    m = e.ctx("msys")
    e.ex.create_native(m, "material_lot", "LOT-1", {"material_id": "MED-1", "status": "released", "expiry": "2999-01-01", "quantity": 50, "unit": "L"}, site_id="S1")
    e.ex.create_native(m, "equipment", "EQ-1", {"equipment_class": "bioreactor", "status": "available", "qualification_due": "2999-01-01",
                                                 "maintenance_status": "ok", "maintenance_qualification": "bioreactor_pm"}, site_id="S1")
    e.ex.create_batch(m, "B1", product="mAb-1", modality="mAb", site_id="S1", order_id="PO-1")
    e.ps.create_draft(e.ctx("eng1"), "REC", name="Rec", category="recipe", definition=exec_recipe(), site_id="S1")
    prop = e.ps.submit_for_publication(e.ctx("eng1"), "REC", rationale="release")
    e.act.decide(e.ctx("qa1"), prop["proposal_id"], expected_revision=1, decision="approved", role="qa", authentication=AUTH)
    e.ps.publish(e.ctx("eng1"), "REC", prop["proposal_id"])


def started(e):
    inst = e.ex.create_instance(e.ctx("op1"), "REC", batch_id="B1", site_id="S1")
    e.ex.start(e.ctx("op1"), inst)
    return inst["instance_id"]


def status(e, iid, step):
    return e.s.read().require(T, "procedure_instance", iid).state["steps"][step]["status"]


def run_through_prep(e, iid):
    e.ex.perform_step(e.ctx("op1"), iid, "charge", {}, RES)
    e.ex.perform_step(e.ctx("op1"), iid, "par", {})
    return e.ex.perform_step(e.ctx("op1"), iid, "ph", GOOD)


def finish_all(e, iid):
    run_through_prep(e, iid)
    e.ex.perform_step(e.ctx("op1"), iid, "hi", {})
    assert e.ex.perform_step(e.ctx("op1"), iid, "fin", {})["status"] == "awaiting_signature"
    e.ex.sign_step(e.ctx("op1"), iid, "fin", "performed", AUTH)
    return e.ex.sign_step(e.ctx("sup1"), iid, "fin", "verified", AUTH)


# --- LS-073 -----------------------------------------------------------------------------------------
def test_LS073_projection_keeps_source_ref_and_is_idempotent(env):
    e = env
    m3 = e.ctx("msys3")
    a = e.ex.project_external(m3, "material_lot", "L-77", {"material_id": "MED-1", "status": "released", "quantity": 5, "unit": "L"},
                              source_system="ERP", source_ref="erp://lots/L-77", source_revision=3, site_id="S3")
    assert a["id"] == "ERP:L-77" and a["origin"] == "projection" and a["source"]["ref"] == "erp://lots/L-77"
    dup = e.ex.project_external(m3, "material_lot", "L-77", {"material_id": "MED-1", "status": "released", "quantity": 5, "unit": "L"},
                                source_system="ERP", source_ref="erp://lots/L-77", source_revision=3, site_id="S3")
    assert dup["duplicate"] is True and dup["revision"] == a["revision"]
    old = e.ex.project_external(m3, "material_lot", "L-77", {"material_id": "MED-1", "status": "quarantined", "quantity": 5, "unit": "L"},
                                source_system="ERP", source_ref="erp://lots/L-77", source_revision=2, site_id="S3")
    assert old["ignored"] == "older source revision" and e.ex.get(m3, "material_lot", "ERP:L-77")["status"] == "released"
    newer = e.ex.project_external(m3, "material_lot", "L-77", {"material_id": "MED-1", "status": "quarantined", "quantity": 5, "unit": "L"},
                                  source_system="ERP", source_ref="erp://lots/L-77", source_revision=4, site_id="S3")
    assert newer["status"] == "quarantined"
    e.ex.project_external(m3, "production_order", "PO-9", {"product": "mAb-1", "status": "released"}, source_system="MES",
                          source_ref="mes://po/9", site_id="S3")
    with pytest.raises(OwnershipViolation):  # native management is not enabled where MES is authoritative
        e.ex.create_native(m3, "material_lot", "LOT-X", {"status": "released"}, site_id="S3")
    with pytest.raises(OwnershipViolation):  # a projection may not shadow a natively owned site
        e.ex.project_external(e.ctx("msys"), "equipment", "E1", {"status": "available"}, source_system="CMMS", source_ref="c://1", site_id="S1")
    with pytest.raises(OwnershipViolation):
        e.ex.update_native(m3, "material_lot", "ERP:L-77", {"status": "released"})
    with pytest.raises(AuthorizationError):  # outside site scope
        e.ex.get(e.ctx("op1"), "material_lot", "ERP:L-77")


def test_LS073_ineligible_or_missing_resources_cannot_complete_step(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    m = e.ctx("msys")
    with pytest.raises(ResourceIneligible, match="no lot supplied"):
        e.ex.perform_step(op, iid, "charge", {}, {"equipment": ["EQ-1"]})
    with pytest.raises(ResourceIneligible, match="required equipment bioreactor not supplied"):
        e.ex.perform_step(op, iid, "charge", {}, {"lots": [{"lot_id": "LOT-1", "quantity": 10}]})
    with pytest.raises(ResourceIneligible, match="LOT-1 has 50 L available, 80 required") as exc:
        e.ex.perform_step(op, iid, "charge", {}, {"lots": [{"lot_id": "LOT-1", "quantity": 80}], "equipment": ["EQ-1"]})
    assert status(e, iid, "charge") == "pending"
    e.ex.update_native(m, "material_lot", "LOT-1", {"expiry": "2001-01-01"})
    with pytest.raises(ResourceIneligible, match="expired 2001-01-01"):
        e.ex.perform_step(op, iid, "charge", {}, RES)
    e.ex.update_native(m, "material_lot", "LOT-1", {"expiry": "2999-01-01", "status": "quarantined"})
    with pytest.raises(ResourceIneligible, match="quarantined, not released"):
        e.ex.perform_step(op, iid, "charge", {}, RES)
    e.ex.update_native(m, "material_lot", "LOT-1", {"status": "released"})
    e.ex.update_native(m, "equipment", "EQ-1", {"qualification_due": "2001-01-01"})
    with pytest.raises(ResourceIneligible, match="qualification overdue since 2001-01-01"):
        e.ex.perform_step(op, iid, "charge", {}, RES)
    e.ex.update_native(m, "equipment", "EQ-1", {"qualification_due": "2999-01-01", "status": "in_maintenance"})
    with pytest.raises(ResourceIneligible, match="in_maintenance, not available"):
        e.ex.perform_step(op, iid, "charge", {}, RES)
    with pytest.raises(ResourceIneligible, match="not found"):
        e.ex.perform_step(op, iid, "charge", {}, {"lots": [{"lot_id": "NOPE", "quantity": 1}], "equipment": ["EQ-1"]})
    assert status(e, iid, "charge") == "pending"
    e.ex.update_native(m, "equipment", "EQ-1", {"status": "available"})
    out = e.ex.perform_step(op, iid, "charge", {}, RES)
    assert out["status"] == "completed"
    assert e.ex.get(m, "material_lot", "LOT-1")["quantity"] == 40  # consumption recorded
    rec = e.ex.batch_record(op, iid)
    assert rec["steps"][0]["attempts"][0]["resources"]["lots"][0]["lot_id"] == "LOT-1"


# --- LS-001 -------------------------------------------------------------------------------------------
def test_LS001_batch_context_links_authorized_development_records(env):
    e = env
    with e.s.transaction("sys") as tx:
        tx.put(T, "development_run", "DEV-1", {"site_id": "S1", "title": "pH study"}, expected_revision=None, action="seed")
        tx.put(T, "development_run", "DEV-2", {"site_id": "S2", "title": "S2 only study"}, expected_revision=None, action="seed")
    ref1 = {"kind": "development_run", "id": "DEV-1", "revision": 1, "site_id": "S1"}
    ref2 = {"kind": "development_run", "id": "DEV-2", "revision": 1, "site_id": "S2"}
    with pytest.raises(PermissionError):  # S1-scoped actor cannot link an S2 development record
        e.ex.create_batch(e.ctx("msys"), "B2", product="p", modality="mAb", site_id="S1", development_refs=[ref1, ref2])
    b = e.ex.create_batch(e.ctx("msys"), "B2", product="p", modality="AAV", site_id="S1", development_refs=[ref1])
    assert b["modality"] == "AAV" and b["development_refs"] == [ref1]
    assert ("batch", "B2", "informs_batch") in e.s.read().edges_from(T, "development_run", "DEV-1")
    e.ex.link_development_context(e.ctx("msys_all"), "B2", [ref2])
    ctx_view = e.ex.batch_context(e.ctx("op1"), "B2")
    assert ctx_view["development_refs"] == [ref1] and ctx_view["development_refs_withheld"] == 1
    assert e.ex.batch_context(e.ctx("qa1"), "B2")["development_refs_withheld"] == 0
    iid = e.ex.create_instance(e.ctx("op1"), "REC", batch_id="B2", site_id="S1")
    assert iid["context"]["batch_id"] == "B2" and iid["context"]["modality"] == "AAV" and iid["context"]["product"] == "p"
    with pytest.raises(AuthorizationError):
        e.ex.batch_context(e.ctx("op_s2"), "B2")


# --- LS-079 / LS-035 --------------------------------------------------------------------------------
def test_LS079_dependency_order_branch_calculation(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    with pytest.raises(StepBlocked, match="dependency charge is pending"):
        e.ex.perform_step(op, iid, "ph", GOOD)
    e.ex.perform_step(op, iid, "charge", {}, RES)
    with pytest.raises(StepBlocked, match="dependency ph is pending"):
        e.ex.perform_step(op, iid, "hi", {})
    out = e.ex.perform_step(op, iid, "ph", GOOD)
    assert out["status"] == "completed" and out["calculated"] == {"feed": 74.0}
    assert status(e, iid, "hi") == "pending" and status(e, iid, "lo") == "skipped_branch"
    with pytest.raises(StepBlocked, match="step is skipped_branch"):
        e.ex.perform_step(op, iid, "lo", {})
    with pytest.raises(StepBlocked, match="step is completed"):
        e.ex.perform_step(op, iid, "charge", {}, RES)
    inst = e.ps.get_instance(op, iid)
    assert inst["values"]["feed"] == 74.0 and inst["steps"]["ph"]["branch_taken"]["next"] == "hi"
    with pytest.raises(ValueError, match="calculated values cannot be entered"):
        e.ex.perform_step(op, iid, "par", {"feed": 1})
    with pytest.raises(AuthorizationError):  # sup1 can read but a site-S2 operator cannot execute here
        e.ex.perform_step(e.ctx("op_s2"), iid, "par", {})


def test_LS079_unit_conversion_on_entry(env):
    e = env
    iid = started(e)
    e.ex.perform_step(e.ctx("op1"), iid, "charge", {}, RES)
    out = e.ex.perform_step(e.ctx("op1"), iid, "ph", {"ph": 7.1, "temp": {"value": 98.6, "unit": "degF"}})
    assert out["status"] == "completed" and out["evaluations"][1]["value"] == pytest.approx(37.0)


def test_LS079_out_of_limit_creates_exception_event_and_blocks_dependents(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    e.ex.perform_step(op, iid, "charge", {}, RES)
    before = e.s.events_since(T, 0, types=("exec.exception",))
    assert before == []
    out = e.ex.perform_step(op, iid, "ph", {"ph": 7.9, "temp": 37.0})
    assert out["status"] == "exception" and out["violations"][0]["name"] == "ph" and out["violations"][0]["high"] == 7.2
    assert status(e, iid, "ph") == "exception"
    exc = e.s.read().require(T, "exec_exception", out["exception_id"]).state
    assert exc["status"] == "open" and exc["batch_id"] == "B1"
    events = e.s.events_since(T, 0, types=("exec.exception",))
    assert len(events) == 1 and events[0][1].payload["parameter"] == "ph" and events[0][1].payload["value"] == 7.9
    with pytest.raises(StepBlocked, match="dependency ph is exception"):
        e.ex.perform_step(op, iid, "hi", {})
    assert e.ps.get_instance(op, iid)["values"] == {}  # the bad value was not accepted into the run
    retry = e.ex.perform_step(op, iid, "ph", GOOD)  # re-performed in limits -> new attempt
    assert retry["status"] == "completed" and retry["execution_id"].endswith(":ph:2")
    d = e.ex.resolve_exception(e.ctx("sup1"), out["exception_id"], "rework", "re-measured after calibration check")
    assert d["status"] == "dispositioned"
    with pytest.raises(ValueError):
        e.ex.resolve_exception(e.ctx("sup1"), out["exception_id"], "x", " ")
    with pytest.raises(AuthorizationError):
        e.ex.resolve_exception(e.ctx("op1"), out["exception_id"], "x", "operator cannot")


def test_LS079_calculation_limit_violation_is_an_exception(env):
    e = env
    d = exec_recipe()
    d["steps"][2]["calculation"]["high"] = 70  # feed = temp * 2 -> 74 exceeds the calculation limit
    e.ps.create_draft(e.ctx("eng1"), "REC2", name="Rec2", category="recipe", definition=d, site_id="S1")
    prop = e.ps.submit_for_publication(e.ctx("eng1"), "REC2", rationale="release")
    e.act.decide(e.ctx("qa1"), prop["proposal_id"], expected_revision=1, decision="approved", role="qa", authentication=AUTH)
    e.ps.publish(e.ctx("eng1"), "REC2", prop["proposal_id"])
    inst = e.ex.create_instance(e.ctx("op1"), "REC2", batch_id="B1", site_id="S1")
    e.ex.start(e.ctx("op1"), inst)
    iid = inst["instance_id"]
    e.ex.perform_step(e.ctx("op1"), iid, "charge", {}, RES)
    out = e.ex.perform_step(e.ctx("op1"), iid, "ph", GOOD)
    assert out["status"] == "exception" and out["violations"][0]["source"] == "calculation" and out["violations"][0]["value"] == 74.0
    assert status(e, iid, "ph") == "exception" and e.ps.get_instance(e.ctx("op1"), iid)["values"] == {}


def test_LS035_signature_binds_exact_execution_and_procedure_content(env):
    e = env
    iid = started(e)
    op, sup = e.ctx("op1"), e.ctx("sup1")
    run_through_prep(e, iid)
    e.ex.perform_step(op, iid, "hi", {})
    out = e.ex.perform_step(op, iid, "fin", {})
    assert out["status"] == "awaiting_signature" and status(e, iid, "fin") == "awaiting_signature"
    exec_id = out["execution_id"]
    rec = e.s.read().require(T, "step_execution", exec_id)
    assert rec.state["procedure_ref"]["revision"] == 1 and len(rec.state["procedure_ref"]["definition_hash"]) == 64
    with pytest.raises(AuthorizationError, match="performer cannot sign as verified"):
        e.ex.sign_step(op, iid, "fin", "verified", AUTH)
    with pytest.raises(PermissionError):  # authentication method is mandatory
        e.ex.sign_step(op, iid, "fin", "performed", {})
    with pytest.raises(ValueError, match="not a required signature"):
        e.ex.sign_step(op, iid, "fin", "approved", AUTH)
    first = e.ex.sign_step(op, iid, "fin", "performed", AUTH)
    assert first["completed"] is False and first["present"] == {"performed": True, "verified": False}
    assert status(e, iid, "fin") == "awaiting_signature"  # one of two signatures is not enough
    second = e.ex.sign_step(sup, iid, "fin", "verified", AUTH)
    assert second["completed"] is True and second["instance_status"] == "completed"
    assert status(e, iid, "fin") == "completed"
    v = e.sigs.verify(T, second["signature"]["signature_id"])
    assert v["binding_intact"] and v["covers_current_content"]
    assert second["signature"]["content_hash"] == rec.content_hash
    # tampering with the executed content afterwards breaks signature coverage
    with e.s.transaction("attacker") as tx:
        cur = tx.require(T, "step_execution", exec_id)
        tx.put(T, "step_execution", exec_id, {**cur.state, "values": {"forged": 1}}, expected_revision=cur.revision, action="tamper")
    assert e.sigs.verify(T, second["signature"]["signature_id"])["covers_current_content"] is False
    assert e.sigs.required_signatures_present(T, "step_execution", exec_id, ["performed", "verified"]) == {"performed": False, "verified": False}
    assert any(not s["covers_current_content"] for s in e.ex.batch_record(op, iid)["steps"][-1]["signatures"])


# --- LS-079 controlled pause -------------------------------------------------------------------------------
def test_LS079_connectivity_loss_pauses_dependents_and_lists_unrelated_parallel(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    e.ex.perform_step(op, iid, "charge", {}, RES)
    with pytest.raises(AuthorizationError):  # configuring connectivity needs a configure role
        e.ex.set_connectivity(op, iid, False, scopes=["mes"])
    e.ex.set_connectivity(e.ctx("msys"), iid, False, scopes=["mes"])
    report = e.ex.check_authority(op, iid)
    assert report["ok"] is False and "connectivity" in report["reason_kinds"]
    assert report["paused_steps"] == ["fin", "hi", "lo", "ph"]
    assert report["unaffected_parallel_steps"] == ["par"]
    assert status(e, iid, "ph") == "paused_authority_lost" and status(e, iid, "par") == "pending"
    with pytest.raises(AuthorityLost):
        e.ex.perform_step(op, iid, "ph", GOOD)
    assert e.ex.perform_step(op, iid, "par", {})["status"] == "completed"  # unrelated parallel step continues
    with pytest.raises(AuthorityLost):
        e.ex.resume_after_authority(op, iid)
    e.ex.set_connectivity(e.ctx("msys"), iid, True)
    assert e.ex.resume_after_authority(op, iid)["resumed"] == ["fin", "hi", "lo", "ph"]
    assert e.ex.perform_step(op, iid, "ph", GOOD)["status"] == "completed"
    assert e.s.events_since(T, 0, types=("exec.paused_authority_lost",))


def test_LS079_loss_of_role_pauses_actors_dependent_steps(env):
    e = env
    iid = started(e)
    old = e.ctx("op1")
    e.ex.perform_step(old, iid, "charge", {}, RES)
    e.ex.perform_step(old, iid, "ph", {"ph": 7.9, "temp": 37.0})  # op1 left an exception on ph
    e.idn.revoke_role(T, "op1", "operator", site_id="S1", reason="left the area")
    with pytest.raises(AuthorityLost, match="actor authority"):
        e.ex.perform_step(old, iid, "ph", GOOD)  # stale context does not keep authority
    assert status(e, iid, "ph") == "paused_authority_lost" and status(e, iid, "hi") == "paused_authority_lost"
    assert status(e, iid, "par") == "pending"  # another operator can still do unrelated work
    assert e.ex.perform_step(e.ctx("op2"), iid, "par", {})["status"] == "completed"


def test_LS079_ownership_becoming_non_native_pauses_execution(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    e.own.assign(T, Ownership("batch_record", "S1", "external", "MES", ()), by="admin", reason="switch back to MES")
    with pytest.raises(AuthorityLost, match="native execution not enabled"):
        e.ex.perform_step(op, iid, "charge", {}, RES)
    assert status(e, iid, "charge") == "paused_authority_lost"
    with pytest.raises(OwnershipViolation):
        e.ex.start(op, e.ex.create_instance(op, "REC", batch_id="B1", site_id="S1"))


# --- LS-083 --------------------------------------------------------------------------------------------------
def test_LS083_offline_draft_is_provisional_and_never_completes_or_signs(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    e.ex.perform_step(op, iid, "charge", {}, RES)
    rev = e.ps.get_instance(op, iid)["record_revision"]
    with pytest.raises(ValueError, match="cannot carry signatures"):
        e.ex.submit_offline_draft(op, iid, "ph", {**GOOD, "signature": "op1"}, rev, "tablet-1")
    d = e.ex.submit_offline_draft(op, iid, "ph", GOOD, rev, "tablet-1")
    assert d["provisional"] is True and d["signatures"] == [] and d["authoritative"] is False and d["status"] == "provisional"
    again = e.ex.submit_offline_draft(op, iid, "ph", GOOD, rev, "tablet-1")
    assert again["draft_id"] == d["draft_id"] and again["duplicate"] is True  # retry does not duplicate
    assert status(e, iid, "ph") == "pending"
    with pytest.raises(StepBlocked):  # a draft never authorizes the dependent step
        e.ex.perform_step(op, iid, "hi", {})
    cov = e.ex.review_by_exception(op, iid)["unchecked_scope"]
    assert any("offline drafts not resolved" in c for c in cov)
    out = e.ex.reconcile_offline(op, d["draft_id"])
    assert out == {**out, "status": "clean", "completes_step": False}
    assert status(e, iid, "ph") == "pending"  # reconcile alone completes nothing
    assert e.ex.perform_step(op, iid, "ph", GOOD)["status"] == "completed"  # the human performs it authoritatively


def test_LS083_reconcile_detects_amended_procedure_and_step_done_by_another(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    e.ex.perform_step(op, iid, "charge", {}, RES)
    rev = e.ps.get_instance(op, iid)["record_revision"]
    d1 = e.ex.submit_offline_draft(op, iid, "ph", GOOD, rev, "tablet-1")
    amd = e.ps.amend_instance(e.ctx("op2"), iid, {"step_id": "ph", "parameter": "temp", "field": "high", "value": 38.0}, "wider band")
    for role, actor in (("qa", "qa1"), ("msat", "msat1")):
        r = e.s.read().require(T, "proposal", amd["proposal_id"]).revision
        e.act.decide(e.ctx(actor), amd["proposal_id"], expected_revision=r, decision="approved", role=role, authentication=AUTH)
    e.ps.apply_amendment(e.ctx("eng1"), amd["amendment_id"])
    res = e.ex.reconcile_offline(op, d1["draft_id"])
    assert res["status"] == "conflict" and any("amended" in c for c in res["conflicts"])
    rev2 = e.ps.get_instance(op, iid)["record_revision"]
    d2 = e.ex.submit_offline_draft(op, iid, "ph", GOOD, rev2, "tablet-1")
    e.ex.perform_step(e.ctx("op2"), iid, "ph", GOOD)  # someone else completes the step online
    res2 = e.ex.reconcile_offline(op, d2["draft_id"])
    assert res2["status"] == "conflict" and any("already completed" in c for c in res2["conflicts"])
    assert e.s.read().require(T, "offline_draft", d2["draft_id"]).state["status"] == "reconciled_conflict"


# --- LS-078 ----------------------------------------------------------------------------------------------------
def test_LS078_empty_exception_list_is_not_release_authorization(env):
    e = env
    iid = started(e)
    finish_all(e, iid)
    qa = e.ctx("qa1")
    r = e.ex.review_by_exception(qa, iid)
    assert r["exceptions"] == [] and r["release_authorized"] is False
    assert r["checked_scope"] and r["unchecked_scope"]
    assert any("MES/ERP" in u for u in r["unchecked_scope"]) and any("signature bindings" in c for c in r["checked_scope"])
    prop = e.ex.request_release(e.ctx("op1"), iid, rationale="all steps complete, no exceptions")
    assert prop["operation"] == "release_batch" and prop["status"] == "proposed" and prop["target_id"] == "B1"
    assert prop["payload"]["review_coverage"]["unchecked"]  # the unchecked scope travels with the request
    assert e.ex.get(e.ctx("msys"), "batch", "B1")["status"] == "planned"  # nothing was released
    with pytest.raises(AuthorizationError):  # agents can never decide a release
        e.act.decide(e.ctx("bot", "agent"), prop["proposal_id"], expected_revision=1, decision="approved", role="qa", authentication=AUTH)
    with pytest.raises(AuthorizationError):  # the requester cannot approve their own request
        e.act.decide(e.ctx("op1"), prop["proposal_id"], expected_revision=1, decision="approved", role="qa", authentication=AUTH)


def test_LS078_batch_record_compiles_evidence_and_blocks_release_with_gaps(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    with pytest.raises(ValueError, match="only after all steps are terminal"):
        e.ex.request_release(op, iid, rationale="too early")
    e.ex.perform_step(op, iid, "charge", {}, RES)
    ex_out = e.ex.perform_step(op, iid, "ph", {"ph": 7.9, "temp": 37.0})
    rec = e.ex.batch_record(op, iid)
    assert [s["status"] for s in rec["steps"]][:3] == ["completed", "pending", "exception"]
    assert rec["exceptions"][0]["exception_id"] == ex_out["exception_id"]
    un = rec["review_coverage"]["unchecked"]
    assert any(u.startswith("steps not terminal") for u in un) and any("open exceptions awaiting disposition" in u for u in un)
    assert rec["steps"][2]["attempts"][0]["device_type"] == "web"
    assert e.ex.review_by_exception(op, iid)["open_exception_count"] == 1
    e.ex.perform_step(op, iid, "par", {})
    e.ex.perform_step(op, iid, "ph", GOOD)
    e.ex.perform_step(op, iid, "hi", {})
    e.ex.perform_step(op, iid, "fin", {})
    e.ex.sign_step(op, iid, "fin", "performed", AUTH)
    e.ex.sign_step(e.ctx("sup1"), iid, "fin", "verified", AUTH)
    with pytest.raises(ValueError, match="open exceptions must be dispositioned"):
        e.ex.request_release(op, iid, rationale="exception still open")
    e.ex.resolve_exception(e.ctx("sup1"), ex_out["exception_id"], "retest", "re-measured within limits")
    assert e.ex.request_release(op, iid, rationale="ready for QA")["status"] == "proposed"


def test_LS078_amendment_redline_appears_in_record_and_unchecked_when_pinned_hash_is_wrong(env):
    e = env
    iid = started(e)
    rec = e.ex.batch_record(e.ctx("op1"), iid)
    assert any("pinned procedure revision hash matches" in c for c in rec["review_coverage"]["checked"])
    with e.s.transaction("x") as tx:
        cur = tx.require(T, "procedure_instance", iid)
        tx.put(T, "procedure_instance", iid, {**cur.state, "definition_hash": "0" * 64}, expected_revision=cur.revision, action="corrupt")
    assert "pinned revision hash mismatch" in e.ex.batch_record(e.ctx("op1"), iid)["review_coverage"]["unchecked"]


# --- LS-074 ------------------------------------------------------------------------------------------------------
def test_LS074_maintenance_preparation_lists_gaps_and_links_evidence(env):
    e = env
    with e.s.transaction("sys") as tx:
        tx.put(T, "fault_log", "F-1", {"site_id": "S1", "text": "pump stall"}, expected_revision=None, action="seed")
        tx.put(T, "manual", "M-1", {"site_id": "S1"}, expected_revision=None, action="seed")
        tx.put(T, "spare_part", "S1:SEAL-9", {"on_hand": 0}, expected_revision=None, action="seed")
        tx.put(T, "spare_part", "S1:BELT-2", {"on_hand": 5}, expected_revision=None, action="seed")
    faults = [{"kind": "fault_log", "id": "F-1", "revision": 1, "site_id": "S1"}]
    manuals = [{"kind": "manual", "id": "M-1", "revision": 1, "site_id": "S1"}]
    mt = e.ctx("maint1")
    out = e.ex.prepare_maintenance(mt, "EQ-1", faults, manuals, [{"part": "SEAL-9", "quantity": 1}, {"part": "BELT-2", "quantity": 2}],
                                   technician_id="tech9", description="replace pump seal")
    gaps = {g["gap"] for g in out["gaps"]}
    assert gaps == {"technician_qualification_missing", "spare_not_in_stock", "equipment_not_isolated"} and out["ready"] is False
    p = out["proposal"]
    assert p["operation"] == "create_work_order" and p["status"] == "proposed"
    assert {b["kind"] for b in p["basis"]} == {"equipment", "fault_log", "manual"} and p["payload"]["gaps"] == out["gaps"]
    assert [s for s in out["spares"] if s["part"] == "SEAL-9"][0]["on_hand"] == 0
    # close the gaps
    with e.s.transaction("sys") as tx:
        tx.put(T, "personnel_qualification", "tech9", {"qualifications": {"bioreactor_pm": "2999-01-01"}}, expected_revision=None, action="seed")
        s9 = tx.require(T, "spare_part", "S1:SEAL-9")
        tx.put(T, "spare_part", "S1:SEAL-9", {"on_hand": 2}, expected_revision=s9.revision, action="restock")
    e.ex.update_native(e.ctx("msys"), "equipment", "EQ-1", {"isolated": True})
    ok = e.ex.prepare_maintenance(mt, "EQ-1", faults, manuals, [{"part": "SEAL-9", "quantity": 1}], technician_id="tech9")
    assert ok["gaps"] == [] and ok["ready"] is True
    none = e.ex.prepare_maintenance(mt, "EQ-1", [], [], [], technician_id=None)
    assert {"no_fault_history_evidence", "no_manual_reference", "technician_not_assigned"} <= {g["gap"] for g in none["gaps"]}
    with pytest.raises(AuthorizationError):
        e.ex.prepare_maintenance(e.ctx("op_s2"), "EQ-1", faults, manuals, [])


# --- LS-008 (web only) -----------------------------------------------------------------------------------------------
def test_LS008_only_web_is_qualified_other_devices_return_explicit_error(env):
    e = env
    iid = started(e)
    op = e.ctx("op1")
    for dev in ("mobile", "hands_free", "tablet", "wearable", "toaster"):
        with pytest.raises(DeviceNotQualified, match="device not qualified"):
            e.ex.perform_step(op, iid, "charge", {}, RES, device_type=dev)
    assert status(e, iid, "charge") == "pending"
    e.ex.perform_step(op, iid, "charge", {}, RES, device_type="web")
    rec = e.ex.batch_record(op, iid)
    assert rec["steps"][0]["attempts"][0]["device_type"] == "web"
    sup = e.ex.supported_devices()
    assert sup["web"]["qualified"] is True and sup["mobile"]["qualified"] is False and sup["hands_free"]["qualified"] is False
    out = e.ex.perform_step(op, iid, "ph", {"ph": 7.9, "temp": 37.0})  # exceptions are delivered as events from the web path
    assert out["status"] == "exception" and e.s.events_since(T, 0, types=("exec.exception",))
