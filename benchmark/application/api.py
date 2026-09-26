from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from .bootstrap import ApplicationServices, build_services_from_env
from .connector_monitor import ConnectorConfig
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

    @asynccontextmanager
    async def lifespan(_app):
        if runtime.connector_monitor:
            runtime.connector_monitor.start()
        try:
            yield
        finally:
            if runtime.connector_monitor:
                runtime.connector_monitor.stop()

    app = FastAPI(title="CDMO Operations Intelligence", version="0.3.0", lifespan=lifespan)

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

    class AgentToolInput(BaseModel):
        criteria: dict[str, Any] = Field(default_factory=dict)

    class IntelligenceInput(BaseModel):
        arguments: dict[str, Any] = Field(default_factory=dict)

    class ConnectorInput(BaseModel):
        connector_id: str
        name: str
        source_system: str
        base_url: str
        records_path: str
        site_id: str
        poll_interval_seconds: int = Field(60, ge=5, le=86400)
        trigger_event_types: list[str] = Field(default_factory=list)
        auto_start_agent: bool = False
        enabled: bool = True
        cursor_parameter: str = "cursor"
        auth_header: str | None = None
        auth_token_env: str | None = None
        classification: str = "internal"
        owner_id: str = "qa-monitor"
        field_mapping: dict[str, str] = Field(default_factory=dict)

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
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    def visible_site(site_id: str | None, access: AccessContext) -> bool:
        return not site_id or not access.site_ids or site_id in access.site_ids

    def visible_cases(access: AccessContext):
        return [
            case for case in runtime.thread.cases.list_cases(access.tenant_id)
            if visible_site(case.site_id, access)
        ]

    def require_visible_case(case_id: str, access: AccessContext):
        case = runtime.thread.cases.get_case(case_id, access.tenant_id)
        if case is None or not visible_site(case.site_id, access):
            raise HTTPException(404, "case not found")
        return case

    def require_connector_admin(access: AccessContext) -> None:
        if "system_admin" not in access.roles:
            raise HTTPException(403, "system_admin role is required")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "extensions": runtime.extensions.status(),
            "connector_monitor": runtime.connector_monitor is not None,
            "action_execution": runtime.execution.configured,
        }

    @app.get("/api/session")
    def session(access: AccessContext = Depends(identity)) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tenant_id": access.tenant_id, "actor_id": access.actor_id,
            "site_ids": list(access.site_ids), "roles": list(access.roles),
            "clearances": list(access.clearances),
        }
        if services is None and os.getenv("APP_MODE", "demo").lower() != "production":
            result["demo_tenants"] = [
                {"tenant_id": "demo-cdmo", "name": "Northstar Therapeutics", "site_id": "PHX-01"},
                {"tenant_id": "helix-biologics", "name": "Helix Biologics", "site_id": "BOS-02"},
            ]
        return result

    @app.get("/api/control-plane")
    def control_plane(access: AccessContext = Depends(identity)) -> dict[str, Any]:
        orchestrator = runtime.extensions.orchestrator
        router = runtime.extensions.model_router
        tools = runtime.extensions.tool_executor
        return {
            "tenant_id": access.tenant_id,
            "agents": orchestrator.catalog() if orchestrator and hasattr(orchestrator, "catalog") else [],
            "models": router.status() if router and hasattr(router, "status") else [],
            "tools": tools.status() if tools and hasattr(tools, "status") else [],
            "action_execution": {
                "configured": runtime.execution.configured,
                "mode": runtime.execution.mode,
            },
        }

    @app.post("/api/intelligence/{tool_name}")
    def run_intelligence(
        tool_name: str, value: IntelligenceInput, access: AccessContext = Depends(identity),
    ):
        if not ({"scientist", "msat", "qa", "sponsor_qa", "system_admin"} & set(access.roles)):
            raise HTTPException(403, "a science or quality role is required")
        tools = runtime.extensions.tool_executor
        if tools is None:
            raise HTTPException(503, "tool gateway is not configured")
        return safe(lambda: tools.execute(tool_name, value.arguments))

    @app.get("/api/dashboard")
    def dashboard(access: AccessContext = Depends(identity)) -> dict[str, Any]:
        cases = visible_cases(access)
        case_ids = {case.case_id for case in cases}
        tasks = [task for task in runtime.thread.cases.list_tasks(access.tenant_id) if task.case_id in case_ids]
        proposals = [
            proposal for proposal in runtime.action_store.list(access.tenant_id)
            if visible_site(proposal.site_id, access)
        ]
        batches = _batch_cards(cases)
        task_load = Counter(task.assigned_role for task in tasks if task.status == "open")
        return jsonable_encoder({
            "tenant_id": access.tenant_id,
            "stats": {
                "open_cases": sum(case.status != CaseStatus.CLOSED for case in cases),
                "pending_tasks": sum(task.status == "open" for task in tasks),
                "pending_approvals": sum(proposal.status == "pending_approval" for proposal in proposals),
                "batches_in_view": len(batches),
                "source_connectors": len([
                    item for item in runtime.connector_monitor.list(access.tenant_id)
                    if visible_site(item.get("site_id"), access)
                ])
                if runtime.connector_monitor else 0,
            },
            "batches": batches,
            "quality_trend": [94, 96, 95, 97, 96, 98, 97, 99, 98, 98, 99, 98],
            "generated_at": datetime.now(timezone.utc),
            "handoff": [
                {
                    "at": case.updated_at,
                    "text": f"{case.title} is {case.status.value.replace('_', ' ')}; owner {case.owner_id}.",
                }
                for case in sorted(cases, key=lambda item: item.updated_at, reverse=True)[:3]
            ],
            "task_load": [
                {"role": role, "open_tasks": count}
                for role, count in sorted(task_load.items(), key=lambda item: (-item[1], item[0]))
            ],
            "extensions": runtime.extensions.status(),
            "demo_data": services is None and os.getenv("APP_MODE", "demo").lower() != "production",
        })

    @app.get("/api/connectors")
    def list_connectors(access: AccessContext = Depends(identity)):
        if runtime.connector_monitor is None:
            raise HTTPException(503, "connector monitor is not configured")
        return [
            item for item in runtime.connector_monitor.list(access.tenant_id)
            if visible_site(item.get("site_id"), access)
        ]

    @app.post("/api/connectors", status_code=201)
    def put_connector(value: ConnectorInput, access: AccessContext = Depends(identity)):
        require_connector_admin(access)
        if not visible_site(value.site_id, access):
            raise HTTPException(403, "connector site is outside the actor's scope")
        if runtime.connector_monitor is None:
            raise HTTPException(503, "connector monitor is not configured")
        config = ConnectorConfig(
            connector_id=value.connector_id,
            name=value.name,
            source_system=value.source_system,
            base_url=value.base_url,
            records_path=value.records_path,
            tenant_id=access.tenant_id,
            site_id=value.site_id,
            poll_interval_seconds=value.poll_interval_seconds,
            trigger_event_types=tuple(value.trigger_event_types),
            auto_start_agent=value.auto_start_agent,
            enabled=value.enabled,
            cursor_parameter=value.cursor_parameter,
            auth_header=value.auth_header,
            auth_token_env=value.auth_token_env,
            classification=value.classification,
            owner_id=value.owner_id,
            field_mapping=value.field_mapping,
        )
        return jsonable_encoder(safe(lambda: runtime.connector_monitor.put(config)))

    @app.post("/api/connectors/{connector_id}/sync")
    def sync_connector(connector_id: str, access: AccessContext = Depends(identity)):
        require_connector_admin(access)
        if runtime.connector_monitor is None:
            raise HTTPException(503, "connector monitor is not configured")
        connector = next(
            (
                item for item in runtime.connector_monitor.list(access.tenant_id)
                if item["connector_id"] == connector_id
            ),
            None,
        )
        if connector is None:
            raise HTTPException(404, "connector not found")
        if not visible_site(connector.get("site_id"), access):
            raise HTTPException(404, "connector not found")
        return safe(lambda: runtime.connector_monitor.sync(connector_id, access.tenant_id))

    @app.get("/api/cases")
    def list_cases(access: AccessContext = Depends(identity)):
        return jsonable_encoder(visible_cases(access))

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str, access: AccessContext = Depends(identity)):
        case = require_visible_case(case_id, access)
        orchestrator = runtime.extensions.orchestrator
        return jsonable_encoder({
            "case": case,
            "tasks": runtime.thread.cases.tasks_for_case(case_id, access.tenant_id),
            "actions": [
                item for item in runtime.action_store.list(access.tenant_id)
                if item.case_id == case_id and visible_site(item.site_id, access)
            ],
            "agent_run": orchestrator.latest(case_id, access.tenant_id) if orchestrator else None,
            "agent_case_state": orchestrator.case_state(case_id, access.tenant_id) if orchestrator else None,
        })

    @app.post("/api/cases", status_code=201)
    def create_case(value: CaseInput, access: AccessContext = Depends(identity)):
        if not visible_site(value.site_id, access):
            raise HTTPException(403, "case site is outside the actor's scope")
        case = CaseRecord(
            value.case_id, access.tenant_id, value.case_type, value.title, value.owner_id,
            value.site_id, entity_refs=tuple(EntityRef(item, "entity") for item in value.entity_ids),
        )
        safe(lambda: runtime.thread.open_case(case, access=access))
        return jsonable_encoder(case)

    @app.get("/api/tasks")
    def list_tasks(access: AccessContext = Depends(identity)):
        case_ids = {case.case_id for case in visible_cases(access)}
        return jsonable_encoder([
            task for task in runtime.thread.cases.list_tasks(access.tenant_id)
            if task.case_id in case_ids
        ])

    @app.post("/api/tasks", status_code=201)
    def create_task(value: TaskInput, access: AccessContext = Depends(identity)):
        require_visible_case(value.case_id, access)
        task = HumanTask(
            value.task_id, value.case_id, access.tenant_id, value.task_type,
            value.title, value.assigned_role, assigned_to=value.assigned_to,
        )
        safe(lambda: runtime.thread.assign_task(task, access=access))
        return jsonable_encoder(task)

    @app.post("/api/tasks/{task_id}/complete")
    def complete_task(task_id: str, access: AccessContext = Depends(identity)):
        task = next(
            (item for item in runtime.thread.cases.list_tasks(access.tenant_id) if item.task_id == task_id),
            None,
        )
        if task is None:
            raise HTTPException(404, "task not found")
        require_visible_case(task.case_id, access)
        return jsonable_encoder(safe(lambda: runtime.thread.complete_task(task_id, access=access)))

    @app.get("/api/actions")
    def list_actions(access: AccessContext = Depends(identity)):
        return jsonable_encoder([
            proposal for proposal in runtime.action_store.list(access.tenant_id)
            if visible_site(proposal.site_id, access)
        ])

    @app.post("/api/actions", status_code=201)
    def propose_action(value: ProposalInput, access: AccessContext = Depends(identity)):
        case = require_visible_case(value.case_id, access)
        site_id = value.site_id or case.site_id
        if not visible_site(site_id, access):
            raise HTTPException(403, "action site is outside the actor's scope")
        proposal = ActionProposal(
            value.proposal_id, access.tenant_id, value.case_id, value.operation,
            value.target_id, value.payload, access.actor_id, value.reason, site_id,
        )
        return jsonable_encoder(safe(lambda: runtime.actions.propose(proposal, access)))

    @app.post("/api/actions/{proposal_id}/decision")
    def decide_action(proposal_id: str, value: DecisionInput, access: AccessContext = Depends(identity)):
        proposal = runtime.action_store.get(access.tenant_id, proposal_id)
        if proposal is None or not visible_site(proposal.site_id, access):
            raise HTTPException(404, "action proposal not found")
        decision = ApprovalDecision(
            value.approval_id, access.actor_id, value.role, value.decision,
            value.meaning, comment=value.comment,
        )
        return jsonable_encoder(safe(lambda: runtime.actions.decide(proposal_id, decision, access)))

    @app.post("/api/actions/{proposal_id}/execute")
    def execute_action(proposal_id: str, access: AccessContext = Depends(identity)):
        return jsonable_encoder(safe(lambda: runtime.execution.execute(proposal_id, access)))

    @app.get("/api/audit")
    def audit(limit: int = Query(100, ge=1, le=500), access: AccessContext = Depends(identity)):
        visible_action_ids = {
            proposal.proposal_id for proposal in runtime.action_store.list(access.tenant_id)
            if visible_site(proposal.site_id, access)
        }
        return jsonable_encoder([
            entry for entry in runtime.action_store.audit(access.tenant_id, limit)
            if entry.object_type != "action_proposal" or entry.object_id in visible_action_ids
        ])

    @app.get("/api/context")
    def context(
        query: str, entity_id: list[str] = Query(default=[]),
        access: AccessContext = Depends(identity),
    ):
        return runtime.thread.knowledge.context(query, entity_ids=entity_id, access=access).to_dict()

    @app.post("/api/cases/{case_id}/agent", status_code=202)
    def start_deviation_agent(case_id: str, access: AccessContext = Depends(identity)):
        orchestrator = runtime.extensions.orchestrator
        if orchestrator is None:
            raise HTTPException(503, "Prime Agent deviation orchestrator is not configured")
        case = require_visible_case(case_id, access)
        entity_ids = [reference.entity_id for reference in case.entity_refs]
        context_bundle = runtime.thread.knowledge.context(
            case.title,
            entity_ids=entity_ids,
            access=access,
            limit=50,
        )
        context = jsonable_encoder({
            "case": case,
            "case_source": {
                "source_system": "Bio-Demo case service",
                "source_record_id": case.case_id,
                "timestamp": case.opened_at,
                "evidence_ref": f"biodemo://cases/{case.case_id}",
            },
            "tasks": runtime.thread.cases.tasks_for_case(case_id, access.tenant_id),
            "existing_action_proposals": [
                item for item in runtime.action_store.list(access.tenant_id)
                if item.case_id == case_id and visible_site(item.site_id, access)
            ],
            "digital_thread": context_bundle.to_dict(),
            "identity": {
                "tenant_id": access.tenant_id,
                "site_ids": list(access.site_ids),
                "clearances": list(access.clearances),
            },
        })
        return orchestrator.start(case_id, context)

    @app.get("/api/agent-runs/{run_id}")
    def agent_run(run_id: str, access: AccessContext = Depends(identity)):
        orchestrator = runtime.extensions.orchestrator
        if orchestrator is None:
            raise HTTPException(503, "Prime Agent deviation orchestrator is not configured")
        run = orchestrator.get(run_id)
        if run is None or run.get("tenant_id", access.tenant_id) != access.tenant_id:
            raise HTTPException(404, "agent run not found")
        case = runtime.thread.cases.get_case(run["case_id"], access.tenant_id)
        if case is None or not visible_site(case.site_id, access):
            raise HTTPException(404, "agent run not found")
        return {
            **run,
            "case_state": orchestrator.case_state(run["case_id"], access.tenant_id),
        }

    allowed_agent_tools = {
        "batches", "process_steps", "process_traces", "equipment_history",
        "material_lineage", "lab_results", "deviations", "capas",
        "governing_documents", "batch_relationships", "batch_metrics",
        "process_knowledge",
    }

    @app.post("/api/agent/tools/{concept}")
    def agent_tool(
        concept: str,
        value: AgentToolInput,
        access: AccessContext = Depends(identity),
    ):
        if concept not in allowed_agent_tools:
            raise HTTPException(404, "unknown manufacturing concept")
        criteria = value.criteria
        entity_ids: list[str] = []
        for key in (
            "batch_id", "equipment_id", "material_lot", "supplier_lot",
            "product", "process_version", "procedure", "deviation_id",
        ):
            item = criteria.get(key)
            if isinstance(item, list):
                entity_ids.extend(str(entry) for entry in item if entry)
            elif item:
                entity_ids.append(str(item))
        terms = [concept.replace("_", " ")]
        terms.extend(str(item) for item in criteria.values() if item and not isinstance(item, (list, dict)))
        bundle = runtime.thread.knowledge.context(
            " ".join(terms),
            entity_ids=entity_ids,
            access=access,
            limit=100,
        )
        records = _agent_tool_records(bundle, concept, criteria)
        return {
            "concept": concept,
            "criteria": criteria,
            "records": records,
            "citations": [citation.__dict__ for citation in bundle.citations],
            "status": "OK",
        }

    static_root = Path(__file__).with_name("static")
    app.mount("/assets", StaticFiles(directory=static_root), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static_root / "index.html")

    return app


def _batch_cards(cases) -> list[dict[str, Any]]:
    cards = []
    stages = {
        "deviation": "Investigation", "oos": "QC assessment",
        "maintenance": "Equipment assessment", "capa": "Effectiveness review",
        "release": "Release review",
    }
    progress = {"open": 25, "investigating": 55, "pending_approval": 80, "closed": 100}
    for case in cases:
        batch = next((ref.entity_id for ref in case.entity_refs if ref.entity_type == "batch"), None)
        if batch:
            cards.append({
                "batch_id": batch, "stage": stages.get(case.case_type, "Case review"),
                "status": "attention" if case.status != "closed" else "normal",
                "case_id": case.case_id, "progress": progress.get(case.status.value, 25),
                "next_gate": "Human approval" if case.status.value == "pending_approval" else "Case closure",
                "updated_at": case.updated_at,
            })
    return cards


def _agent_tool_records(bundle, concept: str, criteria: dict[str, Any]) -> list[dict[str, Any]]:
    if concept != "batch_metrics":
        records = [document.payload for document in bundle.documents]
        records.extend(event.to_dict() for event in bundle.events)
        return records
    requested = criteria.get("batch_id", [])
    requested_batches = requested if isinstance(requested, list) else [requested]
    records = []
    for document in bundle.documents:
        numeric: dict[str, float] = {}
        _flatten_numeric(document.payload, numeric)
        document_batches = [
            entity_id for entity_id in document.metadata.get("entity_ids", [])
            if str(entity_id).upper().startswith("BATCH-")
        ]
        batches = document_batches or requested_batches
        for batch_id in batches:
            if batch_id:
                records.append({"batch_id": str(batch_id), **numeric})
    return records


def _flatten_numeric(value: Any, output: dict[str, float], prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            _flatten_numeric(item, output, path)
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and prefix:
        output[prefix] = value
        output.setdefault(prefix.rsplit(".", 1)[-1], value)
