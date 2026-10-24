from types import SimpleNamespace

import pytest

from src.lifesci.actions import ActionService
from src.lifesci.evidence import EvidenceRef, EvidenceService
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.ownership import OwnershipRegistry
from src.lifesci.quality import (ArtifactService, CaseService, ClaimRejected, ClaimService, FormService, PackageService,
                                 ReuseService)
from src.lifesci.records import SignatureService
from src.lifesci.store import ConflictError, RecordStore

T = "tenant-a"
AUTH = {"method": "sso_reauth"}


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    for actor, role in [("op1", "operator"), ("owner1", "supervisor"), ("qa1", "qa"), ("qar", "qa_reviewer"),
                        ("prior_owner", "supervisor"), ("sup1", "supervisor")]:
        idn.assign_role(T, actor, role, site_id="S1")
    idn.assign_role(T, "bot", "agent", site_id="S1", actor_kind="agent")
    ev = EvidenceService(s, idn)
    sigs = SignatureService(s, idn)
    reuse = ReuseService(s, idn)
    e = SimpleNamespace(
        s=s, idn=idn, ev=ev, sigs=sigs, cases=CaseService(s, idn), claims=ClaimService(s, idn, ev),
        forms=FormService(s, idn, ev, sigs), reuse=reuse, pkgs=PackageService(s, idn, ev, sigs, reuse),
        arts=ArtifactService(s, idn, ev), act=ActionService(s, idn, OwnershipRegistry(s)),
        op=idn.context_for(T, "op1"), owner=idn.context_for(T, "owner1"), qa=idn.context_for(T, "qa1"),
        qar=idn.context_for(T, "qar"), bot=idn.context_for(T, "bot", actor_kind="agent"),
        sup=idn.context_for(T, "sup1"))
    e.cases.open(e.owner, "C1", "owner1", "qar", "S1")
    e.cases.open(e.owner, "PRIOR", "prior_owner", "qar", "S1")
    return e


def ingest(e, rid, content=b"v1"):
    r = e.ev.ingest(e.op, source_system="LIMS", source_record_id=rid, content=content, media_type="text/plain",
                    site_id="S1", event_time="2026-01-01T00:00:00+00:00")
    return EvidenceRef("evidence", r["evidence_id"], r["revision"], "S1")


# --- LS-064 -------------------------------------------------------------------------------
def test_LS064_claim_rules(env):
    a, b = ingest(env, "r1"), ingest(env, "r2")
    with pytest.raises(ClaimRejected):
        env.claims.record_claim(env.bot, "C1", "pH drifted", "calculation", [a], [])
    with pytest.raises(ClaimRejected):
        env.claims.record_claim(env.bot, "C1", "probe fault", "hypothesis", [a], [])
    with pytest.raises(ClaimRejected):
        env.claims.record_claim(env.bot, "C1", "probe fault is the cause", "verified_cause", [a], [])
    with pytest.raises(ClaimRejected):
        env.claims.record_claim(env.bot, "C1", "observed", "observation", [], [])
    with pytest.raises(ClaimRejected):
        env.claims.record_claim(env.bot, "C1", "probe fault", "hypothesis", [a], [b], counterevidence_status="searched_none")
    ok = env.claims.record_claim(env.bot, "C1", "pH drift 0.4 over 2h", "calculation", [a], [], calculation_ref="calc:ph-slope@1")
    assert ok["claim_class"] == "calculation" and ok["status"] == "current"
    h = env.claims.record_claim(env.bot, "C1", "probe fault", "hypothesis", [a], [], counterevidence_status="not_searched")
    assert h["label"].startswith("Hypothesis")


def test_LS064_probability_flagged_uncalibrated(env):
    a = ingest(env, "r1")
    c = env.claims.record_claim(env.bot, "C1", "Probe fault is 95% likely", "hypothesis", [a], [], counterevidence_status="not_searched")
    assert c["uncalibrated_probability"] and "uncalibrated_probability" in c["flags"]
    d = env.claims.record_claim(env.bot, "C1", "pH is 6.8", "observation", [a], [])
    assert not d["uncalibrated_probability"]
    v = env.claims.claim_view(env.op, c["id"])
    assert v["uncertainty"]["uncalibrated_probability"] and v["uncertainty"]["verified"] is False


def test_LS064_claim_view_exposes_basis_contradiction_uncertainty_unresolved(env):
    a, b, c = ingest(env, "r1"), ingest(env, "r2"), ingest(env, "r3")
    h1 = env.claims.record_claim(env.bot, "C1", "probe fault", "hypothesis", [a], [b])
    h2 = env.claims.record_claim(env.bot, "C1", "feed contamination", "hypothesis", [b], [c])
    u = env.claims.record_claim(env.bot, "C1", "operator training unknown", "unknown", [], [], unknowns=["training record not provided"])
    v = env.claims.claim_view(env.op, h1["id"])
    assert v["evidence_basis"][0]["id"] == a.id and v["evidence_basis"][0]["current_revision"] == 1
    assert v["contradictions"]["counterevidence_status"] == "searched_found"
    assert v["contradictions"]["counterevidence"][0]["id"] == b.id
    assert [x["claim_id"] for x in v["contradictions"]["conflicting_claims"]] == [h2["id"]]
    uv = env.claims.claim_view(env.op, u["id"])
    assert uv["unresolved"] == ["training record not provided"] and "no_supporting_evidence" in uv["uncertainty"]["flags"]
    nv = env.claims.record_claim(env.bot, "C1", "other cause", "hypothesis", [a], [], counterevidence_status="not_searched")
    assert "counterevidence has not been searched" in env.claims.claim_view(env.op, nv["id"])["unresolved"]


def test_LS064_evidence_correction_marks_claim_stale(env):
    a = ingest(env, "r1")
    c = env.claims.record_claim(env.bot, "C1", "pH 6.8", "observation", [a], [])
    assert not env.claims.claim_view(env.op, c["id"])["staleness"]["stale"]
    env.ev.ingest(env.op, source_system="LIMS", source_record_id="r1", content=b"v2-corrected", media_type="text/plain",
                  site_id="S1", event_time=None)
    st = env.claims.claim_view(env.op, c["id"])["staleness"]
    assert st["stale"] and st["status"] == "stale" and st["evidence_drift"][0]["current_revision"] == 2


def test_LS060_outcome_kept_apart_from_predicted_benefit(env):
    a, b = ingest(env, "r1"), ingest(env, "r2")
    rec = env.claims.record_claim(env.bot, "C1", "recalibrate probe", "recommendation", [a], [],
                                  predicted_benefit="drift events reduced")
    with pytest.raises(ClaimRejected):
        env.claims.record_outcome_observation(env.op, "C1", rec["id"], "no drift next 3 batches", [b], [])
    env.claims.record_outcome_observation(env.op, "C1", rec["id"], "no drift next 3 batches", [b], ["3 batches only", "feed lot changed"])
    v = env.claims.claim_view(env.op, rec["id"])
    assert v["predicted_benefit"] == "drift events reduced" and v["effect_confirmed"] is False
    assert v["observed_outcomes"][0]["attribution_limits"] == ["3 batches only", "feed lot changed"]


# --- LS-071 -----------------------------------------------------------------------------------
def make_form(env):
    a, b = ingest(env, "r1"), ingest(env, "r2")
    form = env.forms.draft(env.bot, "C1", "deviation_form", [
        {"name": "batch_id", "value": "B-7", "evidence_refs": [a], "status": "cited"},
        {"name": "root_cause", "value": "probe fault", "evidence_refs": [], "status": "cited"},
        {"name": "duration", "value": "2h", "evidence_refs": [b], "status": "cited"}])
    return a, b, form


def test_LS071_fields_without_evidence_are_unresolved_not_filled(env):
    _, _, form = make_form(env)
    assert form["unresolved"] == ["root_cause"]
    f = form["fields"]["root_cause"]
    assert f["field_status"] == "unresolved" and f["value"] is None and f["uncited_suggestion"] == "probe fault"
    view = env.forms.view(env.op, form["form_id"])
    assert view["unresolved"] == ["root_cause"] and view["fields"]["batch_id"]["field_status"] == "cited"


def test_LS071_return_field_invalidates_dependents_but_not_unrelated(env):
    a, b, form = make_form(env)
    fid = form["form_id"]
    dep = env.claims.record_claim(env.bot, "C1", "batch B-7 had a deviation", "observation", [a], [], field_refs=[(fid, "batch_id")])
    other = env.claims.record_claim(env.bot, "C1", "duration 2h", "observation", [b], [], field_refs=[(fid, "duration")])
    env.forms.edit_field(env.op, fid, "root_cause", "probe fault", 1, evidence_refs=[b])
    env.claims.record_claim(env.bot, "C1", "dummy to refresh", "observation", [b], [])
    approval = env.forms.approve_form(env.qa, fid, AUTH)
    pkg = env.pkgs.build_package(env.op, "C1")
    papp = env.pkgs.approve_package(env.qar, pkg["id"], AUTH)
    assert env.pkgs.package_status(env.qar, pkg["id"])["approved"]
    assert env.forms.approval_valid(T, approval["approval_id"])["valid"]

    out = env.forms.return_field_for_correction(env.qar, fid, "batch_id", "batch id mismatches MES record")
    assert out["field_status"] == "returned"
    assert f"claim:{dep['id']}" in out["invalidated"]
    assert f"form_approval:{approval['approval_id']}" in out["invalidated"]
    assert f"qa_package:{pkg['id']}" in out["invalidated"]
    assert f"package_approval:{papp['approval_id']}" in out["invalidated"]
    assert env.claims.claim_view(env.op, dep["id"])["staleness"]["stale"]
    assert not env.forms.approval_valid(T, approval["approval_id"])["valid"]
    st = env.pkgs.package_status(env.qar, pkg["id"])
    assert not st["approved"] and st["package_status"] == "stale"
    view = env.forms.view(env.op, fid)
    assert view["returned"] == ["batch_id"]
    assert view["fields"]["duration"]["status"] == "current" and view["fields"]["root_cause"]["status"] == "current"
    assert not env.claims.claim_view(env.op, other["id"])["staleness"]["stale"]
    assert f"claim:{other['id']}" not in out["invalidated"]
    with pytest.raises(ValueError):
        env.pkgs.approve_package(env.qar, pkg["id"], AUTH)


def test_LS071_edit_field_is_audited_and_revision_checked(env):
    a, b, form = make_form(env)
    fid = form["form_id"]
    out = env.forms.edit_field(env.op, fid, "batch_id", "B-8", 1, reason="typo")
    assert out["field_status"] == "human_asserted" and out["value"] == "B-8" and out["edits"][0]["previous_value"] == "B-7"
    with pytest.raises(ConflictError):
        env.forms.edit_field(env.op, fid, "batch_id", "B-9", 1)
    with pytest.raises(AuthorizationError):
        env.forms.edit_field(env.bot, fid, "batch_id", "B-9", 2)
    actions = [x.action for x in env.s.read().audit(T, "form_field", f"{fid}.batch_id")]
    assert "human_edit" in actions and "derive" in actions


def test_LS071_qa_return_requires_person_and_reason(env):
    _, _, form = make_form(env)
    with pytest.raises(AuthorizationError):
        env.forms.return_field_for_correction(env.bot, form["form_id"], "batch_id", "x")
    with pytest.raises(ValueError):
        env.forms.return_field_for_correction(env.qar, form["form_id"], "batch_id", " ")
    with pytest.raises(AuthorizationError):
        env.forms.return_field_for_correction(env.op, form["form_id"], "batch_id", "operator cannot")


def test_LS071_form_approval_refuses_unresolved_unless_accepted(env):
    _, _, form = make_form(env)
    with pytest.raises(ValueError):
        env.forms.approve_form(env.qa, form["form_id"], AUTH)
    ok = env.forms.approve_form(env.qa, form["form_id"], AUTH, accept_unresolved=True)
    assert ok["accepted_unresolved"] == ["root_cause"]


# --- LS-070 -------------------------------------------------------------------------------------
def request(env, purpose="reuse the root-cause checklist"):
    return env.reuse.request(env.bot, "C1", "PRIOR", "prior probe fault", ["same equipment"], ["different media lot"], purpose)


def test_LS070_approved_reuse_enables_only_stated_reuse(env):
    r = request(env)
    assert r["status"] == "pending"
    env.reuse.decide(env.owner, r["request_id"], "approve")
    assert env.reuse.reuse_allowed(env.op, "C1", "PRIOR", "reuse the root-cause checklist")
    assert not env.reuse.reuse_allowed(env.op, "C1", "PRIOR", "reuse its CAPA conclusions")


def test_LS070_silence_and_rejection_do_not_enable(env):
    r = request(env)
    assert not env.reuse.reuse_allowed(env.op, "C1", "PRIOR", "reuse the root-cause checklist")
    assert "silence" in env.reuse.explain(env.op, "C1", "PRIOR", "reuse the root-cause checklist")["reason"]
    env.reuse.decide(env.owner, r["request_id"], "reject")
    assert not env.reuse.reuse_allowed(env.op, "C1", "PRIOR", "reuse the root-cause checklist")


def test_LS070_only_investigation_owner_decides(env):
    r = request(env)
    for ctx in (env.qa, env.qar, env.sup, env.bot):
        with pytest.raises(AuthorizationError):
            env.reuse.decide(ctx, r["request_id"], "approve")
    assert not env.reuse.reuse_allowed(env.op, "C1", "PRIOR", "reuse the root-cause checklist")


def test_LS070_request_requires_summary_similarities_differences(env):
    with pytest.raises(ValueError):
        env.reuse.request(env.bot, "C1", "PRIOR", "s", [], ["d"], "purpose")


def test_LS070_prior_case_change_after_approval_voids_reuse(env):
    r = request(env)
    env.reuse.decide(env.owner, r["request_id"], "approve")
    env.cases.add_timeline_event(env.owner, "PRIOR", "2026-01-02T00:00:00+00:00", "prior conclusion amended")
    assert not env.reuse.reuse_allowed(env.op, "C1", "PRIOR", "reuse the root-cause checklist")
    assert env.reuse.requests_for_case(env.op, "C1")[0]["effective_status"] == "stale"


# --- review package, coverage, artifacts ------------------------------------------------------------
def test_LS071_package_contents_and_hash_bound_approval(env):
    a, b, form = make_form(env)
    env.claims.record_claim(env.bot, "C1", "pH 6.8", "observation", [a], [])
    env.claims.record_claim(env.bot, "C1", "probe fault", "hypothesis", [a], [], counterevidence_status="not_searched")
    env.claims.record_claim(env.bot, "C1", "training unknown", "unknown", [], [], unknowns=["training record"])
    env.cases.add_timeline_event(env.owner, "C1", "2026-01-01T01:00:00+00:00", "alarm raised", [a])
    env.cases.set_procedures(env.owner, "C1", [{"id": "SOP-12", "revision": 3}])
    r = env.reuse.request(env.bot, "C1", "PRIOR", "s", ["x"], ["y"], "checklist")
    env.reuse.decide(env.owner, r["request_id"], "approve")
    with pytest.raises(ValueError):
        env.pkgs.build_package(env.op, "C1", next_steps=[{"action": "recalibrate"}])
    pkg = env.pkgs.build_package(env.op, "C1", next_steps=[{"action": "recalibrate probe", "owner_id": "owner1"}])
    c = pkg["content"]
    assert c["forms"][0]["form_id"] == form["form_id"] and len(c["fields"]) == 3
    assert [t["description"] for t in c["timeline"]] == ["alarm raised"]
    assert set(c["claims_by_class"]) == {"observation", "calculation", "hypothesis", "recommendation", "unknown"}
    assert len(c["claims_by_class"]["hypothesis"]) == 1
    kinds = {g["type"] for g in c["gaps"]}
    assert {"field_unresolved", "unknown", "counterevidence_not_searched"} <= kinds
    assert c["procedures"] == [{"id": "SOP-12", "revision": 3}]
    assert c["reuse_approvals"][0]["effective_status"] == "approved"
    assert c["next_steps"][0]["owner_id"] == "owner1"
    assert pkg["authorizes_operational_action"] is False

    with pytest.raises(AuthorizationError):
        env.pkgs.approve_package(env.qa, pkg["id"], AUTH)
    with pytest.raises(AuthorizationError):
        env.pkgs.approve_package(env.bot, pkg["id"], AUTH)
    ap = env.pkgs.approve_package(env.qar, pkg["id"], AUTH)
    assert ap["package_hash"] == pkg["package_hash"]
    assert env.pkgs.package_status(env.qar, pkg["id"])["approved"]


def test_LS071_upstream_evidence_correction_makes_package_approval_stale(env):
    a, b, form = make_form(env)
    env.claims.record_claim(env.bot, "C1", "pH 6.8", "observation", [a], [])
    pkg = env.pkgs.build_package(env.op, "C1")
    env.pkgs.approve_package(env.qar, pkg["id"], AUTH)
    assert env.pkgs.package_status(env.qar, pkg["id"])["approved"]
    env.ev.ingest(env.op, source_system="LIMS", source_record_id="r1", content=b"corrected", media_type="text/plain",
                  site_id="S1", event_time=None)
    st = env.pkgs.package_status(env.qar, pkg["id"])
    assert not st["approved"] and st["package_status"] == "stale"


def test_LS071_review_by_exception_coverage_lists_checked_and_unchecked(env):
    assert env.pkgs.coverage(env.op, "PRIOR")["complete"] is False
    assert "not evidence" in env.pkgs.coverage(env.op, "PRIOR")["statement"]
    a, b, form = make_form(env)
    cov = env.pkgs.coverage(env.op, "C1")
    assert cov["checked"] == [] and cov["total"] == len(cov["unchecked"]) == 5 and not cov["complete"]
    env.pkgs.mark_checked(env.qar, "C1", "form_field", f"{form['form_id']}.batch_id")
    env.pkgs.mark_checked(env.qar, "C1", "evidence", a.id)
    cov = env.pkgs.coverage(env.op, "C1")
    assert {i["item_id"] for i in cov["checked"]} == {f"{form['form_id']}.batch_id", a.id}
    assert len(cov["unchecked"]) == 3
    env.forms.edit_field(env.op, form["form_id"], "batch_id", "B-9", 1)
    cov = env.pkgs.coverage(env.op, "C1")
    reasons = {i["item_id"]: i["reason"] for i in cov["unchecked"]}
    assert reasons[f"{form['form_id']}.batch_id"] == "changed_since_check"
    with pytest.raises(AuthorizationError):
        env.pkgs.mark_checked(env.bot, "C1", "evidence", a.id)


def test_LS021_artifacts_always_draft_requires_review_with_sources(env):
    a, b, form = make_form(env)
    obs = env.claims.record_claim(env.bot, "C1", "pH 6.8", "observation", [a], [])
    env.claims.record_claim(env.bot, "C1", "probe fault", "hypothesis", [a], [], counterevidence_status="not_searched")
    env.claims.record_claim(env.bot, "C1", "recalibrate", "recommendation", [a], [])
    for kind in ("deviation", "capa", "report"):
        art = env.arts.generate(env.bot, "C1", kind)
        assert art["review_state"] == "draft_requires_review" and obs["id"] in art["sources"]["claims"]
        assert a.id in art["sources"]["evidence"]
    dev = env.arts.generate(env.bot, "C1", "deviation")
    assert any("[UNRESOLVED] root_cause" == u["text"] for u in dev["sections"]["unresolved"])
    assert dev["sections"]["investigation"][0]["label"].startswith("Hypothesis")
    edited = env.arts.edit_section(env.op, dev["id"], "description", [{"text": "rewritten by human"}], dev["revision"] if "revision" in dev else 1)
    assert edited["review_state"] == "draft_requires_review" and edited["review_history"][-1]["event"] == "edited"
    with pytest.raises(AuthorizationError):
        env.arts.edit_section(env.bot, dev["id"], "description", [], edited["revision"])


def test_LS021_artifact_stale_after_return_and_submission_only_a_proposal(env):
    a, b, form = make_form(env)
    env.claims.record_claim(env.bot, "C1", "pH 6.8", "observation", [a], [], field_refs=[(form["form_id"], "batch_id")])
    art = env.arts.generate(env.bot, "C1", "deviation")
    prop = env.arts.propose_submission(env.bot, art["id"], env.act, "owner1")
    assert prop["status"] == "proposed" and prop["operation"] == "submit_deviation" and prop["requested_by_kind"] == "agent"
    env.forms.return_field_for_correction(env.qar, form["form_id"], "batch_id", "wrong batch")
    assert env.ev.read_derived(env.op, "draft_artifact", art["id"])["status"] == "stale"
    with pytest.raises(ValueError):
        env.arts.propose_submission(env.bot, art["id"], env.act, "owner1")
