"""Independent scorer replay on exact saved outputs; never a new agent attempt."""
import argparse
import json
from pathlib import Path
import time
from benchmarks.common.case_protocol import ROOT,digest,save
from benchmarks.common.input_store import materialize
from benchmarks.common.objective_scores import score_objective


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',nargs='+',required=True)
    args=parser.parse_args();results=[]
    for identifier in args.run_id:
        if Path(identifier).name!=identifier:raise ValueError('Expected run identifier, not a path')
        directory=ROOT/'results/evaluation'/identifier
        run=json.loads((directory/'run.json').read_text());case=run['case']
        manifest=ROOT/'benchmarks/manifests'/case['benchmark_id']/(case['case_id']+'-'+case['condition'])
        reference=json.loads((manifest/case['reference']).read_text())
        if digest(manifest/case['reference'])!=case['reference_sha256']:raise ValueError('Frozen reference changed')
        if digest(directory/'output.json')!=run['output_sha256']:raise ValueError('Saved output changed')
        materialize(manifest/'case.json')
        tick=time.monotonic()
        scores=score_objective(json.loads((directory/'output.json').read_text()),reference,case,manifest/case['input_root'])
        results.append({'run_id':identifier,'output_sha256':run['output_sha256'],
                        'scorer_sha256':digest(ROOT/'benchmarks/common/objective_scores.py'),
                        'scoring_seconds':time.monotonic()-tick,'scores_identical_to_recorded':scores==run['objective_scores'],
                        'scores':scores,'new_agent_execution':False})
        print(json.dumps({k:v for k,v in results[-1].items() if k!='scores'}),flush=True)
    save(ROOT/'results/publication/evaluator-replay.json',{'replays':results,'scientific_qualification':'not_established'})
    if not all(r['scores_identical_to_recorded'] for r in results):raise SystemExit(1)


if __name__=='__main__':main()
