from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.state import Blackboard, CausalHypothesisGraph, DecisionGraph
from src.tools import ToolContext, ToolRegistry


@dataclass(frozen=True)
class RLMConfig:
    max_depth: int = 2
    max_parallel_subtasks: int = 6
    max_total_tool_calls_per_rollout: int = 24


class LeadManufacturingRLM:
    """Owns synthesis and global graphs; workers own no persistent worldview."""

    def __init__(self, config: RLMConfig | None = None) -> None:
        self.config = config or RLMConfig()

    @staticmethod
    def _severity(records: list[dict[str, Any]], prior: str) -> str:
        rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        observed = rank.get(prior, 0)
        for row in records:
            text = json.dumps(row).lower()
            if "out_of_specification" in text or '"severity": "critical"' in text:
                observed = max(observed, 3)
            elif any(token in text for token in ('"status": "action"', '"severity": "high"', "action_limit")):
                observed = max(observed, 2)
            elif any(token in text for token in ('"status": "alert"', '"severity": "medium"')):
                observed = max(observed, 1)
        return ("LOW", "MEDIUM", "HIGH", "CRITICAL")[observed]

    @staticmethod
    def _signal_domain(record: dict[str, Any]) -> str:
        text = json.dumps(record).lower()
        if any(token in text for token in ("micro", "bioburden", "organism", "sterility", "endotoxin")):
            return "microbiology"
        if any(token in text for token in ("equipment", "pressure", "pump", "vessel", "maintenance")):
            return "equipment"
        if any(token in text for token in ("yield", "process", "temperature", "cycle")):
            return "process"
        return "quality"

    def synthesize(
        self,
        *,
        problem: str,
        blackboard: Blackboard,
        new_evidence: list[dict[str, Any]],
        findings: list[dict[str, Any]],
        tools: ToolRegistry,
        context: ToolContext,
        recursion_depth: int,
        subtasks_spawned: int,
    ) -> dict[str, Any]:
        valid_ids = context.session.visible_evidence_ids()
        new_ids = [row["_evidence_id"] for row in new_evidence if row["_evidence_id"] in valid_ids]
        finding_ids = [
            identifier
            for finding in findings
            for identifier in [*finding["supporting_evidence_ids"], *finding["contradicting_evidence_ids"]]
            if identifier in valid_ids
        ]
        all_ids = list(dict.fromkeys([*blackboard.evidence_ids, *new_ids, *finding_ids]))
        blackboard.evidence_ids = all_ids
        batches = list(dict.fromkeys(
            str(row.get("batch_id") or row.get("linked_batch_id") or row.get("lot"))
            for row in [*new_evidence, *context.session.get(all_ids)]
            if row.get("batch_id") or row.get("linked_batch_id") or row.get("lot")
        ))
        equipment = list(dict.fromkeys(str(row["equipment_id"]) for row in context.session.get(all_ids) if row.get("equipment_id")))
        blackboard.scope = {
            "type": "multi_batch" if len(batches) > 1 else "single_batch" if batches else "undetermined",
            "batch_ids": batches,
            "equipment_ids": equipment,
        }
        blackboard.severity = self._severity(new_evidence, blackboard.severity)
        for row in new_evidence:
            observation = {"statement": f"New {row['_table']} evidence became available.", "evidence_ids": [row["_evidence_id"]]}
            if observation not in blackboard.observations:
                blackboard.observations.append(observation)
        blackboard.completed_investigations.extend(finding for finding in findings if finding not in blackboard.completed_investigations)
        blackboard.resolved_questions.extend(
            {"question": finding["question"], "finding": finding["finding"], "evidence_ids": finding["supporting_evidence_ids"]}
            for finding in findings if finding["supporting_evidence_ids"]
        )
        blackboard.open_questions = list(dict.fromkeys(
            uncertainty for finding in findings for uncertainty in finding["uncertainties"]
        ))

        domain = self._signal_domain(new_evidence[-1] if new_evidence else {})
        graph = CausalHypothesisGraph(blackboard.causal_hypotheses)
        root_id = "H-SIGNAL"
        graph.upsert({
            "hypothesis_id": root_id,
            "statement": f"The observed {domain} signal represents a material manufacturing abnormality.",
            "causal_parent_ids": ["H-DIGITAL", "H-MEASUREMENT", "H-EQUIPMENT"],
            "causal_child_ids": [],
            "confidence": min(.9, .35 + .08 * len(new_ids)),
            "supporting_evidence_ids": new_ids,
            "contradicting_evidence_ids": [
                evidence for finding in findings for evidence in finding["contradicting_evidence_ids"]
            ],
            "unknowns": blackboard.open_questions,
            "tests_or_observations_that_would_discriminate": ["independent measurement", "cross-batch comparison"],
        }, valid_ids)
        hypotheses = [
            ("H-DIGITAL", "A process or environmental condition contributed to the signal.", .42),
            ("H-MEASUREMENT", "Sampling or measurement variation contributed to the signal.", .30),
            ("H-EQUIPMENT", "Equipment condition or maintenance state contributed to the signal.", .28),
        ]
        buckets = {
            "H-DIGITAL": [finding for finding in findings if finding["question_id"].endswith(("3", "4"))],
            "H-MEASUREMENT": [finding for finding in findings if "quality" in finding["question"].lower() or "histor" in finding["question"].lower()],
            "H-EQUIPMENT": [finding for finding in findings if "equipment" in finding["question"].lower()],
        }
        for identifier, statement, base in hypotheses:
            support = [evidence for finding in buckets[identifier] for evidence in finding["supporting_evidence_ids"]]
            contradict = [evidence for finding in buckets[identifier] for evidence in finding["contradicting_evidence_ids"]]
            graph.upsert({
                "hypothesis_id": identifier, "statement": statement,
                "causal_parent_ids": [], "causal_child_ids": [root_id],
                "confidence": min(.8, base + .02 * min(len(support), 8)),
                "supporting_evidence_ids": support, "contradicting_evidence_ids": contradict,
                "unknowns": blackboard.open_questions[:3],
                "tests_or_observations_that_would_discriminate": ["targeted review of independent evidence"],
            }, valid_ids)
        blackboard.causal_hypotheses = graph.to_list()

        pending_request = None
        if blackboard.open_questions or domain in {"microbiology", "equipment"}:
            request_type = "organism identification test" if domain == "microbiology" else "equipment inspection" if domain == "equipment" else "operator confirmation"
            pending_request = tools.execute("request_new_evidence", context, {
                "evidence_type": request_type,
                "target": batches[0] if batches else equipment[0] if equipment else "incident scope",
                "reason": "Discriminate among competing causal hypotheses without inventing physical evidence.",
                "priority": "high" if blackboard.severity in {"HIGH", "CRITICAL"} else "medium",
                "decision_dependency": "scope and escalation branch",
            })["request"]
        if not blackboard.recommended_actions:
            task = tools.execute("create_investigation_task", context, {
                "owner": "QA", "action": "Review the evidence-grounded investigation and confirm scope.",
                "priority": blackboard.severity.lower(), "evidence_ids": all_ids,
                "reason": "The Manufacturing OS may prepare recommendations but QA retains decision authority.",
            })["task"]
        else:
            task = blackboard.recommended_actions[-1]

        decisions = DecisionGraph(blackboard.decision_branches)
        dependency_ids = [pending_request["request_id"]] if pending_request else []
        decisions.upsert({
            "decision_id": "D-CURRENT",
            "condition": f"Pending discriminating evidence supports the leading {domain} pathway.",
            "if_true": ["D-EXPAND"], "if_false": ["D-ALTERNATE"],
            "actions_available_now": ["complete historical review", "compare batches", "review process and equipment context", task["task_id"]],
            "pending_dependencies": dependency_ids,
        })
        decisions.upsert({
            "decision_id": "D-EXPAND", "condition": "Evidence supports broader scope.",
            "if_true": [], "if_false": [], "actions_available_now": ["propose QA scope expansion"], "pending_dependencies": [],
        })
        decisions.upsert({
            "decision_id": "D-ALTERNATE", "condition": "Evidence does not support the current leading pathway.",
            "if_true": [], "if_false": [], "actions_available_now": ["increase investigation of competing explanations"], "pending_dependencies": [],
        })
        blackboard.decision_branches = decisions.to_list()
        blackboard.status = "suspended_pending_evidence" if blackboard.pending_evidence else "awaiting_human_review"
        assessment = f"Investigation opened or resumed from {len(new_ids)} newly available evidence record(s); {len(findings)} bounded investigations completed."
        output = {
            "assessment": assessment,
            "severity": blackboard.severity,
            "scope": blackboard.scope,
            "causal_hypotheses": blackboard.causal_hypotheses,
            "evidence_ids": all_ids,
            "related_batches": batches,
            "related_equipment": equipment,
            "resolved_questions": blackboard.resolved_questions,
            "open_questions": blackboard.open_questions,
            "actions_now": blackboard.recommended_actions,
            "pending_evidence_requests": blackboard.pending_evidence,
            "decision_branches": blackboard.decision_branches,
            "teams": blackboard.teams_involved,
            "continue_investigation": bool(blackboard.open_questions or blackboard.pending_evidence),
            "rollout_metrics": {
                "rlm_recursion_depth": recursion_depth,
                "subtasks_spawned": subtasks_spawned,
                "tool_calls": tools.calls,
            },
        }
        return output
