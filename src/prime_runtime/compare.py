"""Run a simple, explicitly labeled baseline-versus-Prime pilot on one package."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from benchmarks.baselines.conventional_extraction import ConventionalExtraction
from benchmarks.common.agent_adapter import InvestigationInput
from src.manufacturing_data import ManufacturingStore, ingest_package
from src.manufacturing_data.ingest import _members
from src.state import BlackboardStore
from src.workflows import ManufacturingInvestigationWorkflow

from .harness import PrimeManufacturingHarness


def _minutes(value: float | None, label: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{label} must be nonnegative")


def run_comparison(*, package: Path, objective: str, output: Path,
                   as_of: str | None = None, scope: str = "pilot",
                   baseline_human_minutes: float | None = None,
                   assisted_human_minutes: float | None = None,
                   loaded_hourly_rate_usd: float | None = None,
                   total_agent_cost_usd: float | None = None,
                   progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Use the same source folder for a parser baseline and a real Prime rollout.

    This is a pilot comparison, not a held-out benchmark score. The baseline
    does no investigation, and human time/cost inputs must be observed separately.
    """
    package, output = package.resolve(), output.resolve()
    if not package.is_dir() and not (package.is_file() and package.suffix.lower() == ".zip"):
        raise ValueError("package must be a source folder or ZIP")
    if package.is_dir() and not any(path.is_file() for path in package.rglob("*")):
        raise ValueError("package has no files")
    if package.is_dir() and (output == package or package in output.parents):
        raise ValueError("output must be outside the source package")
    if not objective.strip():
        raise ValueError("objective is required")
    for value, label in ((baseline_human_minutes, "baseline human minutes"),
                         (assisted_human_minutes, "assisted human minutes"),
                         (loaded_hourly_rate_usd, "loaded hourly rate"),
                         (total_agent_cost_usd, "total agent cost")):
        _minutes(value, label)
    if bool(baseline_human_minutes is not None) != bool(assisted_human_minutes is not None):
        raise ValueError("provide both baseline and assisted human minutes")
    if as_of is None:
        as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        as_of = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    output.mkdir(parents=True, exist_ok=True)
    # Avoid reusing a previous store or session; the two modes get the same
    # source bytes and each command is an independent trial.
    with tempfile.TemporaryDirectory(prefix="manufacturing-pilot-") as temporary:
        trial = Path(temporary)
        baseline_package = package
        if package.suffix.lower() == ".zip":
            baseline_package = trial / "baseline_package"
            baseline_package.mkdir()
            for relative, content, _, _ in _members(package):
                destination = baseline_package / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        if progress:
            progress("Reading source records")
        baseline = ConventionalExtraction().run_investigation(
            InvestigationInput(baseline_package, objective, as_of,
                               {"capture_records": False}))
        store = ManufacturingStore(trial / "store")
        if progress:
            progress("Preparing the agent evidence store")
        ingestion_started = time.monotonic()
        ingestion = ingest_package(package, store, access_scope=scope)
        ingestion_seconds = round(time.monotonic() - ingestion_started, 3)
        if ingestion["errors"]:
            raise RuntimeError("ingestion had extraction errors; review them before comparing: "
                               + json.dumps(ingestion["errors"][:10]))
        boards = BlackboardStore(trial / "blackboards")
        workflow = ManufacturingInvestigationWorkflow(
            trial / "workflow", store, scope=scope, blackboards=boards)
        harness = PrimeManufacturingHarness.from_env(
            store=store, blackboards=boards, workflow=workflow, scope=scope)
        try:
            if progress:
                progress("Agent investigating evidence")
            agent_started = time.monotonic()
            agent = harness.run(incident_id="pilot-001", problem=objective,
                                new_evidence_ids=[], as_of=as_of)
            agent_seconds = round(time.monotonic() - agent_started, 3)
        except BaseException:
            # Preserve the private run logs before the temp trial is deleted.
            run_logs = trial / "blackboards" / "prime-runtime" / "logs"
            if run_logs.is_dir():
                for entry in sorted(run_logs.iterdir()):
                    if entry.is_file():
                        shutil.copy2(entry, output / entry.name)
            for name in ('investigation-checkpoint.json','analysis-preparation.json'):
                artifact=trial/'blackboards/prime-runtime/workspaces/pilot-001'/name
                if artifact.is_file():shutil.copy2(artifact,output/name)
            raise
        cited = []
        for identifier in dict.fromkeys(agent.get("evidence_ids", [])):
            cited.extend(store.visible(as_of=as_of, scopes=(scope,),
                                       observation_id=str(identifier), limit=1))
        (output / "cited_evidence.json").write_text(json.dumps(cited, indent=2, default=str) + "\n")
        metrics = agent.get("rollout_metrics", {})
        log = Path(metrics["prime_log"]) if metrics.get("prime_log") else None
        if log and log.is_file():
            copied = output / "prime_sdk_events.jsonl"
            shutil.copy2(log, copied)
            metrics["prime_log"] = str(copied)
        tools_log = Path(metrics["prime_tool_calls"]) if metrics.get("prime_tool_calls") else None
        if tools_log and tools_log.is_file():
            copied_tools = output / "prime_tool_calls.jsonl"
            shutil.copy2(tools_log, copied_tools)
            metrics["prime_tool_calls"] = str(copied_tools)
        for name in ('investigation-checkpoint.json','analysis-preparation.json'):
            artifact=trial/'blackboards/prime-runtime/workspaces/pilot-001'/name
            if artifact.is_file():shutil.copy2(artifact,output/name)
        if agent.get('analysis_preparation_artifact'):
            agent['analysis_preparation_artifact']=str(output/'analysis-preparation.json')

    if progress:
        progress("Saving the investigation report")
    human_minutes_saved = None
    labor_value_usd = None
    net_value_usd = None
    if baseline_human_minutes is not None and assisted_human_minutes is not None:
        human_minutes_saved = round(baseline_human_minutes - assisted_human_minutes, 2)
        if loaded_hourly_rate_usd is not None:
            labor_value_usd = round(human_minutes_saved / 60 * loaded_hourly_rate_usd, 2)
            if total_agent_cost_usd is not None:
                net_value_usd = round(labor_value_usd - total_agent_cost_usd, 2)
    result = {
        "claim_status": "pilot_comparison_not_held_out_evaluation",
        "objective": objective, "as_of": as_of, "scope": scope,
        "source_package": str(package),
        "without_agent": {
            "capability": "conventional extraction only; no investigation",
            "parsed_files_or_sheets": len(baseline["files"]),
            "extraction_seconds": baseline["usage"]["runtime_seconds"],
            "human_minutes": baseline_human_minutes,
        },
        "with_agent": {
            "capability": "Prime SDK investigation on an ingested copy of the same files",
            "ingestion": {"files_seen": ingestion["files_seen"],
                          "files_indexed": ingestion["files_indexed"],
                          "observations": ingestion["observations"],
                          "runtime_seconds": ingestion_seconds},
            "investigation_seconds": agent_seconds,
            "assessment": agent.get("assessment"),
            "severity": agent.get("severity"),
            "cited_evidence_count": len(agent.get("evidence_ids", [])),
            "hypothesis_count": len(agent.get("causal_hypotheses", [])),
            "pending_evidence_request_count": len(agent.get("pending_evidence_requests", [])),
            "rollout_metrics": agent.get("rollout_metrics", {}),
            "human_minutes_including_review_and_correction": assisted_human_minutes,
        },
        "measured_value": {
            "human_minutes_saved": human_minutes_saved,
            "loaded_hourly_rate_usd": loaded_hourly_rate_usd,
            "labor_value_usd": labor_value_usd,
            "total_agent_cost_usd": total_agent_cost_usd,
            "net_value_usd": net_value_usd,
            "note": "Human times and total cost are user-supplied measurements. "
                    "Prime root-session cost excludes child worker usage; supply total cost separately.",
        },
        "limitations": [
            "The conventional parser is not a human investigation or an equivalent reasoning system.",
            "Investigation quality and causal correctness require independent review.",
            "One case does not establish repeatability or generalization.",
        ],
    }
    (output / "comparison.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    (output / "agent_report.json").write_text(json.dumps(agent, indent=2, default=str) + "\n")
    (output / "comparison.md").write_text(
        "# Manufacturing OS pilot comparison\n\n"
        f"Objective: {objective}\n\nAs of: {as_of}\n\n"
        "| Measure | Without agent | With Prime |\n| --- | ---: | ---: |\n"
        f"| Machine seconds | {baseline['usage']['runtime_seconds']} extraction | "
        f"{ingestion_seconds} ingestion + {agent_seconds} investigation |\n"
        f"| Cited evidence | none | {len(agent.get('evidence_ids', []))} |\n"
        f"| Hypotheses | none | {len(agent.get('causal_hypotheses', []))} |\n"
        f"| Human minutes | {baseline_human_minutes if baseline_human_minutes is not None else 'unmeasured'} | "
        f"{assisted_human_minutes if assisted_human_minutes is not None else 'unmeasured'} |\n\n"
        f"Human minutes saved: {human_minutes_saved if human_minutes_saved is not None else 'unmeasured'}  \n"
        f"Net labor value (USD): {net_value_usd if net_value_usd is not None else 'unmeasured'}\n\n"
        "The baseline only extracts files; it does not investigate. Review the agent's "
        "evidence and conclusions independently. This is a pilot, not a held-out benchmark score.\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare conventional extraction with a Prime investigation")
    parser.add_argument("package", type=Path, help="folder or ZIP of raw source files")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--as-of", help="ISO timestamp with timezone; defaults to now")
    parser.add_argument("--scope", default="pilot")
    parser.add_argument("--output", type=Path, default=Path("runs/prime-comparison"))
    parser.add_argument("--baseline-human-minutes", type=float)
    parser.add_argument("--assisted-human-minutes", type=float)
    parser.add_argument("--loaded-hourly-rate-usd", type=float)
    parser.add_argument("--total-agent-cost-usd", type=float)
    args = parser.parse_args()
    result = run_comparison(package=args.package, objective=args.objective,
                            output=args.output, as_of=args.as_of, scope=args.scope,
                            baseline_human_minutes=args.baseline_human_minutes,
                            assisted_human_minutes=args.assisted_human_minutes,
                            loaded_hourly_rate_usd=args.loaded_hourly_rate_usd,
                            total_agent_cost_usd=args.total_agent_cost_usd)
    print(json.dumps({"report": str(args.output.resolve() / "comparison.md"),
                      "human_minutes_saved": result["measured_value"]["human_minutes_saved"],
                      "net_value_usd": result["measured_value"]["net_value_usd"]}, indent=2))


if __name__ == "__main__":
    main()
