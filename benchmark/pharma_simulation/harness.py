from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .agent import BenchmarkAgent, validate_output
from .generator import DEFAULT_OUTPUT
from .rules_baseline import assess_rules
from .store import SimulationStore, parse_time


TRIAGE_RANK = {"NONE": 0, "L1": 1, "L2": 2, "L3": 3}
CONDITIONS = {
    "A_current_event_only": "current_event_only",
    "B_current_batch_plus_LIMS": "lims_only",
    "C_current_batch_plus_LIMS_QMS": "lims_qms",
    "D_full_OS_context": "full_os",
}


def _all_refs(output: dict[str, Any]) -> list[str]:
    refs = list(output.get("evidence_ids", []))
    for item in output.get("hypotheses", []):
        refs.extend(item.get("supporting_evidence_ids", []))
        refs.extend(item.get("contradicting_evidence_ids", []))
    return refs


def _overlap(predicted: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    predicted_words = [set(item.lower().replace("-", " ").split()) for item in predicted]
    matched = 0
    for target in expected:
        target_words = set(target.lower().replace("-", " ").split())
        if any(len(target_words & words) / max(1, len(target_words)) >= .5 for words in predicted_words):
            matched += 1
    return matched / len(expected)


def _evaluate(
    store: SimulationStore,
    *,
    name: str,
    context: str,
    assessment: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, int]]],
    include_memory: bool = False,
) -> dict[str, Any]:
    labels = store.labels()
    batch_outcomes: dict[str, dict[str, Any]] = {}
    citation_totals = {"cited": 0, "valid": 0, "stripped": 0}
    for label in labels:
        batch_id = label["batch_id"]
        ideal_rank = TRIAGE_RANK[label["ideal_escalation_level"]]
        best_rank = 0
        detected_at: str | None = None
        best_output: dict[str, Any] = {}
        for event in store.event_stream(batch_id):
            state = store.state_at(
                event["_timestamp"], current_batch_id=batch_id,
                context=context, current_event=event, include_memory=include_memory,
            )
            output, audit = assessment(state)
            for key in citation_totals:
                citation_totals[key] += audit[key]
            rank = TRIAGE_RANK[output["triage_level"]]
            if rank >= best_rank:
                best_rank = rank
                best_output = output
            threshold = ideal_rank if label["true_incident"] else max(TRIAGE_RANK["L2"], ideal_rank + 1)
            if detected_at is None and rank >= threshold:
                detected_at = event["_timestamp"]
        batch_outcomes[batch_id] = {
            "detected_at": detected_at, "best_rank": best_rank, "best_output": best_output,
        }

    true_labels = [row for row in labels if row["true_incident"]]
    normal_labels = [row for row in labels if not row["true_incident"]]
    true_detected = [row for row in true_labels if batch_outcomes[row["batch_id"]]["detected_at"]]
    false_detected = [row for row in normal_labels if batch_outcomes[row["batch_id"]]["detected_at"]]
    all_detected = len(true_detected) + len(false_detected)
    delays: list[float] = []
    triage_correct = 0
    scope_scores: list[float] = []
    hypothesis_scores: list[float] = []
    action_scores: list[float] = []
    delay_by_batch: dict[str, float | None] = {}
    for label in true_labels:
        outcome = batch_outcomes[label["batch_id"]]
        if outcome["detected_at"] and label["earliest_detectable_timestamp"]:
            delay = (parse_time(outcome["detected_at"]) - parse_time(label["earliest_detectable_timestamp"])).total_seconds() / 60
            delay_by_batch[label["batch_id"]] = max(0.0, delay)
            delays.append(delay_by_batch[label["batch_id"]])
        else:
            delay_by_batch[label["batch_id"]] = None
        if outcome["best_rank"] == TRIAGE_RANK[label["ideal_escalation_level"]]:
            triage_correct += 1
        output = outcome["best_output"]
        relevant = set(label["relevant_batch_ids"])
        surfaced = set(output.get("related_batch_ids", []))
        scope_scores.append(len(relevant & surfaced) / len(relevant) if relevant else 1.0)
        hypothesis_scores.append(_overlap(
            [item["hypothesis"] for item in output.get("hypotheses", [])],
            label["plausible_hypotheses"],
        ))
        action_scores.append(_overlap(output.get("recommended_actions", []), label["expected_actions"]))

    cited = citation_totals["cited"]
    metrics = {
        "condition": name,
        "incident_detection_recall": len(true_detected) / len(true_labels),
        "precision": len(true_detected) / all_detected if all_detected else 0.0,
        "false_positive_rate": len(false_detected) / len(normal_labels),
        "median_time_to_detection_minutes": statistics.median(delays) if delays else None,
        "triage_accuracy": triage_correct / len(true_labels),
        "evidence_grounding_accuracy": citation_totals["valid"] / cited if cited else 1.0,
        "future_leakage_rate": citation_totals["stripped"] / cited if cited else 0.0,
        "investigation_scope_recall": statistics.mean(scope_scores),
        "hypothesis_relevance": statistics.mean(hypothesis_scores),
        "action_relevance": statistics.mean(action_scores),
        "true_incidents": len(true_labels),
        "true_incidents_detected": len(true_detected),
        "false_positive_batches": len(false_detected),
        "evaluated_batches": len(labels),
        "citation_audit": citation_totals,
        "time_to_detection_minutes_by_incident_batch": delay_by_batch,
    }
    return metrics


def run_validation(
    database: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    live: bool = False,
    provider: Any = None,
) -> dict[str, Any]:
    store = SimulationStore(database)
    agent = BenchmarkAgent(provider)

    def rules(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
        raw = assess_rules(state)
        return validate_output(raw, set(state["visible_evidence_ids"]))

    def contextual(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
        return agent.assess(state, live=live)

    results: dict[str, Any] = {
        "dataset_fingerprint": store.metadata()["dataset_fingerprint"],
        "live_provider_used": bool(live and provider),
        "rules_baseline": _evaluate(store, name="rules_baseline", context="current_event_only", assessment=rules),
        "ablations": {},
    }
    for name, context in CONDITIONS.items():
        results["ablations"][name] = _evaluate(store, name=name, context=context, assessment=contextual)
    results["memory_ablation"] = {
        "A_no_manufacturing_memory": results["ablations"]["D_full_OS_context"],
        "B_manufacturing_memory_enabled": _evaluate(
            store, name="full_OS_with_manufacturing_memory", context="full_os_with_memory",
            assessment=contextual, include_memory=True,
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (output_dir / "benchmark_results.md").write_text(_markdown(results), encoding="utf-8")
    return results


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _time(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value >= 1440:
        return f"{value / 1440:.1f} days"
    if value >= 60:
        return f"{value / 60:.1f} hr"
    return f"{value:.1f} min"


def _markdown(results: dict[str, Any]) -> str:
    selected = {
        "Rules baseline": results["rules_baseline"],
        "Context agent (deterministic)": results["ablations"]["C_current_batch_plus_LIMS_QMS"],
        "Full-context agent (deterministic)": results["ablations"]["D_full_OS_context"],
    }
    lines = [
        "# Computed benchmark results", "",
        f"Dataset fingerprint: `{results['dataset_fingerprint']}`", "",
        "> These are simulated benchmark results computed from the frozen synthetic dataset. They are not claims about the historical manufacturer or avoided recalls.", "",
        "| Metric | " + " | ".join(selected) + " |",
        "|---|" + "---:|" * len(selected),
    ]
    rows = [
        ("Incident recall", "incident_detection_recall", _percent),
        ("Precision", "precision", _percent),
        ("False-positive rate", "false_positive_rate", _percent),
        ("Median time-to-detection", "median_time_to_detection_minutes", _time),
        ("Triage accuracy", "triage_accuracy", _percent),
        ("Evidence grounding", "evidence_grounding_accuracy", _percent),
        ("Future leakage", "future_leakage_rate", _percent),
        ("Investigation-scope recall", "investigation_scope_recall", _percent),
        ("Hypothesis relevance", "hypothesis_relevance", _percent),
        ("Action relevance", "action_relevance", _percent),
    ]
    for label, key, formatter in rows:
        lines.append(f"| {label} | " + " | ".join(formatter(value[key]) for value in selected.values()) + " |")
    lines.extend(["", "## Ablation results", "", "| Condition | Recall | Precision | FPR | Median TTD | Scope recall |", "|---|---:|---:|---:|---:|---:|"])
    for name, value in results["ablations"].items():
        lines.append(
            f"| {name} | {_percent(value['incident_detection_recall'])} | {_percent(value['precision'])} | "
            f"{_percent(value['false_positive_rate'])} | {_time(value['median_time_to_detection_minutes'])} | "
            f"{_percent(value['investigation_scope_recall'])} |"
        )
    lines.extend(["", "## Manufacturing-memory ablation", "", "| Condition | Recall | Median TTD | First reconstructed lot TTD | Scope recall |", "|---|---:|---:|---:|---:|"])
    for name, value in results["memory_ablation"].items():
        lines.append(
            f"| {name} | {_percent(value['incident_detection_recall'])} | "
            f"{_time(value['median_time_to_detection_minutes'])} | "
            f"{_time(value['time_to_detection_minutes_by_incident_batch'].get('BATCH-075'))} | "
            f"{_percent(value['investigation_scope_recall'])} |"
        )
    lines.extend([
        "", "## Interpretation", "",
        "The ablation changes only information availability. Evaluation labels are held outside agent-visible state. Broader context should improve recurrence recognition, triage, and investigation scope; the actual values above are generated by the benchmark run.", "",
        "## Limitations", "",
        "This committed run uses the deterministic contextual agent, not an LLM. The scenario labels and deterministic policy were authored within the same benchmark project, so perfect scores are internal consistency results—not independent evidence of real-world performance. The frozen fingerprint prevents post-score dataset tuning, while the blind SME package supports independent realism and label review. External claims require a versioned held-out dataset and adjudication by manufacturing SMEs.", "",
    ])
    return "\n".join(lines)
