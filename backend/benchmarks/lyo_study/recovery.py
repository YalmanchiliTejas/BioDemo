"""Infrastructure-only journal recovery and continuation of never-attempted slots.

Original artifacts remain immutable. No hidden scoring is imported. Inference is
opt-in and requires a separate bounded proxy whose cap fits the original balance.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
from urllib.parse import urlparse

from . import run_agents as runner

VERSION = 'lyo-cleanup-recovery-v2'


def journal(path):
    if not path.exists():
        return [], []
    records, errors = [], []
    for index, line in enumerate(path.read_text().splitlines()):
        try:
            value = runner.strict_json(line)
            if not isinstance(value, dict):
                raise ValueError('not an object')
            records.append(value)
        except ValueError:
            errors.append({'file': path.name, 'line': index+1})
    return records, errors


def audit_original(original):
    original = Path(original).resolve()
    protocol = runner.strict_json((original / 'protocol.json').read_text())
    records, untouched, hashes = [], [], {}
    for case_id in protocol['case_ids']:
        for task in protocol['tasks']:
            for arm in protocol['arms']:
                slot = {'case_id': case_id, 'task': task, 'arm': arm}
                work = original / 'attempts' / case_id / task / arm
                if not work.exists():
                    untouched.append(slot)
                    continue
                for path in sorted(work.rglob('*')):
                    if path.is_file():
                        hashes[str(path.relative_to(original))] = runner.digest(path)
                if (work / 'run.json').exists():
                    row = runner.strict_json((work / 'run.json').read_text())
                    if any(row.get(key) != value for key,value in slot.items()):
                        raise ValueError('receipt identity mismatch')
                    row = deepcopy(row)
                    row['recovery_provenance'] = {'kind':'original_receipt', 'path':str(work / 'run.json')}
                    records.append(row)
                    continue
                events, event_errors = journal(work / 'events.jsonl')
                tools, tool_errors = journal(work / 'tools.jsonl')
                accepted = [t for t in tools if t.get('name') == 'submit_decision' and t.get('result', {}).get('accepted') is True]
                finished = [e for e in events if e.get('type') == 'finished']
                valid = not (event_errors or tool_errors) and len(accepted) == len(finished) == 1
                valid = valid and finished[0].get('status') == 'completed' and accepted[0].get('arguments') == finished[0].get('decision')
                packet_path = work / 'agent-input/packet.json'
                if valid:
                    try:
                        runner.validate_submission(accepted[0]['arguments'], runner.strict_json(packet_path.read_text()))
                    except (ValueError, OSError, KeyError, TypeError):
                        valid = False
                latest = finished[-1] if finished else {}
                row = dict(slot, version=protocol.get('version'), model=protocol.get('model'),
                    status='completed' if valid else 'infrastructure_error',
                    submission=deepcopy(accepted[0]['arguments']) if valid else None,
                    usage=latest.get('usage', [e.get('usage') for e in events if e.get('type') == 'model_usage']),
                    model_calls=latest.get('model_calls',sum(e.get('type') == 'model_start' for e in events)),
                    tool_calls=len(tools), physical_model_calls=sum(t.get('name') == 'physical_forward_model' for t in tools),
                    common_input_sha256=runner.digest(packet_path) if packet_path.exists() else None,
                    common_prompt_sha256=runner.digest(packet_path) if packet_path.exists() else None,
                    system_prompt_sha256=protocol.get('system_prompt_sha256'),
                    capability_audit=next((e for e in events if e.get('type') == 'capability_audit'),None),
                    wall_seconds=None, provider_cost_usd=None, real_equipment_actions=False,
                    error=None if valid else 'Incomplete or inconsistent original journal; attempt retained and never retried',
                    infrastructure_failure='Original final receipt absent after cleanup; original journals retained without modification',
                    recovery_provenance={'kind':'matched_journal_reconstruction' if valid else 'unrecoverable_attempt',
                        'directory':str(work), 'malformed_lines':event_errors+tool_errors,
                        'finished_event_present':bool(finished), 'accepted_submission_count':len(accepted),
                        'wall_time_status':'not reconstructed from filesystem timestamps'})
                records.append(row)
    return {'records':records, 'untouched':untouched, 'original_artifact_sha256':hashes,
            'original_protocol_sha256':runner.digest(original / 'protocol.json')}


def campaign_balance(campaign):
    """Retain unsettled reservations; never infer zero cost from absent usage."""
    campaign = Path(campaign)
    entries, errors = journal(campaign / 'modal-admission.jsonl')
    if errors or not entries:
        raise ValueError('Original campaign admission ledger missing or malformed')
    reservations, settlements, finished = {}, {}, set()
    for row in entries:
        ordinal = row.get('ordinal')
        if row['event'] == 'reserved':
            if ordinal in reservations:
                raise ValueError('duplicate reservation')
            reservations[ordinal] = row['reserved_usd']
        elif row['event'] == 'settled':
            if ordinal in settlements:
                raise ValueError('duplicate settlement')
            settlements[ordinal] = row['conservative_cost_usd']
        elif row['event'] == 'finished':
            finished.add(ordinal)
    if set(reservations) != finished or not set(settlements) <= set(reservations):
        raise ValueError('Original proxy requests are not all finished; wait before recovery')
    held = sum(settlements.get(key,value) for key,value in reservations.items())
    return {'original_held_usd':held, 'remaining_cap_usd':max(0.,10.-held),
            'ledger_sha256':runner.digest(campaign / 'modal-admission.jsonl'),
            'basis':'Provider settlements where available; full original reservation retained otherwise; combined cap $10'}


def recover(dataset, original, output, original_campaign, *, execute=False, continuation_campaign=None):
    from .study import verify_dataset
    dataset, original, output = map(lambda p:Path(p).resolve(), (dataset,original,output))
    verification = verify_dataset(dataset)
    protocol = runner.strict_json((original / 'protocol.json').read_text())
    audit = audit_original(original)
    balance = campaign_balance(original_campaign)
    current = Path(runner.__file__).resolve()
    sources = {p.name:p for p in (current,current.with_name('sdk_experiment.mjs'),current.with_name('study.py'),
        current.parents[1] / 'physics_value/research_sandbox.py',current.parents[2] / 'src/prime_runtime/provider_config.mjs')}
    for name, expected in protocol['runner_sha256'].items():
        if name != 'run_agents.py' and runner.digest(sources[name]) != expected:
            raise ValueError('Inference semantics changed: '+name)
    if hashlib.sha256(runner.SYSTEM.encode()).hexdigest() != protocol['system_prompt_sha256']:
        raise ValueError('Common system prompt changed')
    if runner.digest(dataset / 'protocol.json') != protocol['dataset_protocol_sha256']:
        raise ValueError('Dataset protocol changed')
    for key,expected in protocol['public_packet_sha256'].items():
        case,task=key.split('/')
        if runner.digest(dataset / 'public' / case / (task+'.json')) != expected:
            raise ValueError('Public packet changed')
    plan = {'version':VERSION, 'kind':'infrastructure_only_continuation',
        'original':str(original), 'original_campaign':str(Path(original_campaign).resolve()),
        'original_protocol_sha256':audit['original_protocol_sha256'],
        'original_artifact_sha256':audit['original_artifact_sha256'],
        'original_runner_sha256':protocol['runner_sha256'],
        'corrected_runner_sha256':{name:runner.digest(path) for name,path in sources.items()},
        'recovery_source_sha256':runner.digest(Path(__file__).resolve()),
        'dataset_verification':verification, 'balance':balance, 'untouched':audit['untouched'],
        'inference_protocol':protocol,
        'change':'macOS exited process group reaping and receipt-safe cleanup; shared runner adds optional sensitivity SDK/prompt overrides unused in this continuation; original prompt/SDK/model/physics/budgets preserved',
        'selection':'Only slots whose original attempt directory never existed; existing failures never replaced'}
    plan_path = output / 'recovery-protocol.json'
    if output.exists():
        if not plan_path.exists() or runner.strict_json(plan_path.read_text()) != plan:
            raise ValueError('Recovery output is frozen and differs; use fresh output')
    else:
        output.mkdir(parents=True)
        runner.dump(plan_path, plan)
        for source in list(sources.values())+[Path(__file__).resolve()]:
            destination=output / 'runner-source' / source.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source,destination)
        original_source=original / 'runner-source/run_agents.py'
        if original_source.exists():
            delta=''.join(difflib.unified_diff(original_source.read_text().splitlines(True),current.read_text().splitlines(True),fromfile='original/run_agents.py',tofile='corrected/run_agents.py'))
            (output / 'infrastructure-correction.diff').write_text(delta)
        for row in audit['records']:
            runner.dump(output / 'original-records' / row['case_id'] / row['task'] / row['arm'] / 'run.json', row)
    if not execute:
        return {'status':'prepared_no_inference', 'existing_records':len(audit['records']), 'untouched':audit['untouched'], 'balance':balance}
    if continuation_campaign is None:
        raise ValueError('Execution requires the separate continuation budget proxy policy')
    policy=runner.strict_json((Path(continuation_campaign) / 'modal-budget-policy.json').read_text())
    endpoint=urlparse(os.environ.get('BIODEMO_MODAL_BASE_URL',''))
    if endpoint.hostname != '127.0.0.1' or endpoint.scheme != 'http':
        raise ValueError('Continuation must run through the local bounded budget proxy')
    cap=policy['maximum_campaign_reservation_usd']
    if type(cap) not in (int,float) or not 0 < cap <= balance['remaining_cap_usd']+1e-9:
        raise ValueError('Continuation cap exceeds remaining combined $10 budget')
    runner.isolation_probe(output)
    records=deepcopy(audit['records'])
    lock=threading.Lock()
    grouped={}
    for slot in audit['untouched']:
        grouped.setdefault((slot['case_id'],slot['task']),set()).add(slot['arm'])
    def pair(case,task,arms):
        index=protocol['case_ids'].index(case)
        for arm in runner.arm_order(index):
            if arm not in arms or (output / 'STOP').exists():
                continue
            if (original / 'attempts' / case / task / arm).exists():
                raise ValueError('Original changed; refusing newly attempted slot')
            row=runner.run_one(dataset,output,case,task,arm,protocol)
            row['recovery_provenance']={'kind':'previously_untouched_slot','original_protocol_sha256':audit['original_protocol_sha256']}
            with lock:
                records.append(row)
                runner.dump(output / 'progress.json',runner.aggregate(records,protocol))
                print(json.dumps({'case_id':case,'task':task,'arm':arm,'status':row['status']}),flush=True)
    with ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        futures=[pool.submit(pair,case,task,arms) for (case,task),arms in grouped.items()]
        for future in as_completed(futures):future.result()
    records.sort(key=lambda row:(row['case_id'],row['task'],row['arm']))
    final=runner.aggregate(records,protocol,'interrupted' if (output / 'STOP').exists() else 'complete')
    final['recovery_protocol_sha256']=runner.digest(plan_path)
    final['infrastructure_correction']=VERSION
    final_path=output / 'results.json'
    if final_path.exists() and runner.strict_json(final_path.read_text()) != final:
        raise ValueError('Final cohort already frozen')
    if not final_path.exists():runner.dump(final_path,final)
    return {k:final[k] for k in ('status','attempted','completed','complete_triples','matched_inputs')}


if __name__=='__main__':
    runner.load_env_file(Path(__file__).resolve().parents[2] / '.env.local')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','original','output','original-campaign'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--continuation-campaign',type=Path)
    args=parser.parse_args()
    print(json.dumps(recover(args.dataset,args.original,args.output,args.original_campaign,
        execute=args.execute,continuation_campaign=args.continuation_campaign),indent=2))
