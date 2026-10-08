from __future__ import annotations

import json
from typing import Any

from src.data import TemporalFactoryStore
from src.state import BlackboardStore, CausalHypothesisGraph, DecisionGraph
from src.tools import ToolContext, build_tool_registry

from .decomposer import RecursiveDecomposer
from .lead_agent import LeadManufacturingRLM
from .workers import run_parallel


class RolloutEngine:
    """OBSERVE → LOAD → DECOMPOSE → INVESTIGATE → SYNTHESIZE → PERSIST → SUSPEND."""

    def __init__(self, data: TemporalFactoryStore, blackboards: BlackboardStore, lead: LeadManufacturingRLM | None = None) -> None:
        self.data = data
        self.blackboards = blackboards
        self.lead = lead or LeadManufacturingRLM()
        self.decomposer = RecursiveDecomposer()

    def run(
        self,
        *,
        incident_id: str,
        problem: str,
        new_evidence_ids: list[str],
        as_of: str,
        mode: str = "full_os",
    ) -> dict[str, Any]:
        session = self.data.session(as_of=as_of, mode=mode, current_evidence_ids=new_evidence_ids)
        new_evidence = session.get(new_evidence_ids)
        if not new_evidence:
            raise ValueError("rollout requires at least one currently available evidence record")
        blackboard = self.blackboards.load_or_create(incident_id)
        tools = build_tool_registry(max_calls=self.lead.config.max_total_tool_calls_per_rollout)
        context = ToolContext(session, blackboard)
        questions = self.decomposer.decompose(
            problem, new_evidence, blackboard.open_questions,
            depth=1, limit=self.lead.config.max_parallel_subtasks,
        )
        findings = run_parallel(
            questions, tools, context,
            max_workers=self.lead.config.max_parallel_subtasks,
        )
        depth = 1
        if self.lead.config.max_depth > 1:
            # Parallelism is bounded per wave. Recursive waves may add work, while
            # the rollout-wide tool budget remains the hard aggregate limit.
            followups = self.decomposer.recurse(
                findings, depth=2, limit=self.lead.config.max_parallel_subtasks,
            )
            if followups:
                findings.extend(run_parallel(followups, tools, context, max_workers=self.lead.config.max_parallel_subtasks))
                depth = 2
        output = self.lead.synthesize(
            problem=problem, blackboard=blackboard, new_evidence=new_evidence,
            findings=findings, tools=tools, context=context,
            recursion_depth=depth, subtasks_spawned=len(findings),
        )
        serialized_input = json.dumps({"problem": problem, "blackboard": blackboard.to_dict(), "new_evidence": new_evidence}, default=str)
        serialized_output = json.dumps(output, default=str)
        output["rollout_metrics"].update({
            "input_tokens": max(1, len(serialized_input) // 4),
            "output_tokens": max(1, len(serialized_output) // 4),
        })
        blackboard.rollout_history.append({
            "as_of": as_of, "mode": mode, "new_evidence_ids": new_evidence_ids,
            "metrics": output["rollout_metrics"], "status": blackboard.status,
        })
        valid_ids = session.visible_evidence_ids()
        errors = CausalHypothesisGraph(blackboard.causal_hypotheses).validate(valid_ids)
        errors += DecisionGraph(blackboard.decision_branches).validate({item["request_id"] for item in blackboard.pending_evidence})
        if errors:
            raise ValueError("invalid persisted investigation graph: " + "; ".join(errors))
        self.blackboards.save(blackboard)
        output["blackboard_status"] = blackboard.status
        return output
