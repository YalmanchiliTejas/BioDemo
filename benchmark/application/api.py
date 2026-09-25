from pathlib import Path
import os
from typing import Any

from .bootstrap import ApplicationServices, build_services_from_env
from .models import ActionProposal, ApprovalDecision


def create_app(services: ApplicationServices | None = None):
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Query
        from fastapi.encoders import jsonable_encoder
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field
    except ImportError as exc:  # pragma: no cover - optional runtime
        raise RuntimeError("Install the 'app' extra to run the API and UI") from exc

    from benchmark.knowledge.domain import AccessContext, CaseRecord, CaseStatus, EntityRef, HumanTask

    runtime = services or build_services_from_env()
    app = FastAPI(title="CDMO Operations Intelligence", version="0.2.0")

    class CaseInput(BaseModel):
        case_id: str
        case_type: str
        title: str
        owner_id: str
        site_id: str | None = None
        entity_ids: list[str] = Field(default_factory=list)

    class TaskInput(BaseModel):
        task_id: str
        case_id: str
        task_type: str
        title: str
        assigned_role: str
        assigned_to: str | None = None

    class ProposalInput(BaseModel):
        proposal_id: str
        case_id: str
        operation: str
        target_id: str
        reason: str
        payload: dict[str, Any] = Field(default_factory=dict)
        site_id: str | None = None

    class DecisionInput(BaseModel):
        approval_id: str
        decision: str
        meaning: str
        role: str
        comment: str = ""

    def identity(
        x_tenant_id: str = Header("demo-cdmo"),
        x_actor_id: str = Header("qa-14"),
        x_roles: str = Header("qa,sponsor_qa,supervisor,operator"),
        x_site_ids: str = Header("PHX-01"),
        x_clearances: str = Header("internal,confidential"),
    ) -> AccessContext:
        # These headers are a development identity adapter. Production must replace
        # it with verified OIDC/JWT claims at the trusted API boundary.
        split = lambda value: tuple(item.strip() for item in value.split(",") if item.strip())
        return AccessContext(x_tenant_id, x_actor_id, split(x_site_ids), split(x_roles), split(x_clearances))

    def safe(call):
        try:
            return call()
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "extensions": runtime.extensions.status()}

    @app.get("/api/dashboard")
    def dashboard(access: AccessContext = Depends(identity)) -> dict[str, Any]:
        cases = runtime.thread.cases.list_cases(access.tenant_id)
        tasks = runtime.thread.cases.list_tasks(access.tenant_id)
        proposals = runtime.action_store.list(access.tenant_id)
        batches = _batch_cards(cases)
        return jsonable_encoder({
            "tenant_id": access.tenant_id,
            "stats": {
                "open_cases": sum(case.status != CaseStatus.CLOSED for case in cases),
                "pending_tasks": sum(task.status == "open" for task in tasks),
                "pending_approvals": sum(proposal.status == "pending_approval" for proposal in proposals),
                "batches_in_view": len(batches),
            },
            "batches": batches,
            "quality_trend": [94, 96, 95, 97, 96, 98, 97, 99, 98, 98, 99, 98],
            "extensions": runtime.extensions.status(),
            "demo_data": services is None and os.getenv("APP_MODE", "demo").lower() != "production",
        })

    @app.get("/api/cases")
    def list_cases(access: AccessContext = Depends(identity)):
        return jsonable_encoder(runtime.thread.cases.list_cases(access.tenant_id))

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str, access: AccessContext = Depends(identity)):
        case = runtime.thread.cases.get_case(case_id, access.tenant_id)
        if case is None:
            raise HTTPException(404, "case not found")
        return jsonable_encoder({
            "case": case,
            "tasks": runtime.thread.cases.tasks_for_case(case_id, access.tenant_id),
            "actions": [item for item in runtime.action_store.list(access.tenant_id) if item.case_id == case_id],
        })

    @app.post("/api/cases", status_code=201)
    def create_case(value: CaseInput, access: AccessContext = Depends(identity)):
        case = CaseRecord(
            value.case_id, access.tenant_id, value.case_type, value.title, value.owner_id,
            value.site_id, entity_refs=tuple(EntityRef(item, "entity") for item in value.entity_ids),
        )
        safe(lambda: runtime.thread.open_case(case, access=access))
        return jsonable_encoder(case)

    @app.get("/api/tasks")
    def list_tasks(access: AccessContext = Depends(identity)):
        return jsonable_encoder(runtime.thread.cases.list_tasks(access.tenant_id))

    @app.post("/api/tasks", status_code=201)
    def create_task(value: TaskInput, access: AccessContext = Depends(identity)):
        task = HumanTask(
            value.task_id, value.case_id, access.tenant_id, value.task_type,
            value.title, value.assigned_role, assigned_to=value.assigned_to,
        )
        safe(lambda: runtime.thread.assign_task(task, access=access))
        return jsonable_encoder(task)

    @app.get("/api/actions")
    def list_actions(access: AccessContext = Depends(identity)):
        return jsonable_encoder(runtime.action_store.list(access.tenant_id))

    @app.post("/api/actions", status_code=201)
    def propose_action(value: ProposalInput, access: AccessContext = Depends(identity)):
        proposal = ActionProposal(
            value.proposal_id, access.tenant_id, value.case_id, value.operation,
            value.target_id, value.payload, access.actor_id, value.reason, value.site_id,
        )
        return jsonable_encoder(safe(lambda: runtime.actions.propose(proposal, access)))

    @app.post("/api/actions/{proposal_id}/decision")
    def decide_action(proposal_id: str, value: DecisionInput, access: AccessContext = Depends(identity)):
        decision = ApprovalDecision(
            value.approval_id, access.actor_id, value.role, value.decision,
            value.meaning, comment=value.comment,
        )
        return jsonable_encoder(safe(lambda: runtime.actions.decide(proposal_id, decision, access)))

    @app.get("/api/audit")
    def audit(limit: int = Query(100, ge=1, le=500), access: AccessContext = Depends(identity)):
        return jsonable_encoder(runtime.action_store.audit(access.tenant_id, limit))

    @app.get("/api/context")
    def context(
        query: str, entity_id: list[str] = Query(default=[]),
        access: AccessContext = Depends(identity),
    ):
        return runtime.thread.knowledge.context(query, entity_ids=entity_id, access=access).to_dict()

    static_root = Path(__file__).with_name("static")
    app.mount("/assets", StaticFiles(directory=static_root), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_root / "index.html")

    return app


def _batch_cards(cases) -> list[dict[str, Any]]:
    cards = []
    stages = ["Upstream", "QC review", "Downstream", "Release"]
    for index, case in enumerate(cases):
        batch = next((ref.entity_id for ref in case.entity_refs if ref.entity_type == "batch"), None)
        if batch:
            cards.append({
                "batch_id": batch, "stage": stages[index % len(stages)],
                "status": "attention" if case.status != "closed" else "normal",
                "case_id": case.case_id, "progress": 34 + (index * 23) % 58,
            })
    return cards
