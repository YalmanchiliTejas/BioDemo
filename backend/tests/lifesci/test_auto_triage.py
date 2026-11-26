"""Deviation signals wake the one assistant for read-only triage, within site limits, owned by QA."""
import pytest

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from src.lifesci.triage import TRIAGE, TriageService


def signal(sid='SIG-1', severity='action', site='NF1'):
    return {'signal_id': sid, 'site_id': site, 'severity': severity, 'kind': 'spec_excursion',
            'rule': 'DO 24 % < low 30 % (spec SPEC-DO-1 v2)', 'subject': {'kind': 'batch', 'id': 'B-2024-117'}}


@pytest.fixture
def p():
    platform = Platform(RecordStore(), providers={})
    platform.identity.assign_role('T', 'quinn', 'qa', site_id='NF1')
    platform.identity.assign_role('T', 'olu', 'operator', site_id='NF1')
    platform.identity.assign_role('T', 'bot', 'agent', site_id='NF1', actor_kind='agent')
    return platform


@pytest.fixture(autouse=True)
def action_threshold(monkeypatch):
    # These tests exercise triage on 'action' signals; the shipped default is 'critical' only (see the test below).
    import src.lifesci.triage as triage_module
    monkeypatch.setitem(triage_module.DEFAULTS, 'min_severity', 'action')


@pytest.fixture
def triage(p):
    reports, submitted = [], []
    service = TriageService(p, report=lambda t, s, st: reports.append((s, st)),
                            submit_turn=lambda ctx, thread, turn: submitted.append((ctx.delegated_from, thread, turn)))
    return service, reports, submitted


def ctx(p, who, kind='person'):
    return p.identity.context_for('T', who, actor_kind=kind)


def test_action_signal_starts_a_labelled_background_turn_owned_by_site_qa(p, triage):
    service, reports, submitted = triage
    state = service.on_signal('T', signal())
    assert state['status'] == 'running' and submitted[0][0] == 'quinn'
    thread = p.engineering_conversations.get(ctx(p, 'quinn'), state['conversation_id'])
    turn = thread['turns'][-1]
    assert turn['origin'] == 'background' and turn['triage_signal_id'] == 'SIG-1'
    assert turn['user_text'].startswith('Signal SIG-1: triage request (system-generated; not written by a person)')
    assert 'Never conclude a root cause' in turn['user_text']
    assert reports[-1] == ('SIG-1', state)


def test_below_threshold_paused_and_no_owner_are_skipped_with_reasons(p, triage):
    service, _, submitted = triage
    assert 'threshold' in service.on_signal('T', signal('SIG-W', 'warning'))['reason']
    service.set_settings(ctx(p, 'quinn'), 'NF1', {'paused': True})
    assert service.on_signal('T', signal('SIG-P'))['reason'] == 'auto-triage is paused for this site'
    assert 'no QA reviewer' in service.on_signal('T', signal('SIG-X', site='NF9'))['reason']
    assert submitted == []


def test_daily_cap_is_enforced_and_reported(p, triage):
    service, _, submitted = triage
    service.set_settings(ctx(p, 'quinn'), 'NF1', {'daily_cap': 1})
    assert service.on_signal('T', signal('SIG-1'))['status'] == 'running'
    skipped = service.on_signal('T', signal('SIG-2'))
    assert skipped['status'] == 'skipped' and 'daily auto-triage limit (1)' in skipped['reason']
    assert len(submitted) == 1


def test_idempotent_per_signal_and_reruns_only_on_escalation(p, triage):
    service, _, submitted = triage
    first = service.on_signal('T', signal())
    assert service.on_signal('T', signal()) == first and len(submitted) == 1
    during = service.on_signal('T', signal(severity='critical'))  # still running: no second concurrent run
    assert during['turn_id'] == first['turn_id'] and 'escalated to critical' in during['reason'] and len(submitted) == 1
    with p.store.transaction('fixture') as tx:
        turn = tx.require('T', 'engineering_chat_turn', first['turn_id'])
        tx.put('T', 'engineering_chat_turn', turn.id, {**turn.state, 'status': 'completed'}, expected_revision=turn.revision, action='fixture')
    service.refresh('T', 'SIG-1')
    # Finished; a later, higher escalation starts a fresh turn in the same conversation.
    with p.store.transaction('fixture') as tx:
        rec = tx.require('T', 'signal_triage', 'SIG-1')
        tx.put('T', 'signal_triage', 'SIG-1', {**rec.state, 'severity_handled': 2}, expected_revision=rec.revision, action='fixture')
    escalated = service.on_signal('T', signal(severity='critical'))
    assert escalated['conversation_id'] == first['conversation_id'] and escalated['turn_id'] != first['turn_id']
    assert len(submitted) == 2


def test_unavailable_model_leaves_a_visible_failed_state_and_nothing_is_executed(p):
    reports = []
    service = TriageService(p, report=lambda t, s, st: reports.append(st))  # inline run, no model configured
    state = service.on_signal('T', signal())
    assert state['status'] == 'failed' and state['reason']
    assert reports[-1]['status'] == 'failed'
    assert p.store.read().list('T', 'case') == []  # triage never opens a case
    assert p.store.read().list('T', 'notification') == []  # nor sends anything


def test_refresh_moves_a_finished_turn_to_ready(p, triage):
    service, reports, _ = triage
    state = service.on_signal('T', signal())
    with p.store.transaction('fixture') as tx:
        turn = tx.require('T', 'engineering_chat_turn', state['turn_id'])
        tx.put('T', 'engineering_chat_turn', turn.id, {**turn.state, 'status': 'completed'}, expected_revision=turn.revision, action='fixture')
    assert service.refresh('T', 'SIG-1')['status'] == 'ready' and reports[-1][1]['status'] == 'ready'
    assert service.refresh_active('T') == 0


def test_settings_need_a_person_with_approve(p, triage):
    service, _, _ = triage
    with pytest.raises(PermissionError):
        service.set_settings(ctx(p, 'bot', 'agent'), 'NF1', {'paused': True})
    with pytest.raises(Exception):
        service.set_settings(ctx(p, 'olu'), 'NF1', {'paused': True})
    with pytest.raises(ValueError):
        service.set_settings(ctx(p, 'quinn'), 'NF1', {'min_severity': 'urgent'})
    assert service.settings('T', 'NF1') == {'min_severity': 'action', 'daily_cap': 5, 'paused': False, 'site_id': 'NF1'}
    assert p.store.read().list('T', TRIAGE) == []


def test_shipped_default_only_triages_critical_signals():
    import importlib, src.lifesci.triage as triage_module
    defaults = importlib.reload(triage_module).DEFAULTS
    assert defaults['min_severity'] == 'critical' and defaults['daily_cap'] == 5
