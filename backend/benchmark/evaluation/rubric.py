from __future__ import annotations


# Controller-independent minimum evidence needed to support each investigation.
# These are benchmark assertions and must be reviewed against site procedures
# before the resulting scores are used outside this demonstration.
EVIDENCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "bioreactor_drift": ("Historian/SCADA", "MES/eBR", "QMS", "CMMS"),
    "viability_decline": ("LIMS", "Historian/SCADA", "MES/eBR", "ERP", "QMS"),
    "chrom_pressure": ("Historian/SCADA", "CMMS", "MES/eBR", "QMS"),
    "equipment_failure": ("Historian/SCADA", "CMMS", "MES/eBR", "Scheduler", "QMS"),
    "material_issue": ("ERP", "MES/eBR", "LIMS", "Scheduler", "QMS"),
    "qc_delay": ("LIMS", "Scheduler", "MES/eBR"),
    "oos": ("LIMS", "MES/eBR", "Historian/SCADA", "QMS"),
    "schedule_delay": ("MES/eBR", "Scheduler", "LMS"),
    "maintenance_conflict": ("CMMS", "Scheduler", "MES/eBR", "Historian/SCADA"),
    "operator_unavailable": ("LMS", "Scheduler", "MES/eBR"),
    "recurring_deviation": ("QMS", "MES/eBR", "Historian/SCADA"),
    "compound_failure": ("Historian/SCADA", "CMMS", "ERP", "MES/eBR", "Scheduler", "QMS"),
}
