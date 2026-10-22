from __future__ import annotations

import csv
import json
from pathlib import Path

from benchmarks.common.leakage_audit import audit_package
from benchmarks.fresenius.build_multimodal_package import build_package
from benchmarks.fresenius.build_tasks import build_tasks
from benchmarks.fresenius.temporal_replay import state_at
from benchmarks.cho.aggregation_baseline import _load_stream, _interpolate
from benchmarks.common.agent_adapter import run_investigation
from benchmarks.common.provenance_validator import validate_mapping
from benchmarks.cho.build_comparison_reference import build as build_comparison_reference


def test_replay_redacts_future_fields(tmp_path: Path) -> None:
    tasks = {task["id"]: task for task in build_tasks()}
    first = tasks["FRE-02"]["as_of"]
    current = state_at(first)
    assert current
    assert all(row["available_at"] <= first for row in current)
    assert not any(row.get("status") == "out_of_specification" for row in current if row["_table"] == "lab_results")
    package = tmp_path / "agent_input"
    build_package(package, as_of=first, map_output=tmp_path / "hidden" / "map.json")
    assert audit_package(package, as_of=first)[0]
    assert not (package / "hidden" / "map.json").exists()
    with (package / "laboratory" / "lims_export.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert all(row["available_at"] <= first for row in rows)


def test_hidden_file_rejected(tmp_path: Path) -> None:
    (tmp_path / "benchmark_ground_truth.json").write_text("{}")
    assert not audit_package(tmp_path)[0]


def test_public_future_finding_rejected(tmp_path: Path) -> None:
    (tmp_path / "shift_note.txt").write_text("FDA warning letter says this was recalled")
    assert not audit_package(tmp_path, as_of="2024-01-01T00:00:00Z")[0]


def test_local_time_export_future_row_rejected(tmp_path: Path) -> None:
    path = tmp_path / "lims_review_local.csv"
    path.write_text("Record,Released local (UTC-07)\nLAB-TEST,2024-01-02T00:00:00-07:00\n")
    assert not audit_package(tmp_path, as_of="2024-01-02T06:59:59Z")[0]


def test_raw_stream_time_reordering_preserves_values() -> None:
    class Sheet:
        title = "R01_inline_Sensor"
        def iter_rows(self, values_only: bool = True):
            return iter([("Time (h)", "value"), (0.0, 2.0), (2.0, 8.0), (1.0, 4.0)])
    stream = _load_stream(Sheet())
    assert stream["backward_steps_reordered"] == 1
    assert stream["times"] == [0.0, 1.0, 2.0]
    assert _interpolate(stream, 1, 1.0) == 4.0


def test_spreadsheet_summary_keeps_source_rows(tmp_path: Path) -> None:
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "R01_inline_Sensor"
    sheet.append(["Time (h)", "Reading (units)"])
    sheet.append([0, 4])
    sheet.append([1, 2])
    sheet.append([2, 8])
    workbook.save(tmp_path / "EXP001_batch.xlsx")
    output = run_investigation(tmp_path, "summarize", configuration={"capture_records": False,
                                                                   "summarize_numeric": True})
    summary = output["files"][0]["numeric_summary"]["Reading (units)"]
    assert (summary["min"], summary["min_row"], summary["max"], summary["max_row"]) == (2, 3, 8, 4)
    assert summary["mean"] == 14/3
    assert output["records"] == []


def test_descriptive_cho_reference_has_no_causal_claim() -> None:
    reference = build_comparison_reference()
    assert len(reference["experiments"]) == 12
    assert "No independence assumption" in reference["interpretation_limit"]
    assert all(item["reactors"] == ["R01", "R02"] for item in reference["experiments"].values())


def test_scanned_and_chart_pointers_are_valid(tmp_path: Path) -> None:
    from benchmarks.fresenius.source_formats import add_discrete_process_charts, add_scanned_lab_report
    mapping = []
    lab = [{"_evidence_id": "LAB-TEST", "batch_id": "SYN-TEST",
            "available_at": "2024-01-01T00:00:00Z", "numerical_result": 0.5, "unit": "ratio"}]
    process = [{"_evidence_id": "PROC-TEST", "batch_id": "SYN-TEST",
                "timestamp": "2024-01-01T00:00:00Z", "parameter": "measured_delta", "value": 0.5}]
    add_scanned_lab_report(tmp_path, lab, mapping)
    add_discrete_process_charts(tmp_path, process, mapping)
    hidden = tmp_path / "map.json"
    hidden.write_text(json.dumps({"mappings": mapping}))
    assert validate_mapping(tmp_path, hidden)["pass"]
