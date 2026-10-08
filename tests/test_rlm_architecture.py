from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from src.data import TemporalFactoryStore
from src.data.temporal_store import TABLE_IDS, parse_time
from src.data.upgrade_v11 import upgrade
from src.evaluation.leakage_audit import run_leakage_audit
from src.rlm import LeadManufacturingRLM, RLMConfig, RolloutEngine
from src.state import BlackboardStore, CausalHypothesisGraph, DecisionGraph
from src.tools import RUNTIME_TOOLS


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "v1.1"


def store() -> TemporalFactoryStore:
    return TemporalFactoryStore(DATA / "agent_data.json")


def first_action_event(factory: TemporalFactoryStore):
    for event in factory.event_stream():
        rows = factory.session(as_of=event["available_at"], current_evidence_ids=[event["evidence_id"]]).get([event["evidence_id"]])
        if rows and rows[0].get("status") == "action":
            return event, rows[0]
    raise AssertionError("no action event")


def test_v11_is_additive_and_v10_remains_frozen() -> None:
    v10 = json.loads((ROOT / "benchmark/incident_demo/data/agent_data.json").read_text())
    v11 = json.loads((DATA / "agent_data.json").read_text())
    assert v10["metadata"]["dataset_version"] == "v1.0-frozen"
    assert v11["metadata"]["dataset_version"] == "v1.1-frozen"
    assert len(v10["batches"]) == len(v11["batches"]) == 100
    assert {row["batch_id"] for row in v10["batches"]} == {row["batch_id"] for row in v11["batches"]}
    assert (DATA / "frozen.sha256").read_text().strip() == v11["metadata"]["content_sha256"]


def test_upgrade_is_reproducible(tmp_path: Path) -> None:
    first = upgrade(target=tmp_path / "one")
    second = upgrade(target=tmp_path / "two")
    assert first["agent_data_content_sha256"] == second["agent_data_content_sha256"]
    assert (tmp_path / "one/agent_data.json").read_bytes() == (tmp_path / "two/agent_data.json").read_bytes()


def test_leakage_audit_passes_and_agent_layer_has_no_hidden_or_public_outcomes() -> None:
    audit = run_leakage_audit(DATA / "agent_data.json")
    assert audit.status == "PASS", audit.failures
    serialized = (DATA / "agent_data.json").read_text().lower()
    for forbidden in ("true_incident", "ideal_escalation_level", "hard_failure_timestamp", "public_lot_mapping", '"outcome": "recalled"'):
        assert forbidden not in serialized


def test_future_records_and_fields_are_redacted() -> None:
    factory = store()
    batch = next(row for row in factory.data["batches"] if row["batch_id"] == "BATCH-075")
    early = factory.session(as_of=batch["start_time"], mode="full_os", current_evidence_ids=["BATCH-075"])
    visible = early.get(["BATCH-075"])[0]
    assert "end_time" not in visible
    assert "disposition" not in visible
    assert "first_ship_time" not in visible
    assert all(parse_time(row["available_at"]) <= parse_time(batch["start_time"]) for row in early.records())


def test_pending_physical_evidence_cannot_be_known_early(tmp_path: Path) -> None:
    factory = store()
    event, record = first_action_event(factory)
    engine = RolloutEngine(factory, BlackboardStore(tmp_path))
    output = engine.run(
        incident_id="INC-TEST", problem="Investigate the first meaningful signal",
        new_evidence_ids=[event["evidence_id"]], as_of=event["available_at"], mode="full_os",
    )
    request = output["pending_evidence_requests"][0]
    assert request["status"] == "pending"
    assert request["answer"] is None
    assert request["request_id"] not in output["evidence_ids"]


def test_blackboard_persists_and_new_evidence_resumes_it(tmp_path: Path) -> None:
    factory = store()
    actions = []
    for event in factory.event_stream():
        rows = factory.session(as_of=event["available_at"], current_evidence_ids=[event["evidence_id"]]).get([event["evidence_id"]])
        if rows and rows[0].get("status") in {"alert", "action"}:
            actions.append(event)
        if len(actions) == 2:
            break
    blackboards = BlackboardStore(tmp_path)
    engine = RolloutEngine(factory, blackboards)
    first = engine.run(incident_id="INC-RESUME", problem="Investigate", new_evidence_ids=[actions[0]["evidence_id"]], as_of=actions[0]["available_at"])
    second = engine.run(incident_id="INC-RESUME", problem="Investigate", new_evidence_ids=[actions[1]["evidence_id"]], as_of=actions[1]["available_at"])
    persisted = blackboards.load("INC-RESUME")
    assert persisted is not None
    assert actions[0]["evidence_id"] in persisted.evidence_ids
    assert actions[1]["evidence_id"] in persisted.evidence_ids
    assert len(persisted.rollout_history) == 2
    assert len(second["evidence_ids"]) >= len(first["evidence_ids"])


def test_graphs_reference_only_valid_evidence_and_dependencies(tmp_path: Path) -> None:
    factory = store()
    event, _ = first_action_event(factory)
    blackboards = BlackboardStore(tmp_path)
    RolloutEngine(factory, blackboards).run(
        incident_id="INC-GRAPH", problem="Investigate", new_evidence_ids=[event["evidence_id"]], as_of=event["available_at"]
    )
    board = blackboards.load("INC-GRAPH")
    assert board is not None
    visible = factory.session(as_of=event["available_at"]).visible_evidence_ids()
    assert CausalHypothesisGraph(board.causal_hypotheses).validate(visible) == []
    assert any(node["contradicting_evidence_ids"] for node in board.causal_hypotheses)
    assert DecisionGraph(board.decision_branches).validate({row["request_id"] for row in board.pending_evidence}) == []


def test_recursion_and_tool_calls_obey_configured_bounds(tmp_path: Path) -> None:
    factory = store()
    event, _ = first_action_event(factory)
    config = RLMConfig(max_depth=2, max_parallel_subtasks=3, max_total_tool_calls_per_rollout=12)
    output = RolloutEngine(factory, BlackboardStore(tmp_path), LeadManufacturingRLM(config)).run(
        incident_id="INC-BOUNDS", problem="Investigate", new_evidence_ids=[event["evidence_id"]], as_of=event["available_at"]
    )
    metrics = output["rollout_metrics"]
    assert metrics["rlm_recursion_depth"] <= 2
    assert metrics["tool_calls"] <= 12
    assert metrics["subtasks_spawned"] <= 6


def test_system_md_tool_names_equal_runtime_registry() -> None:
    documented = set(re.findall(r"^## Tool: ([a-z_]+)$", (ROOT / "system.md").read_text(), flags=re.MULTILINE))
    assert documented == set(RUNTIME_TOOLS)


def test_all_evidence_ids_exist_and_citations_were_available(tmp_path: Path) -> None:
    factory = store()
    all_ids = {event["evidence_id"] for event in factory.event_stream()}
    assert len(all_ids) == sum(len(factory.data.get(table, [])) for table in TABLE_IDS)
    event, _ = first_action_event(factory)
    output = RolloutEngine(factory, BlackboardStore(tmp_path)).run(
        incident_id="INC-CITE", problem="Investigate", new_evidence_ids=[event["evidence_id"]], as_of=event["available_at"]
    )
    visible = factory.session(as_of=event["available_at"]).visible_evidence_ids()
    cited = set(output["evidence_ids"])
    for node in output["causal_hypotheses"]:
        cited.update(node["supporting_evidence_ids"])
        cited.update(node["contradicting_evidence_ids"])
    assert cited <= all_ids
    assert cited <= visible


def test_valid_dataset_chronology_and_no_same_line_overlap() -> None:
    factory = store()
    for event in factory.event_stream():
        assert parse_time(event["occurred_at"]) <= parse_time(event["available_at"])
    by_line: dict[str, list[dict]] = {}
    for batch in factory.data["batches"]:
        by_line.setdefault(batch["production_line"], []).append(batch)
    for batches in by_line.values():
        ordered = sorted(batches, key=lambda row: row["start_time"])
        for earlier, later in zip(ordered, ordered[1:]):
            assert parse_time(earlier["end_time"]) <= parse_time(later["start_time"])


def test_precursors_include_incident_and_negative_controls_only_in_hidden_metadata() -> None:
    agent = json.loads((DATA / "agent_data.json").read_text())
    ground = json.loads((DATA / "benchmark_ground_truth.json").read_text())
    precursors = [row for row in agent["lab_results"] if row["result_id"].startswith("PRE-LAB-")]
    metadata = ground["precursor_evaluator_metadata"]
    assert len(precursors) == len(metadata) == 4
    assert sum(item["hard_failure_timestamp"] is None for item in metadata) == 2
    assert "proactive_detection_optional" not in json.dumps(precursors)
