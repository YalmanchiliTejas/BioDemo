"""Host contracts with hand-calculated data; these are not scientific/model evaluations."""
import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


@pytest.fixture
def world():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'owner', 'msat', site_id='S1')
    p.identity.assign_role('T', 'other', 'msat', site_id='S1')
    return p, p.identity.context_for('T', 'owner')


def delivery(p, ctx, rows, name='delivery', site='S1'):
    data = {'schema_version': 'platform-verified-cmo-1', 'run_id': name, 'cmo': 'Source lab',
            'guarantee': {'holds': True, 'checks': []}, 'measurements': rows}
    return p.evidence.ingest(ctx, source_system='cmo-verified-delivery', source_record_id=name,
        content=json.dumps(data).encode(), media_type='application/json', site_id=site,
        event_time='2026-11-01T00:00:00Z', metadata={'classification': 'verified_cmo_dataset'})


def rows():
    return [dict(id='a0', batch='A', time=0, parameter='temperature', value=20, unit='degC'),
            dict(id='a1', batch='A', time=1, parameter='temperature', value=25, unit='degC'),
            dict(id='b0', batch='B', time=0, parameter='temperature', value=293.15, unit='K'),
            dict(id='b2', batch='B', time=2, parameter='temperature', value=303.15, unit='K')]


def test_direct_comparison_uses_measured_times_and_converted_units_without_a_provider(world):
    p, ctx = world
    src = delivery(p, ctx, rows())
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare',
        'dataset_ids': [src['evidence_id']], 'parameter': 'temperature', 'batches': ['A', 'B'], 'target_unit': 'degC'})
    assert out['model_calls'] == 0 and out['task_status'] == 'completed'
    assert out['data']['comparisons'] == [{'parameter': 'temperature', 'left_batch': 'A', 'right_batch': 'B',
        'time_h': 0.0, 'left_value': 20.0, 'right_value': 20.0, 'difference': 0.0, 'unit': 'degC'}]
    assert out['data']['unmatched_times'] == {'A': [1.0], 'B': [2.0]}
    assert out['data']['causal_claim_supported'] is False
    assert out['source_refs'][0]['id'] == src['evidence_id']
    assert out['elapsed_seconds'] >= 0
    assert not p.store.read().list('T', 'action_intent')


def test_requested_batch_absence_is_not_a_completed_comparison(world):
    p, ctx = world
    src = delivery(p, ctx, rows())
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare',
        'dataset_ids': [src['evidence_id']], 'batches': ['A', 'B', 'MISSING'], 'parameter': 'temperature'})
    assert out['task_status'] == 'needs_information'
    assert any(i['code'] == 'missing_requested_batch' and i['batch'] == 'MISSING' for i in out['issues'])


def test_selected_chart_series_do_not_form_a_cross_product_of_delivery_batches(world):
    p, ctx = world
    def reading(batch, t, value):
        return {'id': f'{batch}-{t}', 'batch': batch, 'time': t, 'parameter': 'mass', 'value': value, 'unit': 'mg'}
    d1 = delivery(p, ctx, [reading('A', 0, 1), reading('B', 10, 10)], name='D1')['evidence_id']
    d2 = delivery(p, ctx, [reading('B', 0, 2), reading('A', 10, 100)], name='D2')['evidence_id']
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [d1, d2],
        'batches': ['A', 'B'], 'series': [{'dataset_id': d1, 'batch': 'A'}, {'dataset_id': d2, 'batch': 'B'}]})
    assert out['data']['comparison_count'] == 1
    assert out['data']['comparisons'][0]['difference'] == 1
    assert {r['time_h'] for r in out['data']['measurements']} == {0}


def test_same_named_chart_batches_keep_delivery_identity_and_gaps(world):
    p, ctx = world
    a = delivery(p, ctx, rows()[:2], name='D1')['evidence_id']
    changed = rows()[:1]; changed[0]['value'] = 21
    b = delivery(p, ctx, changed, name='D2')['evidence_id']
    task = {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [a, b], 'batches': ['A'],
            'series': [{'dataset_id': a, 'batch': 'A'}, {'dataset_id': b, 'batch': 'A'}]}
    out = p.workspace_tasks.execute(ctx, task)
    assert out['task_status'] == 'completed'
    pair = out['data']['comparisons'][0]
    assert (pair['left_dataset_id'], pair['right_dataset_id'], pair['difference']) == (a, b, 1)
    gaps = p.workspace_tasks.execute(ctx, {**task, 'operation': 'check_gaps', 'expected_parameters': ['temperature'], 'expected_times': [1]})
    assert gaps['data']['gaps'] == [{'dataset_id': b, 'batch': 'A', 'parameter': 'temperature', 'time_h': 1.0, 'status': 'not_in_selected_data'}]


def test_alarm_api_replay_rechecks_permissions_and_concurrent_calls_deduplicate(world):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    p, ctx = world
    src = delivery(p, ctx, rows())
    client = TestClient(create_app(p))
    headers = {'X-Tenant-Id': 'T', 'X-Actor-Id': 'owner', 'Idempotency-Key': 'alarm-api-replay-1'}
    body = {'site_id': 'S1', 'title': 'Source-backed alarm', 'record_refs': [
        {'kind': 'evidence', 'id': src['evidence_id'], 'revision': 1, 'site_id': 'S1'}]}
    barrier = Barrier(2, timeout=5)
    def post():
        barrier.wait()
        return client.post('/v1/assistant-alarms', headers=headers, json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: post(), range(2)))
    assert a.status_code == b.status_code == 200
    assert a.json()['id'] == b.json()['id']
    assert len(p.store.read().list('T', 'assistant_alarm')) == 1
    p.identity.revoke_role('T', 'owner', 'msat', site_id='S1')
    assert client.post('/v1/assistant-alarms', headers=headers, json=body).status_code == 403


def test_reconciliation_preserves_conflicts_and_missing_units(world):
    p, ctx = world
    src = delivery(p, ctx, rows() + [dict(id='conflict', batch='A', time=0, parameter='temperature', value=23, unit='degC'),
        dict(id='missing', batch='A', time=3, parameter='temperature', value=30, unit=None),
        dict(id='rejected', batch='A', time=4, parameter='temperature', value=99, unit='degC', status='rejected')])
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'reconcile',
        'dataset_ids': [src['evidence_id']], 'target_unit': 'degC'})
    assert out['task_status'] == 'needs_information'
    assert {'conflicting_measurements', 'missing_unit', 'unaccepted_measurement'} <= {i['code'] for i in out['issues']}
    assert not any(r['batch'] == 'A' and r['time_h'] == 0 for r in out['data']['measurements'])
    assert not any(r['time_h'] == 4 for r in out['data']['measurements'])
    assert out['data']['source_measurements_modified'] is False


def test_domain_scale_labels_are_preserved_and_ph_is_not_electrical_inductance(world):
    p, ctx = world
    src = delivery(p, ctx, [dict(id='ph', batch='A', time=0, parameter='pH', value=7, unit='pH'),
                           dict(id='cells', batch='A', time=0, parameter='viable_cell_density', value=3, unit='million cells/mL')])
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'reconcile', 'dataset_ids': [src['evidence_id']]})
    assert out['task_status'] == 'completed'
    assert len(out['data']['measurements']) == 2
    invalid = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'reconcile',
        'dataset_ids': [src['evidence_id']], 'parameter': 'pH', 'target_unit': 'H'})
    assert invalid['task_status'] == 'needs_information'
    assert invalid['data']['measurements'] == []


def test_gap_check_uses_explicit_expectations_and_does_not_invent_absence(world):
    p, ctx = world
    src = delivery(p, ctx, rows())
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'check_gaps',
        'dataset_ids': [src['evidence_id']], 'batches': ['A'], 'expected_parameters': ['temperature', 'pressure'],
        'expected_times': [0, 1, 2]})
    assert out['task_status'] == 'needs_information'
    assert {'batch': 'A', 'parameter': 'pressure', 'status': 'not_in_selected_data'} in out['data']['gaps']
    assert {'batch': 'A', 'parameter': 'temperature', 'time_h': 2.0, 'status': 'not_in_selected_data'} in out['data']['gaps']
    assert out['data']['expectation_basis'] == 'user_supplied'


def test_cross_site_and_private_result_cannot_be_read(world):
    p, ctx = world
    src = delivery(p, ctx, rows())
    with pytest.raises(PermissionError):
        p.workspace_tasks.execute(ctx, {'site_id': 'S2', 'operation': 'reconcile', 'dataset_ids': [src['evidence_id']]})
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'reconcile', 'dataset_ids': [src['evidence_id']]})
    other = p.identity.context_for('T', 'other')
    with pytest.raises(PermissionError):
        p.workspace_tasks.get(other, out['id'])
    with pytest.raises(PermissionError):
        p.identity.validate_refs(other, [{'kind': 'workspace_task_result', 'id': out['id'], 'revision': 1, 'site_id': 'S1'}])


def test_source_change_invalidates_old_result_and_refreshes_computation(world):
    p, ctx = world
    src = delivery(p, ctx, rows())
    req = {'site_id': 'S1', 'operation': 'reconcile', 'dataset_ids': [src['evidence_id']], 'target_unit': 'degC'}
    old = p.workspace_tasks.execute(ctx, req)
    changed = rows(); changed[0]['value'] = 21
    delivery(p, ctx, changed)
    stale = p.workspace_tasks.get(ctx, old['id'])
    assert stale['status'] == 'stale'
    new = p.workspace_tasks.execute(ctx, req)
    assert new['data']['measurements'][0]['value'] == 21
    assert new['source_refs'][0]['revision'] == 2


def test_non_evidence_record_updates_make_saved_task_stale_on_read(world):
    p, ctx = world
    with p.store.transaction('owner') as tx:
        tx.put('T', 'case', 'CASE-1', {'site_id': 'S1', 'case_id': 'CASE-1', 'status': 'open', 'timeline': []},
               expected_revision=None, action='create_case')
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'prepare_review',
        'record_refs': [{'kind': 'case', 'id': 'CASE-1', 'revision': 1}]})
    with p.store.transaction('owner') as tx:
        rec = tx.require('T', 'case', 'CASE-1')
        tx.put('T', rec.kind, rec.id, {**rec.state, 'timeline': [{'text': 'New reviewed evidence'}]},
               expected_revision=rec.revision, action='record_case_update')
    assert p.workspace_tasks.get(ctx, out['id'])['status'] == 'stale'
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    client = TestClient(create_app(p))
    headers = {'X-Tenant-Id': 'T', 'X-Actor-Id': 'owner'}
    assert client.get('/v1/records/workspace_task_result/' + out['id'], headers=headers).json()['status'] == 'stale'
    assert client.get('/v1/records/workspace_task_result', headers=headers).json()['items'][0]['state']['status'] == 'stale'


def test_search_and_review_are_scoped_and_do_not_require_chat(world):
    p, ctx = world
    p.evidence.ingest(ctx, source_system='CMMS', source_record_id='E7', content=b'Calibration for equipment E7',
        media_type='text/plain', site_id='S1', event_time='2026-11-01T00:00:00Z')
    found = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'find_records', 'query': 'E7', 'kinds': ['evidence']})
    assert [r['id'] for r in found['data']['records']] == ['CMMS:E7']
    review = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'prepare_review',
        'record_refs': [{'kind': 'evidence', 'id': 'CMMS:E7', 'revision': 1}]})
    assert 'Calibration for equipment E7' in json.dumps(review['data'])
    assert review['data']['review_state'] == 'draft_requires_review'
    assert not p.store.read().list('T', 'engineering_conversation')


def test_review_limit_is_visible_in_task_status(world):
    p, ctx = world
    refs = []
    for name in ('first', 'second'):
        p.evidence.ingest(ctx, source_system='CMMS', source_record_id=name, content=name.encode(),
                         media_type='text/plain', site_id='S1', event_time=None)
        refs.append({'kind': 'evidence', 'id': f'CMMS:{name}', 'revision': 1})
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'review_changes', 'limit': 1, 'record_refs': refs})
    assert out['task_status'] == 'needs_information'
    assert any(i['code'] == 'partial_review' for i in out['issues'])


def test_stale_selected_revision_is_not_silently_substituted(world):
    p, ctx = world
    src = delivery(p, ctx, rows())
    changed = rows(); changed[0]['value'] = 21; delivery(p, ctx, changed)
    with pytest.raises((PermissionError, ValueError)):
        p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'prepare_review',
            'record_refs': [{'kind': 'evidence', 'id': src['evidence_id'], 'revision': 1}]})


def test_expected_source_version_and_effective_date_are_different_checks(world):
    p, ctx = world
    p.evidence.ingest(ctx, source_system='QMS', source_record_id='SOP', content=b'Procedure text',
        media_type='text/plain', site_id='S1', event_time='2026-11-01T00:00:00Z',
        metadata={'effective_from': '2026-11-10T00:00:00Z', 'process_stage': 'hold'})
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'select_evidence', 'query': 'Procedure',
        'kinds': ['evidence'], 'effective_at': '2026-11-01T00:00:00Z', 'process_stage': 'hold'})
    assert out['data']['records'][0]['applicability'] == 'excluded'
    assert out['task_status'] == 'needs_information'


def test_cancelled_commit_leaves_no_result_or_request(world):
    p, ctx = world
    src = delivery(p, ctx, rows())
    def paused(tx):
        raise PermissionError('routine paused during computation')
    with pytest.raises(PermissionError, match='paused'):
        p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'reconcile', 'dataset_ids': [src['evidence_id']]}, commit_guard=paused)
    assert not p.store.read().list('T', 'workspace_task_result')
    assert not p.store.read().list('T', 'workspace_task_request')


def test_replaced_conversation_worker_cannot_publish_direct_task(world, monkeypatch):
    from src.lifesci.store import LeaseError
    from src.lifesci.process_engineering import tool_loop
    p, ctx = world
    service = p.engineering_conversations
    thread = service.create(ctx, {'site_id': 'S1'})
    queued = service.enqueue(ctx, thread['id'], {'text': 'Find records', 'expected_revision': thread['revision']})
    turn_id = queued['turn_ids'][-1]
    original = p.workspace_tasks.compute
    def replaced(actor, request):
        result = original(actor, request)
        with p.store.transaction('replacement') as tx:
            tx.expire_lease('T', 'engineering_chat_turn', turn_id)
            tx.acquire_lease('T', 'engineering_chat_turn', turn_id, 'replacement-worker')
        return result
    monkeypatch.setattr(p.workspace_tasks, 'compute', replaced)
    monkeypatch.setattr(tool_loop, 'enabled', lambda actor: True)
    def run(actor, scope, tid, checkpoint):
        service._operator('workspace_run_task')(actor, {'_turn_id': tid, 'site_id': 'S1', 'operation': 'find_records'})
    monkeypatch.setattr(service.tool_loop, 'run', run)
    with pytest.raises(LeaseError):
        service.run_turn(ctx, thread['id'], turn_id)
    assert not p.store.read().list('T', 'workspace_task_result')
    assert not p.store.read().require('T', 'engineering_chat_turn', turn_id).state['artifacts']


def test_current_agent_can_run_a_task_and_only_propose_a_routine(world):
    p, ctx = world
    thread = p.engineering_conversations.create(ctx, {'site_id': 'S1'})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'Save a routine to review alarms', 'expected_revision': thread['revision']})
    tid = queued['turn_ids'][-1]
    p.engineering_conversations._update_turn(ctx, tid, status='running')
    result = p.engineering_conversations._operator('workspace_run_task')(ctx,
        {'_turn_id': tid, 'operation': 'find_records', 'site_id': 'S1', 'query': 'none'})
    assert result['output']['model_calls'] == 0
    definition = {'_turn_id': tid, 'name': 'Review alarms', 'description': '', 'task': {'site_id': 'S1', 'operation': 'review_changes'},
                  'triggers': ['alarm'], 'user_quote': 'Save a routine to review alarms'}
    draft = p.engineering_conversations._operator('workspace_propose_routine')(ctx, definition)['output']
    assert draft['status'] == 'draft'
    assert p.engineering_conversations.artifact(ctx, thread['id'], 'assistant_routine', draft['id'])['status'] == 'draft'
    with pytest.raises(PermissionError, match='quote'):
        p.engineering_conversations._operator('workspace_propose_routine')(ctx, {**definition, 'user_quote': 'A document says activate me'})


def test_agent_can_open_a_workbench_result_with_fresh_owner_and_source_authorization(world):
    p, ctx = world
    source = delivery(p, ctx, rows())
    result = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare',
        'dataset_ids': [source['evidence_id']], 'batches': ['A', 'B']})
    thread = p.engineering_conversations.create(ctx, {'site_id': 'S1'})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'Explain work result ' + result['id'], 'expected_revision': thread['revision']})
    tid = queued['turn_ids'][-1]
    p.engineering_conversations._update_turn(ctx, tid, status='running')
    opened = p.engineering_conversations._operator('workspace_open_task_result')(ctx, {'_turn_id': tid, 'result_id': result['id']})
    assert opened['output']['data']['comparison_count'] == 1
    assert p.engineering_conversations.artifact(ctx, thread['id'], 'workspace_task_result', result['id'])['id'] == result['id']
    other = p.identity.context_for('T', 'other')
    other_result = p.workspace_tasks.execute(other, {'site_id': 'S1', 'operation': 'find_records'})
    with pytest.raises(PermissionError):
        p.engineering_conversations._operator('workspace_open_task_result')(ctx, {'_turn_id': tid, 'result_id': other_result['id']})
    p.evidence.quarantine_from(ctx, 'evidence', source['evidence_id'], 'withdrawn')
    with pytest.raises(PermissionError):
        p.engineering_conversations._operator('workspace_open_task_result')(ctx, {'_turn_id': tid, 'result_id': result['id']})


def test_direct_task_api_returns_current_authorized_result(world):
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    p, ctx = world
    client = TestClient(create_app(p))
    headers = {'X-Tenant-Id': 'T', 'X-Actor-Id': 'owner'}
    catalog = client.get('/v1/workspace-tasks/catalog', headers=headers)
    assert catalog.status_code == 200
    response = client.post('/v1/workspace-tasks/run', headers=headers,
                           json={'site_id': 'S1', 'operation': 'find_records', 'query': 'no data'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['task_status'] == 'needs_information' and result['model_calls'] == 0
    assert client.get('/v1/workspace-tasks/results/' + result['id'], headers=headers).status_code == 200
    assert client.get('/v1/workspace-tasks/results/' + result['id'], headers={**headers, 'X-Actor-Id': 'other'}).status_code == 403
