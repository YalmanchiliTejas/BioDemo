"""Native tool loop: contract tests with a scripted provider. They establish host behavior, not model accuracy."""
import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.gateway import ProviderError
from src.lifesci.process_engineering import tool_loop
from src.lifesci.store import RecordStore
from tests.lifesci.test_engineering_conversation import fake_planner, send


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p = Platform(RecordStore(), providers={})
    seed(p)
    ctx = p.identity.context_for(TENANT, 'priya')
    p.cases.open(ctx, 'DEV-77', 'priya', 'quinn', 'NF1')
    p.cases.add_timeline_event(ctx, 'DEV-77', '2026-11-01T10:00:00Z', 'Foaming at 4 h in B-200; DO fell to 25 %.')
    return p, ctx


def call(name, **arguments):
    return {'name': name, 'arguments': arguments}


def run(p, ctx, script, text='What happened in DEV-77?'):
    fake = fake_planner(p, [])
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = list(script)  # tool turns, not JSON plans
    turn = send(p, ctx, p.engineering_conversations.create(ctx, {}), text)['turns'][-1]
    return turn, fake


def revision(p, case_id='DEV-77'):
    return p.store.read().require(TENANT, 'case', case_id).revision


def test_reads_then_answers_with_steps_artifacts_and_grounding(env):
    p, ctx = env
    turn, fake = run(p, ctx, [
        {'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))]},
        'DEV-77: foaming at 4 h in B-200 and DO fell to 25 %. The cause is not recorded yet.'])
    assert turn['status'] == 'completed', (turn['issues'], turn.get('system_message'))
    assert turn['reply'].startswith('DEV-77') and not turn['questions']
    assert [(s['title'], s['status']) for s in turn['steps']] == [('Read case DEV-77', 'completed')]
    assert [a['kind'] for a in turn['artifacts']] == ['assistant_workspace_result']
    assert len(turn['gateway_runs']) == 2 and turn['grounding']['status'] != 'evaluation_unavailable'
    assert '25 %' in json.dumps(fake.calls[1]['messages'][-1])  # the model saw the record before answering
    assert '_loop' not in turn  # internal working state never reaches the browser


def test_a_bad_call_is_a_tool_error_the_model_corrects_not_a_lost_round(env):
    p, ctx = env
    turn, fake = run(p, ctx, [
        {'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p), colour='red')]},
        {'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))]},
        'DEV-77 records foaming in B-200.'])
    assert turn['status'] == 'completed'
    assert [s['status'] for s in turn['steps']] == ['blocked', 'completed']
    assert 'colour' in turn['steps'][0]['issues'][0]
    assert 'colour' in fake.calls[1]['messages'][-1]['content']  # the error went back to the model


def test_budget_ends_in_a_tools_off_answer_never_in_unplanned_work(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'MAX_MODEL_CALLS', 3)
    search = {'tool_calls': [call('workspace_search', kinds=['case'], query='foaming')]}
    turn, fake = run(p, ctx, [search, search, 'Two foaming cases found; DEV-77 is the open one.'])
    assert turn['status'] == 'completed' and turn['reply'].startswith('Two foaming')
    assert fake.calls[-1]['tool_choice'] == 'none' and 'Budget reached' in fake.calls[-1]['messages'][-1]['content']


def test_one_question_ends_the_turn_waiting_for_the_person(env):
    p, ctx = env
    turn, _ = run(p, ctx, [{'content': 'I need one thing first.', 'tool_calls': [call('ask_user', question='Which batch do you mean?')]}],
                  text='Forecast the batch')
    assert turn['status'] == 'needs_information' and turn['questions'] == ['Which batch do you mean?']


def test_records_the_person_may_not_read_are_refused_by_the_host(env):
    p, ctx = env
    with p.store.transaction('fixture') as tx:
        tx.put(TENANT, 'case', 'OTHER-SITE', {'case_id': 'OTHER-SITE', 'site_id': 'NF2', 'status': 'open', 'timeline': []},
               expected_revision=None, action='fixture')
    turn, fake = run(p, ctx, [
        {'tool_calls': [call('workspace_read', kind='case', record_id='OTHER-SITE', revision=1)]},
        'I could not read OTHER-SITE.'])
    assert turn['steps'][0]['status'] == 'blocked' and not turn['artifacts']
    assert 'NF2' not in fake.calls[1]['messages'][-1]['content'] or 'error' in fake.calls[1]['messages'][-1]['content']


def test_a_model_failure_is_visible_with_its_reason(env):
    p, ctx = env
    exhausted = ProviderError('modal returned no answer content (output token budget exhausted)', retryable=False, kind='output_limit')
    turn, _ = run(p, ctx, [exhausted, exhausted])
    assert turn['status'] == 'agent_unavailable' and 'budget exhausted' in ' '.join(turn['issues'])


def test_demo_workspaces_use_the_tool_loop_by_default_and_the_switch_overrides(monkeypatch):
    class Ctx:
        tenant_id = 'demo_123'
    monkeypatch.delenv('ASSISTANT_LOOP', raising=False)
    assert tool_loop.enabled(Ctx())
    Ctx.tenant_id = 'acme'
    assert not tool_loop.enabled(Ctx())
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    assert tool_loop.enabled(Ctx())
    monkeypatch.setenv('ASSISTANT_LOOP', 'planner')
    Ctx.tenant_id = 'demo_123'
    assert not tool_loop.enabled(Ctx())


def test_a_readable_verified_delivery_exposes_the_forecast_tool_without_attaching_it(env):
    """Live 2026-11-07: the forecast tool was hidden until a dataset was attached, so the assistant said it could not
    forecast and drafted an unrelated proposal instead."""
    from tests.lifesci.test_bioprocess import _verified_dataset
    p, ctx = env
    _verified_dataset(p, ctx)
    turn, fake = run(p, ctx, ['Done.'], text='Forecast glucose for CHO-001-R01 from 72 h')
    assert 'cho_dataset_forecast' in fake.calls[0]['tools']


def test_step_titles_never_show_system_ids():
    assert tool_loop.title('workspace_read', {'kind': 'deviation_signal', 'record_id': 'sig_01M6T1D8WVZ1T1V41KG0ABCD'}) == 'Read deviation signal'
    assert tool_loop.title('workspace_read', {'kind': 'case', 'record_id': 'DEV-31'}) == 'Read case DEV-31'


def test_the_model_sees_a_forecast_summary_not_a_truncated_trajectory(env):
    """Live 2026-11-07: a raw forecast cut off at ~104 h, and the model integrated the equations itself for later hours."""
    from tests.lifesci.test_bioprocess import _verified_dataset
    p, ctx = env
    dataset = _verified_dataset(p, ctx)
    forecast = call('cho_dataset_forecast', dataset_id=dataset, batch='CHO-001-R01', cutoff_h=60, rationale='Forecast from 60 h')
    turn, fake = run(p, ctx, [{'tool_calls': [forecast]}, 'Forecast done.'], text='Forecast CHO-001-R01 from 60 h')
    assert turn['steps'][0]['status'] == 'completed', turn['steps']
    seen = json.loads(fake.calls[1]['messages'][-1]['content'])
    assert {'fit', 'holdout_errors', 'holdout_comparison'} <= set(seen) and 'trajectory' not in seen
    assert 'training_fit' in seen['fit']


def converse(p, ctx, thread_id, script, text):
    fake = fake_planner(p, [])
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = list(script)
    thread = p.engineering_conversations.get(ctx, thread_id)
    return send(p, ctx, thread, text)['turns'][-1], fake


def test_only_recent_turns_are_loaded_older_ones_are_an_index(env):
    p, ctx = env
    tid = p.engineering_conversations.create(ctx, {})['id']
    for i in range(4):
        converse(p, ctx, tid, [f'Answer {i}: ' + 'detail ' * 300], f'Question {i}')
    _, fake = converse(p, ctx, tid, ['Fine.'], 'Question 4')
    context = fake.calls[0]['messages'][1]['content']
    assert 'Answer 3' in context and 'Answer 2' in context  # the last two exchanges, for follow-ups
    # the two recent answers (clipped at 2,000 chars, ~285 words each) plus ~22 per older index line, not 300 per answer
    assert context.count('detail') < 2 * 290 + 2 * 25
    assert '"earlier_turns_index"' in context and 'Question 0' in context


def test_an_earlier_result_is_reloaded_on_demand(env):
    p, ctx = env
    tid = p.engineering_conversations.create(ctx, {})['id']
    first, _ = converse(p, ctx, tid, [{'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))]},
                                      'DEV-77 noted.'], 'Read DEV-77')
    result_id = first['artifacts'][0]['id']
    turn, fake = converse(p, ctx, tid, [{'tool_calls': [call('open_result', result_id=result_id)]}, 'Reloaded.'], 'What did DEV-77 say again?')
    assert turn['steps'][0]['status'] == 'completed' and 'B-200' in fake.calls[1]['messages'][-1]['content']
    bad, _ = converse(p, ctx, tid, [{'tool_calls': [call('open_result', result_id='assi_not_here')]}, 'No.'], 'Open something else')
    assert bad['steps'][0]['status'] == 'blocked'


def test_recall_finds_your_past_conversations_never_someone_elses_private_memory(env):
    p, ctx = env
    mine = p.engineering_conversations.create(ctx, {})['id']
    converse(p, ctx, mine, ['The antifoam pump seal was the cause.'], 'Why did the antifoam pump fail?')
    p.identity.assign_role(TENANT, 'quinn2', 'engineering', site_id='NF1')
    other = p.identity.context_for(TENANT, 'quinn2')
    theirs = p.engineering_conversations.create(other, {})['id']
    converse(p, other, theirs, ['Private: antifoam supplier dispute.'], 'Antifoam supplier dispute notes')
    turn, fake = converse(p, ctx, p.engineering_conversations.create(ctx, {})['id'],
                          [{'tool_calls': [call('recall', query='antifoam pump')]}, 'Found it.'], 'What did we find about antifoam?')
    seen = fake.calls[1]['messages'][-1]['content']
    assert turn['steps'][0]['status'] == 'completed' and 'antifoam pump' in seen
    assert 'supplier dispute' not in seen  # another person's memory needs their grant


def test_large_transcripts_turn_old_results_into_pointers_and_never_overflow(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'CONTEXT_CHARS', 7000)
    monkeypatch.setattr(tool_loop, 'HARD_CHARS', 10**9)
    read = {'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))]}
    turn, fake = run(p, ctx, [read] * 6 + ['Done.'])
    last = fake.calls[-1]['messages']
    tool_contents = [m['content'] for m in last if m['role'] == 'tool']
    assert any(c.startswith('{"cleared"') and 'open_result' in c for c in tool_contents[:-4])
    assert not any(c.startswith('{"cleared"') for c in tool_contents[-4:])  # recent results stay whole
    monkeypatch.setattr(tool_loop, 'HARD_CHARS', 7000)  # even pointers don't fit: answer now, don't overflow
    turn, fake = run(p, ctx, [read] * 3 + ['Answered with what fits.'])
    assert turn['status'] == 'completed' and fake.calls[-1]['tool_choice'] == 'none'


def test_an_answer_written_beside_a_remember_call_is_not_lost(env):
    """Live 2026-11-07: the triage was written beside a remember call, and the person saw only the closing recap."""
    p, ctx = env
    answer = 'DEV-77: foaming at 4 h in B-200 and DO fell to 25 %. ' + 'Evidence and next steps follow. ' * 20
    turn, _ = run(p, ctx, [{'tool_calls': [read_case := call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))]},
                           {'content': answer, 'tool_calls': [call('remember', text='DEV-77 foaming coincided with the DO drop.',
                                                                    kind='open_thread', basis='inferred', sources=[{'kind': 'case', 'id': 'DEV-77'}])]},
                           'Saved to memory. The items above are what I would request first.'])
    assert turn['reply'].startswith('DEV-77: foaming') and turn['reply'].endswith('request first.')


def test_narration_beside_a_lookup_is_not_shown_as_the_answer(env):
    p, ctx = env
    turn, _ = run(p, ctx, [{'content': 'Let me check the case.', 'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))]},
                           'DEV-77 records foaming in B-200.'])
    assert turn['reply'] == 'DEV-77 records foaming in B-200.'


def test_memory_and_recent_turns_sit_last_just_before_the_question(env):
    p, ctx = env
    _, fake = run(p, ctx, ['DEV-77 shows foaming at 4 h.'])
    context = fake.calls[0]['messages'][1]['content']
    order = [context.index(f'"{k}"') for k in ('capabilities', 'case_index', 'memory_index', 'recent_turns')]
    assert order == sorted(order) and context.rindex('Question:') > order[-1]
