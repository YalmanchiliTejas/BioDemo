"""Explicit suite commands over shared domain services; no dynamic method dispatch.

Native ownership and qualification remain domain prerequisites. These endpoints
do not turn draft creation, publication requests or empty exception lists into
authorization to manufacture or release a batch.
"""
from typing import Any, Literal

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .identity import AccessContext
from .network import TransferPackage


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DefinitionIn(Command):
    definition: dict[str, Any]
    params: dict[str, Any] = Field(default_factory=dict)


class DraftIn(Command):
    procedure_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=256)
    category: Literal["recipe", "work_instruction", "lab_method"]
    definition: dict[str, Any]
    site_id: str | None = Field(default=None, min_length=1)


class DraftUpdateIn(Command):
    definition: dict[str, Any]
    expected_revision: int = Field(ge=1)


class RationaleIn(Command):
    rationale: str = Field(min_length=1)


class PublishIn(Command):
    approved_proposal_id: str = Field(min_length=1)


class BatchIn(Command):
    batch_id: str = Field(min_length=1, max_length=128)
    product: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    order_id: str | None = None


class InstanceIn(Command):
    procedure_id: str
    batch_id: str
    site_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    revision: int | None = Field(default=None, ge=1)


class StepIn(Command):
    values: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    device_type: Literal["web", "mobile", "headset"] = "web"


class SignatureIn(Command):
    meaning: str
    authentication: dict[str, Any]


class SampleIn(Command):
    batch_id: str
    step_id: str | None = None
    sample_type: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8, max_length=128)
    volume: float | None = Field(default=None, gt=0)
    unit: str = "mL"


class CustodyIn(Command):
    from_actor: str
    to_actor: str
    reason: str = Field(min_length=1)


class ResultIn(Command):
    analyte: str = Field(min_length=1)
    value: float
    unit: str
    method_ref: dict[str, Any] | None = None
    instrument_id: str | None = None
    limits: dict[str, float] | None = None


class LabRunIn(Command):
    method_id: str
    site_id: str
    instruments: list[str] = Field(default_factory=list)
    reagents: list[str] = Field(default_factory=list)
    sample_ids: list[str] = Field(default_factory=list)
    revision: int | None = Field(default=None, ge=1)
    params: dict[str, Any] = Field(default_factory=dict)


class CaseIn(Command):
    case_id: str
    owner_id: str
    qa_reviewer_id: str
    site_id: str


class TransferIn(Command):
    sending_site: str
    receiving_site: str
    product_id: str
    procedure_refs: list[dict[str, Any]] = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    material_mapping: dict[str, str | None] = Field(default_factory=dict)
    equipment_mapping: dict[str, str | None] = Field(default_factory=dict)
    required_qualifications: list[dict[str, str]] = Field(default_factory=list)
    open_gaps: list[dict[str, Any]] = Field(default_factory=list)


class FlowNodeIn(Command):
    node_id: str = Field(min_length=1, max_length=80)
    task_kind: str
    depends_on: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    prompt: str = Field(default="", max_length=20000)


class FlowIn(Command):
    site_id: str = Field(min_length=1)
    nodes: list[FlowNodeIn] = Field(min_length=1, max_length=50)
    expected_revision: int | None = Field(default=None, ge=1)


class FlowRunIn(Command):
    inputs: list[dict[str, Any]] = Field(default_factory=list)


class PlateIn(Command):
    plate_id: str
    plate_format: Literal[96, 384]
    positions: dict[str, str] = Field(min_length=1)


class ResultReviewIn(Command):
    decision: Literal["approved", "rejected"]
    comment: str = ""


class ArtifactIn(Command):
    artifact_kind: Literal["deviation", "capa", "report"]


class RequirementIn(Command):
    text: str = Field(min_length=1)
    risk: str
    tests: list[str] = Field(min_length=1)
    intended_use: str = Field(min_length=1)


class TestRunIn(Command):
    junit_xml: str = Field(min_length=1, max_length=1000000)
    build: str = Field(min_length=1)
    environment: dict[str, Any]


class RemoteSessionIn(Command):
    case_id: str
    participants: list[str]
    media_provider: str


class ConsentIn(Command):
    granted: bool


def install_suite_api(p: Any, app: Any, ctx_dep: Any, idempotent: Any) -> None:
    def guard(ctx: AccessContext, kind: str, rid: str, action: str = "read") -> Any:
        rec = p.store.read().require(ctx.tenant_id, kind, rid)
        p.identity.require(ctx, action, kind, rid, site_id=rec.state.get("site_id"))
        return rec

    def command(ctx: AccessContext, key: str | None, route: str, body: BaseModel, run: Any) -> Any:
        # Domain commands and their replay receipt commit together. Idempotency
        # cannot replay after a failure left only half of a multi-record change.
        with p.store.transaction(ctx.actor_id):
            return idempotent(ctx, key, route, body.model_dump(), run)

    @app.post("/v1/procedures/preview")
    def preview(body: DefinitionIn, ctx: AccessContext = Depends(ctx_dep)):
        p.identity.require(ctx, "propose", "procedure")
        return {"steps": p.procedures.preview(body.definition, body.params), "writes": False}

    @app.post("/v1/procedures", status_code=201)
    def draft(body: DraftIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        if body.site_id is None and ctx.site_ids:
            raise PermissionError("global templates require tenant-wide authoring authority")
        p.identity.require(ctx, "propose", "procedure", body.procedure_id, site_id=body.site_id)
        return command(ctx, key, "suite:procedure", body, lambda: p.procedures.create_draft(ctx, **body.model_dump()))

    @app.post("/v1/procedures/{pid}/draft")
    def update(pid: str, body: DraftUpdateIn, ctx: AccessContext = Depends(ctx_dep)):
        guard(ctx, "procedure", pid, "propose")
        return command(ctx, None, f"draft:{pid}", body, lambda: p.procedures.update_draft(ctx, pid, **body.model_dump()))

    @app.post("/v1/procedures/{pid}/submit")
    def submit(pid: str, body: RationaleIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "procedure", pid, "propose")
        return command(ctx, key, f"submit:{pid}", body, lambda: p.procedures.submit_for_publication(ctx, pid, rationale=body.rationale))

    @app.post("/v1/procedures/{pid}/publish")
    def publish(pid: str, body: PublishIn, ctx: AccessContext = Depends(ctx_dep)):
        guard(ctx, "procedure", pid, "propose")
        return command(ctx, None, f"publish:{pid}", body, lambda: p.procedures.publish(ctx, pid, body.approved_proposal_id))

    @app.get("/v1/procedures/{pid}/effective")
    def effective(pid: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.procedures.get_revision(ctx, pid)

    @app.post("/v1/manufacturing/batches", status_code=201)
    def batch(body: BatchIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        p.identity.require(ctx, "configure", "batch", body.batch_id, site_id=body.site_id)
        return command(ctx, key, "suite:batch", body, lambda: p.execution.create_batch(ctx, **body.model_dump()))

    @app.post("/v1/manufacturing/instances", status_code=201)
    def instance(body: InstanceIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "batch", body.batch_id)
        return command(ctx, key, "suite:instance", body, lambda: p.execution.create_instance(ctx, **body.model_dump()))

    @app.get("/v1/manufacturing/instances/{iid}")
    def get_instance(iid: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.procedures.get_instance(ctx, iid)

    @app.post("/v1/manufacturing/instances/{iid}/start")
    def start(iid: str, ctx: AccessContext = Depends(ctx_dep)):
        guard(ctx, "procedure_instance", iid)
        with p.store.transaction(ctx.actor_id):
            return p.execution.start(ctx, iid)

    @app.post("/v1/manufacturing/instances/{iid}/steps/{sid}")
    def step(iid: str, sid: str, body: StepIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "procedure_instance", iid)
        return command(ctx, key, f"step:{iid}:{sid}", body, lambda: p.execution.perform_step(ctx, iid, sid, body.values, body.resources, device_type=body.device_type))

    @app.post("/v1/manufacturing/instances/{iid}/steps/{sid}/sign")
    def sign(iid: str, sid: str, body: SignatureIn, ctx: AccessContext = Depends(ctx_dep)):
        guard(ctx, "procedure_instance", iid)
        # Reauthentication assertions must never be stored in replay receipts.
        with p.store.transaction(ctx.actor_id):
            return p.execution.sign_step(ctx, iid, sid, body.meaning, body.authentication)

    @app.get("/v1/manufacturing/instances/{iid}/batch-record")
    def batch_record(iid: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.execution.batch_record(ctx, iid)

    @app.get("/v1/manufacturing/instances/{iid}/exceptions")
    def exceptions(iid: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.execution.review_by_exception(ctx, iid)

    @app.post("/v1/manufacturing/instances/{iid}/request-release")
    def release(iid: str, body: RationaleIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "procedure_instance", iid)
        return command(ctx, key, f"release:{iid}", body, lambda: p.execution.request_release(ctx, iid, rationale=body.rationale))

    @app.post("/v1/laboratory/samples", status_code=201)
    def sample(body: SampleIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "batch", body.batch_id)
        # Scope the domain sample key by caller as well as tenant.
        data = body.model_dump()
        from .ids import content_hash
        data["idempotency_key"] = content_hash([ctx.actor_id, body.idempotency_key])
        return command(ctx, key, "suite:sample", body, lambda: p.lab.register_sample(ctx, **data))

    @app.get("/v1/laboratory/samples/{sample_id}/custody")
    def custody(sample_id: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.lab.custody_chain(ctx, sample_id)

    @app.post("/v1/laboratory/samples/{sample_id}/custody")
    def transfer_custody(sample_id: str, body: CustodyIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "sample", sample_id)
        return command(ctx, key, f"custody:{sample_id}", body, lambda: p.lab.transfer_custody(ctx, sample_id, body.from_actor, body.to_actor, body.reason))

    @app.post("/v1/laboratory/samples/{sample_id}/results", status_code=201)
    def result(sample_id: str, body: ResultIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "sample", sample_id)
        return command(ctx, key, f"result:{sample_id}", body, lambda: p.lab.record_result(ctx, sample_id, **body.model_dump()))

    @app.post("/v1/laboratory/runs", status_code=201)
    def lab_run(body: LabRunIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        p.identity.require(ctx, "execute", "step_execution", site_id=body.site_id)
        for sample_id in body.sample_ids:
            sample = guard(ctx, "sample", sample_id)
            if sample.state["site_id"] != body.site_id:
                raise ValueError("sample belongs to a different site")
        return command(ctx, key, "suite:lab-run", body, lambda: p.lab.start_run(ctx, **body.model_dump()))

    @app.post("/v1/laboratory/runs/{iid}/steps/{sid}")
    def lab_step(iid: str, sid: str, body: StepIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "procedure_instance", iid)
        return command(ctx, key, f"lab-step:{iid}:{sid}", body, lambda: p.lab.perform_method_step(ctx, iid, sid, body.values))

    @app.post("/v1/quality/cases", status_code=201)
    def case(body: CaseIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        p.identity.require(ctx, "propose", "case", body.case_id, site_id=body.site_id)
        return command(ctx, key, "suite:case", body, lambda: p.cases.open(ctx, **body.model_dump()))

    @app.post("/v1/quality/cases/{cid}/review-package", status_code=201)
    def package(cid: str, ctx: AccessContext = Depends(ctx_dep)):
        p.cases.get(ctx, cid)
        with p.store.transaction(ctx.actor_id):
            return p.packages.build_package(ctx, cid)

    @app.get("/v1/network/sites")
    def sites(ctx: AccessContext = Depends(ctx_dep)):
        return p.network.site_view(ctx, ("batch", "procedure_instance", "sample", "case"))

    @app.post("/v1/network/transfers", status_code=201)
    def transfer(body: TransferIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        p.identity.require(ctx, "propose", "transfer_package", site_id=body.sending_site)
        p.identity.validate_refs(ctx, body.procedure_refs, require_current=True)
        return command(ctx, key, "suite:transfer", body, lambda: p.transfers.create(ctx, TransferPackage(**body.model_dump())))

    @app.post("/v1/network/transfers/{pid}/readiness")
    def transfer_readiness(pid: str, inventory: dict[str, Any], ctx: AccessContext = Depends(ctx_dep)):
        return p.transfers.recipient_checklist(ctx, pid, inventory)

    @app.post("/v1/intelligence/flows/{fid}")
    def save_flow(fid: str, body: FlowIn, ctx: AccessContext = Depends(ctx_dep)):
        return p.flows.save(ctx, fid, **body.model_dump())

    @app.post("/v1/intelligence/flows/{fid}/runs", status_code=201)
    def flow_run(fid: str, body: FlowRunIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        guard(ctx, "data_flow", fid, "propose")
        if body.inputs:
            p.identity.validate_refs(ctx, body.inputs, require_current=True)
        return command(ctx, key, f"flow-run:{fid}", body, lambda: p.flows.create_run(ctx, fid, inputs=body.inputs))

    @app.post("/v1/intelligence/runs/{rid}/resume")
    def resume_flow(rid: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.flows.run(ctx, rid)

    @app.post("/v1/laboratory/plates", status_code=201)
    def plate(body: PlateIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        if p.store.read().get(ctx.tenant_id, "plate", body.plate_id):
            guard(ctx, "plate", body.plate_id)
        for sid in body.positions.values():
            guard(ctx, "sample", sid)
        return command(ctx, key, "suite:plate", body, lambda: p.lab.assign_plate(ctx, **body.model_dump()))

    @app.post("/v1/laboratory/results/{rid}/review")
    def review_result(rid: str, body: ResultReviewIn, ctx: AccessContext = Depends(ctx_dep)):
        guard(ctx, "result", rid, "approve")
        with p.store.transaction(ctx.actor_id):
            return p.lab.review_result(ctx, rid, body.decision, body.comment)

    @app.post("/v1/laboratory/results/{rid}/release")
    def release_result(rid: str, ctx: AccessContext = Depends(ctx_dep)):
        guard(ctx, "result", rid, "release")
        with p.store.transaction(ctx.actor_id):
            return p.lab.release_result(ctx, rid)

    @app.post("/v1/quality/cases/{cid}/artifacts", status_code=201)
    def artifact(cid: str, body: ArtifactIn, ctx: AccessContext = Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        p.cases.get(ctx, cid)
        return command(ctx, key, f"artifact:{cid}", body, lambda: p.artifacts.generate(ctx, cid, body.artifact_kind))

    @app.post("/v1/assurance/requirements/{rid}")
    def requirement(rid: str, body: RequirementIn, ctx: AccessContext = Depends(ctx_dep)):
        p.identity.require(ctx, "configure", "requirement", rid)
        if ctx.site_ids:
            raise PermissionError("tenant-wide qualification requirements require tenant-wide authority")
        with p.store.transaction(ctx.actor_id):
            p.assurance.define_requirement(ctx, rid, **body.model_dump())
        return {"requirement_id": rid}

    @app.post("/v1/assurance/test-runs", status_code=201)
    def test_run(body: TestRunIn, ctx: AccessContext = Depends(ctx_dep)):
        p.identity.require(ctx, "configure", "requirement")
        if ctx.site_ids:
            raise PermissionError("tenant-wide qualification evidence requires tenant-wide authority")
        from xml.etree.ElementTree import ParseError
        try:
            with p.store.transaction(ctx.actor_id):
                rid = p.assurance.record_test_run(ctx, **body.model_dump())
        except ParseError as exc:
            raise ValueError("invalid JUnit XML") from exc
        return {"run_id": rid, "evidence_type": "user_submitted_test_report", "independently_verified": False}

    @app.get("/v1/assurance/test-runs/{rid}/trace")
    def qualification_trace(rid: str, ctx: AccessContext = Depends(ctx_dep)):
        p.identity.require(ctx, "configure", "requirement")
        if ctx.site_ids:
            raise PermissionError("tenant-wide qualification evidence requires tenant-wide authority")
        return p.assurance.qualification_trace(ctx.tenant_id, rid)

    @app.get("/v1/collaboration/providers")
    def providers(ctx: AccessContext = Depends(ctx_dep)):
        p.identity.require(ctx, "read", "case")
        return {"configured": sorted(p.media_providers), "available": bool(p.media_providers)}

    @app.post("/v1/collaboration/sessions", status_code=201)
    def remote_session(body: RemoteSessionIn, ctx: AccessContext = Depends(ctx_dep)):
        case = p.cases.get(ctx, body.case_id)
        if body.media_provider not in p.media_providers:
            raise HTTPException(503, "Requested media provider is not configured")
        # Provider I/O stays outside the database transaction. Session lifecycle
        # and provider reconciliation are separate from manufacturing actions.
        return p.remote_sessions.create(ctx, body.case_id, body.participants, body.media_provider, site_id=case["site_id"])

    @app.post("/v1/collaboration/sessions/{sid}/consent")
    def consent(sid: str, body: ConsentIn, ctx: AccessContext = Depends(ctx_dep)):
        session = p.store.read().require(ctx.tenant_id, "remote_session", sid)
        p.cases.get(ctx, session.state["case_id"])
        return p.remote_sessions.record_consent(ctx, sid, body.granted)

    @app.post("/v1/collaboration/sessions/{sid}/join")
    def join(sid: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.remote_sessions.join(ctx, sid)

    @app.post("/v1/collaboration/sessions/{sid}/end")
    def end(sid: str, ctx: AccessContext = Depends(ctx_dep)):
        return p.remote_sessions.end(ctx, sid)

    from .workflow_api import install_workflow_api
    install_workflow_api(p, app, ctx_dep, command, guard)
