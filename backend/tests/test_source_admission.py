"""Source trajectories must pass the same oxygen-domain gate as receivers."""
from pathlib import Path
import pytest
from benchmarks.external_simulators.challenges import admit_source,pen_scenario
from benchmarks.external_simulators.forecast_contract import evidence_hash,validate_case_source_calibration


def test_floor_count_is_rejected_even_if_saved_observation_is_positive():
    with pytest.raises(ValueError,match='Completed source'):
        admit_source({'audit':{'dissolved_oxygen_floor_events':1},'terminal':{'DO2':10.}})
    admit_source({'audit':{'dissolved_oxygen_floor_events':0}})


@pytest.mark.skipif(not Path('/private/tmp/biodemo-audited-native').exists(),reason='Pinned runtime required')
def test_actual_clipped_source_is_rejected_and_declared_aeration_plan_is_admitted():
    paths={'pensim':'/private/tmp/biodemo-pensimpy-source','native':'/private/tmp/biodemo-audited-native'}
    legacy=pen_scenario(paths,8005,{'feed_factor':1.,'air_factor':1.,'apply_after_h':60.})
    with pytest.raises(ValueError,match='oxygen-floor'):admit_source(legacy)
    revised=pen_scenario(paths,8005,{'feed_factor':1.,'air_factor':1.15,'apply_after_h':60.})
    admit_source(revised)
    assert revised['audit']['dissolved_oxygen_floor_events']==0


def test_fitted_source_schedule_must_match_the_declared_source_plan():
    history=[{'time_h':96.,'state':{'P':5.}}];digest=evidence_hash(history)
    full={'source_history':history,'source_operating_plan':{'air_factor':1.15},'source_calibration':{
        'evidence_scope':'completed_source_before_receiving','source_history_sha256':digest,'product_ratio':1.,'indicator_offset':0.,
        'physical_parameter_fit':{'method':'source_trajectory_kinetics_v2','source_history_sha256':digest,'source_operating_plan':{'air_factor':1.}}}}
    with pytest.raises(ValueError,match='operating plan mismatch'):validate_case_source_calibration(full)
    full['source_calibration']['physical_parameter_fit']['source_operating_plan']={'air_factor':1.15}
    validate_case_source_calibration(full)
