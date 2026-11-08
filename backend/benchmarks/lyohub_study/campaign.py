"""Frozen LyoHUB modeling-tool campaign; reuses restricted Prime experiment host."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from benchmarks.lyo_study import run_agents as runner
from benchmarks.lyo_study import study
from benchmarks.lyo_study.sensitivity import SYSTEM
from benchmarks.lyohub_study import models
from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile

VERSION='lyohub-model-tool-20261107-v1'
ROOT=Path(__file__).resolve().parents[3]
ARMS={'A':'Agent · no prepared model','B':'Agent + LyoPRONTO','C':'Agent + Sievance model'}
SOURCES=['backend/benchmarks/lyohub_study/'+n for n in ('campaign.py','models.py','upstream_worker.py')]+[
 'backend/benchmarks/lyo_study/run_agents.py','backend/benchmarks/lyo_study/study.py',
 'backend/benchmarks/lyo_study/sdk_sensitivity.mjs','backend/benchmarks/lyo_study/sdk_sensitivity_policy.mjs',
 'backend/benchmarks/physics_value/research_sandbox.py','backend/benchmarks/physics_value/lyo_reference.py',
 'backend/src/lifesci/lyophilization/heterogeneous.py','backend/src/prime_runtime/provider_config.mjs']
PROMPT=SYSTEM+'''
This new tool-comparison protocol fits both supplied models on remaining-ice observations only.
The thermal observation is NOT treated as an equivalent LyoPRONTO front/bottom thermometer.
Read the returned model identity, applicability and limitations. A prepared model is not ground truth.
The two prepared tools differ in physics/observables; numerical-only agents may derive their own physics.
'''


def read(path):return runner.strict_json(Path(path).read_text())
def hashed(value):return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
def code_hashes():return {p:runner.digest(ROOT/p) for p in SOURCES}


def prepare(base):
    base=Path(base).resolve();dataset=base/'frozen';study.verify_dataset(dataset)
    archived=read(ROOT/'docs/case_studies/lyo-study-20261102/summary.json')['agent_protocol']
    cases=sorted(p.name for p in (dataset/'public').iterdir() if p.is_dir())
    packets={f'{case}/{task}':runner.digest(dataset/'public'/case/(task+'.json')) for case in cases for task in ('forecast','pretransfer')}
    if packets!=archived['public_packet_sha256']:raise ValueError('Public packets differ from archived study')
    profile=hosted_research_profile()
    if profile is None:raise ValueError('saved research model unavailable')
    import numpy,scipy
    protocol={'version':VERSION,'date':'2026-11-07','issue':'https://github.com/YalmanchiliTejas/BioDemo/issues/28',
      'model':f'{profile.provider}/{profile.model}','case_ids':cases,'tasks':['forecast','pretransfer'],'arms':ARMS,
      'planned_attempts':len(cases)*6,'model_calls':8,'tool_calls':8,'wall_seconds':240,'max_output_tokens':4096,
      'workers':4,'reasoning_effort':'low','system_prompt':PROMPT,'system_prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
      'sdk_script':str(ROOT/'backend/benchmarks/lyo_study/sdk_sensitivity.mjs'),
      'public_packet_sha256':packets,'source_sha256':code_hashes(),'upstream_commit':models.PIN,
      'upstream_repository':'https://github.com/LyoHUB/LyoPRONTO','upstream_version':'1.2.0',
      'dependencies':{'numpy':numpy.__version__,'scipy':scipy.__version__},
      'calibration':'B/C remaining-ice only; soft_l1; 1e-5 kg; .6..1.8 multipliers; max_nfev16; no pretransfer fit',
      'calibration_change':'Historical C used thermometry and ice; new C uses ice only for common observable support',
      'lyopronto_mapping':'cSolid=1.5*(1-porosity) g/mL; frozen height matched; native ice mass retained (~0.85% mismatch); front temperature; 1e6 native-unit/min ramps; dt=None terminal event',
      'capacity_policy':'Same wrapper gate: no usable prescribed-pressure completion forecast after vapor/condenser overload or observed pressure discrepancy',
      'scoring_reference':'Original synthetic two-population reference, inaccessible to agents; shared physical laws and approximate structure favor C; no independent experimental validation',
      'scope':'Reused 24 synthetic cases; one fresh realization per case/task/arm; no manufacturing actions or Purdue endorsement',
      'budget_usd':10,'order':'All six arm permutations cycle by sorted case, same for both tasks; four concurrent case/task blocks',
      'no_retry':'Scored failures retained; resume fills only slots with no prior attempt directory'}
    path=base/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen protocol differs')
    runner.dump(path,protocol)
    return protocol


def verify(base):
    base=Path(base).resolve();p=read(base/'protocol.json')
    if p['source_sha256']!=code_hashes():raise ValueError('frozen source changed')
    for key,v in p['public_packet_sha256'].items():
        if runner.digest(base/'frozen/public'/Path(key).with_suffix('.json'))!=v:raise ValueError('public packet changed')
    return p


def controls(base):
    base=Path(base).resolve();p=verify(base);output=base/'controls';output.mkdir(exist_ok=True)
    def one(case,task,arm):
        target=output/case/task/(arm+'.json')
        if target.exists():return read(target)
        packet=read(base/'frozen/public'/case/(task+'.json'));t=time.monotonic()
        try:
            out=models.evaluate(packet,arm);error=None
        except Exception as exc:
            out={'submission':None,'predictions':{},'raw':{}};error=type(exc).__name__+': '+str(exc)
        truth=read(base/'frozen/evaluator'/case/(task+'.json'))
        record={'case_id':case,'task':task,'arm':arm,'family':truth['family'],'error':error,'wall_seconds':time.monotonic()-t,
            'packet_sha256':p['public_packet_sha256'][f'{case}/{task}'],**out,
            'score':study.score(out['submission'],truth['outcomes'],packet['config']['load_vials'])}
        runner.dump(target,record)
        print(json.dumps({'control':case,'task':task,'arm':arm,'error':error}),flush=True)
        return record
    rows=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(one,c,t,a) for c in p['case_ids'] for t in p['tasks'] for a in ('B','C')]
        for future in as_completed(futures):rows.append(future.result())
    rows=sorted(rows,key=lambda r:(r['case_id'],r['task'],r['arm']))
    runner.dump(output/'results.json',rows)
    runner.dump(output/'manifest.json',{f'{r["case_id"]}/{r["task"]}/{r["arm"]}.json':runner.digest(output/r['case_id']/r['task']/(r['arm']+'.json')) for r in rows})
    return {'controls':len(rows),'errors':sum(bool(r['error']) for r in rows)}


class MatchedTools(runner.HostTools):
    base=None
    def call(self,name,args):
        if name!='physical_forward_model' or self.arm not in ('B','C'):return super().call(name,args)
        started=time.perf_counter()
        try:
            if self.submission is not None:raise ValueError('decision already frozen')
            if len(self.history)>=self.budget:raise ValueError('tool budget exhausted')
            if not isinstance(args,dict) or set(args)!={'action_id'} or args['action_id'] not in {a['id'] for a in self.packet['allowed_actions'] if a['id']!='characterize'}:
                raise ValueError('one allowed operating action_id required; no overrides')
            path=self.base/'controls'/self.packet['case_id']/self.packet['task']/(self.arm+'.json')
            manifest=read(self.base/'controls/manifest.json')
            key=f'{self.packet["case_id"]}/{self.packet["task"]}/{self.arm}.json'
            if runner.digest(path)!=manifest[key]:raise ValueError('frozen control artifact changed')
            record=read(path)
            packet_hash=runner.digest(self.base/'frozen/public'/self.packet['case_id']/(self.packet['task']+'.json'))
            if record['packet_sha256']!=packet_hash:raise ValueError('model packet changed')
            if record['error']:raise ValueError(record['error'])
            result=deepcopy(record['predictions'][args['action_id']])
            # Precomputed only from public data; never return the selector or reference.
            json.dumps(result,allow_nan=False)
        except Exception as exc:result={'error':type(exc).__name__+': '+str(exc)[:1200]}
        self.history.append({'name':name,'arguments':deepcopy(args),'result':deepcopy(result),'wall_seconds':time.perf_counter()-started})
        return result


def agents(base,preflight=False):
    base=Path(base).resolve();p=verify(base);output=base/'agents';output.mkdir(exist_ok=True)
    MatchedTools.base=base;runner.HostTools=MatchedTools
    runner.isolation_probe(output)
    if preflight:
        rows=[runner.run_one(base/'frozen',output,p['case_ids'][0],'forecast',a,p,preflight=True) for a in ARMS]
        runner.dump(output/'preflight.json',rows)
        if not all(r['status']=='preflight_passed' for r in rows):raise ValueError('preflight failed')
        return {'preflight':'passed','model_calls':sum(r['model_calls'] for r in rows)}
    if not (output/'preflight.json').exists():raise ValueError('run preflight first')
    # Require complete model outputs and frozen manifest before admitting any model request.
    if len(read(base/'controls/results.json'))!=96:raise ValueError('model controls incomplete')
    rows=[];lock=threading.Lock()
    def block(index,case,task):
        for arm in runner.arm_order(index):
            r=runner.run_one(base/'frozen',output,case,task,arm,p)
            truth=read(base/'frozen/evaluator'/case/(task+'.json'))
            packet=read(base/'frozen/public'/case/(task+'.json'))
            r={**r,'family':truth['family'],'score':study.score(r['submission'],truth['outcomes'],packet['config']['load_vials'])}
            with lock:
                rows.append(r);runner.dump(output/'results.json',{'protocol_sha256':runner.digest(base/'protocol.json'),'records':rows})
                print(json.dumps({'attempted':len(rows),'of':p['planned_attempts'],'case':case,'task':task,'arm':arm,'status':r['status']}),flush=True)
    with ThreadPoolExecutor(max_workers=p['workers']) as pool:
        futures=[pool.submit(block,i,c,t) for i,c in enumerate(p['case_ids']) for t in p['tasks']]
        for f in as_completed(futures):f.result()
    return {'attempted':len(rows),'completed':sum(r['submission'] is not None for r in rows)}


if __name__=='__main__':
    load_env_file(ROOT/'backend/.env.local')
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','controls','preflight','agents']);parser.add_argument('--base',type=Path,required=True)
    args=parser.parse_args();result=prepare(args.base) if args.command=='prepare' else controls(args.base) if args.command=='controls' else agents(args.base,preflight=args.command=='preflight')
    print(json.dumps(result,indent=2))
