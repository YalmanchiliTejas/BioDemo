"""Run synthetic tasks through an already authenticated Sievance browser.

Tokens remain inside the browser. Reports are produced by the deployed assistant,
never imported from reference answers. One inference submission per case; no retries.
"""
import argparse
import base64
import csv
import io
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.workflow_agents.campaign import score_answer

FAMILIES = ('investigations', 'deviations', 'ingestion', 'scheduling')
RESERVE = 2.25


def prompt(case):
    parts = [f'Synthetic manufacturing evaluation 2026-11-01 — {case["case_id"]}. '
             'Produce a concise reviewable report in your reply from these user-supplied synthetic CSV records. '
             'Assess this case independently; earlier cases in this conversation are separate datasets. '
             'This is a bounded desk review, not a request for simulation or a production action. '
             'State that sources are synthetic and unverified. Include findings, source filename and row references, '
             'requested task_answer JSON, limitations, and next human review step. '
             'Do not claim validated RCA or QA approval.\nTask: ' + case['objective']]
    for source in case['sources']:
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(source['records'][0]))
        writer.writeheader(); writer.writerows(source['records'])
        parts.append(source['file'] + '\n' + stream.getvalue())
    text = '\n\n'.join(parts)
    if len(text) > 4000:
        raise ValueError('Case exceeds deployed message limit; never truncate evidence')
    return text


def extract(reply, family):
    keys = {'investigations': {'affected_batch_ids'}, 'deviations': {'deviation_result_ids'},
            'ingestion': {'measurements', 'review_record_ids'}, 'scheduling': {'feasible', 'assignments'}}[family]
    candidates = []
    decoder = json.JSONDecoder()
    for index, char in enumerate(reply or ''):
        if char != '{': continue
        try: obj, _ = decoder.raw_decode(reply[index:])
        except ValueError: continue
        if isinstance(obj, dict) and keys <= obj.keys():
            if obj not in candidates: candidates.append(obj)
    return candidates[0] if len(candidates) == 1 else None


def browser_call(args, body):
    js = """(async()=>{
      const entry=Object.entries(localStorage).find(([k])=>k.startsWith('sb-')&&k.endsWith('-auth-token'));
      if(!entry)throw Error('Sign in first');
      const s=JSON.parse(entry[1]);
      const headers={Authorization:'Bearer '+s.access_token,'X-Organization-Id':localStorage.getItem('sievance.organization:'+s.user.id),'Content-Type':'application/json'};
      const request=async(path,method='GET',body=null,key=null)=>{
        const h={...headers};if(key)h['Idempotency-Key']=key;
        const r=await fetch('https://api.sievance.com'+path,{method,headers:h,...(body?{body:JSON.stringify(body)}:{})});
        if(!r.ok)throw Error('Account API HTTP '+r.status);return r.json();
      };
      BODY
    })()""".replace('BODY', body)
    result = subprocess.run([str(args.browser), '--session', args.session, 'eval', '-b',
                             base64.b64encode(js.encode()).decode()], capture_output=True, text=True, timeout=120)
    if result.returncode: raise RuntimeError('Authenticated browser operation failed: ' + result.stderr[-300:])
    data = json.loads(result.stdout)
    return json.loads(data) if isinstance(data, str) else data


def safe_turn(turn):
    # No user/organization identity or auth fields leave the browser.
    return {k: turn.get(k) for k in ('id', 'status', 'reply', 'questions', 'issues', 'system_message',
                                    'gateway_runs', 'artifacts', 'created_at', 'completed_at', 'elapsed_seconds')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--browser', type=Path, required=True);p.add_argument('--session', required=True)
    p.add_argument('--cases', type=Path, required=True);p.add_argument('--output', type=Path, required=True)
    p.add_argument('--existing-investigation-thread', required=True)
    p.add_argument('--budget-usd', type=float, default=20)
    args = p.parse_args();args.output.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.cases.read_text())
    for case in cases: prompt(case)  # Preflight every input before starting paid work.
    state_path=args.output/'campaign.json'
    if state_path.exists(): state=json.loads(state_path.read_text())
    else:
        state={'version':'sievance-account-evals-v1','started_at':datetime.now(timezone.utc).isoformat(),
               'method':'Deployed authenticated Assistant; user-supplied synthetic CSVs; four sequential workflow conversations.',
               'threads':{'investigations':args.existing_investigation_thread},'attempts':{},'budget_usd':args.budget_usd}
    def save(): state_path.write_text(json.dumps(state,indent=2)+'\n')
    save()
    if 'investigations-01' not in state['attempts']:
        state['attempts']['investigations-01']={'thread_id':args.existing_investigation_thread,'submitted_at':time.time(),'adopted_ui_submission':True}
        save()
    while True:
        pending = {v['thread_id'] for v in state['attempts'].values() if 'status' not in v}
        for tid in list(pending):
            thread=browser_call(args,f"const d=await request('/v1/process-model/conversations/'+{json.dumps(tid)});return {{id:d.id,revision:d.revision,turns:d.turns}};")
            for case_id, attempt in state['attempts'].items():
                if attempt['thread_id']!=tid or 'status' in attempt: continue
                turn=thread['turns'][-1]
                if case_id not in turn.get('user_text','').split('\n',1)[0]:
                    raise RuntimeError('Submission needs reconciliation; never reuse a different case response')
                if turn['status'] in ('running','queued'):continue
                case=next(c for c in cases if c['case_id']==case_id)
                answer=extract(turn.get('reply'),case['family'])
                usage=[]
                for run in turn.get('gateway_runs',[]):usage.extend(run.get('attempts',[]))
                known=sum((u.get('input_tokens',0)*1.4+u.get('output_tokens',0)*4.4)/1e6 for u in usage)
                unknown=sum(not u.get('input_tokens') and not u.get('output_tokens') for u in usage)
                charged=known+RESERVE*unknown
                if not usage: charged=RESERVE
                attempt.update(status=turn['status'],turn_id=turn['id'],answer=answer,
                               scores=score_answer(case['family'],answer,case['reference']),
                               conservative_accounting_usd=charged,known_token_estimate_usd=known,
                               unknown_usage_attempts=unknown,elapsed_to_observation_seconds=time.time()-attempt['submitted_at'])
                (args.output/(case_id+'.json')).write_text(json.dumps({'case_id':case_id,'family':case['family'],
                    'thread_id':tid,'turn':safe_turn(turn),'answer':answer,'scores':attempt['scores']},indent=2)+'\n')
                save();print(json.dumps({'case_id':case_id,'status':attempt['status'],'correct':attempt['scores']['exact']}),flush=True)
        pending={v['thread_id'] for v in state['attempts'].values() if 'status' not in v}
        spent=sum(v.get('conservative_accounting_usd',0) for v in state['attempts'].values())
        for family in FAMILIES:
            if len(pending)>=2:break
            tid=state['threads'].get(family)
            if tid in pending:continue
            available=sorted((c for c in cases if c['family']==family and c['case_id'] not in state['attempts']),key=lambda c:c['case_id'])
            if not available:continue
            if spent+RESERVE*(len(pending)+1)>args.budget_usd:continue
            case=available[0]
            if not tid:
                thread=browser_call(args,"const d=await request('/v1/process-model/conversations','POST',{},'account-evals-20261101-"+family+"');return {id:d.id,revision:d.revision};")
                tid=thread['id'];state['threads'][family]=tid;save()
            thread=browser_call(args,f"const d=await request('/v1/process-model/conversations/'+{json.dumps(tid)});return {{revision:d.revision}};")
            # Persist intent first; an interrupted submit is never blindly repeated.
            state['attempts'][case['case_id']]={'thread_id':tid,'submitted_at':time.time(),'submission_intent':True};save()
            body={'text':prompt(case),'expected_revision':thread['revision'],'enable_demo':False}
            result=browser_call(args,"const d=await request('/v1/process-model/conversations/'+"+json.dumps(tid)+"+'/messages','POST',"+json.dumps(body)+","+json.dumps('account-evals-20261101-'+case['case_id'])+");return {id:d.id,revision:d.revision};")
            state['attempts'][case['case_id']]['submission_confirmed']=True;save();pending.add(tid)
            print(json.dumps({'submitted':case['case_id'],'thread_id':tid}),flush=True)
        done=sum('status' in a for a in state['attempts'].values())
        if done==len(cases):break
        if not pending:
            state['stopped_reason']='Conservative admission cap; unfinished cases not submitted';save();break
        time.sleep(5)
    print(json.dumps({'completed':done,'correct':sum(a.get('scores',{}).get('exact',False) for a in state['attempts'].values()),'accounting_usd':spent}),flush=True)


if __name__=='__main__':main()
