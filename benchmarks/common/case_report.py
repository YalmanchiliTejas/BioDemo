"""All-attempt reports with separate datasets, conditions and comparison groups."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from .case_protocol import ROOT, VERSION, GROUPS, save
from .human_work import aggregate_effort, produce_comparison, template


def safe_usage(run):
    from .usage import recover_usage
    usage=dict(run.get('usage') or recover_usage(ROOT/'results/evaluation'/run['run_id']/'runtime-artifacts'))
    if run.get('mode')=='full_rlm' and usage.get('inference_cost_usd')==0:
        usage.update(recorded_inference_cost_usd=0,inference_cost_usd=None,cost_status='unknown_legacy_provider_or_child_telemetry')
    return usage or None


def summarize_runs(runs, human_logs=None):
    logs=human_logs or template()
    cohorts={}
    for benchmark in ('fresenius','cho'):
        conditions={}
        for condition in ('raw','clean','held_out','updated','historical'):
            selected=[r for r in runs if r['benchmark_id']==benchmark and r['condition']==condition]
            # Never average different datasets or condition mixes into one score.
            effort=aggregate_effort(selected,logs,allocation_universe=runs)
            comparison=produce_comparison(selected,effort)
            conditions[condition]={'runs':[{'run_id':r['run_id'],'case_id':r['case_id'],'mode':r['mode'],
                                          'status':r['status'],'qualification':r.get('qualification'),
                                          'objective_scores':r.get('objective_scores'), 'usage':safe_usage(r),
                                          'wall_clock_seconds':r.get('wall_clock_seconds'),
                                          'trace_path':r.get('trace_path'),'audit':r.get('audit'),'failure_modes':r.get('failure_modes',[]),
                                          'scorer_sha256':r.get('environment',{}).get('scorer_sha256')} for r in selected],
                                   'effort':effort,'comparison':comparison}
        cohorts[benchmark]=conditions
    repeat_groups={}
    for run in runs:
        if run.get('attempted'):
            key=(run['benchmark_id'],run['condition'],run['mode'],run['case']['task_spec_sha256'],run.get('environment',{}).get('working_tree_code_sha256','legacy_unpinned'))
            repeat_groups.setdefault(key,[]).append(run)
    reliability=[]
    for key,group in repeat_groups.items():
        times=[r['wall_clock_seconds'] for r in group if r.get('wall_clock_seconds') is not None]
        citations=[{json.dumps({k:c['source'].get(k) for k in ('path','sheet','cell','row','column','page','span','region')},sort_keys=True)
                    for c in r.get('output',{}).get('citations',[]) if isinstance(c.get('source'),dict)} for r in group]
        jaccards=[len(a&b)/len(a|b) if a|b else None for i,a in enumerate(citations) for b in citations[i+1:]]
        reliability.append({'benchmark_id':key[0],'condition':key[1],'mode':key[2], 'task_spec_sha256':key[3],
                            'implementation_sha256':key[4], 'runs':len(group),
                            'completed':sum(r.get('status')=='completed' for r in group),
                            'incomplete':sum(r.get('status')=='incomplete' for r in group),
                            'failed':sum(r.get('status')=='failed' for r in group),
                            'wall_clock_mean':statistics.mean(times) if times else None,
                            'wall_clock_sample_stdev':statistics.stdev(times) if len(times)>1 else None,
                            'pairwise_citation_jaccard':jaccards,'citation_overlap_basis':'canonical source coordinates, not generated evidence IDs',
                            'material_finding_stability':None,'generalization_claim':'not_established'})
    return {'version':VERSION,'cohorts':cohorts,'reliability':reliability,
            'incumbent_status':'not_tested','root_cause_accuracy':'not_applicable_without_independent_labels',
            'human_study_status':'not_tested_without_observed_logs_and_blinded_reviews'}


def _show(value, suffix=''):
    return 'Not measured' if value is None else f'{value:.3f}{suffix}' if type(value) in (float,int) else str(value)


def produce_report(benchmark='all', *, root=None, human_logs=None):
    directory=Path(root or ROOT/'results/evaluation')
    runs=[json.loads(p.read_text()) for p in sorted(directory.glob('*/run.json'))]
    runs=[r for r in runs if r.get('version')==VERSION]
    for run in runs:
        trace=directory/run['run_id']/run.get('trace_path','trace.jsonl')
        if trace.is_file():
            events=[json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
            run['failure_modes']=sorted({event['error_code'] for event in events if event.get('error_code')})
    logs=json.loads(Path(human_logs).read_text()) if human_logs else None
    summary=summarize_runs(runs,logs)
    save(directory/'summary.json',summary)
    lines=['# Manufacturing OS evaluation v2','',
           'Principle: equivalent or better correct, reviewable investigation outcomes with fewer total human-hours.',
           'CHO uses authentic laboratory measurements. Fresenius uses a synthetic FDA-anchored 100-batch reconstruction.',
           'No universal accuracy score, competitor marketing comparison, verified internal RCA or recall-prevention claim is made.','']
    failures=['# Failure analysis','']
    for bid,conditions in summary['cohorts'].items():
        if benchmark!='all' and bid!=benchmark:continue
        lines.extend([f'## {bid.upper()}',''])
        for condition,data in conditions.items():
            lines.extend([f'### {condition}','',
                '| Group | Attempts | Qualified rate | Human hours, all attempts | Hours per qualified case | Status |',
                '|---|---:|---:|---:|---:|---|'])
            for mode,group in data['effort']['groups'].items():
                lines.append(f"| {GROUPS[mode]} | {group['attempted_cases']} | {_show(group['quality_qualified_rate'])} | {_show(group['total_human_hours_all_attempts'])} | {'Undefined (zero qualified)' if group['effort_per_qualified_status']=='undefined' else _show(group['human_hours_per_qualified_case'])} | {group['status']} |")
            comparison=data['comparison']
            lines.extend(['',f"Paired sample: {comparison['paired_sample_size']}; observed effort reduction: {_show(comparison['paired_human_effort_reduction_pct'],'%')}.",
                          *['- '+issue for issue in comparison['issues']], ''])
            for run in data['runs']:
                lines.extend([f"- `{run['run_id']}` / {run['case_id']} / {run['mode']}: {run['status']}, investigation qualification `{run['qualification']['status']}`. Trace: `{run['run_id']}/trace.jsonl`."])
                scores=run.get('objective_scores') or {}
                accuracy=scores.get('data_preparation',{}).get('field_accuracy',{})
                if accuracy:
                    lines.append(f"  - Emitted field checks: {accuracy.get('correct')}/{accuracy.get('checked')} correct; {accuracy.get('missing')} missing of {accuracy.get('expected')} expected. Wall clock: {_show(run.get('wall_clock_seconds'),' s')}. This is technical transcription performance, not investigation qualification.")
                if run.get('usage'):
                    usage=dict(run['usage'])
                    if run['mode']=='full_rlm' and usage.get('inference_cost_usd')==0:usage['inference_cost_usd']=None
                    lines.append(f"  - Machine usage: input/output tokens {usage.get('input_tokens')}/{usage.get('output_tokens')}; tool calls {usage.get('tool_calls')}; inference cost {_show(usage.get('inference_cost_usd'))}. Scope: {usage.get('usage_scope','recorded parser or provider usage only')}.")
                if run['qualification']['status']!='qualified':
                    failures.extend([f"## {run['run_id']} · {run['case_id']}",
                                     f"Execution: {run['status']}; qualification: {run['qualification']['status']}",
                                     f"Observed failure codes: {', '.join(run.get('failure_modes',[])) or 'see run artifact'}",
                                     *['- '+reason for reason in run['qualification'].get('reasons',[])], ''])
    lines.extend(['## Limits and next measurements','',
                  'Draft investigation and routing policies await independent domain approval. Human timers and blinded reviews must be collected; legacy supplied estimates are not v2 measurements.',
                  'Raw, clean, held-out, updated and historical conditions remain separate. Existing CHO data have been inspected during development, so no untouched generalization claim is supported.',
                  'Root-session Prime token/cost counts exclude child usage unless independently captured. Unknown costs remain unknown.',
                  'Existing v1 parser scores and modeled simulations remain in the supporting report; they are not migrated into qualified-case scores.'])
    report=directory/('benchmark_comparison.md' if benchmark=='all' else f'{benchmark}_report.md'); report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text('\n'.join(lines)+'\n'); (directory/'failure_analysis.md').write_text('\n'.join(failures)+'\n')
    # Refresh the existing presentation from the same versioned summary.
    from benchmark.case_comparison.report import write_report
    write_report()
    return report
