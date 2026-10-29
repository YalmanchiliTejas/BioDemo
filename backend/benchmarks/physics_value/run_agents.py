"""Execute matched, restricted Prime-SDK research agents against the frozen pilot.

This is a bounded tool-access experiment, not a test of the full autonomous
manufacturing workflow. The SDK/provider are reused; only explicit host tools
are visible. General numerical code is available equally in both arms and runs
under separately probed OS filesystem/network denial.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time

from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile
from src.paths import DEFAULT_PRIME_BUNDLE

from .evaluate import SimulationSession, load_packet, score_submission, stage, verify_implementation
from .generate import digest, dump
from .public_models import predict
from .research_sandbox import analyze, probe

VERSION = 'restricted-prime-physics-comparison-3-public-id-enums'
SYSTEM = '''You are a manufacturing process research agent in a synthetic experiment.
Investigate only the public packet supplied in this session. The evidence includes
historical source observations, receiving specifications and, except pretransfer,
receiving measurements available at the stated decision time. Future commands are
plans, not measurements. A simulated mechanism may be unidentifiable. Rank a
small justified hypothesis set, distinguish observation from assumption and do
not assert verified causality from ambiguous traces. Sensor bias, multiple causes
and model mismatch are possible. Minimize the declared objective subject to the
declared constraints, using only allowed actions. A past excursion cannot be
erased by changing future settings. Before transfer you may request characterization
or abstain instead of guessing a receiving action. Tool outputs are predictions
or observations with their own limits. Use numerical analysis when helpful.
For resolution you may request measurements; time and work advance by their
declared synthetic costs. Submit an intervention only when you have enough
evidence, or submit keep with explicit unresolved uncertainty if no action can
be justified. This research never authorizes real equipment changes.
Conclude by calling submit_decision with hypotheses, applicable action_id or
pretransfer decision, rationale, uncertainty and concrete evidence references.
Do not enumerate every hypothesis as a substitute for investigation. Stop after
submission. No tools can retrieve external answers or other task histories.'''


def _compact_prediction(value: dict) -> dict:
    value = deepcopy(value)
    rows = value['result'].get('trajectory')
    if rows:
        stride = max(1, len(rows)//32)
        value['result']['trajectory'] = rows[::stride]
        if value['result']['trajectory'][-1] != rows[-1]:
            value['result']['trajectory'].append(rows[-1])
        value['result']['trajectory_sampling_notice'] = 'Display downsample only; summary constraints and endpoint use full calculation.'
    return value


class HostTools:
    def __init__(self, dataset: Path, case_id: str, task: str, arm: str, scratch: Path, budget: int):
        self.dataset, self.case_id, self.task, self.arm = dataset, case_id, task, arm
        self.packet = load_packet(dataset, case_id, task)
        self.session = SimulationSession(dataset, case_id) if task == 'resolution' else None
        self.scratch, self.budget = scratch, budget
        self.history = []
        self.submission = None
        self.score = None

    def call(self, name: str, args: dict) -> dict:
        if self.submission is not None:
            return {'error': 'decision already frozen'}
        if len(self.history) >= self.budget and name != 'submit_decision':
            return {'error': 'tool budget exhausted; submit a decision with explicit limitations'}
        started = time.perf_counter()
        try:
            if name == 'python_analysis':
                value = analyze(args['code'], self.packet, self.scratch)
            elif name == 'physical_forward_model' and self.arm == 'B':
                value = _compact_prediction(predict(self.packet, args.get('action_id', 'keep'),
                                                   parameter_overrides=args.get('parameter_overrides')))
            elif name == 'request_measurement' and self.session is not None:
                value = self.session.request_measurement(args['measurement'])
                self.packet = deepcopy(value['current_packet'])
            elif name == 'submit_decision':
                if not isinstance(args.get('rationale'), str) or not isinstance(args.get('uncertainty'), str):
                    raise ValueError('rationale and uncertainty required')
                if self.session:
                    # Score interpretation separately from physical intervention.
                    score = score_submission(self.dataset, self.case_id, 'diagnosis', args)
                    verified = self.session.commit(args.get('action_id', ''), hypotheses=args.get('hypotheses', []))
                    score.update(task='resolution', resolution_verification=verified,
                                 verified_cause_asserted_without_session_measurements=bool(args.get('claim_verified')) and not any(e.get('measurement') for e in self.session.events))
                else:
                    score = score_submission(self.dataset, self.case_id, self.task, args)
                self.submission, self.score = deepcopy(args), score
                # No hidden score, causal label or counterfactual gets sent back.
                value = {'accepted': True, 'decision_frozen': True}
            else:
                value = {'error': 'tool unavailable in this arm or task'}
        except Exception as exc:
            value = {'error': type(exc).__name__+': '+str(exc)[:1200]}
        self.history.append({'name': name, 'arguments': args, 'result': value,
                             'wall_seconds': time.perf_counter()-started})
        return value


def run_one(dataset: Path, output: Path, case_id: str, task: str, arm: str, protocol: dict, *, preflight=False) -> dict:
    work = output / 'attempts' / case_id / task / arm
    receipt = work / 'run.json'
    if receipt.exists():
        return json.loads(receipt.read_text())
    work.mkdir(parents=True, exist_ok=True)
    inputs = work / 'agent-input'
    staged = stage(dataset, case_id, task, arm, inputs)
    host = HostTools(dataset, case_id, task, arm, work / 'numerical-scratch', protocol['tool_calls'])
    request = {'type': 'initialize', 'bundle_root': str(DEFAULT_PRIME_BUNDLE),
               'cwd': str(inputs.resolve()), 'model': protocol['model'], 'task': task, 'arm': arm,
               'system_prompt': SYSTEM,
               'prompt': json.dumps({'task': host.packet['objective'], 'packet': host.packet,
                                     'budget': {'host_tool_calls': protocol['tool_calls'], 'wall_seconds': protocol['wall_seconds']}}, separators=(',', ':')),
               'timeout_seconds': protocol['wall_seconds'], 'max_model_calls': protocol['model_calls'],
               'public_schema': {'hypotheses': host.packet['hypothesis_classes'],
                                 'actions': [a['id'] for a in host.packet['allowed_actions']],
                                 'measurements': [m['id'] for m in host.packet['measurement_catalog']],
                                 'parameters': ['kla_h_inv', 'our_scale', 'broth_factor'] if host.packet['domain']=='oxygen' else ['kv_scale', 'rp_scale']},
               'max_output_tokens': protocol['max_output_tokens'], 'preflight': preflight}
    node = shutil.which('node')
    started = time.perf_counter()
    process = subprocess.Popen([node, str(Path(__file__).with_name('sdk_experiment.mjs').resolve())],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, cwd=inputs, env=os.environ.copy(), start_new_session=True, bufsize=1)
    events = queue.Queue()
    errors = []
    def stdout_reader():
        for line in process.stdout:
            events.put(line)
        events.put(None)
    def stderr_reader():
        errors.extend(process.stderr)
    readers = [threading.Thread(target=stdout_reader, daemon=True), threading.Thread(target=stderr_reader, daemon=True)]
    for thread in readers:
        thread.start()
    process.stdin.write(json.dumps(request)+'\n')
    process.stdin.flush()
    log = []
    finished = None
    capability = None
    deadline = time.monotonic()+protocol['wall_seconds']+20
    try:
        while time.monotonic() < deadline:
            if (output / 'STOP').exists():
                break
            try:
                line = events.get(timeout=1)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            if line is None:
                break
            try:
                event = json.loads(line)
            except ValueError:
                log.append({'type': 'sdk_log', 'text': line[:2000]})
                continue
            log.append(event)
            if event.get('type') == 'capability_audit':
                capability = event
            elif event.get('type') == 'tool_request':
                value = host.call(event['name'], event.get('args', {}))
                process.stdin.write(json.dumps({'type': 'tool_result', 'id': event['id'], 'result': value})+'\n')
                process.stdin.flush()
            elif event.get('type') == 'finished':
                finished = event
                break
    finally:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        for thread in readers:
            thread.join(timeout=1)
    status = 'completed' if host.submission is not None else 'interrupted' if (output / 'STOP').exists() else (finished or {}).get('status', 'failed')
    result = {'version': VERSION, 'case_id': case_id, 'task': task, 'arm': arm,
              'model': protocol['model'], 'status': status, 'preflight_only': preflight,
              'wall_seconds': time.perf_counter()-started,
              'common_input_sha256': staged['common_input_sha256'], 'capability_audit': capability,
              'model_calls': (finished or {}).get('model_calls', sum(e.get('type') == 'model_start' for e in log)),
              'usage': (finished or {}).get('usage', [e.get('usage') for e in log if e.get('type') == 'model_usage']),
              'provider_cost_usd': None, 'cost_status': 'hosted_billing_unknown',
              'tool_calls': len(host.history), 'physical_model_calls': sum(e['name'] == 'physical_forward_model' for e in host.history),
              'submission': host.submission, 'score': host.score,
              'error': (finished or {}).get('error') or (''.join(errors)[-1800:] if status != 'completed' else None),
              'real_equipment_actions': False}
    dump(work / 'events.json', log)
    dump(work / 'tools.json', host.history)
    dump(receipt, result)
    return result


def metric_rows(records: list[dict], task: str, arm: str):
    return [r for r in records if r['task'] == task and r['arm'] == arm]


def arm_metrics(rows: list[dict], task: str) -> dict:
    completed = [r for r in rows if r['status'] == 'completed' and r.get('score')]
    scores = [r['score'] for r in completed]
    def mean(values):
        return sum(values)/len(values) if values else None
    result = {'attempted': len(rows), 'completed': len(completed), 'failed_or_unsubmitted': len(rows)-len(completed),
              'mean_authored_cause_coverage': mean([s['authored_cause_coverage'] for s in scores]),
              'mean_hypothesis_set_size': mean([s['hypothesis_set_size'] for s in scores]),
              'top_rank_matches': sum(s['top_rank_matches_authored_cause'] is True for s in scores),
              'mean_agent_wall_seconds': mean([r['wall_seconds'] for r in rows]),
              'mean_tool_calls': mean([r['tool_calls'] for r in rows]),
              'physical_model_calls': sum(r['physical_model_calls'] for r in rows),
              'verified_cause_assertions_without_measurements': sum(s['verified_cause_asserted_without_session_measurements'] for s in scores)}
    if task in ('optimization', 'pretransfer'):
        committed = [s for s in scores if s.get('independently_replayed_outcome')]
        result.update(actions_committed=len(committed),
                      feasible_selected_actions=sum(s['independently_replayed_outcome']['feasible_full_batch'] for s in committed),
                      deferrals=sum(s.get('action_not_committed', False) for s in scores),
                      mean_feasible_grid_regret=mean([s['feasible_objective_regret'] for s in committed if s.get('feasible_objective_regret') is not None]))
    if task == 'pretransfer':
        result['warnings'] = {key: sum(s['warning_result'] == key for s in scores) for key in ('TP', 'FP', 'FN', 'TN', 'abstained')}
    if task == 'resolution':
        verified = [s['resolution_verification'] for s in scores]
        resolved = [v for v in verified if v['verified_process_constraint_resolution_h'] is not None]
        result.update(verified_simulated_resolutions=len(resolved),
                      mean_simulated_resolution_h=mean([v['verified_process_constraint_resolution_h'] for v in resolved]),
                      mean_synthetic_measurement_rounds=mean([v['synthetic_measurement_rounds'] for v in verified]),
                      mean_synthetic_human_work_minutes=mean([v['synthetic_human_work_minutes'] for v in verified]))
    return result


def aggregate(records: list[dict], protocol: dict, *, status='running') -> dict:
    pairs = {}
    for row in records:
        pairs.setdefault((row['case_id'], row['task']), {})[row['arm']] = row
    paired = [arms for arms in pairs.values() if set(arms) == {'A', 'B'}]
    matched = all(p['A']['common_input_sha256'] == p['B']['common_input_sha256'] for p in paired)
    audited = [p for p in paired if all((p[arm].get('capability_audit') or {}).get('shared_tool_schema_sha256') for arm in ('A','B'))]
    schema_match = all(p['A']['capability_audit']['shared_tool_schema_sha256'] == p['B']['capability_audit']['shared_tool_schema_sha256'] for p in audited) if audited else None
    return {'version': VERSION, 'status': status, 'protocol': protocol,
            'planned_attempts': protocol['planned_attempts'], 'attempted': len(records),
            'completed': sum(r['status'] == 'completed' for r in records),
            'complete_pairs': sum(p['A']['status'] == p['B']['status'] == 'completed' for p in paired),
            'pair_inputs_match': matched,
            'shared_tool_schemas_match': schema_match, 'schema_pairs_audited': len(audited),
            'tasks': {task: {arm: arm_metrics(metric_rows(records, task, arm), task) for arm in ('A', 'B')} for task in protocol['tasks']},
            'records': records, 'observed_engineer_hours_saved': None, 'real_batches_prevented': None,
            'publication_scope': 'Exploratory synthetic, restricted-tool Prime SDK comparison; not full-platform validation or a prospective manufacturing study.',
            'independent_scientific_review': 'not_performed', 'provider_billing': 'unknown'}


def execute(dataset: Path, output: Path, *, workers=3, limit_cases=None, tasks=None, timeout=120, preflight_only=False):
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    verify_implementation(dataset)
    manifest = json.loads((dataset / 'manifest.json').read_text())
    profile = hosted_research_profile()
    if profile is None:
        raise RuntimeError('No configured hosted research model; no model selected implicitly')
    cases = sorted({row['case_id'] for row in json.loads((dataset / 'public/catalogue.json').read_text())})
    if limit_cases:
        cases = cases[:limit_cases]
    tasks = tasks or ['pretransfer', 'diagnosis', 'optimization', 'resolution']
    if any(t not in ('pretransfer', 'diagnosis', 'optimization', 'resolution') for t in tasks):
        raise ValueError('unknown task')
    output.mkdir(parents=True, exist_ok=True)
    code_files = ['run_agents.py', 'sdk_experiment.mjs', 'research_sandbox.py']
    protocol = {'version': VERSION, 'model': f'{profile.provider}/{profile.model}',
                'case_ids': cases, 'tasks': tasks, 'planned_attempts': len(cases)*len(tasks)*2,
                'wall_seconds': timeout, 'tool_calls': 10, 'model_calls': 8, 'max_output_tokens': 8192,
                'thinking': 'native low via reasoning_effort and chat_template_kwargs in both arms',
                'reasoning_configuration_source': 'https://recipes.vllm.ai/zai-org/GLM-5.3#reasoning-modes',
                'workers': workers, 'dataset_manifest_sha256': digest(dataset / 'manifest.json'),
                'runner_sha256': {name: digest(Path(__file__).with_name(name)) for name in code_files},
                'system_prompt_sha256': hashlib.sha256(SYSTEM.encode()).hexdigest(),
                'arm_difference': 'B additionally receives physical_forward_model; numerical Python is shared.',
                'submission_schema': 'Exact enums from the public packet for hypothesis, action and measurement IDs in both arms; explanations have separate rationale/evidence fields.',
                'pair_order': 'Counterbalanced by case/task hash, sequential arms within each pair; independent pairs may execute concurrently.',
                'scope': 'Restricted read-only research via existing Prime SDK; no production qualification is created.',
                'scoring': 'Authored cause coverage plus set size/rank; feasible action grid regret; warning confusion incl abstention; verified simulated full-batch constraints and assumed measurement effort.',
                'known_limits': ['Synthetic, previously inspected development cases; no untouched holdout.',
                                 'No repeated stochastic trials or prespecified statistical power.',
                                 'No independently blinded scientific adjudication or real engineer-effort measurement.',
                                 'Steady oxygen and representative-vial tools share physical laws with richer synthetic evaluators.',
                                 'Full-batch constraints penalize prior excursions; no rescue is implied.']}
    path = output / 'protocol.json'
    if path.exists() and json.loads(path.read_text()) != protocol:
        raise ValueError('protocol differs from existing run; use a fresh output directory')
    dump(path, protocol)  # frozen before any model call
    for name in code_files:
        snapshot = output / 'runner-source' / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not snapshot.exists():
            shutil.copyfile(Path(__file__).with_name(name), snapshot)
    isolation = probe(dataset, output / 'isolation-probe')
    dump(output / 'isolation.json', isolation)
    if preflight_only:
        value = run_one(dataset, output, cases[0], tasks[0], 'A', protocol, preflight=True)
        dump(output / 'preflight.json', value)
        return value
    lock = threading.Lock()
    records = []
    def pair(case_id, task):
        order = ('A', 'B') if int(hashlib.sha256(f'{case_id}:{task}'.encode()).hexdigest()[:2], 16) % 2 else ('B', 'A')
        for arm in order:
            if (output / 'STOP').exists():
                return
            row = run_one(dataset, output, case_id, task, arm, protocol)
            with lock:
                records.append(row)
                dump(output / 'results.json', aggregate(records, protocol))
                print(json.dumps({'case_id': case_id, 'task': task, 'arm': arm, 'status': row['status'],
                                  'attempted': len(records), 'planned': protocol['planned_attempts'],
                                  'wall_seconds': round(row['wall_seconds'], 2)}), flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(pair, case_id, task) for case_id in cases for task in tasks]
        for future in as_completed(futures):
            future.result()
    result = aggregate(records, protocol, status='interrupted' if (output / 'STOP').exists() else 'complete')
    dump(output / 'results.json', result)
    return {k: result[k] for k in ('version', 'status', 'planned_attempts', 'attempted', 'completed', 'complete_pairs', 'pair_inputs_match', 'tasks')}


if __name__ == '__main__':
    load_env_file(Path(__file__).resolve().parents[2] / '.env.local')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--workers', type=int, default=3, choices=range(1, 5))
    parser.add_argument('--limit-cases', type=int)
    parser.add_argument('--tasks', nargs='+')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(execute(args.dataset, args.output, workers=args.workers, limit_cases=args.limit_cases,
                             tasks=args.tasks, timeout=args.timeout, preflight_only=args.preflight_only), indent=2))
