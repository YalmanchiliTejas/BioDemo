from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


TABLE_IDS = {
    "batches": "batch_id",
    "lab_results": "result_id",
    "process_events": "event_id",
    "environmental_monitoring": "sample_id",
    "deviations": "deviation_id",
    "maintenance": "work_order",
    "complaints": "complaint_id",
    "operator_events": "operator_event_id",
    "incident_memory": "incident_id",
}
MODE_TABLES = {
    "current_event_only": set(),
    "lims_only": {"batches", "lab_results"},
    "lims_qms": {"batches", "lab_results", "deviations"},
    "full_os": set(TABLE_IDS),
}
SYSTEM_TABLES = {
    "MES": {"batches", "process_events", "operator_events"},
    "LIMS": {"lab_results"},
    "QMS": {"deviations"},
    "CMMS": {"maintenance"},
    "ENVIRONMENT": {"environmental_monitoring"},
    "COMPLAINTS": {"complaints"},
}
FORBIDDEN_KEYS = {
    "benchmark_ground_truth", "simulation_labels", "batch_labels", "final_outcomes",
    "true_incident", "expected_severity", "ideal_escalation_level", "public_lot_mapping",
    "generation_reason", "synthetic_reason", "hard_failure_timestamp",
    "proactive_signal_window_start", "proactive_detection_optional",
}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evidence_id(table: str, record: dict[str, Any]) -> str:
    return str(record[TABLE_IDS[table]])


class TemporalFactoryStore:
    """Read-only access to the agent layer with availability-time redaction."""

    def __init__(self, agent_data_path: str | Path) -> None:
        self.path = Path(agent_data_path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        if self.data.get("metadata", {}).get("dataset_version") != "v1.1-frozen":
            raise ValueError("TemporalFactoryStore requires dataset_version v1.1-frozen")
        forbidden = FORBIDDEN_KEYS & set(self.data)
        if forbidden:
            raise ValueError(f"agent layer contains hidden benchmark keys: {sorted(forbidden)}")
        self._index: dict[str, tuple[str, dict[str, Any]]] = {}
        for table, id_field in TABLE_IDS.items():
            for record in self.data.get(table, []):
                identifier = str(record[id_field])
                if identifier in self._index:
                    raise ValueError(f"duplicate evidence ID: {identifier}")
                self._index[identifier] = (table, record)

    def session(
        self,
        *,
        as_of: str,
        mode: str = "full_os",
        current_evidence_ids: Iterable[str] = (),
    ) -> "TemporalSession":
        if mode not in MODE_TABLES:
            raise ValueError(f"unknown benchmark mode: {mode}")
        return TemporalSession(self, as_of, mode, set(map(str, current_evidence_ids)))

    def event_stream(self) -> list[dict[str, Any]]:
        events = []
        for identifier, (table, record) in self._index.items():
            events.append({
                "evidence_id": identifier,
                "table": table,
                "batch_id": record.get("batch_id") or record.get("linked_batch_id") or record.get("lot"),
                "occurred_at": record["occurred_at"],
                "available_at": record["available_at"],
                "availability_type": record["availability_type"],
            })
        return sorted(events, key=lambda item: (item["available_at"], item["evidence_id"]))


class TemporalSession:
    def __init__(self, store: TemporalFactoryStore, as_of: str, mode: str, current_ids: set[str]) -> None:
        self.store = store
        self.as_of = as_of
        self.mode = mode
        self.current_ids = current_ids

    def _allowed_table(self, table: str) -> bool:
        if self.mode == "current_event_only":
            return True
        return table in MODE_TABLES[self.mode]

    def _visible(self, table: str, record: dict[str, Any]) -> bool:
        identifier = evidence_id(table, record)
        if self.mode == "current_event_only" and identifier not in self.current_ids:
            return False
        return self._allowed_table(table) and parse_time(record["available_at"]) <= parse_time(self.as_of)

    def _redact(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        value = deepcopy(record)
        availability = value.pop("field_available_at", {})
        visible_field_times: dict[str, str] = {}
        for field, timestamp in availability.items():
            if parse_time(timestamp) > parse_time(self.as_of):
                value.pop(field, None)
            else:
                visible_field_times[field] = timestamp
        value["field_available_at"] = visible_field_times
        value["_table"] = table
        value["_evidence_id"] = evidence_id(table, record)
        return value

    def records(self, tables: Iterable[str] | None = None) -> list[dict[str, Any]]:
        selected = set(tables or TABLE_IDS)
        rows: list[dict[str, Any]] = []
        for table in TABLE_IDS:
            if table not in selected:
                continue
            for record in self.store.data.get(table, []):
                if self._visible(table, record):
                    rows.append(self._redact(table, record))
        return sorted(rows, key=lambda item: (item["available_at"], item["_evidence_id"]))

    def get(self, identifiers: Iterable[str]) -> list[dict[str, Any]]:
        rows = []
        for identifier in dict.fromkeys(map(str, identifiers)):
            found = self.store._index.get(identifier)
            if found and self._visible(*found):
                rows.append(self._redact(*found))
        return rows

    def visible_evidence_ids(self) -> set[str]:
        return {row["_evidence_id"] for row in self.records()}

    def tables_for_systems(self, systems: Iterable[str]) -> set[str]:
        requested = {str(value).upper() for value in systems}
        if not requested:
            return set(TABLE_IDS)
        return set().union(*(SYSTEM_TABLES.get(system, set()) for system in requested))

