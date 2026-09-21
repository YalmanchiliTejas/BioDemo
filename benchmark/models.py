from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProcessLimits:
    ph_low: float = 6.8
    ph_high: float = 7.2
    do_low_pct: float = 35.0
    viability_low_pct: float = 80.0
    chromatography_pressure_high_bar: float = 3.0


@dataclass(frozen=True)
class BatchPlan:
    batch_id: str
    planned_start_hour: int
    target_kg: float = 2.0
    material_lot_id: str = "RM-001"


@dataclass
class BatchState:
    plan: BatchPlan
    stage: str = "scheduled"
    stage_remaining_h: int = 0
    actual_start_hour: int | None = None
    released_hour: int | None = None
    yield_fraction: float = 0.90
    hold_until_hour: int = 0
    rejected: bool = False
    reworked: bool = False


@dataclass
class Equipment:
    asset_id: str
    kind: str
    available: bool = True
    health: float = 1.0
    occupied_by: str | None = None
    unavailable_until_hour: int = 0


@dataclass
class MaterialLot:
    lot_id: str
    material: str
    quantity: float
    status: str = "released"


@dataclass
class Operator:
    operator_id: str
    qualifications: tuple[str, ...]
    available: bool = True


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    name: str
    trigger_hour: int
    event_type: str
    target: str
    ground_truth_cause: str
    severity: str
    seed: int


@dataclass
class EventRecord:
    timestamp: str
    plant_state: dict[str, Any]
    event_failure: str
    information_available: list[str]
    actor_agent_action: str
    tool_used: str | None
    decision: str
    approval_required: bool
    time_consumed_hours: float
    production_impact: dict[str, Any]
    quality_impact: dict[str, Any]
    financial_impact: dict[str, Any]
    scenario_id: str | None = None
    ground_truth_cause: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Investigation:
    scenario_id: str
    triggered_hour: int
    detected_hour: int
    diagnosed_hour: int
    intervention_hour: int
    closure_hour: int
    engineer_hours: float
    systems_accessed: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ResponsePlan:
    detection_delay_h: int
    diagnosis_delay_h: int
    intervention_delay_h: int
    closure_delay_h: int
    engineer_hours: float
    systems: tuple[str, ...]
    action: str
    decision: str
    approval_required: bool = True
    equipment_downtime_h: int = 0
    batch_hold_h: int = 0
    yield_loss: float = 0.0
    reject_batch: bool = False
    rework_batch: bool = False
