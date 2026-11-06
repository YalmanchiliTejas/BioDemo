"""Public demo workspaces: anonymous-only, isolated, synthetic, limited, expiring, with a separate feedback corpus."""
import json
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src.lifesci import demo as demo_module
from src.lifesci.api import create_app
from src.lifesci.cmo_datasets import require_dataset
from src.lifesci.container import Platform
from src.lifesci.demo import CONTROL, CORPUS, FeedbackIn, PERSONA_ROLES
from src.lifesci.ids import iso, utc_now
from src.lifesci.store import ConflictError, RecordStore
from src.lifesci.supabase_auth import supabase_resolver


class FakeVerifier:
    """Bearer anon-<id> is an anonymous Supabase user; Bearer user-<id> a normal account."""
    tenant = 'deployment'

    def verify(self, authorization):
        kind, _, sub = (authorization or '').removeprefix('Bearer ').partition('-')
        return {'sub': f'{kind}-{sub}', 'is_anonymous': kind == 'anon', 'email': None if kind == 'anon' else f'{sub}@x.test'}


@pytest.fixture
def p():
    return Platform(RecordStore(), providers={})


@pytest.fixture
def api(p, monkeypatch):
    monkeypatch.delenv('CMO_API_TOKEN', raising=False)
    monkeypatch.setenv('LIFESCI_AUTH_MODE', 'supabase')
    return TestClient(create_app(p, resolver=supabase_resolver(p, verifier=FakeVerifier())))


def start(api, who='anon-1', persona='qa', accepted=True):
    return api.post('/v1/demo/workspaces', json={'persona': persona, 'accepted_notice': accepted},
                    headers={'Authorization': f'Bearer {who}'})


def as_visitor(who, tenant):
    return {'Authorization': f'Bearer {who}', 'X-Organization-Id': tenant}


def test_only_anonymous_visitors_create_demo_workspaces_and_notice_is_required(api):
    assert start(api, 'user-real').status_code == 403  # a real account never gets a demo tenant
    assert start(api, accepted=False).status_code == 400
    created = start(api)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body['tenant_id'].startswith('demo_') and body['messages_left'] == 20 and len(body['scenarios']) >= 3
    assert start(api).json()['tenant_id'] == body['tenant_id']  # one active workspace per visitor
    # The visitor can list (only) this workspace and use it.
    account = api.get('/v1/account', headers={'Authorization': 'Bearer anon-1'}).json()
    assert [o['id'] for o in account['organizations']] == [body['tenant_id']]
    assert api.get('/v1/demo/workspace', headers=as_visitor('anon-1', body['tenant_id'])).json()['persona'] == 'qa'
    # Anonymous visitors cannot reach any other organization.
    assert api.get('/v1/demo/workspace', headers={'Authorization': 'Bearer anon-1'}).status_code == 403


@pytest.mark.parametrize('persona', sorted(PERSONA_ROLES))
def test_persona_role_is_org_wide_and_seed_is_synthetic_and_quiet(p, persona):
    view = p.demo.provision('anon-x', persona, True)
    ctx = p.identity.context_for(view['tenant_id'], 'anon-x')
    assert ctx.roles == {PERSONA_ROLES[persona]} and not ctx.site_ids
    assert require_dataset(p, ctx, view['dataset_id'], 'NF1').state['metadata']['synthetic'] is True
    signals = {(s['kind'], s['severity']): s for s in p.signals.list(ctx)}
    assert ('qms_deviation', 'critical') in signals and ('spec_excursion', 'action') in signals
    # Seeding never starts a model call: triage is paused in demo workspaces.
    assert all(s['triage']['status'] == 'skipped' for s in signals.values())
    cases = {r.id: r.state for r in p.store.read().list(view['tenant_id'], 'case')}
    assert sorted(i for i, c in cases.items() if c['status'] == 'closed') == ['DEV-12', 'DEV-19']
    assert cases['DEV-31']['status'] == 'open'


def test_workspaces_are_isolated_between_visitors(api):
    a, b = start(api, 'anon-a').json(), start(api, 'anon-b').json()
    assert a['tenant_id'] != b['tenant_id']
    assert api.get('/v1/demo/workspace', headers=as_visitor('anon-b', a['tenant_id'])).status_code == 403
    assert api.get('/v1/signals', headers=as_visitor('anon-b', a['tenant_id'])).status_code == 403


def test_uploads_are_refused_in_demo_workspaces(api):
    t = start(api).json()['tenant_id']
    refused = api.post('/api/cmo-ingestion/deliveries', json={'cmo': 'Mine', 'name': 'x'}, headers=as_visitor('anon-1', t))
    assert refused.status_code == 403 and 'sample data' in refused.text


def test_per_workspace_and_daily_message_limits(p, monkeypatch):
    t = p.demo.provision('anon-1', 'msat', True)['tenant_id']
    ctx = p.identity.context_for(t, 'anon-1')
    monkeypatch.setattr(demo_module, 'PER_WORKSPACE', 2)
    p.demo.consume_message(ctx); p.demo.consume_message(ctx)
    with pytest.raises(ConflictError, match="used this demo's 2 messages"):
        p.demo.consume_message(ctx)
    other = p.identity.context_for(p.demo.provision('anon-2', 'qa', True)['tenant_id'], 'anon-2')
    monkeypatch.setattr(demo_module, 'GLOBAL_DAILY', 2)  # two messages already used today
    with pytest.raises(ConflictError, match="today's limit"):
        p.demo.consume_message(other)
    # The limit is enforced where turns are queued.
    thread = p.engineering_conversations.create(other, {'site_id': 'NF1'})
    with pytest.raises(ConflictError):
        p.engineering_conversations.enqueue(other, thread['id'], {'text': 'Hello', 'expected_revision': thread['revision']})


def expire(p, tenant):
    with p.store.transaction('test') as tx:
        rec = tx.require(CONTROL, 'demo_workspace', tenant)
        tx.put(CONTROL, 'demo_workspace', tenant, {**rec.state, 'expires_at': iso(utc_now() - timedelta(minutes=1))},
               expected_revision=rec.revision, action='test_expire')


def test_expiry_returns_410_and_revokes_access(api, p):
    t = start(api).json()['tenant_id']
    expire(p, t)
    assert api.get('/v1/demo/workspace', headers=as_visitor('anon-1', t)).status_code == 410
    p.demo.tick()
    assert not p.identity.context_for(t, 'anon-1').roles
    assert p.store.read().require(CONTROL, 'demo_workspace', t).state['status'] == 'expired'
    assert start(api).json()['tenant_id'] != t  # a new visit gets a fresh workspace


def completed_turn(p, ctx):
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'Triage DEV-31', 'expected_revision': thread['revision']})
    turn_id = queued['turns'][-1]['id']
    with p.store.transaction('test') as tx:
        rec = tx.require(ctx.tenant_id, 'engineering_chat_turn', turn_id)
        tx.put(ctx.tenant_id, 'engineering_chat_turn', turn_id, {**rec.state, 'status': 'completed', 'reply': 'DEV-31 summary.'},
               expected_revision=rec.revision, action='test_complete')
    return thread['id'], turn_id


def test_feedback_and_transcripts_go_only_to_the_corpus(p):
    t = p.demo.provision('anon-1', 'qa', True)['tenant_id']
    ctx = p.identity.context_for(t, 'anon-1')
    thread_id, turn_id = completed_turn(p, ctx)
    out = p.demo.feedback(ctx, FeedbackIn(kind='answer', turn_id=turn_id, rating='down', comment='Missed the lot'))
    stored = p.store.read().require(CORPUS, 'demo_feedback', out['feedback_id']).state
    assert stored['persona'] == 'qa' and stored['turn']['reply'] == 'DEV-31 summary.' and stored['rating'] == 'down'
    p.demo.feedback(ctx, FeedbackIn(kind='scenario', scenario_id='qa-triage', realistic=4, useful=5))
    with pytest.raises(ValueError):
        p.demo.feedback(ctx, FeedbackIn(kind='scenario', scenario_id='nope'))
    # Nothing of the corpus lives in the visitor's tenant.
    assert p.store.read().list(t, 'demo_feedback') == []
    assert p.demo.snapshot_workspace(t) == 1 and p.demo.snapshot_workspace(t) == 0  # idempotent per turn
    transcript = p.store.read().require(CORPUS, 'demo_transcript', f'{t}:{thread_id}').state
    assert transcript['persona'] == 'qa' and transcript['turns'][0]['user_text'] == 'Triage DEV-31'
    assert {'gateway_runs', 'steps', 'artifacts', 'capabilities_used'} <= set(transcript['turns'][0])


def test_purge_deletes_only_expired_workspaces_and_old_corpus(tmp_path):
    url = f'sqlite:///{tmp_path / "demo.db"}'
    p = Platform(RecordStore(url), providers={})
    old, kept = p.demo.provision('anon-old', 'qa', True)['tenant_id'], p.demo.provision('anon-new', 'msat', True)['tenant_id']
    p.demo.feedback(p.identity.context_for(kept, 'anon-new'), FeedbackIn(kind='overall', useful=4))
    with p.store.transaction('test') as tx:
        tx.put(CORPUS, 'demo_feedback', 'ancient', {'recorded_at': iso(utc_now() - timedelta(days=91))}, expected_revision=None, action='t')
    expire(p, old)
    result = demo_module.purge(url)
    assert result['purged_workspaces'] == [old] and result['purged_corpus_items'] == 1
    db = sqlite3.connect(tmp_path / 'demo.db')
    count = lambda tenant: db.execute('SELECT COUNT(*) FROM aggregate_revisions WHERE tenant_id=?', (tenant,)).fetchone()[0]
    assert count(old) == 0 and db.execute('SELECT COUNT(*) FROM audit WHERE tenant_id=?', (old,)).fetchone()[0] == 0
    assert count(kept) > 0
    assert db.execute("SELECT COUNT(*) FROM aggregates WHERE tenant_id=? AND id='ancient'", (CORPUS,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM aggregates WHERE tenant_id=? AND kind='demo_feedback'", (CORPUS,)).fetchone()[0] == 1
    with pytest.raises(sqlite3.DatabaseError, match='append-only'):  # triggers are back after the purge
        db.execute('DELETE FROM audit WHERE tenant_id=?', (kept,))


def test_demo_at_capacity_is_429_not_a_conflict(api, monkeypatch):
    # The frontend shows "at capacity, talk to us" on 429; plain 409s are edit conflicts.
    import src.lifesci.demo as demo_module
    monkeypatch.setattr(demo_module, 'GLOBAL_DAILY', 0)
    response = start(api, 'anon-capacity')
    assert response.status_code == 429 and 'capacity' in response.json()['detail']
