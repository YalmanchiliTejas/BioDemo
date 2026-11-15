"""The trial benchmark's own checks: a reference check that cannot fail, or a calibration that leaks, proves nothing."""
import copy
import json

import pytest

from benchmarks.workflow_trial import run as trial

WORLD = {'decoy': 'decoy-id', 'deliveries': {'p': {'revision': 1}}, 'constructed': {'differs_in': ['Equipment']}}
TASK = {'package': 'p', 'dataset': 'd', 'check': {'kind': 'compare', 'conflict_expected': False, 'cohort': 'not_established', 'expected': {
    'matched_times': 2, 'mean_difference': 1.0, 'largest_abs_difference': 2.0, 'largest_at': [5.0], 'standard_deviation': 1.5}}}
GOOD = {'model_calls': 0, 'source_refs': [{'kind': 'evidence', 'id': 'd', 'revision': 1, 'site_id': 'S'}],
        'evidence_state': 'provisional', 'issues': [], 'task_status': 'completed',
        'data': {'comparison_count': 2, 'series': [1, 2], 'series_complete': True, 'truncated': False,
                 'cohort': {'verdict': 'not_established', 'not_recorded': ['Scale'], 'differs': []},
                 'comparison_summary': [{'matched_times': 2, 'mean_difference': 1.0, 'statistics': {'standard_deviation': 1.5},
                                         'largest_difference': {'difference': -2.0, 'time_h': 5.0}}]}}


def test_correct_result_passes_and_each_wrong_field_fails():
    assert trial.check(TASK, GOOD, WORLD) == []
    for path, value in [(('data', 'comparison_summary', 0, 'mean_difference'), 1.02),
                        (('data', 'comparison_summary', 0, 'largest_difference', 'time_h'), 6.0),
                        (('data', 'comparison_count'), 3), (('data', 'truncated'), True), (('evidence_state',), 'verified'),
                        (('data', 'comparison_summary', 0, 'statistics', 'standard_deviation'), 1.6),
                        (('data', 'cohort', 'verdict'), 'same_context'),  # context that is not recorded is not "the same"
                        (('model_calls',), 1), (('task_status',), 'needs_information'),
                        (('source_refs', 0, 'revision'), 2)]:
        wrong = copy.deepcopy(GOOD)
        target = wrong
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        assert trial.check(TASK, wrong, WORLD), path
    leaked = copy.deepcopy(GOOD)
    leaked['source_refs'].append({'kind': 'evidence', 'id': 'decoy-id', 'revision': 1, 'site_id': trial.OTHER_SITE})
    assert any('wrong-site' in problem for problem in trial.check(TASK, leaked, WORLD))


def test_calibration_threshold_comes_from_the_fit_split_only():
    sample = lambda probability, correct, split: {'probability': probability, 'correct': correct, 'split': split}
    samples = ([sample(.99, True, 'fit')] * 8 + [sample(.97, True, 'fit')] * 4 + [sample(.90, False, 'fit'), sample(.85, True, 'fit')]
               + [sample(.98, True, 'held_out')] * 5 + [sample(.60, False, 'held_out')])
    found = trial.calibrate(samples)
    assert found['threshold'] == .97 and found['fit']['precision'] == 1.0 and found['fit']['accepted'] == 12
    assert found['held_out'] == {'n': 6, 'accepted': 5, 'accepted_correct': 5, 'precision': 1.0, 'coverage': 5 / 6}
    # A wrong high-confidence answer in the held-out split is reported, not hidden by the fit threshold.
    surprised = trial.calibrate(samples + [sample(.995, False, 'held_out')])
    assert surprised['threshold'] == .97 and surprised['held_out']['precision'] == 5 / 6
    # Too few confident fit answers: no threshold, so nothing is ever applied automatically.
    assert trial.calibrate([sample(.99, True, 'fit')] * 3)['threshold'] is None


def test_same_task_ignores_batch_order_only():
    # The reference pairs each sample with the nearest one inside the tolerance, and refuses to score a tie.
    ref = {'present': {('A', 'x'): {0.0: 1.0, 10.0: 2.0, 20.0: 5.0}, ('B', 'x'): {1.0: 2.0, 10.0: 2.5, 29.0: 9.0}}}
    paired = trial.expected_comparison(ref, 'x', 'A', 'B', tolerance=2.0)
    assert paired['matched_times'] == 2 and paired['mean_difference'] == 0.75 and paired['largest_at'] == [0.0]
    assert trial.expected_comparison(ref, 'x', 'A', 'B')['matched_times'] == 1
    assert trial.expected_comparison(ref, 'x', 'A', 'B', window=(5, 25))['matched_times'] == 1
    tie = {'present': {('A', 'x'): {5.0: 1.0}, ('B', 'x'): {4.0: 1.0, 6.0: 2.0}}}
    assert trial.expected_comparison(tie, 'x', 'A', 'B', tolerance=2.0) is None
    expect = {'operation': 'compare', 'dataset_ids': ['d'], 'parameter': 'glucose', 'batches': ['A', 'B']}
    assert trial.same_task({**expect, 'batches': ['B', 'A'], 'site_id': 'S'}, expect)
    assert not trial.same_task({**expect, 'parameter': 'lactate'}, expect) and not trial.same_task(None, expect)


def test_trial_runs_on_the_real_deliveries_without_any_model(tmp_path, monkeypatch):
    for name in (*trial.ISOLATED, 'CMO_HOSTED_INFERENCE_APPROVED', 'CMO_REPOSITORY_ROOT'):
        monkeypatch.setenv(name, '')  # restored afterwards; the run points every store at its own temporary directory
    for name in ('LIFESCI_DECISION_ADAPTER', 'TYPESAFE_API_KEY', 'ASSISTANT_LOOP'):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / 'report'
    assert trial.main(['--output', str(output), '--repeats', '1']) == 0
    report = json.loads((output / 'report.json').read_text())
    direct = report['B_direct_workflows']
    assert direct['tasks']['passed'] == direct['tasks']['requests'] >= 60 and direct['tasks']['time']['over_target'] == 0
    assert {job['job'][:2] for job in direct['tasks']['by_job']} >= {'01', '02', '03', '04', '05', '06', '07', '08'}
    assert direct['typed_requests']['outcomes'].get('direct_wrong', 0) == 0
    assert report['reasoning_model'] == {'calls': 0, 'blocked_attempts': 0, 'cost_usd': 0}
    assert report['C_decision_model']['status'] == 'not_run'
    with pytest.raises(SystemExit):
        trial.main(['--output', str(output)])  # never overwrites an earlier report
