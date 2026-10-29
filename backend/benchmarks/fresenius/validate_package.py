from __future__ import annotations

import hashlib
import csv
from datetime import datetime
import json
import tempfile
from pathlib import Path

from benchmarks.common.leakage_audit import audit_package
from benchmarks.common.provenance_validator import validate_mapping
from .build_multimodal_package import build_package
from .build_tasks import build_tasks
from .temporal_replay import state_at
from benchmarks.common.artifact_store import uses_assets


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]


@uses_assets(ROOT / "raw_package")
def validate() -> dict:
    """Validate immutable inputs and every historical package without running an agent."""
    sources = json.loads((ROOT / "source_manifest.json").read_text(encoding="utf-8"))
    source_checks = {}
    for item in sources["source_files"]:
        path = REPOSITORY / item["path"]
        source_checks[item["path"]] = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    current_package = ROOT / "raw_package"
    recorded = json.loads((current_package / "package_manifest.json").read_text(encoding="utf-8"))
    current_files_match = all(
        (current_package / item["path"]).is_file()
        and hashlib.sha256((current_package / item["path"]).read_bytes()).hexdigest() == item["sha256"]
        for item in recorded["files"])
    from benchmarks.common.artifact_store import read_json
    full_map = read_json(ROOT / "ground_truth/source_provenance.json")
    mapped_files_cover_package = ({item["source_file"] for item in full_map["mappings"]} ==
                                  {item["path"] for item in recorded["files"]})
    with tempfile.TemporaryDirectory(prefix="fresenius-determinism-check-") as temporary:
        rebuilt = build_package(Path(temporary) / "raw_package")
        deterministic = (recorded["version"] == rebuilt["version"] and
                         [(item["path"], item["sha256"]) for item in recorded["files"]] ==
                         [(item["path"], item["sha256"]) for item in rebuilt["files"]])
    scenarios = []
    for task in build_tasks():
        with tempfile.TemporaryDirectory(prefix="fresenius-data-check-") as temporary:
            package = Path(temporary) / "agent_input"
            hidden_map = Path(temporary) / "hidden_map.json"
            manifest = build_package(package, as_of=task["as_of"], map_output=hidden_map)
            provenance = validate_mapping(package, hidden_map)
            safe, failures = audit_package(package, as_of=task["as_of"])
            visible = {row["_evidence_id"] for row in state_at(task["as_of"])}
            visible_labs = {row["_evidence_id"]: row for row in state_at(task["as_of"])
                            if row["_table"] == "lab_results"}
            converted_values_valid = True
            local_export = package / "laboratory/lims_review_local.csv"
            if local_export.exists():
                with local_export.open(newline="", encoding="utf-8") as stream:
                    for exported in csv.DictReader(stream):
                        canonical = visible_labs.get(exported["Record"])
                        if canonical is None:
                            converted_values_valid = False; break
                        local = datetime.fromisoformat(exported["Released local (UTC-07)"])
                        utc = datetime.fromisoformat(canonical["available_at"].replace("Z", "+00:00"))
                        value = canonical.get("numerical_result")
                        expected = float(value)*100 if isinstance(value, (int, float)) else None
                        actual = float(exported["Result (% of limit)"]) if exported["Result (% of limit)"] else None
                        if local != utc or actual != expected or exported["Limit basis"] != (canonical.get("unit") or ""):
                            converted_values_valid = False; break
            pointers = json.loads(hidden_map.read_text(encoding="utf-8"))["mappings"]
            mapped = {item["canonical_record_id"] for item in pointers}
            scenarios.append({"task": task["id"], "as_of": task["as_of"],
                              "package_version": manifest["version"], "source_files": len(manifest["files"]),
                              "visible_records": len(visible), "mapped_records": len(mapped),
                              "map_points_to_visible_records": mapped <= visible,
                              "converted_values_valid": converted_values_valid,
                              "provenance_valid": provenance["pass"],
                              "leakage_audit_pass": safe, "leakage_failures": failures})
    result = {"source_checks": source_checks, "current_files_match_manifest": current_files_match,
              "mapped_files_cover_package": mapped_files_cover_package,
              "byte_deterministic_rebuild": deterministic, "scenarios": scenarios,
              "pass": all(source_checks.values()) and current_files_match and mapped_files_cover_package and deterministic and all(
                  row["map_points_to_visible_records"] and row["converted_values_valid"] and row["provenance_valid"]
                  and row["leakage_audit_pass"] for row in scenarios)}
    destination = ROOT / "reports/data_validation.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    report = validate()
    print(json.dumps({"pass": report["pass"], "scenarios": len(report["scenarios"]),
                      "source_checks_pass": all(report["source_checks"].values())}, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
