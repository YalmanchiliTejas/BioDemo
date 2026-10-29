from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ModelChoice(StrictModel):
    model_id: str = Field(min_length=1, max_length=100)
    rationale: str = Field(min_length=8, max_length=2000)


class ThermalAssumptions(StrictModel):
    vial_heat_capacity_j_k: float = Field(ge=.1, le=100.)
    initial_temperature_c: float = Field(ge=-65., le=-1.)


class PipelineSpec(StrictModel):
    simulation_id: str = Field(min_length=1, max_length=100)
    candidate_index: int = Field(default=0, ge=0, le=10, strict=True)
    objective: str = Field(min_length=8, max_length=4000)
    models: list[ModelChoice] = Field(min_length=1, max_length=2)
    thermal_assumptions: ThermalAssumptions | None = None
    calibration: Literal["none", "kv_scale"] = "none"
    calibration_until_h: float = Field(default=3., ge=.1, le=24.)
    evidence_cutoff_h: float = Field(default=6., ge=.2, le=48.)
    temperature_observable: Literal["interface_temperature_c", "bottom_temperature_c"] = "interface_temperature_c"
    samples: int = Field(default=4, ge=0, le=16, strict=True)
    seed: int = Field(default=2025, ge=0, strict=True)
    max_solver_calls: int = Field(default=48, ge=2, le=64, strict=True)
    max_wall_seconds: float = Field(default=60., ge=1., le=120.)
    views: list[Literal["trajectories", "validation", "vial_3d"]] = Field(default_factory=lambda: ["trajectories", "validation", "vial_3d"], min_length=1, max_length=3)

    @model_validator(mode="after")
    def distinct_models_and_times(self):
        if len({m.model_id for m in self.models}) != len(self.models):
            raise ValueError("each model can appear only once")
        if len(set(self.views)) != len(self.views):
            raise ValueError("view requests must be distinct")
        if self.calibration_until_h >= self.evidence_cutoff_h:
            raise ValueError("calibration window must end before the evidence cutoff")
        if self.samples == 1:
            raise ValueError("request zero or at least two uncertainty samples")
        return self


class AgentPlanIn(StrictModel):
    simulation_id: str = Field(min_length=1, max_length=100)
    candidate_index: int = Field(default=0, ge=0, le=10)
    objective: str = Field(min_length=8, max_length=4000)
    thermal_assumptions: ThermalAssumptions | None = None


class ReviewIn(StrictModel):
    owner_id: str = Field(min_length=1, max_length=100)


class AdapterProposalIn(StrictModel):
    simulation_id: str = Field(min_length=1, max_length=100)
    model_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    title: str = Field(min_length=5, max_length=200)
    governing_equations: str = Field(min_length=20, max_length=8000)
    required_inputs_and_units: list[str] = Field(min_length=1, max_length=50)
    source_and_license: str = Field(min_length=10, max_length=4000)
    verification_and_validation_plan: str = Field(min_length=20, max_length=8000)
    intended_use_and_limits: str = Field(min_length=20, max_length=4000)
    owner_id: str = Field(min_length=1, max_length=100)
