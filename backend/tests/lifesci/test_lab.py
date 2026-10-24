from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.lifesci.actions import ActionService
from src.lifesci.evidence import EvidenceService
from src.lifesci.execution import ExecutionService
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.lab import LabService, PlateError, ReadinessError, ResultLocked, normalize_well
from src.lifesci.ownership import Ownership, OwnershipRegistry, OwnershipViolation
from src.lifesci.procedures import ProcedureInvalid, ProcedureService
from src.lifesci.records import SignatureService
from src.lifesci.store import ConflictError, RecordStore

T = "tenant-a"
AUTH = {"method": "sso_reauth"}


def method(**over):
    d = {"constants": {"factor": 12.5},
         "requires": {"instruments": [{"instrument_class": "plate_reader"}], "reagents": [{"material_id": "STD-1"}]},
         "steps": [
             {"step_id": "prep", "title": "Prepare standards", "kind": "instruction", "depends_on": [],
              "media": [{"type": "image", "ref": "img://standards"}, {"type": "pdf", "ref": "pdf://assay-sop"}]},
             {"step_id": "blank", "title": "Read blank", "kind": "data_entry", "depends_on": ["prep"],
              "parameters": [{"name": "blank_abs", "unit": "AU", "low": 0, "high": 0.2, "site_adjustable": True,
                              "site_range": {"low": 0, "high": 0.3}}]},
             {"step_id": "read", "title": "Read sample", "kind": "data_entry", "depends_on": ["prep"],
              "parameters": [{"name": "sample_abs", "unit": "AU", "low": 0.05, "high": 2.0}]},
             {"step_id": "calc", "title": "Concentration", "kind": "calculation", "depends_on": ["blank", "read"],
              "calculation": {"name": "conc", "expr": "(sample_abs - blank_abs) * factor", "unit": "mg/mL", "low": 1.0, "high": 20.0}}]}
    d.update(over)
    return d


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    for actor, role, site in [("eng1", "engineering", "S1"), ("qa1", "qa", None), ("rev1", "qa_reviewer", None), ("op1", "operator", "S1"),
                              ("op2", "operator", "S1"), ("msys", "manufacturing_systems", "S1"), ("op_s2", "operator", "S2")]:
        idn.assign_role(T, actor, role, site_id=site)
    idn.assign_role(T, "bot", "agent", actor_kind="agent")
    own = OwnershipRegistry(s)
    for rc in ("batch_record", "lab_record"):
        own.assign(T, Ownership(rc, "S1", "native", None, (), True, "pilot", "IQ-1"), by="admin", reason="pilot")
    own.assign(T, Ownership("lab_record", "S3", "external", "LIMS", ()), by="admin", reason="LIMS")
    act = ActionService(s, idn, own)
    ps = ProcedureService(s, idn, act, EvidenceService(s, idn))
    ex = ExecutionService(s, idn, own, ps, SignatureService(s, idn))
    lab = LabService(s, idn, own, ps)
    e = SimpleNamespace(s=s, idn=idn, own=own, act=act, ps=ps, ex=ex, lab=lab, ctx=lambda a, kind="person": idn.context_for(T, a, actor_kind=kind))
    m = e.ctx("msys")
    ex.create_batch(m, "B1", product="mAb-1", modality="mAb", site_id="S1")
    lab.register_instrument(m, "INS-1", {"instrument_class": "plate_reader", "status": "ready", "calibration_due": "2999-01-01"}, site_id="S1")
    ex.create_native(m, "material_lot", "RG-1", {"material_id": "STD-1", "status": "released", "expiry": "2999-01-01", "quantity": 100, "unit": "mL"}, site_id="S1")
    return e


def publish(e, pid, definition=None, site_id=None, create=True):
    if create:
        e.lab.author_method(e.ctx("eng1"), pid, name="Assay", definition=definition or method(), site_id=site_id)
    prop = e.ps.submit_for_publication(e.ctx("eng1"), pid, rationale="release method")
    e.act.decide(e.ctx("qa1"), prop["proposal_id"], expected_revision=1, decision="approved", role="qa", authentication=AUTH)
    return e.ps.publish(e.ctx("eng1"), pid, prop["proposal_id"])


def run(e, user="op1"):
    publish(e, "ASSAY", site_id="S1")
    return e.lab.start_run(e.ctx(user), "ASSAY", site_id="S1", instruments=["INS-1"], reagents=["RG-1"])["run_id"]


def decide_all(e, proposal_id, pairs):
    for actor, role in pairs:
        r = e.s.read().require(T, "proposal", proposal_id).revision
        e.act.decide(e.ctx(actor), proposal_id, expected_revision=r, decision="approved", role=role, authentication=AUTH)


# --- LS-011 --------------------------------------------------------------------------------------------
def test_LS011_method_authoring_rejects_invalid_units_parameters_limits(env):
    e = env
    ctx = e.ctx("eng1")
    ok = e.lab.author_method(ctx, "M-OK", name="ok", definition=method())
    assert ok["validation_errors"] == [] and ok["category"] == "lab_method"
    assert ok["draft"]["steps"][0]["media"][1] == {"type": "pdf", "ref": "pdf://assay-sop"}

    def bad(mutate):
        d = method()
        mutate(d)
        return e.lab.author_method(ctx, f"M-{id(d)}", name="bad", definition=d)["validation_errors"]

    assert any("unit" in x and "unknown" in x for x in bad(lambda d: d["steps"][1]["parameters"][0].update(unit="parsecs_per_fortnight")))
    assert any("low 0.5 greater than high 0.2" in x for x in bad(lambda d: d["steps"][1]["parameters"][0].update(low=0.5)))
    assert any("needs a unit" in x for x in bad(lambda d: d["steps"][1]["parameters"][0].pop("unit")))
    assert any("needs numeric low and high" in x for x in bad(lambda d: d["steps"][2]["parameters"][0].pop("high")))
    assert any("needs a result unit" in x for x in bad(lambda d: d["steps"][3]["calculation"].pop("unit")))
    assert any("calculation unit" in x and "unknown" in x for x in bad(lambda d: d["steps"][3]["calculation"].update(unit="zzz")))
    assert any("undefined names ['oops']" in x for x in bad(lambda d: d["steps"][3]["calculation"].update(expr="sample_abs * oops")))
    assert any("media needs type" in x for x in bad(lambda d: d["steps"][0]["media"].append({"type": "gif", "ref": "x"})))
    with pytest.raises(ProcedureInvalid):  # an invalid method cannot even be submitted for publication
        d = method()
        d["steps"][1]["parameters"][0]["low"] = 9
        e.lab.author_method(ctx, "M-BAD", name="b", definition=d)
        e.ps.submit_for_publication(ctx, "M-BAD", rationale="x")


def test_LS011_execute_assay_fixture_with_limit_evaluation(env):
    e = env
    rid = run(e)
    op1, op2 = e.ctx("op1"), e.ctx("op2")
    assert e.lab.perform_method_step(op1, rid, "prep", {})["status"] == "completed"
    assert e.lab.perform_method_step(op1, rid, "blank", {"blank_abs": 0.05})["status"] == "completed"
    with pytest.raises(ValueError, match="dependency read is pending"):
        e.lab.perform_method_step(op1, rid, "calc", {})
    e.lab.perform_method_step(op2, rid, "read", {"sample_abs": 0.45})
    out = e.lab.perform_method_step(op1, rid, "calc", {})
    assert out["status"] == "completed" and out["run_status"] == "completed"
    assert out["calculated"]["conc"] == pytest.approx(5.0) and out["limit_evaluation"] == "within_limits"
    batch = e.ex.get(e.ctx("op1"), "batch", "B1")
    s = e.lab.register_sample(op1, "B1", "S-step", "in_process", "k1")
    res = e.lab.record_run_result(op1, rid, s["sample_id"], "conc")
    assert res["value"] == pytest.approx(5.0) and res["unit"] == "mg/mL" and res["limit_evaluation"]["evaluation"] == "within_limits"
    assert res["method_ref"]["run_id"] == rid and res["method_ref"]["revision"] == 1 and res["instrument_id"] == "INS-1"
    assert res["calculation_validated"] is True and res["analytical_validity"] == "not_assessed"
    assert batch["status"] == "planned"


def test_LS011_out_of_limit_calculation_and_out_of_range_input(env):
    e = env
    rid = run(e)
    op = e.ctx("op1")
    e.lab.perform_method_step(op, rid, "prep", {})
    e.lab.perform_method_step(op, rid, "blank", {"blank_abs": 0.05})
    exc = e.lab.perform_method_step(op, rid, "read", {"sample_abs": 2.5})  # above the linear range
    assert exc["status"] == "exception" and e.s.events_since(T, 0, types=("lab.exception",))
    assert e.lab.get_run(op, rid)["steps"]["read"]["status"] == "exception"
    ok = e.lab.perform_method_step(op, rid, "read", {"sample_abs": 1.9})
    assert ok["status"] == "completed"
    calc = e.lab.perform_method_step(op, rid, "calc", {})
    assert calc["calculated"]["conc"] == pytest.approx(23.125)
    assert calc["limit_evaluation"] == "out_of_limits_review_required" and calc["out_of_limits"][0]["name"] == "conc"
    s = e.lab.register_sample(op, "B1", None, "in_process", "k-oos")
    res = e.lab.record_run_result(op, rid, s["sample_id"], "conc")
    assert res["limit_evaluation"]["evaluation"] == "out_of_limits"  # flagged for review, not silently passed or dropped
    with pytest.raises(ValueError):
        e.lab.perform_method_step(op, rid, "calc", {"conc": 1})  # a calculated value cannot be entered / step already done


# --- LS-013 ---------------------------------------------------------------------------------------------
def test_LS013_instrument_and_reagent_readiness_gate_runs(env):
    e = env
    publish(e, "ASSAY", site_id="S1")
    m, op = e.ctx("msys"), e.ctx("op1")
    start = lambda **kw: e.lab.start_run(op, "ASSAY", site_id="S1", **{"instruments": ["INS-1"], "reagents": ["RG-1"], **kw})
    e.lab.register_instrument(m, "INS-1", {"instrument_class": "plate_reader", "status": "ready", "calibration_due": "2001-01-01"}, site_id="S1")
    with pytest.raises(ReadinessError, match="calibration overdue since 2001-01-01"):
        start()
    e.lab.register_instrument(m, "INS-1", {"instrument_class": "plate_reader", "status": "out_of_service", "calibration_due": "2999-01-01"}, site_id="S1")
    with pytest.raises(ReadinessError, match="out_of_service, not ready"):
        start()
    e.lab.register_instrument(m, "INS-1", {"instrument_class": "plate_reader", "status": "ready", "calibration_due": "2999-01-01"}, site_id="S1")
    e.ex.update_native(m, "material_lot", "RG-1", {"expiry": "2001-01-01"})
    with pytest.raises(ReadinessError, match="expired"):
        start()
    e.ex.update_native(m, "material_lot", "RG-1", {"expiry": "2999-01-01"})
    with pytest.raises(ReadinessError, match="required reagent STD-1 not supplied"):
        start(reagents=[])
    with pytest.raises(ReadinessError, match="required instrument class plate_reader not supplied"):
        start(instruments=[])
    with pytest.raises(ReadinessError, match="INS-404 not found"):
        start(instruments=["INS-1", "INS-404"])
    rid = start()["run_id"]
    op_run = e.lab.get_run(op, rid)
    assert op_run["context"]["instruments"] == ["INS-1"] and op_run["context"]["reagents"] == ["RG-1"]
    e.lab.perform_method_step(op, rid, "prep", {})
    e.lab.register_instrument(m, "INS-1", {"instrument_class": "plate_reader", "status": "ready", "calibration_due": "2001-01-01"}, site_id="S1")
    with pytest.raises(ReadinessError, match="calibration overdue"):  # readiness is rechecked on each step
        e.lab.perform_method_step(op, rid, "blank", {"blank_abs": 0.05})
    assert e.lab.get_run(op, rid)["steps"]["blank"]["status"] == "pending"


def test_LS013_concurrent_authorized_users_and_scope_denial(env):
    e = env
    rid = run(e)
    op1, op2 = e.ctx("op1"), e.ctx("op2")
    e.lab.perform_method_step(op1, rid, "prep", {})
    e.lab.perform_method_step(op1, rid, "blank", {"blank_abs": 0.04})
    e.lab.perform_method_step(op2, rid, "read", {"sample_abs": 0.9})
    e.lab.perform_method_step(op2, rid, "calc", {})
    steps = e.lab.get_run(op1, rid)["steps"]
    assert steps["blank"]["performed_by"] == "op1" and steps["read"]["performed_by"] == "op2" and steps["calc"]["performed_by"] == "op2"
    s = e.lab.register_sample(op1, "B1", None, "in_process", "scope-1")
    assert e.lab.get_sample(op2, s["sample_id"])["sample_id"] == s["sample_id"]
    outsider = e.ctx("op_s2")
    with pytest.raises(AuthorizationError, match="outside actor scope"):
        e.lab.get_run(outsider, rid)
    with pytest.raises(AuthorizationError):
        e.lab.get_sample(outsider, s["sample_id"])
    with pytest.raises(AuthorizationError):
        e.lab.perform_method_step(outsider, rid, "prep", {})
    assert e.lab.list_samples(outsider) == [] and len(e.lab.list_samples(op1)) == 1
    with pytest.raises(AuthorizationError):
        e.lab.register_sample(outsider, "B1", None, "x", "scope-2")


# --- LS-014 (method) ---------------------------------------------------------------------------------------
def test_LS014_method_site_adaptation_keeps_parent_and_local_approval(env):
    e = env
    publish(e, "GLOBAL-M")
    ctx = e.ctx("eng1")
    v = e.lab.adapt_method(ctx, "GLOBAL-M", 1, "S1", {"blank_abs": {"high": 0.25}})
    assert v["parent"] == {"procedure_id": "GLOBAL-M", "revision": 1, "definition_hash": v["parent"]["definition_hash"]}
    assert v["draft"]["steps"][1]["parameters"][0]["high"] == 0.25
    with pytest.raises(ProcedureInvalid, match="outside allowed site range"):
        e.lab.adapt_method(ctx, "GLOBAL-M", 1, "S1", {"blank_abs": {"high": 0.9}})
    with pytest.raises(ProcedureInvalid, match="not site adjustable"):
        e.lab.adapt_method(ctx, "GLOBAL-M", 1, "S1", {"sample_abs": {"high": 1.5}})
    assert e.ps.site_variant_status(ctx, "GLOBAL-M~S1")["local_approval"]["status"] == "not_submitted"
    publish(e, "GLOBAL-M~S1", create=False)
    st = e.ps.site_variant_status(ctx, "GLOBAL-M~S1")
    assert st["local_approval"]["status"] == "approved" and st["parent"]["revision"] == 1
    # an adaptation that breaks laboratory rules is still rejected by the laboratory validator
    d = method()
    d["steps"][1]["parameters"][0]["site_range"] = {"low": 0, "high": 0.3}
    assert e.ps.validate(d, "lab_method") == []


# --- LS-012 samples, plates, custody ---------------------------------------------------------------------------------
def test_LS012_sample_registration_is_idempotent_and_linked(env):
    e = env
    op = e.ctx("op1")
    a = e.lab.register_sample(op, "B1", "S5", "in_process", "retry-1", volume=10.0)
    assert a["sample_id"] == "SMP-S1-000001" and a["batch_id"] == "B1" and a["step_id"] == "S5" and a["duplicate"] is False
    again = e.lab.register_sample(op, "B1", "S5", "in_process", "retry-1", volume=10.0)
    assert again["sample_id"] == a["sample_id"] and again["duplicate"] is True
    assert len(e.s.read().list(T, "sample")) == 1
    b = e.lab.register_sample(op, "B1", "S5", "in_process", "retry-2")
    assert b["sample_id"] == "SMP-S1-000002"  # the retry did not burn an identifier
    with pytest.raises(ConflictError):
        e.lab.register_sample(op, "B1", "S6", "final", "retry-1")
    assert ("sample", a["sample_id"], "sampled_from") in e.s.read().edges_from(T, "batch", "B1")
    assert a["custody"][0]["kind"] == "collection" and a["custody"][0]["to"] == "op1"
    with pytest.raises(OwnershipViolation):  # native lab records need enabled ownership
        with e.s.transaction("sys") as tx:
            tx.put(T, "batch", "B3", {"site_id": "S3", "product": "p"}, expected_revision=None, action="seed")
        e.idn.assign_role(T, "op3", "operator", site_id="S3")
        e.lab.register_sample(e.ctx("op3"), "B3", None, "x", "k3")


def test_LS012_aliquots_split_volume_and_are_idempotent(env):
    e = env
    op = e.ctx("op1")
    s = e.lab.register_sample(op, "B1", None, "harvest", "al-1", volume=10.0)
    kids = e.lab.aliquot(op, s["sample_id"], 3, 2.0, "mL", idempotency_key="split-1")
    assert [k["sample_id"] for k in kids] == [f"{s['sample_id']}-A{i}" for i in (1, 2, 3)]
    assert all(k["parent_sample_id"] == s["sample_id"] and k["volume"] == 2.0 for k in kids)
    parent = e.lab.get_sample(op, s["sample_id"])
    assert parent["volume"] == 4.0 and len(parent["aliquot_ids"]) == 3
    replay = e.lab.aliquot(op, s["sample_id"], 3, 2.0, "mL", idempotency_key="split-1")
    assert [k["sample_id"] for k in replay] == [k["sample_id"] for k in kids] and e.lab.get_sample(op, s["sample_id"])["volume"] == 4.0
    with pytest.raises(ValueError, match="requested"):
        e.lab.aliquot(op, s["sample_id"], 3, 2.0, "mL")
    ul = e.lab.aliquot(op, s["sample_id"], 1, 500, "uL")
    assert ul[0]["sample_id"].endswith("-A4") and e.lab.get_sample(op, s["sample_id"])["volume"] == pytest.approx(3.5)
    assert ("sample", kids[0]["sample_id"], "aliquot_of") in e.s.read().edges_from(T, "sample", s["sample_id"])


def test_LS012_plate_positions_reject_occupied_and_invalid_wells(env):
    e = env
    op = e.ctx("op1")
    ids = [e.lab.register_sample(op, "B1", None, "x", f"p{i}")["sample_id"] for i in range(4)]
    assert normalize_well("a01", 96) == "A1" and normalize_well("H12", 96) == "H12" and normalize_well("I1", 96) is None
    assert normalize_well("H13", 96) is None and normalize_well("P24", 384) == "P24" and normalize_well("A25", 384) is None
    plate = e.lab.assign_plate(op, "PL-1", 96, {"A1": ids[0], "A02": ids[1]})
    assert plate["wells"] == {"A1": ids[0], "A2": ids[1]}
    assert e.lab.get_sample(op, ids[0])["plate"] == {"plate_id": "PL-1", "well": "A1"}
    with pytest.raises(PlateError, match="well A1 is occupied by"):
        e.lab.assign_plate(op, "PL-1", 96, {"A1": ids[2], "B1": ids[3]})
    assert e.s.read().require(T, "plate", "PL-1").state["wells"] == {"A1": ids[0], "A2": ids[1]}  # nothing partially written
    assert e.lab.get_sample(op, ids[3])["plate"] is None
    with pytest.raises(PlateError, match="not a valid|not valid"):
        e.lab.assign_plate(op, "PL-1", 96, {"I1": ids[2]})
    with pytest.raises(PlateError, match="is a 96-well plate"):
        e.lab.assign_plate(op, "PL-1", 384, {"C1": ids[2]})
    with pytest.raises(PlateError, match="already at PL-1:A1"):
        e.lab.assign_plate(op, "PL-1", 96, {"C1": ids[0]})
    with pytest.raises(PlateError, match="more than once"):
        e.lab.assign_plate(op, "PL-2", 96, {"A1": ids[2], "A01": ids[3]})
    with pytest.raises(PlateError, match="format"):
        e.lab.assign_plate(op, "PL-3", 48, {"A1": ids[2]})
    assert e.lab.assign_plate(op, "PL-1", 96, {"A1": ids[0]})["wells"] == {"A1": ids[0], "A2": ids[1]}  # idempotent re-assign
    big = e.lab.assign_plate(op, "PL-384", 384, {"P24": ids[2]})
    assert big["wells"] == {"P24": ids[2]}


def test_LS012_custody_chain_and_auditable_correction(env):
    e = env
    op1, op2 = e.ctx("op1"), e.ctx("op2")
    s = e.lab.register_sample(op1, "B1", None, "x", "c1")
    sid = s["sample_id"]
    with pytest.raises(ValueError, match="requires a reason"):
        e.lab.transfer_custody(op1, sid, "op1", "lab-fridge", " ")
    with pytest.raises(ConflictError, match="held by op1"):
        e.lab.transfer_custody(op1, sid, "someone-else", "lab-fridge", "move")
    t1 = e.lab.transfer_custody(op1, sid, "op1", "qc-fridge", "to QC storage")
    e.lab.transfer_custody(op2, sid, "qc-fridge", "analyst-7", "for assay")
    chain = e.lab.custody_chain(op1, sid)
    assert [c["effective"]["to"] for c in chain["chain"]] == ["op1", "qc-fridge", "analyst-7"] and chain["current_custodian"] == "analyst-7"
    corr = e.lab.correct_custody(op2, t1["entry_id"], {"to": "qc-freezer"}, "recorded the wrong storage unit")
    assert corr["kind"] == "correction" and corr["original"] == {"from": "op1", "to": "qc-fridge"}
    after = e.lab.custody_chain(op1, sid)
    assert after["chain"][1]["to"] == "qc-fridge"  # original entry retained verbatim
    assert after["chain"][1]["effective"]["to"] == "qc-freezer" and after["chain"][1]["corrections"] == [corr["entry_id"]]
    assert len(after["raw_entries"]) == 4 and after["raw_entries"][1] == t1
    audit = e.s.read().audit(T, "sample", sid)
    assert any(a.action == "correct_custody" and a.reason == "recorded the wrong storage unit" and a.details["corrects"] == t1["entry_id"] for a in audit)
    before_state = e.s.read().revision(T, "sample", sid, 2).state  # revision prior to the correction is still readable
    assert len(before_state["custody"]) == 2 and before_state["custody"][1]["to"] == "qc-fridge"
    with pytest.raises(ValueError, match="requires a reason"):
        e.lab.correct_custody(op1, t1["entry_id"], {"to": "x"}, "")
    with pytest.raises(ValueError, match="not found or is itself a correction"):
        e.lab.correct_custody(op1, corr["entry_id"], {"to": "x"}, "fixing a correction")


def test_LS012_results_release_lock_and_invalidation_path(env):
    e = env
    op, rev, qa = e.ctx("op1"), e.ctx("rev1"), e.ctx("qa1")
    sid = e.lab.register_sample(op, "B1", None, "final", "r1")["sample_id"]
    r1 = e.lab.record_result(op, sid, "titer", 5.0, "mg/mL", limits={"low": 1, "high": 20}, raw_data=b"A450=0.45")
    assert r1["status"] == "recorded" and r1["limit_evaluation"]["evaluation"] == "within_limits" and r1["raw_data_digest"]
    retry = e.lab.record_result(op, sid, "titer", 5.0, "mg/mL", limits={"low": 1, "high": 20}, raw_data=b"A450=0.45")
    assert retry["duplicate"] is True and retry["revision"] == r1["revision"]
    with pytest.raises(ValueError, match="unknown unit"):
        e.lab.record_result(op, sid, "titer", 5.0, "bogus_unit")
    fixed = e.lab.record_result(op, sid, "titer", 5.2, "mg/mL", limits={"low": 1, "high": 20})  # unreleased result may be corrected
    assert fixed["revision"] == 2 and fixed["history"][0]["value"] == 5.0
    with pytest.raises(ValueError, match="only a reviewed result"):
        e.lab.release_result(qa, r1["result_id"])
    reviewed = e.lab.review_result(rev, r1["result_id"], "approved", "values match raw data")
    assert reviewed["status"] == "reviewed" and "not a validation" in reviewed["review"]["scope"]
    with pytest.raises(AuthorizationError):
        e.lab.release_result(op, r1["result_id"])
    rel = e.lab.release_result(qa, r1["result_id"])
    assert rel["status"] == "released"
    with pytest.raises(ResultLocked, match="invalidate_result"):
        e.lab.record_result(op, sid, "titer", 9.9, "mg/mL")
    same = e.lab.record_result(op, sid, "titer", 5.2, "mg/mL", limits={"low": 1, "high": 20})
    assert same["duplicate"] is True and same["status"] == "released"  # an identical retry is harmless
    assert e.lab.get_result(op, r1["result_id"])["value"] == 5.2
    prop = e.lab.request_invalidation(op, r1["result_id"], "wrong plate map")
    assert prop["operation"] == "invalidate_result" and prop["status"] == "proposed"
    with pytest.raises(PermissionError):
        e.lab.apply_invalidation(e.ctx("eng1"), r1["result_id"], prop["proposal_id"])
    decide_all(e, prop["proposal_id"], [("qa1", "qa"), ("rev1", "qa_reviewer")])
    with pytest.raises(AuthorizationError):
        e.lab.apply_invalidation(e.ctx("bot", "agent"), r1["result_id"], prop["proposal_id"])
    inv = e.lab.apply_invalidation(e.ctx("eng1"), r1["result_id"], prop["proposal_id"])
    assert inv["status"] == "invalidated" and inv["value"] == 5.2  # the original value is retained
    new = e.lab.record_result(op, sid, "titer", 6.1, "mg/mL")
    assert new["status"] == "recorded" and new["value"] == 6.1 and new["revision"] > inv["revision"]
    assert new["history"][-1]["status"] == "invalidated" and new["history"][-1]["value"] == 5.2
    released_rev = [r for r in range(1, new["revision"]) if e.s.read().revision(T, "result", r1["result_id"], r).state["status"] == "released"]
    assert released_rev and e.s.read().revision(T, "result", r1["result_id"], released_rev[0]).state["value"] == 5.2  # released revision stays readable
    audit = [a.action for a in e.s.read().audit(T, "result", r1["result_id"])]
    assert "release_result" in audit and "invalidate_result" in audit


def test_LS012_recorder_cannot_review_own_result(env):
    e = env
    e.idn.assign_role(T, "sup_s1", "supervisor", site_id="S1")
    sid = e.lab.register_sample(e.ctx("op1"), "B1", None, "x", "own")["sample_id"]
    e.idn.assign_role(T, "op1", "supervisor", site_id="S1")
    r = e.lab.record_result(e.ctx("op1"), sid, "ph", 7.0, "pH")
    with pytest.raises(AuthorizationError, match="own result"):
        e.lab.review_result(e.ctx("op1"), r["result_id"], "approved")
    assert e.lab.review_result(e.ctx("sup_s1"), r["result_id"], "approved")["status"] == "reviewed"
