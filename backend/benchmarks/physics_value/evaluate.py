"""Host-side synthetic scoring and sequential measurement/intervention sessions."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

import numpy as np

from .domains import actions, apply_action, measure, measurement_catalog, observe, outcome, run_reference
from .generate import digest, dump


def checked_file(dataset: Path, relative: str) -> Path:
    root = Path(dataset).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("dataset path escape")
    manifest = json.loads((root / "manifest.json").read_text())
    if str(path.relative_to(root)) not in manifest["files_sha256"]:
        raise ValueError("file is not in the frozen manifest")
    if digest(path) != manifest["files_sha256"][str(path.relative_to(root))]:
        raise ValueError("dataset checksum mismatch: " + relative)
    return path


def verify_implementation(dataset: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    manifest = json.loads((Path(dataset) / "manifest.json").read_text())
    for relative, expected in manifest["code_sha256"].items():
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file() or digest(source) != expected:
            raise ValueError("implementation differs from frozen dataset: " + relative)


def load_case(dataset: Path, case_id: str) -> dict:
    if not re.fullmatch(r"PV-[0-9a-f]{12}", case_id):
        raise ValueError("invalid case identifier")
    return json.loads(checked_file(dataset, f"evaluator/cases/{case_id}.json").read_text())


def load_packet(dataset: Path, case_id: str, task: str) -> dict:
    if task not in ("diagnosis", "optimization", "resolution", "pretransfer"):
        raise ValueError("unknown task")
    if not re.fullmatch(r"PV-[0-9a-f]{12}", case_id):
        raise ValueError("invalid case identifier")
    return json.loads(checked_file(dataset, f"public/{case_id}/{task}/packet.json").read_text())


def stage(dataset: Path, case_id: str, task: str, arm: str, destination: Path) -> dict:
    """Copy one task, not a parent directory containing futures or evaluator data."""
    if arm not in ("A", "B"):
        raise ValueError("arm must be A or B")
    packet = load_packet(dataset, case_id, task)
    destination = Path(destination).resolve()
    if destination.is_relative_to(Path(dataset).resolve()):
        raise ValueError("agent workspace must be outside the evaluator dataset")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("stage into a fresh workspace")
    destination.mkdir(parents=True, exist_ok=True)
    directory = Path(dataset) / "public" / case_id / task
    common = {}
    for source in sorted(directory.iterdir()):
        checked_file(dataset, str(source.relative_to(dataset)))
        shutil.copyfile(source, destination / source.name)
        common[source.name] = digest(source)
    tool = {"normal_tools": "Same evidence retrieval, statistics and general-purpose computation in both arms.",
            "additional_host_tools": ([{"name": "physical_forward_model", "entry_point": "benchmarks.physics_value.public_models.predict",
                                        "arguments": ["packet", "action_id", "parameter_overrides"],
                                        "description": "Forward prediction only. No hidden reference, cause label, action ranking or future measurements."}]
                                      if arm == "B" else [])}
    dump(destination / "tools.json", tool)
    receipt = {"case_id": packet["case_id"], "task": task, "arm": arm,
               "common_input_sha256": common, "executed_agent": False,
               "security": "Staging does not enforce worker filesystem/network isolation. Host must deny the source dataset, evaluator code and external answer retrieval."}
    dump(destination / "staging-receipt.json", receipt)
    return receipt


def score_submission(dataset: Path, case_id: str, task: str, submission: dict) -> dict:
    verify_implementation(dataset)
    case = load_case(dataset, case_id)
    packet = load_packet(dataset, case_id, task)
    hypotheses = submission.get("hypotheses", [])
    if not isinstance(hypotheses, list) or any(not isinstance(x, str) for x in hypotheses):
        raise ValueError("hypotheses must be a ranked list of class names")
    if len(set(hypotheses)) != len(hypotheses) or set(hypotheses) - set(packet["hypothesis_classes"]):
        raise ValueError("unknown or duplicate hypothesis")
    truth = set(case["causes"])
    result = {"case_id": case_id, "task": task,
              "classification": "synthetic_reference_score_not_real_causal_validation",
              "authored_cause_coverage": len(truth & set(hypotheses)) / len(truth),
              "hypothesis_set_size": len(hypotheses),
              "top_rank_matches_authored_cause": hypotheses[0] in truth if hypotheses else None,
              "unique_cause_identifiability": case["initial_unique_cause_identifiability"],
              "verified_cause_asserted_without_session_measurements": submission.get("claim_verified", False) is True,
              "evidence_grounding_score": None, "blinded_scientific_review": None,
              "agent_wall_seconds": None, "observed_human_minutes": None}
    if task == "resolution":
        raise ValueError("resolution requires SimulationSession; a static report is not a verified fix")
    if task in ("optimization", "pretransfer"):
        chosen = submission.get("action_id")
        outcomes = case["counterfactuals"][task]
        decision = submission.get("decision", "proceed")
        if task == "pretransfer" and decision in ("characterize", "abstain"):
            requested = submission.get("requested_measurements", [])
            valid = {r["id"] for r in packet["measurement_catalog"]}
            if not isinstance(requested, list) or any(not isinstance(x, str) or x not in valid for x in requested):
                raise ValueError("unknown requested measurement")
            if decision == "characterize" and not requested:
                raise ValueError("characterization requires a requested measurement")
            result.update(decision=decision, chosen_action_id=None, action_not_committed=True,
                          requested_measurements=requested, characterization_usefulness_review=None,
                          independently_replayed_outcome=None, feasible_objective_regret=None)
        else:
            if task == "pretransfer" and decision != "proceed":
                raise ValueError("unknown pretransfer decision")
            if chosen not in outcomes:
                raise ValueError("choose an allowed action_id")
            actual = outcomes[chosen]
            feasible = [r["objective_value"] for r in outcomes.values()
                        if r["feasible_full_batch"] and r["objective_value"] is not None]
            best = min(feasible) if feasible else None
            result.update(chosen_action_id=chosen, independently_replayed_outcome=actual,
                          finite_grid_best_feasible_objective=best,
                          feasible_objective_regret=actual["objective_value"]-best
                          if actual["feasible_full_batch"] and best is not None else None,
                          finite_grid_has_feasible_action=best is not None)
        if task == "pretransfer":
            warned = submission.get("warn_before_transfer")
            if warned is not None and type(warned) is not bool:
                raise ValueError("warn_before_transfer must be true, false or null for abstention")
            original = outcomes["keep"]
            risk = not original["feasible_full_batch"]
            result.update(original_plan_has_simulated_risk=risk,
                          warning_result="abstained" if warned is None else
                          ("TP" if risk else "FP") if warned else ("FN" if risk else "TN"),
                          potential_warning_lead_h=original["first_issue_h"] if warned and risk else None,
                          prevented_real_batches=None)
    return result


class SimulationSession:
    """Host-owned sequential resolution. It exposes results only after clock advances.

    Assays are idealized and exact in this pilot. No time/effort result here is an
    observed human measurement. One committed action ends this single-batch trial.
    """

    def __init__(self, dataset: Path, case_id: str):
        verify_implementation(dataset)
        self.case = load_case(dataset, case_id)
        self.packet = load_packet(dataset, case_id, "resolution")
        self.time_h = self.packet["decision_time_h"]
        self.human_work_minutes = 0.
        self.events = []
        self.finished = False

    def request_measurement(self, measurement: str) -> dict:
        if self.finished:
            raise ValueError("session already committed")
        options = {m["id"]: m for m in measurement_catalog(self.case["domain"])}
        if measurement not in options:
            raise ValueError("unknown measurement")
        if any(e.get("measurement") == measurement for e in self.events):
            raise ValueError("measurement already available; reuse its result")
        option = options[measurement]
        arrives = self.time_h + option["turnaround_h"]
        physical_end = self.case["reference"]["completion_time_h"] or self.case["config"]["duration_h"]
        if arrives >= physical_end:
            raise ValueError("measurement would arrive after the batch decision window")
        result = measure(self.case, measurement, arrives)
        self.time_h = arrives
        self.human_work_minutes += option["human_work_minutes"]
        self.events.append(result)
        observations = [deepcopy(r) for r in self.case["observations"] if r["available_at_h"] <= arrives]
        self.packet["decision_time_h"] = arrives
        self.packet["receiving_observations"] = observations
        return {"result": deepcopy(result), "current_time_h": arrives, "observations": observations,
                "current_packet": deepcopy(self.packet),
                "synthetic_human_work_minutes": self.human_work_minutes}

    def commit(self, action_id: str, *, hypotheses: list[str]) -> dict:
        if self.finished:
            raise ValueError("session already committed")
        if not isinstance(hypotheses, list) or any(not isinstance(x, str) for x in hypotheses) or set(hypotheses) - set(self.packet["hypothesis_classes"]):
            raise ValueError("unknown hypothesis class")
        action = next((a for a in actions(self.case["domain"]) if a["id"] == action_id), None)
        if action is None:
            raise ValueError("action not available for an in-progress batch")
        config = apply_action(self.case["domain"], self.case["config"], action, self.time_h)
        actual = run_reference(self.case["domain"], config, self.case["mechanism"])
        scored = outcome(self.case["domain"], actual, config, self.time_h)
        finish = actual["completion_time_h"] or config["duration_h"]
        if finish <= self.time_h:
            raise ValueError("batch already completed before intervention")
        seed = int(hashlib.sha256(f"{self.case['case_id']}:{action_id}:{self.time_h}".encode()).hexdigest()[:16], 16)
        observed = observe(self.case["domain"], actual, self.case["mechanism"], np.random.default_rng(seed))
        # Verification is an assumed additional one-hour/15-minute assay, after
        # observing the actual endpoint, not an instantaneous counterfactual oracle.
        verified_at = finish + 1.
        self.human_work_minutes += 15.
        decision = self.time_h
        self.time_h = verified_at
        self.finished = True
        complete_cause_set = set(self.case["causes"]) <= set(hypotheses)
        result = {"action_id": action_id, "intervention_time_h": decision,
                  "verification_available_at_h": verified_at,
                  "outcome": scored,
                  "verified_process_constraint_resolution_h": verified_at-6. if scored["feasible_full_batch"] else None,
                  "authored_cause_set_covered": complete_cause_set,
                  "synthetic_measurement_rounds": len(self.events),
                  "synthetic_human_work_minutes": self.human_work_minutes,
                  "observed_engineer_time_saved": None,
                  "real_manufacturing_action_executed": False,
                  "post_action_observations": [r for r in observed if decision <= r["time_h"] <= finish],
                  "limitation": "Whole-batch synthetic constraint verification; not validated root-cause correction or repair of sensor hardware."}
        self.events.append({"committed_action": action_id, "intervention_time_h": decision,
                            "verification_available_at_h": verified_at})
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    staging = sub.add_parser("stage")
    scoring = sub.add_parser("score")
    for command in (staging, scoring):
        command.add_argument("--dataset", required=True, type=Path)
        command.add_argument("--case", required=True)
        command.add_argument("--task", choices=("diagnosis", "optimization", "resolution", "pretransfer"), required=True)
    staging.add_argument("--arm", choices=("A", "B"), required=True)
    staging.add_argument("--output", required=True, type=Path)
    scoring.add_argument("--submission", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "stage":
        value = stage(args.dataset, args.case, args.task, args.arm, args.output)
    else:
        value = score_submission(args.dataset, args.case, args.task, json.loads(args.submission.read_text()))
    print(json.dumps(value, indent=2, allow_nan=False))
