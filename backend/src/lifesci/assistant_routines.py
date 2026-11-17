"""Named, owner-scoped deterministic work on the existing mission event pump.

Definitions are data. A draft grants no standing authority, and only its owner
can activate it. Routines do not add a scheduler, model, or external writer.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from .ids import content_hash, iso, new_id, utc_now
from .memory import principal
from .roles import agent_context_for
from .store import ConflictError, LeaseError
from .workspace_tasks import SourceRef, TaskSpec


KIND = 'assistant_routine'
RUN = 'assistant_routine_run'
Trigger = Literal['case', 'evidence', 'batch', 'sample', 'deviation', 'alarm', 'team_request']


class RoutineIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=2000)
    task: TaskSpec
    triggers: list[Trigger] = Field(default_factory=list, max_length=7)
    every_minutes: int | None = Field(default=None, ge=15, le=10080)
    max_runs: int = Field(default=3, ge=1, le=100)

    @field_validator('name')
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip():
            raise ValueError('routine name cannot be blank')
        return value.strip()


class RoutineUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    task: TaskSpec | None = None
    triggers: list[Trigger] | None = Field(default=None, max_length=7)
    every_minutes: int | None = Field(default=None, ge=15, le=10080)
    max_runs: int | None = Field(default=None, ge=1, le=100)


class AlarmIn(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=2000)
    site_id: str = Field(default='NF1', min_length=1, max_length=100)
    record_refs: list[SourceRef] = Field(min_length=1, max_length=50,
        validation_alias=AliasChoices('record_refs', 'source_refs'))
    severity: Literal['info', 'warning', 'critical'] = 'warning'
    request_key: str | None = Field(default=None, min_length=1, max_length=160)


class WorkReplyIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    reply: str = Field(min_length=1, max_length=2000)

    @field_validator('reply')
    @classmethod
    def says_something(cls, value):
        if not value.strip():
            raise ValueError('a reply cannot be blank')
        return value.strip()


class WorkRequestIn(AlarmIn):
    owner_id: str = Field(min_length=1, max_length=160)
    record_refs: list[SourceRef] = Field(default_factory=list, max_length=50,
        validation_alias=AliasChoices('record_refs', 'source_refs'))


class AssistantRoutineService:
    def __init__(self, platform):
        self.p = platform

    def _current_owner(self, ctx, site_id, *, action='read', tx=None):
        owner = self.p.identity.context_for(ctx.tenant_id, principal(ctx),
            actor_kind='person' if ctx.delegated_from else ctx.actor_kind,
            partner_org_id=ctx.partner_org_id)
        self.p.identity.require(ctx, action, KIND, site_id=site_id, tx=tx)
        self.p.identity.require(owner, action, KIND, site_id=site_id, tx=tx)
        return owner

    def _record(self, ctx, routine_id, tx=None, *, write=False):
        tx = tx or self.p.store.read()
        rec = tx.require(ctx.tenant_id, KIND, routine_id)
        self._current_owner(ctx, rec.state['site_id'], action='propose' if write else 'read', tx=tx)
        if principal(ctx) != rec.state['owner_id']:
            raise PermissionError('routines are private to their owner')
        return rec

    @staticmethod
    def _person(ctx):
        if ctx.actor_kind != 'person' or ctx.delegated_from:
            raise PermissionError('a person must activate or pause standing routine work')

    @staticmethod
    def _expected(rec, revision):
        if rec.revision != revision:
            raise ConflictError('routine changed; refresh before editing its standing authority')

    def create(self, ctx, request):
        request = RoutineIn.model_validate(request)
        owner = self._current_owner(ctx, request.task.site_id, action='propose')
        with self.p.store.transaction(ctx.actor_id) as tx:
            thread = self.p.engineering_conversations.create(owner, {'site_id': request.task.site_id})
            routine_id = new_id('routine')
            state = {**request.model_dump(mode='json'), 'id': routine_id,
                'site_id': request.task.site_id, 'owner_id': owner.actor_id,
                'created_by': ctx.actor_id, 'status': 'draft', 'definition_version': 1,
                'runs_admitted': 0, 'run_ids': [], 'latest_result_id': None,
                'thread_id': thread['id'], 'mission_id': thread['mission_id'],
                'created_at': iso(utc_now()), 'updated_at': iso(utc_now())}
            rec = tx.put(ctx.tenant_id, KIND, routine_id, state,
                expected_revision=None, action='draft_assistant_routine')
            self._sync_mission(owner, rec.state, tx)
        return self.get(ctx, routine_id)

    def list(self, ctx, site_id=None):
        rows = []
        for rec in self.p.store.read().list(ctx.tenant_id, KIND):
            if rec.state['owner_id'] != principal(ctx) or (site_id and rec.state['site_id'] != site_id):
                continue
            try:
                rows.append(self.get(ctx, rec.id))
            except PermissionError:
                continue
        return sorted(rows, key=lambda r: r['updated_at'], reverse=True)

    def get(self, ctx, routine_id):
        rec = self._record(ctx, routine_id)
        runs = []
        for run_id in rec.state['run_ids']:
            saved = self.p.store.read().require(ctx.tenant_id, RUN, run_id)
            run = {**saved.state, 'revision': saved.revision}
            # Receipts are operational history, not an alternate cache of source
            # values embedded in numerical warnings or exception messages.
            run['issues'] = self._issue_codes(run.get('issues', []))
            if run.get('result_id'):
                try:
                    run['result'] = self.p.workspace_tasks.get(ctx, run['result_id'])
                except (PermissionError, ValueError, KeyError):
                    run['result'] = None
                    run['basis_status'] = 'unavailable'
                    run['task'] = {k: run['task'][k] for k in ('operation', 'site_id')}
                    run['event_versions'] = {}
            runs.append(run)
        latest = next((r.get('result') for r in reversed(runs)
                       if r.get('result_id') == rec.state['latest_result_id']), None)
        return {**rec.state, 'revision': rec.revision, 'runs': runs, 'latest_result': latest}

    @staticmethod
    def _issue_codes(issues):
        messages = {
            'routine_cancelled': 'Routine stopped because its definition or current authority changed.',
            'source_limit_exceeded': 'Selected sources plus changed records exceed 100. Narrow the routine scope and retry.',
            'task_failed': 'The task could not complete. Inspect authorized sources and retry.',
        }
        codes = [str(issue.get('code', 'task_failed'))[:80] if isinstance(issue, dict) else 'task_failed'
            for issue in issues]
        return [{'code': code, **({'message': messages[code]} if code in messages else {})} for code in codes]

    def update(self, ctx, routine_id, request):
        request = RoutineUpdate.model_validate(request)
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = self._record(ctx, routine_id, tx, write=True)
            self._expected(rec, request.expected_revision)
            changes = request.model_dump(mode='json', exclude_unset=True, exclude={'expected_revision'})
            definition = RoutineIn.model_validate({**{k: rec.state[k] for k in RoutineIn.model_fields}, **changes})
            if definition.task.site_id != rec.state['site_id']:
                raise ValueError('routine site is immutable; create a routine for another site')
            state = {**rec.state, **definition.model_dump(mode='json'),
                'status': 'draft' if rec.state['status'] == 'draft' else 'paused',
                'definition_version': rec.state['definition_version'] + 1, 'updated_at': iso(utc_now())}
            saved = tx.put(ctx.tenant_id, KIND, routine_id, state,
                expected_revision=rec.revision, action='edit_assistant_routine')
            self._sync_mission(ctx, saved.state, tx)
        return self.get(ctx, routine_id)

    def activate(self, ctx, routine_id, *, expected_revision, acknowledge_inference):
        self._person(ctx)
        if not acknowledge_inference:
            raise ValueError('acknowledge the standing-work allowance before activation')
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = self._record(ctx, routine_id, tx, write=True)
            self._expected(rec, expected_revision)
            if not rec.state['triggers'] and not rec.state['every_minutes']:
                raise ValueError('select a trigger or schedule before activation')
            if rec.state['runs_admitted'] >= rec.state['max_runs']:
                raise ValueError('routine allowance exhausted; explicitly increase max_runs')
            state = {**rec.state, 'status': 'active', 'updated_at': iso(utc_now()),
                'definition_version': rec.state['definition_version'] + 1,
                'activated_by': ctx.actor_id, 'activated_at': iso(utc_now())}
            tx.put(ctx.tenant_id, KIND, routine_id, state, expected_revision=rec.revision,
                action='activate_assistant_routine')
            self._sync_mission(ctx, state, tx)
        return self.get(ctx, routine_id)

    def pause(self, ctx, routine_id, *, expected_revision):
        self._person(ctx)
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = self._record(ctx, routine_id, tx, write=True)
            self._expected(rec, expected_revision)
            state = {**rec.state, 'status': 'paused', 'updated_at': iso(utc_now()),
                'definition_version': rec.state['definition_version'] + 1}
            tx.put(ctx.tenant_id, KIND, routine_id, state, expected_revision=rec.revision,
                action='pause_assistant_routine')
            self._sync_mission(ctx, state, tx)
        return self.get(ctx, routine_id)

    def _sync_mission(self, ctx, state, tx):
        from .process_engineering.responsibilities import EVENT_TYPES
        mission = tx.require(ctx.tenant_id, 'mission', state['mission_id'])
        thread = tx.require(ctx.tenant_id, 'engineering_conversation', state['thread_id'])
        enabled = state['status'] == 'active'
        task = state['task']
        subjects = list(dict.fromkeys([*(r['id'] for r in task['record_refs']),
            *task['dataset_ids'], *task['batches'], *([task['record_id']] if task['record_id'] else [])]))
        config = {'enabled': enabled, 'routine_id': state['id'], 'thread_id': state['thread_id'],
            'task_kind': 'workspace_task', 'objective': state['description'] or state['name'],
            'kinds': state['triggers'], 'max_runs': state['max_runs'],
            'runs_admitted': state['runs_admitted'], 'every_minutes': state['every_minutes'],
            'definition_version': state['definition_version'], 'updated_at': iso(utc_now()),
            'billing': 'Direct routine work invokes no model. This allowance limits admitted background runs.'}
        subscriptions = []
        if enabled:
            for kind in state['triggers']:
                for event in EVENT_TYPES[kind]:
                    sub = {'type': event, 'site_id': state['site_id'], 'require_site': True,
                        'authorized_owner_id': state['owner_id'], 'subjects': subjects}
                    if kind == 'team_request':
                        sub['owner_id'] = state['owner_id']
                    subscriptions.append(sub)
        tx.put(ctx.tenant_id, 'mission', mission.id, {**mission.state,
            'assistant_responsibility': config, 'subscriptions': subscriptions,
            'obligations': [o for o in mission.state['obligations'] if o.get('task_kind') != 'assistant_follow_up'],
            'status': 'active' if enabled else 'blocked', 'status_reason': None if enabled else 'Routine is not active.',
            'objective': config['objective']}, expected_revision=mission.revision,
            action='configure_routine_responsibility')
        tx.put(ctx.tenant_id, 'engineering_conversation', thread.id,
            {**thread.state, 'responsibility': config, 'routine_id': state['id'],
             'title': state['name'][:90], 'title_set_by_owner': True},
            expected_revision=thread.revision, action='configure_routine_conversation')
        if enabled and state['every_minutes']:
            self.p.missions.add_obligation(ctx, mission.id, description=config['objective'],
                task_kind='assistant_follow_up', every_minutes=state['every_minutes'],
                due_at=iso(utc_now() + timedelta(minutes=state['every_minutes'])))

    def run(self, ctx, routine_id, parameters=None):
        """One explicit run never activates a draft or changes its standing scope."""
        rec = self._record(ctx, routine_id, write=True)
        parameters = dict(parameters or {})
        for key in ('operation', 'site_id'):
            if key in parameters and parameters[key] != rec.state['task'][key]:
                raise ValueError(f'routine {key} is immutable for a run')
        task = TaskSpec.model_validate({**rec.state['task'], **parameters}).model_dump(mode='json')
        run = self._admit(ctx, rec.state, task, [], {}, None)
        return self._execute_run(ctx, rec.state['id'], run['id'])

    def _admit(self, ctx, routine, task, event_ids, event_versions, activation):
        with self.p.store.transaction(ctx.actor_id) as tx:
            current = self._record(ctx, routine['id'], tx, write=True)
            if current.state['definition_version'] != routine['definition_version']:
                raise ConflictError('routine definition changed before admission')
            state = current.state
            if activation:
                tx.check_lease(ctx.tenant_id, 'mission', activation.mission_id, activation.worker_id, activation.token)
                mission = tx.require(ctx.tenant_id, 'mission', activation.mission_id)
                if state['status'] != 'active' or not mission.state['assistant_responsibility']['enabled']:
                    raise PermissionError('routine is no longer active')
                if state['runs_admitted'] >= state['max_runs']:
                    tx.put(ctx.tenant_id, KIND, current.id, {**state, 'status': 'paused', 'updated_at': iso(utc_now())},
                        expected_revision=current.revision, action='exhaust_routine_allowance')
                    tx.put(ctx.tenant_id, 'mission', mission.id,
                        {**mission.state, 'status': 'paused_budget', 'status_reason': 'Routine run allowance exhausted.'},
                        expected_revision=mission.revision, action='exhaust_routine_allowance')
                    return None
            run_id = new_id('routinerun')
            run = {'id': run_id, 'routine_id': current.id, 'site_id': state['site_id'],
                'owner_id': state['owner_id'], 'definition_version': state['definition_version'],
                'task': task, 'origin': 'background' if activation else 'manual',
                'status': 'running', 'event_ids': event_ids, 'event_versions': event_versions,
                'result_id': None, 'started_at': iso(utc_now()), 'finished_at': None, 'issues': []}
            if task['record_refs']:
                run['inputs'] = task['record_refs']
            tx.put(ctx.tenant_id, RUN, run_id, run, expected_revision=None, action='admit_routine_run')
            admitted = state['runs_admitted'] + int(activation is not None)
            tx.put(ctx.tenant_id, KIND, current.id,
                {**state, 'run_ids': [*state['run_ids'], run_id], 'runs_admitted': admitted,
                 'updated_at': iso(utc_now())}, expected_revision=current.revision, action='record_routine_admission')
            if activation:
                config = {**mission.state['assistant_responsibility'], 'runs_admitted': admitted}
                tx.put(ctx.tenant_id, 'mission', mission.id, {**mission.state, 'assistant_responsibility': config},
                    expected_revision=mission.revision, action='admit_deterministic_responsibility')
        return run

    def _execute_run(self, ctx, routine_id, run_id, activation=None, due=()):
        worker_id = new_id('routineworker')
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = self._record(ctx, routine_id, tx, write=True)
            run = tx.require(ctx.tenant_id, RUN, run_id)
            token = tx.acquire_lease(ctx.tenant_id, RUN, run_id, worker_id)

        def guard(tx):
            current = self._record(ctx, routine_id, tx, write=True)
            tx.check_lease(ctx.tenant_id, RUN, run_id, worker_id, token)
            if current.state['definition_version'] != run.state['definition_version']:
                raise ConflictError('routine was paused or edited while the task was running')
            if activation:
                tx.check_lease(ctx.tenant_id, 'mission', activation.mission_id, activation.worker_id, activation.token)
                mission = tx.require(ctx.tenant_id, 'mission', activation.mission_id)
                if (current.state['status'] != 'active' or mission.state['status'] != 'active'
                        or not mission.state['assistant_responsibility']['enabled']):
                    raise PermissionError('routine is no longer active')

        def finish(tx, result):
            guard(tx)
            saved_run = tx.require(ctx.tenant_id, RUN, run_id)
            current = tx.require(ctx.tenant_id, KIND, routine_id)
            result_record = tx.require(ctx.tenant_id, 'workspace_task_result', result['id'])
            tx.put(ctx.tenant_id, RUN, run_id, {**saved_run.state, 'result_id': result['id'],
                'status': result.get('task_status', 'completed'), 'finished_at': iso(utc_now()),
                'issues': self._issue_codes(result.get('issues', [])),
                'inputs': [{'kind': 'workspace_task_result', 'id': result['id'],
                    'revision': result_record.revision, 'site_id': current.state['site_id']}]},
                expected_revision=saved_run.revision,
                action='complete_routine_run')
            tx.put(ctx.tenant_id, KIND, routine_id,
                {**current.state, 'latest_result_id': result['id'], 'updated_at': iso(utc_now())},
                expected_revision=current.revision, action='publish_routine_result')
            if activation:
                for obligation in due:
                    timer_id = f"timer:{obligation['obligation_id']}:{obligation['due_at']}"
                    if timer_id in saved_run.state['event_ids']:
                        self.p.missions.complete_obligation(ctx, activation.mission_id, obligation['obligation_id'],
                            artifact_ref={'kind': 'workspace_task_result', 'id': result['id']}, coalesce_missed=True)

        try:
            # The result and its routine receipt commit together, so replay after a
            # process failure never needs another completed calculation.
            return self.p.workspace_tasks.execute(ctx, run.state['task'], commit_guard=guard, on_commit=finish)
        except (ValueError, KeyError, PermissionError, ConflictError, LeaseError) as exc:
            with self.p.store.transaction(ctx.actor_id) as tx:
                try:
                    tx.check_lease(ctx.tenant_id, RUN, run_id, worker_id, token)
                except LeaseError:
                    raise exc
                current = tx.require(ctx.tenant_id, RUN, run_id)
                failure = exc
                try:
                    guard(tx)
                except (PermissionError, ConflictError, LeaseError) as stopped:
                    failure = stopped
                cancelled = isinstance(failure, (PermissionError, ConflictError, LeaseError))
                issue = {'code': 'routine_cancelled' if cancelled else 'task_failed'}
                if not cancelled and len(run.state['task']['record_refs']) > 100:
                    issue = {'code': 'source_limit_exceeded'}
                tx.put(ctx.tenant_id, RUN, run_id,
                    {**current.state, 'status': 'cancelled' if cancelled else 'failed',
                     'finished_at': iso(utc_now()), 'issues': self._issue_codes([issue])},
                    expected_revision=current.revision, action='block_routine_run')
                if activation and not cancelled:
                    tx.check_lease(ctx.tenant_id, 'mission', activation.mission_id, activation.worker_id, activation.token)
                    mission = tx.require(ctx.tenant_id, 'mission', activation.mission_id)
                    obligations = []
                    for obligation in mission.state['obligations']:
                        timer_id = f"timer:{obligation['obligation_id']}:{obligation.get('due_at')}"
                        if timer_id in current.state['event_ids']:
                            obligation = {**obligation, 'runtime_status': 'blocked',
                                'runtime_issues': ['Routine failed; inspect its authorized inputs and retry.'],
                                'surfaced_due_at': obligation['due_at']}
                        obligations.append(obligation)
                    tx.put(ctx.tenant_id, 'mission', mission.id, {**mission.state, 'obligations': obligations},
                        expected_revision=mission.revision, action='surface_failed_routine_schedule')
            raise failure
        finally:
            with self.p.store.transaction(ctx.actor_id) as tx:
                try:
                    tx.check_lease(ctx.tenant_id, RUN, run_id, worker_id, token)
                except LeaseError:
                    pass
                else:
                    tx.expire_lease(ctx.tenant_id, RUN, run_id)

    def run_activation(self, ctx, activation):
        """Coalesce authorized changes and return IDs only after a durable outcome."""
        mission = self.p.missions.get(ctx, activation.mission_id)
        config = mission.get('assistant_responsibility') or {}
        if not config.get('enabled') or mission['status'] != 'active':
            return []
        owner = self.p.identity.context_for(ctx.tenant_id, mission['owner_id'])
        delegated = agent_context_for(owner, self.p.identity)
        routine = self._record(delegated, config['routine_id'], write=True).state
        if routine['status'] != 'active':
            return []
        due = [o for o in mission['obligations'] if o.get('task_kind') == 'assistant_follow_up'
            and o['status'] == 'open' and o.get('due_at') and o['due_at'] <= iso(utc_now())
            and o.get('surfaced_due_at') != o['due_at']]
        timer_ids = {f"timer:{o['obligation_id']}:{o['due_at']}" for o in due}
        pending = set(activation.pending_event_ids) | timer_ids
        if not pending:
            return []
        runs = [self.p.store.read().require(ctx.tenant_id, RUN, rid).state for rid in routine['run_ids']]
        terminal = [r for r in runs if r['status'] in ('completed', 'needs_information', 'failed')]
        consumed = pending.intersection(eid for r in terminal for eid in r['event_ids'])
        remaining = pending - consumed
        resumable = next((r for r in reversed(runs) if r['status'] == 'running'
            and set(r['event_ids']).intersection(remaining)
            and r['definition_version'] == routine['definition_version']), None)
        if resumable:
            self._execute_run(delegated, routine['id'], resumable['id'], activation, due)
            return sorted(consumed | set(resumable['event_ids']))
        requested_events = remaining - timer_ids
        events, found, cursor = [], set(), 0
        while requested_events - found:
            page = self.p.store.events_since(ctx.tenant_id, cursor, limit=1000)
            if not page:
                break
            for _, event in page:
                if event.event_id not in requested_events:
                    continue
                found.add(event.event_id)
                if not self.p.missions._subscribed(mission, event):
                    consumed.add(event.event_id)
                    continue
                key = f'{event.aggregate_kind}:{event.aggregate_id}'
                if any(r.get('event_versions', {}).get(key, 0) >= event.revision for r in terminal):
                    consumed.add(event.event_id)
                else:
                    events.append(event)
            cursor = page[-1][0]
        if requested_events - found:
            raise ValueError('Pending event history is incomplete; routine cannot acknowledge unseen events')
        newest = {}
        for event in events:
            key = (event.aggregate_kind, event.aggregate_id)
            if key not in newest or event.revision > newest[key].revision:
                newest[key] = event
        selected_keys = list(newest)[:50]
        selected = set(selected_keys)
        handled = {e.event_id for e in events if (e.aggregate_kind, e.aggregate_id) in selected}
        handled |= timer_ids - consumed
        if not handled:
            return sorted(consumed)
        event_refs, versions = [], {}
        for kind, rid in selected_keys:
            current = self.p.store.read().require(ctx.tenant_id, kind, rid)
            event_refs.append({'kind': kind, 'id': rid, 'revision': current.revision,
                'site_id': current.state.get('site_id')})
            versions[f'{kind}:{rid}'] = current.revision
        task = dict(routine['task'])
        if task['operation'] == 'review_changes':
            refs = {(r['kind'], r['id']): r for r in event_refs}
            for ref in task['record_refs']:
                refs.setdefault((ref['kind'], ref['id']), ref)
            task['record_refs'] = list(refs.values())
        # Validate the merged event envelope inside an admitted run. A larger
        # selection must produce an inspectable failure, never an endless retry
        # before a receipt exists. Changed records take precedence in limited views.
        run = self._admit(delegated, routine, task, sorted(handled), versions, activation)
        if run is None:
            return sorted(consumed)
        try:
            self._execute_run(delegated, routine['id'], run['id'], activation, due)
        except (ValueError, KeyError):
            # Invalid task/evidence is an inspectable failed run, not perpetual work.
            return sorted(consumed | handled)
        return sorted(consumed | handled)

    def _request_refs(self, ctx, site_id, refs, *, tx, action='propose'):
        owner = self._current_owner(ctx, site_id, action=action, tx=tx)
        if not refs:
            return []
        pinned = self.p.identity.validate_refs(owner, refs, tx=tx)
        for ref in pinned:
            source = tx.require(ctx.tenant_id, ref['kind'], ref['id'])
            if source.state.get('site_id') != site_id:
                raise PermissionError('request evidence must belong to the selected site')
            self.p.memory.require_record(owner, source.kind, source.state)
        return pinned

    def create_work_request(self, ctx, request):
        self._person(ctx)
        return self._create_source_event(ctx, WorkRequestIn.model_validate(request), 'assistant_work_request', 'work.requested')

    def raise_alarm(self, ctx, request):
        self._person(ctx)
        return self._create_source_event(ctx, AlarmIn.model_validate(request), 'assistant_alarm', 'alarm.raised')

    def _create_source_event(self, ctx, request, kind, event_type):
        body = request.model_dump(mode='json')
        with self.p.store.transaction(ctx.actor_id) as tx:
            refs = self._request_refs(ctx, request.site_id, body['record_refs'], tx=tx)
            if kind == 'assistant_work_request':
                owner = self.p.identity.context_for(ctx.tenant_id, request.owner_id)
                self.p.identity.require(owner, 'read', kind, site_id=request.site_id, tx=tx)
                for ref in refs:
                    source = tx.require(ctx.tenant_id, ref['kind'], ref['id'])
                    self.p.identity.require(owner, 'read', ref['kind'], ref['id'], site_id=request.site_id, tx=tx)
                    self.p.memory.require_record(owner, source.kind, source.state)
            key = body.get('request_key')
            rid = (kind + ':' + content_hash([principal(ctx), request.site_id, key])[:32]) if key else new_id(kind)
            existing = tx.get(ctx.tenant_id, kind, rid)
            fingerprint = content_hash(body)
            if existing:
                if existing.state['request_hash'] != fingerprint:
                    raise ConflictError('request_key was already used for different content')
                return {**existing.state, 'revision': existing.revision}
            state = {**body, 'id': rid, 'record_refs': refs, 'requested_by': principal(ctx),
                'request_hash': fingerprint, 'status': 'open', 'created_at': iso(utc_now())}
            if refs:
                state['inputs'] = refs
            rec = tx.put(ctx.tenant_id, kind, rid, state, expected_revision=None,
                action='record_team_request' if kind == 'assistant_work_request' else 'record_source_alarm',
                event_type=event_type, event_payload={'site_id': request.site_id, 'id': rid,
                    **({'owner_id': request.owner_id} if kind == 'assistant_work_request' else {})})
            for ref in refs:
                tx.add_edge(ctx.tenant_id, (ref['kind'], ref['id']), (kind, rid), 'request_source')
        if kind == 'assistant_work_request' and state['owner_id'] != state['requested_by']:
            self._tell(ctx.tenant_id, state['owner_id'], f'work-request:{rid}', 'work_request',
                       f"{state['requested_by']} asked you: {state['title']}")
        return {**rec.state, 'revision': rec.revision}

    def _tell(self, tenant_id, person, key, kind, title):
        """An in-app notice that something is waiting for this person. The request stands whether or not it is sent."""
        alerts = getattr(self.p, 'alerts', None)
        if alerts is not None:
            alerts.notify(tenant_id, person, key=key, kind=kind, title=title[:200], link='/dashboard/')

    def answer_work_request(self, ctx, request_id, request):
        """The person who was asked replies, once. The reply is recorded as their statement, with their name and the
        time; it is not verified evidence, and the request then reads as answered for both people."""
        if ctx.actor_kind != 'person' or ctx.delegated_from:
            raise PermissionError('a person answers a request addressed to them')
        body = WorkReplyIn.model_validate(request)
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, 'assistant_work_request', request_id)
            self._current_owner(ctx, rec.state['site_id'], tx=tx)
            if principal(ctx) != rec.state['owner_id']:
                raise PermissionError('only the person who was asked can answer this request')
            if rec.revision != body.expected_revision:
                raise ConflictError('the request changed; refresh before answering')
            if rec.state.get('status', 'open') != 'open':
                raise ValueError('this request was already answered')
            state = {**rec.state, 'status': 'answered', 'reply': body.reply, 'answered_by': principal(ctx),
                     'answered_at': iso(utc_now())}
            out = tx.put(ctx.tenant_id, 'assistant_work_request', request_id, state, expected_revision=rec.revision,
                         action='answer_team_request', event_type='work.answered',
                         event_payload={'site_id': state['site_id'], 'id': request_id, 'requested_by': state['requested_by']})
        if state['requested_by'] != state['owner_id']:
            self._tell(ctx.tenant_id, state['requested_by'], f'work-reply:{request_id}', 'work_reply',
                       f"{state['owner_id']} replied: {state['title']}")
        return {**out.state, 'revision': out.revision}

    def get_work_request(self, ctx, request_id):
        rec = self.p.store.read().require(ctx.tenant_id, 'assistant_work_request', request_id)
        self._current_owner(ctx, rec.state['site_id'])
        if principal(ctx) not in (rec.state['owner_id'], rec.state['requested_by']):
            raise PermissionError('work requests are private to their requester and intended owner')
        if rec.state['record_refs']:
            self._request_refs(ctx, rec.state['site_id'], rec.state['record_refs'], tx=self.p.store.read(), action='read')
        return {**rec.state, 'revision': rec.revision}

    def get_alarm(self, ctx, alarm_id):
        rec = self.p.store.read().require(ctx.tenant_id, 'assistant_alarm', alarm_id)
        self._request_refs(ctx, rec.state['site_id'], rec.state['record_refs'], tx=self.p.store.read(), action='read')
        return {**rec.state, 'revision': rec.revision}
