"""Input boundaries and independent numerical checks before inference."""
from pathlib import Path
import argparse,json
import numpy as np
from .experiment import checked,dump,sha
from .challenges import common,run_action,response,values,score
from .treatments import assert_no_supplied_model


def verify(dataset,out):
    p=checked(dataset,'protocol.json');checks=[];catalogue=checked(dataset,'public/catalogue.json')
    for item in catalogue:
        case=item['case_id'];full=checked(dataset,f'public/{case}/packet.json');public=common(full)
        assert_no_supplied_model(public)
        assert 'source_calibration' not in public and 'seed' not in public
        assert all(r['time_h']<=full['decision_time_h']+1e-8 for r in public['receiving_observations'])
        assert full['task']!='transfer' or public['receiving_observations']==[]
        assert all(t['time_h']>full['decision_time_h'] for t in full['forecast_targets'].values())
        truth=checked(dataset,f'evaluator/{case}/truth.json')
        if p.get('require_source_admission'):
            from .challenges import admit_source,pen_scenario,thinning
            admit_source({'audit':full['source_simulation_audit']})
            if full['simulator']=='pensim' and full['task']=='prediction':
                if full.get('oxygen_policy')=='continuous_nonnegative_ODE':
                    from .oxygen import run_continuous
                    source=run_continuous(p['paths'],pen_scenario,p['paths'],truth['seed'],full['source_operating_plan'])
                else:source=pen_scenario(p['paths'],truth['seed'],full['source_operating_plan'])
                admit_source(source)
                assert thinning(source)==full['source_history']
                assert source['audit']==full['source_simulation_audit']
                checks.append({'case':case,'passed':True,'check':'completed_source_replay_and_admission'})
        actual=values(truth['complete_trajectories']['keep'],full['forecast_targets'])
        assert truth['forecasts']==actual
        if full['task']!='prediction':
            decision={'action_id':'abstain','predictions':truth['forecasts']}
            s=score(public,truth,decision)
            assert s['decision_score'] in (0.,1.)
        checks.append({'case':case,'passed':True,'checks':['model_isolation','receiving_cutoff','exact_future_clocks','KEEP_targets','abstention_scoring']})
    for sim in ('pensim','mab'):
        for task in ('prediction','transfer'):
            item=next(i for i in catalogue if i['simulator']==sim and i['task']==task)
            full=checked(dataset,f"public/{item['case_id']}/packet.json")
            library=checked(dataset,f"model-library/{item['case_id']}/nominal.json")
            # Nominal worker execution never reads evaluator paths or true seeds.
            base=run_action(full,'keep',p['paths'],nominal=True)
            live=response(full,'keep',base)
            assert live['predictions']==library['keep']['predictions']
            alternate=run_action(full,'keep',p['paths'],nominal=True,rtol=1e-8,solver='python' if sim=='pensim' else 'Radau')
            b=values(base,full['forecast_targets']);a=values(alternate,full['forecast_targets'])
            discrepancy=max(abs(a[k]-b[k])/max(abs(b[k]),1e-9) for k in b)
            assert discrepancy<.005
            checks.append({'case':item['case_id'],'passed':True,'check':'live_cache_and_independent_solver','maximum_relative_discrepancy':discrepancy})
    assert all(sha(f)==digest for f,digest in p['frozen_model_files_sha256'].items())
    dump(out,{'passed':True,'case_packets':len(catalogue),'coverage_failures':checked(dataset,'coverage-failures.json'),
        'model_files_unchanged':True,'checks':checks,'scope':'Input/numerical implementation gates, not independent experimental accuracy.'})
    print(json.dumps({'passed':True,'case_packets':len(catalogue),'checks':len(checks)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();verify(a.dataset,a.output)
