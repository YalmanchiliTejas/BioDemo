from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from .generator import DEFAULT_OUTPUT


TIMESTAMP_FIELDS = {
    "lab_results": "timestamp", "process_events": "timestamp",
    "environmental_monitoring": "timestamp", "deviations": "opened_at",
    "maintenance": "timestamp", "complaints": "timestamp",
    "operator_events": "timestamp", "incident_memory": "created_at",
}
ID_FIELDS = {
    "batches": "batch_id", "lab_results": "result_id", "process_events": "event_id",
    "environmental_monitoring": "sample_id", "deviations": "deviation_id",
    "maintenance": "work_order", "complaints": "complaint_id",
    "operator_events": "operator_event_id", "incident_memory": "incident_id",
}
CONTEXT_TABLES = {
    "current_event_only": set(),
    "lims_only": {"lab_results"},
    "lims_qms": {"lab_results", "deviations"},
    "full_os": set(TIMESTAMP_FIELDS) - {"incident_memory"},
    "full_os_with_memory": set(TIMESTAMP_FIELDS) - {"incident_memory"},
}

FORBIDDEN_AGENT_FIELDS = {
    "synthetic_reason", "incident_family", "negative_control", "ground_truth_class",
    "expected_escalation", "true_incident", "final_outcome", "public_lot",
}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "symptoms", "evidence_ids", "actions", "evidence_required", "relevant_batch_ids",
        "relevant_equipment_ids", "plausible_hypotheses", "expected_actions", "expected_teams",
    ):
        if isinstance(row.get(key), str) and row[key].startswith("["):
            row[key] = json.loads(row[key])
    return row


def _agent_safe(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in FORBIDDEN_AGENT_FIELDS}


class SimulationStore:
    """Read-only, time-bounded access to the benchmark database."""

    def __init__(self, database: Path | None = None) -> None:
        self.database = database or DEFAULT_OUTPUT / "pharma_simulation.db"
        if not self.database.exists():
            raise FileNotFoundError(f"Generate the dataset first: {self.database}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def metadata(self) -> dict[str, str]:
        with self._connect() as connection:
            return {row["key"]: row["value"] for row in connection.execute("SELECT * FROM metadata")}

    def labels(self) -> list[dict[str, Any]]:
        """Evaluation-only API. Never included in state_at()."""
        with self._connect() as connection:
            return [_decode(dict(row)) for row in connection.execute("SELECT * FROM simulation_labels ORDER BY batch_id")]

    def event_stream(self, batch_id: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with self._connect() as connection:
            for table, time_field in TIMESTAMP_FIELDS.items():
                if table == "incident_memory":
                    continue
                lot_field = "lot" if table == "complaints" else "linked_batch_id" if table == "maintenance" else "batch_id"
                for raw in connection.execute(f"SELECT * FROM {table} WHERE {lot_field} = ?", (batch_id,)):
                    row = _agent_safe(_decode(dict(raw)))
                    row["_table"] = table
                    row["_evidence_id"] = str(row[ID_FIELDS[table]])
                    row["_timestamp"] = row[time_field]
                    events.append(row)
        return sorted(events, key=lambda item: (item["_timestamp"], item["_evidence_id"]))

    def state_at(
        self,
        timestamp: str,
        *,
        current_batch_id: str,
        context: str = "full_os",
        current_event: dict[str, Any] | None = None,
        include_memory: bool = False,
    ) -> dict[str, Any]:
        if context not in CONTEXT_TABLES:
            raise ValueError(f"Unknown context: {context}")
        allowed_tables = CONTEXT_TABLES[context]
        state: dict[str, Any] = {
            "timestamp": timestamp,
            "current_batch": None,
            "new_events": [_agent_safe(deepcopy(current_event))] if current_event else [],
            "recent_lab_results": [],
            "historical_similar_events": [],
            "maintenance": [],
            "deviations": [],
            "environmental_monitoring": [],
            "process_events": [],
            "operator_events": [],
            "complaints": [],
            "incident_memory": [],
            "visible_evidence_ids": [],
            "context_condition": context,
        }
        evidence: set[str] = set()
        if current_event:
            evidence.add(str(current_event["_evidence_id"]))
        with self._connect() as connection:
            batch_context = {
                row["batch_id"]: {"product": row["product"], "production_line": row["production_line"]}
                for row in connection.execute("SELECT batch_id, product, production_line FROM batches")
            }
            batch = connection.execute("SELECT * FROM batches WHERE batch_id = ?", (current_batch_id,)).fetchone()
            if batch:
                visible_batch = _agent_safe(dict(batch))
                # Derive live status from time; never expose future disposition or shipment times.
                if timestamp < visible_batch["start_time"]:
                    visible_batch["status"], visible_batch["disposition"] = "planned", "pending"
                elif timestamp <= visible_batch["end_time"]:
                    visible_batch["status"], visible_batch["disposition"] = "in_process", "pending"
                elif timestamp < visible_batch["disposition_time"]:
                    visible_batch["status"], visible_batch["disposition"] = "quality_review", "pending"
                else:
                    visible_batch["status"], visible_batch["disposition"] = "released", "released"
                visible_batch.pop("disposition_time", None)
                visible_batch.pop("first_ship_time", None)
                visible_batch["_evidence_id"] = current_batch_id
                state["current_batch"] = visible_batch
                evidence.add(current_batch_id)

            mapping = {
                "lab_results": "recent_lab_results", "process_events": "process_events",
                "environmental_monitoring": "environmental_monitoring", "deviations": "deviations",
                "maintenance": "maintenance", "complaints": "complaints",
                "operator_events": "operator_events", "incident_memory": "incident_memory",
            }
            for table in allowed_tables:
                time_field = TIMESTAMP_FIELDS[table]
                rows = connection.execute(
                    f"SELECT * FROM {table} WHERE {time_field} <= ? ORDER BY {time_field}", (timestamp,)
                )
                for raw in rows:
                    row = _agent_safe(_decode(dict(raw)))
                    if table == "deviations" and row.get("closed_at") and row["closed_at"] > timestamp:
                        row["closed_at"] = None
                        row["investigation_status"] = "open"
                        row["root_cause"] = None
                        row["capa"] = None
                    row["_table"] = table
                    row["_evidence_id"] = str(row[ID_FIELDS[table]])
                    row["_timestamp"] = row[time_field]
                    related_batch = row.get("batch_id") or row.get("linked_batch_id") or row.get("lot")
                    if related_batch in batch_context:
                        row["_product"] = batch_context[related_batch]["product"]
                        row["_production_line"] = batch_context[related_batch]["production_line"]
                    state[mapping[table]].append(row)
                    evidence.add(row["_evidence_id"])

            if include_memory or context == "full_os_with_memory":
                table = "incident_memory"
                time_field = TIMESTAMP_FIELDS[table]
                for raw in connection.execute(
                    f"SELECT * FROM {table} WHERE {time_field} <= ? ORDER BY {time_field}", (timestamp,)
                ):
                    row = _agent_safe(_decode(dict(raw)))
                    row["_table"] = table
                    row["_evidence_id"] = str(row[ID_FIELDS[table]])
                    row["_timestamp"] = row[time_field]
                    state["incident_memory"].append(row)
                    evidence.add(row["_evidence_id"])

        if context in {"lims_qms", "full_os", "full_os_with_memory"}:
            state["historical_similar_events"] = [
                item for item in state["recent_lab_results"]
                if item["batch_id"] != current_batch_id and item["status"] in {"alert", "action", "out_of_specification"}
            ]
        state["visible_evidence_ids"] = sorted(evidence)
        return state
