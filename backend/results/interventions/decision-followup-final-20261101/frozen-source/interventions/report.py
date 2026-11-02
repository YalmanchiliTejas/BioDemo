"""Separate outcomes for frozen intervention A/B; no combined decision score."""
from pathlib import Path
from collections import Counter
import argparse,json
import numpy as np
from benchmarks.external_simulators.experiment import dump,sha


def write(root,out):
    data=json.loads((root/'results.json').read_text());p=json.loads((root/'protocol.json').read_text())
    if data['status']!='complete':raise ValueError('Study is unfinished')
    assert all(sha(f)==h for f,h in p['code_sha256'].items()),'Frozen implementation changed'
    cases=data['cases'];records=[r for c in cases for r in c['records']]
    groups={}
    for arm in ['A','B']:
        attempted=[r for r in records if r['arm']==arm];done=[r for r in attempted if r.get('evaluation')]
        def avg(fn):return float(np.mean([fn(r) for r in done])) if done else None
        groups[arm]={'executed_attempts':len(attempted),'completed':len(done),'execution_failures':len(attempted)-len(done),
            'model_domain_unattempted':p['independent_scenarios']*p['repeats']-len(attempted),
            'mean_product_mass_kg':avg(lambda r:r['evaluation']['outcome']['product_mass_kg']),
            'mean_concentration_g_l':avg(lambda r:r['evaluation']['outcome']['terminal_concentration_g_l']),
            'mean_volume_l':avg(lambda r:r['evaluation']['outcome']['terminal_volume_l']),
            'mean_post_decision_violation_h':avg(lambda r:r['evaluation']['outcome']['post_decision']['below_limit_h']),
            'mean_whole_process_violation_h':avg(lambda r:r['evaluation']['outcome']['whole_process']['below_limit_h']),
            'violating_operating_decisions':sum(not r['evaluation']['outcome']['stopped'] and not r['evaluation']['outcome']['post_decision_feasible'] for r in done),
            'stops':sum(r['evaluation']['outcome']['stopped'] for r in done),
            'unnecessary_stops':sum(r['evaluation'].get('unnecessary_stop',False) for r in done),
            'correct_stops_within_menu':sum(r['evaluation'].get('correct_stop_within_action_menu',False) for r in done),
            'unknown_stop_adjudications':sum(r['evaluation'].get('stop_adjudication') is not None for r in done),
            'mean_wall_seconds':float(np.mean([r['wall_seconds'] for r in attempted if r.get('wall_seconds') is not None])) if attempted else None,
            'mean_measurement_delay_h':avg(lambda r:r['evaluation']['physical_decision_delay_h']),
            'assumed_measurement_work_minutes':sum(r['evaluation']['assumed_measurement_work_minutes'] for r in done),
            'model_calls':sum(r.get('model_calls') or 0 for r in attempted),'host_calls':sum(len(r.get('tools',[])) for r in attempted),
            'provider_cost_usd':None,'measured_product_quality':None}
    original_by_case={c['case_id']:c['original_recipe'] for c in cases if c.get('original_recipe')}
    original_reference={'independent_cases':len(original_by_case),'mean_product_mass_kg':float(np.mean([v['product_mass_kg'] for v in original_by_case.values()])) if original_by_case else None,'mean_post_decision_violation_h':float(np.mean([v['post_decision']['below_limit_h'] for v in original_by_case.values()])) if original_by_case else None,'violating_scenarios':sum(not v['post_decision_feasible'] for v in original_by_case.values())}
    paired={}
    for c in cases:
        by={r['arm']:r for r in c['records'] if r.get('evaluation')}
        if set(by)=={'A','B'}:paired.setdefault(c['case_id'],[]).append(by)
    differences=[]
    for case,pairs in paired.items():
        differences.append({'case_id':case,'paired_repetitions':len(pairs),
            'mass_B_minus_A_kg':float(np.mean([v['B']['evaluation']['outcome']['product_mass_kg']-v['A']['evaluation']['outcome']['product_mass_kg'] for v in pairs])),
            'post_violation_B_minus_A_h':float(np.mean([v['B']['evaluation']['outcome']['post_decision']['below_limit_h']-v['A']['evaluation']['outcome']['post_decision']['below_limit_h'] for v in pairs]))})
    intervals={}
    if differences:
        rng=np.random.default_rng(20261029);ix=rng.integers(0,len(differences),(20000,len(differences)))
        for field in ['mass_B_minus_A_kg','post_violation_B_minus_A_h']:
            values=np.array([r[field] for r in differences]);intervals[field]={'mean':float(values.mean()),'interval95':np.quantile(values[ix].mean(axis=1),[.025,.975]).tolist(),'independent_case_clusters':len(values)}
    failure_cases=sorted({c['case_id'] for c in cases if c['status']=='numerical_domain_failure'})
    summary={'status':'complete','protocol':p,'original_recipe_reference':original_reference,'groups':groups,'paired_case_differences':differences,'paired_intervals':intervals,
        'numerical_domain_failure_cases':failure_cases,'all_selected_cases_evaluable':not failure_cases,
        'failures':[{'case_id':c['case_id'],'repeat':c['repeat'],'error':c.get('error')} for c in cases if c['status']=='numerical_domain_failure'],
        'source_qualification':{k:v for k,v in json.loads((root/'source-qualification.json').read_text()).items() if k!='source_measurements'}}
    out.mkdir(parents=True,exist_ok=True);dump(out/'analysis.json',summary)
    lines=['# PenSim intervention A/B: imperfect receiving model','',
        'Same AI without a supplied model versus the same AI with physics. Original recipe retained as a reference. Earlier optimizer development results remain available; this narrower study cannot establish that agents outperform conventional modeling software.','',
        f"{p['independent_scenarios']} independent receiver scenarios, {p['repeats']} AI repetitions/arm, {p['planned_AI_sessions']} planned AI slots. {len(failure_cases)} selected scenarios had numerical-domain coverage failures; these were not replaced or counted as correct stops.",'',
        '## Separate outcomes','','| Outcome | AI alone | AI + physics |','|---|---:|---:|']
    labels=[('completed','Completed submissions'),('mean_product_mass_kg','Mean terminal product mass (kg)'),('mean_concentration_g_l','Mean product concentration (g/L)'),('mean_post_decision_violation_h','Mean oxygen violation after decision (h)'),('mean_whole_process_violation_h','Mean whole-process oxygen violation (h)'),('violating_operating_decisions','Operating choices with oxygen violations'),('stops','Stops'),('unnecessary_stops','Unnecessary stops within menu'),('correct_stops_within_menu','Correct stops within menu'),('unknown_stop_adjudications','Stops/decisions with incomplete menu adjudication'),('mean_wall_seconds','Mean agent wall time (s)'),('mean_measurement_delay_h','Mean measurement-induced process delay (h)'),('assumed_measurement_work_minutes','Total assumed assay work (min)'),('execution_failures','Execution failures')]
    def fmt(v):return 'Unknown' if v is None else f'{v:.3f}' if isinstance(v,float) else str(v)
    for k,label in labels:lines.append(f'| {label} | {fmt(groups["A"][k])} | {fmt(groups["B"][k])} |')
    lines+=['','Means condition on completed submissions; their denominators and unattempted coverage failures appear in analysis.json. Stops contribute zero product. Product mass and constraint compliance are reported separately; an infeasible run does not become a successful intervention because it produced more material. No product-quality measurements are available. Assay work is assumed, billing unknown, and wall time is not measured engineer effort.','','## Paired uncertainty','',json.dumps(intervals,indent=2),'','Intervals resample independent scenarios with repetitions nested. They are exploratory and conditional on paired completed scenarios, not calibrated physical confidence or proof of general manufacturing benefit.','',
        '## Evidence and boundaries','',
        'Source calibration uses three completed source batches, DO and delayed product assays; no perfect substrate measurement. Receiver initial states and kinetics differ; the tool never receives hidden true parameters or future observations. Candidate change-time fitting and a fixed sensitivity set use only available observations. Sensitivity members are not probabilities of feasibility.','',
        'The predeclared normal/moderate/severe mix describes disturbance assumptions, not guaranteed recoverability. Severe numerical failures expose model-domain gaps, not physically established unrecoverable conditions. Full230h viscosity remains unresolved; the horizon here is96h. Source-model kinetic ranges/noise/action limits are synthetic assumptions informed by the port, not empirically validated receiver distributions.','',
        'The research SDK demonstrates an investigation/recommendation interface; this is not an end-to-end production OS deployment or a real intervention. The physical NISTCHO dataset is a separate, campaign-confounded feeding comparison and cannot validate this oxygen mechanism.','',
        'All source snapshots, protocol hashes, input packets, tool events, recommendations, hidden action replays and failures remain in the study directory. The prior matching-model benchmark remains the upper-bound reference.']
    lines+=['','## Original recipe reference','',f"{original_reference['independent_cases']} admitted independent scenarios: mean terminal mass {fmt(original_reference['mean_product_mass_kg'])}kg; mean post-decision oxygen violation {fmt(original_reference['mean_post_decision_violation_h'])}h; {original_reference['violating_scenarios']} scenarios violate the oxygen limit. These are unmodified-recipe outcomes, not another AI arm."]
    (out/'report.md').write_text('\n'.join(lines)+'\n');dump(out/'provenance.json',{'protocol_sha256':sha(root/'protocol.json'),'results_sha256':sha(root/'results.json'),'report_sha256':sha(out/'report.md'),'analysis_sha256':sha(out/'analysis.json')})
    print(json.dumps({'groups':groups,'coverage_failures':len(failure_cases),'paired_intervals':intervals}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();write(a.root,a.output)
