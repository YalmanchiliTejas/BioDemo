"""Controlled trial behavior; fixture scores are never manufacturing results."""
import copy
import json

import pytest

from benchmarks.common import pilot_benchmark as pilot
from benchmarks.common.case_protocol import digest, load_case, save, stable_hash
from benchmarks.common.case_runner import evaluate_run
from benchmarks.common.human_work import aggregate_effort, produce_comparison
from test_case_evaluation_v2 import fixture_case, artifact, review, measured_logs, output


def suite(tmp_path, **kwargs):
    source = tmp_path / 'source'
    fixture_case(source)
    path = tmp_path / 'suite'
    pilot.freeze(path, [source / 'case.json'], **kwargs)
    return path


def fake_runner(manifest, mode, *, output_root, operator_id):
    """Use real run/review hashes to exercise orchestration, not model accuracy."""
    from benchmarks.common.case_runner import review_template
    from benchmarks.common.trace import TraceSink
    import uuid
    case = load_case(manifest)
    policy = json.loads((manifest.parent / case['quality_policy']).read_text())
    run = artifact(case, policy, uuid.uuid4().hex, mode)
    run['condition'] = case['condition']
    path = output_root / run['run_id']
    path.mkdir(parents=True)
    save(path / 'output.json', run['output'])
    save(path / 'quality-policy.json', policy)
    run['output_sha256'] = digest(path / 'output.json')
    sink = TraceSink(path / 'trace.jsonl', case['case_id'], run['run_id'])
    sink.emit(actor='evaluator', stage='verification', action='fixture')
    run.update(trace_sha256=digest(sink.path), trace_path='trace.jsonl')
    save(path / 'run.json', run)
    save(path / 'review-template.json', review_template(run))
    return path / 'run.json'


def test_freeze_pins_shared_inputs_and_shuffles_repeat_pairs(tmp_path):
    path = suite(tmp_path, repeats=3)
    _, protocol = pilot.load_suite(path, check_code=True)
    assert len(protocol['cases']) == 2
    assert len(protocol['schedule']) == 24
    for pair in {a['pair_id'] for a in protocol['schedule']}:
        assert {a['method'] for a in protocol['schedule'] if a['pair_id'] == pair} == set(pilot.METHODS)
    raw, variant = [load_case(path / e['manifest']) for e in protocol['cases']]
    assert [f['sha256'] for f in raw['allowlist']] == [f['sha256'] for f in variant['allowlist']]
    assert raw['reference_sha256'] != variant['reference_sha256']
    assert variant['generalization_claim_eligible'] is False
    assert raw['execution_policy'] == {'mode': 'adaptive_v1', 'soft_tool_calls': 48}
    with pytest.raises(ValueError, match='fresh'): pilot.freeze(path)


def test_freeze_rejects_duplicate_cases_and_incomplete_domain_approval(tmp_path):
    source = tmp_path / 'source'
    fixture_case(source)
    with pytest.raises(ValueError, match='Duplicate'):
        pilot.freeze(tmp_path / 'suite', [source / 'case.json'] * 2)
    bad = tmp_path / 'bad.json'
    save(bad, {'status': 'approved'})
    with pytest.raises(ValueError, match='approval'):
        pilot.freeze(tmp_path / 'suite', [source / 'case.json'], quality_policy=bad)


def test_implementation_drift_blocks_execution(tmp_path, monkeypatch):
    path = suite(tmp_path)
    monkeypatch.setattr(pilot, 'implementation_hash', lambda: 'different')
    with pytest.raises(ValueError, match='changed after freeze'): pilot.execute(path)


def test_resume_keeps_failures_and_stop_file_prevents_new_attempts(tmp_path, monkeypatch):
    path = suite(tmp_path, repeats=1, filename_challenges=False)
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('fixture infrastructure failure')
    monkeypatch.setattr('benchmarks.common.case_runner.run_case', fail)
    state = pilot.execute(path, methods=['full_rlm'])
    assert len(calls) == 1
    assert next(iter(state['assignments'].values()))['status'] == 'runner_error'
    pilot.execute(path, methods=['full_rlm'])
    assert len(calls) == 1  # no automatic selection of a successful retry
    (path / 'STOP').touch()
    pilot.execute(path)
    assert len(calls) == 1
    report = pilot.report(path)
    assert report['readiness']['status'] == 'not_ready'
    assert report['runner_problems']
    assert report['recorded_runs'] == 0


def test_blinded_export_and_return_bind_exact_output_and_persist_review(tmp_path, monkeypatch):
    path = suite(tmp_path, repeats=1, filename_challenges=False)
    monkeypatch.setattr('benchmarks.common.case_runner.run_case', fake_runner)
    pilot.execute(path, methods=['full_rlm'])
    exported = pilot.export_reviews(path, tmp_path / 'reviewers')
    assert exported['packets'] == 1
    form_path = next((tmp_path / 'reviewers').glob('*.review.json'))
    form = json.loads(form_path.read_text())
    assert not {'run_id', 'output_sha256', 'policy_sha256'} & form.keys()
    assert not list((tmp_path / 'reviewers').glob('*key*'))
    key = pilot._load(exported['private_key'])
    entry = key['packets'][form['packet_id']]
    run = json.loads((path / entry['run_path']).read_text())
    checked = review(run, run['quality_policy'])
    form.update({k: v for k, v in checked.items() if k not in ('run_id', 'output_sha256', 'policy_sha256')})
    save(form_path, form)
    assert pilot.import_review(path, form_path, exported['private_key'])['qualified'] is True
    assert evaluate_run(path / entry['run_path'])['qualified'] is True
    summary = pilot.report(path)
    assert summary['readiness']['status'] == 'not_ready'  # missing baselines and observed effort
    (path / entry['run_path']).parent.joinpath('output.json').write_text('{}')
    assert pilot.report(path)['readiness']['status'] == 'not_ready'


def test_report_rejects_reassignment_or_method_mismatch(tmp_path, monkeypatch):
    path = suite(tmp_path, repeats=1, filename_challenges=False)
    monkeypatch.setattr('benchmarks.common.case_runner.run_case', fake_runner)
    state = pilot.execute(path, methods=['full_rlm'])
    entry = next(iter(state['assignments'].values()))
    run_path = path / entry['run_path']
    run = json.loads(run_path.read_text())
    run['mode'] = 'conventional'
    save(run_path, run)
    with pytest.raises(ValueError, match='method differs'): pilot.report(path)


def test_explicit_pair_ids_allow_repeats_without_cherry_picking(tmp_path):
    case, _, policy = fixture_case(tmp_path)
    runs = []
    for repeat in range(2):
        for mode in ('manual', 'full_rlm'):
            run = artifact(copy.deepcopy(case), policy, f'{mode}-{repeat}', mode)
            run.update(pair_id=f'pair-{repeat}', qualification={'status': 'qualified', 'qualified': True, 'quality_score': 3})
            runs.append(run)
    logs = measured_logs(runs)
    for row in logs['runs']:
        if row['run_id'].startswith('full_rlm'):
            for phase in row['phases'].values(): phase['active_seconds'] = 30
    result = produce_comparison(runs, aggregate_effort(runs, logs))
    assert result['paired_sample_size'] == 2
    assert result['paired_human_effort_reduction_pct'] == 50
    runs.append(copy.deepcopy(runs[-1]))
    with pytest.raises(ValueError): aggregate_effort(runs, measured_logs(runs))


def test_manual_output_needs_observation_and_never_overwrites_assignment(tmp_path):
    path = suite(tmp_path, repeats=1, filename_challenges=False)
    _, protocol = pilot.load_suite(path)
    assignment = next(a for a in protocol['schedule'] if a['method'] == 'manual')
    session_path, output_path = tmp_path / 'session.json', tmp_path / 'manual.json'
    save(output_path, output())
    save(session_path, {'operator_id': 'engineer'})
    with pytest.raises(ValueError, match='attestations'):
        pilot.record_manual(path, assignment['assignment_id'], output_path, session_path)
    save(session_path, {'operator_id': 'engineer', 'evidence_ref': 'observer-log',
                        'authorized_evidence_only': True, 'no_future_leakage': True,
                        'started_at': '2026-02-01T00:00:00Z', 'ended_at': '2026-02-01T00:10:00Z'})
    run_path = pilot.record_manual(path, assignment['assignment_id'], output_path, session_path)
    run = json.loads(run_path.read_text())
    assert run['attempted'] and run['mode'] == 'manual'
    assert 'attestation' in run['isolation_audit']['mechanism']
    assert run['qualification']['qualified'] is None
    with pytest.raises(ValueError, match='already recorded'):
        pilot.record_manual(path, assignment['assignment_id'], output_path, session_path)


def test_filename_variant_freezes_rewritten_package_index_and_exports_only_sources(tmp_path):
    from benchmarks.common.case_audit import audit_case
    source = tmp_path / 'source'
    case, _, _ = fixture_case(source)
    metadata = source / 'agent_input/package_manifest.json'
    metadata.write_text(json.dumps({'files': [{'path': 'records.csv', 'sha256': case['allowlist'][0]['sha256']}]}))
    case['allowlist'].append({'path': metadata.name, 'sha256': digest(metadata), 'bytes': metadata.stat().st_size, 'available_at': None})
    case['package_sha256'] = stable_hash(case['allowlist'])
    case['task_spec_sha256'] = stable_hash({k: v for k, v in case.items() if k not in ('frozen_at', 'task_spec_sha256')})
    save(source / 'case.json', case)
    path = tmp_path / 'suite'
    pilot.freeze(path, [source / 'case.json'], repeats=1)
    _, protocol = pilot.load_suite(path)
    entry = protocol['cases'][1]
    manifest = path / entry['manifest']
    changed = load_case(manifest)
    exported = tmp_path / 'public-evidence'
    pilot.export_inputs(path, exported, entry['key'])
    public = exported / changed['task_spec_sha256']
    index = json.loads((public / 'package_manifest.json').read_text())
    assert index['files'][0]['path'] == 'sources/input_0000.csv'
    assert digest(public / 'package_manifest.json') == next(f['sha256'] for f in changed['allowlist'] if f['path'] == 'package_manifest.json')
    assert not (public / 'reference.json').exists()
    assert not (public / 'quality-policy.json').exists()
    assert {str(p.relative_to(public)) for p in public.rglob('*') if p.is_file()} == {f['path'] for f in changed['allowlist']}


def test_sdk_setting_drift_requires_new_freeze(tmp_path, monkeypatch):
    path = suite(tmp_path)
    current = pilot.runtime_configuration()
    monkeypatch.setattr(pilot, 'runtime_configuration', lambda: {**current, 'compaction_target_tokens': 'off'})
    with pytest.raises(ValueError, match='runtime settings changed'):
        pilot.execute(path)


def test_provider_env_excludes_database_secrets_and_restores_process(tmp_path, monkeypatch):
    for name in ('MODAL_PROXY_TOKEN', 'SUPABASE_SERVICE_ROLE_KEY'):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / 'provider.env'
    env.write_text('MODAL_PROXY_TOKEN=fixture-inference-token\nSUPABASE_SERVICE_ROLE_KEY=fixture-admin-secret\n')
    import os
    with pilot.provider_environment(env):
        assert os.environ.get('MODAL_PROXY_TOKEN') == 'fixture-inference-token'
        assert 'SUPABASE_SERVICE_ROLE_KEY' not in os.environ
    assert 'MODAL_PROXY_TOKEN' not in os.environ


def test_pending_visual_source_checks_require_bound_independent_receipts(tmp_path):
    from benchmarks.common.case_runner import review_template
    from benchmarks.common.quality import score_review
    case, _, policy = fixture_case(tmp_path)
    run = artifact(case, policy)
    run['output']['analysis'].update(source_verification_status='human_review_pending',
        verification={'pending_source_reviews': [{'observation_id': 'scan-1', 'source_ref': {'path': 'records.csv', 'row': 2}}]})
    checked = review(run, policy)
    assert score_review(run, policy, checked)['qualified'] is None
    checked['source_reviews'] = review_template(run)['source_reviews']
    receipt = checked['source_reviews'][0]
    receipt.update(value_matches=True, reviewer_id='independent-reviewer', evidence_ref='visual-review-receipt')
    assert score_review(run, policy, checked)['qualified'] is True
    receipt['sha256'] = 'wrong-version'
    assert score_review(run, policy, checked)['qualified'] is None
    receipt['value_matches'] = False
    assert score_review(run, policy, checked)['qualified'] is False
