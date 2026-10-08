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
AGENT_DATA_PATH = Path(__file__).with_name("data") / "agent_data.json"
REPLAY_UI_PATH = Path(__file__).with_name("data") / "replay_ui.json"
PUBLIC_DATA_PATH = Path(__file__).with_name("data") / "public_ground_truth.json"
BENCHMARK_RESULTS_PATH = Path(__file__).resolve().parents[1] / "pharma_simulation" / "artifacts" / "benchmark_results.json"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class IncidentDemoService:
    def __init__(self, dataset_path: Path = DATA_PATH, *, provider=None) -> None:
        self.dataset_path = dataset_path
        agent_path = AGENT_DATA_PATH if dataset_path == DATA_PATH and AGENT_DATA_PATH.exists() else dataset_path
        self.agent_data = json.loads(agent_path.read_text(encoding="utf-8"))
        replay = json.loads(REPLAY_UI_PATH.read_text(encoding="utf-8"))
        public = json.loads(PUBLIC_DATA_PATH.read_text(encoding="utf-8"))
        self.data = self._ui_adapter(self.agent_data)
        self.data.update({
            "metadata": replay["metadata"], "tasks": replay["tasks"],
            "replay_events": replay["replay_events"], "public_facts": replay.get("public_facts", public["facts"]),
        })
        repository = Path(__file__).resolve().parents[2]
        self.agent = ManufacturingAgent(provider if provider is not None else reasoning_provider_from_env(repository))
        self._lock = RLock()
        self._completed_tasks: dict[str, str] = {}

    @staticmethod
    def _ui_adapter(agent_data: dict[str, Any]) -> dict[str, Any]:
        labs = []
        for row in agent_data["lab_results"]:
            item = deepcopy(row)
            item["id"] = item.pop("result_id")
            item["test"] = "bioburden" if item["test_name"] == "relative_bioburden_signal" else item["test_name"]
            item["result"] = item["categorical_result"] if item["categorical_result"] is not None else (
                "missing" if item["numerical_result"] is None else f"{item['numerical_result']:.2f} {item['unit']}"
            )
            item["limit"] = "1.00 normalized action limit" if item["action_limit"] is not None else (
                "1.00 normalized specification" if item["specification_limit"] is not None else "categorical"
            )
            item["status"] = "action_limit" if item["status"] == "action" else "pass" if item["status"] == "normal" else item["status"]
            labs.append(item)
        process = []
        for row in agent_data["process_events"]:
            item = deepcopy(row)
            item["id"] = item.pop("event_id")
            item["expected_range"] = f"{item['expected_low']}–{item['expected_high']}"
            process.append(item)
        deviations = []
        for row in agent_data["deviations"]:
            item = deepcopy(row)
            item["timestamp"] = item["opened_at"]
            deviations.append(item)
        maintenance = []
        for row in agent_data["maintenance"]:
            item = deepcopy(row)
            item["batch_id"] = item["linked_batch_id"]
            maintenance.append(item)
        return {
            "batches": deepcopy(agent_data["batches"]), "lab_results": labs,
            "process_events": process, "deviations": deviations,
            "maintenance": maintenance, "complaints": deepcopy(agent_data["complaints"]),
            "environmental_monitoring": deepcopy(agent_data.get("environmental_monitoring", [])),
            "operator_events": deepcopy(agent_data.get("operator_events", [])),
            "incident_memory": [],
        }

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
                    "risk": "high", "product": "Famotidine Injection", "batch_id": "BATCH-075",
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
        if BENCHMARK_RESULTS_PATH.exists():
            benchmark = json.loads(BENCHMARK_RESULTS_PATH.read_text(encoding="utf-8"))
            rules = benchmark["rules_baseline"]
            full = benchmark["ablations"]["D_full_OS_context"]

            def percent(value: float) -> str:
                return f"{value * 100:.1f}%"

            def minutes(value: float | None) -> str:
                return "n/a" if value is None else f"{value:.1f} min"

            return {
                "label": "SIMULATED BENCHMARK RESULT",
                "dataset_fingerprint": benchmark["dataset_fingerprint"],
                "without_os": {
                    "title": "RULES / LOCAL EVENT CONTEXT",
                    "metrics": [
                        ["Incident recall", percent(rules["incident_detection_recall"])],
                        ["Median time-to-detection", minutes(rules["median_time_to_detection_minutes"])],
                        ["Triage accuracy", percent(rules["triage_accuracy"])],
                        ["Investigation-scope recall", percent(rules["investigation_scope_recall"])],
                    ],
                },
                "with_os": {
                    "title": "FULL MANUFACTURING OS CONTEXT",
                    "metrics": [
                        ["Incident recall", percent(full["incident_detection_recall"])],
                        ["Median time-to-detection", minutes(full["median_time_to_detection_minutes"])],
                        ["Triage accuracy", percent(full["triage_accuracy"])],
                        ["Investigation-scope recall", percent(full["investigation_scope_recall"])],
                    ],
                },
                "conclusion": "The reconstructed OS surfaced the cross-batch risk pattern earlier in this simulation.",
            }

        return {
            "label": "SIMULATED BENCHMARK RESULT",
            "without_os": {
                "title": "RULES / LOCAL EVENT CONTEXT",
                "metrics": [["Benchmark", "Generate results first"]],
            },
            "with_os": {
                "title": "FULL MANUFACTURING OS CONTEXT",
                "metrics": [["Benchmark", "Generate results first"]],
            },
            "conclusion": "Run python generate_report.py to compute the frozen-dataset comparison.",
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
            if _time(cutoff) <= _time(batch["end_time"]):
                batch["status"], batch["disposition"] = "in_process", "pending"
            elif batch.get("disposition_time") and _time(cutoff) < _time(batch["disposition_time"]):
                batch["status"], batch["disposition"] = "quality_review", "pending"
            else:
                batch["status"], batch["disposition"] = "released", "released"
            batch.pop("disposition_time", None)
            batch.pop("first_ship_time", None)
            batch["provenance"] = "synthetic_factory_signal"
            visible_batches.append(batch)
        visible_deviations = []
        for item in self.data["deviations"]:
            if not visible(item):
                continue
            deviation = deepcopy(item)
            if deviation.get("closed_at") and _time(deviation["closed_at"]) > _time(cutoff):
                deviation["closed_at"] = None
                deviation["investigation_status"] = "open"
                deviation["root_cause"] = None
                deviation["capa"] = None
            visible_deviations.append(deviation)
        visible_labs = [item for item in self.data["lab_results"] if visible(item)]
        if "TASK-MICRO-01" in completed:
            visible_labs.append({
                "id": "LR-HUMAN-001", "batch_id": "BATCH-099", "timestamp": cutoff,
                "sample_collected_at": cutoff, "sample_type": "microbiology isolate",
                "test": "organism identification", "result": self._completed_tasks["TASK-MICRO-01"],
                "limit": "not applicable", "status": "identified",
                "organism": "gram-negative morphology", "provenance": "human_decision",
            })
        state = {
            "as_of": cutoff,
            "batches": visible_batches,
            "lab_results": visible_labs,
            "process_events": [item for item in self.data["process_events"] if visible(item)],
            "deviations": visible_deviations,
            "maintenance": [item for item in self.data["maintenance"] if visible(item)],
            "complaints": [item for item in self.data["complaints"] if visible(item)],
            "environmental_monitoring": [item for item in self.data["environmental_monitoring"] if visible(item)],
            "operator_events": [item for item in self.data["operator_events"] if visible(item)],
            "incident_memory": self.data["incident_memory"],
            "completed_human_tasks": [task for task in self.tasks() if task["status"] == "complete"],
        }
        records = [
            *state["batches"], *state["lab_results"], *state["process_events"],
            *state["deviations"], *state["maintenance"], *state["complaints"],
            *state["environmental_monitoring"], *state["operator_events"],
            *state["incident_memory"],
        ]
        evidence: dict[str, dict[str, Any]] = {}
        for record in records:
            for key in ("id", "sample_id", "operator_event_id", "batch_id", "deviation_id", "work_order", "complaint_id", "incident_id"):
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
        memory = {
            "incident_id": "MEM-POST-REPLAY-001",
            "symptoms": ["repeated normalized upstream bioburden excursion", "gram-negative morphology"],
            "evidence": ["completed replay investigation package"],
            "root_cause": None,
            "actions": ["retrieve prior assessment", "verify current evidence independently"],
            "outcome": "Structured memory created only after the simulated incident is resolved.",
            "provenance": "synthetic_factory_signal",
        }
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
