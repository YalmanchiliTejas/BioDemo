from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .generator import DEFAULT_OUTPUT
from .store import SimulationStore


CASE_SPECS = [
    ("SME-01", "SYN-0020", "lab_results", "finished product"),
    ("SME-02", "SYN-0001", "lab_results", "upstream process sample"),
    ("SME-03", "BATCH-075", "lab_results", "upstream process sample"),
    ("SME-04", "BATCH-075", "lab_results", "finished product"),
    ("SME-05", "BATCH-084", "lab_results", "upstream process sample"),
    ("SME-06", "BATCH-099", "environmental_monitoring", "relative microbial environmental signal"),
    ("SME-07", "BATCH-099", "lab_results", "upstream process sample"),
    ("SME-08", "SYN-0090", "process_events", "equipment_pressure_ratio"),
    ("SME-09", "SYN-0091", "deviations", "procedure"),
    ("SME-10", "BATCH-075", "lab_results", "finished-product reserve"),
]


def _matches(event: dict[str, Any], value: str) -> bool:
    return value in {
        str(event.get("sample_type")), str(event.get("test_name")),
        str(event.get("parameter")), str(event.get("category")),
    }


def generate_sme_package(database: Path | None = None, output_dir: Path = DEFAULT_OUTPUT) -> None:
    store = SimulationStore(database)
    sections = [
        "# Blind SME review cases", "",
        "These cases intentionally omit simulation labels and future outcomes. Reviewers should answer before opening the benchmark ground truth.", "",
    ]
    for case_id, batch_id, table, selector in CASE_SPECS:
        event = next(item for item in store.event_stream(batch_id) if item["_table"] == table and _matches(item, selector))
        state = store.state_at(event["_timestamp"], current_batch_id=batch_id, context="full_os", current_event=event)
        compact = {
            "timestamp": state["timestamp"], "current_batch": state["current_batch"],
            "new_events": state["new_events"],
            "recent_lab_results": state["recent_lab_results"][-8:],
            "deviations": state["deviations"][-5:],
            "maintenance": state["maintenance"][-5:],
            "environmental_monitoring": state["environmental_monitoring"][-8:],
            "process_events": state["process_events"][-8:],
            "incident_memory": state["incident_memory"][-2:],
        }
        sections.extend([
            f"## {case_id}", "", "```json", json.dumps(compact, indent=2), "```", "",
            "1. Would you investigate?", "2. What severity would you assign?",
            "3. L1, L2, or L3?", "4. What evidence would you request?",
            "5. What teams should be involved?", "6. Is anything unrealistic?",
            "7. What action would you take next?", "",
        ])
    (output_dir / "sme_review_cases.md").write_text("\n".join(sections), encoding="utf-8")
    fields = [
        "case_id", "reviewer_role", "investigate_yes_no", "severity", "triage_level",
        "recommended_actions", "realism_score_1_5", "comments",
    ]
    with (output_dir / "sme_review_template.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case_id, *_ in CASE_SPECS:
            writer.writerow({"case_id": case_id})
