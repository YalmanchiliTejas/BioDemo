from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.temporal_store import FORBIDDEN_KEYS, TABLE_IDS, TemporalFactoryStore, parse_time


@dataclass(frozen=True)
class LeakageAudit:
    status: str
    failures: tuple[str, ...]
    checks: dict[str, bool]


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_walk_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_walk_keys(item) for item in value), set())
    return set()


def run_leakage_audit(agent_data_path: str | Path) -> LeakageAudit:
    path = Path(agent_data_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    keys = _walk_keys(data)
    hidden = sorted(keys & FORBIDDEN_KEYS)
    if hidden:
        failures.append(f"hidden evaluator keys in agent layer: {hidden}")
    metadata = dict(data.get("metadata", {}))
    expected = metadata.pop("content_sha256", None)
    actual = hashlib.sha256(json.dumps({**data, "metadata": metadata}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != actual:
        failures.append("agent_data content checksum mismatch")
    identifiers: set[str] = set()
    chronology_ok = True
    for table, id_field in TABLE_IDS.items():
        for record in data.get(table, []):
            identifier = str(record.get(id_field, ""))
            if not identifier or identifier in identifiers:
                failures.append(f"missing or duplicate evidence ID: {table}/{identifier}")
            identifiers.add(identifier)
            for required in ("occurred_at", "available_at", "availability_type", "field_available_at"):
                if required not in record:
                    failures.append(f"{identifier} lacks {required}")
            try:
                if parse_time(record["available_at"]) < parse_time(record["occurred_at"]):
                    chronology_ok = False
                    failures.append(f"{identifier} is available before it occurred")
                for field, timestamp in record.get("field_available_at", {}).items():
                    if field not in record:
                        failures.append(f"{identifier} has availability for absent field {field}")
                    if parse_time(timestamp) < parse_time(record["occurred_at"]):
                        chronology_ok = False
                        failures.append(f"{identifier}.{field} is available before record occurrence")
            except (KeyError, ValueError):
                chronology_ok = False
    try:
        store = TemporalFactoryStore(path)
        temporal_store_loads = True
        for event in store.event_stream():
            session = store.session(as_of=event["available_at"], current_evidence_ids=[event["evidence_id"]])
            if event["evidence_id"] not in session.visible_evidence_ids():
                failures.append(f"evidence unavailable at own available_at: {event['evidence_id']}")
                break
    except Exception as exc:
        temporal_store_loads = False
        failures.append(f"temporal store rejected dataset: {exc}")
    checks = {
        "no_hidden_benchmark_access": not hidden,
        "checksum_valid": expected == actual,
        "chronology_valid": chronology_ok,
        "temporal_store_loads": temporal_store_loads,
    }
    return LeakageAudit("PASS" if not failures else "FAIL", tuple(failures), checks)

