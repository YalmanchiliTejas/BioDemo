"""Matched restricted Prime SDK experiment; hidden-outcome scoring is separate."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
from itertools import permutations
import json
import math
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import threading
import time

from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile
from src.paths import DEFAULT_PRIME_BUNDLE
from benchmarks.physics_value.research_sandbox import analyze

VERSION = 'lyo-matched-prime-1'
SYSTEM = '''You are a manufacturing process research agent in a synthetic freeze-drying study.
Use only the public packet and tools available in this fresh session. Observations
are evidence; simulations are predictions with limitations. When completion_time_h
is null or applicability is invalid, diagnostic_completion_time_h is NOT a usable
completion forecast; never substitute that diagnostic for the censored forecast. Unknown receiving
characterization and model mismatch may matter. No real equipment action is authorized.
For BOTH forecast and pretransfer tasks, completion_time_h, thermal_warning and
capacity_warning MUST describe the KEEP schedule, independently of your action_id.
The completion time is absolute elapsed hours from batch start, not remaining hours.
Warnings concern a thermal limit excursion and equipment vapor capacity exceedance
respectively. Use null when unable to assess. Separately select a justified allowed
action to reduce completion time subject to thermal and capacity constraints, or
characterize when the evidence does not justify committing a schedule. Describe
uncertainty and concrete evidence references. Never treat plans as observations.
You have at most 8 host tool calls INCLUDING submission and 4 model calls. Reserve
one tool call for submit_decision, then stop. No tool retrieves hidden answers.'''
ACTIONS = {'keep', 'cool', 'moderate', 'warm', 'characterize'}
FIELDS = {'completion_time_h', 'thermal_warning', 'capacity_warning', 'action_id',
          'rationale', 'uncertainty', 'evidence'}


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('nonfinite JSON number')
        return parsed
    def reject(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject, parse_float=number)


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arm_order(index):
    return tuple(permutations(('A', 'B', 'C')))[index % 6]


def validate_submission(value, packet):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('submission requires exactly the declared fields')
    duration = value['completion_time_h']
    if duration is not None and (type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0):
        raise ValueError('completion_time_h must be finite nonnegative number or null')
    for field in ('thermal_warning', 'capacity_warning'):
        if value[field] is not None and type(value[field]) is not bool:
            raise ValueError(field + ' must be boolean or null')
    allowed = ACTIONS & {a['id'] for a in packet['allowed_actions']}
    if not isinstance(value['action_id'], str) or value['action_id'] not in allowed:
        raise ValueError('invalid action_id')
    if any(not isinstance(value[field], str) for field in ('rationale', 'uncertainty')):
        raise ValueError('rationale and uncertainty must be strings')
    if not isinstance(value['evidence'], list) or any(not isinstance(v, str) for v in value['evidence']):
        raise ValueError('evidence must be an array of strings')


class HostTools:
    def __init__(self, packet, arm, scratch, budget=8):
        if arm not in ('A', 'B', 'C'):
            raise ValueError('invalid arm')
        self.packet, self.arm, self.scratch = deepcopy(packet), arm, Path(scratch)
        self.budget, self.history, self.submission = min(budget, 8), [], None

    def call(self, name, args):
        started = time.perf_counter()
        try:
            if self.submission is not None:
                raise ValueError('decision already frozen')
            if len(self.history) >= self.budget:
                raise ValueError('tool budget exhausted')
            if not isinstance(args, dict):
                raise ValueError('tool arguments must be an object')
            if name == 'submit_decision':
                validate_submission(args, self.packet)
                self.submission = deepcopy(args)
                result = {'accepted': True, 'decision_frozen': True}
            elif name == 'python_analysis':
                if set(args) != {'code'}:
                    raise ValueError('only code is accepted')
                result = analyze(args['code'], self.packet, self.scratch)
            elif name == 'physical_forward_model' and self.arm in ('B', 'C'):
                if set(args) != {'action_id'} or not isinstance(args['action_id'], str):
                    raise ValueError('only a required action_id is accepted; no parameter overrides')
                if args['action_id'] not in {a['id'] for a in self.packet['allowed_actions']}:
                    raise ValueError('unknown action_id')
                from .study import predict
                result = predict(deepcopy(self.packet), self.arm, args['action_id'])
                # Never leak a nonfinite JSON value through the host boundary.
                json.dumps(result, allow_nan=False)
            else:
                raise ValueError('tool unavailable in this arm')
        except Exception as exc:
            result = {'error': type(exc).__name__ + ': ' + str(exc)[:1200]}
        self.history.append({'name': name, 'arguments': deepcopy(args), 'result': deepcopy(result),
                             'wall_seconds': time.perf_counter() - started})
        return result


def isolation_probe(output):
    scratch = output / 'isolation-probe' / 'scratch'
    hidden = output / 'isolation-probe' / 'hidden-canary.json'
    hidden.parent.mkdir(parents=True, exist_ok=True)
    hidden.write_text('{"private_probe":true}')
    codes = {'arithmetic': 'print(int(np.sum([data["probe"],5])))',
             'hidden_file': f'open({str(hidden.resolve())!r}).read()',
             'network': 'import socket; socket.socket().connect(("127.0.0.1",9))',
             'credentials': 'import os; print(any("TOKEN" in k or "KEY" in k for k in os.environ))'}
    probes = {name: analyze(code, {'probe': 7}, scratch) for name, code in codes.items()}
    passed = (probes['arithmetic'].get('stdout', '').strip() == '12'
              and 'PermissionError' in probes['hidden_file'].get('error', '')
              and 'PermissionError' in probes['network'].get('error', '')
              and probes['credentials'].get('stdout', '').strip() == 'False')
    result = {'passed': passed, 'mechanism': 'macOS sandbox-exec', 'probes': probes}
    dump(output / 'isolation.json', result)
    if not passed:
        raise RuntimeError('OS sandbox probes failed; inference prohibited')
    return result



def cleanup_process(process, threads):
    """Reap exited macOS groups and preserve receipts even if teardown fails."""
    errors = []
    def record(exc):
        errors.append(type(exc).__name__ + ': ' + str(exc)[:600])
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            # Darwin may return EPERM for an unreaped, exited process group.
            # Reap first, but still signal groups with surviving descendants.
            process.poll()
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                # Exit can race the first poll. Do not hide denial for live processes.
                if process.poll() is None:
                    raise
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if sig == signal.SIGKILL:
                    raise
        except Exception as exc:
            record(exc)
    for thread in threads:
        try:
            thread.join(timeout=1)
        except Exception as exc:
            record(exc)
    for index, stream in enumerate((process.stdin, process.stdout, process.stderr)):
        if index and len(threads) >= index and threads[index-1].is_alive():
            errors.append('Reader still alive; stream close skipped to preserve receipt')
            continue
        try:
            stream.close()
        except Exception as exc:
            record(exc)
    return errors

def run_one(dataset, output, case_id, task, arm, protocol, *, preflight=False):
    dataset, output = Path(dataset), Path(output)
    work = output / ('preflight-attempts' if preflight else 'attempts') / case_id / task / arm
    receipt = work / 'run.json'
    if receipt.exists():
        return strict_json(receipt.read_text())
    if work.exists():
        recovered, malformed = {}, []
        for name in ('events.jsonl', 'tools.jsonl'):
            recovered[name] = []
            saved = work / name
            if saved.exists():
                for index, line in enumerate(saved.read_text().splitlines()):
                    try:
                        value = strict_json(line)
                        if not isinstance(value, dict):
                            raise ValueError('record must be object')
                        recovered[name].append(value)
                    except ValueError:
                        malformed.append({'file': name, 'line': index + 1})
        events, history = recovered['events.jsonl'], recovered['tools.jsonl']
        accepted = [entry['arguments'] for entry in history if entry.get('name') == 'submit_decision' and entry.get('result', {}).get('accepted')]
        staged = work / 'agent-input/packet.json'
        result = {'version': VERSION, 'case_id': case_id, 'task': task, 'arm': arm,
                  'status': 'interrupted', 'error': 'Unfinished prior attempt retained; never retried',
                  'submission': accepted[0] if accepted else None,
                  'usage': [entry.get('usage') for entry in events if entry.get('type') == 'model_usage'],
                  'model_calls': sum(entry.get('type') == 'model_start' for entry in events),
                  'tool_calls': len(history),
                  'physical_model_calls': sum(entry.get('name') == 'physical_forward_model' for entry in history),
                  'common_input_sha256': digest(staged) if staged.exists() else None,
                  'capability_audit': next((entry for entry in events if entry.get('type') == 'capability_audit'), None),
                  'malformed_journal_lines': malformed, 'wall_seconds': None}
        dump(receipt, result)
        return result
    work.mkdir(parents=True)
    started = time.perf_counter()
    log, host, finished, capability, process = [], None, None, None, None
    errors, threads, input_hash = [], [], None
    status, error = 'failed', None
    system_prompt = protocol.get('system_prompt', SYSTEM)
    sdk_script = Path(protocol.get('sdk_script', Path(__file__).resolve().with_name('sdk_experiment.mjs'))).resolve()
    def append(name, value):
        with (work / name).open('a') as handle:
            handle.write(json.dumps(value, allow_nan=False) + '\n')
            handle.flush()
    try:
        public_path = dataset / 'public' / case_id / (task + '.json')
        raw = public_path.read_bytes()
        packet = strict_json(raw)
        input_hash = hashlib.sha256(raw).hexdigest()
        inputs = work / 'agent-input'
        inputs.mkdir()
        (inputs / 'packet.json').write_bytes(raw)
        host = HostTools(packet, arm, work / 'numerical-scratch', protocol['tool_calls'])
        request = {'type': 'initialize', 'bundle_root': str(DEFAULT_PRIME_BUNDLE),
                   'cwd': str(inputs.resolve()), 'model': protocol['model'], 'task': task, 'arm': arm,
                   'system_prompt': system_prompt, 'prompt': raw.decode('utf-8'),
                   'timeout_seconds': protocol['wall_seconds'], 'max_model_calls': protocol['model_calls'],
                   'public_schema': {'actions': [a['id'] for a in packet['allowed_actions']]},
                   'max_output_tokens': protocol['max_output_tokens'], 'preflight': preflight}
        process = subprocess.Popen([shutil.which('node') or 'node', str(sdk_script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=inputs, env=os.environ.copy(), start_new_session=True, bufsize=1)
        events = queue.Queue()
        def stdout_reader():
            for line in process.stdout:
                events.put(line)
            events.put(None)
        def stderr_reader():
            for line in process.stderr:
                errors.append(line)
                with (work / 'stderr.log').open('a') as handle:
                    handle.write(line)
        threads = [threading.Thread(target=stdout_reader, daemon=True), threading.Thread(target=stderr_reader, daemon=True)]
        for thread in threads:
            thread.start()
        process.stdin.write(json.dumps(request, allow_nan=False) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + protocol['wall_seconds']
        while time.monotonic() < deadline:
            if (output / 'STOP').exists():
                status = 'interrupted'
                break
            try:
                line = events.get(timeout=min(0.25, max(0.001, deadline-time.monotonic())))
            except queue.Empty:
                continue
            if line is None:
                break
            event = strict_json(line)
            if not isinstance(event, dict):
                raise ValueError('SDK event must be a JSON object')
            log.append(event)
            append('events.jsonl', event)
            if event.get('type') == 'capability_audit':
                capability = event
            elif event.get('type') == 'tool_request':
                value = host.call(event['name'], event.get('args', {}))
                append('tools.jsonl', host.history[-1])
                process.stdin.write(json.dumps({'type': 'tool_result', 'id': event['id'], 'result': value}, allow_nan=False) + '\n')
                process.stdin.flush()
            elif event.get('type') == 'finished':
                finished = event
                status = event.get('status', 'failed')
                break
        else:
            status = 'timeout'
        if host.submission is not None:
            status = 'completed'
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)[:1200]
    finally:
        cleanup_errors = cleanup_process(process, threads) if process is not None else []
    history = host.history if host else []
    result = {'version': VERSION, 'case_id': case_id, 'task': task, 'arm': arm,
              'model': protocol.get('model'), 'status': status, 'preflight_only': preflight,
              'wall_seconds': time.perf_counter()-started, 'common_input_sha256': input_hash,
              'common_prompt_sha256': input_hash, 'system_prompt_sha256': hashlib.sha256(system_prompt.encode()).hexdigest(),
              'capability_audit': capability,
              'model_calls': (finished or {}).get('model_calls', sum(e.get('type') == 'model_start' for e in log)),
              'usage': (finished or {}).get('usage', [e.get('usage') for e in log if e.get('type') == 'model_usage']),
              'tool_calls': len(history), 'physical_model_calls': sum(e['name'] == 'physical_forward_model' for e in history),
              'submission': host.submission if host else None,
              'error': error or (finished or {}).get('error') or (''.join(errors)[-1800:] if status not in ('completed', 'preflight_passed') else None),
              'cleanup_errors': cleanup_errors,
              'infrastructure_revision': 'macos-exited-group-reap-and-receipt-safe-cleanup-v2',
              'provider_cost_usd': None, 'cost_status': 'budget_proxy_receipt_required', 'real_equipment_actions': False}
    dump(work / 'events.json', log)
    dump(work / 'tools.json', history)
    dump(receipt, result)
    return result


def aggregate(records, protocol, status='running'):
    grouped = {}
    for record in records:
        grouped.setdefault((record['case_id'], record['task']), {})[record['arm']] = record
    triples = [value for value in grouped.values() if len(value) == 3]
    schemas = [[(row.get('capability_audit') or {}).get('shared_tool_schema_sha256') for row in triple.values()] for triple in triples]
    return {'version': VERSION, 'status': status, 'protocol': protocol, 'records': records,
            'planned_attempts': protocol['planned_attempts'], 'attempted': len(records),
            'completed': sum(row['status'] == 'completed' for row in records),
            'complete_triples': sum(all(row['status'] == 'completed' for row in triple.values()) for triple in triples),
            'matched_inputs': all(len({row.get('common_input_sha256') for row in triple.values()}) == 1 and all(row.get('common_input_sha256') for row in triple.values()) for triple in triples),
            'shared_tool_schemas_match': all(all(items) and len(set(items)) == 1 for items in schemas) if schemas else None,
            'scope': 'Synthetic restricted-tool experiment; outcomes scored separately; no real engineer effort measured.'}


def execute(dataset, output, *, workers=2, limit_cases=None, preflight_only=False, resume=False):
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    if output.exists() and not resume:
        raise FileExistsError('Frozen output exists; choose a fresh path or explicit --resume')
    if workers not in (1, 2, 3, 4) or (limit_cases is not None and limit_cases < 1):
        raise ValueError('invalid workers or case limit')
    from .study import verify_dataset
    verification = verify_dataset(dataset)
    source_protocol = strict_json((dataset / 'protocol.json').read_text())
    cases = sorted(path.name for path in (dataset / 'public').iterdir() if path.is_dir())
    if limit_cases is not None:
        cases = cases[:limit_cases]
    if not cases:
        raise ValueError('no public cases')
    for case in cases:
        for task in ('forecast', 'pretransfer'):
            packet = strict_json((dataset / 'public' / case / (task + '.json')).read_text())
            if packet['case_id'] != case or packet['task'] != task:
                raise ValueError('public packet identity mismatch')
    profile = hosted_research_profile()
    if profile is None:
        raise RuntimeError('No saved hosted research model configured')
    runner_path = Path(__file__).resolve()
    sources = [runner_path, runner_path.with_name('sdk_experiment.mjs'),
               runner_path.parents[1] / 'physics_value/research_sandbox.py',
               runner_path.parents[2] / 'src/prime_runtime/provider_config.mjs']
    study = runner_path.with_name('study.py')
    if study.exists():
        sources.append(study)
    protocol = {'version': VERSION, 'model': f'{profile.provider}/{profile.model}',
                'case_ids': cases, 'tasks': ['forecast', 'pretransfer'], 'arms': ['A', 'B', 'C'],
                'planned_attempts': len(cases)*6, 'wall_seconds': 120, 'tool_calls': 8,
                'model_calls': 4, 'max_output_tokens': 4096, 'reasoning_effort': 'low', 'workers': workers,
                'dataset_verification': verification,
                'dataset_protocol_sha256': digest(dataset / 'protocol.json'),
                'dataset_protocol': source_protocol,
                'public_packet_sha256': {f'{case}/{task}': digest(dataset / 'public' / case / (task + '.json')) for case in cases for task in ('forecast', 'pretransfer')},
                'runner_sha256': {path.name: digest(path) for path in sources},
                'system_prompt_sha256': hashlib.sha256(SYSTEM.encode()).hexdigest(),
                'arm_difference': 'A no physical model; B legacy model; C improved model. Shared numerical tool and submission schema.',
                'order': 'Six arm permutations cycle across sorted cases, same order for both tasks; sequential arms within each case/task.',
                'preflight_only': preflight_only}
    path = output / 'protocol.json'
    if resume and (not path.exists() or strict_json(path.read_text()) != protocol):
        raise ValueError('Resume requires the identical frozen protocol, source hashes, and public inputs')
    output.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        dump(path, protocol)
        dump(output / 'dataset-verification.json', verification)
        for source in sources:
            destination = output / 'runner-source' / source.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)
    isolation_probe(output)
    if preflight_only:
        rows = [run_one(dataset, output, cases[0], 'forecast', arm, protocol, preflight=True) for arm in ('A', 'B', 'C')]
        result = {'status': 'preflight_passed' if all(row['status'] == 'preflight_passed' for row in rows) else 'preflight_failed', 'records': rows}
        dump(output / 'preflight.json', result)
        return result
    records, lock = [], threading.Lock()
    def triple(index, case, task):
        for arm in arm_order(index):
            if (output / 'STOP').exists():
                return
            row = run_one(dataset, output, case, task, arm, protocol)
            with lock:
                records.append(row)
                dump(output / 'results.json', aggregate(records, protocol))
                print(json.dumps({'case_id': case, 'task': task, 'arm': arm, 'status': row['status'], 'attempted': len(records), 'planned': protocol['planned_attempts']}), flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(triple, index, case, task) for index, case in enumerate(cases) for task in protocol['tasks']]
        for future in as_completed(futures):
            future.result()
    result = aggregate(records, protocol, 'interrupted' if (output / 'STOP').exists() else 'complete')
    dump(output / 'results.json', result)
    return {key: result[key] for key in ('status', 'attempted', 'completed', 'complete_triples', 'matched_inputs', 'shared_tool_schemas_match')}


if __name__ == '__main__':
    load_env_file(Path(__file__).resolve().parents[2] / '.env.local')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2, choices=range(1, 5))
    parser.add_argument('--limit-cases', type=int)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    print(json.dumps(execute(args.dataset, args.output, workers=args.workers, limit_cases=args.limit_cases,
                             preflight_only=args.preflight, resume=args.resume), indent=2))
