"""SMPL original balances with explicit uncertain kinetic multipliers.

Local AST copies modify only three named rate assignments, preserving source
files, minute units and coupled inventory accounting. No DO/quality state added.
"""
from pathlib import Path
import ast
import numpy as np
from scipy.integrate import solve_ivp
from benchmarks.external_simulators.upstream import read_mab,MAB_NAMES


def uncertain_model(source,parameters):
    import casadi as cs
    mapping={'mu_max':'growth_factor','mu_dmax':'death_factor','m_mabx':'production_factor'}
    if set(parameters)!=set(mapping.values()) or any(not np.isfinite(v) or v<=0 for v in parameters.values()):raise ValueError('Explicit positive kinetic multipliers required')
    path=source/'smpl/envs/helpers/mab_helpers.py';tree=ast.parse(path.read_text())
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='UpModelHelper');counts=dict.fromkeys(mapping,0)
    for node in ast.walk(cls):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in mapping:
                node.value=ast.BinOp(left=node.value,op=ast.Mult(),right=ast.Name(id=mapping[name],ctx=ast.Load()));counts[name]+=1
    if any(v!=1 for v in counts.values()):raise ValueError('Pinned kinetic assignment contract changed')
    namespace={'np':np,'cs':cs,**parameters};module=ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[]));exec(compile(module,str(path),'exec'),namespace)
    _,x,u=read_mab(source)
    return namespace['UpModelHelper'](17,7,x,u,x,np.maximum(np.abs(u),1.)),x,u


def evolve(source,initial,command,hours,parameters):
    model,xss,_=uncertain_model(source,parameters);x=np.array(initial,dtype=float);u=np.array(command,dtype=float)
    scale=np.maximum(np.abs(xss),1.);times=np.linspace(0,hours*60,int(round(hours*4))+1)
    sol=solve_ivp(lambda t,z:np.array(model.xdot(z*scale,u),dtype=float)/scale,[0,hours*60],x/scale,t_eval=times,method='BDF',rtol=1e-8,atol=1e-10,max_step=30.)
    states=sol.y.T*scale
    if not sol.success or not np.isfinite(states).all() or np.any(states[:,:16]<0) or np.any(states[:,[7,15]]<=0):raise ValueError('SMPL uncertain trajectory outside physical domain')
    return {'trace':[{'time_h':float(t/60),'state':dict(zip(MAB_NAMES,map(float,row)))} for t,row in zip(times,states)],
        'external_harvest_mg':float(np.trapz(states[:,14]*u[3],times)),
        'terminal_inventory_mg':float(states[-1,6]*states[-1,7]+states[-1,14]*states[-1,15]),
        'units':'Native minutes,flowsL/min,mAbmg/L,external harvestmg; no internal stream double-counting.'}


def forecast_from_measurements(source,source_prior,observed,command,*,decision_h,seed=1,members=16,hours=24.):
    """Model-tool boundary: source prior + released assays, never receiver truth."""
    from .smpl_observations import initial_ensemble
    ensemble=initial_ensemble(source_prior,observed,decision_h=decision_h,seed=seed,members=members)
    predictions=[];failures=[]
    for index,(state,parameters) in enumerate(zip(ensemble['initial_state_members'],ensemble['parameter_members'])):
        try:
            result=evolve(source,state,command,hours,parameters);last=result['trace'][-1]['state']
            predictions.append({'mAb_reactor_mg_l':last['mAb_reactor'],'viable_cells_reactor_cells_l':last['viable_cells_reactor'],'external_harvest_mg':result['external_harvest_mg']})
        except Exception as exc:failures.append({'member':index,'error':str(exc)})
    if not predictions:raise ValueError('No admitted uncertainty member')
    return {'classification':'partial_observation_model_prediction_not_measurement',
        'forecasts':{key:{'mean':float(np.mean([r[key] for r in predictions])),
            'range':[min(r[key] for r in predictions),max(r[key] for r in predictions)]} for key in predictions[0]},
        'members':members,'admitted_members':len(predictions),'failed_members':failures,
        'conditioning':'Released initial assays only; later temperatures/holdups are not treated as exact initial states.',
        'limits':'Fixed sensitivity set, not calibrated probability; source-only nominal prior, latent separator states, uncertain kinetics. No product-quality or real site-transfer claim.'}
