"""Partial SMPL measurement contract; no complete true-state model restart.

Exact clocks/noise are declared synthetic benchmark assumptions, with sources
in docs/research/smpl-partial-observation-benchmark.md. Not plant validation.
"""
from copy import deepcopy
import hashlib
import math
import numpy as np
from benchmarks.external_simulators.upstream import MAB_NAMES

METABOLITES=['glucose_reactor','glutamine_reactor','lactate_reactor','ammonia_reactor']
ONLINE=['temperature','volume_reactor','volume_separator']


def noise(seed,field,t):
    key=f'{seed}/{field}/{t:.6f}'.encode();return np.random.default_rng(int(hashlib.sha256(key).hexdigest()[:16],16))


def measurements(trace,cutoff_h,*,seed,cadence_h=24.):
    if cadence_h not in (12.,24.):raise ValueError('Use frozen assay cadence')
    rows=[]
    for row in trace:
        t=row['time_h'];state=row['state']
        if abs(t-round(t))<1e-8 and t<=cutoff_h+1e-8:
            for field in ONLINE:
                sigma=.1 if field=='temperature' else .01*state[field]
                value=state[field]+float(noise(seed,field,t).normal(0,sigma))
                rows.append({'field':field,'value':value,'sample_time_h':t,'available_at_h':t,
                    'unit':'degC' if field=='temperature' else 'L','kind':'simulated_online_sensor' if field=='temperature' else 'derived_holdup_estimate'})
        if abs(t/cadence_h-round(t/cadence_h))<1e-8:
            for field in [*METABOLITES,'viable_cells_reactor','mAb_reactor','viability_reactor']:
                delay=4. if field=='mAb_reactor' else 2.
                if t+delay>cutoff_h+1e-8:continue
                if field=='viability_reactor':
                    value=float(np.clip(100*state['viable_cells_reactor']/state['total_cells_reactor']+noise(seed,field,t).normal(0,2.),.1,100.));unit='%'
                else:
                    cv=.1 if field=='viable_cells_reactor' else .05;s=math.sqrt(math.log1p(cv*cv))
                    value=state[field]*float(noise(seed,field,t).lognormal(-s*s/2,s))
                    unit='cells/L' if field=='viable_cells_reactor' else 'mg/L' if field=='mAb_reactor' else 'mM'
                rows.append({'field':field,'value':value,'sample_time_h':t,'available_at_h':t+delay,'unit':unit,'kind':'simulated_delayed_assay'})
    return sorted(rows,key=lambda r:(r['available_at_h'],r['field']))


def initial_ensemble(source_prior,observed,*,decision_h,seed,members=16):
    """Infer initial-state uncertainty from t0 assays + source-only prior.

    Later observations are not silently interpreted as exact t0 states. A full
    observer can condition later records after their clocks are propagated.
    """
    if any(r['available_at_h']>decision_h+1e-8 for r in observed):raise ValueError('Future assay in initialization')
    if len(source_prior)!=17:raise ValueError('Source-only17-state prior required')
    initial={r['field']:r for r in observed if abs(r['sample_time_h'])<1e-8}
    rng=np.random.default_rng(seed);draws=[]
    for _ in range(members):
        state=np.array(source_prior,dtype=float)*rng.uniform(.9,1.1,17)
        state[16]=source_prior[16]+rng.normal(0,.2)
        for i,field in enumerate(MAB_NAMES):
            if field in initial:
                value=initial[field]['value'];cv=.1 if i==0 else .01 if i in (7,15) else .05
                state[i]=value+rng.normal(0,.1) if i==16 else value*rng.uniform(1-cv,1+cv)
        if 'viability_reactor' in initial:state[1]=state[0]/max(.001,min(1.,initial['viability_reactor']['value']/100))
        state[1]=max(state[0],state[1]);state[9]=max(state[8],state[9])
        if np.any(state[:16]<=0) or not 32<=state[16]<=39:raise ValueError('Nonphysical uncertain initial state')
        draws.append(state.tolist())
    return {'initial_state_members':draws,'parameter_members':[{'growth_factor':float(rng.uniform(.9,1.1)),
        'production_factor':float(rng.uniform(.9,1.1)),'death_factor':float(rng.uniform(.8,1.2))} for _ in range(members)],
        'basis':'Source-only prior plus available initial assays; separator concentrations latent. Ranges are declared sensitivity assumptions, not posterior probabilities.',
        'measurements_used':[deepcopy(r) for r in initial.values()]}
