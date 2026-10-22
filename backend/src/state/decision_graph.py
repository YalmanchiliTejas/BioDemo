from __future__ import annotations

from copy import deepcopy
from typing import Any


class DecisionGraph:
    """Conditional actions kept separate from beliefs about causal mechanisms."""

    def __init__(self, nodes: list[dict[str, Any]] | None = None) -> None:
        self.nodes = {node["decision_id"]: deepcopy(node) for node in (nodes or [])}

    def upsert(self, node: dict[str, Any]) -> None:
        identifier = str(node["decision_id"])
        self.nodes[identifier] = {
            "decision_id": identifier,
            "condition": str(node.get("condition", "")),
            "if_true": list(dict.fromkeys(map(str, node.get("if_true", [])))),
            "if_false": list(dict.fromkeys(map(str, node.get("if_false", [])))),
            "actions_available_now": list(dict.fromkeys(map(str, node.get("actions_available_now", [])))),
            "pending_dependencies": list(dict.fromkeys(map(str, node.get("pending_dependencies", [])))),
        }

    def validate(self, pending_request_ids: set[str]) -> list[str]:
        errors: list[str] = []
        for identifier, node in self.nodes.items():
            for branch in node["if_true"] + node["if_false"]:
                if branch not in self.nodes:
                    errors.append(f"{identifier} references missing decision node {branch}")
            for dependency in node["pending_dependencies"]:
                if dependency not in pending_request_ids:
                    errors.append(f"{identifier} references missing evidence request {dependency}")
        return errors

    def to_list(self) -> list[dict[str, Any]]:
        return [deepcopy(self.nodes[key]) for key in sorted(self.nodes)]

