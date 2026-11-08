"""Matched ice-only calibration for the LyoPRONTO and existing model tools."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy.optimize import least_squares
from benchmarks.lyo_study.study import (action_config, validate_packet, _pressure_mismatch, score)
from src.lifesci.lyophilization.heterogeneous import simulate as population

PIN='c6a9225a9e551ae4e7c11c1ef056b67c6204afbd'
CHECKOUT=Path(os.environ.get('LYOPRONTO_CHECKOUT','/private/tmp/lyohub-rerun-source'))


def upstream(config):
    head=subprocess.check_output(['git','-c','core.fsmonitor=false','-C',str(CHECKOUT),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-c','core.fsmonitor=false','-C',str(CHECKOUT),'status','--porcelain','--untracked-files=no'],text=True).strip()
    if head!=PIN or dirty:raise ValueError('LyoPRONTO checkout must be clean at frozen pin')
    process=subprocess.run([sys.executable,str(Path(__file__).with_name('upstream_worker.py'))],
        input=json.dumps({'checkout':str(CHECKOUT),'config':config}),text=True,capture_output=True,timeout=45,
        env={**{k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT')},
             'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','MPLCONFIGDIR':'/private/tmp/lyohub-mpl',
             'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    try:out=json.loads(process.stdout)
    except ValueError:raise ValueError('external simulator failed: '+process.stderr[-600:]) from None
    if process.returncode or out.get('error'):raise ValueError(out.get('error','external simulator failure'))
    return out


def simulate(config,arm):
    return upstream(config) if arm=='B' else population(config)


def fit(packet,arm):
    if not packet['observations']:return {'kv_scale':1.,'rp_scale':1.,'status':'nominal_pretransfer_no_receiving_measurements','nfev':0}
    if _pressure_mismatch(packet):return {'kv_scale':1.,'rp_scale':1.,'status':'invalid_observed_pressure_control','nfev':0}
    config=deepcopy(packet['config']);config['duration_h']=packet['cutoff_h']
    config['schedule']=[s for s in config['schedule'] if s['time_h']<config['duration_h']]
    obs=packet['observations'];times=[r['time_h'] for r in obs]
    def residual(x):
        c=deepcopy(config);c['equipment']['kv_scale'],c['product']['rp_scale']=x.tolist()
        run=simulate(c,arm)
        if run['numerical_status']!='completed':raise ValueError('calibration numerical failure')
        if any(v['constraint'] in ('vapor_capacity','condenser_ice_capacity') and v['first_time_h']<=max(times) for v in run['violations']):
            return np.full(len(obs),1000.)
        rows=run['trajectory']
        return (np.interp(times,[r['time_h'] for r in rows],[r['remaining_ice_kg_per_vial'] for r in rows])-
                np.array([r['remaining_ice_kg_per_vial'] for r in obs]))/1e-5
    fitted=least_squares(residual,[1.,1.],bounds=([.6,.6],[1.8,1.8]),loss='soft_l1',
        max_nfev=16,diff_step=.002,xtol=1e-5,ftol=1e-5,gtol=1e-5)
    return {'kv_scale':float(fitted.x[0]),'rp_scale':float(fitted.x[1]),'nfev':fitted.nfev,
        'status':'invalid_calibration_domain' if np.all(fitted.fun==1000.) else 'converged' if fitted.success else 'iteration_limit',
        'normalized_residual_rms':float(np.sqrt(np.mean(fitted.fun**2))),
        'objective':'Remaining-ice observations only, <=cutoff; 1e-5 kg residual scale; no thermal observable equivalence assumed',
        'interpretation':'effective fit, potentially non-identifiable; not verified causes'}


def prediction(packet,arm,action,fitted):
    config=action_config(packet,action);config['equipment']['kv_scale']=fitted['kv_scale'];config['product']['rp_scale']=fitted['rp_scale']
    run=simulate(config,arm)
    if run['numerical_status']!='completed':raise ValueError('forward numerical failure')
    cap=min((v['first_time_h'] for v in run['violations'] if v['constraint'] in ('vapor_capacity','condenser_ice_capacity')),default=None)
    thermal=min((v['first_time_h'] for v in run['violations'] if v['constraint']=='critical_temperature'),default=None)
    pressure=_pressure_mismatch(packet);invalid=cap is not None or pressure or fitted['status'].startswith('invalid')
    out={'action_id':action,'model_version':run['model_version'],'calibration':fitted,
        'completion_time_h':None if invalid else run['completion_time_h'],
        'diagnostic_completion_time_h':run['completion_time_h'],
        'thermal_warning':None if invalid and (pressure or fitted['status'].startswith('invalid') or thermal is None or (cap is not None and thermal>=cap)) else thermal is not None,
        'capacity_warning':cap is not None or pressure,'minimum_critical_margin_c':run['minimum_critical_margin_c'],
        'minimum_capacity_margin_kg_h':run['minimum_capacity_margin_kg_h'],'prediction_valid_until_h':cap,
        'measured_pressure_mismatch':pressure,'applicability':'prescribed_pressure_invalid' if invalid else 'within_declared_model_domain',
        'nominal_feasible':not invalid and thermal is None and run['completion_time_h'] is not None,
        'warnings':run['warnings'],'temperature_observable':run.get('temperature_observable','weighted population thermal node / hottest active population constraint'),
        'constraint_source':run.get('constraint_source','existing heterogeneous model'),
        'limitations':['Synthetic inputs and remaining-ice channel; not plant validation','No calibrated confidence or causal identification'],
        'trajectory':[]}
    if arm=='B':out['limitations'] += [run['mapping'],'Front temperature is not the hottest transient vial','Equipment guards are wrapper checks, not upstream capabilities']
    rows=run['trajectory'];chosen=rows[::max(1,len(rows)//18)]
    for r in chosen:
        if invalid and (pressure or cap is None or r['time_h']>=cap):continue
        out['trajectory'].append({k:r[k] for k in ('time_h','remaining_ice_kg_per_vial','chamber_pressure_pa','sublimation_kg_h')}|
            {'product_temperature_c':r.get('product_temperature_c',r.get('interface_temperature_c'))})
    return out,run


def evaluate(packet,arm):
    validate_packet(packet);fitted=fit(packet,arm);predictions={};raw={}
    for action in packet['allowed_actions']:
        if action['id']=='characterize':continue
        predictions[action['id']],raw[action['id']]=prediction(packet,arm,action['id'],fitted)
    usable=[p for p in predictions.values() if p['nominal_feasible']]
    chosen=min(usable,key=lambda p:p['completion_time_h'])['action_id'] if usable else 'characterize'
    keep=predictions['keep']
    submission={k:keep[k] for k in ('completion_time_h','thermal_warning','capacity_warning')}|{'action_id':chosen}
    return {'submission':submission,'predictions':predictions,'raw':raw}
