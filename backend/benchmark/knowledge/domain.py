from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from .models import utc_now


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"


class CaseStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    PENDING_APPROVAL = "pending_approval"
    CLOSED = "closed"


@dataclass(frozen=True)
class AccessContext:
    tenant_id: str
    actor_id: str
    site_ids: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    clearances: tuple[str, ...] = ("internal",)

    def permits(self, metadata: dict[str, Any]) -> bool:
        if metadata.get("tenant_id", "default") != self.tenant_id:
            return False
        site_id = metadata.get("site_id")
        if site_id and self.site_ids and site_id not in self.site_ids:
            return False
        document_sites = set(metadata.get("site_ids") or ())
        if document_sites and self.site_ids and not document_sites.intersection(self.site_ids):
            return False
        return metadata.get("classification", "internal") in self.clearances


@dataclass(frozen=True)
class EntityRef:
    entity_id: str
    entity_type: str
    role: str = "affected"


@dataclass(frozen=True)
class DomainEntity:
    entity_id: str
    tenant_id: str
    entity_type: str
    name: str
    site_id: str | None = None
    classification: str = "internal"
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    tenant_id: str
    source_system: str
    source_record_id: str
    content_sha256: str
    uri: str
    media_type: str
    event_time: datetime
    ingested_at: datetime
    site_id: str | None = None
    classification: str = "internal"
    size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    tenant_id: str
    source_system: str
    source_record_id: str
    event_type: str
    occurred_at: datetime
    ingested_at: datetime
    evidence_id: str
    entities: tuple[EntityRef, ...]
    site_id: str | None = None
    classification: str = "internal"
    summary: str = ""
    correlation_id: str | None = None
    causation_id: str | None = None
    schema_version: int = 1
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlledDocument:
    document_id: str
    tenant_id: str
    document_type: str
    title: str
    owner_id: str
    site_ids: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    classification: str = "internal"


@dataclass(frozen=True)
class DocumentRevision:
    revision_id: str
    document_id: str
    revision: str
    status: DocumentStatus
    evidence_id: str
    effective_from: datetime
    approved_by: tuple[str, ...] = ()
    effective_until: datetime | None = None
    supersedes_revision_id: str | None = None
    sections: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class DocumentSection:
    section_id: str
    title: str
    text: str
    page: int | None = None


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    actor_id: str
    role: str
    decision: str
    signed_at: datetime
    meaning: str


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    tenant_id: str
    case_id: str
    statement: str
    rationale: str
    outcome: str
    decided_at: datetime
    decided_by: str
    site_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    procedure_revision_ids: tuple[str, ...] = ()
    affected_entities: tuple[EntityRef, ...] = ()
    approvals: tuple[ApprovalRecord, ...] = ()
    classification: str = "internal"


@dataclass
class CaseRecord:
    case_id: str
    tenant_id: str
    case_type: str
    title: str
    owner_id: str
    site_id: str | None = None
    status: CaseStatus = CaseStatus.OPEN
    entity_refs: tuple[EntityRef, ...] = ()
    hypothesis: str | None = None
    opened_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1


@dataclass
class HumanTask:
    task_id: str
    case_id: str
    tenant_id: str
    task_type: str
    title: str
    assigned_role: str
    status: str = "open"
    assigned_to: str | None = None
    due_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None


@dataclass(frozen=True)
class OutboxMessage:
    message_id: str
    tenant_id: str
    topic: str
    aggregate_id: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)
    published_at: datetime | None = None


def serialize(value: Any) -> dict[str, Any]:
    result = asdict(value)
    for key, item in tuple(result.items()):
        if isinstance(item, datetime):
            result[key] = item.isoformat()
        elif isinstance(item, StrEnum):
            result[key] = item.value
    return result
