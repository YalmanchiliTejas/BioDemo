"""Run frozen, matched trials serially; preserve every actual attempt.

Run from the repository root with PYTHONPATH=. (see REPRODUCE.md).
"""
import argparse
import json
import os
from pathlib import Path
import shlex
from benchmarks.common.case_runner import run_case
from benchmarks.common.case_protocol import ROOT, digest, save


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',nargs='+',default=['CHO-04','FRE-02'])
    parser.add_argument('--methods',nargs='+',choices=['conventional','retrieval_llm','full_rlm'],default=['conventional','retrieval_llm','full_rlm'])
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--load-local-env',action='store_true')
    parser.add_argument('--model',help='Explicit full-RLM provider/model, e.g. modal/zai-org/GLM-5.3')
    parser.add_argument('--execution-policy',choices=['fixed','adaptive'],default='fixed')
    parser.add_argument('--wall-clock-seconds',type=int,default=1800,help='Per-trial deadline (default: 1800 / 30 minutes); frozen in a separate case version')
    args=parser.parse_args()
    if args.repeats<1:parser.error('repeats must be positive')
    if args.wall_clock_seconds<1:parser.error('wall-clock-seconds must be positive')
    if args.load_local_env:
        allowed={'OPENAI_API_KEY','BIODEMO_PRIME_MODEL','BIODEMO_MODAL_PROXY_TOKEN','MODAL_PROXY_TOKEN','BIODEMO_MODAL_BASE_URL'}
        for line in (ROOT/'.env.local').read_text().splitlines():
            if '=' not in line or line.lstrip().startswith('#'):continue
            key,value=line.split('=',1);key=key.strip()
            if key in allowed and not os.environ.get(key):
                parts=shlex.split(value,comments=True)
                if len(parts)!=1:raise ValueError('Local environment value must be one literal string: '+key)
                os.environ[key]=parts[0]
    if args.model:os.environ['BIODEMO_PRIME_MODEL']=args.model
    # Verify the implementation and case bytes before each trial; don't pool a
    # development edit into a repeated fixed-version reliability series.
    def implementation_snapshot():
        return {p:digest(p) for base in ('src','prime_skills','benchmarks/common','benchmarks/baselines') for p in (ROOT/base).rglob('*')
                if p.is_file() and p.suffix in {'.py','.md','.mjs','.json'} and '__pycache__' not in p.parts}
    frozen_code=implementation_snapshot();frozen={};manifests={}
    for cid in args.cases:
        bid='cho' if cid.startswith('CHO-') else 'fresenius'
        manifest=ROOT/'benchmarks/manifests'/bid/(cid+'-raw')/'case.json'
        if args.execution_policy=='adaptive' or args.wall_clock_seconds!=900:
            from benchmarks.common.execution_policy import freeze_execution_variant
            adaptive=args.execution_policy=='adaptive'
            suffix=('adaptive-v1' if adaptive else 'fixed-v1')
            if args.wall_clock_seconds!=900:suffix+='-'+str(args.wall_clock_seconds)+'s'
            manifest=freeze_execution_variant(manifest,manifest.parent.with_name(cid+'-raw-'+suffix),
                soft=48,hard=72 if adaptive else 48,mode='adaptive_v1' if adaptive else 'fixed_v1',
                wall_clock_seconds=args.wall_clock_seconds)
        manifests[cid]=manifest
        frozen[manifest]=digest(manifest)
    for cid in args.cases:
        bid='cho' if cid.startswith('CHO-') else 'fresenius'
        for method in args.methods:
            for trial in range(args.repeats):
                if implementation_snapshot()!=frozen_code or any(not p.exists() or digest(p)!=h for p,h in frozen.items()):
                    raise RuntimeError('Implementation/case changed during frozen series; remaining trials not run.')
                path=run_case(manifests[cid],method)
                run=json.loads(path.read_text())
                print(json.dumps({'case':cid,'method':method,'trial':trial+1,'status':run['status'],'run':str(path)}),flush=True)
                # Authentication/payment failures are infrastructure blockers;
                # repeatedly paying for ingestion cannot test model reliability.
                diagnostics=' '.join(p.read_text() for p in (path.parent/'runtime-artifacts').glob('*.stderr'))
                if 'provider_payment_required' in diagnostics or 'authentication is missing' in diagnostics or 'proxy auth required' in diagnostics:
                    print(json.dumps({'remaining_trials':'blocked_provider_access','method':method}),flush=True)
                    break


if __name__=='__main__':main()
