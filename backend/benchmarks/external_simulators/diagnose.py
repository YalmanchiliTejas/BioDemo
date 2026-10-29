"""Replay prior failures and source-only oxygen calibration; no receiving-label fit."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
from scipy.optimize import least_squares

from .experiment import checked,dump
from .upstream import pen_run,pen_module,PenModelDomainError


def trace_at(result,times,field):
    t=np.array([r['time_h'] for r in result['trace']])
    y=np.array([r['state'][field] for r in result['trace']])
    return np.interp(times,t,y)


def fit_oxygen(source_history,paths):
    """Fit two nominal physical factors ONLY to common completed source readings.

    Multiplicative kLa and growth factors preserve the receiving oxygen-balance
    structure. Unlike adding a source endpoint offset to receiving DO, the fitted
    parameters act inside the ODE after an aeration change. This does not predict
    unknown future disturbances or establish parameter identifiability.
    """
    rows=[r for r in source_history if r['time_h']>=20.]
    times=np.array([r['time_h'] for r in rows])
    do=np.array([r['state']['DO2'] for r in rows])
    substrate=np.array([r['state']['S'] for r in rows])
    evaluations=[]
    def residual(log_factors):
        factors=np.exp(log_factors)
        result=pen_run(Path(paths['pensim']),Path(paths['native']),seed=0,hours=96.,nominal=True,
                       parameter_overrides={'kla_factor':float(factors[0]),'growth_factor':float(factors[1])})
        # Scale in declared physical units; source only. No receiver trajectories.
        error=np.r_[(trace_at(result,times,'DO2')-do)/2.,
                    (trace_at(result,times,'S')-substrate)/5.]
        evaluations.append({'factors':factors.tolist(),'source_residual_norm':float(np.linalg.norm(error))})
        return error
    solved=least_squares(residual,np.zeros(2),bounds=(np.log([.5,.7]),np.log([1.5,1.3])),
                         max_nfev=35,diff_step=1e-3,loss='soft_l1',f_scale=1.)
    factors=np.exp(solved.x)
    return {'method':'source_fitted_kla_growth_v1',
            'kla_factor':float(factors[0]),'growth_factor':float(factors[1]),
            'fit_source_times_h':times.tolist(),'optimizer_success':bool(solved.success),
            'optimizer_message':solved.message,'source_fit_cost':float(solved.cost),
            'source_evaluations':len(evaluations),'bounds':{'kla_factor':[.5,1.5],'growth_factor':[.7,1.3]},
            'residual_scales':{'DO2_mg_l':2.,'substrate_g_l':5.},
            'provenance':'Only the completed source_history supplied identically to both arms. No receiving labels.'}


def full_batch_diagnosis(paths,output):
    records=[]
    for solver,rtol in [('native',1e-7),('native',1e-9),('python',1e-8)]:
        started=time.monotonic()
        try:
            r=pen_run(Path(paths['pensim']),Path(paths['native']),seed=17,hours=230.,solver=solver,rtol=rtol)
            record={'solver':solver,'rtol':rtol,'status':'complete','terminal':r['terminal']}
        except PenModelDomainError as exc:
            ctx=exc.context;module=pen_module(Path(paths['pensim']),Path(paths['native']))
            boundary=np.array(ctx['initial_state']);boundary[9]=0.
            rhs=np.array(module.fastodeint.rhs(boundary,np.array(ctx['parameters']),ctx['time_start_h']))
            record={'solver':solver,'rtol':rtol,'status':'rejected','error':str(exc),'context':ctx,
                    'viscosity_rhs_at_zero':float(rhs[9]),
                    'water_command_as_implemented':ctx['parameters'][14],
                    'water_dilution_term_cp_h':-.005*ctx['parameters'][14],
                    'zero_boundary_invariant':bool(rhs[9]>=0)}
        record['seconds']=time.monotonic()-started;records.append(record)
    receipt={'records':records,'full_batch_qualified':False,
        'finding':'The empirical viscosity ODE can point below zero during water addition. Independent/tighter solvers reproduce it; accepting clipping would conceal the domain failure.',
        'correction_policy':'Retain raw-state rejection and the full230h failure. No unvalidated rheology replacement or shorter-horizon success is called a full-batch fix.'}
    dump(output/'full-batch-diagnosis.json',receipt)
    return receipt


def oxygen_diagnosis(dataset,output):
    paths=checked(dataset,'protocol.json')['paths'];catalogue=checked(dataset,'public/catalogue.json')
    fits={};rows=[]
    for item in catalogue:
        if item['simulator']!='pensim' or item['task']!='prediction':continue
        case=item['case_id'];p=checked(dataset,f'public/{case}/packet.json')
        truth=checked(dataset,f'evaluator/{case}/truth.json')
        nominal=checked(dataset,f'model-library/{case}/nominal.json')['keep']
        key=json.dumps(p['source_history'],sort_keys=True)
        if key not in fits:fits[key]=fit_oxygen(p['source_history'],paths)
        fitted=fits[key];cap=p['receiving_specifications']['receiving_nominal_aeration_factor_vs_source']
        predicted=pen_run(Path(paths['pensim']),Path(paths['native']),seed=0,hours=96.,nominal=True,
            aeration_factor=cap,parameter_overrides={k:fitted[k] for k in ('kla_factor','growth_factor')})
        actual=truth['baseline']['process_indicator']
        alternatives={'nominal':nominal['process_indicator'],
                      'legacy_additive_offset':nominal['process_indicator']+p['source_calibration']['indicator_offset'],
                      'source_fitted_physical_parameters':predicted['terminal']['DO2']}
        rows.append({'case':case,'receiving_aeration_factor':cap,'actual_do_mg_l':actual,
                     'predictions':alternatives,'relative_errors':{k:abs(v-actual)/actual for k,v in alternatives.items()},
                     'source_only_fit':fitted})
    receipt={'cases':rows,'mean_relative_errors':{k:float(np.mean([r['relative_errors'][k] for r in rows])) for k in rows[0]['predictions']},
             'scope':'Previously inspected pilot cases diagnose a correction; fresh cases are required to assess generalization. Fitting uses only source history.'}
    dump(output/'oxygen-diagnosis.json',receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    paths=checked(args.dataset,'protocol.json')['paths']
    f=full_batch_diagnosis(paths,args.output)
    print(json.dumps({'full_batch':[{'solver':r['solver'],'status':r['status'],'time_h':r.get('context',{}).get('time_start_h'),'boundary_rhs':r.get('viscosity_rhs_at_zero')} for r in f['records']]}),flush=True)
    o=oxygen_diagnosis(args.dataset,args.output)
    print(json.dumps({'oxygen_mean_errors':o['mean_relative_errors']}),flush=True)
