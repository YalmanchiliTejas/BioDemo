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

from .control import ActionControlPlane, ActionStore, InMemoryActionStore
from .extensions import ExtensionRegistry
from .models import ActionProposal, ApprovalDecision


@dataclass
class ApplicationServices:
    thread: DigitalThread
    actions: ActionControlPlane
    action_store: ActionStore
    extensions: ExtensionRegistry


def build_demo_services(evidence_root: Path | None = None) -> ApplicationServices:
    graph = InMemoryGraphStore()
    documents = InMemoryDocumentStore()
    cases = InMemoryCaseStore()
    outbox = InMemoryOutbox()
    root = evidence_root or Path(tempfile.gettempdir()) / "cdmo-application-evidence"
    thread = DigitalThread(KnowledgeBase(graph, documents), FileEvidenceStore(root), cases, outbox)
    action_store = InMemoryActionStore()
    services = ApplicationServices(
        thread, ActionControlPlane(action_store), action_store, ExtensionRegistry(),
    )
    _seed_demo(services)
    return services


def build_services_from_env() -> ApplicationServices:
    if os.getenv("APP_MODE", "demo").lower() != "production":
        return build_demo_services()
    from benchmark.knowledge.runtime import digital_thread_from_env
    from .postgres import PostgresActionStore

    thread = digital_thread_from_env(semantic=os.getenv("SEMANTIC_SEARCH", "false").lower() == "true")
    action_store = PostgresActionStore(os.getenv(
        "POSTGRES_DSN", "postgresql://biopharma:biopharma-dev@localhost:5432/biopharma"
    ))
    return ApplicationServices(
        thread, ActionControlPlane(action_store), action_store, ExtensionRegistry(),
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
