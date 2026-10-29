from __future__ import annotations

import csv
import json
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


from benchmarks.common.artifact_store import uses_assets

ROOT = Path(__file__).resolve().parent


def _head_types(rows: list[tuple]) -> dict[str, int]:
    return dict(Counter(type(cell).__name__ for row in rows for cell in row if cell is not None))


def _time_info(values: list[Any]) -> dict:
    numeric = []
    for value in values:
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            pass
    times = [value.isoformat() for value in values if isinstance(value, datetime)]
    deltas = [b-a for a,b in zip(numeric, numeric[1:]) if b > a]
    return {"numeric_count_sample": len(numeric), "datetime_count_sample": len(times),
            "numeric_first": numeric[:3], "datetime_first": times[:3],
            "median_positive_interval_sample": statistics.median(deltas) if deltas else None,
            "duplicate_time_count_sample": len(numeric)-len(set(numeric))}


def _entities(name: str) -> dict:
    exp = re.search(r"EXP[\s_\-]*(\d+)", name, re.I)
    reactor = re.search(r"(?:^|[_\s\-])R[\s_\-]*(\d+)(?:\D|$)", name, re.I)
    mode = "fed-batch" if re.search(r"fed[\s_\-]*batch", name, re.I) else "batch" if re.search(r"batch", name, re.I) else None
    return {"experiment": exp.group(1) if exp else None, "reactor": reactor.group(1) if reactor else None, "mode": mode}


@uses_assets(ROOT / "raw", ROOT / "reference/aligned")
def inspect() -> dict:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("Install openpyxl to inspect the original workbooks") from exc
    workbooks = []
    for path in sorted((ROOT / "raw/workbooks").glob("*.xlsx")):
        wb = load_workbook(path, read_only=True, data_only=True)
        sheets = []
        for sheet in wb:
            iterator = sheet.iter_rows(values_only=True)
            sample = [tuple(row) for _, row in zip(range(8), iterator)]
            first_column = [row[0] for row in sample if row]
            missing = sum(cell is None for row in sample[1:] for cell in row)
            observed = len(sample)
            seen_rows = set()
            duplicate_rows = 0
            for row in sample[1:]:
                if row in seen_rows: duplicate_rows += 1
                seen_rows.add(row)
            times = [float(value) for value in first_column[1:] if isinstance(value, (int, float))]
            duplicates = len(times) - len(set(times))
            backward = sum(b < a for a, b in zip(times, times[1:]))
            previous = times[-1] if times else None
            intervals = [b-a for a,b in zip(times, times[1:]) if b > a]
            for row in iterator:
                observed += 1
                missing += sum(cell is None for cell in row)
                if row in seen_rows: duplicate_rows += 1
                seen_rows.add(row)
                if row and isinstance(row[0], (int, float)):
                    current = float(row[0])
                    if previous is not None:
                        if current == previous:
                            duplicates += 1
                        elif current < previous:
                            backward += 1
                        elif current > previous and len(intervals) < 10000:
                            intervals.append(current-previous)
                    previous = current
            sheets.append({"name": sheet.title, "rows_reported": sheet.max_row, "columns_reported": sheet.max_column,
                           "rows_observed": observed, "missing_cells": missing,
                           "adjacent_duplicate_timestamps": duplicates,
                           "backward_timestamp_steps": backward,
                           "duplicate_data_rows": duplicate_rows,
                           "median_positive_interval_hours_sample": statistics.median(intervals) if intervals else None,
                           "columns": [str(value) if value is not None else None for value in sample[0]] if sample else [],
                           "units_from_headers": {str(value): re.findall(r"\(([^()]*)\)", str(value))[-1]
                                                  for value in (sample[0] if sample else []) if value is not None and re.findall(r"\(([^()]*)\)", str(value))},
                           "first_rows": [[str(cell) if cell is not None else None for cell in row[:20]] for row in sample],
                           "sample_types": _head_types(sample), "first_column_time": _time_info(first_column),
                           **_entities(sheet.title)})
        workbooks.append({"file": path.name, **_entities(path.name), "sheets": sheets})
        wb.close()
    csvs = []
    for path in sorted((ROOT / "reference/aligned").glob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.reader(stream)
            header = next(reader, [])
            sample = [row for _,row in zip(range(500), reader)]
            missing = sum(cell.strip() == "" for row in sample for cell in row)
            observed = len(sample)
            seen_rows = set()
            duplicate_rows = 0
            for row in sample:
                value = tuple(row)
                if value in seen_rows: duplicate_rows += 1
                seen_rows.add(value)
            previous = None
            duplicate_times = 0
            backward = 0
            intervals = []
            for row in sample:
                try:
                    current = float(row[0])
                    if previous is not None:
                        if current == previous: duplicate_times += 1
                        elif current < previous: backward += 1
                        elif current > previous and len(intervals) < 10000: intervals.append(current-previous)
                    previous = current
                except (ValueError, IndexError): pass
            for row in reader:
                observed += 1
                missing += sum(cell.strip() == "" for cell in row)
                value = tuple(row)
                if value in seen_rows: duplicate_rows += 1
                seen_rows.add(value)
                try:
                    current = float(row[0])
                    if previous is not None:
                        if current == previous: duplicate_times += 1
                        elif current < previous: backward += 1
                        elif current > previous and len(intervals) < 10000: intervals.append(current-previous)
                    previous = current
                except (ValueError, IndexError): pass
        csvs.append({"file": path.name, **_entities(path.name), "columns": header,
                     "units_from_headers": {value: re.findall(r"\(([^()]*)\)", value)[-1]
                                            for value in header if re.findall(r"\(([^()]*)\)", value)},
                     "rows_observed": observed, "missing_cells": missing,
                     "adjacent_duplicate_timestamps": duplicate_times,
                     "backward_timestamp_steps": backward,
                     "duplicate_data_rows": duplicate_rows,
                     "median_positive_interval_hours_sample": statistics.median(intervals) if intervals else None,
                     "first_rows": sample[:3], "first_column_time": _time_info([row[0] for row in sample if row])})
    inventory = {"workbooks": workbooks, "aligned_csvs": csvs,
                 "workbook_count": len(workbooks), "worksheet_count": sum(len(w["sheets"]) for w in workbooks),
                 "csv_count": len(csvs)}
    (ROOT / "data_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    lines = ["# CHO dataset profile", "", "Generated by inspecting extracted source files.", "",
             f"- Workbooks: {len(workbooks)}", f"- Worksheets: {inventory['worksheet_count']}",
             f"- Aligned CSV references: {len(csvs)}", "",
             f"- Process modes by filename: {dict(Counter(book['mode'] for book in workbooks))}",
             "- Reactors: R01 and R02 are named in each workbook's sheet labels.",
             f"- Raw measurement rows: {sum(sheet['rows_observed']-1 for book in workbooks for sheet in book['sheets']):,}",
             f"- Raw empty cells: {sum(sheet['missing_cells'] for book in workbooks for sheet in book['sheets']):,}",
             f"- Adjacent repeated timestamps in raw sheets: {sum(sheet['adjacent_duplicate_timestamps'] for book in workbooks for sheet in book['sheets'])}",
             f"- Backward timestamp steps in raw sheets: {sum(sheet['backward_timestamp_steps'] for book in workbooks for sheet in book['sheets'])}",
             f"- Exact duplicate raw rows: {sum(sheet['duplicate_data_rows'] for book in workbooks for sheet in book['sheets'])}",
             "- Time axis: numeric hours since inoculation in the first column of each sheet; CSV readers receive decimal strings.",
             "- Sheet names distinguish `inline`, `online`, and `offline`, while aligned CSVs group the source `online` channels into `inline` files.", "",
             "## Raw workbook structure", ""]
    for wb in workbooks:
        lines.append(f"- `{wb['file']}`: {len(wb['sheets'])} sheets; experiment={wb['experiment']}; mode={wb['mode']}")
        for sheet in wb["sheets"]:
            lines.append(f"  - `{sheet['name']}`: {sheet['rows_observed']} rows × {sheet['columns_reported']} columns; median sampled interval={sheet['median_positive_interval_hours_sample']} h; missing cells={sheet['missing_cells']}; columns={sheet['columns']}")
    lines.extend(["", "## Aligned reference columns", ""])
    for item in csvs:
        lines.append(f"- `{item['file']}`: {item['columns']}")
    lines.extend(["", "Units are transcribed from source headers where present. The aligned CSVs are publication-provided reconstruction references, not independent biological ground truth."])
    (ROOT / "dataset_profile.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return inventory


if __name__ == "__main__":
    result = inspect()
    print(f"{result['workbook_count']} workbooks, {result['worksheet_count']} worksheets, {result['csv_count']} CSVs")
