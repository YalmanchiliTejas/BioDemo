"""Export measured batch results to the UI; never load runtime stores or hidden labels."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def trajectory(root,run,checks):
    """An illustrative source trajectory; never interpolate, infer onset or tune scores."""
    groups={}
    for check in checks.values():
        ref=check.get('source_ref',{});column=str(ref.get('column',''))
        if check.get('value_matches') is True and check.get('source_integrity') is True and 'viability mean' in column.lower() and '%' in column:
            groups.setdefault((ref.get('path'),ref.get('row'),column),[]).append(check)
    pairs=[]
    for key,items in groups.items():
        for index,a in enumerate(items):
            for b in items[index+1:]:
                if a['source_ref'].get('sheet')!=b['source_ref'].get('sheet'):
                    pairs.append((abs(float(a['observed'])-float(b['observed'])),key,a,b))
    expected={f['path']:f['sha256'] for f in run['case'].get('allowlist',[])}
    for _,(name,row,column),a,b in sorted(pairs,key=lambda item:item[0],reverse=True):
        base=root/'benchmarks/cho/raw/workbooks';source=base/name
        if source.resolve().parent!=base.resolve() or not source.is_file() or digest(source)!=expected.get(name):continue
        from openpyxl import load_workbook
        from openpyxl.utils.cell import get_column_letter
        book=load_workbook(source,read_only=True,data_only=True);series=[];comparison_times=[]
        try:
            for check in (a,b):
                ref=check['source_ref'];sheet=book[ref['sheet']];iterator=sheet.iter_rows(values_only=True);headers=list(next(iterator))
                clock=next((i for i,h in enumerate(headers) if str(h).strip().lower()=='time (h)'),None)
                if clock is None or column not in headers:break
                value_index=headers.index(column);points=[]
                for number,values in enumerate(iterator,2):
                    t,y=values[clock],values[value_index]
                    if type(t) in (int,float) and type(y) in (int,float) and math.isfinite(t) and math.isfinite(y):
                        points.append({'time_hours':t,'value':y,'row':number,'value_cell':get_column_letter(value_index+1)+str(number)})
                        if number==row:comparison_times.append(t)
                times=[p['time_hours'] for p in points]
                if not points or times!=sorted(set(times)):break
                series.append({'label':ref['sheet'].split('_')[0],'sheet':ref['sheet'],'column':column,'points':points})
        finally:book.close()
        if len(series)==2 and len(comparison_times)==2 and comparison_times[0]==comparison_times[1]:
            return {'source':name,'source_sha256':expected[name],'series':series,
                    'selection':'Illustrative largest paired viability difference among cited cells at matching source times; not an outcome ranking.',
                    'limitation':'Authentic sampled laboratory means. Lines connect observed samples; event onset, fault and cause are not established.'}
    return None

def export(root=ROOT):
    logs=root/'results/background-logs';batches={}
    for path in logs.glob('*.log'):
        match=re.fullmatch(r'(cho|fresenius)-(\d{8}-\d{6})\.log',path.name)
        if match:batches.setdefault(match[2],{})[match[1]]=path
    paired=[stamp for stamp,paths in batches.items() if set(paths)=={'cho','fresenius'}]
    if not paired:raise ValueError('No paired CHO/Fresenius background batch logs found')
    batch=max(paired);runs=[];missing=[];seen=set()
    public=root/'ui/public/benchmarks';public.mkdir(parents=True,exist_ok=True)
    for bid in ('cho','fresenius'):
        for line in batches[batch][bid].read_text().splitlines():
            try:entry=json.loads(line)
            except ValueError:continue
            if 'run' not in entry:continue
            id=Path(entry['run']).parent.name
            if not re.fullmatch('[a-f0-9]{32}',id):raise ValueError('Invalid recorded run identifier')
            if id in seen:continue
            seen.add(id);path=root/'results/evaluation'/id/'run.json'
            if not path.exists():missing.append({'case_id':entry.get('case'),'run_id':id});continue
            run=json.loads(path.read_text())
            if run['benchmark_id']!=bid or run['case_id']!=entry['case']:raise ValueError('Batch log and recorded case disagree')
            output_path=path.parent/'output.json';report=run.get('output',{}).get('analysis',{})
            output_valid=(digest(output_path)==run.get('output_sha256')) if output_path.exists() else None
            if report and output_valid is not True:raise ValueError('Recorded output checksum mismatch: '+id)
            verification=report.get('verification',{});review=report.get('investigation_review',{})
            scores=run.get('objective_scores',{});checks=verification.get('evidence_checks',{})
            usage=dict(run.get('usage') or {})
            # Incomplete pricing is unknown, regardless of SDK zero placeholders.
            if usage.get('cost_status') not in {'complete','measured'}:
                usage['total_cost_usd']=None
            execution=run.get('execution_status') or ('failed' if run['status']=='failed' else 'evaluation_unavailable')
            investigation=run.get('investigation_status') or ('complete' if report.get('report_status')=='complete_for_available_evidence' else 'incomplete' if report else 'unavailable')
            source=run.get('source_verification_status') or verification.get('source_verification_status','unavailable')
            failures=verification.get('unlinked_numeric_literals',[])
            if execution=='failed':label='Execution failed'
            elif investigation!='complete':label='Partial investigation'
            elif source=='human_review_pending':label='Final report · source review pending'
            else:label='Final report · source checks passed' if source in {'automatically_verified','verified_with_human_review'} else 'Final report · verification unavailable'
            if execution=='failed':reason='Execution failed; read the recorded diagnostics.'
            elif failures:reason=f"{len(failures)} numerical literals need verification; source review may also be pending."
            elif source=='human_review_pending':reason=f"{verification.get('pending_source_review_count',0)} scanned-source citations await visual review."
            else:reason='Automated source checks passed; independent scientific review remains pending.'
            row={'run_id':id,'case_id':run['case_id'],'benchmark_id':bid,'condition':run['condition'],
                 'method':run['mode'],'execution_status':execution,'investigation_status':investigation,
                 'source_verification_status':source,'scientific_status':run.get('qualification',{}).get('status','pending_review'),
                 'scientifically_qualified':run.get('qualification',{}).get('qualified') is True,
                 'recorded_status':run['status'],'label':label,'disclosure':reason,'started_at':run['started_at'],'ended_at':run.get('ended_at'),
                 'runtime_seconds':run.get('wall_clock_seconds'),'budgets':run['execution_budgets'],
                 'coverage_reviewed':review.get('reviewed_unit_count'),'coverage_total':review.get('screened_unit_count'),
                 'candidate_count':len(review.get('candidate_reviews',[])),
                 'source_check_count':len(checks) if report else None,'automatically_verified_sources':sum(c.get('source_integrity') is True and c.get('value_matches') is True for c in checks.values()) if report else None,
                 'pending_source_reviews':verification.get('pending_source_review_count') if report else None,
                 'calculation_count':verification.get('numerical_metrics_verified') if report else None,
                 'field_checks':scores.get('data_preparation',{}).get('field_accuracy'),
                 'claim_issues':verification.get('claim_verification',{}).get('issues',[]),
                 'numeric_review_items':failures,'usage':usage,'case_sha256':run['case'].get('task_spec_sha256'),
                 'dataset_sha256':run['case'].get('package_sha256'),'output_sha256':run.get('output_sha256'),
                 'run_file_sha256':digest(path),'output_hash_matches':output_valid,'details_url':f'/benchmarks/{id}.json'}
            detail={**row,'assessment':report.get('assessment'),'cross_scope_synthesis':report.get('cross_scope_synthesis'),
                    'observed_facts':report.get('observed_facts',[]),'interpretations':report.get('interpretations',[]),
                    'hypotheses':report.get('causal_hypotheses',report.get('hypotheses',[])),
                    'calculations':report.get('calculated_metrics',[]),'coverage':review.get('coverage',[]),
                    'candidate_reviews':review.get('candidate_reviews',[]),'open_questions':report.get('open_questions',[]),
                    'next_actions':report.get('actions_now',[]),'evidence_requests':report.get('pending_evidence_requests',[]),
                    'pending_reviews':verification.get('pending_source_reviews',[]),
                    'source_checks':list(checks.values()),'diagnostic':run.get('reason'),
                    'qualification_reasons':run.get('qualification',{}).get('reasons',[]),
                    'trajectory':trajectory(root,run,checks) if bid=='cho' else None,
                    'source_record':f'results/evaluation/{id}/run.json'}
            (public/(id+'.json')).write_text(json.dumps(detail,indent=2)+'\n')
            runs.append(row)
    payload={'batch':batch,'exported_at':datetime.now(timezone.utc).isoformat(),'runs':runs,'unavailable_records':missing,
             'source_logs':[str(p.relative_to(root)) for p in batches[batch].values()],
             'disclosures':['CHO uses authentic laboratory measurements.',
                 'Fresenius is a synthetic manufacturing reconstruction informed by publicly available FDA-related materials; no internal company data, participation, endorsement or validation.',
                 'Investigation completion, source verification and independent scientific qualification are separate.',
                 'All attempts from this paired batch are included. Historical attempts remain in the detailed benchmark archive.',
                 'Runtime is machine wall time, not measured human effort. Provider usage may exclude children; unknown costs remain unknown.',
                 'No measured manual-engineer comparison, human-effort savings, confirmed root cause or production improvement is established.']}
    destination=root/'ui/src/data/benchmarks.json';destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(payload,indent=2)+'\n')
    (public/'summary.json').write_text(json.dumps(payload,indent=2)+'\n')
    return payload

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args()
    payload=export(args.root.resolve());print(json.dumps({'batch':payload['batch'],'exported_runs':len(payload['runs']),'unavailable':len(payload['unavailable_records'])}))
