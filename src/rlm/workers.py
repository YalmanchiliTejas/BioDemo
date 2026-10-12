from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.tools import ToolContext, ToolRegistry

from .decomposer import InvestigationQuestion
from .provider import CodexRLMProvider


def _compact(
    question: InvestigationQuestion,
    finding: str,
    result: dict[str, Any],
    uncertainties: list[str],
    *,
    supporting: list[str] | None = None,
    contradicting: list[str] | None = None,
) -> dict[str, Any]:
    evidence = list(dict.fromkeys(map(str, supporting if supporting is not None else result.get("evidence_ids", []))))
    return {
        "question_id": question.question_id,
        "question": question.question,
        "finding": finding,
        "supporting_evidence_ids": evidence,
        "contradicting_evidence_ids": list(dict.fromkeys(map(str, contradicting or []))),
        "uncertainties": uncertainties,
        "depth": question.depth,
        "batch_id": question.batch_id,
        "equipment_id": question.equipment_id,
        "search_term": question.search_term,
    }


def investigate(question: InvestigationQuestion, tools: ToolRegistry, context: ToolContext) -> dict[str, Any]:
    batch = question.batch_id
    term = question.search_term or "abnormal signal"
    if question.investigation_type == "batch_context" and batch:
        result = tools.execute("get_batch_context", context, {"batch_id": batch, "as_of": context.session.as_of})
        return _compact(question, f"Retrieved {len(result['evidence_ids'])} time-valid records for {batch}.", result, [] if result["evidence_ids"] else ["No batch-linked evidence is currently available"])
    if question.investigation_type == "batch_comparison":
        search = tools.execute("search_factory_data", context, {"query": term, "as_of": context.session.as_of, "limit": 30})
        batches = list(dict.fromkeys(
            str(row.get("batch_id") or row.get("linked_batch_id") or row.get("lot"))
            for row in search["records"] if row.get("batch_id") or row.get("linked_batch_id") or row.get("lot")
        ))
        if batch and batch not in batches:
            batches.insert(0, batch)
        if len(batches) >= 2:
            result = tools.execute("compare_batches", context, {
                "batch_ids": batches[:8],
                "comparison_dimensions": ["microbiology", "process", "environment", "equipment", "maintenance", "deviations", "operators"],
                "as_of": context.session.as_of,
            })
            return _compact(question, f"Compared {len(batches[:8])} batches across available manufacturing dimensions.", result, [])
        return _compact(question, "No time-valid comparison cohort was available.", search, ["At least one comparable batch is needed"])
    systems = {
        "historical": [],
        "process_environment": ["MES", "ENVIRONMENT"],
        "equipment_maintenance": ["MES", "CMMS"],
        "quality_microbiology": ["LIMS", "QMS"],
        "evidence_verification": [],
    }.get(question.investigation_type, [])
    query = term if question.investigation_type == "historical" else f"{term} {question.investigation_type.replace('_', ' ')}"
    result = tools.execute("search_factory_data", context, {
        "query": query,
        "systems": systems,
        "batch_ids": [batch] if batch and question.investigation_type != "historical" else [],
        "equipment_ids": [question.equipment_id] if question.equipment_id and question.investigation_type == "equipment_maintenance" else [],
        "as_of": context.session.as_of,
        "limit": 20,
    })
    finding = f"Found {result['count']} time-valid records relevant to {question.investigation_type.replace('_', ' ')}."
    uncertainties = [] if result["count"] else [f"No existing record resolved: {question.question}"]
    contradicting = [
        row["_evidence_id"] for row in result["records"]
        if str(row.get("status", "")).lower() in {"normal", "pass"}
        or str(row.get("severity", "")).lower() == "normal"
    ]
    supporting = [identifier for identifier in result["evidence_ids"] if identifier not in set(contradicting)]
    return _compact(
        question, finding, result, uncertainties,
        supporting=supporting, contradicting=contradicting,
    )


def run_parallel(
    questions: list[InvestigationQuestion],
    tools: ToolRegistry,
    context: ToolContext,
    *,
    max_workers: int,
) -> list[dict[str, Any]]:
    if not questions:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(questions)), thread_name_prefix="rlm-worker") as executor:
        futures = [executor.submit(investigate, question, tools, context) for question in questions]
        return [future.result() for future in futures]


def run_agentic_parallel(
    questions: list[InvestigationQuestion],
    tools: ToolRegistry,
    context: ToolContext,
    provider: CodexRLMProvider,
    *,
    max_workers: int,
) -> list[dict[str, Any]]:
    """Plan bounded workers with Luna, execute their tools concurrently, then compress findings."""
    question_values = [question.__dict__ for question in questions]
    planned = provider.plan_workers({
        "as_of": context.session.as_of,
        "questions": question_values,
        "available_tools": [name for name in tools.names if name not in {"request_new_evidence", "create_investigation_task"}],
        "constraints": {"max_tool_requests_per_question": 2, "read_only": True},
    })
    by_id = {question.question_id: question for question in questions}

    def execute_plan(plan: dict[str, Any]) -> dict[str, Any]:
        question_id = str(plan.get("question_id", ""))
        if question_id not in by_id:
            return {"question_id": question_id, "tool_results": [], "error": "unknown question_id"}
        results = []
        for request in plan.get("tool_requests", [])[:2]:
            name = str(request.get("tool_name", ""))
            try:
                arguments = json.loads(str(request.get("arguments_json", "{}")))
                if not isinstance(arguments, dict):
                    raise ValueError("arguments_json must decode to an object")
                arguments["as_of"] = context.session.as_of
                results.append({"tool_name": name, "status": "ok", "result": tools.execute(name, context, arguments)})
            except Exception as exc:
                results.append({"tool_name": name, "status": "error", "error": str(exc)})
        return {"question_id": question_id, "tool_results": results}

    plans = [plan for plan in planned.get("plans", []) if isinstance(plan, dict)]
    # Preserve capacity for up to three physical-evidence requests and three
    # human tasks during Lead synthesis. The aggregate ToolRegistry remains the
    # hard enforcement boundary; this scheduler prevents workers from consuming
    # the entire budget before the decision/action phase.
    remaining_worker_budget = max(0, tools.max_calls - tools.calls - 6)
    bounded_plans: list[dict[str, Any]] = []
    for plan in plans:
        permitted = min(2, remaining_worker_budget)
        bounded_plans.append({**plan, "tool_requests": list(plan.get("tool_requests", []))[:permitted]})
        remaining_worker_budget -= permitted
    plans = bounded_plans
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(plans))), thread_name_prefix="rlm-agentic-worker") as executor:
        tool_packets = list(executor.map(execute_plan, plans))
    summarized = provider.summarize_workers({
        "as_of": context.session.as_of,
        "questions": question_values,
        "tool_packets": tool_packets,
        "required_behavior": "Cite only evidence IDs present in tool results and identify counterevidence and uncertainty.",
    })
    allowed: dict[str, set[str]] = {}
    for packet in tool_packets:
        ids: set[str] = set()
        for result in packet["tool_results"]:
            ids.update(map(str, result.get("result", {}).get("evidence_ids", [])))
        allowed[packet["question_id"]] = ids
    returned = {str(item.get("question_id")): item for item in summarized.get("findings", []) if isinstance(item, dict)}
    findings: list[dict[str, Any]] = []
    for question in questions:
        item = returned.get(question.question_id, {})
        valid = allowed.get(question.question_id, set())
        findings.append({
            "question_id": question.question_id,
            "question": question.question,
            "finding": str(item.get("finding") or "No model finding returned."),
            "supporting_evidence_ids": [str(value) for value in item.get("supporting_evidence_ids", []) if str(value) in valid],
            "contradicting_evidence_ids": [str(value) for value in item.get("contradicting_evidence_ids", []) if str(value) in valid],
            "uncertainties": [str(value) for value in item.get("uncertainties", [])],
            "depth": question.depth, "batch_id": question.batch_id,
            "equipment_id": question.equipment_id, "search_term": question.search_term,
        })
    return findings
