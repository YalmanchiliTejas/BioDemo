"""Authenticated additive API; no manufacturing dispatch endpoint."""
from typing import Literal

from fastapi import Depends, Header
from pydantic import BaseModel, ConfigDict, Field


class SimulationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audience: Literal["technology_transfer", "cdmo_operation"] = "technology_transfer"
    site_id: str = "NF1"
    shelf_c: float = Field(default=-24., ge=-28, le=-20)
    load_vials: int = Field(default=11000, ge=100, le=11000, strict=True)
    capacity_kg_h: float = Field(default=.65, ge=.1, le=2.)
    samples: int = Field(default=8, ge=2, le=32)
    seed: int = Field(default=2025, ge=0)
    measurements: list[dict] | None = Field(default=None, max_length=1000)
    cutoff_h: float = Field(default=6., ge=.5, le=12.)
    cdmo_future_shelf_c: float = Field(default=-14., ge=-24., le=-10.)


class RecommendationIn(BaseModel):
    owner_id: str = Field(min_length=1, max_length=100)


def install_process_api(p, app, ctx_dep, idempotent):
    @app.post("/v1/process-model/contexts")
    def context(body: SimulationIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, "process-input-context", body.model_dump(), lambda: p.process_models.context(ctx, **body.model_dump()))

    @app.post("/v1/process-model/runs")
    def run(body: SimulationIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, "process-model-run", body.model_dump(), lambda: p.process_models.run(ctx, **body.model_dump()))

    @app.get("/v1/process-model/runs/{run_id}")
    def get(run_id: str, ctx=Depends(ctx_dep)):
        return p.process_models.get(ctx, run_id)

    @app.post("/v1/process-model/runs/{run_id}/recommendation")
    def propose(run_id: str, body: RecommendationIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, f"process-model-propose:{run_id}", body.model_dump(), lambda: p.process_models.propose(ctx, run_id, owner_id=body.owner_id))
