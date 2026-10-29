"""Condition-held-out, raw-measurement CHO batch forecasting.

A lumped Monod batch growth / glucose balance, NOT the continuous SMPL model.
No antibody output is present in these workbooks. No future recorded feed is used.
"""
import argparse
from pathlib import Path
import json
import hashlib
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
from .experiment import dump,sha

FIELDS=('viable_cells_million_per_ml','glucose_g_per_l')
BOUNDS=([.005,0.,.01,.1,.00001],[.08,.03,10.,10.,.1])
STARTS=([.035,.003,.5,2.,.005],[.05,.01,2.,3.,.01],[.025,.001,.1,1.,.001])


def integrate(parameters,state,start,times):
    mu_max,kd,ks,yield_xg,maintenance=parameters
    def rhs(t,z):
        x,g=np.exp(z)
        mu=mu_max*g/(ks+g)
        return [mu-kd,-(mu_max/yield_xg+maintenance)*x/(ks+g)]
    times=np.array(times,dtype=float)
    if not len(times):return np.empty((0,2))
    if np.any(np.asarray(state)<=0):raise ValueError('Positive conditioning state required')
    if times[0]<start:raise ValueError('Prediction times precede state')
    if times[-1]==start:return np.tile(state,(len(times),1))
    sol=solve_ivp(rhs,[start,times[-1]],np.log(state),t_eval=times,method='LSODA',rtol=1e-7,atol=1e-9)
    if not sol.success or not np.all(np.isfinite(sol.y)):raise ValueError('CHO model integration failed')
    return np.exp(sol.y.T)


def raw_cultures(root):
    import openpyxl
    cultures=[];provenance=[]
    for experiment in range(1,10):
        path=root/f'EXP{experiment:03d}_batch.xlsx'
        workbook=openpyxl.load_workbook(path,read_only=True,data_only=True)
        provenance.append({'file':path.name,'sha256':sha(path)})
        for reactor in ('R01','R02'):
            measurements=[]
            for suffix,key in [('CellAnalysis',FIELDS[0]),('MediumAnalysis',FIELDS[1])]:
                sheet=workbook[f'{reactor}_offline_{suffix}']
                for rownum,row in enumerate(sheet.values,1):
                    if rownum==1:continue
                    t,value=row[:2]
                    if not isinstance(t,(int,float)) or not isinstance(value,(int,float)) or t>120:continue
                    if not np.isfinite(value) or value<0:raise ValueError('Invalid raw measurement')
                    measurements.append({'time_h':float(t),'field':key,'value':float(value)/(1e6 if key==FIELDS[0] else 1.),
                        'source':{'workbook':path.name,'sheet':sheet.title,'time_cell':f'A{rownum}','value_cell':f'B{rownum}'}})
            measurements.sort(key=lambda r:(r['time_h'],r['field']))
            cultures.append({'condition':f'EXP{experiment:03d}','culture':f'EXP{experiment:03d}_{reactor}',
                'fold':(experiment-1)%3,'measurements':measurements})
        workbook.close()
    return cultures,provenance


def initial(culture):
    rows=culture['measurements'];first=[next(r for r in rows if r['field']==key) for key in FIELDS]
    if first[0]['time_h']!=first[1]['time_h']:raise ValueError('Asynchronous initial states require explicit conditioning')
    return first[0]['time_h'],[r['value'] for r in first]


def fit(training):
    def residual(logpars):
        pars=np.exp(logpars);errors=[]
        for culture in training:
            start,state=initial(culture);rows=culture['measurements']
            times=sorted(set(r['time_h'] for r in rows));pred=integrate(pars,state,start,times)
            lookup={t:pred[i] for i,t in enumerate(times)}
            for r in rows:
                v=lookup[r['time_h']][FIELDS.index(r['field'])]
                errors.append(np.log(max(v,1e-12)/r['value']) if r['field']==FIELDS[0] else (v-r['value'])/7.)
        return np.array(errors)
    lo=np.array(BOUNDS[0]);lo[1]=1e-7
    fits=[least_squares(residual,np.log(start),bounds=(np.log(lo),np.log(BOUNDS[1])),max_nfev=120,loss='soft_l1') for start in STARTS]
    best=min(fits,key=lambda f:f.cost)
    return {'parameters':np.exp(best.x).tolist(),'parameter_names':['mu_max_per_h','death_per_h','Ks_g_l','yield_million_cells_ml_per_g_l','maintenance_g_l_per_million_cells_ml_h'],
        'training_conditions':sorted(set(c['condition'] for c in training)),
        'training_cultures':[c['culture'] for c in training],
        'optimizer_success':bool(best.success),'cost':float(best.cost),'initializations':STARTS,'bounds':BOUNDS,
        'equations':'mu=mu_max*G/(Ks+G); dX=(mu-kd)*X; dG=-(mu/Y+m*G/(Ks+G))*X',
        'limitations':'Constant lumped kinetics; missing other nutrients/metabolites, stress and environmental effects; parameters may be weakly identifiable. Batch only, not fed-batch or SMPL.'}


def predict(packet):
    params=packet['cho_model']['parameters'];rows=packet['test_prefix']
    c={'measurements':rows};start,state=initial(c);state=np.array(state)
    # Assimilation uses only readings <=72h, with fitted global parameters fixed.
    if any(r['time_h']>72 for r in rows):raise ValueError('Future value in conditioning prefix')
    for time in sorted(set(r['time_h'] for r in rows)):
        state=integrate(params,state,start,[time])[0]
        for row in rows:
            if row['time_h']==time:state[FIELDS.index(row['field'])]=max(row['value'],1e-9)
        start=time
    result={}
    for key,time in packet['forecast_times_h'].items():
        result[key]=float(integrate(params,state,start,[time])[0,FIELDS.index(key)])
    return result


def forward(packet,action):
    if action!='keep':raise ValueError('CHO observational forecast has no intervention')
    return {'classification':'fitted_mechanistic_forecast_not_observation','action_id':'keep','predictions':predict(packet),
        'model':packet['cho_model'],'conditioning':'Only this held-out culture observations through72h; no refitting to future values.'}


def score(packet,truth,submission):
    if submission['action_id']!='keep':raise ValueError('CHO action must be keep')
    errors={}
    for key in FIELDS:
        value=submission['predictions'][key];actual=truth['targets'][key]['value']
        errors[key]={'predicted':value,'actual':actual,'absolute_error':abs(value-actual),
            'normalized_absolute_error':abs(value-actual)/truth['training_scales'][key]}
    return {'prediction_errors':errors,'classification':'real_CHO_offline_measurements_condition_held_out',
        'selected_action':'keep','objective_change':0.,'objective_change_percent':0.,'finite_grid_regret':None}


def generate(root,output,paths):
    if output.exists():raise ValueError('Fresh output directory required')
    output.mkdir(parents=True)
    protocol={'version':'real-cho-batch-20261028-v1','paths':paths,'source':'https://zenodo.org/records/20829178',
        'job':'Compare same AI with/without a fitted batch growth/glucose balance against real measurements.',
        'fold_rule':'(EXP number-1)%3; entire EXP with both reactors withheld; train on other six EXPs.',
        'cutoff_h':72,'target_rule':'First actual offline reading for each field within[96,120]h; exact recorded timestamps, no target interpolation.',
        'repeats':2,'primary_metrics':'MAE in physical units; error divided by median positive training measurement in each field. Paired differences clustered by EXP; repeats not independent.',
        'scope':'Batch EXP001..009 only; 18 candidate cultures. A paired test requires both actual targets in[96,120]h; missing targets are recorded, never imputed. Six fed-batch cultures excluded for missing feed composition/planned inputs. No antibody titer or real intervention/tech-transfer test.',
        'selection':'Retrospective grouped holdout from a previously available public dataset, not a prospective blind study.',
        'comparison':'Same training measurements and held-out prefix to both AI arms. Only B has fitted mechanistic forward tool.',
        'model_choice':'Simple Monod glucose-limited growth/death plus substrate mass balance; continuous SMPL equations inappropriate to these batch cultivations.',
        'design_tradeoff':'Small transparent batch model before richer hybrid models; omitted nutrients/environment may harm accuracy. No tuning on test futures.',
        'pillars':'Reuse source workbooks; preserve cell provenance; compare actionable prediction errors; isolated benchmark, no application migration.'}
    dump(output/'protocol.json',protocol)
    cultures,provenance=raw_cultures(root);dump(output/'source-provenance.json',provenance)
    catalogue=[];exclusions=[]
    for fold in range(3):
        training=[c for c in cultures if c['fold']!=fold];testing=[c for c in cultures if c['fold']==fold]
        model=fit(training);dump(output/'fits'/f'fold-{fold}.json',model)
        if set(model['training_conditions']) & {c['condition'] for c in testing}:raise ValueError('Condition leakage')
        scales={key:float(np.median([r['value'] for c in training for r in c['measurements'] if r['field']==key and r['value']>0])) for key in FIELDS}
        for culture in testing:
            missing=[key for key in FIELDS if not any(r['field']==key and 96<=r['time_h']<=120 for r in culture['measurements'])]
            if missing:
                exclusions.append({'culture':culture['culture'],'condition':culture['condition'],'missing_target_fields':missing,'reason':'No measured target in predeclared96..120h window; no imputation.'})
                continue
            targets={key:next(r for r in culture['measurements'] if r['field']==key and 96<=r['time_h']<=120) for key in FIELDS}
            case='CH-'+hashlib.sha256(culture['culture'].encode()).hexdigest()[:12]
            packet={'case_id':case,'simulator':'cho_real','task':'prediction','condition':culture['condition'],'culture':culture['culture'],'fold':fold,
                'allowed_actions':['keep'],'decision_time_h':72.,'forecast_fields':list(FIELDS),
                'forecast_times_h':{k:v['time_h'] for k,v in targets.items()},
                'field_units':{FIELDS[0]:'million viable cells/mL',FIELDS[1]:'g/L'},
                'objective':'Predict each listed field at its exact forecast time. This is observational prediction; keep is the only action.',
                'training_cultures':training,'test_prefix':[r for r in culture['measurements'] if r['time_h']<=72],
                'cultivation_mode':'CHO-K1 batch','cho_model':model}
            dump(output/'public'/case/'packet.json',packet)
            dump(output/'model-library'/case/'nominal.json',{'keep':predict(packet)})
            dump(output/'evaluator'/case/'truth.json',{'condition':culture['condition'],'culture':culture['culture'],'targets':targets,'training_scales':scales})
            catalogue.append({'case_id':case,'simulator':'cho_real','task':'prediction'})
        print(json.dumps({'fold':fold,'fit_success':model['optimizer_success'],'cost':model['cost']}),flush=True)
    dump(output/'exclusions.json',exclusions)
    dump(output/'public/catalogue.json',catalogue);dump(output/'evaluator/catalogue.json',catalogue)
    dump(output/'manifest.json',{'files_sha256':{str(p.relative_to(output)):sha(p) for p in output.rglob('*.json') if p.name!='manifest.json'}})
    dump(output/'generation-status.json',{'status':'complete','cases':len(catalogue)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--paths-from',type=Path,required=True)
    a=p.parse_args();generate(a.raw,a.output,json.loads(a.paths_from.read_text())['paths'])
