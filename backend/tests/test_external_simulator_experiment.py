"""Leakage/scoring contracts; fixtures are not simulator or agent evidence."""
import json
import math

import pytest

from benchmarks.external_simulators.experiment import model_prediction,score,checked,dump,sha
from benchmarks.external_simulators.run_agents import Host,aggregate
from benchmarks.external_simulators.upstream import monitor_pen
from benchmarks.external_simulators.treatments import common_evidence,assert_no_supplied_model


def packet():
    return {'allowed_actions':['keep','feed_up'],'source_calibration':{
        'product_ratio':2.,'indicator_offset':1.},'decision_time_h':80.,
        'receiving_observations':[{'time_h':80.}]}


def test_physics_tool_is_nominal_and_cannot_read_or_return_evaluator_truth(tmp_path):
    common=packet();nominal={'keep':{'product_concentration':3.,'process_indicator':4.,'objective':3.}}
    a=Host(common,nominal,'A',tmp_path/'a',10)
    b=Host(common,nominal,'B',tmp_path/'b',10)
    assert a.packet==b.packet
    assert 'error' in a.call('physical_forward_model',{'action_id':'keep'})
    value=b.call('physical_forward_model',{'action_id':'keep'})
    assert value['predictions']['product_concentration']==6.
    assert value['predictions']['process_indicator']==5.
    assert 'truth' not in value and 'score' not in value
    assert value['classification']=='nominal_model_prediction_not_observation'


def test_submission_freezes_without_any_evaluator_and_cannot_be_revised(tmp_path):
    host=Host(packet(),{},'A',tmp_path,10)
    decision={'action_id':'keep','predictions':{'product_concentration':5.,'process_indicator':8.},
              'rationale':'test fixture','uncertainty':'unknown','evidence':[]}
    assert host.call('submit_decision',decision)=={'accepted':True,'decision_frozen':True}
    assert host.call('submit_decision',{**decision,'action_id':'feed_up'})=={'error':'decision already frozen'}
    decision['predictions']['product_concentration']=999.
    assert host.submission['predictions']['product_concentration']==5.


@pytest.mark.parametrize('bad',[math.nan,math.inf,-1.,True,'5'])
def test_invalid_predictions_never_become_successes(tmp_path,bad):
    host=Host(packet(),{},'A',tmp_path,10)
    assert 'error' in host.call('submit_decision',{'action_id':'keep',
        'predictions':{'product_concentration':bad,'process_indicator':1.},
        'rationale':'fixture','uncertainty':'fixture'})
    assert host.submission is None


def test_forecasts_are_scored_against_keep_even_if_action_differs():
    truth={'baseline':{'product_concentration':10.,'process_indicator':5.,'objective':10.},
           'actions':{'keep':{'objective':10.},'feed_up':{'objective':12.}}}
    result=score(packet(),truth,{'action_id':'feed_up','predictions':{'product_concentration':10.,'process_indicator':5.}})
    assert result['prediction_errors']['product_concentration']['absolute_error']==0
    assert result['objective_change_percent']==20.
    assert result['finite_grid_regret']==0
    assert result['real_batches_saved'] is None


def test_corrupt_frozen_inputs_fail_closed(tmp_path):
    dump(tmp_path/'public/case/packet.json',packet())
    dump(tmp_path/'manifest.json',{'files_sha256':{'public/case/packet.json':sha(tmp_path/'public/case/packet.json')}})
    assert checked(tmp_path,'public/case/packet.json')==packet()
    dump(tmp_path/'public/case/packet.json',{'leaked_future':'answer'})
    with pytest.raises(ValueError,match='checksum'):checked(tmp_path,'public/case/packet.json')


def test_failed_attempts_remain_in_denominators():
    row={'case_id':'EX-1','simulator':'mab','task':'prediction','arm':'A',
         'score':None,'wall_seconds':120.,'common_input_sha256':'x','capability_audit':None}
    summary=aggregate([row],{})
    assert summary['groups']['mab']['prediction']['A']['failed']==1
    assert summary['groups']['mab']['prediction']['A']['mean_product_relative_error'] is None
    assert summary['completed']==0
    assert not summary['pair_inputs_match']


def test_raw_solver_invalid_state_is_rejected_before_upstream_flooring():
    import numpy as np
    from types import SimpleNamespace
    initial=np.ones(33);initial[4]=58000.
    raw=initial.copy();raw[9]=-.2
    native=SimpleNamespace(integrate=lambda *_:None,integrate_checked=lambda *_:raw)
    module=SimpleNamespace(fastodeint=native)
    with monitor_pen(module):
        with pytest.raises(ValueError,match='raw physical state invalid'):
            native.integrate(initial,np.ones(31),0.,.205,.005)


def test_no_model_baseline_preserves_evidence_but_excludes_equations_and_calibration():
    full={'case_id':'fixture','simulator':'pensim','task':'transfer',
          'decision_time_h':0.,'source_history':[{'time_h':96.,'state':{'P':5.}}],
          'receiving_observations':[],'allowed_actions':['keep'],
          'nominal_model_equations':'SECRET_MODEL_EQUATIONS',
          'source_calibration':{'product_ratio':1.0314159},
          'nominal_model_limitations':['model internals'],
          'receiving_specifications':{'horizon_h':96.,
              'receiving_nominal_aeration_factor_vs_source':.9,
              'maximum_allowed_aeration_factor':.909,
              'nominal_equation_initial_state':['SECRET_STATE'],
              'nominal_equation_initial_parameters':['SECRET_PARAMETERS'],
              'nominal_controller_equations':'SECRET_CONTROLLER',
              'nominal_recipe':{'Fg':[{'time_h':0.,'value':30.}],
                                'Fs':[{'time_h':0.,'value':8.}]}}}
    common=common_evidence(full)
    assert assert_no_supplied_model(common)
    assert common['source_history']==full['source_history']
    assert common['receiving_observations']==[]
    assert common['source_operating_schedule']['Fg'][0]['value']==30.
    assert common['receiving_specifications']['planned_operating_schedule']['Fg'][0]['value']==27.
    encoded=json.dumps(common)
    assert 'SECRET_' not in encoded and 'source_calibration' not in encoded
    assert '1.0314159' not in encoded


def test_guard_rejects_nested_model_information_in_no_model_prompt():
    with pytest.raises(ValueError,match='Model information'):
        assert_no_supplied_model({'receiving_specifications':{'nominal_controller_equations':'leak'}})
