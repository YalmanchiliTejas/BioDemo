"""One assistant with capability packs: the request, roles and context choose the tools it is shown."""
import pytest

from src.lifesci import capabilities as cap
from src.lifesci.container import Platform
from src.lifesci.ids import iso, utc_now
from src.lifesci.store import RecordStore


def test_selection_by_keywords_roles_and_context():
    assert cap.select('Why did DEV-31 happen? open a CAPA') == ['core', 'quality']
    assert 'process' in cap.select('forecast titer for this transfer')
    assert cap.select('anything', roles=['operator']) == ['core', 'operations']
    assert 'process' in cap.select('hello', has_process_context=True)
    assert 'quality' in cap.select('hello', has_signal=True)
    # Nothing specific: every pack is offered rather than guessing tools away.
    assert cap.select('hello') == ['core', *[p.id for p in cap.PACKS]]


def test_operators_always_include_core_and_never_unknown_ids():
    ops = cap.operators(['quality'])
    assert {'workspace_search', 'workspace_read', 'workspace_propose_action', 'workspace_propose_investigation'} <= ops
    assert not any(o.startswith('physical_') for o in ops)
    assert cap.operators(['nope']) == set(cap.CORE.operators)


def prompt_for(p, who, text):
    thread = p.engineering_conversations.create(p.identity.context_for('T', who), {'site_id': 'NF1'})
    tid = f"turn-{thread['id']}"
    with p.store.transaction('fixture') as tx:
        tx.put('T', 'engineering_chat_turn', tid, {'conversation_id': thread['id'], 'site_id': 'NF1', 'user_text': text,
               'artifacts': [], 'status': 'running', 'created_at': iso(utc_now())}, expected_revision=None, action='fixture')
    return p.engineering_conversations._prompt(p.identity.context_for('T', who), {**thread, 'turn_ids': [tid]}, [])


def test_planner_shows_only_chosen_packs_and_records_them(monkeypatch):
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'quinn', 'qa', site_id='NF1')
    triage = 'Triage deviation signal SIG-1 on batch B-001'
    monkeypatch.delenv('INVESTIGATIONS_ENABLED_TENANTS', raising=False)
    off = prompt_for(p, 'quinn', triage)  # a paid feature: neither the tool nor an offer where it is off
    assert 'workspace_propose_investigation' not in off['operator_payload_schemas']
    assert any('not available in this workspace' in i for i in off['instructions'])
    monkeypatch.setenv('INVESTIGATIONS_ENABLED_TENANTS', 'T')
    shown = prompt_for(p, 'quinn', triage)
    assert shown['capabilities_used'] == ['core', 'quality']
    assert 'workspace_propose_investigation' in shown['operator_payload_schemas']
    assert not any(k.startswith('physical_') for k in shown['operator_payload_schemas'])
    assert [c['id'] for c in shown['capabilities']] == ['core', 'quality']


def test_deviation_signals_are_searchable_workspace_records():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'quinn', 'qa', site_id='NF1')
    q = p.identity.context_for('T', 'quinn')
    with p.store.transaction('fixture') as tx:
        tx.put('T', 'deviation_signal', 'SIG-1', {'signal_id': 'SIG-1', 'site_id': 'NF1', 'severity': 'action',
               'rule': 'DO 24 % < low 30 %', 'status': 'open', 'first_at': iso(utc_now())}, expected_revision=None, action='fixture')
    thread = p.engineering_conversations.create(q, {'site_id': 'NF1'})
    found = p.engineering_conversations.workspace.search(q, thread, kinds=['deviation_signal'], query='')
    assert [r['id'] for r in found['records']] == ['SIG-1'] and 'DO 24 %' in found['records'][0]['label']


@pytest.mark.parametrize('role,prompt', [
    ('msat', 'Save a routine to list cases every hour'),
    ('qa', 'Read the saved review result from Routines'),
    ('operator', 'List the records for my shift'),
])
def test_agent_can_discover_direct_tasks_saved_results_and_routine_drafts(role, prompt):
    """Capability filtering must not hide the tools the assistant is instructed to use."""
    from src.lifesci.process_engineering.tool_loop import ToolLoop
    p = Platform(RecordStore(), providers={})
    try:
        p.identity.assign_role('T', 'owner', role, site_id='NF1')
        ctx = p.identity.context_for('T', 'owner')
        thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
        queued = p.engineering_conversations.enqueue(ctx, thread['id'], {
            'text': prompt, 'expected_revision': thread['revision']})
        _, tools, _, _, _ = ToolLoop(p.engineering_conversations)._setup(ctx, queued)
        available = {tool['function']['name'] for tool in tools}
        assert {'workspace_run_task', 'workspace_open_task_result', 'workspace_propose_routine'} <= available
        # Discovery offers a proposal; it must not expose standing-work activation to the model.
        assert 'workspace_activate_routine' not in available
    finally:
        p.store.release_connections()
