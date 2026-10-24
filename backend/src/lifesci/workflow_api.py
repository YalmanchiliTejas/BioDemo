"""Complete workflow commands over existing domain boundaries."""
from datetime import datetime
from typing import Any, Literal
from fastapi import Depends, Header
from pydantic import Field
from .suite_api import Command


class AdaptIn(Command):
    revision: int = Field(ge=1)
    site_id: str
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AmendmentIn(Command):
    change: dict[str, Any]
    reason: str = Field(min_length=1)


class ReasonIn(Command):
    reason: str = Field(min_length=1)


class InstrumentIn(Command):
    site_id: str
    instrument_class: str
    status: Literal["ready", "maintenance", "unavailable"]
    calibration_due: str


class AliquotIn(Command):
    n: int = Field(ge=1, le=384)
    volume: float = Field(gt=0)
    unit: str = "mL"


class CalculatedResultIn(Command):
    sample_id: str
    calculation: str
    analyte: str | None = None


class TransferDecisionIn(Command):
    role: Literal["sender", "recipient"]
    expected_revision: int = Field(ge=1)
    inventory: dict[str, Any] = Field(default_factory=dict)


class TransferRevisionIn(Command):
    expected_revision: int = Field(ge=1)
    changes: dict[str, Any]


class PartnerGrantIn(Command):
    partner_org_id: str = Field(min_length=1)
    mode: Literal["view", "interactive"] = "view"
    expires_at: datetime


class MembershipIn(Command):
    partner_org_id: str
    active: bool = True


class PartnerReviewIn(Command):
    decision: Literal["approve", "reject", "comment"]
    comment: str = Field(min_length=1)


class AnnotationIn(Command):
    tool: Literal["chat", "drawing", "pointer"]
    content: dict[str, Any]


class ResourceIn(Command):
    kind: Literal["material_lot", "equipment", "personnel_qualification", "spare_part"]
    record_id: str
    site_id: str
    state: dict[str, Any]


class DispositionIn(Command):
    disposition: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def install_workflow_api(p, app, ctx_dep, command, guard):
    @app.post("/v1/intelligence/runs/{rid}/queue", status_code=202)
    def queue_flow(rid: str, ctx=Depends(ctx_dep)):
        from .ids import new_id
        rec = guard(ctx, "data_flow_run", rid)
        if rec.state["status"] in ("stale", "quarantined"):
            raise ValueError("invalidated flow requires a new run")
        p.identity.require(ctx, "propose", "data_flow", rec.state["flow_id"], site_id=rec.state["site_id"])
        p.identity.validate_refs(ctx, rec.state["inputs"])
        with p.store.transaction(ctx.actor_id) as tx:
            current = tx.require(ctx.tenant_id, "data_flow_run", rid)
            if current.state.get("queued"):
                return {"run_id": rid, "queued": True}
            tx.put(ctx.tenant_id, "data_flow_run", rid,
                   {**current.state, "queued": True, "queued_by": ctx.actor_id, "queue_request_id": new_id("queue")},
                   expected_revision=current.revision, action="queue_flow")
        return {"run_id": rid, "queued": True}

    @app.post("/v1/manufacturing/resources")
    def resource(body: ResourceIn, ctx=Depends(ctx_dep)):
        return command(ctx, None, "native-resource", body, lambda: p.execution.create_native(ctx, body.kind, body.record_id, body.state, site_id=body.site_id))

    @app.post("/v1/manufacturing/exceptions/{eid}/disposition")
    def disposition(eid: str, body: DispositionIn, ctx=Depends(ctx_dep)):
        guard(ctx, "exec_exception", eid)
        return command(ctx, None, f"disposition:{eid}", body, lambda: p.execution.resolve_exception(ctx, eid, body.disposition, body.reason))
    @app.get("/v1/procedures/{pid}/validation")
    def validation(pid: str, ctx=Depends(ctx_dep)):
        rec = guard(ctx, "procedure", pid)
        return {"errors": p.procedures.validate(rec.state["draft"], rec.state["category"]), "revision": rec.revision}

    @app.post("/v1/procedures/{pid}/adapt")
    def adapt(pid: str, body: AdaptIn, ctx=Depends(ctx_dep)):
        guard(ctx, "procedure", pid)
        return command(ctx, None, f"adapt:{pid}", body, lambda: p.procedures.adapt_for_site(ctx, pid, body.revision, body.site_id, body.overrides))

    @app.post("/v1/manufacturing/instances/{iid}/amendments")
    def amendment(iid: str, body: AmendmentIn, ctx=Depends(ctx_dep)):
        guard(ctx, "procedure_instance", iid, "propose")
        return command(ctx, None, f"amend:{iid}", body, lambda: p.procedures.amend_instance(ctx, iid, body.change, body.reason))

    @app.post("/v1/manufacturing/amendments/{aid}/apply")
    def apply_amendment(aid: str, ctx=Depends(ctx_dep)):
        rec = p.store.read().require(ctx.tenant_id, "amendment_request", aid)
        guard(ctx, "procedure_instance", rec.state["instance_id"], "propose")
        with p.store.transaction(ctx.actor_id):
            return p.procedures.apply_amendment(ctx, aid)

    @app.post("/v1/manufacturing/instances/{iid}/steps/{sid}/not-applicable")
    def not_applicable(iid: str, sid: str, body: ReasonIn, ctx=Depends(ctx_dep)):
        guard(ctx, "procedure_instance", iid)
        return command(ctx, None, f"na:{iid}:{sid}", body, lambda: p.procedures.mark_not_applicable(ctx, iid, sid, body.reason))

    @app.post("/v1/laboratory/instruments/{iid}")
    def instrument(iid: str, body: InstrumentIn, ctx=Depends(ctx_dep)):
        p.identity.require(ctx, "configure", "instrument", iid, site_id=body.site_id)
        old = p.store.read().get(ctx.tenant_id, "instrument", iid)
        if old and old.state["site_id"] != body.site_id:
            raise ValueError("instrument site cannot be changed")
        datetime.fromisoformat(body.calibration_due)
        return command(ctx, None, f"instrument:{iid}", body, lambda: p.lab.register_instrument(ctx, iid, body.model_dump(exclude={"site_id"}), site_id=body.site_id))

    @app.post("/v1/laboratory/samples/{sid}/aliquots")
    def aliquot(sid: str, body: AliquotIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "sample", sid)
        return command(ctx, key, f"aliquot:{sid}", body, lambda: p.lab.aliquot(ctx, sid, **body.model_dump()))

    @app.post("/v1/laboratory/runs/{rid}/results")
    def calculated_result(rid: str, body: CalculatedResultIn, ctx=Depends(ctx_dep)):
        guard(ctx, "procedure_instance", rid)
        guard(ctx, "sample", body.sample_id)
        return command(ctx, None, f"run-result:{rid}", body, lambda: p.lab.record_run_result(ctx, rid, **body.model_dump()))

    @app.post("/v1/laboratory/results/{rid}/request-invalidation")
    def invalidate_result(rid: str, body: ReasonIn, ctx=Depends(ctx_dep)):
        guard(ctx, "result", rid)
        return command(ctx, None, f"invalidate:{rid}", body, lambda: p.lab.request_invalidation(ctx, rid, body.reason))

    @app.post("/v1/laboratory/results/{rid}/invalidate/{proposal_id}")
    def apply_invalidation(rid: str, proposal_id: str, ctx=Depends(ctx_dep)):
        guard(ctx, "result", rid)
        with p.store.transaction(ctx.actor_id):
            return p.lab.apply_invalidation(ctx, rid, proposal_id)

    @app.get("/v1/network/transfers")
    def transfers(ctx=Depends(ctx_dep)):
        return {"items": [{**r.state, "revision": r.revision} for r in p.store.read().list(ctx.tenant_id, "transfer_package")
            if any(p.identity.check(ctx, "read", "transfer_package", r.id, site_id=r.state[k]) for k in ("sending_site", "receiving_site"))]}

    @app.post("/v1/network/transfers/{pid}/revisions")
    def revise_transfer(pid: str, body: TransferRevisionIn, ctx=Depends(ctx_dep)):
        return command(ctx, None, f"transfer-revision:{pid}", body, lambda: p.transfers.revise(ctx, pid, body.expected_revision, **body.changes))

    @app.post("/v1/network/transfers/{pid}/receive")
    def receive_transfer(pid: str, ctx=Depends(ctx_dep)):
        return p.transfers.acknowledge_receipt(ctx, pid)

    @app.post("/v1/network/transfers/{pid}/approve")
    def approve_transfer(pid: str, body: TransferDecisionIn, ctx=Depends(ctx_dep)):
        from .store import ConflictError
        with p.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "transfer_package", pid)
            if rec.revision != body.expected_revision:
                raise ConflictError("transfer changed; review current content")
            return p.transfers.approve(ctx, pid, body.role, body.inventory)

    @app.post("/v1/partners/members/{actor_id}")
    def member(actor_id: str, body: MembershipIn, ctx=Depends(ctx_dep)):
        p.identity.require(ctx, "configure", "partner_membership")
        if ctx.site_ids or ctx.actor_kind != "person":
            raise PermissionError("partner membership requires tenant-wide configuration authority")
        if p.identity.context_for(ctx.tenant_id, actor_id).roles:
            raise ValueError("use a distinct partner identity without internal roles")
        with p.store.transaction(ctx.actor_id) as tx:
            old = tx.get(ctx.tenant_id, "partner_membership", actor_id)
            out = tx.put(ctx.tenant_id, "partner_membership", actor_id, body.model_dump(),
                         expected_revision=old.revision if old else None, action="configure_partner_membership")
        return {"actor_id": actor_id, **out.state}

    @app.post("/v1/partners/batches/{bid}/grants")
    def grant_partner(bid: str, body: PartnerGrantIn, ctx=Depends(ctx_dep)):
        from .ids import utc_now
        if body.expires_at.tzinfo is None or body.expires_at <= utc_now():
            raise ValueError("partner access requires a future timezone-aware expiry")
        with p.store.transaction(ctx.actor_id):
            return p.partners.grant_partner(ctx, body.partner_org_id, bid, body.mode, body.expires_at)

    @app.post("/v1/partners/grants/{gid}/revoke")
    def revoke(gid: str, body: ReasonIn, ctx=Depends(ctx_dep)):
        with p.store.transaction(ctx.actor_id):
            return p.partners.revoke_partner(ctx, gid, body.reason)

    @app.get("/v1/partners/batches/{bid}")
    def partner_view(bid: str, ctx=Depends(ctx_dep)):
        return p.partners.partner_batch_view(ctx, bid)

    @app.post("/v1/partners/batches/{bid}/reviews")
    def partner_review(bid: str, body: PartnerReviewIn, ctx=Depends(ctx_dep)):
        return p.partners.partner_review(ctx, bid, body.decision, body.comment)

    @app.get("/v1/collaboration/cases/{cid}/sessions")
    def sessions(cid: str, ctx=Depends(ctx_dep)):
        p.cases.get(ctx, cid)
        return {"items": p.remote_sessions.sessions_for_case(ctx, cid)}

    @app.post("/v1/collaboration/sessions/{sid}/reconcile")
    def reconcile_session(sid: str, ctx=Depends(ctx_dep)):
        return p.remote_sessions.reconcile_creation(ctx, sid)

    @app.get("/v1/collaboration/sessions/{sid}/annotations")
    def annotations(sid: str, ctx=Depends(ctx_dep)):
        return {"items": p.remote_sessions.annotations(ctx, sid)}

    @app.post("/v1/collaboration/sessions/{sid}/annotations")
    def annotate(sid: str, body: AnnotationIn, ctx=Depends(ctx_dep)):
        return p.remote_sessions.annotate(ctx, sid, body.tool, body.content)
