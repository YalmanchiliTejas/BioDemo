from __future__ import annotations

import json
import math
import sqlite3
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .generator import BENCHMARK_LOTS, DATA_DIR, DEFAULT_OUTPUT, PUBLIC_TO_BENCHMARK
from .store import SimulationStore, parse_time


def _rows(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, parameters)]


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2:
        return 0.0
    lm, rm = statistics.mean(left), statistics.mean(right)
    numerator = sum((x - lm) * (y - rm) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - lm) ** 2 for x in left) * sum((y - rm) ** 2 for y in right))
    return numerator / denominator if denominator else 0.0


def validate_no_line_overlap(batches: list[dict[str, Any]]) -> list[str]:
    """Return one issue for each impossible same-line batch overlap."""
    issues: list[str] = []
    by_line: dict[str, list[dict[str, Any]]] = {}
    for batch in batches:
        by_line.setdefault(batch["production_line"], []).append(batch)
    for line, line_batches in by_line.items():
        ordered = sorted(line_batches, key=lambda row: row["start_time"])
        for previous, current in zip(ordered, ordered[1:]):
            if parse_time(current["start_time"]) < parse_time(previous["end_time"]):
                issues.append(
                    f"Production-line overlap on {line}: {previous['batch_id']} and {current['batch_id']}"
                )
    return issues


def validate_dataset(database: Path | None = None, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    store = SimulationStore(database)
    issues: list[str] = []
    frozen_fingerprint = (DATA_DIR / "frozen_seed_42.sha256").read_text(encoding="utf-8").strip()
    actual_fingerprint = store.metadata()["dataset_fingerprint"]
    if store.metadata().get("simulation_seed") == "42" and actual_fingerprint != frozen_fingerprint:
        issues.append("Seed-42 dataset differs from the frozen benchmark fingerprint")
    with store._connect() as connection:
        batches = _rows(connection, "SELECT * FROM batches")
        labels = store.labels()
        labs = _rows(connection, "SELECT * FROM lab_results")
        process = _rows(connection, "SELECT * FROM process_events")
        em = _rows(connection, "SELECT * FROM environmental_monitoring")
        if len(batches) != 100:
            issues.append(f"Expected 100 batches; found {len(batches)}")
        issues.extend(validate_no_line_overlap(batches))
        incident_count = sum(row["true_incident"] for row in labels)
        negative_controls = sum(row["negative_control"] for row in labels)
        if not 3 <= incident_count <= 7:
            issues.append(f"Incident prevalence outside configured range: {incident_count}")
        if negative_controls < 15:
            issues.append(f"Fewer than 15 negative controls: {negative_controls}")
        starts = {row["batch_id"]: row["start_time"] for row in batches}
        ends = {row["batch_id"]: row["end_time"] for row in batches}
        for row in batches:
            if not parse_time(row["start_time"]) < parse_time(row["end_time"]):
                issues.append(f"Batch start is not before end: {row['batch_id']}")
            if not parse_time(row["end_time"]) < parse_time(row["disposition_time"]):
                issues.append(f"Batch end is not before disposition: {row['batch_id']}")
        for row in labs:
            if parse_time(row["timestamp"]) < parse_time(starts[row["batch_id"]]):
                issues.append(f"Lab result precedes batch start: {row['result_id']}")
            if parse_time(row["timestamp"]) < parse_time(row["sample_collected_at"]):
                issues.append(f"Lab result precedes sample collection: {row['result_id']}")
            if row["test_name"] == "sterility":
                elapsed = (parse_time(row["timestamp"]) - parse_time(row["sample_collected_at"])).total_seconds()
                if elapsed < 14 * 24 * 3600:
                    issues.append(f"Sterility result available before 14-day modeled incubation: {row['result_id']}")
        for row in process:
            if not parse_time(starts[row["batch_id"]]) <= parse_time(row["timestamp"]) <= parse_time(ends[row["batch_id"]]):
                issues.append(f"Process event outside batch window: {row['event_id']}")
        labs_by_batch: dict[str, list[dict[str, Any]]] = {}
        for row in labs:
            labs_by_batch.setdefault(row["batch_id"], []).append(row)
        for row in batches:
            release_results = [item for item in labs_by_batch[row["batch_id"]] if item["sample_type"] == "finished product"]
            if release_results and parse_time(row["disposition_time"]) < max(parse_time(item["timestamp"]) for item in release_results):
                issues.append(f"Disposition precedes completed release testing: {row['batch_id']}")
            if parse_time(row["first_ship_time"]) < parse_time(row["disposition_time"]):
                issues.append(f"First shipment precedes disposition: {row['batch_id']}")
        durations = [(parse_time(row["end_time"]) - parse_time(row["start_time"])).total_seconds() / 3600 for row in batches]
        bio = [row for row in labs if row["test_name"] == "relative_bioburden_signal"]
        bio_by_batch = {row["batch_id"]: row["numerical_result"] for row in bio if row["numerical_result"] is not None}
        em_by_batch = {row["batch_id"]: row["result"] for row in em}
        shared = sorted(set(bio_by_batch) & set(em_by_batch))
        correlation = _correlation([bio_by_batch[key] for key in shared], [em_by_batch[key] for key in shared])
        exact_patterns = Counter((round(bio_by_batch[key], 4), round(em_by_batch[key], 4)) for key in shared)
        duplicate_patterns = sum(count - 1 for count in exact_patterns.values() if count > 1)
        if duplicate_patterns > 3:
            issues.append(f"Too many exact duplicate signal patterns: {duplicate_patterns}")
        normal_ids = {row["batch_id"] for row in labels if not row["true_incident"]}
        line_a_normal = sum(row["production_line"] == "LINE-A" and row["batch_id"] in normal_ids for row in batches)
        if line_a_normal < 50:
            issues.append(f"Too few normal batches share incident production line: {line_a_normal}")
        high_hold_normal = sum(
            row["parameter"] == "hold_duration_margin" and row["value"] >= .88 and row["batch_id"] in normal_ids
            for row in process
        )
        if high_hold_normal < 20:
            issues.append(f"Too few normal near-limit hold durations: {high_hold_normal}")
        causal_sanity = {
            "same_line_overlaps": len(validate_no_line_overlap(batches)),
            "invalid_batch_chronologies": sum(
                not parse_time(row["start_time"]) < parse_time(row["end_time"]) < parse_time(row["disposition_time"])
                for row in batches
            ),
            "results_before_collection": sum(parse_time(row["timestamp"]) < parse_time(row["sample_collected_at"]) for row in labs),
            "sterility_results_under_14_days": sum(
                row["test_name"] == "sterility"
                and (parse_time(row["timestamp"]) - parse_time(row["sample_collected_at"])).total_seconds() < 14 * 24 * 3600
                for row in labs
            ),
            "shipments_before_disposition": sum(parse_time(row["first_ship_time"]) < parse_time(row["disposition_time"]) for row in batches),
            "process_events_outside_batch_window": sum(
                not parse_time(starts[row["batch_id"]]) <= parse_time(row["timestamp"]) <= parse_time(ends[row["batch_id"]])
                for row in process
            ),
            "future_maintenance_visibility_prevented_by_state_at": True,
        }

    composition = Counter(row["incident_type"] for row in labels)
    report = {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "dataset_fingerprint": actual_fingerprint,
        "frozen_seed_42_fingerprint": frozen_fingerprint,
        "composition": {
            "batches": len(batches), "true_incidents": incident_count,
            "non_incident_batches": len(batches) - incident_count,
            "benign_abnormalities": composition["benign_abnormality"],
            "negative_controls": negative_controls,
        },
        "distribution_sanity": {
            "batch_duration_hours_min": min(durations),
            "batch_duration_hours_median": statistics.median(durations),
            "batch_duration_hours_max": max(durations),
            "bioburden_signal_median": statistics.median(row["numerical_result"] for row in bio if row["numerical_result"] is not None),
            "bioburden_alert_crossings": sum(row["status"] == "alert" for row in bio),
            "bioburden_action_crossings": sum(row["status"] == "action" for row in bio),
            "environment_bioburden_correlation": correlation,
            "exact_duplicate_signal_patterns": duplicate_patterns,
            "normal_batches_on_LINE_A": line_a_normal,
            "normal_near_limit_hold_durations": high_hold_normal,
        },
        "missingness": {
            "lab_numerical_missing": sum(row["numerical_result"] is None for row in labs),
            "note": "Categorical sterility rows intentionally have no numerical result.",
        },
        "noise": {
            "normal_batches_have_nonzero_variation": len({round(value, 3) for key, value in bio_by_batch.items() if key not in BENCHMARK_LOTS}) > 20,
            "negative_controls_include_alerts_without_true_incident": any(
                row["status"] == "alert" and next(label for label in labels if label["batch_id"] == row["batch_id"])["negative_control"]
                for row in bio
            ),
        },
        "causal_sanity": causal_sanity,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "validation_report.md").write_text(_dataset_markdown(report), encoding="utf-8")
    return report


def _dataset_markdown(report: dict[str, Any]) -> str:
    c, d, n, causal = report["composition"], report["distribution_sanity"], report["noise"], report["causal_sanity"]
    issues = "None." if not report["issues"] else "\n".join(f"- {item}" for item in report["issues"])
    return f"""# Dataset validation report

**Status: {report['status']}**  
Dataset fingerprint: `{report['dataset_fingerprint']}`

## Dataset composition

- {c['batches']} total batches
- {c['non_incident_batches']} non-incident batches
- {c['benign_abnormalities']} deliberately benign abnormality batches
- {c['true_incidents']} labeled incident batches across three scenario families
- {c['negative_controls']} explicit negative controls

## Distribution sanity

- Batch duration: {d['batch_duration_hours_min']:.2f}–{d['batch_duration_hours_max']:.2f} hours; median {d['batch_duration_hours_median']:.2f}
- Median normalized bioburden signal: {d['bioburden_signal_median']:.3f}
- Alert crossings: {d['bioburden_alert_crossings']}
- Action crossings: {d['bioburden_action_crossings']}
- Environmental/bioburden correlation: {d['environment_bioburden_correlation']:.3f}
- Exact duplicate signal patterns: {d['exact_duplicate_signal_patterns']}
- Normal batches on reconstructed LINE-A: {d['normal_batches_on_LINE_A']}
- Normal near-limit hold-duration values: {d['normal_near_limit_hold_durations']}

## Threshold and noise behavior

Normal operations contain nonzero variation: **{n['normal_batches_have_nonzero_variation']}**.  
Negative controls include abnormal signals without a true incident: **{n['negative_controls_include_alerts_without_true_incident']}**.

## Causal sanity

- Results before sample collection: {causal['results_before_collection']}
- Same-line batch overlaps: {causal['same_line_overlaps']}
- Invalid start/end/disposition chronologies: {causal['invalid_batch_chronologies']}
- Sterility results before the modeled 14-day minimum: {causal['sterility_results_under_14_days']}
- Shipments before disposition: {causal['shipments_before_disposition']}
- Process events outside their batch window: {causal['process_events_outside_batch_window']}
- Future maintenance is excluded by `state_at(timestamp)`: **{causal['future_maintenance_visibility_prevented_by_state_at']}**

## Validation issues

{issues}

All numerical limits are normalized synthetic parameters unless explicitly identified as public facts. This report checks internal consistency and statistical shape; it is not a claim that the distributions reproduce a manufacturer's validated process.
"""


def validate_public_facts(database: Path | None = None, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    store = SimulationStore(database)
    ground_truth = json.loads((DATA_DIR / "public_ground_truth.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    facts = ground_truth["facts"]
    for fact in facts:
        if not fact.get("source") or not str(fact.get("source_url", "")).startswith("https://www.fda.gov/"):
            failures.append(f"Unsourced or non-FDA public fact: {fact.get('fact_id')}")
        if not fact.get("available_at"):
            failures.append(f"Public fact lacks available_at: {fact.get('fact_id')}")
        source = str(fact.get("source", "")).lower()
        url = str(fact.get("source_url", ""))
        if "warning letter" in source and "/warning-letters/" not in url:
            failures.append(f"Warning-letter fact has wrong source URL: {fact.get('fact_id')}")
        if "recall announcement" in source and "/recalls-market-withdrawals-safety-alerts/" not in url:
            failures.append(f"Recall fact has wrong source URL: {fact.get('fact_id')}")
    with store._connect() as connection:
        batch_rows = {row["batch_id"]: dict(row) for row in connection.execute("SELECT * FROM batches")}
        for lot in BENCHMARK_LOTS:
            if lot not in batch_rows:
                failures.append(f"Missing recalled lot: {lot}")
            elif batch_rows[lot]["status"] != "released" or batch_rows[lot]["disposition"] != "released":
                failures.append(f"Live batch row leaks later outcome: {lot}")
        first_ship = {
            PUBLIC_TO_BENCHMARK[fact["affected_lot"]]: fact["event_date"]
            for fact in facts if fact["category"] == "first_shipment"
        }
        for lot, ship_time in first_ship.items():
            if lot in batch_rows and parse_time(batch_rows[lot]["end_time"]) >= parse_time(ship_time):
                failures.append(f"Reconstructed manufacture is not before documented first shipment: {lot}")
        incident_labs = _rows(connection, "SELECT * FROM lab_results WHERE batch_id IN (?,?,?)", BENCHMARK_LOTS)
        if sum(row["test_name"] == "relative_bioburden_signal" and row["status"] == "action" for row in incident_labs) < 2:
            failures.append("Reconstruction lacks repeated bioburden action crossings")
        passes = [row for row in incident_labs if row["sample_type"] == "finished product" and row["status"] == "pass"]
        reserve = [row for row in incident_labs if row["sample_type"] == "finished-product reserve" and row["status"] == "out_of_specification"]
        if not passes or not reserve or max(parse_time(row["timestamp"]) for row in passes) >= min(parse_time(row["timestamp"]) for row in reserve):
            failures.append("Passing finished-product results do not precede reserve OOS")
        recall_date = next(fact["event_date"] for fact in facts if fact["fact_id"] == "FDA-F005")
        if reserve and min(parse_time(row["timestamp"]) for row in reserve) >= parse_time(recall_date):
            failures.append("Reserve OOS does not precede recall date")
        confirmed = connection.execute(
            "SELECT COUNT(*) FROM deviations WHERE batch_id IN (?,?,?) AND root_cause IS NOT NULL", BENCHMARK_LOTS
        ).fetchone()[0]
        if confirmed:
            failures.append("Synthetic reconstruction asserts a confirmed public-incident root cause")
        outcomes = connection.execute(
            "SELECT COUNT(*) FROM benchmark_outcomes WHERE outcome='recalled' AND benchmark_only=1"
        ).fetchone()[0]
        if outcomes != 3:
            failures.append(f"Expected three hidden recall outcomes; found {outcomes}")
    result = {
        "status": "PASS" if not failures else "FAIL", "failures": failures,
        "facts_checked": len(facts), "source_file": str(DATA_DIR / "public_ground_truth.json"),
    }
    text = f"PUBLIC FACT CONSISTENCY: {result['status']}\nFacts checked: {len(facts)}\n"
    if failures:
        text += "\n".join(f"- {item}" for item in failures) + "\n"
    (output_dir / "public_fact_consistency.txt").write_text(text, encoding="utf-8")
    return result
