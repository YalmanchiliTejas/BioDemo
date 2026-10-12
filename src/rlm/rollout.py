from __future__ import annotations

import json
from typing import Any

from src.data import TemporalFactoryStore
from src.state import BlackboardStore, CausalHypothesisGraph, DecisionGraph
from src.tools import ToolContext, build_tool_registry

from .decomposer import InvestigationQuestion, RecursiveDecomposer
from .lead_agent import LeadManufacturingRLM
from .provider import CodexRLMProvider
from .workers import run_agentic_parallel, run_parallel


class RolloutEngine:
    """OBSERVE → LOAD → DECOMPOSE → INVESTIGATE → SYNTHESIZE → PERSIST → SUSPEND."""

    def __init__(
        self,
        data: TemporalFactoryStore,
        blackboards: BlackboardStore,
        lead: LeadManufacturingRLM | None = None,
        provider: CodexRLMProvider | None = None,
    ) -> None:
        self.data = data
        self.blackboards = blackboards
        self.lead = lead or LeadManufacturingRLM()
        self.decomposer = RecursiveDecomposer()
        self.provider = provider

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
        provider_before = self.provider.snapshot() if self.provider else None
        tools = build_tool_registry(max_calls=self.lead.config.max_total_tool_calls_per_rollout)
        context = ToolContext(session, blackboard)
        if self.provider:
            proposed = self.provider.decompose({
                "problem": problem,
                "blackboard": blackboard.to_dict(),
                "new_evidence": new_evidence,
                "as_of": as_of,
                "available_tools": list(tools.names),
                "limits": {
                    "max_depth": self.lead.config.max_depth,
                    "max_parallel_subtasks": self.lead.config.max_parallel_subtasks,
                    "max_total_tool_calls": self.lead.config.max_total_tool_calls_per_rollout,
                },
            })
            questions = [
                InvestigationQuestion(
                    f"Q-D1-{index}", str(item["question"]), str(item["investigation_type"]), 1,
                    str(item.get("batch_id") or "") or None,
                    str(item.get("equipment_id") or "") or None,
                    str(item.get("search_term") or "") or None,
                )
                for index, item in enumerate(
                    proposed.get("questions", [])[:self.lead.config.max_parallel_subtasks], 1,
                )
            ]
            if not questions:
                raise RuntimeError("Codex decomposition returned no bounded questions")
            findings = run_agentic_parallel(
                questions, tools, context, self.provider,
                max_workers=self.lead.config.max_parallel_subtasks,
            )
        else:
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
                if self.provider:
                    findings.extend(run_agentic_parallel(
                        followups, tools, context, self.provider,
                        max_workers=self.lead.config.max_parallel_subtasks,
                    ))
                else:
                    findings.extend(run_parallel(
                        followups, tools, context,
                        max_workers=self.lead.config.max_parallel_subtasks,
                    ))
                depth = 2
        model_synthesis = self.provider.synthesize({
            "problem": problem,
            "blackboard": blackboard.to_dict(),
            "new_evidence": new_evidence,
            "compressed_findings": findings,
            "as_of": as_of,
            "instruction": "Maintain competing hypotheses, distinguish confidence from severity, and prepare work while physical evidence is pending.",
        }) if self.provider else None
        output = self.lead.synthesize(
            problem=problem, blackboard=blackboard, new_evidence=new_evidence,
            findings=findings, tools=tools, context=context,
            recursion_depth=depth, subtasks_spawned=len(findings),
            model_synthesis=model_synthesis,
        )
        serialized_input = json.dumps({"problem": problem, "blackboard": blackboard.to_dict(), "new_evidence": new_evidence}, default=str)
        serialized_output = json.dumps(output, default=str)
        if self.provider and provider_before is not None:
            provider_after = self.provider.snapshot()
            provider_usage = {key: provider_after[key] - provider_before[key] for key in provider_after}
            if provider_usage["model_calls"] > self.lead.config.max_model_calls_per_rollout:
                raise RuntimeError("model-call budget exceeded")
            output["rollout_metrics"].update({
                **provider_usage,
                "token_count_method": "codex_reported_usage",
                "provider_id": self.provider.provider_id,
            })
        else:
            output["rollout_metrics"].update({
                "model_calls": 0,
                "input_tokens": max(1, len(serialized_input) // 4),
                "cached_input_tokens": 0,
                "output_tokens": max(1, len(serialized_output) // 4),
                "reasoning_output_tokens": 0,
                "token_count_method": "estimated_utf8_characters_divided_by_4",
                "provider_id": "deterministic.reference",
            })
        blackboard.rollout_history.append({
            "as_of": as_of, "mode": mode, "new_evidence_ids": new_evidence_ids,
            "metrics": output["rollout_metrics"], "status": blackboard.status,
        })
        valid_ids = session.visible_evidence_ids() | set(blackboard.evidence_ids)
        errors = CausalHypothesisGraph(blackboard.causal_hypotheses).validate(valid_ids)
        errors += DecisionGraph(blackboard.decision_branches).validate({item["request_id"] for item in blackboard.pending_evidence})
        if errors:
            raise ValueError("invalid persisted investigation graph: " + "; ".join(errors))
        self.blackboards.save(blackboard)
        output["blackboard_status"] = blackboard.status
        return output
