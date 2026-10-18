"""Score reviewed engineering deliverables and measured human effort.

This is an evaluation-side ledger, never an agent input or a runtime estimate.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

VERSION = "engineering-work-v1"
HEADLINE = "Correctly completed engineering work per human-hour, including setup and verification"
PHASES = ("setup", "alignment", "analysis", "verification", "rework")
WORKFLOWS = ("traditional", "ai")
GATES = ("complete", "evidence_supported", "risk_signals_addressed",
         "escalation_correct", "uncertainty_appropriate")
ROOT = Path(__file__).resolve().parents[2]


def protocol(benchmark: str) -> dict:
    if benchmark not in {"fresenius", "cho"}:
        raise ValueError(f"unknown benchmark: {benchmark}")
    if benchmark == "fresenius":
        experiments = [
            ("A", "Total effort", "Produce a reviewable investigation from raw records.",
             ["Count retrieval, batch reconciliation, timeline construction, investigation drafting, review and corrections."],
             ["Time-valid evidence inventory", "Risk assessment and competing RCA hypotheses", "Human-reviewed next actions"]),
            ("B", "Unfamiliar data", "Investigate frozen variants with missing or contradictory documents and inconsistent batch identifiers.",
             ["Missing critical lab review", "Conflicting lab and batch records", "Aliased or ambiguous batch identifiers"],
             ["Identify missing and contradictory evidence", "Resolve identifiers or explicitly abstain", "Escalate unresolved material risk"]),
            ("C", "Trustworthiness", "Distinguish supported conclusions from plausible RCA and respond correctly to risk signals.",
             ["Plausible but unsupported RCA", "Subtle cross-batch risk signal", "Unrelated abnormality requiring scoped escalation"],
             ["No unsupported confirmed root cause", "No missed material risk signal", "Correct escalation and uncertainty"]),
        ]
    else:
        experiments = [
            ("A", "Total effort", "Produce a validated cultivation comparison from raw experimental tables.",
             ["Count setup, schema and unit mapping, time alignment, analysis, validation and corrections."],
             ["Traceable cultivation alignment", "Validated numerical comparison", "Evidence-linked findings and limitations"]),
            ("B", "Unfamiliar data", "Repeat on raw tables from cultivations excluded from prompt and mapping development.",
             ["Hold out entire experiments with both reactors together", "Freeze prompts and mappings before release", "Use new cultivations for an untouched generalization claim"],
             ["Recover identities, units and time axes", "Validate on held-out cultivations", "Report unresolved schema and coverage gaps"]),
            ("C", "Trustworthiness", "Assess descriptive associations without unsupported process optimization claims.",
             ["Constant or confounded channels", "Spurious association or irrelevant variable", "Optimization request without causal or intervention evidence"],
             ["Reject false correlations", "No unsupported causal or optimization claim", "Quantify uncertainty and propose validation"]),
        ]
    return {
        "version": VERSION, "benchmark": benchmark, "headline": HEADLINE,
        "phases": list(PHASES), "acceptance_gates": list(GATES),
        "experiments": [dict(id=i, label=label, objective=objective, variants=variants,
                             deliverables=deliverables, status="planned")
                        for i, label, objective, variants, deliverables in experiments],
        "qualification": (
            "Existing extraction scores, simulation projections and unscored pilots do not measure this metric. "
            "Current CHO splits were defined after all workbooks had been used; they are not an untouched holdout."
        ),
    }


def template(benchmark: str) -> dict:
    """Nulls deliberately require observation; zero means observed zero effort."""
    return {"version": VERSION, "benchmark": benchmark, "runs": [
        {"run_id": f"{experiment}-{workflow}-1", "pair_id": f"{experiment}-1",
         "experiment": experiment, "workflow": workflow,
         "package_sha256": None, "task_spec_sha256": None, "output_ref": None,
         "effort_complete": False,
         "human_effort": {phase: {"person_minutes": None, "manual_steps": None} for phase in PHASES},
         "review": {"reviewer": None, "evidence_ref": None,
                    "gates": {gate: None for gate in GATES}}}
        for experiment in ("A", "B", "C") for workflow in WORKFLOWS]}


def _number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _run_errors(run: dict) -> list[str]:
    errors = []
    for key in ("run_id", "pair_id", "output_ref"):
        if not isinstance(run.get(key), str) or not run[key].strip():
            errors.append(f"missing {key}")
    for key in ("package_sha256", "task_spec_sha256"):
        digest = run.get(key)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            errors.append(f"invalid {key}")
    if run.get("effort_complete") is not True:
        errors.append("human effort log incomplete")
    for phase in PHASES:
        effort = run.get("human_effort", {}).get(phase, {})
        if not _number(effort.get("person_minutes")):
            errors.append(f"missing measured {phase} person-minutes")
        steps = effort.get("manual_steps")
        if type(steps) is not int or steps < 0:
            errors.append(f"missing measured {phase} manual steps")
    review = run.get("review", {})
    for key in ("reviewer", "evidence_ref"):
        if not isinstance(review.get(key), str) or not review[key].strip():
            errors.append(f"missing review {key}")
    for gate in GATES:
        if type(review.get("gates", {}).get(gate)) is not bool:
            errors.append(f"unreviewed gate: {gate}")
    return errors


def score(ledger: dict) -> dict:
    """Withhold incomplete cohorts; failed work still contributes all effort.

    One row is one assigned deliverable, with every retry included in its effort.
    Review gate failures count as zero completions, not missing observations.
    """
    benchmark = ledger.get("benchmark")
    spec = protocol(benchmark)
    if ledger.get("version") != VERSION:
        raise ValueError("unsupported engineering-work ledger version")
    runs = ledger.get("runs", [])
    seen = set()
    pairs = set()
    for run in runs:
        if run.get("workflow") not in WORKFLOWS or run.get("experiment") not in {"A", "B", "C"}:
            raise ValueError("unknown workflow or experiment")
        identifier = run.get("run_id")
        if identifier and identifier in seen:
            raise ValueError(f"duplicate run_id: {identifier}")
        seen.add(identifier)
        pair = (run["experiment"], run.get("pair_id"), run["workflow"])
        if pair in pairs:
            raise ValueError(f"duplicate workflow assignment: {pair}")
        pairs.add(pair)
    output = {"version": VERSION, "benchmark": benchmark, "headline": HEADLINE, "experiments": []}
    for experiment in spec["experiments"]:
        selected = [r for r in runs if r["experiment"] == experiment["id"]]
        sides = {}
        for workflow in WORKFLOWS:
            rows = [r for r in selected if r["workflow"] == workflow]
            issues = [f"{r.get('run_id')}: {error}" for r in rows for error in _run_errors(r)]
            if not rows:
                issues.append("No human effort and reviewed outcomes recorded.")
            minutes = sum(r["human_effort"][p]["person_minutes"] for r in rows for p in PHASES) if not issues else None
            if minutes == 0:
                issues.append("Zero human time cannot establish a per-human-hour rate.")
            completed = sum(all(r["review"]["gates"][g] for g in GATES) for r in rows) if not issues else None
            sides[workflow] = {
                "status": "not_measured" if issues else "observed",
                "assigned": len(rows), "correctly_completed": completed,
                "person_hours": minutes / 60 if minutes is not None else None,
                "manual_steps": sum(r["human_effort"][p]["manual_steps"] for r in rows for p in PHASES) if not issues else None,
                "gate_failures": {g: sum(not r["review"]["gates"][g] for r in rows) for g in GATES} if not issues else None,
                "value": completed / (minutes / 60) if not issues else None,
                "issues": issues,
            }
        matched = bool(selected) and all(s["status"] == "observed" for s in sides.values())
        by_workflow = {w: {r.get("pair_id"): (r.get("package_sha256"), r.get("task_spec_sha256"))
                           for r in selected if r["workflow"] == w} for w in WORKFLOWS}
        matched = matched and by_workflow["traditional"] == by_workflow["ai"]
        output["experiments"].append({**experiment, "status": "observed" if matched else "not_measured",
                                      "paired": matched, "sides": sides})
    # A is the end-to-end productivity endpoint. B and C test its robustness;
    # pooling their different challenge mixes would obscure the effect.
    output["primary"] = output["experiments"][0]
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=["fresenius", "cho"], required=True)
    parser.add_argument("--ledger", type=Path, help="Score a completed evaluation-side ledger")
    parser.add_argument("--template", action="store_true", help="Print an unmeasured capture template")
    args = parser.parse_args()
    if args.ledger and args.template:
        parser.error("choose --ledger or --template")
    if args.ledger:
        ledger = json.loads(args.ledger.read_text())
        if ledger.get("benchmark") != args.benchmark:
            parser.error("ledger benchmark does not match --benchmark")
        result = score(ledger)
    else:
        result = template(args.benchmark) if args.template else protocol(args.benchmark)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
