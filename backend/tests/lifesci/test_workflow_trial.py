"""Host contracts for the trial additions: the optional decision model (option C), complete results, deliveries
still in review, cause screening, typed-request routing and request timing.

The decision provider here is a scripted stand-in. These tests establish what the host does with an answer; they say
nothing about how good the real model's answers are.
"""
import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.gateway.decisions import (DEFAULT_MODEL, UNKNOWN, DecisionAdapter, DecisionRequest, JevProvider,
                                            Question, load_calibration)
from src.lifesci.gateway.providers import ProviderError
from src.lifesci.store import RecordStore


class Scripted:
    """Answers each question from a script: {question name: answer}, or a callable(questions) -> answers."""
    name = 'scripted'

    def __init__(self, script, *, model=DEFAULT_MODEL, error=None):
        self.script, self.model, self.error, self.calls = script, model, error, []

    def decide(self, *, model, state, questions, timeout_s):
        self.calls.append({'model': model, 'state': state, 'questions': questions, 'timeout_s': timeout_s})
        if self.error:
            raise self.error
        answers = self.script(questions) if callable(self.script) else {name: self.script[name] for name in questions}
        return {'model': self.model, 'answers': answers, 'usage': {'input_tokens': 100, 'output_tokens': 10}}


def choice(value, probability=0.99, others=()):
    rest = {o: (1 - probability) / max(len(others), 1) for o in others}
    return {'type': 'choice', 'choice': value, 'confidence': probability, 'probabilities': {value: probability, **rest}}


def calibrated(task, threshold=0.9, model=DEFAULT_MODEL):
    return {task: {'model': model, 'threshold': threshold, 'eval_id': 'held-out-test', 'held_out_n': 50}}


@pytest.fixture
def world():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'owner', 'msat', site_id='S1')
    p.identity.assign_role('T', 'outsider', 'msat', site_id='S2')
    return p, p.identity.context_for('T', 'owner')


def use(p, provider, calibration=None):
    p.gateway.decisions = DecisionAdapter(p.gateway, provider, enabled=True, calibration=calibration or {})
    return provider


def delivery(p, ctx, rows, name='October delivery', site='S1', provisional=None):
    meta = {'classification': 'provisional_cmo_dataset' if provisional else 'verified_cmo_dataset', 'cmo': 'Source lab',
            'delivery_name': name, 'batches': sorted({r['batch'] for r in rows}),
            'parameters': sorted({r['parameter'] for r in rows})}
    data = {'schema_version': 'platform-provisional-cmo-1' if provisional else 'platform-verified-cmo-1', 'run_id': name,
            'cmo': 'Source lab', 'guarantee': {'holds': not provisional, 'checks': []}, 'measurements': rows}
    if provisional:
        data['review'] = meta['review'] = provisional
    return p.evidence.ingest(ctx, source_system='cmo-provisional-delivery' if provisional else 'cmo-verified-delivery',
        source_record_id=name, content=json.dumps(data).encode(), media_type='application/json', site_id=site,
        event_time='2026-11-01T00:00:00Z', metadata=meta)['evidence_id']


def glucose(batches=('A', 'B'), points=3):
    return [dict(id=f'{b}{t}', batch=b, time=t, parameter='Glucose', value=10 - t - i, unit='g/L')
            for i, b in enumerate(batches) for t in range(points)]


# --- option C: the decision adapter -----------------------------------------------------------------------------

def test_adapter_is_off_by_default_and_tasks_are_unchanged(world):
    p, ctx = world
    assert p.gateway.decisions.enabled is False
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [delivery(p, ctx, glucose())],
                                          'parameter': 'sugar', 'batches': ['A', 'B']})
    assert out['decisions'] == [] and out['decision_model_calls'] == 0 and out['model_calls'] == 0
    assert any(i['code'] == 'missing_requested_parameter' for i in out['issues'])


def test_uncalibrated_answer_is_a_suggestion_and_is_never_applied(world):
    p, ctx = world
    provider = use(p, Scripted({'parameter': choice('Glucose', 0.99)}))
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [delivery(p, ctx, glucose())],
                                          'parameter': 'sugar', 'batches': ['A', 'B']})
    assert out['task_status'] == 'needs_information' and out['data']['comparison_count'] == 0
    suggestion = next(i for i in out['issues'] if i['code'] == 'parameter_needs_confirmation')
    assert suggestion['suggested'] == 'Glucose' and 'parameter_used' not in out['data']
    answer = out['decisions'][0]['answers'][0]
    assert answer['status'] == 'advisory' and out['decisions'][0]['model'] == DEFAULT_MODEL
    # The model saw recorded names and the request only, and unknown was offered.
    asked = provider.calls[0]['questions']['parameter']
    assert set(asked['criteria']) == {'Glucose', UNKNOWN} and 'untrusted data' in asked['instructions']


def test_calibrated_answer_is_applied_and_audited(world):
    p, ctx = world
    use(p, Scripted({'parameter': choice('Glucose', 0.97)}), calibrated('field_meaning'))
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [delivery(p, ctx, glucose())],
                                          'parameter': 'sugar', 'batches': ['A', 'B']})
    assert out['task_status'] == 'completed' and out['data']['parameter_used'] == 'Glucose'
    assert out['data']['comparison_count'] == 3 and out['decisions'][0]['answers'][0]['status'] == 'accepted'
    trace = p.store.read().require('T', 'model_run', out['decisions'][0]['run_id']).state
    assert trace['task_kind'] == 'bounded_decision' and trace['status'] == 'completed'
    assert trace['attempts'][0]['decisions'][0]['value'] == 'Glucose' and trace['input_manifest'][0]['revision'] == 1


@pytest.mark.parametrize('answer, model, reason', [
    (choice('Glucose', 0.6), DEFAULT_MODEL, 'below the calibrated threshold'),
    (choice('Glucose', 0.99), 'jev-1.13.0', 'calibrated for'),
    (choice(UNKNOWN, 0.99), DEFAULT_MODEL, 'could not decide'),
])
def test_low_confidence_drift_and_unknown_are_flagged_not_applied(world, answer, model, reason):
    p, ctx = world
    use(p, Scripted({'parameter': answer}, model=model), calibrated('field_meaning'))
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'reconcile', 'dataset_ids': [delivery(p, ctx, glucose())],
                                          'parameter': 'sugar'})
    assert 'parameter_used' not in out['data'] and out['data']['measurement_count'] == 0
    assert out['decisions'][0]['answers'][0]['status'] == 'flagged' and reason in out['decisions'][0]['answers'][0]['reason']


@pytest.mark.parametrize('script', [
    {'parameter': choice('Lactate')},                                              # not one of the supplied candidates
    {'parameter': {'type': 'choice', 'choice': 'Glucose', 'probabilities': {'Glucose': 1.4}}},  # not a probability
    {'parameter': {'type': 'noul', 'noul': 0.9}},                                  # wrong answer type
])
def test_invalid_model_output_falls_back_to_host_rules(world, script):
    p, ctx = world
    use(p, Scripted(script), calibrated('field_meaning'))
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'reconcile', 'dataset_ids': [delivery(p, ctx, glucose())],
                                          'parameter': 'sugar'})
    assert out['decisions'][0]['status'] == 'fallback' and 'invalid' in out['decisions'][0]['reason']
    assert any(i['code'] == 'missing_requested_parameter' for i in out['issues'])


def test_timeout_falls_back_and_opens_the_breaker(world):
    p, ctx = world
    provider = use(p, Scripted({}, error=ProviderError('timed out', retryable=True, kind='timeout')))
    task = {'site_id': 'S1', 'operation': 'reconcile', 'dataset_ids': [delivery(p, ctx, glucose())], 'parameter': 'sugar'}
    first = p.workspace_tasks.execute(ctx, task)
    second = p.workspace_tasks.execute(ctx, task)
    assert 'timed out' in first['decisions'][0]['reason'] and 'recently failed' in second['decisions'][0]['reason']
    assert len(provider.calls) == 1  # the second request did not wait on a model that just timed out
    assert first['task_status'] == second['task_status'] == 'needs_information'


def test_decision_never_reads_evidence_the_person_cannot(world):
    p, ctx = world
    source = delivery(p, ctx, glucose())
    provider = use(p, Scripted({'q': choice('a')}))
    outsider = p.identity.context_for('T', 'outsider')
    result = p.gateway.decisions.decide(DecisionRequest('field_meaning', outsider, {'x': 1},
        [Question('q', 'choice', 'Which?', choices={'a': None, UNKNOWN: None})],
        inputs=[{'kind': 'evidence', 'id': source, 'revision': 1, 'site_id': 'S1'}]))
    assert result.status == 'fallback' and 'not readable' in result.reason and provider.calls == []


def test_request_contract_requires_unknown_and_bounded_state(world):
    p, ctx = world
    provider = use(p, Scripted({'q': choice('a')}))
    no_unknown = p.gateway.decisions.decide(DecisionRequest('t', ctx, 'state', [Question('q', 'choice', 'Which?', choices={'a': None, 'b': None})]))
    too_large = p.gateway.decisions.decide(DecisionRequest('t', ctx, 'x' * 30_000, [Question('q', 'choice', 'Which?', choices={'a': None, UNKNOWN: None})]))
    assert no_unknown.status == 'fallback' and 'unknown' in no_unknown.reason
    assert too_large.status == 'fallback' and 'exceeds' in too_large.reason and provider.calls == []


def test_host_rule_disagreement_is_flagged_even_when_calibrated(world):
    p, ctx = world
    use(p, Scripted({'q': choice('b', 0.99)}), calibrated('t'))
    result = p.gateway.decisions.decide(DecisionRequest('t', ctx, 'state', [
        Question('q', 'choice', 'Which?', choices={'a': None, 'b': None, UNKNOWN: None}, deterministic='a')]))
    assert result.decisions['q'].status == 'flagged' and 'disagrees' in result.decisions['q'].reason


def test_environment_configuration_and_jev_request_shape(tmp_path, monkeypatch):
    p = Platform(RecordStore(), providers={})
    assert DecisionAdapter.from_env(p.gateway, {}).enabled is False
    missing = DecisionAdapter.from_env(p.gateway, {'LIFESCI_DECISION_ADAPTER': 'jev'})
    assert missing.enabled is False and 'TYPESAFE_API_KEY' in missing.configuration_issue
    path = tmp_path / 'calibration.json'
    path.write_text(json.dumps({'tasks': calibrated('route_request', 0.95)}))
    adapter = DecisionAdapter.from_env(p.gateway, {'LIFESCI_DECISION_ADAPTER': 'jev', 'TYPESAFE_API_KEY': 'k',
                                                   'LIFESCI_DECISION_CALIBRATION': str(path)})
    assert adapter.enabled and adapter.model == 'jev-1.14.0' and adapter.describe()['calibrated_tasks']['route_request']['threshold'] == 0.95
    with pytest.raises(ValueError):
        bad = tmp_path / 'bad.json'
        bad.write_text(json.dumps({'tasks': {'x': {'model': 'm', 'eval_id': 'e', 'held_out_n': 5, 'threshold': 0.2}}}))
        load_calibration(bad)
    sent = {}

    class Response:
        status_code = 200
        def json(self):
            return {'model': 'jev-1.14.0', 'answers': {}, 'usage': {'input_tokens': 1, 'output_tokens': 0}}

    def post(url, json, headers, timeout):
        sent.update(url=url, body=json, headers=headers, timeout=timeout)
        return Response()
    import httpx
    monkeypatch.setattr(httpx, 'post', post)
    JevProvider('secret').decide(model='jev-1.14.0', state='s', questions={'q': {'type': 'noul', 'instructions': 'x'}}, timeout_s=2)
    assert sent['url'] == 'https://api.typesafe.ai/v1/systemone' and sent['headers']['Authorization'] == 'Bearer secret'
    assert set(sent['body']) == {'model', 'state', 'questions'} and sent['timeout'] == 2


def test_found_records_are_reordered_but_none_is_dropped(world):
    p, ctx = world
    for name in ('alpha', 'beta', 'gamma'):
        p.evidence.ingest(ctx, source_system='notes', source_record_id=name, content=f'{name} filter integrity report'.encode(),
                          media_type='text/plain', site_id='S1', event_time='2026-11-01T00:00:00Z')
    score = lambda value: {'type': 'score', 'score': value, 'confidence': 0.8, 'legend': {}, 'probabilities': {}}
    use(p, Scripted(lambda questions: {name: score(i) for i, name in enumerate(questions)}))
    # Word matches only: a literal match of the whole query always stays first and is never reordered.
    task = {'site_id': 'S1', 'operation': 'find_records', 'query': 'integrity filter', 'kinds': ['evidence']}
    plain = p.workspace_tasks.execute(ctx, {**task, 'use_decision_model': False})
    ranked = p.workspace_tasks.execute(ctx, task)
    assert sorted(r['id'] for r in ranked['data']['records']) == sorted(r['id'] for r in plain['data']['records'])
    assert [r['id'] for r in ranked['data']['records']] == [r['id'] for r in plain['data']['records']][::-1]
    assert ranked['decisions'][0]['answers'][0]['status'] == 'advisory' and plain['decisions'] == []


def test_mention_scores_never_confirm_exposure(world):
    p, ctx = world
    p.evidence.ingest(ctx, source_system='mes', source_record_id='use-1', content=b'x', media_type='text/plain', site_id='S1',
                      event_time='2026-11-01T00:00:00Z', metadata={'note': 'Filter LOT-7781 installed on TK-7'})
    use(p, Scripted(lambda questions: {name: {'type': 'noul', 'noul': 0.93} for name in questions}), calibrated('impact_link'))
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'trace_impact', 'record_id': 'LOT-7781'})
    record = out['data']['records'][0]
    assert record['link_suggestion']['documents_use_probability'] == 0.93
    assert out['data']['exposure_confirmed'] is False and out['data']['causal_claim_supported'] is False


# --- truncated retrieval ------------------------------------------------------------------------------------------

def test_every_requested_batch_is_in_the_result_whatever_the_row_page(world):
    p, ctx = world
    source = delivery(p, ctx, glucose(batches=('A', 'B', 'C'), points=150))
    task = {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [source], 'parameter': 'Glucose', 'batches': ['A', 'B', 'C']}
    out = p.workspace_tasks.execute(ctx, task)
    data = out['data']
    assert out['task_status'] == 'completed' and data['truncated'] is False and data['series_complete'] is True
    assert {s['batch']: s['n'] for s in data['series']} == {'A': 150, 'B': 150, 'C': 150}
    assert len(data['measurements']) == 50 and data['next_offset'] == 50 and data['measurement_count'] == 450
    summary = {(s['left_batch'], s['right_batch']): s for s in data['comparison_summary']}
    assert set(summary) == {('A', 'B'), ('A', 'C'), ('B', 'C')}
    assert summary[('A', 'C')]['matched_times'] == 150 and summary[('A', 'C')]['mean_difference'] == -2
    assert data['comparison_count'] == 450 and data['comparisons_next_offset'] == 50
    second = p.workspace_tasks.execute(ctx, {**task, 'offset': 50})
    assert second['data']['measurements'][0] != data['measurements'][0] and second['data']['comparison_summary'] == data['comparison_summary']


def test_the_assistant_sees_valid_complete_figures_not_a_cut_string(world):
    from src.lifesci.process_engineering import tool_loop
    p, ctx = world
    source = delivery(p, ctx, glucose(batches=('A', 'B', 'C'), points=400))
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [source],
                                          'parameter': 'Glucose', 'batches': ['A', 'B', 'C']})
    assert len(json.dumps(out)) > tool_loop.RESULT_CHARS  # the old path cut this mid-structure
    shown = json.loads(tool_loop._for_model(out))         # still valid JSON
    assert len(json.dumps(shown)) <= tool_loop.RESULT_CHARS + 200
    assert {s['right_batch'] for s in shown['data']['comparison_summary']} == {'B', 'C'}
    assert {s['batch'] for s in shown['data']['series']} == {'A', 'B', 'C'}
    marker = shown['data']['series'][0]['points'][-1]
    assert marker['not_shown'] > 0 and marker['of'] == 400  # what is missing is stated, never silent


def test_csv_field_comma_is_not_a_thousands_separator():
    from src.lifesci.process_engineering.grounding import check_reply
    source = {'lims': 'sample_id,time_h\nS-009-R01-16,231.00'}
    assert check_reply('The last sample was taken at 231.00 h.', [], source)['unsupported_numbers'] == []
    assert check_reply('Viable density 9,626,667 cells/mL.', [], {'s': 'vcd 9626667'})['unsupported_numbers'] == []
    assert check_reply('The last sample was taken at 232.00 h.', [], source)['unsupported_numbers'] == [232.0]


# --- deliveries still in review --------------------------------------------------------------------------------------

def test_delivery_in_review_runs_only_on_request_and_says_so(world):
    from src.lifesci.cmo_datasets import require_dataset
    p, ctx = world
    rows = glucose()
    rows[0]['status'], rows[1]['status'], rows[2]['status'] = 'needs_review', 'auto_accepted', 'needs_review'
    source = delivery(p, ctx, rows, provisional={'pending_values': 2, 'rejected_values': 1, 'open_issues': 3,
                                                 'open_issue_counts': {'MISSING_FIELD': 3}, 'verified_package': False})
    task = {'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [source], 'parameter': 'Glucose', 'batches': ['A', 'B']}
    refused = p.workspace_tasks.execute(ctx, task)
    assert refused['task_status'] == 'needs_information' and refused['data']['comparison_count'] == 0
    assert [i['code'] for i in refused['issues']][0] == 'unverified_dataset'
    out = p.workspace_tasks.execute(ctx, {**task, 'include_unverified': True})
    assert out['task_status'] == 'completed' and out['evidence_state'] == 'provisional'
    assert 'still in review' in out['summary'] and out['data']['comparison_count'] == 3
    check = out['data']['verification'][0]
    assert check['state'] == 'provisional' and check['values_still_in_review_used'] == 2 and check['open_checks'] == 3
    assert {m.get('review_status') for m in out['data']['measurements']} >= {'needs_review', 'auto_accepted'}
    # Everything that requires a verified dataset keeps refusing it.
    with pytest.raises(ValueError, match='still in review'):
        require_dataset(p, ctx, source, 'S1')
    thread = p.engineering_conversations.create(ctx, {'site_id': 'S1'})
    with pytest.raises(ValueError, match='still in review'):
        p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'use it', 'expected_revision': thread['revision'], 'dataset_ids': [source]})


# --- causes: screening, never a conclusion ----------------------------------------------------------------------------

def test_cause_screening_orders_candidates_and_never_claims_a_cause(world):
    p, ctx = world
    def record(name, when, **meta):
        return p.evidence.ingest(ctx, source_system='qms', source_record_id=name, content=name.encode(), media_type='text/plain',
                                 site_id='S1', event_time=when, metadata=meta)['evidence_id']
    subject = record('DEV-77', '2026-11-01T10:00:00Z', equipment_id='TK-7', batch_id='B-204')
    before = record('CAL-12', '2026-11-01T08:00:00Z', equipment_id='TK-7')
    after = record('MNT-9', '2026-11-01T15:00:00Z', equipment_id='TK-7')
    record('UNRELATED', '2026-11-01T07:00:00Z', equipment_id='TK-99')
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'suggest_causes', 'record_id': subject, 'record_kind': 'evidence'})
    data = out['data']
    assert data['causal_claim_supported'] is False and data['causal_status'] == 'hypotheses_only'
    assert 'No cause is established' in out['summary'] and out['model_calls'] == 0
    by_record = {f['record']['id']: f for f in data['chronology']}
    assert set(by_record) == {before, after}
    assert by_record[before]['screening'] == 'not_ruled_out' and by_record[after]['screening'] == 'weakened_by_timing'
    assert [h['factor_id'] for h in data['hypotheses']] == [by_record[before]['id']]
    assert data['hypotheses'][0]['kind'] == 'hypothesis' and data['hypotheses'][0]['not_established']
    assert [c['factor_id'] for c in data['contrary_evidence']] == [by_record[after]['id']]
    assert any('cannot access' in u for u in data['unknowns'])
    assert {r['id'] for r in out['source_refs']} >= {subject, before, after}


def test_cause_screening_without_a_subject_asks_for_one(world):
    p, ctx = world
    out = p.workspace_tasks.execute(ctx, {'site_id': 'S1', 'operation': 'suggest_causes'})
    assert out['task_status'] == 'needs_information' and out['issues'][0]['code'] == 'record_required'
    assert out['data']['hypotheses'] == [] and out['data']['causal_claim_supported'] is False


# --- typed request from typed words --------------------------------------------------------------------------------------

@pytest.mark.parametrize('text, route', [
    ('Compare Glucose between A and B', 'direct'),
    ('compare glucose for all batches', 'direct'),
    ('Reconcile glucose in the October delivery', 'direct'),
    ('Why is Glucose lower in B than A?', 'assistant'),             # a question about a cause
    ('Compare Glucose between A and B and say which is healthier', 'assistant'),  # words left over
    ('Compare Glucose for A', 'assistant'),                         # one batch is not a comparison
    ('Compare sugar between A and B', 'assistant'),                 # not a recorded name
    ('Compare Glucose between A and B after 48 h', 'assistant'),    # a condition the task does not take
])
def test_only_a_whole_routine_request_is_routed_directly(world, text, route):
    p, ctx = world
    source = delivery(p, ctx, glucose())
    found = p.workspace_tasks.route(ctx, 'S1', text)
    assert found['route'] == route and found['basis'] == 'host_rules', found['reason']
    if route == 'direct':
        assert found['task']['dataset_ids'] == [source] and found['task']['parameter'] == 'Glucose'


def test_decision_model_routing_applies_only_inside_calibration(world):
    p, ctx = world
    source = delivery(p, ctx, glucose())
    def script(questions):
        return {name: ({'type': 'noul', 'noul': 0.98} if q['type'] == 'noul' else
                       choice('compare', 0.98) if name == 'operation' else choice('Glucose', 0.98))
                for name, q in questions.items()}
    use(p, Scripted(script))
    suggested = p.workspace_tasks.route(ctx, 'S1', 'Compare sugar between A and B')
    assert suggested['route'] == 'assistant' and suggested['suggested_task']['parameter'] == 'Glucose'
    use(p, Scripted(script), calibrated('route_request'))
    applied = p.workspace_tasks.route(ctx, 'S1', 'Compare sugar between A and B')
    assert applied['route'] == 'direct' and applied['basis'] == 'decision_model'
    assert applied['task']['dataset_ids'] == [source] and applied['task']['batches'] == ['A', 'B']
    # A request for reasoning never reaches the decision model.
    provider = use(p, Scripted(script), calibrated('route_request'))
    assert p.workspace_tasks.route(ctx, 'S1', 'Why is sugar lower in B?')['route'] == 'assistant' and provider.calls == []


# --- time to an answer -----------------------------------------------------------------------------------------------------

def ask(p, ctx, text):
    thread = p.engineering_conversations.create(ctx, {'site_id': 'S1'})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': text, 'expected_revision': thread['revision']})
    p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
    # Timing is saved as the worker releases the turn, so read the conversation as the page does afterwards.
    return p.engineering_conversations.get(ctx, thread['id'])['turns'][-1]


def test_routine_chat_request_is_answered_directly_and_timed(world, monkeypatch):
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p, ctx = world
    delivery(p, ctx, glucose())
    turn = ask(p, ctx, 'Compare Glucose between A and B')
    assert turn['status'] == 'completed' and turn['response_mode'] == 'direct_task' and turn['gateway_runs'] == []
    assert 'Largest difference -1 g/L at 0 h' in turn['reply'] and 'do not explain' in turn['reply']
    assert turn['artifacts'][0]['kind'] == 'workspace_task_result' and turn['steps'][0]['status'] == 'completed'
    timing = turn['timing']
    assert timing['path'] == 'direct' and timing['model_calls'] == 0 and timing['within_target'] is True
    assert 0 <= timing['answer_seconds'] <= timing['target_seconds'] == 10.0


def test_question_goes_to_the_assistant_and_its_time_is_recorded(world, monkeypatch):
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p, ctx = world
    delivery(p, ctx, glucose())
    turn = ask(p, ctx, 'Why is Glucose lower in B than A?')
    assert turn['status'] == 'agent_unavailable'  # no reasoning model is configured in this test
    assert turn.get('response_mode') != 'direct_task' and turn['routing']['route'] == 'assistant'
    assert turn['timing']['path'] == 'assistant' and turn['timing']['answer_seconds'] >= 0


def test_direct_route_can_be_switched_off(world, monkeypatch):
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    monkeypatch.setenv('ASSISTANT_DIRECT_ROUTE', 'off')
    p, ctx = world
    delivery(p, ctx, glucose())
    turn = ask(p, ctx, 'Compare Glucose between A and B')
    assert turn.get('response_mode') != 'direct_task' and 'routing' not in turn


def test_requests_report_their_duration_and_the_recent_window(world):
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    p, ctx = world
    source = delivery(p, ctx, glucose())
    client = TestClient(create_app(p))
    headers = {'X-Tenant-Id': 'T', 'X-Actor-Id': 'owner'}
    ran = client.post('/v1/workspace-tasks/run', headers=headers, json={
        'site_id': 'S1', 'operation': 'compare', 'dataset_ids': [source], 'parameter': 'Glucose', 'batches': ['A', 'B']})
    assert ran.status_code == 200 and ran.headers['server-timing'].startswith('app;dur=')
    result = ran.json()
    assert result['timing']['within_target'] is True and result['timing']['target_seconds'] == 10.0
    assert {'authorize', 'retrieve', 'calculate'} <= set(result['timing']['phases'])
    routed = client.post('/v1/workspace-tasks/route', headers=headers, json={'site_id': 'S1', 'text': 'Compare Glucose between A and B'})
    assert routed.json()['route'] == 'direct'
    window = client.get('/v1/latency', headers=headers, params={'prefix': 'workspace-tasks'}).json()
    by_route = {r['route']: r for r in window['routes']}
    assert by_route['POST /v1/workspace-tasks/run']['n'] == 1 and by_route['POST /v1/workspace-tasks/run']['over_target'] == 0
    assert client.get('/v1/workspace-tasks/catalog', headers=headers).json()['decision_model']['enabled'] is False


# --- prepared evidence for a question ---------------------------------------------------------------------------------

def test_question_reaches_the_assistant_with_the_calculation_already_done(world, monkeypatch):
    from tests.lifesci.test_engineering_conversation import fake_planner
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p, ctx = world
    delivery(p, ctx, glucose())
    fake = fake_planner(p, [])
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = [
        'Glucose is 1 g/L lower in B than in A at every measured time (0, 1 and 2 h). The records do not say why.']
    turn = ask(p, ctx, 'Why is Glucose lower in B than A?')
    assert turn['status'] == 'completed' and turn.get('response_mode') != 'direct_task'  # the assistant answered
    # No explanation model is configured here, so no quick answer is attempted and the assistant answers: one call.
    assert turn['routing']['route'] == 'assistant'
    assert sum('model' in a for run in turn['gateway_runs'] for a in run['attempts']) == 1
    first = fake.calls[0]['messages'][-1]['content']
    # Batches are compared in the order the question names them: A minus B.
    assert 'Calculated by the host' in first and '"comparison_summary"' in first and '"mean_difference": 1.0' in first
    assert turn['steps'][0]['title'].startswith('Calculated before asking the assistant')
    assert turn['artifacts'][0]['kind'] == 'workspace_task_result'
    assert turn['grounding']['unsupported_numbers'] == []  # the figures trace to the calculated result
    assert turn['timing']['path'] == 'assistant' and turn['timing']['model_calls'] == 1


def test_prepared_task_exists_only_for_a_question_about_one_recorded_parameter(world):
    p, ctx = world
    source = delivery(p, ctx, glucose())
    asked = p.workspace_tasks.route(ctx, 'S1', 'Why is Glucose lower in B than A?')
    assert asked['route'] == 'assistant' and asked['task'] is None
    assert (asked['prepared_task']['operation'], asked['prepared_task']['batches']) == ('compare', ['B', 'A'])
    one = p.workspace_tasks.route(ctx, 'S1', 'Is Glucose in A acceptable?')['prepared_task']
    assert (one['operation'], one['batches'], one['dataset_ids']) == ('reconcile', ['A'], [source])
    assert p.workspace_tasks.route(ctx, 'S1', 'Why did the batch fail?')['prepared_task'] is None
    assert p.workspace_tasks.route(ctx, 'S1', 'Compare Glucose between A and B')['prepared_task'] is None  # it simply runs
