"""Bounded live question/task evaluation on public CHO evidence, using the production tool loop.

Run with -I. Without --execute this checks only host calculations and the scorer.
Prompts and answer-key references are frozen before inference; keys never enter the application.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from collections import Counter

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from benchmarks.workflow_trial import live, run as trial


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')
    temporary.replace(path)


def comparison_checks(case, result, delivery, decoy):
    """Score the stored calculation, including signed direction and source identity."""
    expected = case['expected']
    data = result.get('data') or {}
    summaries = data.get('comparison_summary') or []
    summary = summaries[0] if len(summaries) == 1 else {}
    largest = summary.get('largest_difference') or {}
    refs = result.get('source_refs') or []
    codes = {issue.get('code') for issue in result.get('issues') or []}
    return {
        'comparison_status': result.get('task', {}).get('operation') == 'compare'
            and result.get('task_status') == ('needs_information' if case['conflict_expected'] else 'completed')
            and result.get('status') == 'current',
        'parameter_and_direction': summary.get('parameter') == case['parameter']
            and summary.get('left_batch') == case['left'] and summary.get('right_batch') == case['right'],
        'unit': summary.get('unit') == case['unit'],
        'matched_times': summary.get('matched_times') == expected['matched_times']
            and data.get('comparison_count') == expected['matched_times'],
        'signed_mean': trial.close(summary.get('mean_difference'), expected['mean_difference']),
        'largest_magnitude': isinstance(largest.get('difference'), (int, float))
            and trial.close(abs(largest['difference']), expected['largest_abs_difference']),
        'largest_time': any(trial.close(largest.get('time_h'), t) for t in expected['largest_at']),
        'standard_deviation': expected['standard_deviation'] is None
            or trial.close((summary.get('statistics') or {}).get('standard_deviation'), expected['standard_deviation']),
        'complete_series': len(data.get('series') or []) == 2 and bool(data.get('series_complete')) and not data.get('truncated'),
        'exact_time_alignment': (data.get('alignment') or {}).get('tolerance_h') == 0,
        'current_source': any(r.get('kind') == 'evidence' and r.get('id') == delivery['id']
            and r.get('revision') == delivery['revision'] and r.get('site_id') == trial.SITE for r in refs),
        'no_wrong_site': not any(r.get('id') == decoy or r.get('site_id') == trial.OTHER_SITE for r in refs)
            and decoy not in json.dumps(data),
        'provisional_disclosed': result.get('evidence_state') == 'provisional',
        'conflicts_disclosed': ('conflicting_measurements' in codes) == case['conflict_expected'],
        'deterministic_calculation': result.get('model_calls') == 0,
    }


def reply_coverage(case, reply):
    """Necessary figure coverage only; presence cannot establish semantic correctness."""
    # Avoid interpreting a suffix in an identifier as a signed measurement.
    clean = reply.replace(case['left'], '').replace(case['right'], '')
    found = live.numbers(clean)
    expected = case['expected']
    near = lambda target, absolute=False: target is not None and any(
        abs((abs(n) if absolute else n) - target) <= max(0.006, abs(target) * 0.006) for n in found)
    return {'signed_mean': near(expected['mean_difference']),
            'largest_magnitude': near(expected['largest_abs_difference'], absolute=True),
            'largest_time': any(any(abs(n - t) <= 0.051 for n in found) for t in expected['largest_at']),
            'both_batches': case['left'] in reply and case['right'] in reply}


def score_attempt(case, turn, results, delivery, decoy):
    checks = [{'result_id': result.get('id'), 'checks': comparison_checks(case, result, delivery, decoy)}
              for result in results if result.get('task', {}).get('operation') == 'compare']
    computed = any(all(item['checks'].values()) for item in checks)
    coverage = reply_coverage(case, turn.get('reply') or '')
    objective = turn.get('status') == 'completed' and computed and all(coverage.values())
    return {'objective_pass': objective, 'correct_computed_result': computed,
            'task_completion_pass': turn.get('status') == 'completed' and computed,
            'objective_reply_coverage_pass': all(coverage.values()), 'reply_figure_coverage': coverage,
            'computed_checks': checks, 'manual_wording_review_required': True,
            'scope': 'Correct saved calculation plus necessary signed reply figures and batch names; '
                     'not a semantic judgment of all claims or scientific reasoning.'}


def distribution(values):
    if not values:
        return {'n': 0, 'mean': None, 'median': None, 'p90': None, 'min': None, 'max': None}
    ordered = sorted(values)
    return {'n': len(values), 'mean': round(statistics.mean(values), 3), 'median': round(statistics.median(values), 3),
            'p90': round(ordered[max(0, math.ceil(.9 * len(values)) - 1)], 3),
            'min': round(min(values), 3), 'max': round(max(values), 3)}


def summarize(rows):
    timed = [r for r in rows if 'seconds' in r and not r.get('interrupted_by_sleep')]
    successful = lambda r: bool(r.get('score', {}).get('objective_pass'))
    return {'attempts': len(rows), 'statuses': dict(Counter(r['status'] for r in rows)),
            'objective_passes': sum(successful(r) for r in rows),
            'correct_computed_results': sum(bool(r.get('score', {}).get('correct_computed_result')) for r in rows),
            'all_reply_figures': sum(bool(r.get('score', {}).get('reply_figure_coverage'))
                and all(r['score']['reply_figure_coverage'].values()) for r in rows),
            'all_attempt_seconds': distribution([r['seconds'] for r in timed]),
            'successful_seconds': distribution([r['seconds'] for r in timed if successful(r)]),
            'unsuccessful_seconds': distribution([r['seconds'] for r in timed if not successful(r)]),
            'completed_seconds': distribution([r['seconds'] for r in timed if r['status'] == 'completed']),
            'failed_turn_seconds': distribution([r['seconds'] for r in timed if r['status'] != 'completed']),
            'sleep_interrupted_timings_excluded': sum(bool(r.get('interrupted_by_sleep')) for r in rows)}


def cases(world):
    result = []
    for base in live.cases(world):
        ref = trial.reference(world['keys'][base['package']])
        case = {**base, 'unit': ref['units'][base['parameter']],
                'conflict_expected': any(c[1] == base['parameter'] and c[0] in (base['left'], base['right'])
                                         for c in ref['conflicts'])}
        pair = f"{case['left']} and {case['right']}"
        details = (f"Use exact matching elapsed sample times and define differences as {case['right']} minus {case['left']}. "
                   "Report the mean signed difference, largest absolute difference, its elapsed time in hours, and name both batches. "
                   "Include the deliveries still in review and state their provisional status.")
        for kind, text in (
            ('question', f"For {case['spoken']} between {pair}, what are the mean signed difference and the largest absolute difference, and when does the largest occur? "),
            ('task', f"Create a saved comparison of {case['spoken']} between {pair} and summarize the numerical result. "),
        ):
            result.append({**case, 'id': base['id'] + ':' + kind, 'kind': kind, 'prompt': text + details})
    return result


def host_case(world, case):
    p, ctx, deliveries, decoy = world['new_platform']()
    try:
        delivery = deliveries[case['package']]
        result = p.workspace_tasks.execute(ctx, {'operation': 'compare', 'site_id': trial.SITE,
            'dataset_ids': [delivery['id']], 'batches': [case['left'], case['right']],
            'parameter': case['parameter'], 'include_unverified': True})
        result = p.workspace_tasks.get(ctx, result['id'])
        checks = comparison_checks(case, result, delivery, decoy)
        return {'id': case['id'], 'status': 'host_checked', 'host_pass': all(checks.values()),
                'computed_checks': checks, 'result': result}
    finally:
        p.store.release_connections()


def live_attempt(world, case, repeat, settings, budget, deadline):
    from benchmarks.agent_pilot.runner import RecordedProvider
    ident = case['id'].replace(':', '--') + f'--repeat-{repeat}'
    row = {'id': ident, 'case': case['id'], 'case_id': case['id'], 'kind': case['kind'], 'package': case['package'],
           'repeat': repeat, 'prompt': case['prompt'], 'status': 'error', 'setup_excluded': True}
    provider = RecordedProvider(settings, budget, ident, deadline)
    p = None
    started = wall = None
    try:
        p, ctx, deliveries, decoy = world['new_platform'](providers={'modal': provider}, allow_unqualified=True)
        p.gateway.max_retries = 0
        thread = p.engineering_conversations.create(ctx, {'site_id': trial.SITE})
        wall, started = time.time(), time.perf_counter()
        queued = p.engineering_conversations.enqueue(ctx, thread['id'], {
            'text': case['prompt'], 'expected_revision': thread['revision'], 'include_unverified': True})
        p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
        turn = p.engineering_conversations.get(ctx, thread['id'])['turns'][-1]
        row.update(seconds=time.perf_counter() - started, wall_clock_seconds=time.time() - wall,
                   started_at=datetime.fromtimestamp(wall, timezone.utc).isoformat(), status=turn['status'], turn=turn)
        # Persisted artifacts are fetched AFTER the measured completed-turn fetch.
        results = [p.workspace_tasks.get(ctx, record.id) for record in p.store.read().list(trial.TENANT, 'workspace_task_result')]
        row.update(results=results, score=score_attempt(case, turn, results, deliveries[case['package']], decoy))
    except Exception as exc:
        row.update(error_type=type(exc).__name__, error=str(exc)[:500])
    finally:
        if started is not None and 'seconds' not in row:
            row.update(seconds=time.perf_counter() - started, wall_clock_seconds=time.time() - wall,
                       started_at=datetime.fromtimestamp(wall, timezone.utc).isoformat())
        if started is not None:
            row['interrupted_by_sleep'] = abs(row['seconds'] - row['wall_clock_seconds']) > 2.0
            row['completion_seconds'] = row['seconds']
            row['sleep_timing_excluded'] = row['interrupted_by_sleep']
        row['success'] = bool(row.get('score', {}).get('objective_pass'))
        row['outcome'] = ('correct' if row['success'] else 'incorrect' if row['status'] == 'completed' else 'error')
        row['provider_requests'] = provider.posts
        if p is not None:
            p.store.release_connections()
    return row


def settings_for_live():
    from src.lifesci.envfile import parse_env
    # Explicit inference-only allowlist. No configured DB, project, identity, or customer data is loaded.
    allowed = {k for k in live.MODEL_SETTINGS if k.startswith(('MODAL_', 'BIODEMO_MODAL_', 'LIFESCI_LLM_'))}
    allowed.update(('MODAL_COMPLETION_JSON', 'MODAL_COMPLETION_REASONING_EFFORT'))
    settings = {}
    for path in (BACKEND / 'deploy/aws/production.env', BACKEND / '.env.local'):
        if path.is_file():
            settings.update({k: v for k, v in parse_env(path.read_text()).items() if k in allowed and v})
    settings.update({k: v for k, v in os.environ.items() if k in allowed and v})
    return settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--budget-usd', type=float, default=4)
    parser.add_argument('--max-requests', type=int, default=180)
    parser.add_argument('--max-seconds', type=int, default=2700)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('use a new output directory; earlier attempts are preserved')
    if not 1 <= args.repeats <= 3 or not 1 <= args.workers <= 3 or not 0 < args.budget_usd <= 4 or not 1 <= args.max_requests <= 180:
        parser.error('limits: repeats 1–3, workers 1–3, estimated budget <= $4, requests <= 180')
    settings = settings_for_live() if args.execute else {}
    if args.execute:
        from src.lifesci.gateway.providers import modal_settings
        token, endpoint = modal_settings(settings)
        if not token or not endpoint:
            parser.error('inference endpoint and token must be configured; no calls made')
    os.environ.clear()
    os.environ.update({k: '' for k in trial.ISOLATED})
    os.environ.update(LIFESCI_DECISION_ADAPTER='off', LIFESCI_TENANTS=trial.TENANT)
    args.output.mkdir(parents=True)
    from benchmarks.agent_pilot.runner import CampaignBudget, MODEL, configure_agent
    from src.lifesci.process_engineering import tool_loop
    budget = CampaignBudget(args.budget_usd, args.max_requests, receipt_dir=args.output / 'requests')
    deadline = time.monotonic() + args.max_seconds
    with tempfile.TemporaryDirectory(prefix='answer-evaluation-') as temporary:
        world = trial.prepare(Path(temporary))
        os.environ.update(ASSISTANT_LOOP='tools', ASSISTANT_DIRECT_ROUTE='off')
        if args.execute:
            configure_agent()
        selected = cases(world)
        sources = [Path(__file__), BACKEND / 'benchmarks/workflow_trial/run.py', BACKEND / 'benchmarks/workflow_trial/live.py',
                   BACKEND / 'benchmarks/agent_pilot/runner.py', *sorted((BACKEND / 'src/lifesci').rglob('*.py'))]
        protocol = {'schema': 'answer-evaluation-v1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'live_agent' if args.execute else 'host_preflight', 'model': MODEL if args.execute else None,
            'cases': selected, 'repeats': args.repeats if args.execute else 1, 'workers': args.workers if args.execute else 1,
            'planned_attempts': len(selected) * args.repeats if args.execute else len(selected) // 2,
            'estimated_budget_usd': args.budget_usd if args.execute else 0,
            'max_provider_requests': args.max_requests if args.execute else 0,
            'production_limits': {k: getattr(tool_loop, k) for k in ('MAX_MODEL_CALLS', 'MAX_TOOL_CALLS', 'MAX_SECONDS', 'CALL_SECONDS')},
            'timing': 'Local application-service caller: immediately before enqueue through run_turn and final get. '
                      'Includes authorization, model/tool calls, computation, persistence and completed-turn retrieval. '
                      'Excludes fixture ingestion, fresh platform/thread construction, post-turn scoring, browser/network/remote queue delay.',
            'scoring': 'Saved comparison checked against independent fixture answer keys with 0.5% relative tolerance; '
                       'reply figures checked with signed mean, 0.6% relative / 0.006 absolute tolerance, time +/- 0.051 h, and both batch names. '
                       'A pass requires completed turn, correct computed artifact, and all reply figures. Semantic wording still needs review.',
            'source_hashes': {str(p.relative_to(BACKEND)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'answer_key_hashes': {package: hashlib.sha256((trial.DEMO / package / 'evaluation/answer_key.json').read_bytes()).hexdigest()
                                  for package in trial.TARGETS},
            'preparation': world['preparation'],
            'limitations': ['Authored tasks on three public CHO deliveries; not a general-purpose external benchmark.',
                'Six evidence cases with two paraphrased requests each; repeats are correlated, not independent questions.',
                'Unchanged production ToolLoop forced on, direct deterministic route off, gateway retries disabled.',
                'Fresh local platform per attempt, allow_unqualified model route, public provisional evidence only.',
                'No scientific-cause, regulatory validation, production latency, or time-savings claim.',
                'All final replies require semantic review; numeric presence alone is not correctness.',
                'Cost is token-rate estimate; hosted compute invoices are not reconciled.']}
        write(args.output / 'protocol.json', protocol)  # frozen BEFORE any inference
        rows = []

        def checkpoint(row):
            rows.append(row)
            write(args.output / (row['id'].replace(':', '--') + '.json'), row)
            report = {'protocol': protocol, 'rows': sorted(rows, key=lambda r: r['id']), 'budget': budget.snapshot(),
                      'summary': summarize(rows), 'complete': len(rows) == protocol['planned_attempts'],
                      'by_kind': {kind: summarize([r for r in rows if r.get('kind') == kind]) for kind in ('question', 'task')}}
            if not args.execute:
                report['host_passes'] = sum(r['host_pass'] for r in rows)
            write(args.output / 'report.json', report)
            print(json.dumps({'id': row['id'], 'status': row['status'], 'seconds': round(row.get('seconds', 0), 3),
                              'objective_pass': row.get('score', {}).get('objective_pass'), 'host_pass': row.get('host_pass'),
                              'provider_requests': len(row.get('provider_requests', []))}), flush=True)

        try:
            if args.execute:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    pending = [pool.submit(live_attempt, world, case, repeat, settings, budget, deadline)
                               for repeat in range(1, args.repeats + 1) for case in selected]
                    for future in as_completed(pending):
                        checkpoint(future.result())
            else:
                for case in selected[::2]:
                    checkpoint(host_case(world, case))
        finally:
            world['platform'].store.release_connections()
        print(json.dumps({'summary': summarize(rows), 'requests': budget.snapshot()['requests'],
                          'accounted_usd': budget.snapshot()['accounted_usd']}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
