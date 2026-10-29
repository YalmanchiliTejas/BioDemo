"""Regressions retain the upstream failure and distinguish signed heat from material."""
from pathlib import Path
import numpy as np
import pytest
from benchmarks.external_simulators.upstream import pen_run,invalid_pen_states,PenModelDomainError
from benchmarks.external_simulators.cho_real import integrate,predict,FIELDS
from benchmarks.external_simulators.treatments import common_evidence,assert_no_supplied_model

SOURCE=Path('/private/tmp/biodemo-pensimpy-source')
NATIVE=Path('/private/tmp/biodemo-audited-native')
PINNED=pytest.mark.skipif(not SOURCE.is_dir() or not NATIVE.is_dir(),reason='Pinned external simulator runtime required')

@PINNED
def test_full_batch_failure_is_rejected_before_clipping():
    with pytest.raises(PenModelDomainError) as captured:
        pen_run(SOURCE,NATIVE,seed=17,hours=230.)
    c=captured.value.context
    assert c['raw_state'][9]<0
    assert c['time_start_h']>96
    assert 'Viscosity' in str(captured.value)

@PINNED
@pytest.mark.xfail(strict=True,reason='Known upstream empirical viscosity law; uncorrected full230h model is unqualified')
def test_full_batch_physically_admissible_regression_remains_unresolved():
    result=pen_run(SOURCE,NATIVE,seed=17,hours=230.)
    assert result['is_complete_230h_batch']


def test_signed_heat_is_allowed_but_negative_material_and_viscosity_rejected():
    state=np.ones(33);state[8]=-30762.78
    assert invalid_pen_states(state)=={}
    state[9]=-.1;state[0]=-.02
    assert invalid_pen_states(state)=={'S':-.02,'Viscosity':-.1}

@PINNED
def test_seed3004_false_positive_heat_guard_is_corrected():
    r=pen_run(SOURCE,NATIVE,seed=3004,hours=96.)
    assert r['horizon_h']==96 and r['terminal']['Viscosity']>0


def test_cho_units_and_closed_growth_substrate_balance():
    # No death/maintenance, saturating G: X + Y*G is conserved in declared units.
    p=[.035,0.,.5,2.,0.]
    values=integrate(p,[.5,7.],0.,[0.,24.,48.,96.])
    assert np.allclose(values[:,0]+2*values[:,1],14.5,rtol=2e-6)
    assert np.all(values>0)


def test_cho_future_prefix_rejected_and_models_removed_from_common():
    packet={'case_id':'CH-x','simulator':'cho_real','task':'prediction','condition':'EXP001','culture':'R01','fold':0,
        'allowed_actions':['keep'],'decision_time_h':72.,'forecast_fields':list(FIELDS),'forecast_times_h':dict.fromkeys(FIELDS,96.),
        'field_units':{},'objective':'forecast','training_cultures':[],'cultivation_mode':'batch',
        'test_prefix':[{'time_h':0.,'field':FIELDS[0],'value':.5},{'time_h':0.,'field':FIELDS[1],'value':7.}],
        'cho_model':{'parameters':[.035,.001,.5,2.,.005]}}
    common=common_evidence(packet);assert_no_supplied_model(common)
    assert 'cho_model' not in common
    assert common['test_prefix']==packet['test_prefix']
    result=predict(packet)
    assert set(result)==set(FIELDS)
    packet['test_prefix'].append({'time_h':80.,'field':FIELDS[0],'value':2.})
    with pytest.raises(ValueError,match='Future'):predict(packet)
