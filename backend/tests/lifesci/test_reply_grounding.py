"""Reply grounding through the real conversation service; only the model is scripted."""
import json

from tests.lifesci.test_conversation_instruction_provenance import platform, send


def _ask(tmp_path, final):
    p, ctx, _ = platform(tmp_path / 'g.sqlite', [], initialize=True)
    eid = p.evidence.ingest(ctx, source_system='LIMS', source_record_id='ASSAY-9',
        content=b'ASSAY-9 result 2500 mg/L; minimum 2.8 g/L.', media_type='text/plain',
        site_id='NF1', event_time=None)['evidence_id']
    model = p.gateway.registry.profiles['anthropic-opus'].model
    p.gateway.providers['anthropic'].scripts[model] = [json.dumps({'reply': 'Inspecting.', 'workflow': [
        {'node_id': 'inspect', 'task_kind': 'workspace_read', 'title': 'Inspect assay',
         'payload': {'kind': 'evidence', 'record_id': eid, 'revision': 1}, 'depends_on': []}]}),
        json.dumps(final(eid))]
    return send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Does ASSAY-9 meet its minimum?')['turns'][-1]


def test_quoted_and_derived_claims_are_grounded(tmp_path):
    turn = _ask(tmp_path, lambda eid: {'reply': 'ASSAY-9 is 2500 mg/L (2.5 g/L), below the 2.8 g/L minimum.', 'claims': [
        {'text': 'result is 2500 mg/L', 'source_id': eid, 'quote': 'result 2500 mg/L'},
        {'text': '2500 mg/L equals 2.5 g/L', 'kind': 'derived', 'source_id': eid, 'quote': 'result 2500 mg/L'},
        {'text': 'minimum is 2.8 g/L', 'source_id': eid, 'quote': 'minimum 2.8 g/L'}]})
    assert turn['grounding']['status'] == 'grounded', turn['grounding']
    assert turn['grounding']['derived_numbers'] == [2.5]


def test_the_time_a_record_was_read_does_not_vouch_for_an_invented_value():
    """The test below failed whenever it ran during minute 26 of an hour, and would have all day on the 26th."""
    from src.lifesci.process_engineering.grounding import check_reply, source_text
    for stamp in ('2026-11-17T05:26:41.123456+00:00', '2026-11-26T05:13:41.123456+00:00', '2026-11-17T05:13:26+00:00', '2026-11-26'):
        seen = {'e1': source_text({'kind': 'evidence', 'id': 'e1', 'ingested_at': stamp, 'data': {'original': 'ASSAY-9 result 2500 mg/L.'}})}
        assert check_reply('ASSAY-9 is 2600 mg/L and passed.', [], seen)['unsupported_numbers'] == [2600.0], stamp
        assert check_reply('ASSAY-9 is 0.26 g/L.', [], seen)['unsupported_numbers'] == [0.26], stamp
    # The date itself can be restated, and a value that is in the source still converts between units.
    seen = {'e1': source_text({'id': 'e1', 'ingested_at': '2026-11-26T05:26:41+00:00', 'data': {'original': 'ASSAY-9 result 2500 mg/L.'}})}
    assert check_reply('Read on 26 November 2026 at 05:26: 2500 mg/L, which is 2.5 g/L.', [], seen)['unsupported_numbers'] == []


def test_invented_number_and_fake_quote_are_flagged_not_hidden(tmp_path):
    turn = _ask(tmp_path, lambda eid: {'reply': 'ASSAY-9 is 2600 mg/L and passed.', 'claims': [
        {'text': 'assay passed', 'source_id': eid, 'quote': 'result passed'}]})
    assert turn['reply'] == 'ASSAY-9 is 2600 mg/L and passed.'
    assert turn['grounding']['status'] == 'ungrounded'
    assert turn['grounding']['unsupported_numbers'] == [2600.0]
    assert turn['grounding']['claims'][0]['problem'] == 'quote_not_found'
