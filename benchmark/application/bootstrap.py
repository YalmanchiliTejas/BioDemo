from __future__ import annotations

import tempfile
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from benchmark.knowledge.digital_thread import DigitalThread
from benchmark.knowledge.domain import AccessContext, CaseRecord, CaseStatus, EntityRef, HumanTask
from benchmark.knowledge.evidence import FileEvidenceStore
from benchmark.knowledge.memory import (
    InMemoryCaseStore, InMemoryDocumentStore, InMemoryGraphStore, InMemoryOutbox,
)
from benchmark.knowledge.service import KnowledgeBase

from .connector_monitor import ConnectorMonitor
from .control import ActionControlPlane, ActionStore, InMemoryActionStore
from .deviation_agent import PrimeAgentDeviationOrchestrator
from .execution import ActionExecutionGateway, DemoActionWriter, IntegrationActionWriter
from .extensions import ExtensionRegistry
from .intelligence import DeterministicModelRouter, ToolGateway
from .models import ActionProposal, ApprovalDecision
from .orchestration import CaseOrchestrator


@dataclass
class ApplicationServices:
    thread: DigitalThread
    actions: ActionControlPlane
    action_store: ActionStore
    extensions: ExtensionRegistry
    execution: ActionExecutionGateway
    connector_monitor: ConnectorMonitor | None = None


def build_demo_services(evidence_root: Path | None = None) -> ApplicationServices:
    graph = InMemoryGraphStore()
    documents = InMemoryDocumentStore()
    cases = InMemoryCaseStore()
    outbox = InMemoryOutbox()
    root = evidence_root or Path(tempfile.gettempdir()) / "cdmo-application-evidence"
    thread = DigitalThread(KnowledgeBase(graph, documents), FileEvidenceStore(root), cases, outbox)
    action_store = InMemoryActionStore()
    deviation_harness = PrimeAgentDeviationOrchestrator.from_env()
    router = DeterministicModelRouter(llm_configured=deviation_harness is not None)
    tools = ToolGateway(router)
    orchestrator = CaseOrchestrator(tools, deviation_harness)
    extensions = ExtensionRegistry(orchestrator=orchestrator, model_router=router, tool_executor=tools)
    connector_state = (
        evidence_root.parent / "connectors.json"
        if evidence_root
        else Path(os.getenv("BIODEMO_CONNECTOR_STATE", Path.cwd() / ".prime" / "connectors.json"))
    )
    actions = ActionControlPlane(action_store)
    services = ApplicationServices(
        thread, actions, action_store, extensions, ActionExecutionGateway(actions, DemoActionWriter(thread)),
        ConnectorMonitor(thread, extensions, connector_state),
    )
    _seed_demo(services)
    return services


def build_services_from_env() -> ApplicationServices:
    if os.getenv("APP_MODE", "demo").lower() != "production":
        return build_demo_services()
    from benchmark.knowledge.runtime import digital_thread_from_env
    from benchmark.integration import IntegrationGateway, connectors_from_settings
    from .postgres import PostgresActionStore

    thread = digital_thread_from_env(semantic=os.getenv("SEMANTIC_SEARCH", "false").lower() == "true")
    action_store = PostgresActionStore(os.getenv(
        "POSTGRES_DSN", "postgresql://biopharma:biopharma-dev@localhost:5432/biopharma"
    ))
    deviation_harness = PrimeAgentDeviationOrchestrator.from_env()
    router = DeterministicModelRouter(llm_configured=deviation_harness is not None)
    tools = ToolGateway(router)
    extensions = ExtensionRegistry(
        orchestrator=CaseOrchestrator(tools, deviation_harness),
        model_router=router,
        tool_executor=tools,
    )
    connector_state = Path(os.getenv(
        "BIODEMO_CONNECTOR_STATE", Path.cwd() / ".prime" / "connectors.json"
    ))
    actions = ActionControlPlane(action_store)
    connectors = connectors_from_settings(os.environ)
    writable = {
        key: connector for key, connector in connectors.items()
        if connector.config.write_path is not None
    }
    writer = IntegrationActionWriter(IntegrationGateway(thread, thread.cases), writable) if writable else None
    return ApplicationServices(
        thread, actions, action_store, extensions, ActionExecutionGateway(actions, writer),
        ConnectorMonitor(thread, extensions, connector_state),
    )


def _seed_demo(services: ApplicationServices) -> None:
    now = datetime.now(timezone.utc)
    access = AccessContext(
        "demo-cdmo", "operator-07", ("PHX-01",), ("operator", "supervisor"),
        ("internal", "confidential"),
    )
    cases = (
        CaseRecord(
            "CASE-2409", "demo-cdmo", "deviation", "Bioreactor pH excursion", "qa-14",
            "PHX-01", CaseStatus.INVESTIGATING,
            (EntityRef("BATCH-2409", "batch"), EntityRef("BIOREACTOR-01", "asset")),
            "Probe drift or insufficient base addition", now - timedelta(hours=8), now - timedelta(minutes=18),
        ),
        CaseRecord(
            "CASE-2410", "demo-cdmo", "oos", "Release assay potency trend", "qc-03",
            "PHX-01", CaseStatus.PENDING_APPROVAL,
            (EntityRef("BATCH-2410", "batch"), EntityRef("SAMPLE-884", "sample")),
            "Method variability under review", now - timedelta(hours=19), now - timedelta(hours=1),
        ),
        CaseRecord(
            "CASE-2398", "demo-cdmo", "maintenance", "Chromatography pressure increase", "msat-05",
            "PHX-01", CaseStatus.OPEN,
            (EntityRef("BATCH-2398", "batch"), EntityRef("CHROM-01", "asset")),
            None, now - timedelta(days=1), now - timedelta(hours=3),
        ),
    )
    for case in cases:
        services.thread.open_case(case, access=access)
    tasks = (
        HumanTask("TASK-81", "CASE-2409", "demo-cdmo", "review", "Review historian pH trace", "MSAT", assigned_to="msat-05"),
        HumanTask("TASK-82", "CASE-2410", "demo-cdmo", "approval", "Approve OOS phase-I assessment", "QA"),
        HumanTask("TASK-83", "CASE-2398", "demo-cdmo", "inspection", "Inspect column inlet frit", "Maintenance", assigned_to="maint-02"),
    )
    for task in tasks:
        services.thread.assign_task(task, access=access)
    proposal = services.actions.propose(ActionProposal(
        "ACT-2409-HOLD", "demo-cdmo", "CASE-2409", "place_hold", "BATCH-2409",
        {"reason_code": "process_excursion"}, "operator-07", "Prevent disposition before investigation",
        "PHX-01",
    ), access)
    supervisor = AccessContext(
        "demo-cdmo", "supervisor-02", ("PHX-01",), ("supervisor",), ("internal", "confidential"),
    )
    services.actions.decide(proposal.proposal_id, ApprovalDecision(
        "APR-81", "supervisor-02", "supervisor", "approved", "manufacturing hold authorization",
        now - timedelta(minutes=12), "Hold is proportionate to observed risk",
    ), supervisor)
    qa_access = AccessContext("demo-cdmo", "msat-05", ("PHX-01",), ("supervisor",), ("internal", "confidential"))
    services.actions.propose(ActionProposal(
        "ACT-2410-CLOSE", "demo-cdmo", "CASE-2410", "close_deviation", "DEV-2410",
        {"disposition": "phase_i_complete"}, "msat-05", "Phase-I assessment package complete", "PHX-01",
    ), qa_access)

    # A second sponsor proves tenant isolation in the running demo instead of
    # relying only on tests or a tenant label in the interface.
    partner_access = AccessContext(
        "helix-biologics", "operator-22", ("BOS-02",),
        ("operator", "supervisor"), ("internal", "confidential"),
    )
    partner_case = CaseRecord(
        "CASE-7812", "helix-biologics", "capa", "Filter integrity CAPA effectiveness",
        "qa-22", "BOS-02", CaseStatus.INVESTIGATING,
        (EntityRef("BATCH-7812", "batch"), EntityRef("FILTER-07", "asset")),
        "Effectiveness evidence is being assembled", now - timedelta(hours=6),
        now - timedelta(minutes=42),
    )
    services.thread.open_case(partner_case, access=partner_access)
    services.thread.assign_task(HumanTask(
        "TASK-211", "CASE-7812", "helix-biologics", "review",
        "Verify CAPA effectiveness evidence", "QA", assigned_to="qa-22",
    ), access=partner_access)
