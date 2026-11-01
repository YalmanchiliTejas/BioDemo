"""Export actual-agent answers and hidden-key scores after a frozen campaign.

Only synthetic source fixtures, selected task answers and metrics become public.
Provider credentials, model transcripts and runtime error strings remain private.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from benchmarks.common.case_protocol import load_case, stable_hash


def export(suite, destination, allow_partial=False):
    protocol=json.loads((suite/'protocol.json').read_text())
    if protocol['sha256']!=stable_hash({k:v for k,v in protocol.items() if k!='sha256'}):raise ValueError('Frozen protocol changed')
    reference_audit=json.loads((suite/'reference-audit.json').read_text())
    if not reference_audit['all_passed'] or reference_audit['protocol_sha256']!=protocol['sha256']:
        raise ValueError('Independent source-reference audit missing or invalid')
    rows=[json.loads(line) for line in (suite/'attempts.jsonl').read_text().splitlines()]
    if not allow_partial and len(rows)!=len(protocol['cases']):
        raise ValueError('Campaign not complete; do not publish a partial sample as the full suite')
    summary=json.loads((suite/'summary.json').read_text())
    summary['limitations'] += [
        'Fifteen data variants per workflow share four scenario templates; they are not independent factory incidents.',
        'Investigation tasks test hold-time screening, not verified root-cause analysis. Scheduling uses four jobs on one line, not factory-scale optimization.',
        'Ingestion tasks measure agent normalization and reconciliation of CSV deliveries; OCR and image extraction are not evaluated in this cohort.',
        'Deviation reference follows the source-labeled current SOP; historical effective-time reconstruction is not validated.',
    ]
    lookup={c['id']:c for c in protocol['cases']}
    cases=[]
    for row in rows:
        case=lookup[row['case_id']];manifest=suite/case['manifest'];spec=load_case(manifest)
        gold=json.loads((manifest.parent/'reference.json').read_text())
        files=[]
        for file in spec['allowlist']:
            path=manifest.parent/spec['input_root']/file['path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=file['sha256']:
                raise ValueError('Frozen input changed')
            with path.open(newline='') as stream:records=list(csv.DictReader(stream))
            files.append({'file':file['path'],'sha256':file['sha256'],'records':records})
        public={k:row.get(k) for k in ('case_id','family','model','mode','status','elapsed_seconds',
                                       'task_answer_submitted','final_report_submitted','isolation_pass','source_audit_pass','answer','scores')}
        failure=None
        if row['status']!='completed':
            receipt_path=suite/row['run_path'] if row.get('run_path') else None
            receipt=json.loads(receipt_path.read_text()) if receipt_path else {}
            errors='\n'.join(p.read_text() for p in (receipt_path.parent/'runtime-artifacts').glob('*.stderr')) if receipt_path else ''
            failure=('budget_blocked' if 'Campaign admission cap' in errors else
                     'answer_format' if 'parseTaskResponse' in errors else
                     'deadline' if 'deadline' in errors.lower() or 'wall-clock' in receipt.get('reason','') else
                     'runtime_or_source_check')
        elif not row['scores']['exact']:failure='incorrect_task_answer'
        public['failure_category']=failure
        public.update(objective=spec['objective'],reference=gold['answer'],sources=files,
                      receipt_sha256=hashlib.sha256((suite/row['run_path']).read_bytes()).hexdigest() if row.get('run_path') else None)
        cases.append(public)
    admission=suite/'modal-admission.jsonl'
    events=[json.loads(line) for line in admission.read_text().splitlines()] if admission.exists() else []
    summary.update(status='completed_controlled_agent_evaluation' if len(rows)==len(protocol['cases']) else 'partial_controlled_agent_evaluation',
        task_exact_correct=sum(r['scores']['exact'] for r in rows),
        task_exact_accuracy=sum(r['scores']['exact'] for r in rows)/len(rows) if rows else None,
        answers_present=sum(r['scores']['answer_present'] for r in rows),
        concurrency=2,
        cost={'admitted_requests':sum(e['event']=='reserved' for e in events),
              'usage_based_estimate_usd':sum(e['conservative_cost_usd'] for e in events if e['event']=='settled'),
              'invoice_status':'not_reconciled'},
        protocol_sha256=protocol['sha256'],
        reference_audit={k:v for k,v in reference_audit.items() if k!='cases'},
        input_scope='Complete controlled synthetic manufacturing tasks, not selected fragments of a larger incident.',
        methodology='Actual GLM 5.3 through the Prime SDK and scoped Manufacturing OS tools. This cohort evaluates native task answers, separately from full QA-report completion. No deterministic answer substitution or model judge.',
        timing_notice='Local agent pipeline at concurrency two. Answer percentiles include emitted structured answers; failures remain in task accuracy and terminal durations. At 15 cases per workflow, empirical p99 is the maximum and is exploratory.',
        annotation_notice='Developer-authored explicit operational rules and exhaustive scheduling references, not independently adjudicated factory incidents.')
    history=suite/'admission-history.json'
    if history.exists():
        history=json.loads(history.read_text())
        summary['admission_history']={k:history[k] for k in ('resumed_without_prior_predictions','selection_rule','original_ledger_sha256','continuation_ledger_sha256')}
        summary['timing_notice']+=' Per-task timing starts at its inference admission phase; it excludes campaign waiting during budget reconciliation. Only tasks with zero prior provider usage and no generated content were resumed.'
    for family, metrics in summary['families'].items():
        selected=[r for r in rows if r['family']==family]
        metrics['status_counts']=dict(Counter(r['status'] for r in selected))
        ordered=sorted(r['elapsed_seconds'] for r in selected)
        metrics['all_attempt_terminal_seconds']={f'p{p}':ordered[math.ceil(p/100*len(ordered))-1] if ordered else None for p in (50,90,99)}
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (destination/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    (destination/'reference-audit.json').write_text(json.dumps(reference_audit,indent=2)+'\n')
    lines=['# Actual GLM 5.3 agent accuracy', '',summary['methodology'], '',summary['annotation_notice'], '',
        f"{len(rows)}/{len(protocol['cases'])} tasks attempted. {summary['task_exact_correct']} exactly correct agent answers. {summary['answers_present']} machine-readable answers returned.", '',
        '| Workflow | Attempted / planned | Exactly correct | Precision | Recall | F1 | Answers returned | p90 seconds | p99 seconds |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    def pct(value):return '—' if value is None else f'{value:.2%}'
    def seconds(value):return '—' if value is None else f'{value:.2f}'
    for name,m in summary['families'].items():
        c=m['classification'] or {};latency=m['submitted_answer_latency_seconds']
        lines.append(f"| {name} | {m['attempted']}/{m['planned']} | {m['task_exact_correct']} | {pct(c.get('precision'))} | {pct(c.get('recall'))} | {pct(c.get('f1'))} | {m['answer_present']} | {seconds(latency['p90'])} | {seconds(latency['p99'])} |")
    lines+=['',summary['timing_notice'],'',
            'Every input/answer pair is inspectable in cases.json, including failures. Gold keys were outside agent inputs and OS-denied during execution. The deterministic parser accepts one unambiguous structured JSON answer, including when surrounded by prose; it never interprets prose or selects an answer using the key.', '',
            'Precision/recall measure returned batch/result IDs and correct normalized values. Scheduling uses independent constraint/optimality checks. These do not measure independently established root causes, regulatory compliance or production scheduling qualification.', '',
            'Calibration and earlier interrupted large-case investigations are excluded from these scored-task percentages and retained in their separate receipts.', '',
            f"Provider calls admitted: {summary['cost']['admitted_requests']}. Usage-based list-rate estimate: ${summary['cost']['usage_based_estimate_usd']:.4f}; invoice not reconciled.", '',
            f"Frozen protocol SHA-256: {protocol['sha256']}"]
    (destination/'report.md').write_text('\n'.join(lines)+'\n')
    (destination/'checksums.json').write_text(json.dumps({name:hashlib.sha256((destination/name).read_bytes()).hexdigest()
                                                       for name in ('summary.json','cases.json','report.md','reference-audit.json')},indent=2)+'\n')
    print(json.dumps({'public_output':str(destination),'attempted':len(rows),'correct':summary['task_exact_correct']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--suite',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args();export(args.suite.resolve(),args.output.resolve(),args.allow_partial)
