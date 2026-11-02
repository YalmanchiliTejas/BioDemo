"""Small adapters around external equations; no production or equipment writes.

SMPL uses its original 17-state upstream equations, not downstream purification.
PenSimPy keeps original controllers/postprocessing but monitors raw integration.
Native globals prohibit threaded simulations; call these in separate processes.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
from copy import deepcopy
import importlib
import json
import math
from pathlib import Path
import sys
import warnings

import numpy as np
from scipy.integrate import solve_ivp


PEN_NAMES=['S','DO2','O2','P','V','Wt','pH','T','Q','Viscosity','Culture_age',
           'a0','a1','a3','a4','n0','n1','n2','n3','n4','n5','n6','n7','n8','n9','nm','phi0',
           'CO2outgas','CO2_d','PAA','NH3','mu_P_calc','mu_X_calc']
PEN_COMMANDS=['Fs','Foil','Fg','pressure','discharge','Fw','Fpaa']
MAB_NAMES=['viable_cells_reactor','total_cells_reactor','glucose_reactor','glutamine_reactor',
           'lactate_reactor','ammonia_reactor','mAb_reactor','volume_reactor',
           'viable_cells_separator','total_cells_separator','glucose_separator','glutamine_separator',
           'lactate_separator','ammonia_separator','mAb_separator','volume_separator','temperature']
MAB_UNITS=['cells/L','cells/L','mM','mM','mM','mM','mg/L','L',
           'cells/L','cells/L','mM','mM','mM','mM','mg/L','L','degC']
MAB_COMMANDS=['inlet_flow','reactor_outlet_flow','recycle_flow','product_outlet_flow',
              'inlet_glucose','inlet_glutamine','coolant_temperature']


class PenModelDomainError(ValueError):
    """Rejected raw trajectory, with evaluator-only diagnostic context."""
    def __init__(self,message,context):
        super().__init__(message)
        self.context=context


def read_mab(source: Path):
    import casadi as cs
    path=source/'smpl/envs/helpers/mab_helpers.py'
    tree=ast.parse(path.read_text())
    selected=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='UpModelHelper']
    if len(selected)!=1:
        raise ValueError('Upstream SMPL helper missing')
    # Execute the unmodified class body. Avoid installing unrelated RL/MPC packages.
    namespace={'np':np,'cs':cs}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),namespace)
    data=source/'smpl/configdata/mabenv'
    x=np.load(data/'xss.npy')[:17]
    u=np.load(data/'uss.npy')[:7]
    model=namespace['UpModelHelper'](17,7,x,u,x,np.maximum(np.abs(u),1.))
    return model,x,u


def mab_run(source: Path, *, initial=None, command=None, hours=24., solver='BDF',rtol=1e-8):
    model,xss,uss=read_mab(source)
    x0=np.array(initial if initial is not None else xss,dtype=float)
    u=np.array(command if command is not None else uss,dtype=float)
    scale=np.maximum(np.abs(xss),1.)
    def fun(_time,z):
        return np.array(model.xdot(z*scale,u),dtype=float)/scale
    times=np.linspace(0,hours*60,int(round(hours*4))+1)
    result=solve_ivp(fun,(0,hours*60),x0/scale,method=solver,rtol=rtol,
                     atol=rtol*.01,t_eval=times,max_step=30.)
    if not result.success:
        raise ValueError('SMPL solver failed: '+result.message)
    values=result.y.T*scale
    if not np.isfinite(values).all() or (values[:,:16]<-1e-6).any():
        raise ValueError('SMPL produced negative or nonfinite physical state')
    if np.any(values[:,[7,15]]<=0) or np.any(values[:,16]<0):
        raise ValueError('SMPL volume/temperature invalid')
    # Output stream crosses the upstream boundary; recycle/reactor outlet are internal.
    mass_mg=float(np.trapz(values[:,14]*u[3],times))
    trace=[{'time_h':float(t/60),'state':dict(zip(MAB_NAMES,map(float,row)))} for t,row in zip(times,values)]
    return {'trace':trace,'terminal':trace[-1]['state'], 'product_mass_mg':mass_mg,
            'solver':solver,'rtol':rtol,'rhs_evaluations':result.nfev,
            'scope':'Original SMPL 17-state upstream bioreactor/separator only; downstream not simulated.'}


def pen_module(source: Path,native: Path):
    for directory in (source,native):
        value=str(directory.resolve())
        if value not in sys.path:
            sys.path.insert(0,value)
    return importlib.import_module('pensimpy.peni_env_setup')


def pen_recipe(*, supplied=False):
    from pensimpy.data import constants as c
    from pensimpy.examples.recipe import Recipe,RecipeCombo
    draw=[{'time':0,'value':0}]
    for start in (100,130,150,170,190,210):
        draw.extend([{'time':start,'value':4000},{'time':start+2,'value':0}])
    profiles=[c.FS_DEFAULT_PROFILE,c.FOIL_DEFAULT_PROFILE,c.FG_DEFAULT_PROFILE,c.PRESS_DEFAULT_PROFILE,
              c.DISCHARGE_DEFAULT_PROFILE if supplied else draw,c.WATER_DEFAULT_PROFILE,c.PAA_DEFAULT_PROFILE]
    return RecipeCombo({n:Recipe(deepcopy(p),n) for n,p in zip(PEN_COMMANDS,profiles)})


@contextmanager
def monitor_pen(module,*,rtol=1e-7,solver='native',correct_clock=True):
    original=module.fastodeint.integrate
    counters={'integrations':0,'raw_floor_events':0,'dissolved_oxygen_floor_events':0,
              'max_rhs_relative_disagreement':0.,'clock_mode':'exact_nominal_endpoints' if correct_clock else 'upstream_extended_endpoints'}
    samples=[]
    def integrate(initial,parameters,start,end,dt):
        y0=np.array(initial,dtype=float)
        p=np.array(parameters,dtype=float)
        # Upstream calls [k*0.2, (k+1)*0.2+0.005] but restarts on nominal clock.
        # Correct only this documented driver endpoint; retain equations/controllers.
        actual_end=end-dt if correct_clock else end
        if solver=='native':
            result=np.array(module.fastodeint.integrate_checked(y0,p,start,actual_end,dt,1e-9,rtol),copy=True)
        else:
            solved=solve_ivp(lambda t,y:module.indpensim_ode_py(t,np.array(y,copy=True),p),
                (start,actual_end),y0,method='LSODA',atol=1e-9,rtol=rtol)
            if not solved.success:
                raise ValueError('Python reference solver failed: '+solved.message)
            result=solved.y[:,-1]
        counters['integrations']+=1
        if not np.isfinite(result).all():
            raise ValueError('PenSim raw solver contains nonfinite state')
        bad=invalid_pen_states(result)
        if bad or result[4]<=0 or result[6]<=0:
            context={'time_start_h':float(start),'time_end_h':float(actual_end),
                     'initial_state':y0.tolist(),'raw_state':result.tolist(),'parameters':p.tolist(),
                     'rhs_at_start':np.array(module.fastodeint.rhs(y0.copy(),p,float(start))).tolist() if hasattr(module.fastodeint,'rhs') else None}
            raise PenModelDomainError('PenSim raw physical state invalid: '+json.dumps(bad),context)
        counters['raw_floor_events']+=int(np.sum(result[:31]<=0))
        counters['dissolved_oxygen_floor_events']+=int(result[1]<2)
        if counters['integrations'] in (1,100,400,800,1150):
            native_rhs=np.array(module.fastodeint.rhs(y0,p,float(start)))
            python_rhs=np.array(module.indpensim_ode_py(float(start),y0.copy(),p))
            difference=float(np.max(np.abs(native_rhs-python_rhs)/(1+np.abs(python_rhs))))
            counters['max_rhs_relative_disagreement']=max(counters['max_rhs_relative_disagreement'],difference)
            samples.append({'time_h':float(start),'state':y0.tolist(),'parameters':p.tolist(),
                            'rhs_relative_disagreement':difference})
        # ndarray will be clipped IN PLACE by upstream; samples above retain copies.
        return result
    module.fastodeint.integrate=integrate
    try:
        yield counters,samples
    finally:
        module.fastodeint.integrate=original


def pen_run(source: Path,native: Path,*,seed=1,action='keep',start_h=80.,
            aeration_factor=1.,rtol=1e-7,solver='native',supplied=False,correct_clock=True,hours=230.,nominal=False,parameter_overrides=None):
    module=pen_module(source,native)
    env=module.PenSimEnv(pen_recipe(supplied=supplied),fast=True)
    env.random_seed_ref=seed
    # Raman generation has no effect on equations/controllers with SBC=0.
    env.ctrl_flags.Raman_spec=0
    if nominal:
        # Fully specified nominal model: no undisclosed future disturbance stream.
        env.ctrl_flags.Dis=0
    _,state=env.reset()
    overrides=parameter_overrides or {}
    if set(overrides)-{'kla_factor','growth_factor'}:
        raise ValueError('Unsupported nominal parameter override')
    for key,index in [('kla_factor',2),('growth_factor',1)]:
        factor=overrides.get(key,1.)
        if not np.isfinite(factor) or factor<=0:
            raise ValueError('Nominal parameter factor must be positive and finite')
        env.param_list[index]*=factor
    trace=[]
    with monitor_pen(module,rtol=rtol,solver=solver,correct_clock=correct_clock) as (audit,samples):
        steps=int(round(hours/.2))
        if not 1<=steps<=1150 or abs(steps*.2-hours)>1e-8:
            raise ValueError('PenSim horizon must align with its 0.2h control interval')
        for step in range(1,steps+1):
            time_h=step*.2
            controls=env.recipe_combo.get_values_dict_at(time_h)
            controls['Fg']*=aeration_factor
            if time_h>start_h:
                if action=='feed_down': controls['Fs']*=.99
                elif action=='feed_up': controls['Fs']*=1.01
                elif action=='air_up': controls['Fg']*=1.01
                elif action!='keep': raise ValueError('Unknown PenSim action')
            _,state,_,_=env.step(step,state,**controls)
            # Read physical H+ before upstream's terminal conversion to pH.
            ph=float(state.pH.y[step-1])
            ph=ph if step==1150 else -math.log10(ph)
            row={'time_h':time_h,'state':{n:float(getattr(state,n).y[step-1]) for n in ('S','DO2','O2','P','V','Wt','T','Viscosity')},
                 'commands':controls}
            row['state']['pH']=ph
            trace.append(row)
    return {'trace':trace,'terminal':trace[-1]['state'],'audit':audit,'rhs_samples':samples,
            'seed':seed,'action':action,'rtol':rtol,'solver':solver,
            'horizon_h':hours,'is_complete_230h_batch':steps==1150,
            'nominal_control_flags':dict(vars(env.ctrl_flags)) if nominal else None,
            'parameter_overrides':overrides,
            'scope':'PenSimPy with documented C++ exponent/driver-clock corrections and explicit two-hour draw-off recipe.'}
def invalid_pen_states(result):
    # Q (index8) integrates the SIGNED net heat balance, not a concentration.
    # Its derivative includes cooling; the equations never read y[8]. Treating
    # negative Q as negative material was an overly broad admission guard.
    return {PEN_NAMES[i]:float(v) for i,v in enumerate(result[:31]) if i!=8 and v< -1e-5}

