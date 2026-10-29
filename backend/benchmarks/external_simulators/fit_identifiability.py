"""Development-seed diagnostic for PenSim source-fit baselines.

Compares the frozen fit (seed-0 reset as nominal baseline) with a
population-mean baseline and with a population-mean baseline plus a fitted
initial-inoculum factor. Uses seeds disjoint from every study suite, never
reads study evaluator files, and does not modify frozen study code. Results
are implementation diagnostics on simulated data, not empirical validation.
"""
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import argparse,json,time
import numpy as np
from scipy.optimize import least_squares

from . import calibrated_pen as cp
from .challenges import admit_source,evaluate,pen_scenario,thinning
from .oxygen import run_continuous
from .upstream import pen_module,pen_recipe

PATHS={'pensim':'/private/tmp/biodemo-pensimpy-source','native':'/private/tmp/biodemo-audited-native'}
SOURCE_PLAN={'feed_factor':1.,'air_factor':1.15,'apply_after_h':60.}
VARIANTS=('seed0','population_mean','population_mean_inoculum')
INOCULUM_BOUNDS=(.6,1.4)
# Expected values of every random draw in PenSimPy reset (randn -> 0).
MEAN_X0={'mux':.41,'mup':.041,'S':1.,'DO2':15.,'X':.5,'P':0.,'V':5.8e4,'Wt':6.2e4,'CO2outgas':.038,'O2':.2,
    'pH':10**-6.5,'T':297.,'a0':.5/3,'a1':.5*2/3,'a3':0.,'a4':0.,'Culture_age':0.,'PAA':1400.,'NH3':1700.}
MEAN_PARAMS=[.041,.41,85.,150000.,530000.]
TARGETS=[(t,f) for t in (64.,72.,96.) for f in ('P','DO2')]
FEEDS_AIR115=(.85,.9,1.,1.05,1.1,1.15)
FEEDS_AIR100=(.85,1.)


def plan(feed,air):
    return {'feed_factor':feed,'air_factor':air,'apply_after_h':60.}


@contextmanager
def baseline(kind,inoculum=1.):
    if kind=='seed0':
        yield
        return
    module=pen_module(Path(PATHS['pensim']),Path(PATHS['native']))
    original=module.PenSimEnv.reset
    def reset(env):
        out=original(env)
        for key,value in MEAN_X0.items():setattr(env.x0,key,value)
        env.x0.X*=inoculum;env.x0.a0*=inoculum;env.x0.a1*=inoculum
        env.param_list=list(MEAN_PARAMS)
        return out
    module.PenSimEnv.reset=reset
    try:yield
    finally:module.PenSimEnv.reset=original


def predict(operating,fit,kind):
    factors={k:fit[k] for k in cp.PARAMETERS}
    with baseline(kind,fit.get('inoculum_factor',1.)):
        return cp.simulate(PATHS,operating,factors)


def fit_variant(history,kind):
    if kind=='seed0':
        result=cp.fit_source(history,PATHS,source_plan=SOURCE_PLAN)
        return {**{k:result[k] for k in cp.PARAMETERS},'optimizer_success':result['optimizer_success'],
            'evaluations':result['evaluations'],'source_MAE':result['source_MAE']}
    names=list(cp.PARAMETERS)+(['inoculum_factor'] if kind=='population_mean_inoculum' else [])
    low=list(cp.BOUNDS[0])+([INOCULUM_BOUNDS[0]] if len(names)==4 else [])
    high=list(cp.BOUNDS[1])+([INOCULUM_BOUNDS[1]] if len(names)==4 else [])
    rows=[r for r in history if r['time_h']>=20.];count=[0]
    def residual(logpars):
        count[0]+=1
        fit=dict(zip(names,map(float,np.exp(logpars))))
        return cp.source_residual(predict(SOURCE_PLAN,fit,kind),rows)
    solved=least_squares(residual,np.zeros(len(names)),bounds=(np.log(low),np.log(high)),
        diff_step=1e-3,max_nfev=60,loss='soft_l1',f_scale=1.)
    fit=dict(zip(names,map(float,np.exp(solved.x))))
    errors=cp.source_residual(predict(SOURCE_PLAN,fit,kind),rows).reshape(len(cp.FIELDS),len(rows))
    return {**fit,'optimizer_success':bool(solved.success),'evaluations':count[0],
        'source_MAE':{f:float(np.mean(np.abs(errors[i]))*cp.SCALES[f]) for i,f in enumerate(cp.FIELDS)}}


def truth(seed):
    module=pen_module(Path(PATHS['pensim']),Path(PATHS['native']))
    env=module.PenSimEnv(pen_recipe(),fast=True);env.random_seed_ref=seed;env.reset()
    return {'params':list(map(float,env.param_list[:3])),'inoculum':float(env.x0.a0+env.x0.a1)}


def at(result,time_h,field):
    rows=[r for r in result['trace'] if abs(r['time_h']-time_h)<1e-7]
    if len(rows)!=1:raise ValueError('Target time missing')
    return rows[0]['state'][field]


def summary(result):
    return {'targets':{f'{f}@{t:g}':at(result,t,f) for t,f in TARGETS},'objective':result['objective'],
        'trace_DO2_after_60':[r['state']['DO2'] for r in result['trace'] if r['time_h']>60+1e-8],
        'resources':result['resources'],'audit':{'dissolved_oxygen_floor_events':result['audit'].get('dissolved_oxygen_floor_events',0)}}


def seed_job(seed):
    start=time.monotonic()
    source=run_continuous(PATHS,pen_scenario,PATHS,seed,SOURCE_PLAN);admit_source(source)
    history=thinning(source)
    plans={f'f{f}_a1.15':plan(f,1.15) for f in FEEDS_AIR115}
    plans.update({f'f{f}_a1.0':plan(f,1.) for f in FEEDS_AIR100})
    actual={k:summary(run_continuous(PATHS,pen_scenario,PATHS,seed,v)) for k,v in plans.items()}
    identical=all(abs(at(source,t,f)-actual['f1.0_a1.15']['targets'][f'{f}@{t:g}'])<1e-12 for t,f in TARGETS)
    fits={};predictions={}
    for kind in VARIANTS:
        fits[kind]=run_continuous(PATHS,fit_variant,history,kind)
        fit=fits[kind]
        predictions[kind]={k:summary(run_continuous(PATHS,predict,v,fit,kind)) for k,v in plans.items()}
    return {'seed':seed,'truth':truth(seed),'source_history':history,'plans':plans,'actual':actual,
        'fits':fits,'predictions':predictions,'source_equals_keep_f1.0_a1.15':identical,'seconds':time.monotonic()-start}


def baseline_params(kind):
    return truth(0)['params'] if kind=='seed0' else MEAN_PARAMS[:3]


def feasible(entry,limits):
    feed=entry['resources']['feed_factor'];air=entry['resources']['air_factor']
    return (not entry['audit']['dissolved_oxygen_floor_events'] and feed<=limits['maximum_feed_factor']+1e-9
        and air<=limits['maximum_air_factor']+1e-9 and min(entry['trace_DO2_after_60'])>=limits['minimum_do_mg_l'])


def decision_scores(job,kind):
    """Study-style decision score for every scenario cell in the frozen grid."""
    scores=[]
    for keep in (.9,1.,1.05,1.1):
        for max_feed in (.9,1.,1.15):
            for max_air in (1.,1.15):
                limits={'maximum_feed_factor':max_feed,'maximum_air_factor':max_air,'minimum_do_mg_l':2.}
                actions={'keep':f'f{keep}_a1.15','lean':'f0.85_a1.15','standard':'f1.0_a1.15','rich':'f1.15_a1.15',
                    'lean_low_gas':'f0.85_a1.0','standard_low_gas':'f1.0_a1.0'}
                real={a:job['actual'][k] for a,k in actions.items()}
                pred={a:job['predictions'][kind][k] for a,k in actions.items()}
                real_ok=[a for a in real if feasible(real[a],limits)]
                pred_ok=[a for a in pred if feasible(pred[a],limits)]
                best=max((real[a]['objective'] for a in real_ok),default=0.)
                if not pred_ok:score=1. if not real_ok else 0.
                else:
                    choice=max(pred_ok,key=lambda a:pred[a]['objective'])
                    score=real[choice]['objective']/best if choice in real_ok and best>0 else 0.
                scores.append(score)
    return scores


def analyze(jobs):
    out={'seeds':[j['seed'] for j in jobs],'variants':{}}
    for kind in VARIANTS:
        base=np.array(baseline_params(kind))
        true=np.array([np.array(j['truth']['params'])/base for j in jobs])
        names=['production_factor','growth_factor','kla_factor']
        fit=np.array([[j['fits'][kind][n] for n in names] for j in jobs])
        bounds={'production_factor':cp.BOUNDS[0][2],'growth_factor':cp.BOUNDS[0][1],'kla_factor':cp.BOUNDS[0][0]}
        upper={'production_factor':cp.BOUNDS[1][2],'growth_factor':cp.BOUNDS[1][1],'kla_factor':cp.BOUNDS[1][0]}
        recovery={}
        for i,n in enumerate(names):
            at_bound=sum(abs(v-bounds[n])<1e-3 or abs(v-upper[n])<1e-3 for v in fit[:,i])
            recovery[n]={'corr':float(np.corrcoef(fit[:,i],true[:,i])[0,1]),'mean_abs_error':float(np.mean(abs(fit[:,i]-true[:,i]))),'at_bound':int(at_bound)}
        if kind=='population_mean_inoculum':
            ti=np.array([j['truth']['inoculum']/.5 for j in jobs]);fi=np.array([j['fits'][kind]['inoculum_factor'] for j in jobs])
            recovery['inoculum_factor']={'corr':float(np.corrcoef(fi,ti)[0,1]),'mean_abs_error':float(np.mean(abs(fi-ti))),
                'at_bound':int(sum(abs(v-b)<1e-3 for v in fi for b in INOCULUM_BOUNDS))}
        errors={'all_plans':[],'challenge_keep':[],'changed_air':[],'source_identical':[]}
        for j in jobs:
            scale={f:max(float(np.median([r['state'][f] for r in j['source_history']])),1e-6) for f in ('P','DO2')}
            for k in j['plans']:
                e=np.mean([abs(j['predictions'][kind][k]['targets'][f'{f}@{t:g}']-j['actual'][k]['targets'][f'{f}@{t:g}'])/scale[f] for t,f in TARGETS])
                errors['all_plans'].append(e)
                if k in ('f0.9_a1.15','f1.05_a1.15','f1.1_a1.15'):errors['challenge_keep'].append(e)
                if k.endswith('a1.0'):errors['changed_air'].append(e)
                if k=='f1.0_a1.15':errors['source_identical'].append(e)
        dec=[s for j in jobs for s in decision_scores(j,kind)]
        out['variants'][kind]={'parameter_recovery':recovery,
            'optimizer_success':int(sum(j['fits'][kind]['optimizer_success'] for j in jobs)),
            'max_residual_evaluations':int(max(j['fits'][kind]['evaluations'] for j in jobs)),
            'source_MAE_mean':{f:float(np.mean([j['fits'][kind]['source_MAE'][f] for j in jobs])) for f in cp.FIELDS},
            'normalized_forecast_error_mean':{k:float(np.mean(v)) for k,v in errors.items()},
            'decision_score_mean':float(np.mean(dec)),'decision_cells':len(dec)}
    # Source-copy reference: predict KEEP target values by interpolating the completed source history.
    copy={'challenge_keep':[]}
    for j in jobs:
        scale={f:max(float(np.median([r['state'][f] for r in j['source_history']])),1e-6) for f in ('P','DO2')}
        times=[r['time_h'] for r in j['source_history']]
        for k in ('f0.9_a1.15','f1.05_a1.15','f1.1_a1.15'):
            copy['challenge_keep'].append(np.mean([abs(np.interp(t,times,[r['state'][f] for r in j['source_history']])-j['actual'][k]['targets'][f'{f}@{t:g}'])/scale[f] for t,f in TARGETS]))
    out['source_copy_reference']={k:float(np.mean(v)) for k,v in copy.items()}
    out['source_equals_ordinary_keep']=all(j['source_equals_keep_f1.0_a1.15'] for j in jobs)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seeds',default='9501-9512');p.add_argument('--workers',type=int,default=6);a=p.parse_args()
    lo,hi=map(int,a.seeds.split('-'));seeds=list(range(lo,hi+1))
    a.output.mkdir(parents=True,exist_ok=True)
    done={s:json.loads((a.output/f'seed-{s}.json').read_text()) for s in seeds if (a.output/f'seed-{s}.json').exists()}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for job in pool.map(seed_job,[s for s in seeds if s not in done]):
            done[job['seed']]=job;(a.output/f"seed-{job['seed']}.json").write_text(json.dumps(job))
            print(json.dumps({'seed':job['seed'],'seconds':round(job['seconds'],1)}),flush=True)
    jobs=[done[s] for s in seeds]
    result=analyze(jobs);(a.output/'analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
