"""Replay mission worlds through real services. Exit 1=observed failures, 2=unavailable coverage."""
import argparse
from copy import deepcopy
from importlib.metadata import version,PackageNotFoundError
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import yaml

from . import ROOT
from .adapter import SievanceMissionAdapter
from .providers import configure
from .schema import load_case
from .graders import check,unavailable,overall
from .graders import mission as mission_grader, retrieval
from .graders.deep_eval import evaluate as deep_evaluate, simulate
from .reporting import write,metrics
from src.lifesci.ids import content_hash

BASE=Path(__file__).parent


def code_fingerprint():
    import hashlib
    paths=list((ROOT/'backend/src/lifesci').rglob('*.py'))+[p for p in BASE.glob('*.py')]+list((BASE/'graders').glob('*.py'))
    return content_hash({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})


def provider_calls(directory):
    path=Path(directory)/'provider-calls.json'
    return json.loads(path.read_text()) if path.exists() else []


def _dispatch(adapter,event,sessions,case,world):
    kind=event['type']
    if kind=='user_message':
        name=event['session']
        if name not in sessions:
            sessions[name]=adapter.open_session(adapter.mission_id)
        return adapter.send_user_message(sessions[name],event['text'])
    if kind=='enable_followup':
        return adapter.configure_followup(sessions[event['session']],case['mission_goal'],every_minutes=event.get('every_minutes'))
    if kind=='close_session':return adapter.close_session(sessions[event['session']])
    if kind in ('ingest_document','inject_document'):
        doc=event.get('document') or next(d for d in world['updates'] if d['id']==event['document_id'])
        if event.get('model_context'):
            adapter._call('model_context', mission_id=adapter.mission_id, settings=event['model_context'])
        adapter.ingest_document(adapter.mission_id,doc)
        return adapter.drain_until_idle(max_steps=4)
    if kind=='equipment_alert':
        adapter.emit_external_event(adapter.mission_id,{'type':kind,'id':event['event_id'],'content':event['content']})
        return adapter.drain_until_idle(max_steps=4)
    if kind=='duplicate_delivery':
        adapter.emit_external_event(adapter.mission_id,{'type':kind})
        return adapter.drain_until_idle(max_steps=4)
    if kind=='restart_runtime':return adapter.restart_runtime()
    if kind=='scheduled_tick':return adapter.drain_until_idle(max_steps=4)
    if kind=='inject_tool_failure':return adapter._call('inject_fault',count=event['count'])
    if kind=='seed_isolation':return adapter._call('seed_isolation')
    raise NotImplementedError(kind)


def run_case(case,directory,*,provider_env=None,variant=0,repetition=0,judge_model=None,providers=None,simulator_model=None):
    world=yaml.safe_load((BASE/'fixtures/worlds'/f"{case['world']}.yaml").read_text())
    truth=yaml.safe_load((BASE/'fixtures/truth'/f"{case['world']}.yaml").read_text())
    # Mutate public presentation only; preserve checked facts and labels.
    if variant:
        for doc in world['initial']+world['updates']+world.get('distractors',[]):
            doc['content']='Synthetic source formatting variant '+str(variant)+'\n'+doc['content']
    adapter=SievanceMissionAdapter(directory,timestamp=case['initial_clock'],provider_env=provider_env,
        max_requests=case['limits']['max_provider_requests'], max_tool_calls=case['limits']['max_tool_calls'], providers=providers)
    result={'id':case['id'],'world':case['world'],'goal':case['mission_goal'],
            'variant':variant,'repetition':repetition,'fixture_hash':content_hash({'case':case,'world':world,'truth':truth}),
            'evaluation_mode':'scripted_contract_test' if providers is not None else 'real_model',
            'timeline':[],'final_checks':[],'trace_refs':[],'evidence_directory':str(directory)}
    source_fingerprint=code_fingerprint()
    result['code_fingerprint']=source_fingerprint
    started=time.monotonic()
    sessions={}
    last_snapshot=None
    try:
        mid=adapter.start_mission('SYNTHETIC-'+case['id'],objective=case['mission_goal'],initial_documents=world['initial']+world.get('distractors',[]))
        result['mission_id']=mid
        for index,event in enumerate(case['timeline']):
            row={'at':event['at'],'type':event['type'],'expected':event.get('expect',{}),'checks':[]}
            if time.monotonic()-started>case['limits']['max_wall_seconds']:
                row['checks']=[check('mission_wall_budget',False,case['limits']['max_wall_seconds'])]
                row['status']='FAIL'
                result['timeline'].append(row)
                break
            adapter.advance_clock(event['at'])
            before=adapter.read_mission_state(mid)
            before_observations=len(adapter._observations())
            calls_before=len(provider_calls(directory))
            try:
                _dispatch(adapter,event,sessions,case,world)
                after=adapter.read_mission_state(mid)
                last_snapshot=after
                new_observations=adapter._observations()[before_observations:]
                calls_after=len(provider_calls(directory))
                row['checks']=mission_grader.grade(event.get('expect',{}),before,after,new_observations,
                    provider_calls_before=calls_before,provider_calls_after=calls_after)
                old={n['id'] for n in before['notifications']}
                row['notifications_emitted']=sum(n['id'] not in old for n in after['notifications'])
                row['completed_tool_calls']=sum(o['name']=='tool.call' and o['status']=='completed'
                    and (o.get('output') or {}).get('status')=='completed' for o in new_observations)
                row['actual_new_turns']=[{'id':t['id'],'origin':t.get('origin','user_turn'),'status':t['status']}
                    for t in after['turns'] if t['id'] not in {b['id'] for b in before['turns']}]
                if not row['checks']:
                    row['checks']=[check('application_operation_completed',True,{'operation':event['type']})]
                (Path(directory)/f'step-{index:02d}.json').write_text(json.dumps(
                    {'before':before,'after':after,'observations':new_observations,'result':row},indent=2,default=str))
            except Exception as exc:
                row['checks']=[check('application_operation_completed',False,{'exception_type':type(exc).__name__,'error':str(exc)})]
            row['status']=overall(row['checks'])
            result['timeline'].append(row)
        for skipped in case['timeline'][len(result['timeline']):]:
            result['timeline'].append({'at':skipped['at'],'type':skipped['type'],'expected':skipped.get('expect',{}),
                'status':'SKIPPED','checks':[{'name':'timeline_not_run','status':'SKIPPED','evidence':'Mission budget exhausted.'}]})
        if simulator_model:
            adaptive_session=adapter.open_session(mid)
            simulated=simulate(adapter,adaptive_session,case['mission_goal'],model=simulator_model,max_user_simulations=3)
            result['adaptive_simulation']={'sessions':1,'conversations':len(simulated),'status':'PASS',
                'limitation':'Generated user fidelity requires review; mission hard gates still apply.'}
        last_snapshot=adapter.read_mission_state(mid)
        observations=adapter._observations()
        result['final_checks']=mission_grader.grade(case['final_expect'],last_snapshot,last_snapshot,observations)
        tools=adapter.read_action_log(mid)
        result['final_checks'] += [
            check('tool_call_budget',len(tools)<=case['limits']['max_tool_calls'],len(tools)),
            check('notification_budget',len(last_snapshot['notifications'])<=case['limits']['max_emitted_notifications'],len(last_snapshot['notifications'])),
            check('step_budget',len(result['timeline'])<=case['limits']['max_test_steps'],len(result['timeline']))]
        result['retrieval']=retrieval.score(adapter.read_retrieval_log(mid),truth['required_documents'])
        result['advisory']=deep_evaluate(last_snapshot,observations,judge_model)
        result['trace_refs']=adapter.get_trace_refs(mid)
        if not result['trace_refs']:
            result['trace_export']=unavailable('langfuse_export','Unconfigured; fill evals/.env.example later.')
        else:
            result['trace_export']=adapter._call('verify_traces', trace_ids=sorted({r['trace_id'] for r in result['trace_refs']}))
            adapter._call('scores',mission_id=mid,scores=[{'name':c['name'],'value':1.0 if c['status']=='PASS' else 0.0}
                for c in result['final_checks'] if c['status'] in ('PASS','FAIL')] +
                [{'name':c['name'],'value':c['score']} for c in result['advisory'] if c.get('score') is not None],trace_id=result['trace_refs'][-1]['trace_id'])
        result['session_count']=len(last_snapshot['sessions'])
        result['turn_count']=len(last_snapshot['turns'])
        result['background_turns']=sum(t.get('origin')=='background' for t in last_snapshot['turns'])
        result['notifications']=len(last_snapshot['notifications'])
        (Path(directory)/'final-state.json').write_text(json.dumps(last_snapshot,indent=2,default=str))
    except Exception as exc:
        result['final_checks'].append(check('mission_execution',False,{'exception_type':type(exc).__name__,'error':str(exc)}))
    finally:
        result['final_checks'].append(check('code_unchanged_during_mission',code_fingerprint()==source_fingerprint,source_fingerprint,hard=True))
        result['provider_calls']=provider_calls(directory)
        result['elapsed_seconds']=time.monotonic()-started
        result['metrics']=metrics(result)
        result['status']=overall([c for e in result['timeline'] for c in e['checks']]+result['final_checks'])
        if not any(c['status']=='completed' for c in result['provider_calls']):
            result['availability']=unavailable('live_model','No successful real-model responses. Host execution is not agent-quality evidence.')
        else:
            result['availability']={'name':'live_model','status':'PASS'}
        result['billing']='Provider-reported cost when available; unknown is not zero. Profile estimates are not invoices.'
    return result


def versions():
    out={}
    for name in ('langfuse','deepeval','PyYAML'):
        try:out[name]=version(name)
        except PackageNotFoundError:out[name]='NOT_INSTALLED'
    out['code_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    out['code_dirty']=bool(subprocess.check_output(['git','-c','core.fsmonitor=false','status','--porcelain'],cwd=ROOT,text=True).strip())
    from src.lifesci.process_engineering.conversation import VERSION,OPERATIONS
    out['code_fingerprint']=code_fingerprint()
    out['prompt_version']=VERSION
    out['tool_schema_hash']=content_hash({k:v.model_json_schema() for k,v in OPERATIONS.items()})
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=['smoke','mission','memory'],default='smoke')
    parser.add_argument('--output',type=Path,default=BASE/'reports/latest.json')
    parser.add_argument('--provider-env',type=Path)
    parser.add_argument('--case',action='append',help='Optional mission file stem')
    parser.add_argument('--repetitions',type=int,default=1)
    parser.add_argument('--variants',type=int,default=1)
    parser.add_argument('--judge-model')
    parser.add_argument('--simulator-model',help='Optional DeepEval adaptive-user model; incurs separate inference.')
    parser.add_argument('--jobs',type=int,default=1,help='Independent isolated missions; 1..3')
    parser.add_argument('--compare',type=Path)
    args=parser.parse_args(argv)
    if not 1<=args.repetitions<=5 or not 1<=args.variants<=5:parser.error('repetitions and variants must be 1..5')
    if not 1<=args.jobs<=3:parser.error('jobs must be 1..3')
    configure(args.provider_env)
    paths=sorted((BASE/'missions').glob('*.yaml'))
    if args.case:paths=[p for p in paths if p.stem in args.case]
    elif args.suite=='smoke':paths=[BASE/'missions/batch_risk_watch.yaml']
    elif args.suite=='memory':paths=[BASE/'missions'/f'{s}.yaml' for s in ('sop_change_monitor','conflicting_source_revision','cross_tenant_memory_isolation')]
    if not paths:parser.error('no cases selected')
    cases=[load_case(p) for p in paths]
    run_id=time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    runs=args.output.resolve().parent/'runs'/run_id
    missions=[]
    tasks=[]
    for case in cases:
        if args.suite=='smoke':
            case=deepcopy(case)
            case['timeline']=case['timeline'][:4]
            case['final_expect']={'no_unauthorised_writes':True}
        for variant in range(args.variants):
            for repetition in range(args.repetitions):
                tasks.append((case,variant,repetition))
    def execute_task(task):
        case,variant,repetition=task
        directory=runs/f"{case['id']}-v{variant}-r{repetition}"
        return run_case(case,directory,provider_env=args.provider_env,variant=variant,
                        repetition=repetition,judge_model=args.judge_model,simulator_model=args.simulator_model)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures=[pool.submit(execute_task,task) for task in tasks]
        for future in as_completed(futures):
            result=future.result()
            missions.append(result)
            print(json.dumps({'mission':result['id'],'variant':result['variant'],'repetition':result['repetition'],
                              'status':result['status'],'provider_calls':len(result['provider_calls'])}),flush=True)
            # Preserve each completed mission even if a later process is interrupted.
            (runs/'completed-missions.json').write_text(json.dumps(missions,indent=2,default=str))
    missions.sort(key=lambda m:(m['id'],m['variant'],m['repetition']))
    unavailable_model=any(m['availability']['status']!='PASS' for m in missions)
    status=overall([{'status':m['status']} for m in missions])
    report={'schema_version':1,'suite':args.suite,'run_id':run_id,'mode':'real application services / real configured providers / synthetic isolated records',
        'status':status,'versions':versions(),'missions':missions,
        'counts':{'missions':len(missions),'events':sum(len(m['timeline']) for m in missions),
                  'sessions':sum(m.get('session_count',0) for m in missions),
                  'background_turns':sum(m.get('background_turns',0) for m in missions),
                  'provider_responses':sum(c['status']=='completed' for m in missions for c in m['provider_calls'])},
        'outstanding_work':[
            'Remote Langfuse export is unconfigured until project credentials are supplied; local structured observations are retained.',
            'DeepEval judgments require an explicitly configured judge; calibrate 3–5 judgments with domain-aware reviewers before relying on scores.',
            'Reviewed fact-memory consolidation/retirement is NOT_IMPLEMENTED; this suite measures durable mission assessments and authorized prior-work retrieval.',
            'Chunk-level retrieval is NOT_TESTABLE on the record-based workspace path.',
            'Temporal production deployment and real MES/LIMS/QMS connectors were not exercised; local runtime uses the same coordinator.',
            'External notification delivery is not enabled; in-app background publications are evaluated.',
            'Comprehensive semantic causal/physics validation requires domain review; lexical hard checks do not establish scientific accuracy.',
            'Explicit generation seeds are NOT_IMPLEMENTED by the current provider protocol; variants change fixture presentation, not model sampling seeds.' ]}
    report['outstanding_work'] += sorted({f"{m['id']}: {c['name']} {c['status']}" for m in missions
        for c in m['final_checks'] + [c for event in m['timeline'] for c in event['checks']] if c['status'] in ('FAIL','NOT_IMPLEMENTED')})
    if args.compare:
        previous=json.loads(args.compare.read_text())
        prior={m['id']:m['status'] for m in previous['missions']}
        report['comparison']=[{'mission':m['id'],'before':prior.get(m['id']),'after':m['status']} for m in missions]
    write(report,args.output)
    print(json.dumps({'report':str(args.output),'status':status,'counts':report['counts']}))
    return 2 if unavailable_model else (1 if status=='FAIL' else 2 if status in ('NOT_TESTABLE','NOT_IMPLEMENTED') else 0)

if __name__=='__main__':raise SystemExit(main())
