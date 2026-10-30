from benchmarks.interventions.pensim import outcomes,optimizer,stop_classification


def fixture(stopped=False):
 return {'action_id':'stop' if stopped else 'keep','stopped':stopped,'decision_h':1.,'trace':[{'time_h':1.,'state':{'DO2':1.,'P':2.,'V':100.}},{'time_h':1.2,'state':{'DO2':3.,'P':2.,'V':100.}}]}


def test_mass_and_concentration_are_separate_and_stop_has_zero_production():
 run=fixture();a=outcomes(run);run['trace'][-1]['state'].update(P=1.,V=200.);b=outcomes(run)
 assert a['product_mass_kg']==b['product_mass_kg']==.2
 assert a['terminal_concentration_g_l']!=b['terminal_concentration_g_l']
 assert outcomes(fixture(True))['product_mass_kg']==0


def test_intervention_does_not_erase_earlier_violation():
 r=outcomes(fixture());assert r['post_decision_feasible']
 assert r['whole_process']['below_limit_h']>.0
 assert r['post_decision']['below_limit_h']==0


def test_optimizer_avoids_infeasible_high_product_and_marks_unnecessary_stop():
 good={'post_decision_feasible':True,'product_mass_kg':1.}
 bad={'post_decision_feasible':False,'product_mass_kg':10.}
 actions={'keep':good,'rich':bad,'stop':bad}
 assert optimizer(actions)=='keep'
 assert stop_classification('stop',actions)['unnecessary_stop']
 assert optimizer({'keep':bad,'stop':bad})=='stop'


def test_observation_clock_hides_unavailable_assays_and_substrate():
 from benchmarks.interventions.pensim import observations
 run={'trace':[{'time_h':12.,'state':{'DO2':3.,'P':2.,'S':5.}}, {'time_h':16.,'state':{'DO2':4.,'P':3.,'S':6.}}]}
 early=observations(run,12.,noise_seed=1)
 assert all(r['available_at_h']<=12. for r in early)
 assert {r['field'] for r in early}=={'DO2'}
 later=observations(run,16.,noise_seed=1)
 assay=next(r for r in later if r['field']=='P')
 assert assay['time_h']==12. and assay['available_at_h']==16.
 assert not any(r['field']=='S' for r in later)


def test_model_update_rejects_future_measurements_before_running_solver():
 import pytest
 from benchmarks.interventions.model import ReceivingModel
 m=ReceivingModel({}, {'factors':{}})
 with pytest.raises(ValueError,match='Future observation'):
  m.update({'decision_time_h':52.,'receiving_observations':[{'time_h':48.,'available_at_h':53.,'field':'P','value':1.}]})
