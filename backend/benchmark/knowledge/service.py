from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from .domain import AccessContext, CanonicalEvent
from .models import Citation, ContextBundle, DocumentRecord, KnowledgeEvent, KnowledgeRule
from .ports import DocumentStore, GraphStore, SemanticIndex


class KnowledgeBase:
    """Coordinates durable event history, versioned rules, and source documents."""

    def __init__(
        self, graph: GraphStore, documents: DocumentStore, semantic: SemanticIndex | None = None
    ) -> None:
        self.graph = graph
        self.documents = documents
        self.semantic = semantic

    def put_document(self, document: DocumentRecord) -> None:
        self.documents.put(document)
        if self.semantic is not None:
            self.semantic.index(document)

    def ingest_event(self, record: dict[str, Any], *, source: str = "benchmark") -> KnowledgeEvent:
        occurred_at = _parse_datetime(record["timestamp"])
        event_id = record.get("event_id") or _stable_id(record)
        entity_ids = tuple(sorted(_extract_entity_ids(record)))
        document_id = f"event:{event_id}"
        event = KnowledgeEvent(
            event_id=event_id,
            occurred_at=occurred_at,
            event_type=str(record.get("event_failure", "unknown")),
            source=source,
            entity_ids=entity_ids,
            document_id=document_id,
            scenario_id=record.get("scenario_id"),
            summary=" | ".join(
                str(value) for value in (
                    record.get("event_failure"), record.get("actor_agent_action"), record.get("decision")
                ) if value
            ),
            attributes={
                "approval_required": bool(record.get("approval_required", False)),
                "tool_used": record.get("tool_used"),
            },
        )

        self.put_document(DocumentRecord(
            document_id=document_id,
            text=event.summary,
            metadata={
                "kind": "event",
                "event_id": event_id,
                "event_type": event.event_type,
                "entity_ids": list(entity_ids),
                "occurred_at": occurred_at.isoformat(),
                "tenant_id": "default", "site_id": None, "classification": "internal",
            },
            payload=record,
            created_at=occurred_at,
        ))
        self.graph.upsert_event(event)
        # Rebuilding the affected entity timelines also handles late-arriving events:
        # both the inserted event and its successor receive the correct predecessor.
        for entity_id in entity_ids:
            self.graph.rebuild_timeline(entity_id)
        return event

    def ingest_canonical(
        self, envelope: CanonicalEvent, payload: dict[str, Any], *, evidence_uri: str | None = None
    ) -> KnowledgeEvent:
        event = KnowledgeEvent(
            event_id=envelope.event_id, occurred_at=envelope.occurred_at,
            event_type=envelope.event_type, source=envelope.source_system,
            entity_ids=tuple(ref.entity_id for ref in envelope.entities),
            document_id=f"{envelope.tenant_id}:event:{envelope.event_id}", tenant_id=envelope.tenant_id,
            site_id=envelope.site_id, classification=envelope.classification,
            evidence_id=envelope.evidence_id, ingested_at=envelope.ingested_at,
            scenario_id=envelope.attributes.get("scenario_id"), summary=envelope.summary,
            attributes={**envelope.attributes, "source_record_id": envelope.source_record_id,
                        "schema_version": envelope.schema_version},
        )
        self.put_document(DocumentRecord(
            document_id=event.document_id, text=event.summary,
            metadata={
                "kind": "event", "event_id": event.event_id, "event_type": event.event_type,
                "entity_ids": list(event.entity_ids), "occurred_at": event.occurred_at.isoformat(),
                "tenant_id": event.tenant_id, "site_id": event.site_id,
                "classification": event.classification, "evidence_id": event.evidence_id,
                "source_uri": evidence_uri,
            }, payload=payload, created_at=event.occurred_at,
        ))
        self.graph.upsert_event(event)
        for entity_id in event.entity_ids:
            self.graph.rebuild_timeline(entity_id, event.tenant_id)
        return event

    def ingest_events(self, records: Iterable[dict[str, Any]], *, source: str = "benchmark") -> list[KnowledgeEvent]:
        return [self.ingest_event(record, source=source) for record in records]

    def update_rule(self, rule: KnowledgeRule) -> None:
        if rule.version < 1:
            raise ValueError("rule version must be at least 1")
        if rule.effective_from.tzinfo is None or (
            rule.effective_until is not None and rule.effective_until.tzinfo is None
        ):
            raise ValueError("rule effective dates must include a timezone")
        if rule.effective_until is not None and rule.effective_until <= rule.effective_from:
            raise ValueError("rule effective_until must be after effective_from")
        existing = self.graph.latest_rule(rule.rule_id, rule.tenant_id)
        same_version = existing is not None and existing.version == rule.version
        if same_version:
            if existing != rule:
                raise ValueError("published rule versions are immutable")
        else:
            expected_version = 1 if existing is None else existing.version + 1
            if rule.version != expected_version:
                raise ValueError(f"next rule version must be {expected_version}")
            if existing is not None and rule.supersedes_version not in {None, existing.version}:
                raise ValueError("a rule update must supersede the immediately preceding version")
        self.graph.upsert_rule(rule)
        self.put_document(DocumentRecord(
            document_id=f"rule:{rule.key}",
            text=rule.statement,
            metadata={
                "kind": "rule",
                "rule_id": rule.rule_id,
                "version": rule.version,
                "entity_ids": list(rule.scope_entity_ids),
                "event_types": list(rule.event_types),
                "tenant_id": rule.tenant_id, "site_id": None, "classification": "internal",
            },
            payload=rule.to_dict(),
            created_at=rule.effective_from,
        ))

    def context(
        self,
        query: str,
        *,
        entity_ids: Iterable[str] = (),
        event_type: str | None = None,
        at: datetime | None = None,
        limit: int = 10,
        access: AccessContext | None = None,
    ) -> ContextBundle:
        when = at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            raise ValueError("context time must include a timezone")
        entities = tuple(sorted(set(entity_ids)))
        tenant_id = access.tenant_id if access else "default"
        events = self.graph.related_events(entities, event_type, when, limit, tenant_id)
        if access:
            events = [event for event in events if access.permits({
                "tenant_id": event.tenant_id, "site_id": event.site_id,
                "classification": event.classification,
            })]
        rules = self.graph.active_rules(entities, event_type, when, tenant_id)
        metadata_filters = {"tenant_id": tenant_id}
        documents = self.documents.search(
            query,
            entity_ids=entities,
            event_ids=tuple(event.event_id for event in events),
            metadata_filters=metadata_filters,
            limit=limit,
        )
        if self.semantic is not None and query.strip():
            semantic_documents = self.semantic.search(query, metadata_filters=metadata_filters, limit=limit)
            event_ids = {event.event_id for event in events}
            semantic_documents = [document for document in semantic_documents
                                  if not entities
                                  or set(document.metadata.get("entity_ids", ())).intersection(entities)
                                  or document.metadata.get("event_id") in event_ids]
            combined = {document.document_id: document for document in documents}
            for document in semantic_documents:
                combined.setdefault(document.document_id, document)
            documents = list(combined.values())[:limit]
        if access:
            documents = [document for document in documents if access.permits(document.metadata)]
        documents = _effective_documents(documents, when)
        previous = {
            entity_id: latest.event_id
            for entity_id in entities
            if (latest := self.graph.latest_event(entity_id, before=when, tenant_id=tenant_id)) is not None
        }
        citations = tuple(citation for document in documents for citation in _citations(document))
        return ContextBundle(query, tuple(events), tuple(rules), tuple(documents), previous, citations)


def _parse_datetime(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _stable_id(record: dict[str, Any]) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]


def _extract_entity_ids(record: dict[str, Any]) -> set[str]:
    entities: set[str] = set()
    state = record.get("plant_state") or {}
    for collection in ("batches", "equipment", "materials", "active_batches"):
        values = state.get(collection, {})
        if isinstance(values, dict):
            entities.update(str(key) for key in values)
    entities.update(str(value) for value in state.get("unavailable_assets", []) if value)
    scenario_id = record.get("scenario_id")
    if scenario_id:
        entities.add(str(scenario_id))
    for value in record.get("information_available") or []:
        if isinstance(value, str):
            entities.update(_identifier_tokens(value))
    return entities


def _identifier_tokens(value: str) -> set[str]:
    tokens = value.replace(":", " ").replace("=", " ").replace(",", " ").split()
    return {token for token in tokens if "-" in token and token.replace("-", "").isalnum()}


def _effective_documents(documents: list[DocumentRecord], at: datetime) -> list[DocumentRecord]:
    ordinary: list[DocumentRecord] = []
    controlled: dict[str, list[DocumentRecord]] = {}
    for document in documents:
        metadata = document.metadata
        if metadata.get("kind") != "controlled_document":
            ordinary.append(document)
            continue
        if metadata.get("status") != "approved":
            continue
        effective_from = _parse_datetime(metadata["effective_from"])
        effective_until = _parse_datetime(metadata["effective_until"]) if metadata.get("effective_until") else None
        if effective_from > at or (effective_until is not None and at >= effective_until):
            continue
        document_id = metadata["document_id"]
        current = controlled.get(document_id, [])
        if not current or _parse_datetime(current[0].metadata["effective_from"]) < effective_from:
            controlled[document_id] = [document]
        elif current[0].metadata.get("revision_id") == metadata.get("revision_id"):
            current.append(document)
    return ordinary + [document for revisions in controlled.values() for document in revisions]


def _citations(document: DocumentRecord) -> list[Citation]:
    metadata = document.metadata
    evidence_ids = list(metadata.get("evidence_ids") or ())
    if metadata.get("evidence_id"):
        evidence_ids.insert(0, metadata["evidence_id"])
    if not evidence_ids:
        evidence_ids.append(None)
    return [Citation(
        citation_id=f"cite:{document.document_id}:{index}", document_id=document.document_id,
        evidence_id=evidence_id, source_uri=metadata.get("source_uri"),
        revision=metadata.get("revision"), section=metadata.get("section"),
        page=metadata.get("page"),
    ) for index, evidence_id in enumerate(evidence_ids)]
