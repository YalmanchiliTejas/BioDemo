from __future__ import annotations

from datetime import datetime

from .domain import CaseRecord, HumanTask, OutboxMessage
from .models import DocumentRecord, KnowledgeEvent, KnowledgeRule


class InMemoryGraphStore:
    """Reference adapter used by tests and local development."""

    def __init__(self) -> None:
        self.events: dict[str, KnowledgeEvent] = {}
        self.rules: dict[str, KnowledgeRule] = {}
        self.previous: dict[tuple[str, str], str] = {}
        self.domain_objects: dict[tuple[str, str], dict] = {}
        self.domain_relationships: set[tuple[str, str, str, str]] = set()

    def upsert_event(self, event: KnowledgeEvent) -> None:
        key = event.event_id if event.tenant_id == "default" else f"{event.tenant_id}:{event.event_id}"
        self.events[key] = event

    def link_previous(
        self, entity_id: str, event_id: str, previous_event_id: str, tenant_id: str = "default"
    ) -> None:
        key_entity = entity_id if tenant_id == "default" else f"{tenant_id}:{entity_id}"
        self.previous[(key_entity, event_id)] = previous_event_id

    def rebuild_timeline(self, entity_id: str, tenant_id: str = "default") -> None:
        ordered = sorted(
            (event for event in self.events.values()
             if event.tenant_id == tenant_id and entity_id in event.entity_ids),
            key=lambda event: (event.occurred_at, event.event_id),
        )
        key_entity = entity_id if tenant_id == "default" else f"{tenant_id}:{entity_id}"
        for key in [key for key in self.previous if key[0] == key_entity]:
            del self.previous[key]
        for previous, current in zip(ordered, ordered[1:]):
            self.link_previous(entity_id, current.event_id, previous.event_id, tenant_id)

    def latest_event(
        self, entity_id: str, before: datetime | None = None, tenant_id: str = "default"
    ) -> KnowledgeEvent | None:
        matches = [
            event for event in self.events.values()
            if event.tenant_id == tenant_id and entity_id in event.entity_ids
            and (before is None or event.occurred_at <= before)
        ]
        return max(matches, key=lambda event: (event.occurred_at, event.event_id), default=None)

    def related_events(
        self, entity_ids: tuple[str, ...], event_type: str | None, before: datetime | None, limit: int,
        tenant_id: str = "default",
    ) -> list[KnowledgeEvent]:
        entity_set = set(entity_ids)
        matches = [
            event for event in self.events.values()
            if event.tenant_id == tenant_id
            and (not entity_set or entity_set.intersection(event.entity_ids))
            and (event_type is None or event.event_type == event_type)
            and (before is None or event.occurred_at <= before)
        ]
        matches.sort(key=lambda event: (event.occurred_at, event.event_id), reverse=True)
        return matches[:limit]

    def upsert_rule(self, rule: KnowledgeRule) -> None:
        self.rules[rule.key] = rule

    def latest_rule(self, rule_id: str, tenant_id: str = "default") -> KnowledgeRule | None:
        matches = [rule for rule in self.rules.values()
                   if rule.rule_id == rule_id and rule.tenant_id == tenant_id]
        return max(matches, key=lambda rule: rule.version, default=None)

    def active_rules(
        self, entity_ids: tuple[str, ...], event_type: str | None, at: datetime,
        tenant_id: str = "default",
    ) -> list[KnowledgeRule]:
        entities = set(entity_ids)
        candidates = [
            rule for rule in self.rules.values()
            if rule.tenant_id == tenant_id
            and rule.effective_from <= at
            and (rule.effective_until is None or at < rule.effective_until)
            and (not rule.scope_entity_ids or entities.intersection(rule.scope_entity_ids))
            and (not rule.event_types or event_type is None or event_type in rule.event_types)
        ]
        latest: dict[str, KnowledgeRule] = {}
        for rule in candidates:
            if rule.rule_id not in latest or rule.version > latest[rule.rule_id].version:
                latest[rule.rule_id] = rule
        return sorted(latest.values(), key=lambda rule: (rule.rule_id, -rule.version))

    def upsert_domain_object(self, object_id: str, kind: str, tenant_id: str, properties: dict) -> None:
        self.domain_objects[(tenant_id, object_id)] = {"kind": kind, **properties}

    def relate_domain_objects(
        self, from_id: str, to_id: str, relationship: str, tenant_id: str, properties: dict | None = None
    ) -> None:
        if (tenant_id, from_id) not in self.domain_objects or (tenant_id, to_id) not in self.domain_objects:
            raise KeyError("both domain objects must exist before they can be related")
        self.domain_relationships.add((tenant_id, from_id, relationship, to_id))


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self.documents: dict[str, DocumentRecord] = {}

    def put(self, document: DocumentRecord) -> None:
        self.documents[document.document_id] = document

    def search(
        self, query: str, *, entity_ids: tuple[str, ...] = (), event_ids: tuple[str, ...] = (),
        metadata_filters: dict | None = None, limit: int = 10
    ) -> list[DocumentRecord]:
        terms = {term.lower() for term in query.split() if term}
        entities = set(entity_ids)
        events = set(event_ids)

        def score(document: DocumentRecord) -> tuple[int, datetime]:
            haystack = f"{document.text} {document.payload}".lower()
            return (sum(term in haystack for term in terms), document.created_at)

        matches = [
            document for document in self.documents.values()
            if (not entities and not events
                or bool(entities.intersection(document.metadata.get("entity_ids", [])))
                or document.metadata.get("event_id") in events)
            and all(document.metadata.get(key) == value for key, value in (metadata_filters or {}).items())
        ]
        matches.sort(key=score, reverse=True)
        return matches[:limit]


class InMemoryCaseStore:
    def __init__(self) -> None:
        self.cases: dict[tuple[str, str], CaseRecord] = {}
        self.tasks: dict[tuple[str, str], HumanTask] = {}

    def create_case(self, case: CaseRecord) -> None:
        key = (case.tenant_id, case.case_id)
        if key in self.cases:
            raise ValueError(f"case already exists: {case.case_id}")
        self.cases[key] = case

    def get_case(self, case_id: str, tenant_id: str) -> CaseRecord | None:
        return self.cases.get((tenant_id, case_id))

    def list_cases(self, tenant_id: str) -> list[CaseRecord]:
        return sorted(
            (case for (tenant, _), case in self.cases.items() if tenant == tenant_id),
            key=lambda case: case.updated_at, reverse=True,
        )

    def update_case(self, case: CaseRecord, expected_version: int) -> None:
        current = self.get_case(case.case_id, case.tenant_id)
        if current is None:
            raise KeyError(case.case_id)
        if current.version != expected_version or case.version != expected_version + 1:
            raise RuntimeError("case was modified concurrently")
        self.cases[(case.tenant_id, case.case_id)] = case

    def put_task(self, task: HumanTask) -> None:
        if (task.tenant_id, task.case_id) not in self.cases:
            raise KeyError(task.case_id)
        self.tasks[(task.tenant_id, task.task_id)] = task

    def tasks_for_case(self, case_id: str, tenant_id: str) -> list[HumanTask]:
        return [task for (tenant, _), task in self.tasks.items()
                if tenant == tenant_id and task.case_id == case_id]

    def list_tasks(self, tenant_id: str) -> list[HumanTask]:
        return sorted(
            (task for (tenant, _), task in self.tasks.items() if tenant == tenant_id),
            key=lambda task: task.created_at, reverse=True,
        )


class InMemoryOutbox:
    def __init__(self) -> None:
        self.messages: dict[str, OutboxMessage] = {}

    def append(self, message: OutboxMessage) -> None:
        existing = self.messages.get(message.message_id)
        if existing is not None and existing != message:
            raise ValueError("outbox message ids are immutable")
        self.messages[message.message_id] = message

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        values = [message for message in self.messages.values() if message.published_at is None]
        return sorted(values, key=lambda message: message.created_at)[:limit]

    def mark_published(self, message_id: str, at: datetime) -> None:
        message = self.messages[message_id]
        self.messages[message_id] = OutboxMessage(
            message_id=message.message_id, tenant_id=message.tenant_id, topic=message.topic,
            aggregate_id=message.aggregate_id, payload=message.payload,
            created_at=message.created_at, published_at=at,
        )
