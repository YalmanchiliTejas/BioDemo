"""Link review API: list a run's cross-file links, confirm or reject them with a recorded reason."""
from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def client_and_run(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    for name in ['OPENAI_API_KEY', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_AUTH_TOKEN', 'SUPABASE_URL', 'CMO_DATABASE_URL']:
        monkeypatch.delenv(name, raising=False)
    packages = tmp_path/'packages'; folder = packages/'test'/'raw'; folder.mkdir(parents=True)
    (folder/'bioreactor.csv').write_text('batch_id,equipment_id,elapsed_h,temperature [degC]\nB-001,BR-03,0,35\nB-001,BR-03,1,36\n')
    (folder/'deviations.csv').write_text('deviation_id,batch_id,description\nDEV-9,B001,foaming\n')
    (packages/'catalog.json').write_text(json.dumps([{'id': 'test', 'dataset': 'x', 'condition': 'unseen', 'cmo': 'api',
        'synthetic': False, 'disclosure': 'Test fixture only', 'files': [{'path': 'bioreactor.csv'}, {'path': 'deviations.csv'}]}]))
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(tmp_path/'runtime')); monkeypatch.setenv('CMO_PACKAGES_ROOT', str(packages))
    monkeypatch.setenv('CMO_API_TOKEN', 't')
    app = FastAPI(); app.include_router(router(tmp_path)); client = TestClient(app); client.headers['X-CMO-Token'] = 't'
    ident = client.post('/api/cmo-ingestion/runs', json={'package_id': 'test', 'configuration': 'preview'}).json()['id']
    for _ in range(200):
        run = client.get('/api/cmo-ingestion/runs/'+ident).json()
        if run['status'] not in {'queued', 'running'}: break
        time.sleep(.02)
    assert run['status'] not in {'failed', 'queued', 'running'}, run.get('error')
    return client, ident


def test_lists_links_with_counts_and_alias(client_and_run):
    client, ident = client_and_run
    body = client.get(f'/api/cmo-ingestion/runs/{ident}/links').json()
    pairs = {frozenset((l['a'], l['b'])): l for l in body['links']}
    assert frozenset(('B-001', 'BR-03')) in pairs
    assert pairs[frozenset(('B001', 'B-001'))]['predicate'] == 'same_identifier'
    assert body['sources_searched'] == 2 and sum(body['counts'].values()) == len(body['links'])
    graph = client.get(f'/api/cmo-ingestion/runs/{ident}/links', params={'entity_id': 'DEV-9', 'hops': 2}).json()
    assert 'BR-03' in graph['entities']


def test_reject_requires_reason_and_removes_link_from_traversal(client_and_run):
    client, ident = client_and_run
    alias = next(l for l in client.get(f'/api/cmo-ingestion/runs/{ident}/links').json()['links']
                 if l['predicate'] == 'same_identifier')
    url = f'/api/cmo-ingestion/runs/{ident}/links/reviews'
    assert client.post(url, json={'link_id': alias['link_id'], 'decision': 'rejected', 'actor': 'qa'}).status_code == 400
    ok = client.post(url, json={'link_id': alias['link_id'], 'decision': 'rejected', 'actor': 'qa', 'reason': 'site 2 numbering'})
    assert ok.status_code == 200 and ok.json()['decision'] == 'rejected'
    graph = client.get(f'/api/cmo-ingestion/runs/{ident}/links', params={'entity_id': 'DEV-9', 'hops': 2}).json()
    assert 'BR-03' not in graph['entities']


def test_confirm_has_default_reason_and_unknown_link_is_404(client_and_run):
    client, ident = client_and_run
    link = client.get(f'/api/cmo-ingestion/runs/{ident}/links').json()['links'][0]
    url = f'/api/cmo-ingestion/runs/{ident}/links/reviews'
    done = client.post(url, json={'link_id': link['link_id'], 'decision': 'confirmed', 'actor': 'qa'}).json()
    assert done['reason'] == 'Checked the cited source row'
    assert client.post(url, json={'link_id': '0'*24, 'decision': 'confirmed', 'actor': 'qa'}).status_code == 404
    assert client.post(url, json={'link_id': 'bad', 'decision': 'confirmed', 'actor': 'qa'}).status_code == 422


def start_run(client):
    ident = client.post('/api/cmo-ingestion/runs', json={'package_id': 'test', 'configuration': 'preview'}).json()['id']
    for _ in range(200):
        if client.get('/api/cmo-ingestion/runs/'+ident).json()['status'] not in {'queued', 'running'}: break
        time.sleep(.02)
    return ident


def test_review_carries_to_a_later_run_of_the_same_cmo(client_and_run):
    client, first = client_and_run
    alias = next(l for l in client.get(f'/api/cmo-ingestion/runs/{first}/links').json()['links']
                 if l['predicate'] == 'same_identifier')
    client.post(f'/api/cmo-ingestion/runs/{first}/links/reviews',
                json={'link_id': alias['link_id'], 'decision': 'rejected', 'actor': 'qa', 'reason': 'site 2 numbering'})
    second = start_run(client)
    assert second != first
    later = {l['link_id']: l for l in client.get(f'/api/cmo-ingestion/runs/{second}/links').json()['links']}
    assert later[alias['link_id']]['status'] == 'rejected'
    assert later[alias['link_id']]['review']['reason'] == 'site 2 numbering'


def test_links_rebuild_when_this_server_lacks_the_parsed_store(client_and_run, tmp_path):
    import shutil
    client, ident = client_and_run
    before = client.get(f'/api/cmo-ingestion/runs/{ident}/links').json()
    shutil.rmtree(tmp_path/'runtime'/'stores'/ident)  # as on a different Lambda instance
    after = client.get(f'/api/cmo-ingestion/runs/{ident}/links').json()
    assert after['rebuilt_from_originals'] is True
    assert {l['link_id'] for l in after['links']} == {l['link_id'] for l in before['links']}
    assert client.get(f'/api/cmo-ingestion/runs/{ident}/links').json()['rebuilt_from_originals'] is False
