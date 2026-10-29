"""Prevent stale initial-state corrections and mismatched calibration evidence."""
from copy import deepcopy
import hashlib,json
import pytest
from benchmarks.external_simulators.challenges import response
from benchmarks.external_simulators.upstream import MAB_NAMES


def source_hash(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def mab_fixture():
    state=dict.fromkeys(MAB_NAMES,1.)
    return {'simulator':'mab','forecast_contract_version':2,
        'model_execution_context':{'initialization':'observed_source_state_shared_with_receiver','residual_origin':'nominal_initialization_difference'},
        'source_history':[{'time_h':0.,'state':state}],
        'source_calibration':{'product_ratio':1.2,'indicator_offset':10.},
        'forecast_targets':{'product_concentration':{'state':'mAb_reactor','time_h':24.},'process_indicator':{'state':'viable_cells_reactor','time_h':24.}},
        'constraints':{'constraint_start_h':0.,'maximum_flow_factor':1.,'maximum_nutrient_input_relative_source':1.,'minimum_viable_cells_l':80.}},


def result():
    return {'trace':[{'time_h':0.,'state':dict.fromkeys(MAB_NAMES,1.)},{'time_h':24.,'state':{'mAb_reactor':50.,'viable_cells_reactor':100.,'temperature':36.8}}],
        'resources':{'flow_factor':1.,'nutrient_factor':1.,'nutrient_input_relative_source':1.},'objective':123.,'audit':{'dissolved_oxygen_floor_events':0}}


def test_observed_initial_state_forecast_does_not_import_nominal_initialization_bias():
    packet=mab_fixture()[0]
    r=response(packet,'keep',result())
    assert r['predictions']=={'product_concentration':50.,'process_indicator':100.}
    assert not r['calibration']['applied']


def test_legacy_study_replays_without_silently_rewriting_its_predictions():
    packet=mab_fixture()[0];packet.pop('forecast_contract_version')
    assert response(packet,'keep',result())['predictions']=={'product_concentration':60.,'process_indicator':110.}


def test_observed_state_policy_requires_the_declared_complete_observed_state():
    packet=mab_fixture()[0];packet['source_history'][0]['state'].pop('glucose_reactor')
    with pytest.raises(ValueError,match='initial state'):response(packet,'keep',result())


def test_new_contract_rejects_calibration_from_a_different_completed_source():
    packet=mab_fixture()[0];packet['simulator']='pensim'
    packet['source_calibration'].update(source_history_sha256=source_hash([{'different':'batch'}]),evidence_scope='completed_source_before_receiving')
    with pytest.raises(ValueError,match='source calibration'):response(packet,'keep',result())


def test_observed_state_policy_rejects_a_model_that_actually_started_elsewhere():
    packet=mab_fixture()[0];r=result();r['trace'][0]['state']['glucose_reactor']=2.
    with pytest.raises(ValueError,match='initial state differs'):response(packet,'keep',r)


def test_explicit_packet_context_separates_source_plan_from_receiving_keep():
    from benchmarks.external_simulators.challenges import common
    from benchmarks.external_simulators.treatments import assert_no_supplied_model
    packet=mab_fixture()[0]
    packet.update(source_operating_plan={'flow_factor':1.,'nutrient_factor':1.,'apply_after_h':0.},
        action_plans={'keep':{'flow_factor':.8,'nutrient_factor':.9,'apply_after_h':6.}},
        operating_specification={'prechange_flow_factor':.9,'prechange_nutrient_factor':1.})
    public=common(packet);context=public['operating_plan_context']
    assert context['completed_source_plan']['flow_factor']==1.
    assert context['receiving_KEEP_plan']['flow_factor']==.8
    assert context['receiving_before_change']['prechange_flow_factor']==.9
    assert context['forecast_plan_required']=='keep'
    assert 'source_calibration' not in public
    assert_no_supplied_model(public)


def test_case_source_calibration_accepts_matching_provenance_without_parameter_tuning():
    packet=mab_fixture()[0];packet['simulator']='pensim'
    packet['source_history']=[{'time_h':96.,'state':{'P':5.,'DO2':10.}}]
    packet['forecast_targets']={'product_concentration':{'state':'P','time_h':96.},'process_indicator':{'state':'DO2','time_h':96.}}
    packet['source_calibration'].update(source_history_sha256=source_hash(packet['source_history']),evidence_scope='completed_source_before_receiving',product_ratio=1.,indicator_offset=0.)
    packet['constraints']={'constraint_start_h':60.,'maximum_feed_factor':1.15,'maximum_air_factor':1.15,'minimum_do_mg_l':2.}
    r={'trace':[{'time_h':96.,'state':{'P':5.,'DO2':10.}}],'resources':{'feed_factor':1.,'air_factor':1.},'objective':5.,'audit':{'dissolved_oxygen_floor_events':0}}
    answer=response(packet,'keep',r)
    assert answer['predictions']=={'product_concentration':5.,'process_indicator':10.}
    assert answer['calibration']['applied']
