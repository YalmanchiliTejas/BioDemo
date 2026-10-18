"""Offline audit of a saved run against its source store; never invokes a model.

No hidden benchmark references are loaded; original run artifacts remain unchanged.
"""
import argparse
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from src.manufacturing_data import ManufacturingStore,ManufacturingTools
from src.manufacturing_data.session import ManufacturingSession
from src.workflows.investigation_review import review_investigation
from src.workflows.report_verification import verify_report,collect_citations


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    saved=json.loads((args.run/'run.json').read_text());output=json.loads((args.run/'output.json').read_text())
    old=output['analysis'];scope=output['constraints']['scope'];cutoff=output['constraints']['as_of']
    original=Path(saved['runtime_workspace'])/'state/store'
    with tempfile.TemporaryDirectory(prefix='investigation-audit-') as folder:
        root=Path(folder);shutil.copy2(original/'metadata.sqlite',root/'metadata.sqlite')
        shutil.copytree(original/'originals',root/'originals',copy_function=os.link)
        store=ManufacturingStore(root)
        tools=ManufacturingTools(store,scopes=(scope,),as_of=cutoff);session=ManufacturingSession(store,as_of=cutoff,scopes=(scope,))
        start=time.perf_counter();prepared=tools.analysis().prepare();preparation_seconds=time.perf_counter()-start
        report=copy.deepcopy(old);report['hypotheses']=report.pop('causal_hypotheses',[])
        for key in ('analysis_preparation','workflow','verification','examined_scope','analysis_preparation_artifact'):
            report.pop(key,None)
        ids=collect_citations(report);rows=session.get(ids)
        temporal_receipts=[]
        for claim in report.get('temporal_claims',[]):
            try:
                receipt=review_investigation({'temporal_claims':[claim]},prepared,rows)['temporal_claims'][0]
            except ValueError as exc:
                receipt={'claim_id':claim.get('claim_id'),'verification':'rejected','diagnostic':str(exc)}
            temporal_receipts.append(receipt)
        try:
            review=review_investigation(report,prepared,rows)
        except ValueError as exc:
            review={'report_status':'incomplete','issues':[{'code':'invalid_saved_report','diagnostic':str(exc)}],
                    'temporal_claims':temporal_receipts}
        start=time.perf_counter();verified,_,checks=verify_report(report,session,tools,set(ids));verification_seconds=time.perf_counter()-start
        screen=prepared['screening'];priorities=screen['priority_candidates']
        hashes=[]
        for s in store.visible_sources(scopes=(scope,),as_of=cutoff):
            actual=hashlib.sha256(Path(s['original_path']).read_bytes()).hexdigest()
            hashes.append({'source_id':s['id'],'pass':actual==s['sha256']})
        summary={'run_id':saved['run_id'],'baseline_wall_clock_seconds':saved['wall_clock_seconds'],
            'baseline_usage':output['usage'],'original_citation_count':len(output['citations']),
            'original_citation_sources':dict(collections.Counter(c['source']['path'] for c in output['citations'])),
            'new_preparation_seconds':preparation_seconds,'new_source_and_metric_reverification_seconds':verification_seconds,
            'source_checks_passed':sum(c['source_integrity'] and c['value_matches'] is True for c in checks['evidence_checks'].values()),
            'source_checks_count':len(checks['evidence_checks']),'numerical_metrics_verified':checks['numerical_metrics_verified'],
            'source_hashes':hashes,'replayed_report_status':review['report_status'],
            'screened_unit_count':len(screen['coverage_units']),'raw_anomaly_series_count':screen['anomaly_series_count'],
            'raw_anomaly_flag_count':screen['raw_anomaly_flag_count'],'grouped_quality_candidate_count':screen['grouped_quality_candidate_count'],
            'preview_source_count':len({c['source_id'] for c in priorities}),
            'preview_family_count':len({c['measurement_family'] for c in priorities}),
            'preview_categories':dict(collections.Counter(c['category'] for c in priorities)),
            'priority_build_policy':screen['policy'],'new_live_rlm_run':False,
            'scientific_correctness':'unscored; independent scientific review required',
            'retrieval_recall_precision':'unscored; no independent relevance labels supplied',
            'root_cause_confirmation':False}
        repository=Path(__file__).resolve().parents[1]
        summary['implementation_file_sha256']={str(path.relative_to(repository)):hashlib.sha256(path.read_bytes()).hexdigest()
            for parent in ('src/workflows','src/manufacturing_data','src/prime_runtime')
            for path in sorted((repository/parent).glob('*.py'))}
        summary['temporal_claims']=temporal_receipts
        summary['claim_issues']=checks.get('claim_verification',{}).get('issues',[])
        (args.output/'summary.json').write_text(json.dumps(summary,indent=2,default=str)+'\n')
        (args.output/'review.json').write_text(json.dumps(review,indent=2,default=str)+'\n')
        (args.output/'screening.json').write_text(json.dumps(screen,indent=2,default=str)+'\n')
        (args.output/'verification.json').write_text(json.dumps(checks,indent=2,default=str)+'\n')
        print(json.dumps({k:v for k,v in summary.items() if k not in {'baseline_usage','source_hashes'}},indent=2))
if __name__=='__main__':main()
