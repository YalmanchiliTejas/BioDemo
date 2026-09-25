from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .domain import CaseRecord, EvidenceRecord, HumanTask, OutboxMessage
from .models import DocumentRecord, KnowledgeEvent, KnowledgeRule


class GraphStore(Protocol):
    def upsert_event(self, event: KnowledgeEvent) -> None: ...

    def link_previous(
        self, entity_id: str, event_id: str, previous_event_id: str, tenant_id: str = "default"
    ) -> None: ...

    def rebuild_timeline(self, entity_id: str, tenant_id: str = "default") -> None: ...

    def latest_event(
        self, entity_id: str, before: datetime | None = None, tenant_id: str = "default"
    ) -> KnowledgeEvent | None: ...

    def related_events(
        self, entity_ids: tuple[str, ...], event_type: str | None, before: datetime | None, limit: int,
        tenant_id: str = "default",
    ) -> list[KnowledgeEvent]: ...

    def upsert_rule(self, rule: KnowledgeRule) -> None: ...

    def latest_rule(self, rule_id: str, tenant_id: str = "default") -> KnowledgeRule | None: ...

    def active_rules(
        self, entity_ids: tuple[str, ...], event_type: str | None, at: datetime,
        tenant_id: str = "default",
    ) -> list[KnowledgeRule]: ...

    def upsert_domain_object(
        self, object_id: str, kind: str, tenant_id: str, properties: dict[str, Any]
    ) -> None: ...

    def relate_domain_objects(
        self, from_id: str, to_id: str, relationship: str, tenant_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None: ...


class DocumentStore(Protocol):
    def put(self, document: DocumentRecord) -> None: ...

    def search(
        self, query: str, *, entity_ids: tuple[str, ...] = (), event_ids: tuple[str, ...] = (),
        metadata_filters: dict[str, Any] | None = None, limit: int = 10
    ) -> list[DocumentRecord]: ...


class SemanticIndex(Protocol):
    def index(self, document: DocumentRecord) -> None: ...

    def search(
        self, query: str, *, metadata_filters: dict[str, Any] | None = None, limit: int = 10
    ) -> list[DocumentRecord]: ...


class EvidenceStore(Protocol):
    def put(
        self, content: bytes, *, tenant_id: str, source_system: str, source_record_id: str,
        media_type: str, event_time: datetime, site_id: str | None = None,
        classification: str = "internal", metadata: dict[str, Any] | None = None,
    ) -> EvidenceRecord: ...

    def read(self, evidence_id: str, tenant_id: str) -> bytes: ...


class CaseStore(Protocol):
    def create_case(self, case: CaseRecord) -> None: ...

    def get_case(self, case_id: str, tenant_id: str) -> CaseRecord | None: ...

    def update_case(self, case: CaseRecord, expected_version: int) -> None: ...

    def put_task(self, task: HumanTask) -> None: ...

    def tasks_for_case(self, case_id: str, tenant_id: str) -> list[HumanTask]: ...


class Outbox(Protocol):
    def append(self, message: OutboxMessage) -> None: ...

    def pending(self, limit: int = 100) -> list[OutboxMessage]: ...

    def mark_published(self, message_id: str, at: datetime) -> None: ...
