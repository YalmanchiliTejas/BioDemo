"""A person's working file for one question: what they looked at, what they decided to do next, and where each
step stands.

Engineers and QA do not converse with their data. They consolidate it, see what is happening, decide the next steps
and act. A work plan keeps that sequence as one durable record instead of a chat transcript: the selection, the
results it produced, and the next steps, each linked to the result that prompted it and, where it became one, to the
proposal or request that carries it. Approval, dispatch and receipts stay with the action service; a step only
points at them and reports where they stand.

Private to its owner, like their task results.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .ids import iso, new_id, utc_now
from .memory import principal
from .store import ConflictError

KIND = 'work_plan'
StepKind = Literal['check', 'request', 'action', 'note']
StepStatus = Literal['open', 'done', 'dropped']


class PlanIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    site_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    selection: dict[str, Any] = Field(default_factory=dict)  # the deliveries, batches, parameter and window in view


class StepIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    kind: StepKind = 'check'
    text: str = Field(min_length=1, max_length=600)
    result_id: str | None = Field(default=None, max_length=200)   # the result that prompted this step
    basis: str | None = Field(default=None, max_length=600)       # the finding or hypothesis it answers, in words
    proposal_id: str | None = Field(default=None, max_length=200)
    work_request_id: str | None = Field(default=None, max_length=200)


class StepUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    status: StepStatus | None = None
    text: str | None = Field(default=None, min_length=1, max_length=600)
    outcome: str | None = Field(default=None, max_length=600)    # what happened when it was done
    proposal_id: str | None = Field(default=None, max_length=200)
    work_request_id: str | None = Field(default=None, max_length=200)


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: Literal['open', 'closed'] | None = None
    selection: dict[str, Any] | None = None
    add_result_id: str | None = Field(default=None, max_length=200)


class WorkPlanService:
    def __init__(self, platform):
        self.p = platform

    def _record(self, ctx, plan_id, tx=None):
        rec = (tx or self.p.store.read()).require(ctx.tenant_id, KIND, plan_id)
        self.p.identity.require(ctx, 'read', KIND, plan_id, site_id=rec.state['site_id'], tx=tx)
        self.p.memory.require_record(ctx, KIND, rec.state)
        return rec

    def _own(self, ctx, plan_id, expected_revision, tx):
        rec = self._record(ctx, plan_id, tx)
        if rec.state['owner_id'] != principal(ctx):
            raise PermissionError('only the owner changes a work plan')
        if rec.revision != expected_revision:
            raise ConflictError('the plan changed; refresh before editing')
        return rec

    def _result(self, ctx, plan, result_id):
        """A result joins a plan only if this person can read it now and it belongs to the same site."""
        result = self.p.workspace_tasks.get(ctx, result_id)
        if result['site_id'] != plan['site_id']:
            raise PermissionError('the result belongs to another site')
        return result

    def create(self, ctx, request):
        body = PlanIn.model_validate(request)
        self.p.identity.require(ctx, 'propose', KIND, site_id=body.site_id)
        plan_id, now = new_id('plan'), iso(utc_now())
        state = {'id': plan_id, 'site_id': body.site_id, 'owner_id': principal(ctx), 'title': body.title,
                 'selection': body.selection, 'result_ids': [], 'steps': [], 'status': 'open',
                 'created_at': now, 'updated_at': now}
        with self.p.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, KIND, plan_id, state, expected_revision=None, action='create_work_plan',
                   event_type='work_plan.created', event_payload={'id': plan_id, 'site_id': body.site_id})
        return self.get(ctx, plan_id)

    def list(self, ctx, site_id):
        self.p.identity.require(ctx, 'read', KIND, site_id=site_id)
        out = []
        me = principal(ctx)
        # ponytail: filters the tenant's plans; declare a site index for work_plan when people keep hundreds.
        for rec in self.p.store.read().list(ctx.tenant_id, KIND, lambda st: st.get('site_id') == site_id and st.get('owner_id') == me):
            if rec.state['owner_id'] == me:
                steps = rec.state['steps']
                out.append({k: rec.state[k] for k in ('id', 'title', 'status', 'site_id', 'created_at', 'updated_at')}
                           | {'revision': rec.revision, 'results': len(rec.state['result_ids']),
                              'open_steps': sum(s['status'] == 'open' for s in steps), 'steps': len(steps)})
        return sorted(out, key=lambda plan: plan['updated_at'], reverse=True)

    def get(self, ctx, plan_id):
        rec = self._record(ctx, plan_id)
        state, tx = rec.state, self.p.store.read()
        from .worklist import Names
        names = Names(self.p.store, ctx.tenant_id, principal(ctx))
        steps = []
        for step in state['steps']:
            view = dict(step)
            # Where the linked proposal or request stands now, read from its own record: the step never copies it.
            if step.get('proposal_id'):
                proposal = tx.get(ctx.tenant_id, 'proposal', step['proposal_id'])
                readable = proposal is not None and self.p.identity.check(
                    ctx, 'read', 'proposal', proposal.id, site_id=proposal.state.get('site_id'))
                view['proposal'] = ({k: proposal.state.get(k) for k in ('operation', 'target_id', 'status', 'execution_status',
                                                                         'effectiveness', 'required_roles', 'risk', 'constraints')}
                                    if readable else {'status': 'not_available'})
            if step.get('work_request_id'):
                request = tx.get(ctx.tenant_id, 'assistant_work_request', step['work_request_id'])
                view['request'] = ({k: request.state.get(k) for k in ('title', 'owner_id', 'reply', 'answered_at')}
                                   | {'status': request.state.get('status', 'open'), 'owner_name': names(request.state.get('owner_id'))}
                                   if request else {'status': 'not_available'})
            view['stands'] = self._stands(view)
            # A step that carries a proposal is finished by the proposal's own outcome, never by ticking it off.
            view['waiting_on'] = ('approval' if view['stands'] == 'waiting for approval' else
                                  'execution' if view['stands'].startswith('approved') else
                                  'reply' if view['stands'] == 'waiting for a reply' else None)
            view['can_complete'] = step['status'] == 'open' and view['waiting_on'] in (None, 'reply')
            steps.append(view)
        results = []
        for result_id in state['result_ids']:
            try:
                r = self.p.workspace_tasks.get(ctx, result_id)
                results.append({k: r.get(k) for k in ('id', 'operation', 'summary', 'task_status', 'status', 'work_status',
                                                      'evidence_state', 'created_at')})
            except (PermissionError, ValueError, KeyError, LookupError):
                results.append({'id': result_id, 'status': 'not_available'})
        return {**state, 'revision': rec.revision, 'steps': steps, 'results': results,
                'progress': {'open': sum(s['status'] == 'open' for s in steps), 'done': sum(s['status'] == 'done' for s in steps),
                             'to_do': sum(s['stands'] == 'to do' for s in steps),
                             'waiting_for_approval': sum(s['stands'] == 'waiting for approval' for s in steps),
                             'waiting_for_reply': sum(s['stands'] == 'waiting for a reply' for s in steps)}}

    @staticmethod
    def _stands(step):
        if step['status'] != 'open':
            return step['status']
        proposal = step.get('proposal') or {}
        if proposal.get('status') == 'proposed':
            return 'waiting for approval'
        if proposal.get('status') == 'approved':
            return 'approved, not yet carried out' if proposal.get('execution_status') in (None, 'not_started', 'queued') \
                else f"approved · {str(proposal.get('execution_status')).replace('_', ' ')}"
        if proposal.get('status') in ('rejected', 'stale', 'withdrawn'):
            return f"proposal {proposal['status']}"
        if step.get('request'):
            # A reply ends the wait; the step's owner still reads it and closes the step with what came of it.
            return 'reply received' if step['request'].get('status') == 'answered' else 'waiting for a reply'
        return 'to do'

    def update(self, ctx, plan_id, request):
        body = PlanUpdate.model_validate(request)
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = self._own(ctx, plan_id, body.expected_revision, tx)
            state = dict(rec.state)
            if body.add_result_id:
                self._result(ctx, state, body.add_result_id)
                state['result_ids'] = list(dict.fromkeys([*state['result_ids'], body.add_result_id]))[-50:]
            for key in ('title', 'status', 'selection'):
                if getattr(body, key) is not None:
                    state[key] = getattr(body, key)
            state['updated_at'] = iso(utc_now())
            tx.put(ctx.tenant_id, KIND, plan_id, state, expected_revision=rec.revision, action='update_work_plan')
        return self.get(ctx, plan_id)

    def add_step(self, ctx, plan_id, request):
        body = StepIn.model_validate(request)
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = self._own(ctx, plan_id, body.expected_revision, tx)
            state = dict(rec.state)
            if len(state['steps']) >= 100:
                raise ValueError('a plan holds at most 100 steps; close it and start another')
            if body.result_id:
                self._result(ctx, state, body.result_id)
                state['result_ids'] = list(dict.fromkeys([*state['result_ids'], body.result_id]))[-50:]
            self._links(ctx, state, body.proposal_id, body.work_request_id, tx)
            step = {'step_id': new_id('step'), **body.model_dump(exclude={'expected_revision'}), 'status': 'open',
                    'added_by': ctx.actor_id, 'created_at': iso(utc_now()), 'done_at': None, 'outcome': None}
            state.update(steps=[*state['steps'], step], updated_at=iso(utc_now()))
            tx.put(ctx.tenant_id, KIND, plan_id, state, expected_revision=rec.revision, action='add_work_plan_step')
        return self.get(ctx, plan_id)

    def update_step(self, ctx, plan_id, step_id, request):
        body = StepUpdate.model_validate(request)
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = self._own(ctx, plan_id, body.expected_revision, tx)
            state = dict(rec.state)
            steps = [dict(s) for s in state['steps']]
            step = next((s for s in steps if s['step_id'] == step_id), None)
            if step is None:
                raise KeyError(step_id)
            self._links(ctx, state, body.proposal_id, body.work_request_id, tx)
            for key in ('text', 'outcome', 'proposal_id', 'work_request_id'):
                if getattr(body, key) is not None:
                    step[key] = getattr(body, key)
            if body.status is not None and body.status != step['status']:
                step['status'] = body.status
                step['done_at'] = iso(utc_now()) if body.status == 'done' else None
            state.update(steps=steps, updated_at=iso(utc_now()))
            tx.put(ctx.tenant_id, KIND, plan_id, state, expected_revision=rec.revision, action='update_work_plan_step')
        return self.get(ctx, plan_id)

    def _links(self, ctx, plan, proposal_id, work_request_id, tx):
        """A step may point only at a proposal or request this person can read at this site."""
        for kind, record_id in (('proposal', proposal_id), ('assistant_work_request', work_request_id)):
            if record_id:
                linked = tx.require(ctx.tenant_id, kind, record_id)
                if linked.state.get('site_id') != plan['site_id']:
                    raise PermissionError('the linked record belongs to another site')
                self.p.identity.require(ctx, 'read', kind, record_id, site_id=plan['site_id'], tx=tx)
