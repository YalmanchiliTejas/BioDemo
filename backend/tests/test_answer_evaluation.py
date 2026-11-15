"""The answer scorer must reject plausible figures attached to the wrong evidence."""
from copy import deepcopy

from benchmarks.skills import answers


CASE = {'left': 'CHO-001-R01', 'right': 'CHO-001-R02', 'parameter': 'glucose', 'unit': 'g/L',
        'expected': {'matched_times': 2, 'mean_difference': -1.0, 'largest_abs_difference': 2.0,
                     'largest_at': [5.0], 'standard_deviation': 1.4142135623730951},
        'conflict_expected': False}
RESULT = {'id': 'result-1', 'status': 'current', 'task_status': 'completed', 'evidence_state': 'provisional',
          'model_calls': 0, 'issues': [], 'task': {'operation': 'compare'},
          'source_refs': [{'kind': 'evidence', 'id': 'delivery-1', 'revision': 1, 'site_id': answers.trial.SITE}],
          'data': {'comparison_count': 2, 'series': [[], []], 'series_complete': True, 'truncated': False,
                   'alignment': {'tolerance_h': 0}, 'comparison_summary': [
                       {'left_batch': 'CHO-001-R01', 'right_batch': 'CHO-001-R02', 'parameter': 'glucose',
                        'unit': 'g/L', 'matched_times': 2, 'mean_difference': -1.0,
                        'statistics': {'standard_deviation': 1.4142135623730951},
                        'largest_difference': {'difference': -2.0, 'time_h': 5.0}}]}}


def test_computed_comparison_rejects_wrong_value_identity_or_provenance():
    assert all(answers.comparison_checks(CASE, RESULT, {'id': 'delivery-1', 'revision': 1}, 'decoy').values())
    for path, value in [
        (('data', 'comparison_summary', 0, 'mean_difference'), 1.0),
        (('data', 'comparison_summary', 0, 'parameter'), 'lactate'),
        (('data', 'comparison_summary', 0, 'right_batch'), 'CHO-002-R02'),
        (('data', 'comparison_summary', 0, 'unit'), 'mg/L'),
        (('data', 'comparison_summary', 0, 'largest_difference', 'time_h'), 6.0),
        (('data', 'comparison_summary', 0, 'largest_difference', 'difference'), -3.0),
        (('data', 'comparison_count'), 3), (('data', 'series_complete'), False),
        (('source_refs', 0, 'revision'), 2), (('source_refs', 0, 'id'), 'decoy'),
        (('evidence_state',), 'verified'), (('task_status',), 'needs_information'),
        (('status',), 'stale'),
    ]:
        bad = deepcopy(RESULT)
        target = bad
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        assert not all(answers.comparison_checks(CASE, bad, {'id': 'delivery-1', 'revision': 1}, 'decoy').values()), path


def test_reply_presence_does_not_erase_the_mean_sign():
    good = 'CHO-001-R02 minus CHO-001-R01: mean -1.0 g/L; largest absolute difference 2.0 g/L at 5.0 h.'
    assert all(answers.reply_coverage(CASE, good).values())
    assert not answers.reply_coverage(CASE, good.replace('-1.0', '+1.0'))['signed_mean']


def test_known_source_conflict_must_keep_needs_information_status():
    case = {**CASE, 'conflict_expected': True}
    result = deepcopy(RESULT)
    result['task_status'] = 'needs_information'
    result['issues'] = [{'code': 'conflicting_measurements'}]
    assert all(answers.comparison_checks(case, result, {'id': 'delivery-1', 'revision': 1}, 'decoy').values())
    result['task_status'] = 'completed'
    assert not all(answers.comparison_checks(case, result, {'id': 'delivery-1', 'revision': 1}, 'decoy').values())


def test_figures_without_correct_saved_computation_never_pass():
    turn = {'status': 'completed', 'reply': 'CHO-001-R02 minus CHO-001-R01: mean -1.0 g/L; largest 2.0 g/L at 5.0 h.'}
    assert not answers.score_attempt(CASE, turn, [], {'id': 'delivery-1', 'revision': 1}, 'decoy')['objective_pass']
    bad = deepcopy(RESULT)
    bad['data']['comparison_summary'][0]['mean_difference'] = 1.0
    assert not answers.score_attempt(CASE, turn, [bad], {'id': 'delivery-1', 'revision': 1}, 'decoy')['objective_pass']
    good = answers.score_attempt(CASE, turn, [RESULT], {'id': 'delivery-1', 'revision': 1}, 'decoy')
    assert good['objective_pass'] and good['manual_wording_review_required']


def test_completed_but_incorrect_turn_is_separate_from_successful_timing():
    rows = [
        {'status': 'completed', 'seconds': 10, 'score': {'objective_pass': True}},
        {'status': 'completed', 'seconds': 20, 'score': {'objective_pass': False}},
        {'status': 'agent_unavailable', 'seconds': 30, 'score': {'objective_pass': False}},
    ]
    summary = answers.summarize(rows)
    assert summary['objective_passes'] == 1
    assert summary['successful_seconds']['mean'] == 10
    assert summary['unsuccessful_seconds']['mean'] == 25
    assert summary['completed_seconds']['mean'] == 15
