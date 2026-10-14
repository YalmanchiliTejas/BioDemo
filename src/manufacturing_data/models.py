from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

EntityKind = Literal["site", "process", "campaign", "batch", "run", "equipment", "sample", "document", "event", "deviation", "investigation", "maintenance"]
ValidationStatus = Literal["source_transcribed", "normalized", "ambiguous", "unverified", "rejected"]

class SourceRef(BaseModel):
    source_id: str
    path: str
    sheet: str | None = None
    row: int | None = None
    column: str | None = None
    cell: str | None = None
    page: int | None = None
    span: str | None = None
    region: tuple[float, float, float, float] | None = None

class Observation(BaseModel):
    observation_id: str
    source: SourceRef
    name: str
    value_text: str | None = None
    value_number: float | None = None
    unit: str | None = None
    occurred_at: str | None = None
    available_at: str | None = None
    entity_id: str | None = None
    entity_kind: EntityKind | None = None
    related_entities: list[tuple[EntityKind,str]] = Field(default_factory=list)
    validation_status: ValidationStatus = "source_transcribed"
    access_scope: str = "default"
    extraction_method: str
    confidence: float | None = Field(default=None, ge=0, le=1)

class ToolRequest(BaseModel):
    as_of: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["default"])
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    records: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
