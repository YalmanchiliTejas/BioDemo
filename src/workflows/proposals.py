"""Persist reviewable task and evidence proposals from a Prime report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.state.blackboard import Blackboard


@dataclass
class ProposalContext:
    session: Any
    blackboard: Blackboard
    additional_visible_evidence_ids: set[str] = field(default_factory=set)


OWNERS = {"QA", "Microbiology", "MSAT", "Manufacturing", "Maintenance"}


def create_investigation_task(context: ProposalContext, arguments: dict[str, Any]) -> dict[str, Any]:
    owner = str(arguments.get("owner", ""))
    if owner not in OWNERS:
        raise ValueError(f"owner must be one of {sorted(OWNERS)}")
    requested_ids = list(dict.fromkeys(map(str,arguments.get("evidence_ids",[]))))
    if hasattr(context.session,'store'):
        visible = {row['_evidence_id'] for row in context.session.get(requested_ids)}
    else:
        visible = context.session.visible_evidence_ids()
    visible |= context.additional_visible_evidence_ids
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


def request_new_evidence(context: ProposalContext, arguments: dict[str, Any]) -> dict[str, Any]:
    required = ("evidence_type", "target", "reason", "priority", "decision_dependency")
    missing = [key for key in required if not str(arguments.get(key, "")).strip()]
    if missing:
        raise ValueError(f"missing request fields: {missing}")
    signature = tuple(str(arguments[key]) for key in required)
    existing = next((item for item in context.blackboard.pending_evidence
                     if tuple(str(item.get(key, "")) for key in required) == signature), None)
    if existing:
        return {"request": existing, "evidence_ids": []}
    request = {
        "request_id": f"ER-{len(context.blackboard.pending_evidence) + 1:03d}",
        **{key: arguments[key] for key in required},
        "availability_type": "requires_new_test" if "test" in str(arguments["evidence_type"]).lower()
        or "identification" in str(arguments["evidence_type"]).lower()
        else "requires_human_observation",
        "status": "pending",
        "answer": None,
    }
    context.blackboard.pending_evidence.append(request)
    return {"request": request, "evidence_ids": []}
