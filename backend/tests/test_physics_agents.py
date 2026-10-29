"""Restricted runner contracts; scripted fixtures here are not agent results."""
import json
from pathlib import Path

import pytest

from benchmarks.physics_value.generate import generate
from benchmarks.physics_value.run_agents import HostTools, aggregate, arm_metrics


@pytest.fixture(scope='module')
def dataset(tmp_path_factory):
    path = tmp_path_factory.mktemp('physics-agent-contracts') / 'dataset'
    generate(path, seed=109, replicates=1, plots=False)
    return path


def case_id(dataset, domain='oxygen', family='nominal'):
    return next(c['case_id'] for c in json.loads((dataset / 'evaluator/catalogue.json').read_text())
                if c['domain'] == domain and c['family'] == family)


def decision(**updates):
    return {'hypotheses': ['nominal'], 'action_id': 'keep', 'warn_before_transfer': False,
            'rationale': 'Test-only submission', 'uncertainty': 'Synthetic contract fixture',
            'evidence': ['receiving_configuration'], **updates}


def test_model_is_only_an_additional_b_capability(dataset, tmp_path):
    identity = case_id(dataset)
    a = HostTools(dataset, identity, 'optimization', 'A', tmp_path / 'a', 10)
    b = HostTools(dataset, identity, 'optimization', 'B', tmp_path / 'b', 10)
    assert a.packet == b.packet
    assert a.call('physical_forward_model', {'action_id': 'keep'}) == {'error': 'tool unavailable in this arm or task'}
    predicted = b.call('physical_forward_model', {'action_id': 'keep'})
    assert 'result' in predicted and 'causes' not in predicted and 'recommended_action' not in predicted


def test_submission_freezes_without_revealing_evaluator_scores(dataset, tmp_path):
    host = HostTools(dataset, case_id(dataset), 'pretransfer', 'A', tmp_path, 10)
    accepted = host.call('submit_decision', decision())
    assert accepted == {'accepted': True, 'decision_frozen': True}
    assert host.score['warning_result'] == 'TN'
    assert 'warning_result' not in accepted and 'authored_cause_coverage' not in accepted
    assert host.call('submit_decision', decision(action_id='pressure')) == {'error': 'decision already frozen'}
    assert host.submission['action_id'] == 'keep'


def test_invalid_submission_is_not_upgraded_to_a_success(dataset, tmp_path):
    host = HostTools(dataset, case_id(dataset), 'diagnosis', 'B', tmp_path, 10)
    result = host.call('submit_decision', decision(hypotheses=['answer_from_hidden_file']))
    assert 'error' in result and host.submission is None and host.score is None


def test_only_resolution_can_release_new_measurements(dataset, tmp_path):
    identity = case_id(dataset, family='sensor_bias')
    for task in ('pretransfer', 'diagnosis', 'optimization'):
        host = HostTools(dataset, identity, task, 'A', tmp_path / task, 10)
        assert 'error' in host.call('request_measurement', {'measurement': 'sensor_check'})
    host = HostTools(dataset, identity, 'resolution', 'A', tmp_path / 'resolution', 10)
    result = host.call('request_measurement', {'measurement': 'sensor_check'})
    assert result['current_time_h'] == 7
    assert host.packet['decision_time_h'] == 7
    assert all(r['available_at_h'] <= 7 for r in host.packet['receiving_observations'])
    assert host.call('submit_decision', decision(hypotheses=['sensor_bias']))['accepted']
    assert host.score['resolution_verification']['verification_available_at_h'] == 25


def test_failed_attempts_remain_in_denominators_and_unknown_metrics_stay_null():
    failed = {'status': 'no_submission', 'score': None, 'wall_seconds': 120., 'tool_calls': 0, 'physical_model_calls': 0}
    metrics = arm_metrics([failed], 'optimization')
    assert metrics['attempted'] == 1 and metrics['completed'] == 0
    assert metrics['failed_or_unsubmitted'] == 1 and metrics['feasible_selected_actions'] == 0
    assert metrics['mean_authored_cause_coverage'] is None


def test_input_mismatch_is_visible_in_aggregate():
    base = {'case_id': 'example', 'task': 'diagnosis', 'status': 'no_submission',
            'score': None, 'wall_seconds': 1., 'tool_calls': 0, 'physical_model_calls': 0}
    rows = [dict(base, arm='A', common_input_sha256={'packet.json': 'one'}),
            dict(base, arm='B', common_input_sha256={'packet.json': 'different'})]
    result = aggregate(rows, {'planned_attempts': 2, 'tasks': ['diagnosis']})
    assert not result['pair_inputs_match'] and result['complete_pairs'] == 0
    assert result['observed_engineer_hours_saved'] is None
