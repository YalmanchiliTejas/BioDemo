from __future__ import annotations

from typing import Any

from .base import ToolContext


OWNERS = {"QA", "Microbiology", "MSAT", "Manufacturing", "Maintenance"}


def create_investigation_task(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    owner = str(arguments.get("owner", ""))
    if owner not in OWNERS:
        raise ValueError(f"owner must be one of {sorted(OWNERS)}")
    visible = context.session.visible_evidence_ids()
    evidence_ids = [str(value) for value in arguments.get("evidence_ids", []) if str(value) in visible]
    task = {
        "task_id": f"IT-{len(context.blackboard.recommended_actions) + 1:03d}",
        "owner": owner,
        "action": str(arguments.get("action", "")),
        "priority": str(arguments.get("priority", "medium")),
        "evidence_ids": evidence_ids,
        "reason": str(arguments.get("reason", "")),
        "status": "proposed_for_human_review",
        "requires_human_approval": True,
    }
    context.blackboard.recommended_actions.append(task)
    if owner not in context.blackboard.teams_involved:
        context.blackboard.teams_involved.append(owner)
    return {"task": task, "evidence_ids": evidence_ids}

