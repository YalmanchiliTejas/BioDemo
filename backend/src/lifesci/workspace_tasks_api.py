"""One authenticated interface for direct work and saved responsibilities."""
from typing import Any

from fastapi import Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from .assistant_routines import AlarmIn, RoutineIn, RoutineUpdate, WorkRequestIn
from .workspace_tasks import TaskSpec
from .ids import content_hash


class RevisionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)


class ActivateIn(RevisionIn):
    acknowledge_inference: bool = False


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

    @app.post('/v1/workspace-tasks/run')
    def run_task(body: TaskSpec, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        result = idempotent(ctx, key, 'workspace-task', body.model_dump(), lambda: p.workspace_tasks.execute(ctx, body))
        # Even an idempotent response must recheck source permissions and freshness.
        return p.workspace_tasks.get(ctx, result['id'])

    @app.get('/v1/workspace-tasks/results/{result_id}')
    def task_result(result_id: str, ctx=Depends(ctx_dep)):
        return p.workspace_tasks.get(ctx, result_id)

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

    @app.post('/v1/assistant-alarms')
    def alarm(body: AlarmIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        result = command(ctx, key, 'assistant-alarm', body.model_dump(),
                         lambda: p.assistant_routines.raise_alarm(ctx, body.model_dump()))
        return p.assistant_routines.get_alarm(ctx, result['id'])
