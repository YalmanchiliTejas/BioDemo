from __future__ import annotations

from typing import Any


def _output(severity: str = "NORMAL", triage: str = "NONE", summary: str = "No rule fired.") -> dict[str, Any]:
    return {
        "severity": severity, "triage_level": triage, "summary": summary,
        "evidence_ids": [], "hypotheses": [], "recommended_actions": [],
        "teams_to_notify": [], "related_batch_ids": [],
    }


def assess_rules(state: dict[str, Any]) -> dict[str, Any]:
    """Local-event baseline: thresholds and explicit record severity only."""
    result = _output()
    event = state["new_events"][-1] if state.get("new_events") else None
    if not event:
        return result
    evidence_id = event["_evidence_id"]
    table = event["_table"]
    if table == "lab_results" and event.get("status") in {"action", "out_of_specification"}:
        result.update(
            severity="MEDIUM", triage_level="L2",
            summary="A local laboratory threshold requires investigation.",
            evidence_ids=[evidence_id],
            hypotheses=[{"hypothesis": "local laboratory or process cause", "confidence": .45,
                         "supporting_evidence_ids": [evidence_id], "contradicting_evidence_ids": []}],
            recommended_actions=["review laboratory result", "open local deviation"],
            teams_to_notify=["QA"], related_batch_ids=[event.get("batch_id")],
        )
    elif table == "process_events" and event.get("severity") == "high":
        result.update(
            severity="MEDIUM", triage_level="L2", summary="A local equipment threshold requires review.",
            evidence_ids=[evidence_id], hypotheses=[{
                "hypothesis": "equipment pressure control", "confidence": .55,
                "supporting_evidence_ids": [evidence_id], "contradicting_evidence_ids": [],
            }], recommended_actions=["equipment inspection"], teams_to_notify=["Maintenance"],
            related_batch_ids=[event.get("batch_id")],
        )
    elif table == "deviations" and event.get("severity") == "high":
        result.update(
            severity="MEDIUM", triage_level="L2", summary="A high-severity deviation requires review.",
            evidence_ids=[evidence_id], recommended_actions=["review deviation"], teams_to_notify=["QA"],
            related_batch_ids=[event.get("batch_id")],
        )
    elif table == "lab_results" and event.get("status") == "alert":
        result.update(severity="LOW", triage_level="L1", summary="An isolated alert is monitored proportionally.", evidence_ids=[evidence_id])
    return result

