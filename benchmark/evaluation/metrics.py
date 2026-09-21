from __future__ import annotations

from statistics import mean

from benchmark.factory.state import FactoryState
from benchmark.systems import SystemRegistry


def _avg(values: list[float]) -> float:
    return round(mean(values), 2) if values else 0.0


def calculate_metrics(state: FactoryState, systems: SystemRegistry, duration_h: int, scenario_fingerprint: str) -> dict:
    released = [b for b in state.batches.values() if b.stage == "released"]
    completed = released + [b for b in state.batches.values() if b.rejected]
    good_kg = sum(b.plan.target_kg * b.yield_fraction for b in released)
    starts = [b for b in state.batches.values() if b.actual_start_hour is not None]
    adherence = sum((b.actual_start_hour or 0) <= b.plan.planned_start_hour + 8 for b in starts) / len(starts) if starts else 0
    investigations = state.investigations
    deviation_durations = [
        d["closed_hour"] - d["opened_hour"]
        for d in systems.qms.deviations
        if d["closed_hour"] is not None and d["closed_hour"] <= duration_h
    ]
    return {
        "campaign": {
            "duration_days": duration_h / 24,
            "scenario_fingerprint": scenario_fingerprint,
            "scenario_count": len(investigations),
        },
        "primary": {
            "released_batches_per_month": len(released),
            "good_released_product_kg_per_month": round(good_kg, 3),
        },
        "manufacturing": {
            "mean_released_yield_fraction": round(mean([b.yield_fraction for b in released]), 4) if released else 0,
            "throughput_kg_per_day": round(good_kg / (duration_h / 24), 4),
            "equipment_utilization_fraction": round(state.actual_production_h / (duration_h * 2), 4),
            "unplanned_downtime_hours": state.unplanned_downtime_h,
            "schedule_adherence_fraction": round(adherence, 4),
            "mean_batch_cycle_time_hours": _avg([(b.released_hour or duration_h) - (b.actual_start_hour or 0) for b in released]),
        },
        "quality": {
            "deviation_count": len(systems.qms.deviations),
            "open_deviations_at_campaign_end": sum((d["closed_hour"] or duration_h + 1) > duration_h for d in systems.qms.deviations),
            "mean_deviation_closure_hours": _avg(deviation_durations),
            "batch_rejection_rate": round(state.rejected_batches / len(completed), 4) if completed else 0,
            "batch_rework_rate": round(state.reworked_batches / len(completed), 4) if completed else 0,
            "repeat_deviations": sum(d["scenario_id"] == "S11" for d in systems.qms.deviations),
            "mean_batch_release_time_hours": _avg([(b.released_hour or duration_h) - (b.qc_complete_hour or 0) for b in released]),
            "right_first_time_rate": round(sum(not b.reworked for b in released) / len(released), 4) if released else 0,
        },
        "msat_process_engineering": {
            "mean_time_to_detect_hours": _avg([i.detected_hour - i.triggered_hour for i in investigations]),
            "mean_time_to_diagnose_hours": _avg([i.diagnosed_hour - i.detected_hour for i in investigations]),
            "mean_time_to_intervention_hours": _avg([i.intervention_hour - i.detected_hour for i in investigations]),
            "total_engineer_hours": round(sum(i.engineer_hours for i in investigations), 2),
            "mean_engineer_hours_per_investigation": _avg([i.engineer_hours for i in investigations]),
            "mean_systems_accessed_per_investigation": _avg([len(i.systems_accessed) for i in investigations]),
            "investigations_per_engineer_month": len(investigations) / 2,
        },
    }
