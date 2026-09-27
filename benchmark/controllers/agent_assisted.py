from __future__ import annotations

from benchmark.evaluation.rubric import EVIDENCE_REQUIREMENTS
from benchmark.models import ResponsePlan, Scenario


class AgentAssistedController:
    """Inspectable assumptions for a human-governed, agent-assisted workflow.

    This is an operating-model projection, not an LLM performance measurement.
    It keeps the same faults and physical interventions as the Traditional
    controller while changing information assembly and coordination delays.
    """

    mode = "agent_assisted"

    _impact: dict[str, dict] = {
        "bioreactor_drift": {"equipment_downtime_h": 4, "batch_hold_h": 14, "yield_loss": 0.08, "action": "Assemble trends and calibration history; propose bounded pH/DO correction"},
        "viability_decline": {"batch_hold_h": 18, "yield_loss": 0.12, "action": "Correlate viability, media genealogy, and hold time; propose harvest review"},
        "chrom_pressure": {"equipment_downtime_h": 18, "batch_hold_h": 14, "yield_loss": 0.04, "action": "Correlate pressure trend and maintenance history; propose column inspection"},
        "equipment_failure": {"equipment_downtime_h": 28, "batch_hold_h": 20, "yield_loss": 0.03, "action": "Build pump failure timeline; propose seal inspection and replacement"},
        "material_issue": {"batch_hold_h": 28, "reject_batch": True, "action": "Trace impacted genealogy; propose quarantine and released-lot substitution"},
        "qc_delay": {"batch_hold_h": 30, "action": "Identify queue constraint and propose prioritized QC review"},
        "oos": {"batch_hold_h": 52, "reject_batch": True, "action": "Assemble phase I/II OOS evidence and propose disposition review"},
        "schedule_delay": {"batch_hold_h": 12, "action": "Reconcile line-clearance evidence and propose schedule update"},
        "maintenance_conflict": {"equipment_downtime_h": 16, "batch_hold_h": 18, "action": "Detect schedule conflict and propose an approved maintenance window"},
        "operator_unavailable": {"batch_hold_h": 20, "action": "Find qualified available coverage and propose reassignment"},
        "recurring_deviation": {"batch_hold_h": 24, "yield_loss": 0.06, "action": "Link prior CAPA and current evidence; propose effectiveness review"},
        "compound_failure": {"equipment_downtime_h": 30, "batch_hold_h": 36, "rework_batch": True, "yield_loss": 0.10, "action": "Reconcile equipment and material evidence; propose containment and rework review"},
    }

    # Inferred conclusions are deliberately independent of Scenario.ground_truth_cause.
    _diagnoses = {
        "bioreactor_drift": "pH probe calibration bias caused base over-addition",
        "viability_decline": "media hold time reduced nutrient availability",
        "chrom_pressure": "column fouling increased backpressure",
        "equipment_failure": "seal wear caused pump trip",
        "material_issue": "supplier lot had out-of-spec osmolality",
        "qc_delay": "QC instrument queue exceeded capacity",
        "oos": "bioburden excursion during sampling",
        "schedule_delay": "manual line clearance completed late",
        "maintenance_conflict": "preventive maintenance was scheduled over processing",
        "operator_unavailable": "qualified operator called out with no planned backfill",
        "recurring_deviation": "prior filter setup CAPA was ineffective",
        "compound_failure": "pump cavitation coincided with a quarantined buffer lot",
    }

    def respond(self, scenario: Scenario) -> ResponsePlan:
        impact = self._impact[scenario.event_type]
        critical_extra = 2 if scenario.severity == "critical" else 0
        systems = EVIDENCE_REQUIREMENTS[scenario.event_type]
        return ResponsePlan(
            detection_delay_h=1,
            diagnosis_delay_h=4 + critical_extra,
            intervention_delay_h=2,
            closure_delay_h=36 + 2 * critical_extra,
            engineer_hours=4.0 + 0.6 * len(systems) + critical_extra / 2,
            systems=systems,
            action=impact["action"],
            decision="Prepare cited recommendation, challenge the hypothesis, obtain required human approval, then execute",
            approval_required=scenario.event_type not in {"qc_delay", "schedule_delay"},
            equipment_downtime_h=impact.get("equipment_downtime_h", 0),
            batch_hold_h=impact.get("batch_hold_h", 0),
            yield_loss=impact.get("yield_loss", 0.0),
            reject_batch=impact.get("reject_batch", False),
            rework_batch=impact.get("rework_batch", False),
            diagnosed_cause=self._diagnoses[scenario.event_type],
            evidence_cited=True,
            counterevidence_assessed=True,
            approval_compliant=True,
        )
