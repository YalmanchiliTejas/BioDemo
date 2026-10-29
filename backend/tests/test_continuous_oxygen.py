"""Reject invalid raw oxygen; preserve actual nonnegative ODE evolution."""
from types import SimpleNamespace
import numpy as np
import pytest
from benchmarks.external_simulators.oxygen import preserve_oxygen


def test_positive_low_oxygen_is_preserved_and_audit_retains_the_event():
    solver=lambda *a:np.array([3.,1.992250509720407])
    module=SimpleNamespace(fastodeint=SimpleNamespace(integrate=solver))
    state=SimpleNamespace(DO2=SimpleNamespace(y=np.array([1.])))
    audit={'dissolved_oxygen_floor_events':1}
    with preserve_oxygen(module,audit,True) as restore:
        module.fastodeint.integrate();restore(state,1)
    assert state.DO2.y[0]==1.992250509720407
    assert audit['raw_low_oxygen_intervals']==1
    assert audit['dissolved_oxygen_floor_events']==0
    assert len(audit['prevented_upstream_resets'])==1
    assert module.fastodeint.integrate is solver


@pytest.mark.parametrize('oxygen',[-1e-8,float('nan')])
def test_invalid_raw_oxygen_is_rejected_not_clipped(oxygen):
    module=SimpleNamespace(fastodeint=SimpleNamespace(integrate=lambda *a:np.array([3.,oxygen])))
    with pytest.raises(ValueError,match='nonnegative finite'):
        with preserve_oxygen(module,{'dissolved_oxygen_floor_events':0},True):module.fastodeint.integrate()


def test_actual_source_retains_raw_oxygen_and_agrees_with_independent_solver():
    from pathlib import Path
    if not Path('/private/tmp/biodemo-audited-native').exists():pytest.skip('Pinned runtime required')
    from benchmarks.external_simulators.challenges import pen_scenario,admit_source
    from benchmarks.external_simulators.oxygen import run_continuous
    paths={'pensim':'/private/tmp/biodemo-pensimpy-source','native':'/private/tmp/biodemo-audited-native'}
    plan={'feed_factor':1.,'air_factor':1.15,'apply_after_h':60.}
    corrected=run_continuous(paths,pen_scenario,paths,9014,plan)
    assert corrected['audit']['raw_low_oxygen_intervals']>0
    event=corrected['audit']['prevented_upstream_resets'][0]
    row=next(r for r in corrected['trace'] if r['time_h']==event['time_h'])
    assert row['state']['DO2']==event['raw_DO_mg_l']
    assert row['state']['DO2']==pytest.approx(1.992250509720407,rel=1e-9)
    admit_source(corrected)
    independent=run_continuous(paths,pen_scenario,paths,9014,plan,solver='python',rtol=1e-8)
    for field in ('P','DO2','S'):
        a=np.array([r['state'][field] for r in corrected['trace']]);b=np.array([r['state'][field] for r in independent['trace']])
        assert np.max(np.abs(a-b)/np.maximum(np.abs(a),.01))<.005
    # A later ordinary legacy call still has its original reset semantics.
    legacy=pen_scenario(paths,9014,plan)
    with pytest.raises(ValueError,match='oxygen-floor'):admit_source(legacy)


def test_low_oxygen_remains_an_operating_constraint_violation_after_reset_fix():
    from benchmarks.external_simulators.challenges import evaluate
    result={'trace':[{'time_h':64.,'state':{'DO2':1.9}}],'resources':{'feed_factor':1.,'air_factor':1.},'objective':5.,'audit':{'dissolved_oxygen_floor_events':0,'raw_low_oxygen_intervals':1}}
    score=evaluate('pensim',result,{'constraint_start_h':60.,'maximum_feed_factor':1.15,'maximum_air_factor':1.15,'minimum_do_mg_l':2.})
    assert score['qualified'] and not score['feasible']
    assert 'dissolved_oxygen_study_limit' in score['violations']
