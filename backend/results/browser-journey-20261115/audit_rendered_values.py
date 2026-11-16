"""Adjudicate retained DOM values against the independent delivery answer key.

No application imports, network calls, or changes to original browser results.
Run from any directory with Python 3. Output is a separate audit artifact.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
read = lambda p: json.loads(p.read_text())
digest = lambda p: sha256(p.read_bytes()).hexdigest()
report_path = HERE / "timed-1/report.json"
report = read(report_path)
protocol = report["protocol"]
ref = protocol["reference"]
key_path = ROOT / "backend/benchmarks/cmo_ingestion/demo" / ref["package"] / "evaluation/answer_key.json"
assert digest(key_path) == protocol["answer_key_sha256"]
assert digest(HERE / "timed-1/browser-script-at-execution.cjs") == protocol["browser_script_sha256"]
assert digest(HERE / "data-manifest.json") == protocol["manifest_sha256"]
key = read(key_path)
conflicts = {(d["batch"], float(d["time"])) for d in key["defects"]
             if d["rule_code"] == "DUPLICATE_CONFLICT" and d["parameter"] == ref["parameter"]}
points = {(f["batch"], float(f["time"])): float(f["value"]) for f in key["fields"]
          if f["present"] and f["parameter"] == ref["parameter"]
          and f["batch"] in (ref["left"], ref["right"])
          and (f["batch"], float(f["time"])) not in conflicts}
left = {t: v for (b, t), v in points.items() if b == ref["left"]}
right = {t: v for (b, t), v in points.items() if b == ref["right"]}
times = sorted(left.keys() & right.keys())
diffs = {t: right[t] - left[t] for t in times}
largest_time = max(times, key=lambda t: abs(diffs[t]))
unit = ref["unit"]
num = r"([-+]?\d+(?:\.\d+)?)"


def close(got, expected):
    # UI comparison values display four decimal places; no broad relative tolerance.
    return abs(float(got) - expected) <= 0.00005001


def check(row):
    try:
        cells = row["rendered_comparison"].split("\n", 1)[1].split("\t")
        largest = re.fullmatch(num + " " + re.escape(unit) + r" at " + num + r" h", cells[3].splitlines()[0])
        checks = {
            "pair_and_direction": cells[0] == f'{ref["right"]} minus {ref["left"]}',
            "matched_times": int(cells[1].splitlines()[0]) == len(times),
            "elapsed_range": cells[1].splitlines()[1] == f"{times[0]:g} to {times[-1]:g} h",
            "signed_mean_and_unit": cells[2].strip().endswith(" " + unit)
                and close(cells[2].split()[0], statistics.mean(diffs.values())),
            "signed_largest_and_time": bool(largest) and close(largest[1], diffs[largest_time])
                and float(largest[2]) == largest_time,
            "largest_point_values": cells[3].splitlines()[1]
                == f'{ref["right"]} {right[largest_time]:g} {unit} · {ref["left"]} {left[largest_time]:g} {unit}',
            "spread_and_unit": cells[4].splitlines()[0].endswith(" " + unit)
                and close(cells[4].split()[0], statistics.stdev(diffs.values()))
                and "standard deviation" in cells[4],
            "matched_share": cells[5].strip() == f"{100 * len(times) / max(len(left), len(right)):g}%",
        }
        expected = {f"{b}@{t:g}": v for (b, t), v in points.items()}
        drawn = row["rendered_chart_points"]
        checks["unique_expected_point_keys"] = len(drawn) == len(expected) and {p["point"] for p in drawn} == set(expected)
        checks["all_rendered_point_values"] = all(
            (m := re.search(r" h, " + num + " " + re.escape(unit), p["label"]))
            and p["point"] in expected and close(m[1], expected[p["point"]]) for p in drawn)
        return checks
    except (IndexError, KeyError, ValueError, TypeError):
        return {"parseable_comparison_and_chart": False}


rows = [{"repeat": r["repeat"], "checks": check(r)} for r in report["rows"]]
assert all(all(r["checks"].values()) for r in rows), rows
# Negative controls: prove the audit rejects plausible display errors independently
# of unchanged, correct API payloads. These copies never replace recorded results.
rejected = []
for old, new in [("-0.2068", "0.2068"), ("-0.555", "0.555"), ("at 18 h", "at 44 h"),
                 ("0.1945", "0.2945"), ("90%", "100%"), ("g/L", "mg/L")]:
    altered = deepcopy(report["rows"][0])
    assert old in altered["rendered_comparison"]
    altered["rendered_comparison"] = altered["rendered_comparison"].replace(old, new)
    assert not all(check(altered).values()), (old, new)
    rejected.append(f"{old} -> {new}")
altered = deepcopy(report["rows"][0])
altered["rendered_chart_points"][-1] = altered["rendered_chart_points"][0]
assert not all(check(altered).values())
rejected.append("duplicate chart point replaces another point")
audit = {
    "method": "Offline DOM adjudication; values recomputed from independent answer-key fields, excluding labelled conflicts.",
    "source_report_sha256": digest(report_path), "answer_key_sha256": digest(key_path),
    "original_results_modified": False, "repeats_passed": len(rows), "checks_per_repeat": len(rows[0]["checks"]),
    "negative_controls_rejected": rejected, "rows": rows,
}
(HERE / "rendered-values-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
print(json.dumps({k: v for k, v in audit.items() if k != "rows"}))
