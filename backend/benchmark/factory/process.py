from __future__ import annotations

from dataclasses import dataclass

from benchmark.models import BatchState, ProcessLimits


@dataclass(frozen=True)
class StageDefinition:
    name: str
    duration_h: int
    resource: str


class DeterministicProcessModel:
    """Small process-layer adapter; replaceable by a mechanistic simulator later."""

    stages = (
        StageDefinition("upstream", 36, "BIOREACTOR-01"),
        StageDefinition("downstream", 18, "CHROM-01"),
        StageDefinition("qc", 12, "QC-LAB-01"),
        StageDefinition("release", 8, "RELEASE-DESK"),
    )

    def __init__(self, limits: ProcessLimits | None = None) -> None:
        self.limits = limits or ProcessLimits()

    def next_stage(self, current: str) -> StageDefinition | None:
        names = [stage.name for stage in self.stages]
        if current == "scheduled":
            return self.stages[0]
        if current not in names or current == names[-1]:
            return None
        return self.stages[names.index(current) + 1]

    def complete_stage(self, batch: BatchState) -> str:
        if batch.stage == "release":
            return "released"
        next_stage = self.next_stage(batch.stage)
        return next_stage.name if next_stage else batch.stage

    def nominal_signals(self, stage: str) -> dict[str, float]:
        if stage == "upstream":
            return {"pH": 7.0, "DO_pct": 45.0, "temperature_C": 37.0}
        if stage == "downstream":
            return {"pressure_bar": 1.8, "flow_L_min": 2.4}
        return {}

