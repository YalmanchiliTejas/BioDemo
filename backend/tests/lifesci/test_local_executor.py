"""Laptop demo executor: same interface as the remote one, the harness replaced by a fake runner."""
import hashlib
import threading
import time

import pytest

from src.lifesci import investigations as inv
from src.lifesci.container import Platform
from src.lifesci.local_executor import LocalExecutor, local_executor_from_env
from src.lifesci.store import RecordStore


def fake_runner(events=3, fail=False, gate=None):
    def run(job_id, manifest, write, cancelled, harnesses):
        write({'local_seq': 1, 'at': '2026-11-05T10:00:00Z', 'kind': 'agent_started', 'agent_id': 'lead', 'parent_id': None,
               'payload': {'depth': 0, 'status': 'running', 'question': manifest['objective']}})
        for i in range(2, events + 1):
            write({'local_seq': i, 'at': '2026-11-05T10:00:0%dZ' % i, 'kind': 'agent_activity', 'agent_id': f'child-{i}',
                   'parent_id': 'lead', 'payload': {'status': 'running', 'tool': 'search_evidence', 'tool_use_count': i}})
        if gate:
            gate.wait(5)
        if fail:
            raise RuntimeError('model provider rejected the key')
        return {'hypotheses': [{'statement': 'Antifoam dosing lagged foaming onset'}], 'open_questions': []}
    return run


def wait(executor, job_id, states=('succeeded', 'failed', 'cancelled')):
    for _ in range(200):
        if executor.job('p', job_id)['state'] in states:
            return executor.job('p', job_id)
        time.sleep(0.01)
    raise AssertionError('job did not finish')


def submit(executor, job_id='run-1', data=b'zip-bytes'):
    sha = hashlib.sha256(data).hexdigest()
    executor.upload('p', sha, data)
    return executor.submit('p', job_id, {'sha256': sha, 'objective': 'Why did DEV-31 foam?', 'as_of': None,
                                         'timeout_seconds': 600, 'max_tool_calls': 30})


def test_upload_checks_the_digest(tmp_path):
    with pytest.raises(ValueError):
        LocalExecutor(tmp_path).upload('p', '0' * 64, b'x')


def test_runs_in_the_background_streams_events_and_stores_a_reviewable_result(tmp_path):
    ex = LocalExecutor(tmp_path, runner=fake_runner())
    assert submit(ex)['state'] in ('queued', 'running')
    assert submit(ex)['id'] == 'run-1'  # idempotent
    assert wait(ex, 'run-1')['state'] == 'succeeded'
    page = ex.events('p', 'run-1', 0)
    assert [e['seq'] for e in page['events']] == [1, 2, 3] and page['next'] == 3
    assert ex.events('p', 'run-1', 3)['events'] == []
    result = ex.result('p', 'run-1')
    assert result['review_status'] == 'requires_human_review' and result['run_id'] == 'run-1'


def test_failure_keeps_detail_local_and_reports_a_short_reason(tmp_path):
    ex = LocalExecutor(tmp_path, runner=fake_runner(fail=True))
    submit(ex)
    job = wait(ex, 'run-1')
    assert job['state'] == 'failed' and 'rejected the key' in job['error']
    with pytest.raises(KeyError):
        ex.result('p', 'run-1')


def test_stop_cancels_and_no_result_is_written(tmp_path):
    gate = threading.Event()
    ex = LocalExecutor(tmp_path, runner=fake_runner(gate=gate))
    submit(ex)
    assert ex.cancel('p', 'run-1')['state'] == 'cancelled'
    gate.set()
    time.sleep(0.05)
    assert ex.job('p', 'run-1')['state'] == 'cancelled'
    with pytest.raises(KeyError):
        ex.result('p', 'run-1')


def test_a_restarted_api_shows_the_interrupted_run_as_failed(tmp_path):
    gate = threading.Event()
    submit(LocalExecutor(tmp_path, runner=fake_runner(gate=gate)))
    job = LocalExecutor(tmp_path).job('p', 'run-1')  # a new process: the thread is gone
    gate.set()
    assert job['state'] == 'failed' and 'restarted' in job['error']


def test_enabled_only_by_env_and_refused_on_lambda(tmp_path):
    assert local_executor_from_env({}) is None
    assert isinstance(local_executor_from_env({'INVESTIGATION_EXECUTOR': 'local', 'INVESTIGATION_LOCAL_ROOT': str(tmp_path)}), LocalExecutor)
    with pytest.raises(RuntimeError, match='Lambda'):
        local_executor_from_env({'INVESTIGATION_EXECUTOR': 'local', 'AWS_LAMBDA_FUNCTION_NAME': 'api'})


def test_platform_drives_a_local_investigation_to_review(tmp_path, monkeypatch):
    monkeypatch.setenv('INVESTIGATIONS_ENABLED_TENANTS', '*')
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role('T', 'ana', 'msat', site_id='NF1')
    ctx = p.identity.context_for('T', 'ana')
    p.evidence.ingest(ctx, source_system='lims', source_record_id='B-001', content=b'batch,do\nB-001,24\n',
                      media_type='text/csv', site_id='NF1', event_time=None)
    ex = LocalExecutor(tmp_path, runner=fake_runner())
    p.investigations = inv.InvestigationService(p, config=None, executor=ex)
    run = p.investigations.start(ctx, {'objective': 'Why did DEV-31 foam?', 'site_id': 'NF1',
                                       'record_refs': [{'kind': 'evidence', 'id': 'lims:B-001'}]})
    wait(ex, run['run_id'])
    view = p.investigations.sync(ctx, run['run_id'], force=True)
    view = p.investigations.get(ctx, run['run_id'])
    assert view['status'] == 'awaiting_review'
    assert {a['agent_id'] for a in view['agents']} >= {'lead', 'child-2', 'child-3'}
    assert p.investigations.report(ctx, run['run_id'])['report']['hypotheses']
