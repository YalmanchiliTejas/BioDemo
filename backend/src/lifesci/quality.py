"""Claims, editable forms, prior-investigation reuse, QA review packages and review coverage.

Implements LS-064 (claim classes, counterevidence, claim view), LS-070 (owner-approved
prior-investigation reuse), LS-071 (field-level evidence, unresolved markers, QA correction
dependencies), the editable-artifact part of LS-021 and the claim/outcome separation that
supports LS-060. Every claim, form field and package is a derived record whose inputs form
dependency edges, so a corrected source or a field returned by QA marks every dependent
conclusion, approval and package stale instead of leaving it authorizing changed content.
A QA review package approval is a distinct object from any operational action authorization.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .actions import ActionService
from .evidence import STATUS_CURRENT, EvidenceRef, EvidenceService
from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import content_hash, iso, new_id, utc_now
from .records import SignatureService
from .store import ConflictError, NotFoundError, RecordStore, Transaction

CLAIM_CLASSES = ("observation", "calculation", "hypothesis", "recommendation", "unknown")
SEARCH_STATUSES = ("searched_found", "searched_none", "not_searched")
CLAIM_LABELS = {
    "observation": "Observation (sourced)", "calculation": "Calculation (reproducible)",
    "hypothesis": "Hypothesis (not verified)", "recommendation": "Recommendation (not approved)",
    "unknown": "Unknown (unresolved)",
}
FIELD_STATUSES = ("cited", "unresolved", "returned", "human_asserted")
ARTIFACT_KINDS = ("deviation", "capa", "report")
_PROBABILITY = re.compile(
    r"\d+(?:\.\d+)?\s*%\s*(?:\w+\s+){0,2}(?:likely|probab\w*|chance|certain\w*|confiden\w*|sure|likelihood)"
    r"|(?:probab\w*|likelihood|chance|odds|confidence)\W+(?:\w+\W+){0,3}?(?:\d+(?:\.\d+)?\s*%|0?\.\d+)", re.I)


class ClaimRejected(ValueError):
    """A claim violates the classification rules and was not recorded."""


def _as_ref(value: Any) -> EvidenceRef:
    if isinstance(value, EvidenceRef):
        return value
    return EvidenceRef(value["kind"], value["id"], int(value["revision"]), value.get("site_id"))


def _unique(refs: Iterable[Any]) -> list[EvidenceRef]:
    seen: set[tuple[str, str]] = set()
    out: list[EvidenceRef] = []
    for r in map(_as_ref, refs):
        if (r.kind, r.id) not in seen:
            seen.add((r.kind, r.id))
            out.append(r)
    return out


def field_id(form_id: str, name: str) -> str:
    return f"{form_id}.{name}"


def _require_person(ctx: AccessContext, what: str) -> None:
    if ctx.actor_kind != "person":
        raise AuthorizationError(Decision(False, f"{what} requires a human actor; {ctx.actor_kind} credentials cannot"))


# --- cases -------------------------------------------------------------------------
class CaseService:
    """Minimal deviation-case record: investigation owner, QA reviewer, timeline and procedures."""

    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def open(self, ctx: AccessContext, case_id: str, owner_id: str, qa_reviewer_id: str, site_id: str) -> dict[str, Any]:
        self.identity.require(ctx, "propose", "case", case_id, site_id=site_id)
        state = {"case_id": case_id, "owner_id": owner_id, "qa_reviewer_id": qa_reviewer_id, "site_id": site_id,
                 "timeline": [], "procedure_refs": [], "status": "open", "opened_at": iso(utc_now()),
                 "opened_by": ctx.actor_id}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, "case", case_id, state, expected_revision=None, action="open_case",
                         event_type="case.opened", event_payload={"case_id": case_id, "site_id": site_id})
        return {**rec.state, "revision": rec.revision}

    def get(self, ctx: AccessContext, case_id: str, tx: Transaction | None = None) -> dict[str, Any]:
        tx = tx or self.store.read()
        rec = tx.require(ctx.tenant_id, "case", case_id)
        self.identity.require(ctx, "read", "case", case_id, site_id=rec.state["site_id"], tx=tx)
        return {**rec.state, "revision": rec.revision}

    def ref(self, ctx: AccessContext, case_id: str) -> EvidenceRef:
        case = self.get(ctx, case_id)
        return EvidenceRef("case", case_id, case["revision"], case["site_id"])

    def add_timeline_event(self, ctx: AccessContext, case_id: str, event_time: str, description: str,
                           evidence_refs: Iterable[Any] = ()) -> dict[str, Any]:
        refs = [r.to_dict() for r in _unique(evidence_refs)]
        return self._update(ctx, case_id, "timeline_event", lambda s: {
            **s, "timeline": sorted([*s["timeline"], {"time": event_time, "description": description,
                                                      "evidence_refs": refs, "added_by": ctx.actor_id}],
                                    key=lambda e: e["time"])})

    def set_procedures(self, ctx: AccessContext, case_id: str, procedure_refs: list[dict[str, Any]]) -> dict[str, Any]:
        for p in procedure_refs:
            if not p.get("id") or p.get("revision") is None:
                raise ValueError("procedure references must carry id and revision")
        return self._update(ctx, case_id, "set_procedures", lambda s: {**s, "procedure_refs": list(procedure_refs)})

    def _update(self, ctx: AccessContext, case_id: str, action: str, change) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "case", case_id)
            self.identity.require(ctx, "propose", "case", case_id, site_id=rec.state["site_id"], tx=tx)
            out = tx.put(ctx.tenant_id, "case", case_id, change(rec.state), expected_revision=rec.revision, action=action)
        return {**out.state, "revision": out.revision}


def _case_lineage(tx: Transaction, ctx: AccessContext, case_id: str) -> EvidenceRef:
    rec = tx.require(ctx.tenant_id, "case", case_id)
    return EvidenceRef("case", case_id, rec.revision, rec.state["site_id"])


# --- claims (LS-064) -----------------------------------------------------------------
class ClaimService:
    def __init__(self, store: RecordStore, identity: IdentityService, evidence: EvidenceService) -> None:
        self.store = store
        self.identity = identity
        self.evidence = evidence

    def record_claim(self, ctx: AccessContext, case_id: str, text: str, claim_class: str,
                     evidence_refs: Iterable[Any], counterevidence_refs: Iterable[Any],
                     calculation_ref: Any = None, unknowns: Iterable[str] = (), *,
                     counterevidence_status: str | None = None, field_refs: Iterable[tuple[str, str]] = (),
                     predicted_benefit: str | None = None, outcome_of: str | None = None,
                     attribution_limits: Iterable[str] = (), artifact_id: str | None = None) -> dict[str, Any]:
        """Record a labeled claim. Re-derive an existing claim (after correction) by passing its artifact_id."""
        if claim_class == "verified_cause":
            raise ClaimRejected("'verified_cause' is not a recordable class: causes stay hypotheses until approved by review")
        if claim_class not in CLAIM_CLASSES:
            raise ClaimRejected(f"claim_class must be one of {CLAIM_CLASSES}")
        if not text or not text.strip():
            raise ClaimRejected("claim text is empty")
        ev_refs, ce_refs = _unique(evidence_refs), _unique(counterevidence_refs)
        unknowns = [u for u in unknowns if u]
        if claim_class == "calculation" and not calculation_ref:
            raise ClaimRejected("a calculation claim requires a calculation_ref")
        if claim_class in ("observation", "calculation", "recommendation") and not ev_refs:
            raise ClaimRejected(f"a {claim_class} claim requires evidence_refs")
        if claim_class == "unknown" and not unknowns:
            raise ClaimRejected("an unknown claim must list what is unknown")
        if ce_refs and counterevidence_status is None:
            counterevidence_status = "searched_found"
        if claim_class == "hypothesis" and counterevidence_status not in SEARCH_STATUSES:
            raise ClaimRejected(f"a hypothesis must state counterevidence search status: {SEARCH_STATUSES}")
        if counterevidence_status == "searched_found" and not ce_refs:
            raise ClaimRejected("searched_found requires counterevidence_refs")
        if counterevidence_status == "searched_none" and ce_refs:
            raise ClaimRejected("searched_none contradicts supplied counterevidence_refs")
        if counterevidence_status is not None and counterevidence_status not in SEARCH_STATUSES:
            raise ClaimRejected(f"counterevidence_status must be one of {SEARCH_STATUSES}")
        flags: list[str] = []
        if _PROBABILITY.search(text):
            flags.append("uncalibrated_probability")
        if not ev_refs:
            flags.append("no_supporting_evidence")
        self.identity.require(ctx, "propose", "claim", site_id=None)
        tx = self.store.read()
        site_id = tx.require(ctx.tenant_id, "case", case_id).state["site_id"]
        field_ids = [field_id(f, n) for f, n in field_refs]
        for fid in field_ids:
            f = tx.require(ctx.tenant_id, "form_field", fid)
            if f.state["field_status"] in ("unresolved", "returned") and "relies_on_unresolved_field" not in flags:
                flags.append("relies_on_unresolved_field")
        lineage = _unique([*ev_refs, *ce_refs]) or [_case_lineage(tx, ctx, case_id)]
        payload = {
            "case_id": case_id, "site_id": site_id, "text": text, "claim_class": claim_class,
            "label": CLAIM_LABELS[claim_class], "evidence_refs": [r.to_dict() for r in ev_refs],
            "counterevidence_refs": [r.to_dict() for r in ce_refs], "counterevidence_status": counterevidence_status,
            "calculation_ref": calculation_ref, "unknowns": unknowns, "flags": flags,
            "uncalibrated_probability": "uncalibrated_probability" in flags, "field_refs": field_ids,
            "predicted_benefit": predicted_benefit, "outcome_of": outcome_of,
            "attribution_limits": list(attribution_limits), "recorded_by": ctx.actor_id,
            "recorded_by_kind": ctx.actor_kind, "recorded_at": iso(utc_now()),
        }
        out = self.evidence.record_derived(ctx, "claim", payload, inputs=lineage, artifact_id=artifact_id,
                                           produced_by={"actor_id": ctx.actor_id, "actor_kind": ctx.actor_kind,
                                                        "method": "claim_service.record_claim"})
        for fid in field_ids:
            self.evidence.link(ctx, ("form_field", fid), ("claim", out["id"]), "relies_on")
        return out

    def record_outcome_observation(self, ctx: AccessContext, case_id: str, recommendation_claim_id: str, text: str,
                                   evidence_refs: Iterable[Any], attribution_limits: Iterable[str]) -> dict[str, Any]:
        """Observed outcome kept apart from the recommendation's predicted benefit (LS-060 support)."""
        rec = self.evidence.read_derived(ctx, "claim", recommendation_claim_id)
        if rec["claim_class"] != "recommendation":
            raise ClaimRejected("outcomes attach to recommendation claims")
        limits = list(attribution_limits)
        if not limits:
            raise ClaimRejected("an observed outcome must state its attribution limits")
        return self.record_claim(ctx, case_id, text, "observation", evidence_refs, [], outcome_of=recommendation_claim_id,
                                 attribution_limits=limits)

    def claim_view(self, ctx: AccessContext, claim_id: str) -> dict[str, Any]:
        c = self.evidence.read_derived(ctx, "claim", claim_id)
        tx = self.store.read()
        basis, drift = [], []
        for ref in c["evidence_refs"]:
            cur = tx.get(ctx.tenant_id, ref["kind"], ref["id"])
            now = cur.revision if cur else None
            basis.append({**ref, "current_revision": now, "digest": cur.state.get("digest") if cur else None})
            if now != ref["revision"]:
                drift.append({"ref": f"{ref['kind']}:{ref['id']}", "cited_revision": ref["revision"], "current_revision": now})
        mine = {r["id"] for r in c["evidence_refs"]}
        theirs = {r["id"] for r in c["counterevidence_refs"]}
        conflicting = [{"claim_id": o.id, "claim_class": o.state["claim_class"], "text": o.state["text"],
                        "reason": "its counterevidence overlaps this claim's evidence" if {r["id"] for r in o.state["counterevidence_refs"]} & mine
                        else "its evidence is cited as counterevidence here"}
                       for o in tx.list(ctx.tenant_id, "claim", lambda s: s["case_id"] == c["case_id"]) if o.id != claim_id
                       and o.state["status"] == STATUS_CURRENT
                       and ({r["id"] for r in o.state["counterevidence_refs"]} & mine or {r["id"] for r in o.state["evidence_refs"]} & theirs)]
        unresolved = list(c["unknowns"])
        if c["claim_class"] == "hypothesis" and c["counterevidence_status"] == "not_searched":
            unresolved.append("counterevidence has not been searched")
        for fid in c["field_refs"]:
            f = tx.get(ctx.tenant_id, "form_field", fid)
            if f and f.state["field_status"] in ("unresolved", "returned"):
                unresolved.append(f"field {fid} is {f.state['field_status']}")
        stale = c["status"] != STATUS_CURRENT or bool(drift)
        view = {
            "claim_id": claim_id, "claim_class": c["claim_class"], "label": c["label"], "text": c["text"],
            "evidence_basis": basis, "calculation_ref": c["calculation_ref"],
            "contradictions": {"counterevidence": c["counterevidence_refs"],
                               "counterevidence_status": c["counterevidence_status"], "conflicting_claims": conflicting},
            "uncertainty": {"flags": c["flags"], "uncalibrated_probability": c["uncalibrated_probability"],
                            "unknowns": c["unknowns"], "verified": False},
            "unresolved": unresolved,
            "staleness": {"stale": stale, "status": c["status"], "reasons": c.get("stale_reasons", []), "evidence_drift": drift},
        }
        if c["claim_class"] == "recommendation":
            view["predicted_benefit"] = c["predicted_benefit"]
            view["observed_outcomes"] = [{"claim_id": o.id, "text": o.state["text"], "attribution_limits": o.state["attribution_limits"],
                                          "evidence_refs": o.state["evidence_refs"]}
                                         for o in tx.list(ctx.tenant_id, "claim", lambda s: s.get("outcome_of") == claim_id)]
            view["effect_confirmed"] = False
        return view

    def claims_for_case(self, ctx: AccessContext, case_id: str) -> list[dict[str, Any]]:
        tx = self.store.read()
        return [{"id": r.id, "revision": r.revision, **r.state}
                for r in tx.list(ctx.tenant_id, "claim", lambda s: s["case_id"] == case_id)]


# --- editable forms (LS-071) ------------------------------------------------------------
class FormService:
    def __init__(self, store: RecordStore, identity: IdentityService, evidence: EvidenceService,
                 signatures: SignatureService) -> None:
        self.store = store
        self.identity = identity
        self.evidence = evidence
        self.signatures = signatures

    def draft(self, ctx: AccessContext, case_id: str, template: str, fields: list[dict[str, Any]],
              form_id: str | None = None) -> dict[str, Any]:
        """Field = {name, value, evidence_refs, status}. A field without evidence is always unresolved; its value is withheld."""
        tx = self.store.read()
        case = tx.require(ctx.tenant_id, "case", case_id).state
        self.identity.require(ctx, "propose", "form", site_id=case["site_id"], tx=tx)
        names = [f["name"] for f in fields]
        if len(set(names)) != len(names):
            raise ValueError("duplicate field names")
        form_id = form_id or new_id("form")
        out: dict[str, dict[str, Any]] = {}
        for f in fields:
            requested = f.get("status", "cited")
            if requested not in ("cited", "unresolved"):
                raise ValueError(f"draft field status must be cited or unresolved, got {requested}")
            refs = _unique(f.get("evidence_refs") or [])
            cited = bool(refs) and requested == "cited"
            reason = None if cited else ("no supporting evidence; left unresolved" if not refs else "marked unresolved by drafter")
            payload = {"form_id": form_id, "case_id": case_id, "name": f["name"], "site_id": case["site_id"],
                       "value": f.get("value") if cited else None,
                       "uncited_suggestion": None if cited else f.get("value"),
                       "field_status": "cited" if cited else "unresolved", "unresolved_reason": reason,
                       "evidence_refs": [r.to_dict() for r in refs], "edits": [], "return_history": []}
            fid = field_id(form_id, f["name"])
            out[f["name"]] = self.evidence.record_derived(
                ctx, "form_field", payload, inputs=refs or [_case_lineage(tx, ctx, case_id)], artifact_id=fid,
                produced_by={"actor_id": ctx.actor_id, "actor_kind": ctx.actor_kind, "method": "form_service.draft"})
        state = {"form_id": form_id, "case_id": case_id, "site_id": case["site_id"], "template": template,
                 "field_names": names, "review_state": "draft_requires_review", "created_by": ctx.actor_id}
        with self.store.transaction(ctx.actor_id) as w:
            w.put(ctx.tenant_id, "form", form_id, state, expected_revision=None, action="draft_form",
                  event_type="form.drafted", event_payload={"form_id": form_id, "case_id": case_id})
        return {**state, "fields": out, "unresolved": [n for n, f in out.items() if f["field_status"] != "cited"]}

    def view(self, ctx: AccessContext, form_id: str) -> dict[str, Any]:
        tx = self.store.read()
        form = tx.require(ctx.tenant_id, "form", form_id)
        self.identity.require(ctx, "read", "form", form_id, site_id=form.state["site_id"], tx=tx)
        fields = {n: {"revision": r.revision, **r.state} for n in form.state["field_names"]
                  if (r := tx.require(ctx.tenant_id, "form_field", field_id(form_id, n)))}
        return {**form.state, "fields": fields,
                "unresolved": [n for n, f in fields.items() if f["field_status"] in ("unresolved", "returned")],
                "returned": [n for n, f in fields.items() if f["field_status"] == "returned"],
                "stale_fields": [n for n, f in fields.items() if f["status"] != STATUS_CURRENT]}

    def edit_field(self, ctx: AccessContext, form_id: str, field: str, value: Any, expected_revision: int,
                   evidence_refs: Iterable[Any] = (), reason: str | None = None) -> dict[str, Any]:
        """Human edit with audit. Dependents of the previous value become stale; new evidence makes the field cited."""
        _require_person(ctx, "editing a form field")
        fid = field_id(form_id, field)
        refs = _unique(evidence_refs)
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "form_field", fid)
            self.identity.require(ctx, "propose", "form_field", fid, site_id=rec.state["site_id"], tx=tx)
            if rec.revision != expected_revision:
                raise ConflictError(f"form_field:{fid} is at revision {rec.revision}; edit targeted {expected_revision}")
            s = rec.state
            inputs = _unique([*[i for i in s["inputs"] if i["kind"] != "case"], *refs]) if refs else None
            state = {**s, "value": value, "uncited_suggestion": None, "unresolved_reason": None,
                     "field_status": "cited" if refs else "human_asserted",
                     "evidence_refs": [r.to_dict() for r in refs] if refs else s["evidence_refs"],
                     "inputs": [i.to_dict() for i in inputs] if inputs else s["inputs"],
                     "edits": [*s["edits"], {"by": ctx.actor_id, "at": iso(utc_now()), "previous_value": s["value"],
                                             "new_value": value, "reason": reason, "cited": bool(refs)}]}
            out = tx.put(ctx.tenant_id, "form_field", fid, state, expected_revision=rec.revision, action="human_edit",
                         reason=reason, details={"previous_value": s["value"], "new_value": value},
                         event_type="form_field.edited", event_payload={"form_id": form_id, "field": field})
            for r in refs:
                tx.add_edge(ctx.tenant_id, (r.kind, r.id), ("form_field", fid), "input_of")
        invalidated = self.evidence.invalidate(ctx, "form_field", fid, f"field {field} edited by {ctx.actor_id}")
        return {"field_id": fid, "revision": out.revision, **out.state, "invalidated": invalidated}

    def return_field_for_correction(self, ctx_qa: AccessContext, form_id: str, field: str, reason: str) -> dict[str, Any]:
        _require_person(ctx_qa, "returning a field for correction")
        if not reason or not reason.strip():
            raise ValueError("a return for correction requires a reason")
        fid = field_id(form_id, field)
        with self.store.transaction(ctx_qa.actor_id) as tx:
            rec = tx.require(ctx_qa.tenant_id, "form_field", fid)
            self.identity.require(ctx_qa, "approve", "form_field", fid, site_id=rec.state["site_id"], tx=tx)
            s = rec.state
            state = {**s, "field_status": "returned", "returned_by": ctx_qa.actor_id, "returned_reason": reason,
                     "return_history": [*s["return_history"], {"by": ctx_qa.actor_id, "at": iso(utc_now()), "reason": reason}]}
            out = tx.put(ctx_qa.tenant_id, "form_field", fid, state, expected_revision=rec.revision,
                         action="return_for_correction", reason=reason, event_type="form_field.returned",
                         event_payload={"form_id": form_id, "field": field})
        invalidated = self.evidence.invalidate(ctx_qa, "form_field", fid, f"QA returned field {field}: {reason}")
        return {"field_id": fid, "field_status": "returned", "revision": out.revision, "invalidated": invalidated}

    def approve_form(self, ctx: AccessContext, form_id: str, authentication: dict[str, Any],
                     accept_unresolved: bool = False) -> dict[str, Any]:
        """Signed approval bound to the exact field revisions; every field edge makes it stale if any field changes."""
        view = self.view(ctx, form_id)
        blocking = [n for n, f in view["fields"].items() if f["field_status"] == "returned" or f["status"] != STATUS_CURRENT]
        if blocking:
            raise ValueError(f"fields returned or stale cannot be approved: {blocking}")
        if view["unresolved"] and not accept_unresolved:
            raise ValueError(f"unresolved fields remain: {view['unresolved']}")
        approval_id = new_id("fapr")
        state = {"form_id": form_id, "case_id": view["case_id"], "site_id": view["site_id"],
                 "field_revisions": {n: f["revision"] for n, f in view["fields"].items()},
                 "accepted_unresolved": list(view["unresolved"]), "approved_by": ctx.actor_id,
                 "status": STATUS_CURRENT, "stale_reasons": []}
        self.identity.require(ctx, "approve", "form_approval", site_id=view["site_id"])
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "form_approval", approval_id, state, expected_revision=None, action="approve_form",
                   event_type="form.approved", event_payload={"form_id": form_id})
            for n in view["fields"]:
                tx.add_edge(ctx.tenant_id, ("form_field", field_id(form_id, n)), ("form_approval", approval_id), "approved_content")
        sig = self.signatures.sign(ctx, "form_approval", approval_id, expected_revision=1, meaning="approved",
                                   authentication=authentication, site_id=view["site_id"])
        return {"approval_id": approval_id, "signature_id": sig.signature_id, **state}

    def approval_valid(self, tenant_id: str, approval_id: str) -> dict[str, Any]:
        return _approval_status(self.store, self.signatures, tenant_id, "form_approval", approval_id)


def _approval_status(store: RecordStore, signatures: SignatureService, tenant_id: str, kind: str, approval_id: str) -> dict[str, Any]:
    tx = store.read()
    rec = tx.require(tenant_id, kind, approval_id)
    covered = any(signatures.verify(tenant_id, s["signature_id"], tx)["covers_current_content"]
                  for s in signatures.signatures_for(tenant_id, kind, approval_id, tx))
    valid = rec.state["status"] == STATUS_CURRENT and covered
    return {"approval_id": approval_id, "valid": valid, "status": rec.state["status"], "signature_covers_current_content": covered,
            "reasons": rec.state.get("stale_reasons", [])}


# --- prior-investigation reuse (LS-070) --------------------------------------------------------
class ReuseService:
    """Reuse needs the investigation owner's explicit approval of exactly the stated intended reuse."""

    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def request(self, ctx: AccessContext, case_id: str, prior_case_id: str, summary: str,
                similarities: list[str], differences: list[str], intended_reuse: str) -> dict[str, Any]:
        if not (summary and similarities and differences and intended_reuse and intended_reuse.strip()):
            raise ValueError("a reuse request must show summary, similarities, differences and intended reuse")
        tx = self.store.read()
        case, prior = tx.require(ctx.tenant_id, "case", case_id), tx.require(ctx.tenant_id, "case", prior_case_id)
        self.identity.require(ctx, "propose", "reuse_request", site_id=case.state["site_id"], tx=tx)
        self.identity.require(ctx, "read", "case", prior_case_id, site_id=prior.state["site_id"], tx=tx)
        rid = new_id("reuse")
        state = {"request_id": rid, "case_id": case_id, "prior_case_id": prior_case_id, "summary": summary,
                 "similarities": list(similarities), "differences": list(differences), "intended_reuse": intended_reuse,
                 "prior_case_revision": prior.revision, "prior_case_hash": prior.content_hash,
                 "owner_id": case.state["owner_id"], "requested_by": ctx.actor_id, "requested_by_kind": ctx.actor_kind,
                 "status": "pending", "decided_by": None, "decided_at": None, "requested_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as w:
            rec = w.put(ctx.tenant_id, "reuse_request", rid, state, expected_revision=None, action="request_reuse",
                        event_type="reuse.requested", event_payload={"request_id": rid, "case_id": case_id})
        return {**rec.state, "revision": rec.revision}

    def decide(self, ctx_owner: AccessContext, request_id: str, decision: str, expected_revision: int | None = None,
               comment: str | None = None) -> dict[str, Any]:
        verdict = {"approve": "approved", "approved": "approved", "reject": "rejected", "rejected": "rejected"}.get(decision)
        if verdict is None:
            raise ValueError("decision must be approve or reject")
        with self.store.transaction(ctx_owner.actor_id) as tx:
            rec = tx.require(ctx_owner.tenant_id, "reuse_request", request_id)
            case = tx.require(ctx_owner.tenant_id, "case", rec.state["case_id"]).state
            if ctx_owner.actor_kind != "person" or ctx_owner.actor_id != case["owner_id"]:
                raise AuthorizationError(Decision(False, "only the case's investigation owner can decide prior-investigation reuse"))
            self.identity.require(ctx_owner, "read", "case", rec.state["case_id"], site_id=case["site_id"], tx=tx)
            if expected_revision is not None and rec.revision != expected_revision:
                raise ConflictError(f"reuse_request at revision {rec.revision}; decision targeted {expected_revision}")
            if rec.state["status"] != "pending":
                raise ValueError(f"reuse request already {rec.state['status']}")
            state = {**rec.state, "status": verdict, "decided_by": ctx_owner.actor_id, "decided_at": iso(utc_now()),
                     "decision_comment": comment}
            out = tx.put(ctx_owner.tenant_id, "reuse_request", request_id, state, expected_revision=rec.revision,
                         action=f"reuse_{verdict}", reason=comment, event_type=f"reuse.{verdict}",
                         event_payload={"request_id": request_id})
        return {**out.state, "revision": out.revision}

    def explain(self, ctx: AccessContext, case_id: str, prior_case_id: str, purpose: str) -> dict[str, Any]:
        tx = self.store.read()
        prior = tx.get(ctx.tenant_id, "case", prior_case_id)
        want = (purpose or "").strip().casefold()
        reason, matched = "no approved request for this prior case and purpose", None
        for r in tx.list(ctx.tenant_id, "reuse_request", lambda s: s["case_id"] == case_id and s["prior_case_id"] == prior_case_id):
            s = r.state
            if s["intended_reuse"].strip().casefold() != want:
                continue
            if s["status"] == "pending":
                reason, matched = "request pending: silence is not approval", r.id
            elif s["status"] == "rejected":
                reason, matched = "request rejected", r.id
            elif prior is None or prior.revision != s["prior_case_revision"]:
                reason, matched = "prior investigation changed after approval; re-approval required", r.id
            else:
                return {"allowed": True, "request_id": r.id, "reason": "approved by investigation owner for exactly this reuse"}
        return {"allowed": False, "request_id": matched, "reason": reason}

    def reuse_allowed(self, ctx: AccessContext, case_id: str, prior_case_id: str, purpose: str) -> bool:
        return self.explain(ctx, case_id, prior_case_id, purpose)["allowed"]

    def requests_for_case(self, ctx: AccessContext, case_id: str) -> list[dict[str, Any]]:
        tx = self.store.read()
        out = []
        for r in tx.list(ctx.tenant_id, "reuse_request", lambda s: s["case_id"] == case_id):
            s = r.state
            prior = tx.get(ctx.tenant_id, "case", s["prior_case_id"])
            changed = prior is None or prior.revision != s["prior_case_revision"]
            effective = "stale" if s["status"] == "approved" and changed else s["status"]
            out.append({"request_id": r.id, "revision": r.revision, **s, "effective_status": effective})
        return out


# --- QA review package and coverage -----------------------------------------------------------------
class PackageService:
    def __init__(self, store: RecordStore, identity: IdentityService, evidence: EvidenceService,
                 signatures: SignatureService, reuse: ReuseService | None = None) -> None:
        self.store = store
        self.identity = identity
        self.evidence = evidence
        self.signatures = signatures
        self.reuse = reuse or ReuseService(store, identity)

    def build_package(self, ctx: AccessContext, case_id: str, next_steps: Iterable[dict[str, Any]] = (),
                      procedure_refs: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
        tx = self.store.read()
        case = tx.require(ctx.tenant_id, "case", case_id)
        self.identity.require(ctx, "propose", "qa_package", site_id=case.state["site_id"], tx=tx)
        steps = [dict(s) for s in next_steps]
        for s in steps:
            if not s.get("action") or not s.get("owner_id"):
                raise ValueError("each proposed next step needs an action and a named owner")
        fields = tx.list(ctx.tenant_id, "form_field", lambda s: s["case_id"] == case_id)
        claims = tx.list(ctx.tenant_id, "claim", lambda s: s["case_id"] == case_id)
        current_claims = [c for c in claims if c.state["status"] == STATUS_CURRENT]
        by_class = {k: [{"claim_id": c.id, "revision": c.revision, "text": c.state["text"], "label": c.state["label"],
                         "flags": c.state["flags"], "evidence": [r["id"] for r in c.state["evidence_refs"]]}
                        for c in current_claims if c.state["claim_class"] == k] for k in CLAIM_CLASSES}
        field_rows = [{"field_id": f.id, "revision": f.revision, "name": f.state["name"], "value": f.state["value"],
                       "field_status": f.state["field_status"], "status": f.state["status"],
                       "evidence": [r["id"] for r in f.state["evidence_refs"]]} for f in fields]
        conflicts = []
        for c in current_claims:
            mine = {r["id"] for r in c.state["evidence_refs"]}
            for o in current_claims:
                if o.id > c.id and ({r["id"] for r in o.state["counterevidence_refs"]} & mine
                                    or {r["id"] for r in c.state["counterevidence_refs"]} & {r["id"] for r in o.state["evidence_refs"]}):
                    conflicts.append({"claims": [c.id, o.id], "reason": "evidence of one is counterevidence of the other"})
        gaps = [{"type": f"field_{r['field_status']}", "field_id": r["field_id"]} for r in field_rows if r["field_status"] != "cited"
                and r["field_status"] != "human_asserted"]
        gaps += [{"type": "stale_field", "field_id": r["field_id"]} for r in field_rows if r["status"] != STATUS_CURRENT]
        gaps += [{"type": "stale_claim", "claim_id": c.id} for c in claims if c.state["status"] != STATUS_CURRENT]
        gaps += [{"type": "unknown", "claim_id": c.id, "unknowns": c.state["unknowns"]} for c in current_claims if c.state["unknowns"]]
        gaps += [{"type": "counterevidence_not_searched", "claim_id": c.id} for c in current_claims
                 if c.state["claim_class"] == "hypothesis" and c.state["counterevidence_status"] == "not_searched"]
        gaps += [{"type": "uncalibrated_probability", "claim_id": c.id} for c in current_claims if c.state["uncalibrated_probability"]]
        procedures = [*case.state["procedure_refs"], *procedure_refs]
        reuse = [{"request_id": r["request_id"], "prior_case_id": r["prior_case_id"], "intended_reuse": r["intended_reuse"],
                  "effective_status": r["effective_status"], "decided_by": r["decided_by"]}
                 for r in self.reuse.requests_for_case(ctx, case_id)]
        content = {"case_id": case_id, "owner_id": case.state["owner_id"], "qa_reviewer_id": case.state["qa_reviewer_id"],
                   "forms": [{"form_id": f.id, "template": f.state["template"], "field_names": f.state["field_names"]}
                             for f in tx.list(ctx.tenant_id, "form", lambda s: s["case_id"] == case_id)],
                   "fields": field_rows, "timeline": case.state["timeline"], "claims_by_class": by_class,
                   "gaps": gaps, "conflicts": conflicts, "procedures": procedures, "reuse_approvals": reuse,
                   "next_steps": steps}
        content["coverage"] = self.coverage(ctx, case_id)
        inputs = [EvidenceRef("form_field", f.id, f.revision, f.state["site_id"]) for f in fields] + \
                 [EvidenceRef("claim", c.id, c.revision, c.state["site_id"]) for c in current_claims]
        payload = {"case_id": case_id, "site_id": case.state["site_id"], "content": content,
                   "package_hash": content_hash(content), "review_state": "pending_qa_review",
                   "authorizes_operational_action": False}
        return self.evidence.record_derived(ctx, "qa_package", payload,
                                            inputs=inputs or [EvidenceRef("case", case_id, case.revision, case.state["site_id"])],
                                            produced_by={"actor_id": ctx.actor_id, "actor_kind": ctx.actor_kind,
                                                         "method": "package_service.build_package"})

    def approve_package(self, ctx: AccessContext, package_id: str, authentication: dict[str, Any]) -> dict[str, Any]:
        """QA approval of this exact package content hash; it never authorizes an operational action."""
        _require_person(ctx, "approving a QA review package")
        pkg = self.evidence.read_derived(ctx, "qa_package", package_id)
        tx = self.store.read()
        case = tx.require(ctx.tenant_id, "case", pkg["case_id"]).state
        if ctx.actor_id != case["qa_reviewer_id"]:
            raise AuthorizationError(Decision(False, "only the case's QA reviewer can approve its QA review package"))
        self.identity.require(ctx, "approve", "qa_package", package_id, site_id=pkg["site_id"])
        if pkg["status"] != STATUS_CURRENT:
            raise ValueError(f"package is {pkg['status']}; rebuild it before approval")
        if content_hash(pkg["content"]) != pkg["package_hash"]:
            raise ValueError("package content does not match its recorded hash")
        blocking = [g for g in pkg["content"]["gaps"] if g["type"] in ("field_returned", "stale_field", "stale_claim")]
        if blocking:
            raise ValueError(f"package has blocking gaps: {blocking}")
        aid = new_id("papr")
        state = {"package_id": package_id, "package_revision": pkg["revision"], "package_hash": pkg["package_hash"],
                 "case_id": pkg["case_id"], "site_id": pkg["site_id"], "approved_by": ctx.actor_id,
                 "status": STATUS_CURRENT, "stale_reasons": [], "authorizes_operational_action": False}
        with self.store.transaction(ctx.actor_id) as w:
            w.put(ctx.tenant_id, "package_approval", aid, state, expected_revision=None, action="approve_package",
                  event_type="package.approved", event_payload={"package_id": package_id, "hash": pkg["package_hash"]})
            w.add_edge(ctx.tenant_id, ("qa_package", package_id), ("package_approval", aid), "approves")
        sig = self.signatures.sign(ctx, "package_approval", aid, expected_revision=1, meaning="approved",
                                   authentication=authentication, site_id=pkg["site_id"])
        return {"approval_id": aid, "signature_id": sig.signature_id, **state}

    def package_status(self, ctx: AccessContext, package_id: str) -> dict[str, Any]:
        tx = self.store.read()
        pkg = tx.require(ctx.tenant_id, "qa_package", package_id)
        self.identity.require(ctx, "read", "qa_package", package_id, site_id=pkg.state["site_id"], tx=tx)
        approvals = tx.list(ctx.tenant_id, "package_approval", lambda s: s["package_id"] == package_id)
        valid = None
        for a in approvals:
            st = _approval_status(self.store, self.signatures, ctx.tenant_id, "package_approval", a.id)
            if st["valid"] and a.state["package_hash"] == pkg.state["package_hash"] and a.state["package_revision"] == pkg.revision \
                    and pkg.state["status"] == STATUS_CURRENT:
                valid = a.id
        return {"package_id": package_id, "package_status": pkg.state["status"], "stale_reasons": pkg.state.get("stale_reasons", []),
                "approved": valid is not None, "approval_id": valid, "package_hash": pkg.state["package_hash"],
                "approvals_seen": len(approvals)}

    # --- review by exception ---------------------------------------------------------------
    def _items(self, tx: Transaction, ctx: AccessContext, case_id: str) -> list[dict[str, Any]]:
        case = tx.require(ctx.tenant_id, "case", case_id).state
        items: dict[tuple[str, str], dict[str, Any]] = {}
        evidence_ids: set[str] = set()
        for kind in ("form_field", "claim"):
            for r in tx.list(ctx.tenant_id, kind, lambda s: s["case_id"] == case_id):
                items[(kind, r.id)] = {"item_kind": kind, "item_id": r.id, "revision": r.revision}
                evidence_ids |= {i["id"] for i in r.state["inputs"] if i["kind"] == "evidence"}
        for eid in sorted(evidence_ids):
            cur = tx.get(ctx.tenant_id, "evidence", eid)
            items[("evidence", eid)] = {"item_kind": "evidence", "item_id": eid, "revision": cur.revision if cur else None}
        for p in case["procedure_refs"]:
            items[("procedure", p["id"])] = {"item_kind": "procedure", "item_id": p["id"], "revision": p["revision"]}
        return list(items.values())

    def mark_checked(self, ctx: AccessContext, case_id: str, item_kind: str, item_id: str,
                     note: str | None = None) -> dict[str, Any]:
        _require_person(ctx, "marking an item checked")
        with self.store.transaction(ctx.actor_id) as tx:
            case = tx.require(ctx.tenant_id, "case", case_id).state
            self.identity.require(ctx, "comment", "coverage_check", site_id=case["site_id"], tx=tx)
            item = next((i for i in self._items(tx, ctx, case_id) if i["item_kind"] == item_kind and i["item_id"] == item_id), None)
            if item is None:
                raise NotFoundError(f"{item_kind}:{item_id} is not an item of case {case_id}")
            cid = f"{case_id}|{item_kind}|{item_id}"
            cur = tx.get(ctx.tenant_id, "coverage_check", cid)
            state = {"case_id": case_id, "item_kind": item_kind, "item_id": item_id, "item_revision": item["revision"],
                     "checked_by": ctx.actor_id, "checked_at": iso(utc_now()), "note": note}
            tx.put(ctx.tenant_id, "coverage_check", cid, state, expected_revision=cur.revision if cur else None,
                   action="mark_checked")
        return state

    def coverage(self, ctx: AccessContext, case_id: str) -> dict[str, Any]:
        tx = self.store.read()
        checks = {(r.state["item_kind"], r.state["item_id"]): r.state
                  for r in tx.list(ctx.tenant_id, "coverage_check", lambda s: s["case_id"] == case_id)}
        checked, unchecked = [], []
        for item in self._items(tx, ctx, case_id):
            c = checks.get((item["item_kind"], item["item_id"]))
            if c is None:
                unchecked.append({**item, "reason": "never_checked"})
            elif c["item_revision"] != item["revision"]:
                unchecked.append({**item, "reason": "changed_since_check", "checked_revision": c["item_revision"]})
            else:
                checked.append({**item, "checked_by": c["checked_by"], "checked_at": c["checked_at"]})
        total = len(checked) + len(unchecked)
        return {"case_id": case_id, "checked": checked, "unchecked": unchecked, "total": total,
                "complete": total > 0 and not unchecked,
                "statement": "no reviewable items recorded; an empty list is not evidence of review" if total == 0 else
                f"{len(checked)} of {total} items checked; unchecked items are listed explicitly"}


# --- editable artifacts (LS-021 artifact part) -------------------------------------------------------
class ArtifactService:
    """Deviation/CAPA/report drafts built from claims and fields; always editable and pending human review."""

    def __init__(self, store: RecordStore, identity: IdentityService, evidence: EvidenceService) -> None:
        self.store = store
        self.identity = identity
        self.evidence = evidence

    def generate(self, ctx: AccessContext, case_id: str, artifact_kind: str) -> dict[str, Any]:
        if artifact_kind not in ARTIFACT_KINDS:
            raise ValueError(f"artifact_kind must be one of {ARTIFACT_KINDS}")
        tx = self.store.read()
        case = tx.require(ctx.tenant_id, "case", case_id)
        self.identity.require(ctx, "propose", "draft_artifact", site_id=case.state["site_id"], tx=tx)
        claims = tx.list(ctx.tenant_id, "claim", lambda s: s["case_id"] == case_id)
        fields = tx.list(ctx.tenant_id, "form_field", lambda s: s["case_id"] == case_id)
        live = [c for c in claims if c.state["status"] == STATUS_CURRENT]
        excluded = [c.id for c in claims if c.state["status"] != STATUS_CURRENT]

        def entries(*classes: str) -> list[dict[str, Any]]:
            return [{"text": c.state["text"], "label": c.state["label"], "claim_id": c.id,
                     "evidence_ids": [r["id"] for r in c.state["evidence_refs"]], "flags": c.state["flags"]}
                    for c in live if c.state["claim_class"] in classes]

        unresolved = [{"text": f"[UNRESOLVED] {f.state['name']}", "field_id": f.id, "reason": f.state["unresolved_reason"] or f.state["field_status"]}
                      for f in fields if f.state["field_status"] in ("unresolved", "returned")]
        unresolved += [{"text": f"[UNKNOWN] {u}", "claim_id": c.id} for c in live for u in c.state["unknowns"]]
        field_rows = [{"text": f"{f.state['name']}: {f.state['value']}", "field_id": f.id, "field_status": f.state["field_status"]}
                      for f in fields if f.state["field_status"] in ("cited", "human_asserted")]
        sections = {
            "deviation": {"description": entries("observation"), "form_fields": field_rows, "investigation": entries("calculation", "hypothesis"),
                          "unresolved": unresolved, "proposed_actions": entries("recommendation")},
            "capa": {"problem_basis": entries("observation", "calculation"), "candidate_causes": entries("hypothesis"),
                     "proposed_actions": entries("recommendation"), "unresolved": unresolved},
            "report": {"observations": entries("observation"), "calculations": entries("calculation"), "hypotheses": entries("hypothesis"),
                       "recommendations": entries("recommendation"), "form_fields": field_rows, "unresolved": unresolved},
        }[artifact_kind]
        evidence_ids = sorted({i["id"] for r in [*live, *fields] for i in r.state["inputs"] if i["kind"] == "evidence"})
        inputs = [EvidenceRef("claim", c.id, c.revision, c.state["site_id"]) for c in live] + \
                 [EvidenceRef("form_field", f.id, f.revision, f.state["site_id"]) for f in fields]
        payload = {"case_id": case_id, "site_id": case.state["site_id"], "artifact_kind": artifact_kind, "sections": sections,
                   "sources": {"claims": [c.id for c in live], "fields": [f.id for f in fields], "evidence": evidence_ids},
                   "excluded_stale_claims": excluded, "review_state": "draft_requires_review",
                   "review_history": [{"event": "generated", "by": ctx.actor_id, "at": iso(utc_now())}]}
        return self.evidence.record_derived(ctx, "draft_artifact", payload,
                                            inputs=inputs or [EvidenceRef("case", case_id, case.revision, case.state["site_id"])],
                                            produced_by={"actor_id": ctx.actor_id, "actor_kind": ctx.actor_kind,
                                                         "method": f"artifact_service.generate:{artifact_kind}"})

    def edit_section(self, ctx: AccessContext, artifact_id: str, section: str, content: Any, expected_revision: int,
                     reason: str | None = None) -> dict[str, Any]:
        _require_person(ctx, "editing a draft artifact")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "draft_artifact", artifact_id)
            self.identity.require(ctx, "propose", "draft_artifact", artifact_id, site_id=rec.state["site_id"], tx=tx)
            if rec.revision != expected_revision:
                raise ConflictError(f"draft_artifact:{artifact_id} is at revision {rec.revision}; edit targeted {expected_revision}")
            s = rec.state
            state = {**s, "sections": {**s["sections"], section: content}, "review_state": "draft_requires_review",
                     "review_history": [*s["review_history"], {"event": "edited", "section": section, "by": ctx.actor_id,
                                                                "at": iso(utc_now()), "reason": reason}]}
            out = tx.put(ctx.tenant_id, "draft_artifact", artifact_id, state, expected_revision=rec.revision,
                         action="edit_artifact", reason=reason)
        return {"id": artifact_id, "revision": out.revision, **out.state}

    def propose_submission(self, ctx: AccessContext, artifact_id: str, actions: ActionService, owner_id: str) -> dict[str, Any]:
        """Submission is only ever a proposal through ActionService; this module never submits."""
        art = self.evidence.read_derived(ctx, "draft_artifact", artifact_id)
        if art["status"] != STATUS_CURRENT:
            raise ValueError("artifact is stale; regenerate it from current claims before proposing submission")
        op = {"deviation": "submit_deviation", "capa": "approve_capa", "report": "submit_report"}[art["artifact_kind"]]
        return actions.propose(
            ctx, target_system="QMS", operation=op, target_id=art["case_id"], payload={"artifact_id": artifact_id},
            basis=[{"kind": "draft_artifact", "id": artifact_id, "revision": art["revision"], "site_id": art["site_id"]}],
            rationale=f"{art['artifact_kind']} draft prepared from {len(art['sources']['claims'])} claims for review",
            expected_result="record created in the quality system after human approval", owner_id=owner_id, site_id=art["site_id"])
