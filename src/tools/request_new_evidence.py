from __future__ import annotations

from typing import Any

from .base import ToolContext


def request_new_evidence(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    required = ("evidence_type", "target", "reason", "priority", "decision_dependency")
    missing = [key for key in required if not str(arguments.get(key, "")).strip()]
    if missing:
        raise ValueError(f"missing request fields: {missing}")
    signature = tuple(str(arguments[key]) for key in required)
    existing = next((item for item in context.blackboard.pending_evidence if tuple(str(item.get(key, "")) for key in required) == signature), None)
    if existing:
        return {"request": existing, "evidence_ids": []}
    request = {
        "request_id": f"ER-{len(context.blackboard.pending_evidence) + 1:03d}",
        **{key: arguments[key] for key in required},
        "availability_type": "requires_new_test" if "test" in str(arguments["evidence_type"]).lower() or "identification" in str(arguments["evidence_type"]).lower() else "requires_human_observation",
        "status": "pending",
        "answer": None,
    }
    context.blackboard.pending_evidence.append(request)
    return {"request": request, "evidence_ids": []}

