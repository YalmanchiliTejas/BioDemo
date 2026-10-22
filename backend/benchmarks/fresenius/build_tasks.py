from __future__ import annotations

import json
from pathlib import Path

from .temporal_replay import FROZEN_AGENT_DATA


ROOT = Path(__file__).resolve().parent


def build_tasks() -> list[dict]:
    data = json.loads(FROZEN_AGENT_DATA.read_text(encoding="utf-8"))
    labels = json.loads((FROZEN_AGENT_DATA.parent / "benchmark_ground_truth.json").read_text(encoding="utf-8"))
    incident_batches = {row["benchmark_batch_id"] for row in labels["batch_labels"] if row["true_incident"]}
    abnormal = sorted((row for row in data["lab_results"]
                       if row.get("batch_id") in incident_batches and row.get("status") == "action"),
                      key=lambda row: row["available_at"])
    if len(abnormal) < 3:
        raise ValueError("frozen simulation lacks three chronological abnormality checkpoints")
    first, second, third = abnormal[:3]
    unrelated = min((row for row in data["lab_results"] if row.get("status") == "action"
                     and row.get("batch_id") not in incident_batches), key=lambda row: row["available_at"])
    tasks = [
        {"id": "FRE-01", "objective": "Examine available manufacturing records and identify significant abnormalities requiring investigation.", "as_of": third["available_at"]},
        {"id": "FRE-02", "objective": f"Investigate newly available laboratory result {first['result_id']}; assess scope, plausible explanations and human-reviewed next steps.", "as_of": first["available_at"], "trigger_record_id": first["result_id"]},
        {"id": "FRE-03", "objective": f"Reassess available evidence across batches after new laboratory result {third['result_id']}.", "as_of": third["available_at"], "trigger_record_id": third["result_id"]},
        {"id": "FRE-04", "objective": f"For newly available laboratory result {second['result_id']}, identify actions possible now, missing physical evidence and decisions for human review.", "as_of": second["available_at"], "trigger_record_id": second["result_id"]},
        {"id": "FRE-05", "objective": f"Investigate newly available laboratory result {unrelated['result_id']}; assess scope and evidence for any related-batch conclusions.", "as_of": unrelated["available_at"], "trigger_record_id": unrelated["result_id"]},
    ]
    (ROOT / "tasks").mkdir(exist_ok=True)
    (ROOT / "tasks/tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    return tasks
