"""Independent arithmetic, grouped paired summaries, and reviewable artifacts."""
from pathlib import Path
import argparse,json
from collections import defaultdict
import numpy as np
from .experiment import dump,checked,sha


def interval(values):
    v=np.array(values,dtype=float)
    rng=np.random.default_rng(20261028)
    boot=np.mean(rng.choice(v,size=(20000,len(v)),replace=True),axis=1)
    return {'difference_B_minus_A':float(v.mean()),'descriptive_cluster_bootstrap_95':np.quantile(boot,[.025,.975]).tolist(),'independent_clusters':len(v)}


def cluster_mean(rows,arm,value):
    clusters=defaultdict(list)
    for r in rows:clusters[r['cluster']].append(value(r[arm]['score']))
    return float(np.mean([np.mean(v) for v in clusters.values()]))


def analyze(run,dataset):
    data=json.loads((run/'results.json').read_text());records=data['records']
    pairs=defaultdict(dict);checks=[];mapping={};groups=defaultdict(list)
    for item in checked(dataset,'public/catalogue.json'):
        case=item['case_id'];truth=checked(dataset,f'evaluator/{case}/truth.json')
        packet=checked(dataset,f'public/{case}/packet.json');mapping[case]=(truth,packet)
        if item['simulator']=='cho_real':
            fit=packet['cho_model']
            checks.append({'check':'condition_disjoint','case':case,'passed':packet['condition'] not in fit['training_conditions'] and all(c['condition']!=packet['condition'] for c in packet['training_cultures'])})
            checks.append({'check':'prefix_cutoff','case':case,'passed':all(r['time_h']<=72 for r in packet['test_prefix'])})
            checks.append({'check':'raw_target_cells','case':case,'passed':all('value_cell' in t['source'] and 96<=t['time_h']<=120 for t in truth['targets'].values())})
    for record in records:
        pairs[(record['case_id'],record['repeat'])][record['arm']]=record
        truth,packet=mapping[record['case_id']]
        if not record['score']:continue
        for field,error in record['score']['prediction_errors'].items():
            actual=truth['targets'][field]['value'] if record['simulator']=='cho_real' else truth['baseline'][field]
            predicted=record['submission']['predictions'][field]
            scale=truth['training_scales'][field] if record['simulator']=='cho_real' else max(abs(actual),1e-9)
            checks.append({'check':'arithmetic','case':record['case_id'],'repeat':record['repeat'],'arm':record['arm'],'field':field,
                'passed':np.isclose(abs(predicted-actual),error['absolute_error'],rtol=1e-12) and np.isclose(abs(predicted-actual)/scale,error['normalized_absolute_error'],rtol=1e-12)})
        if record['simulator']!='cho_real':
            selected=truth['actions'][record['submission']['action_id']]['objective'];base=truth['baseline']['objective']
            checks.append({'check':'action_arithmetic','case':record['case_id'],'repeat':record['repeat'],'arm':record['arm'],
                'passed':np.isclose(record['score']['objective_change_percent'],100*(selected-base)/max(abs(base),1e-9),rtol=1e-12,atol=1e-12)})
    for (case,repeat),pair in pairs.items():
        if set(pair)!={'A','B'}:continue
        a,b=pair['A'],pair['B'];truth,packet=mapping[case]
        ap=run/'attempts'/case/f'repeat-{repeat:02d}'/'A'/'agent-input/packet.json'
        bp=run/'attempts'/case/f'repeat-{repeat:02d}'/'B'/'agent-input/packet.json'
        checks.append({'check':'identical_inputs','case':case,'repeat':repeat,'passed':ap.read_bytes()==bp.read_bytes() and sha(ap)==a['common_input_sha256']==b['common_input_sha256']})
        checks.append({'check':'identical_shared_schemas','case':case,'repeat':repeat,'passed':a['capability_audit']['shared_tool_schema_sha256']==b['capability_audit']['shared_tool_schema_sha256']})
        checks.append({'check':'no_A_physics_calls','case':case,'repeat':repeat,'passed':a['physical_model_calls']==0})
        if not a['score'] or not b['score']:continue
        cluster=truth['condition'] if a['simulator']=='cho_real' else str(truth['seed'])
        group=(a['simulator'],a['task'])
        groups[group].append({'case':case,'repeat':repeat,'cluster':cluster,'A':a,'B':b})
    summary=[]
    for (sim,task),rows in sorted(groups.items()):
        for field in rows[0]['A']['score']['prediction_errors']:
            for metric in ('absolute_error','normalized_absolute_error'):
                clusters=defaultdict(list)
                for r in rows:clusters[r['cluster']].append(r['B']['score']['prediction_errors'][field][metric]-r['A']['score']['prediction_errors'][field][metric])
                summary.append({'simulator':sim,'task':task,'field':field,'metric':metric,'paired_runs':len(rows),
                    'A':cluster_mean(rows,'A',lambda s:s['prediction_errors'][field][metric]),
                    'B':cluster_mean(rows,'B',lambda s:s['prediction_errors'][field][metric]),
                    **interval([np.mean(v) for v in clusters.values()])})
        if sim!='cho_real' and task!='prediction':
            clusters=defaultdict(list)
            for r in rows:clusters[r['cluster']].append(r['B']['score']['objective_change_percent']-r['A']['score']['objective_change_percent'])
            summary.append({'simulator':sim,'task':task,'field':'operating_objective','metric':'objective_change_percent','paired_runs':len(rows),
                'A':cluster_mean(rows,'A',lambda s:s['objective_change_percent']),
                'B':cluster_mean(rows,'B',lambda s:s['objective_change_percent']),**interval([np.mean(v) for v in clusters.values()])})
    tool_errors=[];used=0;total=0
    for r in records:
        path=run/'attempts'/r['case_id']/f"repeat-{r['repeat']:02d}"/r['arm']/'tools.json'
        calls=json.loads(path.read_text());physics=[c for c in calls if c['name']=='physical_forward_model']
        used+=int(bool(physics));total+=len(physics)
        tool_errors.extend({'case':r['case_id'],'repeat':r['repeat'],'error':c['result']['error']} for c in physics if 'error' in c['result'])
    for check in checks:check['passed']=bool(check['passed'])
    return {'status':data['status'],'planned':data['protocol']['planned_attempts'],'attempted':len(records),'completed':data['completed'],
        'failed_attempts':[{'case':r['case_id'],'repeat':r['repeat'],'arm':r['arm'],'status':r['status'],'error':r['error']} for r in records if not r['score']],
        'B_sessions_using_physics':used,'physics_calls':total,'physics_tool_errors':tool_errors,
        'summary':summary,'checks':checks,'all_checks_pass':all(c['passed'] for c in checks),
        'caution':'Complete-pair effects; every failure separately retained in denominators. Session repeats stay inside seed/experimental-condition clusters. Descriptive intervals; overlapping CHO training folds and small condition counts limit inference.'}


def write(root,out):
    out.mkdir(parents=True,exist_ok=True)
    results={name:analyze(root/run,root/dataset) for name,run,dataset in [('simulated','fresh-agents','fresh-dataset-v2'),('real_CHO','cho-agents','cho-dataset-v2')]}
    dump(out/'analysis.json',results)
    lines=['# Physics model evaluation improvements — 28 October 2026','','The main comparison is the same configured AI with a physics-model tool (B) versus without a supplied model (A). Identical raw evidence, numerical tools, model, limits and fresh sessions. All attempts, including failed ones, are retained. This is a retrospective exploratory evaluation, not manufacturing validation.','','The fresh simulator tests favor physics for product forecasts. PenSim oxygen errors are lower on average, but their intervals include no benefit. PenSim decision gains remain small; SMPL decision gains are mostly ties. Real CHO forecasts have higher average errors with this physics model. The full 230 h PenSim batch remains unqualified.', '', '![Comparison of the same AI with and without physics](comparison.png)', '', '## Diagnosis and corrections','','The original oxygen calibration added an endpoint error from the source process to the receiving process after changing aeration. That correction need not obey the receiving oxygen balance. The corrected tool fits kLa and growth factors inside the ODE using completed source measurements only. No receiving targets fit those factors. On four previously inspected diagnostic cases, tool oxygen relative error averaged 20.62% with the additive offset versus 9.07% after source-only fitting (nominal uncalibrated 10.00%). One corrected case still has 33.60% error. These old cases are development evidence only. Product calibration remains a source endpoint ratio. Parameter identifiability is not established.','','The 230 h PenSim batch still fails: viscosity crosses below zero around 148.8 h. Native 1e-7, tighter 1e-9 and independent Python LSODA 1e-8 all reproduce it; the viscosity derivative at zero is negative during water addition. This is a structural domain problem in the empirical law. No arbitrary clipping or unvalidated replacement is claimed as a fix. All scored PenSim cases remain explicitly 96 h partial processes.','','A second admission error surfaced during fresh generation: Q is a signed net-heat integral, not a nonnegative material concentration. The old broad guard rejected seed 3004 solely for negative Q. The source equations include cooling and never use Q as an input. The corrected guard permits signed Q while continuing to reject negative viscosity/material states. Before/after reproduction and regressions are retained. That guard was corrected before AI inference; no AI outcome was used to select it. Failed dataset generations remain available.','','## Fresh simulator experiment','','12 new seeds 3001..3012 per simulator; one aeration/flow factor per seed; prediction, operating decision and changed-recipe transfer tasks; three separate AI sessions per arm and case. 72 cases and 432 planned agent attempts. Receiving interventions use the original fixed action grid. SMPL is the 17-state upstream reactor/separator only. Transfer changes commands in the same geometry; it is not real-site transfer or scale-up. Independent sample size is 12 seed clusters per simulator/task, not 36 AI repetitions.','','Prediction errors below are percent of actual endpoint magnitude; lower is better. Objective values are percent change versus KEEP; higher is better. Differences are B minus A; A and B means weight each seed equally after averaging its completed pairs. Bootstrap intervals resample seed clusters, preserving repetitions.','','| Process / task | Measure | AI alone A | AI + physics B | B−A [descriptive 95% interval] | Clusters |','|---|---|---:|---:|---:|---:|']
    for r in results['simulated']['summary']:
        if r['metric'] not in ('normalized_absolute_error','objective_change_percent'):continue
        scale=100 if r['metric']=='normalized_absolute_error' else 1
        lo,hi=r['descriptive_cluster_bootstrap_95']
        measure={'product_concentration':'Product error (%)','process_indicator':'Oxygen error (%)' if r['simulator']=='pensim' else 'Cell-count error (%)','operating_objective':'Objective change (%)'}[r['field']]
        process={'pensim':'PenSimPy','mab':'SMPL upstream'}[r['simulator']]
        lines.append(f"| {process} / {r['task']} | {measure} | {scale*r['A']:.4f} | {scale*r['B']:.4f} | {scale*r['difference_B_minus_A']:.4f} [{scale*lo:.4f}, {scale*hi:.4f}] | {r['independent_clusters']} |")
    lines+=['','## Predictions against real CHO measurements','','Batch CHO-K1 data from the [author-published dataset](https://zenodo.org/records/20829178). Raw offline measurements retain workbook/sheet/cell provenance and workbook hashes. No aligned/interpolated values are ground truth. Cells/mL are converted to million cells/mL; glucose remains g/L. A simple glucose-limited growth/death and substrate balance is fitted separately in three folds, withholding both reactors of each test experimental condition. A 72 h observation prefix conditions the held-out culture state; its future values never fit parameters. Both arms see the same raw training histories and test prefix. Later target timestamps are the original recorded times within 96..120 h.','','16 scored cultures across eight conditions, two AI sessions per arm/culture: 64 planned attempts. EXP009 has no glucose target in the declared window; both reactors are excluded with a receipt, not imputed. Six fed-batch cultures are excluded because nutrient feed composition/planned inputs are insufficient. No antibody target exists in the source. This is real prediction evidence, not a real intervention or technology-transfer experiment.','','| Real CHO target | MAE AI alone A | MAE AI + physics B | B−A [descriptive 95% interval] | Conditions |','|---|---:|---:|---:|---:|']
    for r in results['real_CHO']['summary']:
        if r['metric']!='absolute_error':continue
        lo,hi=r['descriptive_cluster_bootstrap_95']
        label={'viable_cells_million_per_ml':'Viable cells (million/mL)','glucose_g_per_l':'Glucose (g/L)'}[r['field']]
        lines.append(f"| {label} | {r['A']:.4f} | {r['B']:.4f} | {r['difference_B_minus_A']:.4f} [{lo:.4f}, {hi:.4f}] | {r['independent_clusters']} |")
    lines+=['','MAE units: million viable cells/mL and g glucose/L. Positive differences mean worse average error with the physics tool. Intervals resample whole EXP conditions, retaining both reactors and AI repetitions. Overlapping training folds and eight conditions mean these intervals are descriptive. The public data and unknown model pretraining prevent a claim of prospective blind validation. The simple model omits other nutrients, inhibition and environmental effects; the observed real-data result must not be generalized to every physics model.','','## Completion, checks and retained evidence','']
    for name,r in results.items():
        lines.append(f"- {name}: {r['completed']}/{r['planned']} completed; {len(r['failed_attempts'])} failed attempts. B used physics in {r['B_sessions_using_physics']} sessions, {r['physics_calls']} queries, {len(r['physics_tool_errors'])} tool errors. {len(r['checks'])} arithmetic/input/split checks; all pass={r['all_checks_pass']}.")
    lines+=['','Additional CHO checks verified 3,364 value/time pairs against original workbook cells and 16 held-out forecasts against an independent direct-state DOP853 integration. Five oxygen correction/reproducibility checks passed. These are implementation/numerical checks, not additional independent biological samples.', '', 'AI+physics is analyzed as assigned, including B sessions that choose not to call physics. No selectively chosen successful sessions or tasks. Complete-pair effect estimates exclude unscored failures but failure counts remain in the denominator and receipts. Isolation probes deny hidden evaluator/model-file reads, simulator imports, network and credentials in numerical Python; they establish an implementation boundary, not resistance to every possible exploit. No hidden receiving trajectories or scores are returned to agents.','','Regression status: 18 passed, one expected failure retaining the unresolved full 230 h viscosity defect. Tests include signed heat versus negative material/viscosity, the actual seed 3004 trajectory, glucose/cell balance units, future-prefix rejection and exclusion of supplied models from common packets. Original diagnosis receipts, failed generations, fit receipts, frozen input manifests, runner source snapshots, per-session event/tool logs and immutable submissions are under backend/results/external-simulators/improvements-20261027. Historical runs were moved to verified archives by the workspace storage migration; descriptors under backend/benchmarks/assets/external-simulators-*-archive-20261028.json retain hashes and restore locations. They were not overwritten by this work.','','[Detailed CHO protocol](../../research/cho-real-prediction-protocol-audit.md). [Machine-readable analysis and independent checks](analysis.json).']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();write(a.root,a.output)
