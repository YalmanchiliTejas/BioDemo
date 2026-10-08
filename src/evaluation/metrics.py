from __future__ import annotations

import statistics
from typing import Any


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def summarize_rollouts(values: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rlm_recursion_depth": max((item["rlm_recursion_depth"] for item in values), default=0),
        "subtasks_spawned": sum(item["subtasks_spawned"] for item in values),
        "tool_calls": sum(item["tool_calls"] for item in values),
        "input_tokens": sum(item["input_tokens"] for item in values),
        "output_tokens": sum(item["output_tokens"] for item in values),
        "token_count_method": "estimated_utf8_characters_divided_by_4",
    }
