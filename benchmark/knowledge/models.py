from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class KnowledgeEvent:
    event_id: str
    occurred_at: datetime
    event_type: str
    source: str
    entity_ids: tuple[str, ...]
    document_id: str
    tenant_id: str = "default"
    site_id: str | None = None
    classification: str = "internal"
    evidence_id: str | None = None
    ingested_at: datetime = field(default_factory=utc_now)
    scenario_id: str | None = None
    summary: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["occurred_at"] = self.occurred_at.isoformat()
        value["ingested_at"] = self.ingested_at.isoformat()
        value["entity_ids"] = list(self.entity_ids)
        return value


@dataclass(frozen=True)
class KnowledgeRule:
    rule_id: str
    version: int
    statement: str
    scope_entity_ids: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    effective_from: datetime = field(default_factory=utc_now)
    effective_until: datetime | None = None
    supersedes_version: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"

    @property
    def key(self) -> str:
        base = f"{self.rule_id}:v{self.version}"
        return base if self.tenant_id == "default" else f"{self.tenant_id}:{base}"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["effective_from"] = self.effective_from.isoformat()
        value["effective_until"] = self.effective_until.isoformat() if self.effective_until else None
        value["scope_entity_ids"] = list(self.scope_entity_ids)
        value["event_types"] = list(self.event_types)
        return value


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    text: str
    metadata: dict[str, Any]
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ContextBundle:
    query: str
    events: tuple[KnowledgeEvent, ...]
    rules: tuple[KnowledgeRule, ...]
    documents: tuple[DocumentRecord, ...]
    previous_event_by_entity: dict[str, str]
    citations: tuple["Citation", ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "events": [event.to_dict() for event in self.events],
            "rules": [rule.to_dict() for rule in self.rules],
            "documents": [
                {
                    "document_id": doc.document_id,
                    "text": doc.text,
                    "metadata": doc.metadata,
                    "payload": doc.payload,
                    "created_at": doc.created_at.isoformat(),
                }
                for doc in self.documents
            ],
            "previous_event_by_entity": self.previous_event_by_entity,
            "citations": [asdict(citation) for citation in self.citations],
        }


@dataclass(frozen=True)
class Citation:
    citation_id: str
    document_id: str
    evidence_id: str | None
    source_uri: str | None
    revision: str | None = None
    section: str | None = None
    page: int | None = None
