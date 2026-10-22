from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _float(value: str | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def compare(normalized_root: Path = ROOT / "tasks/normalized") -> dict:
    """Evaluator-only full-series comparison against publication alignment."""
    if not (normalized_root / "manifest.json").exists():
        raise FileNotFoundError("run CHO aggregation baseline first")
    summaries = json.loads((ROOT / "reference/objective_summaries.json").read_text(encoding="utf-8"))["cultivations"]
    tolerance = json.loads((ROOT.parents[1] / "benchmarks/configs/cho.json").read_text(encoding="utf-8"))["full_series_normalized_tolerance"]
    files = []
    all_pairs = all_within = all_missing = 0
    for reference_path in sorted((ROOT / "reference/aligned").glob("*.csv")):
        normalized_path = normalized_root / reference_path.name
        if not normalized_path.exists():
            raise FileNotFoundError(normalized_path)
        name = reference_path.stem
        cultivation = "_".join(name.split("_")[:3:2])  # EXP001_R01, ignoring process mode
        if cultivation not in summaries:
            raise KeyError(cultivation)
        with normalized_path.open(newline="", encoding="utf-8-sig") as stream:
            normalized_rows = list(csv.DictReader(stream))
        kind = "offline" if name.endswith("_offline") else "inline"
        if kind == "inline":
            index = {round(float(row["Time (h)"])*60): row for row in normalized_rows}
            get_row = lambda t: index.get(round(t*60)) if abs(t*60-round(t*60)) < 1e-5 else None
        else:
            index = {round(float(row["Time (h)"]), 7): row for row in normalized_rows}
            get_row = lambda t: index.get(round(t, 7))
        metrics = defaultdict(lambda: {"pairs": 0, "within_tolerance": 0, "missing_reconstruction": 0,
                                       "absolute_errors": [], "normalized_errors": []})
        with reference_path.open(newline="", encoding="utf-8-sig") as stream:
            for reference in csv.DictReader(stream):
                t = _float(reference.get("Time (h)"))
                if t is None:
                    continue
                actual = get_row(t)
                for column, reference_value in reference.items():
                    if column == "Time (h)":
                        continue
                    target = _float(reference_value)
                    if target is None:
                        continue
                    record = metrics[column]
                    estimate = _float(actual.get(column)) if actual else None
                    if estimate is None:
                        record["missing_reconstruction"] += 1; all_missing += 1
                        continue
                    descriptor = summaries[cultivation]["measurements"].get(column)
                    if descriptor is None:
                        raise KeyError((cultivation, column))
                    scale = max(descriptor["max"]-descriptor["min"], abs(target), 1e-6)
                    absolute = abs(estimate-target)
                    normalized = absolute/scale
                    record["pairs"] += 1; all_pairs += 1
                    record["absolute_errors"].append(absolute)
                    record["normalized_errors"].append(normalized)
                    if normalized <= tolerance:
                        record["within_tolerance"] += 1; all_within += 1
        compact = {}
        for column, row in metrics.items():
            errors = sorted(row.pop("normalized_errors"))
            absolutes = row.pop("absolute_errors")
            compact[column] = {**row,
                               "median_normalized_absolute_error": statistics.median(errors) if errors else None,
                               "p95_normalized_absolute_error": errors[min(len(errors)-1, math.floor(.95*len(errors)))] if errors else None,
                               "mean_absolute_error_native_units": statistics.mean(absolutes) if absolutes else None}
        files.append({"aligned_csv": reference_path.name, "normalized_csv": normalized_path.name,
                      "measurements": compact})
    result = {"method": "same-timestamp comparison; errors normalized by max(reference range, reference magnitude, 1e-6)",
              "tolerance": f"normalized absolute error <= {tolerance}",
              "comparable_values": all_pairs, "within_tolerance": all_within,
              "within_tolerance_fraction": all_within/all_pairs if all_pairs else None,
              "missing_reconstruction_values": all_missing, "files": files}
    destination = ROOT / "reports/full_series_comparison.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    result = compare()
    print({key: result[key] for key in ("comparable_values", "within_tolerance", "within_tolerance_fraction", "missing_reconstruction_values")})
