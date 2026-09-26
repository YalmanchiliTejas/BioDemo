from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .domain import (
    AccessContext, CanonicalEvent, CaseRecord, ControlledDocument, DecisionRecord, DomainEntity,
    DocumentRevision, DocumentSection, DocumentStatus, HumanTask, OutboxMessage, serialize,
)
from .models import DocumentRecord, KnowledgeEvent
from .normalizer import EventNormalizer
from .ports import CaseStore, EvidenceStore, GraphStore, Outbox
from .service import KnowledgeBase, _parse_datetime


class DigitalThread:
    """Application service joining evidence, memory, graph, cases, and the outbox."""

    def __init__(
        self, knowledge: KnowledgeBase, evidence: EvidenceStore, cases: CaseStore,
        outbox: Outbox, normalizer: EventNormalizer | None = None, extractor: Any | None = None,
    ) -> None:
        self.knowledge = knowledge
        self.evidence = evidence
        self.cases = cases
        self.outbox = outbox
        self.normalizer = normalizer or EventNormalizer()
        self.extractor = extractor

    @property
    def graph(self) -> GraphStore:
        return self.knowledge.graph

    def ingest_raw_event(
        self, record: dict[str, Any], *, access: AccessContext, source_system: str,
        site_id: str | None = None, classification: str = "internal",
    ) -> KnowledgeEvent:
        _require_clearance(access, classification)
        occurred_at = _parse_datetime(record["timestamp"])
        source_record_id = str(record.get("source_record_id") or _stable_source_id(record))
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode()
        evidence = self.evidence.put(
            raw, tenant_id=access.tenant_id, source_system=source_system,
            source_record_id=source_record_id, media_type="application/json",
            event_time=occurred_at, site_id=site_id, classification=classification,
            metadata={"schema": "canonical-event-source/v1"},
        )
        envelope = self.normalizer.normalize(
            {**record, "source_record_id": source_record_id}, evidence,
            tenant_id=access.tenant_id, source_system=source_system,
            site_id=site_id, classification=classification,
        )
        event = self.knowledge.ingest_canonical(envelope, record, evidence_uri=evidence.uri)
        self.graph.upsert_domain_object(evidence.evidence_id, "evidence", access.tenant_id, serialize(evidence))
        self.graph.upsert_domain_object(event.event_id, "event", access.tenant_id, event.to_dict())
        self.graph.relate_domain_objects(event.event_id, evidence.evidence_id, "SUPPORTED_BY", access.tenant_id)
        self._emit("knowledge.event.normalized", event.event_id, access.tenant_id, _canonical_payload(envelope))
        return event

    def register_entity(self, entity: DomainEntity, *, access: AccessContext) -> None:
        """Register a sponsor, site, product, process, batch, lot, asset, sample, or quality object."""
        _same_tenant(access, entity.tenant_id)
        _require_clearance(access, entity.classification)
        self.graph.upsert_domain_object(
            entity.entity_id, entity.entity_type, entity.tenant_id, serialize(entity)
        )
        self._emit("knowledge.entity.registered", entity.entity_id, entity.tenant_id, serialize(entity))

    def relate_entities(
        self, source: DomainEntity, target: DomainEntity, relationship: str,
        *, access: AccessContext, properties: dict[str, Any] | None = None,
    ) -> None:
        _same_tenant(access, source.tenant_id)
        if source.tenant_id != target.tenant_id:
            raise PermissionError("cross-tenant relationships are not allowed")
        self.register_entity(source, access=access)
        self.register_entity(target, access=access)
        self.graph.relate_domain_objects(
            source.entity_id, target.entity_id, relationship, source.tenant_id, properties,
        )

    def publish_document(
        self, document: ControlledDocument, revision: DocumentRevision,
        *, extracted_text: str, access: AccessContext, source_uri: str | None = None,
        sections: tuple[DocumentSection, ...] = (),
    ) -> None:
        _same_tenant(access, document.tenant_id)
        if revision.document_id != document.document_id:
            raise ValueError("revision does not belong to the supplied document")
        if revision.status == DocumentStatus.APPROVED and not revision.approved_by:
            raise ValueError("approved revisions require at least one approver")
        if revision.effective_until and revision.effective_until <= revision.effective_from:
            raise ValueError("revision effective_until must be after effective_from")
        existing = self.knowledge.documents.search(
            "", metadata_filters={"tenant_id": document.tenant_id,
                                  "revision_id": revision.revision_id}, limit=1,
        )
        payload = {"document": serialize(document), "revision": serialize(revision)}
        if existing and existing[0].payload != payload:
            raise ValueError("published document revisions are immutable")
        if revision.supersedes_revision_id:
            predecessor = self.knowledge.documents.search(
                "", metadata_filters={"tenant_id": document.tenant_id,
                                      "revision_id": revision.supersedes_revision_id}, limit=1,
            )
            if not predecessor:
                raise ValueError("superseded revision does not exist")
            if predecessor[0].metadata.get("document_id") != document.document_id:
                raise ValueError("a revision can only supersede a revision of the same document")
        base_metadata = {
                "kind": "controlled_document", "tenant_id": document.tenant_id,
                "site_id": document.site_ids[0] if len(document.site_ids) == 1 else None,
                "site_ids": list(document.site_ids), "classification": document.classification,
                "document_id": document.document_id, "revision_id": revision.revision_id,
                "revision": revision.revision, "status": revision.status.value,
                "evidence_id": revision.evidence_id,
                "source_uri": source_uri,
                "entity_ids": list(document.product_ids),
                "effective_from": revision.effective_from.isoformat(),
                "effective_until": revision.effective_until.isoformat() if revision.effective_until else None,
            }
        records = [DocumentRecord(
            document_id=f"{document.tenant_id}:revision:{revision.revision_id}:{section.section_id}",
            text=section.text,
            metadata={**base_metadata, "section": section.title, "section_id": section.section_id,
                      "page": section.page},
            payload=payload, created_at=revision.created_at,
        ) for section in sections] if sections else [DocumentRecord(
            document_id=f"{document.tenant_id}:revision:{revision.revision_id}", text=extracted_text,
            metadata=base_metadata, payload=payload, created_at=revision.created_at,
        )]
        for record in records:
            self.knowledge.put_document(record)
        self.graph.upsert_domain_object(document.document_id, "controlled_document", document.tenant_id, serialize(document))
        self.graph.upsert_domain_object(revision.revision_id, "document_revision", document.tenant_id, serialize(revision))
        self.graph.relate_domain_objects(revision.revision_id, document.document_id, "REVISION_OF", document.tenant_id)
        self.graph.upsert_domain_object(
            revision.evidence_id, "evidence", document.tenant_id, {"evidence_id": revision.evidence_id}
        )
        self.graph.relate_domain_objects(
            revision.revision_id, revision.evidence_id, "SUPPORTED_BY", document.tenant_id
        )
        if revision.supersedes_revision_id:
            self.graph.relate_domain_objects(
                revision.revision_id, revision.supersedes_revision_id, "SUPERSEDES", document.tenant_id
            )
        for entity_id in (*document.site_ids, *document.product_ids):
            self.graph.upsert_domain_object(entity_id, "scope", document.tenant_id, {"entity_id": entity_id})
            self.graph.relate_domain_objects(revision.revision_id, entity_id, "APPLIES_TO", document.tenant_id)
        self._emit("knowledge.document.published", revision.revision_id, document.tenant_id, payload)

    def ingest_controlled_document(
        self, document: ControlledDocument, revision: DocumentRevision, original_content: bytes,
        *, extracted_text: str | None = None, access: AccessContext, source_system: str = "DMS",
        media_type: str = "application/pdf", sections: tuple[DocumentSection, ...] = (),
    ) -> DocumentRevision:
        """Persist original bytes first, then publish their controlled revision projection."""
        _same_tenant(access, document.tenant_id)
        evidence = self.evidence.put(
            original_content, tenant_id=document.tenant_id, source_system=source_system,
            source_record_id=revision.revision_id, media_type=media_type,
            event_time=revision.created_at,
            site_id=document.site_ids[0] if len(document.site_ids) == 1 else None,
            classification=document.classification,
            metadata={"document_id": document.document_id, "revision": revision.revision},
        )
        if revision.evidence_id and revision.evidence_id != evidence.evidence_id:
            raise ValueError("revision evidence_id does not match the original content hash")
        materialized = replace(revision, evidence_id=evidence.evidence_id)
        if extracted_text is None:
            if self.extractor is None:
                raise ValueError("extracted_text or a document extractor is required")
            extracted_text, extracted_sections = self.extractor.extract(original_content, media_type)
            if not sections:
                sections = extracted_sections
        self.graph.upsert_domain_object(
            evidence.evidence_id, "evidence", document.tenant_id, serialize(evidence)
        )
        self.publish_document(
            document, materialized, extracted_text=extracted_text, access=access,
            source_uri=evidence.uri, sections=sections,
        )
        return materialized

    def open_case(self, case: CaseRecord, *, access: AccessContext) -> None:
        _same_tenant(access, case.tenant_id)
        self.cases.create_case(case)
        self.graph.upsert_domain_object(case.case_id, "case", case.tenant_id, serialize(case))
        for ref in case.entity_refs:
            self.graph.upsert_domain_object(ref.entity_id, ref.entity_type, case.tenant_id, serialize(ref))
            self.graph.relate_domain_objects(case.case_id, ref.entity_id, "CONTAINS", case.tenant_id)
        self._emit("case.opened", case.case_id, case.tenant_id, serialize(case))

    def update_case(self, case: CaseRecord, *, expected_version: int, access: AccessContext) -> None:
        _same_tenant(access, case.tenant_id)
        if case.version != expected_version + 1:
            raise ValueError("case version must increment by exactly one")
        case.updated_at = datetime.now(timezone.utc)
        self.cases.update_case(case, expected_version)
        self.graph.upsert_domain_object(case.case_id, "case", case.tenant_id, serialize(case))
        self._emit("case.updated", case.case_id, case.tenant_id, serialize(case))

    def assign_task(self, task: HumanTask, *, access: AccessContext) -> None:
        _same_tenant(access, task.tenant_id)
        self.cases.put_task(task)
        self.graph.upsert_domain_object(task.task_id, "human_task", task.tenant_id, serialize(task))
        self.graph.relate_domain_objects(task.case_id, task.task_id, "CONTAINS", task.tenant_id)
        self._emit("human_task.assigned", task.task_id, task.tenant_id, serialize(task))

    def complete_task(self, task_id: str, *, access: AccessContext) -> HumanTask:
        task = next(
            (item for item in self.cases.list_tasks(access.tenant_id) if item.task_id == task_id),
            None,
        )
        if task is None:
            raise KeyError(task_id)
        if task.status != "open":
            raise ValueError("only open tasks can be completed")
        if task.assigned_to and task.assigned_to != access.actor_id:
            raise PermissionError("task is assigned to another actor")
        if not task.assigned_to and task.assigned_role.lower() not in {
            role.lower() for role in access.roles
        }:
            raise PermissionError("actor does not hold the assigned task role")
        completed = replace(
            task, status="completed", assigned_to=task.assigned_to or access.actor_id,
            completed_at=datetime.now(timezone.utc),
        )
        self.cases.put_task(completed)
        self.graph.upsert_domain_object(
            completed.task_id, "human_task", completed.tenant_id, serialize(completed)
        )
        self._emit("human_task.completed", completed.task_id, completed.tenant_id, serialize(completed))
        return completed

    def record_decision(self, decision: DecisionRecord, *, access: AccessContext) -> None:
        _same_tenant(access, decision.tenant_id)
        _require_clearance(access, decision.classification)
        if self.cases.get_case(decision.case_id, decision.tenant_id) is None:
            raise KeyError(f"unknown case: {decision.case_id}")
        if not decision.evidence_ids:
            raise ValueError("decisions must cite at least one evidence record")
        if any(approval.decision not in {"approved", "rejected"} for approval in decision.approvals):
            raise ValueError("approval decisions must be approved or rejected")
        payload = serialize(decision)
        self.knowledge.put_document(DocumentRecord(
            document_id=f"{decision.tenant_id}:decision:{decision.decision_id}",
            text=f"{decision.statement}\n{decision.rationale}\n{decision.outcome}",
            metadata={
                "kind": "decision", "tenant_id": decision.tenant_id,
                "site_id": decision.site_id, "classification": decision.classification,
                "case_id": decision.case_id, "evidence_ids": list(decision.evidence_ids),
                "entity_ids": [ref.entity_id for ref in decision.affected_entities],
            }, payload=payload, created_at=decision.decided_at,
        ))
        self.graph.upsert_domain_object(decision.decision_id, "decision", decision.tenant_id, payload)
        self.graph.relate_domain_objects(decision.case_id, decision.decision_id, "CONTAINS", decision.tenant_id)
        for evidence_id in decision.evidence_ids:
            self.graph.relate_domain_objects(decision.decision_id, evidence_id, "BASED_ON", decision.tenant_id)
        for revision_id in decision.procedure_revision_ids:
            self.graph.relate_domain_objects(decision.decision_id, revision_id, "FOLLOWED_PROCEDURE", decision.tenant_id)
        for ref in decision.affected_entities:
            self.graph.upsert_domain_object(ref.entity_id, ref.entity_type, decision.tenant_id, serialize(ref))
            self.graph.relate_domain_objects(decision.decision_id, ref.entity_id, "AFFECTED", decision.tenant_id)
        for approval in decision.approvals:
            self.graph.upsert_domain_object(approval.actor_id, "person", decision.tenant_id, {"actor_id": approval.actor_id})
            self.graph.relate_domain_objects(
                decision.decision_id, approval.actor_id, "APPROVED_BY", decision.tenant_id,
                serialize(approval),
            )
        self._emit("decision.recorded", decision.decision_id, decision.tenant_id, payload)

    def _emit(self, topic: str, aggregate_id: str, tenant_id: str, payload: dict[str, Any]) -> None:
        identity = json.dumps([tenant_id, topic, aggregate_id, payload], sort_keys=True, default=str)
        message_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
        self.outbox.append(OutboxMessage(message_id, tenant_id, topic, aggregate_id, payload))


def _same_tenant(access: AccessContext, tenant_id: str) -> None:
    if access.tenant_id != tenant_id:
        raise PermissionError("cross-tenant access is not allowed")


def _require_clearance(access: AccessContext, classification: str) -> None:
    if classification not in access.clearances:
        raise PermissionError(f"actor lacks {classification!r} clearance")


def _stable_source_id(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _canonical_payload(event: CanonicalEvent) -> dict[str, Any]:
    return serialize(event)
