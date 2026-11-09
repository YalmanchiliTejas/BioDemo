"""Explicit typed production API/tool payloads; no caller code/import paths."""

from typing import Any, Literal
from pydantic import AliasChoices, Field, model_validator
from .schemas import StrictModel


class Basis(StrictModel):
    kind: str = Field(min_length=1, max_length=100)
    id: str = Field(min_length=1, max_length=300)
    revision: int = Field(ge=1, strict=True)
    site_id: str = Field(min_length=1, max_length=100)


class ConfigurationIn(StrictModel):
    model_id: str = Field(min_length=1, max_length=100)
    site_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=3, max_length=200)
    config: dict[str, Any]
    basis: list[Basis] = Field(min_length=1, max_length=20)
    # JSON source paths make config/equipment/material/recipe values verifiable.
    source_path: str = Field(default="config", max_length=300)
    classification: Literal["measured_unverified", "published_characterization", "synthetic_assumption"]
    assumptions: list[str] = Field(default_factory=list, max_length=30)


class LibraryPipelineSpec(StrictModel):
    """Prepare bounded work on an EXISTING saved configuration. Read its record first, then copy its context ID; the server creates the plan and result IDs."""

    @model_validator(mode="before")
    @classmethod
    def one_context_identifier(cls, values):
        if isinstance(values, dict) and "context_id" in values and "simulation_id" in values:
            raise ValueError("Provide context_id (or the legacy simulation_id), never both")
        return values

    mode: Literal["model_library"] = "model_library"
    simulation_id: str = Field(min_length=1, max_length=200,
        validation_alias=AliasChoices("context_id", "simulation_id"),
        description="Exact existing physical_analysis_context record ID returned by catalogue discovery and read with model_library_read. Copy that ID unchanged. This is NOT a new simulation/run name; the server generates execution IDs.")
    model_id: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=8, max_length=4000)
    operation: Literal[
        "simulate",
        "compare",
        "fit",
        "sensitivity",
        "train_hybrid",
        "adapt_hybrid",
        "calibrate_intervals",
        "predict_intervals",
        "evaluate_intervals",
        "assess_transfer",
        "experiments",
    ]
    options: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str | None = Field(default=None, max_length=300, description="Optional existing physical_model_dataset ID containing partitioned measurement runs. Omit for a forward simulation. Never put a configuration ID here.")
    checkpoint_id: str | None = Field(default=None, max_length=300)
    calibration_id: str | None = Field(default=None, max_length=300)
    receiver_context_id: str | None = Field(default=None, max_length=300, description="Existing receiving-site configuration ID only for comparisons/adaptation. Omit for a single-source simulation; do not move the source context ID into this field.")
    max_solver_calls: int = Field(default=96, ge=1, le=512, strict=True)
    max_wall_seconds: float = Field(default=60.0, ge=1.0, le=180.0)


class DatasetIn(StrictModel):
    site_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=3, max_length=200)
    source: Basis
    source_path: str = Field(default="runs", max_length=300)
    site_holdout: bool = False


class LibraryPlanId(StrictModel):
    plan_id: str = Field(min_length=1, max_length=200)


class RefreshIn(StrictModel):
    context_id: str = Field(min_length=1, max_length=200)
    objective: str = Field(
        default="Reassess the affected configuration using its current evidence revision.",
        min_length=8,
        max_length=4000,
    )


class LibraryCatalogIn(StrictModel):
    model_id: str | None = None
    process_family: str | None = None


class LibraryReadIn(StrictModel):
    kind: Literal[
        "physical_analysis_context",
        "physical_model_dataset",
        "physical_analysis_plan",
        "physical_analysis_result",
        "physical_model_checkpoint",
        "physical_interval_calibration",
    ]
    record_id: str = Field(min_length=1, max_length=300)


class LibraryContextId(StrictModel):
    context_id: str = Field(min_length=1, max_length=300)


class ProposedParameter(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.]{1,99}$")
    unit: str = Field(min_length=1, max_length=60)
    lower_bound: float
    upper_bound: float
    identifying_measurement: str = Field(min_length=8, max_length=1000)

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.lower_bound >= self.upper_bound:
            raise ValueError("parameter lower bound must be below its upper bound")
        return self


class ModelExtensionIn(StrictModel):
    """A reviewable change to the physics of a REGISTERED model; never applied automatically."""

    context_id: str = Field(min_length=1, max_length=300)
    model_id: str = Field(min_length=1, max_length=100)
    basis: list[Basis] = Field(min_length=1, max_length=20)
    mechanism_change: str = Field(min_length=20, max_length=4000)
    affected_equations: str = Field(min_length=20, max_length=8000)
    new_parameters: list[ProposedParameter] = Field(default_factory=list, max_length=20)
    conservation_impact: str = Field(min_length=20, max_length=4000)
    limiting_case: str = Field(min_length=20, max_length=2000)
    verification_plan: str = Field(min_length=20, max_length=8000)
    owner_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct_parameters(self):
        names = [p.name for p in self.new_parameters]
        if len(set(names)) != len(names):
            raise ValueError("proposed parameter names must be distinct")
        return self
