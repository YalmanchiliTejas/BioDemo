"""Deviation-signal alerts: admin-only configuration, recipients, idempotency, escalation, content limits, inbox."""
import pytest

from src.lifesci.alerts import AlertService, SIGNAL
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


class FakeResponse:
    status_code = 200

    def json(self):
        return {}


class FakeHttp:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append({'url': url, **kwargs})
        return FakeResponse()


class FakeSmtp:
    sent = []

    def __init__(self, host, port, timeout=15):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        FakeSmtp.sent.append(msg)


@pytest.fixture
def p(monkeypatch):
    monkeypatch.setenv('APP_URL', 'https://app.example')
    platform = Platform(RecordStore(), providers={})
    idn = platform.identity
    idn.assign_role('T', 'admin1', 'admin')
    idn.assign_role('T', 'site-admin', 'admin', site_id='NF1')
    idn.assign_role('T', 'qa1', 'qa', site_id='NF1')
    idn.assign_role('T', 'qa2', 'qa', site_id='NF2')
    idn.assign_role('T', 'qa-global', 'qa')
    idn.assign_role('T', 'sup1', 'supervisor', site_id='NF1')
    idn.assign_role('T', 'op1', 'operator', site_id='NF1')
    idn.assign_role('T', 'bot', 'agent', site_id='NF1', actor_kind='agent')
    with platform.store.transaction('fixture') as tx:
        for actor in ('qa1', 'qa-global', 'sup1', 'admin1'):
            tx.put('T', 'organization_member', actor, {'email': f'{actor}@example.test'}, expected_revision=None, action='fixture')
    FakeSmtp.sent = []
    platform.http = FakeHttp()
    platform.alerts = AlertService(platform, transport=platform.http, smtp_factory=FakeSmtp)
    return platform


def ctx(p, who, kind='person'):
    return p.identity.context_for('T', who, actor_kind=kind)


def signal(p, severity='action', sid='sig-1', site='NF1'):
    state = {'signal_id': sid, 'site_id': site, 'kind': 'spec_excursion', 'severity': severity,
             'rule': 'DO 24 % < low 30 % (spec SPEC-DO-1 v2)', 'subject': {'kind': 'batch', 'id': 'B-2024-117'},
             'evidence_refs': [{'kind': 'evidence', 'id': 'lims:B-2024-117'}],
             'details': {'note': 'SECRET SOURCE TEXT that must never leave the platform'},
             'occurrences': 1, 'first_at': '2026-11-05T10:00:00+00:00', 'last_at': '2026-11-05T10:00:00+00:00',
             'status': 'open'}
    with p.store.transaction('fixture') as tx:
        current = tx.get('T', SIGNAL, sid)
        tx.put('T', SIGNAL, sid, {**(current.state if current else {}), **state},
               expected_revision=current.revision if current else None, action='fixture')
    return state


def configure(p):
    a = ctx(p, 'admin1')
    slack = p.alerts.save_channel(a, {'kind': 'slack', 'name': '#qa-alerts', 'secrets': {'webhook_url': 'https://hooks.slack.com/services/T/B/X'}})
    email = p.alerts.save_channel(a, {'kind': 'email', 'name': 'QA mail', 'config': {'host': 'smtp.example', 'port': 587, 'from_addr': 'alerts@example.test'},
                                      'secrets': {'username': 'u', 'password': 'pw-secret'}})
    p.alerts.save_route(a, {'site_id': 'NF1', 'min_severity': 'action', 'roles': ['qa', 'supervisor'],
                            'channels': [slack['channel_id'], email['channel_id']]})
    return slack, email


def test_only_org_wide_admins_configure_and_secrets_are_never_returned(p):
    for who, kind in (('qa1', 'person'), ('site-admin', 'person'), ('bot', 'agent')):
        with pytest.raises(PermissionError):
            p.alerts.save_channel(ctx(p, who, kind), {'kind': 'slack', 'secrets': {'webhook_url': 'https://hooks.slack.com/x'}})
    slack, email = configure(p)
    listed = p.alerts.channels(ctx(p, 'admin1'))
    text = repr(listed)
    assert 'hooks.slack.com' not in text and 'pw-secret' not in text
    assert {c['channel_id']: c['secret_fields'] for c in listed}[email['channel_id']] == ['password', 'username']


def test_webhooks_only_to_provider_hosts(p):
    with pytest.raises(ValueError):
        p.alerts.save_channel(ctx(p, 'admin1'), {'kind': 'slack', 'secrets': {'webhook_url': 'https://169.254.169.254/latest'}})
    with pytest.raises(ValueError):
        p.alerts.save_channel(ctx(p, 'admin1'), {'kind': 'teams', 'secrets': {'webhook_url': 'http://x.webhook.office.com/a'}})


def test_default_route_alerts_site_qa_and_supervisor_in_app(p):
    out = p.alerts.on_signal('T', signal(p))
    assert out['routes'] == ['default']
    people = {i['recipient_id'] for who in ('qa1', 'qa-global', 'sup1', 'qa2', 'op1')
              for i in p.alerts.inbox(ctx(p, who))['items']}
    assert people == {'qa1', 'qa-global', 'sup1'}  # NF2 QA and the operator are not routed
    assert p.alerts.on_signal('T', signal(p, severity='warning', sid='sig-w'))['sent'] == 0  # below default threshold


def test_repeat_does_not_realert_but_escalation_does(p):
    configure(p)
    first = p.alerts.on_signal('T', signal(p))
    assert first['sent'] > 0
    assert len(p.http.calls) == 1 and len(FakeSmtp.sent) == 3  # one channel post; one email per routed person (qa1, qa-global, sup1)
    assert p.alerts.on_signal('T', signal(p))['sent'] == 0
    assert len(p.http.calls) == 1 and len(FakeSmtp.sent) == 3
    p.alerts.on_signal('T', signal(p, severity='critical'))
    assert len(p.http.calls) == 2 and len(FakeSmtp.sent) == 6
    assert p.store.read().require('T', SIGNAL, 'sig-1').state['alerts']['sent'] >= first['sent']


def test_external_body_has_rule_and_link_but_no_document_text(p):
    configure(p)
    p.alerts.on_signal('T', signal(p))
    posted = p.http.calls[0]['json']['text']
    mailed = FakeSmtp.sent[0].get_content()
    for body in (posted, mailed):
        assert 'DO 24 % < low 30 %' in body and 'https://app.example/signals/?id=sig-1' in body
        assert 'SECRET SOURCE TEXT' not in body and 'lims:' not in body
        assert 'not a confirmed deviation' in body


def test_dismissed_signals_are_not_alerted(p):
    assert p.alerts.on_signal('T', {**signal(p), 'status': 'dismissed'})['sent'] == 0


def test_triage_ready_updates_inbox_and_channels_once(p):
    configure(p)
    p.alerts.on_signal('T', signal(p))
    p.alerts.mark_read(ctx(p, 'qa1'), p.alerts.inbox(ctx(p, 'qa1'))['items'][0]['inbox_id'])
    before = len(p.http.calls)
    p.alerts.on_triage_ready('T', signal(p))
    p.alerts.on_triage_ready('T', signal(p))
    item = p.alerts.inbox(ctx(p, 'qa1'))['items'][0]
    assert item['read_at'] is None and [u['kind'] for u in item['updates']] == ['triage_ready']
    assert len(p.http.calls) == before + 1


def test_inbox_is_private_unread_first(p):
    p.alerts.on_signal('T', signal(p, sid='sig-a'))
    p.alerts.on_signal('T', signal(p, sid='sig-b'))
    mine = p.alerts.inbox(ctx(p, 'qa1'))
    assert mine['unread'] == 2
    p.alerts.mark_read(ctx(p, 'qa1'), mine['items'][0]['inbox_id'])
    again = p.alerts.inbox(ctx(p, 'qa1'))
    assert again['unread'] == 1 and again['items'][0]['read_at'] is None
    with pytest.raises(PermissionError):
        p.alerts.mark_read(ctx(p, 'sup1'), mine['items'][0]['inbox_id'])


def test_test_channel_sends_a_test_message(p):
    slack, _ = configure(p)
    out = p.alerts.test_channel(ctx(p, 'admin1'), slack['channel_id'])
    assert out['status'] == 'sent' and 'test' in p.http.calls[-1]['json']['text'].lower()
    with pytest.raises(PermissionError):
        p.alerts.test_channel(ctx(p, 'qa1'), slack['channel_id'])


def test_routes_mount_and_require_admin(p):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.lifesci.alerts import alert_routes
    app = FastAPI()
    who = {'id': 'qa1'}
    alert_routes(app, p, lambda: ctx(p, who['id']))
    client = TestClient(app)
    assert client.get('/v1/alert-channels').status_code == 403
    p.alerts.on_signal('T', signal(p))
    items = client.get('/v1/notifications').json()['items']
    assert items and client.post(f"/v1/notifications/{items[0]['inbox_id']}/read").status_code == 200
    who['id'] = 'admin1'
    assert client.post('/v1/alert-routes', json={'min_severity': 'critical', 'roles': ['qa'], 'channels': []}).status_code == 200
    assert client.get('/v1/alert-routes').json()['routes'][0]['min_severity'] == 'critical'
