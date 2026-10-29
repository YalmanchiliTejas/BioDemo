"""Decision validity, withheld forecasts and evidence boundaries for new scenarios."""
from copy import deepcopy
from pathlib import Path
import pytest
from benchmarks.external_simulators.challenges import common,score,values,targets,evaluate,action_plans
from benchmarks.external_simulators.treatments import assert_no_supplied_model


def fixture():
    packet={'experiment_version':'operating-challenges-20261028-v1','case_id':'NC-test','simulator':'pensim','task':'outcome',
        'forecast_fields':['product_concentration','process_indicator'],'allowed_actions':['keep','rich','abstain'],
        'source_history':[{'time_h':96,'state':{'P':5.}}],'receiving_observations':[{'time_h':60,'state':{'P':3.}}],
        'source_calibration':{'product_ratio':1.23456},'evaluator_seed':999,'hidden_ranking':['rich']}
    truth={'forecasts':{'product_concentration':10.,'process_indicator':5.},'normalization_scales':{'product_concentration':5.,'process_indicator':10.},
        'actions':{'keep':{'feasible':True,'qualified':True,'objective':10.},'rich':{'feasible':False,'qualified':False,'objective':100.,'violations':['oxygen_floor_model_domain']},
                   'abstain':{'feasible':True,'qualified':True,'objective':0.}}}
    submission={'action_id':'rich','predictions':{'product_concentration':10.,'process_indicator':5.}}
    return packet,truth,submission


def test_qualified_product_cannot_be_increased_by_exploiting_oxygen_floor():
    packet,truth,submission=fixture();s=score(packet,truth,submission)
    assert s['decision_score']==0 and s['invalid_decision']
    assert not s['objective_change_is_qualified']
    assert s['prediction_errors']['product_concentration']['absolute_error']==0
    assert s['finite_grid_regret']==10


def test_abstention_is_rewarded_only_when_no_process_action_is_feasible():
    packet,truth,submission=fixture();submission['action_id']='abstain'
    assert score(packet,truth,submission)['decision_score']==0
    truth['actions']['keep']['feasible']=False
    result=score(packet,truth,submission)
    assert result['correct_abstention'] and result['decision_score']==1


def test_common_projection_preserves_raw_evidence_without_hidden_physics_or_targets():
    full,_,_=fixture();projected=common(full)
    assert projected['source_history']==full['source_history']
    assert projected['receiving_observations']==full['receiving_observations']
    assert 'source_calibration' not in projected and 'evaluator_seed' not in projected and 'hidden_ranking' not in projected
    assert_no_supplied_model(projected)


def test_timecourse_target_requires_actual_requested_output_clock():
    ts={'product_concentration':{'state':'P','time_h':96.}}
    assert values({'trace':[{'time_h':96.,'state':{'P':3.}}]},ts)=={'product_concentration':3.}
    with pytest.raises(ValueError,match='exact simulator'):values({'trace':[{'time_h':95.,'state':{'P':3.}}]},ts)
    assert len(targets('pensim'))==6 and len(targets('mab'))==6


def test_resource_violation_is_not_compensated_by_product():
    r={'trace':[{'time_h':96.,'state':{'DO2':10.}}], 'audit':{'dissolved_oxygen_floor_events':0},
       'resources':{'feed_factor':1.15,'air_factor':1.15},'objective':999.}
    s=evaluate('pensim',r,{'constraint_start_h':60.,'maximum_feed_factor':1.,'maximum_air_factor':1.15,'minimum_do_mg_l':2.})
    assert s['qualified'] and not s['feasible'] and s['violations']==['feed_delivery_limit']


def test_multi_horizon_errors_all_use_keep_even_for_an_alternative_action():
    packet,truth,submission=fixture()
    packet['forecast_fields'].append('product_at_64h');truth['forecasts']['product_at_64h']=3.;truth['normalization_scales']['product_at_64h']=2.
    submission['predictions']['product_at_64h']=4.
    s=score(packet,truth,submission)
    assert s['prediction_errors']['product_at_64h']['normalized_absolute_error']==.5


def test_case_bootstrap_uses_paired_case_values_and_correct_effect_direction():
    from benchmarks.external_simulators.challenge_report import boot
    forecast=boot([2.,4.,6.],[1.,2.,3.],ratio=True)
    assert forecast['effect']==.5
    assert forecast['interval95']==[.5,.5]
    decisions=boot([.2,.3,.4],[.3,.4,.5])
    assert decisions['effect']==pytest.approx(.1)
    assert decisions['case_clusters']==3
    assert decisions['interval95']==pytest.approx([.1,.1])
