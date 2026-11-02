"""Read-only diagnostics of retained agent failures and real CHO forecasts.

Previously inspected conditions are development evidence, never a new holdout.
No inference or raw-dataset download is required.
"""
from collections import defaultdict
from pathlib import Path
import argparse
import json
import numpy as np
from benchmarks.external_simulators import cho_real
from benchmarks.external_simulators.experiment import dump, sha

REPO = Path(__file__).resolve().parents[3]


def stopping_failures(results):
    failures = []
    for case in results['cases']:
        for record in case['records']:
            if record['arm'] != 'B' or not record.get('evaluation'):
                continue
            proposal = record['evaluation']['proposal']
            action = proposal['action_id']
            matching = [t for t in record['tools'] if t['name'] == 'physical_forward_model'
                        and t['arguments'].get('action_id') == action]
            if action != 'stop' and matching:
                result = matching[-1]['result']
                if result.get('outcome_prediction', {}).get('post_decision_feasible') is False:
                    failures.append({'case_id': case['case_id'], 'repeat': case['repeat'],
                                     'action': action, 'central_prediction_infeasible': True,
                                     'sensitivity': result.get('sensitivity')})
    return failures


def empirical(packet, method):
    predictions = {}
    for field, target in packet['forecast_times_h'].items():
        rows = [r for r in packet['test_prefix'] if r['field'] == field]
        last = rows[-1]
        if method == 'last_value' or len(rows) < 2:
            value = last['value']
        else:
            previous = rows[-2]
            slope = (last['value'] - previous['value']) / (last['time_h'] - previous['time_h'])
            value = max(0., last['value'] + slope * (target - last['time_h']))
        predictions[field] = value
    return predictions


def diagnose(output):
    output.mkdir(parents=True, exist_ok=False)
    old = REPO / 'backend/results/interventions/frozen-ab-20261029/results.json'
    failures = stopping_failures(json.loads(old.read_text()))
    dump(output / 'stopping-baseline.json', {'source_sha256': sha(old),
         'red_signal': bool(failures), 'failure_count': len(failures), 'failures': failures,
         'interpretation': 'Recorded choices violate the proposed feasibility-first policy. No new GLM calls.'})
    root = REPO / 'backend/results/external-simulators/improvements-20261027/cho-dataset-v2'
    rows = []
    for path in sorted((root / 'public').glob('*/packet.json')):
        packet = json.loads(path.read_text())
        truth_path = root / 'evaluator' / packet['case_id'] / 'truth.json'
        truth = json.loads(truth_path.read_text())
        fitted = cho_real.predict(packet)
        stored = json.loads((root / 'model-library' / packet['case_id'] / 'nominal.json').read_text())['keep']
        if not all(np.isclose(fitted[k], stored[k], rtol=1e-6, atol=1e-7) for k in fitted):
            raise ValueError('Current CHO integration no longer reproduces the frozen model')
        for method, prediction in [('mechanistic', fitted), ('last_value', empirical(packet, 'last_value')),
                                   ('linear_prefix', empirical(packet, 'linear_prefix'))]:
            for field, value in prediction.items():
                actual = truth['targets'][field]['value']
                rows.append({'case_id': packet['case_id'], 'condition': packet['condition'],
                             'culture': packet['culture'], 'method': method, 'field': field,
                             'prediction': value, 'actual': actual, 'error': value - actual,
                             'absolute_error': abs(value - actual), 'packet_sha256': sha(path),
                             'truth_sha256': sha(truth_path),
                             'parameters': packet['cho_model']['parameters'] if method == 'mechanistic' else None})
    if len(rows) != 16 * 3 * 2:
        raise ValueError('CHO diagnostic coverage changed')
    summary = []
    for method in ['mechanistic', 'last_value', 'linear_prefix']:
        for field in cho_real.FIELDS:
            selected = [r for r in rows if r['method'] == method and r['field'] == field]
            summary.append({'method': method, 'field': field, 'n_cultures': len(selected),
                            'MAE': float(np.mean([r['absolute_error'] for r in selected])),
                            'mean_signed_error': float(np.mean([r['error'] for r in selected]))})
    # Check whether the declared limiting nutrient actually becomes exhausted.
    target_glucose = [r['actual'] for r in rows if r['method'] == 'mechanistic' and r['field'] == cho_real.FIELDS[1]]
    value = {'classification': 'retrospective_development_diagnosis_not_new_validation',
             'model_reproduction_checked': True, 'cultures': 16, 'conditions': 8,
             'summary': summary, 'rows': rows,
             'glucose_target_range_g_l': [min(target_glucose), max(target_glucose)],
             'mechanistic_limitations': ['Only glucose-limited growth and constant death/maintenance are represented.',
                 'Other nutrients, inhibition, environmental effects and changing death kinetics are absent.',
                 'These data cannot uniquely identify which omitted mechanism caused the errors.',
                 'Simple empirical baselines are diagnostics, not newly held-out performance.'],
             'qualification': 'No real manufacturing/intervention qualification established; do not rerun GLM on these same cases to claim external validation.'}
    dump(output / 'cho-diagnosis.json', value)
    lines = ['# Retained-failure and real CHO diagnosis', '',
             f'Recorded model-informed infeasible operating choices: **{len(failures)}**. This is the red baseline; old decisions are unchanged.', '',
             'CHO model outputs were recomputed and matched their frozen predictions. Previously inspected cases remain development data.', '',
             '| Method | Target | MAE | Mean signed error |', '|---|---|---:|---:|']
    lines += [f"| {r['method']} | {r['field']} | {r['MAE']:.4f} | {r['mean_signed_error']:.4f} |" for r in summary]
    lines += ['', 'Units: million viable cells/mL and g glucose/L. No causal attribution to a particular omitted mechanism is established.',
              'The prior negative agent A/B result is retained. Numerical consistency does not qualify this model as a decision authority.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'recorded_unsafe_choices': len(failures), 'CHO_summary': summary}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--assert-old-safe', action='store_true')
    a = p.parse_args()
    diagnose(a.output)
    if a.assert_old_safe:
        value = json.loads((a.output / 'stopping-baseline.json').read_text())
        assert value['failure_count'] == 0, f"{value['failure_count']} recorded choices fail feasibility-first policy"
