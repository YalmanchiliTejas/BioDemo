"""Host contracts for the workbench: prepared profiles, fair-comparison checks, statistics, requirement-based gaps,
recorded usage, proposals from results, bounded explanations, templates run as flows, and work plans.

Records here are hand-made to exercise the rules. They are not manufacturing data and prove nothing scientific.
"""
import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.gateway import FakeProvider
from src.lifesci.gateway.registry import Qualification
from src.lifesci.store import ConflictError, RecordStore
from tests.lifesci.test_workflow_trial import delivery, glucose


@pytest.fixture
def world():
    p = Platform(RecordStore(), providers={})
    for actor in ('owner', 'colleague'):
        p.identity.assign_role('T', actor, 'msat', site_id='S1')
    p.identity.assign_role('T', 'qa-lead', 'qa', site_id='S1')
    p.identity.assign_role('T', 'outsider', 'msat', site_id='S2')
    return p, p.identity.context_for('T', 'owner')


def compare(source, **extra):
    return {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [source], 'parameter': 'Glucose', 'batches': ['A', 'B'], **extra}


def batch(p, ctx, name, status='completed', **fields):
    """A batch record as projected from the site's MES, which owns batch records here."""
    p.identity.assign_role('T', 'mes-sync', 'manufacturing_systems', site_id='S1')
    return p.execution.project_external(p.identity.context_for('T', 'mes-sync'), 'batch', name,
        {'batch_id': name, 'product': 'mAb-1', 'status': status, **fields}, source_system='mes', source_ref=f'mes/batches/{name}', site_id='S1')


# --- preparation and reuse ---------------------------------------------------------------------------------------

def test_delivery_profile_is_calculated_once_per_revision(world):
    p, ctx = world
    source = delivery(p, ctx, glucose(batches=('A', 'B'), points=4))
    first = p.workspace_tasks.profile(ctx, source, 'S1')
    assert first['prepared'] == 'calculated' and first['values'] == 8 and first['batches'] == ['A', 'B']
    assert first['parameters'] == [{'parameter': 'Glucose', 'units': ['g/L'], 'batches': 2, 'values': 8}]
    series = {s['batch']: s for s in first['series']}
    assert (series['A']['n'], series['A']['min'], series['A']['max'], series['A']['mean']) == (4, 7.0, 10.0, 8.5)
    assert first['time_range_h'] == [0.0, 3.0] and first['conflicting_sample_times'] == 0
    assert p.workspace_tasks.profile(ctx, source, 'S1')['prepared'] == 'reused'
    with pytest.raises(PermissionError):
        p.workspace_tasks.profile(p.identity.context_for('T', 'outsider'), source, 'S1')


def test_repeated_calculation_is_reused_and_dropped_when_a_dependency_changes(world):
    p, ctx = world
    source = delivery(p, ctx, glucose())
    batch(p, ctx, 'A', scale='2 L')
    first, second = p.workspace_tasks.compute(ctx, compare(source)), p.workspace_tasks.compute(ctx, compare(source))
    assert first['cache']['hit'] is False and second['cache']['hit'] is True
    assert second['data'] == first['data'] and second['source_refs'] == first['source_refs']
    assert p.workspace_tasks.compute(ctx, compare(source, limit=10))['cache']['hit'] is False  # a different request
    batch(p, ctx, 'B', scale='2 L')  # a batch record the comparison depends on now exists
    again = p.workspace_tasks.compute(ctx, compare(source))
    assert again['cache']['hit'] is False and again['data']['cohort']['batch_records_found'] == 2
    # Another person never receives this person's calculation.
    assert p.workspace_tasks.compute(p.identity.context_for('T', 'colleague'), compare(source))['cache']['hit'] is False


# --- comparison: window, alignment, statistics, context --------------------------------------------------------------

def test_time_window_alignment_and_statistics(world):
    p, ctx = world
    rows = [dict(id=f'a{t}', batch='A', time=t, parameter='Glucose', value=v, unit='g/L') for t, v in ((0, 10), (12, 8), (24, 6), (48, 2))]
    rows += [dict(id=f'b{t}', batch='B', time=t, parameter='Glucose', value=v, unit='g/L') for t, v in ((0.5, 9), (12.5, 8.5), (30, 5), (48, 1))]
    source = delivery(p, ctx, rows)
    exact = p.workspace_tasks.compute(ctx, compare(source))['data']
    assert exact['comparison_count'] == 1 and exact['alignment']['method'] == 'exact sample times'
    aligned = p.workspace_tasks.compute(ctx, compare(source, align_tolerance_h=1))['data']
    summary = aligned['comparison_summary'][0]
    assert summary['matched_times'] == 3  # 0↔0.5, 12↔12.5, 48↔48; 24 h has no sample within one hour
    assert [(c['time_h'], c['right_time_h'], c['difference']) for c in aligned['comparisons']] == [(0.0, 0.5, -1.0), (12.0, 12.5, 0.5), (48.0, 48.0, -1.0)]
    stats = summary['statistics']
    assert stats['n'] == 3 and stats['mean'] == pytest.approx(-0.5) and stats['median'] == -1.0
    assert stats['standard_deviation'] == pytest.approx(0.8660254) and 'not independent' in stats['note']
    assert 'nearest within 1 h' in summary['difference_definition'] and 'not interpolated' in aligned['limitations'][1]
    window = p.workspace_tasks.compute(ctx, compare(source, align_tolerance_h=1, time_from_h=10, time_to_h=40))['data']
    assert window['comparison_count'] == 1 and window['time_window_h'] == [10, 40] and window['measurement_count'] == 4
    with pytest.raises(ValueError, match='start before'):
        p.workspace_tasks.compute(ctx, compare(source, time_from_h=40, time_to_h=10))


def test_comparison_reports_whether_the_batches_share_their_context(world):
    p, ctx = world
    source = delivery(p, ctx, glucose())
    unknown = p.workspace_tasks.execute(ctx, compare(source))
    assert unknown['data']['cohort']['verdict'] == 'not_established' and unknown['task_status'] == 'completed'
    assert 'Scale' in unknown['data']['cohort']['not_recorded']  # not recorded is never assumed equal
    batch(p, ctx, 'A', scale='2 L', process_version='v3', equipment_id='BR-01', process_stage='production')
    batch(p, ctx, 'B', scale='200 L', process_version='v3', equipment_id='BR-07', process_stage='production')
    differs = p.workspace_tasks.execute(ctx, compare(source))
    cohort = differs['data']['cohort']
    assert cohort['verdict'] == 'differs' and cohort['differs'] == ['Equipment', 'Scale']
    by = {a['attribute']: a for a in cohort['attributes']}
    assert by['scale']['values'] == {'A': '2 L', 'B': '200 L'} and by['process_version']['verdict'] == 'same'
    assert differs['task_status'] == 'needs_information' and differs['issues'][0]['code'] == 'cohort_differs'
    assert {r['kind'] for r in differs['source_refs']} == {'evidence', 'batch'}  # the context is cited


# --- gaps against approved requirements ------------------------------------------------------------------------------

def test_gaps_are_checked_against_approved_specifications_and_drafted_as_a_request(world):
    p, ctx = world
    rows = glucose(batches=('A', 'B')) + [dict(id='c0', batch='C', time=0, parameter='pH', value=7, unit='pH')]
    source = delivery(p, ctx, rows)
    task = {'site_id': 'S1', 'operation': 'check_gaps', 'dataset_ids': [source]}
    assert p.workspace_tasks.execute(ctx, task)['issues'][0]['code'] == 'expectations_required'  # nothing approved, nothing typed
    p.specifications.create(ctx, site_id='S1', parameter='Glucose', unit='g/L', low=1, high=12, reason='batch record limits')
    p.specifications.create(ctx, site_id='S1', parameter='Lactate', unit='g/L', high=3, reason='batch record limits')
    batch(p, ctx, 'C', status='in_progress')
    out = p.workspace_tasks.execute(ctx, task)
    data = out['data']
    assert data['expectation_basis'] == 'approved_specifications' and data['requirements_checked'] == 2
    found = {(g.get('batch'), g['parameter']): g['status'] for g in data['gaps']}
    assert found == {(None, 'Lactate'): 'unavailable', ('C', 'Glucose'): 'not_yet_known'}
    assert data['gap_status_counts'] == {'not_yet_known': 1, 'unavailable': 1}
    assert {r['kind'] for r in out['source_refs']} == {'evidence', 'specification'}
    draft = data['draft_request']
    assert draft['status'] == 'draft_not_sent' and '- Glucose for C' in draft['description'] and '- Lactate' in draft['description']
    assert not p.store.read().list('T', 'assistant_work_request')  # drafting sends nothing
    sent = p.workspace_tasks.request_evidence(ctx, out['id'], {'owner_id': 'colleague'})
    assert sent['owner_id'] == 'colleague' and sent['title'] == draft['title']
    with pytest.raises(ValueError, match='no missing evidence'):
        p.workspace_tasks.request_evidence(ctx, p.workspace_tasks.execute(ctx, compare(source))['id'], {'owner_id': 'colleague'})


# --- impact: what was recorded as used ---------------------------------------------------------------------------------

def test_recorded_usage_is_distinguished_from_a_mention(world):
    p, ctx = world
    for name in ('B-1', 'B-2'):
        batch(p, ctx, name)
    with p.store.transaction('owner') as tx:  # an executed step, as the execution service records it
        tx.put('T', 'procedure_instance', 'inst-1', {'site_id': 'S1', 'context': {'batch_id': 'B-1'}, 'status': 'completed'},
               expected_revision=None, action='test')
        tx.put('T', 'step_execution', 'inst-1:feed:1', {'instance_id': 'inst-1', 'step_id': 'feed', 'performed_at': '2026-11-01T09:00:00Z',
               'resources': {'lots': [{'lot_id': 'LOT-7781'}], 'equipment': [{'equipment_id': 'BR-07'}]}},
               expected_revision=None, action='test')
    p.evidence.ingest(ctx, source_system='email', source_record_id='note-1', content=b'x', media_type='text/plain', site_id='S1',
                      event_time='2026-11-02T00:00:00Z', metadata={'note': 'Supplier asked about LOT-7781'})
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'trace_impact', 'record_id': 'lot 7781'.replace(' ', '-')})
    data = out['data']
    assert data['affected_batches'] == ['B-1'] and data['recorded_usage'][0]['basis'] == 'recorded_usage'
    assert data['recorded_usage'][0]['used_as'] == 'material lot' and data['recorded_usage'][0]['step_id'] == 'feed'
    assert [r['kind'] for r in data['records']] == ['evidence']  # the email only mentions it: a candidate, not usage
    assert data['genealogy']['complete'] is False and data['genealogy']['examples'] == ['B-2']
    assert data['exposure_confirmed'] is False and data['causal_claim_supported'] is False
    assert {'kind': 'procedure_instance', 'id': 'inst-1', 'revision': 1, 'site_id': 'S1'} in out['source_refs']
    none = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'trace_impact', 'record_id': 'LOT-0000'})
    assert none['data']['genealogy']['status'] == 'no_recorded_usage' and none['data']['affected_batches'] == []


# --- several tasks for one question, as a flow ------------------------------------------------------------------------

def test_template_runs_its_tasks_through_the_flow_runtime_and_saves_each_result(world):
    p, ctx = world
    source = delivery(p, ctx, glucose())
    p.specifications.create(ctx, site_id='S1', parameter='Glucose', unit='g/L', low=1, high=12, reason='limits')
    out = p.workspace_tasks.run_template(ctx, 'batch_picture', {'site_id': 'S1', 'dataset_ids': [source], 'parameter': 'Glucose', 'batches': ['A', 'B']})
    assert out['status'] == 'completed' and set(out['results']) == {'reconcile', 'compare', 'gaps'} and out['model_calls'] == 0
    assert out['results']['compare']['data']['comparison_count'] == 3 and out['results']['gaps']['data']['gap_count'] == 0
    run = p.store.read().require('T', 'data_flow_run', out['flow_run_id']).state
    assert run['status'] == 'completed' and set(run['results']) == {'reconcile', 'compare', 'gaps'}
    assert all(p.workspace_tasks.get(ctx, r['id'])['status'] == 'current' for r in out['results'].values())
    assert [t['id'] for t in p.workspace_tasks.templates()] == ['batch_picture']
    with pytest.raises(KeyError):
        p.workspace_tasks.run_template(ctx, 'unknown', {'site_id': 'S1'})


# --- from a result to a reviewed action -----------------------------------------------------------------------------------

def test_result_becomes_a_proposal_that_only_an_authorized_person_approves(world):
    p, ctx = world
    result = p.workspace_tasks.execute(ctx, compare(delivery(p, ctx, glucose())))
    assert p.workspace_tasks.get(ctx, result['id'])['work_status'] == 'complete'
    proposal = p.workspace_tasks.propose(ctx, result['id'], {
        'operation': 'close_deviation', 'target_id': 'DEV-77', 'rationale': 'Glucose in B tracks A within 1 g/L.',
        'expected_result': 'Deviation closed with the comparison attached.'})
    assert proposal['status'] == 'proposed' and proposal['required_roles'] == ['qa'] and proposal['execution_status'] == 'not_started'
    assert proposal['basis'][0] == {'kind': 'workspace_task_result', 'id': result['id'], 'revision': 1, 'site_id': 'S1'}
    waiting = p.workspace_tasks.get(ctx, result['id'])
    assert waiting['work_status'] == 'needs_approval' and waiting['proposals'][0]['status'] == 'proposed'
    assert not p.store.read().list('T', 'action_intent')  # nothing is carried out by proposing
    with pytest.raises(Exception):  # the proposer's role cannot approve a QA action
        p.actions.decide(ctx, proposal['proposal_id'], expected_revision=1, decision='approved', role='qa', authentication={'method': 'password'})
    p.actions.decide(p.identity.context_for('T', 'qa-lead'), proposal['proposal_id'], expected_revision=1, decision='approved', role='qa', authentication={'method': 'password'})
    approved = p.workspace_tasks.get(ctx, result['id'])
    assert approved['proposals'][0]['status'] == 'approved' and approved['work_status'] == 'complete'


def test_proposal_from_values_in_review_or_changed_evidence_says_so_or_is_refused(world):
    p, ctx = world
    rows = glucose()
    review = {'pending_values': 6, 'rejected_values': 0, 'open_issues': 2, 'open_issue_counts': {}, 'verified_package': False}
    source = delivery(p, ctx, rows, provisional=review)
    result = p.workspace_tasks.execute(ctx, compare(source, include_unverified=True))
    body = {'operation': 'request_review', 'target_id': 'B', 'rationale': 'r', 'expected_result': 'e'}
    assert any('still in review' in c for c in p.workspace_tasks.propose(ctx, result['id'], body)['constraints'])
    delivery(p, ctx, rows[:-1], provisional=review)  # the delivery changed: same record, new revision
    with pytest.raises(ValueError, match='changed'):
        p.workspace_tasks.propose(ctx, result['id'], body)


# --- one bounded explanation ------------------------------------------------------------------------------------------------

def explainer(p, replies):
    fake = FakeProvider(name='anthropic')
    p.gateway.providers['anthropic'] = fake
    p.gateway.registry.qualify(Qualification('comparison_explanation', 'anthropic-sonnet', 'unit-test-only', True,
        {'contract': 1.}, {'contract': 1.}, 'Test double, not a measured model', 'test'))
    fake.scripts[p.gateway.registry.profiles['anthropic-sonnet'].model] = [json.dumps(r) for r in replies]
    return fake


def test_explanation_is_one_call_and_its_numbers_must_come_from_the_result(world):
    p, ctx = world
    result = p.workspace_tasks.execute(ctx, compare(delivery(p, ctx, glucose())))
    good = {'explanation': 'Glucose in B is 1 g/L lower than in A at each of the 3 matched times.',
            'observations': ['Mean difference -1 g/L'], 'hypotheses': [{'statement': 'B may have a higher cell density.', 'check': 'Compare viable cell density.'}],
            'unknowns': ['Why the difference exists.'], 'source_refs': [result['id']]}
    fake = explainer(p, [good])
    out = p.workspace_tasks.explain(ctx, result['id'], 'Is B consuming more glucose?')
    assert out['status'] == 'completed' and out['model_calls'] == 1 and len(fake.calls) == 1
    assert out['hypotheses'] == [{'statement': 'B may have a higher cell density.', 'check': 'Compare viable cell density.', 'kind': 'hypothesis'}]
    assert out['timing']['target_seconds'] == 10.0 and out['requires_human_review'] is True
    sent = fake.calls[0]['prompt']
    assert '"comparison_summary"' in sent and 'Is B consuming more glucose?' in sent


def test_explanation_with_an_invented_number_is_withheld(world):
    p, ctx = world
    result = p.workspace_tasks.execute(ctx, compare(delivery(p, ctx, glucose())))
    invented = {'explanation': 'Glucose in B is 37.5 % lower than in A.', 'observations': [], 'hypotheses': [], 'unknowns': [],
                'source_refs': [result['id']]}
    fake = explainer(p, [invented, invented])
    out = p.workspace_tasks.explain(ctx, result['id'])
    assert out['status'] == 'withheld' and '37.5' in out['reason'] and 'explanation' not in out
    assert len(fake.calls) == 2  # one correction was allowed, then the reply was withheld rather than shown


# --- the working file ---------------------------------------------------------------------------------------------------------

def test_work_plan_keeps_results_steps_and_where_each_stands(world):
    p, ctx = world
    result = p.workspace_tasks.execute(ctx, compare(delivery(p, ctx, glucose())))
    plan = p.work_plans.create(ctx, {'site_id': 'S1', 'title': 'Glucose in B', 'selection': {'parameter': 'Glucose', 'batches': ['A', 'B']}})
    plan = p.work_plans.add_step(ctx, plan['id'], {'expected_revision': plan['revision'], 'kind': 'check',
                                                   'text': 'Compare viable cell density', 'result_id': result['id'], 'basis': 'B is 1 g/L lower'})
    assert plan['results'][0]['id'] == result['id'] and plan['steps'][0]['stands'] == 'to do'
    proposal = p.workspace_tasks.propose(ctx, result['id'], {'operation': 'close_deviation', 'target_id': 'DEV-77', 'rationale': 'r', 'expected_result': 'e'})
    plan = p.work_plans.add_step(ctx, plan['id'], {'expected_revision': plan['revision'], 'kind': 'action', 'text': 'Close DEV-77',
                                                   'result_id': result['id'], 'proposal_id': proposal['proposal_id']})
    assert plan['steps'][1]['stands'] == 'waiting for approval' and plan['progress']['waiting_for_approval'] == 1
    p.actions.decide(p.identity.context_for('T', 'qa-lead'), proposal['proposal_id'], expected_revision=1, decision='approved', role='qa', authentication={'method': 'password'})
    plan = p.work_plans.get(ctx, plan['id'])
    assert plan['steps'][1]['stands'] == 'approved, not yet carried out'  # approval is not execution
    step = plan['steps'][0]['step_id']
    plan = p.work_plans.update_step(ctx, plan['id'], step, {'expected_revision': plan['revision'], 'status': 'done', 'outcome': 'VCD matched'})
    assert plan['steps'][0]['stands'] == 'done' and plan['steps'][0]['done_at'] and plan['progress'] == {
        'open': 1, 'done': 1, 'to_do': 0, 'waiting_for_approval': 0, 'waiting_for_reply': 0}
    # An approved proposal is carried out by the action service, so its step cannot be ticked off by hand.
    assert plan['steps'][1]['can_complete'] is False and plan['steps'][1]['waiting_on'] == 'execution'
    assert [x['id'] for x in p.work_plans.list(ctx, 'S1')] == [plan['id']]
    with pytest.raises(ConflictError):
        p.work_plans.add_step(ctx, plan['id'], {'expected_revision': 1, 'text': 'stale edit'})
    colleague = p.identity.context_for('T', 'colleague')
    assert p.work_plans.list(colleague, 'S1') == []
    with pytest.raises(Exception):
        p.work_plans.get(colleague, plan['id'])


# --- the person, not the assistant, includes values in review -------------------------------------------------------------------

def test_assistant_can_use_values_in_review_only_when_the_person_chose_that_for_the_message(world):
    p, ctx = world
    review = {'pending_values': 6, 'rejected_values': 0, 'open_issues': 2, 'open_issue_counts': {}, 'verified_package': False}
    source = delivery(p, ctx, glucose(), provisional=review)
    task = {'operation': 'compare', 'site_id': 'S1', 'dataset_ids': [source], 'parameter': 'Glucose', 'batches': ['A', 'B'], 'include_unverified': True}
    def turn(**message):
        thread = p.engineering_conversations.create(ctx, {'site_id': 'S1'})
        queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'What changed in glucose?', 'expected_revision': thread['revision'], **message})
        p.engineering_conversations._update_turn(ctx, queued['turn_ids'][-1], status='running')
        return queued['turn_ids'][-1]
    with pytest.raises(PermissionError, match='person chose'):
        p.engineering_conversations._operator('workspace_run_task')(ctx, {'_turn_id': turn(), **task})
    out = p.engineering_conversations._operator('workspace_run_task')(ctx, {'_turn_id': turn(include_unverified=True), **task})['output']
    assert out['evidence_state'] == 'provisional' and out['data']['comparison_count'] == 3


def test_preview_calculates_the_picture_without_saving_and_actions_name_their_approvers(world):
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    p, ctx = world
    source = delivery(p, ctx, glucose())
    client, headers = TestClient(create_app(p)), {'X-Tenant-Id': 'T', 'X-Actor-Id': 'owner'}
    selection = {'site_id': 'S1', 'dataset_ids': [source], 'parameter': 'Glucose', 'batches': ['A', 'B']}
    preview = client.post('/v1/workspace-tasks/templates/batch_picture/preview', headers=headers, json={'selection': selection}).json()
    assert preview['saved'] is False and set(preview['results']) == {'reconcile', 'compare', 'gaps'}
    assert 'id' not in preview['results']['compare'] and len(preview['results']['reconcile']['data']['series']) == 2
    assert not p.store.read().list('T', 'workspace_task_result') and not p.store.read().list('T', 'data_flow_run')
    kept = client.post('/v1/workspace-tasks/templates/batch_picture/run', headers=headers, json={'selection': selection}).json()
    assert kept['results']['compare']['id'] and kept['results']['compare']['work_status'] == 'complete'
    profile = client.get(f'/v1/workspace-tasks/deliveries/{source}/profile', headers=headers, params={'site_id': 'S1'}).json()
    assert profile['values'] == 6 and profile['verification'] == 'verified'
    actions = client.get('/v1/workspace-tasks/actions', headers=headers).json()
    assert {'operation': 'close_deviation', 'label': 'Close deviation', 'risk': 'high', 'approved_by': ['qa'], 'approved_by_words': ['QA']} in actions['operations']
    assert any(a['label'] == 'Approve CAPA' for a in actions['operations'])
    looked = client.post('/v1/workspace-tasks/preview', headers=headers, json={**selection, 'operation': 'reconcile', 'batches': ['A'],
                                                                           'time_from_h': 1, 'time_to_h': 1, 'limit': 5}).json()
    assert looked['saved'] is False and 'id' not in looked and len(looked['data']['measurements']) == 1  # the source of one value
    assert looked['data']['measurements'][0]['sources'][0]['evidence_id'] == source
    assert len(p.store.read().list('T', 'workspace_task_result')) == 3  # only the three kept by the template run
    plan = client.post('/v1/work-plans', headers=headers, json={'site_id': 'S1', 'title': 'Glucose', 'selection': selection}).json()
    step = client.post(f"/v1/work-plans/{plan['id']}/steps", headers=headers, json={
        'expected_revision': plan['revision'], 'text': 'Check VCD', 'result_id': kept['results']['compare']['id']}).json()
    assert step['steps'][0]['stands'] == 'to do' and client.get('/v1/work-plans', headers=headers, params={'site_id': 'S1'}).json()['plans'][0]['open_steps'] == 1


def test_explanation_role_can_use_its_own_reasoning_effort_without_touching_the_assistant():
    from src.lifesci.gateway import default_registry
    from src.lifesci.gateway.configuration import INTERPRETER_PROVIDER, configure_engineering_llms
    base = {'LIFESCI_LLM_PROVIDER': 'modal', 'LIFESCI_LLM_MODEL': 'zai-org/GLM-5.3', 'MODAL_BASE_URL': 'https://example.invalid/v1'}
    plain = default_registry()
    configure_engineering_llms(plain, base)
    assert {plain.profiles[f'engineering-{r}'].provider for r in ('planner', 'interpreter')} == {'modal'}
    split = default_registry()
    configure_engineering_llms(split, {**base, 'LIFESCI_INTERPRETER_REASONING_EFFORT': 'low'})
    assert split.profiles['engineering-planner'].provider == 'modal'              # the assistant is unchanged
    assert split.profiles['engineering-interpreter'].provider == INTERPRETER_PROVIDER
    assert split.profiles['engineering-interpreter'].version != plain.profiles['engineering-interpreter'].version
    for word in ('turbo', 'default', ''):                       # not one of the model's levels: nothing is sent
        ignored = default_registry()
        configure_engineering_llms(ignored, {**base, 'LIFESCI_INTERPRETER_REASONING_EFFORT': word})
        assert ignored.profiles['engineering-interpreter'].provider == 'modal', word
    for level in ('high', 'max'):                               # GLM-5.3's other two levels
        other = default_registry()
        configure_engineering_llms(other, {**base, 'LIFESCI_INTERPRETER_REASONING_EFFORT': level})
        assert other.profiles['engineering-interpreter'].provider == INTERPRETER_PROVIDER, level


def test_explanation_with_a_flagged_sentence_is_shown_with_a_caution_not_withheld(world):
    p, ctx = world
    result = p.workspace_tasks.execute(ctx, compare(delivery(p, ctx, glucose())))
    flagged = {'explanation': 'The largest gap is -1 g/L at 0 h, where A reads 10 g/L and B reads 9 g/L.', 'observations': [],
               'hypotheses': [], 'unknowns': [], 'source_refs': [result['id']]}
    fake = explainer(p, [flagged])
    out = p.workspace_tasks.explain(ctx, result['id'])
    assert out['status'] == 'completed' and len(fake.calls) == 1 and isinstance(out['cautions'], list)


def test_explanation_may_round_a_figure_but_not_invent_one(world):
    p, ctx = world
    rows = [dict(id=f'{b}{t}', batch=b, time=t, parameter='Glucose', value=v, unit='cells/mL')
            for b, values in (('A', (1466667, 9930000)), ('B', (1634478, 8813333))) for t, v in enumerate(values)]
    result = p.workspace_tasks.execute(ctx, compare(delivery(p, ctx, rows)))
    rounded = {'explanation': 'B starts 167800 cells/mL above A and ends about 1.117e6 cells/mL below it.', 'observations': [],
               'hypotheses': [], 'unknowns': [], 'source_refs': [result['id']]}
    explainer(p, [rounded])
    assert p.workspace_tasks.explain(ctx, result['id'])['status'] == 'completed'  # 167,811 and 1,116,667 to four digits
    other = p.workspace_tasks.execute(ctx, compare(delivery(p, ctx, rows, name='second'), limit=10))
    explainer(p, [{**rounded, 'explanation': 'B starts 170000 cells/mL above A.', 'source_refs': [other['id']]}] * 2)
    assert p.workspace_tasks.explain(ctx, other['id'])['status'] == 'withheld'    # two digits stand for nothing in the result


def test_chat_answers_a_question_first_from_the_calculated_comparison_then_hands_follow_ups_to_the_assistant(world, monkeypatch):
    from tests.lifesci.test_engineering_conversation import fake_planner
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p, ctx = world
    delivery(p, ctx, glucose())
    quick = {'explanation': 'Glucose is 1 g/L lower in B than in A at each of the 3 matched times.', 'observations': [],
             'hypotheses': [{'statement': 'B may hold more cells.', 'check': 'Compare viable cell density.'}],
             'unknowns': ['Why the difference exists.'], 'source_refs': []}
    fake = explainer(p, [quick])
    thread = p.engineering_conversations.create(ctx, {'site_id': 'S1'})
    def ask(text):
        current = p.engineering_conversations.get(ctx, thread['id'])
        queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': text, 'expected_revision': current['revision']})
        p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
        return p.engineering_conversations.get(ctx, thread['id'])['turns'][-1]
    first = ask('Why is Glucose lower in B than A?')
    assert first['status'] == 'completed' and first['response_mode'] == 'bounded_explanation'
    assert first['reply'].startswith('Glucose is 1 g/L lower in B') and 'Check: Compare viable cell density.' in first['reply']
    assert 'no other record was read' in first['reply'] and len(fake.calls) == 1
    assert first['timing']['path'] == 'explanation' and first['timing']['model_calls'] == 1
    assert [s['title'] for s in first['steps']][1] == 'Explained the calculated comparison'
    assert first['artifacts'][0]['kind'] == 'workspace_task_result'
    # The follow-up is the assistant's, even though it again names the delivery's parameter.
    planner = fake_planner(p, [])
    planner.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = ['No related deviation or case names A or B.']
    second = ask('Why is Glucose lower in B than A? Look further.')
    assert second.get('response_mode') != 'bounded_explanation' and second['timing']['path'] == 'assistant'


def test_withheld_quick_answer_falls_back_to_the_assistant_and_can_be_switched_off(world, monkeypatch):
    from tests.lifesci.test_engineering_conversation import fake_planner
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p, ctx = world
    delivery(p, ctx, glucose())
    invented = {'explanation': 'Glucose is 37.5 % lower in B.', 'observations': [], 'hypotheses': [], 'unknowns': [], 'source_refs': []}
    planner = fake_planner(p, [])  # one scripted provider serves both roles; each model has its own script
    planner.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = ['Glucose is 1 g/L lower in B at 0, 1 and 2 h.'] * 2
    p.gateway.registry.qualify(Qualification('comparison_explanation', 'anthropic-sonnet', 'unit-test-only', True,
        {'contract': 1.}, {'contract': 1.}, 'Test double, not a measured model', 'test'))
    planner.scripts[p.gateway.registry.profiles['anthropic-sonnet'].model] = [json.dumps(invented)] * 2
    def ask(text):
        thread = p.engineering_conversations.create(ctx, {'site_id': 'S1'})
        queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': text, 'expected_revision': thread['revision']})
        p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
        return p.engineering_conversations.get(ctx, thread['id'])['turns'][-1]
    turn = ask('Why is Glucose lower in B than A?')
    assert turn['status'] == 'completed' and turn.get('response_mode') != 'bounded_explanation'  # the assistant answered
    assert '37.5' not in turn['reply'] and any('37.5' in ' '.join(s['issues']) for s in turn['steps'])  # and the reason is on record
    monkeypatch.setenv('ASSISTANT_QUICK_ANSWERS', 'off')
    off = ask('Why is Glucose lower in B than A?')
    assert all(s['title'] != 'Explained the calculated comparison' for s in off['steps'])


# --- a request is two-way: the person asked sees it and replies -------------------------------------------------------

def _gap_request(p, ctx, to='colleague'):
    rows = glucose(batches=('A', 'B'))
    source = delivery(p, ctx, rows)
    if not p.specifications.list(ctx, site_id='S1'):
        p.specifications.create(ctx, site_id='S1', parameter='Lactate', unit='g/L', high=3, reason='batch record limits')
    result = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'check_gaps', 'dataset_ids': [source]})
    return result, p.workspace_tasks.request_evidence(ctx, result['id'], {'owner_id': to})


def test_request_reaches_the_person_asked_who_replies_once_and_the_step_reads_reply_received(world):
    p, ctx = world
    colleague = p.identity.context_for('T', 'colleague')
    result, sent = _gap_request(p, ctx)
    assert sent['status'] == 'open'
    told = p.alerts.inbox(colleague)['items']
    assert [(i['kind'], i['link']) for i in told] == [('work_request', '/dashboard/')] and told[0]['title'].startswith('owner asked you: ')
    plan = p.work_plans.create(ctx, {'site_id': 'S1', 'title': 'Missing lactate', 'selection': {}})
    plan = p.work_plans.add_step(ctx, plan['id'], {'expected_revision': plan['revision'], 'kind': 'request', 'text': 'Ask colleague',
                                                   'result_id': result['id'], 'work_request_id': sent['id']})
    assert plan['steps'][0]['stands'] == 'waiting for a reply' and plan['progress']['waiting_for_reply'] == 1

    reply = {'expected_revision': sent['revision'], 'reply': '  Lactate was not sampled on this run; see LIMS-4411.  '}
    for other in (ctx, p.identity.context_for('T', 'qa-lead')):   # the requester and a bystander cannot answer for them
        with pytest.raises(PermissionError):
            p.assistant_routines.answer_work_request(other, sent['id'], reply)
    with pytest.raises(ConflictError):
        p.assistant_routines.answer_work_request(colleague, sent['id'], {**reply, 'expected_revision': 99})
    answered = p.assistant_routines.answer_work_request(colleague, sent['id'], reply)
    assert (answered['status'], answered['reply'], answered['answered_by']) == ('answered', 'Lactate was not sampled on this run; see LIMS-4411.', 'colleague')
    assert answered['answered_at'] and answered['title'] == sent['title']                    # the request itself is unchanged
    with pytest.raises(ValueError, match='already answered'):
        p.assistant_routines.answer_work_request(colleague, sent['id'], {'expected_revision': answered['revision'], 'reply': 'again'})

    assert [i['title'] for i in p.alerts.inbox(ctx)['items']] == [f"colleague replied: {sent['title']}"]
    step = p.work_plans.get(ctx, plan['id'])['steps'][0]
    assert step['stands'] == 'reply received' and step['can_complete'] and step['waiting_on'] is None
    assert step['request']['reply'].startswith('Lactate was not sampled') and step['request']['status'] == 'answered'


def test_the_same_gaps_can_be_asked_of_a_second_person(world):
    p, ctx = world
    p.identity.assign_role('T', 'third', 'msat', site_id='S1')
    result, first = _gap_request(p, ctx)
    again = p.workspace_tasks.request_evidence(ctx, result['id'], {'owner_id': 'colleague'})
    assert again['id'] == first['id']                                                        # a repeat is the same request
    second = p.workspace_tasks.request_evidence(ctx, result['id'], {'owner_id': 'third'})
    assert second['id'] != first['id'] and second['owner_id'] == 'third'


def test_a_trace_with_no_batch_records_at_the_site_is_not_reported_as_complete(world):
    """An empty batch list has no batch without recorded steps. That must not read as "nothing was exposed"."""
    p, ctx = world
    p.evidence.ingest(ctx, source_system='email', source_record_id='note-2', content=b'x', media_type='text/plain', site_id='S1',
                      event_time='2026-11-02T00:00:00Z', metadata={'note': 'Supplier asked about LOT-9001'})
    genealogy = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'trace_impact', 'record_id': 'LOT-9001'})['data']['genealogy']
    assert genealogy['complete'] is False and genealogy['batches_without_usage_records'] == 0
    assert 'No batch records are held here for this site' in genealogy['note']
    batch(p, ctx, 'B-1')                                          # one batch, with no recorded steps: still not complete, and it says why
    again = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'trace_impact', 'record_id': 'LOT-9001'})['data']['genealogy']
    assert again['complete'] is False and '1 batches at this site have no recorded steps' in again['note']
