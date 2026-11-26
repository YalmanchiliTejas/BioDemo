"""One authenticated interface for direct work and saved responsibilities."""
from typing import Any

from fastapi import Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from .assistant_routines import AlarmIn, RoutineIn, RoutineUpdate, WorkReplyIn, WorkRequestIn
from .workspace_tasks import TaskSpec
from .work_plans import PlanIn, PlanUpdate, StepIn, StepUpdate
from .ids import content_hash


class RevisionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)


class ActivateIn(RevisionIn):
    acknowledge_inference: bool = False


class RouteIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    site_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=2000)
    dataset_ids: list[str] = Field(default_factory=list, max_length=10)
    use_decision_model: bool = True
    # Deliveries still in review are matched only when the person has chosen to include them.
    include_unverified: bool = False


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selection: dict[str, Any]


class ProposeIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=2000)
    expected_result: str = Field(min_length=1, max_length=1000)
    target_system: str | None = Field(default=None, max_length=100)
    owner_id: str | None = Field(default=None, max_length=160)
    follow_up_measure: str | None = Field(default=None, max_length=600)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    payload: dict[str, Any] = Field(default_factory=dict)


class RequestEvidenceIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    owner_id: str = Field(min_length=1, max_length=160)
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    severity: str | None = Field(default=None, pattern='^(info|warning|critical)$')


class ExplainIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(default='', max_length=600)


class RunIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parameters: dict[str, Any] = Field(default_factory=dict)


def install_workspace_tasks_api(p, app, ctx_dep, idempotent):
    def command(ctx, key, route, body, run):
        # Store-only mutations and their replay receipts commit atomically.
        # Computation stays outside this lock so pause/revocation can interrupt it.
        with p.store.transaction(ctx.actor_id) as tx:
            if key:
                tx.lock_command(ctx.tenant_id, content_hash([ctx.actor_id, route, key]))
            return idempotent(ctx, key, route, body, run)

    @app.get('/v1/workspace-tasks/catalog')
    def catalog(ctx=Depends(ctx_dep)):
        return p.workspace_tasks.catalog()

    @app.post('/v1/workspace-tasks/route')
    def route_request(body: RouteIn, ctx=Depends(ctx_dep)):
        """Match typed words to one typed task, or say why the request belongs to the assistant. Runs nothing."""
        return p.workspace_tasks.route(ctx, body.site_id, body.text, dataset_ids=body.dataset_ids,
                                       use_decision_model=body.use_decision_model,
                                       include_unverified=body.include_unverified)

    @app.get('/v1/latency')
    def latency(prefix: str = '', ctx=Depends(ctx_dep)):
        """Recent server handling time per route, against the ten-second answer target."""
        return app.state.latency.summary(prefix)

    @app.post('/v1/workspace-tasks/run')
    def run_task(body: TaskSpec, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        result = idempotent(ctx, key, 'workspace-task', body.model_dump(), lambda: p.workspace_tasks.execute(ctx, body))
        # Even an idempotent response must recheck source permissions and freshness.
        return p.workspace_tasks.get(ctx, result['id'])

    @app.get('/v1/workspace-tasks/results/{result_id}')
    def task_result(result_id: str, ctx=Depends(ctx_dep)):
        return p.workspace_tasks.get(ctx, result_id)

    @app.get('/v1/workspace-tasks/templates')
    def templates(ctx=Depends(ctx_dep)):
        return {'templates': p.workspace_tasks.templates()}

    @app.post('/v1/workspace-tasks/templates/{template_id}/run')
    def run_template(template_id: str, body: TemplateIn, ctx=Depends(ctx_dep)):
        """Several tasks for one working question, run together through the flow runtime."""
        return p.workspace_tasks.run_template(ctx, template_id, body.selection)

    @app.post('/v1/workspace-tasks/templates/{template_id}/preview')
    def preview_template(template_id: str, body: TemplateIn, ctx=Depends(ctx_dep)):
        """The same tasks, calculated without saving: a picture that follows the selection as it changes."""
        return p.workspace_tasks.preview_template(ctx, template_id, body.selection)

    @app.post('/v1/workspace-tasks/preview')
    def preview_task(body: TaskSpec, ctx=Depends(ctx_dep)):
        """One task calculated without saving: for a lookup that should leave nothing behind."""
        return p.workspace_tasks.preview(ctx, body)

    @app.get('/v1/workspace-tasks/actions')
    def proposable_actions(ctx=Depends(ctx_dep)):
        return p.workspace_tasks.actions()

    @app.get('/v1/workspace-tasks/deliveries/{evidence_id}/profile')
    def delivery_profile(evidence_id: str, site_id: str, ctx=Depends(ctx_dep)):
        """What a delivery holds, per batch and parameter, calculated once per revision."""
        return p.workspace_tasks.profile(ctx, evidence_id, site_id)

    @app.post('/v1/workspace-tasks/results/{result_id}/propose', status_code=201)
    def propose_from_result(result_id: str, body: ProposeIn, ctx=Depends(ctx_dep),
                            key: str | None = Header(None, alias='Idempotency-Key')):
        """Draft an action for review from a result. Approval, dispatch and receipt stay with /v1/proposals."""
        return idempotent(ctx, key, f'task-proposal:{result_id}', body.model_dump(),
                          lambda: p.workspace_tasks.propose(ctx, result_id, body.model_dump()))

    @app.post('/v1/workspace-tasks/results/{result_id}/request-evidence', status_code=201)
    def request_evidence(result_id: str, body: RequestEvidenceIn, ctx=Depends(ctx_dep)):
        """Send the drafted request for missing evidence to a named person."""
        return p.workspace_tasks.request_evidence(ctx, result_id, body.model_dump(exclude_none=True))

    @app.post('/v1/workspace-tasks/results/{result_id}/explain')
    def explain_result(result_id: str, body: ExplainIn, ctx=Depends(ctx_dep)):
        """One bounded model explanation of a calculated result. Its numbers must all come from the result."""
        return p.workspace_tasks.explain(ctx, result_id, body.question)

    @app.get('/v1/work-plans')
    def work_plans(site_id: str, ctx=Depends(ctx_dep)):
        return {'plans': p.work_plans.list(ctx, site_id)}

    @app.post('/v1/work-plans', status_code=201)
    def create_work_plan(body: PlanIn, ctx=Depends(ctx_dep)):
        return p.work_plans.create(ctx, body.model_dump())

    @app.get('/v1/work-plans/{plan_id}')
    def work_plan(plan_id: str, ctx=Depends(ctx_dep)):
        return p.work_plans.get(ctx, plan_id)

    @app.post('/v1/work-plans/{plan_id}/update')
    def update_work_plan(plan_id: str, body: PlanUpdate, ctx=Depends(ctx_dep)):
        return p.work_plans.update(ctx, plan_id, body.model_dump(exclude_unset=True))

    @app.post('/v1/work-plans/{plan_id}/steps', status_code=201)
    def add_work_plan_step(plan_id: str, body: StepIn, ctx=Depends(ctx_dep)):
        return p.work_plans.add_step(ctx, plan_id, body.model_dump())

    @app.post('/v1/work-plans/{plan_id}/steps/{step_id}')
    def update_work_plan_step(plan_id: str, step_id: str, body: StepUpdate, ctx=Depends(ctx_dep)):
        return p.work_plans.update_step(ctx, plan_id, step_id, body.model_dump(exclude_unset=True))

    @app.get('/v1/assistant-routines')
    def routines(site_id: str | None = None, ctx=Depends(ctx_dep)):
        return {'routines': p.assistant_routines.list(ctx, site_id=site_id)}

    @app.post('/v1/assistant-routines')
    def create_routine(body: RoutineIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        result = command(ctx, key, 'assistant-routine', body.model_dump(), lambda: p.assistant_routines.create(ctx, body.model_dump()))
        return p.assistant_routines.get(ctx, result['id'])

    @app.get('/v1/assistant-routines/{routine_id}')
    def routine(routine_id: str, ctx=Depends(ctx_dep)):
        return p.assistant_routines.get(ctx, routine_id)

    @app.post('/v1/assistant-routines/{routine_id}/update')
    def update(routine_id: str, body: RoutineUpdate, ctx=Depends(ctx_dep)):
        return p.assistant_routines.update(ctx, routine_id, body.model_dump(exclude_unset=True))

    @app.post('/v1/assistant-routines/{routine_id}/activate')
    def activate(routine_id: str, body: ActivateIn, ctx=Depends(ctx_dep)):
        return p.assistant_routines.activate(ctx, routine_id, **body.model_dump())

    @app.post('/v1/assistant-routines/{routine_id}/pause')
    def pause(routine_id: str, body: RevisionIn, ctx=Depends(ctx_dep)):
        return p.assistant_routines.pause(ctx, routine_id, **body.model_dump())

    @app.post('/v1/assistant-routines/{routine_id}/run')
    def run_routine(routine_id: str, body: RunIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        result = idempotent(ctx, key, f'assistant-routine-run:{routine_id}', body.model_dump(),
                            lambda: p.assistant_routines.run(ctx, routine_id, body.parameters))
        return p.workspace_tasks.get(ctx, result['id'])

    @app.post('/v1/work-requests')
    def work_request(body: WorkRequestIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        result = command(ctx, key, 'assistant-work-request', body.model_dump(),
                            lambda: p.assistant_routines.create_work_request(ctx, body.model_dump()))
        return p.assistant_routines.get_work_request(ctx, result['id'])

    @app.get('/v1/work-requests/{request_id}')
    def get_work_request(request_id: str, ctx=Depends(ctx_dep)):
        return p.assistant_routines.get_work_request(ctx, request_id)

    @app.post('/v1/work-requests/{request_id}/answer')
    def answer_work_request(request_id: str, body: WorkReplyIn, ctx=Depends(ctx_dep)):
        """The person asked replies; the request then reads as answered for the person who sent it."""
        return p.assistant_routines.answer_work_request(ctx, request_id, body.model_dump())

    @app.post('/v1/assistant-alarms')
    def alarm(body: AlarmIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        result = command(ctx, key, 'assistant-alarm', body.model_dump(),
                         lambda: p.assistant_routines.raise_alarm(ctx, body.model_dump()))
        return p.assistant_routines.get_alarm(ctx, result['id'])
