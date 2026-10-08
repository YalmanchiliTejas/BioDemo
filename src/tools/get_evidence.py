from __future__ import annotations

from typing import Any

from .base import ToolContext


def get_evidence(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    requested = list(map(str, arguments.get("record_ids", [])))
    records = context.session.get(requested)
    return {
        "records": records,
        "evidence_ids": [record["_evidence_id"] for record in records],
        "unavailable_or_unknown_ids": sorted(set(requested) - {record["_evidence_id"] for record in records}),
    }

