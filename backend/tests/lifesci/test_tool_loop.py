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


def run_failing(p, ctx, script, text='What happened in DEV-77?'):
    """As run(), for a turn that is expected to end without an answer."""
    fake = fake_planner(p, [])
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = list(script)
    thread = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': text, 'expected_revision': thread['revision']})
    p.engineering_conversations.run_turn(ctx, queued['id'], queued['turn_ids'][-1])
    return p.engineering_conversations.get(ctx, thread['id'])['turns'][-1], fake


def revision(p, case_id='DEV-77'):
    return p.store.read().require(TENANT, 'case', case_id).revision


def test_reads_then_answers_with_steps_artifacts_and_grounding(env, monkeypatch):
    monkeypatch.setattr(tool_loop, 'MAX_SECONDS', float('inf'))  # Workbook readers can pause inside the turn.
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


def test_one_model_response_cannot_execute_more_tools_than_the_turn_allows(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'MAX_TOOL_CALLS', 1)
    searches = [call('workspace_search', kinds=['case'], query=query) for query in ('foaming', 'pressure')]
    turn, fake = run(p, ctx, [{'tool_calls': searches}, 'I checked the foaming records.'])
    assert len(turn['artifacts']) == 1
    assert fake.calls[-1]['tool_choice'] == 'none'
    replies = [m for m in fake.calls[-1]['messages'] if m['role'] == 'tool']
    assert len(replies) == 2 and 'budget' in replies[-1]['content'].lower()


def test_invalid_tool_arguments_cannot_crash_the_progress_label(env):
    p, ctx = env
    turn, _ = run(p, ctx, [
        {'tool_calls': [call('workspace_search', kinds=42, query='foaming')]},
        'I could not search the records.'])
    assert turn['status'] == 'completed'
    assert turn['steps'][0]['status'] == 'blocked'


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


def test_a_turn_budget_counts_solver_calls_used_not_the_maximum_each_run_reserved(env):
    p, ctx = env
    conv = p.engineering_conversations
    thread = conv.create(ctx, {})
    tid = conv.enqueue(ctx, thread['id'], {'text': 'Check both receiving vessels.', 'expected_revision': thread['revision']})['turn_ids'][-1]
    for _ in range(2):  # each reserves 96 (the whole turn budget) but uses 4
        turn = p.store.read().require(ctx.tenant_id, 'engineering_chat_turn', tid).state
        assert turn['solver_calls_admitted'] + 96 <= 96 + 8
        conv._update_turn(ctx, tid, solver_calls_admitted=turn['solver_calls_admitted'] + 96)
        conv._settle_solver_calls(ctx, tid, 96, 4)
    turn = p.store.read().require(ctx.tenant_id, 'engineering_chat_turn', tid).state
    assert turn['solver_calls_admitted'] == 8 and turn['solver_calls_used'] == 8


def test_two_full_budget_pre_transfer_checks_both_run_in_one_answer(env):
    """Live regression (2026-11-10): the second check was refused because the first reserved the whole turn budget."""
    p, ctx = env
    contexts = {r.state['label']: r.id for r in p.store.read().list(ctx.tenant_id, 'physical_analysis_context')
                if r.state.get('model_id') == 'chemical.parallel_batch'}
    sending = next(i for k, i in contexts.items() if 'receiving' not in k)
    a, b = (next(i for k, i in contexts.items() if f'option {x}' in k) for x in 'AB')
    criteria = [{'metric': 'product_yield_fraction', 'unit': 'fraction', 'role': 'yield', 'operator': '>=', 'limit': 0.85}]
    prepare = lambda receiver: call('model_library_prepare', mode='model_library', context_id=sending, receiver_context_id=receiver,
                                    model_id='chemical.parallel_batch', objective='Pre-transfer check to the receiving vessel',
                                    operation='assess_transfer', options={'criteria': criteria, 'max_solver_calls': 96})
    latest_plan = lambda messages: {'tool_calls': [call('model_library_execute', plan_id=sorted(
        p.store.read().list(ctx.tenant_id, 'physical_analysis_plan'), key=lambda r: r.id)[-1].id)]}
    script = [{'tool_calls': [call('model_library_read', kind='physical_analysis_context', record_id=sending)]},
              {'tool_calls': [prepare(a)]}, latest_plan, {'tool_calls': [prepare(b)]}, latest_plan, 'Both checks ran.']
    turn, _ = run(p, ctx, script, 'Check both receiving vessels.')
    results = p.store.read().list(ctx.tenant_id, 'physical_analysis_result')
    assert [s['status'] for s in turn['steps'] if s['title'].startswith('Model library')].count('blocked') == 0
    assert len(results) == 2 and all(r.state['execution_status'] == 'completed' for r in results)
    assert sorted(r.state['spec']['options'] == {'criteria': criteria} for r in results) == [True, True]


def test_answer_links_come_from_the_records_a_turn_read():
    from src.lifesci.process_engineering.open_links import open_links

    def read(kind, record_id, status='completed', task='workspace_read'):
        return {'task_kind': task, 'status': status, 'payload': {'kind': kind, 'record_id': record_id}}
    records = {'cmo-verified-delivery:run1': {'metadata': {'parameters': ['viable_cell_density', 'pH']}},
               'cmo-verified-delivery:demo': {'metadata': {'synthetic': True, 'parameters': ['pH']}}}
    steps = [read('deviation_signal', 'sig_1'), read('deviation_signal', 'sig_1'), read('deviation_signal', 'sig_2', status='blocked'),
             read('evidence', 'cmo-verified-delivery:run1'), read('evidence', 'cmo-verified-delivery:demo'),
             read('evidence', 'cmo-verified-delivery:hidden'), read('case', 'DEV-12'), read('evidence', 'cmo-verified-delivery:run1', task='workspace_search')]
    links = open_links(steps, evidence=records.get, question='How did viable cell density compare?', answer='pH was steady.')
    assert links == [{'label': 'Open the signal and its chart', 'href': '/signals/?id=sig_1'},
                     {'label': 'Plot viable cell density across batches', 'href': '/trends/?parameter=viable_cell_density'},
                     {'label': 'Open the delivery and its source files', 'href': '/cmo/?run=run1'}]
    # No parameter named: the page still opens; nothing is guessed.
    assert open_links(steps[3:4], evidence=records.get, question='Anything odd?')[0] == {'label': 'Plot this data across batches', 'href': '/trends/'}
    # A record the person cannot read, a synthetic dataset and a failed step give no link.
    assert open_links([steps[2], steps[4], steps[5]], evidence=records.get) == []


# --- thinking again at the fullest level before anything is saved ------------------------------------------------------

def test_only_tools_that_save_a_proposal_or_a_result_are_taken_again():
    saving = ('workspace_propose_action', 'workspace_propose_routine', 'workspace_propose_rule', 'model_library_propose_extension',
              'lyopronto_record_result')
    others = ('workspace_read', 'workspace_search', 'workspace_run_task', 'workspace_open_task_result', 'cho_dataset_forecast',
              'model_library_prepare', 'model_library_execute', 'remember', 'recall', 'open_result', 'open_memory', 'ask_user')
    assert all(tool_loop.commits(name) for name in saving) and not any(tool_loop.commits(name) for name in others)


def test_a_step_that_saves_is_taken_again_at_the_fullest_reasoning_and_only_that_version_runs(env, monkeypatch):
    p, ctx = env
    # A search stands in for a saving tool, so the test needs no approval set-up: the rule looks only at the tool's name.
    monkeypatch.setattr(tool_loop, 'COMMITS', ('search',))
    read = {'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))], 'effort': 'high'}
    turn, fake = run(p, ctx, [
        read,                                                                                        # a lookup: runs as written
        {'tool_calls': [call('workspace_search', kinds=['case'], query='written in haste')], 'effort': 'high'},  # dropped
        {'tool_calls': [call('workspace_search', kinds=['case'], query='foaming')]},                # the same step, thought through
        {'content': 'DEV-77 is the open foaming case.', 'effort': 'high'}])
    assert turn['status'] == 'completed' and turn['reply'].startswith('DEV-77')
    asked = [c['reasoning_effort'] for c in fake.calls]
    assert asked == [None, None, 'max', 'max']           # the saving step was asked for again; the turn then stays careful
    ran = [(s['task_kind'], s['payload'].get('query')) for s in turn['steps']]
    assert ran == [('workspace_read', None), ('workspace_search', 'foaming')]      # the hasty version never ran
    assert 'written in haste' not in json.dumps(fake.calls[-1]['messages'])        # and the model never saw it either
    assert len(turn['gateway_runs']) == 4                 # every model call is on the record, the dropped one included
    assert turn['gateway_runs'][2]['output']['reasoning_effort'] == 'max'


def test_a_saving_step_already_at_the_fullest_level_is_not_asked_for_twice(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'COMMITS', ('search',))
    for level in (None, 'max'):                           # nothing sent means the model's own fullest level
        turn, fake = run(p, ctx, [
            {'tool_calls': [call('workspace_search', kinds=['case'], query='foaming')], **({'effort': level} if level else {})},
            'DEV-77 is the open foaming case.'])
        assert turn['status'] == 'completed' and len(fake.calls) == 2 and [c['reasoning_effort'] for c in fake.calls] == [None, None]


def test_with_no_step_left_to_think_again_a_hasty_save_is_refused_not_run(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'COMMITS', ('search',))
    monkeypatch.setattr(tool_loop, 'MAX_MODEL_CALLS', 2)  # one step with tools, then the answer
    turn, fake = run(p, ctx, [
        {'tool_calls': [call('workspace_search', kinds=['case'], query='foaming'),
                        call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))], 'effort': 'high'},
        'DEV-77 records foaming in B-200. I could not save the search.'])
    assert turn['status'] == 'completed' and len(fake.calls) == 2 and fake.calls[-1]['tool_choice'] == 'none'
    assert [(s['task_kind'], s['status']) for s in turn['steps']] == [('workspace_search', 'blocked'), ('workspace_read', 'completed')]
    assert 'no step was left' in turn['steps'][0]['issues'][0] and 'not saved' in json.dumps(fake.calls[-1]['messages'])


def test_once_a_saving_step_is_reached_the_rest_of_the_turn_stays_at_the_fullest_level(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'COMMITS', ('search',))
    read = lambda: {'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=revision(p))], 'effort': 'high'}
    turn, fake = run(p, ctx, [
        read(),                                                                                   # before: the usual level
        {'tool_calls': [call('workspace_search', kinds=['case'], query='hasty')], 'effort': 'high'},     # dropped
        read(),                              # thought through, the model first checks something else instead of saving
        {'tool_calls': [call('workspace_search', kinds=['case'], query='foaming')]},              # then saves: not asked twice
        'DEV-77 is the open foaming case.'])
    assert turn['status'] == 'completed'
    assert [c['reasoning_effort'] for c in fake.calls] == [None, None, 'max', 'max', 'max']
    assert [(s['task_kind'], s['payload'].get('query')) for s in turn['steps']] == [
        ('workspace_read', None), ('workspace_read', None), ('workspace_search', 'foaming')]


def test_a_second_thought_that_does_not_finish_saves_nothing_and_the_turn_still_answers(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'COMMITS', ('search',))
    turn, fake = run(p, ctx, [
        {'tool_calls': [call('workspace_search', kinds=['case'], query='foaming')], 'effort': 'high'},
        ProviderError('reply not finished after 150 s', retryable=True, kind='unfinished'),   # one try only, then give up on it
        {'content': 'DEV-77 is the open foaming case. I could not save the search.', 'effort': 'high'}])
    assert turn['status'] == 'completed' and turn['reply'].startswith('DEV-77')
    assert [c['reasoning_effort'] for c in fake.calls] == [None, 'max', None]      # the answer is back at the usual level
    assert [(s['task_kind'], s['status']) for s in turn['steps']] == [('workspace_search', 'blocked')]
    assert 'the check did not finish' in turn['steps'][0]['issues'][0] and not turn['artifacts']


def test_a_second_thought_lost_to_an_endpoint_that_went_silent_ends_the_turn_visibly(env, monkeypatch):
    p, ctx = env
    monkeypatch.setattr(tool_loop, 'COMMITS', ('search',))
    turn, fake = run_failing(p, ctx, [
        {'tool_calls': [call('workspace_search', kinds=['case'], query='foaming')], 'effort': 'high'},
        ProviderError('the endpoint sent nothing for 30 s', retryable=True, kind='timeout')])
    # A silent endpoint is treated as down for a while, so the answer cannot be asked for either. Nothing was saved.
    assert turn['status'] == 'agent_unavailable' and not turn['artifacts']
    assert [(s['task_kind'], s['status']) for s in turn.get('steps') or []] == [('workspace_search', 'blocked')]
    assert [c['reasoning_effort'] for c in fake.calls] == [None, 'max']
