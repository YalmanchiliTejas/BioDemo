from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol


OUTPUT_SCHEMA = {
    "severity": "NORMAL|LOW|MEDIUM|HIGH|CRITICAL",
    "triage_level": "NONE|L1|L2|L3",
    "summary": "string",
    "evidence_ids": ["string"],
    "hypotheses": [{
        "hypothesis": "string", "confidence": "number 0..1",
        "supporting_evidence_ids": ["string"], "contradicting_evidence_ids": ["string"],
    }],
    "recommended_actions": ["string"], "teams_to_notify": ["string"],
    "related_batch_ids": ["string"],
}

SYSTEM_PROMPT = """You are one bounded pharmaceutical Manufacturing OS agent. Use only the
time-bounded structured state. Never use future outcomes or simulation labels. Distinguish an
observation from a hypothesis, cite only visible evidence IDs, and escalate proportionally. You may
recommend investigation or containment but may not release, reject, disposition, or recall a GMP
batch. Return strict JSON matching the supplied schema."""


class Provider(Protocol):
    provider_id: str
    def complete(self, request: dict[str, Any]) -> dict[str, Any]: ...


def _all_labs(state: dict[str, Any]) -> list[dict[str, Any]]:
    labs = list(state.get("recent_lab_results", []))
    event = state.get("new_events", [None])[-1] if state.get("new_events") else None
    if event and event.get("_table") == "lab_results" and not any(item["_evidence_id"] == event["_evidence_id"] for item in labs):
        labs.append(event)
    return labs


def assess_contextual(state: dict[str, Any]) -> dict[str, Any]:
    labs = _all_labs(state)
    current_batch = state.get("current_batch") or {}
    current_event = state.get("new_events", [None])[-1] if state.get("new_events") else None
    product = current_batch.get("product")
    visible_action_bio = [
        row for row in labs
        if row.get("test_name") == "relative_bioburden_signal" and row.get("status") == "action"
        and (not product or row.get("batch_id") == current_batch.get("batch_id") or row.get("_product") == product)
    ]
    # Historical abnormalities are used only after the current batch presents a related
    # trigger. This avoids converting background history into a perpetual false alarm.
    current_action = [row for row in visible_action_bio if row.get("batch_id") == current_batch.get("batch_id")]
    action_bio = visible_action_bio if current_action else []
    reserve_oos = [
        row for row in labs
        if row.get("sample_type") == "finished-product reserve"
        and row.get("status") == "out_of_specification"
        and row.get("batch_id") == current_batch.get("batch_id")
    ]
    gram_negative = [
        row for row in state.get("environmental_monitoring", [])
        if "gram-negative" in str(row.get("organism", "")).lower()
        and row.get("batch_id") == current_batch.get("batch_id")
    ]
    memory = state.get("incident_memory", [])
    process_rows = list(state.get("process_events", []))
    deviation_rows = list(state.get("deviations", []))
    if current_event and current_event.get("_table") == "process_events" and not any(row["_evidence_id"] == current_event["_evidence_id"] for row in process_rows):
        process_rows.append(current_event)
    if current_event and current_event.get("_table") == "deviations" and not any(row["_evidence_id"] == current_event["_evidence_id"] for row in deviation_rows):
        deviation_rows.append(current_event)
    process_high = [row for row in process_rows if row.get("severity") == "high" and row.get("batch_id") == current_batch.get("batch_id")]
    recurring_devs = [row for row in deviation_rows if row.get("recurrence_flag") and row.get("batch_id") == current_batch.get("batch_id")]
    related_batches = sorted({row["batch_id"] for row in action_bio})
    evidence = [row["_evidence_id"] for row in action_bio]
    hypotheses: list[dict[str, Any]] = []
    actions: list[str] = []
    teams: list[str] = []

    if reserve_oos or gram_negative:
        severity, triage = "CRITICAL", "L3"
        summary = "Microbiological and later product evidence require urgent cross-functional assessment."
    elif len(related_batches) >= 2 or (current_action and memory):
        severity, triage = "HIGH", "L3"
        summary = (
            "A current upstream signal matches a retrieved manufacturing-memory pattern."
            if len(related_batches) < 2 else
            "Repeated upstream microbiological action signals span related batches."
        )
    elif action_bio:
        severity, triage = "MEDIUM", "L2"
        summary = "An upstream microbiological action signal requires investigation; recurrence is not yet established."
    elif recurring_devs:
        severity, triage = "HIGH", "L3"
        summary = "A recurring deviation suggests the prior corrective action may be ineffective."
    elif process_high:
        severity, triage = "MEDIUM", "L2"
        summary = "An equipment/process anomaly requires technical review; downstream quality evidence is currently benign."
    else:
        if current_event and current_event.get("status") == "alert":
            severity, triage, summary = "LOW", "L1", "An isolated alert should be monitored proportionally."
            evidence = [current_event["_evidence_id"]]
        else:
            severity, triage, summary = "NORMAL", "NONE", "No currently visible evidence supports escalation."

    if action_bio:
        contradicting = [row["_evidence_id"] for row in labs if row.get("sample_type") == "finished product" and row.get("status") == "pass"]
        hypotheses.extend([
            {"hypothesis": "upstream microbiological control", "confidence": .78 if len(related_batches) >= 2 else .48,
             "supporting_evidence_ids": evidence + [row["_evidence_id"] for row in gram_negative],
             "contradicting_evidence_ids": contradicting},
            {"hypothesis": "sampling or laboratory anomaly", "confidence": .16 if len(related_batches) >= 2 else .35,
             "supporting_evidence_ids": evidence[-1:], "contradicting_evidence_ids": evidence[:-1]},
        ])
        actions.extend(["organism identification", "compare related batches", "QA scope assessment"])
        teams.extend(["QA", "Microbiology", "MSAT"])
        if memory:
            memory_id = memory[-1]["_evidence_id"]
            evidence.append(memory_id)
            hypotheses.append({
                "hypothesis": "historical pattern recurrence", "confidence": .58,
                "supporting_evidence_ids": [current_action[-1]["_evidence_id"], memory_id],
                "contradicting_evidence_ids": [],
            })
    if process_high:
        item = process_high[-1]
        evidence.append(item["_evidence_id"])
        hypotheses.append({"hypothesis": "equipment pressure control", "confidence": .67,
                           "supporting_evidence_ids": [item["_evidence_id"]], "contradicting_evidence_ids": []})
        actions.extend(["equipment inspection", "process trajectory review"])
        teams.extend(["Maintenance", "MSAT"])
    if recurring_devs:
        item = recurring_devs[-1]
        evidence.append(item["_evidence_id"])
        hypotheses.append({"hypothesis": "prior corrective action ineffective", "confidence": .71,
                           "supporting_evidence_ids": [item["_evidence_id"]], "contradicting_evidence_ids": []})
        actions.extend(["review prior CAPA", "effectiveness check"])
        teams.extend(["QA", "Manufacturing"])
    if reserve_oos:
        evidence.extend(row["_evidence_id"] for row in reserve_oos)
    if gram_negative:
        evidence.extend(row["_evidence_id"] for row in gram_negative)
    return {
        "severity": severity, "triage_level": triage, "summary": summary,
        "evidence_ids": list(dict.fromkeys(evidence)), "hypotheses": hypotheses,
        "recommended_actions": list(dict.fromkeys(actions)), "teams_to_notify": sorted(set(teams)),
        "related_batch_ids": related_batches or ([current_batch["batch_id"]] if current_batch else []),
    }


def build_request(state: dict[str, Any]) -> dict[str, Any]:
    return {"system": SYSTEM_PROMPT, "state": state, "output_schema": OUTPUT_SCHEMA}


def validate_output(value: Any, visible_ids: set[str]) -> tuple[dict[str, Any], dict[str, int]]:
    fallback = {
        "severity": "NORMAL", "triage_level": "NONE", "summary": "No valid assessment returned.",
        "evidence_ids": [], "hypotheses": [], "recommended_actions": [],
        "teams_to_notify": [], "related_batch_ids": [],
    }
    if not isinstance(value, dict):
        return fallback, {"cited": 0, "valid": 0, "stripped": 0}
    out = deepcopy(fallback)
    if value.get("severity") in {"NORMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        out["severity"] = value["severity"]
    if value.get("triage_level") in {"NONE", "L1", "L2", "L3"}:
        out["triage_level"] = value["triage_level"]
    if isinstance(value.get("summary"), str):
        out["summary"] = value["summary"]
    cited = 0
    valid = 0
    def refs(items: Any) -> list[str]:
        nonlocal cited, valid
        if not isinstance(items, list):
            return []
        cited += len(items)
        kept = [str(item) for item in items if str(item) in visible_ids]
        valid += len(kept)
        return kept
    out["evidence_ids"] = refs(value.get("evidence_ids"))
    for hypothesis in value.get("hypotheses", []) if isinstance(value.get("hypotheses"), list) else []:
        if not isinstance(hypothesis, dict) or not isinstance(hypothesis.get("hypothesis"), str):
            continue
        out["hypotheses"].append({
            "hypothesis": hypothesis["hypothesis"],
            "confidence": max(0.0, min(1.0, float(hypothesis.get("confidence", 0)))),
            "supporting_evidence_ids": refs(hypothesis.get("supporting_evidence_ids")),
            "contradicting_evidence_ids": refs(hypothesis.get("contradicting_evidence_ids")),
        })
    for key in ("recommended_actions", "teams_to_notify", "related_batch_ids"):
        if isinstance(value.get(key), list):
            out[key] = [str(item) for item in value[key]]
    return out, {"cited": cited, "valid": valid, "stripped": cited - valid}


class BenchmarkAgent:
    def __init__(self, provider: Provider | None = None) -> None:
        self.provider = provider

    def assess(self, state: dict[str, Any], *, live: bool = False) -> tuple[dict[str, Any], dict[str, int]]:
        raw = assess_contextual(state)
        provider_id = "contextual.deterministic"
        if live and self.provider:
            raw = self.provider.complete(build_request(state))
            provider_id = self.provider.provider_id
        output, audit = validate_output(raw, set(state["visible_evidence_ids"]))
        output["provider_id"] = provider_id
        return output, audit
