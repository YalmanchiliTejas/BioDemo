"""Dataset and replay checks independent of the Prime investigation runtime."""

from __future__ import annotations

import json
from pathlib import Path

from src.data import TemporalFactoryStore
from src.data.temporal_store import parse_time
from src.data.upgrade_v11 import upgrade
from src.evaluation.leakage_audit import run_leakage_audit


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "v1.1"


def test_v11_preserves_original_batch_ids() -> None:
    original = json.loads((ROOT / "benchmark/incident_demo/data/agent_data.json").read_text())
    current = json.loads((DATA / "agent_data.json").read_text())
    assert len(original["batches"]) == len(current["batches"]) == 100
    assert {row["batch_id"] for row in original["batches"]} == {row["batch_id"] for row in current["batches"]}
    assert (DATA / "frozen.sha256").read_text().strip() == current["metadata"]["content_sha256"]


def test_upgrade_is_reproducible(tmp_path: Path) -> None:
    first = upgrade(target=tmp_path / "one")
    second = upgrade(target=tmp_path / "two")
    assert first["agent_data_content_sha256"] == second["agent_data_content_sha256"]
    assert (tmp_path / "one/agent_data.json").read_bytes() == (tmp_path / "two/agent_data.json").read_bytes()


def test_agent_data_has_no_hidden_labels() -> None:
    audit = run_leakage_audit(DATA / "agent_data.json")
    assert audit.status == "PASS", audit.failures
    text = (DATA / "agent_data.json").read_text().lower()
    for forbidden in ("true_incident", "ideal_escalation_level", "hard_failure_timestamp", "public_lot_mapping"):
        assert forbidden not in text


def test_replay_redacts_future_fields() -> None:
    store = TemporalFactoryStore(DATA / "agent_data.json")
    batch = next(row for row in store.data["batches"] if row["batch_id"] == "BATCH-075")
    session = store.session(as_of=batch["start_time"], mode="full_os", current_evidence_ids=["BATCH-075"])
    visible = session.get(["BATCH-075"])[0]
    assert "end_time" not in visible and "disposition" not in visible
    assert all(parse_time(row["available_at"]) <= parse_time(batch["start_time"]) for row in session.records())


def test_dataset_chronology() -> None:
    store = TemporalFactoryStore(DATA / "agent_data.json")
    for event in store.event_stream():
        assert parse_time(event["occurred_at"]) <= parse_time(event["available_at"])
    by_line: dict[str, list[dict]] = {}
    for batch in store.data["batches"]:
        by_line.setdefault(batch["production_line"], []).append(batch)
    for batches in by_line.values():
        ordered = sorted(batches, key=lambda row: row["start_time"])
        assert all(parse_time(a["end_time"]) <= parse_time(b["start_time"])
                   for a, b in zip(ordered, ordered[1:]))


def test_precursors_have_hidden_evaluator_metadata() -> None:
    agent = json.loads((DATA / "agent_data.json").read_text())
    hidden = json.loads((DATA / "benchmark_ground_truth.json").read_text())
    precursors = [row for row in agent["lab_results"] if row["result_id"].startswith("PRE-LAB-")]
    metadata = hidden["precursor_evaluator_metadata"]
    assert len(precursors) == len(metadata) == 4
    assert sum(item["hard_failure_timestamp"] is None for item in metadata) == 2
    assert "proactive_detection_optional" not in json.dumps(precursors)
