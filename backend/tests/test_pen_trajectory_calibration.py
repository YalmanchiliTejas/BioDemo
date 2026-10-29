"""Actual ODE/fit regressions, not fixture copies of implementation."""
from pathlib import Path
import numpy as np
import pytest
from benchmarks.external_simulators.calibrated_pen import simulate,fit_source,source_residual
from benchmarks.external_simulators.challenges import pen_scenario,thinning

PATHS={'pensim':'/private/tmp/biodemo-pensimpy-source','native':'/private/tmp/biodemo-audited-native'}
PLAN={'feed_factor':1.,'air_factor':1.,'apply_after_h':60.}
pytestmark=pytest.mark.skipif(not all(Path(p).exists() for p in PATHS.values()),reason='Pinned physics runtime required')


def test_new_driver_preserves_equations_and_nominal_trajectory():
    old=pen_scenario(PATHS,0,PLAN,nominal=True)
    new=simulate(PATHS,PLAN)
    assert old['trace']==new['trace']
    assert old['audit']==new['audit']


def test_product_parameter_changes_coupled_balances_not_just_reported_output():
    old=simulate(PATHS,PLAN)
    new=simulate(PATHS,PLAN,{'production_factor':.75})
    for field in ('P','DO2','S'):
        assert not np.allclose([r['state'][field] for r in old['trace']], [r['state'][field] for r in new['trace']],rtol=1e-3)


def test_fit_recovers_omitted_production_kinetics_and_predicts_withheld_source_times():
    known={'production_factor':.75,'growth_factor':1.1,'kla_factor':1.2}
    result=simulate(PATHS,PLAN,known)
    prefix=thinning(result,72.)
    fitted=fit_source(prefix,PATHS)
    replay=simulate(PATHS,PLAN,fitted)
    for key in known:assert fitted[key]==pytest.approx(known[key],rel=.015)
    heldout=[r for r in thinning(result) if r['time_h']>72.]
    assert np.max(np.abs(source_residual(replay,heldout)))<.02
