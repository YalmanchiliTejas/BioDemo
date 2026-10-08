from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.data import TemporalFactoryStore
from src.data.temporal_store import parse_time
from src.rlm import RolloutEngine
from src.state import BlackboardStore

from .benchmark_modes import BENCHMARK_MODES
from .leakage_audit import run_leakage_audit
from .metrics import mean, summarize_rollouts


def _meaningful(record: dict[str, Any]) -> bool:
    text = json.dumps(record).lower()
    return any(token in text for token in (
        '"status": "alert"', '"status": "action"', '"status": "out_of_specification"',
        '"severity": "medium"', '"severity": "high"', '"severity": "critical"',
        "excursion", "complaint",
    ))


def _problem(record: dict[str, Any]) -> str:
    signal = record.get("test_name") or record.get("parameter") or record.get("category") or record.get("event_type") or record["_table"]
    batch = record.get("batch_id") or record.get("linked_batch_id") or record.get("lot") or "unknown scope"
    return f"Investigate the {signal} signal associated with {batch}; determine scope, plausible causes, existing evidence, pending evidence, and safe next actions."


def _incident_key(store: TemporalFactoryStore, record: dict[str, Any]) -> str:
    batch_id = record.get("batch_id") or record.get("linked_batch_id") or record.get("lot")
    product = next((row.get("product") for row in store.data["batches"] if row["batch_id"] == batch_id), "unknown")
    signal = record.get("test_name") or record.get("parameter") or record.get("category") or record["_table"]
    safe = "-".join(str(value).upper().replace("_", "-").replace(" ", "-") for value in (product, signal))
    return "INC-" + "".join(character for character in safe if character.isalnum() or character == "-")[:100]


def _refs(output: dict[str, Any]) -> list[str]:
    values = list(output.get("evidence_ids", []))
    for hypothesis in output.get("causal_hypotheses", []):
        values.extend(hypothesis.get("supporting_evidence_ids", []))
        values.extend(hypothesis.get("contradicting_evidence_ids", []))
    for action in output.get("actions_now", []):
        values.extend(action.get("evidence_ids", []))
    return values


def run_benchmark(
    data_dir: str | Path = Path("data/v1.1"),
    output_path: str | Path | None = Path("artifacts/rlm_benchmark_results.json"),
) -> dict[str, Any]:
    data_dir = Path(data_dir)
    agent_path = data_dir / "agent_data.json"
    audit = run_leakage_audit(agent_path)
    print(f"LEAKAGE AUDIT: {audit.status}")
    if audit.status != "PASS":
        raise RuntimeError("benchmark blocked by leakage audit: " + "; ".join(audit.failures))
    store = TemporalFactoryStore(agent_path)
    ground = json.loads((data_dir / "benchmark_ground_truth.json").read_text(encoding="utf-8"))
    labels = {row["benchmark_batch_id"]: row for row in ground["batch_labels"]}
    meaningful_events = []
    for event in store.event_stream():
        record = store.session(as_of=event["available_at"], mode="full_os", current_evidence_ids=[event["evidence_id"]]).get([event["evidence_id"]])
        if record and _meaningful(record[0]):
            meaningful_events.append((event, record[0]))
    results: dict[str, Any] = {"dataset_version": "v1.1-frozen", "leakage_audit": audit.checks, "modes": {}}
    for mode in BENCHMARK_MODES:
        detected: dict[str, str] = {}
        outputs_by_batch: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        rollout_metrics: list[dict[str, Any]] = []
        citations = valid_citations = future_citations = 0
        retrieved_existing: set[str] = set()
        available_existing: set[str] = set()
        completed_before_physical = total_before_physical = 0
        unnecessary_request_ids: set[tuple[str, str]] = set()
        with tempfile.TemporaryDirectory(prefix=f"biodemo-rlm-{mode}-") as temporary:
            engine = RolloutEngine(store, BlackboardStore(Path(temporary)))
            for event, record in meaningful_events:
                batch_id = event.get("batch_id")
                if not batch_id:
                    continue
                permitted = store.session(
                    as_of=event["available_at"], mode=mode,
                    current_evidence_ids=[event["evidence_id"]],
                ).get([event["evidence_id"]])
                if not permitted:
                    # A mode cannot be triggered by a system it is not allowed
                    # to observe. The agent and prompt remain unchanged.
                    continue
                output = engine.run(
                    incident_id=_incident_key(store, record), problem=_problem(record),
                    new_evidence_ids=[event["evidence_id"]], as_of=event["available_at"], mode=mode,
                )
                outputs_by_batch[batch_id].append((event["available_at"], output))
                rollout_metrics.append(output["rollout_metrics"])
                if output["severity"] in {"MEDIUM", "HIGH", "CRITICAL"} and batch_id not in detected:
                    detected[batch_id] = event["available_at"]
                session = store.session(as_of=event["available_at"], mode=mode, current_evidence_ids=[event["evidence_id"]])
                # Blackboard evidence observed during an earlier rollout remains
                # available even in current-event-only mode. Future leakage is a
                # time violation, not the absence of an old record from this
                # rollout's retrieval permission set.
                available_by_time = {
                    candidate["evidence_id"] for candidate in store.event_stream()
                    if candidate["available_at"] <= event["available_at"]
                }
                refs = _refs(output)
                citations += len(refs)
                valid_citations += sum(reference in available_by_time for reference in refs)
                future_citations += sum(reference not in available_by_time for reference in refs)
                retrieved_existing.update(reference for reference in output["evidence_ids"] if reference in available_by_time)
                available_existing.update(row["_evidence_id"] for row in session.records() if row["availability_type"] == "existing_record")
                next_physical = next((candidate for candidate in store.event_stream() if candidate["available_at"] > event["available_at"] and candidate["availability_type"] != "existing_record"), None)
                if next_physical:
                    total_before_physical += 1
                    completed_before_physical += bool(output["resolved_questions"])
                if batch_id in labels and not labels[batch_id]["true_incident"]:
                    incident_key = _incident_key(store, record)
                    unnecessary_request_ids.update(
                        (incident_key, request["request_id"])
                        for request in output["pending_evidence_requests"]
                    )
        true_batches = {batch for batch, label in labels.items() if label["true_incident"]}
        normal_batches = set(labels) - true_batches
        true_detected = true_batches & set(detected)
        false_detected = normal_batches & set(detected)
        delays = [
            max(0.0, (parse_time(detected[batch]) - parse_time(labels[batch]["earliest_detectable_timestamp"])).total_seconds() / 60)
            for batch in true_detected if labels[batch].get("earliest_detectable_timestamp")
        ]
        scope_scores = []
        correct_scope_times = []
        decision_ready_times = []
        for batch in true_batches:
            relevant = {row["benchmark_batch_id"] for row in ground["batch_labels"] if row.get("incident_family") == labels[batch].get("incident_family") and row.get("true_incident")}
            outputs = outputs_by_batch.get(batch, [])
            surfaced = set(outputs[-1][1]["related_batches"]) if outputs else set()
            scope_scores.append(len(relevant & surfaced) / len(relevant) if relevant else 1.0)
            origin = labels[batch].get("earliest_detectable_timestamp")
            if origin:
                for evaluated_at, output in outputs:
                    if relevant <= set(output["related_batches"]):
                        correct_scope_times.append(max(0.0, (parse_time(evaluated_at) - parse_time(origin)).total_seconds() / 60))
                        break
                for evaluated_at, output in outputs:
                    if output["actions_now"] and output["decision_branches"]:
                        decision_ready_times.append(max(0.0, (parse_time(evaluated_at) - parse_time(origin)).total_seconds() / 60))
                        break
        total_detected = len(true_detected) + len(false_detected)
        results["modes"][mode] = {
            "incident_recall": len(true_detected) / len(true_batches),
            "precision": len(true_detected) / total_detected if total_detected else 0.0,
            "false_positive_rate": len(false_detected) / len(normal_batches),
            "time_to_first_investigation_minutes": mean(delays),
            "time_to_correct_scope_minutes": mean(correct_scope_times),
            "time_to_decision_ready_minutes": mean(decision_ready_times),
            "related_batch_recall": mean(scope_scores),
            "evidence_grounding_accuracy": valid_citations / citations if citations else 1.0,
            "future_leakage": future_citations,
            "existing_evidence_retrieval_coverage": len(retrieved_existing & available_existing) / len(available_existing) if available_existing else 1.0,
            "available_work_completed_before_next_physical_result": completed_before_physical / total_before_physical if total_before_physical else 1.0,
            "unnecessary_new_evidence_requests": len(unnecessary_request_ids),
            **summarize_rollouts(rollout_metrics),
        }
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results
