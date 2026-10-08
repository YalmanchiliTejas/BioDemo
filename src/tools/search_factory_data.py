from __future__ import annotations

import json
from typing import Any

from .base import ToolContext


def search_factory_data(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", "")).lower()
    terms = {term for term in query.replace("/", " ").replace("_", " ").split() if len(term) > 2}
    tables = context.session.tables_for_systems(arguments.get("systems", []))
    batch_ids = set(map(str, arguments.get("batch_ids", [])))
    equipment_ids = set(map(str, arguments.get("equipment_ids", [])))
    product = arguments.get("product")
    time_range = arguments.get("time_range") or {}
    limit = max(1, min(int(arguments.get("limit", 20)), 100))
    matches: list[tuple[int, dict[str, Any]]] = []
    for record in context.session.records(tables):
        batch = str(record.get("batch_id") or record.get("linked_batch_id") or record.get("lot") or "")
        equipment = str(record.get("equipment_id") or "")
        if batch_ids and batch not in batch_ids:
            continue
        if equipment_ids and equipment not in equipment_ids:
            continue
        if product and str(record.get("product") or record.get("_product") or "") != str(product):
            continue
        if time_range:
            occurred = record["occurred_at"]
            if time_range.get("start") and occurred < time_range["start"]:
                continue
            if time_range.get("end") and occurred > time_range["end"]:
                continue
        haystack = json.dumps(record, sort_keys=True, default=str).lower()
        score = sum(term in haystack for term in terms)
        if not terms or score:
            matches.append((score, record))
    matches.sort(key=lambda item: (-item[0], item[1]["available_at"], item[1]["_evidence_id"]))
    records = [record for _, record in matches[:limit]]
    return {"records": records, "evidence_ids": [row["_evidence_id"] for row in records], "count": len(records)}

