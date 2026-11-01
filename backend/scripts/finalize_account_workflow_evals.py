"""Verify persisted account runs and create four clearly titled demo overviews."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

from scripts.run_account_workflow_evals import browser_call, extract, prompt, safe_turn, FAMILIES, RESERVE
from benchmarks.workflow_agents.campaign import score_answer


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--browser',type=Path,required=True);p.add_argument('--session',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--cases',type=Path,required=True)
    args=p.parse_args();state=json.loads((args.output/'campaign.json').read_text())
    cases=json.loads(args.cases.read_text());lookup={c['case_id']:c for c in cases}
    if len(state['attempts'])!=60 or any('status' not in a for a in state['attempts'].values()):
        raise ValueError('Wait for all 60 cases; never summarize a partial run as complete')
    audit=[];families={};report_rows=[]
    for family,tid in state['threads'].items():
        d=browser_call(args,"const d=await request('/v1/process-model/conversations/'+"+json.dumps(tid)+");return {id:d.id,title:d.title,turns:d.turns};")
        if len(d['turns'])!=15:raise ValueError('Expected 15 persisted turns per workflow')
        durations=[];statuses=Counter();selected=[]
        for t in d['turns']:
            cid=t['user_text'].split('\n',1)[0].split(' — ')[1].split('.')[0]
            c=lookup[cid];a=state['attempts'][cid]
            expected=prompt(c)
            if cid=='investigations-01':
                expected=expected.replace('Assess this case independently; earlier cases in this conversation are separate datasets. ','')
            if expected.strip().replace('\r\n','\n')!=t['user_text'].strip().replace('\r\n','\n'):
                raise ValueError('Persisted input differs from submitted source task: '+cid)
            ans=extract(t.get('reply'),family);scores=score_answer(family,ans,c['reference'])
            if scores!=a['scores'] or t['id']!=a['turn_id']:raise ValueError('Persisted answer/grade identity changed')
            routes=[run.get('route',{}) for run in t.get('gateway_runs',[])]
            if any(r.get('model')!='zai-org/GLM-5.3' or r.get('provider')!='modal' for r in routes):
                raise ValueError('Unexpected deployed provider/model')
            row={'case_id':cid,'thread_id':tid,'turn':safe_turn(t),'answer':ans,'scores':scores,
                 'actual_input_sha256':hashlib.sha256(t['user_text'].encode()).hexdigest()}
            (args.output/(cid+'.json')).write_text(json.dumps(row,indent=2)+'\n')
            audit.append({'case_id':cid,'turn_id':t['id'],'input_matches':True,'answer_matches':True,
                          'actual_input_sha256':row['actual_input_sha256']})
            statuses[t['status']]+=1;selected.append(row);report_rows.append(row)
            if t.get('elapsed_seconds') is not None:durations.append(t['elapsed_seconds'])
        durations.sort();classification={key:sum((r['scores'].get('classification') or {}).get(key,0) for r in selected) for key in ('tp','fp','fn')}
        tp,fp,fn=(classification[k] for k in ('tp','fp','fn'))
        classification.update(precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
                              f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)
        families[family]={'reports':len(selected),'correct_task_answers':sum(r['scores']['exact'] for r in selected),
            'status_counts':dict(statuses),'classification':classification if family!='scheduling' else None,
            'reported_turn_latency_seconds':{f'p{k}':durations[math.ceil(k/100*len(durations))-1] if durations else None for k in (50,90,99)},
            'latency_sample_count':len(durations),'thread_id':tid}
    if len(audit)!=60 or len({a['case_id'] for a in audit})!=60:raise ValueError('Persisted case coverage differs')
    (args.output/'persistence-audit.json').write_text(json.dumps({'verified_cases':60,'all_inputs_and_answers_match':True,'cases':audit},indent=2)+'\n')
    repair_path=args.output/'report-followups.json'
    repairs=json.loads(repair_path.read_text()) if repair_path.exists() else {}
    for original in report_rows:
        if original['turn'].get('reply'):continue
        cid=original['case_id']
        if cid in repairs and repairs[cid].get('status'):continue
        cost_so_far=sum(a.get('conservative_accounting_usd',0) for a in state['attempts'].values())+sum(r.get('accounting_usd',RESERVE) for r in repairs.values())
        if cost_so_far+RESERVE>state['budget_usd']:raise ValueError('Follow-up exceeds accounting budget')
        text=f'Report follow-up — {cid}\nThe original saved request was blocked before displaying a report. '
        text+='Return a compact report UNDER 1800 CHARACTERS including the requested task_answer JSON, source row citations, one limitation and next review step. '
        text+='Preserve synthetic/unverified classification. The original failed request remains in the evaluation record.\n'+prompt(lookup[cid])
        if len(text)>4000:raise ValueError('Follow-up exceeds message limit')
        if cid not in repairs:
            d=browser_call(args,"const d=await request('/v1/process-model/conversations','POST',{},"+json.dumps('account-evals-followup-20261101-'+cid)+");return {id:d.id,revision:d.revision};")
            repairs[cid]={'thread_id':d['id'],'original_thread_id':original['thread_id'],'submission_intent':True}
            repair_path.write_text(json.dumps(repairs,indent=2)+'\n')
            body={'text':text,'expected_revision':d['revision'],'enable_demo':False}
            browser_call(args,"const d=await request('/v1/process-model/conversations/'+"+json.dumps(d['id'])+"+'/messages','POST',"+json.dumps(body)+","+json.dumps('account-evals-followup-message-20261101-'+cid)+");return {id:d.id};")
        while True:
            d=browser_call(args,"const d=await request('/v1/process-model/conversations/'+"+json.dumps(repairs[cid]['thread_id'])+");return {turns:d.turns};")
            if not d['turns']:raise ValueError('Follow-up submission needs reconciliation')
            t=d['turns'][-1]
            if t['status'] not in ('running','queued'):break
            time.sleep(5)
        usage=[u for run in t.get('gateway_runs',[]) for u in run.get('attempts',[])]
        cost=sum((u.get('input_tokens',0)*1.4+u.get('output_tokens',0)*4.4)/1e6 if u.get('input_tokens') or u.get('output_tokens') else RESERVE for u in usage) if usage else RESERVE
        answer=extract(t.get('reply'),lookup[cid]['family'])
        repairs[cid].update(status=t['status'],turn=safe_turn(t),answer=answer,
                            scores=score_answer(lookup[cid]['family'],answer,lookup[cid]['reference']),accounting_usd=cost)
        repair_path.write_text(json.dumps(repairs,indent=2)+'\n')
        print(json.dumps({'followup':cid,'status':t['status'],'reply_present':bool(t.get('reply'))}),flush=True)
    overview_path=args.output/'overviews.json'
    overviews=json.loads(overview_path.read_text()) if overview_path.exists() else {}
    labels={'investigations':'Investigation reports','deviations':'Deviation reports','ingestion':'Data ingestion reports','scheduling':'Scheduling reports'}
    for family in FAMILIES:
        if family in overviews and overviews[family].get('status'):continue
        m=families[family];selected=sorted((r for r in report_rows if r['case_id'].startswith(family)),key=lambda r:r['case_id'])
        items=[]
        for r in selected:
            answer=r['answer'] or {}
            if family=='ingestion':details={'normalized_values':len(answer.get('measurements',[])),'review_record_ids':answer.get('review_record_ids',[])}
            elif family=='scheduling':details={'feasible':answer.get('feasible'),'makespan':r['scores'].get('makespan'),'constraint_violations':r['scores'].get('violations',[])}
            else:details=answer
            items.append({'case':r['case_id'],'status':r['turn']['status'],'correct':r['scores']['exact'],'answer':details})
        title=labels[family]+' — 15 account evaluations'
        text=title+'\nWrite a concise demo overview report (under 1800 characters) from these observed account runs. '
        text+='This is a supplied evaluation log, not new measured manufacturing evidence. Do not execute a workflow or ask to dispatch actions. '
        text+='Include: outcome; one concrete example; the 15 case IDs; limitations; next human review step. '
        text+='State that these were synthetic CSV desk reviews by the deployed GLM 5.3 Assistant, with shared conversation history per workflow. '
        text+='Distinguish correct task answers from completed app status; preserve needs_information cases and their review requirements. '
        text+='Source verification, physical simulation, manufacturing dispatch and QA approval were not performed. '
        text+='The detailed 15 reports are saved separately in conversation '+m['thread_id']+'. '
        text+='Do not claim independent factory accuracy or an improvement over the separate local benchmark. '
        text+='Do not invent precision/recall or latency numbers. Observed records: '+json.dumps(items,separators=(',',':'))
        repaired=[{'case':cid,'followup_status':r['status'],'followup_answer_present':bool(r['turn'].get('reply')),'thread_id':r['thread_id']} for cid,r in repairs.items() if cid.startswith(family)]
        if repaired:text+=' Separate follow-up reports (never substituted in first-attempt scores): '+json.dumps(repaired,separators=(',',':'))
        if len(text)>4000:raise ValueError('Overview exceeds message limit')
        spent=sum(a.get('conservative_accounting_usd',0) for a in state['attempts'].values())+sum(v.get('accounting_usd',RESERVE) for v in overviews.values())+sum(r['accounting_usd'] for r in repairs.values())
        if spent+RESERVE>state['budget_usd']:raise ValueError('Overview admission exceeds accounting budget')
        if family not in overviews:
            d=browser_call(args,"const d=await request('/v1/process-model/conversations','POST',{},"+json.dumps('account-evals-overview-20261101-'+family)+");return {id:d.id,revision:d.revision};")
            overviews[family]={'thread_id':d['id'],'title':title,'submission_intent':True}
            overview_path.write_text(json.dumps(overviews,indent=2)+'\n')
            body={'text':text,'expected_revision':d['revision'],'enable_demo':False}
            browser_call(args,"const d=await request('/v1/process-model/conversations/'+"+json.dumps(d['id'])+"+'/messages','POST',"+json.dumps(body)+","+json.dumps('account-evals-overview-message-20261101-'+family)+");return {id:d.id};")
        while True:
            d=browser_call(args,"const d=await request('/v1/process-model/conversations/'+"+json.dumps(overviews[family]['thread_id'])+");return {id:d.id,title:d.title,turns:d.turns};")
            if not d['turns']:raise ValueError('Interrupted overview submission needs reconciliation')
            t=d['turns'][-1]
            if t['status'] not in ('running','queued'):break
            time.sleep(5)
        usage=[a for run in t.get('gateway_runs',[]) for a in run.get('attempts',[])]
        cost=sum((u.get('input_tokens',0)*1.4+u.get('output_tokens',0)*4.4)/1e6 if u.get('input_tokens') or u.get('output_tokens') else RESERVE for u in usage) if usage else RESERVE
        overviews[family].update(status=t['status'],turn=safe_turn(t),accounting_usd=cost)
        overview_path.write_text(json.dumps(overviews,indent=2)+'\n')
        print(json.dumps({'overview':family,'status':t['status'],'reply_present':bool(t.get('reply'))}),flush=True)
    summary={'method':'Actual deployed Sievance Assistant; synthetic CSV desk-review tasks; 15 sequential cases per workflow conversation.',
             'reports':60,'correct_task_answers':sum(a['scores']['exact'] for a in state['attempts'].values()),
             'families':families,'model':'zai-org/GLM-5.3','provider':'modal',
             'input_case_file_sha256':hashlib.sha256(args.cases.read_bytes()).hexdigest(),
             'known_uncached_token_estimate_usd':sum(a.get('known_token_estimate_usd',0) for a in state['attempts'].values()),
             'accounting_including_overviews_usd':sum(a.get('conservative_accounting_usd',0) for a in state['attempts'].values())+sum(v['accounting_usd'] for v in overviews.values())+sum(r['accounting_usd'] for r in repairs.values()),
             'report_followups':{cid:{k:r[k] for k in ('thread_id','status','scores')} for cid,r in repairs.items()},
             'invoice_status':'not_reconciled','overviews':{f:{k:v[k] for k in ('thread_id','title','status')} for f,v in overviews.items()},
             'limitations':['Different deployed interface and report prompt from local native-task benchmark; not a paired model comparison.',
                            'Shared workflow history and repeated synthetic templates limit independence and generalization.',
                            'Assistant reviewed user-supplied CSV text; verified ingestion pipeline, OCR, full QA reporting and scheduling tool execution were not tested.',
                            'Task correctness does not imply app workflow completion; status counts and reviewer questions are retained.',
                            'At 15 tasks per workflow, p99 is the observed maximum, not a stable production tail estimate.']}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'verified_reports':60,'overview_reports':len(overviews),'correct':summary['correct_task_answers']}),flush=True)


if __name__=='__main__':main()
