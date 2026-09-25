from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol

from benchmark.knowledge.domain import AccessContext

from .models import ActionProposal, ApprovalDecision, AuditEntry, ProposalStatus, RiskLevel


class ActionStore(Protocol):
    def put(self, proposal: ActionProposal) -> None: ...
    def get(self, tenant_id: str, proposal_id: str) -> ActionProposal | None: ...
    def list(self, tenant_id: str) -> list[ActionProposal]: ...
    def append_audit(self, entry: AuditEntry) -> None: ...
    def audit(self, tenant_id: str, limit: int = 200) -> list[AuditEntry]: ...


class InMemoryActionStore:
    def __init__(self) -> None:
        self.proposals: dict[tuple[str, str], ActionProposal] = {}
        self.audit_entries: list[AuditEntry] = []

    def put(self, proposal: ActionProposal) -> None:
        self.proposals[(proposal.tenant_id, proposal.proposal_id)] = proposal

    def get(self, tenant_id: str, proposal_id: str) -> ActionProposal | None:
        return self.proposals.get((tenant_id, proposal_id))

    def list(self, tenant_id: str) -> list[ActionProposal]:
        return sorted(
            (proposal for (tenant, _), proposal in self.proposals.items() if tenant == tenant_id),
            key=lambda proposal: proposal.updated_at, reverse=True,
        )

    def append_audit(self, entry: AuditEntry) -> None:
        self.audit_entries.append(entry)

    def audit(self, tenant_id: str, limit: int = 200) -> list[AuditEntry]:
        return [entry for entry in reversed(self.audit_entries) if entry.tenant_id == tenant_id][:limit]


class RiskPolicyEngine:
    """Deterministic policy boundary; agents may propose but cannot override it."""

    critical_operations = {"release_batch", "reject_batch", "invalidate_result"}
    high_operations = {"close_deviation", "approve_capa", "change_specification", "quarantine_lot"}
    medium_operations = {"reschedule_batch", "create_work_order", "request_retest", "place_hold"}

    def evaluate(self, operation: str) -> tuple[RiskLevel, tuple[str, ...]]:
        if operation in self.critical_operations:
            return RiskLevel.CRITICAL, ("qa", "sponsor_qa")
        if operation in self.high_operations:
            return RiskLevel.HIGH, ("qa",)
        if operation in self.medium_operations:
            return RiskLevel.MEDIUM, ("supervisor",)
        return RiskLevel.LOW, ("operator",)


class ActionControlPlane:
    def __init__(self, store: ActionStore, policy: RiskPolicyEngine | None = None) -> None:
        self.store = store
        self.policy = policy or RiskPolicyEngine()

    def propose(self, proposal: ActionProposal, access: AccessContext) -> ActionProposal:
        if proposal.tenant_id != access.tenant_id or proposal.requested_by != access.actor_id:
            raise PermissionError("proposal identity does not match authenticated actor")
        if self.store.get(proposal.tenant_id, proposal.proposal_id) is not None:
            raise ValueError("proposal already exists")
        risk, roles = self.policy.evaluate(proposal.operation)
        now = datetime.now(timezone.utc)
        evaluated = replace(
            proposal, risk=risk, required_roles=roles, status=ProposalStatus.PENDING,
            approvals=(), created_at=now, updated_at=now,
        )
        self.store.put(evaluated)
        self._audit(evaluated.tenant_id, access.actor_id, "proposed", evaluated, {
            "risk": risk.value, "required_roles": list(roles),
        })
        return evaluated

    def decide(
        self, proposal_id: str, decision: ApprovalDecision, access: AccessContext,
    ) -> ActionProposal:
        proposal = self._required(access.tenant_id, proposal_id)
        if proposal.status != ProposalStatus.PENDING:
            raise ValueError("only pending proposals can be decided")
        if decision.actor_id != access.actor_id or decision.role not in access.roles:
            raise PermissionError("approval identity or role does not match authenticated actor")
        if decision.actor_id == proposal.requested_by:
            raise PermissionError("requesters cannot approve their own actions")
        if decision.role not in proposal.required_roles:
            raise PermissionError("actor role is not required by this policy")
        if decision.decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        if any(item.role == decision.role for item in proposal.approvals):
            raise ValueError("that approval role has already decided")
        approvals = (*proposal.approvals, decision)
        approved_roles = {item.role for item in approvals if item.decision == "approved"}
        status = ProposalStatus.REJECTED if decision.decision == "rejected" else (
            ProposalStatus.APPROVED
            if set(proposal.required_roles).issubset(approved_roles)
            else ProposalStatus.PENDING
        )
        updated = replace(proposal, approvals=approvals, status=status, updated_at=datetime.now(timezone.utc))
        self.store.put(updated)
        self._audit(updated.tenant_id, access.actor_id, decision.decision, updated, {
            "role": decision.role, "meaning": decision.meaning, "comment": decision.comment,
        })
        return updated

    def mark_executed(self, proposal_id: str, access: AccessContext, source_record_id: str) -> ActionProposal:
        proposal = self._required(access.tenant_id, proposal_id)
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError("only approved proposals may be marked executed")
        updated = replace(proposal, status=ProposalStatus.EXECUTED, updated_at=datetime.now(timezone.utc))
        self.store.put(updated)
        self._audit(updated.tenant_id, access.actor_id, "executed", updated, {
            "source_record_id": source_record_id,
        })
        return updated

    def _required(self, tenant_id: str, proposal_id: str) -> ActionProposal:
        proposal = self.store.get(tenant_id, proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        return proposal

    def _audit(
        self, tenant_id: str, actor_id: str, action: str,
        proposal: ActionProposal, details: dict,
    ) -> None:
        occurred_at = datetime.now(timezone.utc)
        identity = json.dumps(
            [tenant_id, actor_id, action, proposal.proposal_id, occurred_at.isoformat()],
            separators=(",", ":"),
        )
        self.store.append_audit(AuditEntry(
            hashlib.sha256(identity.encode()).hexdigest()[:24], tenant_id, actor_id,
            action, "action_proposal", proposal.proposal_id, occurred_at, details,
        ))
