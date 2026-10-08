from __future__ import annotations

from typing import Any

from .base import ToolContext


def get_batch_context(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    batch_id = str(arguments.get("batch_id", ""))
    if not batch_id:
        raise ValueError("batch_id is required")
    grouped: dict[str, list[dict[str, Any]]] = {}
    evidence_ids: list[str] = []
    for record in context.session.records():
        related = record.get("batch_id") or record.get("linked_batch_id") or record.get("lot")
        if str(related) != batch_id:
            continue
        grouped.setdefault(record["_table"], []).append(record)
        evidence_ids.append(record["_evidence_id"])
    return {"batch_id": batch_id, "context": grouped, "evidence_ids": evidence_ids}

