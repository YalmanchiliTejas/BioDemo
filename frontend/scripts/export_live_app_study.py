"""Export actual authenticated app captures; never synthesize successful runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {'completed', 'blocked', 'agent_unavailable', 'needs_information', 'failed', 'interrupted'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(identifier, label, passed, detail):
    return {'id': identifier, 'label': label, 'status': 'not_applicable' if passed is None else 'passed' if passed else 'failed', 'detail': detail}


def summarize(captures):
    turns, artifacts = {}, {}
    deliveries = []
    sources = []
    for path in captures:
        record = json.loads(Path(path).read_text())
        if record.get('version') not in {'sievance-live-demo-v1', 'sievance-live-delivery-v1'} or record.get('execution') != 'live_authenticated_app':
            raise ValueError('Only actual live-app captures are eligible')
        expected = hashlib.sha256(json.dumps({k: v for k, v in record.items() if k != 'capture_sha256'}, sort_keys=True).encode()).hexdigest()
        if expected != record['capture_sha256']:
            raise ValueError('Capture changed after collection')
        sources.append({'file': Path(path).name, 'sha256': sha(path), 'captured_at': record['captured_at']})
        if record['version'] == 'sievance-live-delivery-v1':
            delivery = record['delivery']
            if delivery.get('cmo') != 'Sievance public demo 2026-10-31' or delivery.get('status') not in {'complete', 'failed', 'interrupted', 'unavailable'}:
                raise ValueError('Only terminal explicitly labeled demo deliveries are eligible')
            deliveries.append({k: delivery.get(k) for k in ('id', 'package_id', 'status', 'error', 'disclosure', 'summary', 'stages')})
            continue
        if record['thread'].get('demo_enabled') is not True:
            raise ValueError('Non-demo conversation cannot be published')
        for turn in record['thread']['turns']:
            turns[turn['id']] = turn
        for artifact in record['artifacts']:
            artifacts[artifact['id']] = artifact
    if not turns or any(t['status'] not in TERMINAL for t in turns.values()):
        raise ValueError('Wait for every included attempt to reach a terminal state')
    ordered = sorted(turns.values(), key=lambda t: (t.get('created_at', ''), t['id']))
    results, checks = [], []
    plans = {a['id']: a['data'] for a in artifacts.values() if a['kind'] == 'physical_analysis_plan'}
    for artifact in artifacts.values():
        if artifact['kind'] != 'physical_analysis_result':
            continue
        data = artifact['data']
        plan = plans.get(data['plan_id'])
        checks.append(checked(data['id'] + '-plan', 'Result binds to the recorded plan',
                              bool(plan) and plan['plan_hash'] == data['plan_hash'], data['plan_id']))
        usage = data['resource_usage']
        checks.append(checked(data['id'] + '-budget', 'Solver calls stay within the recorded allowance',
                              usage['solver_calls'] <= usage['maximum_solver_calls'],
                              f"{usage['solver_calls']} / {usage['maximum_solver_calls']} solver calls"))
        for model in data['models']:
            prediction = model.get('prediction') or {}
            trajectory = prediction.get('trajectory') or []
            completed = model['status'] == 'completed' and prediction.get('numerical_status') == 'completed'
            checks.append(checked(data['id'] + model['model_id'] + '-numerics', 'Numerical solver completed', completed,
                                  prediction.get('numerical_error') or model.get('error') or prediction.get('numerical_status', 'Unavailable')))
            times = [r['time_h'] for r in trajectory]
            finite = bool(times) and all(math.isfinite(t) for t in times) and all(b >= a for a, b in zip(times, times[1:]))
            checks.append(checked(data['id'] + model['model_id'] + '-times', 'Trajectory times are finite and ordered',
                                  finite if completed else None, f'{len(times)} returned trajectory points'))
            holdout = model.get('holdout_evaluation') or {}
            pairs = holdout.get('pairs') or []
            residuals = [r['residual_c'] for r in pairs] if pairs and all('residual_c' in r for r in pairs) else []
            calculated_rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals)) if residuals else None
            checks.append(checked(data['id'] + model['model_id'] + '-holdout', 'Reported holdout RMSE reproduces from residuals',
                                  math.isclose(calculated_rmse, holdout['rmse_c'], rel_tol=1e-7, abs_tol=1e-9)
                                  if calculated_rmse is not None and holdout.get('rmse_c') is not None else None,
                                  'No holdout observations available' if not pairs else f'{len(pairs)} paired observations'))
            results.append({'result_id': data['id'], 'model_id': model['model_id'], 'status': model['status'],
                            'numerical_status': prediction.get('numerical_status'), 'completion_time_h': prediction.get('completion_time_h'),
                            'minimum_critical_margin_c': prediction.get('minimum_critical_margin_c'),
                            'minimum_capacity_margin_kg_h': prediction.get('minimum_capacity_margin_kg_h'),
                            'violations': prediction.get('violations', []), 'warnings': prediction.get('warnings', []),
                            'trajectory': trajectory, 'holdout': holdout, 'uncertainty': model.get('uncertainty'),
                            'provenance': data['observation_provenance'], 'plan_hash': data['plan_hash'],
                            'implementation_digest': model.get('implementation_digest'), 'resource_usage': usage})
    attempts = [{'id': t['id'], 'prompt': t['user_text'], 'status': t['status'], 'reply': t.get('reply'),
                 'questions': t.get('questions', []), 'issues': t.get('issues', []), 'system_message': t.get('system_message'),
                 'elapsed_seconds': t.get('elapsed_seconds'), 'steps': t.get('steps', []), 'artifacts': t.get('artifacts', []),
                 'gateway_runs': t.get('gateway_runs', [])} for t in ordered]
    return {'version': 'sievance-live-app-study-v1', 'title': 'From a question to an executed numerical workflow',
            'classification': 'Live product functional evaluation · exploratory', 'date': '2026-10-31',
            'execution_origin': 'https://www.sievance.com', 'attempts': attempts, 'results': results, 'checks': checks,
            'delivery_checks': deliveries,
            'counts': {'attempts': len(attempts), 'completed': sum(a['status'] == 'completed' for a in attempts),
                       'blocked_or_unavailable': sum(a['status'] in {'blocked', 'agent_unavailable', 'failed', 'interrupted'} for a in attempts),
                       'needs_information': sum(a['status'] == 'needs_information' for a in attempts),
                       'numerical_results': len(results), 'checks_passed': sum(c['status'] == 'passed' for c in checks),
                       'checks_failed': sum(c['status'] == 'failed' for c in checks),
                       'checks_not_applicable': sum(c['status'] == 'not_applicable' for c in checks)},
            'sources': sources, 'provider_billed_cost_usd': None,
            'cost_notice': 'Actual provider billing was not returned by the app. Zero-valued gateway estimates do not mean free inference.',
            'limits': ['This is an exploratory live-app functional evaluation, not the proposed extensive benchmark.',
                       'Prompts were refined after failures; attempts are correlated and no untouched generalization claim is supported.',
                       'Reconstructed/synthetic demo observations are not independent plant measurements.',
                       'Numerical completion does not establish a feasible process or scientific model qualification.',
                       'No independent scientific adjudication, matched human-time baseline or manufacturing action was performed.',
                       'Prior paired physics studies below are separate experiments and are not replications of these app runs.']}


def export(captures, destination, video=None):
    destination = Path(destination)
    data = summarize(captures)
    destination.mkdir(parents=True, exist_ok=True)
    if video:
        video = Path(video)
        if not video.is_file() or video.suffix != '.mp4':
            raise ValueError('Video must be an existing MP4')
        target = destination / video.name
        if target.resolve() != video.resolve():
            shutil.copyfile(video, target)
        data.update(video=target.name, video_sha256=sha(target),
                    video_classification='edited_walkthrough_of_saved_live_results; login_excluded')
    for source in captures:
        shutil.copyfile(source, destination / Path(source).name)
    (destination / 'summary.json').write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    lines = ['# Live Sievance app evaluation', '', data['classification'], '',
             f"Recorded {data['counts']['attempts']} actual attempts; {data['counts']['completed']} completed workflow turns.", '',
             '| Attempt | Status | Wall seconds |', '|---|---|---:|',
             *[f"| {a['id']} | {a['status']} | {a.get('elapsed_seconds')} |" for a in data['attempts']], '',
             '## Numerical results', '', '| Model | Completion h | Critical margin C | Capacity margin kg/h |', '|---|---:|---:|---:|',
             *[f"| {r['model_id']} | {r['completion_time_h']} | {r['minimum_critical_margin_c']} | {r['minimum_capacity_margin_kg_h']} |" for r in data['results']], '',
             'A returned trajectory with a vapor-capacity violation is an invalid-control diagnostic extrapolation, not a feasible operating plan.', '',
             '## Limits', '', *['- ' + item for item in data['limits']], '', data['cost_notice'], '',
             '## Additional delivery checks', '',
             *[f"- {d['id']} · {d['status']} · {d.get('error') or 'No error returned'}" for d in data['delivery_checks']], '',
             '## Captures', '', *[f"- {s['file']} · SHA-256 {s['sha256']}" for s in data['sources']]]
    (destination / 'report.md').write_text('\n'.join(lines) + '\n')
    return data['counts']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'frontend/public/case-study-results/live-app')
    parser.add_argument('--video', type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.capture, args.output, args.video)))
