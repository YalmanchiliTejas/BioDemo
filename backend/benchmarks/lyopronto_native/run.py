"""Current application assistant evaluated in fresh native LyoPRONTO worlds."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from src.lifesci.gateway.providers import Completion,modal_settings
from benchmarks.agent_pilot.runner import CampaignBudget,RecordedProvider,MODEL
from .connector import NativeConversation
from .grade import grade
from .suite import ROOT,cases,references,write,digest,generate

TENANT='lyopronto-native-evaluation'


def seed(p,case):
    p.identity.assign_role(TENANT,'engineer','msat',site_id='NF1')
    ctx=p.identity.context_for(TENANT,'engineer')
    source=p.evidence.ingest(ctx,source_system='LyoPRONTO-native-case',source_record_id=case['id'],
        content=json.dumps(case['source'],sort_keys=True).encode(),media_type='application/json',site_id='NF1',
        event_time='2026-11-08T00:00:00Z',metadata={'title':'Authored native primary-drying inputs · '+case['id'],'synthetic':True})
    service=NativeConversation.attach(p.engineering_conversations)
    thread=service.create(ctx,{'site_id':'NF1'})
    return ctx,thread,source['evidence_id']


def prompt(case,source_id):
    return (f"Use the LyoPRONTO characterization source {source_id}, revision 1. Read it before calculating. "
        +case['question']+' Save the assessment using lyopronto_record_result; include native simulation result_ids when calculations are supported. '
        'Do not infer a measured outcome, operate equipment, create approvals or invent missing characterization. '
        'For report tasks preserve the scheduled inputs; for recipe tasks select only an allowed pressure/shelf pair. '
        'The native model returns flux per square metre; whole-batch rate requires product area in m2 and the vial count. '
        'Use the vial-BOTTOM temperature for T_pr_crit, and a+b*P_Torr for the whole-batch equipment line. '
        'This is an authored simulator-world task, not experimental validation.')


def settings():
    from src.lifesci.envfile import parse_env
    raw=parse_env((ROOT/'backend/.env.local').read_text()) if (ROOT/'backend/.env.local').exists() else {}
    raw.update(os.environ)
    allowed=('BIODEMO_MODAL_PROXY_TOKEN','MODAL_PROXY_TOKEN','MODAL_BASE_URL','BIODEMO_MODAL_BASE_URL','MODAL_MIN_MAX_TOKENS')
    return {k:raw[k] for k in allowed if k in raw}


def verify(base):
    base=Path(base);protocol=json.loads((base/'protocol.json').read_text());manifest=json.loads((base/'manifest.json').read_text())
    for name,value in protocol['sources_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=value:raise ValueError('Frozen code changed: '+name)
    for name,value in manifest.items():
        if hashlib.sha256((base/name).read_bytes()).hexdigest()!=value:raise ValueError('Frozen input/reference changed: '+name)
    return protocol


def episode(case,reference,directory,provider):
    directory.mkdir(parents=True,exist_ok=False)
    p=Platform(RecordStore(str(directory/'workspace.sqlite')),providers={provider.name:provider},allow_unqualified=True)
    p.gateway.max_retries=0
    ctx,thread,source_id=seed(p,case);svc=p.engineering_conversations;t=time.monotonic();error=None
    try:
        queued=svc.enqueue(ctx,thread['id'],{'text':prompt(case,source_id),'expected_revision':thread['revision']})
        svc.run_turn(ctx,thread['id'],queued['turn_ids'][-1])
    except Exception as exc:error=type(exc).__name__+': '+str(exc)[:500]
    view=svc.get(ctx,thread['id']);turn=view['turns'][-1] if view['turns'] else {}
    trace={'native_simulations':list(svc.native_results.values()),
        'action_intents':len(p.store.read().list(TENANT,'action_intent')),
        'tool_steps':turn.get('steps',[]),'gateway_runs':turn.get('gateway_runs',[]),
        'turn_status':turn.get('status'),'reply':turn.get('reply'),'questions':turn.get('questions',[]),
        'grounding':turn.get('grounding')}
    verdict=grade(case,reference,svc.assessment,trace)
    result={'case_id':case['id'],'family':case['family'],'assessment':svc.assessment,'verdict':verdict,
        'elapsed_seconds':time.monotonic()-t,'solver_calls':svc.solver_calls,'error':error,'trace':trace,
        'source_sha256':digest(case['source']),'reference_sha256':digest(reference)}
    write(directory/'result.json',result)
    p.runtime.close();p.store.release_connections()
    return result


class ContractProvider:
    """Offline host-contract double; never represented as measured model ability."""
    name='anthropic'
    def __init__(self,case):self.case=case;self.n=0;self.platform=None;self.tools_seen=[]
    def chat(self,**kwargs):
        self.n+=1;self.tools_seen.append([t['function']['name'] for t in kwargs['tools']])
        svc=self.platform.engineering_conversations
        source=self.platform.store.read().list(TENANT,'evidence',lambda s:s.get('source_system')=='LyoPRONTO-native-case')[0].id
        if self.n==1:name,args='workspace_read',{'kind':'evidence','record_id':source,'revision':1}
        elif self.n==2:name,args='lyopronto_simulate',{'source_id':source}
        elif self.n==3:
            rid,data=next(iter(svc.native_results.items()));s=data['summary'];src=self.case['source']
            name='lyopronto_record_result';args={'source_id':source,'answer_status':'completed','completion_h':s['last_elapsed_h'],
                'maximum_bottom_temperature_c':s['maximum_returned_bottom_temperature_c'],
                'peak_batch_sublimation_kg_h':s['maximum_returned_flux_kg_h_m2']*src['native_inputs']['vial']['Ap']*.0001*src['nVial'],
                'result_ids':[rid],'rationale':'Native model calculation, supplied source inputs, simulated quantities only.'}
        else:return Completion('The simulated assessment is saved for review.',1,1)
        return Completion('',1,1,tool_calls=({'id':f'contract{self.n}','name':name,'arguments':json.dumps(args)},))


def preflight(output):
    case=next(c for c in cases() if c['family']=='report');ref=references(case);provider=ContractProvider(case)
    # One clean platform, then identical ordinary assistant invocation as paid runs.
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    p=Platform(RecordStore(str(out/'workspace.sqlite')),providers={'anthropic':provider},allow_unqualified=True);p.gateway.max_retries=0;provider.platform=p
    ctx,thread,source_id=seed(p,case);svc=p.engineering_conversations
    queued=svc.enqueue(ctx,thread['id'],{'text':prompt(case,source_id),'expected_revision':thread['revision']})
    svc.run_turn(ctx,thread['id'],queued['turn_ids'][-1]);view=svc.get(ctx,thread['id']);turn=view['turns'][-1]
    trace={'native_simulations':list(svc.native_results.values()),'action_intents':len(p.store.read().list(TENANT,'action_intent'))}
    result=grade(case,ref,svc.assessment,trace)
    result.update(inference_requests=0,scope='Scripted provider + actual application ToolLoop + actual native solver; host contract only',
        tool_names=provider.tools_seen,turn_status=turn['status'])
    if any(name.startswith(('physical_','bioprocess_','cho_')) for names in provider.tools_seen for name in names):raise ValueError('Internal model tool leaked into native workspace')
    write(out/'preflight.json',result);p.runtime.close();p.store.release_connections()
    if not result['passed'] or turn['status']!='completed':raise ValueError('Native assistant preflight failed: '+json.dumps(result))
    return result


def execute(base,output):
    base=Path(base);output=Path(output);protocol=verify(base);output.mkdir(parents=True,exist_ok=False)
    limits=protocol['campaign_limits'];cfg=settings()
    token,url=modal_settings(cfg)
    if not token or not url:raise ValueError('Existing Modal credentials/endpoint are not configured')
    budget=CampaignBudget(limits['estimate_usd'],limits['max_requests'],reserve_per_request=.4,receipt_dir=output/'requests')
    deadline=time.monotonic()+limits['max_seconds'];results=[];lock=threading.Lock()
    files=sorted((base/'public').glob('*.json'))
    def one(path):
        case=json.loads(path.read_text());reference=json.loads((base/'reference'/path.name).read_text())
        provider=RecordedProvider(cfg,budget,case['id'],deadline)
        result=episode(case,reference,output/case['id'],provider)
        with lock:
            results.append(result);write(output/'results.json',{'protocol_sha256':digest(protocol),'records':results,'budget':budget.snapshot()})
            print(json.dumps({'finished':len(results),'of':24,'family':case['family'],'passed':result['verdict']['passed'],'turn_status':result['trace']['turn_status']}),flush=True)
    with ThreadPoolExecutor(max_workers=limits['workers']) as pool:
        futures=[pool.submit(one,path) for path in files]
        for future in as_completed(futures):future.result()
    return {'completed':len(results),'passed':sum(r['verdict']['passed'] for r in results),'budget':budget.snapshot()}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['generate','preflight','run']);parser.add_argument('--base',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    env={'ASSISTANT_LOOP':'tools','MODAL_EMBEDDINGS_URL':''}
    if args.command=='preflight':env.update(LIFESCI_LLM_PROVIDER='anthropic',LIFESCI_LLM_MODEL='native-contract-double')
    else:env.update(LIFESCI_LLM_PROVIDER='modal',LIFESCI_LLM_MODEL=MODEL)
    with patch.dict(os.environ,env):
        result=generate(args.output) if args.command=='generate' else preflight(args.output) if args.command=='preflight' else execute(args.base,args.output)
    print(json.dumps(result,indent=2))
