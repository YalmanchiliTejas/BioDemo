"""Resume only tasks that produced no model output; never retry a paid failure."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from benchmarks.common.case_protocol import stable_hash


def eligible(messages, error):
    if 'Campaign admission cap reached' not in error:return False
    assistants=[m for m in messages if m.get('role')=='assistant']
    if not assistants:return False
    return all(not m.get('content') and not any((m.get('usage') or {}).get(k,0)>0
        for k in ('input','output','cacheRead','cacheWrite')) for m in assistants)


def session_messages(suite,row):
    receipt=json.loads((suite/row['run_path']).read_text());workspace=Path(receipt['runtime_workspace'])
    paths=list(workspace.glob('state/blackboards/prime-runtime/sessions/evaluation-case/*.jsonl'))
    if len(paths)!=1:raise ValueError('No unique original session')
    messages=[r['message'] for r in map(json.loads,paths[0].read_text().splitlines()) if isinstance(r.get('message'),dict)]
    error='\n'.join(p.read_text() for p in (suite/row['run_path']).parent.joinpath('runtime-artifacts').glob('*.stderr'))
    return messages,error


def plan(parent,destination):
    destination.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((parent/'protocol.json').read_text());rows=[json.loads(l) for l in (parent/'attempts.jsonl').read_text().splitlines()]
    selected={r['case_id'] for r in rows if eligible(*session_messages(parent,r))}
    assert all(not r['scores']['answer_present'] for r in rows if r['case_id'] in selected)
    pending=[c for c in protocol['cases'] if c['id'] in selected]
    for case in pending:
        manifest=Path(case['manifest']);shutil.copytree((parent/manifest).parent,(destination/manifest).parent)
    protocol.update(cases=pending,continuation_of=json.loads((parent/'protocol.json').read_text())['sha256'],
        selection_rule='Only original cases with zero provider usage, no assistant content and explicit admission-cap rejection. Paid and malformed-answer failures are never retried.',
        original_attempts_sha256=hashlib.sha256((parent/'attempts.jsonl').read_bytes()).hexdigest())
    protocol['sha256']=stable_hash({k:v for k,v in protocol.items() if k!='sha256'})
    (destination/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    print(json.dumps({'pending_unexecuted_cases':len(pending),'continuation':str(destination)}))


def merge(parent,continuation,destination):
    destination.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((parent/'protocol.json').read_text());next_protocol=json.loads((continuation/'protocol.json').read_text())
    if next_protocol['continuation_of']!=protocol['sha256']:raise ValueError('Continuation belongs to a different cohort')
    originals=[json.loads(l) for l in (parent/'attempts.jsonl').read_text().splitlines()]
    later=[json.loads(l) for l in (continuation/'attempts.jsonl').read_text().splitlines()]
    if len({r['case_id'] for r in later})!=len(later):raise ValueError('Duplicate continuation attempts are not eligible for selection')
    allowed={r['case_id'] for r in originals if eligible(*session_messages(parent,r))}
    if not {r['case_id'] for r in later}<=allowed:raise ValueError('Cannot substitute a new answer for a paid original attempt')
    selected={r['case_id']:(parent,r) for r in originals}
    for row in later:selected[row['case_id']]=(continuation,row)
    assert len(selected)==len(protocol['cases'])
    shutil.copytree(parent/'cases',destination/'cases')
    shutil.copyfile(parent/'protocol.json',destination/'protocol.json')
    shutil.copyfile(parent/'reference-audit.json',destination/'reference-audit.json')
    with (destination/'attempts.jsonl').open('x') as ledger:
        for case in protocol['cases']:
            source,row=selected[case['id']]
            original=source/row['run_path'];target=destination/row['run_path']
            shutil.copytree(original.parent,target.parent)
            row={**row,'admission_phase':'continuation' if source==continuation else 'original'}
            ledger.write(json.dumps(row,sort_keys=True)+'\n')
    with (destination/'modal-admission.jsonl').open('x') as ledger:
        for phase,source in [('original',parent),('continuation',continuation)]:
            for line in (source/'modal-admission.jsonl').read_text().splitlines():
                ledger.write(json.dumps({**json.loads(line),'admission_phase':phase},sort_keys=True)+'\n')
    (destination/'admission-history.json').write_text(json.dumps({
        'original_suite':str(parent),'continuation_suite':str(continuation),
        'resumed_without_prior_predictions':len(later),'selection_rule':next_protocol['selection_rule'],
        'original_ledger_sha256':hashlib.sha256((parent/'modal-admission.jsonl').read_bytes()).hexdigest(),
        'continuation_ledger_sha256':hashlib.sha256((continuation/'modal-admission.jsonl').read_bytes()).hexdigest(),
        'blocked_original_receipts_retained':str(parent/'attempts.jsonl')},indent=2)+'\n')
    from benchmarks.workflow_agents.campaign import report
    report(destination)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','merge'])
    p.add_argument('--parent',type=Path,required=True);p.add_argument('--continuation',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.action=='plan':plan(a.parent.resolve(),a.continuation.resolve())
    else:
        if not a.output:p.error('merge requires --output')
        merge(a.parent.resolve(),a.continuation.resolve(),a.output.resolve())
