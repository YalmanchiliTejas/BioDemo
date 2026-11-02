"""Frozen paired A/B intervention study. Prior optimizer results stay archived.

Source qualification precedes freeze. Final receiver seeds are generated only
from the frozen protocol. Process workers isolate native global solver state.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
from copy import deepcopy
import argparse,hashlib,json,shutil,time,traceback
import numpy as np
from benchmarks.external_simulators.experiment import checked,dump,sha
from benchmarks.external_simulators.run_agents import isolation
from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile
from .pensim import simulate,outcomes,ACTIONS,stop_classification
from .model import SensitivityReceivingModel
from .session import InterventionSession
from .run_agents import attempt,SYSTEM


def freeze(root):
    if root.exists():raise ValueError('Fresh study directory required')
    repo=Path(__file__).resolve().parents[3]
    source=repo/'backend/results/interventions/source-qualification-20261029.json'
    q=json.loads(source.read_text())
    if not q['optimizer_converged']:raise ValueError('Source optimizer failed')
    load_env_file(repo/'backend/.env.local');p=hosted_research_profile()
    if p is None:raise ValueError('No saved research provider')
    root.mkdir(parents=True)
    files=list(Path(__file__).parent.glob('*.py'))+list(Path(__file__).parent.glob('*.mjs'))
    files += [repo/'backend/benchmarks/external_simulators'/name for name in ['upstream.py','oxygen.py','run_agents.py']]
    paths=checked(repo/'backend/results/external-simulators/model-repair-continuous-20261028/dataset','protocol.json')['paths']
    files += [Path(paths['pensim'])/'pensimpy/ode/indpensim_ode_py.py',Path(paths['pensim'])/'pensimpy/peni_env_setup.py']
    protocol={'version':'pensim-interventions-20261029-v1','frozen_utc':datetime.now(timezone.utc).isoformat(),
        'primary_comparison':'Same AI without supplied model versus same AI with source-calibrated imperfect model',
        'claim_limit':'Tests model access benefit to agents; does not test added agent value beyond conventional optimizer. Earlier optimizer comparison retained.',
        'model':p.provider+'/'+p.model,'independent_scenarios':36,'repeats':2,'planned_AI_sessions':144,
        'seed_rule':'31001..31036; cyclic normal/moderate_loss/severe_loss,12 each; no resampling',
        'strata':['normal','moderate_loss','severe_loss'],'interpretation':'Strata specify disturbance assumptions, not guaranteed recoverability; report realized finite-menu feasibility separately.',
        'sampling_seed':20261029,'receiving_factor_ranges':{'kla_factor':[.8,1.2],'growth_factor':[.9,1.1],'production_factor':[.9,1.1]},
        'parameter_reference':'Coefficients relative to fixed seed0 kinetics; private seed varies unobserved initial states independently. Ranges are synthetic assumptions informed by port variability, not validated physical transfer distributions.',
        'transfer_multiplier_ranges':{'normal':[1.,1.],'moderate_loss':[.5,.6],'severe_loss':[.4,.5]},
        'deterioration_time_choices_h':[46.,48.,50.],'decision_h':52.,'horizon_h':96.,'actions':ACTIONS,
        'measurement_policy':'DO every0.2h with assumedSD0.15mg/L; P every12h,4h delay,assumedSD0.03g/L; one extra ideal P assay4h delay and20assumed work minutes. No perfect substrate or complete initial state.',
        'limits':'Simulated DO>=2mg/L; no measured product-quality conclusion. Stop counts zero product; earlier violations remain counted.',
        'analysis':'Report separate violation duration/deficit, mass, concentration, volume, unnecessary stops, decision/measurement time, tool/model calls, completion. No combined score. Average repetitions within scenario; paired scenario bootstrap20000 draws for descriptive contrasts. No sample extension.',
        'failures':'Retain every selected scenario including numerical-domain failures and failed submissions. No infrastructure retries in primary study. No failures relabeled as correct stops.',
        'bounds_of_claim':'Exploratory synthetic study; fixed initial/control family; model/evaluator share equations. Restricted research SDK, not end-to-end production OS validation.',
        'paths':paths,'code_sha256':{str(f.resolve()):sha(f) for f in files},'source_qualification_sha256':sha(source),
        'system_prompt_sha256':hashlib.sha256(SYSTEM.encode()).hexdigest(),'wall_seconds':180,'model_calls':10,'tool_calls':12,'max_output_tokens':8192}
    dump(root/'protocol.json',protocol);shutil.copy2(source,root/'source-qualification.json')
    for f in files:
        dest=root/'frozen-source'/f.parent.name/f.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
    print(json.dumps({'frozen':True,'scenarios':36,'planned_AI_sessions':144}),flush=True)


def generate(root):
    p=json.loads((root/'protocol.json').read_text())
    assert all(sha(f)==h for f,h in p['code_sha256'].items())
    rng=np.random.default_rng(p['sampling_seed']);items=[]
    for i in range(p['independent_scenarios']):
        stratum=p['strata'][i%3];lo,hi=p['transfer_multiplier_ranges'][stratum]
        hidden={'seed':31001+i,'factors':{k:float(rng.uniform(*bounds)) for k,bounds in p['receiving_factor_ranges'].items()},
            'transfer_multiplier':float(rng.uniform(lo,hi)),'disturbance_h':float(rng.choice(p['deterioration_time_choices_h'])),
            'decision_h':p['decision_h'],'kinetics_reference':'seed0'}
        item={'case_id':f'PI-{31001+i}','stratum':stratum,'hidden':hidden}
        dump(root/'private-cases'/(item['case_id']+'.json'),item);items.append(item)
    dump(root/'private-catalogue.json',items)


def job(root,item,repeat):
    root=Path(root);p=json.loads((root/'protocol.json').read_text());q=json.loads((root/'source-qualification.json').read_text())
    rows=q['source_measurements'];fit=q['final_source_fit'];paths=p['paths'];case=item['case_id'];records=[]
    order=['A','B'] if (item['hidden']['seed']+repeat)%2 else ['B','A']
    try:
        reference=outcomes(simulate(paths,**item['hidden'],action='keep'))
    except Exception as e:
        receipt={'case_id':case,'repeat':repeat,'stratum':item['stratum'],'status':'numerical_domain_failure','error':str(e),'records':[]}
        dump(root/'cases'/case/f'repeat-{repeat}.json',receipt);return receipt
    truths={}
    for arm in order:
        out=root/'attempts'/case/f'repeat-{repeat}'/arm
        try:
            s=InterventionSession(paths,item['hidden'],rows,predictor=SensitivityReceivingModel(paths,fit) if arm=='B' else None)
            r=attempt(s,arm,p['model'],out,wall_seconds=p['wall_seconds'])
            if r['evaluation']:
                e=r['evaluation'];clock=e['proposal']['decision_time_h']
                if clock not in truths:
                    truths[clock]={}
                    for a in ACTIONS:
                        try:truths[clock][a]=outcomes(simulate(paths,**dict(item['hidden'],decision_h=clock),action=a))
                        except Exception as exc:truths[clock][a]={'post_decision_feasible':False,'model_domain_failure':str(exc)}
                # Unknown domain outcomes cannot establish correct stopping.
                if any('model_domain_failure' in v for v in truths[clock].values()):
                    e['stop_adjudication']='unknown_due_to_action_domain_failure'
                else:e.update(stop_classification(e['proposal']['action_id'],truths[clock]))
            r.update(case_id=case,repeat=repeat,stratum=item['stratum']);records.append(r)
        except Exception as exc:
            out.mkdir(parents=True,exist_ok=True)
            r={'case_id':case,'repeat':repeat,'arm':arm,'stratum':item['stratum'],'status':'runner_failure','error':str(exc),'evaluation':None}
            dump(out/'runner-error.json',{'error':str(exc),'traceback':traceback.format_exc()});records.append(r)
    receipt={'case_id':case,'repeat':repeat,'stratum':item['stratum'],'status':'attempted','original_recipe':reference,'records':records,'private_action_replays_by_clock':truths}
    dump(root/'cases'/case/f'repeat-{repeat}.json',receipt);return receipt


def execute(root):
    root=root.resolve();p=json.loads((root/'protocol.json').read_text())
    assert all(sha(f)==h for f,h in p['code_sha256'].items())
    repo=Path(__file__).resolve().parents[3];load_env_file(repo/'backend/.env.local')
    dump(root/'isolation.json',isolation(root,root/'isolation'/'scratch'))
    if not (root/'private-catalogue.json').exists():generate(root)
    items=json.loads((root/'private-catalogue.json').read_text());results=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        pending=[pool.submit(job,str(root),item,r) for r in range(1,p['repeats']+1) for item in items]
        for future in as_completed(pending):
            results.append(future.result());dump(root/'results.json',{'status':'running','cases':results})
            print(json.dumps({'case_repetitions_finished':len(results),'planned':len(pending)}),flush=True)
    dump(root/'results.json',{'status':'complete','cases':results,'protocol':p})
    print(json.dumps({'status':'complete','case_repetitions':len(results)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','execute']);p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    (freeze if a.phase=='freeze' else execute)(a.root)
