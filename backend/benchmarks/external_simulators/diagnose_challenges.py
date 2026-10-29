"""Read-only causal diagnostics on the inspected challenge study; no new AI runs.

Diagnostic comparisons are retrospective development evidence, not new A/B results.
"""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,json
import numpy as np
from .experiment import checked,dump,sha
from .challenges import run_action,values


def mean(values):return float(np.mean(values)) if values else None

def diagnose(root,out):
    out.mkdir(parents=True,exist_ok=True)
    dataset=root/'dataset';run=root/'paired-recovery-view';result=json.loads((run/'results.json').read_text())
    protocol=checked(dataset,'protocol.json');records={(r['case_id'],r['repeat'],r['arm']):r for r in result['records']}
    case_rows=[];fields=[];state_checks=[];decisions=defaultdict(list);examples=[];allchecks=[]
    # One fixed nominal prechange path. All PenSim plans are identical through60h.
    catalogue=checked(dataset,'public/catalogue.json')
    pen_item=next(i for i in catalogue if i['simulator']=='pensim' and i['task']=='prediction')
    pen_full=checked(dataset,f"public/{pen_item['case_id']}/packet.json")
    pen_nominal=run_action(pen_full,'keep',protocol['paths'],nominal=True)
    nominal60=next(r['state'] for r in pen_nominal['trace'] if abs(r['time_h']-60.)<1e-8)
    for item in catalogue:
        case=item['case_id'];sim=item['simulator'];task=item['task']
        full=checked(dataset,f'public/{case}/packet.json');truth=checked(dataset,f'evaluator/{case}/truth.json')
        library=checked(dataset,f'model-library/{case}/nominal.json');supplied=library['keep']['predictions'];cal=full['source_calibration']
        raw={k:(v/cal['product_ratio'] if full['forecast_targets'][k]['state'] in ('P','mAb_reactor') else v-cal['indicator_offset']) for k,v in supplied.items()}
        scales=truth['normalization_scales'];actual=values(truth['complete_trajectories']['keep'],full['forecast_targets'])
        assert actual==truth['forecasts']
        target_values={k:{'tool':abs(supplied[k]-actual[k])/scales[k],'before_output_bias':abs(raw[k]-actual[k])/scales[k],'A':[],'B':[]} for k in actual}
        row={'case':case,'simulator':sim,'task':task,'tool_error':mean([v['tool'] for v in target_values.values()]),
            'same_ODE_before_endpoint_bias_error':mean([v['before_output_bias'] for v in target_values.values()]),'A_errors':[],'B_errors':[]}
        for repeat in (1,2):
            pair={arm:records[(case,repeat,arm)] for arm in ('A','B')}
            complete=all(r['score'] is not None for r in pair.values())
            for arm,r in pair.items():
                if task!='prediction':
                    if r['score'] is None:category='submission_failure';loss=1.
                    else:
                        s=r['score'];category=('invalid_plan' if s['invalid_decision'] else 'unnecessary_abstention' if s['unnecessary_abstention'] else 'feasible_product_regret' if s['feasible_choice'] else 'correct_abstention')
                        loss=1-s['decision_score']
                    decisions[(sim,task,arm)].append({'case':case,'repeat':repeat,'category':category,'loss':loss,
                        'score':r['score'],'record_status':r['status']})
                if not complete:continue
                errors=[];tool_distance=[]
                for k in actual:
                    prediction=r['submission']['predictions'][k];error=abs(prediction-actual[k])/scales[k]
                    assert np.isclose(error,r['score']['prediction_errors'][k]['normalized_absolute_error'],rtol=1e-12)
                    errors.append(error);target_values[k][arm].append(error);tool_distance.append(abs(prediction-supplied[k])/scales[k])
                row[f'{arm}_errors'].append(mean(errors))
                if arm=='B':
                    example={'case':case,'repeat':repeat,'simulator':sim,'task':task,'AI_error':mean(errors),'tool_error':row['tool_error'],
                        'degradation_vs_tool':mean(errors)-row['tool_error'],'distance_from_KEEP_tool':mean(tool_distance),
                        'action':r['submission']['action_id'],'rationale':r['submission']['rationale'],'uncertainty':r['submission']['uncertainty'],
                        'KEEP_tool_predictions':supplied,'submission':r['submission']['predictions'],'actual':actual}
                    if r['submission']['action_id']!='abstain' and r['submission']['action_id'] in library:
                        chosen=library[r['submission']['action_id']].get('predictions',{})
                        if set(chosen)==set(actual):example['distance_from_selected_action_tool']=mean([abs(r['submission']['predictions'][k]-chosen[k])/scales[k] for k in actual])
                    examples.append(example)
            if task!='prediction' and complete:
                a,b=(pair[arm]['score'] for arm in ('A','B'))
                if a['feasible_choice'] and b['feasible_choice']:
                    row.setdefault('both_feasible_product_gain_percent',[]).append(100*(b['objective']/a['objective']-1))
        row['A_error']=mean(row.pop('A_errors'));row['B_error']=mean(row.pop('B_errors'));case_rows.append(row)
        for key,v in target_values.items():
            fields.append({'case':case,'simulator':sim,'task':task,'field':key,'state':full['forecast_targets'][key]['state'],'time_h':full['forecast_targets'][key]['time_h'],
                'tool_error':v['tool'],'same_ODE_before_endpoint_bias_error':v['before_output_bias'],'A_error':mean(v['A']),'B_error':mean(v['B'])})
        if sim=='pensim' and task=='prediction':
            obs=full['receiving_observations'][-1];assert abs(obs['time_h']-60.)<1e-8
            comparisons={}
            for state in ('P','DO2','S'):
                nominal=nominal60[state];nominal=nominal*cal['product_ratio'] if state=='P' else nominal+cal['indicator_offset'] if state=='DO2' else nominal
                comparisons[state]={'observed':obs['state'][state],'nominal_tool_at_cutoff':nominal,
                    'relative_error':abs(nominal-obs['state'][state])/max(abs(obs['state'][state]),1e-9)}
            state_checks.append({'case':case,'time_h':60.,'values':comparisons})
    summary=[];target_summary=[]
    for sim in ('pensim','mab'):
        for task in ('prediction','outcome','transfer'):
            rows=[r for r in case_rows if r['simulator']==sim and r['task']==task and r['A_error'] is not None]
            summary.append({'simulator':sim,'task':task,'cases':len(rows),**{key:mean([r[key] for r in rows]) for key in ('A_error','B_error','tool_error','same_ODE_before_endpoint_bias_error')},
                'both_feasible_product_gain_percent':mean([v for r in rows for v in r.get('both_feasible_product_gain_percent',[])])})
            for key in sorted({r['field'] for r in fields if r['simulator']==sim and r['task']==task}):
                rows2=[r for r in fields if r['simulator']==sim and r['task']==task and r['field']==key and r['A_error'] is not None]
                target_summary.append({'simulator':sim,'task':task,'field':key,'time_h':rows2[0]['time_h'],**{k:mean([r[k] for r in rows2]) for k in ('A_error','B_error','tool_error','same_ODE_before_endpoint_bias_error')}})
    decomposition=[]
    for (sim,task,arm),rows in decisions.items():
        losses={kind:sum(r['loss'] for r in rows if r['category']==kind)/len(rows) for kind in ('submission_failure','invalid_plan','unnecessary_abstention','feasible_product_regret')}
        score=mean([r['score']['decision_score'] if r['score'] else 0. for r in rows])
        assert np.isclose(1-sum(losses.values()),score,rtol=1e-12)
        decomposition.append({'simulator':sim,'task':task,'arm':arm,'attempts':len(rows),'decision_score':score,
            'counts':dict(Counter(r['category'] for r in rows)),'score_loss_by_cause':losses})
    # Direct numerical replay verifies that inverse calibration is not a posthoc
    # algebra coincidence. Same measured initial state / inputs, no test fitting.
    for stratum,task in (('ordinary','prediction'),('challenge','prediction'),('challenge','transfer')):
        item=next(i for i in catalogue if i['simulator']=='mab' and i['task']==task and checked(dataset,f"public/{i['case_id']}/packet.json")['stratum']==stratum)
        full=checked(dataset,f"public/{item['case_id']}/packet.json");truth=checked(dataset,f"evaluator/{item['case_id']}/truth.json")
        direct=values(run_action(full,'keep',protocol['paths'],nominal=True),full['forecast_targets'])
        discrepancy=max(abs(direct[k]-truth['forecasts'][k])/max(abs(truth['forecasts'][k]),1e-9) for k in direct)
        allchecks.append({'case':item['case_id'],'check':'matched_observed_initial_state_raw_ODE_replay','relative_discrepancy':discrepancy,'passed':discrepancy<1e-7})
    assert all(sha(p)==h for p,h in protocol['frozen_model_files_sha256'].items())
    selection=sorted([r for r in examples if r['task']=='prediction'],key=lambda r:r['degradation_vs_tool'],reverse=True)[:6]
    payload={'scope':'Retrospective diagnosis of inspected cases; no new AI runs, no model tuning, no replacement of original A/B results.',
        'summary':summary,'targets':target_summary,'PenSim_state_at_forecast_start':state_checks,'decision_score_decomposition':decomposition,
        'largest_agent_vs_tool_degradations':selection,'numerical_replays':allchecks,'physical_models_unchanged':True,'all_arithmetic_recomputed':True,
        'primary_forecast_only_KEEP':all(r['submission']['action_id']=='keep' for r in result['records'] if r['task']=='prediction' and r['submission']),
        'sources':{'dataset_manifest_sha256':sha(dataset/'manifest.json'),'run_results_sha256':sha(run/'results.json')},'cases':case_rows}
    dump(out/'diagnosis.json',payload)
    print(json.dumps({'summary':summary,'PenSim_cutoff_mean_relative_error':{k:mean([r['values'][k]['relative_error'] for r in state_checks]) for k in ('P','DO2','S')},'matched_state_replay':allchecks},indent=2))
    return payload

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();diagnose(a.root,a.output)
