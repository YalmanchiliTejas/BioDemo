from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.common.agent_adapter import run_investigation
from benchmarks.common.leakage_audit import print_audit
from benchmarks.common.isolated_runner import run_isolated
from benchmarks.baselines.retrieval_llm import SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[2]


def _write_result(benchmark: str, payload: dict) -> Path:
    directory = ROOT / "results" / benchmark
    directory.mkdir(parents=True, exist_ok=True)
    stem = "baseline" if payload["mode"] == "conventional" else payload["mode"]
    if payload.get("task_filter"):
        stem += "_" + payload["task_filter"].lower().replace("-", "_")
    path = directory / f"{stem}_results.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def run(benchmark: str, mode: str, *, isolated: bool = True,
        task_filter: str | None = None) -> dict:
    if mode == "full_rlm":
        raise RuntimeError("Full RLM raw-source integration is not implemented; refusing to publish a surrogate score")
    config_path = ROOT / "benchmarks/configs" / f"{benchmark}.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if benchmark == "fresenius":
        from benchmarks.fresenius.build_tasks import build_tasks
        from benchmarks.fresenius.build_multimodal_package import build_package
        from benchmarks.fresenius.evaluate import evaluate
        from benchmarks.common.provenance_validator import validate_mapping
        outcomes = []
        tasks = build_tasks()
        if task_filter:
            tasks = [task for task in tasks if task["id"] == task_filter]
            if not tasks:
                raise ValueError(f"unknown {benchmark} task: {task_filter}")
        for task in tasks:
            with tempfile.TemporaryDirectory(prefix="fresenius-staged-") as temporary:
                staged = Path(temporary) / "agent_input"
                hidden_map = ROOT / "benchmarks/fresenius/ground_truth/replay_maps" / f"{task['id']}.json"
                preparation_started = time.monotonic()
                manifest = build_package(staged, as_of=task["as_of"], map_output=hidden_map)
                provenance = validate_mapping(staged, hidden_map)
                if not provenance["pass"]:
                    raise RuntimeError("source-to-record provenance validation failed")
                preparation_seconds = round(time.monotonic()-preparation_started, 3)
                if not print_audit(staged, as_of=task["as_of"]):
                    raise RuntimeError("leakage audit failed; scores withheld")
                output = (run_isolated if isolated else run_investigation)(staged, task["objective"], task["as_of"], {"mode": mode, **config})
                outcomes.append({"task": task, "package_records": manifest["record_count"],
                                 "package_version": manifest["version"], "package_files": len(manifest["files"]),
                                 "metrics": evaluate(output, task["as_of"]), "usage": output["usage"],
                                 "automated_package_preparation_seconds": preparation_seconds,
                                 "analysis": output.get("analysis")})
    elif benchmark == "cho":
        from benchmarks.cho.build_tasks import build_tasks
        from benchmarks.cho.evaluate import evaluate
        package = ROOT / "benchmarks/cho/raw/workbooks"
        reference = ROOT / "benchmarks/cho/reference/aligned"
        if not list(package.glob("*.xlsx")):
            raise RuntimeError("CHO workbooks absent; run download first")
        if not print_audit(package):
            raise RuntimeError("leakage audit failed; scores withheld")
        outcomes = []
        # Extraction is shared across objectives; no repeated 12-workbook scan.
        tasks = build_tasks()
        if task_filter:
            tasks = [task for task in tasks if task["id"] == task_filter]
            if not tasks:
                raise ValueError(f"unknown {benchmark} task: {task_filter}")
        first = tasks[0]
        extraction_config = {"mode": "conventional", "capture_records": False,
                             "summarize_numeric": mode == "retrieval_llm", **config}
        if isolated:
            output = run_isolated(package, first["objective"], None, extraction_config)
        else:
            output = run_investigation(package, first["objective"], configuration=extraction_config)
        metrics = evaluate(output, reference, rtol=config["time_zero_rtol"], atol=config["time_zero_atol"])
        full_series_path = ROOT / "benchmarks/cho/reports/full_series_comparison.json"
        comparison = json.loads(full_series_path.read_text(encoding="utf-8")) if full_series_path.exists() else None
        normalization_manifest_path = ROOT / "benchmarks/cho/tasks/normalized/manifest.json"
        normalization_manifest = json.loads(normalization_manifest_path.read_text(encoding="utf-8")) if normalization_manifest_path.exists() else {}
        if comparison is None:
            raise RuntimeError("CHO full-series reference comparison is absent; run --action normalize then --action compare before scoring")
        for task in tasks:
            if task["id"] == "CHO-05":
                perturbed = ROOT / "benchmarks/cho/tasks/perturbed"
                if not list(perturbed.glob("*.xlsx")):
                    from benchmarks.cho.perturbations import generate
                    generate()
                if list(perturbed.glob("*.xlsx")):
                    if not print_audit(perturbed):
                        raise RuntimeError("CHO perturbation leakage audit failed")
                    if isolated:
                        with tempfile.TemporaryDirectory(prefix="cho-perturbed-staged-") as temp_variant:
                            staged_variant = Path(temp_variant) / "agent_input"
                            staged_variant.mkdir()
                            for workbook in perturbed.glob("*.xlsx"):
                                shutil.copy2(workbook, staged_variant / workbook.name)
                            variant = run_isolated(staged_variant, task["objective"], None,
                                                   {"mode": "conventional", "capture_records": False,
                                                    "summarize_numeric": mode == "retrieval_llm", **config})
                            if mode == "retrieval_llm":
                                variant_analysis = run_isolated(staged_variant, task["objective"], None,
                                    {"mode": mode, "preextracted": variant, **config})
                    else:
                        variant = run_investigation(perturbed, task["objective"],
                                                    configuration={"mode": "conventional", "capture_records": False,
                                                                   "summarize_numeric": mode == "retrieval_llm", **config})
                        if mode == "retrieval_llm":
                            variant_analysis = run_investigation(perturbed, task["objective"],
                                configuration={"mode": mode, "preextracted": variant, **config})
                    variant_metrics = {"parsed_sheets": len(variant["files"]),
                                       "parsed_rows": sum(file["records"] for file in variant["files"]),
                                       "semantic_consistency_scored": False,
                                       "reason": "Extraction baseline has no experiment/variable interpretation to compare."}
                    if mode == "retrieval_llm":
                        cited = variant_analysis.get("analysis", {}).get("evidence_ids", [])
                        available = {f"{file['path']}#{file['sheet']}" for file in variant["files"] if file["type"] == "xlsx"}
                        retrieved = set(variant_analysis.get("retrieved_record_ids", []))
                        variant_metrics["analysis_citation_precision"] = sum(identifier in available for identifier in cited)/len(cited) if cited else None
                        variant_metrics["citation_retrieved_precision"] = sum(identifier in retrieved for identifier in cited)/len(cited) if cited else None
                        variant_metrics["source_sheets_retrieved"] = len(retrieved)
                    outcomes.append({"task": task, "metrics": variant_metrics,
                                     "usage": variant_analysis["usage"] if mode == "retrieval_llm" else variant["usage"],
                                     "extraction_usage": variant["usage"] if mode == "retrieval_llm" else None,
                                     "analysis": variant_analysis.get("analysis") if mode == "retrieval_llm" else None})
                    continue
            task_metrics = dict(metrics) if task["id"] in {"CHO-01", "CHO-02"} else {"scored": False, "reason": "Baseline has no autonomous investigation."}
            if task["id"] == "CHO-02" and comparison and mode == "conventional":
                task_metrics.update({"full_trajectory_reconstruction_scored": True,
                                     "full_series_comparable_values": comparison["comparable_values"],
                                     "full_series_within_tolerance": comparison["within_tolerance"],
                                     "full_series_within_tolerance_fraction": comparison["within_tolerance_fraction"],
                                     "full_series_missing_reconstruction_values": comparison["missing_reconstruction_values"],
                                     "full_series_tolerance": comparison["tolerance"]})
                task_metrics.pop("reason", None)
            if mode == "retrieval_llm":
                analyzed = (run_isolated if isolated else run_investigation)(package, task["objective"], None,
                    {"mode": mode, "preextracted": output, **config})
                cited = analyzed.get("analysis", {}).get("evidence_ids", [])
                available = {f"{file['path']}#{file['sheet']}" for file in output["files"] if file["type"] == "xlsx"}
                retrieved = set(analyzed.get("retrieved_record_ids", []))
                task_metrics["analysis_citation_precision"] = sum(identifier in available for identifier in cited)/len(cited) if cited else None
                task_metrics["citation_retrieved_precision"] = sum(identifier in retrieved for identifier in cited)/len(cited) if cited else None
                task_metrics["source_sheets_retrieved"] = len(retrieved)
                outcomes.append({"task": task, "metrics": task_metrics, "usage": analyzed["usage"],
                                 "extraction_usage": output["usage"] if task["id"] == "CHO-01" else None,
                                 "analysis": analyzed.get("analysis")})
                continue
            usage = output["usage"] if task["id"] == "CHO-01" else (
                {"runtime_seconds": normalization_manifest.get("runtime_seconds"), "input_tokens": 0,
                 "output_tokens": 0, "model_calls": 0, "inference_cost_usd": 0}
                if task["id"] == "CHO-02" else {})
            outcomes.append({"task": task, "metrics": task_metrics, "usage": usage})
    else:
        raise ValueError(benchmark)
    versions = {}
    for package_name in ("openpyxl", "reportlab", "pypdf"):
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = None
    source_path = ROOT / ("benchmarks/cho/raw/Dataset.zip" if benchmark == "cho" else "data/v1.1/agent_data.json")
    result = {"benchmark": benchmark, "mode": mode, "task_filter": task_filter,
              "os_isolated_agent": isolated,
              "run_at": datetime.now(timezone.utc).isoformat(), "tasks": outcomes}
    result["reproducibility"] = {"python": platform.python_version(), "packages": versions,
                                  "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                                  "task_sha256": hashlib.sha256(json.dumps([row["task"] for row in outcomes], sort_keys=True).encode()).hexdigest(),
                                  "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() if mode == "retrieval_llm" else None,
                                  "adapter_code_sha256": hashlib.sha256((ROOT / "benchmarks/baselines/retrieval_llm.py" if mode == "retrieval_llm" else ROOT / "benchmarks/baselines/conventional_extraction.py").read_bytes()).hexdigest(),
                                  "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                                  "model": "gpt-6-luna" if mode == "retrieval_llm" else None}
    if benchmark == "cho":
        normalized_manifest = ROOT / "benchmarks/cho/tasks/normalized/manifest.json"
        result["reproducibility"]["normalization_manifest_sha256"] = (
            hashlib.sha256(normalized_manifest.read_bytes()).hexdigest() if normalized_manifest.exists() else None)
    else:
        result["reproducibility"]["package_version"] = outcomes[0]["package_version"] if outcomes else None
    _write_result(benchmark, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", choices=["cho", "fresenius"], required=True)
    parser.add_argument("--mode", choices=["baseline", "retrieval_llm", "full_rlm"], default="baseline")
    parser.add_argument("--task", help="Run one task ID, such as CHO-03 or FRE-02")
    parser.add_argument("--action", choices=["run", "download", "inventory", "references", "generate", "perturb", "normalize", "compare", "clean-generated", "audit", "report", "validate", "data-check"], default="run")
    parser.add_argument("--no-isolation", action="store_true", help="Development only; scores are not publication eligible")
    args = parser.parse_args()
    if args.action in {"download", "inventory", "references", "perturb", "normalize", "compare", "clean-generated"} and args.benchmark != "cho":
        parser.error(f"{args.action} applies only to cho")
    if args.action == "clean-generated":
        generated = (
            * (ROOT / "benchmarks/cho/tasks/normalized").glob("*.csv"),
            * (ROOT / "benchmarks/cho/tasks/perturbed").glob("*.xlsx"),
        )
        bytes_removed = sum(path.stat().st_size for path in generated)
        for path in generated:
            path.unlink()
        print(json.dumps({"removed_files": len(generated), "removed_bytes": bytes_removed}))
        return
    if args.action == "generate" and args.benchmark != "fresenius":
        parser.error("generate applies only to fresenius")
    if args.action == "download":
        from benchmarks.cho.download_dataset import download_and_extract
        print(json.dumps(download_and_extract(), indent=2)); return
    if args.action == "inventory":
        from benchmarks.cho.inspect_dataset import inspect
        result = inspect(); print(result["workbook_count"], result["worksheet_count"], result["csv_count"]); return
    if args.action == "references":
        from benchmarks.cho.reference_builder import build_reference, build_objective_summaries
        from benchmarks.cho.build_comparison_reference import build
        mapping = build_reference()
        objective = build_objective_summaries()
        comparisons = build()
        print(json.dumps({"mapped_columns": mapping["unique_matches"],
                          "cultivations": len(objective["cultivations"]),
                          "experiments_compared": len(comparisons["experiments"])}, indent=2)); return
    if args.action == "generate":
        from benchmarks.fresenius.build_multimodal_package import build_package
        print(json.dumps(build_package(map_output=ROOT / "benchmarks/fresenius/ground_truth/source_provenance.json"), indent=2)); return
    if args.action == "perturb":
        from benchmarks.cho.perturbations import generate
        print(json.dumps(generate(), indent=2)); return
    if args.action == "normalize":
        from benchmarks.cho.aggregation_baseline import build
        result = build(); print(f"Normalized {len(result['cultivations'])} cultivations from original workbooks"); return
    if args.action == "compare":
        from benchmarks.cho.compare_aggregation import compare
        normalized = ROOT / "benchmarks/cho/tasks/normalized"
        if not list(normalized.glob("*.csv")):
            from benchmarks.cho.aggregation_baseline import build
            build()
        result = compare(); print(json.dumps({key: result[key] for key in ("comparable_values", "within_tolerance", "within_tolerance_fraction", "missing_reconstruction_values")}, indent=2)); return
    if args.action == "audit":
        package = ROOT / ("benchmarks/cho/raw/workbooks" if args.benchmark == "cho" else "benchmarks/fresenius/raw_package")
        if not print_audit(package):
            raise SystemExit(1)
        return
    if args.action == "report":
        from benchmarks.common.report import generate
        print(generate(args.benchmark)); return
    if args.action == "validate":
        if args.benchmark == "cho":
            from benchmarks.cho.download_dataset import MD5
            archive = ROOT / "benchmarks/cho/raw/Dataset.zip"
            state = hashlib.md5()
            with archive.open("rb") as source:
                for chunk in iter(lambda: source.read(1024*1024), b""):
                    state.update(chunk)
            digest = state.hexdigest()
            if digest != MD5:
                raise SystemExit(f"CHO checksum mismatch: {digest}")
            manifest = json.loads((ROOT / "benchmarks/cho/source_manifest.json").read_text(encoding="utf-8"))
            for member in manifest["members"]:
                path = ROOT / "benchmarks/cho" / member["installed_path"]
                if hashlib.sha256(path.read_bytes()).hexdigest() != member["sha256"]:
                    raise SystemExit("CHO extracted source checksum mismatch: " + member["installed_path"])
            print(f"CHO archive and {len(manifest['members'])} extracted source checksums: PASS")
        else:
            from src.evaluation.leakage_audit import run_leakage_audit
            manifest = json.loads((ROOT / "benchmarks/fresenius/source_manifest.json").read_text(encoding="utf-8"))
            for source in manifest["source_files"]:
                path = ROOT / source["path"]
                if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                    raise SystemExit("Fresenius source checksum mismatch: " + source["path"])
            audit = run_leakage_audit(ROOT / "data/v1.1/agent_data.json")
            if audit.status != "PASS":
                raise SystemExit("Fresenius frozen data validation failed: " + "; ".join(audit.failures))
            print("Fresenius frozen data validation: PASS")
        return
    if args.action == "data-check":
        if args.benchmark == "cho":
            perturbed = ROOT / "benchmarks/cho/tasks/perturbed"
            if not list(perturbed.glob("*.xlsx")):
                from benchmarks.cho.perturbations import generate
                generate()
            from benchmarks.cho.validate_perturbation import validate
            result = validate()
            print(json.dumps({"pass": result["pass"], "cells_checked": result["cells_checked"]}, indent=2))
        else:
            from benchmarks.fresenius.validate_package import validate
            result = validate()
            print(json.dumps({"pass": result["pass"], "scenarios": len(result["scenarios"])}, indent=2))
        if not result["pass"]:
            raise SystemExit(1)
        return
    mode = "conventional" if args.mode == "baseline" else args.mode
    result = run(args.benchmark, mode, isolated=not args.no_isolation, task_filter=args.task)
    stem = "baseline" if mode == "conventional" else mode
    if args.task:
        stem += "_" + args.task.lower().replace("-", "_")
    print(json.dumps({"benchmark": result["benchmark"], "tasks": len(result["tasks"]),
                      "result": str(ROOT / "results" / args.benchmark / f"{stem}_results.json")}, indent=2))


if __name__ == "__main__":
    main()
