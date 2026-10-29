"""A separate report of every new challenge result, with independent checks."""
from pathlib import Path
from collections import defaultdict
import argparse,csv,json,os
import numpy as np
from .experiment import checked,dump,sha
from .challenges import values,common


def boot(a,b,ratio=False):
    a=np.array(a,dtype=float);b=np.array(b,dtype=float)
    rng=np.random.default_rng(20261028);indices=rng.integers(0,len(a),(20000,len(a)))
    aa=a[indices].mean(axis=1);bb=b[indices].mean(axis=1)
    samples=1-bb/np.maximum(aa,1e-12) if ratio else bb-aa
    effect=1-float(b.mean())/max(float(a.mean()),1e-12) if ratio else float((b-a).mean())
    return {'A':float(a.mean()),'B':float(b.mean()),'effect':effect,'interval95':np.quantile(samples,[.025,.975]).tolist(),'case_clusters':len(a)}


def analyze(dataset,run):
    result=json.loads((run/'results.json').read_text());protocol=checked(dataset,'protocol.json')
    records=result['records'];index={(r['case_id'],r['repeat'],r['arm']):r for r in records}
    checks=[];case_rows=[];forecast_rows=[];failures=[];tool_errors=[];physics_calls=0;physics_sessions=0;unavailable_audits=[]
    catalogue=checked(dataset,'public/catalogue.json');mapping={}
    for item in catalogue:
        case=item['case_id'];full=checked(dataset,f'public/{case}/packet.json');truth=checked(dataset,f'evaluator/{case}/truth.json');mapping[case]=(full,truth)
        expected=values(truth['complete_trajectories']['keep'],full['forecast_targets'])
        if full.get('forecast_contract_version')==2:
            from .forecast_contract import evidence_hash
            checks.append({'check':'frozen_case_source_calibration','case':case,'passed':evidence_hash(full['source_calibration'])==protocol['case_calibration_sha256'][case]})
        else:
            checks.append({'check':'frozen_calibration','case':case,'passed':full['source_calibration']==protocol['frozen_calibrations'][item['simulator']]})
        checks.append({'check':'forecast_targets_from_KEEP_trace','case':case,'passed':expected==truth['forecasts']})
        checks.append({'check':'cutoff','case':case,'passed':all(r['time_h']<=full['decision_time_h']+1e-8 for r in full['receiving_observations']) and (full['task']!='transfer' or not full['receiving_observations'])})
        per_arm={a:[] for a in ('A','B')};forecasts={a:[] for a in ('A','B')}
        target_errors={key:{a:[] for a in ('A','B')} for key in full['forecast_fields']}
        decision_detail={arm:{'failed':0,'invalid':0,'correct_abstention':0,'unnecessary_abstention':0,'feasible':0,'qualified_objective_changes':[]} for arm in ('A','B')}
        for repeat in range(1,result['protocol']['repeats']+1):
            pair={arm:index.get((case,repeat,arm)) for arm in ('A','B')}
            pair_complete=all(r and r['score'] for r in pair.values())
            if all(pair.values()):
                ap=run/'attempts'/case/f'repeat-{repeat:02d}'/'A/agent-input/packet.json'
                bp=run/'attempts'/case/f'repeat-{repeat:02d}'/'B/agent-input/packet.json'
                checks.append({'check':'identical_common_inputs','case':case,'repeat':repeat,'passed':ap.read_bytes()==bp.read_bytes() and json.loads(ap.read_text())==common(full)})
                ca,cb=(pair[a]['capability_audit'] for a in ('A','B'))
                if ca and cb:
                    checks.append({'check':'same_shared_schema','case':case,'repeat':repeat,'passed':ca['shared_tool_schema_sha256']==cb['shared_tool_schema_sha256']})
                elif pair_complete:
                    checks.append({'check':'completed_pair_must_have_schema_audit','case':case,'repeat':repeat,'passed':False})
                else:unavailable_audits.append({'case':case,'repeat':repeat,'audit':'SDK shared schema unavailable for failed session'})
            feasible={a:v for a,v in truth['actions'].items() if a!='abstain' and v.get('feasible')}
            best=max((v['objective'] for v in feasible.values()),default=0.)
            for arm,r in pair.items():
                if r is None or not r['score']:
                    per_arm[arm].append(0.);decision_detail[arm]['failed']+=1
                    if r:failures.append({key:r.get(key) for key in ('case_id','repeat','arm','status','error')})
                    continue
                s=r['score'];choice=r['submission']['action_id'];action=truth['actions'][choice]
                # Reconstruct the constrained objective without calling scorer.
                expected_score=(action['objective']/best if choice in feasible and best>0 else float(choice=='abstain' and not feasible))
                checks.append({'check':'independent_decision_arithmetic','case':case,'repeat':repeat,'arm':arm,'passed':np.isclose(expected_score,s['decision_score'],rtol=1e-12)})
                per_arm[arm].append(expected_score)
                for label,field in [('invalid','invalid_decision'),('correct_abstention','correct_abstention'),('unnecessary_abstention','unnecessary_abstention'),('feasible','feasible_choice')]:decision_detail[arm][label]+=int(s[field])
                if s['objective_change_is_qualified']:decision_detail[arm]['qualified_objective_changes'].append(s['objective_change_percent'])
                errors=[]
                for field in full['forecast_fields']:
                    predicted=r['submission']['predictions'][field];actual=expected[field];scale=truth['normalization_scales'][field]
                    error=abs(predicted-actual)/scale
                    checks.append({'check':'independent_forecast_arithmetic','case':case,'repeat':repeat,'arm':arm,'field':field,'passed':np.isclose(error,s['prediction_errors'][field]['normalized_absolute_error'],rtol=1e-12)})
                    if pair_complete:target_errors[field][arm].append(error);errors.append(error)
                if pair_complete:forecasts[arm].append(float(np.mean(errors)))
        case_rows.append({'case_id':case,'seed':truth['seed'],'simulator':item['simulator'],'task':item['task'],'stratum':full['stratum'],
            'decision_A':float(np.mean(per_arm['A'])),'decision_B':float(np.mean(per_arm['B'])),
            'forecast_A':float(np.mean(forecasts['A'])) if forecasts['A'] else None,'forecast_B':float(np.mean(forecasts['B'])) if forecasts['B'] else None,
            'completed_pairs':len(forecasts['A']),'no_feasible_process_action':not bool(feasible),'decision_details':decision_detail,
            'qualified_grid_actions':sum(v.get('qualified',False) for a,v in truth['actions'].items() if a!='abstain'),
            'unqualified_grid_actions':sum(not v.get('qualified',False) for a,v in truth['actions'].items() if a!='abstain')})
        for field,t in full['forecast_targets'].items():
            if target_errors[field]['A']:
                forecast_rows.append({'case_id':case,'seed':truth['seed'],'simulator':item['simulator'],'task':item['task'],'stratum':full['stratum'],'field':field,'state':t['state'],'time_h':t['time_h'],'unit':t['unit'],
                    'A':float(np.mean(target_errors[field]['A'])),'B':float(np.mean(target_errors[field]['B']))})
    for r in records:
        calls=json.loads((run/'attempts'/r['case_id']/f"repeat-{r['repeat']:02d}"/r['arm']/'tools.json').read_text())
        physics=[c for c in calls if c['name']=='physical_forward_model'];physics_calls+=len(physics);physics_sessions+=int(bool(physics))
        if not r.get('tool_history_unavailable'):
            checks.append({'check':'A_cannot_use_physics','case':r['case_id'],'repeat':r['repeat'],'arm':r['arm'],'passed':not physics if r['arm']=='A' else True})
        else:unavailable_audits.append({'case':r['case_id'],'repeat':r['repeat'],'arm':r['arm'],'audit':'Tool history unavailable for failed session'})
        tool_errors.extend({'case':r['case_id'],'repeat':r['repeat'],'error':c['result']['error']} for c in physics if 'error' in c['result'])
    for p,digest in protocol['frozen_model_files_sha256'].items():checks.append({'check':'frozen_physical_model','file':p,'passed':sha(p)==digest})
    for c in checks:c['passed']=bool(c['passed'])
    primary=[];strata=[]
    for sim in ('pensim','mab'):
        for task in ('prediction','outcome','transfer'):
            for stratum in ('all','ordinary','challenge'):
                rows=[r for r in case_rows if r['simulator']==sim and r['task']==task and (stratum=='all' or r['stratum']==stratum)]
                if task=='prediction':
                    rows=[r for r in rows if r['forecast_A'] is not None];a=[r['forecast_A'] for r in rows];b=[r['forecast_B'] for r in rows]
                else:a=[r['decision_A'] for r in rows];b=[r['decision_B'] for r in rows]
                if not a:continue
                summary={'simulator':sim,'task':task,'stratum':stratum,**boot(a,b,ratio=task=='prediction')}
                threshold=.2 if task=='prediction' else .05
                summary.update(minimum_useful_effect=threshold,criterion_met=summary['interval95'][0]>threshold)
                (primary if stratum=='all' else strata).append(summary)
    target_summaries=[]
    for sim in ('pensim','mab'):
        for task in ('prediction','outcome','transfer'):
            fields=sorted({r['field'] for r in forecast_rows if r['simulator']==sim and r['task']==task})
            for field in fields:
                rows=[r for r in forecast_rows if r['simulator']==sim and r['task']==task and r['field']==field]
                target_summaries.append({'simulator':sim,'task':task,'field':field,'time_h':rows[0]['time_h'],'state':rows[0]['state'],'unit':rows[0]['unit'],**boot([r['A'] for r in rows],[r['B'] for r in rows],ratio=True)})
    coverage=checked(dataset,'coverage-failures.json')
    return {'status':result['status'],'protocol':protocol,'planned_attempts':protocol['planned_agent_attempts'],'attempted':len(records),'completed':result['completed'],
        'failures':failures,'coverage_failures':coverage,'primary':primary,'strata':strata,'targets':target_summaries,'cases':case_rows,'case_target_errors':forecast_rows,
        'physics_sessions':physics_sessions,'physics_calls':physics_calls,'physics_tool_errors':tool_errors,'unavailable_audits':unavailable_audits,'checks':checks,'all_checks_pass':all(c['passed'] for c in checks),
        'all_three_criterion_met':all(p['criterion_met'] for p in primary) and len(primary)==6 and not coverage and result['completed']/protocol['planned_agent_attempts']>=.95,
        'analysis_plan':json.loads((run.parent/'analysis-plan.json').read_text()),
        'transport_recovery':result.get('transport_recovery')}


def save_csv(path,rows,fields):
    with path.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)


def write(dataset,run,output):
    output.mkdir(parents=True,exist_ok=True);data=analyze(dataset,run)
    if data['status']!='complete':raise ValueError('Cannot publish a completed report of an unfinished run')
    if not data['all_checks_pass']:raise ValueError('Audit check failed; report blocked')
    dump(output/'analysis.json',data)
    save_csv(output/'case-results.csv',data['cases'],['case_id','seed','simulator','task','stratum','decision_A','decision_B','forecast_A','forecast_B','completed_pairs','no_feasible_process_action','qualified_grid_actions','unqualified_grid_actions'])
    save_csv(output/'all-forecast-targets.csv',data['targets'],['simulator','task','field','state','time_h','unit','A','B','effect','interval95','case_clusters'])
    name={'pensim':'PenSimPy','mab':'SMPL upstream'}
    lines=['# AI with and without physics: operating challenges','','28 October 2026. A new experiment set, using frozen physical models. Result tables here contain only this new set; every new outcome is included. Earlier studies remain preserved separately.','','## What this run establishes','',
        f"Completed **{data['completed']:,}/{data['planned_attempts']:,}** planned agent attempts; {len(data['failures'])} failed submissions; {len(data['coverage_failures'])} unscorable selected task cases.",
        '',('The new suite meets its exploratory all-three improvement criterion.' if data['all_three_criterion_met'] else '**The new suite does not establish improvement in all three aspects under its stated criterion.**'),
        '', 'This is controlled simulation evidence. The physics tool and evaluator share equations, so success does not establish real manufacturing accuracy or real site-transfer readiness. No real CHO measurements were tested in this new run.',
        '', '![New challenge results](comparison.png)', '', '## Main results', '',
        'A is the configured AI without a supplied physics model. B is the same AI plus a live physics tool. Both receive identical raw observations, source history, plans, limits, units, ordinary numerical Python and request budgets.', '',
        '| Process | Aspect | AI alone A | AI + physics B | Benefit [95% case-bootstrap interval] | Cases | Criterion met? |',
        '|---|---|---:|---:|---:|---:|---|']
    for row in data['primary']:
        prediction=row['task']=='prediction';a=100*row['A'];b=100*row['B'];effect=100*row['effect'];lo,hi=[100*v for v in row['interval95']]
        label='Forecast error (% source scale; lower better)' if prediction else ('Operating decision score (0–100; higher better)' if row['task']=='outcome' else 'Recipe adaptation score (0–100; higher better)')
        suffix='% relative error reduction' if prediction else ' score points'
        lines.append(f"| {name[row['simulator']]} | {label} | {a:.3f} | {b:.3f} | {effect:.3f}{suffix} [{lo:.3f}, {hi:.3f}] | {row['case_clusters']} | {'Yes' if row['criterion_met'] else 'No'} |")
    lines+=['','Forecast error averages both variables at three future times, normalized by each variable’s visible completed-source median. Forecast benefit is relative error reduction. Only completed paired sessions have numerical forecast errors; failures remain in completion counts. Decision scores include failed submissions as zero. The stated useful-effect thresholds are 20% error reduction and 5 score points for each decision aspect; the interval lower bound must exceed the threshold. The all-three claim requires all aspects in both processes to pass, at least 95% completion, and no unscorable selected cases.','','The score rewards a feasible plan’s product relative to the best feasible plan in the fixed private grid. An invalid plan scores zero. Correct abstention scores 100 only when no process plan can meet the study limits; abstention produces no product. Thus higher decision score must not be described as the same percentage increase in manufacturing production.','','## Experiment setup','','- 48 new seeded situations per simulator, seeds 7001–7048; each supplies prediction, outcome and transfer tasks. Two independent AI sessions per arm/task: 288 task packets and 1,152 planned attempts. Repetitions are nested inside situation clusters. These are simulated situations with repeated factorial regimes, not 96 biological experiments.','- Every fourth case is an ordinary comparison; the rest involve declared changes/constraints. All selected cases are retained without resampling until a favorable result appears.','- PenSim: changed sugar/aeration plans after 60 h, forecasts at 64/72/96 h. Decisions choose materially different allowed plans. The endpoint is penicillin concentration, not recovered mass or full-batch yield.','- SMPL: balanced throughput and nutrient plans, forecasts at 8/12/24 h. Operating decisions begin at 6 h; transfer plans begin at 0 h. Its 17-state upstream reactor/separator is used; harvested product is the external separator outflow integral in mg.','- Each session commits one plan from a finite grid. Its consequences are scored against trajectories frozen before inference and hidden until submission; this is not continuous closed-loop control.', '- Transfer has no receiving observations. It changes permitted operating/resource plans at fixed geometry/biology. SMPL explicitly shares the measured source initial inoculum with the receiver; this optimistic assumption is given to both arms. PenSim source and receiver also share a latent material/disturbance seed, so their prechange paths can be identical; this is not independent receiving-site variability. This is a simulated recipe-adaptation proxy.','- Command limits are permitted-plan/resource requirements. KEEP forecasts may be counterfactual where KEEP violates those requirements. They are not measurements of an executable/approved plan, and no additional actuator-saturation law is modeled.','- Existing equations, coefficients, native corrections and earlier calibration values are frozen. No fitting or parameter tuning was performed. Calibration comes deterministically from the first prior prediction case in catalogue order for each process. It may fit a new situation poorly; it was not chosen using new outcomes. SMPL’s observed source initial state is an ordinary scenario input.','- Tool/evaluator action meanings match. B’s live worker receives no realization seed, receiving future, outcome table or optimal-action ranking. Its predictions are checked against frozen nominal records.','','## Every forecast target','','Lower source-normalized error is better. This table includes all targets for the prediction task; the downloadable CSV includes all targets in all three tasks.','','| Process | Variable | Time (h) | A error (% source scale) | B error (% source scale) | Error reduction (%) |','|---|---|---:|---:|---:|---:|']
    for r in sorted(data['targets'],key=lambda r:(r['simulator'],r['state'],r['time_h'])):
        if r['task']!='prediction':continue
        var='Product' if r['state'] in ('P','mAb_reactor') else ('Oxygen' if r['state']=='DO2' else 'Viable cells')
        lines.append(f"| {name[r['simulator']]} | {var} | {r['time_h']:g} | {100*r['A']:.3f} | {100*r['B']:.3f} | {100*r['effect']:.3f} |")
    lines+=['','## Ordinary versus challenge cases','','Both predeclared strata are reported; neither is discarded to improve the headline. Benefit is forecast-error reduction or change in decision-score points.','','| Process | Task | Stratum | Cases | Benefit | 95% interval |','|---|---|---|---:|---:|---|']
    for r in data['strata']:
        lines.append(f"| {name[r['simulator']]} | {r['task']} | {r['stratum']} | {r['case_clusters']} | {100*r['effect']:.3f} | [{100*r['interval95'][0]:.3f}, {100*r['interval95'][1]:.3f}] |")
    lines+=['','## Failures, infeasibility and model limits','','| Process / task | Arm | Failed submissions | Invalid decisions | Correct abstentions | Unnecessary abstentions | Feasible process choices |','|---|---|---:|---:|---:|---:|---:|']
    for sim in ('pensim','mab'):
        for task in ('outcome','transfer'):
            rows=[r for r in data['cases'] if r['simulator']==sim and r['task']==task]
            for arm in ('A','B'):
                totals={key:sum(r['decision_details'][arm][key] for r in rows) for key in ('failed','invalid','correct_abstention','unnecessary_abstention','feasible')}
                lines.append(f"| {name[sim]} / {task} | {arm} | {totals['failed']} | {totals['invalid']} | {totals['correct_abstention']} | {totals['unnecessary_abstention']} | {totals['feasible']} |")
    lines+=['','Oxygen-floor or raw invalid trajectories cannot become successful operating outcomes. Unqualified actions score zero even if the upstream simulator displays a higher product value. The complete 230 h viscosity defect remains unresolved; this report concerns only the declared 96 h partial process. SMPL’s tested nutrient terms are near saturation and some plans have obvious rankings; the benchmark does not establish that all its decisions are difficult. Study limits are not validated manufacturing safety/quality limits.','','Failed submissions are retained in [analysis.json](analysis.json). All case-level scores and grid qualification counts are in [case-results.csv](case-results.csv). All forecast targets, including negative effects, are in [all-forecast-targets.csv](all-forecast-targets.csv).','','## Verification and statistical limits','',
        f"{len(data['checks']):,} arithmetic, input and model-hash checks passed for the available records. B used physics in {data['physics_sessions']} sessions, with {data['physics_calls']} live queries and {len(data['physics_tool_errors'])} tool errors. Source snapshots, manifests, isolation probes, frozen inputs, tool/event logs and submissions are retained under backend/results/external-simulators/challenges-20261028.",
        '', 'The sample count and meaningful-effect thresholds were frozen before generating cases. The analysis addendum defining aggregation/bootstrap details was written after inference started but before inspection of any A/B scores; this was not independently preregistered. This is a fixed-sample exploratory report, not a power-qualified definitive demonstration. Confidence intervals resample whole synthetic case clusters with AI repetitions kept together; shared equations and repeated regimes limit generalization. No optional sample extension or favorable-target selection was performed.',
        '', f"{len(data['unavailable_audits'])} audit entries are unavailable for failed sessions and are listed in analysis.json. The original runner's per-pair exception handling could stop its combined progress update while other scheduled workers continued. Final totals are reconciled from durable original run receipts; lost/unknown results are conservatively failures, with no lost result imputed as a success. Fresh sessions in the explicitly declared paired recovery pass are separate attempts; prior session state is never reused. The original exception, incomplete summary and reconciliation receipt are preserved.", '', 'Checks establish numerical/software consistency and input isolation, not independent physical accuracy. Earlier empirical and simulator reports remain available in the [historical study](../physics-improvements-20261028/report.md); this new report does not retire or invalidate them. Model changes and new independent empirical validation remain separate future work.']
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    plot(data,output)
    dump(output/'provenance.json',{'dataset_manifest_sha256':sha(dataset/'manifest.json'),'run_results_sha256':sha(run/'results.json'),'analysis_plan_sha256':sha(run.parent/'analysis-plan.json'),'report_sha256':sha(output/'report.md'),'analysis_sha256':sha(output/'analysis.json')})
    return data


def plot(data,output):
    os.environ.setdefault('MPLCONFIGDIR','/private/tmp/biodemo-mpl-challenges')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(13,7))
    colors=['#476878','#be6e35']
    for i,sim in enumerate(('pensim','mab')):
        for j,task in enumerate(('prediction','outcome','transfer')):
            r=next(v for v in data['primary'] if v['simulator']==sim and v['task']==task);ax=axes[i,j]
            vals=[100*r['A'],100*r['B']];ax.bar(['AI alone','AI + physics'],vals,color=colors)
            ax.set_title(('PenSimPy' if sim=='pensim' else 'SMPL upstream')+' / '+task,loc='left',fontsize=11,fontweight='bold')
            ax.set_ylabel('Error (% source scale), lower better' if task=='prediction' else 'Decision score (0–100), higher better',fontsize=9)
            if task!='prediction':ax.set_ylim(0,110)
            else:ax.set_ylim(0,max(vals)*1.22)
            for k,v in enumerate(vals):ax.annotate(f'{v:.2f}',(k,v),xytext=(0,5),textcoords='offset points',ha='center',fontsize=10)
            ax.spines[['top','right']].set_visible(False);ax.yaxis.grid(True,alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('New operating challenges: paired transport-recovery analysis' if data.get('transport_recovery') else 'New operating challenges: same AI, frozen physics models',x=.04,ha='left',fontsize=15,fontweight='bold')
    fig.text(.04,.02,f"{data['completed']:,}/{data['planned_attempts']:,} comparison slots scored. 48 simulated case clusters/process; two AI repetitions.\nSecondary recovery view; original batch completed 1,004/1,152 attempts. Decision scores include correct abstention, not percentage production gain.",fontsize=9,color='#46545a')
    fig.tight_layout(rect=(.02,.09,.99,.93));fig.savefig(output/'comparison.png',dpi=160);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();write(a.dataset,a.run,a.output)
