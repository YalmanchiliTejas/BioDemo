from __future__ import annotations

import statistics
from typing import Any


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def summarize_rollouts(values: list[dict[str, Any]]) -> dict[str, Any]:
    methods = {str(item.get("token_count_method", "unknown")) for item in values}
    providers = {str(item.get("provider_id", "unknown")) for item in values}
    return {
        "rlm_recursion_depth": max((item["rlm_recursion_depth"] for item in values), default=0),
        "subtasks_spawned": sum(item["subtasks_spawned"] for item in values),
        "tool_calls": sum(item["tool_calls"] for item in values),
        "model_calls": sum(item.get("model_calls", 0) for item in values),
        "input_tokens": sum(item["input_tokens"] for item in values),
        "cached_input_tokens": sum(item.get("cached_input_tokens", 0) for item in values),
        "output_tokens": sum(item["output_tokens"] for item in values),
        "reasoning_output_tokens": sum(item.get("reasoning_output_tokens", 0) for item in values),
        "token_count_method": next(iter(methods)) if len(methods) == 1 else "mixed",
        "provider_id": next(iter(providers)) if len(providers) == 1 else "mixed",
    }
