"""Separate, prospectively frozen factorial supplement; never invokes an AI.

Motivated after inspecting primary-study event support. This is an intended-use
challenge, not another independent holdout or evidence of plant effectiveness.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from itertools import product
import json
from pathlib import Path
import platform
import time

import numpy as np
import scipy

from src.lifesci.lyophilization.case import receiving_config
from benchmarks.physics_value.lyo_reference import reference
from . import study

VERSION = 'lyo-factorial-supplement-1'
SHELVES = [-28., -24., -20., -16.]
LOADS = [4000, 11000]
CAPACITIES = [.4, 1.49]
HIDDEN_KV = [1., 1.25]
LABELS = ('TP', 'TN', 'FP', 'FN', 'abstain', 'censored', 'execution_failed', 'reference_failed')


def cases():
    """Enumerate the complete fixed factorial without computing any outcome."""
    result = []
    for number, (shelf, load, capacity, kv) in enumerate(product(SHELVES, LOADS, CAPACITIES, HIDDEN_KV), 1):
        identifier = f'LYO-STRESS-{number:02d}'
        config = receiving_config(shelf_c=shelf, load_vials=load, capacity_kg_h=capacity)
        config['duration_h'] = 90.
        config['populations'] = [{'weight': .8, 'kv_scale': .95, 'rp_scale': 1.05},
                                 {'weight': .2, 'kv_scale': 1.20, 'rp_scale': .90}]
        config['thermal'] = {'vial_heat_capacity_j_k': 3., 'initial_equilibrium': True}
        packet = {'case_id': identifier, 'task': 'pretransfer', 'cutoff_h': 0.,
                  'config': config, 'observations': [],
                  'allowed_actions': [{'id': 'keep', 'shelf_temperature_c': None}],
                  'objective': 'Forecast KEEP completion and thermal/capacity warnings; no action selection.',
                  'evidence_scope': 'Synthetic nominal characterization; no receiving observations. The effective receiving Kv shift is unknown.'}
        result.append({'case_id': identifier, 'packet': packet,
                       'factors': {'shelf_temperature_c': shelf, 'load_vials': load,
                                   'vapor_capacity_kg_h': capacity, 'hidden_kv_scale': kv},
                       'mechanism': {'kv_scale': kv, 'rp_scale': 1., 'capacity_scale': 1.}})
    return result


def assess(prediction, actual):
    """Reuse primary censoring/scoring, without reporting any action objective."""
    if actual is None:
        return {'truth': None, 'completion_eligible': None,
                'completion_absolute_error_h': None, 'completion_signed_error_h': None,
                'thermal': 'reference_failed', 'capacity': 'reference_failed',
                'hindsight_capacity_invalid_completion': False}
    submission = ({key: prediction[key] for key in ('completion_time_h', 'thermal_warning', 'capacity_warning')}
                  if prediction is not None else None)
    scored = study.score(submission, {'keep': actual}, 1)
    return {key: scored[key] for key in ('truth', 'completion_eligible', 'completion_absolute_error_h',
                                        'completion_signed_error_h', 'thermal', 'capacity',
                                        'hindsight_capacity_invalid_completion')}


def aggregate(records, arm):
    scored = [record['models'][arm]['score'] for record in records]
    eligible = [row for row in scored if row['completion_eligible'] is True]
    errors = [row['completion_absolute_error_h'] for row in eligible if row['completion_absolute_error_h'] is not None]
    signed = [row['completion_signed_error_h'] for row in eligible if row['completion_signed_error_h'] is not None]
    result = {'planned': len(records),
              'numerically_completed': sum(record['models'][arm]['error'] is None for record in records),
              'numerical_failures': sum(record['models'][arm]['error'] is not None for record in records),
              'completion_eligible': len(eligible), 'completion_predictions': len(errors),
              'completion_prediction_coverage': len(errors)/len(eligible) if eligible else None,
              'completion_mae_h': float(np.mean(errors)) if errors else None,
              'completion_signed_error_h': float(np.mean(signed)) if signed else None,
              'hindsight_capacity_invalid_completion': sum(row['hindsight_capacity_invalid_completion'] for row in scored)}
    for kind in ('thermal', 'capacity'):
        counts = Counter(row[kind] for row in scored)
        truths = [row['truth'][kind+'_warning'] for row in scored if row['truth'] is not None]
        result[kind] = {label: counts[label] for label in LABELS}
        result[kind].update(truth_positive=sum(value is True for value in truths),
                            truth_negative=sum(value is False for value in truths),
                            truth_censored=sum(value is None for value in truths))
    return result


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(output):
    output = Path(output)
    status = json.loads((output/'status.json').read_text())
    if status['status'] != 'complete':
        raise ValueError('supplement execution incomplete')
    manifest = json.loads((output/'manifest.json').read_text())
    if study.digest(manifest) != status['manifest_sha256']:
        raise ValueError('manifest hash mismatch')
    for name, expected in manifest.items():
        if _hash(output/name) != expected:
            raise ValueError('artifact hash mismatch: '+name)
    protocol = json.loads((output/'protocol.json').read_text())
    root = Path(__file__).resolve().parents[3]
    for name, expected in protocol['source_sha256'].items():
        if _hash(root/name) != expected:
            raise ValueError('source hash mismatch: '+name)
    return {'verified': True, 'files_verified': len(manifest), 'manifest_sha256': study.digest(manifest)}


def markdown(summary):
    lines = ['# Supplementary freeze-drying factorial challenge', '',
             'Post hoc motivated by limited event support in the primary study; this complete grid was prospectively frozen before its numerical outcomes. '
             'Its results are separate from the primary study and agent campaign. No AI calls or manufacturing actions were performed.', '',
             'The 32 cases cross shelf temperatures −28/−24/−20/−16 °C, loads 4,000/11,000 vials, '
             'capacities 0.40/1.49 kg/h, and hidden receiving Kv multipliers 1/1.25. '
             'All use a constant shelf setpoint from time zero, 8 Pa prescribed pressure, 90 h horizon, and equilibrium initialization. '
             'These are idealized conditions, not realistic startup sequences.', '',
             'B and C receive the same nominal public characterization and no receiving observations. '
             'The effective Kv multiplier is hidden and cannot be identified from these inputs. Rp and capacity multipliers equal one. '
             'Both models use the existing pretransfer KEEP predictor without fitting and the same applicability gate.', '',
             '| Model | Planned | Numerical failures | Completion eligible | Predicted | Coverage | Completion MAE (h) |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    def formatted(value):
        return '—' if value is None else f'{value:.4f}'
    for arm, row in summary['arms'].items():
        lines.append(f'| {arm} | {row["planned"]} | {row["numerical_failures"]} | {row["completion_eligible"]} | '
                     f'{row["completion_predictions"]} | {formatted(row["completion_prediction_coverage"])} | {formatted(row["completion_mae_h"])} |')
    for kind in ('thermal', 'capacity'):
        lines += ['', f'## {kind.capitalize()} warnings', '',
                  '| Model | Truth positive | Truth negative | Truth censored | TP | TN | FP | FN | Abstain | Censored | Model failure | Reference failure |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        for arm, group in summary['arms'].items():
            row = group[kind]
            values = [arm, row['truth_positive'], row['truth_negative'], row['truth_censored'], *[row[key] for key in LABELS]]
            lines.append('| '+' | '.join(map(str, values))+' |')
    lines += ['', '## Interpretation', '',
              'Completion error is conditional on a reference-valid completed trajectory and a numerical prediction; '
              'coverage divides predictions by all reference-eligible cases, including model failures. '
              'Thermal outcomes at or after capacity overload are censored. Reference failures remain separate from negative outcomes. '
              'Diagnostic post-overload trajectories are retained as raw evidence, not physical forecast targets.', '',
              'The evaluator and models share constitutive laws. Its invented pressure response cannot validate post-overload physics. '
              'This challenge expands behavioral coverage; it does not establish manufacturing prevalence, independent physical validation, '
              'agent benefit, general superiority, or process effectiveness. Hidden Kv shifts can cause forecast misses through unavailable characterization. '
              'No tuning follows these results. No statistical significance or manufacturing risk probability is inferred.', '',
              f'Reference numerical failures: {summary["reference_failures"]}/{summary["cases"]}. '
              'Per-case results include errors, predictions and scores. Full reference curves are in `evaluator/`; '
              '`case-plan.json` contains every frozen input and evaluator mechanism. `summary.json` also separates the two hidden-Kv strata.', '']
    return '\n'.join(lines)


def run(output):
    output = Path(output)
    study.write_new_directory(output)
    root = Path(__file__).resolve().parents[3]
    names = ['backend/benchmarks/lyo_study/stress.py', 'backend/benchmarks/lyo_study/study.py',
             'backend/benchmarks/physics_value/lyo_reference.py',
             'backend/src/lifesci/lyophilization/model.py', 'backend/src/lifesci/lyophilization/heterogeneous.py',
             'backend/src/lifesci/lyophilization/case.py', 'backend/src/lifesci/ids.py']
    planned = cases()
    protocol = {'version': VERSION, 'status': 'frozen_before_any_supplement_simulation',
                'frozen_at_utc': datetime.now(timezone.utc).isoformat(), 'cases': 32,
                'motivation': 'Post hoc primary-study coverage gap; prospectively frozen complete factorial supplement, never pooled.',
                'factor_levels': {'shelf_temperature_c': SHELVES, 'load_vials': LOADS,
                                  'vapor_capacity_kg_h': CAPACITIES, 'hidden_kv_scale': HIDDEN_KV},
                'design': 'Full factorial, no random sampling, no outcome-based exclusion or tuning.',
                'task': 'pretransfer KEEP only', 'arms': ['B', 'C'], 'fitting': 'none; no receiving observations',
                'initialization': 'per-population equilibrium; constant setpoint from t=0, no startup ramp',
                'censoring': 'Existing study.target: no completion after overload; thermal requires onset strictly before overload.',
                'metrics': ['truth class support', 'warning confusion/abstentions', 'reference/model failures',
                            'completion MAE and signed error conditional on prediction', 'completion coverage over eligible reference cases'],
                'hidden_shift_interpretation': 'Receiving Kv multiplier is unknown to predictors; misses need not imply inferable model error.',
                'reference_limitation': 'Shared constitutive laws, unvalidated pressure response; no plant validation.',
                'case_plan_sha256': study.digest(planned),
                'source_sha256': {name: _hash(root/name) for name in names},
                'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__}}
    study.dump(output/'protocol.json', protocol)
    study.dump(output/'case-plan.json', planned)
    study.dump(output/'status.json', {'status': 'running', 'protocol_sha256': _hash(output/'protocol.json')})
    records = []
    for case in planned:
        actual, reference_error = None, None
        started = time.monotonic()
        try:
            actual = reference(case['packet']['config'], case['mechanism'])
            json.dumps(actual, allow_nan=False)
        except Exception as exc:
            actual, reference_error = None, f'{type(exc).__name__}: {exc}'
        study.dump(output/'evaluator'/(case['case_id']+'.json'), {'result': actual, 'error': reference_error})
        record = {'case_id': case['case_id'], 'factors': case['factors'],
                  'reference_error': reference_error, 'reference_wall_seconds': time.monotonic()-started, 'models': {}}
        for arm in ('B', 'C'):
            prediction, error = None, None
            started = time.monotonic()
            try:
                prediction = study.predict(case['packet'], arm, 'keep')
                json.dumps(prediction, allow_nan=False)
            except Exception as exc:
                prediction, error = None, f'{type(exc).__name__}: {exc}'
            record['models'][arm] = {'prediction': prediction, 'error': error,
                                     'wall_seconds': time.monotonic()-started, 'score': assess(prediction, actual)}
        records.append(record)
        study.dump(output/'cases'/(case['case_id']+'.json'), record)
        print(json.dumps({'stress_cases_completed': len(records), 'planned': len(planned)}), flush=True)
    summary = {'version': VERSION, 'cases': len(records), 'scope': 'Separate synthetic factorial supplement; no AI or plant efficacy claim.',
               'protocol_sha256': _hash(output/'protocol.json'),
               'reference_failures': sum(row['reference_error'] is not None for row in records),
               'arms': {arm: aggregate(records, arm) for arm in ('B', 'C')},
               'hidden_kv_strata': {str(kv): {arm: aggregate([row for row in records if row['factors']['hidden_kv_scale'] == kv], arm)
                                             for arm in ('B', 'C')} for kv in HIDDEN_KV}}
    study.dump(output/'results.json', records)
    study.dump(output/'summary.json', summary)
    (output/'report.md').write_text(markdown(summary))
    manifest = {str(path.relative_to(output)): _hash(path) for path in sorted(output.rglob('*'))
                if path.is_file() and path.name not in ('manifest.json', 'status.json')}
    study.dump(output/'manifest.json', manifest)
    study.dump(output/'status.json', {'status': 'complete', 'cases': len(records),
                                    'manifest_sha256': study.digest(manifest),
                                    'completed_at_utc': datetime.now(timezone.utc).isoformat()})
    verify(output)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.output), indent=2))
