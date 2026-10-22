from __future__ import annotations

import json
from pathlib import Path

from src.data.temporal_store import TemporalFactoryStore

from .temporal_replay import FROZEN_AGENT_DATA


def evaluate(output: dict, as_of: str) -> dict:
    """Objective extraction scores only; no root-cause score from synthetic labels."""
    visible = TemporalFactoryStore(FROZEN_AGENT_DATA).session(as_of=as_of).records()
    ground = json.loads((FROZEN_AGENT_DATA.parent / "benchmark_ground_truth.json").read_text(encoding="utf-8"))
    incident_batches = {row["benchmark_batch_id"] for row in ground["batch_labels"] if row["true_incident"]}
    expected = {row["_evidence_id"] for row in visible}
    extracted = {row.get("record_id") for row in output["records"] if row.get("record_id")}
    correct = expected & extracted
    citation_rows = [row for row in output["records"] if row.get("record_id")]
    grounded = sum(row["record_id"] in expected for row in citation_rows)
    critical = {row["_evidence_id"] for row in visible if row["_table"] == "lab_results"
                and row.get("batch_id") in incident_batches and row.get("status") in {"action", "out_of_specification"}}
    relevant_retrieved = critical & extracted
    analysis = output.get("analysis")
    cited = set(analysis.get("evidence_ids", [])) if isinstance(analysis, dict) else set()
    retrieved = set(output.get("retrieved_record_ids", []))
    return {"visible_canonical_records": len(expected), "extracted_unique_ids": len(extracted),
            "entity_recall": len(correct) / len(expected) if expected else None,
            "entity_precision": len(correct) / len(extracted) if extracted else None,
            "source_grounding_fraction": grounded / len(citation_rows) if citation_rows else None,
            "future_id_leakage": len(extracted - expected),
            "critical_lab_ids_visible": len(critical),
            "critical_lab_recall": len(relevant_retrieved) / len(critical) if critical else None,
            "critical_lab_precision_among_all_extracted": len(relevant_retrieved) / len(extracted) if extracted and critical else None,
            "irrelevant_extraction_fraction_for_critical_lab_task": 1-len(relevant_retrieved)/len(extracted) if extracted and critical else None,
            "retrieved_critical_lab_recall": len(critical & retrieved)/len(critical) if critical and retrieved else None,
            "cited_critical_lab_recall": len(critical & cited)/len(critical) if critical and cited else None,
            "analysis_citation_precision": len(cited & expected)/len(cited) if cited else None,
            "analysis_future_or_hallucinated_ids": sorted(cited - expected),
            "hypotheses_scored": False, "reason": "No verified root-cause labels are applied to free-text hypotheses."}
