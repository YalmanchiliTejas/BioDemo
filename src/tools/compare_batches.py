from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from .base import ToolContext


DIMENSION_TABLES = {
    "microbiology": {"lab_results"}, "release tests": {"lab_results"},
    "process": {"process_events"}, "environment": {"environmental_monitoring"},
    "equipment": {"process_events", "maintenance"}, "maintenance": {"maintenance"},
    "deviations": {"deviations"}, "operators": {"operator_events"},
}


def compare_batches(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    batch_ids = list(dict.fromkeys(map(str, arguments.get("batch_ids", []))))
    if len(batch_ids) < 2:
        raise ValueError("compare_batches requires at least two batch_ids")
    dimensions = [str(value).lower() for value in arguments.get("comparison_dimensions", [])]
    tables = set().union(*(DIMENSION_TABLES.get(item, set()) for item in dimensions)) if dimensions else set().union(*DIMENSION_TABLES.values())
    by_batch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_ids: list[str] = []
    for record in context.session.records(tables):
        batch = str(record.get("batch_id") or record.get("linked_batch_id") or record.get("lot") or "")
        if batch in batch_ids:
            by_batch[batch].append(record)
            evidence_ids.append(record["_evidence_id"])
    summaries: dict[str, Any] = {}
    for batch in batch_ids:
        rows = by_batch[batch]
        numeric: dict[str, list[float]] = defaultdict(list)
        categories: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            for key, value in row.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric[key].append(float(value))
                elif key in {"status", "severity", "parameter", "test_name", "equipment_id", "category"} and value is not None:
                    categories[key].add(str(value))
        summaries[batch] = {
            "record_count": len(rows),
            "numeric_means": {key: statistics.fmean(values) for key, values in numeric.items()},
            "categories": {key: sorted(values) for key, values in categories.items()},
        }
    common_categories: dict[str, list[str]] = {}
    for key in set.intersection(*(set(value["categories"]) for value in summaries.values())) if summaries else set():
        shared = set.intersection(*(set(value["categories"][key]) for value in summaries.values()))
        if shared:
            common_categories[key] = sorted(shared)
    return {
        "batch_summaries": summaries,
        "similarities": {"common_categories": common_categories},
        "differences": {"per_batch": summaries},
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
    }

