from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_ROOT / "data"
DEFAULT_OUTPUT = PACKAGE_ROOT / "artifacts"
DEMO_DATA_PATH = PACKAGE_ROOT.parent / "incident_demo" / "data" / "fresenius_famotidine_demo.json"
DEMO_DATA_DIR = DEMO_DATA_PATH.parent
DATASET_VERSION = "v1.0-frozen"
DATASET_CREATED_AT = "2026-10-07T00:00:00Z"
PUBLIC_LOTS = ("6133156", "6133194", "6133388")
PUBLIC_TO_BENCHMARK = {
    "6133156": "BATCH-075",
    "6133194": "BATCH-084",
    "6133388": "BATCH-099",
}
BENCHMARK_LOTS = tuple(PUBLIC_TO_BENCHMARK.values())
TABLES = (
    "batches", "lab_results", "process_events", "environmental_monitoring",
    "deviations", "maintenance", "complaints", "operator_events",
    "incident_memory", "benchmark_outcomes", "simulation_labels",
)


SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE batches (
  batch_id TEXT PRIMARY KEY, product TEXT NOT NULL, dosage_form TEXT NOT NULL,
  production_line TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
  status TEXT NOT NULL, disposition TEXT NOT NULL,
  disposition_time TEXT, first_ship_time TEXT
);
CREATE TABLE lab_results (
  result_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, timestamp TEXT NOT NULL,
  sample_collected_at TEXT NOT NULL,
  sample_type TEXT NOT NULL, test_name TEXT NOT NULL, numerical_result REAL,
  categorical_result TEXT, unit TEXT, specification_limit REAL, alert_limit REAL,
  action_limit REAL, status TEXT NOT NULL, organism TEXT, synthetic_reason TEXT NOT NULL
);
CREATE TABLE process_events (
  event_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, timestamp TEXT NOT NULL,
  equipment_id TEXT NOT NULL, parameter TEXT NOT NULL, value REAL,
  expected_low REAL, expected_high REAL, severity TEXT NOT NULL,
  event_type TEXT NOT NULL, synthetic_reason TEXT NOT NULL
);
CREATE TABLE environmental_monitoring (
  sample_id TEXT PRIMARY KEY, batch_id TEXT, timestamp TEXT NOT NULL,
  location TEXT NOT NULL, sample_type TEXT NOT NULL, result REAL NOT NULL,
  alert_limit REAL NOT NULL, action_limit REAL NOT NULL, organism TEXT,
  status TEXT NOT NULL
);
CREATE TABLE deviations (
  deviation_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, opened_at TEXT NOT NULL,
  closed_at TEXT, category TEXT NOT NULL, severity TEXT NOT NULL,
  description TEXT NOT NULL, investigation_status TEXT NOT NULL, root_cause TEXT,
  capa TEXT, recurrence_flag INTEGER NOT NULL, public_or_synthetic TEXT NOT NULL
);
CREATE TABLE maintenance (
  work_order TEXT PRIMARY KEY, timestamp TEXT NOT NULL, equipment_id TEXT NOT NULL,
  work_type TEXT NOT NULL, description TEXT NOT NULL, action TEXT NOT NULL,
  status TEXT NOT NULL, linked_batch_id TEXT
);
CREATE TABLE complaints (
  complaint_id TEXT PRIMARY KEY, product TEXT NOT NULL, lot TEXT NOT NULL,
  timestamp TEXT NOT NULL, description TEXT NOT NULL, severity TEXT NOT NULL,
  outcome TEXT, public_or_synthetic TEXT NOT NULL
);
CREATE TABLE operator_events (
  operator_event_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, timestamp TEXT NOT NULL,
  role TEXT NOT NULL, event_type TEXT NOT NULL, description TEXT NOT NULL,
  severity TEXT NOT NULL
);
CREATE TABLE incident_memory (
  incident_id TEXT PRIMARY KEY, pattern_signature TEXT NOT NULL, symptoms TEXT NOT NULL,
  evidence_ids TEXT NOT NULL, confirmed_root_cause TEXT, actions TEXT NOT NULL,
  outcome TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE benchmark_outcomes (
  outcome_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, outcome TEXT NOT NULL,
  effective_at TEXT NOT NULL, available_at TEXT NOT NULL, public_fact_id TEXT,
  benchmark_only INTEGER NOT NULL
);
CREATE TABLE simulation_labels (
  batch_id TEXT PRIMARY KEY, true_incident INTEGER NOT NULL, true_severity TEXT NOT NULL,
  incident_type TEXT NOT NULL, earliest_detectable_timestamp TEXT,
  ideal_escalation_level TEXT NOT NULL, rationale TEXT NOT NULL,
  evidence_required TEXT NOT NULL, relevant_batch_ids TEXT NOT NULL,
  relevant_equipment_ids TEXT NOT NULL, plausible_hypotheses TEXT NOT NULL,
  expected_actions TEXT NOT NULL, expected_teams TEXT NOT NULL,
  negative_control INTEGER NOT NULL, counterfactual_pair_id TEXT,
  counterfactual_role TEXT
);
CREATE INDEX lab_time_idx ON lab_results(timestamp);
CREATE INDEX process_time_idx ON process_events(timestamp);
CREATE INDEX em_time_idx ON environmental_monitoring(timestamp);
CREATE INDEX deviation_time_idx ON deviations(opened_at);
"""


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clamp(value: float, low: float, high: float) -> float:
    return round(max(low, min(high, value)), 4)


def _insert(connection: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    fields = list(row)
    connection.execute(
        f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
        [json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value for value in row.values()],
    )


def _batch_schedule() -> list[tuple[str, datetime]]:
    base = datetime(2024, 2, 5, 7, 0, tzinfo=timezone.utc)
    rows = [(f"SYN-{index:04d}", base + timedelta(days=index * 4)) for index in range(1, 98)]
    # SYN-0075 would otherwise overlap BATCH-075 on LINE-A. Its deterministic
    # one-day reschedule keeps the source population intact without overlap.
    rows = [(batch_id, start + timedelta(days=1) if batch_id == "SYN-0075" else start) for batch_id, start in rows]
    rows.extend([
        # Dates are reconstructed early enough to allow a 14-day sterility incubation
        # and documented disposition before the public first-ship dates.
        ("BATCH-075", datetime(2024, 12, 1, 6, 40, tzinfo=timezone.utc)),
        ("BATCH-084", datetime(2025, 1, 4, 7, 5, tzinfo=timezone.utc)),
        ("BATCH-099", datetime(2025, 3, 12, 6, 55, tzinfo=timezone.utc)),
    ])
    return sorted(rows, key=lambda item: (item[1], item[0]))


def generate(seed: int = 42, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = output_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "pharma_simulation.db"
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    metadata = {
        "simulation_seed": str(seed),
        "generator_version": "3.0",
        "dataset_version": DATASET_VERSION,
        "dataset_created_at": DATASET_CREATED_AT,
        "provenance_notice": (
            "Public incident facts are sourced. Internal measurements, timings, systems records, "
            "and telemetry are synthetic and do not represent manufacturer internal data."
        ),
    }
    for key, value in metadata.items():
        _insert(connection, "metadata", {"key": key, "value": value})

    synthetic_ids = [f"SYN-{index:04d}" for index in range(1, 90)]
    benign_ids = set(rng.sample(synthetic_ids, 8))
    remaining = [item for item in synthetic_ids if item not in benign_ids]
    low_deviation_ids = set(rng.sample(remaining, 4))
    negative_controls = set(rng.sample([item for item in remaining if item not in low_deviation_ids], 15)) | benign_ids
    benign_order = sorted(benign_ids)
    isolated_excursion_id = benign_order[0]
    resolved_sample_id = benign_order[1]
    benign_equipment_id = benign_order[2]
    benign_environment_ids = set(benign_order[3:6])
    high_hold_ids = set(rng.sample([item for item in synthetic_ids if item not in {"SYN-0090", "SYN-0091"}], 24))
    family_b = "SYN-0090"
    family_c = "SYN-0091"
    true_incidents = {*BENCHMARK_LOTS, family_b, family_c}
    rows_by_table: dict[str, list[dict[str, Any]]] = {table: [] for table in TABLES}
    counters = {"lab": 0, "process": 0, "em": 0, "dev": 0, "maint": 0, "op": 0}

    def add(table: str, row: dict[str, Any]) -> None:
        rows_by_table[table].append(row)
        _insert(connection, table, row)

    for order, (batch_id, start) in enumerate(_batch_schedule(), 1):
        duration_hours = clamp(rng.gauss(9.2, 0.8), 7.1, 11.5)
        end = start + timedelta(hours=duration_hours)
        is_public = batch_id in BENCHMARK_LOTS
        is_incident = batch_id in true_incidents
        product = "Famotidine Injection, USP" if is_public else rng.choice([
            "Famotidine Injection, USP", "Electrolyte Injection", "Saline Injection",
            "Ondansetron Injection", "Heparin Sodium Injection",
        ])
        if batch_id == isolated_excursion_id:
            product = "Electrolyte Injection"
        incident_id = "INC-MICRO-001" if is_public else (
            "INC-EQUIP-001" if batch_id == family_b else "INC-CAPA-001" if batch_id == family_c else None
        )
        sterility_result_time = end + timedelta(days=14, hours=rng.uniform(.75, 11.5))
        disposition_time = sterility_result_time + timedelta(hours=rng.uniform(3, 22))
        documented_first_ship = {
            "BATCH-075": datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc),
            "BATCH-084": datetime(2025, 2, 4, 0, 0, tzinfo=timezone.utc),
            "BATCH-099": datetime(2025, 4, 15, 0, 0, tzinfo=timezone.utc),
        }
        first_ship_time = documented_first_ship.get(batch_id, disposition_time + timedelta(days=rng.uniform(1, 4.5)))
        production_line = "LINE-A" if is_public or rng.random() < .72 else rng.choice(["LINE-B", "LINE-C"])
        add("batches", {
            "batch_id": batch_id, "product": product, "dosage_form": "sterile solution for injection",
            "production_line": production_line,
            "start_time": iso(start), "end_time": iso(end),
            "status": "released", "disposition": "released",
            "disposition_time": iso(disposition_time), "first_ship_time": iso(first_ship_time),
        })

        # Normal operations are sampled first. Scenario shifts are applied afterward.
        bioburden = clamp(rng.lognormvariate(math.log(0.18), 0.36), 0.02, 0.68)
        em_result = clamp(rng.lognormvariate(math.log(0.12), 0.42), 0.01, 0.64)
        endotoxin = clamp(rng.lognormvariate(math.log(0.16), 0.34), 0.03, 0.55)
        if batch_id in benign_ids:
            bioburden = round(rng.uniform(0.72, 0.94), 4)
        if batch_id == isolated_excursion_id:
            bioburden = 1.08
        if batch_id in benign_environment_ids:
            em_result = round(rng.uniform(.72, .92), 4)
        if is_public:
            incident_rank = BENCHMARK_LOTS.index(batch_id)
            bioburden = [1.23, 1.48, 1.71][incident_rank]
            em_result = [0.71, 0.86, 1.09][incident_rank]

        bio_missing = not is_public and batch_id not in benign_ids and rng.random() < .02
        bio_observed = None if bio_missing else bioburden

        counters["lab"] += 1
        upstream_id = f"LAB-{counters['lab']:04d}"
        sample_collected_at = start + timedelta(hours=4)
        lab_time = sample_collected_at + timedelta(hours=1, minutes=20)
        lab_status = "missing" if bio_missing else "action" if bioburden >= 1 else "alert" if bioburden >= .7 else "normal"
        add("lab_results", {
            "result_id": upstream_id, "batch_id": batch_id, "timestamp": iso(lab_time),
            "sample_collected_at": iso(sample_collected_at),
            "sample_type": "upstream process sample", "test_name": "relative_bioburden_signal",
            "numerical_result": bio_observed, "categorical_result": None, "unit": "action-limit ratio",
            "specification_limit": None, "alert_limit": .7, "action_limit": 1.0,
            "status": lab_status, "organism": None,
            "synthetic_reason": "configured missing-data injection" if lab_status == "missing" else "normal model" if lab_status == "normal" else (
                "isolated negative-control action excursion" if batch_id == isolated_excursion_id else
                "negative-control alert" if batch_id in benign_ids else "incident family A shift"
            ),
        })

        counters["lab"] += 1
        final_endo_id = f"LAB-{counters['lab']:04d}"
        add("lab_results", {
            "result_id": final_endo_id, "batch_id": batch_id, "timestamp": iso(end + timedelta(hours=18)),
            "sample_collected_at": iso(end),
            "sample_type": "finished product", "test_name": "relative_endotoxin_signal",
            "numerical_result": endotoxin, "categorical_result": None, "unit": "specification ratio",
            "specification_limit": 1.0, "alert_limit": None, "action_limit": None,
            "status": "pass", "organism": None,
            "synthetic_reason": "normal release-result model; passing result preserves public incident sequence" if is_public else "normal model",
        })
        counters["lab"] += 1
        add("lab_results", {
            "result_id": f"LAB-{counters['lab']:04d}", "batch_id": batch_id,
            "timestamp": iso(sterility_result_time), "sample_collected_at": iso(end), "sample_type": "finished product",
            "test_name": "sterility", "numerical_result": None, "categorical_result": "no growth",
            "unit": None, "specification_limit": None, "alert_limit": None, "action_limit": None,
            "status": "pass", "organism": None, "synthetic_reason": "normal categorical release result",
        })

        if batch_id == resolved_sample_id:
            counters["lab"] += 1
            failed_sample_id = f"LAB-{counters['lab']:04d}"
            add("lab_results", {
                "result_id": failed_sample_id, "batch_id": batch_id,
                "timestamp": iso(lab_time + timedelta(hours=2)), "sample_collected_at": iso(lab_time + timedelta(hours=1)),
                "sample_type": "upstream process sample repeat", "test_name": "relative_bioburden_signal",
                "numerical_result": 1.06, "categorical_result": None, "unit": "action-limit ratio",
                "specification_limit": None, "alert_limit": .7, "action_limit": 1.0,
                "status": "invalidated", "organism": None,
                "synthetic_reason": "synthetic failed sample followed by documented laboratory invalidation and passing resample",
            })
            counters["lab"] += 1
            add("lab_results", {
                "result_id": f"LAB-{counters['lab']:04d}", "batch_id": batch_id,
                "timestamp": iso(lab_time + timedelta(hours=5)), "sample_collected_at": iso(lab_time + timedelta(hours=4)),
                "sample_type": "upstream process sample resample", "test_name": "relative_bioburden_signal",
                "numerical_result": .22, "categorical_result": None, "unit": "action-limit ratio",
                "specification_limit": None, "alert_limit": .7, "action_limit": 1.0,
                "status": "normal", "organism": None,
                "synthetic_reason": "justified synthetic resample after invalidated sample",
            })

        # Process variation is independent of the microbiological scenario unless explicitly injected.
        temp_delta = clamp(rng.gauss(0, .62), -1.9, 1.9)
        pressure_ratio = clamp(rng.gauss(1.0, .035), .90, 1.10)
        dp_margin = clamp(rng.betavariate(5, 2) * .8 + .2, .2, 1.0)
        hold_margin = round(rng.uniform(.88, .99), 4) if batch_id in high_hold_ids else round(rng.uniform(.25, .82), 4)
        if is_public:
            hold_margin = [.42, .95, .61][BENCHMARK_LOTS.index(batch_id)]
        if batch_id in {family_b, benign_equipment_id}:
            pressure_ratio = 1.24
        for parameter, value, low, high, equipment, event_type, offset_hours in (
            ("process_temperature_delta", temp_delta, -2.0, 2.0, "VESSEL-01", "process_summary", 2),
            ("equipment_pressure_ratio", pressure_ratio, .9, 1.1, "PUMP-02", "equipment_summary", 3),
            ("differential_pressure_margin", dp_margin, .2, 1.0, "AREA-CORE", "environment_summary", 2.5),
            ("hold_duration_margin", hold_margin, 0.0, 1.0, "VESSEL-01", "hold_summary", 4.5),
        ):
            counters["process"] += 1
            severity = "high" if value < low or value > high else "low" if abs(value - (low + high) / 2) > (high - low) * .44 else "normal"
            add("process_events", {
                "event_id": f"PROC-{counters['process']:04d}", "batch_id": batch_id,
                "timestamp": iso(start + timedelta(hours=offset_hours)),
                "equipment_id": equipment, "parameter": parameter, "value": value,
                "expected_low": low, "expected_high": high, "severity": severity,
                "event_type": event_type,
                "synthetic_reason": (
                    "incident family B injected excursion" if batch_id == family_b and parameter == "equipment_pressure_ratio" else
                    "benign unrelated equipment alarm" if batch_id == benign_equipment_id and parameter == "equipment_pressure_ratio" else
                    "near-limit normal hold-duration variation" if parameter == "hold_duration_margin" and hold_margin >= .88 else
                    "normal variation"
                ),
            })

        counters["em"] += 1
        em_status = "action" if em_result >= 1 else "alert" if em_result >= .7 else "normal"
        add("environmental_monitoring", {
            "sample_id": f"EM-{counters['em']:04d}", "batch_id": batch_id,
            "timestamp": iso(start + timedelta(hours=4, minutes=10)), "location": "process support area",
            "sample_type": "relative microbial environmental signal", "result": em_result,
            "alert_limit": .7, "action_limit": 1.0,
            "organism": "gram-negative morphology" if batch_id == "BATCH-099" else None,
            "status": em_status,
        })

        counters["op"] += 1
        add("operator_events", {
            "operator_event_id": f"OP-{counters['op']:04d}", "batch_id": batch_id,
            "timestamp": iso(start + timedelta(hours=1, minutes=15)), "role": "Manufacturing Operator",
            "event_type": "batch_check", "description": "Routine in-process verification completed.",
            "severity": "normal",
        })

        deviation_needed = is_public or batch_id in low_deviation_ids or batch_id in {family_b, family_c}
        if deviation_needed:
            counters["dev"] += 1
            category = "microbiology" if is_public else "equipment" if batch_id == family_b else "procedure"
            # Public recurrence is something the agent must infer across records, not a label
            # embedded in each local deviation. Family C explicitly tests a QMS recurrence flag.
            recurrence = int(batch_id == family_c)
            add("deviations", {
                "deviation_id": f"DEV-{counters['dev']:04d}", "batch_id": batch_id,
                "opened_at": iso(lab_time + timedelta(minutes=18)),
                "closed_at": None if is_incident else iso(lab_time + timedelta(days=2)),
                "category": category, "severity": "high" if is_public or batch_id == family_c else "low",
                "description": (
                    "Deviation opened for an action-level upstream microbiological signal."
                    if is_public else "Deviation opened for proportional investigation and local assessment."
                ),
                "investigation_status": "open" if is_incident else "closed",
                "root_cause": None if is_public else "not confirmed" if is_incident else "isolated execution variance",
                "capa": None if is_public else "local coaching" if batch_id in low_deviation_ids else "inspection frequency increased",
                "recurrence_flag": recurrence, "public_or_synthetic": "synthetic",
            })

        if order % 11 == 0 or batch_id in {family_b, family_c, "BATCH-084"}:
            counters["maint"] += 1
            add("maintenance", {
                "work_order": f"WO-{counters['maint']:04d}",
                "timestamp": iso(start - timedelta(hours=10)),
                "equipment_id": "PUMP-02" if batch_id == family_b else "VESSEL-01",
                "work_type": "inspection", "description": "Planned equipment inspection.",
                "action": "Inspection completed; observations recorded.", "status": "closed",
                "linked_batch_id": batch_id,
            })

        true_severity = "HIGH" if is_public else "MEDIUM" if batch_id == family_b else "HIGH" if batch_id == family_c else "LOW"
        ideal = (
            "L3" if is_public or batch_id == family_c else
            "L2" if batch_id in {family_b, isolated_excursion_id, benign_equipment_id} else
            "L1" if batch_id in benign_ids else "NONE"
        )
        earliest = (iso(start + timedelta(hours=4, minutes=10)) if batch_id == "BATCH-099" else iso(lab_time)) if is_public else (
            iso(start + timedelta(hours=3)) if batch_id == family_b else
            iso(lab_time + timedelta(minutes=18)) if batch_id == family_c else None
        )
        relevant_batches = list(BENCHMARK_LOTS[: BENCHMARK_LOTS.index(batch_id) + 1]) if is_public else [batch_id]
        add("simulation_labels", {
            "batch_id": batch_id, "true_incident": int(is_incident), "true_severity": true_severity,
            "incident_type": "repeated_microbiological_excursion" if is_public else (
                "equipment_process_anomaly_benign_quality" if batch_id == family_b else
                "recurring_deviation_ineffective_action" if batch_id == family_c else
                "benign_abnormality" if batch_id in benign_ids else "none"
            ),
            "earliest_detectable_timestamp": earliest, "ideal_escalation_level": ideal,
            "rationale": (
                "Reconstructed family A; public sequence, synthetic operational details."
                if is_public else "Synthetic benchmark control or incident scenario."
            ),
            "evidence_required": [upstream_id] if is_public else [],
            "relevant_batch_ids": relevant_batches,
            "relevant_equipment_ids": ["PUMP-02"] if batch_id == family_b else (["VESSEL-01"] if batch_id == family_c else []),
            "plausible_hypotheses": ["upstream microbiological control", "sampling or laboratory anomaly"] if is_public else (
                ["equipment pressure control"] if batch_id == family_b else ["prior corrective action ineffective"] if batch_id == family_c else []
            ),
            "expected_actions": ["organism identification", "compare related batches", "QA scope assessment"] if is_public else (
                ["equipment inspection", "process trajectory review"] if batch_id == family_b else
                ["review prior CAPA", "effectiveness check"] if batch_id == family_c else []
            ),
            "expected_teams": ["QA", "Microbiology", "MSAT"] if is_public else (["Maintenance", "MSAT"] if batch_id == family_b else ["QA", "Manufacturing"] if batch_id == family_c else []),
            "negative_control": int(batch_id in negative_controls),
            "counterfactual_pair_id": "PAIR-MICRO-01" if batch_id in {isolated_excursion_id, "BATCH-084"} else None,
            "counterfactual_role": "isolated_negative_control" if batch_id == isolated_excursion_id else "recurring_target" if batch_id == "BATCH-084" else None,
        })

    # Later records preserve the documented sequence but do not assert the affected public lot.
    counters["lab"] += 1
    reserve_time = datetime(2025, 10, 27, 14, 10, tzinfo=timezone.utc)
    add("lab_results", {
        "result_id": f"LAB-{counters['lab']:04d}", "batch_id": "BATCH-075", "timestamp": iso(reserve_time),
        "sample_collected_at": iso(reserve_time - timedelta(hours=3)),
        "sample_type": "finished-product reserve", "test_name": "relative_endotoxin_signal",
        "numerical_result": 1.37, "categorical_result": None, "unit": "specification ratio",
        "specification_limit": 1.0, "alert_limit": None, "action_limit": None, "status": "out_of_specification",
        "organism": None,
        "synthetic_reason": "Reconstructed timing and lot assignment; public record confirms a reserve-sample OOS in one lot but does not identify it.",
    })
    add("complaints", {
        "complaint_id": "CMP-0001", "product": "Famotidine Injection, USP", "lot": "BATCH-075",
        "timestamp": "2025-10-20T09:00:00Z",
        "description": "Complaint describing a reported pyrogenic-type symptom pattern; lot assignment and wording are reconstructed.",
        "severity": "high", "outcome": "under investigation", "public_or_synthetic": "synthetic",
    })
    add("incident_memory", {
        "incident_id": "MEM-SYN-001", "pattern_signature": "upstream microbial signal + repeated deviation",
        "symptoms": ["relative bioburden action crossing", "repeat occurrence"],
        "evidence_ids": ["historical synthetic record"], "confirmed_root_cause": "extended wet hold",
        "actions": ["sanitization timing review", "pre-use verification"],
        "outcome": "No recurrence during synthetic three-month review window.",
        "created_at": "2024-01-15T00:00:00Z",
    })
    for index, lot in enumerate(BENCHMARK_LOTS, 1):
        add("benchmark_outcomes", {
            "outcome_id": f"OUT-{index:03d}", "batch_id": lot, "outcome": "recalled",
            "effective_at": "2025-11-06T00:00:00Z", "available_at": "2025-11-07T00:00:00Z",
            "public_fact_id": "FDA-F005", "benchmark_only": 1,
        })

    connection.commit()
    fingerprint = _fingerprint(connection)
    connection.execute("INSERT INTO metadata(key,value) VALUES (?,?)", ("dataset_fingerprint", fingerprint))
    connection.commit()
    _export(connection, output_dir, csv_dir)
    if output_dir.resolve() == DEFAULT_OUTPUT.resolve():
        _write_layered_outputs(connection, DEMO_DATA_DIR)
    connection.close()
    manifest = {
        "seed": seed, "database": str(database), "dataset_fingerprint": fingerprint,
        "counts": {table: len(rows_by_table[table]) for table in TABLES},
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _fingerprint(connection: sqlite3.Connection) -> str:
    canonical: dict[str, Any] = {}
    connection.row_factory = sqlite3.Row
    for table in TABLES:
        primary = connection.execute(f"PRAGMA table_info({table})").fetchall()[0][1]
        canonical[table] = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY {primary}")]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _export(connection: sqlite3.Connection, output_dir: Path, csv_dir: Path) -> None:
    connection.row_factory = sqlite3.Row
    combined: dict[str, Any] = {}
    for table in TABLES:
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
        combined[table] = rows
        target = csv_dir / f"{table}.csv"
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)
    (output_dir / "pharma_simulation.json").write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")


def _write_demo_projection(connection: sqlite3.Connection, target: Path) -> None:
    """Project the frozen 100-batch store into the UI's legacy JSON-shaped adapter."""
    presentation = json.loads(target.read_text(encoding="utf-8"))
    public_ground_truth = json.loads((DATA_DIR / "public_ground_truth.json").read_text(encoding="utf-8"))["facts"]
    fact_by_number = {fact["fact_id"].split("F")[-1].lstrip("0"): fact for fact in public_ground_truth}
    for fact in presentation.get("public_facts", []):
        number = str(fact.get("id", "")).split("-")[-1].lstrip("0")
        source_fact = fact_by_number.get(number)
        if source_fact:
            fact["available_at"] = source_fact["available_at"]
            fact["source_url"] = source_fact["source_url"]
    connection.row_factory = sqlite3.Row
    batches = [dict(row) for row in connection.execute("SELECT * FROM batches ORDER BY start_time")]
    labs_raw = [dict(row) for row in connection.execute("SELECT * FROM lab_results ORDER BY timestamp")]
    process_raw = [dict(row) for row in connection.execute("SELECT * FROM process_events ORDER BY timestamp")]
    deviations_raw = [dict(row) for row in connection.execute("SELECT * FROM deviations ORDER BY opened_at")]
    maintenance_raw = [dict(row) for row in connection.execute("SELECT * FROM maintenance ORDER BY timestamp")]
    complaints_raw = [dict(row) for row in connection.execute("SELECT * FROM complaints ORDER BY timestamp")]

    presentation["batches"] = [
        {
            "batch_id": row["batch_id"], "product": row["product"],
            "production_line": row["production_line"], "start_time": row["start_time"],
            "end_time": row["end_time"], "status": row["status"], "disposition": row["disposition"],
            "disposition_time": row["disposition_time"], "first_ship_time": row["first_ship_time"],
            "provenance": "synthetic_factory_signal",
        }
        for row in batches
    ]
    presentation["lab_results"] = [
        {
            "id": row["result_id"], "batch_id": row["batch_id"], "timestamp": row["timestamp"],
            "sample_collected_at": row["sample_collected_at"], "sample_type": row["sample_type"],
            "test": "bioburden" if row["test_name"] == "relative_bioburden_signal" else row["test_name"],
            "result": row["categorical_result"] if row["categorical_result"] is not None else (
                "missing" if row["numerical_result"] is None else f"{row['numerical_result']:.2f} {row['unit']}"
            ),
            "limit": "1.00 normalized action limit" if row["action_limit"] is not None else
                     "1.00 normalized specification" if row["specification_limit"] is not None else "categorical",
            "status": "action_limit" if row["status"] == "action" else "pass" if row["status"] == "normal" else row["status"],
            "organism": row["organism"], "synthetic_reason": row["synthetic_reason"],
            "provenance": "synthetic_factory_signal",
        }
        for row in labs_raw
    ]
    presentation["process_events"] = [
        {
            "id": row["event_id"], "batch_id": row["batch_id"], "timestamp": row["timestamp"],
            "equipment_id": row["equipment_id"], "parameter": row["parameter"],
            "value": str(row["value"]), "expected_range": f"{row['expected_low']}–{row['expected_high']}",
            "severity": row["severity"], "synthetic_reason": row["synthetic_reason"],
            "provenance": "synthetic_factory_signal",
        }
        for row in process_raw
    ]
    presentation["deviations"] = [
        {
            "deviation_id": row["deviation_id"], "batch_id": row["batch_id"],
            "timestamp": row["opened_at"], "category": row["category"],
            "description": row["description"], "investigation_status": row["investigation_status"],
            "root_cause": row["root_cause"], "capa": row["capa"],
            "recurrence_flag": bool(row["recurrence_flag"]), "provenance": "synthetic_factory_signal",
        }
        for row in deviations_raw
    ]
    presentation["maintenance"] = [
        {
            "work_order": row["work_order"], "timestamp": row["timestamp"],
            "equipment_id": row["equipment_id"], "description": row["description"],
            "action": row["action"], "status": row["status"],
            "batch_id": row["linked_batch_id"], "provenance": "synthetic_factory_signal",
        }
        for row in maintenance_raw
    ]
    presentation["complaints"] = [
        {
            "complaint_id": row["complaint_id"], "product": row["product"], "lot": row["lot"],
            "timestamp": row["timestamp"], "description": row["description"],
            "severity": row["severity"], "provenance": "synthetic_factory_signal",
        }
        for row in complaints_raw
    ]
    # Memory is intentionally absent from the primary replay and tested separately.
    presentation["incident_memory"] = []

    def batch(batch_id: str) -> dict[str, Any]:
        return next(row for row in batches if row["batch_id"] == batch_id)

    def lab(batch_id: str, test_name: str, sample_type: str | None = None) -> dict[str, Any]:
        return next(
            row for row in labs_raw
            if row["batch_id"] == batch_id and row["test_name"] == test_name
            and (sample_type is None or row["sample_type"] == sample_type)
        )

    def deviation(batch_id: str) -> dict[str, Any]:
        return next(row for row in deviations_raw if row["batch_id"] == batch_id)

    lot1, lot2, lot3 = (batch(lot) for lot in PUBLIC_LOTS)
    bio1, bio2, bio3 = (lab(lot, "relative_bioburden_signal") for lot in PUBLIC_LOTS)
    endo1 = lab("6133156", "relative_endotoxin_signal", "finished product")
    sterility1 = lab("6133156", "sterility")
    reserve = lab("6133156", "relative_endotoxin_signal", "finished-product reserve")
    dev1, dev2 = deviation("6133156"), deviation("6133194")
    organism_time = iso(parse_datetime(bio3["timestamp"]) + timedelta(days=2))
    presentation["lab_results"].append({
        "id": "LR-HUMAN-001", "batch_id": "6133388", "timestamp": organism_time,
        "sample_collected_at": bio3["sample_collected_at"], "sample_type": "microbiology isolate",
        "test": "organism identification", "result": "gram-negative morphology confirmed",
        "limit": "not applicable", "status": "identified", "organism": "gram-negative morphology",
        "synthetic_reason": "human-entered reconstructed finding", "provenance": "synthetic_factory_signal",
        "requires_task": "TASK-MICRO-01",
    })
    complaint = complaints_raw[0]
    events = [
        (lot1["start_time"], "MES", "Batch 6133156 started", "A reconstructed batch entered production.", ["6133156"], "normal"),
        (bio1["timestamp"], "LIMS", "Bioburden action limit exceeded", "Normalized upstream signal crossed 1.00 × the synthetic action limit.", [bio1["result_id"]], "high"),
        (dev1["opened_at"], "QMS", "Local deviation opened", "A batch-local microbiology investigation was initiated.", [dev1["deviation_id"]], "medium"),
        (sterility1["timestamp"], "LIMS", "Finished-product tests available", "Reconstructed sterility and normalized endotoxin results were within specification.", [endo1["result_id"], sterility1["result_id"]], "normal"),
        (lot2["start_time"], "MES", "Batch 6133194 started", "A second reconstructed lot entered production.", ["6133194"], "normal"),
        (bio2["timestamp"], "LIMS", "Second bioburden excursion", "A second normalized upstream action-limit crossing became available.", [bio2["result_id"]], "high"),
        (dev2["opened_at"], "QMS", "Second deviation opened", "A second batch-local deviation was recorded.", [dev2["deviation_id"]], "medium"),
        (lot3["start_time"], "MES", "Batch 6133388 started", "A third reconstructed lot entered production.", ["6133388"], "normal"),
        (bio3["timestamp"], "LIMS", "Third bioburden excursion", "A third normalized upstream action-limit crossing became available.", [bio3["result_id"]], "high"),
        (organism_time, "LIMS", "Organism identification ready", "Microbiology has a finding available for human verification.", ["LR-HUMAN-001"], "high"),
        (complaint["timestamp"], "Complaints", "Field signal received", "A synthetic complaint prompted broader assessment.", [complaint["complaint_id"]], "high"),
        (reserve["timestamp"], "LIMS", "Reserve-sample endotoxin OOS", "A reconstructed reserve result exceeded the normalized specification.", [reserve["result_id"]], "critical"),
        ("2025-11-07T00:00:00Z", "Public outcome", "Three lots recalled", "FDA posted the company announcement identifying the three lots.", ["FDA-F005"], "critical"),
    ]
    presentation["replay_events"] = [
        {
            "id": f"EVT-{index:03d}", "timestamp": timestamp, "offset_seconds": (index - 1) * 5,
            "system": system, "title": title, "detail": detail, "record_ids": record_ids,
            "provenance": "public_fda_fact" if system == "Public outcome" else "synthetic_factory_signal",
            "severity": severity, **({"outcome_only": True} if system == "Public outcome" else {}),
        }
        for index, (timestamp, system, title, detail, record_ids, severity) in enumerate(events, 1)
    ]
    target.write_text(json.dumps(presentation, indent=2) + "\n", encoding="utf-8")


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_layered_outputs(connection: sqlite3.Connection, target_dir: Path) -> None:
    """Write physically separated agent, benchmark, public, and UI layers.

    The legacy demo filename remains an exact copy of the agent-safe layer so
    existing tooling keeps working without receiving benchmark annotations.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    connection.row_factory = sqlite3.Row

    def rows(table: str, order: str) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}")]

    batches = rows("batches", "start_time")
    labs = rows("lab_results", "timestamp")
    process = rows("process_events", "timestamp")
    environmental = rows("environmental_monitoring", "timestamp")
    deviations = rows("deviations", "opened_at")
    maintenance = rows("maintenance", "timestamp")
    complaints = rows("complaints", "timestamp")
    operators = rows("operator_events", "timestamp")
    labels = rows("simulation_labels", "batch_id")
    outcomes = rows("benchmark_outcomes", "outcome_id")
    metadata = {row["key"]: row["value"] for row in connection.execute("SELECT * FROM metadata")}

    agent_data: dict[str, Any] = {
        "metadata": {
            "dataset_version": DATASET_VERSION,
            "generation_seed": int(metadata["simulation_seed"]),
            "creation_timestamp": DATASET_CREATED_AT,
            "provenance_notice": metadata["provenance_notice"],
        },
        "batches": [{**row, "provenance": "synthetic_factory_signal"} for row in batches],
        "lab_results": [
            {**{key: value for key, value in row.items() if key != "synthetic_reason"},
             "provenance": "synthetic_factory_signal"}
            for row in labs
        ],
        "process_events": [
            {**{key: value for key, value in row.items() if key != "synthetic_reason"},
             "provenance": "synthetic_factory_signal"}
            for row in process
        ],
        "environmental_monitoring": [
            {**row, "provenance": "synthetic_factory_signal"} for row in environmental
        ],
        "deviations": [{**row, "provenance": "synthetic_factory_signal"} for row in deviations],
        "maintenance": [{**row, "provenance": "synthetic_factory_signal"} for row in maintenance],
        "complaints": [{**row, "provenance": "synthetic_factory_signal"} for row in complaints],
        "operator_events": [{**row, "provenance": "synthetic_factory_signal"} for row in operators],
        # Disabled in the primary benchmark. The memory ablation reads the DB's
        # time-bounded incident_memory table explicitly.
        "incident_memory": [],
    }
    canonical = json.dumps(agent_data, sort_keys=True, separators=(",", ":"))
    agent_checksum = hashlib.sha256(canonical.encode()).hexdigest()
    agent_data["metadata"]["content_sha256"] = agent_checksum

    generation_reasons = [
        {"record_id": row["result_id"], "generation_reason": row["synthetic_reason"]}
        for row in labs
    ] + [
        {"record_id": row["event_id"], "generation_reason": row["synthetic_reason"]}
        for row in process
    ]
    label_by_id = {row["batch_id"]: row for row in labels}
    benchmark_ground_truth = {
        "metadata": {
            "dataset_version": DATASET_VERSION,
            "generation_seed": int(metadata["simulation_seed"]),
            "creation_timestamp": DATASET_CREATED_AT,
            "agent_data_content_sha256": agent_checksum,
            "access": "benchmark_only_never_agent_input",
        },
        "public_lot_mapping": {
            benchmark: {"public_lot": public}
            for public, benchmark in PUBLIC_TO_BENCHMARK.items()
        },
        "batch_labels": [
            {
                "record_id": f"LABEL-{row['batch_id']}",
                "original_batch_id": next(
                    (public for public, benchmark in PUBLIC_TO_BENCHMARK.items() if benchmark == row["batch_id"]),
                    row["batch_id"],
                ),
                "benchmark_batch_id": row["batch_id"],
                "true_incident": bool(row["true_incident"]),
                "incident_family": row["incident_type"],
                "negative_control": bool(row["negative_control"]),
                "expected_severity": row["true_severity"],
                "expected_triage": row["ideal_escalation_level"],
                "earliest_detectable_timestamp": row["earliest_detectable_timestamp"],
                "final_outcome": next(
                    (outcome["outcome"] for outcome in outcomes if outcome["batch_id"] == row["batch_id"]),
                    None,
                ),
                "generation_reason": row["rationale"],
            }
            for row in labels
        ],
        "generation_reasons": generation_reasons,
        "simulation_labels": labels,
        "final_outcomes": outcomes,
    }

    public_ground_truth = json.loads((DATA_DIR / "public_ground_truth.json").read_text(encoding="utf-8"))
    selected_fact_ids = ("FDA-F001", "FDA-F002", "FDA-F003", "FDA-F004", "FDA-F005", "FDA-F009")
    facts_by_id = {row["fact_id"]: row for row in public_ground_truth["facts"]}
    ui_facts = [
        {**facts_by_id[fact_id], "id": f"PF-{index:03d}"}
        for index, fact_id in enumerate(selected_fact_ids, 1)
    ]
    tasks = [
        {"task_id": "TASK-QA-01", "owner": "QA", "title": "Assess disposition and potentially affected lots", "status": "open", "evidence_required": "Batch records, deviations, release tests, and cross-lot scope", "priority": "high"},
        {"task_id": "TASK-MICRO-01", "owner": "Microbiology", "title": "Confirm organism identification", "status": "open", "evidence_required": "Isolate identification and morphology report", "priority": "high", "default_observation": "Gram-negative organism with confluent growth confirmed."},
        {"task_id": "TASK-MSAT-01", "owner": "MSAT", "title": "Compare affected process trajectories", "status": "open", "evidence_required": "Hold times, process stage, and successful-run comparison", "priority": "high"},
        {"task_id": "TASK-MFG-01", "owner": "Manufacturing", "title": "Review interventions and execution records", "status": "open", "evidence_required": "Operator interventions, line clearance, and batch narrative", "priority": "medium"},
        {"task_id": "TASK-MAINT-01", "owner": "Maintenance", "title": "Review relevant equipment history", "status": "open", "evidence_required": "Work orders and equipment condition for VESSEL-01 and PUMP-02", "priority": "medium"},
    ]
    by_batch = {row["batch_id"]: row for row in batches}
    lab_by_key = {(row["batch_id"], row["test_name"], row["sample_type"]): row for row in labs}
    dev_by_batch = {row["batch_id"]: row for row in deviations}
    lot1, lot2, lot3 = (by_batch[lot] for lot in BENCHMARK_LOTS)
    bio1, bio2, bio3 = (
        lab_by_key[(lot, "relative_bioburden_signal", "upstream process sample")] for lot in BENCHMARK_LOTS
    )
    endo1 = lab_by_key[("BATCH-075", "relative_endotoxin_signal", "finished product")]
    sterile1 = lab_by_key[("BATCH-075", "sterility", "finished product")]
    reserve = lab_by_key[("BATCH-075", "relative_endotoxin_signal", "finished-product reserve")]
    organism_time = iso(parse_datetime(bio3["timestamp"]) + timedelta(days=2))
    complaint = complaints[0]
    events = [
        (lot1["start_time"], "MES", "Batch started", "A reconstructed batch entered production.", ["BATCH-075"], "normal"),
        (bio1["timestamp"], "LIMS", "Bioburden action limit exceeded", "A normalized upstream signal crossed its action limit.", [bio1["result_id"]], "high"),
        (dev_by_batch["BATCH-075"]["opened_at"], "QMS", "Deviation opened", "A batch-local microbiology investigation was initiated.", [dev_by_batch["BATCH-075"]["deviation_id"]], "medium"),
        (sterile1["timestamp"], "LIMS", "Finished-product tests available", "Sterility and normalized endotoxin release results were within specification.", [endo1["result_id"], sterile1["result_id"]], "normal"),
        (lot2["start_time"], "MES", "Batch started", "Another reconstructed batch entered production.", ["BATCH-084"], "normal"),
        (bio2["timestamp"], "LIMS", "Bioburden action limit exceeded", "A normalized upstream signal crossed its action limit.", [bio2["result_id"]], "high"),
        (dev_by_batch["BATCH-084"]["opened_at"], "QMS", "Deviation opened", "A batch-local microbiology investigation was initiated.", [dev_by_batch["BATCH-084"]["deviation_id"]], "medium"),
        (lot3["start_time"], "MES", "Batch started", "Another reconstructed batch entered production.", ["BATCH-099"], "normal"),
        (bio3["timestamp"], "LIMS", "Bioburden action limit exceeded", "A normalized upstream signal crossed its action limit.", [bio3["result_id"]], "high"),
        (organism_time, "LIMS", "Organism identification available", "A microbiology finding is available for human verification.", ["LR-HUMAN-001"], "high"),
        (complaint["timestamp"], "Complaints", "Field signal received", "A complaint was entered for assessment.", [complaint["complaint_id"]], "high"),
        (reserve["timestamp"], "LIMS", "Reserve-sample result available", "A reserve result exceeded the normalized specification.", [reserve["result_id"]], "critical"),
        ("2025-11-07T00:00:00Z", "Public outcome", "Public recall announced", "The public outcome is revealed only after replay reasoning is complete.", [], "critical"),
    ]
    replay_ui = {
        "metadata": {
            "demo_id": "famotidine-bioburden-2026",
            "title": "Famotidine Injection — evolving microbiological signal",
            "company": "Fresenius Kabi USA, LLC",
            "dataset_version": DATASET_VERSION,
            "permanent_disclosure": "Reconstructed simulation based on publicly documented FDA findings. Operational telemetry shown in this demo is synthetic.",
            "retrospective_disclaimer": "This prototype is a retrospective reconstruction for demonstrating manufacturing decision-support concepts. It does not establish that a different system would have prevented the real-world event.",
        },
        "public_facts": ui_facts,
        "tasks": tasks,
        "replay_events": [
            {"id": f"EVT-{index:03d}", "timestamp": timestamp, "offset_seconds": (index - 1) * 5,
             "system": system, "title": title, "detail": detail, "record_ids": record_ids,
             "provenance": "public_fda_fact" if system == "Public outcome" else "synthetic_factory_signal",
             "severity": severity, **({"outcome_only": True} if system == "Public outcome" else {})}
            for index, (timestamp, system, title, detail, record_ids, severity) in enumerate(events, 1)
        ],
    }

    for filename, payload in (
        ("agent_data.json", agent_data),
        ("fresenius_famotidine_demo.json", agent_data),
        ("benchmark_ground_truth.json", benchmark_ground_truth),
        ("public_ground_truth.json", public_ground_truth),
        ("replay_ui.json", replay_ui),
    ):
        (target_dir / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
