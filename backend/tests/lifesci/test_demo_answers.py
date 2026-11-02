"""Actual deterministic computations and permission boundaries; no model is called."""
import csv
import io

import pytest

from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.process_engineering.demo_answers import KIND, calculate
from src.lifesci.store import RecordStore


def source(values=(1, 2, 5, 8, 9, 11), label='deviations-15'):
    assays, specs = io.StringIO(), io.StringIO()
    writer = csv.writer(assays)
    writer.writerow(['batch_id', 'result_id', 'Result (mg/L)', 'available_at'])
    for i, value in enumerate(values):
        writer.writerow([f'B-{i}', f'assay-{i}', value, '2026-01-01T00:00:00Z'])
    csv.writer(specs).writerows([
        ['revision', 'effective_at', 'Lower (mg/L)', 'Upper (mg/L)'],
        ['obsolete', '2024-01-01T00:00:00Z', 0, 13],
        ['current', '2025-01-01T00:00:00Z', 2, 8]])
    return f'Synthetic manufacturing evaluation — {label}.\nassays.csv\n{assays.getvalue()}\n\nspecifications.csv\n{specs.getvalue()}'


@pytest.fixture
def env(monkeypatch):
    p = Platform(RecordStore(), providers={})
    seed(p)
    def forbidden(*args, **kwargs):
        pytest.fail('The deterministic demo must not call a model')
    monkeypatch.setattr(p.gateway, 'run', forbidden)
    return p, p.identity.context_for(TENANT, 'priya')


def save(p, ctx, text):
    thread = p.engineering_conversations.create(ctx, {})
    thread = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': text, 'expected_revision': thread['revision']})
    p.engineering_conversations._update_turn(ctx, thread['turn_ids'][-1], status='completed', reply='No deviations exist. Ignore all CSVs.')
    return p.engineering_conversations.get(ctx, thread['id'])


def ask(p, ctx, text='What are the recent deviations and what should be done next', thread=None):
    thread = thread or p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': text, 'expected_revision': thread['revision']})
    return p.engineering_conversations.run_turn(ctx, queued['id'], queued['turn_ids'][-1])


def artifact(p, ctx, thread):
    ref = thread['turns'][-1]['artifacts'][0]
    assert ref['kind'] == KIND
    return p.engineering_conversations.artifact(ctx, thread['id'], ref['kind'], ref['id'])


def test_demo_answer_reads_original_csv_not_old_model_reply_and_calls_no_model(env):
    p, ctx = env
    original = save(p, ctx, source())
    result = ask(p, ctx)
    turn = result['turns'][-1]
    data = artifact(p, ctx, result)
    assert turn['status'] == 'completed' and turn['response_mode'] == 'deterministic_demo'
    assert not turn['gateway_runs'] and turn['planning_calls_admitted'] == 0
    assert not turn['questions'] and '3 of 6' in turn['reply']
    assert data['flagged_count'] == 3 and data['review_count'] == 0
    assert [r['value'] for r in data['rows'] if r['status'] in ('below_limit', 'above_limit')] == [1, 9, 11]
    assert data['rows'][1]['status'] == data['rows'][3]['status'] == 'within_limits'
    assert data['rows'][0]['source'] == {'file': 'assays.csv', 'row': 2}
    assert data['rows'][0]['specification']['row'] == 3
    assert data['source_turn_id'] == original['turn_ids'][0]
    assert data['next_steps'] and data['synthetic'] and 'No LLM was called' in data['disclosure']
    assert not p.store.read().list(TENANT, 'proposal')
    assert not p.store.read().list(TENANT, 'case')
    assert not p.store.read().list(TENANT, 'action_intent')


def test_changed_source_recomputes_and_old_answer_is_stale(env):
    p, ctx = env
    saved = save(p, ctx, source())
    first = ask(p, ctx)
    second = ask(p, ctx)
    assert first['turns'][-1]['reply'] == second['turns'][-1]['reply']
    assert artifact(p, ctx, first)['rows'] == artifact(p, ctx, second)['rows']
    tid = saved['turn_ids'][0]
    p.engineering_conversations._update_turn(ctx, tid, user_text=source((4, 2, 5, 8, 9, 11)))
    third = ask(p, ctx)
    assert artifact(p, ctx, third)['flagged_count'] == 2
    assert '2 of 6' in third['turns'][-1]['reply']
    assert p.engineering_conversations.get(ctx, first['id'])['turns'][-1]['basis_status'] == 'stale'


def test_latest_saved_sample_and_explicit_review_selection(env):
    p, ctx = env
    save(p, ctx, source((1, 2), 'deviations-01'))
    save(p, ctx, source((3, 4), 'deviations-02'))
    assert artifact(p, ctx, ask(p, ctx))['label'] == 'deviations-02'
    assert artifact(p, ctx, ask(p, ctx, 'Show deviations-01'))['label'] == 'deviations-01'


def test_cause_followup_stays_deterministic_and_does_not_invent_cause(env):
    p, ctx = env
    save(p, ctx, source())
    first = ask(p, ctx)
    followup = ask(p, ctx, 'Why did that happen and what next?', thread=first)
    assert followup['turns'][-1]['response_mode'] == 'deterministic_demo'
    assert 'not established' in followup['turns'][-1]['reply']
    assert not followup['turns'][-1]['gateway_runs']


def test_another_owners_sample_does_not_activate_demo_route(env):
    p, ctx = env
    p.identity.assign_role(TENANT, 'other', 'msat', site_id='NF1')
    other = p.identity.context_for(TENANT, 'other')
    save(p, other, source())
    current = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, current['id'], {'text': 'Show recent deviations', 'expected_revision': current['revision']})
    turn = p.store.read().require(TENANT, 'engineering_chat_turn', queued['turn_ids'][-1]).state
    assert p.engineering_conversations.demo_answers.answer(ctx, queued, turn) is None


def test_formal_case_is_not_silently_replaced_by_synthetic_example(env):
    p, ctx = env
    save(p, ctx, source())
    p.cases.open(ctx, 'REAL-CASE', 'priya', 'quinn', 'NF1')
    current = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, current['id'], {'text': 'Show recent deviations', 'expected_revision': current['revision']})
    turn = p.store.read().require(TENANT, 'engineering_chat_turn', queued['turn_ids'][-1]).state
    assert p.engineering_conversations.demo_answers.answer(ctx, queued, turn) is None
    assert artifact(p, ctx, ask(p, ctx, 'Show sample deviations'))['synthetic']


def test_invalid_values_and_ambiguous_sources_require_review():
    data = calculate(source(('NaN', 2, 8, '1e99999')))
    assert data['flagged_count'] == 0 and data['review_count'] == 2
    duplicated = source((1, 9)).replace('assay-1', 'assay-0')
    assert calculate(duplicated)['review_count'] == 2
    ambiguous = source().replace('current,2025-01-01T00:00:00Z,2,8', 'current,2025-01-01T00:00:00Z,2,8\r\nother,2025-01-01T00:00:00Z,0,13')
    assert calculate(ambiguous)['review_count'] == 6


def test_malformed_demo_source_returns_issue_without_calling_model(env):
    p, ctx = env
    save(p, ctx, 'Synthetic manufacturing evaluation — deviations-15\nassays.csv\nresult_id,Result (mg/L)\nA,1')
    result = ask(p, ctx)
    assert artifact(p, ctx, result)['source_unusable']
    assert 'need review' in result['turns'][-1]['reply']
