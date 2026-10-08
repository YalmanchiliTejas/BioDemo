from __future__ import annotations

import json
import hashlib
from pathlib import Path

from benchmark.pharma_simulation.agent import BenchmarkAgent, validate_output
from benchmark.pharma_simulation.generator import DATA_DIR, DEMO_DATA_DIR, generate
from benchmark.pharma_simulation.harness import run_validation
from benchmark.pharma_simulation.store import SimulationStore, TIMESTAMP_FIELDS, parse_time
from benchmark.pharma_simulation.validation import validate_dataset, validate_no_line_overlap, validate_public_facts


def generated_store(tmp_path: Path) -> SimulationStore:
    generate(42, tmp_path)
    return SimulationStore(tmp_path / "pharma_simulation.db")


def test_generation_is_reproducible_and_matches_frozen_fingerprint(tmp_path: Path) -> None:
    first = generate(42, tmp_path / "one")
    second = generate(42, tmp_path / "two")
    frozen = (DATA_DIR / "frozen_seed_42.sha256").read_text().strip()
    assert first["dataset_fingerprint"] == second["dataset_fingerprint"] == frozen


def test_state_at_never_returns_future_records_or_evaluation_labels(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    cutoff = "2025-02-01T00:00:00Z"
    state = store.state_at(cutoff, current_batch_id="BATCH-084", context="full_os")
    serialized = json.dumps(state)
    assert "true_incident" not in serialized
    assert "ideal_escalation_level" not in serialized
    for key, table in (
        ("recent_lab_results", "lab_results"), ("process_events", "process_events"),
        ("environmental_monitoring", "environmental_monitoring"), ("deviations", "deviations"),
        ("maintenance", "maintenance"), ("complaints", "complaints"),
        ("operator_events", "operator_events"), ("incident_memory", "incident_memory"),
    ):
        timestamp_field = TIMESTAMP_FIELDS[table]
        assert all(parse_time(row[timestamp_field]) <= parse_time(cutoff) for row in state[key])


def test_later_endotoxin_complaint_recall_and_final_disposition_are_hidden(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    state = store.state_at("2025-01-01T00:00:00Z", current_batch_id="BATCH-075", context="full_os")
    assert not any(row["sample_type"] == "finished-product reserve" for row in state["recent_lab_results"])
    assert not state["complaints"]
    assert state["current_batch"]["disposition"] == "released"
    assert state["current_batch"]["status"] != "recalled"
    assert "recall" not in json.dumps(state).lower()
    assert "benchmark_outcomes" not in state


def test_public_facts_have_availability_timestamps() -> None:
    facts = json.loads((DATA_DIR / "public_ground_truth.json").read_text())["facts"]
    assert facts
    assert all(fact.get("available_at") for fact in facts)


def test_pf006_uses_warning_letter_publication_time_and_source() -> None:
    replay = json.loads((DEMO_DATA_DIR / "replay_ui.json").read_text())
    fact = next(item for item in replay["public_facts"] if item["id"] == "PF-006")
    assert fact["fact_id"] == "FDA-F009"
    assert fact["available_at"] == "2026-09-22T00:00:00Z"
    assert "/warning-letters/" in fact["source_url"]


def test_later_maintenance_cannot_be_cited_early(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    with store._connect() as connection:
        later = connection.execute("SELECT * FROM maintenance ORDER BY timestamp DESC LIMIT 1").fetchone()
    cutoff = "2024-03-01T00:00:00Z"
    state = store.state_at(cutoff, current_batch_id="SYN-0005", context="full_os")
    assert later["work_order"] not in state["visible_evidence_ids"]


def test_invalid_or_future_evidence_ids_are_stripped(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    state = store.state_at("2025-01-01T00:00:00Z", current_batch_id="BATCH-075", context="full_os")
    output, audit = validate_output({
        "severity": "CRITICAL", "triage_level": "L3", "summary": "bad citation",
        "evidence_ids": ["LAB-DOES-NOT-EXIST"],
        "hypotheses": [{"hypothesis": "future outcome", "confidence": 1,
                        "supporting_evidence_ids": ["LAB-DOES-NOT-EXIST"],
                        "contradicting_evidence_ids": []}],
    }, set(state["visible_evidence_ids"]))
    assert output["evidence_ids"] == []
    assert output["hypotheses"][0]["supporting_evidence_ids"] == []
    assert audit["stripped"] == 2


def test_public_consistency_and_dataset_validation_pass(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    assert validate_dataset(store.database, tmp_path)["status"] == "PASS"
    assert validate_public_facts(store.database, tmp_path)["status"] == "PASS"


def test_benchmark_metrics_are_computed_and_grounded(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    results = run_validation(store.database, tmp_path)
    full = results["ablations"]["D_full_OS_context"]
    current = results["ablations"]["A_current_event_only"]
    assert full["incident_detection_recall"] >= current["incident_detection_recall"]
    assert full["investigation_scope_recall"] >= current["investigation_scope_recall"]
    assert full["evidence_grounding_accuracy"] == 1.0
    assert full["future_leakage_rate"] == 0.0


def test_negative_control_does_not_escalate_to_l3(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    control = next(row for row in store.labels() if row["counterfactual_role"] == "isolated_negative_control")
    event = next(row for row in store.event_stream(control["batch_id"]) if row.get("status") == "action")
    state = store.state_at(event["_timestamp"], current_batch_id=control["batch_id"], context="full_os", current_event=event)
    output, _ = BenchmarkAgent().assess(state)
    assert output["triage_level"] == "L2"


def test_counterfactual_pair_escalates_differently(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    control = next(row for row in store.labels() if row["counterfactual_role"] == "isolated_negative_control")
    target = next(row for row in store.labels() if row["counterfactual_role"] == "recurring_target")
    control_event = next(row for row in store.event_stream(control["batch_id"]) if row.get("status") == "action")
    target_event = next(row for row in store.event_stream(target["batch_id"]) if row.get("status") == "action")
    control_state = store.state_at(control_event["_timestamp"], current_batch_id=control["batch_id"], context="full_os", current_event=control_event)
    target_state = store.state_at(target_event["_timestamp"], current_batch_id=target["batch_id"], context="full_os", current_event=target_event)
    assert BenchmarkAgent().assess(control_state)[0]["triage_level"] == "L2"
    assert BenchmarkAgent().assess(target_state)[0]["triage_level"] == "L3"


def test_sterility_disposition_and_shipping_causal_order(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    with store._connect() as connection:
        for lab in connection.execute("SELECT * FROM lab_results WHERE test_name='sterility'"):
            assert (parse_time(lab["timestamp"]) - parse_time(lab["sample_collected_at"])).total_seconds() >= 14 * 24 * 3600
        for batch in connection.execute("SELECT * FROM batches"):
            assert parse_time(batch["start_time"]) < parse_time(batch["end_time"])
            assert parse_time(batch["end_time"]) < parse_time(batch["disposition_time"])
            assert parse_time(batch["disposition_time"]) <= parse_time(batch["first_ship_time"])


def test_no_batches_overlap_on_the_same_line(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    with store._connect() as connection:
        batches = [dict(row) for row in connection.execute("SELECT * FROM batches")]
    assert validate_no_line_overlap(batches) == []


def test_memory_is_an_explicit_ablation_not_primary_context(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    event = next(row for row in store.event_stream("BATCH-075") if row.get("status") == "action")
    primary = store.state_at(event["_timestamp"], current_batch_id="BATCH-075", context="full_os", current_event=event)
    memory = store.state_at(event["_timestamp"], current_batch_id="BATCH-075", context="full_os_with_memory", current_event=event)
    assert primary["incident_memory"] == []
    assert len(memory["incident_memory"]) == 1
    assert BenchmarkAgent().assess(primary)[0]["triage_level"] == "L2"
    assert BenchmarkAgent().assess(memory)[0]["triage_level"] == "L3"


def test_agent_layers_contain_no_labels_public_lots_or_ui_artifacts(tmp_path: Path) -> None:
    generate(42, tmp_path)
    # Default generation does not rewrite committed demo data, so inspect the
    # store interface directly and the committed layer contract separately.
    store = SimulationStore(tmp_path / "pharma_simulation.db")
    event = next(row for row in store.event_stream("BATCH-075") if row.get("status") == "action")
    state = store.state_at(event["_timestamp"], current_batch_id="BATCH-075", context="full_os", current_event=event)
    serialized = json.dumps(state).lower()
    for forbidden in (
        "synthetic_reason", "incident_family", "negative_control", "true_incident",
        "6133156", "6133194", "6133388", "public_facts", "warning letter", "replay_events",
    ):
        assert forbidden not in serialized


def test_frozen_agent_layer_version_and_checksum() -> None:
    data = json.loads((DEMO_DATA_DIR / "agent_data.json").read_text())
    expected = data["metadata"].pop("content_sha256")
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    assert data["metadata"]["dataset_version"] == "v1.0-frozen"
    assert data["metadata"]["generation_seed"] == 42
    assert hashlib.sha256(payload.encode()).hexdigest() == expected


def test_all_benchmark_modes_exclude_hidden_layers(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    event = next(row for row in store.event_stream("BATCH-084") if row.get("status") == "action")
    for mode in ("current_event_only", "lims_only", "lims_qms", "full_os", "full_os_with_memory"):
        state = store.state_at(event["_timestamp"], current_batch_id="BATCH-084", context=mode, current_event=event)
        serialized = json.dumps(state).lower()
        assert "public_facts" not in serialized
        assert "replay_events" not in serialized
        assert "synthetic_reason" not in serialized
        assert "true_incident" not in serialized
        assert "6133156" not in serialized
        assert "6133194" not in serialized
        assert "6133388" not in serialized


def test_deviation_resolution_is_temporally_redacted(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    with store._connect() as connection:
        row = connection.execute(
            "SELECT * FROM deviations WHERE closed_at IS NOT NULL ORDER BY opened_at LIMIT 1"
        ).fetchone()
    state = store.state_at(row["opened_at"], current_batch_id=row["batch_id"], context="lims_qms")
    visible = next(item for item in state["deviations"] if item["deviation_id"] == row["deviation_id"])
    assert visible["closed_at"] is None
    assert visible["root_cause"] is None
    assert visible["capa"] is None
