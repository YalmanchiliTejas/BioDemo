from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.tools import ToolContext, ToolRegistry

from .decomposer import InvestigationQuestion


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
