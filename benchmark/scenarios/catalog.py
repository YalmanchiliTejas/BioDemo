from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass

from benchmark.models import Scenario


@dataclass(frozen=True)
class ScenarioManifest:
    campaign_seed: int
    scenarios: tuple[Scenario, ...]

    def to_dict(self) -> dict:
        return {"campaign_seed": self.campaign_seed, "scenarios": [asdict(s) for s in self.scenarios]}

    @property
    def fingerprint(self) -> str:
        payload = repr(self.to_dict()).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


def build_scenario_manifest(seed: int) -> ScenarioManifest:
    """Build the same fault schedule for every controller given a campaign seed."""
    rng = random.Random(seed)
    definitions = (
        ("S01", "Bioreactor pH/DO drift", 20, "bioreactor_drift", "BATCH-01", "pH probe calibration bias caused base over-addition", "major"),
        ("S02", "Declining cell viability", 72, "viability_decline", "BATCH-02", "media hold time reduced nutrient availability", "major"),
        ("S03", "Chromatography pressure increase", 148, "chrom_pressure", "CHROM-01", "column fouling increased backpressure", "major"),
        ("S04", "Transfer pump failure", 178, "equipment_failure", "PUMP-01", "seal wear caused pump trip", "critical"),
        ("S05", "Bad raw-material lot", 231, "material_issue", "RM-003", "supplier lot had out-of-spec osmolality", "critical"),
        ("S06", "QC result delayed", 278, "qc_delay", "BATCH-04", "QC instrument queue exceeded capacity", "moderate"),
        ("S07", "Out-of-specification result", 342, "oos", "BATCH-06", "bioburden excursion during sampling", "critical"),
        ("S08", "Batch starts 12 hours late", 376, "schedule_delay", "BATCH-08", "manual line clearance completed late", "moderate"),
        ("S09", "Maintenance conflicts with production", 451, "maintenance_conflict", "CHROM-01", "preventive maintenance was scheduled over processing", "major"),
        ("S10", "Qualified operator unavailable", 484, "operator_unavailable", "BATCH-10", "qualified operator called out with no planned backfill", "major"),
        ("S11", "Recurring deviation", 528, "recurring_deviation", "BATCH-10", "prior filter setup CAPA was ineffective", "major"),
        ("S12", "Simultaneous equipment and material problem", 570, "compound_failure", "BATCH-11", "pump cavitation coincided with a quarantined buffer lot", "critical"),
    )
    scenarios = tuple(
        Scenario(sid, name, base_hour + rng.randint(0, 2), event_type, target, cause, severity, seed + index)
        for index, (sid, name, base_hour, event_type, target, cause, severity) in enumerate(definitions, start=1)
    )
    return ScenarioManifest(seed, scenarios)
