"""Supplement contracts: complete grid, information boundary, freeze, denominators."""
import importlib
import json
from itertools import product

import pytest


def module():
    return importlib.import_module('benchmarks.lyo_study.stress')


def test_complete_factorial_and_hidden_shift_never_enters_public_packet():
    cases = module().cases()
    expected = set(product([-28., -24., -20., -16.], [4000, 11000], [.4, 1.49], [1., 1.25]))
    actual = {tuple(c['factors'][k] for k in ('shelf_temperature_c', 'load_vials', 'vapor_capacity_kg_h', 'hidden_kv_scale')) for c in cases}
    assert len(cases) == len(actual) == 32
    assert actual == expected
    assert len({c['case_id'] for c in cases}) == 32
    for case in cases:
        packet = case['packet']
        assert packet['observations'] == []
        assert packet['cutoff_h'] == 0
        assert packet['config']['duration_h'] == 90
        assert len(packet['config']['schedule']) == 1
        assert 'kv_scale' not in packet['config']['equipment']
        assert 'mechanism' not in packet and 'factors' not in packet
        assert case['mechanism']['rp_scale'] == case['mechanism']['capacity_scale'] == 1
    for left, right in zip(cases[::2], cases[1::2]):
        assert left['packet']['config'] == right['packet']['config']
        assert left['mechanism']['kv_scale'] != right['mechanism']['kv_scale']


def test_metrics_censor_after_capacity_and_separate_reference_failure():
    stress = module()
    prediction = {'completion_time_h': 12., 'thermal_warning': False, 'capacity_warning': False}
    truth = {'completion_time_h': 10., 'first_capacity_h': 2., 'first_critical_h': 3.}
    value = stress.assess(prediction, truth)
    assert value['completion_eligible'] is False
    assert value['completion_absolute_error_h'] is None
    assert value['thermal'] == 'censored'
    assert value['capacity'] == 'FN'
    assert value['hindsight_capacity_invalid_completion'] is True
    missing = stress.assess(prediction, None)
    assert missing['thermal'] == missing['capacity'] == 'reference_failed'
    assert missing['completion_eligible'] is None
    truth.update(first_capacity_h=None, first_critical_h=None)
    missing_prediction = stress.assess(None, truth)
    assert missing_prediction['thermal'] == 'execution_failed'
    assert missing_prediction['completion_eligible'] is True
    assert stress.assess(prediction, truth)['completion_absolute_error_h'] == 2.


def test_protocol_precedes_solves_and_failures_remain_in_all_case_denominators(tmp_path, monkeypatch):
    stress = module()
    output = tmp_path/'supplement'
    calls = {'reference': 0, 'B': 0, 'C': 0}

    # Replace only expensive numerical boundaries. Exercise the real freezing,
    # orchestration, failure capture, scoring, aggregation and artifact writes.
    def reference(config, mechanism):
        assert (output/'protocol.json').is_file()
        assert len(json.loads((output/'case-plan.json').read_text())) == 32
        calls['reference'] += 1
        if calls['reference'] == 1:
            raise RuntimeError('reference failed fixture')
        return {'completion_time_h': 10., 'first_capacity_h': None,
                'first_critical_h': None, 'trajectory': [], 'reference_version': 'fixture'}

    def predict(packet, arm, action_id):
        assert packet['observations'] == [] and action_id == 'keep'
        calls[arm] += 1
        if arm == 'B' and calls[arm] == 2:
            raise RuntimeError('model failed fixture')
        return {'completion_time_h': 12., 'thermal_warning': False, 'capacity_warning': False,
                'calibration': {'status': 'nominal_pretransfer_no_receiving_measurements', 'nfev': 0}}

    monkeypatch.setattr(stress, 'reference', reference)
    monkeypatch.setattr(stress.study, 'predict', predict)
    summary = stress.run(output)
    assert calls == {'reference': 32, 'B': 32, 'C': 32}
    assert summary['cases'] == 32 and summary['reference_failures'] == 1
    b, c = summary['arms']['B'], summary['arms']['C']
    assert b['planned'] == c['planned'] == 32
    assert b['completion_eligible'] == c['completion_eligible'] == 31
    assert b['completion_predictions'] == 30 and c['completion_predictions'] == 31
    assert b['completion_prediction_coverage'] == pytest.approx(30/31)
    assert b['completion_mae_h'] == c['completion_mae_h'] == 2.
    assert b['thermal']['truth_negative'] == 31
    assert b['thermal']['TN'] == 30
    assert b['thermal']['execution_failed'] == b['thermal']['reference_failed'] == 1
    records = json.loads((output/'results.json').read_text())
    assert len(records) == 32
    assert records[0]['reference_error'] == 'RuntimeError: reference failed fixture'
    assert records[1]['models']['B']['error'] == 'RuntimeError: model failed fixture'
    assert len(list((output/'evaluator').glob('*.json'))) == 32
    assert (output/'report.md').is_file()
    assert json.loads((output/'status.json').read_text())['status'] == 'complete'
    assert stress.verify(output)['verified'] is True
    with pytest.raises(FileExistsError):
        stress.run(output)
    assert calls == {'reference': 32, 'B': 32, 'C': 32}
    (output/'results.json').write_text('[]')
    with pytest.raises(ValueError, match='hash'):
        stress.verify(output)
