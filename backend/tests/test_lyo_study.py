from copy import deepcopy

import pytest

from benchmarks.lyo_study import study
from src.lifesci.lyophilization.case import receiving_config


def packet():
    c = receiving_config(load_vials=4000, capacity_kg_h=1.49)
    c['schedule'].append({'time_h': 8., 'shelf_temperature_c': -18., 'chamber_pressure_pa': 8.})
    return {'config': c, 'cutoff_h': 6., 'observations': [], 'allowed_actions': study.ACTIONS}


def test_action_preserves_past_and_replaces_only_future():
    p = packet()
    c = study.action_config(p, 'cool')
    assert c['schedule'][0] == p['config']['schedule'][0]
    assert c['schedule'][1]['time_h'] == 6.
    assert c['schedule'][1]['shelf_temperature_c'] == -30.
    assert len(c['schedule']) == 2
    assert p['config']['schedule'][1]['time_h'] == 8.


def test_pretransfer_changes_start_at_zero():
    p = packet(); p['cutoff_h'] = 0.
    assert study.action_config(p, 'moderate')['schedule'] == [
        {'time_h': 0., 'shelf_temperature_c': -26., 'chamber_pressure_pa': 8.}]


def test_reject_unknown_or_characterization_as_manufacturing_action():
    for name in ['invented', 'characterize']:
        with pytest.raises(ValueError): study.action_config(packet(), name)


def test_cutoff_is_enforced_before_fitting():
    p = packet(); p['observations'] = [{'time_h': 7., 'available_at_h': 7.}]
    with pytest.raises(ValueError, match='cutoff'): study.validate_packet(p)


def test_reference_capacity_censors_completion_and_thermal_label():
    truth = {'completion_time_h': 25., 'first_capacity_h': 10., 'first_critical_h': 12.}
    result = study.target(truth)
    assert result['completion_time_h'] is None
    assert result['thermal_warning'] is None
    assert result['capacity_warning'] is True


def test_thermal_before_overload_is_observable():
    truth = {'completion_time_h': 25., 'first_capacity_h': 10., 'first_critical_h': 9.}
    assert study.target(truth)['thermal_warning'] is True


def test_simultaneous_sampled_thermal_and_capacity_onsets_are_censored():
    assert study.target({'completion_time_h':25.,'first_capacity_h':10.,'first_critical_h':10.})['thermal_warning'] is None


def test_pressure_mismatch_prevents_calibration():
    import json
    p=packet();p['observations']=[{'time_h':1.,'chamber_pressure_pa':10.}]
    for arm in ('B','C'):
        assert study._fit(json.dumps(p),arm)['status']=='invalid_observed_pressure_control'


def test_abstention_is_not_a_true_negative_or_successful_operation():
    truth = {'keep': {'completion_time_h': 25., 'first_capacity_h': None, 'first_critical_h': None}}
    s = study.score({'completion_time_h': None, 'thermal_warning': None, 'capacity_warning': None,
                     'action_id': 'characterize'}, truth, 4000)
    assert s['thermal'] == 'abstain'
    assert s['capacity'] == 'abstain'
    assert s['selected_feasible'] is False
    assert s['selection_made'] is False
    assert s['throughput_vials_h'] == 0.
    assert s['abstained_with_hindsight_feasible_action'] is True


def test_failed_execution_is_preserved_separately_from_abstention():
    s = study.score(None, {'keep': {'completion_time_h': 25., 'first_capacity_h': None, 'first_critical_h': None}}, 4000)
    assert s['execution_completed'] is False
    assert s['thermal'] == 'execution_failed'


def test_prior_excursion_makes_later_intervention_infeasible():
    assert not study.feasible({'completion_time_h': 25., 'first_capacity_h': None, 'first_critical_h': 2.})


def test_output_is_immutable(tmp_path):
    study.write_new_directory(tmp_path/'run')
    with pytest.raises(FileExistsError): study.write_new_directory(tmp_path/'run')


def test_hash_changes_with_data():
    assert study.digest({'a':1}) != study.digest({'a':2})


def test_manifest_tampering_is_rejected(tmp_path):
    study.dump(tmp_path/'generation-status.json',{'status':'complete','manifest_sha256':study.digest({'original':'hash'})})
    study.dump(tmp_path/'manifest.json',{})
    with pytest.raises(ValueError,match='manifest hash mismatch'): study.verify_dataset(tmp_path)
