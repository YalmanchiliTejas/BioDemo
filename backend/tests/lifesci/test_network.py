from datetime import timedelta
from types import SimpleNamespace

import pytest

from src.lifesci.actions import ActionService
from src.lifesci.evidence import EvidenceService
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.ids import parse_iso, utc_now
from src.lifesci.network import (LifecycleService, NetworkService, PartnerService, SchedulingService, TransferPackage,
                                 TransferService, validate_site_override)
from src.lifesci.ownership import OwnershipRegistry
from src.lifesci.store import RecordStore

T = "tenant-a"


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    for actor, role, site in [("op1", "operator", "S1"), ("op2", "operator", "S2"), ("sup1", "supervisor", "S1"),
                              ("sup2", "supervisor", "S2"), ("qa", "qa", None), ("msys", "manufacturing_systems", None),
                              ("admin", "admin", None), ("supply", "supply_chain", "S1")]:
        idn.assign_role(T, actor, role, site_id=site)
    ev = EvidenceService(s, idn)
    e = SimpleNamespace(
        s=s, idn=idn, ev=ev, net=NetworkService(s, idn), xfer=TransferService(s, idn), partners=PartnerService(s, idn, ev),
        life=LifecycleService(s, idn), sched=SchedulingService(s, idn), act=ActionService(s, idn, OwnershipRegistry(s)),
        op1=idn.context_for(T, "op1"), op2=idn.context_for(T, "op2"), sup1=idn.context_for(T, "sup1"),
        sup2=idn.context_for(T, "sup2"), qa=idn.context_for(T, "qa"), msys=idn.context_for(T, "msys"),
        admin=idn.context_for(T, "admin"), supply=idn.context_for(T, "supply"),
        bot=None)
    e.partner = idn.context_for(T, "pa1", actor_kind="partner", partner_org_id="ORG1")
    e.partner2 = idn.context_for(T, "pb1", actor_kind="partner", partner_org_id="ORG2")
    return e


def put(env, kind, id, state):
    with env.s.transaction("test") as tx:
        cur = tx.get(T, kind, id)
        return tx.put(T, kind, id, state, expected_revision=cur.revision if cur else None, action="seed")


def make_batch(env, bid, site="S1", status="in_process", evidence=("e1",)):
    for eid in evidence:
        env.ev.ingest(env.qa, source_system="MES", source_record_id=eid, content=f"{bid}-{eid}".encode(), media_type="text/plain",
                      site_id=site, event_time="2026-01-01T00:00:00+00:00")
    put(env, "batch", bid, {"batch_id": bid, "site_id": site, "product_id": "P1", "status": status, "secret_note": "internal",
                            "evidence_ids": [f"MES:{e}" for e in evidence]})


# --- LS-015 ------------------------------------------------------------------------------------
def test_LS015_site_user_sees_only_own_site_enterprise_aggregates(env):
    make_batch(env, "B1", "S1", "released")
    make_batch(env, "B2", "S1", "in_process", evidence=("e2",))
    make_batch(env, "B3", "S2", "in_process", evidence=("e3",))
    v1 = env.net.site_view(env.op1)
    assert v1["scope"] == "site" and set(v1["sites"]) == {"S1"} and v1["sites"]["S1"]["counts"]["batch"]["total"] == 2
    assert {r["id"] for r in v1["sites"]["S1"]["records"]} == {"B1", "B2"}
    assert set(env.net.site_view(env.op2)["sites"]) == {"S2"}
    ent = env.net.site_view(env.qa)
    assert ent["scope"] == "enterprise" and ent["totals"] == {"S1": {"batch": 2}, "S2": {"batch": 1}}
    assert ent["sites"]["S1"]["counts"]["batch"]["released"] == 1


def test_LS015_partner_sees_only_granted_batches(env):
    make_batch(env, "B1", "S1")
    make_batch(env, "B2", "S1", evidence=("e2",))
    assert env.net.site_view(env.partner)["sites"] == {}
    env.partners.grant_partner(env.qa, "ORG1", "B1")
    view = env.net.site_view(env.partner)
    assert view["scope"] == "granted" and [r["id"] for r in view["sites"]["S1"]["records"]] == ["B1"]


# --- LS-009 ---------------------------------------------------------------------------------------
def rollout(env):
    env.net.set_baseline(env.msys, {"mix_speed": 100, "hold_h": 4, "templates": {"TPL-1": 3}})
    return env.net.plan_rollout(env.msys, "S2", [{"template_id": "TPL-1", "revision": 4}],
                                {"mix_speed": 120, "hold_h": 4, "new_param": 1}, "CC-100")


def test_LS009_rollout_records_differences_against_baseline(env):
    r = rollout(env)
    diffs = {d["parameter"]: d for d in r["differences"]}
    assert set(diffs) == {"mix_speed", "new_param", "template:TPL-1"}
    assert diffs["mix_speed"]["baseline_value"] == 100 and diffs["mix_speed"]["site_value"] == 120
    assert diffs["new_param"]["change"] == "added" and diffs["template:TPL-1"]["baseline_value"] == 3
    assert r["status"] == "planned" and r["qms_reference"] == "CC-100"
    with pytest.raises(AuthorizationError):
        env.net.plan_rollout(env.op2, "S2", [], {}, "CC-1")


def test_LS009_reconcile_linked_qms_reference(env):
    r = rollout(env)
    ok = env.net.reconcile_qms(env.msys, r["rollout_id"], {"reference": "CC-100", "status": "approved", "site_id": "S2",
                                                           "covered_parameters": ["mix_speed", "new_param", "template:TPL-1"]})
    assert ok["status"] == "reconciled" and ok["reconciliation"]["difference_coverage"] == "checked"
    for rec, key in [({"reference": "CC-100", "status": "draft", "site_id": "S2"}, "not approved"),
                     ({"reference": "CC-999", "status": "approved", "site_id": "S2"}, "does not match"),
                     ({"reference": "CC-100", "status": "approved", "site_id": "S1"}, "for site S1"),
                     ({"reference": "CC-100", "status": "approved", "site_id": "S2", "covered_parameters": ["mix_speed"]}, "not covered"),
                     (None, "not found")]:
        fresh = rollout(env)
        out = env.net.reconcile_qms(env.msys, fresh["rollout_id"], rec)
        assert out["status"] == "discrepancy" and any(key in i for i in out["reconciliation"]["issues"]), key


# --- LS-016 distribution part ---------------------------------------------------------------------------
def test_LS016_distribution_records_per_site_ack(env):
    out = env.net.distribute(env.msys, "TPL-1", 4, ["S1", "S2"])
    assert [d["ack_status"] for d in out] == ["pending", "pending"] and out[0]["adoption"] == "not_confirmed"
    assert env.net.distribute(env.msys, "TPL-1", 4, ["S1"])[0]["revision"] == 1
    env.net.acknowledge(env.op1, "TPL-1", 4, "S1")
    status = {d["site_id"]: d["ack_status"] for d in env.net.distribution_status(env.qa, "TPL-1")}
    assert status == {"S1": "acknowledged", "S2": "pending"}
    with pytest.raises(AuthorizationError):
        env.net.acknowledge(env.op1, "TPL-1", 4, "S2")
    with pytest.raises(AuthorizationError):
        env.net.distribute(env.op1, "TPL-1", 5, ["S1"])


def test_LS016_override_must_identify_template_revision_and_allowed_params():
    allowed = {"mix_speed": {"min": 50, "max": 150}, "mode": {"choices": ["a", "b"]}, "label": None}
    assert validate_site_override({"template_id": "T", "template_revision": 3, "overrides": {"mix_speed": 120, "label": "x"}}, allowed, 3)["valid"]
    r = validate_site_override({"template_id": "T", "overrides": {"mix_speed": 200, "hold_h": 1, "mode": "z"}}, allowed)
    assert not r["valid"] and len(r["problems"]) == 4
    assert not validate_site_override({"template_id": "T", "template_revision": 2, "overrides": {}}, allowed, 3)["valid"]


# --- LS-017 -----------------------------------------------------------------------------------------------
def package(**kw):
    base = dict(sending_site="S1", receiving_site="S2", product_id="P1", procedure_refs=[{"id": "SOP-1", "revision": 2}],
                parameters={"temp": 37}, material_mapping={"media-A": "media-X", "resin": None},
                equipment_mapping={"BR-1": "BR-9"}, required_qualifications=[{"equipment": "BR-1", "qualification": "OQ"}],
                open_gaps=[{"id": "g1", "description": "water quality data", "status": "open"}])
    base.update(kw)
    return TransferPackage(**base)


INVENTORY = {"materials": ["media-X", "resin-Y"], "equipment": {"BR-9": {"qualifications": ["IQ"]}}}


def test_LS017_checklist_exposes_missing_mappings_before_readiness(env):
    p = env.xfer.create(env.sup1, package())
    cl = env.xfer.recipient_checklist(env.sup2, p["package_id"], INVENTORY)
    types = {g["type"] for g in cl["gaps"]}
    assert types == {"unmapped_material", "equipment_unqualified", "open_gap"} and cl["readiness"] == "not_ready"
    with pytest.raises(ValueError):
        env.xfer.approve(env.sup2, p["package_id"], "recipient", INVENTORY)
    with pytest.raises(ValueError):
        env.xfer.create(env.sup1, package(procedure_refs=[{"id": "SOP-1"}]))


def test_LS017_receipt_is_not_readiness_and_approval_needs_zero_gaps(env):
    p = env.xfer.create(env.sup1, package())
    pid = p["package_id"]
    p = env.xfer.acknowledge_receipt(env.sup2, pid)
    cl = env.xfer.recipient_checklist(env.sup2, pid, INVENTORY)
    assert cl["received"] and cl["readiness"] == "not_ready"
    p = env.xfer.revise(env.sup1, pid, p["revision"],
                        material_mapping={"media-A": "media-X", "resin": "resin-Y"}, open_gaps=[{"id": "g1", "status": "closed"}])
    inv = {"materials": ["media-X", "resin-Y"], "equipment": {"BR-9": {"qualifications": ["IQ", "OQ"]}}}
    cl = env.xfer.recipient_checklist(env.sup2, pid, inv)
    assert cl["gaps"] == [] and cl["readiness"] == "not_ready" and not cl["recipient_approved"]
    with pytest.raises(AuthorizationError):
        env.xfer.approve(env.sup1, pid, "recipient", inv)
    after = env.xfer.approve(env.sup2, pid, "recipient", inv)
    assert env.xfer.recipient_checklist(env.sup2, pid, inv)["readiness"] == "ready"
    env.xfer.revise(env.sup1, pid, after["revision"], parameters={"temp": 35})
    cl = env.xfer.recipient_checklist(env.sup2, pid, inv)
    assert cl["readiness"] == "not_ready" and "no longer covers" in cl["reasons"][0]
    assert env.xfer.recipient_checklist(env.sup2, pid, {"materials": [], "equipment": {}})["gaps"]


# --- LS-018 -------------------------------------------------------------------------------------------------
def test_LS018_view_only_vs_interactive_grants(env):
    make_batch(env, "B1")
    env.partners.grant_partner(env.qa, "ORG1", "B1", mode="view")
    env.partners.grant_partner(env.qa, "ORG2", "B1", mode="interactive")
    v = env.partners.partner_batch_view(env.partner, "B1")
    assert v["batch"] == {"batch_id": "B1", "product_id": "P1", "status": "in_process", "site_id": "S1"}
    assert "secret_note" not in str(v) and v["permissions"] == {"can_comment": False, "can_approve": False}
    with pytest.raises(AuthorizationError):
        env.partners.partner_review(env.partner, "B1", "approve", "looks good")
    r = env.partners.partner_review(env.partner2, "B1", "approve", "looks good")
    assert r["origin"]["partner_org_id"] == "ORG2" and r["effect"] == "recorded_feedback_only"
    make_batch(env, "B2", evidence=("e9",))
    with pytest.raises(AuthorizationError):
        env.partners.partner_batch_view(env.partner, "B2")


def test_LS018_grants_expire(env):
    make_batch(env, "B1")
    env.partners.grant_partner(env.qa, "ORG1", "B1", expires_at=utc_now() - timedelta(minutes=1))
    with pytest.raises(AuthorizationError):
        env.partners.partner_batch_view(env.partner, "B1")


def test_LS018_revocation_removes_current_and_cached_access(env):
    make_batch(env, "B1", evidence=("e1", "e2"))
    g1 = env.partners.grant_partner(env.qa, "ORG1", "B1")
    env.partners.grant_partner(env.qa, "ORG2", "B1")
    exp1 = env.partners.export_for_partner(env.qa, "B1", "ORG1")
    exp2 = env.partners.export_for_partner(env.qa, "B1", "ORG2")
    assert env.partners.read_export(env.partner, exp1["id"])["projection"]["batch_id"] == "B1"
    with pytest.raises(PermissionError):
        env.partners.read_export(env.partner2, exp1["id"])
    out = env.partners.revoke_partner(env.qa, g1["grant_id"])
    assert f"partner_export:{exp1['id']}" in out["quarantined"]
    with pytest.raises(AuthorizationError):
        env.partners.partner_batch_view(env.partner, "B1")
    with pytest.raises(PermissionError, match="quarantined"):
        env.partners.read_export(env.partner, exp1["id"])
    with pytest.raises(PermissionError):
        env.partners.read_export(env.qa, exp1["id"])
    assert env.partners.read_export(env.partner2, exp2["id"])["partner_org_id"] == "ORG2"
    with pytest.raises(PermissionError):
        env.partners.export_for_partner(env.qa, "B1", "ORG1")
    assert env.net.site_view(env.partner)["sites"] == {}


def test_LS018_only_authorized_internal_roles_grant(env):
    make_batch(env, "B1")
    with pytest.raises(AuthorizationError):
        env.partners.grant_partner(env.op1, "ORG1", "B1")


# --- LS-019 ----------------------------------------------------------------------------------------------------
def test_LS019_readiness_links_to_source_revisions_and_goes_stale(env):
    put(env, "qms_record", "VAL-1", {"site_id": "S1", "state": "approved"})
    put(env, "qms_record", "REG-1", {"site_id": "S1", "state": "filed"})
    i1 = env.life.record_readiness(env.sup1, "P1", "validation", "EU", "ready", "qms_record", "VAL-1", site_id="S1")
    env.life.record_readiness(env.sup1, "P1", "registration", "US", "at_risk", "qms_record", "REG-1", site_id="S1")
    s = env.life.lifecycle_summary(env.sup1, "P1")
    item = s["stages"]["validation"]["EU"][0]
    assert item["source"] == {"kind": "qms_record", "id": "VAL-1", "revision": 1, "site_id": "S1", "current_revision": 1}
    assert item["status"] == "ready" and s["stale_items"] == 0
    put(env, "qms_record", "VAL-1", {"site_id": "S1", "state": "superseded"})
    s = env.life.lifecycle_summary(env.sup1, "P1")
    item = s["stages"]["validation"]["EU"][0]
    assert item["stale"] and item["status"] == "stale" and item["recorded_status"] == "ready" and "revision 1 to 2" in item["stale_reason"]
    assert not s["stages"]["registration"]["US"][0]["stale"] and s["stale_items"] == 1
    env.life.confirm_readiness(env.sup1, i1["item_id"], "not_ready", i1["revision"])
    assert env.life.lifecycle_summary(env.sup1, "P1")["stale_items"] == 0


def test_LS019_unreadable_sources_are_not_disclosed(env):
    put(env, "qms_record", "VAL-2", {"site_id": "S2", "state": "approved"})
    env.life.record_readiness(env.qa, "P2", "validation", "EU", "ready", "qms_record", "VAL-2", site_id="S2")
    s = env.life.lifecycle_summary(env.op1, "P2")
    assert s["stages"] == {} and s["restricted_items"] == 1


# --- LS-075 ---------------------------------------------------------------------------------------------------------
H = {"start": "2026-03-01T00:00:00+00:00", "end": "2026-03-10T00:00:00+00:00"}


def window(start_day, end_day):
    return {"start": f"2026-03-{start_day:02d}T00:00:00+00:00", "end": f"2026-03-{end_day:02d}T00:00:00+00:00"}


def inputs(**over):
    d = dict(
        campaign={"campaign_id": "CAMP1", "site_id": "S1", "batches": [
            {"batch_id": "B1", "equipment": ["BR-1", "BR-2"], "duration_h": 48, "materials": [{"item": "media", "qty": 50}],
             "due": "2026-03-06T00:00:00+00:00"},
            {"batch_id": "B2", "equipment": ["BR-1", "BR-2"], "duration_h": 48, "materials": [{"item": "media", "qty": 50}]}]},
        resources={"equipment": {"BR-1": {"availability": [window(1, 10)], "cleaning_h": 6},
                                 "BR-2": {"availability": [window(1, 10)], "cleaning_h": 6}}},
        materials={"media": [{"lot": "L1", "qty": 60, "expiry": "2026-04-01T00:00:00+00:00"},
                             {"lot": "L2", "qty": 60, "expiry": "2026-05-01T00:00:00+00:00"}]},
        quality_holds=[], horizon=H)
    d.update(over)
    return d


def test_LS075_feasible_schedule_respects_constraints(env):
    out = env.sched.propose_schedule(env.sup1, **inputs())
    assert out["status"] == "feasible" and out["violations"] == []
    a = {x["batch_id"]: x for x in out["assignments"]}
    assert a["B1"]["equipment"] != a["B2"]["equipment"] or parse_iso(a["B2"]["start"]) >= parse_iso(a["B1"]["end"]) + timedelta(hours=6)
    assert {l["lot"] for x in out["assignments"] for l in x["lots"]} == {"L1", "L2"} or sum(l["qty"] for x in out["assignments"] for l in x["lots"]) == 100
    assert not out["applied"]


def test_LS075_cleaning_time_enforced_on_single_equipment(env):
    i = inputs()
    for b in i["campaign"]["batches"]:
        b["equipment"] = ["BR-1"]
    out = env.sched.propose_schedule(env.sup1, **i)
    assert out["status"] == "feasible"
    first, second = sorted(out["assignments"], key=lambda x: x["start"])
    assert parse_iso(second["start"]) >= parse_iso(first["end"]) + timedelta(hours=6)


def test_LS075_infeasible_exposes_violated_constraints(env):
    held = env.sched.propose_schedule(env.sup1, **inputs(quality_holds=[{"lot": "L1"}, {"lot": "L2"}]))
    assert held["status"] == "infeasible" and {v["constraint"] for v in held["violations"]} >= {"quality_hold_on_lot"}
    short = env.sched.propose_schedule(env.sup1, **inputs(materials={"media": [{"lot": "L1", "qty": 70, "expiry": "2026-04-01T00:00:00+00:00"}]}))
    assert short["status"] == "infeasible" and any(v["constraint"] == "material_shortage_campaign" for v in short["violations"])
    expired = env.sched.propose_schedule(env.sup1, **inputs(materials={"media": [{"lot": "L1", "qty": 200, "expiry": "2026-02-20T00:00:00+00:00"}]}))
    assert expired["status"] == "infeasible" and any(v["constraint"] == "material_expired" for v in expired["violations"])
    nowin = inputs(resources={"equipment": {"BR-1": {"availability": [window(1, 2)], "cleaning_h": 6},
                                            "BR-2": {"availability": [window(1, 2)], "cleaning_h": 6}}})
    r = env.sched.propose_schedule(env.sup1, **nowin)
    assert r["status"] == "infeasible" and any(v["constraint"] == "no_equipment_window" for v in r["violations"])
    due = inputs()
    due["campaign"]["batches"][0]["due"] = "2026-03-02T00:00:00+00:00"
    assert any(v["constraint"] == "due_date" for v in env.sched.propose_schedule(env.sup1, **due)["violations"])
    eqhold = env.sched.propose_schedule(env.sup1, **inputs(quality_holds=[{"equipment": "BR-1"}, {"equipment": "BR-2"}]))
    assert any(v["constraint"] == "equipment_quality_hold" for v in eqhold["violations"])


def test_LS075_contention_reported_when_each_batch_alone_is_feasible(env):
    i = inputs(resources={"equipment": {"BR-1": {"availability": [window(1, 4)], "cleaning_h": 6}}})
    for b in i["campaign"]["batches"]:
        b["equipment"] = ["BR-1"]
        b["due"] = None
    out = env.sched.propose_schedule(env.sup1, **i)
    assert out["status"] == "infeasible" and [v["constraint"] for v in out["violations"]] == ["resource_contention"]


def test_LS075_missing_availability_is_incomplete_never_feasible(env):
    i = inputs()
    del i["resources"]["equipment"]["BR-2"]["availability"]
    out = env.sched.propose_schedule(env.sup1, **i)
    assert out["status"] == "incomplete_inputs" and "equipment:BR-2:availability" in out["missing"] and out["assignments"] == []
    assert env.sched.propose_schedule(env.sup1, **inputs(quality_holds=None))["status"] == "incomplete_inputs"
    assert "materials:media" in env.sched.propose_schedule(env.sup1, **inputs(materials={}))["missing"]
    i = inputs()
    del i["resources"]["equipment"]["BR-1"]["cleaning_h"]
    assert env.sched.propose_schedule(env.sup1, **i)["status"] == "incomplete_inputs"


def test_LS075_application_only_through_action_proposal(env):
    out = env.sched.propose_schedule(env.sup1, **inputs())
    prop = env.sched.apply_schedule(env.sup1, out["schedule_id"], env.act, "sup1")
    assert prop["operation"] == "reschedule_batch" and prop["status"] == "proposed" and prop["execution_status"] == "not_started"
    assert prop["required_roles"] == ["supervisor"]
    assert env.s.read().require(T, "schedule_proposal", out["schedule_id"]).state["applied"] is False
    bad = env.sched.propose_schedule(env.sup1, **inputs(quality_holds=None))
    with pytest.raises(ValueError):
        env.sched.apply_schedule(env.sup1, bad["schedule_id"], env.act, "sup1")
    with pytest.raises(AuthorizationError):
        env.sched.propose_schedule(env.op2, **inputs())
