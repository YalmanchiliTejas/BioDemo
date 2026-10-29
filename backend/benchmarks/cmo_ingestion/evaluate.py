"""Run extraction first, then score isolated keys. No keys enter the pipeline.

Use --calibration-protocol for an explicitly simulated template-confirmation study.
It is not a human timing measurement. A/B/C are unavailable without real backends.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from src.manufacturing_data.cmo.pipeline import IngestionService

TARGETS={'field_recall':0.98,'auto_accepted_value_accuracy':0.99,'auto_acceptance_rate':0.8,'human_minutes_max':15}


def ratio(n,d): return n/d if d else None


def location(source):
    # PDF line numbers are extraction-method-specific. Page + field identity is
    # the supported PDF scoring granularity; no fictitious bounding-box accuracy.
    return (source['path'],source.get('sheet'),source.get('row'),source.get('column'),source.get('page'))


def identity(field):
    text=str(field['time']).replace(',','.')
    try: timestamp=float(text)
    except ValueError: timestamp=('unparsed',text)
    return (field['batch'],timestamp,field['parameter'])


def silent_omissions(run,missed):
    """Expected source values that are neither extracted nor visibly flagged.

    A miss is *visible* when its exact spreadsheet cell is flagged or ignored by
    a recorded decision, when an issue names its missing row/parameter, or (for
    documents, scored at page granularity) when an open coverage issue covers
    that file. Anything else would reach a user as silently absent data."""
    elements=run.get('elements') or []
    cells={(e['path'],e.get('sheet'),e.get('row'),e.get('column')):e['state'] for e in elements}
    flagged_docs={e['path'] for e in elements if e['state'] in {'flagged','ignored'} and e.get('row') is None}
    silent=[]
    for field in missed:
        source=field['source']; path=source['path']
        if source.get('row') is not None:
            state=cells.get((path,source.get('sheet'),source['row'],source.get('column')))
            if state in {'flagged','ignored','identifier'}: continue
            if state is None and any(i['rule_code']=='MISSING_FIELD' and i.get('path')==path and
                                     (i.get('row') in {None,source['row']}) for i in run['issues']): continue
        elif path in flagged_docs or any(i['rule_code'] in {'MISSING_PAGE','PARSE_ERROR','MISSING_FIELD','UNACCOUNTED_CONTENT'} and i.get('path')==path for i in run['issues']):
            continue
        silent.append({'path':path,'parameter':field['parameter'],'batch':field['batch'],'time':field['time'],'source':source})
    return silent


def score(run,key):
    if run['status']!='complete': return {'status':run['status'],'reasons':run.get('unavailable_reasons',[run.get('error')])}
    expected=[f for f in key['fields'] if f['present']]
    lookup=defaultdict(list)
    for field in expected: lookup[identity(field)].append(field)
    found=correct=provenance=auto_correct=0; matched=set(); mapping_correct=0
    for measurement in run['measurements']:
        # A source cell can match at most once. Prefer exact location then unmatched identity.
        indices=[i for i,f in enumerate(expected) if identity(f)==identity(measurement) and i not in matched]
        index=next((i for i in indices if location(expected[i]['source'])==location(measurement['source'])),indices[0] if indices else None)
        valid=False
        if index is not None:
            field=expected[index]; matched.add(index); found+=1
            mapping_correct+=location(field['source'])==location(measurement['source'])
            valid=(measurement['value'] is not None and measurement['unit']==field['unit'] and
                   math.isclose(measurement['value'],field['value'],rel_tol=0.005,abs_tol=1e-30))
            correct+=valid; provenance+=location(field['source'])==location(measurement['source'])
        if measurement['status']=='auto_accepted': auto_correct+=valid
    auto=sum(m['status']=='auto_accepted' for m in run['measurements'])
    silent=silent_omissions(run,[f for i,f in enumerate(expected) if i not in matched]) if 'elements' in run else None
    detected=[]
    for defect in key['defects']:
        # Stable rule AND affected source; a random warning elsewhere is not a hit.
        hit=any(i['rule_code']==defect['rule_code'] and i.get('path')==defect['path'] and
                (not defect.get('parameter') or not i.get('parameter') or defect['parameter']==i['parameter']) for i in run['issues'])
        detected.append({**defect,'detected':hit})
    classified={d['path']:d['doc_type'] for d in run['documents']}
    summary=run['summary']; n=len(run['measurements'])
    missing=[d for d in detected if d['rule_code']=='MISSING_FIELD']
    conflicts=[d for d in detected if d['rule_code']=='DUPLICATE_CONFLICT']
    expected_links={tuple(r[k] for k in ['left','right','batch','relation']) for r in key.get('relationships',[])}
    actual_links={tuple(r[k] for k in ['left','right','batch','relation']) for r in run.get('relationships',[])}
    return {'status':'executed','expected_present_fields':len(expected),'expected_missing_fields':sum(not f['present'] for f in key['fields']),
        'extracted_fields':n,'matched_fields':found,'field_recall':ratio(found,len(expected)),
        'value_and_unit_accuracy':ratio(correct,found),'source_provenance_accuracy':ratio(provenance,found),
        'provenance_granularity':'Exact spreadsheet cell/CSV row and header; PDF page and field identity (not bounding boxes)',
        'classification_accuracy':ratio(sum(classified.get(p)==k for p,k in key['documents'].items()),len(key['documents'])),
        'document_relationship_recall':ratio(len(expected_links&actual_links),len(expected_links)),
        'mapping_accuracy':ratio(mapping_correct,n),'defect_detection_rate':ratio(sum(d['detected'] for d in detected),len(detected)),
        'missing_field_detection_rate':ratio(sum(d['detected'] for d in missing),len(missing)),
        'conflict_detection_rate':ratio(sum(d['detected'] for d in conflicts),len(conflicts)),
        'defects':detected,'auto_acceptance_rate':ratio(auto,len(expected)),
        'auto_accepted_value_accuracy':ratio(auto_correct,auto),'incorrect_auto_acceptance_rate':ratio(auto-auto_correct,auto),
        'incorrect_auto_accepted_count':auto-auto_correct,'auto_accepted_count':auto,
        # Zero-silent-error measures: wrong values that skipped review, and
        # expected values absent without any visible flag.
        'silent_errors':auto-auto_correct,
        'silent_omissions':None if silent is None else len(silent),'silent_omission_examples':(silent or [])[:5],
        'missed_but_flagged':None if silent is None else len(expected)-found-len(silent),
        'coverage':run.get('coverage',{}) and {k:v for k,v in run['coverage'].items() if k!='by_document'},
        'review_groups':summary.get('review_groups'),
        'human_minutes':run['human_minutes'],'human_time_status':run['human_time_status'],
        'review_items':summary['needs_review'],'open_issues':summary['open_issues'],'corrections':summary['corrections'],
        'end_to_end_seconds':run['runtime_seconds'],'model_calls':summary['model_calls'],
        'input_tokens':summary['input_tokens'],'output_tokens':summary['output_tokens'],'inference_cost_usd':summary['inference_cost_usd'],
        'actual_parsers':sorted({m['parser'] for m in run['measurements']}),'run_id':run['id']}


def implementation_hash():
    files=sorted((Path(__file__).resolve().parents[2]/'src'/'manufacturing_data').rglob('*.py'))
    h=hashlib.sha256()
    for path in files: h.update(path.name.encode()); h.update(path.read_bytes())
    return h.hexdigest()


def confirm_in_place(service,run):
    """Automated stand-in for a reviewer who confirms every proposed layout
    without edits, then reprocesses. Not human work; exposes what such a
    confirmation would let through."""
    confirmed=0
    for layout in run['layouts']:
        mapping=layout['mapping']
        if not layout['confirmed'] and mapping['columns'] and mapping['batch_column'] and mapping['time_column']:
            service.confirm_template(run['id'],layout['fingerprint'],mapping,'automated-study-protocol',
                'Proposed mapping confirmed without edits by automated protocol; not a human interaction.',origin='study_protocol')
            confirmed+=1
    return confirmed


def evaluate(generated: Path, output: Path, *, calibration_protocol=False, configurations=('clairic_decisions','decisions','D','preview'), confirm_proposals=False, datasets=None):
    from benchmarks.common.artifact_store import asset_path
    with asset_path(generated) as local:
        return _evaluate(local, output, calibration_protocol=calibration_protocol,
                         configurations=configurations, confirm_proposals=confirm_proposals, datasets=datasets)


def _evaluate(generated: Path, output: Path, *, calibration_protocol=False, configurations=('clairic_decisions','decisions','D','preview'), confirm_proposals=False, datasets=None):
    output.mkdir(parents=True,exist_ok=True)
    if (output/'report.json').exists(): raise ValueError('Use a fresh result directory to preserve prior results')
    frozen_code=implementation_hash()
    catalog=json.loads((generated/'catalog.json').read_text())
    records=[]; snapshots=[]
    for configuration in configurations:
        for dataset in datasets or sorted({c['dataset'] for c in catalog}):
            dataset_items=[c for c in catalog if c['dataset']==dataset]
            for condition in ['unseen','returning','changed']:
                item=next(c for c in dataset_items if c['condition']==condition)
                service=IngestionService(output/'stores'/f'{configuration}-{dataset}-{condition}')
                # Unseen has no template state. Returning/changed use only disjoint
                # calibration packages; NEVER their evaluation keys or held-out values.
                if calibration_protocol and condition!='unseen' and not service.availability(configuration,synthetic=item['synthetic']):
                    calibration=next(c for c in dataset_items if c['condition']=='calibration')
                    calibration_run=service.run(generated/calibration['id']/'raw',calibration['cmo'],'preview',synthetic=calibration['synthetic'])
                    if calibration_run['status']!='complete': raise RuntimeError(calibration_run.get('error'))
                    for layout in calibration_run['layouts']:
                        mapping=layout['mapping']
                        if mapping['columns'] and mapping['batch_column'] and mapping['time_column']:
                            service.confirm_template(calibration_run['id'],layout['fingerprint'],mapping,
                                'automated-study-protocol','Public vocabulary draft confirmed by automated calibration protocol; not a human interaction.',origin='study_protocol')
                run=service.run(generated/item['id']/'raw',item['cmo'],configuration,synthetic=item['synthetic'])
                run['package_id']=item['id']; service.save(run)
                snapshots.append((configuration,dataset,condition,item,run))
                if confirm_proposals and run['status']=='complete' and confirm_in_place(service,run):
                    again=service.run(generated/item['id']/'raw',item['cmo'],configuration,synthetic=item['synthetic'])
                    again['package_id']=item['id']; service.save(again)
                    snapshots.append((configuration,dataset,condition+'+confirmed',item,again))
    # Deliberate two-phase boundary: all extraction is finished before any key is opened.
    for configuration,dataset,condition,item,run in snapshots:
        key_path=generated/item['id']/'evaluation'/'answer_key.json'
        key=json.loads(key_path.read_text())
        for file in key['files']:
            actual=hashlib.sha256((generated/item['id']/'raw'/file['path']).read_bytes()).hexdigest()
            if actual!=file['sha256']: raise ValueError('Held-out package changed since key generation')
        records.append({'configuration':configuration,'dataset':dataset,'condition':condition,
                        'package_sha256':hashlib.sha256(json.dumps(key['files'],sort_keys=True).encode()).hexdigest(),
                        **score(run,key)})
    if implementation_hash()!=frozen_code: raise ValueError('Extraction code changed during evaluation; discard this run')
    report={'protocol_version':'cmo-1','targets':TARGETS,'implementation_sha256':frozen_code,
        'calibration_protocol':'Automated confirmation of public vocabulary proposals on calibration packages; not human work' if calibration_protocol else 'No calibration confirmations',
        'confirmation_protocol':('"+confirmed" rows: proposed layouts on the held-out package confirmed without edits by an automated protocol, then reprocessed. '
                                 'Simulates a reviewer accepting every proposal; not human work.') if confirm_proposals else None,
        'human_study':'Not conducted. No human-time or time-savings claim is supported.',
        'scope':'100 source batches, deterministic samples per batch; three Raman channels; one generated package per condition. Synthetic Sanofi forms are intentionally limited.',
        'limitations':['A/B/C require installed Docling and configured real inference endpoints; unavailable is not a score.',
                      'preview is an additional diagnostic baseline, not configuration A.',
                      'D unseen has no confirmed templates and must route all values to review.',
                      'PDF provenance is scored at page level. OCR source agreement still requires visual review.',
                      'No controlled comparison with Invert has been conducted.'], 'results':records}
    (output/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    lines=['# CMO ingestion execution report','',report['scope'],'',report['human_study'],'',
           '| Config | Dataset | Layout | Status | Recall | Value accuracy | Auto accepted | Silent errors | Silent omissions | Missed but flagged | Unaccounted elements | Review items | Review groups | Open issues | Seconds |',
           '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    def percent(n): return '—' if n is None else f'{n:.2%}'
    for r in records:
        lines.append('| '+' | '.join([r['configuration'],r['dataset'],r['condition'],r['status'],
            percent(r.get('field_recall')),percent(r.get('value_and_unit_accuracy')),percent(r.get('auto_acceptance_rate')),
            str(r.get('silent_errors','—')),str(r.get('silent_omissions','—')),str(r.get('missed_but_flagged','—')),
            str((r.get('coverage') or {}).get('unaccounted','—')),str(r.get('review_items','—')),str(r.get('review_groups','—')),
            str(r.get('open_issues','—')),f"{r.get('end_to_end_seconds',0):.3f}"])+ ' |')
    lines+=['','## Protocol', '',report['calibration_protocol'],'',report['confirmation_protocol'] or '','## Limitations','']+['- '+s for s in report['limitations']]
    failures=[r for r in records if r['status']=='executed' and (r['field_recall']<TARGETS['field_recall'] or r.get('incorrect_auto_accepted_count',0) or r.get('silent_omissions'))]
    lines+=['','## Observed failures','']+[f"- {r['configuration']} / {r['dataset']} / {r['condition']}: recall {percent(r['field_recall'])}, {r['incorrect_auto_accepted_count']} incorrect auto-accepted values, {r.get('silent_omissions')} silent omissions ({r.get('missed_but_flagged')} misses flagged for review)." for r in failures]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages',type=Path,default=Path('benchmarks/cmo_ingestion/generated'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--calibration-protocol',action='store_true')
    parser.add_argument('--configurations',nargs='+',default=['clairic_decisions','decisions','D','preview'])
    parser.add_argument('--datasets',nargs='+',help='Datasets to score (default: every dataset in the catalog)')
    parser.add_argument('--confirm-proposals',action='store_true',help='Also score each package after automated confirmation of its proposed layouts')
    args=parser.parse_args(); report=evaluate(args.packages,args.output,calibration_protocol=args.calibration_protocol,
                                              configurations=args.configurations,confirm_proposals=args.confirm_proposals,datasets=args.datasets)
    print(json.dumps({'report':str(args.output/'report.json'),'conditions':len(report['results'])}))


if __name__=='__main__': main()
