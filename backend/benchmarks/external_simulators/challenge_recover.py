"""Reconcile durable original attempts; do not rerun lost/unknown sessions."""
import argparse,json,time,shutil
from pathlib import Path
from .experiment import checked,dump,sha
from .run_agents import aggregate,failed_attempt


def progress(run):
    receipts=[json.loads(p.read_text()) for p in (run/'attempts').glob('*/*/*/run.json')]
    payload={'saved_attempts':len(receipts),'completed':sum(r['score'] is not None for r in receipts),
        'failed':sum(r['score'] is None for r in receipts),'latest_receipt_age_seconds':round(time.time()-max(p.stat().st_mtime for p in (run/'attempts').glob('*/*/*/run.json')),1)}
    dump(run/'durable-progress.json',payload);return payload


def reconcile(dataset,run,exception_file):
    protocol=json.loads((run/'protocol.json').read_text());catalogue=checked(dataset,'public/catalogue.json');records=[];recovered=[]
    if not exception_file.exists():raise ValueError('Wait for the original runner to exit and retain its exception before reconciliation')
    shutil.copy2(run/'results.json',run/'results-before-reconciliation.json')
    detail=exception_file.read_text()
    for item in catalogue:
        for repeat in range(1,protocol['repeats']+1):
            for arm in ('A','B'):
                work=run/'attempts'/item['case_id']/f'repeat-{repeat:02d}'/arm
                if (work/'run.json').exists():r=json.loads((work/'run.json').read_text())
                else:
                    if not (work/'agent-input/packet.json').exists():raise ValueError('Unstarted arm still requires its original planned attempt: '+str(work))
                    r=failed_attempt(run,dict(item,repeat=repeat),arm,protocol,
                        'Original worker exited without a durable result; transport/runner exception. Unknown submission conservatively scored as failed; not rerun.',detail)
                    recovered.append({'case':item['case_id'],'repeat':repeat,'arm':arm})
                records.append(r)
    assert len(records)==protocol['planned_attempts']
    result=aggregate(records,protocol,'complete')
    result['runner_reconciliation']={'recovered_lost_receipts':recovered,'all_other_original_receipts_unchanged':True,'replayed_agent_attempts':0,
        'original_exception_sha256':sha(exception_file),'scope':'Restore complete denominators from durable original attempts; unavailable results are failures, not imputed successes.'}
    dump(run/'results.json',result);dump(run/'reconciliation.json',result['runner_reconciliation']);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--dataset',type=Path);p.add_argument('--exception-file',type=Path);a=p.parse_args()
    if a.exception_file:
        r=reconcile(a.dataset,a.run,a.exception_file);print({'attempted':r['attempted'],'completed':r['completed'],'reconciliation':r['runner_reconciliation']})
    else:print(progress(a.run))
