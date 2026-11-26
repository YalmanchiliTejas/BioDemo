"""Combine saved evaluation receipts without treating component timing as agent latency."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean, median


def distribution(values):
    ordered = sorted(v for v in values if v is not None)
    return {'n': len(ordered), 'mean': fmean(ordered) if ordered else None,
            'median': median(ordered) if ordered else None,
            'p95': ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None}


def group(rows):
    timed = [r for r in rows if not r.get('timing_excluded') and r.get('seconds') is not None]
    return {'attempts': len(rows), 'correct': sum(r['correct'] for r in rows),
            'correct_rate': sum(r['correct'] for r in rows) / len(rows) if rows else None,
            'all_seconds': distribution([r['seconds'] for r in timed]),
            'correct_seconds': distribution([r['seconds'] for r in timed if r['correct']]),
            'failed_seconds': distribution([r['seconds'] for r in timed if not r['correct']]),
            'timings_missing_or_excluded': len(rows) - len(timed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('answers', 'recurring', 'domain', 'decision', 'workflows', 'output', 'wording-review'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--recurring-review', type=Path)
    args = parser.parse_args()
    reports = {name: json.loads((getattr(args, name) / 'report.json').read_text())
               for name in ('answers', 'recurring', 'domain', 'decision', 'workflows')}
    answers, recurring = reports['answers'], reports['recurring']
    if not answers['complete'] or recurring['completed'] != recurring['planned']:
        parser.error('live campaigns are incomplete; retain partial receipts but do not publish a final summary')
    review = json.loads(args.wording_review.read_text())
    reviews = {r['id']: r for r in review['rows']}
    if not review['complete'] or set(reviews) != {r['id'] for r in answers['rows']}:
        parser.error('every live question/task reply must have a completed wording review')
    for row in answers['rows']:
        digest = hashlib.sha256((row.get('turn', {}).get('reply') or '').encode()).hexdigest()
        if not reviews[row['id']]['reviewed'] or reviews[row['id']]['reply_sha256'] != digest:
            parser.error('wording review does not match the saved reply: ' + row['id'])
    rows = [{'id': r['id'], 'area': 'questions' if r['kind'] == 'question' else 'comparison_tasks',
             'case_id': r['case_id'], 'repeat': r['repeat'], 'objective_correct': bool(r.get('score', {}).get('objective_pass')),
             'correct': bool(r.get('score', {}).get('objective_pass')) and not reviews[r['id']]['material_factual_failure'],
             'review_findings': reviews[r['id']]['findings'],
             'seconds': r.get('completion_seconds'), 'timing_excluded': r.get('sleep_timing_excluded', False)}
            for r in answers['rows']]
    rows += [{'id': r['id'], 'area': 'recurring_tasks', 'case_id': r['case_id'], 'repeat': r['repeat'],
              'correct': bool(r.get('functional_pass')), 'seconds': r.get('agent_seconds'),
              'objective_correct': bool(r.get('functional_pass')),
              'timing_excluded': r.get('timing_interrupted', False)} for r in recurring['rows']]
    live = {area: group([r for r in rows if r['area'] == area])
            for area in ('questions', 'comparison_tasks', 'recurring_tasks')}
    repeated = {}
    for area in live:
        selected = [r for r in rows if r['area'] == area]
        cases = sorted({r['case_id'] for r in selected})
        repeated[area] = [{'case_id': case, 'attempts': len([r for r in selected if r['case_id'] == case]),
                           'correct': sum(r['correct'] for r in selected if r['case_id'] == case)} for case in cases]
    domain = reports['domain']
    decision = reports['decision']
    workflows = reports['workflows']
    workflow_rows = workflows['task_rows']
    cost = {'glm_estimated_usd': sum(r['budget']['accounted_usd'] for r in (answers, recurring)),
            'glm_requests': sum(r['budget']['requests'] for r in (answers, recurring)),
            'glm_unknown_usage_requests': sum(r['budget']['unknown_usage_requests'] for r in (answers, recurring)),
            'decision_reported_usd': decision['decision_model']['cost_usd'],
            'provider_invoice_usd': None}
    provenance = {name: {'path': str(getattr(args, name) / 'report.json'),
                         'sha256': hashlib.sha256((getattr(args, name) / 'report.json').read_bytes()).hexdigest()}
                  for name in reports}
    provenance['wording_review'] = {'path': str(args.wording_review),
                                  'sha256': hashlib.sha256(args.wording_review.read_bytes()).hexdigest()}
    recurring_review = None
    if args.recurring_review:
        recurring_review = json.loads(args.recurring_review.read_text())
        if (recurring_review['source_report_sha256'] != provenance['recurring']['sha256']
                or recurring_review['summary']['replies_reviewed'] != recurring['completed']
                or recurring_review['summary']['hidden_wording_failures_among_original_functional_passes']):
            parser.error('recurring wording review is incomplete, mismatched or requires adjudicating additional failures')
        provenance['recurring_wording_review'] = {'path': str(args.recurring_review),
                                                'sha256': hashlib.sha256(args.recurring_review.read_bytes()).hexdigest()}
    summary = {'schema': 'agent-completion-evaluation-v1', 'live': live, 'combined': group(rows),
               'automatic_objective_correct': sum(r['objective_correct'] for r in rows),
               'material_reply_failures': review['material_factual_failures'],
               'recurring_wording_review': recurring_review['summary'] if recurring_review else None,
               'recurring_outcome_note': 'The original raw outcome field labels background inference wrong_value. Functional correctness uses unchanged definition_pass and lifecycle_behavior_pass fields; the saved snapshot preserves the executed runner.',
               'repeated_cases': repeated, 'live_rows': rows, 'sources': provenance, 'cost': cost,
               'recurring_full_lifecycle_passes': recurring['lifecycle_passes'],
               'recurring_background_model_runs': sum(len(r.get('background_model_runs', [])) for r in recurring['rows']),
               'recurring_failures': [
                   {'id': r['id'], 'failed_definition_checks': [k for k, v in r.get('definition_checks', {}).items() if not v],
                    'failed_lifecycle_behavior_checks': [k for k, v in r.get('lifecycle_checks', {}).items() if not v and k != 'no_background_inference'],
                    'saved_routines': len(r.get('definitions', [])),
                    'saved_run_limits': [routine['max_runs'] for routine in r.get('definitions', [])]}
                   for r in recurring['rows'] if not r.get('functional_pass')],
               'component_checks': {
                   'domain': {'attempts': len(domain['rows']), 'outcomes': domain['outcomes'], 'by_skill': domain['summary']},
                   'decision': {'attempts': len(decision['rows']), 'outcomes': decision['outcomes'],
                                'mean_seconds_per_20_request_batch': decision['decision_model']['mean_ms_per_request'] / 1000},
                   'workflows': {'attempts': len(workflow_rows), 'expected_behavior_matches': sum(r['outcome'] == 'passed' for r in workflow_rows),
                                 'status_counts': dict(Counter(r.get('task_status', 'not_a_task') for r in workflow_rows)),
                                 'all_seconds': distribution([r.get('request_seconds') for r in workflow_rows]),
                                 'uncached_seconds': distribution([r.get('request_seconds') for r in workflow_rows if not r.get('cache_hit')]),
                                 'cached_seconds': distribution([r.get('request_seconds') for r in workflow_rows if r.get('cache_hit')])}},
               'limits': [
                   'Authored evaluations: six CHO evidence cases with question/task forms, three repeats; four recurring prompts, five repeats. Repeats are correlated.',
                   'Question/task correctness requires the frozen objective checks plus no material factual error found in Codex review of each saved reply against its result. Automated figure coverage remains reported separately. This is development trace review, not independent scientific validation.',
                   'Known conflicting measurements must remain flagged; a correct needs-information result does not mean the conflict was resolved.',
                   'Recurring correctness means a correct saved draft plus behavior after explicit test-person activation. Local clocks are advanced; no production scheduler or elapsed-day validation.',
                   'Agent time spans enqueue through final turn retrieval, excluding fixture setup, scoring and subsequent lifecycle/memory work; browser and deployed queue delays are not measured.',
                   'Three answer workers overlap one recurring worker on the shared model endpoint; these are observed local campaign timings, not production guarantees.',
                   'Background memory inference is separated from functional correctness and included in the token cost.',
                   'BFCL V4, IBM paraphrase robustness and MuSiQue remain unrun; no established full-agent benchmark score is claimed.',
                   'Sandbox connectivity failures and the pre-inference cache-name collision are retained as infrastructure attempts, not substituted for live results.',
                   'Costs are token-rate estimates/reported decision costs, not reconciled hosted invoices.']}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fmt = lambda value: '—' if value is None else f'{value:.2f} s'
    names = {'questions': 'Answer numerical questions', 'comparison_tasks': 'Save and explain a comparison',
             'recurring_tasks': 'Set up recurring tasks'}
    lines = ['# Agent correctness and completion time', '',
             'Fresh live GLM-5.3 runs on the current product tool loop. Accuracy and latency use every planned attempt; failures remain in the denominator. Question/task replies were also reviewed against their saved results for material factual errors.', '',
             '| Capability | Correct after review / attempts | Mean, all attempts | Mean, correct | Mean, failed | p95, all |',
             '|---|---:|---:|---:|---:|---:|']
    for area, result in live.items():
        lines.append(f"| {names[area]} | {result['correct']}/{result['attempts']} ({result['correct_rate']:.1%}) | "
                     f"{fmt(result['all_seconds']['mean'])} | {fmt(result['correct_seconds']['mean'])} | "
                     f"{fmt(result['failed_seconds']['mean'])} | {fmt(result['all_seconds']['p95'])} |")
    combined = summary['combined']
    lines += ['', f"Combined correctness after review: **{combined['correct']}/{combined['attempts']} ({combined['correct_rate']:.1%})**. "
              f"Average completion time: **{fmt(combined['all_seconds']['mean'])}**; correct attempts: **{fmt(combined['correct_seconds']['mean'])}**.", '',
              f"The automatic objective checks passed {summary['automatic_objective_correct']}/{combined['attempts']}. "
              f"Review found material factual errors in {len(summary['material_reply_failures'])} replies; those attempts are counted as incorrect above.", '',
              'Timing starts immediately before submission to the local application service and ends after the completed turn is retrieved. Setup, evaluation scoring and future routine execution are outside that timer.', '',
              '## Correctness scope', '',
              summary['limits'][0], summary['limits'][1], summary['limits'][2], summary['limits'][3], '',
              '## Component checks — separate from agent completion', '',
              f"- Domain functions: {domain['outcomes'].get('correct', 0)}/{len(domain['rows'])} correct. These execute directly without the agent.",
              f"- Decision routing: {decision['outcomes'].get('correct', 0)}/{len(decision['rows'])} correct; "
              f"{decision['decision_model']['mean_ms_per_request'] / 1000:.3f} s per batch of 20. This is not individual question completion time.",
              f"- Direct workflows: {summary['component_checks']['workflows']['expected_behavior_matches']}/{len(workflow_rows)} matched expected behavior. "
              'Expected refusals and needs-information responses count as appropriate behavior, not completed manufacturing work.', '',
              '## Repeated cases', '', '| Capability | Case | Correct / repeats |', '|---|---|---:|']
    for area, cases in repeated.items():
        for case in cases:
            lines.append(f"| {names[area]} | {case['case_id']} | {case['correct']}/{case['attempts']} |")
    lines += ['', '## Errors found in reply review', '']
    for row in rows:
        if row['objective_correct'] and not row['correct']:
            lines.append(f"- {row['id']}: " + ' '.join(f['finding'] for f in row['review_findings'] if f.get('severity', '').startswith('material')))
    for row in summary['recurring_failures']:
        lines.append(f"- {row['id']}: failed {', '.join(row['failed_definition_checks'] + row['failed_lifecycle_behavior_checks'])}; "
                     f"saved {row['saved_routines']} routines with run limits {row['saved_run_limits']}.")
    lines += ['', '## Cost and background work', '',
              f"GLM: ${cost['glm_estimated_usd']:.4f} estimated across {cost['glm_requests']} provider calls; "
              f"decision routing: ${cost['decision_reported_usd']:.4f} reported. Hosted invoice cost is unknown.", '',
              f"Recurring functional success is separate from the no-background-inference check: "
              f"{recurring['lifecycle_passes']}/{recurring['completed']} passed the full lifecycle including that check; "
              f"{summary['recurring_background_model_runs']} background model runs were observed.", '',
              summary['recurring_outcome_note'], '',
              '## Limits and unrun work', '', *['- ' + value for value in summary['limits'][4:]], '',
              '## Saved evidence', '', *[f"- [{name}]({Path(source['path']).resolve()})" for name, source in provenance.items()], '']
    (args.output / 'report.md').write_text('\n'.join(lines))
    print(json.dumps({'live': live, 'combined': combined, 'cost': cost}, indent=2))


if __name__ == '__main__':
    main()
