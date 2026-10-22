from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from benchmark.integration import AuthorizedAction, IntegrationGateway
from benchmark.knowledge.domain import AccessContext
from benchmark.knowledge.digital_thread import DigitalThread

from .control import ActionControlPlane
from .models import ActionProposal, ProposalStatus


class ActionWriter(Protocol):
    def write(self, proposal: ActionProposal, access: AccessContext) -> str: ...


class DemoActionWriter:
    """Reviewable demo system-of-record loop that emits a canonical acknowledgement."""

    def __init__(self, thread: DigitalThread | None = None) -> None:
        self.thread = thread

    def write(self, proposal: ActionProposal, access: AccessContext) -> str:
        occurred_at = datetime.now(timezone.utc)
        source_record_id = f"DEMO-ACK-{proposal.proposal_id}-{occurred_at.strftime('%Y%m%d%H%M%S%f')}"
        if self.thread is not None:
            self.thread.ingest_raw_event(
                {
                    "source_record_id": source_record_id,
                    "timestamp": occurred_at.isoformat(),
                    "event_type": "action_acknowledged",
                    "title": f"{proposal.operation} accepted by demo system of record",
                    "status": "accepted",
                    "action_id": proposal.proposal_id,
                    "entities": [{"entity_id": proposal.target_id, "entity_type": "action_target"}],
                },
                access=access, source_system=str(proposal.payload.get("source_system", "QMS")),
                site_id=proposal.site_id, classification="internal",
            )
        return source_record_id


class IntegrationActionWriter:
    """Converts an approved proposal into an authoritative connector command."""

    def __init__(self, gateway: IntegrationGateway, connectors: dict[str, Any]) -> None:
        self.gateway = gateway
        self.connectors = connectors

    def write(self, proposal: ActionProposal, access: AccessContext) -> str:
        requested_system = str(proposal.payload.get("source_system", "")).strip()
        if not requested_system:
            raise ValueError("production actions require payload.source_system")
        connector = self.connectors.get(requested_system.lower()) or next((
            value for value in self.connectors.values()
            if value.source_system.lower() == requested_system.lower()
        ), None)
        if connector is None:
            raise ValueError(f"no write connector is configured for {requested_system}")
        approvals = tuple(item for item in proposal.approvals if item.decision == "approved")
        action = AuthorizedAction(
            proposal.proposal_id, proposal.tenant_id, connector.source_system,
            proposal.operation, proposal.target_id, proposal.payload, proposal.requested_by,
            tuple(item.actor_id for item in approvals), max(item.decided_at for item in approvals),
            proposal.site_id, tuple(item.approval_id for item in approvals),
        )
        requester_context = AccessContext(
            access.tenant_id, proposal.requested_by, access.site_ids,
            access.roles, access.clearances,
        )
        acknowledgement = self.gateway.execute_authorized(
            connector, action, access=requester_context,
        )
        return acknowledgement.source_record_id


class ActionExecutionGateway:
    def __init__(self, control: ActionControlPlane, writer: ActionWriter | None = None) -> None:
        self.control = control
        self.writer = writer

    @property
    def configured(self) -> bool:
        return self.writer is not None

    @property
    def mode(self) -> str:
        if self.writer is None:
            return "fail_closed"
        return "demo_acknowledgement" if isinstance(self.writer, DemoActionWriter) else "authoritative_connector"

    def execute(self, proposal_id: str, access: AccessContext) -> dict[str, Any]:
        proposal = self.control.store.get(access.tenant_id, proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        if proposal.site_id and access.site_ids and proposal.site_id not in access.site_ids:
            raise PermissionError("action is outside the actor's authorized sites")
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError("only approved proposals may be executed")
        if "system_executor" not in access.roles:
            raise PermissionError("system_executor role is required")
        if self.writer is None:
            raise RuntimeError("no authorized write connector is configured")
        source_record_id = self.writer.write(proposal, access)
        updated = self.control.mark_executed(proposal_id, access, source_record_id)
        return {"proposal": updated, "source_record_id": source_record_id}
