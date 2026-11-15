"""Authored recurring-work probes through the actual assistant and routine services.

Run with -I. Default is a local host check with supplied routine definitions;
--execute measures the configured GLM's ability to create those definitions.
No judge model; stored task fields and lifecycle receipts are the reference.
These are our cases, not an established benchmark or deployed-system validation.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from statistics import fmean, median

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
from benchmarks.skills.worlds import ISOLATED

TENANT, OWNER, SITE = 'recurring-evaluation', 'benchmark-owner', 'BENCH-SITE'
CASES = [
    {'id': 'hourly', 'name': 'Hourly case list', 'every_minutes': 60, 'triggers': [],
     'prompt': 'Save a routine named Hourly case list that lists case records at BENCH-SITE every hour, for at most 2 runs. Use only the schedule, with no event triggers. Leave it as a draft for me to activate.'},
    {'id': 'quarter-hour', 'name': 'Quarter-hour case list', 'every_minutes': 15, 'triggers': [],
     'prompt': 'Save a routine named Quarter-hour case list that lists case records at BENCH-SITE every 15 minutes, for at most 2 runs. Use only the schedule, with no event triggers. Leave it as a draft for me to activate.'},
    {'id': 'daily-interval', 'name': 'Daily case list', 'every_minutes': 1440, 'triggers': [],
     'prompt': 'Save a routine named Daily case list that lists case records at BENCH-SITE every 24 hours, for at most 2 runs. Use only the interval, with no event triggers. Leave it as a draft for me to activate.'},
    {'id': 'case-event', 'name': 'Changed case list', 'every_minutes': None, 'triggers': ['case'],
     'prompt': 'Save a routine named Changed case list that lists case records at BENCH-SITE when case records change, for at most 2 runs. Use case events only, with no periodic schedule. Leave it as a draft for me to activate.'},
]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')


def summarize_attempts(rows, repeats):
    def distribution(items):
        times = sorted(r['agent_seconds'] for r in items if r.get('agent_seconds') is not None
                       and not r.get('timing_interrupted'))
        return {'n': len(times), 'mean': fmean(times) if times else None,
                'median': median(times) if times else None,
                'p95': times[math.ceil(0.95 * len(times)) - 1] if times else None}

    by_case = {case: [r for r in rows if r['case_id'] == case] for case in {r['case_id'] for r in rows}}
    return {'attempts': len(rows), 'definition_passes': sum(bool(r.get('definition_pass')) for r in rows),
            'functional_passes': sum(bool(r.get('functional_pass')) for r in rows),
            'full_lifecycle_passes': sum(bool(r.get('lifecycle_pass')) for r in rows),
            'cases_correct_every_repeat': sum(len(group) == repeats and all(r.get('functional_pass') for r in group)
                                              for group in by_case.values()),
            'completion_seconds': {
                'all': distribution(rows),
                'correct': distribution([r for r in rows if r.get('functional_pass')]),
                'failed': distribution([r for r in rows if not r.get('functional_pass')])},
            'timings_set_aside': sum(bool(r.get('timing_interrupted')) for r in rows)}


def definition_checks(case, routines):
    checks = {'one_saved_routine': len(routines) == 1}
    if len(routines) != 1:
        return checks
    r = routines[0]
    checks.update(draft=r['status'] == 'draft', owner=r['owner_id'] == OWNER,
                  interval=r['every_minutes'] == case['every_minutes'],
                  triggers=sorted(r['triggers']) == sorted(case['triggers']), max_runs=r['max_runs'] == 2,
                  task=r['task']['operation'] == 'find_records', site=r['task']['site_id'] == SITE,
                  record_kinds=r['task']['kinds'] == ['case'], not_started=r['runs_admitted'] == 0,
                  requested_name=r['name'] == case['name'],
                  unfiltered_listing=not any(r['task'].get(k) for k in ('query', 'record_id', 'record_refs', 'dataset_ids', 'batches')),
                  first_page=r['task'].get('offset') == 0, default_page_capacity=r['task'].get('limit', 0) >= 50)
    return checks


def lifecycle(p, ctx, routine, case, reopen):
    """The test person explicitly activates; time is advanced by making an obligation due.

    Reopening SQLite models application reconstruction, not an OS/process crash.
    The actual runtime and stored task execute; no model response is supplied.
    """
    from src.lifesci.ids import iso, utc_now, parse_iso
    checks = {}
    rid = routine['id']
    p.runtime.tick()
    checks['draft_did_not_run'] = p.assistant_routines.get(ctx, rid)['runs_admitted'] == 0
    r = p.assistant_routines.activate(ctx, rid, expected_revision=routine['revision'], acknowledge_inference=True)
    p, ctx = reopen(p)
    checks['active_survives_reconstruction'] = p.assistant_routines.get(ctx, rid)['status'] == 'active'

    def wake(label):
        if case['every_minutes']:
            with p.store.transaction('benchmark-clock') as tx:
                m = tx.require(TENANT, 'mission', r['mission_id'])
                obligations = [{**o, 'due_at': iso(utc_now() - timedelta(minutes=1))} for o in m.state['obligations']]
                tx.put(TENANT, 'mission', m.id, {**m.state, 'obligations': obligations},
                       expected_revision=m.revision, action='evaluation_clock_advance')
        else:
            p.cases.add_timeline_event(ctx, 'SYNTHETIC-CASE', iso(utc_now()), 'Synthetic update ' + label)
        p.runtime.tick()

    wake('first')
    saved = p.assistant_routines.get(ctx, rid)
    checks['first_run_completed'] = len(saved['runs']) == 1 and saved['runs'][0]['status'] == 'completed'
    result = saved.get('latest_result') or {}
    checks['correct_record_returned'] = [x['id'] for x in result.get('data', {}).get('records', [])] == ['SYNTHETIC-CASE']
    if case['every_minutes']:
        ob = p.missions.get(ctx, r['mission_id'])['obligations'][0]
        checks['next_interval_preserved'] = ob['every_minutes'] == case['every_minutes'] and parse_iso(ob['due_at']) > utc_now()
    p.runtime.tick()
    checks['idle_did_not_duplicate'] = len(p.assistant_routines.get(ctx, rid)['runs']) == 1
    current = p.assistant_routines.get(ctx, rid)
    p.assistant_routines.pause(ctx, rid, expected_revision=current['revision'])
    p, ctx = reopen(p)
    checks['pause_survives_reconstruction'] = p.assistant_routines.get(ctx, rid)['status'] == 'paused'
    wake('while-paused')
    checks['paused_did_not_run'] = len(p.assistant_routines.get(ctx, rid)['runs']) == 1
    current = p.assistant_routines.get(ctx, rid)
    p.assistant_routines.activate(ctx, rid, expected_revision=current['revision'], acknowledge_inference=True)
    wake('resumed')
    resumed_runs = p.assistant_routines.get(ctx, rid)['runs']
    checks['second_run_completed'] = len(resumed_runs) == 2 and all(x['status'] == 'completed' for x in resumed_runs)
    wake('beyond-allowance')
    checks['allowance_stops_further_runs'] = len(p.assistant_routines.get(ctx, rid)['runs']) == 2
    return p, ctx, checks, p.assistant_routines.get(ctx, rid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--budget-usd', type=float, default=2.0, help='Estimated token-rate cap, not hosted billing.')
    parser.add_argument('--max-requests', type=int, default=24)
    args = parser.parse_args()
    if args.repeats < 1 or args.budget_usd <= 0 or args.max_requests < 1:
        parser.error('repeats, budget and max requests must be positive')
    if args.output.exists():
        parser.error('use a new output directory; earlier attempts are preserved')
    args.output.mkdir(parents=True)
    # Load only inference configuration, never the application/database environment.
    from src.lifesci.envfile import parse_env
    settings = {}
    if args.execute:
        # Same precedence as the existing agent-pilot runner; retain inference keys only.
        for path in (BACKEND / 'deploy/aws/production.env', BACKEND / '.env.local'):
            if path.is_file():
                settings.update({k: v for k, v in parse_env(path.read_text()).items()
                                 if k.startswith(('MODAL_', 'BIODEMO_MODAL_', 'LIFESCI_LLM_'))})
        settings.update({k: v for k, v in os.environ.items()
                         if k.startswith(('MODAL_', 'BIODEMO_MODAL_', 'LIFESCI_LLM_'))})
    if args.execute:
        from src.lifesci.gateway.providers import modal_settings
        token, endpoint = modal_settings(settings)
        if not token or not endpoint:
            parser.error('inference token and endpoint must both be configured; no model calls made')
    os.environ.clear()
    os.environ.update({k: '' for k in ISOLATED})
    os.environ.update(ASSISTANT_LOOP='tools', LIFESCI_DECISION_ADAPTER='off', LIFESCI_TENANTS=TENANT)
    from benchmarks.agent_pilot.runner import CampaignBudget, RecordedProvider, configure_agent, MODEL
    from src.lifesci.container import Platform
    from src.lifesci.store import RecordStore
    if args.execute:
        configure_agent()
    budget = CampaignBudget(args.budget_usd, args.max_requests, receipt_dir=args.output / 'requests')
    deadline = time.monotonic() + 3600
    protocol = {'schema': 'recurring-work-evaluation-v2', 'authorship': 'Our authored synthetic cases and deterministic scoring',
                'mode': 'live_agent' if args.execute else 'host_only_supplied_definitions', 'cases': CASES,
                'repeats': args.repeats,
                'model': MODEL if args.execute else None, 'estimated_budget_usd': args.budget_usd if args.execute else 0,
                'max_provider_requests': args.max_requests if args.execute else 0,
                'timing': 'agent_seconds measures enqueue through completed turn retrieval, excluding fixture setup, scoring and future lifecycle checks. '
                          'Failed attempts are timed too; repetitions use independent stores. Timings with wall/monotonic disagreement over 2 seconds are set aside.',
                'functional_pass': 'Correct saved draft and all lifecycle behavior checks; background memory inference is recorded separately in lifecycle_pass.',
                'limits': ['Four explicit requests, not general natural-language accuracy.',
                           'Host lifecycle checks are separate from live definition correctness.',
                           'SQLite reconstruction, not OS crash or deployed scheduler validation.',
                           'Worker tenant explicitly configured with LIFESCI_TENANTS; local due times advanced by the harness.',
                           'Relative intervals only, not time zones, DST or wall-clock recurrence.',
                           'No semantic judge; final wording requires review.',
                           'Token-rate estimates do not reconcile hosted compute billing.']}
    protocol['source_hashes'] = {str(p.relative_to(BACKEND)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [Path(__file__), BACKEND / 'src/lifesci/capabilities.py', BACKEND / 'src/lifesci/assistant_routines.py',
         BACKEND / 'src/lifesci/process_engineering/tool_loop.py', BACKEND / 'src/lifesci/process_engineering/conversation.py',
         BACKEND / 'src/lifesci/missions.py', BACKEND / 'src/lifesci/runtime.py', BACKEND / 'benchmarks/agent_pilot/runner.py']}
    write(args.output / 'protocol.json', protocol)
    rows = []
    cache = BACKEND / '.cache/skill-benchmarks/recurring' / args.output.name
    cache.mkdir(parents=True, exist_ok=False)
    for repeat, case in [(repeat, case) for repeat in range(1, args.repeats + 1) for case in CASES]:
        started = time.monotonic()
        attempt_id = case['id'] if args.repeats == 1 else f"{case['id']}-r{repeat}"
        provider = RecordedProvider(settings, budget, attempt_id, deadline) if args.execute else None
        db = cache / (attempt_id + '.sqlite')

        def build(old=None):
            if old:
                old.store.release_connections()
            p = Platform(RecordStore(str(db)), providers={'modal': provider} if provider else {}, allow_unqualified=args.execute)
            p.gateway.max_retries = 0
            return p, p.identity.context_for(TENANT, OWNER)

        p, ctx = build()
        p.identity.assign_role(TENANT, OWNER, 'msat', site_id=SITE)
        p.identity.assign_role(TENANT, 'benchmark-reviewer', 'qa_reviewer', site_id=SITE)
        ctx = p.identity.context_for(TENANT, OWNER)
        p.cases.open(ctx, 'SYNTHETIC-CASE', OWNER, 'benchmark-reviewer', SITE)
        row = {'id': attempt_id, 'case_id': case['id'], 'repeat': repeat, 'mode': protocol['mode'],
               'setup_seconds': round(time.monotonic() - started, 6)}
        try:
            if args.execute:
                thread = p.engineering_conversations.create(ctx, {'site_id': SITE})
                agent_started, wall_started = time.monotonic(), time.time()
                try:
                    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'text': case['prompt'], 'expected_revision': thread['revision']})
                    p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
                    turn = p.engineering_conversations.get(ctx, thread['id'])['turns'][-1]
                    row.update(turn=turn)
                finally:
                    row['agent_seconds'] = round(time.monotonic() - agent_started, 6)
                    row['agent_wall_seconds'] = round(time.time() - wall_started, 6)
                    row['timing_interrupted'] = abs(row['agent_wall_seconds'] - row['agent_seconds']) > 2.0
                    row['provider_requests'] = list(provider.posts)
            else:
                p.assistant_routines.create(ctx, {'name': case['name'], 'task': {'operation': 'find_records', 'site_id': SITE, 'kinds': ['case']},
                    'triggers': case['triggers'], 'every_minutes': case['every_minutes'], 'max_runs': 2})
            routines = p.assistant_routines.list(ctx)
            row['definition_checks'] = definition_checks(case, routines)
            row['definitions'] = routines
            row['definition_pass'] = all(row['definition_checks'].values())
            if args.execute:
                row['definition_pass'] &= row['turn']['status'] == 'completed'
            if row['definition_pass']:
                before = len(budget.records)
                model_runs_before = {r.id for r in p.store.read().list(TENANT, 'model_run')}
                lifecycle_started = time.monotonic()
                p, ctx, checks, saved = lifecycle(p, ctx, routines[0], case, build)
                row['lifecycle_seconds'] = round(time.monotonic() - lifecycle_started, 6)
                checks['no_background_inference'] = len(budget.records) == before
                background = [r.state for r in p.store.read().list(TENANT, 'model_run') if r.id not in model_runs_before]
                row.update(lifecycle_checks=checks, lifecycle_pass=all(checks.values()), final_routine=saved,
                           background_model_runs=[{k: r.get(k) for k in ('run_id', 'task_kind', 'prompt_version', 'status', 'started_at', 'finished_at')} for r in background],
                           lifecycle_behavior_pass=all(v for k, v in checks.items() if k != 'no_background_inference'))
            else:
                row['lifecycle_status'] = 'not_run_definition_failed'
        except Exception as exc:
            row.update(error_type=type(exc).__name__, error=str(exc)[:500])
        finally:
            p.store.release_connections()
        row['outcome'] = ('error' if 'error' in row or (args.execute and row.get('turn', {}).get('status') == 'agent_unavailable')
                          else 'correct' if row.get('definition_pass') and row.get('lifecycle_pass') else 'wrong_value')
        row['functional_pass'] = bool(row.get('definition_pass') and row.get('lifecycle_behavior_pass'))
        row['seconds'] = round(time.monotonic() - started, 3)
        rows.append(row)
        write(args.output / (attempt_id + '.json'), row)
        report = {'protocol': protocol, 'rows': rows, 'budget': budget.snapshot(), 'planned': len(CASES) * args.repeats,
                  'completed': len(rows), 'definition_passes': sum(r.get('definition_pass', False) for r in rows),
                  'lifecycle_passes': sum(r.get('lifecycle_pass', False) for r in rows),
                  'summary': summarize_attempts(rows, args.repeats),
                  'errors': sum(r['outcome'] == 'error' for r in rows)}
        write(args.output / 'report.json', report)
        print(json.dumps({k: row.get(k) for k in ('id', 'definition_pass', 'functional_pass', 'lifecycle_pass', 'error_type', 'agent_seconds', 'seconds')}), flush=True)
    return 0 if all(r.get('definition_pass') and r.get('lifecycle_pass') for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
