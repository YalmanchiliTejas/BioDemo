from __future__ import annotations

from copy import deepcopy
from typing import Any


class CausalHypothesisGraph:
    """Competing, connected causal explanations with evidence on both sides."""

    def __init__(self, nodes: list[dict[str, Any]] | None = None) -> None:
        self.nodes = {node["hypothesis_id"]: deepcopy(node) for node in (nodes or [])}

    def upsert(self, node: dict[str, Any], valid_evidence_ids: set[str]) -> None:
        identifier = str(node["hypothesis_id"])
        confidence = node.get("confidence", 0.0)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            confidence = 0.0
        clean = {
            "hypothesis_id": identifier,
            "statement": str(node.get("statement", "")),
            "causal_parent_ids": list(dict.fromkeys(map(str, node.get("causal_parent_ids", [])))),
            "causal_child_ids": list(dict.fromkeys(map(str, node.get("causal_child_ids", [])))),
            "confidence": max(0.0, min(1.0, float(confidence))),
            "supporting_evidence_ids": [
                str(value) for value in node.get("supporting_evidence_ids", [])
                if str(value) in valid_evidence_ids
            ],
            "contradicting_evidence_ids": [
                str(value) for value in node.get("contradicting_evidence_ids", [])
                if str(value) in valid_evidence_ids
            ],
            "unknowns": list(dict.fromkeys(map(str, node.get("unknowns", [])))),
            "tests_or_observations_that_would_discriminate": list(dict.fromkeys(map(
                str, node.get("tests_or_observations_that_would_discriminate", [])
            ))),
        }
        self.nodes[identifier] = clean

    def validate(self, valid_evidence_ids: set[str]) -> list[str]:
        errors: list[str] = []
        for identifier, node in self.nodes.items():
            for related in node["causal_parent_ids"] + node["causal_child_ids"]:
                if related not in self.nodes:
                    errors.append(f"{identifier} references missing causal node {related}")
            for evidence in node["supporting_evidence_ids"] + node["contradicting_evidence_ids"]:
                if evidence not in valid_evidence_ids:
                    errors.append(f"{identifier} references unavailable evidence {evidence}")
        return errors

    def to_list(self) -> list[dict[str, Any]]:
        return [deepcopy(self.nodes[key]) for key in sorted(self.nodes)]

