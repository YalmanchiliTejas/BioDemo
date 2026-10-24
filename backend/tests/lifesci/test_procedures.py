from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from src.lifesci.actions import ActionService
from src.lifesci.evidence import EvidenceService
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.ownership import OwnershipRegistry
from src.lifesci.procedures import (ExpressionError, ProcedureInvalid, ProcedureService, expr_names, parse_procedure_text,
                                    safe_eval)
from src.lifesci.store import ConflictError

T = "tenant-a"
AUTH = {"method": "sso_reauth"}


def recipe(**over):
    d = {
        "constants": {"dilution": 2.0},
        "template_params": [{"name": "target_ph", "type": "number", "default": 7.0}, {"name": "product", "type": "text", "default": "mAb-1"}],
        "steps": [
            {"step_id": "prep", "title": "Prepare {{product}} medium", "kind": "data_entry", "depends_on": [],
             "parameters": [{"name": "ph", "unit": "pH", "low": "{{target_ph}}", "high": 7.4, "target": 7.2, "site_adjustable": True,
                             "site_range": {"low": 6.9, "high": 7.5}},
                            {"name": "temp", "unit": "degC", "low": 36.5, "high": 37.5, "target": 37.0}],
             "media": [{"type": "image", "ref": "img://prep"}], "supported_devices": ["tablet"]},
            {"step_id": "calc", "title": "Compute feed", "kind": "calculation", "depends_on": ["prep"],
             "calculation": {"name": "feed", "expr": "temp * dilution", "unit": "mL"},
             "branch": {"condition": "ph > 7.2", "true_next": "hi", "false_next": "lo"}},
            {"step_id": "hi", "title": "High pH path", "kind": "instruction", "depends_on": ["calc"], "parallel_group": "g1"},
            {"step_id": "lo", "title": "Low pH path", "kind": "instruction", "depends_on": ["calc"], "parallel_group": "g1"},
            {"step_id": "fin", "title": "Finish", "kind": "signature", "depends_on": ["hi", "lo"], "required_signatures": ["performed", "verified"]},
        ]}
    d.update(over)
    return d


@pytest.fixture
def env():
    s = RecordStoreFactory()
    idn = IdentityService(s)
    for actor, role, site in [("eng1", "engineering", "S1"), ("qa1", "qa", None), ("msat1", "msat", None), ("op1", "operator", "S1"),
                              ("sup1", "supervisor", "S1"), ("eng2", "engineering", "S2")]:
        idn.assign_role(T, actor, role, site_id=site)
    idn.assign_role(T, "bot", "agent", actor_kind="agent")
    own = OwnershipRegistry(s)
    act = ActionService(s, idn, own)
    ev = EvidenceService(s, idn)
    ps = ProcedureService(s, idn, act, ev)
    ctx = lambda a, kind="person": idn.context_for(T, a, actor_kind=kind)
    return SimpleNamespace(s=s, idn=idn, act=act, ev=ev, ps=ps, ctx=ctx)


def RecordStoreFactory():
    from src.lifesci.store import RecordStore
    return RecordStore()


def approve(env, proposal_id, roles=("qa",)):
    out = None
    for role in roles:
        actor = {"qa": "qa1", "msat": "msat1"}[role]
        rev = env.s.read().require(T, "proposal", proposal_id).revision
        out = env.act.decide(env.ctx(actor), proposal_id, expected_revision=rev, decision="approved", role=role, authentication=AUTH)
    return out


def publish(env, pid, definition=None, name="Recipe", category="recipe", site_id=None, create=True):
    e = env
    if create:
        e.ps.create_draft(e.ctx("eng1"), pid, name=name, category=category, definition=definition or recipe(), site_id=site_id)
    prop = e.ps.submit_for_publication(e.ctx("eng1"), pid, rationale="initial release")
    approve(e, prop["proposal_id"])
    return e.ps.publish(e.ctx("eng1"), pid, prop["proposal_id"])


# --- evaluator -----------------------------------------------------------------------------
def test_safe_evaluator_arithmetic_and_rejection():
    assert safe_eval("(a + 2) * 3 / 2", {"a": 4}) == 9
    assert safe_eval("a > 1 and not b < 0", {"a": 2, "b": 1}) is True
    assert expr_names("x * y + 2") == {"x", "y"}
    for bad in ("__import__('os')", "a.b", "[1]", "'s'", "f(1)", "a if b else c", "lambda: 1", "2 ** 1000", "a / 0"):
        with pytest.raises(ExpressionError):
            safe_eval(bad, {"a": 1, "b": 1, "c": 1})
    with pytest.raises(ExpressionError):
        safe_eval("zz + 1", {})


# --- LS-006 -----------------------------------------------------------------------------------
def test_LS006_validate_rejects_invalid_definitions(env):
    ps = env.ps
    assert ps.validate(recipe()) == []
    cyc = recipe()
    cyc["steps"][0]["depends_on"] = ["fin"]
    assert any("cycle" in e for e in ps.validate(cyc))
    unk = recipe()
    unk["steps"][2]["depends_on"] = ["ghost"]
    assert any("unknown dependency ghost" in e for e in ps.validate(unk))
    badb = recipe()
    badb["steps"][1]["branch"]["true_next"] = "nowhere"
    assert any("branch true_next" in e for e in ps.validate(badb))
    lim = recipe()
    lim["steps"][0]["parameters"][1].update(low=40, high=30)
    assert any("low 40 greater than high 30" in e for e in ps.validate(lim))
    unit = recipe()
    unit["steps"][0]["parameters"][1]["unit"] = "furlongs_per_fortnightly"
    assert any("unit" in e and "unknown" in e for e in ps.validate(unit))
    name = recipe()
    name["steps"][1]["calculation"]["expr"] = "temp * undefined_thing"
    assert any("undefined names ['undefined_thing']" in e for e in ps.validate(name))
    unsafe = recipe()
    unsafe["steps"][1]["calculation"]["expr"] = "__import__('os').system('x')"
    assert ps.validate(unsafe)
    # a calculation may not use a value from a step that is not an ancestor
    sib = recipe()
    sib["steps"][2]["calculation"] = {"name": "q", "expr": "feed + 1"}
    sib["steps"][3]["parameters"] = [{"name": "z", "unit": "mL"}]
    sib["steps"][2]["calculation"] = {"name": "q", "expr": "z + 1"}
    assert any("undefined names ['z']" in e for e in ps.validate(sib))
    with pytest.raises(ProcedureInvalid):
        ps.create_draft(env.ctx("eng1"), "bad", name="b", category="recipe", definition=cyc)
        ps.submit_for_publication(env.ctx("eng1"), "bad", rationale="x")


def test_LS006_preview_resolves_branches_parallel_and_templates(env):
    plan = env.ps.preview(recipe(), {"target_ph": 6.8})
    by = {p["step_id"]: p for p in plan}
    assert [p["step_id"] for p in plan][:2] == ["prep", "calc"]
    assert by["prep"]["title"] == "Prepare mAb-1 medium"
    assert by["prep"]["parameters"][0]["low"] == 6.8
    # branch depends on a runtime-captured value, so both paths stay conditional in the preview
    assert by["calc"]["branch"]["result"] is None and by["hi"]["status"] == "conditional" and by["lo"]["status"] == "conditional"
    assert by["hi"]["parallel_group"] == by["lo"]["parallel_group"] == "g1" and by["hi"]["wave"] == by["lo"]["wave"]
    d = recipe()
    d["constants"]["ph_const"] = 7.5
    d["steps"][1]["branch"]["condition"] = "ph_const > 7.2"
    by = {p["step_id"]: p for p in env.ps.preview(d)}
    assert by["calc"]["branch"]["selected"] == "hi" and by["lo"]["status"] == "skipped_branch" and by["hi"]["status"] == "planned"
    assert by["fin"]["status"] == "planned"
    assert by["fin"]["required_signatures"] == ["performed", "verified"]


def test_LS006_publish_requires_approved_proposal_and_matching_hash(env):
    e = env
    e.ps.create_draft(e.ctx("eng1"), "R1", name="R", category="recipe", definition=recipe())
    prop = e.ps.submit_for_publication(e.ctx("eng1"), "R1", rationale="r")
    assert prop["operation"] == "publish_procedure" and prop["status"] == "proposed"
    with pytest.raises(PermissionError):
        e.ps.publish(e.ctx("eng1"), "R1", prop["proposal_id"])
    with pytest.raises(AuthorizationError):
        e.ps.publish(e.ctx("bot", "agent"), "R1", prop["proposal_id"])
    approve(e, prop["proposal_id"])
    # draft edited after approval -> hash mismatch, approval does not cover the new content
    d2 = recipe()
    d2["steps"][4]["title"] = "Finish (edited)"
    rec = e.s.read().require(T, "procedure", "R1")
    e.ps.update_draft(e.ctx("eng1"), "R1", d2, expected_revision=rec.revision)
    with pytest.raises(ValueError, match="draft changed after approval"):
        e.ps.publish(e.ctx("eng1"), "R1", prop["proposal_id"])


def test_LS006_publish_makes_revision_effective_and_blocks_replay(env):
    rev = publish(env, "R1")
    assert rev["revision"] == 1 and rev["approval_ids"]
    assert env.s.read().require(T, "procedure", "R1").state["effective_revision"] == 1
    prop_id = env.s.read().require(T, "procedure", "R1").state["revisions"][0]["proposal_id"]
    with pytest.raises(ConflictError):
        env.ps.publish(env.ctx("eng1"), "R1", prop_id)


# --- LS-033 -------------------------------------------------------------------------------------
def test_LS033_new_revision_does_not_change_active_instances(env):
    e = env
    publish(e, "WI1", category="work_instruction")
    inst = e.ps.create_instance(e.ctx("op1"), "WI1", site_id="S1")
    old_def = copy.deepcopy(inst["steps_def"])
    d2 = recipe()
    d2["steps"][4]["title"] = "Finish v2"
    rec = e.s.read().require(T, "procedure", "WI1")
    e.ps.update_draft(e.ctx("eng1"), "WI1", d2, expected_revision=rec.revision)
    rev2 = publish(e, "WI1", create=False)
    assert rev2["revision"] == 2
    again = e.ps.get_instance(e.ctx("op1"), inst["instance_id"])
    assert again["revision"] == 1 and again["steps_def"] == old_def and again["steps_def"]["fin"]["title"] == "Finish"
    new_inst = e.ps.create_instance(e.ctx("op1"), "WI1", site_id="S1")
    assert new_inst["revision"] == 2 and new_inst["steps_def"]["fin"]["title"] == "Finish v2"
    pinned = e.ps.create_instance(e.ctx("op1"), "WI1", site_id="S1", revision=1)
    assert pinned["revision"] == 1
    r1 = e.s.read().revision(T, "procedure_revision", "WI1@1", 1)
    assert r1.state["definition"]["steps"][4]["title"] == "Finish"  # revision 1 is immutable


# --- LS-007 -------------------------------------------------------------------------------------
def test_LS007_parameterized_template_for_multiple_products(env):
    publish(env, "TPL")
    a = env.ps.create_instance(env.ctx("op1"), "TPL", site_id="S1", params={"target_ph": 6.8, "product": "mAb-A"})
    b = env.ps.create_instance(env.ctx("op1"), "TPL", site_id="S1", params={"target_ph": 7.1, "product": "AAV-B"})
    assert a["steps_def"]["prep"]["title"] == "Prepare mAb-A medium" and b["steps_def"]["prep"]["title"] == "Prepare AAV-B medium"
    assert a["steps_def"]["prep"]["parameters"][0]["low"] == 6.8 and b["steps_def"]["prep"]["parameters"][0]["low"] == 7.1
    with pytest.raises(ValueError, match="unknown template parameters"):
        env.ps.create_instance(env.ctx("op1"), "TPL", site_id="S1", params={"nope": 1})
    with pytest.raises(ValueError, match="must be numeric"):
        env.ps.create_instance(env.ctx("op1"), "TPL", site_id="S1", params={"target_ph": "high"})


def test_LS007_amendment_requires_approval_keeps_redline_and_completed_history(env):
    ctx = env.ctx("op1")
    d = recipe()
    del d["steps"][1]["branch"]
    d["steps"].insert(2, {"step_id": "late", "title": "Late reading", "kind": "data_entry", "depends_on": ["calc"],
                          "parameters": [{"name": "od", "unit": "AU", "low": 0.1, "high": 0.5}]})
    d["steps"][3]["depends_on"] = d["steps"][4]["depends_on"] = ["late"]
    publish(env, "AM2", definition=d)
    inst = env.ps.create_instance(ctx, "AM2", site_id="S1")
    iid = inst["instance_id"]
    with env.s.transaction("op1") as tx:
        rec = tx.require(T, "procedure_instance", iid)
        st = copy.deepcopy(rec.state)
        st["status"] = "in_progress"
        st["steps"]["prep"]["status"] = "completed"
        st["values"] = {"ph": 7.1, "temp": 37.0}
        tx.put(T, "procedure_instance", iid, st, expected_revision=rec.revision, action="test_setup")
    change = {"step_id": "late", "parameter": "od", "field": "high", "value": 0.8}
    with pytest.raises(ValueError, match="cannot be amended"):  # prep is already completed
        env.ps.amend_instance(ctx, iid, {"step_id": "prep", "parameter": "temp", "field": "high", "value": 38}, "late")
    with pytest.raises(ValueError):
        env.ps.amend_instance(ctx, iid, {"step_id": "late", "parameter": "nope", "field": "high", "value": 1}, "bad param")
    amd = env.ps.amend_instance(ctx, iid, change, "assay range wider for this lot")
    assert amd["status"] == "requested"
    prop = env.s.read().require(T, "proposal", amd["proposal_id"])
    assert prop.state["operation"] == "change_recipe_parameter" and prop.state["status"] == "proposed"
    with pytest.raises(PermissionError):  # not approved yet
        env.ps.apply_amendment(env.ctx("eng1"), amd["amendment_id"])
    assert env.ps.get_instance(ctx, iid)["steps_def"]["late"]["parameters"][0]["high"] == 0.5
    approve(env, amd["proposal_id"], roles=("qa", "msat"))
    redline = env.ps.apply_amendment(env.ctx("eng1"), amd["amendment_id"])
    assert redline["before"] == 0.5 and redline["after"] == 0.8 and redline["reason"] == "assay range wider for this lot"
    assert {a["role"] for a in redline["approval"]} == {"qa", "msat"}
    after = env.ps.get_instance(ctx, iid)
    assert after["steps_def"]["late"]["parameters"][0]["high"] == 0.8
    assert after["steps"]["prep"]["status"] == "completed" and after["values"] == {"ph": 7.1, "temp": 37.0}
    assert redline["completed_steps_at_time"] == ["prep"] and after["revision"] == 1  # pinned revision unchanged
    with pytest.raises(ValueError):  # cannot be applied twice
        env.ps.apply_amendment(env.ctx("eng1"), amd["amendment_id"])


def test_LS007_apply_rejects_step_completed_after_request(env):
    publish(env, "AM3")
    inst = env.ps.create_instance(env.ctx("op1"), "AM3", site_id="S1")
    iid = inst["instance_id"]
    amd = env.ps.amend_instance(env.ctx("op1"), iid, {"step_id": "prep", "parameter": "temp", "field": "high", "value": 38}, "warm")
    approve(env, amd["proposal_id"], roles=("qa", "msat"))
    with env.s.transaction("op1") as tx:  # the step completes while the amendment waits for approval
        rec = tx.require(T, "procedure_instance", iid)
        st = copy.deepcopy(rec.state)
        st["steps"]["prep"]["status"] = "completed"
        tx.put(T, "procedure_instance", iid, st, expected_revision=rec.revision, action="test_setup")
    with pytest.raises(ValueError, match="cannot be amended"):
        env.ps.apply_amendment(env.ctx("eng1"), amd["amendment_id"])
    assert env.ps.get_instance(env.ctx("op1"), iid)["steps_def"]["prep"]["parameters"][1]["high"] == 37.5


def test_LS007_not_applicable_needs_reason_and_supervisor(env):
    publish(env, "NA")
    iid = env.ps.create_instance(env.ctx("op1"), "NA", site_id="S1")["instance_id"]
    with pytest.raises(ValueError, match="requires a reason"):
        env.ps.mark_not_applicable(env.ctx("sup1"), iid, "hi", " ")
    with pytest.raises(AuthorizationError):
        env.ps.mark_not_applicable(env.ctx("op1"), iid, "hi", "not needed")
    with pytest.raises(AuthorizationError):
        env.ps.mark_not_applicable(env.ctx("bot", "agent"), iid, "hi", "not needed")
    na = env.ps.mark_not_applicable(env.ctx("sup1"), iid, "hi", "product has no high-pH path")
    assert na["reason"] == "product has no high-pH path" and na["by"] == "sup1"
    inst = env.ps.get_instance(env.ctx("op1"), iid)
    assert inst["steps"]["hi"]["status"] == "not_applicable"
    audit = env.s.read().audit(T, "procedure_instance", iid)
    assert any(a.action == "not_applicable" and a.reason == "product has no high-pH path" for a in audit)


# --- LS-014 / LS-016 --------------------------------------------------------------------------------
def test_LS016_site_override_records_parent_revision_and_validates_range(env):
    publish(env, "GT")
    ctx = env.ctx("eng1")
    v = env.ps.adapt_for_site(ctx, "GT", 1, "S1", {"ph": {"low": 7.0, "high": 7.3}})
    assert v["parent"]["procedure_id"] == "GT" and v["parent"]["revision"] == 1 and v["scope"] == "site"
    assert v["draft"]["steps"][0]["parameters"][0]["low"] == 7.0
    tpl = env.s.read().revision(T, "procedure_revision", "GT@1", 1)
    assert tpl.state["definition"]["steps"][0]["parameters"][0]["low"] == "{{target_ph}}"  # template untouched
    with pytest.raises(ProcedureInvalid, match="outside allowed site range"):
        env.ps.adapt_for_site(ctx, "GT", 1, "S1", {"ph": {"low": 5.0}})
    with pytest.raises(ProcedureInvalid, match="not site adjustable"):
        env.ps.adapt_for_site(ctx, "GT", 1, "S1", {"temp": {"high": 37.4}})
    with pytest.raises(ProcedureInvalid, match="unknown parameter"):
        env.ps.adapt_for_site(ctx, "GT", 1, "S1", {"zzz": {"high": 1}})
    with pytest.raises(AuthorizationError):  # engineer at S1 cannot adapt for S2
        env.ps.adapt_for_site(ctx, "GT", 1, "S2", {})


def test_LS014_site_variant_local_approval_tracked_separately(env):
    publish(env, "GM", category="lab_method")
    ctx = env.ctx("eng1")
    env.ps.adapt_for_site(ctx, "GM", 1, "S1", {"ph": {"high": 7.3}})
    st = env.ps.site_variant_status(ctx, "GM~S1")
    assert st["local_approval"]["status"] == "not_submitted" and st["parent_is_current"] and st["parent"]["revision"] == 1
    prop = env.ps.submit_for_publication(ctx, "GM~S1", rationale="local use")
    assert env.ps.site_variant_status(ctx, "GM~S1")["local_approval"]["status"] == "pending"
    assert env.s.read().require(T, "procedure", "GM").state["effective_revision"] == 1  # global unaffected
    approve(env, prop["proposal_id"])
    rev = env.ps.publish(ctx, "GM~S1", prop["proposal_id"])
    assert rev["parent"]["revision"] == 1
    st = env.ps.site_variant_status(ctx, "GM~S1")
    assert st["local_approval"]["status"] == "approved" and st["local_approval"]["revision"] == 1
    inst = env.ps.create_instance(env.ctx("op1"), "GM~S1", site_id="S1")
    assert inst["steps_def"]["prep"]["parameters"][0]["high"] == 7.3
    with pytest.raises(AuthorizationError):  # site-scoped variant is not readable from another site
        env.ps.create_instance(env.idn.context_for(T, "eng2"), "GM~S1", site_id="S2")
    with pytest.raises(ValueError, match="applies to site S1 only"):
        env.ps.create_instance(env.ctx("qa1"), "GM~S1", site_id="S2")
    # new template revision -> variant reports its parent is no longer current
    d2 = recipe()
    d2["steps"][4]["title"] = "Finish v2"
    env.ps.update_draft(ctx, "GM", d2, expected_revision=env.s.read().require(T, "procedure", "GM").revision)
    publish(env, "GM", create=False)
    assert env.ps.site_variant_status(ctx, "GM~S1")["parent_is_current"] is False


# --- LS-034 ---------------------------------------------------------------------------------------------
DOC = """Cell expansion work instruction
1. Warm the medium to 37 ± 0.5 °C before use.
Step 2: Adjust pH to between 6.8 and 7.2 using base.
3) Record the viable cell density and proceed.
"""


def _ingest(env, text=DOC, site="S1"):
    return env.ev.ingest(env.ctx("eng1"), source_system="DMS", source_record_id="SOP-1", content=text.encode(),
                         media_type="text/plain", site_id=site, event_time=None)


def test_LS034_baseline_parser_extracts_steps_ranges_and_spans():
    parsed = parse_procedure_text(DOC)
    assert [s["step_number"] for s in parsed["steps"]] == [1, 2, 3] and parsed["issues"] == []
    for s in parsed["steps"]:
        sp = s["source_span"]
        assert DOC[sp["start"]:sp["end"]] == sp["text"] == s["text"]
        for p in s["parameters"]:
            ps_ = p["source_span"]
            assert DOC[ps_["start"]:ps_["end"]] == ps_["text"]
    p1 = parsed["steps"][0]["parameters"][0]
    assert (p1["low"], p1["high"], p1["target"], p1["unit"]) == (36.5, 37.5, 37.0, "degC")
    assert p1["name_unresolved"] is True  # no quantity keyword precedes the range; reviewer must name it
    assert p1["source_span"]["text"] == "37 ± 0.5 °C"
    p2 = parsed["steps"][1]["parameters"][0]
    assert (p2["low"], p2["high"], p2["unit"], p2["name"]) == (6.8, 7.2, "pH", "pH")
    assert p2["source_span"]["text"] == "between 6.8 and 7.2"
    assert parsed["steps"][2]["parameters"] == [] and parsed["steps"][2]["kind"] == "instruction"
    assert parse_procedure_text("no steps here")["issues"] == ["no numbered steps found"]


def test_LS034_interpretation_is_draft_cannot_publish_without_review(env):
    ev = _ingest(env)
    out = env.ps.interpret_document(env.ctx("eng1"), ev["evidence_id"], DOC, media=[{"type": "video", "ref": "vid://warm"}],
                                    supported_devices=["tablet", "wearable"])
    assert out["status"] == "draft_requires_review" and out["requires_human_review"] is True
    assert out["device_guidance_status"] == "declared, not device-tested" and out["media"][0]["ref"] == "vid://warm"
    assert out["inputs"][0]["id"] == ev["evidence_id"]
    rec = env.s.read().require(T, "procedure_interpretation", out["id"])
    assert rec.state["status"] == "draft_requires_review"
    assert ("evidence", ev["evidence_id"], "input_of") in env.s.read().edges_to(T, "procedure_interpretation", out["id"]) or \
        any(k == "evidence" for k, _, _ in env.s.read().edges_to(T, "procedure_interpretation", out["id"]))
    draft = env.ps.draft_from_interpretation(env.ctx("eng1"), out["id"], "SOP1", name="Expansion", site_id="S1")
    assert draft["status"] == "draft" and draft["validation_errors"] == []
    assert draft["draft"]["steps"][0]["parameters"][0]["unit"] == "degC"
    assert draft["draft"]["steps"][0]["device_guidance_status"] == "declared, not device-tested"
    assert draft["draft"]["steps"][1]["depends_on"] == ["S1"]
    with pytest.raises(PermissionError):  # publication still needs a proposal and approval
        prop = env.ps.submit_for_publication(env.ctx("eng1"), "SOP1", rationale="reviewed against SOP")
        env.ps.publish(env.ctx("eng1"), "SOP1", prop["proposal_id"])
    approve(env, prop["proposal_id"])
    assert env.ps.publish(env.ctx("eng1"), "SOP1", prop["proposal_id"])["revision"] == 1


def test_LS034_interpretation_requires_read_access_to_evidence(env):
    ev = _ingest(env)
    with pytest.raises(AuthorizationError):
        env.ps.interpret_document(env.ctx("eng2"), ev["evidence_id"], DOC)


def test_LS034_gateway_output_is_merged_but_stays_draft_and_spans_verified(env):
    ev = _ingest(env)
    span = {"start": DOC.index("Warm"), "end": DOC.index("Warm") + 4, "text": "Warm"}

    class Gateway:
        calls = []

        def run(self, req):
            Gateway.calls.append(req.task_kind)
            return SimpleNamespace(run_id="run1", status="completed", issues=[], output={"steps": [
                {"step_number": 1, "title": "Warm medium", "source_span": span},
                {"step_number": 9, "title": "Hallucinated", "source_span": {"start": 5000, "end": 5010}}]})

    out = env.ps.interpret_document(env.ctx("eng1"), ev["evidence_id"], DOC, gateway=Gateway())
    assert Gateway.calls == ["procedure_interpretation"] and out["status"] == "draft_requires_review"
    assert out["model_suggestions"]["verified_steps"] == 1 and len(out["model_suggestions"]["rejected_items"]) == 1
    assert out["steps"][0]["model_suggestions"][0]["span_verified"] is True
    assert out["produced_by"]["method"] == "baseline_regex_v1+gateway"
    assert len(out["steps"]) == 3  # baseline steps kept; the unverifiable step was not merged


def test_LS034_invalid_media_rejected(env):
    ev = _ingest(env)
    with pytest.raises(ValueError):
        env.ps.interpret_document(env.ctx("eng1"), ev["evidence_id"], DOC, media=[{"type": "hologram", "ref": "x"}])


# --- LS-003 (support) -----------------------------------------------------------------------------------
def test_LS003_supported_devices_marked_declared_not_tested(env):
    d = env.ps.create_draft(env.ctx("eng1"), "DEV", name="d", category="work_instruction", definition=recipe())
    assert d["draft"]["steps"][0]["supported_devices"] == ["tablet"]
    assert d["draft"]["steps"][0]["device_guidance_status"] == "declared, not device-tested"
