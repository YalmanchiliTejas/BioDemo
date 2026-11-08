"""Publishable summaries from frozen receipts; never sends inference."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import statistics
import zipfile

from .campaign import ARMS, ROOT, read, verify
from benchmarks.lyo_study.run_agents import dump,digest

OUT=ROOT/'docs/research/lyohub-rerun-20261107'
PUBLIC=ROOT/'frontend/public/research-results/lyohub'


def metrics(rows):
    scores=[r['score'] for r in rows];n=len(rows)
    submitted=sum(s['execution_completed'] for s in scores)
    feasible=sum(s['selected_feasible'] for s in scores);unsafe=sum(s['unsafe_selection'] for s in scores)
    characterize=sum((r.get('submission') or {}).get('action_id')=='characterize' for r in rows)
    errors=[s['completion_absolute_error_h'] for s in scores if s['completion_absolute_error_h'] is not None]
    assert feasible+unsafe+characterize+(n-submitted)==n
    return {'planned':n,'submitted':submitted,'feasible':feasible,'unsafe':unsafe,'characterize':characterize,'failed':n-submitted,
        'completion_eligible':sum(s['completion_eligible'] for s in scores),'predictions':len(errors),
        'mae_h':statistics.mean(errors) if errors else None,
        'mean_throughput_vials_h':statistics.mean(s['throughput_vials_h'] for s in scores) if n else None,
        'mean_session_seconds':statistics.mean(r['wall_seconds'] for r in rows if r.get('wall_seconds') is not None) if n else None,
        'thermal':{k:sum(s['thermal']==k for s in scores) for k in ('TP','FP','FN','TN','abstain','censored','execution_failed')},
        'capacity':{k:sum(s['capacity']==k for s in scores) for k in ('TP','FP','FN','TN','abstain','censored','execution_failed')},
        'reference_thermal_positive':sum(s['truth']['thermal_warning'] is True for s in scores),
        'reference_capacity_positive':sum(s['truth']['capacity_warning'] is True for s in scores)}


def cost(base):
    path=base/'cost/modal-admission.jsonl'
    entries=[json.loads(line) for line in path.read_text().splitlines()]
    reservations={r['ordinal']:r for r in entries if r['event']=='reserved'}
    settled={r['ordinal']:r for r in entries if r['event']=='settled'}
    unknown=set(reservations)-set(settled)
    measured=sum(r['conservative_cost_usd'] for r in settled.values())
    held=sum(reservations[k]['reserved_usd'] for k in unknown)
    p=read(base/'cost/modal-budget-policy.json')
    assert measured+held<=p['maximum_campaign_reservation_usd']+1e-7
    return {'token_based_estimate_usd':measured,'unknown_reservations_usd':held,'conservative_accounting_usd':measured+held,
      'cap_usd':p['maximum_campaign_reservation_usd'],'requests_admitted':len(reservations),'requests_with_usage':len(settled),
      'requests_without_usage':len(unknown),'denied':sum(e['event']=='denied' for e in entries),
      'response_models':sorted({m for r in settled.values() for m in r.get('response_models',[])}),
      'input_tokens':sum(r['prompt_tokens'] for r in settled.values()),'output_tokens':sum(r['completion_tokens'] for r in settled.values()),
      'note':'Provider token counters at list rates; not an invoice; unknown requests retain full reservations; local solver compute and engineering excluded; shared-endpoint and admission-proxy queueing are included in session wall time',
      'ledger_sha256':digest(path),'policy':p}


def f(value):return '—' if value is None else f'{value:.2f}'


def report(base):
    base=Path(base).resolve();protocol=verify(base)
    from benchmarks.lyo_study.study import verify_dataset
    dataset_verification=verify_dataset(base/'frozen')
    agents=read(base/'agents/results.json')['records'];controls=read(base/'controls/results.json')
    expected={(c,t,a) for c in protocol['case_ids'] for t in protocol['tasks'] for a in ARMS}
    if {(r['case_id'],r['task'],r['arm']) for r in agents}!=expected:raise ValueError('all 144 unique slots required before publishing')
    if len(agents)!=len(expected):raise ValueError('duplicate agent slots')
    # Check that each actual session received the frozen common packet.
    for r in agents:
        if r['common_input_sha256']!=protocol['public_packet_sha256'][f'{r["case_id"]}/{r["task"]}']:
            raise ValueError('agent common input hash mismatch')
        if r['system_prompt_sha256']!=protocol['system_prompt_sha256']:raise ValueError('prompt mismatch')
        audit=r.get('capability_audit') or {}
        if any(audit.get(k) for k in ('native_kernel','children','external_retrieval','cwd_memory_loaded')):raise ValueError('unexpected agent capability')
    groups={source:{t:{a:metrics([r for r in rows if (t=='all' or r['task']==t) and r['arm']==a]) for a in (ARMS if source=='agent' else ('B','C'))}
        for t in ('all','forecast','pretransfer')} for source,rows in [('agent',agents),('model',controls)]}
    paired={}
    for task in protocol['tasks']:
        index={a:{r['case_id']:r for r in agents if r['arm']==a and r['task']==task} for a in ARMS}
        cases=[c for c in protocol['case_ids'] if all(index[a][c]['score']['completion_absolute_error_h'] is not None for a in ARMS)]
        paired[task]={'cases':cases,'n':len(cases),'mae_h':{a:statistics.mean(index[a][c]['score']['completion_absolute_error_h'] for c in cases) if cases else None for a in ARMS}}
    b,c,a=(groups['agent']['all'][k] for k in ('B','C','A'))
    conclusion=f"Agent + LyoPRONTO made {b['feasible']} feasible choices out of 48, compared with {a['feasible']} without a prepared model and {c['feasible']} with the Sievance model."
    details=f"LyoPRONTO's agent arm had {b['unsafe']} unsafe selections, {b['characterize']} characterization decisions and {b['failed']} failed/no-submission slots. These are simulated constraint outcomes, not observed manufacturing incidents."
    for r in agents:
        r['failure_kind']='admission_denied' if r['submission'] is None and 'Campaign admission cap' in (r.get('error') or '') else 'timeout' if r['status']=='timeout' else 'no_submission' if r['submission'] is None else None
    budget_limited=[{'case_id':r['case_id'],'task':r['task'],'arm':r['arm']} for r in agents if r['failure_kind']=='admission_denied']
    slim=[]
    for source,rows in [('agent',agents),('model',controls)]:
        for r in rows:
            slim.append({k:r.get(k) for k in ('case_id','task','arm','family','status','submission','score','wall_seconds','model_calls','tool_calls','physical_model_calls','failure_kind')}|{'source':source})
    summary={'date':'2026-11-07','classification':'Reused-case synthetic tool comparison','cases':24,'planned_sessions':144,
      'model':protocol['model'],'arms':ARMS,'budget_limited_slots':budget_limited,'groups':groups,'paired':paired,'conclusion':conclusion,'detail':details,
      'cost':cost(base),'protocol':{k:v for k,v in protocol.items() if k not in ('sdk_script',)},
      'rows':sorted(slim,key=lambda r:(r['source'],r['case_id'],r['task'],r['arm'])),
      'model_control_errors':sum(bool(r['error']) for r in controls),
      'calibration_statuses':{a:{t:{st:sum(r['arm']==a and r['task']==t and (r.get('predictions',{}).get('keep',{}).get('calibration',{}).get('status'))==st for r in controls) for st in sorted({r.get('predictions',{}).get('keep',{}).get('calibration',{}).get('status','unavailable') for r in controls if r['arm']==a and r['task']==t})} for t in protocol['tasks']} for a in ('B','C')},
      'shared_schema_hashes':sorted({r['capability_audit']['shared_tool_schema_sha256'] for r in agents if r.get('capability_audit')}),
      'provenance':{'protocol_sha256':digest(base/'protocol.json'),'agents_sha256':digest(base/'agents/results.json'),
         'controls_manifest_sha256':digest(base/'controls/manifest.json'),'original_public_packet_hashes_match':48,
         'preflight_sha256':digest(base/'agents/preflight.json'),'isolation_sha256':digest(base/'agents/isolation.json'),
         'dataset_verification':dataset_verification,'dataset_source_sha256':read(base/'frozen/protocol.json')['code_sha256']}}
    if len(summary['shared_schema_hashes'])!=1:raise ValueError('shared tool schemas differ')
    OUT.mkdir(parents=True,exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
    dump(OUT/'summary.json',summary)
    dump(PUBLIC/'results.json',summary)
    dump(ROOT/'frontend/data/lyohub-study.json',summary)
    published_protocol={**protocol,'sdk_script':'backend/benchmarks/lyo_study/sdk_sensitivity.mjs'}
    dump(PUBLIC/'protocol.json',published_protocol)
    flat=[]
    for r in slim:
        s=r['score'];sub=r.get('submission') or {}
        flat.append({k:r[k] for k in ('source','case_id','family','task','arm','status','failure_kind','wall_seconds','model_calls','tool_calls')}|
          {'action_id':sub.get('action_id'),'predicted_completion_h':sub.get('completion_time_h'),
           'reference_completion_h':s['truth']['completion_time_h'],'completion_absolute_error_h':s['completion_absolute_error_h'],
           'submitted':s['execution_completed'],'feasible':s['selected_feasible'],'unsafe':s['unsafe_selection'],
           'thermal':s['thermal'],'capacity':s['capacity'],'throughput_vials_h':s['throughput_vials_h']})
    with (PUBLIC/'per-case.csv').open('w') as h:
        writer=csv.DictWriter(h,fieldnames=list(flat[0]),lineterminator='\n');writer.writeheader();writer.writerows(flat)
    shutil.copyfile(PUBLIC/'per-case.csv',OUT/'per-case.csv')
    # Report actual submissions, not model hidden reasoning or provider response bodies.
    dump(PUBLIC/'agent-submissions.json',[{k:r.get(k) for k in ('case_id','task','arm','status','failure_kind','model','submission','usage','model_calls','tool_calls','physical_model_calls','wall_seconds','common_input_sha256','system_prompt_sha256','capability_audit')} for r in agents])
    dump(PUBLIC/'model-predictions.json',[{k:r.get(k) for k in ('case_id','task','arm','packet_sha256','predictions','submission','error','wall_seconds')} for r in controls])
    reference=[]
    for case in protocol['case_ids']:
        for task in protocol['tasks']:
            truth=read(base/'frozen/evaluator'/case/(task+'.json'))
            reference.append({'case_id':case,'task':task,'family':truth['family'],'mechanism':truth['mechanism'],
                'temperature_bias_c':truth['temperature_bias_c'],'outcomes':{a:{k:r.get(k) for k in ('completion_time_h','first_capacity_h','first_critical_h')} for a,r in truth['outcomes'].items()}})
    dump(PUBLIC/'reference-outcomes.json',reference)
    lines=['# Freeze-drying with Purdue LyoHUB’s LyoPRONTO','',conclusion,'',details,'',
      '**Classification:** synthetic research, reused 24 cases, one realization per case/task/arm. No manufacturing validation or Purdue affiliation/endorsement is claimed.','',
      f"**Execution qualification:** {len(budget_limited)} sessions ({sum(r['arm']=='A' for r in budget_limited)} numerical-only and {sum(r['arm']=='B' for r in budget_limited)} LyoPRONTO) were unable to dispatch further requests after conservative admission capacity was exhausted. These stay in the denominator but are not evidence of solver quality. Full-cohort tool comparisons are confounded by this execution limit.",'', '## Results','', '| Task | Agent tool | Submitted | Feasible | Unsafe | Characterize | Failed | Completion MAE | Predictions / eligible |',
      '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for task in ('forecast','pretransfer'):
        for arm in ARMS:
            g=groups['agent'][task][arm];lines.append(f"| {task} | {ARMS[arm]} | {g['submitted']}/24 | {g['feasible']}/24 | {g['unsafe']} | {g['characterize']} | {g['failed']} | {f(g['mae_h'])} h | {g['predictions']}/{g['completion_eligible']} |")
    lines += ['','Feasibility requires completed primary drying without a thermal/capacity violation in the synthetic reference. Characterize earns no operating throughput. Failed execution and absent submissions stay in the denominator. Error is reported only where a numerical prediction and eligible reference both exist; different coverage limits comparisons.','',
      '## Matched prediction coverage','']
    for task,p in paired.items():lines.append(f"- {task}: {p['n']}/24 cases have predictions in all three arms; common-case MAE A/B/C: "+' / '.join(f(p['mae_h'][a]) for a in ARMS)+' h.')
    lines += ['','## Model-only controls','','| Task | Model | Feasible | Unsafe | Characterize | MAE | Predictions |','| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for t in ('forecast','pretransfer'):
        for arm in ('B','C'):
            g=groups['model'][t][arm];lines.append(f"| {t} | {ARMS[arm].replace('Agent + ','')} | {g['feasible']}/24 | {g['unsafe']} | {g['characterize']} | {f(g['mae_h'])} h | {g['predictions']}/24 |")
    lines += ['','## Protocol and interpretation','',
      '- Same GLM-5.3, public packets, actions, 8 model calls / 8 host calls / 240 s / 4096 output-token limit. The eighth provider call, if reached, requires submission. Earlier plain-text stopping can still leave no accepted structured decision after the shared follow-up prompt. All 144 sessions are fresh; failures are not retried.',
      '- Both prepared models fit Kv/Rp using only <=6h remaining-ice observations; pretransfer remains nominal. Historical Sievance results used a thermal+ice fit, so this is not a pure one-variable change from the old study.',
      '- Both prepared tools use precomputed public-input-only outputs. Their solver time is recorded in model-only controls, outside AI session wall time. A numerical analysis executes inside its session deadline; this workflow difference matters.',
      '- This uses the restricted Prime SDK experiment host, with native kernel, child agents, external retrieval and workspace memory disabled. It is not an evaluation of the full deployed assistant or investigation system.',
      '- No accepted submission is a workflow outcome, not proof the model lacks physics knowledge or wrote no useful text. The harness allows up to eight calls but may stop after a plain-text answer plus one follow-up; submission-only forcing occurs on the eighth request if reached.',
      '- Sessions share a hosted endpoint and conservative admission proxy. Concurrency can queue requests within the wall-time limit; latency/failure outcomes include this execution environment, not only reasoning capability.',
      '- Some effective fits may reach their fixed evaluation limit. Calibration statuses: '+json.dumps(summary['calibration_statuses'],sort_keys=True)+'. The frozen protocol retains those fits; it does not claim they all converged.',
      '- LyoPRONTO is pinned to c6a9225a9e551ae4e7c11c1ef056b67c6204afbd, version 1.2.0. Native SI conversions preserve Kv/Rp/frozen height. cSolid=1.5*(1-porosity) g/mL assumes upstream solute density; native initial ice is approximately 0.85% higher. No silent mass rescaling.',
      '- LyoPRONTO knownRp front temperature is not a weighted thermal node or hottest transient vial. Its lack of population/thermal-storage states can affect risk detection. Constraints are evaluated at returned solver nodes; no between-node maximum guarantee.',
      '- Finite 1e6-unit/min ramps approximate steps; full schedule replays from t=0, preserving past actions. dt=None retains the terminal drying event; horizon noncompletion remains censored.',
      '- Vapor/condenser/temperature checks are supplied by the local wrapper; they are not LyoPRONTO knownRp capabilities. Any overload invalidates pressure-controlled completion and subsequent unsupported thermal predictions.',
      '- Same separately executed synthetic reference as the previous study. Shared physical laws and approximate population structure favor the Sievance model; these are not independent experimental observations. Reused cases and public data do not establish freedom from model-training exposure.',
      '- Primary KEEP cases have '+str(groups['agent']['forecast']['B']['reference_capacity_positive'])+' capacity positives and '+str(groups['agent']['forecast']['B']['reference_thermal_positive'])+' thermal positives out of 24. In particular, zero capacity positives cannot establish detection sensitivity.',
      '- Feasible recommendations do not establish correct rationale, calibrated uncertainty, causal identification, regulatory compliance or real manufacturing benefit. No equipment was operated.',
      '', '## Cost and execution','',
      f"{summary['cost']['requests_admitted']} admitted provider requests; {summary['cost']['requests_with_usage']} have usage receipts. Token-based estimate ${summary['cost']['token_based_estimate_usd']:.6f}; unknown request reservations ${summary['cost']['unknown_reservations_usd']:.2f}; conservative total ${summary['cost']['conservative_accounting_usd']:.6f} under the $10 cap. Each new request required a $2.25 worst-case reservation; remaining unreserved headroom was insufficient even though conservative accounting was below $10. Not an invoice; excludes local solver compute and engineering.",
      '', '## Sources and reproduction','',
      '- [Official LyoHUB LyoPRONTO source](https://github.com/LyoHUB/LyoPRONTO/tree/'+protocol['upstream_commit']+')',
      '- [Original LyoPRONTO paper](https://doi.org/10.1208/s12249-019-1532-7)',
      '- [Frozen protocol and study record](https://github.com/YalmanchiliTejas/BioDemo/issues/28)',
      '- Source/input/output hashes: results.json, protocol.json and manifest.json. Reproduction archive includes public packets and local source, not upstream GPL software or the separately installed Prime SDK.',
      '- Unmodified upstream dependency is GPL-3.0-or-later; this numerical study does not make it a production dependency.','']
    text='\n'.join(lines);(OUT/'report.md').write_text(text);(PUBLIC/'report.md').write_text(text)
    plots(summary,agents,controls,base,PUBLIC)
    with zipfile.ZipFile(PUBLIC/'reproduce.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in dict.fromkeys([*protocol['source_sha256'],*summary['provenance']['dataset_source_sha256'],'backend/src/lifesci/lyophilization/case.py']):
            z.write(ROOT/name,name)
        for p in (base/'frozen/public').glob('*/*.json'):z.write(p,'public/'+str(p.relative_to(base/'frozen/public')))
        for name in ('README.md','report.py'):z.write(Path(__file__).with_name(name),'backend/benchmarks/lyohub_study/'+name)
        z.write(PUBLIC/'protocol.json','protocol.json')
    for svg in PUBLIC.glob('*.svg'):
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    manifest={p.name:digest(p) for p in PUBLIC.iterdir() if p.is_file() and p.name!='manifest.json'}
    dump(PUBLIC/'manifest.json',manifest);dump(OUT/'manifest.json',manifest)
    return {'sessions':len(agents),'controls':len(controls),'conclusion':conclusion,'detail':details,'cost':summary['cost']}


def plots(summary,agents,controls,base,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    labels=['No prepared model','LyoPRONTO','Sievance model'];colors=['#64748b','#b1832f','#0e7490']
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),layout='constrained')
    for ax,task in zip(axes,('forecast','pretransfer')):
        groups=[summary['groups']['agent'][task][a] for a in ARMS];left=np.zeros(3)
        for key,label,color in [('feasible','Feasible','#0e7490'),('unsafe','Unsafe','#c85348'),('characterize','Characterize','#c79845'),('failed','Failed / no submission','#cbd5e1')]:
            values=[g[key] for g in groups];ax.barh(labels,values,left=left,label=label,color=color,height=.6)
            for y,(v,l) in enumerate(zip(values,left)):
                if v:ax.text(l+v/2,y,str(v),ha='center',va='center',color='white' if key in ('feasible','unsafe') else '#183b44',fontsize=10)
            left+=values
        ax.set_xlim(0,24);ax.set_xticks([0,6,12,18,24]);ax.set_xlabel('Agent sessions (all 24 retained)');ax.set_title('After 6 hours' if task=='forecast' else 'Before transfer');ax.invert_yaxis()
    axes[1].legend(loc='upper center',bbox_to_anchor=(.3,-.2),ncol=2,frameon=False)
    fig.suptitle('Actual agent choices under the separate synthetic evaluator',fontsize=13)
    fig.savefig(out/'agent-outcomes.svg',bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax,task in zip(axes,('forecast','pretransfer')):
        p=summary['paired'][task]
        vals=[p['mae_h'][a] if p['mae_h'][a] is not None else 0 for a in ARMS]
        if not p['n']:
            ax.text(.5,.5,'No common numerical predictions',ha='center',va='center',transform=ax.transAxes);ax.set_xticks([]);ax.set_title(task+' · coverage 0/24');continue
        bars=ax.bar(labels,vals,color=colors,width=.6)
        for bar,value in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height(),f'{value:.2f}',ha='center',va='bottom')
        ax.set_ylabel('Completion MAE (hours)');ax.set_title(('After 6 h' if task=='forecast' else 'Pretransfer')+f" · common coverage {p['n']}/24");ax.tick_params(axis='x',labelrotation=12)
    fig.suptitle('Prediction error on the same cases with predictions in every arm',fontsize=12)
    fig.savefig(out/'paired-errors.svg',bbox_inches='tight');plt.close(fig)
    # Predeclared illustrative selection: smallest opaque ID, forecast task, KEEP.
    case=summary['protocol']['case_ids'][0];truth=read(base/'frozen/evaluator'/case/'forecast.json')['outcomes']['keep']['trajectory']
    packet=read(base/'frozen/public'/case/'forecast.json');fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    ax.plot([r['time_h'] for r in truth],[r['remaining_ice_kg_per_vial']*1e3 for r in truth],color='#183b44',label='Synthetic hidden reference',lw=2)
    for arm,label,color in [('B','LyoPRONTO · native ice mass','#b1832f'),('C','Sievance population model','#0e7490')]:
        raw=next(r for r in controls if r['case_id']==case and r['task']=='forecast' and r['arm']==arm)['raw'].get('keep')
        if raw:
            rows=raw['trajectory'];ax.plot([r['time_h'] for r in rows],[r['remaining_ice_kg_per_vial']*1e3 for r in rows],label=label,color=color,ls='--')
    ax.scatter([r['time_h'] for r in packet['observations']],[r['remaining_ice_kg_per_vial']*1e3 for r in packet['observations']],s=16,color='#183b44',label='Early public observations',zorder=4)
    ax.axvline(6,color='#94a3b8',lw=1);ax.set(xlabel='Elapsed hours from batch start',ylabel='Remaining ice per vial (g)',title=case+' · KEEP · first case by ID, selected without outcomes')
    ax.legend(frameon=False,fontsize=9);fig.savefig(out/'ice-trajectory.svg',bbox_inches='tight');plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',type=Path,required=True);a=parser.parse_args();print(json.dumps(report(a.base),indent=2))
