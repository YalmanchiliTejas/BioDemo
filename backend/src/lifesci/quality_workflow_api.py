"""Typed, role-enforced local quality workspace HTTP surface."""
from __future__ import annotations

from typing import Any
from fastapi import Depends, Header, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ConfigDict


class CreateWorkspace(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str | None = None
    expected_case_revision: int | None = Field(default=None, ge=1)
    site_id: str
    title: str
    owner_id: str
    qa_reviewer_id: str
    associations: dict[str, Any] = Field(default_factory=dict)
    discovery_refs: list[dict[str, Any]] = Field(default_factory=list)
    category: str = 'process_excursion'
    priority: str = 'normal'
    initial_risk: str = ''
    deadline: str | None = None
    external_reference: str | None = None


class RevisionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)


class PrepareIn(RevisionIn):
    queued: bool = False


class ScienceIn(RevisionIn):
    queued: bool = False
    configuration_ids: list[str] | None = None


class AssessmentIn(RevisionIn):
    assessment: dict[str, Any]


class HypothesisIn(RevisionIn):
    hypothesis: dict[str, Any]


class EvidenceRequestIn(RevisionIn):
    request: dict[str, Any]


class ActionIn(RevisionIn):
    action: dict[str, Any]


class TransitionIn(RevisionIn):
    transition: str
    reason: str = Field(min_length=1)
    external_reference: str | None = None


def install_quality_workflow_api(p, app, ctx_dep):
    prefix = '/v1/quality/workspaces'

    @app.get(prefix)
    def workspaces(limit: int = Query(100, ge=1, le=200), ctx=Depends(ctx_dep)):
        return p.quality_workflow.list(ctx, limit)

    @app.post(prefix)
    def create(body: CreateWorkspace, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        return p.quality_workflow.create(ctx, **body.model_dump(), idempotency_key=key)

    @app.get(prefix + '/assignees')
    def assignees(site_id: str, ctx=Depends(ctx_dep)):
        return p.quality_workflow.assignees(ctx, site_id)

    @app.get(prefix + '/{case_id}')
    def workspace(case_id: str, ctx=Depends(ctx_dep)):
        return p.quality_workflow.get(ctx, case_id)

    @app.get(prefix + '/{case_id}/adoption-context')
    def adoption_context(case_id: str, ctx=Depends(ctx_dep)):
        return p.quality_workflow.adoption_context(ctx, case_id)

    @app.post(prefix + '/{case_id}/prepare')
    def prepare(case_id: str, body: PrepareIn, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        return p.quality_workflow.prepare(ctx, case_id, **body.model_dump(), idempotency_key=key)

    @app.get(prefix + '/{case_id}/science/catalog')
    def science_catalog(case_id: str, ctx=Depends(ctx_dep)):
        return p.case_science.catalog(ctx,case_id)

    @app.post(prefix + '/{case_id}/science/analyze')
    def science_analyze(case_id: str, body: ScienceIn, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        values=body.model_dump()
        queued=values.pop('queued')
        operation=p.case_science.queue if queued else p.case_science.analyze
        return operation(ctx,case_id,**values,idempotency_key=key)

    @app.post(prefix + '/{case_id}/assessment')
    def assessment(case_id: str, body: AssessmentIn, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        return p.quality_workflow.assessment(ctx, case_id, **body.model_dump(), idempotency_key=key)

    @app.post(prefix + '/{case_id}/hypotheses')
    def hypotheses(case_id: str, body: HypothesisIn, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        return p.quality_workflow.hypotheses(ctx, case_id, **body.model_dump(), idempotency_key=key)

    @app.post(prefix + '/{case_id}/evidence-requests')
    def requests(case_id: str, body: EvidenceRequestIn, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        return p.quality_workflow.evidence_request(ctx, case_id, **body.model_dump(), idempotency_key=key)

    @app.post(prefix + '/{case_id}/actions')
    def actions(case_id: str, body: ActionIn, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        return p.quality_workflow.action(ctx, case_id, **body.model_dump(), idempotency_key=key)

    @app.post(prefix + '/{case_id}/transition')
    def transition(case_id: str, body: TransitionIn, ctx=Depends(ctx_dep), key: str = Header(..., alias='Idempotency-Key')):
        return p.quality_workflow.transition(ctx, case_id, **body.model_dump(), idempotency_key=key)

    @app.get(prefix + '/{case_id}/export')
    def export(case_id: str, format: str = 'json', ctx=Depends(ctx_dep)):
        package = p.quality_workflow.export(ctx, case_id, format)
        return HTMLResponse(package) if format == 'html' else package

    @app.get(prefix + '/{case_id}/evidence/{kind}/{source_id:path}')
    def evidence(case_id: str, kind: str, source_id: str, revision: int = Query(..., ge=1), ctx=Depends(ctx_dep)):
        return p.quality_workflow.source(ctx, case_id, kind, source_id, revision=revision)
