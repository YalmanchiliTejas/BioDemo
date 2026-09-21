from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .campaign import CampaignDefinition, standard_campaign
from .controllers import TraditionalController
from .evaluation.metrics import calculate_metrics
from .factory import DeterministicProcessModel, FactoryState, build_factory
from .models import BatchState, EventRecord, Investigation, ResponsePlan, Scenario
from .scenarios import ScenarioManifest, build_scenario_manifest
from .systems import SystemRegistry


@dataclass
class RunResult:
    metrics: dict[str, Any]
    events: list[EventRecord]
    output_dir: Path | None


class BenchmarkSimulation:
    start_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def __init__(self, seed: int = 20250921, mode: str = "traditional") -> None:
        if mode != "traditional":
            raise ValueError("Only the Traditional baseline is implemented in this milestone")
        self.seed = seed
        self.mode = mode
        self.campaign: CampaignDefinition = standard_campaign()
        self.manifest: ScenarioManifest = build_scenario_manifest(seed)
        self.process = DeterministicProcessModel(self.campaign.quality_limits)
        self.state: FactoryState = build_factory(self.campaign.batches)
        self.systems = SystemRegistry(self.state)
        self.controller = TraditionalController()
        self.events: list[EventRecord] = []
        self._scenario_by_hour = {s.trigger_hour: s for s in self.manifest.scenarios}
        self._qc_delays: dict[str, int] = {}
        self._pending_qms_closures: list[tuple[int, str]] = []
        self._pending_qms_opens: list[tuple[int, int, Scenario, str | None]] = []
        self._pending_responses: list[tuple[int, Scenario, ResponsePlan, str | None]] = []

    def _timestamp(self, hour: int) -> str:
        return (self.start_time + timedelta(hours=hour)).isoformat()

    def _log(
        self,
        event_failure: str,
        action: str,
        decision: str,
        *,
        tool: str | None = None,
        information: list[str] | None = None,
        approval: bool = False,
        time_h: float = 0,
        production: dict[str, Any] | None = None,
        quality: dict[str, Any] | None = None,
        scenario: Scenario | None = None,
    ) -> None:
        self.events.append(EventRecord(
            timestamp=self._timestamp(self.state.hour),
            plant_state=self.state.snapshot(),
            event_failure=event_failure,
            information_available=information or [],
            actor_agent_action=action,
            tool_used=tool,
            decision=decision,
            approval_required=approval,
            time_consumed_hours=time_h,
            production_impact=production or {"delay_hours": 0, "downtime_hours": 0},
            quality_impact=quality or {"yield_loss_fraction": 0, "batch_disposition": "none"},
            financial_impact={"status": "not_in_scope_milestone_1", "amount": None},
            scenario_id=scenario.scenario_id if scenario else None,
            ground_truth_cause=scenario.ground_truth_cause if scenario else None,
        ))

    def _resource_for(self, stage: str) -> str:
        return next(s.resource for s in self.process.stages if s.name == stage)

    def _target_batch(self, scenario: Scenario) -> BatchState | None:
        if scenario.target in self.state.batches:
            return self.state.batches[scenario.target]
        if scenario.target in self.state.materials:
            return next((b for b in self.state.batches.values() if b.material_lot_id == scenario.target and b.stage not in {"released", "rejected"}), None)
        if scenario.target in self.state.equipment:
            occupied = self.state.equipment[scenario.target].occupied_by
            if occupied:
                return self.state.batches[occupied]
        return next((b for b in self.state.batches.values() if b.stage not in {"scheduled", "released", "rejected"}), None)

    def _gather_information(self, scenario: Scenario, plan: ResponsePlan, batch: BatchState | None) -> list[str]:
        batch_id = batch.plan.batch_id if batch else None
        facts: list[str] = []
        for system in plan.systems:
            if system == "MES/eBR" and batch_id:
                facts.append(f"MES/eBR:{self.systems.mes.get_batch(batch_id)['stage']}")
            elif system == "Historian/SCADA" and batch_id:
                facts.append(f"Historian/SCADA:{len(self.systems.historian.get_process_history(batch_id))} points")
            elif system == "LIMS" and batch_id:
                facts.append(f"LIMS:{len(self.systems.lims.get_qc_results(batch_id))} samples")
            elif system == "QMS":
                facts.append(f"QMS:{len(self.systems.qms.get_prior_deviations(as_of_hour=self.state.hour))} visible deviations")
            elif system == "CMMS" and scenario.target in self.state.equipment:
                facts.append(f"CMMS:health={self.systems.cmms.get_equipment_history(scenario.target)['health']}")
            elif system == "ERP":
                lot_id = "BUF-001" if scenario.event_type == "compound_failure" else (scenario.target if scenario.target in self.state.materials else (batch.material_lot_id if batch else "RM-001"))
                facts.append(f"ERP:{lot_id}={self.systems.erp.get_material_lot(lot_id)['status']}")
            elif system == "Scheduler":
                facts.append(f"Scheduler:{len(self.systems.scheduler.get_schedule())} batches")
            elif system == "LMS":
                facts.append(f"LMS:{len(self.systems.lms.qualified_operators('upstream'))} upstream-qualified")
        return facts

    def _apply_scenario(self, scenario: Scenario) -> None:
        plan = self.controller.respond(scenario)
        batch = self._target_batch(scenario)
        batch_id = batch.plan.batch_id if batch else None
        self._record_observation(scenario, batch)
        total_response_h = plan.detection_delay_h + plan.diagnosis_delay_h + plan.intervention_delay_h
        closure_hour = self.state.hour + total_response_h + plan.closure_delay_h
        self._pending_qms_opens.append((self.state.hour + plan.detection_delay_h, closure_hour, scenario, batch_id))
        self._pending_responses.append((self.state.hour + total_response_h, scenario, plan, batch_id))
        self.state.investigations.append(Investigation(
            scenario.scenario_id,
            self.state.hour,
            self.state.hour + plan.detection_delay_h,
            self.state.hour + plan.detection_delay_h + plan.diagnosis_delay_h,
            self.state.hour + total_response_h,
            closure_hour,
            plan.engineer_hours,
            set(plan.systems),
        ))

        if scenario.event_type == "qc_delay" and batch_id:
            self._qc_delays[batch_id] = 30
            self.systems.lims.defer_results(batch_id, 30)
        if scenario.event_type == "oos" and batch_id:
            sample_id = self.systems.lims.request_qc_test(batch_id, "bioburden", self.state.hour, self.state.hour)
            self.systems.lims.set_result(sample_id, "OOS", self.state.hour)
        if scenario.target in self.state.equipment:
            asset = self.state.equipment[scenario.target]
            asset.health = max(0, asset.health - 0.25)
            if plan.equipment_downtime_h:
                asset.available = False
                asset.unavailable_until_hour = self.state.hour + total_response_h + plan.equipment_downtime_h
                self.systems.cmms.create_work_order(scenario.target, self.state.hour, scenario.severity, scenario.name)
        elif scenario.event_type == "compound_failure":
            asset = self.state.equipment["PUMP-01"]
            asset.available = False
            asset.unavailable_until_hour = self.state.hour + total_response_h + plan.equipment_downtime_h
            self.systems.cmms.create_work_order("PUMP-01", self.state.hour, "critical", scenario.name)

        if batch:
            batch.hold_until_hour = max(batch.hold_until_hour, self.state.hour + total_response_h + plan.batch_hold_h)
            batch.yield_fraction = max(0, batch.yield_fraction - plan.yield_loss)
        self._log(
            scenario.name,
            "Physical disturbance occurs; response is pending",
            "Traditional detection, investigation, and escalation are scheduled",
            tool=None,
            information=[f"Observed signal in {scenario.target}"],
            approval=False,
            time_h=0,
            production={"delay_hours": plan.batch_hold_h, "downtime_hours": plan.equipment_downtime_h},
            quality={"yield_loss_fraction": plan.yield_loss, "batch_disposition": "pending_review"},
            scenario=scenario,
        )

    def _perform_intervention(self, scenario: Scenario, plan: ResponsePlan, batch: BatchState | None) -> str:
        if scenario.event_type == "material_issue":
            replacement = next(
                (lot for lot in self.state.materials.values() if lot.lot_id != scenario.target and lot.status == "released" and lot.quantity >= 2),
                None,
            )
            if replacement is not None:
                for waiting in self.state.batches.values():
                    if waiting.material_lot_id == scenario.target and not waiting.material_consumed and waiting.stage == "scheduled":
                        waiting.material_lot_override = replacement.lot_id
                        waiting.hold_until_hour = max(waiting.hold_until_hour, self.state.hour + plan.batch_hold_h)
                        self.systems.scheduler.reschedule_batch(waiting.plan.batch_id, waiting.hold_until_hour, "manual material substitution")
        if scenario.event_type == "compound_failure":
            for waiting in self.state.batches.values():
                if waiting.buffer_lot_id == "BUF-001" and not waiting.buffer_consumed:
                    waiting.buffer_lot_override = "BUF-002"
                    waiting.hold_until_hour = max(waiting.hold_until_hour, self.state.hour + plan.batch_hold_h)
                    self.systems.scheduler.reschedule_batch(waiting.plan.batch_id, waiting.hold_until_hour, "manual buffer substitution")
        if batch is None:
            return "none"
        if scenario.event_type in {"schedule_delay", "operator_unavailable", "maintenance_conflict"}:
            self.systems.scheduler.reschedule_batch(batch.plan.batch_id, batch.hold_until_hour, scenario.name)
        if plan.rework_batch and not batch.reworked:
            batch.reworked = True
            self.state.reworked_batches += 1
        if plan.reject_batch and (scenario.event_type != "material_issue" or batch.material_consumed):
            if batch.stage in {s.name for s in self.process.stages} and batch.stage_remaining_h > 0:
                resource = self.state.equipment[self._resource_for(batch.stage)]
                if resource.occupied_by == batch.plan.batch_id:
                    resource.occupied_by = None
            batch.rejected = True
            batch.stage = "rejected"
            batch.stage_remaining_h = 0
            self.state.rejected_batches += 1
            return "rejected"
        return "rework" if plan.rework_batch else "continued"

    def _record_observation(self, scenario: Scenario, batch: BatchState | None) -> None:
        """Fault evidence is observable in its own record, not only in the scenario log."""
        batch_id = batch.plan.batch_id if batch else scenario.target
        observations = {
            "bioreactor_drift": ("BIOREACTOR-01", {"pH": 7.38, "DO_pct": 29.0, "temperature_C": 37.0}),
            "viability_decline": ("BIOREACTOR-01", {"viability_pct": 74.0, "pH": 7.0, "DO_pct": 43.0}),
            "chrom_pressure": ("CHROM-01", {"pressure_bar": 3.35, "flow_L_min": 1.6}),
            "equipment_failure": ("PUMP-01", {"pump_running": 0.0, "flow_L_min": 0.0}),
            "compound_failure": ("PUMP-01", {"pump_running": 0.0, "flow_L_min": 0.0}),
        }
        if scenario.event_type in observations:
            asset_id, signals = observations[scenario.event_type]
            self.systems.historian.record(self.state.hour, batch_id, signals, asset_id)

    def _release_gate(self, batch: BatchState) -> str | None:
        if batch.rejected:
            return "rejected batch"
        if self.state.materials[batch.material_lot_id].status != "released":
            return "material lot not released"
        if self.state.materials[batch.buffer_lot_id].status != "released":
            return "buffer lot not released"
        results = self.systems.lims.get_qc_results(batch.plan.batch_id)
        if not results or any(s["status"] != "complete" for s in results):
            return "QC result pending"
        if any(s["result"] != "pass" for s in results):
            return "QC result not passing"
        deviations = [
            d for d in self.systems.qms.deviations
            if d["batch_id"] == batch.plan.batch_id
            and (d["closed_hour"] is None or d["closed_hour"] > self.state.hour)
        ]
        if deviations:
            return "QA deviation review pending"
        return None

    def _release_batch(self, batch: BatchState) -> None:
        batch.stage = "released"
        batch.release_block_reason = None
        batch.released_hour = self.state.hour
        self._log(
            "batch_released", "QA releases batch",
            "Release after passing QC, released materials, and closed deviations",
            tool="MES/eBR + LIMS + ERP + QMS",
            information=[batch.plan.batch_id],
            quality={"yield_loss_fraction": round(0.90 - batch.yield_fraction, 4), "batch_disposition": "released"},
        )

    def _check_release_holds(self) -> None:
        for batch in self.state.batches.values():
            if batch.stage != "release_hold":
                continue
            reason = self._release_gate(batch)
            if reason is None:
                self._release_batch(batch)
            elif reason != batch.release_block_reason:
                batch.release_block_reason = reason
                self._log("batch_release_blocked", "QA holds batch", reason, tool="LIMS + ERP + QMS", information=[batch.plan.batch_id], approval=True)

    def _refresh_equipment(self) -> None:
        for asset in self.state.equipment.values():
            if not asset.available and self.state.hour >= asset.unavailable_until_hour:
                asset.available = True

    def _advance_active_batches(self) -> None:
        active_stages = {s.name for s in self.process.stages}
        for batch in self.state.batches.values():
            if batch.stage not in active_stages or batch.stage_remaining_h <= 0:
                continue
            resource = self.state.equipment[self._resource_for(batch.stage)]
            if self.state.hour < batch.hold_until_hour or not resource.available:
                continue
            batch.stage_remaining_h -= 1
            if batch.stage in {"upstream", "downstream"}:
                self.state.actual_production_h += 1
                signals = self.process.nominal_signals(batch.stage)
                if signals:
                    self.systems.historian.record(self.state.hour, batch.plan.batch_id, signals)
            if batch.stage_remaining_h == 0:
                resource.occupied_by = None
                completed_stage = batch.stage
                next_stage = self.process.complete_stage(batch)
                batch.stage = next_stage
                if completed_stage == "qc":
                    batch.qc_complete_hour = self.state.hour
                if next_stage == "released":
                    batch.stage = "release_hold"
                    self._check_release_holds()

    def _start_waiting_batches(self) -> None:
        for batch in self.state.batches.values():
            if batch.stage in {"released", "rejected", "release_hold"} or batch.stage_remaining_h > 0:
                continue
            if batch.stage == "scheduled":
                if self.state.hour < max(batch.plan.planned_start_hour, batch.hold_until_hour):
                    continue
                lot = self.state.materials[batch.material_lot_id]
                if lot.status != "released" or lot.quantity < 1.0:
                    continue
                stage = self.process.stages[0]
            else:
                if self.state.hour < batch.hold_until_hour:
                    continue
                stage = next(s for s in self.process.stages if s.name == batch.stage)
                if stage.name == "downstream":
                    buffer = self.state.materials[batch.buffer_lot_id]
                    if buffer.status != "released" or buffer.quantity < 1.0 or not self.state.equipment["PUMP-01"].available:
                        continue
            resource = self.state.equipment[stage.resource]
            if not resource.available or resource.occupied_by is not None:
                continue
            if self.systems.lms.allocate_operator(stage.name, batch.plan.batch_id, self.state.hour) is None:
                continue
            resource.occupied_by = batch.plan.batch_id
            batch.stage = stage.name
            batch.stage_remaining_h = stage.duration_h
            if batch.actual_start_hour is None:
                self.state.materials[batch.material_lot_id].quantity -= 1.0
                batch.material_consumed = True
                batch.actual_start_hour = self.state.hour
                self.systems.mes.record_operator_action(batch.plan.batch_id, self.state.hour, "batch started")
                self._log("batch_started", "Operator starts recipe", "Start when resource, material, and qualification checks pass", tool="MES/eBR + ERP + LMS", information=[batch.plan.batch_id, batch.material_lot_id])
            if stage.name == "qc":
                self.systems.lims.request_qc_test(batch.plan.batch_id, "release panel", self.state.hour, self.state.hour + stage.duration_h + self._qc_delays.get(batch.plan.batch_id, 0))
            if stage.name == "downstream" and not batch.buffer_consumed:
                self.state.materials[batch.buffer_lot_id].quantity -= 1.0
                batch.buffer_consumed = True

    def run(self, output_dir: Path | None = None) -> RunResult:
        for hour in range(self.campaign.duration_hours):
            self.state.hour = hour
            for open_hour, closure_hour, scenario, batch_id in self._pending_qms_opens:
                if open_hour == hour:
                    deviation_id = self.systems.qms.create_deviation(batch_id, scenario.scenario_id, hour, scenario.name)
                    self._pending_qms_closures.append((closure_hour, deviation_id))
                    self.state.deviations_opened += 1
                    if scenario.target in self.state.materials:
                        self.systems.erp.set_lot_status(scenario.target, "quarantined")
                    if scenario.event_type == "compound_failure":
                        self.systems.erp.set_lot_status("BUF-001", "quarantined")
                    self._log("deviation_opened", "QA opens deviation", "Detection and triage complete", tool="QMS", information=[deviation_id, scenario.scenario_id])
            for due_hour, deviation_id in self._pending_qms_closures:
                if due_hour == hour:
                    self.systems.qms.close_deviation(deviation_id, hour)
                    self.state.deviations_closed += 1
                    self._log("deviation_closed", "QA closes investigation", "Documented review and approval complete", tool="QMS", information=[deviation_id], approval=True)
            for response_hour, scenario, plan, batch_id in self._pending_responses:
                if response_hour == hour:
                    batch = self.state.batches.get(batch_id) if batch_id else None
                    facts = self._gather_information(scenario, plan, batch)
                    disposition = self._perform_intervention(scenario, plan, batch)
                    self._log(
                        "traditional_intervention", plan.action, plan.decision,
                        tool=" + ".join(plan.systems), information=facts,
                        approval=plan.approval_required,
                        time_h=plan.detection_delay_h + plan.diagnosis_delay_h + plan.intervention_delay_h,
                        production={"delay_hours": plan.batch_hold_h, "downtime_hours": plan.equipment_downtime_h},
                        quality={"yield_loss_fraction": plan.yield_loss, "batch_disposition": disposition},
                        scenario=scenario,
                    )
            self._refresh_equipment()
            self.state.unplanned_downtime_h += sum(
                not self.state.equipment[asset_id].available
                for asset_id in ("BIOREACTOR-01", "CHROM-01", "PUMP-01")
            )
            scenario = self._scenario_by_hour.get(hour)
            if scenario:
                self._apply_scenario(scenario)
            for sample in self.systems.lims.complete_due_tests(hour):
                self._log("qc_result_reported", "QC reports assay", sample["result"], tool="LIMS", information=[sample["sample_id"], sample["batch_id"]])
            self._advance_active_batches()
            self._check_release_holds()
            self._start_waiting_batches()

        metrics = calculate_metrics(self.state, self.systems, self.campaign.duration_hours, self.manifest.fingerprint)
        metrics["mode"] = self.mode
        metrics["seed"] = self.seed
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            campaign_payload = {
                "campaign": self.campaign.to_dict(),
                "scenario_manifest": self.manifest.to_dict(),
                "scenario_fingerprint": self.manifest.fingerprint,
                "controller_mode": self.mode,
            }
            (output_dir / "campaign.json").write_text(json.dumps(campaign_payload, indent=2, sort_keys=True) + "\n")
            (output_dir / "events.jsonl").write_text("".join(json.dumps(e.to_dict(), sort_keys=True) + "\n" for e in self.events))
            (output_dir / "summary.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
        return RunResult(metrics, self.events, output_dir)
