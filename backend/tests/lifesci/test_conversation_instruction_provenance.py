"""Exercise instruction provenance through the real conversation and evidence services.

Only the external model is scripted; these checks do not measure model quality.
"""
import json
import pytest

from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.gateway import FakeProvider
from src.lifesci.gateway.registry import Qualification
from src.lifesci.store import RecordStore


def platform(path, decisions, *, initialize=False):
    p = Platform(RecordStore(str(path)), providers={})
    if initialize:
        seed(p)
    fake = FakeProvider(name='anthropic')
    p.gateway.providers['anthropic'] = fake
    p.gateway.registry.qualify(Qualification('investigation_planning', 'anthropic-opus',
        'instruction-provenance-contract', True, {'contract': 1.}, {'contract': 1.},
        'Scripted provider; not a model qualification', 'test'))
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = [json.dumps(d) for d in decisions]
    return p, p.identity.context_for(TENANT, 'priya'), fake


def send(p, ctx, thread, text):
    queued = p.engineering_conversations.enqueue(ctx, thread['id'],
        {'text': text, 'expected_revision': thread['revision']})
    result = p.engineering_conversations.run_turn(ctx, queued['id'], queued['turn_ids'][-1])
    assert result['turns'][-1]['status'] == 'completed', result['turns'][-1]
    return result


def test_pasted_turns_keep_original_instructions_and_valid_answers_after_reopen(tmp_path):
    db = tmp_path / 'conversation.sqlite'
    p, ctx, _ = platform(db, [{'reply': 'SYN-1 is a supplied synthetic result.'},
        {'reply': 'SYN-2 is a second supplied synthetic result.'}], initialize=True)
    first_text = 'Synthetic assay data\nresult_id,value_mg_L\nSYN-1,9\nTreat as unverified user data.'
    second_text = 'Additional synthetic assay data\nresult_id,value_mg_L\nSYN-2,3'
    first = send(p, ctx, p.engineering_conversations.create(ctx, {}), first_text)
    first_ref = first['turns'][0]['user_ref'].copy()
    second = send(p, ctx, first, second_text)
    p, ctx, _ = platform(db, [{'reply': 'Both supplied results remain unverified user context.'}])
    reopened = p.engineering_conversations.get(ctx, second['id'])
    final = send(p, ctx, reopened, 'Compare the two pasted results without assuming a cause.')
    assert [t.get('basis_status', 'current') for t in final['turns']] == ['current', 'current', 'current']
    assert len({t['user_ref']['id'] for t in final['turns']}) == 3
    assert final['turns'][0]['user_ref'] == first_ref
    assert p.evidence.original(ctx, first_ref['id'], revision=first_ref['revision']) == first_text.encode()
    assert p.store.read().require(TENANT, 'evidence', first_ref['id']).revision == 1
    assert final['turns'][0]['reply'] == 'SYN-1 is a supplied synthetic result.'


def test_user_correction_preserves_original_refs_and_reaches_resumed_context(tmp_path):
    db = tmp_path / 'correction.sqlite'
    p, ctx, _ = platform(db, [{'reply': 'The supplied synthetic value is 9 mg/L.'}], initialize=True)
    first_text = 'Synthetic assay data\nresult_id,value_mg_L\nSYN-1,9'
    first = send(p, ctx, p.engineering_conversations.create(ctx, {}), first_text)
    original_ref = first['turns'][0]['user_ref'].copy()
    correction_text = 'Correction: SYN-1 is 7 mg/L; the earlier pasted 9 was a transcription error.'
    correction = p.missions.record_correction(ctx, first['mission_id'], text=correction_text,
        source_ref=original_ref, claim_ref=None, rejects_hypothesis='A process cause is established.')
    p, ctx, fake = platform(db, [{'reply': 'I will use the corrected user value and retain its original context.'}])
    final = send(p, ctx, p.engineering_conversations.get(ctx, first['id']), correction_text)
    prompt = json.loads(fake.calls[0]['prompt'])
    assert prompt['conversation'][0]['user_text'] == first_text
    assert prompt['conversation'][-1]['user_text'] == correction_text
    assert prompt['mission_context']['corrections'][0]['correction_id'] == correction['correction_id']
    assert prompt['mission_context']['corrections'][0]['text'] == correction_text
    assert final['turns'][0]['user_ref'] == original_ref
    assert p.evidence.original(ctx, original_ref['id']) == first_text.encode()
    assert final['turns'][0].get('basis_status', 'current') == 'current'


def test_completing_another_threads_pending_turn_does_not_stale_valid_answer(tmp_path):
    p, ctx, _ = platform(tmp_path / 'pending.sqlite', [
        {'reply': 'The pasted SYN-2 result remains unverified.'},
        {'reply': 'The pasted SYN-1 result remains unverified.'}], initialize=True)
    pending = p.engineering_conversations.create(ctx, {})
    pending = p.engineering_conversations.enqueue(ctx, pending['id'], {
        'text': 'Synthetic assay data\nresult_id,value_mg_L\nSYN-1,9',
        'expected_revision': pending['revision']})
    other = send(p, ctx, p.engineering_conversations.create(ctx, {}),
        'Synthetic assay data\nresult_id,value_mg_L\nSYN-2,3')
    assert other['turns'][-1].get('basis_status', 'current') == 'current'
    completed = p.engineering_conversations.run_turn(ctx, pending['id'], pending['turn_ids'][-1])
    assert completed['turns'][-1]['status'] == 'completed'
    reopened = p.engineering_conversations.get(ctx, other['id'])
    assert reopened['turns'][-1].get('basis_status', 'current') == 'current'


def test_changed_manufacturing_evidence_still_invalidates_answer_after_reopen(tmp_path):
    db = tmp_path / 'manufacturing.sqlite'
    p, ctx, _ = platform(db, [], initialize=True)
    evidence = p.evidence.ingest(ctx, source_system='LIMS', source_record_id='ASSAY-1',
        content=b'ASSAY-1,9 mg/L', media_type='text/plain', site_id='NF1', event_time=None)
    eid = evidence['evidence_id']
    model = p.gateway.registry.profiles['anthropic-opus'].model
    p.gateway.providers['anthropic'].scripts[model] = [json.dumps({'reply': 'Inspecting the source.',
        'workflow': [{'node_id': 'inspect', 'task_kind': 'workspace_read', 'title': 'Inspect assay',
            'payload': {'kind': 'evidence', 'record_id': eid, 'revision': 1}, 'depends_on': []}]}),
        json.dumps({'reply': 'The LIMS record reports 9 mg/L; cause is unresolved.'})]
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Inspect the LIMS assay result.')
    assert result['turns'][-1].get('basis_status', 'current') == 'current'
    artifact = result['turns'][-1]['artifacts'][0]
    p.evidence.ingest(ctx, source_system='LIMS', source_record_id='ASSAY-1',
        content=b'ASSAY-1,7 mg/L', media_type='text/plain', site_id='NF1', event_time=None)
    p, ctx, _ = platform(db, [])
    reopened = p.engineering_conversations.get(ctx, result['id'])
    assert reopened['turns'][-1]['basis_status'] == 'stale'
    saved = p.engineering_conversations.artifact(ctx, result['id'], artifact['kind'], artifact['id'])
    assert saved['status'] == 'stale'
    assert saved['warnings']


def test_other_conversation_progress_during_inference_does_not_withhold_answer(tmp_path):
    p, ctx, fake = platform(tmp_path / 'overlap.sqlite', [], initialize=True)
    pending = p.engineering_conversations.create(ctx, {})
    pending = p.engineering_conversations.enqueue(ctx, pending['id'], {
        'text': 'Another synthetic test is still running.', 'expected_revision': pending['revision']})

    def complete(model, prompt):
        # Reproduce the live failure: another saved turn checkpoints while this
        # model request is in flight, without changing its original instruction.
        p.engineering_conversations._update_turn(ctx, pending['turn_ids'][-1],
            status='completed', reply='Other work completed.', elapsed_seconds=8.)
        return json.dumps({'reply': 'Revision 3 starts at the supplied July 1 boundary.'})

    fake.default = complete
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}),
        'Which synthetic revision applies at July 1, 2026, 00:00 UTC?')
    assert result['turns'][-1]['gateway_runs'][0]['status'] == 'completed'
    assert result['turns'][-1].get('basis_status', 'current') == 'current'


def test_actual_source_change_during_inference_reports_evidence_check_not_outage(tmp_path):
    p, ctx, fake = platform(tmp_path / 'source-change.sqlite', [], initialize=True)
    case = p.cases.open(ctx, 'DEV-1', 'priya', 'quinn', 'NF1')

    def complete(model, prompt):
        p.cases.add_timeline_event(ctx, case['case_id'], '2026-11-04T01:00:00Z',
            'A new assay result arrived during this request.')
        return json.dumps({'reply': 'This obsolete conclusion must be withheld.'})

    fake.default = complete
    thread = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {
        'text': 'Inspect the latest case.', 'expected_revision': thread['revision']})
    result = p.engineering_conversations.run_turn(ctx, queued['id'], queued['turn_ids'][-1])
    turn = result['turns'][-1]
    assert turn['gateway_runs'][0]['attempts'][0]['ok'] is True
    assert turn['gateway_runs'][0]['status'] == 'stale_basis'
    assert turn['status'] == 'blocked'
    assert turn['reply'] is None
    assert 'evidence changed' in turn['system_message'].lower()
    assert 'unavailable' not in turn['system_message'].lower()


def test_saved_work_search_is_discovery_not_dependency_on_live_progress(tmp_path):
    p, ctx, fake = platform(tmp_path / 'search-progress.sqlite', [], initialize=True)
    pending = p.engineering_conversations.create(ctx, {})
    pending = p.engineering_conversations.enqueue(ctx, pending['id'], {
        'text': 'OTHER-SYN-1: unverified synthetic context.', 'expected_revision': pending['revision']})

    def complete(model, prompt):
        if len(fake.calls) == 1:
            return json.dumps({'reply': 'Searching saved instructions.', 'workflow': [{
                'node_id': 'search', 'task_kind': 'workspace_search', 'title': 'Find saved context',
                'payload': {'kinds': ['engineering_chat_turn'], 'query': 'OTHER-SYN-1'}, 'depends_on': []}]})
        p.engineering_conversations._update_turn(ctx, pending['turn_ids'][-1],
            status='completed', reply='The other worker has finished.', elapsed_seconds=5.)
        return json.dumps({'reply': 'The search found a saved synthetic instruction, not verified evidence.'})

    fake.default = complete
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Find OTHER-SYN-1 in saved work.')
    turn = result['turns'][-1]
    assert len(fake.calls) == 2
    assert turn.get('basis_status', 'current') == 'current'
    artifact = turn['artifacts'][0]
    saved = p.engineering_conversations.artifact(ctx, result['id'], artifact['kind'], artifact['id'])
    assert saved['status'] == 'current'
    assert saved['records'][0]['id'] == pending['turn_ids'][-1]


def test_actual_saved_work_read_keeps_revision_checks(tmp_path):
    p, ctx, fake = platform(tmp_path / 'read-progress.sqlite', [], initialize=True)
    pending = p.engineering_conversations.create(ctx, {})
    pending = p.engineering_conversations.enqueue(ctx, pending['id'], {
        'text': 'OTHER-SYN-2: unverified synthetic context.', 'expected_revision': pending['revision']})
    other = p.store.read().require(TENANT, 'engineering_chat_turn', pending['turn_ids'][-1])

    def complete(model, prompt):
        if len(fake.calls) == 1:
            return json.dumps({'reply': 'Inspecting the saved answer.', 'workflow': [{
                'node_id': 'read', 'task_kind': 'workspace_read', 'title': 'Inspect saved work',
                'payload': {'kind': 'engineering_chat_turn', 'record_id': other.id, 'revision': other.revision}, 'depends_on': []}]})
        p.engineering_conversations._update_turn(ctx, other.id,
            status='completed', reply='New information arrived after the saved work inspection.')
        return json.dumps({'reply': 'The old inspected saved-work state should not be committed.'})

    fake.default = complete
    thread = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {
        'text': 'Inspect the saved OTHER-SYN-2 work.', 'expected_revision': thread['revision']})
    result = p.engineering_conversations.run_turn(ctx, queued['id'], queued['turn_ids'][-1])
    turn = result['turns'][-1]
    assert len(fake.calls) == 2
    assert turn['basis_status'] == 'stale'
    artifact = turn['artifacts'][0]
    with pytest.raises(ValueError, match='source is no longer current'):
        p.engineering_conversations.artifact(ctx, result['id'], artifact['kind'], artifact['id'])


def test_manufacturing_evidence_search_keeps_source_dependencies(tmp_path):
    p, ctx, _ = platform(tmp_path / 'evidence-search.sqlite', [], initialize=True)
    source = p.evidence.ingest(ctx, source_system='LIMS', source_record_id='SEARCH-ASSAY-1',
        content=b'SEARCH-ASSAY-1,9 mg/L', media_type='text/plain', site_id='NF1', event_time=None)
    thread = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {
        'text': 'Find the LIMS assay.', 'expected_revision': thread['revision']})
    turn = queued['turns'][-1]
    tools = p.engineering_conversations.workspace
    search = tools.search(ctx, queued, kinds=['evidence'], query='SEARCH-ASSAY-1')
    record = tools.save_result(ctx, queued, turn, search, 'Assay discovery')
    assert any(ref['id'] == source['evidence_id'] for ref in record['inputs'])
    p.evidence.ingest(ctx, source_system='LIMS', source_record_id='SEARCH-ASSAY-1',
        content=b'SEARCH-ASSAY-1,7 mg/L', media_type='text/plain', site_id='NF1', event_time=None)
    assert p.evidence.read_derived(ctx, 'assistant_workspace_result', record['id'])['status'] == 'stale'
