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


def test_the_process_engineer_do_drop_plan_runs_every_step_in_a_demo_workspace(p, monkeypatch):
    """Replays the 8-step plan that stuck live (2026-11-06): non-record IDs and guessed revisions must not stop it."""
    monkeypatch.setenv('ASSISTANT_LOOP', 'planner')  # a planner-path replay; demo workspaces default to the tool loop
    from tests.lifesci.test_engineering_conversation import fake_planner, node
    t = p.demo.provision('anon-pe', 'process_engineer', True)['tenant_id']
    ctx = p.identity.context_for(t, 'anon-pe')
    search = lambda q: {'mode': 'search', 'query': q}
    steps = [node('read_dev31', 'workspace_read', {'kind': 'case', 'record_id': 'DEV-31', 'revision': 1}),
             node('mentions_dev31', 'workspace_search', search('DEV-31')),
             node('links_b117', 'workspace_search', {'mode': 'links', 'record_kind': 'batch', 'record_id': 'B-117'}),
             node('mentions_br07', 'workspace_search', search('BR-07')),
             node('mentions_do', 'workspace_search', search('dissolved oxygen')),
             node('similar_b117', 'workspace_search', {'mode': 'similar_cases', 'case_id': 'B-117', 'query': 'DO below 30 % foaming'}),
             node('read_dev19', 'workspace_read', {'kind': 'case', 'record_id': 'DEV-19', 'revision': 1}),
             node('read_dev12', 'workspace_read', {'kind': 'batch', 'record_id': 'DEV-12', 'revision': 1})]
    fake_planner(p, [{'reply': 'Looking into B-117.', 'workflow': steps}, {'reply': 'DO fell in B-117 on BR-07; see DEV-31.'}])
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'DO fell below 30 % in B-117', 'expected_revision': thread['revision']})
    turn = p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])['turns'][-1]
    assert turn['status'] == 'completed', turn['issues']
    assert turn['planning_calls_admitted'] == 2 and len(turn['artifacts']) == len(steps)


def test_demo_data_answers_what_the_live_e2e_run_found_missing(p):
    """2026-11-07 e2e on sievance.com: the assistant called the seed untrustworthy, saw 1 of 6 runs, couldn't read
    closure conclusions, explained 'opened != occurred' every time, and offered a feature that is off in demos."""
    import json as _json
    t = p.demo.provision('anon-e2e', 'msat', True)['tenant_id']
    ctx = p.identity.context_for(t, 'anon-e2e')
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    ws = p.engineering_conversations.workspace
    rec = p.store.read().require(t, 'evidence', 'cmo-verified-delivery:demo-september')
    data = _json.loads(p.evidence.original(ctx, rec.id))
    assert len(data['measurements'][0]['source_sha256']) == 64 and len(data['guarantee']['checks']) == 2
    read = ws.read(ctx, thread, kind='evidence', record_id=rec.id, revision=rec.revision)['record']['data']
    assert len(read['dataset_summary']['batches']) == 6 and len(read['original']) <= 1000 and read['dataset_summary']['series']
    dev12 = ws.read(ctx, thread, kind='case', record_id='DEV-12', revision=p.store.read().require(t, 'case', 'DEV-12').revision)
    assert 'pump AF-2 seal worn' in dev12['record']['data']['closure']['root_cause']
    assert p.store.read().require(t, 'case', 'DEV-31').state['opened_at'].startswith('2026-11-03')
    assert p.store.read().require(t, 'batch', 'B-117').state['equipment_id'] == 'BR-07'
    assert 'ERP:LOT-L-8812' in {r['id'] for r in ws.links(ctx, thread, kind='batch', record_id='L-8812')['records']}
    p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'Is this delivery trustworthy?', 'expected_revision': thread['revision']})
    prompt = p.engineering_conversations._prompt(ctx, p.engineering_conversations._thread(ctx, thread['id']).state, [])
    assert 'workspace_propose_investigation' not in prompt['operator_payload_schemas']
    assert prompt['current_user_id'] == 'anon-e2e' and prompt['user_roles'] == ['msat']


@pytest.mark.parametrize('persona', sorted(PERSONA_ROLES))
def test_no_lookup_the_assistant_can_plausibly_make_stops_a_turn(p, persona):
    """Every workspace tool on every demo record and on every ID in the scenarios, tried as every kind."""
    from src.lifesci.demo_scenarios import SCENARIOS
    from src.lifesci.process_engineering.workspace import ID_PATTERN, KINDS
    from src.lifesci.store import NotFoundError
    t = p.demo.provision(f'anon-{persona}', persona, True)['tenant_id']
    ctx = p.identity.context_for(t, f'anon-{persona}')
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    ws = p.engineering_conversations.workspace
    kinds = [k for k in KINDS if k != 'engineering_chat_turn']
    records = [(k, r.id, r.revision) for k in kinds for r in p.store.read().list(t, k)]
    texts = [s['prompt'] + ' ' + s['situation'] for s in SCENARIOS if s['persona'] == persona]
    ids = {m for text in texts for m in ID_PATTERN.findall(text)} | {i for _, i, _ in records}
    for k, i, rev in records:
        ws.read(ctx, thread, kind=k, record_id=i, revision=1)  # guessed revision
        ws.links(ctx, thread, kind=k, record_id=i)
    for i in sorted(ids):
        for k in kinds:
            try:
                ws.read(ctx, thread, kind=k, record_id=i, revision=1)
            except NotFoundError:
                pass  # the conversation turns this into a "not found" result
            ws.links(ctx, thread, kind=k, record_id=i)
        ws.similar_cases(ctx, thread, case_id=i)
    for text in texts:
        ws.search(ctx, thread, kinds=[], query=text[:200])
        ws.similar_cases(ctx, thread, text=text[:200])


def test_the_model_sees_the_whole_delivery_summary_with_every_value(p):
    """Live 2026-11-07: the summary exceeded the per-result cap, so the model saw it truncated and paged raw JSON
    ten times (358 s). The summary carries every value as a series and fits."""
    from src.lifesci.process_engineering.tool_loop import _for_model
    t = p.demo.provision('anon-cap', 'msat', True)['tenant_id']
    ctx = p.identity.context_for(t, 'anon-cap')
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    rec = p.store.read().require(t, 'evidence', 'cmo-verified-delivery:demo-september')
    shown = _for_model(p.engineering_conversations.workspace.read(ctx, thread, kind='evidence', record_id=rec.id, revision=rec.revision))
    assert 'truncated' not in shown[-300:]
    series = json.loads(shown)['record']['data']['dataset_summary']['series']
    assert sum(len(v) for runs in series.values() for v in runs.values()) == 306


def test_the_improvement_corpus_keeps_what_the_harness_needs(p, monkeypatch):
    """Per demo turn: what the model saw (to replay it), harness version, scenario, steps, and the visitor's notes."""
    from src.lifesci.demo_scenarios import SCENARIOS
    from tests.lifesci.test_engineering_conversation import fake_planner
    monkeypatch.delenv('ASSISTANT_LOOP', raising=False)  # demo workspaces use the tool loop by default
    t = p.demo.provision('anon-corpus', 'qa', True)['tenant_id']
    ctx = p.identity.context_for(t, 'anon-corpus')
    prompt = next(s for s in SCENARIOS if s['scenario_id'] == 'qa-triage')['prompt']
    fake = fake_planner(p, [])
    dev31 = p.store.read().require(t, 'case', 'DEV-31').revision
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = [
        {'tool_calls': [{'name': 'workspace_read', 'arguments': {'kind': 'case', 'record_id': 'DEV-31', 'revision': dev31}}]},
        {'tool_calls': [{'name': 'remember', 'arguments': {'text': 'DEV-31 is open; triage continues in the case.', 'kind': 'open_thread',
                                                           'basis': 'observed', 'sources': [{'kind': 'case', 'id': 'DEV-31'}]}}]},
        'DEV-31 already exists; no new case is needed.']
    thread = p.engineering_conversations.create(ctx, {'site_id': 'NF1'})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': prompt, 'expected_revision': thread['revision']})
    turn = p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])['turns'][-1]
    assert turn['status'] == 'completed' and '_transcript' not in turn  # never sent to the browser
    p.demo.snapshot_workspace(t)
    item = p.store.read().require(CORPUS, 'demo_transcript', f"{t}:{thread['id']}").state
    saved = item['turns'][0]
    assert saved['harness'] == 'tool-loop-v1' and saved['scenario_id'] == 'qa-triage'
    assert [s['task_kind'] for s in saved['steps']] == ['workspace_read', 'remember']
    roles = [m['role'] for m in saved['model_transcript']]
    assert roles[0] == 'user' and 'tool' in roles and roles[-1] == 'assistant'
    assert item['memory_notes'][0]['kind'] == 'open_thread'
