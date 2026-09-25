from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .models import ActionProposal, ApprovalDecision, AuditEntry, ProposalStatus, RiskLevel


class PostgresActionStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional service
            raise RuntimeError("Install the 'knowledge' extra to use PostgreSQL") from exc
        self._connection = psycopg.connect(dsn)
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS action_proposals (
                    tenant_id text NOT NULL, proposal_id text NOT NULL, status text NOT NULL,
                    updated_at timestamptz NOT NULL, payload jsonb NOT NULL,
                    PRIMARY KEY (tenant_id, proposal_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS action_proposals_inbox ON action_proposals (tenant_id, status, updated_at DESC)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authorization_audit (
                    audit_id text PRIMARY KEY, tenant_id text NOT NULL, actor_id text NOT NULL,
                    action text NOT NULL, object_type text NOT NULL, object_id text NOT NULL,
                    occurred_at timestamptz NOT NULL, details jsonb NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS authorization_audit_tenant ON authorization_audit (tenant_id, occurred_at DESC)")

    def put(self, proposal: ActionProposal) -> None:
        payload = json.dumps(asdict(proposal), default=str)
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO action_proposals VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (tenant_id, proposal_id) DO UPDATE
                   SET status=EXCLUDED.status, updated_at=EXCLUDED.updated_at, payload=EXCLUDED.payload""",
                (proposal.tenant_id, proposal.proposal_id, proposal.status.value,
                 proposal.updated_at, payload),
            )

    def get(self, tenant_id: str, proposal_id: str) -> ActionProposal | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM action_proposals WHERE tenant_id=%s AND proposal_id=%s",
                (tenant_id, proposal_id),
            )
            row = cursor.fetchone()
        return _proposal(row[0]) if row else None

    def list(self, tenant_id: str) -> list[ActionProposal]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM action_proposals WHERE tenant_id=%s ORDER BY updated_at DESC",
                (tenant_id,),
            )
            return [_proposal(row[0]) for row in cursor.fetchall()]

    def append_audit(self, entry: AuditEntry) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO authorization_audit VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (audit_id) DO NOTHING""",
                (entry.audit_id, entry.tenant_id, entry.actor_id, entry.action,
                 entry.object_type, entry.object_id, entry.occurred_at,
                 json.dumps(entry.details, default=str)),
            )

    def audit(self, tenant_id: str, limit: int = 200) -> list[AuditEntry]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT audit_id, tenant_id, actor_id, action, object_type, object_id,
                          occurred_at, details FROM authorization_audit
                   WHERE tenant_id=%s ORDER BY occurred_at DESC LIMIT %s""",
                (tenant_id, limit),
            )
            return [AuditEntry(*row) for row in cursor.fetchall()]


def _proposal(value: dict[str, Any]) -> ActionProposal:
    return ActionProposal(
        proposal_id=value["proposal_id"], tenant_id=value["tenant_id"], case_id=value["case_id"],
        operation=value["operation"], target_id=value["target_id"], payload=value["payload"],
        requested_by=value["requested_by"], reason=value["reason"], site_id=value.get("site_id"),
        risk=RiskLevel(value["risk"]), required_roles=tuple(value.get("required_roles", ())),
        status=ProposalStatus(value["status"]),
        approvals=tuple(ApprovalDecision(
            approval_id=item["approval_id"], actor_id=item["actor_id"], role=item["role"],
            decision=item["decision"], meaning=item["meaning"],
            decided_at=datetime.fromisoformat(item["decided_at"]), comment=item.get("comment", ""),
        ) for item in value.get("approvals", [])),
        created_at=datetime.fromisoformat(value["created_at"]),
        updated_at=datetime.fromisoformat(value["updated_at"]),
    )
