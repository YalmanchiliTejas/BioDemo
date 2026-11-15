"""Real store/event contracts for named deterministic routines; no live model claims."""
import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.roles import agent_context_for
from src.lifesci.store import ConflictError, RecordStore


@pytest.fixture
def env():
    platform = Platform(RecordStore(), providers={})
    seed(platform)
    return platform, platform.identity.context_for(TENANT, 'priya')


def service(platform):
    return platform.assistant_routines


def draft(routines, ctx, **changes):
    return routines.create(ctx, {
        'name': 'Review new cases', 'description': 'Check newly available case evidence.',
        'task': {'operation': 'find_records', 'site_id': 'NF1', 'kinds': ['case']},
        'triggers': ['case'], 'max_runs': 3, **changes})


def test_draft_is_private_and_cannot_admit_event_work(env):
    p, ctx = env
    routines = service(p)
    routine = draft(routines, ctx)
    assert routine['status'] == 'draft'
    assert routine['runs_admitted'] == 0 and routine['runs'] == []
    mission = p.missions.get(ctx, routine['mission_id'])
    assert not mission['subscriptions']
    assert not mission['assistant_responsibility']['enabled']
    p.cases.open(ctx, 'DRAFT-CASE', 'priya', 'quinn', 'NF1')
    p.missions.deliver_events(TENANT)
    assert not p.missions.get(ctx, routine['mission_id'])['pending_event_ids']
    p.identity.assign_role(TENANT, 'colleague', 'msat', site_id='NF1')
    colleague = p.identity.context_for(TENANT, 'colleague')
    assert routines.list(colleague) == []
    with pytest.raises(PermissionError):
        routines.get(colleague, routine['id'])


def test_activation_is_human_revision_checked_and_edits_need_reactivation(env):
    p, ctx = env
    routines = service(p)
    routine = draft(routines, ctx)
    with pytest.raises(PermissionError):
        routines.activate(agent_context_for(ctx, p.identity), routine['id'],
            expected_revision=routine['revision'], acknowledge_inference=True)
    with pytest.raises(ValueError, match='acknowledge'):
        routines.activate(ctx, routine['id'], expected_revision=routine['revision'], acknowledge_inference=False)
    active = routines.activate(ctx, routine['id'], expected_revision=routine['revision'], acknowledge_inference=True)
    assert active['status'] == 'active'
    with pytest.raises(ConflictError):
        routines.update(ctx, active['id'], {'expected_revision': routine['revision'], 'name': 'Old edit'})
    changed = routines.update(ctx, active['id'], {'expected_revision': active['revision'], 'name': 'Review revised cases'})
    assert changed['status'] == 'paused'
    assert not p.missions.get(ctx, changed['mission_id'])['assistant_responsibility']['enabled']


def test_agent_proposal_belongs_to_delegating_person_without_standing_authority(env):
    p, ctx = env
    routines = service(p)
    routine = draft(routines, agent_context_for(ctx, p.identity))
    assert routine['owner_id'] == 'priya' and routine['status'] == 'draft'
    assert p.engineering_conversations.get(ctx, routine['thread_id'])['owner_id'] == 'priya'


def active(routines, ctx, **changes):
    created = draft(routines, ctx, **changes)
    return routines.activate(ctx, created['id'], expected_revision=created['revision'], acknowledge_inference=True)


def pump(p, ctx, routine):
    from src.lifesci.ids import iso, utc_now
    from src.lifesci.runtime import run_coordinator
    p.missions.deliver_events(TENANT)
    delegated = agent_context_for(ctx, p.identity)
    act = p.missions.activate(delegated, routine['mission_id'], 'routine-test-worker')
    try:
        run_coordinator(p, delegated, act, ['events'], iso(utc_now()))
    finally:
        p.missions.release(act)
    return act


def test_manual_run_uses_parameters_without_changing_operation_or_site(env):
    p, ctx = env
    routines = service(p)
    p.cases.open(ctx, 'CASE-MATCH', 'priya', 'quinn', 'NF1')
    p.cases.open(ctx, 'CASE-OTHER', 'priya', 'quinn', 'NF1')
    routine = draft(routines, ctx)
    for parameters in ({'operation': 'prepare_review'}, {'site_id': 'NF2'}):
        with pytest.raises(ValueError, match='immutable'):
            routines.run(ctx, routine['id'], parameters)
    result = routines.run(ctx, routine['id'], {'query': 'MATCH'})
    assert [r['id'] for r in result['data']['records']] == ['CASE-MATCH']
    assert result['model_calls'] == 0
    saved = routines.get(ctx, routine['id'])
    assert saved['status'] == 'draft' and saved['runs_admitted'] == 0
    assert len(saved['runs']) == 1 and saved['latest_result']['id'] == result['id']
    assert not p.store.read().list(TENANT, 'model_run')


@pytest.mark.parametrize('change', ['pause', 'edit', 'revoke'])
def test_inflight_routine_cannot_commit_after_control_or_authority_change(env, monkeypatch, change):
    p, ctx = env
    routines = service(p)
    p.cases.open(ctx, 'CASE-FENCED', 'priya', 'quinn', 'NF1')
    routine = active(routines, ctx)
    compute = p.workspace_tasks.compute
    def change_while_computing(actor, request):
        result = compute(actor, request)
        current = routines.get(ctx, routine['id'])
        if change == 'pause':
            routines.pause(ctx, routine['id'], expected_revision=current['revision'])
        elif change == 'edit':
            routines.update(ctx, routine['id'], {'expected_revision': current['revision'], 'name': 'Changed work'})
        else:
            p.identity.revoke_role(TENANT, 'priya', 'msat', site_id='NF1')
        return result
    monkeypatch.setattr(p.workspace_tasks, 'compute', change_while_computing)
    with pytest.raises((PermissionError, ConflictError)):
        routines.run(ctx, routine['id'])
    assert not p.store.read().list(TENANT, 'workspace_task_result')
    runs = p.store.read().list(TENANT, 'assistant_routine_run')
    assert len(runs) == 1 and runs[0].state['status'] != 'completed'


def test_events_coalesce_and_replay_does_not_duplicate_completed_work(env):
    p, ctx = env
    routines = service(p)
    routine = active(routines, ctx,
        task={'operation': 'review_changes', 'site_id': 'NF1'}, max_runs=2)
    p.cases.open(ctx, 'EVENT-CASE', 'priya', 'quinn', 'NF1')
    p.cases.add_timeline_event(ctx, 'EVENT-CASE', '2026-11-14T10:00:00Z', 'Recorded new evidence.')
    act = pump(p, ctx, routine)
    saved = routines.get(ctx, routine['id'])
    assert saved['runs_admitted'] == 1 and len(saved['runs']) == 1
    assert saved['latest_result']['source_refs'][0]['revision'] == 2
    assert not p.missions.get(ctx, routine['mission_id'])['pending_event_ids']
    assert not p.store.read().list(TENANT, 'model_run')
    with p.store.transaction('redelivery') as tx:
        mission = tx.require(TENANT, 'mission', routine['mission_id'])
        tx.put(TENANT, 'mission', mission.id, {**mission.state, 'pending_event_ids': list(act.pending_event_ids)},
            expected_revision=mission.revision, action='fixture_redelivery')
    pump(p, ctx, routine)
    repeated = routines.get(ctx, routine['id'])
    assert repeated['runs_admitted'] == 1 and len(repeated['runs']) == 1
    assert len(p.store.read().list(TENANT, 'workspace_task_result')) == 1


def test_routine_events_reject_cross_site_private_and_generated_evidence(env):
    p, ctx = env
    routines = service(p)
    routine = active(routines, ctx, triggers=['case', 'evidence'])
    with p.store.transaction('fixture') as tx:
        tx.put(TENANT, 'case', 'OTHER-SITE', {'site_id': 'NF2'}, expected_revision=None,
            action='fixture', event_type='case.opened', event_payload={})
        tx.put(TENANT, 'case', 'UNSCOPED', {}, expected_revision=None,
            action='fixture', event_type='case.opened', event_payload={'site_id': 'NF1'})
    p.identity.assign_role(TENANT, 'colleague', 'msat', site_id='NF1')
    colleague = p.identity.context_for(TENANT, 'colleague')
    private = p.engineering_conversations.create(colleague, {})
    p.evidence.ingest(colleague, source_system='engineering-user-instruction', source_record_id='SECRET',
        content=b'private instruction', site_id='NF1', media_type='text/plain', event_time=None,
        metadata={'conversation_id': private['id']})
    p.evidence.ingest(ctx, source_system='process-analysis-assumptions', source_record_id='GENERATED',
        content=b'computed assumptions', site_id='NF1', media_type='text/plain', event_time=None)
    p.missions.deliver_events(TENANT)
    assert not p.missions.get(ctx, routine['mission_id'])['pending_event_ids']
    pump(p, ctx, routine)
    assert routines.get(ctx, routine['id'])['runs_admitted'] == 0


def test_pause_preserves_queued_events_and_revoked_owner_cannot_admit(env):
    p, ctx = env
    routines = service(p)
    routine = active(routines, ctx)
    p.cases.open(ctx, 'QUEUED', 'priya', 'quinn', 'NF1')
    pending = p.missions.get(ctx, routine['mission_id'])['pending_event_ids']
    assert pending
    current = routines.get(ctx, routine['id'])
    routines.pause(ctx, routine['id'], expected_revision=current['revision'])
    pump(p, ctx, routine)
    assert p.missions.get(ctx, routine['mission_id'])['pending_event_ids'] == pending
    assert routines.get(ctx, routine['id'])['runs_admitted'] == 0
    p.identity.revoke_role(TENANT, 'priya', 'msat', site_id='NF1')
    with pytest.raises(PermissionError):
        routines.run(ctx, routine['id'])


def test_shift_left_signal_scope_matches_actual_subject(env):
    p, ctx = env
    routines = service(p)
    routine = active(routines, ctx, triggers=['deviation'],
        task={'operation': 'review_changes', 'site_id': 'NF1', 'batches': ['B-SELECTED']})
    p.signals.raise_signal(TENANT, kind='trend', severity='warning', site_id='NF1',
        subject={'kind': 'batch', 'id': 'B-OTHER'}, rule='Recorded early warning', rule_key='early-warning')
    selected_signal = p.signals.raise_signal(TENANT, kind='trend', severity='warning', site_id='NF1',
        subject={'kind': 'batch', 'id': 'B-SELECTED'}, rule='Recorded early warning', rule_key='early-warning')
    mission = p.missions.get(ctx, routine['mission_id'])
    assert len(mission['pending_event_ids']) == 1
    pump(p, ctx, routine)
    saved = routines.get(ctx, routine['id'])
    assert [r['id'] for r in saved['latest_result']['source_refs']] == [selected_signal['signal_id']]


def test_work_requests_are_owner_addressed_deduplicated_and_source_scoped(env):
    p, ctx = env
    routines = service(p)
    p.identity.assign_role(TENANT, 'colleague', 'msat', site_id='NF1')
    colleague = p.identity.context_for(TENANT, 'colleague')
    ours = active(routines, ctx, triggers=['team_request'],
        task={'operation': 'review_changes', 'site_id': 'NF1'})
    theirs = active(routines, colleague, triggers=['team_request'])
    request = {'title': 'Check the gap', 'description': 'Which evidence is still needed?',
        'site_id': 'NF1', 'owner_id': 'priya', 'record_refs': [], 'request_key': 'shift-7'}
    first = routines.create_work_request(colleague, request)
    repeated = routines.create_work_request(colleague, request)
    assert first['id'] == repeated['id']
    assert len(p.missions.get(ctx, ours['mission_id'])['pending_event_ids']) == 1
    assert not p.missions.get(colleague, theirs['mission_id'])['pending_event_ids']
    assert routines.get_work_request(colleague, first['id'])['id'] == first['id']
    pump(p, ctx, ours)
    assert routines.get(ctx, ours['id'])['runs_admitted'] == 1


def test_alarm_requires_current_same_site_evidence_and_cannot_be_raised_by_agent(env):
    p, ctx = env
    routines = service(p)
    p.cases.open(ctx, 'ALARM-BASIS', 'priya', 'quinn', 'NF1')
    request = {'title': 'Review recorded alarm', 'site_id': 'NF1',
        'record_refs': [{'kind': 'case', 'id': 'ALARM-BASIS', 'revision': 1}], 'request_key': 'alarm-7'}
    with pytest.raises(PermissionError):
        routines.raise_alarm(agent_context_for(ctx, p.identity), request)
    with pytest.raises(ValueError):
        routines.raise_alarm(ctx, {**request, 'record_refs': []})
    routine = active(routines, ctx, triggers=['alarm'], task={'operation': 'review_changes', 'site_id': 'NF1'})
    first = routines.raise_alarm(ctx, request)
    assert routines.raise_alarm(ctx, request)['id'] == first['id']
    pump(p, ctx, routine)
    result = routines.get(ctx, routine['id'])['latest_result']
    assert result['data']['records'][0]['data']['record_refs'][0]['id'] == 'ALARM-BASIS'


def test_alarm_read_rechecks_live_site_permissions(env):
    p, ctx = env
    routines = service(p)
    p.cases.open(ctx, 'ALARM-READ', 'priya', 'quinn', 'NF1')
    alarm = routines.raise_alarm(ctx, {'title': 'Inspect source alarm', 'site_id': 'NF1',
        'record_refs': [{'kind': 'case', 'id': 'ALARM-READ', 'revision': 1}]})
    p.identity.assign_role(TENANT, 'reader', 'qa_reviewer', site_id='NF1')
    reader = p.identity.context_for(TENANT, 'reader')
    assert routines.get_alarm(reader, alarm['id'])['record_refs'][0]['id'] == 'ALARM-READ'
    p.identity.revoke_role(TENANT, 'reader', 'qa_reviewer', site_id='NF1')
    with pytest.raises(PermissionError):
        routines.get_alarm(reader, alarm['id'])


def test_failed_schedule_records_a_wait_without_repeated_admissions(env):
    p, ctx = env
    routines = service(p)
    routine = active(routines, ctx, triggers=[], every_minutes=60,
        task={'operation': 'review_changes', 'site_id': 'NF1',
              'record_refs': [{'kind': 'case', 'id': 'NOT-YET-AVAILABLE', 'revision': 1}]})
    with p.store.transaction('fixture') as tx:
        mission = tx.require(TENANT, 'mission', routine['mission_id'])
        obligations = [{**o, 'due_at': '2026-10-01T12:00:00Z'} for o in mission.state['obligations']]
        tx.put(TENANT, 'mission', mission.id, {**mission.state, 'obligations': obligations},
            expected_revision=mission.revision, action='fixture_overdue')
    pump(p, ctx, routine)
    mission = p.missions.get(ctx, routine['mission_id'])
    obligation = mission['obligations'][0]
    assert obligation['runtime_status'] == 'blocked'
    assert obligation['surfaced_due_at'] == obligation['due_at']
    pump(p, ctx, routine)
    saved = routines.get(ctx, routine['id'])
    assert saved['runs_admitted'] == 1 and len(saved['runs']) == 1
    assert saved['runs'][0]['status'] == 'failed'


def test_quarantined_source_values_cannot_leak_through_routine_receipts(env):
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    p, ctx = env
    routines = service(p)
    packet = {'schema_version': 'platform-verified-cmo-1', 'run_id': 'sensitive', 'cmo': 'Source lab',
        'guarantee': {'holds': True, 'checks': []}, 'measurements': [
            {'id': 'first', 'batch': 'A', 'time': 0, 'parameter': 'temperature', 'value': 987654.321, 'unit': 'degC'},
            {'id': 'second', 'batch': 'A', 'time': 0, 'parameter': 'temperature', 'value': 10, 'unit': 'degC'}]}
    source = p.evidence.ingest(ctx, source_system='cmo-verified-delivery', source_record_id='sensitive',
        content=json.dumps(packet).encode(), media_type='application/json', site_id='NF1',
        event_time='2026-11-01T00:00:00Z', metadata={'classification': 'verified_cmo_dataset'})
    routine = draft(routines, ctx, task={'operation': 'reconcile', 'site_id': 'NF1',
        'dataset_ids': [source['evidence_id']], 'target_unit': 'degC'})
    result = routines.run(ctx, routine['id'])
    assert result['task_status'] == 'needs_information'
    p.evidence.quarantine_from(ctx, 'evidence', source['evidence_id'], 'Source withdrawn')
    saved = routines.get(ctx, routine['id'])
    assert saved['latest_result'] is None
    assert '987654.321' not in json.dumps(saved)
    run_id = saved['runs'][0]['id']
    receipt = p.store.read().require(TENANT, 'assistant_routine_run', run_id)
    assert receipt.state['inputs'][0]['id'] == result['id']
    assert '987654.321' not in json.dumps(receipt.state)
    client = TestClient(create_app(p))
    response = client.get(f'/v1/records/assistant_routine_run/{run_id}',
        headers={'X-Tenant-Id': TENANT, 'X-Actor-Id': 'priya'})
    assert response.status_code == 403
    listed = client.get('/v1/records/assistant_routine_run',
        headers={'X-Tenant-Id': TENANT, 'X-Actor-Id': 'priya'})
    assert listed.status_code == 200 and listed.json()['items'] == []


def test_oversized_event_context_records_a_failure_instead_of_retrying_forever(env):
    p, ctx = env
    routines = service(p)
    refs = []
    for n in range(100):
        rid = f'CASE-{n:03}'
        p.cases.open(ctx, rid, 'priya', 'quinn', 'NF1')
        refs.append({'kind': 'case', 'id': rid, 'revision': 1, 'site_id': 'NF1'})
    routine = active(routines, ctx, triggers=['alarm'],
        task={'operation': 'review_changes', 'site_id': 'NF1', 'record_refs': refs})
    routines.raise_alarm(ctx, {'title': 'Changed source needs review', 'record_refs': [refs[0]]})
    pump(p, ctx, routine)
    saved = routines.get(ctx, routine['id'])
    assert len(saved['runs']) == 1 and saved['runs'][0]['status'] == 'failed'
    assert saved['runs'][0]['issues'][0]['code'] == 'source_limit_exceeded'
    assert not p.missions.get(ctx, routine['mission_id'])['pending_event_ids']
    pump(p, ctx, routine)
    assert routines.get(ctx, routine['id'])['runs_admitted'] == 1


def test_changed_record_is_reviewed_before_baseline_when_view_is_bounded(env):
    p, ctx = env
    routines = service(p)
    p.cases.open(ctx, 'BASELINE', 'priya', 'quinn', 'NF1')
    ref = {'kind': 'case', 'id': 'BASELINE', 'revision': 1, 'site_id': 'NF1'}
    routine = active(routines, ctx, triggers=['alarm'],
        task={'operation': 'review_changes', 'site_id': 'NF1', 'record_refs': [ref], 'limit': 1})
    alarm = routines.raise_alarm(ctx, {'title': 'Changed source needs review', 'record_refs': [ref]})
    pump(p, ctx, routine)
    result = routines.get(ctx, routine['id'])['latest_result']
    assert result['data']['records'][0]['id'] == alarm['id']
    assert result['task_status'] == 'needs_information'

