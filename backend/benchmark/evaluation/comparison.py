from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from benchmark.simulation import BenchmarkSimulation


ENDPOINTS = {
    "engineer_hours": ("msat_process_engineering", "total_engineer_hours", "lower"),
    "time_to_diagnose_hours": ("msat_process_engineering", "mean_time_to_diagnose_hours", "lower"),
    "time_to_intervention_hours": ("msat_process_engineering", "mean_time_to_intervention_hours", "lower"),
    "deviation_closure_hours": ("quality", "mean_deviation_closure_hours", "lower"),
    "investigation_output_quality": ("investigation_output_quality", "composite_score", "higher"),
    "required_evidence_coverage": ("investigation_output_quality", "mean_required_evidence_coverage_fraction", "higher"),
    "approval_compliance": ("investigation_output_quality", "approval_compliance_rate", "higher"),
    "good_released_product_kg": ("primary", "good_released_product_kg_per_month", "higher"),
    "batch_rejection_rate": ("quality", "batch_rejection_rate", "lower"),
    "right_first_time_rate": ("quality", "right_first_time_rate", "higher"),
}


def compare_modes(*, seed: int, runs: int, output_dir: Path | None = None) -> dict[str, Any]:
    if runs < 1:
        raise ValueError("runs must be at least 1")
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for offset in range(runs):
        run_seed = seed + offset
        traditional_dir = output_dir / "runs" / str(run_seed) / "traditional" if output_dir else None
        assisted_dir = output_dir / "runs" / str(run_seed) / "agent_assisted" if output_dir else None
        traditional = BenchmarkSimulation(seed=run_seed, mode="traditional").run(traditional_dir).metrics
        assisted = BenchmarkSimulation(seed=run_seed, mode="agent_assisted").run(assisted_dir).metrics
        pairs.append((traditional, assisted))

    endpoints: dict[str, Any] = {}
    for name, (section, metric, direction) in ENDPOINTS.items():
        baseline = [float(pair[0][section][metric]) for pair in pairs]
        assisted = [float(pair[1][section][metric]) for pair in pairs]
        changes = [candidate - control for control, candidate in zip(baseline, assisted, strict=True)]
        baseline_mean = mean(baseline)
        change = mean(changes)
        endpoints[name] = {
            "direction": direction,
            "traditional_mean": round(baseline_mean, 4),
            "agent_assisted_mean": round(mean(assisted), 4),
            "absolute_change": round(change, 4),
            "relative_change_percent": round(100 * change / baseline_mean, 2) if baseline_mean else None,
            "paired_change_seed_sensitivity_range": [round(min(changes), 4), round(max(changes), 4)],
        }

    report = {
        "claim_status": "modeled_projection_not_empirical_validation",
        "interpretation": (
            "Paired deterministic simulation under explicit controller assumptions. "
            "Validate timing, labor, and quality rubric inputs in a prospective shadow study before making customer claims."
        ),
        "seed_start": seed,
        "paired_runs": runs,
        "scenario_count_per_run": pairs[0][0]["campaign"]["scenario_count"],
        "endpoints": endpoints,
    }
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "comparison.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
