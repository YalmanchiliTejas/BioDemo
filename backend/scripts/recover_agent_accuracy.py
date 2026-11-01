"""Rescore immutable, actually emitted native GLM answers without inference.

Keeps original adapter failures and budget-blocked tasks separate from content
accuracy. A single structured JSON answer may have explanatory text around it.
"""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from benchmarks.workflow_agents.campaign import score_answer


def recover(suite, output):
    if output.exists():raise ValueError('Use a new recovery directory; original and prior scores are immutable')
    output.mkdir(parents=True)
    protocol=json.loads((suite/'protocol.json').read_text());lookup={c['id']:c for c in protocol['cases']}
    rows=[json.loads(l) for l in (suite/'attempts.jsonl').read_text().splitlines()]
    parser=Path(__file__).resolve().parents[1]/'src/prime_runtime/task_response.mjs'
    javascript=f"import {{parseTaskResponse}} from {json.dumps(parser.as_uri())}; import {{readFileSync}} from 'node:fs'; try {{process.stdout.write(JSON.stringify({{response:parseTaskResponse(JSON.parse(readFileSync(0,'utf8')))}}));}} catch(e) {{process.stdout.write(JSON.stringify({{error:'missing_or_ambiguous_structured_answer'}}));}}"
    recovered=[]
    for row in rows:
        receipt=json.loads((suite/row['run_path']).read_text());directory=(suite/row['run_path']).parent
        workspace=Path(receipt['runtime_workspace'])
        paths=list(workspace.glob('state/blackboards/prime-runtime/sessions/evaluation-case/*.jsonl'))
        if len(paths)!=1:raise ValueError('Expected exactly one original root agent session')
        session=paths[0];events=[json.loads(l) for l in session.read_text().splitlines()]
        messages=[e['message'] for e in events if isinstance(e.get('message'),dict)]
        paid=[m for m in messages if m.get('role')=='assistant' and any((m.get('usage') or {}).get(k,0)>0 for k in ('input','output','cacheRead'))]
        run=subprocess.run(['node','--input-type=module','-e',javascript],input=json.dumps(messages),capture_output=True,text=True,check=True)
        parsed=json.loads(run.stdout);response=parsed.get('response')
        exposed=set()
        preparation=directory/'runtime-artifacts/analysis-preparation.json'
        if preparation.exists():exposed.update(json.loads(preparation.read_text()).get('evidence_ids',[]))
        for p in (directory/'runtime-artifacts').glob('*.tools.jsonl'):
            for line in p.read_text().splitlines():
                if not line.strip():continue
                event=json.loads(line)
                if event.get('ok'):exposed.update(event.get('evidence_ids',[]))
        grounding=bool(response and set(response['evidence_ids'])<=exposed and receipt.get('audit',{}).get('pass') and receipt.get('isolation_audit',{}).get('pass'))
        spec=suite/lookup[row['case_id']]['manifest'];gold=json.loads((spec.parent/'reference.json').read_text())['answer']
        answer=response.get('task_answer') if response else None
        scores=score_answer(row['family'],answer,gold) if paid else None
        final=next((m for m in reversed(messages) if m.get('role')=='assistant'),{})
        final_text=''.join(c.get('text','') for c in final.get('content',[]) if c.get('type')=='text')
        result={'case_id':row['case_id'],'family':row['family'],'model':row['model'],
            'original_adapter_status':row['status'],'agent_executed':bool(paid),'root_model_messages':len(paid),
            'answer':answer,'answer_recovered':bool(response),'grounding_pass':grounding,
            'elapsed_seconds':row['elapsed_seconds'],'scores':scores,
            'source_session_sha256':hashlib.sha256(session.read_bytes()).hexdigest(),
            'original_receipt_sha256':hashlib.sha256((suite/row['run_path']).read_bytes()).hexdigest(),
            'final_response_sha256':hashlib.sha256(final_text.encode()).hexdigest()}
        recovered.append(result)
    (output/'attempts.jsonl').write_text('\n'.join(json.dumps(r,sort_keys=True) for r in recovered)+'\n')
    summary={'version':'actual-agent-answer-recovery-v2','model':protocol['model'],'planned':len(rows),
        'agent_executed':sum(r['agent_executed'] for r in recovered),
        'not_admitted':sum(not r['agent_executed'] for r in recovered),
        'answers_recovered':sum(r['answer_recovered'] for r in recovered),
        'families':{},'original_protocol_sha256':protocol['sha256'],
        'original_attempts_sha256':hashlib.sha256((suite/'attempts.jsonl').read_bytes()).hexdigest(),
        'parser_sha256':hashlib.sha256(parser.read_bytes()).hexdigest(),
        'method':'Offline deterministic rescore of original final agent messages; no inference, answer-key selection or narrative interpretation.',
        'scope':'Controlled synthetic operational tasks using native Prime/GLM tools, not production QA-report completion or expert-reviewed causal accuracy.'}
    for family in ('investigations','deviations','ingestion','scheduling'):
        selected=[r for r in recovered if r['family']==family];executed=[r for r in selected if r['agent_executed']]
        totals={k:sum((r['scores'] or {}).get('classification',{}).get(k,0) for r in executed) for k in ('tp','fp','fn')}
        tp,fp,fn=(totals[k] for k in ('tp','fp','fn'));latency=sorted(r['elapsed_seconds'] for r in executed if r['answer_recovered'])
        summary['families'][family]={'planned':len(selected),'agent_executed':len(executed),
            'not_admitted':len(selected)-len(executed),'answers_recovered':sum(r['answer_recovered'] for r in executed),
            'content_exact_correct':sum(r['scores']['exact'] for r in executed),
            'content_exact_accuracy':sum(r['scores']['exact'] for r in executed)/len(executed) if executed else None,
            'grounded_exact_correct':sum(r['scores']['exact'] and r['grounding_pass'] for r in executed),
            'original_adapter_completed':sum(r['original_adapter_status']=='completed' for r in executed),
            'classification':{**totals,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
                              'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None} if family!='scheduling' else None,
            'answer_latency_sample_count':len(latency),
            'answer_latency_seconds':{f'p{p}':latency[math.ceil(p/100*len(latency))-1] if latency else None for p in (50,90,99)}}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();recover(args.suite.resolve(),args.output.resolve())
