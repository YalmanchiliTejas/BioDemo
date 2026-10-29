"""CMO delivery verification runs inside the platform API, and verified deliveries become assistant evidence."""
import csv
import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.store import RecordStore
from tests.lifesci.test_engineering_conversation import fake_planner, send

HEADERS = {'X-Tenant-Id': TENANT, 'X-Actor-Id': 'priya'}


@pytest.fixture
def platform_client(tmp_path, monkeypatch):
    for name in ['OPENAI_API_KEY', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_AUTH_TOKEN', 'SUPABASE_URL', 'CMO_DATABASE_URL', 'CMO_API_TOKEN']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CMO_PACKAGES_ROOT', str(tmp_path / 'none'))
    monkeypatch.setenv('CMO_DEMO_ROOT', str(tmp_path / 'none'))
    monkeypatch.setenv('CMO_HOSTED_INFERENCE_APPROVED', 'true')
    p = Platform(RecordStore(), providers={})
    seed(p)
    return p, TestClient(create_app(p))


def _wait(client, ident):
    for _ in range(300):
        run = client.get('/api/cmo-ingestion/runs/' + ident).json()
        if run['status'] not in {'queued', 'running'}:
            return run
        time.sleep(.02)
    raise AssertionError('run did not finish')


def _verified_run(client):
    delivery = client.post('/api/cmo-ingestion/deliveries', json={'cmo': 'Acme CDMO', 'name': 'October lots'}).json()
    body = io.StringIO()
    csv.writer(body).writerows([['Lot', 'Elapsed time (h)', 'pH', 'Temperature (°C)'], ['L-1', 0, 7.0, 37], ['L-1', 1, 7.1, 37.1]])
    client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files", params={'filename': 'lot export.csv'},
                content=body.getvalue().encode())
    first = _wait(client, client.post('/api/cmo-ingestion/runs', json={'package_id': delivery['id']}).json()['id'])
    assert first['status'] == 'complete' and not first['summary']['verified_package']
    layout = first['layouts'][0]
    client.post(f"/api/cmo-ingestion/runs/{first['id']}/templates",
                json={'fingerprint': layout['fingerprint'], 'mapping': layout['mapping'], 'actor': 'Parker'})
    newer = _wait(client, client.post(f"/api/cmo-ingestion/runs/{first['id']}/reprocess", json={'actor': 'Parker'}).json()['id'])
    assert newer['summary']['verified_package']
    return first, newer


def test_delivery_verification_is_served_by_the_platform_api(platform_client):
    _, client = platform_client
    assert client.get('/api/cmo-ingestion/catalog').status_code == 200
    first, newer = _verified_run(client)
    assert client.get(f"/api/cmo-ingestion/runs/{newer['id']}/verified").json()['guarantee']['holds']


def test_only_current_verified_deliveries_publish_as_evidence(platform_client):
    p, client = platform_client
    first, newer = _verified_run(client)
    # The first check still had decisions open and was superseded: it must not reach the assistant.
    assert client.post('/v1/cmo-datasets', json={'run_id': first['id']}, headers=HEADERS).status_code == 409
    published = client.post('/v1/cmo-datasets', json={'run_id': newer['id']}, headers=HEADERS)
    assert published.status_code == 201, published.text
    dataset = published.json()
    assert dataset['id'] == f"cmo-verified-delivery:{newer['id']}" and dataset['measurements'] == 4
    assert len(dataset['parameters']) == 2
    again = client.post('/v1/cmo-datasets', json={'run_id': newer['id']}, headers=HEADERS).json()
    assert again['revision'] == dataset['revision']  # unchanged delivery republishes idempotently
    listed = client.get('/v1/cmo-datasets', headers=HEADERS).json()['datasets']
    assert [d['id'] for d in listed] == [dataset['id']]
    detail = client.get(f"/v1/cmo-datasets/{dataset['id']}", headers=HEADERS).json()
    assert detail['summary']['guarantee_holds'] and detail['summary']['measurement_count'] == 4
    stored = json.loads(p.evidence.original(p.identity.context_for(TENANT, 'priya'), dataset['id']))
    assert {m['source']['path'] for m in stored['measurements']} == {'lot export.csv'}
    assert client.post('/v1/cmo-datasets', json={'run_id': newer['id']}).status_code in (401, 403)


def test_assistant_receives_verified_dataset_as_cited_evidence(platform_client, monkeypatch):
    p, client = platform_client
    _, newer = _verified_run(client)
    dataset = client.post('/v1/cmo-datasets', json={'run_id': newer['id']}, headers=HEADERS).json()
    ctx = p.identity.context_for(TENANT, 'priya')
    seen = []
    original = p.gateway.run

    def capture(req):
        seen.append(req)
        return original(req)
    monkeypatch.setattr(p.gateway, 'run', capture)
    fake_planner(p, [{'reply': 'Lot L-1 pH rose from 7.0 to 7.1 between 0 and 1 h (lot export.csv).'}])
    thread = p.engineering_conversations.create(ctx, {})
    result = send(p, ctx, thread, 'How did pH change in lot L-1?', dataset_ids=[dataset['id']])
    assert result['dataset_ids'] == [dataset['id']] and result['turns'][0]['status'] == 'completed'
    prompt = json.loads(seen[0].prompt)
    source = prompt['authorized_sources'][0]
    assert source['kind'] == 'verified_cmo_dataset' and source['status'] == 'verified'
    assert source['measurement_count'] == 4 and source['batches'] == ['L-1']
    assert all(row['source'].startswith('lot export.csv') for row in source['example_rows'])
    assert any('verified_cmo_dataset' in line for line in prompt['instructions'])
    assert {'kind': 'evidence', 'id': dataset['id']}.items() <= next(
        r for r in seen[0].inputs if r['id'] == dataset['id']).items()


def test_unknown_or_cross_site_dataset_cannot_be_attached(platform_client):
    p, client = platform_client
    ctx = p.identity.context_for(TENANT, 'priya')
    thread = p.engineering_conversations.create(ctx, {})
    with pytest.raises(ValueError):
        p.engineering_conversations.enqueue(ctx, thread['id'], {'text': 'Use this', 'expected_revision': thread['revision'],
                                                                 'dataset_ids': ['cmo-verified-delivery:missing']})
