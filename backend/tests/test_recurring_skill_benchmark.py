"""The evaluation must reject plausible-looking definitions that change the request."""
from copy import deepcopy

import pytest

from benchmarks.skills.recurring import CASES, classify_outcome, definition_checks, summarize_attempts


def correct_definition():
    return {'name': 'Hourly case list', 'owner_id': 'benchmark-owner', 'status': 'draft',
            'every_minutes': 60, 'triggers': [], 'max_runs': 2, 'runs_admitted': 0,
            'task': {'operation': 'find_records', 'site_id': 'BENCH-SITE', 'kinds': ['case'],
                     'query': '', 'record_id': None, 'record_refs': [], 'dataset_ids': [], 'batches': [],
                     'offset': 0, 'limit': 50}}


@pytest.mark.parametrize('limit', [50, 100])
def test_requested_definition_is_accepted(limit):
    definition = correct_definition()
    definition['task']['limit'] = limit
    assert all(definition_checks(CASES[0], [definition]).values())


@pytest.mark.parametrize('field,value', [
    ('name', 'Unrequested name'), ('every_minutes', 15), ('status', 'active'),
    ('query', 'SYNTHETIC-CASE'), ('record_id', 'SYNTHETIC-CASE'),
    ('record_refs', [{'kind': 'case', 'id': 'SYNTHETIC-CASE', 'revision': 1}]),
    ('offset', 1), ('limit', 1),
])
def test_changed_request_cannot_receive_full_credit(field, value):
    definition = deepcopy(correct_definition())
    target = definition if field in definition else definition['task']
    target[field] = value
    assert not all(definition_checks(CASES[0], [definition]).values())


def test_missing_or_duplicate_definitions_fail():
    assert not all(definition_checks(CASES[0], []).values())
    assert not all(definition_checks(CASES[0], [correct_definition(), correct_definition()]).values())


def test_failed_attempts_are_counted_and_timed_separately():
    rows = [
        {'case_id': 'hourly', 'definition_pass': True, 'functional_pass': True,
         'lifecycle_pass': False, 'agent_seconds': 4.0},
        {'case_id': 'hourly', 'definition_pass': False, 'functional_pass': False,
         'agent_seconds': 10.0},
        {'case_id': 'daily', 'definition_pass': True, 'functional_pass': True,
         'lifecycle_pass': True, 'agent_seconds': 8.0},
        {'case_id': 'daily', 'definition_pass': True, 'functional_pass': True,
         'lifecycle_pass': True, 'agent_seconds': 12.0},
    ]
    summary = summarize_attempts(rows, repeats=2)
    assert summary['attempts'] == 4
    assert summary['functional_passes'] == 3
    assert summary['full_lifecycle_passes'] == 2
    assert summary['completion_seconds']['all']['mean'] == 8.5
    assert summary['completion_seconds']['correct']['mean'] == 8.0
    assert summary['completion_seconds']['failed']['mean'] == 10.0
    assert summary['cases_correct_every_repeat'] == 1


def test_missing_timings_are_not_zero_and_incomplete_repeats_do_not_pass():
    summary = summarize_attempts([
        {'case_id': 'hourly', 'definition_pass': True, 'functional_pass': True},
        {'case_id': 'daily', 'definition_pass': False, 'functional_pass': False, 'agent_seconds': 3.0},
    ], repeats=5)
    assert summary['attempts'] == 2
    assert summary['completion_seconds']['correct']['n'] == 0
    assert summary['completion_seconds']['correct']['mean'] is None
    assert summary['completion_seconds']['all']['mean'] == 3.0
    assert summary['cases_correct_every_repeat'] == 0


def test_background_inference_is_not_reported_as_wrong_task_values():
    row = {'definition_pass': True, 'lifecycle_behavior_pass': True, 'lifecycle_pass': False}
    assert classify_outcome(row) == 'background_inference'
    assert classify_outcome({**row, 'lifecycle_pass': True}) == 'correct'
    assert classify_outcome({**row, 'definition_pass': False}) == 'wrong_value'


def test_unavailable_or_crashed_attempt_is_an_error():
    assert classify_outcome({'turn': {'status': 'agent_unavailable'}}) == 'error'
    assert classify_outcome({'error': 'failed'}) == 'error'
