"""Join primary and sensitivity outcomes on identical cases, without inference."""
from __future__ import annotations

import argparse
from pathlib import Path
import hashlib
import json
import math

from . import report
from .study import verify_dataset


def report_balance(campaign):
    """Reporting only: retain full reservations even if a stopped proxy never settled."""
    path = Path(campaign)/'modal-admission.jsonl'
    reservations, settlements, finished = {}, {}, set()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        event, ordinal = row['event'], row.get('ordinal')
        if event in ('reserved', 'settled'):
            target = reservations if event=='reserved' else settlements
            key = 'reserved_usd' if event=='reserved' else 'conservative_cost_usd'
            amount = row[key]
            if ordinal in target or type(amount) not in (int,float) or not math.isfinite(amount) or amount < 0:
                raise ValueError('Malformed or duplicated cost event')
            target[ordinal] = amount
        elif event=='finished':
            finished.add(ordinal)
    if not reservations or not (set(settlements)|finished) <= set(reservations):
        raise ValueError('Missing reservation evidence')
    unknown = set(reservations)-set(settlements)
    settled = sum(settlements.values())
    held = settled + sum(reservations[k] for k in unknown)
    return {'original_held_usd':held, 'settled_estimate_usd':settled,
            'unknown_reserved_usd':sum(reservations[k] for k in unknown),
            'unknown_request_ordinals':sorted(unknown),
            'requests_without_finished_event':sorted(set(reservations)-finished),
            'ledger_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'basis':'Reporting snapshot only, never inference authorization; retain full reservation for every request without a settlement, including interrupted proxy requests; not an invoice'}


def generate(base, output):
    base, output = Path(base), Path(output)
    targets = [output/'sensitivity-comparison.json', output/'sensitivity-comparison.md']
    if any(p.exists() for p in targets):
        raise ValueError('Supplement already exists; preserve the original')
    verification = verify_dataset(base/'frozen')
    primary_path = base/'recovered-agents/results.json'
    sensitivity_path = base/'sensitivity/results.json'
    primary, sensitivity = report.read(primary_path), report.read(sensitivity_path)
    if primary['status'] != 'complete' or sensitivity['status'] != 'complete':
        raise ValueError('Both cohorts must finish before publication')
    selected = sensitivity['protocol']['case_ids']
    if not set(selected) <= set(primary['protocol']['case_ids']):
        raise ValueError('Sensitivity is not a primary subset')
    primary['protocol']['case_ids'] = selected
    primary['protocol']['tasks'] = sensitivity['protocol']['tasks']
    models = report.read(base/'model-only/results.json')
    rows = {name: report._records(base/'frozen', models, doc)
            for name, doc in [('primary', primary), ('sensitivity', sensitivity)]}
    comparison = []
    for task in sensitivity['protocol']['tasks']:
        for arm in sensitivity['protocol']['arms']:
            groups = {name: report._group(data, 'agent', arm, task) for name, data in rows.items()}
            indexed = {name: {r['case_id']: r for r in data
                       if r['source']=='agent' and r['task']==task and r['arm']==arm}
                       for name, data in rows.items()}
            common = [case for case in selected if all(
                indexed[name][case]['completion_absolute_error_h'] is not None for name in indexed)]
            comparison.append({'task': task, 'arm': arm, **groups,
                'common_completion_cases': common,
                'primary_mae_h_on_common_predictions': report.mean(indexed['primary'][c]['completion_absolute_error_h'] for c in common),
                'sensitivity_mae_h_on_common_predictions': report.mean(indexed['sensitivity'][c]['completion_absolute_error_h'] for c in common)})
    costs = {name: report_balance(base/name) for name in
             ('campaign', 'recovery-campaign', 'sensitivity-campaign')}
    total = sum(c['original_held_usd'] for c in costs.values())
    if total > 10. + 1e-9:
        raise ValueError('Combined admission accounting exceeds $10')
    final_requests = []
    for path in sorted((base/'sensitivity/attempts').glob('*/*/*/events.jsonl')):
        events = [json.loads(line) for line in path.read_text().splitlines()]
        requests = [e for e in events if e.get('type')=='request_configuration' and e.get('final_turn_submit_only')]
        for request in requests:
            if request['tool_names'] != ['submit_decision']:
                raise ValueError('Final-turn tools do not match frozen policy')
            final_requests.append(str(path.relative_to(base)))
    source_paths = [primary_path, sensitivity_path, base/'sensitivity/protocol.json',
                    base/'model-only/results.json', Path(__file__), Path(report.__file__),
                    Path(__file__).with_name('recovery.py'),
                    *sorted((base/'sensitivity/attempts').glob('*/*/*/events.jsonl'))]
    result = {'scope': 'Post-hoc motivated, prospectively frozen joint budget/submission sensitivity; reused cases, no independent confirmation',
              'case_ids': selected, 'comparison': comparison, 'cost_ledgers': costs,
              'dataset_verification': verification,
              'combined_conservative_accounting_usd': total,
              'cost_scope': 'Original, infrastructure continuation and sensitivity; token-based estimates and any retained unknown reservations, not invoices; excludes local compute and engineering',
              'actual_final_turn_request_journals': final_requests,
              'source_sha256': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}}
    lines = ['# Same-case sensitivity comparison', '', result['scope']+'.', '',
        'Each row compares the original four-call/120-second result with the eight-call/240-second result on the same six cases. The latter also restricts the last provider turn to submission. This bundles budget, wall time and completion policy. All three arms receive the same change. No original failure is replaced.', '',
        'MAE is conditional on numerical predictions; coverage must be read alongside it. The common-prediction table compares identical cases when both sessions provided a numerical answer. One realization per arm and six reused cases cannot identify a stable causal effect.', '']
    table = []
    for row in comparison:
        for name in ('primary', 'sensitivity'):
            g=row[name]
            table.append([row['task'], row['arm'], name, f"{g['completed']}/{g['planned']}",
                f"{g['completion_predictions']}/{g['completion_eligible']}",report.fmt(g['completion_mae_h']),
                g['feasible_selections'], g['unsafe_selections'], g['characterize']])
    lines += [report._table(['Task','Arm','Protocol','Completed','Predicted / eligible','MAE (h)','Feasible','Unsafe','Characterize'],table),'',
        report._table(['Task','Arm','Common predictions','Primary MAE (h)','Sensitivity MAE (h)'],
        [[r['task'],r['arm'],len(r['common_completion_cases']), report.fmt(r['primary_mae_h_on_common_predictions']),
          report.fmt(r['sensitivity_mae_h_on_common_predictions'])] for r in comparison]),'',
        '## Cost and execution evidence','',
        f'Combined original, continuation and sensitivity admission accounting: ${total:.8f}, under the original $10 cap. Of this, ${sum(c["settled_estimate_usd"] for c in costs.values()):.8f} is a settled token-based estimate and ${sum(c["unknown_reserved_usd"] for c in costs.values()):.8f} remains reserved for requests with unknown cost. This is not an invoice; it excludes local simulation and engineering. Interrupted proxy requests retain their entire reservation even without a finished event.', '',
        f'Actual provider-request journals record {len(final_requests)} final submission-only turns; their exposed tool list was verified. The policy does not guarantee successful submission.', '',
        'The JSON companion preserves full warning confusion matrices, failures, coverage, ledger hashes and common-prediction denominators. The primary study remains separate.']
    output.mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json.dumps(result, indent=2)+'\n')
    targets[1].write_text('\n'.join(lines)+'\n')
    return {'comparisons':len(comparison), 'accounting_usd':total, 'submission_only_requests':len(final_requests)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(generate(args.base,args.output),indent=2))
