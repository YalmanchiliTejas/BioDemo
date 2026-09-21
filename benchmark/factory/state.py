from __future__ import annotations

from dataclasses import dataclass, field

from benchmark.models import BatchPlan, BatchState, Equipment, MaterialLot, Operator


@dataclass
class FactoryState:
    hour: int
    batches: dict[str, BatchState]
    equipment: dict[str, Equipment]
    materials: dict[str, MaterialLot]
    operators: dict[str, Operator]
    unplanned_downtime_h: float = 0.0
    planned_production_h: float = 0.0
    actual_production_h: float = 0.0
    deviations_opened: int = 0
    deviations_closed: int = 0
    rejected_batches: int = 0
    reworked_batches: int = 0
    overtime_h: float = 0.0
    investigations: list = field(default_factory=list)

    def snapshot(self) -> dict:
        active = {bid: b.stage for bid, b in self.batches.items() if b.stage not in {"scheduled", "released", "rejected"}}
        return {
            "hour": self.hour,
            "active_batches": active,
            "released_batches": sum(b.stage == "released" for b in self.batches.values()),
            "open_deviations": self.deviations_opened - self.deviations_closed,
            "unavailable_assets": [a.asset_id for a in self.equipment.values() if not a.available],
        }


def build_factory(batch_plans: tuple[BatchPlan, ...]) -> FactoryState:
    assets = {
        "BIOREACTOR-01": Equipment("BIOREACTOR-01", "upstream bioreactor"),
        "CHROM-01": Equipment("CHROM-01", "chromatography skid"),
        "PUMP-01": Equipment("PUMP-01", "transfer pump"),
        "QC-LAB-01": Equipment("QC-LAB-01", "QC lab"),
        "RELEASE-DESK": Equipment("RELEASE-DESK", "batch release"),
    }
    materials = {
        f"RM-{i:03d}": MaterialLot(f"RM-{i:03d}", "cell culture media", 4.0)
        for i in range(1, 7)
    }
    materials.update({
        "BUF-000": MaterialLot("BUF-000", "purification buffer", 10.0),
        "BUF-001": MaterialLot("BUF-001", "purification buffer", 2.0),
        "BUF-002": MaterialLot("BUF-002", "purification buffer", 2.0),
    })
    operators = {
        "OP-01": Operator("OP-01", ("upstream",)),
        "OP-02": Operator("OP-02", ("downstream",)),
        "OP-03": Operator("OP-03", ("upstream", "downstream")),
        "QC-01": Operator("QC-01", ("qc",)),
        "QA-01": Operator("QA-01", ("release",)),
    }
    return FactoryState(0, {p.batch_id: BatchState(p) for p in batch_plans}, assets, materials, operators)
