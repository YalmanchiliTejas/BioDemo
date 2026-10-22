from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def build_tasks() -> list[dict]:
    objectives = [
        ("CHO-01", "Identify experiments, reactors, measurements, units and frequencies from raw workbooks without manual tags."),
        ("CHO-02", "Link measurements into an analysis-ready representation of each cultivation."),
        ("CHO-03", "Identify measurements worth investigating for variation in cultivation performance, citing source data and uncertainty."),
        ("CHO-04", "Compare cultivations and describe operating differences and abnormal trends with evidence."),
        ("CHO-05", "Repeat interpretation under controlled source-format perturbations."),
    ]
    tasks = [{"id": identifier, "objective": objective} for identifier, objective in objectives]
    (ROOT / "tasks").mkdir(exist_ok=True)
    (ROOT / "tasks/tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    return tasks
