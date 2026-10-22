from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from benchmark.knowledge.models import utc_now


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProposalStatus(StrEnum):
    PENDING = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    actor_id: str
    role: str
    decision: str
    meaning: str
    decided_at: datetime = field(default_factory=utc_now)
    comment: str = ""


@dataclass
class ActionProposal:
    proposal_id: str
    tenant_id: str
    case_id: str
    operation: str
    target_id: str
    payload: dict[str, Any]
    requested_by: str
    reason: str
    site_id: str | None = None
    risk: RiskLevel = RiskLevel.LOW
    required_roles: tuple[str, ...] = ()
    status: ProposalStatus = ProposalStatus.PENDING
    approvals: tuple[ApprovalDecision, ...] = ()
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AuditEntry:
    audit_id: str
    tenant_id: str
    actor_id: str
    action: str
    object_type: str
    object_id: str
    occurred_at: datetime
    details: dict[str, Any] = field(default_factory=dict)
