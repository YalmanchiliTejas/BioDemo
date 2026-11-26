"""Post-hoc motivated, prospectively frozen budget/submission-policy sensitivity.

This bundles more model turns, more wall time and a final submit-only provider
turn. It is not a pure compute-budget causal comparison. Primary failures remain
in their original cohort. Default prepares the protocol without inference.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import json
import shutil
import threading
from urllib.parse import urlparse

from . import run_agents as runner
from .recovery import campaign_balance

VERSION = 'lyo-posthoc-budget-submission-sensitivity-v1'
SYSTEM = runner.SYSTEM.replace('4 model calls', '8 model calls') + '''
This sensitivity allows 240 seconds and eight model calls. The final model call
exposes ONLY submit_decision and requires that submission. Reserve one of your
eight host tool calls for submission. Earlier submission is allowed. Numerical
analysis and physical-model outputs are still hypotheses, not validated truth.'''


def select_cases(dataset):
    selected = {}
    for path in sorted((Path(dataset) / 'evaluator').glob('*/forecast.json')):
        # Family is used solely for balanced sampling; no outcome enters selection.
        family=runner.strict_json(path.read_text())['family']
        case=path.parent.name
        if family not in selected or case < selected[family]:selected[family]=case
    return dict(sorted(selected.items()))


def sensitivity(dataset, original, output, prior_campaigns, *, execute=False, campaign=None, preflight=False):
    from .study import verify_dataset
    dataset, original, output = map(lambda value:Path(value).resolve(),(dataset,original,output))
    prior_campaigns=[Path(value).resolve() for value in prior_campaigns]
    if len(set(prior_campaigns)) != len(prior_campaigns):
        raise ValueError('Duplicate prior campaign would double count reservations')
    verification=verify_dataset(dataset)
    baseline=runner.strict_json((original / 'protocol.json').read_text())
    selected=select_cases(dataset)
    expected={'nominal','heat_transfer','product_resistance','capacity','sensor_bias','combined'}
    if set(selected) != expected:raise ValueError('Sensitivity requires all six authored families')
    cases=sorted(selected.values())
    root=Path(__file__).resolve().parent
    sources=[root/'run_agents.py',root/'sensitivity.py',root/'sdk_sensitivity.mjs',root/'sdk_sensitivity_policy.mjs',
             root/'sdk_experiment.mjs',root/'study.py',root/'recovery.py',
             root.parent/'physics_value/research_sandbox.py',root.parents[1]/'src/prime_runtime/provider_config.mjs']
    current={path.name:path for path in sources}
    for name,expected_hash in baseline['runner_sha256'].items():
        if name != 'run_agents.py' and runner.digest(current[name]) != expected_hash:
            raise ValueError('Original model/SDK/physics implementation changed: '+name)
    if hashlib.sha256(runner.SYSTEM.encode()).hexdigest()!=baseline['system_prompt_sha256']:
        raise ValueError('Primary prompt changed')
    if runner.digest(dataset/'protocol.json')!=baseline['dataset_protocol_sha256']:
        raise ValueError('Dataset differs from primary')
    protocol=deepcopy(baseline)
    protocol.update(version=VERSION, case_ids=cases, planned_attempts=36,
        model_calls=8, wall_seconds=240, tool_calls=8, max_output_tokens=4096,
        system_prompt=SYSTEM, system_prompt_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest(),
        sdk_script=str(root/'sdk_sensitivity.mjs'),
        runner_sha256={path.name:runner.digest(path) for path in sources},
        public_packet_sha256={f'{case}/{task}':runner.digest(dataset/'public'/case/(task+'.json')) for case in cases for task in baseline['tasks']},
        original_protocol_sha256=runner.digest(original/'protocol.json'),
        prior_campaigns=[str(path) for path in prior_campaigns], dataset_verification=verification,
        selection_by_family=selected,
        scope='Post-hoc motivated, prospectively frozen same-case subset; joint budget and submission-policy change; not independent confirmation',
        completion_policy='Final eighth provider turn exposes only submit_decision with forced function choice, identically across all three arms; earlier submission allowed; eight host calls include submission',
        selection_rule='Lexicographically smallest opaque case_id in each authored family; no outcomes used for selection',
        motivation='Post-hoc observation that primary A sessions spend their four model turns building numerical analyses; primary failures retained',
        bundled_interventions=['model turns 4 to 8','wall limit 120s to 240s','final provider turn has only submit_decision and forced function choice'],
        interpretation='Prospectively frozen execution of a post-hoc motivated sensitivity; not an untouched holdout or pure compute-budget causal estimate',
        final_turn_policy='Shared by A/B/C: eighth provider request exposes and requires only submit_decision; all earlier tool availability unchanged')
    for key,value in protocol['public_packet_sha256'].items():
        if baseline['public_packet_sha256'].get(key)!=value:raise ValueError('Public input changed')
    protocol_path=output/'protocol.json'
    if output.exists():
        if not protocol_path.exists() or runner.strict_json(protocol_path.read_text())!=protocol:
            raise ValueError('Sensitivity output frozen; protocol/source differs')
    else:
        output.mkdir(parents=True)
        runner.dump(protocol_path,protocol)
        for source in sources:
            destination=output/'runner-source'/source.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source,destination)
    if not execute and not preflight:
        return {'status':'prepared_no_inference','cases':selected,'planned_attempts':36,'model_calls':8,'wall_seconds':240,'final_turn':'submit_only'}
    if preflight:
        runner.isolation_probe(output)
        rows=[runner.run_one(dataset,output,cases[0],'forecast',arm,protocol,preflight=True) for arm in ('A','B','C')]
        result={'status':'preflight_passed' if all(row['status']=='preflight_passed' for row in rows) else 'preflight_failed','records':rows}
        runner.dump(output/'preflight.json',result)
        return result
    if not prior_campaigns or campaign is None:raise ValueError('Execution requires prior campaign ledgers and separate proxy policy')
    balance=[campaign_balance(path) for path in prior_campaigns]
    held=sum(row['original_held_usd'] for row in balance)
    policy=runner.strict_json((Path(campaign)/'modal-budget-policy.json').read_text())
    endpoint=urlparse(os.environ.get('BIODEMO_MODAL_BASE_URL',''))
    cap=policy['maximum_campaign_reservation_usd']
    if endpoint.scheme!='http' or endpoint.hostname!='127.0.0.1':raise ValueError('Bounded loopback proxy required')
    if type(cap) not in (int,float) or not 0 < cap <= 10.-held+1e-9:
        raise ValueError('Sensitivity proxy exceeds combined original+continuation+sensitivity $10 cap')
    admission={'prior_campaigns':dict(zip(map(str,prior_campaigns),balance)), 'prior_held_usd':held,
        'sensitivity_cap_usd':cap,'combined_maximum_usd':held+cap,
        'proxy_policy_sha256':runner.digest(Path(campaign)/'modal-budget-policy.json')}
    admission_path=output/'admission-check.json'
    if admission_path.exists() and runner.strict_json(admission_path.read_text())!=admission:
        raise ValueError('Frozen sensitivity admission evidence changed')
    if not admission_path.exists():runner.dump(admission_path,admission)
    runner.isolation_probe(output)
    records,lock=[],threading.Lock()
    def pair(index,case,task):
        for arm in runner.arm_order(index):
            if (output/'STOP').exists():return
            row=runner.run_one(dataset,output,case,task,arm,protocol)
            with lock:
                records.append(row)
                runner.dump(output/'progress.json',runner.aggregate(records,protocol))
                print(json.dumps({'case_id':case,'task':task,'arm':arm,'status':row['status']}),flush=True)
    with ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        futures=[pool.submit(pair,index,case,task) for index,case in enumerate(cases) for task in protocol['tasks']]
        for future in as_completed(futures):future.result()
    records.sort(key=lambda row:(row['case_id'],row['task'],row['arm']))
    result=runner.aggregate(records,protocol,'interrupted' if (output/'STOP').exists() else 'complete')
    result['sensitivity_caveat']=protocol['interpretation']
    final=output/'results.json'
    if final.exists() and runner.strict_json(final.read_text())!=result:raise ValueError('Final sensitivity cohort already frozen')
    if not final.exists():runner.dump(final,result)
    return {k:result[k] for k in ('status','attempted','completed','complete_triples','matched_inputs')}


if __name__=='__main__':
    runner.load_env_file(Path(__file__).resolve().parents[2]/'.env.local')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','original','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--prior-campaigns',type=Path,nargs='+',required=True)
    parser.add_argument('--campaign',type=Path)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--execute',action='store_true')
    mode.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    print(json.dumps(sensitivity(args.dataset,args.original,args.output,args.prior_campaigns,
        execute=args.execute,campaign=args.campaign,preflight=args.preflight),indent=2))
