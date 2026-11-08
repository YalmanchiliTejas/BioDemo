"""JSON-only external LyoPRONTO execution. No upstream source is vendored.

Run with an unmodified checkout of the pinned GPL-3.0-or-later dependency.
Inputs contain public characterization only; outputs are solver trajectories.
"""
from copy import deepcopy
import contextlib
import io
import json
import math
from pathlib import Path
import sys
import warnings

import numpy as np
from scipy.optimize import least_squares

PIN = 'c6a9225a9e551ae4e7c11c1ef056b67c6204afbd'
TORR_PA = 133.322368
RP_SI = 47996.05248


def inputs(config):
    p,e=config['product'],config['equipment']
    ap=math.pi*p['inner_diameter_m']**2/4
    av=math.pi*p['outer_diameter_m']**2/4
    # Equivalent frozen height under upstream's fixed solute-density assumption.
    # Native initial ice differs by ~0.85%; retain it, never silently rescale flux.
    csolid=1.5*(1-p['porosity'])
    vial={'Av':av*1e4,'Ap':ap*1e4,'Vfill':p['fill_m3']*1e6}
    product={'cSolid':csolid,'R0':p['rp0_m_s']*p.get('rp_scale',1)/RP_SI,
             'A1':p['rp1_per_s']*.01*p.get('rp_scale',1)/RP_SI,'A2':p['rp2_per_m']*.01}
    scale=e.get('kv_scale',1)
    ht={'KC':e['kv_a_w_m2_k']*scale/41840,
        'KP':e['kv_b_w_m2_k_pa']*scale*TORR_PA/41840,'KD':e['kv_c_per_pa']*TORR_PA}
    knots=config['schedule'];end=config['duration_h']
    durations=[((knots[i+1]['time_h'] if i+1<len(knots) else end)-s['time_h'])*60 for i,s in enumerate(knots)]
    def schedule(field,factor=1):
        return {'setpt':[s[field]*factor for s in knots], 'dt_setpt':durations,'ramp_rate':1e6}
    initial_ice_kg=vial['Vfill']*(1-csolid/1.5)*.001
    return vial,product,ht,schedule('chamber_pressure_pa',1/TORR_PA),schedule('shelf_temperature_c'),initial_ice_kg


def simulate(config):
    from lyopronto import calc_knownRp
    vial,product,ht,pressure,shelf,ice=inputs(config)
    with warnings.catch_warnings(record=True) as caught,contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter('always')
        out=calc_knownRp.dry(vial,product,ht,pressure,shelf,dt=None)
    if out.ndim!=2 or out.shape[1]!=7 or not np.isfinite(out).all():
        raise ValueError('nonfinite or malformed upstream output')
    # Keep solver nodes INCLUDING the terminal drying event.
    completion=float(out[-1,0]) if out[-1,6]>=100-1e-5 else None
    p,e=config['product'],config['equipment'];n=config['load_vials']
    ap=math.pi*p['inner_diameter_m']**2/4
    rows=[]
    for v in out:
        remaining=max(0.,ice*(1-v[6]/100))
        rate=float(v[5])*ap*n
        rows.append({'time_h':float(v[0]),'interface_temperature_c':float(v[1]),
            'bottom_temperature_c':float(v[2]),'product_temperature_c':float(v[1]),
            'remaining_ice_kg_per_vial':remaining,'chamber_pressure_pa':float(v[4])*TORR_PA/1000,
            'sublimation_kg_h':rate,'critical_margin_c':p['critical_temperature_c']-float(v[1]),
            'capacity_margin_kg_h':e['vapor_capacity_kg_h']-rate,
            'condenser_margin_kg':e['condenser_capacity_kg']-(ice-remaining)*n})
    violations=[]
    for key,name in [('critical_margin_c','critical_temperature'),('capacity_margin_kg_h','vapor_capacity'),('condenser_margin_kg','condenser_ice_capacity')]:
        bad=[r for r in rows if r[key]<=0]
        if bad:violations.append({'constraint':name,'first_time_h':bad[0]['time_h']})
    return {'model_version':'LyoPRONTO-1.2.0@'+PIN,'trajectory':rows,'completion_time_h':completion,
        'numerical_status':'completed','violations':violations,
        'minimum_critical_margin_c':min(r['critical_margin_c'] for r in rows),
        'minimum_capacity_margin_kg_h':min(r['capacity_margin_kg_h'] for r in rows),
        'warnings':list(dict.fromkeys(str(w.message) for w in caught)),
        'upstream_input':{'vial':vial,'product':product,'ht':ht,'Pchamber':pressure,'Tshelf':shelf},
        'initial_ice_kg_per_vial':ice,
        'mapping':'cSolid=1.5*(1-porosity) g/mL preserves initial frozen height; native ice mass retained; 1e6-unit/min ramps approximate steps',
        'temperature_observable':'sublimation front; not weighted transient thermometry or hottest vial',
        'constraint_source':'BioDemo wrapper; knownRp has no equipment-capacity enforcement'}


def execute(request):
    checkout=Path(request['checkout']).resolve()
    sys.path.insert(0,str(checkout))
    return simulate(request['config'])


if __name__=='__main__':
    try:
        result=execute(json.loads(sys.stdin.read()))
        print(json.dumps(result,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__+': '+str(exc)}))
        raise SystemExit(1)
