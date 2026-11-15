"""Live arms of the workflow trial: the assistant and candidate reasoning models on the same evidence.

    PYTHONPATH=backend .venv/bin/python -m benchmarks.workflow_trial.live --output backend/results/<new-directory>

This spends money and sends the CHO delivery values (public data, CC BY 4.0) to the configured model providers.
Nothing runs unless you start it. Two questions are measured, on the deliveries the offline trial uses:

1. How long does a person wait, and is the answer right, when the same request goes
   - to the assistant alone (it has to find the delivery and calculate through its tools), or
   - through the workbench path (a routine request is calculated by the host; a question reaches the assistant with
     the calculation already attached)?
2. For one bounded explanation of a calculated comparison, which model is fast enough and still right?
   Every candidate gets the identical calculated result and question, in one call.

Scoring uses the reference figures from the answer keys, not a judge model: an answer is checked for the largest
difference, its time, the mean difference and both batch names. Those are necessary, not sufficient: wording and
reasoning quality still need a qualified reader, and a sample this small ranks nothing with confidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import run as trial

MODEL_SETTINGS = ('MODAL_BASE_URL', 'MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_BASE_URL', 'BIODEMO_MODAL_PROXY_TOKEN', 'MODAL_TIMEOUT_SECONDS',
                  'MODAL_MIN_MAX_TOKENS', 'LIFESCI_LLM_MODEL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL', 'OPENAI_API_KEY', 'OPENAI_BASE_URL')
QUESTION = 'What does this comparison show, and what should be checked next?'
NUMBER = re.compile(r'(?<![\w.])[-+−]?\d+(?:[.,]\d+)*(?:\.\d+)?(?:[eE][-+]?\d+)?')


def load_settings() -> dict[str, str]:
    """Model endpoints and keys only, from the local settings files. Never a database or project URL."""
    from src.lifesci.envfile import parse_env
    found: dict[str, str] = {}
    for path in (trial.BACKEND / 'deploy' / 'aws' / 'production.env', trial.BACKEND / '.env.local'):
        if path.is_file():
            found.update({k: v for k, v in parse_env(path.read_text()).items() if k in MODEL_SETTINGS and v})
    found.update({k: os.environ[k] for k in MODEL_SETTINGS if os.environ.get(k)})
    return found


def candidates(settings) -> dict[str, dict[str, Any]]:
    glm = settings.get('LIFESCI_LLM_MODEL') or 'zai-org/GLM-5.3'
    return {
        'glm': {'provider': 'modal', 'model': glm, 'label': f'{glm} (current)', 'env': {}},
        'glm-low-effort': {'provider': 'modal', 'model': glm, 'label': f'{glm}, low reasoning effort', 'env': {'MODAL_COMPLETION_REASONING_EFFORT': 'low', 'MODAL_COMPLETION_JSON': '1'}},
        'haiku': {'provider': 'anthropic', 'model': 'claude-haiku-5-5', 'label': 'Claude Haiku 5.5', 'env': {}},
        'sonnet': {'provider': 'anthropic', 'model': 'claude-sonnet-5-5', 'label': 'Claude Sonnet 5.5', 'env': {}},
        'luna': {'provider': 'openai', 'model': 'gpt-6-luna', 'label': 'GPT-6 Luna', 'env': {}},
        'sol': {'provider': 'openai', 'model': 'gpt-6.1-sol', 'label': 'GPT-6.1 Sol', 'env': {}},
    }


def provider_for(candidate, settings):
    from src.lifesci.gateway import AnthropicProvider, ModalProvider, OpenAIProvider
    if candidate['provider'] == 'modal':
        return ModalProvider(environ={**settings, **candidate['env']})
    if candidate['provider'] == 'anthropic':
        return AnthropicProvider(settings.get('ANTHROPIC_API_KEY'), settings.get('ANTHROPIC_BASE_URL'))
    return OpenAIProvider(settings.get('OPENAI_API_KEY'), settings.get('OPENAI_BASE_URL'))


def platform_for(world, candidate, settings):
    """A fresh application on the same evidence, with exactly this model bound to the reasoning roles."""
    os.environ['LIFESCI_LLM_PROVIDER'], os.environ['LIFESCI_LLM_MODEL'] = candidate['provider'], candidate['model']
    for name in ('LIFESCI_INTERPRETER_PROVIDER', 'LIFESCI_INTERPRETER_MODEL', 'LIFESCI_DECISION_ADAPTER'):
        os.environ.pop(name, None)
    providers = {candidate['provider']: provider_for(candidate, settings)}
    effort = os.environ.get('LIFESCI_INTERPRETER_REASONING_EFFORT', '').strip().lower()
    if candidate['provider'] == 'modal' and effort in ('low', 'medium', 'high'):
        # As the product runs it: the explanation role has its own effort, the assistant keeps the default.
        from src.lifesci.gateway import ModalProvider
        from src.lifesci.gateway.configuration import INTERPRETER_PROVIDER
        providers[INTERPRETER_PROVIDER] = ModalProvider(environ={**settings, 'MODAL_COMPLETION_REASONING_EFFORT': effort, 'MODAL_COMPLETION_JSON': '1'})
    p, ctx, deliveries, _ = world['new_platform'](providers=providers, allow_unqualified=True)
    p.gateway.max_retries = 0  # one request per call: a retry would hide how long a person really waits
    return p, ctx, deliveries


def clocked(call):
    """Run one call and time it two ways. The monotonic timer stops while a laptop sleeps and the wall clock does not,
    so a gap between them means the machine slept during the call: that timing is not a measurement and is set aside."""
    wall, t0 = time.time(), time.perf_counter()
    value = call()
    seconds, elapsed = time.perf_counter() - t0, time.time() - wall
    return value, seconds, {'started_at': datetime.fromtimestamp(wall, timezone.utc).isoformat(),
                            'interrupted_by_sleep': abs(elapsed - seconds) > 2.0, 'wall_clock_seconds': round(elapsed, 1)}


def keep(path, row):
    """Each finished request is written at once, so an interrupted run keeps what it measured."""
    with path.open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
    return row


def numbers(text: str) -> list[float]:
    out = []
    for raw in NUMBER.findall(text or ''):
        cleaned = raw.replace('−', '-').replace(',', '')
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def facts(text: str, expected: dict, left: str, right: str) -> dict[str, bool]:
    """Whether the answer states the reference figures. A figure counts when a number in the text rounds to it."""
    found = numbers(text)
    near = lambda target, slack: target is not None and any(abs(abs(v) - abs(target)) <= max(slack, abs(target) * 0.006) for v in found)
    return {'largest_difference': near(expected['largest_abs_difference'], 0.006),
            'its_time': any(any(abs(v - t) <= 0.051 for v in found) for t in expected['largest_at']),
            'mean_difference': near(expected['mean_difference'], 0.006),
            'both_batches': left in (text or '') and right in (text or '')}


def cases(world) -> list[dict]:
    out = []
    for package in trial.TARGETS:
        ref = trial.reference(world['keys'][package])
        left, right = ref['batches'][0], ref['batches'][1]
        for parameter in ('glucose', 'viable_cell_density'):
            expected = trial.expected_comparison(ref, parameter, left, right)
            out.append({'id': f'{package}:{parameter}', 'package': package, 'parameter': parameter, 'left': left, 'right': right,
                        'expected': expected, 'spoken': parameter.replace('_', ' ')})
    return out


# --- arm 2: one bounded explanation, every candidate on the identical result --------------------------------------
def explain_arm(world, settings, names, selected, log) -> list[dict]:
    rows = []
    for name in names:
        candidate = candidates(settings)[name]
        os.environ.update(candidate['env'])
        try:
            p, ctx, deliveries = platform_for(world, candidate, settings)
            for case in selected:
                row = {'candidate': name, 'label': candidate['label'], 'case': case['id'], 'status': 'error'}
                # Each case is measured on its own: a failure in the previous case must not close the route for this one.
                p.gateway._down_until.clear()
                try:
                    result = p.workspace_tasks.execute(ctx, {
                        'site_id': trial.SITE, 'operation': 'compare', 'dataset_ids': [deliveries[case['package']]['id']],
                        'parameter': case['parameter'], 'batches': [case['left'], case['right']], 'include_unverified': True})
                    answer, seconds, clock = clocked(lambda: p.workspace_tasks.explain(ctx, result['id'], QUESTION))
                    row.update(clock)
                    trace = p.store.read().require(trial.TENANT, 'model_run', answer['run_id']).state
                    attempts = [a for a in trace['attempts'] if 'model' in a]
                    text = ' '.join([answer.get('explanation') or '', *answer.get('observations', [])])
                    row.update(status=answer['status'], seconds=seconds, model_seconds=answer['timing']['model_seconds'],
                               calls=len(attempts), input_tokens=sum(a.get('input_tokens') or 0 for a in attempts),
                               output_tokens=sum(a.get('output_tokens') or 0 for a in attempts),
                               reason=answer.get('reason'), explanation=answer.get('explanation'),
                               observations=answer.get('observations'), hypotheses=answer.get('hypotheses'),
                               unknowns=answer.get('unknowns'),
                               facts=facts(text, case['expected'], case['left'], case['right']) if answer['status'] == 'completed' else None)
                except Exception as exc:  # a failed call stays in the report
                    row['error'] = f'{type(exc).__name__}: {str(exc)[:300]}'
                rows.append(keep(log, row))
                print(f"explain {name:15s} {case['id']:34s} {row['status']:11s} {row.get('seconds', 0):6.1f} s", flush=True)
            p.store.release_connections()
        finally:
            for key in candidate['env']:
                os.environ.pop(key, None)
    return rows


# --- arm 1: the assistant alone against the workbench path ----------------------------------------------------------
def ask(world, settings, candidate, text) -> dict:
    p, ctx, _ = platform_for(world, candidate, settings)
    try:
        thread = p.engineering_conversations.create(ctx, {'site_id': trial.SITE})
        queued = p.engineering_conversations.enqueue(ctx, thread['id'], {
            'text': text, 'expected_revision': thread['revision'], 'include_unverified': True})
        _, waited, clock = clocked(lambda: p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1]))
        turn = p.engineering_conversations.get(ctx, thread['id'])['turns'][-1]
        attempts = [a for run in turn.get('gateway_runs', []) for a in run.get('attempts', []) if 'model' in a]
        grounding = turn.get('grounding') or {}
        return {**clock, 'status': turn['status'], 'seconds': waited, 'timing': turn.get('timing'), 'reply': turn.get('reply'),
                'path': (turn.get('timing') or {}).get('path'), 'model_calls': len(attempts),
                'input_tokens': sum(a.get('input_tokens') or 0 for a in attempts),
                'output_tokens': sum(a.get('output_tokens') or 0 for a in attempts),
                'steps': [s.get('title') for s in turn.get('steps') or []], 'issues': turn.get('issues'),
                'unsupported_numbers': grounding.get('unsupported_numbers'), 'grounding_status': grounding.get('status')}
    finally:
        p.store.release_connections()


def assistant_arm(world, settings, selected, workers, log, arms=('alone', 'workbench'), kinds=('routine', 'question')) -> list[dict]:
    candidate = candidates(settings)['glm']
    requests = []
    for case in selected:
        requests.append({**case, 'kind': 'routine', 'text': f"Compare {case['spoken']} between {case['left']} and {case['right']}"})
        requests.append({**case, 'kind': 'question', 'text': f"Why is {case['spoken']} different between {case['left']} and {case['right']}?"})
    requests = [r for r in requests if r['kind'] in kinds]
    rows = []
    for arm, direct in (('assistant alone', 'off'), ('workbench path', 'on')):
        if ('alone' if 'alone' in arm else 'workbench') not in arms:
            continue
        os.environ['ASSISTANT_DIRECT_ROUTE'], os.environ['ASSISTANT_LOOP'] = direct, 'tools'
        def one(request, arm=arm):
            row = {'arm': arm, 'case': request['id'], 'kind': request['kind'], 'text': request['text'], 'status': 'error'}
            try:
                row.update(ask(world, settings, candidate, request['text']))
                row['facts'] = facts(row.get('reply') or '', request['expected'], request['left'], request['right']) if row.get('reply') else None
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {str(exc)[:300]}'
            print(f"{arm:16s} {request['kind']:9s} {request['id']:34s} {row['status']:18s} {row.get('seconds', 0):6.1f} s", flush=True)
            return keep(log, row)
        # Platforms bind their model when built, from process settings: build them one at a time, then wait together.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows += list(pool.map(one, requests))
    os.environ.pop('ASSISTANT_DIRECT_ROUTE', None)
    return rows


def summarize(rows, key) -> list[dict]:
    from src.lifesci.latency import distribution
    out = []
    for name in dict.fromkeys(r[key] for r in rows):
        group = [r for r in rows if r[key] == name]
        answered = [r for r in group if r.get('facts')]
        figure = lambda k: sum(r['facts'][k] for r in answered)
        out.append({key: name, 'requests': len(group), 'statuses': dict(Counter(r['status'] for r in group)),
                    'answered': len(answered), 'all_reference_figures': sum(all(r['facts'].values()) for r in answered),
                    'largest_difference': figure('largest_difference'), 'its_time': figure('its_time'),
                    'mean_difference': figure('mean_difference'), 'both_batches': figure('both_batches'),
                    'time': distribution([r['seconds'] for r in group if 'seconds' in r and not r.get('interrupted_by_sleep')]),
                    'timings_set_aside_for_sleep': sum(bool(r.get('interrupted_by_sleep')) for r in group),
                    'input_tokens': sum(r.get('input_tokens') or 0 for r in group),
                    'output_tokens': sum(r.get('output_tokens') or 0 for r in group)})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--candidates', default='glm,glm-low-effort,haiku,sonnet,luna,sol')
    parser.add_argument('--explain-cases', type=int, default=6)
    parser.add_argument('--assistant-cases', type=int, default=3, help='Each case is asked twice per arm: as a routine request and as a question.')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--skip', choices=['explain', 'assistant'], action='append', default=[])
    parser.add_argument('--interpreter-effort', choices=['low', 'medium', 'high'],
                        help='Run the explanation role at this reasoning effort, as LIFESCI_INTERPRETER_REASONING_EFFORT does in the product.')
    parser.add_argument('--arms', default='alone,workbench', help='Assistant arms to run: alone, workbench.')
    parser.add_argument('--kinds', default='routine,question', help='Request kinds to send: routine, question.')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('the output directory already exists; choose a new one')
    sys.path.insert(0, str(trial.BACKEND))
    if args.interpreter_effort:
        os.environ['LIFESCI_INTERPRETER_REASONING_EFFORT'] = args.interpreter_effort
    else:
        os.environ.pop('LIFESCI_INTERPRETER_REASONING_EFFORT', None)
    settings = load_settings()
    started = datetime.now(timezone.utc).isoformat()
    names = [n for n in args.candidates.split(',') if n]
    unknown = [n for n in names if n not in candidates(settings)]
    if unknown:
        parser.error(f'unknown candidates: {unknown}')
    args.output.mkdir(parents=True)
    log = args.output / 'rows.jsonl'
    with tempfile.TemporaryDirectory(prefix='workflow-trial-live-') as tmp:
        world = trial.prepare(Path(tmp))
        selected = cases(world)
        explain_rows = [] if 'explain' in args.skip else explain_arm(world, settings, names, selected[:args.explain_cases], log)
        # One case per delivery for the assistant: it is the slow, costly arm.
        per_delivery = [c for c in selected if c['parameter'] == 'glucose'][:args.assistant_cases]
        assistant_rows = [] if 'assistant' in args.skip else assistant_arm(
            world, settings, per_delivery, args.workers, log, tuple(args.arms.split(',')), tuple(args.kinds.split(',')))
    report = {
        'schema_version': 'workflow-trial-live-v1', 'started_at': started, 'question': QUESTION,
        'protocol': {
            'evidence': 'The three held-out CHO deliveries of the offline trial, shared as provisional evidence; every arm starts '
                        'from a fresh application holding the same deliveries.',
            'scoring': 'Reference figures from the answer keys (largest difference, its time, mean difference, both batch names). '
                       'No judge model. Figures are necessary for a right answer, not sufficient: reasoning needs a qualified reader.',
            'timing': 'Time of the call that produces the answer, in process, one request per model call (no retries). A call during '
                      'which the machine slept is kept in the rows, marked, and left out of the timing figures.',
            'limits': ['Small sample; one attempt per case; differences between candidates are indications, not rankings.',
                       'Public laboratory data in fictional deliveries; not manufacturing validation.',
                       'Token counts are as reported by each provider; cost depends on your contract and is not estimated here.'],
        },
        'candidates': {n: {k: v for k, v in candidates(settings)[n].items() if k != 'env'} | {'settings': candidates(settings)[n]['env']} for n in names},
        'explanation': {'by_candidate': summarize(explain_rows, 'candidate'), 'rows': explain_rows},
        'assistant': {'by_arm': [{**s, 'by_kind': summarize([r for r in assistant_rows if r['arm'] == s['arm']], 'kind')}
                                 for s in summarize(assistant_rows, 'arm')], 'rows': assistant_rows},
    }
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n')
    lines = ['# Workflow trial: live arms', '', f'Started {started}.', '']
    if explain_rows:
        lines += ['## One bounded explanation of a calculated comparison', '',
                  '| Model | Answered | All reference figures | Mean s | Slowest s | Within 10 s | Output tokens |', '|---|---:|---:|---:|---:|---:|---:|']
        for s in report['explanation']['by_candidate']:
            t = s['time']
            lines.append(f"| {report['candidates'][s['candidate']]['label']} | {s['answered']}/{s['requests']} | {s['all_reference_figures']}/{s['answered']} | "
                         f"{(t['mean'] or 0):.1f} | {(t['max'] or 0):.1f} | {t['within_target']}/{t['n']} | {s['output_tokens']} |")
    if assistant_rows:
        lines += ['', '## The same requests: assistant alone against the workbench path', '',
                  '| Arm | Request | Answered | All reference figures | Mean s | Slowest s | Within 10 s |', '|---|---|---:|---:|---:|---:|---:|']
        for arm in report['assistant']['by_arm']:
            for s in arm['by_kind']:
                t = s['time']
                lines.append(f"| {arm['arm']} | {s['kind']} | {s['answered']}/{s['requests']} | {s['all_reference_figures']}/{s['answered']} | "
                             f"{(t['mean'] or 0):.1f} | {(t['max'] or 0):.1f} | {t['within_target']}/{t['n']} |")
    lines += ['', 'Limits: ' + ' '.join(report['protocol']['limits']), '']
    (args.output / 'report.md').write_text('\n'.join(lines))
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
