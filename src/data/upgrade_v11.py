from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


VERSION = "v1.1-frozen"
CREATED_AT = "2026-10-08T00:00:00Z"
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "benchmark" / "incident_demo" / "data"
DEFAULT_TARGET = ROOT / "data" / "v1.1"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _temporalize(table: str, record: dict[str, Any]) -> dict[str, Any]:
    row = deepcopy(record)
    if table == "batches":
        occurred = available = row["start_time"]
        field_times = {
            "start_time": row["start_time"], "end_time": row["end_time"],
            "status": row.get("disposition_time", row["end_time"]),
            "disposition": row.get("disposition_time", row["end_time"]),
            "disposition_time": row.get("disposition_time", row["end_time"]),
            "first_ship_time": row.get("first_ship_time", row.get("disposition_time", row["end_time"])),
        }
        kind = "existing_record"
    elif table == "lab_results":
        occurred, available = row.get("sample_collected_at", row["timestamp"]), row["timestamp"]
        result_fields = (
            "numerical_result", "categorical_result", "unit", "specification_limit",
            "alert_limit", "action_limit", "status", "organism",
        )
        field_times = {field: available for field in result_fields if field in row}
        field_times["sample_collected_at"] = occurred
        kind = "requires_new_test" if row.get("sample_type") == "finished-product reserve" or row.get("test_name") == "organism_identification" else "existing_record"
    elif table == "deviations":
        occurred = available = row["opened_at"]
        closed = row.get("closed_at")
        field_times = {field: closed for field in ("closed_at", "investigation_status", "root_cause", "capa") if closed and field in row}
        kind = "existing_record"
    elif table == "maintenance":
        occurred = available = row["timestamp"]
        field_times = {field: available for field in ("action", "status") if field in row}
        kind = "existing_record"
    elif table == "complaints":
        occurred = available = row["timestamp"]
        field_times = {"outcome": available} if "outcome" in row else {}
        kind = "external_signal"
    elif table == "operator_events":
        occurred = available = row["timestamp"]
        field_times = {}
        kind = "requires_human_observation"
    elif table == "incident_memory":
        occurred = available = row["created_at"]
        field_times = {}
        kind = "existing_record"
    else:
        occurred = available = row["timestamp"]
        field_times = {}
        kind = "existing_record"
    row.update({
        "occurred_at": occurred,
        "available_at": available,
        "availability_type": kind,
        "field_available_at": field_times,
    })
    return row


def _add_precursors(agent: dict[str, Any], ground_truth: dict[str, Any]) -> list[dict[str, Any]]:
    bio_by_batch = {
        row["batch_id"]: row for row in agent["lab_results"]
        if row.get("test_name") == "relative_bioburden_signal"
    }
    negative = [
        row["benchmark_batch_id"] for row in ground_truth["batch_labels"]
        if row.get("negative_control") and row["benchmark_batch_id"] in bio_by_batch
    ][:2]
    selected = ["BATCH-075", "BATCH-084", *negative]
    metadata: list[dict[str, Any]] = []
    for index, batch_id in enumerate(selected, 1):
        hard = bio_by_batch[batch_id]
        timestamp = _iso(_time(hard["available_at"]) - timedelta(minutes=45))
        precursor = _temporalize("lab_results", {
            "result_id": f"PRE-LAB-{index:03d}",
            "batch_id": batch_id,
            "timestamp": timestamp,
            "sample_collected_at": _iso(_time(timestamp) - timedelta(minutes=30)),
            "sample_type": "upstream process sample",
            "test_name": "relative_bioburden_signal",
            "numerical_result": round(.76 + .03 * index, 3),
            "categorical_result": None,
            "unit": "action-limit ratio",
            "specification_limit": None,
            "alert_limit": .7,
            "action_limit": 1.0,
            "status": "alert",
            "organism": None,
            "provenance": "synthetic_factory_signal",
        })
        agent["lab_results"].append(precursor)
        metadata.append({
            "record_id": precursor["result_id"],
            "batch_id": batch_id,
            "proactive_signal_window_start": timestamp,
            "hard_failure_timestamp": hard["available_at"] if batch_id.startswith("BATCH-") else None,
            "proactive_detection_optional": True,
            "benchmark_only": True,
        })
    agent["lab_results"].sort(key=lambda row: (row["available_at"], row["result_id"]))
    return metadata


def upgrade(source: Path = SOURCE, target: Path = DEFAULT_TARGET) -> dict[str, str]:
    agent = json.loads((source / "agent_data.json").read_text(encoding="utf-8"))
    ground = json.loads((source / "benchmark_ground_truth.json").read_text(encoding="utf-8"))
    public = json.loads((source / "public_ground_truth.json").read_text(encoding="utf-8"))
    replay = json.loads((source / "replay_ui.json").read_text(encoding="utf-8"))
    for table in (
        "batches", "lab_results", "process_events", "environmental_monitoring",
        "deviations", "maintenance", "complaints", "operator_events", "incident_memory",
    ):
        agent[table] = [_temporalize(table, row) for row in agent.get(table, [])]
    precursor_metadata = _add_precursors(agent, ground)
    agent["metadata"] = {
        **{key: value for key, value in agent["metadata"].items() if key != "content_sha256"},
        "dataset_version": VERSION,
        "creation_timestamp": CREATED_AT,
        "source_dataset_version": "v1.0-frozen",
        "temporal_contract": "occurred_at + available_at + field_available_at",
    }
    canonical = json.dumps(agent, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(canonical.encode()).hexdigest()
    agent["metadata"]["content_sha256"] = checksum
    ground["metadata"] = {
        **ground["metadata"], "dataset_version": VERSION, "creation_timestamp": CREATED_AT,
        "source_dataset_version": "v1.0-frozen", "agent_data_content_sha256": checksum,
    }
    ground["precursor_evaluator_metadata"] = precursor_metadata
    public["metadata"] = {**public.get("metadata", {}), "dataset_version": VERSION, "source_dataset_version": "v1.0-frozen"}
    replay["metadata"] = {**replay["metadata"], "dataset_version": VERSION, "source_dataset_version": "v1.0-frozen"}
    for event in replay.get("replay_events", []):
        event.setdefault("occurred_at", event["timestamp"])
        event.setdefault("available_at", event["timestamp"])
    target.mkdir(parents=True, exist_ok=True)
    payloads = {
        "agent_data.json": agent,
        "benchmark_ground_truth.json": ground,
        "public_ground_truth.json": public,
        "replay_ui.json": replay,
    }
    for filename, payload in payloads.items():
        (target / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (target / "frozen.sha256").write_text(checksum + "\n", encoding="utf-8")
    return {"dataset_version": VERSION, "agent_data_content_sha256": checksum, "target": str(target)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upgrade frozen v1.0 layers to the additive v1.1 temporal contract")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    print(json.dumps(upgrade(args.source, args.target), indent=2))
