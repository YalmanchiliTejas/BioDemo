from __future__ import annotations

import json
import statistics
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .generator import DEFAULT_OUTPUT, generate
from .harness import run_validation
from .validation import validate_dataset, validate_public_facts


METRICS = (
    "incident_detection_recall", "precision", "false_positive_rate",
    "median_time_to_detection_minutes", "triage_accuracy",
    "evidence_grounding_accuracy", "future_leakage_rate",
    "investigation_scope_recall",
)


def run_robustness(seeds: Iterable[int], output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        with tempfile.TemporaryDirectory(prefix=f"pharma-sim-{seed}-") as temporary:
            run_dir = Path(temporary)
            manifest = generate(seed, run_dir)
            dataset_check = validate_dataset(run_dir / "pharma_simulation.db", run_dir)
            public_check = validate_public_facts(run_dir / "pharma_simulation.db", run_dir)
            benchmark = run_validation(run_dir / "pharma_simulation.db", run_dir)
            runs.append({
                "seed": seed, "fingerprint": manifest["dataset_fingerprint"],
                "dataset_validation": dataset_check["status"],
                "public_fact_consistency": public_check["status"],
                "full_context": benchmark["ablations"]["D_full_OS_context"],
                "current_event_only": benchmark["ablations"]["A_current_event_only"],
            })
    summary: dict[str, Any] = {}
    for condition in ("current_event_only", "full_context"):
        summary[condition] = {}
        for metric in METRICS:
            values = [run[condition][metric] for run in runs if run[condition][metric] is not None]
            summary[condition][metric] = {
                "mean": statistics.mean(values) if values else None,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
            }
    result = {
        "seed_count": len(runs), "seeds": [run["seed"] for run in runs],
        "all_dataset_validations_passed": all(run["dataset_validation"] == "PASS" for run in runs),
        "all_public_fact_checks_passed": all(run["public_fact_consistency"] == "PASS" for run in runs),
        "summary": summary, "runs": runs,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "robustness_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output_dir / "robustness_report.md").write_text(_markdown(result), encoding="utf-8")
    return result


def _fmt(value: float | None, percent: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%" if percent else f"{value:.1f} min"


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Multi-seed robustness report", "",
        f"Seeds evaluated: **{result['seed_count']}** (`{result['seeds'][0]}` through `{result['seeds'][-1]}`)", "",
        f"All dataset causal/statistical checks passed: **{result['all_dataset_validations_passed']}**  ",
        f"All public-fact consistency checks passed: **{result['all_public_fact_checks_passed']}**", "",
        "| Condition | Metric | Mean | Min | Max |", "|---|---|---:|---:|---:|",
    ]
    for condition, metrics in result["summary"].items():
        for metric, values in metrics.items():
            percent = metric != "median_time_to_detection_minutes"
            lines.append(
                f"| {condition} | {metric} | {_fmt(values['mean'], percent)} | "
                f"{_fmt(values['min'], percent)} | {_fmt(values['max'], percent)} |"
            )
    lines.extend([
        "", "> Each seed changes normal variation, durations, missingness, benign-scenario placement, line assignment, and irrelevant contextual records while preserving fixed public facts and scenario semantics.", "",
        "These are synthetic robustness results, not estimates of real-world manufacturing prevalence or performance.", "",
    ])
    return "\n".join(lines)

