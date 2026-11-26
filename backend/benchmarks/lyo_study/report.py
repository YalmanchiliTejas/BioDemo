"""Build local, descriptive study artifacts from frozen results; never simulate."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import textwrap

import numpy as np

from .study import score

LABELS = {'model:B': 'Model B (legacy)', 'model:C': 'Model C (population)',
          'agent:A': 'AI A (no prebuilt model)', 'agent:B': 'AI B (legacy tool)',
          'agent:C': 'AI C (population tool)'}
CONFUSION = ('TP', 'TN', 'FP', 'FN', 'abstain', 'censored', 'execution_failed', 'not_attempted')
SCOPE = ('Exploratory synthetic comparison with shared constitutive physics. '
         'Reference completion and subsequent thermal outcomes are censored after equipment capacity exceedance. '
         'These are not plant measurements or plant validation.')


def read(path):
    return json.loads(Path(path).read_text())


def mean(values):
    values = [float(v) for v in values if v is not None]
    return float(np.mean(values)) if values else None


def ratio(numerator, denominator):
    return numerator/denominator if denominator else None


def fmt(value, digits=2):
    return '—' if value is None else f'{value:.{digits}f}'


def _index(records, source):
    indexed = {}
    for record in records:
        key = (record['case_id'], record['task'], record['arm'])
        if key in indexed:
            raise ValueError(f'duplicate {source} result: {key}')
        if record['arm'] not in (('B', 'C') if source == 'model' else ('A', 'B', 'C')):
            raise ValueError(f'unknown {source} arm: {record["arm"]}')
        indexed[key] = record
    return indexed


def _records(dataset, model_records, agent_document):
    models = _index(model_records, 'model')
    agents = _index(agent_document['records'], 'agent')
    packets = {(p.parent.name, p.stem): read(p) for p in sorted((dataset/'public').glob('*/*.json'))}
    if not packets:
        raise ValueError('no public packets')
    for case, task, _arm in [*models, *agents]:
        if (case, task) not in packets:
            raise ValueError(f'result has no public packet: {case}/{task}')
    protocol = agent_document.get('protocol', {})
    agent_cases = set(protocol.get('case_ids', [case for case, _task in packets]))
    agent_tasks = set(protocol.get('tasks', ['forecast', 'pretransfer']))
    rows = []
    for (case, task), packet in packets.items():
        if case not in agent_cases or task not in agent_tasks:
            continue
        if packet['case_id'] != case or packet['task'] != task:
            raise ValueError(f'packet identity mismatch: {case}/{task}')
        evaluator = read(dataset/'evaluator'/case/(task+'.json'))
        for source, indexed, arms in [('model', models, ('B', 'C')), ('agent', agents, ('A', 'B', 'C'))]:
            for arm in arms:
                record = indexed.get((case, task, arm))
                submission = record.get('submission') if record else None
                scored = score(submission, evaluator['outcomes'], packet['config']['load_vials'])
                attempted = record is not None
                status = (record.get('status', 'completed' if submission is not None else 'failed')
                          if record else 'not_attempted')
                if not attempted:
                    scored['thermal'] = scored['capacity'] = 'not_attempted'
                rows.append({'case_id': case, 'task': task, 'source': source, 'arm': arm,
                             'family': evaluator.get('family'), 'attempted': attempted,
                             'completed': status == 'completed' and submission is not None,
                             'status': status, 'submission_present': submission is not None,
                             'action_id': submission.get('action_id') if submission else None,
                             'predicted_completion_time_h': submission.get('completion_time_h') if submission else None,
                             'wall_seconds': record.get('wall_seconds') if record else None,
                             'model_calls': record.get('model_calls') if record else None,
                             'tool_calls': record.get('tool_calls') if record else None,
                             'physical_model_calls': record.get('physical_model_calls') if record else None,
                             'error': record.get('error') if record else None, **scored})
    if not rows:
        raise ValueError('protocol case_ids/tasks select no public packets')
    return rows


def _group(rows, source, arm, task):
    subset = [r for r in rows if (r['source'], r['arm'], r['task']) == (source, arm, task)]
    attempted = [r for r in subset if r['attempted']]
    eligible = [r for r in subset if r['completion_eligible']]
    predicted = [r for r in eligible if r['completion_absolute_error_h'] is not None]
    selected = [r for r in subset if r['selection_made']]
    result = {'source': source, 'arm': arm, 'task': task, 'planned': len(subset),
              'attempted': len(attempted), 'completed': sum(r['completed'] for r in subset),
              'submissions': sum(r['submission_present'] for r in subset),
              'status_counts': dict(Counter(r['status'] for r in subset)),
              'model_call_budget_exhaustions': sum('model call budget exhausted' in (r['error'] or '').lower() for r in subset),
              'completion_eligible': len(eligible),
              'completion_eligible_attempted': sum(r['attempted'] for r in eligible),
              'completion_predictions': len(predicted),
              'completion_prediction_coverage': ratio(len(predicted), len(eligible)),
              'completion_mae_h': mean(r['completion_absolute_error_h'] for r in predicted),
              'completion_signed_error_h': mean(r['completion_signed_error_h'] for r in predicted),
              'hindsight_capacity_invalid_completion': sum(r['hindsight_capacity_invalid_completion'] for r in subset),
              'selected': len(selected), 'decision_coverage': ratio(len(selected), len(subset)),
              'feasible_selections': sum(r['selected_feasible'] for r in subset),
              'unsafe_selections': sum(r['unsafe_selection'] for r in subset),
              'characterize': sum(r['action_id'] == 'characterize' for r in subset),
              'abstained_with_hindsight_feasible_action': sum(r['abstained_with_hindsight_feasible_action'] for r in subset),
              'mean_throughput_vials_h': mean(r['throughput_vials_h'] for r in subset),
              'mean_keep_throughput_vials_h': mean(r['keep_throughput_vials_h'] for r in subset),
              'mean_best_grid_throughput_vials_h': mean(r['best_grid_throughput_vials_h'] for r in subset),
              'mean_feasible_selection_regret_vials_h': mean(r['feasible_selection_regret_vials_h'] for r in subset),
              'feasible_regret_cases': sum(r['feasible_selection_regret_vials_h'] is not None for r in subset),
              'mean_wall_seconds': mean(r['wall_seconds'] for r in attempted),
              'total_wall_seconds': sum(r['wall_seconds'] or 0 for r in attempted),
              'wall_seconds_recorded': sum(r['wall_seconds'] is not None for r in attempted)}
    for key in ('thermal', 'capacity'):
        counts = Counter(r[key] for r in subset)
        result[key] = {label: counts[label] for label in CONFUSION}
        result[key]['truth_positive'] = sum(r['truth'][key+'_warning'] is True for r in subset)
        result[key]['truth_negative'] = sum(r['truth'][key+'_warning'] is False for r in subset)
        result[key]['truth_unknown_or_censored'] = sum(r['truth'][key+'_warning'] is None for r in subset)
    return result


def _difference(values, rng):
    """One row per case within each task: resample cases, never individual arms."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    interval = None
    if n >= 2:
        draws = values[rng.integers(0, n, size=(2000, n))].mean(axis=1)
        interval = np.quantile(draws, [.025, .975]).tolist()
    return {'paired_cases': n, 'mean_difference': float(values.mean()) if n else None,
            'descriptive_bootstrap_95_interval': interval}


def _pairs(rows):
    rng = np.random.default_rng(20261102)
    results = []
    for task in sorted({r['task'] for r in rows}):
        groups = {label: {r['case_id']: r for r in rows if r['task'] == task and r['source']+':'+r['arm'] == label}
                  for label in LABELS}
        for left, right in combinations(LABELS, 2):
            common = sorted(groups[left].keys() & groups[right].keys())
            attempted = [(groups[left][case], groups[right][case]) for case in common
                         if groups[left][case]['attempted'] and groups[right][case]['attempted']]
            errors = [(a['completion_absolute_error_h'], b['completion_absolute_error_h']) for a, b in attempted
                      if a['completion_absolute_error_h'] is not None and b['completion_absolute_error_h'] is not None]
            results.append({'task': task, 'left': left, 'right': right,
                            'matched_attempted_cases': len(attempted),
                            'direction': 'right minus left',
                            'completion_mae_difference_h': _difference([b-a for a, b in errors], rng),
                            'left_completion_mae_h_on_common_predictions': mean(a for a, _b in errors),
                            'right_completion_mae_h_on_common_predictions': mean(b for _a, b in errors),
                            'feasible_selection_rate_difference': _difference([int(b['selected_feasible'])-int(a['selected_feasible']) for a, b in attempted], rng),
                            'unsafe_selection_rate_difference': _difference([int(b['unsafe_selection'])-int(a['unsafe_selection']) for a, b in attempted], rng),
                            'throughput_difference_vials_h': _difference([b['throughput_vials_h']-a['throughput_vials_h'] for a, b in attempted], rng)})
    return results


def _cost(agents, document, ledger_path=None):
    # Provider receipts are the only default monetary basis. Token counts are
    # deliberately not converted using a guessed price or inferred model route.
    records = document['records']
    amounts = [r.get('provider_cost_usd') for r in records]
    known = [v for v in amounts if type(v) in (int, float) and np.isfinite(v) and v >= 0]
    result = {'status': 'complete_provider_receipts' if records and len(known) == len(records) else 'partial_provider_receipts' if known else 'unknown',
            'known_provider_cost_usd': sum(known) if known else None,
            'receipts_with_amount': len(known), 'attempts': len(records),
            'basis': 'Sum of recorded provider_cost_usd per attempt; missing values are unknown, not zero.',
            'includes_local_simulation_cost': False}
    explicit_ledger = ledger_path is not None
    ledger_path = Path(ledger_path) if explicit_ledger else agents.parent/'campaign/modal-admission.jsonl'
    if ledger_path.exists():
        entries = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
        settled = [r for r in entries if r.get('event') == 'settled']
        ordinals = [r.get('ordinal') for r in settled]
        if len(ordinals) != len(set(ordinals)):
            raise ValueError('duplicate settled cost ledger ordinal')
        amount = sum(r['conservative_cost_usd'] for r in settled)
        reserved = next((r['total_reserved_usd'] for r in reversed(entries) if 'total_reserved_usd' in r), None)
        unsettled = max(0., reserved-amount) if reserved is not None else None
        result.update(status='proxy_estimate_with_unsettled_reservations' if unsettled is None or unsettled > 1e-9 else 'proxy_estimate_settled',
                      settled_conservative_estimate_usd=amount, total_reserved_usd=reserved,
                      unsettled_reserved_usd=unsettled, settled_requests=len(settled),
                      ledger_path=str(ledger_path.resolve()), ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
                      basis='Whole campaign proxy ledger, including any preflight or interrupted requests: sum of settled conservative_cost_usd from provider token counts at recorded list rates, not an invoice. Unsettled or abandoned reservations remain unknown spending; total_reserved_usd is the admission accounting amount, not actual charges.')
    elif explicit_ledger:
        raise FileNotFoundError(ledger_path)
    return result


def _table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(str(value) for value in row)+' |' for row in rows]])


def _label(group):
    return LABELS[group['source']+':'+group['arm']]


def _overview(summary):
    lines = []
    for task in ('forecast', 'pretransfer'):
        pair = next((p for p in summary['paired_comparisons'] if p['task'] == task
                     and p['left'] == 'model:B' and p['right'] == 'model:C'), None)
        if pair:
            metric = pair['completion_mae_difference_h']
            n, delta = metric['paired_cases'], metric['mean_difference']
            comparison = (f'population-minus-legacy completion MAE was {delta:+.2f} h on {n} common eligible predictions'
                          if n else 'no common eligible numerical predictions supported a model-only MAE comparison')
            agents = [g for g in summary['groups'] if g['task'] == task and g['source'] == 'agent']
            counts = '; '.join(f'{g["arm"]}: {g["completed"]}/{g["attempted"]} completed, '
                               f'{g["feasible_selections"]} feasible / {g["unsafe_selections"]} unsafe selections' for g in agents)
            lines.append(f'{task.capitalize()}: {comparison}. AI results ({counts}).')
    return lines


def _scope_note(summary):
    protocol = summary['agent_protocol']
    scope = protocol.get('scope', '')
    scope_text = scope if isinstance(scope, str) else json.dumps(scope, sort_keys=True)
    note = 'Protocol scope: '+scope_text+'. ' if scope_text else ''
    if 'sensitivity' in scope_text.lower():
        note += ('This is a post-hoc-motivated, prospectively frozen sensitivity analysis on reused cases, '
                 'not an independent new trial. Budget and completion policy were jointly changed; their effects cannot be separated. ')
    if protocol.get('completion_policy'):
        note += 'Recorded completion policy: '+str(protocol['completion_policy'])+'.'
    return note.strip()


def _budget_note(summary):
    protocol = summary['agent_protocol']
    return f'{protocol.get("model_calls", "unknown")} model calls and {protocol.get("wall_seconds", "unknown")} seconds per attempt'


def _markdown(summary):
    lines = ['# Freeze-drying model and AI comparison', '', SCOPE, '',
             _scope_note(summary), '', *_overview(summary), '',
             'The study asks whether an explicit vial-population model and its availability to an AI agent change forecast errors and proposed operating choices. '
             'Forecast uses early synthetic receiving observations; pretransfer uses characterization without receiving observations. The tasks are reported separately.', '',
             'A receives no prebuilt physical model; it can derive its own simulator using the shared Python tool. '
             'B uses the legacy representative-vial model. C uses the population thermal model. B and C use the same capacity applicability cutoff. '
             'Model-only B/C are deterministic selectors; AI A/B/C are recorded agent runs. These labels do not identify distinct underlying AI models.', '',
             f'Protocol: [frozen issue #1]({summary["issue"]}). Campaign status: **{summary["agent_campaign_status"]}**. '
             'All submitted results are rescored from the frozen evaluator files; missing attempts and failed execution remain visible.', '',
             f'Recorded AI model: {summary["agent_protocol"].get("model", "Unknown")}. '
             f'Per-attempt limits: {summary["agent_protocol"].get("model_calls", "Unknown")} model calls, '
             f'{summary["agent_protocol"].get("tool_calls", "Unknown")} tool calls, '
             f'{summary["agent_protocol"].get("wall_seconds", "Unknown")} seconds; '
             f'output-token limit {summary["agent_protocol"].get("max_output_tokens", "Unknown")}.', '']
    for task in ('forecast', 'pretransfer'):
        groups = [g for g in summary['groups'] if g['task'] == task]
        if not groups:
            continue
        lines += [f'## {task.capitalize()}', '',
                  'Completion errors concern KEEP, regardless of the chosen action. MAE uses only eligible cases with a numerical prediction; '
                  'coverage uses all planned eligible cases. Different coverage can change MAE, so the paired table below also uses common predictions.', '',
                  _table(['Arm', 'Planned', 'Attempted', 'Completed', 'Eligible', 'Predicted', 'Coverage', 'MAE (h)', 'Hindsight-invalid completions'],
                         [[_label(g), g['planned'], g['attempted'], g['completed'], g['completion_eligible'], g['completion_predictions'],
                           fmt(100*g['completion_prediction_coverage'], 1)+'%' if g['completion_prediction_coverage'] is not None else '—',
                           fmt(g['completion_mae_h']), g['hindsight_capacity_invalid_completion']] for g in groups]), '',
                  'Hindsight-invalid means the hidden reference later exceeded capacity; it does not establish that the agent could know that from its public evidence.', '']
        for kind in ('thermal', 'capacity'):
            lines += [f'### {kind.capitalize()} warnings', '',
                      'TP/TN are correct positive/negative calls; FP/FN are incorrect positive/negative calls. Abstain means a submitted unknown. '
                      'Censored means the reference target cannot be evaluated. Execution failures and unattempted runs are separate. '
                      'Truth counts include all planned cases regardless of execution. With zero truth positives, sensitivity cannot be estimated; small positive counts also limit interpretation.', '',
                      _table(['Arm', 'Attempted', 'Completed', 'TP', 'TN', 'FP', 'FN', 'Abstain', 'Censored', 'Failed', 'Not attempted', 'Truth positive', 'Truth negative', 'Truth unknown'],
                             [[_label(g), g['attempted'], g['completed'], *[g[kind][key] for key in CONFUSION],
                               g[kind]['truth_positive'], g[kind]['truth_negative'], g[kind]['truth_unknown_or_censored']] for g in groups]), '']
        lines += ['### Proposed actions', '',
                  'Decision coverage counts a manufacturing choice, not characterize. Unsafe means the selected scenario violates a modeled constraint or fails to complete; '
                  'it is not an observed plant incident. The benchmark throughput score averages synthetic feasible vials/hour over all planned cases, '
                  'assigning zero to invalid selections, characterize, failed runs and missing attempts. This is not measured plant throughput. '
                  'Regret is reported only for feasible selections, relative to the best feasible action in the tested grid.', '',
                  _table(['Arm', 'Attempted', 'Completed', 'Selected / planned', 'Feasible', 'Unsafe', 'Characterize', 'Abstain with hindsight feasible action', 'Benchmark throughput score (vials/h)', 'KEEP score (vials/h)', 'Feasible regret (vials/h; n)'],
                         [[_label(g), g['attempted'], g['completed'], f'{g["selected"]}/{g["planned"]}', g['feasible_selections'], g['unsafe_selections'],
                           g['characterize'], g['abstained_with_hindsight_feasible_action'], fmt(g['mean_throughput_vials_h']), fmt(g['mean_keep_throughput_vials_h']),
                           f'{fmt(g["mean_feasible_selection_regret_vials_h"])}; {g["feasible_regret_cases"]}'] for g in groups]), '',
                  f'![{task} comparison]({task}-comparison.png)', '',
                  '### Matched differences', '',
                  'Differences are right minus left. Completion differences use only cases predicted by both arms. '
                  'Intervals are descriptive 2,000-resample case bootstrap intervals; one-case pairs have no interval. '
                  'Authored case families are not manufacturing prevalence, and these intervals do not establish population-level significance.', '',
                  _table(['Comparison (left → right)', 'Matched attempts', 'Common completion predictions', 'MAE difference (h)', 'Descriptive interval (h)', 'Benchmark throughput score difference (vials/h)'],
                         [[p['left']+' → '+p['right'], p['matched_attempted_cases'], p['completion_mae_difference_h']['paired_cases'],
                           fmt(p['completion_mae_difference_h']['mean_difference']),
                           '—' if p['completion_mae_difference_h']['descriptive_bootstrap_95_interval'] is None else
                           ' to '.join(fmt(v) for v in p['completion_mae_difference_h']['descriptive_bootstrap_95_interval']),
                           fmt(p['throughput_difference_vials_h']['mean_difference'])] for p in summary['paired_comparisons'] if p['task'] == task]), '']
    cost = summary['cost']
    lines += ['## Runtime and cost', '',
              _table(['Task', 'Arm', 'Attempted', 'Completed', 'Call-budget exhaustions', 'Mean recorded wall time (s)', 'Runtime receipts'],
                     [[g['task'], _label(g), g['attempted'], g['completed'], g['model_call_budget_exhaustions'],
                       fmt(g['mean_wall_seconds']), f'{g["wall_seconds_recorded"]}/{g["attempted"]}'] for g in summary['groups']]), '',
              ('Unknown total inference cost: no complete monetary receipt set is available.' if cost['status'] != 'complete_provider_receipts'
               else f'Recorded inference cost: ${cost["known_provider_cost_usd"]:.4f}.'),
              cost['basis'], '',
              (f'Available per-attempt monetary receipts sum to ${cost["known_provider_cost_usd"]:.6f} '
               f'({cost["receipts_with_amount"]}/{cost["attempts"]} attempts with an amount).'
               if cost['known_provider_cost_usd'] is not None else ''), '',
              ('Settled campaign proxy estimate: $'+fmt(cost['settled_conservative_estimate_usd'], 6)+
               '; total admission accounting: $'+fmt(cost['total_reserved_usd'], 6)+
               '; unresolved reservations: $'+fmt(cost['unsettled_reserved_usd'], 6)+'. These are not invoiced charges.'
               if 'settled_conservative_estimate_usd' in cost else ''), '',
              'Wall time sums may overlap under parallel execution. Human engineering effort, plant throughput, avoided failures, and operating savings were not measured.', '',
              '## Interpretation and limits', '',
              'The evaluator and candidate models share physical laws, so this tests behavior under deliberately introduced synthetic mismatch, not independent physical validity. '
              'The population model adds thermal storage and active-vial heterogeneity; it does not resolve temperature fields or predict chamber pressure after overload. '
              'Censoring prevents arbitrary post-overload reference pressure dynamics from becoming a physical accuracy target. '
              'The half-hourly thermal and ice-mass observations are synthetic information channels, not a claim that routine plant sensors supply them. '
              'Pretransfer hidden receiving shifts are unknowable from the supplied characterization alone.', '',
              'Agents may spend their limited Python and model-call budget constructing a simulator. Budget-exhausted runs remain in attempted counts and receive no decision credit. '
              'Any workflow advantage from access to a prepared physical tool is conditional on the recorded call and wall-time limits '
              '('+_budget_note(summary)+'), not evidence that A could not construct a model with more time.', '',
              'Feasible selections are proposals under the synthetic evaluator and a limited action grid. They are not approved manufacturing actions. '
              'Characterization can be an appropriate choice even though it receives no benchmark throughput credit. '
              'Lower completion MAE does not establish better action choices or a higher benchmark throughput score, even on common predictions. '
              'Forecast error, coverage, feasible choices and unsafe choices must be compared separately; the report does not presume that access to the newer model improves every outcome.', '',
              'Artifacts: `per-case.csv` preserves every planned row; `summary.json` contains counts, denominators, paired comparisons and source hashes. '
              'The PNG and SVG plots are generated from those same aggregate counts.', '']
    return '\n'.join(lines)


def _linkedin(summary):
    lines = ['# LinkedIn draft', '', 'We compared two freeze-drying model approaches and AI agents with different tool access in a reproducible synthetic study.', '', SCOPE, '',
             _scope_note(summary), '',
             'AI A receives no prebuilt physical model and can derive its own simulator in Python. B and C receive prepared legacy and population models, respectively.', '']
    for task in ('forecast', 'pretransfer'):
        groups = [g for g in summary['groups'] if g['task'] == task]
        if not groups:
            continue
        lines += [f'{task.capitalize()} results:']
        for g in groups:
            lines.append(f'- {_label(g)}: {g["completed"]}/{g["attempted"]} attempts completed; '
                         f'{g["completion_predictions"]}/{g["completion_eligible"]} eligible completion forecasts; '
                         f'MAE {fmt(g["completion_mae_h"])} h on those predictions; '
                         f'{g["feasible_selections"]} feasible and {g["unsafe_selections"]} unsafe synthetic selections; '
                         f'{g["characterize"]} characterize choices.')
        lines.append('')
    lines += ['The useful distinction is between producing a forecast and knowing when the model no longer applies. '
              'We report prediction coverage, warning abstentions, action feasibility and execution failures alongside error. '
              'A model can have a smaller error on fewer cases without being more useful overall. '
              'Lower completion MAE does not establish an action-selection gain. The observed comparisons above must be read separately for error, coverage and feasibility.', '',
              'Budget-exhausted attempts remain in the results. A can spend its limited calls constructing a simulator; any benefit from a prepared tool is conditional on '
              'the recorded budget of '+_budget_note(summary)+'. A benchmark throughput score gives zero credit to failed or unsafe choices and abstention; it is not real plant throughput.', '',
              'This does not demonstrate plant validation, real failure prevention, or realized manufacturing gains. '
              'The next evidence would need independent experimental or plant data with a defined intended use. '
              'The full local report includes per-case results, model-only comparisons and the limits of this experiment.', '']
    return '\n'.join(lines)


def _plots(summary, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for task in ('forecast', 'pretransfer'):
        groups = [g for g in summary['groups'] if g['task'] == task]
        if not groups:
            continue
        labels = [g['source']+':'+g['arm'] for g in groups]
        x = np.arange(len(groups))
        fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout='constrained')
        axes[0].bar(x, [g['completion_mae_h'] if g['completion_mae_h'] is not None else np.nan for g in groups], color='#327b8a')
        axes[0].set_title('KEEP completion MAE\nEligible predictions only')
        axes[0].set_ylabel('Hours')
        for i, g in enumerate(groups):
            axes[0].text(i, g['completion_mae_h'] or 0, f'{g["completion_predictions"]}/{g["completion_eligible"]}', ha='center', va='bottom', fontsize=9)
        axes[1].bar(x, [100*(g['completion_prediction_coverage'] or 0) for g in groups], color='#618f4c')
        axes[1].set_title('Completion prediction coverage')
        axes[1].set_ylabel('% of planned eligible cases')
        axes[1].set_ylim(0, 110)
        base = np.zeros(len(groups))
        parts = [('feasible_selections', 'Feasible', '#618f4c'), ('unsafe_selections', 'Unsafe', '#b14f4a'),
                 ('characterize', 'Characterize', '#b79842')]
        for key, label, color in parts:
            values = np.array([g[key] for g in groups])
            axes[2].bar(x, values, bottom=base, label=label, color=color)
            base += values
        missing = np.array([g['planned'] for g in groups])-base
        axes[2].bar(x, missing, bottom=base, label='No choice', color='#aaa')
        axes[2].set_title('Proposed action outcomes')
        axes[2].set_ylabel('Planned cases')
        axes[2].legend(fontsize=8)
        for ax in axes:
            ax.set_xticks(x, labels, rotation=30, ha='right')
            ax.spines[['top', 'right']].set_visible(False)
        fig.suptitle(f'{task.capitalize()} — synthetic shared-law comparison; post-capacity reference targets censored', fontsize=12)
        for extension in ('png', 'svg'):
            fig.savefig(output/f'{task}-comparison.{extension}', dpi=170)
        plt.close(fig)


def _brief_pdf(summary, output):
    """Four-page scientific brief; all reported numbers come from the summary."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    ink, teal, muted = '#202e35', '#286577', '#53636a'
    short = {'model:B': 'Model B', 'model:C': 'Model C',
             'agent:A': 'AI A', 'agent:B': 'AI B', 'agent:C': 'AI C'}

    def page(title, number):
        fig = plt.figure(figsize=(8.5, 11), facecolor='#fcfcfa')
        fig.text(.075, .965, 'SYNTHETIC STUDY  /  SHARED CONSTITUTIVE PHYSICS', fontsize=9.5,
                 color=teal, weight='bold')
        if 'sensitivity' in _scope_note(summary).lower():
            fig.text(.075, .945, 'Sensitivity analysis: reused cases; budget and completion policy changed jointly.',
                     fontsize=7.8, color=muted)
        fig.text(.075, .915, title, fontsize=23, color=ink, weight='bold', va='top')
        fig.add_artist(plt.Line2D([.075, .925], [.061, .061], transform=fig.transFigure,
                                 color='#b7c5c9', linewidth=.7))
        fig.text(.075, .039, 'Research comparison only. Not plant validation or an approved manufacturing action.',
                 fontsize=7.7, color=muted)
        fig.text(.925, .039, str(number)+' / 4', fontsize=8, color=muted, ha='right')
        return fig

    def text(fig, y, paragraph, *, size=10.5, width=91, color=ink):
        wrapped = textwrap.fill(paragraph, width=width, break_long_words=False, break_on_hyphens=False)
        fig.text(.075, y, wrapped, fontsize=size, color=color, va='top', linespacing=1.45)
        return y-(wrapped.count('\n')+1)*size/792*1.45-.021

    def heading(fig, y, label):
        fig.text(.075, y, label, fontsize=12.5, color=teal, weight='bold', va='top')
        return y-.034

    def table(fig, bounds, groups, *, show_task=False):
        if not groups:
            fig.text(bounds[0], bounds[1]+bounds[3]/2, 'Not included in this protocol.', fontsize=10, color=muted)
            return
        headers = (['Task'] if show_task else [])+['Arm', 'Done /\ntried', 'Pred. /\neligible',
                                                  'MAE\n(hours)', 'Feasible /\nunsafe', 'Score*\n(vials/h)']
        data = []
        for g in groups:
            data.append(([g['task']] if show_task else [])+
                        [short[g['source']+':'+g['arm']], f'{g["completed"]}/{g["attempted"]}',
                         f'{g["completion_predictions"]}/{g["completion_eligible"]}',
                         fmt(g['completion_mae_h']), f'{g["feasible_selections"]}/{g["unsafe_selections"]}',
                         fmt(g['mean_throughput_vials_h'], 1)])
        ax = fig.add_axes(bounds)
        ax.axis('off')
        grid = ax.table(cellText=data, colLabels=headers, cellLoc='center', bbox=[0, 0, 1, 1])
        grid.auto_set_font_size(False)
        grid.set_fontsize(8.5 if show_task else 9.)
        for (row, _column), cell in grid.get_celld().items():
            cell.set_edgecolor('#d4dddf')
            cell.set_linewidth(.5)
            cell.set_text_props(color=ink)
            if row == 0:
                cell.set_facecolor(teal)
                cell.set_text_props(color='white', weight='bold')
            else:
                cell.set_facecolor('#eef3f3' if row % 2 else 'white')

    def save(pdf, fig):
        pdf.savefig(fig)
        plt.close(fig)

    with PdfPages(output/'case-study-brief.pdf', metadata={
            'Title': 'Freeze-drying models and AI: a synthetic case study',
            'Subject': 'Exploratory shared-physics comparison; no plant validation',
            'Keywords': 'synthetic, freeze-drying, lyophilization, model applicability'}) as pdf:
        fig = page('What changes when the model changes?', 1)
        y = text(fig, .855, 'A freeze-drying cycle must finish primary drying without exceeding product-temperature or equipment-capacity limits. '
                 'This experiment compares forecast errors and proposed operating choices when an AI agent receives different physical tools.')
        if _scope_note(summary):
            context = ('Post-hoc-motivated, prospectively frozen sensitivity analysis on reused cases, not an independent new trial. '
                       'Budget and completion policy changed together.' if 'sensitivity' in _scope_note(summary).lower()
                       else _scope_note(summary))
            y = text(fig, y, context, size=9., width=106, color=muted)
        y = heading(fig, y, 'The engineering change')
        y = text(fig, y, 'Model B represents one quasi-steady vial. Model C represents explicit weighted vial populations with independent ice mass and thermal storage. '
                 'C tracks the hottest still-drying population; already-dry vials can warm without becoming active primary-drying violations.')
        y = text(fig, y, 'Both models retain prescribed chamber pressure. Both use the same rule: once predicted capacity is exceeded, completion is not a valid physical forecast. '
                 'The change does not add a pressure-dynamics model or establish physical validation.')
        y = heading(fig, y, 'Two distinct decisions')
        y = text(fig, y, 'Forecast: use early synthetic receiving observations to predict the known KEEP schedule and choose among the allowed actions. '
                 'Pretransfer: make the same forecasts and choices from characterization alone, without receiving observations. The tasks are never combined into one accuracy number.')
        y = heading(fig, y, 'What was compared')
        y = text(fig, y, 'Deterministic B/C controls select from model predictions. AI A receives no prebuilt physical model and can derive its own simulator using Python. '
                 'AI B and AI C receive prepared legacy and population tools. The candidate action grid also permits characterize.')
        text(fig, y, 'All measurements and reference outcomes are synthetic. Reference completion and subsequent thermal outcomes are censored after capacity exceedance. '
             'The evaluator and candidates share constitutive laws; this is an exploratory comparison under synthetic mismatch.', color=muted)
        save(pdf, fig)

        fig = page('Model-only results, with coverage', 2)
        text(fig, .855, 'MAE describes KEEP completion on eligible cases with a numerical prediction. Pred./eligible exposes that denominator; '
             'feasible/unsafe describes selected actions. Missing or failed attempts remain in the planned-case score.', size=10.)
        controls = [g for g in summary['groups'] if g['source'] == 'model']
        table(fig, [.075, .605, .85, .17], controls, show_task=True)
        ax = fig.add_axes([.12, .31, .78, .23])
        colors = ['#91afb8' if g['arm'] == 'B' else teal for g in controls]
        positions = np.arange(len(controls))
        ax.bar(positions, [g['completion_mae_h'] if g['completion_mae_h'] is not None else np.nan for g in controls], color=colors)
        ax.set_xticks(positions, [g['task']+'\n'+short['model:'+g['arm']] for g in controls], fontsize=9)
        ax.set_ylabel('KEEP completion MAE (h)', fontsize=10)
        ax.spines[['top', 'right']].set_visible(False)
        for i, g in enumerate(controls):
            ax.annotate(f'{g["completion_predictions"]}/{g["completion_eligible"]}',
                        (i, g['completion_mae_h'] or 0), xytext=(0, 4), textcoords='offset points', ha='center', fontsize=8)
        ax.margins(y=.2)
        y = .245
        for task in ('forecast', 'pretransfer'):
            pair = next((p for p in summary['paired_comparisons'] if p['task'] == task and p['left'] == 'model:B' and p['right'] == 'model:C'), None)
            if pair is None:
                continue
            metric = pair['completion_mae_difference_h']
            y = text(fig, y, f'{task.capitalize()} common-prediction comparison: C minus B MAE = '
                     f'{fmt(metric["mean_difference"])} h; n = {metric["paired_cases"]}. '
                     'Negative means lower completion error on that common subset.', size=9.3, width=100)
        text(fig, .112, '* Benchmark throughput score: mean synthetic feasible vials/h over planned cases, with zero for invalid choices, characterize, failure or no attempt. '
             'This is not real plant throughput.', size=8.5, width=110, color=muted)
        save(pdf, fig)

        fig = page('AI decisions versus prepared controls', 3)
        protocol = summary['agent_protocol']
        policy = ' Completion policy: '+str(protocol['completion_policy'])+'.' if protocol.get('completion_policy') else ''
        text(fig, .855, f'Per attempt: {protocol.get("model_calls", "unknown")} model calls, '
             f'{protocol.get("wall_seconds", "unknown")} seconds, {protocol.get("tool_calls", "unknown")} tool calls. '
             'A can build a simulator in Python; B/C receive prepared models. The comparison includes the workflow cost of doing that within these limits.', size=10.)
        if policy:
            fig.text(.075, .783, textwrap.fill(policy.strip(), width=112), fontsize=8.2, color=muted, va='top')
        heading(fig, .76 if policy else .79, 'Forecast')
        table(fig, [.075, .545 if policy else .565, .85, .185 if policy else .195], [g for g in summary['groups'] if g['task'] == 'forecast'])
        heading(fig, .525, 'Pretransfer')
        table(fig, [.075, .300, .85, .195], [g for g in summary['groups'] if g['task'] == 'pretransfer'])
        exhausted = sum(g['model_call_budget_exhaustions'] for g in summary['groups'] if g['source'] == 'agent')
        characterized = sum(g['characterize'] for g in summary['groups'] if g['source'] == 'agent')
        text(fig, .265, f'Recorded AI call-budget exhaustions: {exhausted}; characterize submissions: {characterized} across the two tasks. '
             'Failures and abstentions remain visible and earn zero benchmark throughput credit. Any prepared-tool workflow advantage is conditional on the fixed budget.', size=9.5, width=100)
        text(fig, .159, 'Lower completion MAE does not establish an action-selection gain. Compare coverage, feasible and unsafe selections, and benchmark score separately. '
             'These outcomes do not measure human engineering effort or actual manufacturing gains.', size=9.5, width=100)
        text(fig, .094, 'Done/tried = completed/attempted; Pred./eligible = numerical KEEP forecasts/reference-eligible cases. Score* is the benchmark throughput score defined on page 2.',
             size=8, width=115, color=muted)
        save(pdf, fig)

        fig = page('What this evidence can and cannot say', 4)
        y = .855
        y = heading(fig, y, 'Warning support, not a broad safety claim')
        for task in ('forecast', 'pretransfer'):
            g = next((g for g in summary['groups'] if g['task'] == task and g['source'] == 'model' and g['arm'] == 'B'), None)
            if g is None:
                continue
            capacity, thermal = g['capacity']['truth_positive'], g['thermal']['truth_positive']
            note = (' With zero KEEP capacity positives, capacity sensitivity cannot be estimated.' if capacity == 0
                    else ' Positive counts describe this authored set, not manufacturing prevalence.')
            y = text(fig, y, f'{task.capitalize()} reference support among {g["planned"]} planned cases: '
                     f'{capacity} positive KEEP capacity outcomes; {thermal} positive KEEP thermal outcomes.'+note, size=10.)
        y = heading(fig, y, 'Important limits')
        y = text(fig, y, 'The half-hourly temperature and ice-mass observations are synthetic information channels, not a claim about routine factory sensor availability. '
                 'Pretransfer receiving shifts are hidden and cannot be recovered from the supplied characterization alone.', size=10.)
        y = text(fig, y, 'The evaluator and candidates share laws and approximate population structure. Thermal nodes are not spatial temperature fields. '
                 'Post-overload pressure behavior is not a physical forecast target. The tested action grid is limited; characterize can be a reasonable choice despite earning no score.', size=10.)
        y = heading(fig, y, 'Next evidence needed')
        y = text(fig, y, 'Define the intended decision and acceptable error; independently characterize vial populations, resistance, thermal storage and equipment capacity; '
                 'then compare predictions with independent experimental or plant data. Include positive capacity cases and a practical observation plan before drawing conclusions about warning sensitivity.', size=10.)
        y = heading(fig, y, 'Reproducibility and review')
        y = text(fig, y, 'The companion report, per-case CSV and summary JSON preserve counts, missing attempts, source hashes, cost uncertainty and descriptive paired comparisons. '
                 'No manufacturing actions were executed. This brief is for research review and discussion.', size=10.)
        text(fig, y, 'Frozen protocol: '+summary['issue'], size=8.5, width=110, color=muted)
        save(pdf, fig)


def generate(dataset, models, agents, output, *, cost_ledger=None):
    """Read frozen files, score submissions, and create a fresh report directory."""
    dataset, models, agents, output = map(Path, (dataset, models, agents, output))
    if output.exists():
        raise FileExistsError('report output exists; choose a fresh directory')
    model_records, agent_document = read(models/'results.json'), read(agents/'results.json')
    rows = _records(dataset, model_records, agent_document)
    groups = [_group(rows, source, arm, task) for task in sorted({r['task'] for r in rows})
              for source, arms in [('model', ('B', 'C')), ('agent', ('A', 'B', 'C'))] for arm in arms]
    sources = [dataset/'protocol.json', models/'results.json', agents/'results.json', *sorted((dataset/'public').glob('*/*.json')),
               *sorted((dataset/'evaluator').glob('*/*.json'))]
    summary = {'version': 'lyo-study-report-1', 'scope': SCOPE,
               'issue': read(dataset/'protocol.json').get('issue', 'https://github.com/YalmanchiliTejas/BioDemo/issues/1'),
               'agent_campaign_status': agent_document.get('status', 'unknown'),
               'agent_protocol': agent_document.get('protocol', {}),
               'metric_definitions': {'mean_throughput_vials_h': 'Benchmark throughput score over planned cases: synthetic feasible vials/hour, zero for invalid selections, characterize, execution failures and missing attempts; not real plant throughput.',
                                      'warning_truth_support': 'Positive, negative and unknown reference outcomes among all planned KEEP cases. Sensitivity cannot be estimated with no positives.'},
               'groups': groups, 'paired_comparisons': _pairs(rows), 'cost': _cost(agents, agent_document, cost_ledger),
               'bootstrap': {'seed': 20261102, 'resamples': 2000, 'unit': 'case within task', 'interpretation': 'descriptive; authored families are not manufacturing prevalence'},
               'sources_sha256': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    output.mkdir(parents=True, exist_ok=False)
    (output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    flat = [{**{k: v for k, v in r.items() if k != 'truth'}, **{'truth_'+k: v for k, v in r['truth'].items()}} for r in rows]
    with (output/'per-case.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    (output/'report.md').write_text(_markdown(summary))
    (output/'linkedin-draft.md').write_text(_linkedin(summary))
    _plots(summary, output)
    _brief_pdf(summary, output)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'models', 'agents', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--cost-ledger', type=Path)
    args = parser.parse_args()
    result = generate(args.dataset, args.models, args.agents, args.output, cost_ledger=args.cost_ledger)
    print(json.dumps({'output': str(args.output), 'groups': len(result['groups']), 'cost': result['cost']}, indent=2))
