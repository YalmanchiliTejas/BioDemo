"""The two live evaluations at each reasoning level, side by side. Reads only the saved reports."""
import json
import statistics
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
LEVELS = ('max-default', 'high', 'low')


def stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return '-'
    return f"mean {statistics.mean(values):.1f} · median {statistics.median(values):.1f} · slowest {max(values):.1f}"


summary = {}
print('== Numerical questions and saved comparisons (objective checks against answer keys)')
for level in LEVELS:
    path = OUT / f'answers-{level}' / 'report.json'
    if not path.exists():
        print(f'  {level}: no report')
        continue
    report = json.loads(path.read_text())
    rows = report['rows']
    requests = [q for r in rows for q in r.get('provider_requests', [])]
    usage = [q.get('usage') or {} for q in requests]
    out_tokens = sum(u.get('completion_tokens') or 0 for u in usage)
    in_tokens = sum(u.get('prompt_tokens') or 0 for u in usage)
    by_kind = {k: (sum(bool(r.get('score', {}).get('objective_pass')) for r in rows if r['kind'] == k), sum(r['kind'] == k for r in rows))
               for k in ('question', 'task')}
    passes = sum(bool(r.get('score', {}).get('objective_pass')) for r in rows)
    seconds = [r.get('seconds') for r in rows]
    errors = [(r['id'], r['status'], r.get('error_type')) for r in rows if r['status'] != 'completed']
    summary[f'answers-{level}'] = {'attempts': len(rows), 'objective_passes': passes, 'by_kind': by_kind,
                                   'mean_seconds': round(statistics.mean(seconds), 1), 'median_seconds': round(statistics.median(seconds), 1),
                                   'slowest_seconds': round(max(seconds), 1), 'model_requests': len(requests), 'output_tokens': out_tokens,
                                   'input_tokens': in_tokens, 'estimated_usd': round(report['budget']['accounted_usd'], 3),
                                   'failed_requests': sum(q.get('status') != 'returned' for q in requests), 'not_completed': errors,
                                   'effort_recorded': report['protocol'].get('assistant_reasoning_effort')}
    print(f"  {level:12s} pass {passes}/{len(rows)} (question {by_kind['question'][0]}/{by_kind['question'][1]}, task {by_kind['task'][0]}/{by_kind['task'][1]}) | seconds {stats(seconds)}"
          f" | requests {len(requests)} | output tokens {out_tokens} | ${report['budget']['accounted_usd']:.2f} | not completed {errors} | effort: {report['protocol'].get('assistant_reasoning_effort')}")
    if '-v' in sys.argv:
        for r in sorted(rows, key=lambda r: r['id']):
            s = r.get('score', {})
            print(f"      {r['id']:55s} {r['status']:18s} {r.get('seconds', 0):6.1f}s pass={s.get('objective_pass')} failed_checks={[k for k, v in (s.get('checks') or {}).items() if v is False][:6]}")

print('\n== Open questions through the assistant (reference figures from answer keys)')
for level in LEVELS:
    path = OUT / f'assistant-{level}' / 'report.json'
    if not path.exists():
        print(f'  {level}: no report')
        continue
    report = json.loads(path.read_text())
    rows = report['assistant']['rows']
    for arm in dict.fromkeys(r['arm'] for r in rows):
        for kind in ('routine', 'question'):
            group = [r for r in rows if r['arm'] == arm and r['kind'] == kind]
            if not group:
                continue
            modelled = [r for r in group if (r.get('timing') or {}).get('model_calls')]
            answered = [r for r in group if r.get('facts')]
            full = sum(all(r['facts'].values()) for r in answered)
            seconds = [r.get('seconds') for r in group if not r.get('interrupted_by_sleep')]
            key = f'assistant-{level}:{arm}:{kind}'
            summary[key] = {'requests': len(group), 'answered': len(answered), 'all_reference_figures': full,
                            'statuses': sorted({r['status'] for r in group}), 'mean_seconds': round(statistics.mean(seconds), 1) if seconds else None,
                            'slowest_seconds': round(max(seconds), 1) if seconds else None,
                            'model_calls': sum((r.get('timing') or {}).get('model_calls') or 0 for r in group),
                            'output_tokens': sum(r.get('output_tokens') or 0 for r in group), 'input_tokens': sum(r.get('input_tokens') or 0 for r in group),
                            'effort_recorded': report.get('assistant_reasoning_effort')}
            print(f"  {level:12s} {arm:16s} {kind:9s} answered {len(answered)}/{len(group)} all figures {full}/{len(group)} | seconds {stats(seconds)}"
                  f" | model calls {summary[key]['model_calls']} | output tokens {summary[key]['output_tokens']} | statuses {summary[key]['statuses']}")
            if '-v' in sys.argv:
                for r in group:
                    print(f"      {r['case']:34s} {r['status']:18s} {r.get('seconds', 0):6.1f}s calls={(r.get('timing') or {}).get('model_calls')} out={r.get('output_tokens')} facts={r.get('facts')} issues={str(r.get('issues') or r.get('error') or '')[:120]}")
if '--save' in sys.argv:
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('\nsaved summary.json')
