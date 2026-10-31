"""AWS Lambda hosting: tasks leave the request, run state lives in the database, uploads bypass the 6 MB limit."""
import csv
import io
import json
import sys
import time
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.lifesci import aws_lambda
from src.lifesci.tasks import TASK_KEY, TaskRunner

HEADERS = {'X-Tenant-Id': 'lambda-tenant', 'X-Actor-Id': 'qa'}


@pytest.fixture
def invocations(monkeypatch):
    """A stand-in for boto3: records asynchronous invocations instead of calling AWS."""
    sent = []

    class Client:
        def invoke(self, **kwargs):
            sent.append(kwargs)
            return {'StatusCode': 202}

    monkeypatch.setitem(sys.modules, 'boto3', types.SimpleNamespace(client=lambda name: Client()))
    monkeypatch.setenv('AWS_LAMBDA_FUNCTION_NAME', 'biodemo-api')
    return sent


def test_configuration_that_would_lose_data_is_refused():
    with pytest.raises(aws_lambda.ConfigurationError) as error:
        aws_lambda.check_configuration({'LIFESCI_DATABASE_URL': 'sqlite:///x.db', 'LIFESCI_DB_MIGRATE': '1'})
    message = str(error.value)
    assert 'PostgreSQL' in message and 'LIFESCI_DB_MIGRATE' in message and 'Supabase Storage' in message
    aws_lambda.check_configuration({'LIFESCI_DATABASE_URL': 'postgresql://lifesci_app@db/postgres', 'LIFESCI_DB_MIGRATE': '0',
                                    'SUPABASE_URL': 'https://x.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': 'k',
                                    'DEPLOYMENT_TENANT': 't'})


def test_tasks_run_in_a_thread_off_lambda(monkeypatch):
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)
    tasks, seen = TaskRunner(), []
    tasks.register('echo', seen.append)
    tasks.submit('echo', {'n': 1})
    for _ in range(100):
        if seen: break
        time.sleep(.01)
    assert seen == [{'n': 1}]
    with pytest.raises(KeyError):
        tasks.submit('unknown', {})


def test_tasks_become_asynchronous_invocations_on_lambda(invocations):
    tasks, seen = TaskRunner(), []
    tasks.register('echo', seen.append)
    tasks.submit('echo', {'n': 2})
    [call] = invocations
    assert call['FunctionName'] == 'biodemo-api' and call['InvocationType'] == 'Event'
    event = json.loads(call['Payload'])
    assert tasks.is_task(event) and seen == []
    tasks.run(event)
    assert seen == [{'n': 2}]
    with pytest.raises(TypeError):  # payloads must survive the trip as JSON
        tasks.submit('echo', {'when': object()})


def test_handler_serves_http_and_scheduled_ticks(monkeypatch):
    from mangum import Mangum

    from src.lifesci.api import create_app
    from src.lifesci.container import Platform
    from src.lifesci.devseed import TENANT, seed
    from src.lifesci.store import RecordStore

    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)
    platform = Platform(RecordStore(), providers={})
    seed(platform)
    app = create_app(platform)
    monkeypatch.setattr(aws_lambda, '_state', {'app': app, 'platform': platform, 'http': Mangum(app, lifespan='off')})
    event = {'version': '2.0', 'routeKey': '$default', 'rawPath': '/v1/me', 'rawQueryString': '',
             'headers': {'x-tenant-id': TENANT, 'x-actor-id': 'priya', 'host': 'example.lambda-url.us-east-1.on.aws'},
             'requestContext': {'http': {'method': 'GET', 'path': '/v1/me', 'protocol': 'HTTP/1.1', 'sourceIp': '1.2.3.4',
                                         'userAgent': 'test'}, 'domainName': 'example.lambda-url.us-east-1.on.aws',
                                'stage': '$default', 'requestId': 'r', 'accountId': '1', 'apiId': 'a', 'time': 'now',
                                'timeEpoch': 0},
             'isBase64Encoded': False}
    response = aws_lambda.handler(event, None)
    assert response['statusCode'] == 200 and json.loads(response['body'])['actor_id'] == 'priya'
    tick = aws_lambda.handler({TASK_KEY: {'kind': 'runtime_tick', 'payload': {}}}, None)
    assert tick['task'] == 'runtime_tick' and tick['result']['tenants'] >= 0


def _cmo_app(root, monkeypatch, tasks):
    from src.manufacturing_data.cmo.api import router

    for name in ['OPENAI_API_KEY', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_AUTH_TOKEN', 'SUPABASE_URL', 'CMO_DATABASE_URL',
                 'CMO_API_TOKEN', 'LIFESCI_DATABASE_URL']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(root))
    monkeypatch.setenv('CMO_PACKAGES_ROOT', str(root / 'none'))
    monkeypatch.setenv('CMO_DEMO_ROOT', str(root / 'none'))
    app = FastAPI()
    app.include_router(router(root, tasks=tasks))
    return TestClient(app, headers=HEADERS)


def _delivery(client):
    delivery = client.post('/api/cmo-ingestion/deliveries', json={'cmo': 'Acme', 'name': 'Lots'}).json()
    body = io.StringIO()
    csv.writer(body).writerows([['batch_id', 'elapsed_h', 'pH [pH]'], ['B', 0, 7], ['B', 1, 7.1]])
    client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files", params={'filename': 'lot.csv'},
                content=body.getvalue().encode())
    return delivery


def test_cmo_run_progress_is_shared_between_instances(tmp_path, monkeypatch, invocations):
    api_tasks, worker_tasks = TaskRunner(), TaskRunner()
    api = _cmo_app(tmp_path / 'shared', monkeypatch, api_tasks)          # instance that answered the request
    worker = _cmo_app(tmp_path / 'shared', monkeypatch, worker_tasks)    # instance that receives the task
    delivery = _delivery(api)
    started = api.post('/api/cmo-ingestion/runs', json={'package_id': delivery['id']}).json()
    assert started['status'] == 'queued'
    assert api.get(f"/api/cmo-ingestion/runs/{started['id']}").json()['status'] == 'queued'
    event = json.loads(invocations[0]['Payload'])
    assert worker_tasks.run(event) == 'complete'
    assert worker_tasks.run(event) is None  # Lambda may deliver twice; only the first claim runs
    finished = api.get(f"/api/cmo-ingestion/runs/{started['id']}").json()
    assert finished['status'] == 'complete' and finished['summary']['measurements'] == 2


def test_run_that_outlives_its_worker_is_reported_interrupted(tmp_path, monkeypatch, invocations):
    monkeypatch.setenv('CMO_RUN_TIMEOUT_SECONDS', '0.5')
    client = _cmo_app(tmp_path / 'r', monkeypatch, TaskRunner())
    started = client.post('/api/cmo-ingestion/runs', json={'package_id': _delivery(client)['id']}).json()
    time.sleep(.7)
    run = client.get(f"/api/cmo-ingestion/runs/{started['id']}").json()
    assert run['status'] == 'interrupted' and 'time limit' in run['error']


class FakeStorage:
    backend = 'supabase'

    def __init__(self):
        self.objects = {}

    def put(self, key, path):
        self.objects.setdefault(key, open(path, 'rb').read())

    def get(self, key, destination):
        if key not in self.objects: raise FileNotFoundError(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.objects[key])
        return destination

    def signed_upload(self, key):
        return {'url': f'https://storage.example/upload/{key}?token=t', 'method': 'PUT', 'headers': {'x-upsert': 'false'}}

    def delete(self, key):
        assert key.startswith('uploads/')
        self.objects.pop(key, None)


def test_large_files_upload_through_storage(tmp_path, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr('src.manufacturing_data.cmo.pipeline.evidence_store', lambda: storage)
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)
    client = _cmo_app(tmp_path / 'u', monkeypatch, TaskRunner())
    assert client.get('/api/cmo-ingestion/catalog').json()['upload'] == {'mode': 'storage', 'max_bytes': 64 * 1024 * 1024}
    delivery = client.post('/api/cmo-ingestion/deliveries', json={'cmo': 'Acme', 'name': 'Big'}).json()
    assert client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/uploads",
                       json={'filename': 'run.exe', 'size': 3}).status_code == 400
    assert client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/uploads",
                       json={'filename': 'lot.csv', 'size': 65 * 1024 * 1024}).status_code == 413
    begun = client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/uploads", json={'filename': 'lot.csv', 'size': 30}).json()
    assert begun['method'] == 'PUT' and begun['url'].startswith('https://storage.example/upload/uploads/lambda-tenant/')
    pending = begun['url'].split('/upload/', 1)[1].split('?', 1)[0]
    storage.objects[pending] = b'batch_id,elapsed_h,pH [pH]\nB,0,7\n'  # what the browser PUT
    item = client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/uploads/{begun['upload_id']}/complete").json()
    assert [f['path'] for f in item['files']] == ['lot.csv'] and pending not in storage.objects
    assert f"deliveries/{delivery['id']}/lot.csv" in storage.objects
    forged = begun['upload_id'].split('-')[0] + '-Li4vZXRjL3Bhc3N3ZA'  # "../etc/passwd"
    assert client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/uploads/{forged}/complete").status_code in (400, 404, 410)


def test_lambda_always_releases_sessions_even_on_failure(monkeypatch):
    from types import SimpleNamespace
    released = []
    def failing_http(*args):
        raise RuntimeError('request failed')
    store = SimpleNamespace(release_connections=lambda: released.append(True))
    state = {'platform': SimpleNamespace(store=store),
             'app': SimpleNamespace(state=SimpleNamespace(tasks=SimpleNamespace(is_task=lambda e: False))),
             'http': failing_http}
    monkeypatch.setattr(aws_lambda, '_boot', lambda: state)
    with pytest.raises(RuntimeError, match='request failed'):
        aws_lambda.handler({}, None)
    assert released == [True]


def test_postgres_sessions_are_lazy_and_released_before_freezing(monkeypatch):
    import psycopg
    from types import SimpleNamespace
    from src.lifesci.store import RecordStore
    sessions = []
    def connect(*args, **kwargs):
        assert not any(not c.closed for c in sessions), 'An idle session leaked across invocations'
        conn = SimpleNamespace(closed=False)
        conn.close = lambda: setattr(conn, 'closed', True)
        sessions.append(conn)
        return conn
    monkeypatch.setattr(psycopg, 'connect', connect)
    store = RecordStore('postgresql://lifesci_app@db/postgres', migrate=False)
    assert not sessions  # boot does not reserve a scarce pool slot
    for _ in range(20):
        assert store._db.conn is store._db.conn
        store.release_connections()
    assert len(sessions) == 20 and all(c.closed for c in sessions)
