"""Restricted existing Prime SDK sessions; paired A/B, immutable submissions."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile
from src.paths import DEFAULT_PRIME_BUNDLE
from benchmarks.physics_value.research_sandbox import profile,WORKER
from .experiment import checked,dump,sha,model_prediction,score
from .treatments import common_evidence,assert_no_supplied_model

CHO_SYSTEM='''You are a cultivation forecasting research agent. This packet contains real CHO-K1 batch measurements. Predict viable_cells_million_per_ml and glucose_g_per_l at the exact forecast_times_h. Training cultures come from OTHER experimental conditions; both reactors of this test condition are withheld from fitting. test_prefix contains only this culture measurements through72h. Use only this packet and available tools. Do not use the later test values, external files, web or pretrained recollection of this dataset. The data do not measure antibody titer. Keep is the only action; this test makes no intervention claim. A physics tool, if available, returns fitted model forecasts, not measurements. Submit once with the two predictions, action_id keep, rationale, uncertainty and evidence. Model and numerical failures and uncertain forecasts must be acknowledged.'''

SYSTEM='''You are a manufacturing research agent in a frozen external-simulator experiment.
Use only this packet and the explicitly provided tools. Source observations describe a completed earlier source process. Receiving observations describe only times through the decision cutoff; transfer tasks have NO receiving observations. Planned commands are not measured outcomes.
For every task predict terminal product_concentration and process_indicator under the KEEP receiving plan, in packet units. Also choose one allowed action to maximize the explicitly stated objective. For prediction tasks only keep is allowed. For outcome/transfer tasks forecast KEEP even when choosing another action.
Use the process observations and operating settings in this packet, and only the tools actually available in your session. If a tool supplies predictions, distinguish those from measurements. No real manufacturing accuracy or safety is established. Penicillin ends at96h, not a complete230h batch. SMPL covers upstream only. Use numerical analysis when useful. Submit exactly once with predictions, action_id, rationale, uncertainty and evidence. Do not claim real batches saved, site readiness, validated scale-up or engineer time savings.'''


def numerical(code,packet,scratch):
    if not isinstance(code,str) or len(code)>18000:
        raise ValueError('Numerical code must be at most18000 characters')
    scratch.mkdir(parents=True,exist_ok=True)
    # Python3.11's standard library is installed under the user's uv directory.
    # Permit that interpreter distribution, not the workspace or user config.
    prefix=json.dumps(str(Path(sys.prefix).resolve()))
    base=json.dumps(str(Path(sys.base_prefix).resolve()))
    own=json.dumps(str(scratch.resolve()))
    home=json.dumps(str(Path.home().resolve()))
    allowed=f'(require-any (subpath {prefix}) (subpath {base}) (subpath {own}))'
    sb='\n'.join(['(version 1)','(allow default)','(deny network*)',
        f'(deny file-read-data (require-all (require-any (subpath {home}) (subpath "/private/tmp")) (require-not {allowed})))',
        f'(deny file-write* (require-not (require-any (subpath {own}) (literal "/dev/null"))))'])+'\n'
    # Numerical Python must not gain an installed process simulator implicitly.
    # Generic NumPy/SciPy remain allowed in BOTH arms; physics is B's host tool.
    for site in Path(sys.prefix).glob('lib/python*/site-packages'):
        for name in ('fastodeint*','pensimpy','smpl'):
            for simulator_path in site.glob(name):
                sb+='(deny file-read-data (subpath '+json.dumps(str(simulator_path.resolve()))+'))\n'
    path=scratch/'numerical.sb';path.write_text(sb)
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT') if k in os.environ}
    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
               PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(scratch))
    result=subprocess.run(['sandbox-exec','-f',str(path),sys.executable,'-I','-c',WORKER],
        input=json.dumps({'code':code,'packet':packet}),text=True,capture_output=True,
        cwd=scratch,env=env,timeout=12)
    if result.returncode:
        raise RuntimeError('Numerical sandbox failed: '+result.stderr[-1200:])
    return json.loads(result.stdout)


def isolation(dataset,scratch):
    canary=dataset/'evaluator/catalogue.json'
    private=scratch.parent/'host-model-input'/'isolation-canary.json'
    dump(private,{'private_model':'must not reach numerical tool'})
    probes={
        'arithmetic':'print(int(np.sum([7,5])))',
        'evaluator_read':f'open({str(canary)!r}).read()',
        'source_code_read':f'open({str(Path(__file__).resolve())!r}).read()',
        'model_library_read':f'list(__import__("pathlib").Path({str(dataset/"model-library")!r}).iterdir())',
        'installed_simulator':'import fastodeint; print("UNEXPECTED_SIMULATOR_ACCESS")',
        'host_model_config':f'open({str(private)!r}).read()',
        'network':'import socket; socket.socket().connect(("127.0.0.1",9))',
        'credentials':'import os; print(any("TOKEN" in k or "KEY" in k for k in os.environ))'}
    results={name:numerical(code,{},scratch) for name,code in probes.items()}
    passed=results['arithmetic'].get('stdout','').strip()=='12' and results['credentials'].get('stdout','').strip()=='False'
    passed=passed and all('PermissionError' in results[k].get('error','') for k in ('evaluator_read','source_code_read','model_library_read','host_model_config','network'))
    passed=passed and not results['installed_simulator'].get('ok') and any(
        text in results['installed_simulator'].get('error','') for text in ('Operation not permitted','PermissionError','ModuleNotFoundError','file system sandbox blocked'))
    if not passed: raise RuntimeError('Isolation probes failed: '+json.dumps(results))
    return {'passed':True,'scope':'OS sandbox for arbitrary numerical Python, SDK active-tool allowlist for hosted agent; not a whole-host security proof.','probes':results}


class Host:
    def __init__(self,packet,nominal,arm,scratch,budget,paths=None,physics_packet=None):
        self.packet=packet;self.nominal=nominal;self.arm=arm;self.scratch=scratch
        self.budget=budget;self.history=[];self.submission=None
        self.paths=paths
        self.physics_packet=physics_packet if physics_packet is not None else packet

    def call(self,name,args):
        if self.submission is not None: return {'error':'decision already frozen'}
        if len(self.history)>=self.budget and name!='submit_decision': return {'error':'Tool budget exhausted; submit with limitations'}
        started=time.monotonic()
        try:
            if name=='python_analysis': result=numerical(args['code'],self.packet,self.scratch)
            elif name=='physical_forward_model' and self.arm=='B':
                if self.paths is None:
                    # Contract fixture only. Production always runs the LIVE worker.
                    result=model_prediction(self.physics_packet,self.nominal,args['action_id'])
                else:
                    self.scratch.mkdir(parents=True,exist_ok=True)
                    # Keep model configuration out of the numeric scratch, which
                    # the ordinary Python tool can read. Only the trusted worker
                    # receives this file, outside both arms' numeric read scope.
                    private=self.scratch.parent/'host-model-input';private.mkdir(exist_ok=True)
                    public=private/'forward-model-packet.json';dump(public,self.physics_packet)
                    command=[sys.executable,'-m','benchmarks.external_simulators.forward',
                        '--packet',str(public),'--action',args['action_id']]
                    for key in ('pensim','smpl','native'):command.extend(['--'+key,self.paths[key]])
                    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT') if k in os.environ}
                    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                               PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
                    completed=subprocess.run(command,cwd=Path(__file__).resolve().parents[2],
                        capture_output=True,text=True,env=env,timeout=25)
                    if completed.returncode:raise RuntimeError('Nominal simulation failed: '+completed.stderr[-800:])
                    result=json.loads(completed.stdout)
                    cached=model_prediction(self.physics_packet,self.nominal,args['action_id'])
                    if result['predictions']!=cached['predictions']:
                        raise ValueError('Live nominal output differs from frozen reproducibility record')
            elif name=='submit_decision':
                if args.get('action_id') not in self.packet['allowed_actions']: raise ValueError('Action outside public grid')
                for key in self.packet.get('forecast_fields',('product_concentration','process_indicator')):
                    value=args.get('predictions',{}).get(key)
                    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
                        raise ValueError('Finite nonnegative prediction required: '+key)
                for key in ('rationale','uncertainty'):
                    if not isinstance(args.get(key),str): raise ValueError('Required explanation: '+key)
                self.submission=json.loads(json.dumps(args))
                result={'accepted':True,'decision_frozen':True}
            else: raise ValueError('Unavailable tool')
        except Exception as exc: result={'error':type(exc).__name__+': '+str(exc)[:1000]}
        self.history.append({'name':name,'arguments':args,'result':result,'wall_seconds':time.monotonic()-started})
        return result


def attempt(dataset,output,item,arm,protocol):
    case_id=item['case_id'];work=output/'attempts'/case_id/f"repeat-{item.get('repeat',1):02d}"/arm
    work.mkdir(parents=True,exist_ok=True)
    if (work/'run.json').exists(): return json.loads((work/'run.json').read_text())
    full=checked(dataset,f'public/{case_id}/packet.json')
    packet=json.loads((output/'common-inputs'/case_id/'packet.json').read_text())
    if sha(output/'common-inputs'/case_id/'packet.json')!=protocol['common_packet_sha256'][case_id]:
        raise ValueError('Frozen common process packet changed')
    assert_no_supplied_model(packet)
    nominal=checked(dataset,f'model-library/{case_id}/nominal.json') if arm=='B' else {}
    inputs=work/'agent-input';inputs.mkdir(exist_ok=True)
    dump(inputs/'packet.json',packet)
    host=Host(packet,nominal,arm,work/'numerical-scratch',protocol['tool_calls'],
              protocol['simulator_paths'] if arm=='B' else None,physics_packet=full if arm=='B' else None)
    system_prompt=CHO_SYSTEM if packet['simulator']=='cho_real' else SYSTEM
    if packet.get('experiment_version','').startswith('operating-challenges-'):
        from .challenges import system_prompt as challenge_system_prompt
        system_prompt=challenge_system_prompt(packet['experiment_version'])
    request={'type':'initialize','bundle_root':str(DEFAULT_PRIME_BUNDLE),'cwd':str(inputs.resolve()),
             'model':protocol['model'],'task':item['task'],'arm':arm,'system_prompt':system_prompt,
             'prompt':json.dumps({'packet':packet,'budget':{'tool_calls':protocol['tool_calls'],'seconds':protocol['wall_seconds']}},separators=(',',':')),
             'timeout_seconds':protocol['wall_seconds'],'max_model_calls':protocol['model_calls'],
             'max_output_tokens':protocol['max_output_tokens'],'public_schema':{'actions':packet['allowed_actions'],'forecast_fields':packet.get('forecast_fields',['product_concentration','process_indicator'])},'preflight':False}
    process=subprocess.Popen([shutil.which('node'),str(Path(__file__).with_name('sdk_experiment.mjs').resolve())],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        cwd=inputs,env=os.environ.copy(),bufsize=1,start_new_session=True)
    events=queue.Queue();stderr=[];log=[];finished={};capability=None;started=time.monotonic()
    def read():
        for line in process.stdout: events.put(line)
        events.put(None)
    def readerr(): stderr.extend(process.stderr)
    threads=[threading.Thread(target=read,daemon=True),threading.Thread(target=readerr,daemon=True)]
    for t in threads:t.start()
    process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
    try:
        while time.monotonic()-started<protocol['wall_seconds']+20:
            if (output/'STOP').exists():break
            try: line=events.get(timeout=1)
            except queue.Empty:
                if process.poll() is not None: break
                continue
            if line is None: break
            try:event=json.loads(line)
            except ValueError:log.append({'type':'sdk_log','text':line[:1000]});continue
            log.append(event)
            if event.get('type')=='tool_request':
                response=host.call(event['name'],event.get('args',{}))
                process.stdin.write(json.dumps({'type':'tool_result','id':event['id'],'result':response})+'\n');process.stdin.flush()
            elif event.get('type')=='capability_audit':capability=event
            elif event.get('type')=='finished':finished=event;break
    finally:
        if process.poll() is None:
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        for t in threads:t.join(timeout=1)
    scored=None
    if host.submission is not None:
        # Only now read evaluator targets; SDK sees acceptance only.
        truth=checked(dataset,f'evaluator/{case_id}/truth.json')
        scored=score(packet,truth,host.submission)
    result={'case_id':case_id,'repeat':item.get('repeat',1),'simulator':item['simulator'],'task':item['task'],'arm':arm,
            'status':'completed' if scored else finished.get('status','failed'),
            'wall_seconds':time.monotonic()-started,'common_input_sha256':sha(inputs/'packet.json'),
            'capability_audit':capability,'submission':host.submission,'score':scored,
            'model':protocol['model'],'usage':finished.get('usage',[]),
            'model_calls':finished.get('model_calls'),'tool_calls':len(host.history),
            'physical_model_calls':sum(x['name']=='physical_forward_model' for x in host.history),
            'no_supplied_model_in_common_packet':True,
            'error':finished.get('error') or (''.join(stderr)[-1500:] if scored is None else None),
            'provider_billing':'unknown','real_equipment_actions':False}
    dump(work/'events.json',log);dump(work/'tools.json',host.history);dump(work/'run.json',result)
    return result


def aggregate(records,protocol,status='complete'):
    groups={}
    def mean(values):return sum(values)/len(values) if values else None
    for sim in ('pensim','mab'):
        groups[sim]={}
        for task in ('prediction','outcome','transfer'):
            groups[sim][task]={}
            for arm in ('A','B'):
                rows=[r for r in records if (r['simulator'],r['task'],r['arm'])==(sim,task,arm)]
                completed=[r for r in rows if r['score']]
                groups[sim][task][arm]={'attempted':len(rows),'completed':len(completed),'failed':len(rows)-len(completed),
                    'mean_product_relative_error':mean([r['score']['prediction_errors']['product_concentration']['normalized_absolute_error'] for r in completed]),
                    'mean_indicator_relative_error':mean([r['score']['prediction_errors']['process_indicator']['normalized_absolute_error'] for r in completed]),
                    'mean_objective_change_percent':mean([r['score']['objective_change_percent'] for r in completed]),
                    'actions_improving_objective':sum(r['score']['objective_change']>1e-8 for r in completed),
                    'mean_wall_seconds':mean([r['wall_seconds'] for r in rows if r['wall_seconds'] is not None])}
    if any(r['simulator']=='cho_real' for r in records):
        groups['cho_real']={'prediction':{}}
        for arm in ('A','B'):
            rows=[r for r in records if r['simulator']=='cho_real' and r['arm']==arm]
            done=[r for r in rows if r['score']]
            groups['cho_real']['prediction'][arm]={'attempted':len(rows),'completed':len(done),'failed':len(rows)-len(done),
                'MAE':{k:mean([r['score']['prediction_errors'][k]['absolute_error'] for r in done]) for k in ('viable_cells_million_per_ml','glucose_g_per_l')}}
    pairs={}
    for r in records:pairs.setdefault((r['case_id'],r.get('repeat',1)),{})[r['arm']]=r
    matched=all(set(p)=={'A','B'} and p['A']['common_input_sha256']==p['B']['common_input_sha256'] for p in pairs.values())
    schema_matched=all(set(p)=={'A','B'} and p['A'].get('capability_audit') and p['B'].get('capability_audit') and
        p['A']['capability_audit']['shared_tool_schema_sha256']==p['B']['capability_audit']['shared_tool_schema_sha256'] for p in pairs.values())
    return {'status':status,'protocol':protocol,'groups':groups,'attempted':len(records),
            'completed':sum(r['score'] is not None for r in records),'pair_inputs_match':matched,
            'shared_tool_schemas_match':bool(schema_matched),'records':records,
            'scope':'Exploratory external-model simulation, not plant validation; PenSim96h partial horizon; SMPL24h upstream.',
            'real_batches_saved':None,'observed_engineer_hours_saved':None,'independent_scientific_review':'not_performed'}


def failed_attempt(output,item,arm,protocol,error,trace=None):
    """Retain a runner exception as a failure; never replay an unknown submission."""
    case=item['case_id'];repeat=item.get('repeat',1)
    work=output/'attempts'/case/f'repeat-{repeat:02d}'/arm;work.mkdir(parents=True,exist_ok=True)
    if (work/'run.json').exists():return json.loads((work/'run.json').read_text())
    common=output/'common-inputs'/case/'packet.json'
    inputs=work/'agent-input';inputs.mkdir(exist_ok=True)
    if not (inputs/'packet.json').exists():shutil.copy2(common,inputs/'packet.json')
    receipt={'error':error,'traceback':trace,'scope':'Runner transport/bookkeeping failure. Any unsaved submission/tool history is unknown; no attempt replayed.'}
    dump(work/'runner-error.json',receipt)
    if not (work/'tools.json').exists():dump(work/'tools.json',[])
    if not (work/'events.json').exists():dump(work/'events.json',[])
    result={'case_id':case,'repeat':repeat,'simulator':item['simulator'],'task':item['task'],'arm':arm,
        'status':'runner_error','score':None,'submission':None,'wall_seconds':None,
        'common_input_sha256':sha(inputs/'packet.json'),'capability_audit':None,
        'model':protocol['model'],'usage':[],'model_calls':None,'tool_calls':None,'physical_model_calls':None,
        'error':error,'tool_history_unavailable':True,'provider_billing':'unknown','real_equipment_actions':False}
    dump(work/'run.json',result);return result


def safe_attempt(dataset,output,item,arm,protocol):
    try:return attempt(dataset,output,item,arm,protocol)
    except Exception as exc:
        return failed_attempt(output,item,arm,protocol,type(exc).__name__+': '+str(exc),traceback.format_exc())


def execute(dataset,output,*,workers=2,limit=None,repeats=1):
    dataset=dataset.resolve();output=output.resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Use a fresh run output')
    output.mkdir(parents=True,exist_ok=True)
    load_env_file(Path(__file__).resolve().parents[2]/'.env.local')
    profile_value=hosted_research_profile()
    if profile_value is None:raise RuntimeError('No configured research model; none selected implicitly')
    items=checked(dataset,'public/catalogue.json')
    if limit:items=items[:limit]
    if repeats<1:raise ValueError('Positive repeat count required')
    common_hashes={}
    for item in items:
        full=checked(dataset,f'public/{item["case_id"]}/packet.json')
        common=common_evidence(full);assert_no_supplied_model(common)
        destination=output/'common-inputs'/item['case_id']/'packet.json'
        dump(destination,common);common_hashes[item['case_id']]=sha(destination)
    protocol={'model':profile_value.provider+'/'+profile_value.model,'wall_seconds':120,'model_calls':8,
              'tool_calls':10,'max_output_tokens':8192,'workers':workers,'planned_attempts':2*len(items)*repeats,'repeats':repeats,
              'dataset_manifest_sha256':sha(dataset/'manifest.json'),'dataset':str(dataset),
              'simulator_paths':checked(dataset,'protocol.json')['paths'],
              'comparison_type':'AI with physics-model tool vs same AI without any supplied physics model',
              'common_packet_sha256':common_hashes,
              'A':'Common raw process evidence/settings + numerical Python. No supplied equations, model coefficients, calibration, model outputs or simulator tool.',
              'B':'Byte-identical common raw process evidence/settings + numerical Python + live physics-model tool. Model configuration/calibration remains behind that tool.',
              'case_ids':[i['case_id'] for i in items],
              'arm_difference':'B additionally gets LIVE physical_forward_model. Neither common packet contains model equations or model-derived calibration. No evaluator targets/scores returned.',
              'arm_order':'Counterbalanced by case hash; arms serial within pair; independent pairs concurrent.',
              'reasoning':'Same saved model and native low setting; separate memory-free SDK sessions.',
              'runner_sha256':{p.name:sha(p) for p in Path(__file__).parent.glob('*') if p.suffix in ('.py','.mjs')},
              'provider_billing':'unknown','system_prompt_sha256':hashlib.sha256(SYSTEM.encode()).hexdigest(),
              'cho_system_prompt_sha256':hashlib.sha256(CHO_SYSTEM.encode()).hexdigest()}
    protocol['dataset_version']=checked(dataset,'protocol.json').get('version')
    if str(protocol['dataset_version']).startswith('operating-challenges-'):
        from .challenges import system_prompt as challenge_system_prompt
        protocol['challenge_system_prompt_sha256']=hashlib.sha256(challenge_system_prompt(protocol['dataset_version']).encode()).hexdigest()
        protocol['forecast_error_normalization']='Absolute error divided by the completed visible source-history median; legacy groups relative_error labels are not actual-relative for this version. Challenge report uses exact normalization.'
    dump(output/'protocol.json',protocol)
    frozen=output/'runner-source';frozen.mkdir()
    for p in Path(__file__).parent.glob('*'):
        if p.suffix in ('.py','.mjs'):shutil.copy2(p,frozen/p.name)
    dump(output/'isolation.json',isolation(dataset,output/'isolation-probe'))
    records=[]
    def pair(item):
        if (output/'STOP').exists():return []
        order=('A','B') if (int(item['case_id'][-1],16)+item.get('repeat',1))%2 else ('B','A')
        return [safe_attempt(dataset,output,item,arm,protocol) for arm in order]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        repeated=[dict(item,repeat=r) for r in range(1,repeats+1) for item in items]
        pending={executor.submit(pair,item):item for item in repeated}
        for future in as_completed(pending):
            records.extend(future.result())
            dump(output/'results.json',aggregate(records,protocol,'running'))
            print(json.dumps({'finished_attempts':len(records),'planned':protocol['planned_attempts'],
                              'case':pending[future]['case_id'],'last_status':[r['status'] for r in records[-2:]]}),flush=True)
    result=aggregate(records,protocol,'stopped' if (output/'STOP').exists() else 'complete')
    dump(output/'results.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--repeats',type=int,default=1)
    args=parser.parse_args()
    execute(args.dataset,args.output,workers=args.workers,limit=args.limit,repeats=args.repeats)
