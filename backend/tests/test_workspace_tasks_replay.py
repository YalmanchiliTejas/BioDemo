"""Synthetic host-contract checks, not manufacturing or model-quality evidence."""
import hashlib
import json
import pytest


def make_fixture(tmp_path, tasks=None):
    content = b'Synthetic contract fixture. Equipment TEST-7 has a calibration note.\n'
    (tmp_path / 'source.txt').write_bytes(content)
    spec = {
        'schema_version': 'workspace-tasks-replay-v1',
        'suite_id': 'synthetic-contract',
        'provenance': {'kind': 'synthetic_contract', 'description': 'Hand-authored contract data only.'},
        'context': {'tenant_id': 'replay', 'actor_id': 'reviewer', 'site_id': 'S1'},
        'sources': [{
            'path': 'source.txt', 'sha256': hashlib.sha256(content).hexdigest(),
            'source_system': 'contract', 'source_record_id': 'TEST-7',
            'media_type': 'text/plain', 'event_time': '2026-11-01T00:00:00Z',
            'provenance': {'kind': 'synthetic_contract', 'citation': 'Local authored fixture',
                           'license': 'Local test material; no third-party source.'},
        }],
        'tasks': tasks or [{
            'id': 'find-note',
            'request': {'site_id': 'S1', 'operation': 'find_records', 'query': 'TEST-7', 'kinds': ['evidence']},
            'expected': {'task_status': 'completed', 'data': {'records': [{'id': 'contract:TEST-7'}]}},
        }],
    }
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps(spec))
    return path, spec


def test_subset_checks_ignore_extra_object_keys_but_detect_array_and_boolean_errors():
    from benchmarks.workspace_tasks_replay import check_expected

    assert check_expected({'data': {'value': 2, 'extra': 7}}, {'data': {'value': 2}}) == []
    assert check_expected({'rows': [1, 2]}, {'rows': [1]})
    assert check_expected({'flag': True}, {'flag': 1})
    assert check_expected({'rows': [{'value': 3}]}, {'rows': [{'value': 2}]})
    assert check_expected({}, {'missing': None})


def test_payload_hash_and_path_checks_precede_any_execution(tmp_path):
    from benchmarks.workspace_tasks_replay import load_fixture

    path, spec = make_fixture(tmp_path)
    (tmp_path / 'source.txt').write_text('changed source')
    with pytest.raises(ValueError, match='SHA-256'):
        load_fixture(path)
    spec['sources'][0]['path'] = '../outside.txt'
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='inside the fixture directory'):
        load_fixture(path)


def test_replay_retains_failed_attempts_and_separates_check_results_from_task_status(tmp_path):
    from benchmarks.workspace_tasks_replay import run_replay

    path, spec = make_fixture(tmp_path)
    spec['tasks'] += [
        {'id': 'wrong-answer', 'request': spec['tasks'][0]['request'],
         'expected': {'data': {'records': [{'id': 'wrong'}]}}},
        {'id': 'denied-site', 'request': {**spec['tasks'][0]['request'], 'site_id': 'S2'},
         'expected': {'task_status': 'completed'}},
        {'id': 'missing-dataset', 'request': {'site_id': 'S1', 'operation': 'reconcile'},
         'expected': {'task_status': 'needs_information', 'data': {'measurement_count': 0}}},
    ]
    path.write_text(json.dumps(spec))
    report = run_replay(path, repeats=2)
    assert report['summary']['attempts'] == 8
    assert report['summary']['outcomes'] == {'passed': 4, 'mismatch': 2, 'error': 2}
    assert report['summary']['task_statuses']['needs_information'] == 2
    assert report['summary']['all_run_wall_seconds']['n'] == 8
    assert report['summary']['service_wall_seconds']['n'] == 8
    assert report['summary']['provider_calls'] == 0
    assert report['summary']['blocked_inference_attempts'] == 0
    assert len(report['attempts']) == 8
    assert all(r['wall_seconds'] >= 0 for r in report['attempts'])
    assert all(r['error']['type'] == 'AuthorizationError' for r in report['attempts'] if r['outcome'] == 'error')
    assert report['fixture']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report['fixture']['sources'][0]['provenance']['kind'] == 'synthetic_contract'


def test_inference_guard_blocks_provider_and_embedding_calls_even_if_caught():
    from benchmarks.workspace_tasks_replay import InferenceGuard
    from src.lifesci.container import Platform
    from src.lifesci.store import RecordStore

    platform = Platform(RecordStore(), providers={})
    try:
        guard = InferenceGuard(platform)
        with pytest.raises(RuntimeError, match='inference is disabled'):
            platform.gateway.run(None)
        with pytest.raises(RuntimeError, match='inference is disabled'):
            platform.agent_memory.embedder.embed(['example'])
        assert guard.blocked_attempts == 2
        assert platform.gateway.providers == {}
    finally:
        platform.store.release_connections()


def test_cli_writes_report_and_returns_nonzero_for_failed_checks(tmp_path):
    from benchmarks.workspace_tasks_replay import main

    path, spec = make_fixture(tmp_path)
    spec['tasks'][0]['expected']['task_status'] = 'needs_information'
    path.write_text(json.dumps(spec))
    report_path = tmp_path / 'report.json'
    assert main(['--fixture', str(path), '--output', str(report_path)]) == 1
    report = json.loads(report_path.read_text())
    assert report['summary']['outcomes'] == {'mismatch': 1}
    assert report['attempts'][0]['task_status'] == 'completed'
    assert report['summary']['provider_inference_cost_usd'] == 0
    assert report['summary']['total_compute_cost_usd'] is None


def test_fixture_rejects_missing_provenance_duplicate_tasks_and_vacuous_expectations(tmp_path):
    from benchmarks.workspace_tasks_replay import load_fixture

    path, spec = make_fixture(tmp_path)
    spec['sources'][0]['provenance']['license'] = ''
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='license'):
        load_fixture(path)
    spec['sources'][0]['provenance']['license'] = 'Local test material'
    spec['tasks'].append(spec['tasks'][0])
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='unique'):
        load_fixture(path)
    spec['tasks'] = [spec['tasks'][0]]
    spec['tasks'][0]['expected'] = {}
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='nonempty'):
        load_fixture(path)
