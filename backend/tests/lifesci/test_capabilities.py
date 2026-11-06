"""One assistant with capability packs: the request, roles and context choose the tools it is shown."""
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


def test_planner_shows_only_chosen_packs_and_records_them():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'quinn', 'qa', site_id='NF1')
    shown = prompt_for(p, 'quinn', 'Triage deviation signal SIG-1 on batch B-001')
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
