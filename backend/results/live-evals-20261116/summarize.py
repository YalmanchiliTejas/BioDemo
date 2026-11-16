"""Summarize retained live receipts; never alter outputs or the frozen grader."""
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def stats(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "mean_seconds": None, "median_seconds": None,
                "p95_nearest_rank_seconds": None, "sum_seconds": 0}
    return {"count": len(values), "mean_seconds": statistics.mean(values),
            "median_seconds": statistics.median(values),
            "p95_nearest_rank_seconds": values[math.ceil(.95 * len(values)) - 1],
            "sum_seconds": sum(values)}


def ledger(suite):
    rows = [json.loads(line) for line in
            (BASE / suite / 'cost/modal-admission.jsonl').read_text().splitlines()]
    reserved = {x['ordinal']: x for x in rows if x['event'] == 'reserved'}
    settled = {x['ordinal']: x for x in rows if x['event'] == 'settled'}
    finished = {x['ordinal']: x for x in rows if x['event'] == 'finished'}
    unknown = sorted(set(reserved) - set(settled))
    known_cost = sum(x['conservative_cost_usd'] for x in settled.values())
    unknown_hold = sum(reserved[i]['reserved_usd'] for i in unknown)
    return {
        'forwarded_requests': len(reserved), 'finished_requests': len(finished),
        'usage_known_requests': len(settled), 'usage_unknown_ordinals': unknown,
        'unfinished_receipt_ordinals': sorted(set(reserved) - set(finished)),
        'event_counts': dict(Counter(x['event'] for x in rows)),
        'observed_response_models': sorted({m for x in settled.values()
                                            for m in x['response_models']}),
        'known_usage_estimated_usd': known_cost,
        'unknown_usage_reservation_usd': unknown_hold,
        'conservative_held_usd': known_cost + unknown_hold,
        'prompt_tokens_including_cached': sum(x['prompt_tokens'] for x in settled.values()),
        'cached_prompt_tokens': sum(x['cached_prompt_tokens'] for x in settled.values()),
        'completion_tokens': sum(x['completion_tokens'] for x in settled.values()),
        'forwarded_http_request_latency': stats([x['elapsed_seconds'] for x in finished.values()]),
        'billing_note': 'Provider token counts at published rates; not an invoice. Unknown usage retains the full reservation. Request latency excludes waiting for admission.',
    }


def main():
    source = BASE / 'native/agent/results.json'
    result = read(source)
    records = result['records']
    families = defaultdict(list)
    tool_seconds = defaultdict(list)
    gateway_seconds = []
    failures = []
    for row in records:
        families[row['family']].append(row)
        if not row['verdict']['passed']:
            ref = read(BASE / 'native/frozen/reference' / (row['case_id'] + '.json'))
            assessment = row.get('assessment') or {}
            failures.append({
                'case_id': row['case_id'], 'family': row['family'],
                'turn_status': row['trace']['turn_status'],
                'failed_checks': [k for k, v in row['verdict']['checks'].items() if not v],
                'required_missing': ref.get('required_missing'),
                'recorded_missing_inputs': assessment.get('missing_inputs'),
                'elapsed_seconds': row['elapsed_seconds'],
                'artifact': f"native/agent/{row['case_id']}/result.json",
            })
        for step in row['trace'].get('tool_steps', []):
            start, end = step.get('started_at'), step.get('ended_at')
            if start and end:
                seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
                tool_seconds[step['task_kind']].append(seconds)
        for run in row['trace'].get('gateway_runs', []):
            gateway_seconds.extend(a['latency_ms'] / 1000 for a in run.get('attempts', [])
                                   if isinstance(a.get('latency_ms'), (float, int)))
    passed = [r for r in records if r['verdict']['passed']]
    fully_finished_passed = [r for r in passed if r['trace']['turn_status'] == 'completed']
    planned = len(list((BASE / 'native/frozen/public').glob('*.json')))
    campaigns = {name: ledger(name) for name in ('native', 'cho')}
    receipts = [read(f) for f in (BASE / 'native/agent/requests').glob('*.json')]
    responding_cases = {r['episode'] for r in receipts if r['status'] == 'returned'}
    summary = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'source_results_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'native': {
            'planned_cases': planned, 'recorded_outcomes': len(records),
            'strict_passes': len(passed), 'strict_pass_rate_of_planned': len(passed) / planned,
            'strict_passes_with_completed_turn': len(fully_finished_passed),
            'strict_passes_without_completed_turn': len(passed) - len(fully_finished_passed),
            'assessment_recorded_count': sum(r['assessment'] is not None for r in records),
            'cases_with_returned_model_response': len(responding_cases),
            'provider_client_receipt_statuses': dict(Counter(r['status'] for r in receipts)),
            'turn_status_counts': dict(Counter(r['trace']['turn_status'] for r in records)),
            'all_recorded_episode_time': stats([r['elapsed_seconds'] for r in records]),
            'strict_passing_episode_time': stats([r['elapsed_seconds'] for r in passed]),
            'strict_passing_completed_turn_time': stats([r['elapsed_seconds'] for r in fully_finished_passed]),
            'families': {name: {'cases': len(rows), 'passed': sum(r['verdict']['passed'] for r in rows),
                                'episode_time': stats([r['elapsed_seconds'] for r in rows])}
                         for name, rows in sorted(families.items())},
            'solver_calls': sum(r['solver_calls'] for r in records),
            'tool_time_by_kind': {name: stats(values) for name, values in sorted(tool_seconds.items())},
            'gateway_attempt_time': stats(gateway_seconds),
            'failure_details': failures,
            'timing_scope': 'From enqueue through agent turn, tools and grading after seeding. Includes admission waits and timeouts. Passing-case mean is conditional, not correction time or human resolution time. Concurrent sums are not wall time.',
            'score_scope': 'Frozen deterministic grader, unchanged. Authored synthetic primary-drying cases using actual model calls and the pinned native solver. Research connector; not plant or full quality-workflow validation.',
        },
        'campaigns': campaigns,
        'total_known_usage_estimated_usd': sum(c['known_usage_estimated_usd'] for c in campaigns.values()),
        'total_unknown_usage_reservation_usd': sum(c['unknown_usage_reservation_usd'] for c in campaigns.values()),
        'total_conservative_held_usd': sum(c['conservative_held_usd'] for c in campaigns.values()),
        'cho': {'status': 'incomplete', 'comparison_created': False,
                'cause': 'Request 74 logged HTTP 200 and BrokenPipeError without a usage receipt. Its retained $2.25 reservation prevented admission of another request within the $4 cap. The local gate returned 402; this does not establish a Modal account balance problem.',
                'accuracy': None, 'successful_completion_time_seconds': None,
                'retained_artifacts': '../../runs/cho-comparison'},
        'restored_regression': {'passed': 55, 'failed': 1,
                                'remaining': 'ChoCaseTests.test_recorded_prime_pilot_is_wired',
                                'log': 'logs/restored-tests-after-live.log'},
    }
    (BASE / 'metrics.json').write_text(json.dumps(summary, indent=2) + '\n')
    n = summary['native']
    report = [
        '# Live evaluations — 16 November 2026', '',
        '**Real GLM-5.3 calls were made to the configured Modal endpoint. This batch did not demonstrate reliable end-to-end completion.**', '',
        '| Measure | Recorded result |', '|---|---:|',
        f"| Native cases planned / recorded | {planned} / {len(records)} |",
        f"| Cases receiving a model response | {len(responding_cases)} |",
        f"| Frozen-grader passes | {len(passed)}/{planned} |",
        f"| Passed and finished the assistant turn | {len(fully_finished_passed)}/{planned} |",
        f"| Mean time, passed and finished | {n['strict_passing_completed_turn_time']['mean_seconds']:.1f} s |",
        f"| Mean time, all recorded outcomes including failures | {n['all_recorded_episode_time']['mean_seconds']:.1f} s |",
        '| CHO investigation | Incomplete; no final report |',
        '| Affected regression tests after restoration | 55 passed, 1 failed |', '',
        '## What was exercised', '',
        '- **Lyo:** 24 authored synthetic cases, six each for calculations, recipe selection, missing inputs, and model scope. These use the existing application tool loop and real pinned LyoPRONTO solver through a research connector. They measure tool use, not predictive accuracy on plant data or the complete deviation/QA workflow.',
        '- **CHO:** One investigation over all 12 original public cultivation workbooks, using the existing Prime SDK harness. It has no causal ground-truth score. Ingestion and analysis began, but the investigation did not produce a final report.',
        '- The separate scripted preflight used zero inference requests and is excluded from all live results.', '',
        '## Native outcomes', '',
        '| Family | Strict passes / cases | Mean episode seconds |', '|---|---:|---:|',
    ]
    report += [f"| {name} | {row['passed']}/{row['cases']} | {row['episode_time']['mean_seconds']:.1f} |"
               for name, row in n['families'].items()]
    report += [
        '', 'The frozen scores are unchanged. Inspection found three exact-string grading rejections: the agent explicitly named the required missing parameter and appended an explanation, which the schema permits but the grader rejects. One of those turns also timed out. These are documented separately rather than silently rescored.', '',
        'Two completed answers contain numerical errors: one saved a whole-batch rate of **3.24067 kg/h instead of 0.06538 kg/h**; another selected the correct recipe but reported incorrect thermal and equipment-capacity margins. One other case saved a correctly graded assessment, then timed out before completing its reply; it is excluded from the finished-success count.', '',
        'Later cases timed out waiting for admission behind an unresolved provider response. The batch success fraction therefore mixes answer quality, application completion, and the evaluation budget gate. It must not be described as general model accuracy.', '',
        'See [case-by-case results](native/agent/results.json), [failure inspection](failure-review.json), and [timing and cost metrics](metrics.json).', '',
        '## Timing', '',
        'Episode time starts after workspace seeding and includes the assistant turn, tools, admission waits, and grading. It excludes setup and runtime cleanup. The passing-case mean is conditional on success; failed tasks do not have a successful completion time. No human review or correction time was measured. Concurrent request/tool totals are not wall-clock completion time.', '',
        '## Inference and budget', '',
        '| Campaign | Forwarded requests | Usage receipts | Known-usage estimate | Unknown-usage hold |',
        '|---|---:|---:|---:|---:|',
    ]
    report += [f"| {name} | {c['forwarded_requests']} | {c['usage_known_requests']} | ${c['known_usage_estimated_usd']:.4f} | ${c['unknown_usage_reservation_usd']:.2f} |"
               for name, c in campaigns.items()]
    report += [
        '', f"Known usage totals **${summary['total_known_usage_estimated_usd']:.4f}**; including unknown-usage reservations, the conservative total is **${summary['total_conservative_held_usd']:.4f}**, within the $10 first-batch cap. These are token-rate estimates and reservations, not an invoice. [Published pricing](https://modal.com/library/zai/glm-5-3) was checked before running.", '',
        'The CHO gate recorded request 74 as HTTP 200 followed by `BrokenPipeError`, without usage counters. It retained $2.25 and rejected further dispatch under the $4 campaign cap. The SDK described the resulting local 402 as insufficient balance; that does **not** establish a Modal account billing problem. The failed attempt is preserved in [CHO artifacts](../../runs/cho-comparison/). No successful pilot fixture was fabricated and no failed case was silently rerun.', '',
        '## Restored files and checks', '',
        '- Restored 48 publisher-aligned CHO CSVs and the raw dataset archive/workbooks using the repository artifact tool with checksum verification.',
        '- Restored the external LyoPRONTO checkout at commit `c6a9225a9e551ae4e7c11c1ef056b67c6204afbd` in `/private/tmp/lyohub-rerun-source`.',
        '- Regenerated the existing static benchmark report from recorded artifacts; its previous version is retained in `prior-static-report/`.',
        '- Reran `test_lyopronto_native.py`, `test_lyohub_study.py`, and `test_case_comparison.py`: **55 passed, 1 failed**. The remaining assertion requires the missing completed CHO pilot. [Test log](logs/restored-tests-after-live.log). The full backend suite was not rerun.',
        '- Production databases were disabled. There were no manufacturing-control actions, official quality approvals, commits, pushes, or deployments.', '',
        '## Reproduction and evidence', '',
        'The [driver](execute.py), [outer protocol](protocol.json), [frozen native protocol](native/frozen/protocol.json), provider admission ledgers, per-case SQLite stores, model receipts, and solver outputs are retained here. The inner native protocol allows $10; the outer gate applied the stricter $6 native / $4 CHO split. Repeating a paid run requires a fresh output directory and an explicit new budget; the existing artifacts must not be overwritten.', '',
    ]
    (BASE / 'report.md').write_text('\n'.join(report))
    print(json.dumps({
        'native_outcomes': len(records), 'native_strict_passes': len(passed),
        'mean_passing_seconds': summary['native']['strict_passing_episode_time']['mean_seconds'],
        'known_usage_estimated_usd': summary['total_known_usage_estimated_usd'],
        'conservative_held_usd': summary['total_conservative_held_usd'],
    }, indent=2))


if __name__ == '__main__':
    main()
