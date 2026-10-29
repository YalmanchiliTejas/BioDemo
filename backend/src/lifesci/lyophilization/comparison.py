"""Frozen, honest comparison through the existing Prime adapter (no mock runs)."""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime
import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np

from ..gateway import TaskRequest
from ..ids import content_hash
from ..prime_adapter import PrimeInvestigationAdapter
from .reference import operation_config, reference
from .workflows import operations, visible_measurements


def public_packet(config, observations, cutoff_h):
    return {"config": deepcopy(config), "measurements": visible_measurements(observations, cutoff_h),
            "cutoff_h": cutoff_h, "observation_provenance": "synthetic_assumption",
            "rules": ["Critical interface temperature -28°C", "Complete primary drying before secondary drying",
                      "Respect characterized equipment vapor and condenser limits", "No release / rescue / real failure probability claim"]}


class ExistingPrimeRun:
    """Lazy construction lets existing route qualification fail before host setup.

    This is an adapter configuration, not a separate reasoning harness. All
    evidence/analysis and Python tools of Prime are preserved for BOTH arms.
    """
    model = None

    def __init__(self, p, ctx, packet, directory, protocol, arm):
        self.p, self.ctx, self.packet = p, ctx, packet
        self.directory, self.protocol, self.arm = directory, protocol, arm
        self.last_report = None

    def run(self, *, incident_id, problem, new_evidence_ids, as_of):
        from src.manufacturing_data import ManufacturingStore, ingest_package
        from src.prime_runtime.harness import PrimeManufacturingHarness
        from src.state import BlackboardStore
        from src.workflows import ManufacturingInvestigationWorkflow
        started = perf_counter()
        package = self.directory/"visible-inputs"
        package.mkdir(parents=True, exist_ok=True)
        (package/"process.json").write_text(json.dumps(self.packet["config"], indent=2))
        (package/"rules.txt").write_text("\n".join(self.packet["rules"])+"\nSynthetic reconstruction; no production authorization.\n")
        with (package/"observations.csv").open("w") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.packet["measurements"][0]))
            writer.writeheader(); writer.writerows(self.packet["measurements"])
        # Newly authored synthetic files use the benchmark's virtual calendar
        # cutoff, so ordinary retrieval does not hide them behind wall-clock
        # file creation time. No original source metadata is modified.
        stamp = datetime.fromisoformat(as_of).timestamp()
        for path in package.iterdir():
            os.utime(path, (stamp, stamp))
        store = ManufacturingStore(self.directory/"evidence-store")
        scope = "process-demonstration"
        ingestion = ingest_package(package, store, access_scope=scope)
        if ingestion["errors"]:
            raise RuntimeError("Prime evidence ingestion failed; comparison unavailable")
        boards = BlackboardStore(self.directory/"blackboards")
        workflow = ManufacturingInvestigationWorkflow(self.directory/"workflow", store, scope=scope, blackboards=boards)
        harness = PrimeManufacturingHarness.from_env(store=store, blackboards=boards, workflow=workflow, scope=scope)
        harness.model = self.model
        harness.max_tool_calls = self.protocol["budgets"]["tool_calls"]
        harness.execution_policy = {"mode": "fixed_v1"}
        harness.timeout_seconds = max(1., self.protocol["budgets"]["wall_clock_seconds"]-(perf_counter()-started))
        harness.evaluation_mode = True
        if self.arm == "B":
            # Host-owned inputs only; caller cannot select hidden scenarios or
            # bypass cutoff. Pure simulation adapters have no production writes.
            def forecast(*, shelf_temperature_c=None, as_of=None, scopes=None):
                config = deepcopy(self.packet["config"])
                if shelf_temperature_c is not None:
                    if shelf_temperature_c not in self.protocol["candidate_shelf_temperature_c"]:
                        raise ValueError("candidate outside frozen bounds")
                    cutoff = self.packet["cutoff_h"]
                    config["schedule"] = [s for s in config["schedule"] if s["time_h"] < cutoff]
                    config["schedule"].append({"time_h": cutoff, "shelf_temperature_c": shelf_temperature_c, "chamber_pressure_pa": 8.})
                result = self.p.gateway.run(TaskRequest("primary_drying_simulation", self.ctx, payload={"config": config}))
                return {"evidence_ids": [], "status": result.status, "prediction": result.output,
                        "provenance": "registered physical model; synthetic reconstructed inputs"}
            def optimize(*, as_of=None, scopes=None):
                result = self.p.gateway.run(TaskRequest("primary_drying_optimization", self.ctx,
                    payload={"config": self.packet["config"], "measurements": self.packet["measurements"], "cutoff_h": self.packet["cutoff_h"]}))
                return {"evidence_ids": [], "status": result.status, "prediction": result.output}
            harness.additional_tools = {"primary_drying_simulation": forecast, "primary_drying_optimization": optimize}
            problem += "\nAdditional host tools: primary_drying_simulation(shelf_temperature_c=None|-28|-24|-20), primary_drying_optimization(). Invoke using the existing bridge tool interface."
        self.last_report = harness.run(incident_id=incident_id, problem=problem, new_evidence_ids=[], as_of=as_of)
        return self.last_report


def attempt_agent(p, ctx, packet, directory, protocol, arm):
    directory.mkdir(parents=True, exist_ok=True)
    host = ExistingPrimeRun(p, ctx, packet, directory, protocol, arm)
    adapter = PrimeInvestigationAdapter(p.gateway, host, max_cost_usd=protocol["budgets"]["max_inference_cost_usd"])
    task = TaskRequest("investigation_planning", ctx, prompt=protocol["task"]+"\nEvidence packet:\n"+json.dumps(packet, sort_keys=True), use_cache=False)
    start = perf_counter()
    result = adapter.run(task, incident_id=f"lyo-{arm}", as_of="2026-10-26T06:00:00+00:00", evidence_ids=[])
    persisted = p.store.read().get(ctx.tenant_id, "model_run", result["run_id"])
    return {"arm": arm, "adapter_result": result, "runtime_seconds": perf_counter()-start,
            "packet_hash": content_hash(packet), "budgets": protocol["budgets"], "configured_model": host.model,
            "can_write_numerical_code": True, "existing_normal_tools_preserved": True,
            "gateway_record": persisted.state if persisted else None,
            "report": host.last_report, "measured_ai_performance": host.last_report is not None,
            "scientific_scores": None, "human_review_effort": None,
            "status_note": "No completed agent report means AI scientific performance is unavailable, not zero accuracy."}


def score(prediction, truth, cutoff_h):
    rows = prediction["trajectory"]
    actual = [r for r in truth["trajectory"] if cutoff_h < r["time_h"] <= 48. and r["active_max_temperature_c"] is not None]
    overlap = [r for r in actual if rows and rows[0]["time_h"] <= r["time_h"] <= rows[-1]["time_h"]]
    rmse = None
    if overlap:
        pred = np.interp([r["time_h"] for r in overlap], [r["time_h"] for r in rows], [r["interface_temperature_c"] for r in rows])
        rmse = float(np.sqrt(np.mean((pred-np.array([r["product_temperature_c"] for r in overlap]))**2)))
    detection = {}
    for kind, actual_key in [("critical_temperature", "first_critical_h"), ("vapor_capacity", "first_capacity_h")]:
        forecast = next((v["first_time_h"] for v in prediction["violations"] if v["constraint"] == kind), None)
        onset = truth[actual_key]
        confusion = "TP" if forecast is not None and onset is not None else "FP" if forecast is not None else "FN" if onset is not None else "TN"
        detection[kind] = {"detection": confusion, "predicted_onset_h": forecast, "reference_onset_h": onset,
                           "warning_lead_time_h": onset-cutoff_h if forecast is not None and onset is not None else None}
    end, observed_end = prediction["completion_time_h"], truth["completion_time_h"]
    return {"future_temperature_rmse_c": rmse, "overlap_points": len(overlap), "reference_future_points": len(actual),
            "coverage": len(overlap)/len(actual) if actual else None,
            "completion_absolute_error_h": abs(end-observed_end) if end is not None and observed_end is not None else None,
            "predicted_completion_h": end, "reference_completion_h": observed_end,
            "completion_censored": end is None or observed_end is None, "constraint_detection": detection,
            "reference_is_synthetic": True, "temperature_target": "mean thermometry; constraint target hottest active population"}


def compare(p, ctx, output: Path, protocol: dict):
    output.mkdir(parents=True, exist_ok=True)
    # Labels and shifts never enter public_packet or agent prompts.
    targets = [
        ("S01", "nominal", 1., 1., 1.),
        ("S02", "changed_heat_transfer", 1.25, 1., 1.),
        ("S03", "changed_product_resistance", 1., 1.4, 1.),
        ("S04", "reduced_vapor_capacity", 1., 1., .42),
    ]
    frozen_targets = [{"scenario": sid, "label": label, "kv_scale": kv, "rp_scale": rp, "capacity_scale": capacity}
                      for sid, label, kv, rp, capacity in targets]
    (output/"evaluation-only-targets.json").write_text(json.dumps(frozen_targets, indent=2)+"\n")
    protocol_hash, target_hash = content_hash(protocol), content_hash(frozen_targets)
    (output/"freeze-manifest.json").write_text(json.dumps({"protocol_sha256": protocol_hash, "targets_sha256": target_hash,
                                                        "frozen_before_solver_and_agent_runs": True}, indent=2)+"\n")
    cases = []
    for sid, label, kv, rp, cap in targets:
        config = operation_config()
        truth = reference(config, kv_scale=kv, rp_scale=rp, capacity_scale=cap)
        packet = public_packet(config, truth["trajectory"], protocol["cutoff_h"])
        (output/f"{sid}-agent-visible.json").write_text(json.dumps(packet, indent=2)+"\n")
        (output/f"{sid}-evaluation-only-reference.json").write_text(json.dumps(truth, indent=2)+"\n")
        start = perf_counter()
        physics = operations(config, packet["measurements"], cutoff_h=protocol["cutoff_h"])
        from ..science import detect_emerging_concern
        existing_analytics = detect_emerging_concern([r["product_temperature_c"] for r in packet["measurements"]],
            (None, config["product"]["critical_temperature_c"]), baseline_n=8)
        runtime = perf_counter()-start
        forecast = physics["options"][0]["result"]
        scores = score(forecast, truth, protocol["cutoff_h"])
        selected = physics["recommended_index"]
        intervention = None
        if selected is not None:
            candidate = physics["options"][selected]
            # Strip estimated Kv/Rp modifiers from candidate before evaluator uses
            # its withheld parameters: prediction's fit cannot redefine truth.
            candidate_config = deepcopy(candidate["config"])
            candidate_config["product"].pop("rp_scale", None)
            candidate_config["equipment"].pop("kv_scale", None)
            alternative = reference(candidate_config, kv_scale=kv, rp_scale=rp, capacity_scale=cap)
            intervention = {"selected": candidate["label"], "reference_completion_h": alternative["completion_time_h"],
                            "reference_critical_onset_h": alternative["first_critical_h"], "reference_capacity_onset_h": alternative["first_capacity_h"],
                            "feasible_in_reference": alternative["completion_time_h"] is not None and alternative["first_critical_h"] is None and alternative["first_capacity_h"] is None,
                            "completion_difference_h": alternative["completion_time_h"]-truth["completion_time_h"] if alternative["completion_time_h"] and truth["completion_time_h"] else None}
        agents = [attempt_agent(p, ctx, packet, output/sid/arm, protocol, arm) for arm in ("A", "B")]
        plausible = physics["diagnosis"]["plausible_temperature_explanations"]
        cases.append({"scenario": sid, "packet_hash": content_hash(packet), "existing_deterministic_analytics": existing_analytics, "physics_only": {"scores": scores,
            "runtime_seconds": runtime, "inference_cost_usd": 0., "tool_calls": 0, "analysis": physics,
            "diagnosis": {"plausible": plausible, "set_size": len(plausible),
                          "truth_in_plausible_set": label in plausible if label in ("changed_heat_transfer", "changed_product_resistance") else None,
                          "capacity_identifiability_abstention": all(h["estimate"] is None for h in physics["diagnosis"]["hypotheses"] if h["hypothesis"] == "reduced_vapor_capacity")},
            "intervention": intervention}, "agent_arms": agents})
    return {"protocol_hash": protocol_hash, "target_hash": target_hash, "cases": cases,
            "experimental_prediction_error": None, "human_review_effort": None,
            "conclusion_boundary": "Synthetic evaluation only. Unavailable AI arms cannot establish an AI performance uplift."}
