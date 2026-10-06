from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from benchmark.application.dynamic_agents import reasoning_provider_from_env

from .agent import ManufacturingAgent


DATA_PATH = Path(__file__).with_name("data") / "fresenius_famotidine_demo.json"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class IncidentDemoService:
    def __init__(self, dataset_path: Path = DATA_PATH, *, provider=None) -> None:
        self.dataset_path = dataset_path
        self.data = json.loads(dataset_path.read_text(encoding="utf-8"))
        repository = Path(__file__).resolve().parents[2]
        self.agent = ManufacturingAgent(provider if provider is not None else reasoning_provider_from_env(repository))
        self._lock = RLock()
        self._completed_tasks: dict[str, str] = {}

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self._completed_tasks.clear()
        return {"status": "reset", "tasks": self.tasks()}

    def tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            completed = dict(self._completed_tasks)
        tasks = deepcopy(self.data["tasks"])
        for task in tasks:
            if task["task_id"] in completed:
                task["status"] = "complete"
                task["observation"] = completed[task["task_id"]]
        return tasks

    def complete_task(self, task_id: str, observation: str) -> dict[str, Any]:
        task = next((item for item in self.data["tasks"] if item["task_id"] == task_id), None)
        if task is None:
            raise KeyError(task_id)
        note = observation.strip() or str(task.get("default_observation", "Task completed; evidence attached."))
        with self._lock:
            self._completed_tasks[task_id] = note
        return next(item for item in self.tasks() if item["task_id"] == task_id)

    def overview(self) -> dict[str, Any]:
        return {
            "metadata": self.data["metadata"],
            "public_facts": self.data["public_facts"],
            "plant_health": {
                "active_batches": 4,
                "open_investigations": 3,
                "high_risk_events": 1,
                "equipment_alerts": 2,
            },
            "risk_feed": [
                {
                    "risk": "high", "product": "Famotidine Injection", "batch_id": "6133156",
                    "title": "Repeated bioburden signal requires investigation",
                    "signals": ["3 related events", "2 historical similarities", "1 unresolved investigation"],
                },
                {
                    "risk": "low", "product": "Electrolyte Injection", "batch_id": "SYN-8821",
                    "title": "Short historian communication gap", "signals": ["signal recovered", "no process excursion"],
                },
                {
                    "risk": "normal", "product": "Saline Injection", "batch_id": "SYN-8844",
                    "title": "Batch progressing within operating ranges", "signals": ["release testing on schedule"],
                },
            ],
            "replay_events": self.data["replay_events"],
            "tasks": self.tasks(),
            "comparison": self.comparison(),
            "architecture": {
                "systems": ["MES", "LIMS", "QMS", "CMMS", "Historian", "Complaints"],
                "agent": "One orchestrating Manufacturing Agent",
                "loop": ["Detect", "Correlate", "Triage", "Investigate", "Coordinate", "Learn"],
            },
        }

    def comparison(self) -> dict[str, Any]:
        anchors = self.data["metric_anchors"]
        start = _time(anchors["recurrence_signal_at"])
        traditional_minutes = int((_time(anchors["traditional_pattern_at"]) - start).total_seconds() / 60)
        os_minutes = int((_time(anchors["os_pattern_at"]) - start).total_seconds() / 60)
        return {
            "label": "SIMULATED DEMO RESULTS",
            "without_os": {
                "pattern_recognition_minutes": traditional_minutes,
                "pattern_recognition_display": f"{traditional_minutes // 60} hours",
                "systems_manually_reviewed": len(anchors["systems"]),
                "human_handoffs": anchors["traditional_handoffs"],
                "initial_related_batches": anchors["traditional_initial_batches"],
            },
            "with_os": {
                "pattern_recognition_minutes": os_minutes,
                "pattern_recognition_display": f"{os_minutes} minutes",
                "systems_automatically_searched": len(anchors["systems"]),
                "human_handoffs": anchors["os_handoffs"],
                "historical_events_surfaced": anchors["os_historical_events"],
                "initial_related_batches": anchors["os_initial_batches"],
            },
            "conclusion": "The OS surfaced evidence for broader investigation earlier in this reconstructed scenario.",
        }

    def visible_state(self, cursor: int) -> dict[str, Any]:
        events = self.data["replay_events"]
        cursor = max(0, min(cursor, len(events)))
        visible_events = [
            event for event in events[:cursor]
            if not event.get("traditional_only") and not event.get("outcome_only") and not event.get("os_only")
        ]
        cutoff = visible_events[-1]["timestamp"] if visible_events else events[0]["timestamp"]
        completed = {task["task_id"] for task in self.tasks() if task["status"] == "complete"}

        def visible(record: dict[str, Any]) -> bool:
            timestamp = record.get("timestamp") or record.get("start_time")
            if timestamp and _time(timestamp) > _time(cutoff):
                return False
            gate = record.get("requires_task")
            return not gate or gate in completed

        visible_batches = []
        for item in self.data["batches"]:
            if not visible(item):
                continue
            batch = deepcopy(item)
            # Final recall/disposition fields belong to the retrospective public record,
            # not the evidence available to the agent during the replay.
            batch["status"] = "in_process" if _time(cutoff) <= _time(batch["end_time"]) else "manufactured"
            batch["disposition"] = "not_available_at_current_cutoff"
            batch["provenance"] = "synthetic_factory_signal"
            visible_batches.append(batch)
        state = {
            "as_of": cutoff,
            "current_event": visible_events[-1] if visible_events else None,
            "recent_events": visible_events,
            "batches": visible_batches,
            "lab_results": [item for item in self.data["lab_results"] if visible(item)],
            "process_events": [item for item in self.data["process_events"] if visible(item)],
            "deviations": [item for item in self.data["deviations"] if visible(item)],
            "maintenance": [item for item in self.data["maintenance"] if visible(item)],
            "complaints": [item for item in self.data["complaints"] if visible(item)],
            "incident_memory": self.data["incident_memory"],
            "completed_human_tasks": [task for task in self.tasks() if task["status"] == "complete"],
        }
        records = [
            *state["batches"], *state["lab_results"], *state["process_events"],
            *state["deviations"], *state["maintenance"], *state["complaints"],
            *state["incident_memory"],
        ]
        evidence: dict[str, dict[str, Any]] = {}
        for record in records:
            for key in ("id", "batch_id", "deviation_id", "work_order", "complaint_id", "incident_id"):
                if record.get(key):
                    evidence[str(record[key])] = record
                    break
        state["evidence_by_id"] = evidence
        return state

    def assessment(self, cursor: int, *, live: bool = False) -> dict[str, Any]:
        state = self.visible_state(cursor)
        return {
            "assessment": self.agent.assess(state, live=live),
            "visible_state": state,
            "tasks": self.tasks(),
        }

    def future_match(self) -> dict[str, Any]:
        memory = self.data["incident_memory"][0]
        return {
            "status": "similar_event_pattern_identified",
            "similarity": 0.89,
            "memory": memory,
            "new_signal": {
                "batch_id": "SYN-FUTURE-01",
                "symptoms": ["elevated pre-filtration bioburden", "gram-negative morphology"],
                "provenance": "synthetic_factory_signal",
            },
            "message": "Similar event pattern identified. Retrieve the prior investigation, verify current evidence, and do not assume the same root cause.",
        }
