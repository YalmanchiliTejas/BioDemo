"""Live investigation progress: allow-list, harness streaming, dispatcher ingestion and the events API."""
from __future__ import annotations

import json
import os
import sys
import time
from types import SimpleNamespace

import pytest

from src.prime_runtime.harness import _stream
from src.prime_runtime.investigation_events import EventEmitter, clean, parse_line, session_key


def event(kind, payload, seq=0, **extra):
    return {'type': 'investigation_event', 'local_seq': seq, 'at': '2026-11-05T10:00:00+00:00', 'kind': kind,
            'agent_id': 'lead', 'parent_id': None, 'payload': payload, **extra}


# --- allow-list --------------------------------------------------------------------------------

def test_allow_list_drops_unknown_kinds_keys_and_text_fields():
    assert clean(event('message', {'text': 'confidential'})) is None
    assert clean({**event('phase', {'phase': 'planning'}), 'type': 'child_activity'}) is None
    assert clean(event('phase', {'phase': 'exfiltrate'})) is None
    kept = clean(event('agent_activity', {'status': 'running', 'tool': 'query_data', 'answer_preview': 'secret',
                                          'recap': 'secret', 'error': 'provider said', 'token_count': 12}))
    assert kept['payload'] == {'status': 'running', 'tool': 'query_data', 'token_count': 12}
    assert clean({**event('phase', {'phase': 'planning'}), 'at': '2026-11-05T10:00:00'}) is None  # naive time
    assert clean({**event('phase', {'phase': 'planning'}), 'local_seq': -1}) is None


def test_allow_list_truncates_and_bounds_lists():
    kept = clean(event('allocation', {'task_ids': [f't{i}' for i in range(40)], 'owner': 'o' * 500,
                                      'reason': 'r' * 900, 'calls': 3}))
    assert len(kept['payload']['task_ids']) == 16 and len(kept['payload']['owner']) == 80
    assert len(kept['payload']['reason']) == 300
    saved = clean(event('subreport_saved', {'assessment': 'a' * 2000, 'evidence_ids': [str(i) for i in range(90)]}))
    assert len(saved['payload']['assessment']) == 500 and len(saved['payload']['evidence_ids']) == 50


def test_parse_line_rejects_oversized_and_non_json_lines():
    assert parse_line(b'not json') is None
    assert parse_line(b'{"event":"agent_failed"}') is None
    big = json.dumps(event('error', {'code': 'x'}) | {'padding': 'p' * 9000})
    assert parse_line(big.encode()) is None
    assert parse_line(json.dumps(event('error', {'code': 'agent_failed'})).encode())['kind'] == 'error'


def test_emitter_maps_children_phases_and_bridge_attribution():
    out = []
    emitter = EventEmitter(out.append)
    emitter.set_phase('planning')
    key = session_key('/tmp/sessions/child-a')
    emitter.sdk({'type': 'child_activity', 'child_id': 'c1', 'parent_id': 'root-node', 'status': 'running',
                 'label': 'Check antifoam lot L-8812', 'tool': 'query_data', 'token_count': 900, 'session_key': key})
    emitter.bridge('subreport_saved', {'subreport_id': 's1', 'assessment': 'lot in spec'}, depth=1, key=key)
    emitter.bridge('budget', {'tool_calls_used': 4}, depth=1, key='unknown-session')
    emitter.sdk({'type': 'child_activity', 'child_id': 'c1', 'status': 'done', 'token_count': 1200})
    emitter.sdk({'type': 'message_end', 'message': {'usage': {'input': 100, 'output': 50}}})
    emitter.sdk({'type': 'finalization_reserve'})
    emitter.sdk({'type': 'investigation_report_persisted'})
    kinds = [e['kind'] for e in out]
    assert kinds[:3] == ['phase', 'phase', 'agent_started']
    started = out[2]
    assert started['agent_id'] == 'c1' and started['parent_id'] == 'lead'
    assert started['payload']['question'] == 'Check antifoam lot L-8812'
    saved = next(e for e in out if e['kind'] == 'subreport_saved')
    assert saved['agent_id'] == 'c1'  # exact attribution via the kernel's session key
    assert next(e for e in out if e['kind'] == 'budget')['agent_id'] is None  # approximate
    assert 'agent_finished' in kinds
    assert [e['payload']['phase'] for e in out if e['kind'] == 'phase'] == ['planning', 'investigating', 'finalizing', 'submitted']
    assert [e['local_seq'] for e in out] == list(range(len(out)))
    assert emitter.total_tokens == 150 + 1200


# --- harness streaming -------------------------------------------------------------------------

SCRIPT = ('import json,sys,time\n'
          'data=sys.stdin.read()\n'
          'print(json.dumps({"type":"child_activity","child_id":"c1","status":"running"}),flush=True)\n'
          'print("plain text line",flush=True)\n'
          'sys.stderr.write("warning\\n")\n'
          'print(json.dumps({"type":"echo","n":len(data)}),flush=True)\n')


def test_stream_delivers_lines_live_and_keeps_full_output(tmp_path):
    seen = []
    result = _stream([sys.executable, '-c', SCRIPT], cwd=tmp_path, env=os.environ.copy(), input_text='{"x":1}',
                     timeout=30, on_line=seen.append)
    assert result.returncode == 0
    assert [e['type'] for e in seen] == ['child_activity', 'echo'] and seen[1]['n'] == 7
    assert 'plain text line' in result.stdout and result.stderr == 'warning\n'


def test_stream_times_out_kills_and_keeps_partial_output(tmp_path):
    slow = 'import time;print("started",flush=True);time.sleep(30)'
    started = time.monotonic()
    with pytest.raises(Exception) as error:
        _stream([sys.executable, '-c', slow], cwd=tmp_path, env=os.environ.copy(), input_text='', timeout=1)
    assert type(error.value).__name__ == 'TimeoutExpired' and 'started' in error.value.stdout
    assert time.monotonic() - started < 10


def test_stream_survives_a_failing_consumer(tmp_path):
    def broken(_):
        raise RuntimeError('consumer bug')
    result = _stream([sys.executable, '-c', SCRIPT], cwd=tmp_path, env=os.environ.copy(), input_text='',
                     timeout=30, on_line=broken)
    assert result.returncode == 0


# --- dispatcher ingestion (fake store and container) -------------------------------------------

class FakeStore:
    def __init__(self):
        self.rows, self.since = {}, None

    def append_events(self, ident, fence, attempt, events, log_since=None):
        if fence != 'fence-2' or attempt != 2:  # only the current attempt may write
            return 0
        for e in events:
            self.rows.setdefault((ident, attempt, e['local_seq']), e)
        self.since = log_since
        return len(events)


class FakeContainer:
    def __init__(self, lines):
        self.lines, self.calls = lines, []

    def logs(self, **kwargs):
        self.calls.append(kwargs)
        return b'\n'.join(self.lines)


def log(ts, value):
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    return f'2026-11-05T10:00:{ts:02d}.123456789Z '.encode() + body


def dispatcher(store):
    pytest.importorskip('docker')
    from src.cloud_backend.dispatcher import Dispatcher
    return Dispatcher(store, engine=None, s3=None, encryption_key=b'k' * 32,
                      config={'image': 'agent@sha256:' + 'a' * 64})


def test_ingest_keeps_allow_listed_lines_resumes_and_dedupes():
    store = FakeStore()
    d = dispatcher(store)
    job = {'id': 'job-1', 'fence': 'fence-2', 'attempt': 2, 'log_since': None}
    lines = [log(1, event('phase', {'phase': 'planning'}, 0)), log(2, b'Traceback: secret source text'),
             log(3, event('agent_started', {'depth': 1, 'question': 'q'}, 1)), log(4, {'event': 'agent_failed'})]
    d.ingest(job, FakeContainer(lines))
    assert sorted(k[2] for k in store.rows) == [0, 1]
    assert job['log_since'] == store.since and store.since > 0
    container = FakeContainer(lines + [log(5, event('error', {'code': 'agent_failed'}, 2))])
    d.ingest(job, container)
    assert container.calls[0]['since'] == int(job['log_since']) or container.calls[0]['since'] <= job['log_since']
    assert sorted(k[2] for k in store.rows) == [0, 1, 2]  # re-read lines were not duplicated


def test_ingest_from_a_stale_attempt_is_fenced_out():
    store = FakeStore()
    d = dispatcher(store)
    d.ingest({'id': 'job-1', 'fence': 'old-fence', 'attempt': 1, 'log_since': None},
             FakeContainer([log(1, event('phase', {'phase': 'planning'}))]))
    assert store.rows == {}


# --- events API (fake store, no network) -------------------------------------------------------

class ApiStore:
    def __init__(self):
        self.audits = []
        self.events_rows = [{'seq': i, 'attempt': 1, 'at': '2026-11-05T10:00:00+00:00', 'kind': 'phase',
                             'agent_id': 'lead', 'parent_id': None, 'payload': {'phase': 'planning'}} for i in range(1, 4)]

    def connect(self):
        class Con:
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return Con()

    def audit(self, *args, **kwargs):
        self.audits.append(args)

    def get(self, tenant, project, ident, actor):
        return {'id': ident} if (tenant, project, ident) == ('tenant', 'proj', 'job-1') else None

    def events(self, tenant, project, ident, after=0, limit=500):
        return [e for e in self.events_rows if e['seq'] > after][:limit]


@pytest.fixture
def api(monkeypatch):
    pytest.importorskip('jwt'); pytest.importorskip('psycopg'); pytest.importorskip('cryptography')
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from src.cloud_backend.api import create_app
    monkeypatch.setenv('DEPLOYMENT_TENANT', 'tenant'); monkeypatch.setenv('ARTIFACT_BUCKET', 'bucket')

    class Access:
        def __init__(self, roles): self.subject, self.tenant, self.roles = 'svc', 'tenant', roles
        def require(self, project, allowed):
            if self.roles.get(project) not in allowed:
                raise HTTPException(403, 'Project permission required')

    class Verifier:
        def verify(self, header):
            if header == 'Bearer viewer': return Access({'proj': 'viewer'})
            if header == 'Bearer other': return Access({'other': 'operator'})
            raise HTTPException(401, 'Invalid token')
    return TestClient(create_app(store=ApiStore(), verifier=Verifier(), s3=SimpleNamespace(), encryption_key=b'k' * 32))


def test_events_api_pages_and_enforces_project_access(api):
    first = api.get('/v1/projects/proj/jobs/job-1/events', headers={'Authorization': 'Bearer viewer'})
    assert first.status_code == 200 and [e['seq'] for e in first.json()['events']] == [1, 2, 3]
    later = api.get('/v1/projects/proj/jobs/job-1/events?after=2', headers={'Authorization': 'Bearer viewer'}).json()
    assert [e['seq'] for e in later['events']] == [3] and later['next'] == 3
    empty = api.get('/v1/projects/proj/jobs/job-1/events?after=3', headers={'Authorization': 'Bearer viewer'}).json()
    assert empty == {'events': [], 'next': 3}
    assert api.get('/v1/projects/proj/jobs/job-1/events', headers={'Authorization': 'Bearer other'}).status_code == 403
    assert api.get('/v1/projects/proj/jobs/missing/events', headers={'Authorization': 'Bearer viewer'}).status_code == 404
    assert api.get('/v1/projects/proj/jobs/job-1/events').status_code == 401


# --- PostgreSQL store (skips like the existing cloud tests) ------------------------------------

def test_store_fences_attempts_and_pages_events():
    dsn = os.getenv('CLOUD_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set CLOUD_TEST_DATABASE_URL to an isolated PostgreSQL database')
    from src.cloud_backend.store import Store
    store = Store(dsn); store.migrate()
    with store.connect() as con:
        con.execute('TRUNCATE cloud_job_events, cloud_jobs, cloud_audit RESTART IDENTITY')
    job = store.submit('t', 'p', 'svc', 'key-00001', {'sha256': 'a' * 64, 'timeout_seconds': 60})
    with store.connect() as con:
        con.execute("UPDATE cloud_jobs SET state='running',attempt=1,fence='f1' WHERE id=%s", (job['id'],))
    good = [clean(event('phase', {'phase': 'planning'}, 0)), clean(event('phase', {'phase': 'investigating'}, 1))]
    assert store.append_events(job['id'], 'f1', 1, good, log_since=5.0) == 2
    assert store.append_events(job['id'], 'f1', 1, good) == 0  # duplicate delivery
    assert store.append_events(job['id'], 'stale', 1, good) == 0
    page = store.events('t', 'p', job['id'])
    assert [e['kind'] for e in page] == ['phase', 'phase'] and store.events('t', 'other', job['id']) == []
