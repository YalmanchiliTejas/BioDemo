from __future__ import annotations

import statistics
from typing import Any

from .base import ToolContext


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = statistics.fmean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    return sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator


def analyze_trend(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    metric = str(arguments.get("metric", ""))
    scope = arguments.get("scope") or {}
    window = arguments.get("window") or {}
    values: list[float] = []
    evidence_ids: list[str] = []
    threshold_proximity: list[float] = []
    for row in context.session.records():
        batch = str(row.get("batch_id") or row.get("linked_batch_id") or row.get("lot") or "")
        if scope.get("batch_ids") and batch not in set(map(str, scope["batch_ids"])):
            continue
        if scope.get("equipment_ids") and str(row.get("equipment_id")) not in set(map(str, scope["equipment_ids"])):
            continue
        if window.get("start") and row["occurred_at"] < window["start"]:
            continue
        if window.get("end") and row["occurred_at"] > window["end"]:
            continue
        candidate = row.get(metric)
        if candidate is None and (row.get("parameter") == metric or row.get("test_name") == metric):
            candidate = row.get("value", row.get("numerical_result", row.get("result")))
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            values.append(float(candidate))
            evidence_ids.append(row["_evidence_id"])
            limit = row.get("action_limit") or row.get("expected_high") or row.get("specification_limit")
            if isinstance(limit, (int, float)) and limit:
                threshold_proximity.append(float(candidate) / float(limit))
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "slope": None, "threshold_proximity": None, "historical_comparison": None, "evidence_ids": []}
    midpoint = max(1, len(values) // 2)
    earlier, later = values[:midpoint], values[midpoint:]
    return {
        "count": len(values), "mean": statistics.fmean(values), "median": statistics.median(values),
        "min": min(values), "max": max(values), "slope": _slope(values),
        "threshold_proximity": max(threshold_proximity) if threshold_proximity else None,
        "historical_comparison": None if not later else statistics.fmean(later) - statistics.fmean(earlier),
        "evidence_ids": evidence_ids,
    }

