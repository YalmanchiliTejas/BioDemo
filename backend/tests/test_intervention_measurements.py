import numpy as np
import pytest
from benchmarks.external_simulators.upstream import MAB_NAMES
from benchmarks.interventions.smpl_observations import measurements,initial_ensemble


def trace():
 state=dict.fromkeys(MAB_NAMES,10.);state['temperature']=36.8;state['viable_cells_reactor']=8.
 return [{'time_h':t,'state':state.copy()} for t in [0.,1.,2.,4.,12.,24.]]


def test_sparse_measurements_never_reveal_separator_or_delayed_titer():
 early=measurements(trace(),2.,seed=1)
 assert not any(r['field']=='mAb_reactor' for r in early)
 assert not any(r['field'].endswith('_separator') and not r['field'].startswith('volume') for r in early)
 later=measurements(trace(),4.,seed=1)
 assert any(r['field']=='mAb_reactor' for r in later)
 assert all(r['available_at_h']<=4. for r in later)
 assert all(r in later for r in early)


def test_latent_initialization_has_uncertainty_without_true_receiver_state():
 prior=[10.]*17;prior[16]=36.8
 observed=measurements(trace(),4.,seed=2)
 r=initial_ensemble(prior,observed,decision_h=4.,seed=3)
 a=np.array(r['initial_state_members'])
 assert np.ptp(a[:,8])>0 # latent separator VCD remains uncertain
 assert np.all(a[:,1]>=a[:,0])
 assert len(r['parameter_members'])==16
 with pytest.raises(ValueError,match='Future assay'):initial_ensemble(prior,observed,decision_h=2.,seed=3)


def test_uncertain_smpl_identity_matches_original_and_preserves_inventory_balance():
 from pathlib import Path
 from benchmarks.interventions.smpl_model import uncertain_model,evolve
 from benchmarks.external_simulators.upstream import read_mab,mab_run
 source=Path('/private/tmp/biodemo-smpl-source')
 if not source.exists():pytest.skip('Pinned source required')
 original,x,u=read_mab(source);pars={'growth_factor':1.,'death_factor':1.,'production_factor':1.}
 model,_,_=uncertain_model(source,pars)
 assert np.allclose(model.xdot(x,u),original.xdot(x,u),rtol=1e-12)
 changed=dict(pars,production_factor=.9);model,_,_=uncertain_model(source,changed)
 dx=np.asarray(model.xdot(x,u),dtype=float)
 inventory_rate=dx[6]*x[7]+x[6]*dx[7]+dx[14]*x[15]+x[14]*dx[15]
 assert inventory_rate==pytest.approx(.9*(6.59e-10/60)*x[0]*x[7]-x[14]*u[3],rel=1e-10)
 a=evolve(source,x,u,2.,pars);b=mab_run(source,initial=x,command=u,hours=2.)
 assert a['external_harvest_mg']==pytest.approx(b['product_mass_mg'],rel=1e-6)


def test_forecast_interface_returns_aggregates_without_private_initial_states():
 from pathlib import Path
 from benchmarks.interventions.smpl_model import forecast_from_measurements
 from benchmarks.external_simulators.upstream import read_mab
 source=Path('/private/tmp/biodemo-smpl-source')
 if not source.exists():pytest.skip('Pinned source required')
 _,prior,u=read_mab(source)
 r=forecast_from_measurements(source,prior,[],u,decision_h=0.,members=3,hours=2.)
 assert r['members']==3 and r['admitted_members']==3
 assert 'initial_state_members' not in r and 'parameter_members' not in r
 assert r['forecasts']['external_harvest_mg']['range'][1]>r['forecasts']['external_harvest_mg']['range'][0]
