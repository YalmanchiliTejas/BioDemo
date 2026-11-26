"""The assistant's own memory: notes with provenance, hybrid recall, privacy, entity pages and consolidation.
Contract tests with a scripted model and a toy embedder; they establish host behavior, not retrieval quality."""
import json
import math

import pytest
from fastapi.testclient import TestClient

from src.lifesci.agent_memory import NOTE
from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.embeddings import HashingEmbedder
from src.lifesci.store import RecordStore
from tests.lifesci.test_engineering_conversation import fake_planner, send


class ConceptEmbedder:
    """Toy semantic space: words with the same meaning share a dimension, so paraphrases match without shared words."""
    model = 'concepts-test'
    CONCEPTS = [('oxygen', 'do', 'dissolved', 'aeration'), ('foam', 'foaming', 'antifoam'), ('forecast', 'predict', 'projection'),
                ('glucose', 'sugar'), ('probe', 'sensor', 'electrode'), ('invoice', 'billing')]

    def embed(self, texts, *, query=False):
        out = []
        for t in texts:
            words = t.casefold().replace('-', ' ').split()
            v = [sum(any(w.strip('.,?%') == c for w in words) for c in group) for group in self.CONCEPTS] + [0.01]
            n = math.sqrt(sum(x * x for x in v))
            out.append([x / n for x in v])
        return out


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('ASSISTANT_LOOP', 'tools')
    p = Platform(RecordStore(), providers={})
    seed(p)
    p.agent_memory.embedder = ConceptEmbedder()
    ctx = p.identity.context_for(TENANT, 'priya')
    p.cases.open(ctx, 'DEV-77', 'priya', 'quinn', 'NF1')
    p.cases.add_timeline_event(ctx, 'DEV-77', '2026-11-01T10:00:00Z', 'Foaming at 4 h in B-200; DO fell to 25 %.')
    return p, ctx


def model(p, script):
    fake = fake_planner(p, [])
    fake.scripts[p.gateway.registry.profiles['anthropic-opus'].model] = list(script)
    return fake


def call(name, **arguments):
    return {'name': name, 'arguments': arguments}


def ask(p, ctx, script, text, thread_id=None):
    fake = model(p, script)
    thread = p.engineering_conversations.get(ctx, thread_id) if thread_id else p.engineering_conversations.create(ctx, {})
    return send(p, ctx, thread, text), fake


def read_case(p):
    return call('workspace_read', kind='case', record_id='DEV-77', revision=p.store.read().require(TENANT, 'case', 'DEV-77').revision)


def note_with_source(p, ctx, text='Foaming on DEV-77 coincided with the DO drop; check antifoam first next time.'):
    convo, _ = ask(p, ctx, [{'tool_calls': [read_case(p)]},
                            {'tool_calls': [call('remember', text=text, kind='lesson', basis='observed',
                                                 sources=[{'kind': 'case', 'id': 'DEV-77'}])]}, 'Noted.'], 'What happened in DEV-77?')
    return convo


def test_a_note_must_rest_on_records_this_conversation_read(env):
    p, ctx = env
    convo = note_with_source(p, ctx)
    steps = convo['turns'][-1]['steps']
    assert steps[-1]['title'].startswith('Remember') and steps[-1]['status'] == 'completed'
    [note] = p.agent_memory.notes(ctx)
    assert note['status'] == 'active' and note['sources'][0]['id'] == 'DEV-77' and 'DEV77' in note['entities']
    # A record it never read cannot be cited; an unsupported claim needs to be the person's own statement.
    turn, _ = ask(p, ctx, [{'tool_calls': [call('remember', text='Pump AF-2 is unreliable on every batch.', kind='lesson',
                                                basis='observed', sources=[{'kind': 'case', 'id': 'DEV-77'}])]}, 'ok'], 'Remember that')
    assert turn['turns'][-1]['steps'][0]['status'] == 'blocked' and 'not read' in turn['turns'][-1]['steps'][0]['issues'][0]
    turn, _ = ask(p, ctx, [{'tool_calls': [call('remember', text='Prefers glucose in g/L, never mmol/L.', kind='preference',
                                                basis='user_stated')]}, 'ok'], 'Always show glucose in g/L please')
    assert turn['turns'][-1]['steps'][0]['status'] == 'completed'
    assert {n['basis'] for n in p.agent_memory.notes(ctx)} == {'observed', 'user_stated'}


def test_a_note_goes_stale_when_its_source_record_changes(env):
    p, ctx = env
    note_with_source(p, ctx)
    p.cases.add_timeline_event(ctx, 'DEV-77', '2026-11-02T10:00:00Z', 'Probe replaced.')
    [note] = p.agent_memory.notes(ctx)
    assert note['status'] == 'stale' and 'changed' in note['stale_because'][0]
    p.agent_memory.dream(TENANT, 'priya', use_model=False)
    assert p.store.read().require(TENANT, NOTE, note['id']).state['status'] == 'stale'  # persisted by consolidation


def test_the_same_lesson_twice_is_one_note(env):
    p, ctx = env
    note_with_source(p, ctx)
    note_with_source(p, ctx)
    [note] = p.agent_memory.notes(ctx)
    assert note['history'][-1]['event'] == 'reaffirmed'


def test_recall_finds_a_paraphrase_by_meaning_and_ranks_identifiers(env):
    p, ctx = env
    note_with_source(p, ctx)
    ask(p, ctx, ['Invoices are handled by finance.'], 'Who handles billing?')
    thread = p.engineering_conversations.create(ctx, {})
    found = p.agent_memory.recall(ctx, thread, 'why did aeration suffer?')  # no word in common with the note
    assert found['semantic_search'] == 'used' and found['results'][0]['type'] == 'note'
    lexical_only = p.agent_memory.recall(ctx, thread, 'DEV-77')
    assert any(r['type'] == 'note' for r in lexical_only['results'])


def test_recall_without_the_embedding_service_still_works_by_words(env):
    p, ctx = env
    note_with_source(p, ctx)
    p.agent_memory.embedder = None
    found = p.agent_memory.recall(ctx, p.engineering_conversations.create(ctx, {}), 'antifoam DEV-77')
    assert found['semantic_search'] == 'unavailable' and found['results']


def test_another_persons_notes_are_invisible_without_their_grant(env):
    p, ctx = env
    note_with_source(p, ctx)
    p.identity.assign_role(TENANT, 'sam', 'engineering', site_id='NF1')
    sam = p.identity.context_for(TENANT, 'sam')
    sam_thread = p.engineering_conversations.create(sam, {})
    assert not [r for r in p.agent_memory.recall(sam, sam_thread, 'oxygen foaming antifoam')['results'] if r['type'] == 'note']
    note_id = p.agent_memory.notes(ctx)[0]['id']
    with pytest.raises(PermissionError):
        p.agent_memory.open(sam, note_id)
    grant = p.memory.request(sam, owner_id='priya', scopes=['conversations'], reason='Covering DEV-77', days=7)
    p.memory.approve(ctx, grant['grant_id'])
    shared = [r for r in p.agent_memory.recall(sam, sam_thread, 'oxygen foaming antifoam')['results'] if r['type'] == 'note']
    assert shared and shared[0]['shared_from'] == 'priya'
    with pytest.raises(PermissionError):  # read-only: sam can't change priya's memory
        p.agent_memory.set_status(sam, note_id, 'wrong')


def test_consolidation_builds_entity_pages_an_index_and_keeps_only_supported_notes(env):
    p, ctx = env
    convo = note_with_source(p, ctx)
    turn_id = convo['turns'][-1]['id']
    model(p, [json.dumps({'new_notes': [
        {'turn_id': turn_id, 'text': 'DEV-77: the probe was never bump-tested; verify the sensor before trusting the trend.', 'kind': 'warning',
         'basis': 'inferred', 'sources': ['case:DEV-77']},
        {'turn_id': turn_id, 'text': 'Batch B-999 had the same problem.', 'kind': 'lesson', 'basis': 'observed',
         'sources': ['batch:B-999']}],  # never read: dropped
        'corrections': [{'note_id': 'not-mine', 'action': 'stale', 'reason': 'x'}]})])
    report = p.agent_memory.dream(TENANT, 'priya')
    assert report['new_notes'] == 1 and report['corrections'] == 0
    notes = p.agent_memory.notes(ctx)
    assert any(n['origin'] == 'dreaming' and n['kind'] == 'warning' for n in notes)
    assert not any('B-999' in n['text'] for n in notes)
    page = next(pg for pg in p.agent_memory.pages(ctx) if pg['entity'] == 'DEV77')
    assert len(page['note_ids']) == 2 and 'verify the sensor' in page['summary']
    assert len(p.agent_memory.index(ctx, 'priya')) == 2
    assert p.agent_memory.due(TENANT) == []  # nothing new since: no model call on the next tick


def test_memory_api_lists_and_lets_only_the_owner_forget(env, monkeypatch):
    p, ctx = env
    note_with_source(p, ctx)
    monkeypatch.setenv('LIFESCI_AUTH_MODE', 'development')
    api = TestClient(create_app(p))
    me = {'X-Tenant-Id': TENANT, 'X-Actor-Id': 'priya'}
    body = api.get('/v1/assistant-memory', headers=me).json()
    note_id = body['notes'][0]['id']
    assert body['index'][0]['id'] == note_id and body['semantic_search'] is True
    other = {'X-Tenant-Id': TENANT, 'X-Actor-Id': 'quinn'}
    assert api.get('/v1/memory/priya/notes', headers=other).status_code == 403
    assert api.post(f'/v1/assistant-memory/notes/{note_id}/status', json={'status': 'forgotten'}, headers=other).status_code == 403
    assert api.post(f'/v1/assistant-memory/notes/{note_id}/status', json={'status': 'forgotten'}, headers=me).json()['status'] == 'forgotten'
    assert api.get('/v1/assistant-memory', headers=me).json()['index'] == []


def test_entities_are_real_identifiers_not_joined_or_evidence_ids():
    from src.lifesci.agent_memory import entities
    text = 'DEV-31 (open, B-117/BR-07): lot L-8812, run CHO-003-R01, pump AF-2, on 2026-11-03'
    assert entities(text) == ['AF2', 'B117', 'BR07', 'CHO003R01', 'DEV31', 'L8812']
    assert entities('HISTORIAN:BR-07-AF-DOSING-B-117') == ['B117', 'BR07']
