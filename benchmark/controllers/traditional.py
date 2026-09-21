from __future__ import annotations

from benchmark.models import ResponsePlan, Scenario


class TraditionalController:
    """Rule-based model of siloed systems and human coordination delays."""

    mode = "traditional"

    _specific: dict[str, dict] = {
        "bioreactor_drift": {"equipment_downtime_h": 4, "batch_hold_h": 14, "yield_loss": 0.08, "action": "MSAT reviews trends; operator manually corrects pH and DO"},
        "viability_decline": {"batch_hold_h": 18, "yield_loss": 0.12, "action": "MSAT compares batch record and media lot, then adjusts harvest timing"},
        "chrom_pressure": {"equipment_downtime_h": 18, "batch_hold_h": 14, "yield_loss": 0.04, "action": "Maintenance inspects skid and operations replaces fouled column"},
        "equipment_failure": {"equipment_downtime_h": 28, "batch_hold_h": 20, "yield_loss": 0.03, "action": "Maintenance diagnoses pump and expedites seal replacement"},
        "material_issue": {"batch_hold_h": 28, "reject_batch": True, "action": "Quality quarantines material and planning substitutes a released lot"},
        "qc_delay": {"batch_hold_h": 30, "action": "QA escalates overdue assay and QC manually reprioritizes queue"},
        "oos": {"batch_hold_h": 52, "reject_batch": True, "action": "QC and QA conduct phase I/II OOS investigation"},
        "schedule_delay": {"batch_hold_h": 12, "action": "Planner updates schedule after delayed line clearance"},
        "maintenance_conflict": {"equipment_downtime_h": 16, "batch_hold_h": 18, "action": "Operations and maintenance meet and manually move the work order"},
        "operator_unavailable": {"batch_hold_h": 20, "action": "Supervisor searches LMS and calls qualified operator for overtime"},
        "recurring_deviation": {"batch_hold_h": 24, "yield_loss": 0.06, "action": "QA opens a repeat deviation and MSAT re-investigates setup records"},
        "compound_failure": {"equipment_downtime_h": 30, "batch_hold_h": 36, "rework_batch": True, "yield_loss": 0.10, "action": "Separate maintenance and material investigations are reconciled in daily review"},
    }

    _systems: dict[str, tuple[str, ...]] = {
        "bioreactor_drift": ("Historian/SCADA", "MES/eBR", "QMS"),
        "viability_decline": ("LIMS", "Historian/SCADA", "MES/eBR", "ERP", "QMS"),
        "chrom_pressure": ("Historian/SCADA", "CMMS", "MES/eBR", "QMS"),
        "equipment_failure": ("CMMS", "MES/eBR", "Scheduler", "QMS"),
        "material_issue": ("ERP", "MES/eBR", "LIMS", "Scheduler", "QMS"),
        "qc_delay": ("LIMS", "Scheduler", "MES/eBR"),
        "oos": ("LIMS", "MES/eBR", "Historian/SCADA", "QMS"),
        "schedule_delay": ("MES/eBR", "Scheduler", "LMS"),
        "maintenance_conflict": ("CMMS", "Scheduler", "MES/eBR"),
        "operator_unavailable": ("LMS", "Scheduler", "MES/eBR"),
        "recurring_deviation": ("QMS", "MES/eBR", "Historian/SCADA"),
        "compound_failure": ("CMMS", "ERP", "MES/eBR", "Scheduler", "QMS"),
    }

    def respond(self, scenario: Scenario) -> ResponsePlan:
        impact = self._specific[scenario.event_type]
        critical_extra = 6 if scenario.severity == "critical" else 0
        return ResponsePlan(
            detection_delay_h=4,
            diagnosis_delay_h=12 + critical_extra,
            intervention_delay_h=8,
            closure_delay_h=72 + critical_extra,
            engineer_hours=9.0 + 1.75 * len(self._systems[scenario.event_type]) + critical_extra / 2,
            systems=self._systems[scenario.event_type],
            action=impact["action"],
            decision="Escalate through daily tier meeting, investigate, obtain QA approval, then execute",
            approval_required=scenario.event_type not in {"qc_delay", "schedule_delay"},
            equipment_downtime_h=impact.get("equipment_downtime_h", 0),
            batch_hold_h=impact.get("batch_hold_h", 0),
            yield_loss=impact.get("yield_loss", 0.0),
            reject_batch=impact.get("reject_batch", False),
            rework_batch=impact.get("rework_batch", False),
        )
