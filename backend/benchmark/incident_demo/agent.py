from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol


SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

AGENT_SYSTEM_PROMPT = """You are one bounded Manufacturing Agent for a pharmaceutical plant.
Analyze only the structured records supplied in visible_state. Those records are time-bounded: you
must not infer or mention later events, the real recall outcome, or any record absent from
valid_evidence_ids. Separate observations from inference. Every evidence reference must be an exact
member of valid_evidence_ids. Escalate severity only as evidence accumulates. You may recommend
investigation or containment, but you cannot release, reject, disposition, or recall a GMP batch.
Those decisions require authorized humans. Return one JSON object matching output_schema."""

OUTPUT_SCHEMA: dict[str, Any] = {
    "severity": "low|medium|high|critical",
    "triage_level": "L1|L2|L3",
    "summary": "string",
    "observations": [{"statement": "string", "evidence_ids": ["string"]}],
    "related_events": [{"statement": "string", "evidence_ids": ["string"]}],
    "hypotheses": [{
        "title": "string",
        "confidence": "number from 0 to 1",
        "supporting_evidence_ids": ["string"],
        "contradicting_evidence_ids": ["string"],
    }],
    "recommended_actions": [{
        "action": "string",
        "owner": "QA|Microbiology|MSAT|Manufacturing|Maintenance",
        "priority": "low|medium|high|critical",
        "requires_human_approval": "boolean",
        "evidence_ids": ["string"],
    }],
    "teams_to_notify": ["string"],
}


class ReasoningProvider(Protocol):
    provider_id: str

    def complete(self, request: dict[str, Any]) -> dict[str, Any]: ...


def build_request(visible_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol": "manufacturing-os.famotidine-replay.v1",
        "system": AGENT_SYSTEM_PROMPT,
        "objective": (
            "Detect and correlate the evolving manufacturing signal, assign an evidence-supported "
            "triage level, rank hypotheses, and recommend concrete human-governed actions."
        ),
        "visible_state": visible_state,
        "valid_evidence_ids": sorted(visible_state["evidence_by_id"]),
        "output_schema": OUTPUT_SCHEMA,
    }


def _record_ids(records: list[dict[str, Any]]) -> set[str]:
    keys = ("id", "batch_id", "deviation_id", "work_order", "complaint_id", "incident_id")
    return {
        str(record[key])
        for record in records
        for key in keys
        if record.get(key)
    }


def deterministic_assessment(state: dict[str, Any]) -> dict[str, Any]:
    labs = state["lab_results"]
    deviations = state["deviations"]
    process = state["process_events"]
    maintenance = state["maintenance"]
    complaints = state["complaints"]
    memory = state["incident_memory"]
    product_by_batch = {item["batch_id"]: item.get("product") for item in state.get("batches", [])}
    failing = [item for item in labs if item["status"] in {"action_limit", "out_of_specification"}]
    bioburden = [
        item for item in failing
        if item["test"] == "bioburden" and product_by_batch.get(item["batch_id"]) == "Famotidine Injection, USP"
    ]
    affected_batch_ids = {item["batch_id"] for item in bioburden}
    passing_final = [
        item for item in labs
        if item["sample_type"] == "finished product" and item["status"] == "pass"
        and item["batch_id"] in affected_batch_ids
    ]
    complaints = [item for item in complaints if item.get("product") == "Famotidine Injection, USP"]
    organism = next((item for item in labs if item["test"] == "organism identification"), None)
    reserve_oos = next((item for item in labs if item["sample_type"] == "finished-product reserve"), None)
    batches = sorted({item["batch_id"] for item in bioburden})

    if reserve_oos or organism:
        severity, triage = "critical", "L3"
    elif len(bioburden) >= 2:
        severity, triage = "high", "L3"
    elif len(bioburden) == 1:
        severity, triage = "medium", "L2"
    else:
        severity, triage = "low", "L1"

    observations: list[dict[str, Any]] = []
    related: list[dict[str, Any]] = []
    if bioburden:
        latest = bioburden[-1]
        observations.append({
            "statement": f"Bioburden result {latest['result']} exceeds {latest['limit']} for batch {latest['batch_id']}.",
            "evidence_ids": [latest["id"]],
        })
    if passing_final:
        observations.append({
            "statement": "Available finished-product tests are within their reconstructed specifications; this does not resolve the upstream signal.",
            "evidence_ids": [item["id"] for item in passing_final],
        })
    if len(bioburden) >= 2:
        related.append({
            "statement": f"{len(bioburden)} action-limit excursions affect {len(batches)} batches at the same process stage.",
            "evidence_ids": [item["id"] for item in bioburden],
        })
    if organism:
        observations.append({
            "statement": "Microbiology confirmed gram-negative organism information with confluent growth.",
            "evidence_ids": [organism["id"]],
        })
    if reserve_oos:
        observations.append({
            "statement": "Reserve-sample endotoxin testing is out of specification.",
            "evidence_ids": [reserve_oos["id"]],
        })
    if memory and bioburden:
        related.append({
            "statement": "Incident memory contains a similar pattern: elevated upstream bioburden with a gram-negative isolate despite passing final testing.",
            "evidence_ids": [memory[0]["incident_id"]],
        })

    fail_ids = [item["id"] for item in bioburden]
    pass_ids = [item["id"] for item in passing_final]
    process_ids = [item["id"] for item in process if item.get("batch_id") in batches]
    maintenance_ids = [item["work_order"] for item in maintenance]
    hypotheses = []
    if bioburden:
        hypotheses.append({
            "title": "Upstream microbiological control failure",
            "confidence": 0.86 if organism else (0.68 if len(bioburden) >= 2 else 0.43),
            "supporting_evidence_ids": fail_ids + ([organism["id"]] if organism else []),
            "contradicting_evidence_ids": pass_ids,
        })
        hypotheses.append({
            "title": "Localized sampling or laboratory anomaly",
            "confidence": 0.14 if len(bioburden) >= 2 else 0.34,
            "supporting_evidence_ids": fail_ids[-1:],
            "contradicting_evidence_ids": fail_ids[:-1],
        })
        if process_ids or maintenance_ids:
            hypotheses.append({
                "title": "Equipment hold or sanitization condition contributed",
                "confidence": 0.48 if len(bioburden) >= 2 else 0.27,
                "supporting_evidence_ids": process_ids + maintenance_ids,
                "contradicting_evidence_ids": [],
            })

    actions: list[dict[str, Any]] = []
    if bioburden:
        actions.extend([
            {
                "action": "Identify the organism and compare morphology across affected samples.",
                "owner": "Microbiology", "priority": severity,
                "requires_human_approval": False, "evidence_ids": fail_ids,
            },
            {
                "action": "Review the affected process trajectory against successful batches.",
                "owner": "MSAT", "priority": "high" if len(bioburden) >= 2 else "medium",
                "requires_human_approval": False, "evidence_ids": fail_ids + process_ids,
            },
        ])
    if len(bioburden) >= 2:
        actions.extend([
            {
                "action": "Expand the investigation scope to batches sharing the process stage and relevant conditions.",
                "owner": "QA", "priority": "high", "requires_human_approval": True,
                "evidence_ids": fail_ids + [item["deviation_id"] for item in deviations],
            },
            {
                "action": "Hold disposition of in-scope batches pending authorized QA assessment.",
                "owner": "QA", "priority": severity, "requires_human_approval": True,
                "evidence_ids": fail_ids,
            },
        ])
    if organism:
        actions.append({
            "action": "Perform a documented endotoxin-risk assessment and define expanded sampling with QA approval.",
            "owner": "QA", "priority": "critical", "requires_human_approval": True,
            "evidence_ids": [organism["id"], *fail_ids],
        })
    if complaints:
        actions.append({
            "action": "Reconcile complaint, distribution, reserve-sample, and manufacturing scope.",
            "owner": "QA", "priority": "critical", "requires_human_approval": True,
            "evidence_ids": [item["complaint_id"] for item in complaints],
        })

    summary = {
        "low": "No manufacturing-quality signal requires escalation in the currently visible evidence.",
        "medium": "One upstream bioburden excursion requires technical investigation; broader recurrence is not yet established.",
        "high": "A recurring upstream bioburden pattern spans multiple batches and warrants broader QA-led investigation.",
        "critical": "Accumulated microbiological evidence raises a potentially significant product-quality risk requiring urgent QA-led assessment.",
    }[severity]
    return {
        "severity": severity,
        "triage_level": triage,
        "summary": summary,
        "observations": observations,
        "related_events": related,
        "hypotheses": hypotheses,
        "recommended_actions": actions,
        "teams_to_notify": sorted({item["owner"] for item in actions}),
    }


def validate_assessment(value: dict[str, Any], valid_ids: set[str]) -> dict[str, Any]:
    """Fail closed on shape and remove every reference the agent could not have seen."""
    fallback = {
        "severity": "low", "triage_level": "L1", "summary": "No valid assessment returned.",
        "observations": [], "related_events": [], "hypotheses": [],
        "recommended_actions": [], "teams_to_notify": [],
    }
    if not isinstance(value, dict):
        return fallback
    result = deepcopy(fallback)
    if value.get("severity") in SEVERITY_ORDER:
        result["severity"] = value["severity"]
    if value.get("triage_level") in {"L1", "L2", "L3"}:
        result["triage_level"] = value["triage_level"]
    if isinstance(value.get("summary"), str):
        result["summary"] = value["summary"]

    def valid_refs(item: dict[str, Any], key: str) -> list[str]:
        refs = item.get(key, [])
        return [str(ref) for ref in refs if str(ref) in valid_ids] if isinstance(refs, list) else []

    for key in ("observations", "related_events"):
        for item in value.get(key, []) if isinstance(value.get(key), list) else []:
            if isinstance(item, dict) and isinstance(item.get("statement"), str):
                refs = valid_refs(item, "evidence_ids")
                if refs:
                    result[key].append({"statement": item["statement"], "evidence_ids": refs})
    for item in value.get("hypotheses", []) if isinstance(value.get("hypotheses"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            continue
        result["hypotheses"].append({
            "title": item["title"],
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 0)))),
            "supporting_evidence_ids": valid_refs(item, "supporting_evidence_ids"),
            "contradicting_evidence_ids": valid_refs(item, "contradicting_evidence_ids"),
        })
    for item in value.get("recommended_actions", []) if isinstance(value.get("recommended_actions"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("action"), str):
            continue
        result["recommended_actions"].append({
            "action": item["action"],
            "owner": str(item.get("owner", "QA")),
            "priority": item.get("priority") if item.get("priority") in SEVERITY_ORDER else "medium",
            "requires_human_approval": bool(item.get("requires_human_approval", True)),
            "evidence_ids": valid_refs(item, "evidence_ids"),
        })
    teams = value.get("teams_to_notify", [])
    result["teams_to_notify"] = [str(team) for team in teams if team] if isinstance(teams, list) else []
    return result


class ManufacturingAgent:
    def __init__(self, provider: ReasoningProvider | None = None) -> None:
        self.provider = provider

    def assess(self, visible_state: dict[str, Any], *, live: bool = False) -> dict[str, Any]:
        valid_ids = set(visible_state["evidence_by_id"])
        provider_id = "deterministic.fallback"
        fallback_reason = None
        value = deterministic_assessment(visible_state)
        if live and self.provider is not None:
            try:
                value = self.provider.complete(build_request(visible_state))
                provider_id = self.provider.provider_id
            except Exception as exc:  # demo must remain available when provider fails
                fallback_reason = str(exc)
        result = validate_assessment(value, valid_ids)
        result["provider_id"] = provider_id
        result["fallback_reason"] = fallback_reason
        result["evidence_cutoff"] = visible_state["as_of"]
        result["visible_evidence_count"] = len(valid_ids)
        return result


def prompt_markdown() -> str:
    return "# Manufacturing Agent prompt\n\n```text\n" + AGENT_SYSTEM_PROMPT + "\n```\n\n## Output contract\n\n```json\n" + __import__("json").dumps(OUTPUT_SCHEMA, indent=2) + "\n```\n"
