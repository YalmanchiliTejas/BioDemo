"""One explicitly development-only four-way workflow replay; no final claim."""
from pathlib import Path
import argparse,json
from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile
from benchmarks.external_simulators.experiment import checked,dump
from benchmarks.external_simulators.run_agents import isolation
from .pensim import simulate,observations,outcomes,optimizer,ACTIONS,stop_classification
from .session import InterventionSession
from .model import ReceivingModel
from .run_agents import attempt


def run(output):
    if output.exists():raise ValueError('Fresh development output required')
    output.mkdir(parents=True)
    root=Path(__file__).resolve().parents[3]
    load_env_file(root/'backend/.env.local');p=hosted_research_profile()
    if p is None:raise ValueError('No saved research profile')
    paths=checked(root/'backend/results/external-simulators/model-repair-continuous-20261028/dataset','protocol.json')['paths']
    source=simulate(paths,seed=0,factors={'kla_factor':1.,'growth_factor':1.,'production_factor':1.},transfer_multiplier=1.,decision_h=52.)
    source_rows=observations(source,100.,noise_seed=42001)
    fit=json.loads((root/'backend/results/interventions/development-20261029/model-optimizer-demo.json').read_text())['source_fit']
    hidden={'seed':21002,'factors':{'kla_factor':.95,'growth_factor':1.03,'production_factor':.97},'transfer_multiplier':.5,'decision_h':52.}
    dump(output/'protocol.json',{'scope':'Development case already inspected. Not frozen final evaluation; no efficacy claim. Restricted research SDK, not an end-to-end production OS integration.','model':p.provider+'/'+p.model,'hidden_host_only':hidden,'source_fit':fit})
    dump(output/'isolation.json',isolation(root/'backend/results/external-simulators/model-repair-continuous-20261028/dataset',output/'isolation'/'scratch'))
    results={}
    for arm in ['A','B']:
        s=InterventionSession(paths,hidden,source_rows,predictor=ReceivingModel(paths,fit) if arm=='B' else None)
        results[arm]=attempt(s,arm,p.provider+'/'+p.model,output/arm)
        print(json.dumps({'arm':arm,'status':results[arm]['status']}),flush=True)
    s=InterventionSession(paths,hidden,source_rows,predictor=ReceivingModel(paths,fit))
    predicted={a:s.predict(a)['outcome_prediction'] for a in ACTIONS}
    action=optimizer(predicted)
    results['model_optimizer']=s.recommend(action,rationale='Maximum predicted feasible product mass on same menu.',uncertainty='Effective receiver model, not truth.',evidence=['source assays','current receiving DO'])
    results['original_recipe']=outcomes(simulate(paths,**hidden,action='keep'))
    # Ground truth recoverability is evaluated AFTER commitments and never sent to the approaches.
    truths={}
    for label in ['A','B','model_optimizer']:
        e=results[label]['evaluation'] if label in ['A','B'] else results[label]
        if not e:continue
        clock=e['proposal']['decision_time_h']
        if clock not in truths:
            config=dict(hidden,decision_h=clock)
            truths[clock]={a:outcomes(simulate(paths,**config,action=a)) for a in ACTIONS}
        e.update(stop_classification(e['proposal']['action_id'],truths[clock]))
    dump(output/'results.json',{'classification':'development_workflow_demonstration_not_final_benchmark','results':results,'private_action_replays_by_clock':truths})
    print(json.dumps({'status':'complete','output':str(output)}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output.resolve())
