"""End to end on the wired platform: out-of-spec data -> signal -> in-app alert for QA -> assistant triage turn."""
import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


@pytest.fixture
def p():
    platform = Platform(RecordStore(), providers={})
    for actor, role in (('qa1', 'qa'), ('sup', 'supervisor'), ('op', 'operator')):
        platform.identity.assign_role('T', actor, role, site_id='NF1')
    return platform


def ctx(p, who):
    return p.identity.context_for('T', who)


def historian(p, value, seq):
    return p.evidence.ingest(ctx(p, 'op'), source_system='HISTORIAN', source_record_id=f'DO-{seq}',
                             content=json.dumps({'tag': 'DO', 'value': value}).encode(), media_type='application/json',
                             site_id='NF1', event_time=None,
                             metadata={'mapped': {'tag': 'DO', 'value': value, 'equipment_id': 'BR-07', 'batch_id': 'B-117'},
                                       'units': {'value': '%'}})


def inbox(p, who):
    return p.alerts.inbox(ctx(p, who))['items']


def test_out_of_spec_value_alerts_qa_and_starts_triage_once(p):
    p.triage.set_settings(ctx(p, 'qa1'), 'NF1', {'min_severity': 'action'})  # default triages critical only
    p.specifications.create(ctx(p, 'qa1'), site_id='NF1', parameter='DO [%]', unit='%', low=30, high=80,
                            critical_low=15, reason='Batch record v3')
    historian(p, 24, 1)
    [signal] = p.signals.list(ctx(p, 'qa1'))
    assert signal['severity'] == 'action' and signal['status'] == 'open'
    # QA and the supervisor are told in-app; the operator is not on the default route.
    assert inbox(p, 'qa1') and inbox(p, 'sup') and not inbox(p, 'op')
    state = p.signals.get(ctx(p, 'qa1'), signal['signal_id'])
    assert state['alerts']['sent'] >= 2 and state['alerts']['severity'] == 'action'
    # The assistant was fired: a labelled background turn in a conversation owned by QA.
    assert state['triage']['status'] in ('running', 'ready', 'failed') and state['triage'].get('conversation_id')
    thread = p.engineering_conversations.get(ctx(p, 'qa1'), state['triage']['conversation_id'])
    assert thread['turns'][0]['user_text'].startswith(f"Signal {signal['signal_id']}")
    # A repeat value coalesces: no second alert, no second triage.
    before = len(inbox(p, 'qa1'))
    historian(p, 25, 2)
    p.signal_followup.sweep(['T'])
    assert len(p.signals.list(ctx(p, 'qa1'))) == 1 and len(inbox(p, 'qa1')) == before
    assert len(p.engineering_conversations.list_for(ctx(p, 'qa1'))) == 1
    # No case was opened by the system.
    assert p.store.read().list('T', 'case') == []


def test_escalation_alerts_again(p):
    p.specifications.create(ctx(p, 'qa1'), site_id='NF1', parameter='DO [%]', unit='%', low=30, high=80,
                            critical_low=15, reason='Batch record v3')
    historian(p, 24, 1)
    first = len(inbox(p, 'qa1'))
    historian(p, 10, 2)  # below the critical limit
    [signal] = p.signals.list(ctx(p, 'qa1'))
    assert signal['severity'] == 'critical'
    assert p.signals.get(ctx(p, 'qa1'), signal['signal_id'])['alerts']['severity'] == 'critical'
    assert len(inbox(p, 'qa1')) > first


def test_default_threshold_alerts_but_does_not_triage_an_action_signal(p):
    p.specifications.create(ctx(p, 'qa1'), site_id='NF1', parameter='DO [%]', unit='%', low=30, high=80,
                            critical_low=15, reason='Batch record v3')
    historian(p, 24, 1)
    [signal] = p.signals.list(ctx(p, 'qa1'))
    state = p.signals.get(ctx(p, 'qa1'), signal['signal_id'])
    assert inbox(p, 'qa1') and state['triage']['status'] == 'skipped' and state['triage']['reason']
