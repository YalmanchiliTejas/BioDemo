from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import KnowledgeEvent, KnowledgeRule


class Neo4jGraphStore:
    """Neo4j adapter. The driver is imported lazily so the base benchmark stays lean."""

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j") -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - depends on optional service
            raise RuntimeError("Install the 'knowledge' extra to use Neo4j") from exc
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database
        self._driver.verify_connectivity()
        self._initialize()

    def close(self) -> None:
        self._driver.close()

    def _run(self, query: str, **parameters: Any) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(query, database_=self._database, **parameters)
        return [record.data() for record in records]

    def _initialize(self) -> None:
        for query in (
            "CREATE CONSTRAINT event_key IF NOT EXISTS FOR (e:Event) REQUIRE e.event_key IS UNIQUE",
            "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_key IS UNIQUE",
            "CREATE CONSTRAINT rule_key IF NOT EXISTS FOR (r:Rule) REQUIRE r.key IS UNIQUE",
            "CREATE CONSTRAINT domain_key IF NOT EXISTS FOR (o:DomainObject) REQUIRE o.object_key IS UNIQUE",
            "CREATE INDEX event_occurred_at IF NOT EXISTS FOR (e:Event) ON (e.occurred_at)",
        ):
            self._run(query)

    def upsert_event(self, event: KnowledgeEvent) -> None:
        self._run(
            """
            MERGE (e:Event {event_key: $tenant_id + ':' + $event_id})
            SET e.event_id = $event_id, e.occurred_at = datetime($occurred_at), e.event_type = $event_type,
                e.source = $source, e.document_id = $document_id,
                e.scenario_id = $scenario_id, e.summary = $summary, e.entity_ids = $entity_ids,
                e.attributes_json = $attributes_json, e.tenant_id = $tenant_id,
                e.site_id = $site_id, e.classification = $classification,
                e.evidence_id = $evidence_id, e.ingested_at = datetime($ingested_at)
            WITH e
            UNWIND $entity_ids AS entity_id
            MERGE (n:Entity {entity_key: $tenant_id + ':' + entity_id})
            SET n.entity_id = entity_id, n.tenant_id = $tenant_id
            MERGE (e)-[:AFFECTS]->(n)
            """,
            **_event_parameters(event),
        )

    def link_previous(
        self, entity_id: str, event_id: str, previous_event_id: str, tenant_id: str = "default"
    ) -> None:
        self._run(
            """
            MATCH (current:Event {event_key: $tenant_id + ':' + $event_id}),
                  (previous:Event {event_key: $tenant_id + ':' + $previous_event_id})
            MERGE (current)-[:PREVIOUS_EVENT {entity_id: $entity_id, tenant_id: $tenant_id}]->(previous)
            """,
            entity_id=entity_id,
            event_id=event_id,
            previous_event_id=previous_event_id,
            tenant_id=tenant_id,
        )

    def rebuild_timeline(self, entity_id: str, tenant_id: str = "default") -> None:
        self._run(
            "MATCH (:Event)-[link:PREVIOUS_EVENT {entity_id: $entity_id, tenant_id: $tenant_id}]->(:Event) DELETE link",
            entity_id=entity_id,
            tenant_id=tenant_id,
        )
        self._run(
            """
            MATCH (event:Event)-[:AFFECTS]->(:Entity {entity_key: $tenant_id + ':' + $entity_id})
            WITH event ORDER BY event.occurred_at, event.event_id
            WITH collect(event) AS events
            WHERE size(events) > 1
            UNWIND range(1, size(events) - 1) AS position
            WITH events[position] AS current, events[position - 1] AS previous
            MERGE (current)-[:PREVIOUS_EVENT {entity_id: $entity_id, tenant_id: $tenant_id}]->(previous)
            """,
            entity_id=entity_id,
            tenant_id=tenant_id,
        )

    def latest_event(
        self, entity_id: str, before: datetime | None = None, tenant_id: str = "default"
    ) -> KnowledgeEvent | None:
        rows = self._run(
            """
            MATCH (e:Event)-[:AFFECTS]->(:Entity {entity_key: $tenant_id + ':' + $entity_id})
            WHERE $before IS NULL OR e.occurred_at <= datetime($before)
            RETURN properties(e) AS event ORDER BY e.occurred_at DESC, e.event_id DESC LIMIT 1
            """,
            entity_id=entity_id,
            before=before.isoformat() if before else None,
            tenant_id=tenant_id,
        )
        return _event_from_properties(rows[0]["event"]) if rows else None

    def related_events(
        self, entity_ids: tuple[str, ...], event_type: str | None, before: datetime | None, limit: int,
        tenant_id: str = "default",
    ) -> list[KnowledgeEvent]:
        rows = self._run(
            """
            MATCH (e:Event)
            WHERE ($event_type IS NULL OR e.event_type = $event_type)
              AND e.tenant_id = $tenant_id
              AND ($before IS NULL OR e.occurred_at <= datetime($before))
              AND (size($entity_ids) = 0 OR EXISTS {
                    MATCH (e)-[:AFFECTS]->(n:Entity) WHERE n.entity_id IN $entity_ids
                  })
            RETURN DISTINCT properties(e) AS event
            ORDER BY e.occurred_at DESC, e.event_id DESC LIMIT $limit
            """,
            entity_ids=list(entity_ids),
            event_type=event_type,
            before=before.isoformat() if before else None,
            limit=limit,
            tenant_id=tenant_id,
        )
        return [_event_from_properties(row["event"]) for row in rows]

    def upsert_rule(self, rule: KnowledgeRule) -> None:
        self._run(
            """
            MERGE (r:Rule {key: $key})
            SET r.rule_id = $rule_id, r.version = $version, r.statement = $statement,
                r.event_types = $event_types, r.effective_from = datetime($effective_from),
                r.effective_until = CASE WHEN $effective_until IS NULL THEN NULL ELSE datetime($effective_until) END,
                r.supersedes_version = $supersedes_version, r.metadata_json = $metadata_json
            SET r.tenant_id = $tenant_id
            WITH r
            UNWIND $scope_entity_ids AS entity_id
            MERGE (n:Entity {entity_key: $tenant_id + ':' + entity_id})
            SET n.entity_id = entity_id, n.tenant_id = $tenant_id
            MERGE (r)-[:APPLIES_TO]->(n)
            """,
            key=rule.key,
            rule_id=rule.rule_id,
            version=rule.version,
            statement=rule.statement,
            event_types=list(rule.event_types),
            effective_from=rule.effective_from.isoformat(),
            effective_until=rule.effective_until.isoformat() if rule.effective_until else None,
            supersedes_version=rule.supersedes_version,
            metadata_json=json.dumps(rule.metadata, sort_keys=True),
            scope_entity_ids=list(rule.scope_entity_ids),
            tenant_id=rule.tenant_id,
        )

    def latest_rule(self, rule_id: str, tenant_id: str = "default") -> KnowledgeRule | None:
        rows = self._run(
            """
            MATCH (r:Rule {rule_id: $rule_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (r)-[:APPLIES_TO]->(n:Entity)
            WITH r, collect(n.entity_id) AS scope_entity_ids
            RETURN properties(r) AS rule, scope_entity_ids
            ORDER BY r.version DESC LIMIT 1
            """,
            rule_id=rule_id,
            tenant_id=tenant_id,
        )
        return _rule_from_properties(rows[0]["rule"], rows[0]["scope_entity_ids"]) if rows else None

    def active_rules(
        self, entity_ids: tuple[str, ...], event_type: str | None, at: datetime,
        tenant_id: str = "default",
    ) -> list[KnowledgeRule]:
        rows = self._run(
            """
            MATCH (r:Rule)
            WHERE r.effective_from <= datetime($at)
              AND r.tenant_id = $tenant_id
              AND (r.effective_until IS NULL OR datetime($at) < r.effective_until)
              AND (size(r.event_types) = 0 OR $event_type IS NULL OR $event_type IN r.event_types)
              AND (NOT EXISTS { MATCH (r)-[:APPLIES_TO]->(:Entity) }
                   OR EXISTS { MATCH (r)-[:APPLIES_TO]->(n:Entity) WHERE n.entity_id IN $entity_ids })
            WITH r ORDER BY r.version DESC
            WITH r.rule_id AS rule_id, head(collect(r)) AS r
            OPTIONAL MATCH (r)-[:APPLIES_TO]->(n:Entity)
            RETURN properties(r) AS rule, collect(n.entity_id) AS scope_entity_ids
            ORDER BY rule_id
            """,
            at=at.isoformat(),
            event_type=event_type,
            entity_ids=list(entity_ids),
            tenant_id=tenant_id,
        )
        return [_rule_from_properties(row["rule"], row["scope_entity_ids"]) for row in rows]

    def upsert_domain_object(
        self, object_id: str, kind: str, tenant_id: str, properties: dict[str, Any]
    ) -> None:
        self._run(
            """
            MERGE (object:DomainObject {object_key: $tenant_id + ':' + $object_id})
            SET object.object_id = $object_id, object.tenant_id = $tenant_id,
                object.kind = $kind, object.properties_json = $properties_json
            """,
            object_id=object_id, tenant_id=tenant_id, kind=kind,
            properties_json=json.dumps(properties, sort_keys=True, default=str),
        )

    def relate_domain_objects(
        self, from_id: str, to_id: str, relationship: str, tenant_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self._run(
            """
            MATCH (source:DomainObject {object_key: $tenant_id + ':' + $from_id}),
                  (target:DomainObject {object_key: $tenant_id + ':' + $to_id})
            MERGE (source)-[relation:RELATED {kind: $relationship}]->(target)
            SET relation.properties_json = $properties_json
            """,
            from_id=from_id, to_id=to_id, relationship=relationship, tenant_id=tenant_id,
            properties_json=json.dumps(properties or {}, sort_keys=True, default=str),
        )


def _event_parameters(event: KnowledgeEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "occurred_at": event.occurred_at.isoformat(),
        "event_type": event.event_type,
        "source": event.source,
        "entity_ids": list(event.entity_ids),
        "document_id": event.document_id,
        "scenario_id": event.scenario_id,
        "summary": event.summary,
        "attributes_json": json.dumps(event.attributes, sort_keys=True),
        "tenant_id": event.tenant_id,
        "site_id": event.site_id,
        "classification": event.classification,
        "evidence_id": event.evidence_id,
        "ingested_at": event.ingested_at.isoformat(),
    }


def _event_from_properties(value: dict[str, Any]) -> KnowledgeEvent:
    occurred_at = value["occurred_at"].to_native() if hasattr(value["occurred_at"], "to_native") else value["occurred_at"]
    ingested = value.get("ingested_at")
    ingested_at = ingested.to_native() if hasattr(ingested, "to_native") else (ingested or occurred_at)
    return KnowledgeEvent(
        event_id=value["event_id"], occurred_at=occurred_at, event_type=value["event_type"],
        source=value["source"], entity_ids=tuple(value.get("entity_ids", ())),
        document_id=value["document_id"], scenario_id=value.get("scenario_id"),
        summary=value.get("summary", ""), attributes=json.loads(value.get("attributes_json", "{}")),
        tenant_id=value.get("tenant_id", "default"), site_id=value.get("site_id"),
        classification=value.get("classification", "internal"), evidence_id=value.get("evidence_id"),
        ingested_at=ingested_at,
    )


def _rule_from_properties(value: dict[str, Any], scope: list[str]) -> KnowledgeRule:
    def native(item: Any) -> Any:
        return item.to_native() if hasattr(item, "to_native") else item

    return KnowledgeRule(
        rule_id=value["rule_id"], version=value["version"], statement=value["statement"],
        scope_entity_ids=tuple(scope), event_types=tuple(value.get("event_types", ())),
        effective_from=native(value["effective_from"]), effective_until=native(value.get("effective_until")),
        supersedes_version=value.get("supersedes_version"),
        metadata=json.loads(value.get("metadata_json", "{}")),
        tenant_id=value.get("tenant_id", "default"),
    )
