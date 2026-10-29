from collections import Counter
from contextlib import asynccontextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
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
        from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field
    except ImportError as exc:  # pragma: no cover - optional runtime
        raise RuntimeError("Install the 'app' extra to run the API and UI") from exc

    from benchmark.knowledge.domain import AccessContext, CaseRecord, CaseStatus, EntityRef, HumanTask
    from benchmark.incident_demo import IncidentDemoService
    from src.manufacturing_data import ManufacturingStore
    from src.prime_runtime import PrimeManufacturingHarness
    from src.state import BlackboardStore
    from src.workflows import ManufacturingInvestigationWorkflow

    runtime = services or build_services_from_env()
    incident_demo = IncidentDemoService()
    repository = Path(__file__).resolve().parents[2]
    manufacturing_root = os.getenv("BIODEMO_MANUFACTURING_STORE")
    configured_manufacturing_root = manufacturing_root
    artifact_lifetime = ExitStack()
    if manufacturing_root:
        from benchmarks.common.artifact_store import asset_path, descriptor_for
        descriptor, _ = descriptor_for(manufacturing_root)
        if str(manufacturing_root).startswith('dagshub:') or (descriptor and not (Path(manufacturing_root)/'metadata.sqlite').is_file()):
            manufacturing_root = artifact_lifetime.enter_context(asset_path(manufacturing_root))
    if manufacturing_root and not (Path(manufacturing_root) / "metadata.sqlite").is_file():
        raise RuntimeError("BIODEMO_MANUFACTURING_STORE must point to an ingested store")
    if manufacturing_root and not os.getenv("BIODEMO_MANUFACTURING_SCOPE"):
        raise RuntimeError("BIODEMO_MANUFACTURING_SCOPE is required for a manufacturing store")
    manufacturing_store = ManufacturingStore(manufacturing_root) if manufacturing_root else None
    manufacturing_scope = os.getenv("BIODEMO_MANUFACTURING_SCOPE", "default")
    blackboard_root = repository / ".prime" / "manufacturing-blackboards"
    if manufacturing_store:
        namespace = hashlib.sha256(
            f"{configured_manufacturing_root}|{manufacturing_scope}".encode()
        ).hexdigest()[:16]
        blackboard_root = blackboard_root / namespace
    blackboards = BlackboardStore(blackboard_root)
    investigation_workflow = (
        ManufacturingInvestigationWorkflow(blackboard_root, manufacturing_store,
                                           scope=manufacturing_scope, blackboards=blackboards)
        if manufacturing_store else None
    )
    prime_harness = (
        PrimeManufacturingHarness.from_env(
            store=manufacturing_store, blackboards=blackboards,
            workflow=investigation_workflow, scope=manufacturing_scope,
        ) if manufacturing_store else None
    )

    from src.manufacturing_data.cmo.case_api import case_router
    from src.manufacturing_data.cmo.cases import CaseService
    from src.manufacturing_data.cmo.settings import load_local_settings
    load_local_settings()
    pharma_cases=CaseService(Path(os.getenv('CMO_INGESTION_ROOT',repository/'.cache'/'cmo-ingestion')))

    @asynccontextmanager
    async def lifespan(_app):
        pharma_cases.start()
        if runtime.connector_monitor:
            runtime.connector_monitor.start()
        try:
            yield
        finally:
            pharma_cases.stop()
            if runtime.connector_monitor:
                runtime.connector_monitor.stop()
            artifact_lifetime.close()

    app = FastAPI(title="CDMO Operations Intelligence", version="0.3.0", lifespan=lifespan)
    allowed_origins = [x.strip() for x in os.getenv('BIODEMO_ALLOWED_ORIGINS', '').split(',') if x.strip()]
    if allowed_origins:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                           allow_methods=['GET', 'POST'],
                           allow_headers=['Content-Type', 'X-Tenant-ID', 'X-Actor-ID', 'X-Roles', 'X-Site-IDs', 'X-Clearances', 'X-CMO-Token'],
                           expose_headers=['X-Package-Complete', 'X-Open-Issues', 'X-Values-Pending', 'X-Page-Width', 'X-Page-Height', 'X-Page-Count'])

    from src.manufacturing_data.cmo.api import router as cmo_ingestion_router
    app.include_router(cmo_ingestion_router(repository))

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

    class DemoAssessmentInput(BaseModel):
        cursor: int = Field(0, ge=0)
        live: bool = False

    class DemoTaskInput(BaseModel):
        observation: str = ""

    class RLMRolloutInput(BaseModel):
        incident_id: str
        problem: str
        new_evidence_ids: list[str] = Field(default_factory=list)
        as_of: str
        source_package_sha256: str | None = None

    class InvestigationReviewInput(BaseModel):
        role: str
        decision: str
        note: str = ""

    class InvestigationTaskInput(BaseModel):
        status: str
        note: str = ""

    class InvestigationOutcomeInput(BaseModel):
        finding: str
        evidence_ids: list[str] = Field(min_length=1)
        note: str = ""

    class EvidenceFulfillmentInput(BaseModel):
        evidence_ids: list[str] = Field(min_length=1)
        note: str = ""

    class InvestigationCloseInput(BaseModel):
        note: str = ""

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

    app.include_router(case_router(pharma_cases,identity))

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
            "agent_runtime": orchestrator.runtime_status() if orchestrator and hasattr(orchestrator, "runtime_status") else {"mode": "unavailable", "configured": False},
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
    def start_case_demo(case_id: str, access: AccessContext = Depends(identity)):
        orchestrator = runtime.extensions.orchestrator
        if orchestrator is None:
            raise HTTPException(503, "agent orchestrator is not configured")
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
            raise HTTPException(503, "agent orchestrator is not configured")
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

    @app.get("/api/incident-demo")
    def incident_demo_overview() -> dict[str, Any]:
        return incident_demo.overview()

    @app.post("/api/incident-demo/reset")
    def incident_demo_reset() -> dict[str, Any]:
        return incident_demo.reset()

    @app.post("/api/incident-demo/assess")
    def incident_demo_assess(value: DemoAssessmentInput) -> dict[str, Any]:
        return incident_demo.assessment(value.cursor, live=value.live)

    @app.post("/api/incident-demo/tasks/{task_id}/complete")
    def incident_demo_complete_task(task_id: str, value: DemoTaskInput) -> dict[str, Any]:
        return safe(lambda: {
            "task": incident_demo.complete_task(task_id, value.observation),
            "assessment": incident_demo.assessment(len(incident_demo.data["replay_events"]))["assessment"],
        })

    @app.get("/api/incident-demo/future-match")
    def incident_demo_future_match() -> dict[str, Any]:
        return incident_demo.future_match()

    @app.post("/api/manufacturing-os/rollouts")
    def manufacturing_os_rollout(value: RLMRolloutInput,
                                 access: AccessContext = Depends(identity)) -> dict[str, Any]:
        """Run or resume the Prime SDK manufacturing investigation."""
        def execute():
            if prime_harness is None:
                raise RuntimeError("manufacturing store and Prime SDK are not configured")
            if investigation_workflow and access.tenant_id != manufacturing_scope:
                raise PermissionError("investigation scope does not match tenant")
            if value.source_package_sha256 is not None and manufacturing_store.source_fingerprint(
                    scopes=(manufacturing_scope,)) != value.source_package_sha256:
                raise ValueError('Configured evidence store does not match this case-study source package; configure the retained store before follow-up.')
            return prime_harness.run(
                incident_id=value.incident_id, problem=value.problem,
                new_evidence_ids=value.new_evidence_ids, as_of=value.as_of,
            )
        return safe(execute)

    def required_investigation(access: AccessContext):
        if investigation_workflow is None:
            raise HTTPException(503, "manufacturing investigation workflow is not configured")
        if access.tenant_id != manufacturing_scope:
            raise HTTPException(403, "investigation scope does not match tenant")
        return investigation_workflow

    class SourceReviewInput(BaseModel):
        packet_sha256: str
        decision: str
        note: str = Field(min_length=1,max_length=10000)

    @app.get('/api/manufacturing-os/evidence/{observation_id}/review-packet')
    def source_review_packet(observation_id: str, as_of: str, access: AccessContext = Depends(identity)):
        required_investigation(access)
        from src.manufacturing_data.source_review import review_packet
        return safe(lambda: review_packet(manufacturing_store,observation_id,as_of=as_of,scopes=(manufacturing_scope,)))

    @app.get('/api/manufacturing-os/evidence/{observation_id}/page-image')
    def source_page_image(observation_id: str, as_of: str, access: AccessContext = Depends(identity)):
        required_investigation(access)
        from src.manufacturing_data.source_review import page_image
        return Response(safe(lambda:page_image(manufacturing_store,observation_id,as_of=as_of,scopes=(manufacturing_scope,))),
                        media_type='image/png',headers={'Cache-Control':'no-store'})

    @app.post('/api/manufacturing-os/evidence/{observation_id}/source-review')
    def source_review_decision(observation_id: str, value: SourceReviewInput, as_of: str,
                               access: AccessContext = Depends(identity)):
        required_investigation(access)
        if not set(access.roles)&{'qa','sponsor_qa','supervisor'}:raise HTTPException(403,'Source review requires a QA or supervisor role')
        from src.manufacturing_data.source_review import record_review
        return safe(lambda:record_review(manufacturing_store,observation_id,as_of=as_of,scopes=(manufacturing_scope,),
            packet_sha256=value.packet_sha256,reviewer_id=access.actor_id,decision=value.decision,note=value.note))

    @app.get('/manufacturing-source-review/{observation_id}',include_in_schema=False)
    def source_review_screen(observation_id: str, as_of: str, access: AccessContext = Depends(identity)):
        required_investigation(access)
        # The screen uses the same scoped endpoints, and all source text is
        # inserted with textContent. Production identity remains the app's
        # existing development adapter until replaced by trusted OIDC claims.
        settings=json.dumps({'id':observation_id,'as_of':as_of,'headers':{'X-Tenant-Id':access.tenant_id,
            'X-Actor-Id':access.actor_id,'X-Roles':','.join(access.roles)}}).replace('<','\\u003c')
        return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Source citation review</title>
<style>body{font:16px system-ui;margin:32px;color:#173b35}main{display:grid;grid-template-columns:1fr 1fr;gap:24px}img{width:100%;border:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:100%;min-height:90px}button,select{padding:10px;margin:12px 8px 12px 0}@media(max-width:800px){main{grid-template-columns:1fr}}</style>
<h1>Compare citation with original source</h1><p>Review the visible source and extracted text. A recorded decision does not grant scientific qualification.</p>
<p id="status">Loading source…</p><main><section><h2>Original source</h2><img id="page" hidden alt="Original cited PDF page"><pre id="original"></pre></section>
<section><h2>Extracted citation</h2><pre id="text"></pre><h3>Source coordinates and binding</h3><pre id="binding"></pre>
<form id="review"><label>Comparison decision <select id="decision"><option value="matches">Text matches original</option><option value="does_not_match">Text differs from original</option><option value="unreadable">Cannot determine</option></select></label>
<label>Review note<textarea id="note" required></textarea></label><button>Record source review</button></form><pre id="receipt"></pre></section></main>
<script>const config='''+settings+''';let packet;const base='/api/manufacturing-os/evidence/'+encodeURIComponent(config.id), query='?as_of='+encodeURIComponent(config.as_of);
const status=document.getElementById('status');async function checked(response){if(!response.ok)throw Error(await response.text());return response;}
(async()=>{packet=await(await checked(await fetch(base+'/review-packet'+query,{headers:config.headers}))).json();
document.getElementById('text').textContent=packet.extracted_text;document.getElementById('binding').textContent=JSON.stringify({source:packet.source_ref,source_sha256:packet.source_sha256,packet_sha256:packet.packet_sha256},null,2);
document.getElementById('receipt').textContent=JSON.stringify(packet.human_reviews,null,2);status.textContent=packet.review_status;
if(packet.source_format==='.pdf'){const response=await checked(await fetch(base+'/page-image'+query,{headers:config.headers}));const img=document.getElementById('page');img.src=URL.createObjectURL(await response.blob());img.hidden=false;}
else document.getElementById('original').textContent=packet.original_line??'Automatic original-line comparison is unavailable.';
})().catch(e=>status.textContent=e.message);
document.getElementById('review').onsubmit=async e=>{e.preventDefault();try{if(!packet)throw Error('Load and inspect the packet first');const result=await checked(await fetch(base+'/source-review'+query,{method:'POST',headers:{...config.headers,'Content-Type':'application/json'},body:JSON.stringify({packet_sha256:packet.packet_sha256,decision:document.getElementById('decision').value,note:document.getElementById('note').value})}));document.getElementById('receipt').textContent=JSON.stringify(await result.json(),null,2);status.textContent='Human source review recorded; automatic verification and scientific qualification unchanged.';}catch(e){status.textContent=e.message;}};</script></html>''',headers={'Cache-Control':'no-store'})

    @app.get("/api/manufacturing-os/investigations/{incident_id}")
    def manufacturing_investigation(incident_id: str,
                                    access: AccessContext = Depends(identity)):
        workflow = required_investigation(access)
        return safe(lambda: workflow.get(incident_id))

    @app.get("/api/manufacturing-os/investigations/{incident_id}/history")
    def manufacturing_investigation_history(incident_id: str,
                                            access: AccessContext = Depends(identity)):
        workflow = required_investigation(access)
        return safe(lambda: workflow.history(incident_id))

    @app.post("/api/manufacturing-os/investigations/{incident_id}/review")
    def manufacturing_investigation_review(incident_id: str, value: InvestigationReviewInput,
                                           access: AccessContext = Depends(identity)):
        workflow = required_investigation(access)
        return safe(lambda: workflow.decide_review(
            incident_id, actor_id=access.actor_id, roles=access.roles,
            role=value.role, decision=value.decision, note=value.note))

    @app.post("/api/manufacturing-os/investigations/{incident_id}/tasks/{task_id}")
    def manufacturing_investigation_task(incident_id: str, task_id: str,
                                         value: InvestigationTaskInput,
                                         access: AccessContext = Depends(identity)):
        workflow = required_investigation(access)
        return safe(lambda: workflow.update_task(
            incident_id, task_id, actor_id=access.actor_id,
            roles=access.roles, status=value.status, note=value.note))

    @app.post("/api/manufacturing-os/investigations/{incident_id}/outcomes")
    def manufacturing_investigation_outcome(incident_id: str,
                                            value: InvestigationOutcomeInput,
                                            access: AccessContext = Depends(identity)):
        workflow = required_investigation(access)
        return safe(lambda: workflow.record_outcome(
            incident_id, actor_id=access.actor_id, roles=access.roles,
            finding=value.finding, evidence_ids=value.evidence_ids, note=value.note))

    @app.post("/api/manufacturing-os/investigations/{incident_id}/evidence-requests/{request_id}/fulfill")
    def manufacturing_evidence_fulfill(incident_id: str, request_id: str,
                                       value: EvidenceFulfillmentInput,
                                       access: AccessContext = Depends(identity)):
        workflow = required_investigation(access)
        return safe(lambda: workflow.fulfill_evidence_request(
            incident_id, request_id, actor_id=access.actor_id, roles=access.roles,
            evidence_ids=value.evidence_ids, note=value.note))

    @app.post("/api/manufacturing-os/investigations/{incident_id}/close")
    def manufacturing_investigation_close(incident_id: str, value: InvestigationCloseInput,
                                          access: AccessContext = Depends(identity)):
        workflow = required_investigation(access)
        return safe(lambda: workflow.close(
            incident_id, actor_id=access.actor_id, roles=access.roles, note=value.note))

    from benchmark.case_comparison import ComparisonService
    from benchmark.application.demo_runs import DemoRuns
    case_comparison = ComparisonService(repository)
    demo_runs = DemoRuns(repository)
    app.state.demo_runs = demo_runs

    class DemoRunInput(BaseModel):
        milestone: int = Field(default=1, ge=0, le=20)

    @app.get("/api/demo")
    def demo_payload() -> dict[str, Any]:
        from benchmark.case_comparison.demo import build_demo
        return {"cases": [{**build_demo(case_comparison.case(case_id)),
                           "agent": demo_runs.availability(case_id)}
                          for case_id in ("fresenius", "cho")]}

    @app.post("/api/demo/{case_id}/runs", status_code=202)
    def start_demo_agent(case_id: str, value: DemoRunInput,
                         access: AccessContext = Depends(identity)):
        from benchmark.case_comparison.demo import build_demo
        def start():
            data = build_demo(case_comparison.case(case_id))
            if value.milestone >= len(data["stages"]):
                raise ValueError("unknown timeline milestone")
            cutoff = data["stages"][value.milestone]["time"]
            return demo_runs.start(case_id, access.tenant_id, as_of=cutoff)
        return safe(start)

    @app.get("/api/demo/runs/{run_id}")
    def demo_agent_status(run_id: str, access: AccessContext = Depends(identity)):
        return safe(lambda: demo_runs.get(run_id, access.tenant_id))

    @app.get("/api/case-comparison")
    def case_comparison_index() -> dict[str, Any]:
        """Available benchmark case studies and dashboard sections."""
        return case_comparison.dashboard()

    @app.get("/api/case-comparison/cho/series")
    def case_comparison_cho_series(
        cultivation: str,
        variables: str = "",
        max_points: int = Query(240, ge=10, le=1200),
    ) -> dict[str, Any]:
        """Downsampled aligned trajectories for the CHO process view."""
        names = [name.strip() for name in variables.split("|") if name.strip()]
        return safe(lambda: case_comparison.series(cultivation, names, max_points))

    @app.get("/api/case-comparison/{case_id}")
    def case_comparison_case(case_id: str) -> dict[str, Any]:
        """Full comparison payload for one case study (all sections)."""
        return safe(lambda: case_comparison.case(case_id))

    @app.get("/api/pilot-comparison")
    def pilot_comparison(access: AccessContext = Depends(identity)) -> dict[str, Any]:
        """Serve the one-command pilot comparison (comparison.json + report summary)."""
        import json

        configured = os.getenv("BIODEMO_PILOT_COMPARISON_DIR")
        comparison_dir = Path(configured) if configured else repository / "runs" / "my-comparison"
        comparison_file = comparison_dir / "comparison.json"
        if not comparison_file.is_file():
            raise HTTPException(404, f"pilot comparison not found in {comparison_dir}; "
                                     "run python3 -m src.prime_runtime.compare ... --output runs/my-comparison")

        def load_json(name: str) -> Any | None:
            path = comparison_dir / name
            if not path.is_file():
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None

        comparison = load_json("comparison.json") or {}
        agent = load_json("agent_report.json") or {}
        cited = load_json("cited_evidence.json")
        metrics = dict(agent.get("rollout_metrics", {})) if isinstance(agent, dict) else {}
        for key in ("prime_log", "prime_tool_calls"):
            metrics.pop(key, None)
        hypotheses = agent.get("causal_hypotheses", []) if isinstance(agent, dict) else []
        timeline: dict[str, Any] = {"as_of": comparison.get("as_of"),
                                    "evidence_min": None, "evidence_max": None,
                                    "evidence_count": 0, "by_month": []}
        if isinstance(cited, list) and cited:
            dates = sorted(str(r.get("available_at", "")) for r in cited if r.get("available_at"))
            if dates:
                timeline.update(evidence_min=dates[0], evidence_max=dates[-1])
            timeline["evidence_count"] = len(cited)
            counts: dict[str, int] = {}
            for stamp in dates:
                counts[stamp[:7]] = counts.get(stamp[:7], 0) + 1
            timeline["by_month"] = [{"month": month, "count": counts[month]}
                                    for month in sorted(counts)]
        return jsonable_encoder({
            "directory": str(comparison_dir),
            "comparison": comparison,
            "timeline": timeline,
            "agent": {
                "assessment": agent.get("assessment"),
                "report_status":agent.get('report_status','incomplete'),
                "investigation_review":agent.get('investigation_review',{}),
                "cross_scope_synthesis":agent.get('cross_scope_synthesis',''),
                "observed_facts":agent.get('observed_facts',[]),
                "interpretations":agent.get('interpretations',[]),
                "severity": agent.get("severity"),
                "scope": agent.get("scope"),
                "evidence_ids": agent.get("evidence_ids", [])[:200],
                "evidence_count": len(agent.get("evidence_ids", [])),
                "causal_hypotheses": hypotheses[:12],
                "hypothesis_count": len(agent.get("causal_hypotheses", [])),
                "open_questions": (agent.get("open_questions", []) or [])[:20],
                "pending_evidence_requests": agent.get("pending_evidence_requests", []),
                "rollout_metrics": metrics,
            },
            "cited_evidence_preview": (cited[:20] if isinstance(cited, list) else []),
            "cited_evidence_count": len(cited) if isinstance(cited, list) else 0,
        })

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
        return FileResponse(static_root / "summary.html")

    @app.get("/platform", include_in_schema=False)
    def platform_frontend():
        return RedirectResponse("/")

    @app.get("/landing", include_in_schema=False)
    def landing_page():
        return RedirectResponse("/")

    @app.get("/comparison", include_in_schema=False)
    def comparison_page():
        """Compatibility link to the single demo page."""
        return RedirectResponse("/")

    @app.get("/comparison/detail", include_in_schema=False)
    def comparison_detail_page():
        """Compatibility link to the single demo page."""
        return RedirectResponse("/")

    @app.get("/benchmark", include_in_schema=False)
    def benchmark_report():
        """Current all-attempt publication view; never infer scientific approval."""
        from scripts.build_publication import load_results, example, dashboard
        results=load_results(repository)
        results['investigation_example']=example(repository)
        return HTMLResponse(dashboard(results),headers={"Cache-Control":"no-store"})

    @app.get("/benchmark-details", include_in_schema=False)
    def benchmark_details():
        from benchmark.case_comparison.report import build_report
        return HTMLResponse(build_report(ComparisonService(repository)),
                            headers={"Cache-Control": "no-store"})

    @app.get("/benchmark-artifact/{name}", include_in_schema=False)
    def publication_artifact(name: str):
        allowed={'BENCHMARK_RESULTS.json','BENCHMARK_REPORT.md','FAILURE_ANALYSIS.md',
                 'REPRODUCE.md','PUBLIC_DEMO_SUMMARY.md','PUBLIC_SOURCE_AUDIT.json'}
        if name not in allowed or not (repository/name).is_file():
            raise HTTPException(status_code=404,detail="Publication artifact unavailable")
        return FileResponse(repository/name)

    @app.get("/benchmark-source/{name}", include_in_schema=False)
    def publication_source(name: str):
        # Only publicly sourced CHO workbooks; no arbitrary paths, labels or
        # simulated private records are exposed by this endpoint.
        manifest=repository/'benchmarks/cho/source_manifest.json'
        allowed={Path(m['installed_path']).name for m in json.loads(manifest.read_text()).get('members',[]) if m['installed_path'].endswith('.xlsx')}
        if name not in allowed:
            raise HTTPException(status_code=404,detail="Public source unavailable")
        source=repository/'benchmarks/cho/raw/workbooks'/name
        if not source.is_file():raise HTTPException(status_code=404,detail="Public source unavailable")
        return FileResponse(source,filename=name)

    @app.get("/benchmark-report", include_in_schema=False)
    def legacy_benchmark_report():
        return RedirectResponse("/benchmark")

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
