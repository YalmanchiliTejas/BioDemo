from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .domain import CaseRecord, CaseStatus, EntityRef, HumanTask, OutboxMessage


class PostgresWorkflowStore:
    """Transactional working-memory and outbox adapter for production deployments."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional service
            raise RuntimeError("Install the 'knowledge' extra to use PostgreSQL") from exc
        self._psycopg = psycopg
        self._connection = psycopg.connect(dsn)
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_cases (
                    tenant_id text NOT NULL, case_id text NOT NULL, payload jsonb NOT NULL,
                    version integer NOT NULL, updated_at timestamptz NOT NULL,
                    PRIMARY KEY (tenant_id, case_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_tasks (
                    tenant_id text NOT NULL, task_id text NOT NULL, case_id text NOT NULL,
                    payload jsonb NOT NULL, PRIMARY KEY (tenant_id, task_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS knowledge_tasks_case ON knowledge_tasks (tenant_id, case_id)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_outbox (
                    message_id text PRIMARY KEY, tenant_id text NOT NULL, topic text NOT NULL,
                    aggregate_id text NOT NULL, payload jsonb NOT NULL,
                    created_at timestamptz NOT NULL, published_at timestamptz
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS knowledge_outbox_pending ON knowledge_outbox (created_at) WHERE published_at IS NULL")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_connector_checkpoints (
                    tenant_id text NOT NULL, connector_id text NOT NULL, checkpoint text,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (tenant_id, connector_id)
                )
            """)

    def create_case(self, case: CaseRecord) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO knowledge_cases VALUES (%s, %s, %s, %s, %s)",
                (case.tenant_id, case.case_id, json.dumps(asdict(case), default=str), case.version, case.updated_at),
            )

    def get_case(self, case_id: str, tenant_id: str) -> CaseRecord | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT payload FROM knowledge_cases WHERE tenant_id=%s AND case_id=%s", (tenant_id, case_id))
            row = cursor.fetchone()
        return _case_from_payload(row[0]) if row else None

    def update_case(self, case: CaseRecord, expected_version: int) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                """UPDATE knowledge_cases SET payload=%s, version=%s, updated_at=%s
                   WHERE tenant_id=%s AND case_id=%s AND version=%s""",
                (json.dumps(asdict(case), default=str), case.version, case.updated_at,
                 case.tenant_id, case.case_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("case was modified concurrently")

    def put_task(self, task: HumanTask) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_tasks VALUES (%s, %s, %s, %s)
                   ON CONFLICT (tenant_id, task_id) DO UPDATE SET payload=EXCLUDED.payload""",
                (task.tenant_id, task.task_id, task.case_id, json.dumps(asdict(task), default=str)),
            )

    def tasks_for_case(self, case_id: str, tenant_id: str) -> list[HumanTask]:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT payload FROM knowledge_tasks WHERE tenant_id=%s AND case_id=%s", (tenant_id, case_id))
            return [_task_from_payload(row[0]) for row in cursor.fetchall()]

    def append(self, message: OutboxMessage) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_outbox VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (message_id) DO NOTHING""",
                (message.message_id, message.tenant_id, message.topic, message.aggregate_id,
                 json.dumps(message.payload, default=str), message.created_at, message.published_at),
            )

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT message_id, tenant_id, topic, aggregate_id, payload, created_at, published_at
                   FROM knowledge_outbox WHERE published_at IS NULL ORDER BY created_at LIMIT %s""", (limit,),
            )
            return [OutboxMessage(*row) for row in cursor.fetchall()]

    def mark_published(self, message_id: str, at: datetime) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute("UPDATE knowledge_outbox SET published_at=%s WHERE message_id=%s", (at, message_id))

    def get_checkpoint(self, tenant_id: str, connector_id: str) -> str | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT checkpoint FROM knowledge_connector_checkpoints WHERE tenant_id=%s AND connector_id=%s",
                (tenant_id, connector_id),
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def commit_checkpoint(self, tenant_id: str, connector_id: str, checkpoint: str | None) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO knowledge_connector_checkpoints (tenant_id, connector_id, checkpoint)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (tenant_id, connector_id) DO UPDATE
                   SET checkpoint=EXCLUDED.checkpoint, updated_at=now()""",
                (tenant_id, connector_id, checkpoint),
            )


def _case_from_payload(value: dict[str, Any]) -> CaseRecord:
    return CaseRecord(
        case_id=value["case_id"], tenant_id=value["tenant_id"], case_type=value["case_type"],
        title=value["title"], owner_id=value["owner_id"], site_id=value.get("site_id"),
        status=CaseStatus(value["status"]),
        entity_refs=tuple(EntityRef(**ref) for ref in value.get("entity_refs", [])),
        hypothesis=value.get("hypothesis"), opened_at=datetime.fromisoformat(value["opened_at"]),
        updated_at=datetime.fromisoformat(value["updated_at"]), version=value["version"],
    )


def _task_from_payload(value: dict[str, Any]) -> HumanTask:
    for field in ("due_at", "created_at", "completed_at"):
        if value.get(field):
            value[field] = datetime.fromisoformat(value[field])
    return HumanTask(**value)
