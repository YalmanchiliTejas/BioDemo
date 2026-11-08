"""Meaningful integration checks for external solver units, endpoint and authority."""
from copy import deepcopy
import json
import math
from pathlib import Path
import pytest

from benchmarks.lyohub_study import models
from benchmarks.lyohub_study.upstream_worker import inputs, RP_SI, TORR_PA
from benchmarks.lyo_study.study import validate_packet, action_config, score
from src.lifesci.lyophilization.case import receiving_config
from src.lifesci.lyophilization.model import geometry


def packet():
    c=receiving_config(shelf_c=-30.,load_vials=4000,capacity_kg_h=2.)
    c['populations']=[{'weight':.8,'kv_scale':.95,'rp_scale':1.05},{'weight':.2,'kv_scale':1.2,'rp_scale':.9}]
    c['thermal']={'vial_heat_capacity_j_k':3.,'initial_equilibrium':True}
    return {'case_id':'unit','task':'pretransfer','cutoff_h':0.,'config':c,'observations':[],
        'allowed_actions':[{'id':'keep','shelf_temperature_c':None},{'id':'cool','shelf_temperature_c':-32.},{'id':'characterize','shelf_temperature_c':None}]}


def test_si_conversion_preserves_pressure_dependent_kv_rp_and_frozen_height():
    c=packet()['config'];v,p,h,pc,ts,ice=inputs(c);ap,av,height=geometry(c['product'])
    for pressure in (5.,8.,20.):
        torr=pressure/TORR_PA
        upstream=(h['KC']+h['KP']*torr/(1+h['KD']*torr))*41840
        native=c['equipment']['kv_a_w_m2_k']+c['equipment']['kv_b_w_m2_k_pa']*pressure/(1+c['equipment']['kv_c_per_pa']*pressure)
        assert upstream==pytest.approx(native)
    for cake_m in (0.,.002,.006):
        cm=cake_m*100
        upstream=(p['R0']+p['A1']*cm/(1+p['A2']*cm))*RP_SI
        product=c['product'];native=product['rp0_m_s']+product['rp1_per_s']*cake_m/(1+product['rp2_per_m']*cake_m)
        assert upstream==pytest.approx(native)
    upstream_height=v['Vfill']/(v['Ap']*.918)*(1-p['cSolid']*(1-.918)/1.5)*.01
    assert upstream_height==pytest.approx(height)
    native_ice=height*918*c['product']['porosity']*ap
    assert ice/native_ice==pytest.approx(1.0085179425427158,rel=1e-7)


def test_real_upstream_terminal_event_and_native_mass_balance():
    c=packet()['config'];r=models.upstream(c)
    assert r['completion_time_h'] is not None
    rows=r['trajectory'];assert rows[-1]['time_h']==r['completion_time_h']
    assert rows[-1]['remaining_ice_kg_per_vial']<1e-10
    assert rows[0]['remaining_ice_kg_per_vial']==r['initial_ice_kg_per_vial']
    # Trapezoidal flux on upstream solver nodes should recover native ice to a few percent.
    import numpy as np
    removed=np.trapezoid([r['sublimation_kg_h']/c['load_vials'] for r in rows],[r['time_h'] for r in rows])
    assert removed==pytest.approx(r['initial_ice_kg_per_vial'],rel=.03)


def test_unfinished_upstream_is_not_completed_at_horizon():
    c=packet()['config'];c['duration_h']=.1
    r=models.upstream(c)
    assert r['completion_time_h'] is None
    assert r['trajectory'][-1]['remaining_ice_kg_per_vial']>0


def test_shared_constraint_gate_censors_capacity_extrapolation():
    p=packet();p['config']['equipment']['vapor_capacity_kg_h']=.001
    fitted={'kv_scale':1.,'rp_scale':1.,'status':'nominal','nfev':0}
    for arm in ('B','C'):
        out,_=models.prediction(p,arm,'keep',fitted)
        assert out['capacity_warning']
        assert out['completion_time_h'] is None
        assert not out['nominal_feasible']
        assert out['applicability']=='prescribed_pressure_invalid'
        assert out['thermal_warning'] is None


def test_future_observation_denied_and_action_preserves_the_past():
    p=packet();p['cutoff_h']=6.;p['observations']=[{'time_h':7.,'remaining_ice_kg_per_vial':.001}]
    with pytest.raises(ValueError,match='cutoff'):models.evaluate(p,'B')
    p['observations']=[]
    c=action_config(p,'cool')
    assert c['schedule'][0]==p['config']['schedule'][0]
    assert c['schedule'][1]['time_h']==6
    assert c['schedule'][1]['shelf_temperature_c']==-32
    for arm in ('B','C'):
        assert models.fit(p,arm)['kv_scale']==1.


def test_characterize_and_execution_failure_are_not_feasible_operating_choices():
    outcomes={'keep':{'completion_time_h':20.,'first_capacity_h':None,'first_critical_h':None}}
    base={'completion_time_h':20.,'thermal_warning':False,'capacity_warning':False}
    abstain=score({**base,'action_id':'characterize'},outcomes,4000)
    failed=score(None,outcomes,4000)
    assert not abstain['selected_feasible'] and abstain['throughput_vials_h']==0
    assert abstain['abstained_with_hindsight_feasible_action']
    assert not failed['execution_completed'] and failed['thermal']=='execution_failed'
