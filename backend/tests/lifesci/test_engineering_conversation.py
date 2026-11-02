"""FakeProvider checks orchestration contracts, never measured live AI behavior."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.gateway import FakeProvider
from src.lifesci.gateway.registry import Qualification
from src.lifesci.store import ConflictError, RecordStore

@pytest.fixture
def env():
    p = Platform(RecordStore(), providers={})
    seed(p)
    return p, p.identity.context_for(TENANT, 'priya')

def fake_planner(p, decisions):
    fake = FakeProvider(name='anthropic')
    p.gateway.providers['anthropic'] = fake
    p.gateway.registry.qualify(Qualification('investigation_planning', 'anthropic-opus', 'unit-test-only', True,
        {'contract': 1.}, {'contract': 1.}, 'Test double, not measured AI or scientific qualification', 'test'))
    model = p.gateway.registry.profiles['anthropic-opus'].model
    fake.scripts[model] = [json.dumps(d) for d in decisions]
    return fake

def binding(node, key='id'):
    return {'$node': node, 'path': [key]}

def node(nid, op, payload, deps=()):
    return {'node_id': nid, 'task_kind': op, 'title': nid.replace('_', ' ').capitalize(), 'payload': payload, 'depends_on': list(deps)}

def plan(source):
    return {'simulation_id': source, 'objective': 'Evaluate primary-drying constraints from recorded input assumptions',
        'models': [{'model_id': 'lyo.kv_rp', 'rationale': 'Screen steady primary-drying limits before adding thermal assumptions'}],
        'samples': 0, 'max_solver_calls': 32, 'max_wall_seconds': 30}

def simulate_workflow():
    return [node('source', 'physical_demo_context', {}),
        node('select', 'physical_pipeline_prepare', plan(binding('source')), ['source']),
        node('simulate', 'physical_pipeline_execute', {'plan_id': binding('select')}, ['select'])]

def send(p, ctx, thread, text, **extras):
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': text, 'expected_revision': thread['revision'], **extras})
    return p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])

def test_live_route_unavailable_saves_message_without_invented_workflow(env):
    p, ctx = env
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Help investigate a freeze-drying temperature drift')
    turn = result['turns'][0]
    assert turn['status'] == 'agent_unavailable' and turn['reply'] is None
    assert not turn['artifacts'] and turn['flow_run_id'] is None
    assert turn['gateway_runs'][0]['status'] == 'unresolved'
    assert 'no workflow or simulation has run' in turn['system_message']
    assert not p.store.read().list(TENANT, 'data_flow')
    assert p.missions.get(ctx, result['mission_id'])['notes'][0]['body'] == turn['user_text']

def test_selected_screen_context_is_persisted_and_quoted_without_source_authority(env, monkeypatch):
    p, ctx = env
    seen = []
    original = p.gateway.run
    def capture(req):
        seen.append(json.loads(req.prompt))
        return original(req)
    monkeypatch.setattr(p.gateway, 'run', capture)
    fake_planner(p, [{'reply': 'This is a screen snapshot. I need the recorded inputs.',
        'questions': ['Which authorized source contains these measurements?']}])
    selection = {'kind': 'chart', 'label': 'Feed flow · 250–270 h', 'page_path': '/workbench/AN-104',
        'captured_at': '2026-10-26T12:00:00Z',
        'content': json.dumps({'unit': 'L/h', 'selected_range': [250, 270],
            'series': [{'id': 'MES-26073', 'points': [{'elapsedHours': 264, 'value': 1.4, 'imputed': True}]}]})}
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Explain this range.', display_context=selection)
    turn = result['turns'][0]
    assert turn['display_context']['content'] == selection['content']
    assert turn['display_context']['page_path'] == selection['page_path']
    original_instruction = json.loads(p.evidence.original(ctx, turn['user_ref']['id']))
    assert original_instruction['display_context'] == turn['display_context']
    assert seen[0]['conversation'][0]['display_context'] == turn['display_context']
    assert 'unverified user-selected screen snapshot' in ' '.join(seen[0]['instructions'])
    assert seen[0]['authorized_sources'] == [] and result['source_ids'] == []
    assert not result['demo_enabled'] and not turn['artifacts']
    assert not p.store.read().list(TENANT, 'action_intent')
    # Owner/tenant authorization still protects the attached snapshot.
    p.identity.assign_role(TENANT, 'other', 'msat', site_id='NF1')
    with pytest.raises(PermissionError, match='private'):
        p.engineering_conversations.get(p.identity.context_for(TENANT, 'other'), result['id'])

def test_display_context_contract_rejects_unbounded_or_invalid_snapshots():
    from pydantic import ValidationError
    from src.lifesci.process_engineering.conversation_schemas import MessageIn
    selection = {'kind': 'text', 'label': 'Batch', 'page_path': '/batches/MES-26073',
        'captured_at': '2026-10-26T12:00:00Z', 'content': 'Selected display text'}
    for change in ({'content': 'x' * 120001}, {'page_path': 'https://external.example'},
                   {'captured_at': 'invalid'}, {'kind': 'authorized_evidence'}):
        with pytest.raises(ValidationError):
            MessageIn(text='Explain this', expected_revision=1, display_context={**selection, **change})

def test_clarification_simulation_and_branched_followup(env):
    p, ctx = env
    fake_planner(p, [
        {'reply': 'I need an input context.', 'questions': ['Use the reconstruction or attach measured equipment inputs?']},
        {'reply': 'I will simulate the reconstruction using the quasi-steady adapter.', 'workflow': simulate_workflow()},
    ])
    first = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Can the receiving facility handle this primary drying process?')
    assert first['turns'][0]['status'] == 'needs_information' and not first['turns'][0]['artifacts']
    second = send(p, ctx, first, 'Use the example reconstruction.', enable_demo=True)
    turn = second['turns'][-1]
    assert turn['status'] == 'completed', turn['issues']
    assert [s['task_kind'] for s in turn['steps']] == [n['task_kind'] for n in simulate_workflow()]
    result_ref = next(a for a in turn['artifacts'] if a['kind'] == 'physical_analysis_result')
    result = p.engineering_conversations.artifact(ctx, first['id'], result_ref['kind'], result_ref['id'])
    assert result['execution_status'] == 'completed'
    assert result['models'][0]['prediction']['trajectory'] and result['models'][0]['geometry']['frames']
    assert result['resource_usage']['solver_calls'] > 0
    followup = [node('lower_load', 'physical_context_variant', {'source_id': second['source_ids'][0], 'label': 'Reduced load',
        'rationale': 'Test whether a lower batch load restores vapor-capacity margin', 'load_vials': 6000}),
        node('select_lower', 'physical_pipeline_prepare', plan(binding('lower_load')), ['lower_load']),
        node('simulate_lower', 'physical_pipeline_execute', {'plan_id': binding('select_lower')}, ['select_lower']),
        node('compare', 'physical_results_compare', {'result_ids': [result['id'], binding('simulate_lower')]}, ['simulate_lower'])]
    fake_planner(p, [{'reply': 'I will compare a lower load with the saved forecast.', 'workflow': followup}])
    third = send(p, ctx, second, 'What changes if we lower the load to 6000 vials?')
    assert third['turns'][-1]['status'] == 'completed', third['turns'][-1]['issues']
    assert len(third['turns'][-1]['steps']) == 4
    comparison_ref = third['turns'][-1]['artifacts'][-1]
    comparison = p.engineering_conversations.artifact(ctx, first['id'], comparison_ref['kind'], comparison_ref['id'])
    assert len(comparison['rows']) == 2
    original = p.engineering_conversations.artifact(ctx, first['id'], 'physical_analysis_result', result['id'])
    assert original['status'] != 'stale'
    assert comparison['rows'][0]['violations'] != comparison['rows'][1]['violations']
    assert not p.store.read().list(TENANT, 'action_intent')

def test_no_arbitrary_code_or_silent_demo(env):
    p, ctx = env
    fake_planner(p, [{'reply': 'I will run a reconstruction.', 'workflow': simulate_workflow()}])
    blocked = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Investigate my real manufacturing problem.')
    assert blocked['turns'][-1]['status'] == 'blocked' and not blocked['turns'][-1]['artifacts']
    assert 'not been selected' in blocked['turns'][-1]['steps'][0]['issues'][0]
    fake_planner(p, [{'reply': 'I will execute code.', 'workflow': [node('exec', 'python_exec', {'code': 'import os'})]}])
    invalid = send(p, ctx, blocked, 'Try another approach.')
    assert invalid['turns'][-1]['status'] == 'blocked' and not invalid['turns'][-1]['flow_run_id']

def test_lineage_invalidation_and_owner_boundary(env):
    p, ctx = env
    fake_planner(p, [{'reply': 'I will calculate from the selected example.', 'workflow': simulate_workflow()}])
    thread = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Use the demo.', enable_demo=True)
    assert thread['turns'][-1]['status'] == 'completed', thread['turns'][-1]['issues']
    result = next(a for a in thread['turns'][0]['artifacts'] if a['kind'] == 'physical_analysis_result')
    p.evidence.invalidate(ctx, 'physical_analysis_context', thread['source_ids'][0], 'Equipment revision changed')
    artifact = p.engineering_conversations.artifact(ctx, thread['id'], result['kind'], result['id'])
    assert artifact['status'] == 'stale' and 'models' not in artifact
    assert p.engineering_conversations.get(ctx, thread['id'])['turns'][0]['basis_status'] == 'stale'
    p.identity.assign_role(TENANT, 'other', 'msat', site_id='NF1')
    other = p.identity.context_for(TENANT, 'other')
    with pytest.raises(PermissionError, match='private'):
        p.engineering_conversations.get(other, thread['id'])
    assert p.engineering_conversations.list_for(other) == []
    with pytest.raises(PermissionError):
        p.engineering_conversations.artifact(other, thread['id'], result['kind'], result['id'])

def test_hidden_future_outcomes_not_in_planner_inputs(env, monkeypatch):
    p, ctx = env
    source = p.process_models.context(ctx, audience='cdmo_operation')
    seen = []
    original = p.gateway.run
    def capture(req):
        seen.append(req.prompt)
        return original(req)
    monkeypatch.setattr(p.gateway, 'run', capture)
    fake_planner(p, [{'reply': 'I need the incident context.', 'questions': ['Which sensor recorded the temperature?']}])
    send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Investigate a deviation', source_ids=[source['id']])
    prompt = json.loads(seen[-1])
    assert all(r['time_h'] <= 6 for r in prompt['authorized_sources'][0]['observations'])
    assert all('reference' not in m['id'] for m in prompt['registered_models'])
    assert 'workspace' not in prompt['authorized_sources'][0]
    assert 'evaluation_only' not in seen[-1] and 'hidden_outcome' not in seen[-1]

def test_pending_revision_retry_without_duplicate_turns(env):
    p, ctx = env
    svc = p.engineering_conversations
    thread = svc.create(ctx, {})
    queued = svc.enqueue(ctx, thread['id'], {'text': 'Assess this process', 'expected_revision': thread['revision']})
    with pytest.raises(ConflictError):
        svc.enqueue(ctx, thread['id'], {'text': 'Duplicate send', 'expected_revision': thread['revision']})
    with pytest.raises(ConflictError, match='already running'):
        svc.enqueue(ctx, thread['id'], {'text': 'Another send', 'expected_revision': queued['revision']})
    svc.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
    fake_planner(p, [{'reply': 'Please supply context.', 'questions': ['Which equipment and formulation?']}])
    retried = svc.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
    assert len(retried['turns']) == 1 and retried['turns'][0]['status'] == 'needs_information'
    assert len(retried['turns'][0]['gateway_runs']) == 2

def test_bad_bindings_and_unregistered_models_are_blocked(env):
    p, ctx = env
    workflow = simulate_workflow()
    workflow[1]['depends_on'] = []
    # The gateway permits one correction; keep both invalid to test rejection.
    fake_planner(p, [{'reply': 'I will prepare it.', 'workflow': workflow}] * 2)
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Use the example', enable_demo=True)
    assert result['turns'][-1]['status'] == 'blocked' and not result['turns'][-1]['flow_run_id']
    workflow = simulate_workflow()
    workflow[1]['payload']['models'][0]['model_id'] = 'lyo.unregistered'
    fake_planner(p, [{'reply': 'I will use this adapter.', 'workflow': workflow}])
    result = send(p, ctx, result, 'Try this adapter')
    assert result['turns'][-1]['status'] == 'blocked'
    assert 'unregistered' in result['turns'][-1]['steps'][1]['issues'][0]
    assert not p.store.read().list(TENANT, 'physical_analysis_result')
    workflow = simulate_workflow()
    workflow[1]['payload']['models'].append({'model_id': 'lyo.transient_lumped', 'rationale': 'Compare thermal storage but report required missing characterization explicitly'})
    fake_planner(p, [{'reply': 'I will check both registered adapters and retain missing-input results.', 'workflow': workflow}])
    partial = send(p, ctx, result, 'Compare the two registered adapters.')
    assert partial['turns'][-1]['status'] == 'blocked'
    assert 'thermal.initial_temperature_c' in partial['turns'][-1]['issues'][0]
    assert next(a for a in partial['turns'][-1]['artifacts'] if a['kind'] == 'physical_analysis_result')

def test_api_persistence_and_idempotent_send(env):
    p, ctx = env
    client = TestClient(create_app(p))
    headers = {'X-Tenant-Id': TENANT, 'X-Actor-Id': ctx.actor_id, 'Idempotency-Key': 'chat-create'}
    created = client.post('/v1/process-model/conversations', headers=headers, json={})
    assert created.status_code == 200, created.text
    thread = created.json()
    assert client.post('/v1/process-model/conversations', headers=headers, json={}).json()['id'] == thread['id']
    headers['Idempotency-Key'] = 'chat-send'
    body = {'text': 'Help analyze a physical process problem', 'expected_revision': thread['revision']}
    url = f"/v1/process-model/conversations/{thread['id']}"
    assert client.post(f'{url}/messages', headers=headers, json=body).status_code == 200
    # The turn runs after the response (a thread here, an asynchronous invocation on Lambda); poll like the UI.
    import time
    for _ in range(200):
        final = client.get(url, headers=headers).json()
        if final['turns'][0]['status'] not in ('queued', 'running'):
            break
        time.sleep(.02)
    assert final['turns'][0]['status'] == 'agent_unavailable'
    client.post(f'{url}/messages', headers=headers, json=body)
    assert len(client.get(url, headers=headers).json()['turns']) == 1


def test_review_is_a_proposal_and_finished_flow_replay_does_not_recalculate(env):
    p, ctx = env
    workflow = simulate_workflow() + [node('review', 'physical_analysis_review', {'result_id': binding('simulate')}, ['simulate'])]
    fake_planner(p, [{'reply': 'I will calculate and prepare the engineering review you requested.', 'workflow': workflow}])
    thread = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Use the example and create a review proposal', enable_demo=True)
    turn = thread['turns'][-1]
    assert turn['status'] == 'completed', turn['issues']
    proposal = p.engineering_conversations.artifact(ctx, thread['id'], 'proposal', turn['artifacts'][-1]['id'])
    assert proposal['operation'] == 'review_physical_analysis' and proposal['status'] == 'proposed'
    assert proposal['owner_id'] == ctx.actor_id
    before = len(p.store.read().list(TENANT, 'physical_analysis_result'))
    p.engineering_conversations.run_turn(ctx, thread['id'], turn['id'])
    assert len(p.store.read().list(TENANT, 'physical_analysis_result')) == before
    assert not p.store.read().list(TENANT, 'action_intent')


def test_interrupted_turn_persists_across_restart_and_live_worker_cannot_be_replaced(tmp_path):
    from src.lifesci.store import LeaseError
    path = str(tmp_path/'conversation.db')
    p = Platform(RecordStore(path), providers={})
    seed(p)
    ctx = p.identity.context_for(TENANT, 'priya')
    thread = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'Assess this process', 'expected_revision': thread['revision']})
    tid = queued['turn_ids'][-1]
    p.engineering_conversations._update_turn(ctx, tid, status='running')
    with p.store.transaction(ctx.actor_id) as tx:
        tx.acquire_lease(TENANT, 'engineering_chat_turn', tid, 'test-live-worker')
    with pytest.raises(LeaseError):
        p.engineering_conversations.queue_retry(ctx, thread['id'])
    with p.store.transaction(ctx.actor_id) as tx:
        tx.expire_lease(TENANT, 'engineering_chat_turn', tid)
    restarted = Platform(RecordStore(path), providers={})
    fake_planner(restarted, [{'reply': 'What inputs are available?', 'questions': ['Which formulation and receiving equipment?']}])
    queued_again = restarted.engineering_conversations.queue_retry(ctx, thread['id'])
    assert queued_again['turns'][0]['status'] == 'queued'
    resumed = restarted.engineering_conversations.run_turn(ctx, thread['id'], tid)
    assert len(resumed['turns']) == 1 and resumed['turns'][0]['status'] == 'needs_information'


def test_budget_rejected_before_execution_and_cdmo_history_cannot_be_rewritten(env):
    p, ctx = env
    workflow = simulate_workflow()
    workflow[1]['payload']['max_solver_calls'] = 64
    fake_planner(p, [{'reply': 'I will prepare this analysis.', 'workflow': workflow}])
    thread = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Use the example.', enable_demo=True)
    assert thread['turns'][-1]['status'] == 'blocked'
    assert not p.store.read().list(TENANT, 'physical_analysis_result')
    source = p.process_models.context(ctx, audience='cdmo_operation')
    workflow = [node('change_history', 'physical_context_variant', {'source_id': source['id'], 'label': 'Impossible retrospective cooling',
        'rationale': 'This change must be rejected because it rewrites observed history',
        'schedule': [{'time_h': 0, 'shelf_temperature_c': -40, 'chamber_pressure_pa': 10}]})]
    fake_planner(p, [{'reply': 'I will test the proposed intervention.', 'workflow': workflow}])
    thread = send(p, ctx, thread, 'Apply the cooling change', source_ids=[source['id']])
    assert thread['turns'][-1]['status'] == 'blocked'
    assert 'preserve observed operating history' in thread['turns'][-1]['steps'][0]['issues'][0]


def test_forecast_cannot_claim_an_earlier_cutoff_than_the_agent_was_shown(env):
    p, ctx = env
    source = p.process_models.context(ctx, audience='cdmo_operation', cutoff_h=6.)
    payload = {**plan(source['id']), 'evidence_cutoff_h': 4.}
    fake_planner(p, [{'reply': 'I will prepare the forecast.', 'workflow': [node('plan', 'physical_pipeline_prepare', payload)]}])
    thread = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Forecast at an earlier cutoff.', source_ids=[source['id']])
    assert thread['turns'][-1]['status'] == 'blocked'
    assert 'source evidence cutoff' in thread['turns'][-1]['steps'][0]['issues'][0]
    assert not p.store.read().list(TENANT, 'physical_analysis_plan')


def test_live_glm_source_dependency_is_replanned_before_execution(env, monkeypatch):
    """Actual Nov2 GLM contract failure; scripted correction tests host wiring only."""
    p, ctx = env
    source = p.process_models.context(ctx, audience='technology_transfer')
    text = Path(__file__).with_name('fixtures').joinpath('glm_attached_source_plan.json').read_text()
    invalid = json.loads(text.replace('ATTACHED_SOURCE_ID', source['id']))
    corrected = deepcopy(invalid)
    corrected['workflow'][0]['depends_on'] = []
    corrected['workflow'][0]['payload']['simulation_id'] = source['id']
    corrected['workflow'][1]['payload']['plan_id'] = binding('baseline_prepare')
    requests = []
    original = p.gateway.run
    def capture(req):
        requests.append(req)
        return original(req)
    monkeypatch.setattr(p.gateway, 'run', capture)
    fake = fake_planner(p, [invalid, corrected])
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}),
        'Run one baseline forecast and show the chart.', source_ids=[source['id']])
    turn = result['turns'][-1]
    assert turn['status'] == 'completed', turn['issues']
    assert len(turn['gateway_runs']) == 1  # Reuse the gateway repair loop, not a nested agent loop.
    assert turn['gateway_runs'][0]['attempts'][0]['rejected_output'] == invalid
    assert [a['status'] for a in turn['planning_attempts']] == ['rejected', 'accepted']
    assert source['id'] in turn['planning_attempts'][0]['validation_error']
    repair = json.loads(fake.calls[1]['prompt'])['plan_correction']
    assert repair['rejected_decision'] == invalid
    assert source['id'] in repair['validation_error']
    assert len(requests) == 1 and not requests[0].use_cache and requests[0].max_validation_repairs == 1
    assert len(p.store.read().list(TENANT, 'physical_analysis_result')) == 1
    assert not p.store.read().list(TENANT, 'action_intent')


def test_invalid_plan_correction_is_bounded_and_never_executes(env):
    p, ctx = env
    invalid = {'reply': 'I will run it.', 'workflow': [node('prepare', 'physical_pipeline_prepare',
        plan(binding('missing_source')), ['missing_source'])]}
    fake = fake_planner(p, [invalid, invalid])
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Evaluate the process.')
    turn = result['turns'][-1]
    assert turn['status'] == 'blocked' and turn['flow_run_id'] is None
    assert len(fake.calls) == 2
    assert [a['status'] for a in turn['planning_attempts']] == ['rejected', 'rejected']
    assert all(a['rejected_output'] == invalid for a in turn['gateway_runs'][0]['attempts'])
    assert 'No simulation has run' in turn['system_message']
    assert not turn['artifacts'] and not p.store.read().list(TENANT, 'data_flow')


def test_output_id_alias_is_repaired_before_creating_any_plan(env):
    p, ctx = env
    invalid = {'reply': 'I will calculate the result.', 'workflow': simulate_workflow()}
    invalid['workflow'][2]['payload']['plan_id'] = binding('select', 'plan_id')
    corrected = deepcopy(invalid)
    corrected['workflow'][2]['payload']['plan_id'] = binding('select')
    fake_planner(p, [invalid, corrected])
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Use the example.', enable_demo=True)
    turn = result['turns'][-1]
    assert turn['status'] == 'completed', turn['issues']
    assert 'path ["id"]' in turn['planning_attempts'][0]['validation_error']
    assert len(p.store.read().list(TENANT, 'physical_analysis_plan')) == 1
    assert len(p.store.read().list(TENANT, 'physical_analysis_result')) == 1


def test_binding_rejects_wrong_record_type_and_undeclared_dependency():
    from src.lifesci.process_engineering.conversation import EngineeringConversationService
    from src.lifesci.process_engineering.conversation_schemas import ChatDecision
    workflow = [node('source', 'physical_demo_context', {}),
                node('execute', 'physical_pipeline_execute', {'plan_id': binding('source')}, ['source'])]
    with pytest.raises(ValueError, match='requires an output'):
        EngineeringConversationService._validate_decision({'reply': 'Plan.', 'workflow': workflow})
    workflow = simulate_workflow()
    workflow[2]['depends_on'] = []
    with pytest.raises(ValueError, match='explicit dependency'):
        EngineeringConversationService._validate_workflow(ChatDecision.model_validate({'reply': 'Plan.', 'workflow': workflow}))


def test_valid_attached_source_needs_no_correction_and_prompt_explains_ids(env):
    p, ctx = env
    source = p.process_models.context(ctx, audience='technology_transfer')
    valid = {'reply': 'I will calculate the attached inputs.', 'workflow': [
        node('select', 'physical_pipeline_prepare', plan(source['id'])),
        node('execute', 'physical_pipeline_execute', {'plan_id': binding('select')}, ['select'])]}
    fake = fake_planner(p, [valid])
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Run a forecast.', source_ids=[source['id']])
    assert result['turns'][-1]['status'] == 'completed', result['turns'][-1]['issues']
    assert len(fake.calls) == 1
    prompt = json.loads(fake.calls[0]['prompt'])
    assert 'literal id string' in prompt['binding']['attached_record']
    assert 'language of the latest user message' in ' '.join(prompt['instructions'])
    assert 'plan_id/result_id wrapper' in prompt['binding']['output_id_field']
