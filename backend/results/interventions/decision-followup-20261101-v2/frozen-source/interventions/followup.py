"""Frozen GLM decision follow-up with feasibility-first policy and model mismatch.

No physical outcome, qualified product yield, or industrial transfer is implied.
Run inference only through scripts/run_bounded_agent_benchmark.py admission gate.
"""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import numpy as np
from src.lifesci.envfile import load_env_file
from src.lifesci.fermentation.research_route import hosted_research_profile
from src.paths import DEFAULT_PRIME_BUNDLE
from benchmarks.external_simulators.experiment import dump, sha
from benchmarks.external_simulators.run_agents import isolation
from . import run_agents
from .model import SensitivityReceivingModel
from .pensim import ACTIONS, simulate, outcomes, optimizer
from .session import InterventionSession

REPO = Path(__file__).resolve().parents[3]
MODEL = 'modal/zai-org/GLM-5.3'
POLICY = run_agents.SYSTEM + '''
Decision priorities, in this order:
1. The post-decision DO >= 2 mg/L limit is a HARD constraint at every remaining simulated time. Product mass never compensates for violating it.
2. Do not select an operating plan that available evidence predicts violates that limit. In particular, a centrally predicted infeasible plan is NOT justified by one favorable member of an uncalibrated sensitivity set. Those members are not probabilities.
3. If no operating plan can be justified as meeting the constraint, submit stop and explain the evidence gap or infeasibility. Stop is an available decision, not a tool failure. Prefer a supported feasible operating plan over an unnecessary stop. Stable normal observations do not by themselves require a stop.
4. Among supported feasible plans, retain product mass. Inspect alternatives using available tools; account for forecast error and model mismatch. No guarantee of physical safety is established.
Observation lists use lossless tables: columns define each row; missing values are null. For columns present in dictionaries, a row entry is an integer index into that column's dictionary. All original observations and assay availability times are preserved. The model tool, if available, decodes the same tables. Decode indices before numerical analysis.
'''


def table(rows):
    columns = sorted({key for row in rows for key in row})
    dictionaries = {}
    lookups = {}
    for key in columns:
        if key in ['field', 'unit', 'source_batch', 'measurement_kind', 'time_h', 'available_at_h']:
            values = list(dict.fromkeys(row[key] for row in rows if key in row))
            dictionaries[key] = values
            lookups[key] = {v: i for i, v in enumerate(values)}
    return {'columns': columns, 'dictionaries': dictionaries,
            'rows': [[lookups[key][row[key]] if key in lookups and key in row else row.get(key)
                      for key in columns] for row in rows]}


def expand(value):
    return [{key: value.get('dictionaries', {})[key][v] if key in value.get('dictionaries', {}) else v
             for key, v in zip(value['columns'], row) if v is not None} for row in value['rows']]


def unpack(packet):
    result = deepcopy(packet)
    for key in ['source_observations', 'receiving_observations']:
        if isinstance(result[key], dict):
            result[key] = expand(result[key])
    return result


class TablePredictor:
    def __init__(self, predictor):
        self.predictor = predictor

    def __call__(self, packet, action):
        return self.predictor(unpack(packet), action)


class TableSession(InterventionSession):
    def public_packet(self):
        packet = super().public_packet()
        for key in ['source_observations', 'receiving_observations']:
            packet[key] = table(packet[key])
        return packet


def freeze(root, pensim=None):
    if root.exists():
        raise ValueError('Never overwrite a study')
    root.mkdir(parents=True)
    prior = REPO / 'backend/results/interventions/frozen-ab-20261029'
    old = json.loads((prior / 'protocol.json').read_text())
    if pensim:
        # Restored source must match the previously recorded scientific implementation.
        for relative in ['pensimpy/ode/indpensim_ode_py.py', 'pensimpy/peni_env_setup.py']:
            original = str(Path(old['paths']['pensim']) / relative)
            if sha(pensim / relative) != old['code_sha256'][original]:
                raise ValueError('Restored upstream source differs from frozen original')
        old['paths']['pensim'] = str(pensim.resolve())
    source = prior / 'source-qualification.json'
    if not json.loads(source.read_text())['optimizer_converged']:
        raise ValueError('Source fitting failed')
    # Fixed before receiver generation or new GLM outcomes. Cases are not selected by recoverability.
    protocol = {'version': 'decision-followup-20261101-v1',
        'frozen_utc': datetime.now(timezone.utc).isoformat(), 'model': MODEL,
        'hypothesis': 'Adding this imperfect source-calibrated model to the same agent improves constrained simulated decisions.',
        'independent_scenarios': 48, 'repeats': 1, 'planned_agent_sessions': 96,
        'seed_range': [41001, 41048], 'sampling_seed': 20261101,
        'strata': ['normal', 'moderate_loss', 'severe_loss'],
        'transfer_multiplier_ranges': {'normal': [1., 1.], 'moderate_loss': [.5, .6], 'severe_loss': [.4, .5]},
        'receiving_factor_ranges': old['receiving_factor_ranges'],
        'mismatch': 'Odd case indices use continued transfer decay exp(-0.004/h) after onset; even use step-only. Prediction model is unchanged step-only; no future decay flag is shown.',
        'decision_h': 52., 'horizon_h': 96., 'onsets_h': [46., 48., 50.],
        'actions': ACTIONS, 'source_sha256': sha(source), 'paths': old['paths'],
        'system_prompt': POLICY, 'wall_seconds': 180, 'max_model_calls': 8, 'max_output_tokens': 4096,
        'workers': 2, 'representation': 'Lossless column tables; identical A/B evidence; no observations removed.',
        'primary': 'Paired rate of correct constrained decisions: feasible operation if any menu plan feasible; stop otherwise. Failed submissions count incorrect.',
        'secondary': ['violating operation rate', 'correct stop rate', 'unnecessary stop rate',
                      'product mass alongside feasibility', 'constraint-feasible product mass (zero for violations or stops)',
                      'model-only comparison on identical public evidence', 'completion and wall time'],
        'analysis': 'Average repetitions per scenario. Paired bootstrap 20000 draws over scenarios; unadjusted descriptive95% intervals. No case replacement or sample extension. Report all prespecified strata and both mismatch groups.',
        'success_rule': 'Primary benefit supported within this simulator only if lower paired95% bound >0 and no increase in violating-operation rate. Otherwise inconclusive/negative. No empirical manufacturing claim.',
        'scope': 'Exploratory new synthetic decision cases after development diagnosis; shared equation family; selected uncertainty ranges are assumptions. Not independent physical validation or end-to-end product evaluation.'}
    sources = list(Path(__file__).parent.glob('*.py')) + list(Path(__file__).parent.glob('*.mjs'))
    sources += [REPO / 'backend/scripts/run_bounded_agent_benchmark.py']
    sources += [REPO / 'backend/benchmarks/external_simulators' / n for n in ['upstream.py', 'oxygen.py', 'run_agents.py']]
    sources += [Path(old['paths']['pensim']) / 'pensimpy/ode/indpensim_ode_py.py', Path(old['paths']['pensim']) / 'pensimpy/peni_env_setup.py']
    protocol['code_sha256'] = {str(f.resolve()): sha(f) for f in sources}
    for f in sources:
        target = root / 'frozen-source' / f.parent.name / f.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    shutil.copy2(source, root / 'source-qualification.json')
    dump(root / 'protocol.json', protocol)
    rng = np.random.default_rng(protocol['sampling_seed'])
    cases = []
    for i in range(protocol['independent_scenarios']):
        stratum = protocol['strata'][i % 3]
        hidden = {'seed': 41001 + i, 'factors': {k: float(rng.uniform(*v)) for k, v in protocol['receiving_factor_ranges'].items()},
                  'transfer_multiplier': float(rng.uniform(*protocol['transfer_multiplier_ranges'][stratum])),
                  'disturbance_h': float(rng.choice(protocol['onsets_h'])), 'decision_h': 52.,
                  'kinetics_reference': 'seed0', 'transfer_drift_per_h': -.004 if i % 2 else 0.}
        cases.append({'case_id': f'PF-{41001+i}', 'stratum': stratum,
                      'mismatch': 'continued_decay' if i % 2 else 'step_only', 'hidden': hidden})
    dump(root / 'private-catalogue.json', cases)
    print(json.dumps({'frozen': True, 'protocol_sha256': sha(root / 'protocol.json'), 'cases': len(cases), 'planned_agent_sessions': 96}), flush=True)


def check_frozen(root):
    p = json.loads((root / 'protocol.json').read_text())
    if not all(sha(Path(f)) == h for f, h in p['code_sha256'].items()):
        raise ValueError('Frozen source changed')
    return p


def job(root, item):
    root = Path(root)
    p = check_frozen(root)
    q = json.loads((root / 'source-qualification.json').read_text())
    records = []
    case = item['case_id']
    try:
        # Numerical-domain admission includes the full menu; failures remain coverage failures.
        truths = {52.: {action: outcomes(simulate(p['paths'], **item['hidden'], action=action)) for action in ACTIONS}}
        central = SensitivityReceivingModel(p['paths'], q['final_source_fit'])
        diagnostics = TableSession(p['paths'], item['hidden'], q['source_measurements'])
        predictions = {a: central(unpack(diagnostics.public_packet()), a)['outcome_prediction'] for a in ACTIONS if a != 'stop'}
        model_action = optimizer(predictions)
        model_only = {'action': model_action, 'outcome': truths[52.][model_action], 'predictions': predictions}
        order = ['A', 'B'] if item['hidden']['seed'] % 2 else ['B', 'A']
        for arm in order:
            predictor = TablePredictor(SensitivityReceivingModel(p['paths'], q['final_source_fit'])) if arm == 'B' else None
            session = TableSession(p['paths'], item['hidden'], q['source_measurements'], predictor=predictor)
            record = run_agents.attempt(session, arm, MODEL, root / 'attempts' / case / arm,
                wall_seconds=p['wall_seconds'], system_prompt=p['system_prompt'],
                max_model_calls=p['max_model_calls'], max_output_tokens=p['max_output_tokens'])
            if record.get('evaluation'):
                clock = record['evaluation']['proposal']['decision_time_h']
                if clock not in truths:
                    config = dict(item['hidden'], decision_h=clock)
                    truths[clock] = {a: outcomes(simulate(p['paths'], **config, action=a)) for a in ACTIONS}
                record['menu_any_feasible'] = any(v['post_decision_feasible'] for v in truths[clock].values())
            records.append(record)
        value = {'case_id': case, 'stratum': item['stratum'], 'mismatch': item['mismatch'],
                 'status': 'attempted', 'records': records, 'model_only': model_only,
                 'original_recipe': truths[52.]['keep'], 'private_menu_by_clock': truths}
    except Exception as exc:
        value = {'case_id': case, 'stratum': item['stratum'], 'mismatch': item['mismatch'],
                 'status': 'failed', 'records': records, 'error': type(exc).__name__ + ': ' + str(exc)[:1000]}
    dump(root / 'cases' / (case + '.json'), value)
    return value


def execute(root):
    p = check_frozen(root)
    if (root / 'results.json').exists():
        raise ValueError('No implicit retry/resume of a started study')
    base = os.getenv('BIODEMO_MODAL_BASE_URL', '')
    if not base.startswith('http://127.0.0.1:') or not (root / 'modal-budget-policy.json').exists():
        raise ValueError('Paid dispatch requires the bounded loopback admission gate')
    load_env_file(REPO / 'backend/.env.local')
    profile = hosted_research_profile()
    if not profile or profile.provider + '/' + profile.model != MODEL:
        raise ValueError('Actual saved research model must be Modal GLM-5.3')
    dump(root / 'evaluator/catalogue.json', {'canary': 'private evaluator inaccessible'})
    (root / 'model-library').mkdir(exist_ok=True)
    probe = isolation(root, root / 'isolation/scratch')
    dump(root / 'isolation.json', probe)
    items = json.loads((root / 'private-catalogue.json').read_text())
    results = []
    dump(root / 'results.json', {'status': 'running', 'cases': []})
    with ProcessPoolExecutor(max_workers=p['workers']) as pool:
        futures = [pool.submit(job, str(root), item) for item in items]
        for future in as_completed(futures):
            value = future.result()
            results.append(value)
            dump(root / 'results.json', {'status': 'running', 'cases': results})
            print(json.dumps({'finished_cases': len(results), 'case_id': value['case_id'],
                              'status': value['status'], 'completed_agents': sum(bool(r.get('evaluation')) for r in value['records'])}), flush=True)
    dump(root / 'results.json', {'status': 'complete', 'cases': results, 'protocol_sha256': sha(root / 'protocol.json')})


def preflight(root):
    root.mkdir(parents=True, exist_ok=True)
    dump(root / 'evaluator/catalogue.json', {'canary': 'private evaluator inaccessible'})
    (root / 'model-library').mkdir(exist_ok=True)
    dump(root / 'isolation.json', isolation(root, root / 'scratch'))
    load_env_file(REPO / 'backend/.env.local')
    request = {'type': 'initialize', 'bundle_root': str(DEFAULT_PRIME_BUNDLE), 'cwd': str(root),
               'model': MODEL, 'system_prompt': POLICY, 'prompt': '', 'arm': 'B',
               'max_output_tokens': 4096, 'max_model_calls': 1, 'timeout_seconds': 30,
               'public_schema': {'actions': ['keep', 'stop'], 'forecast_fields': [],
                                 'measurements': ['extra_product_assay']}, 'preflight': True}
    process = subprocess.run(['node', str(Path(__file__).with_name('sdk_intervention.mjs'))],
                             input=json.dumps(request) + '\n', text=True, capture_output=True, timeout=45)
    events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith('{')]
    value = {'returncode': process.returncode, 'events': events,
             'error': process.stderr[-1600:] if process.returncode else None, 'paid_model_requests': 0}
    dump(root / 'sdk-preflight.json', value)
    print(json.dumps(value), flush=True)
    if process.returncode or not any(e.get('status') == 'preflight_passed' for e in events):
        raise ValueError('SDK preflight failed; no paid dispatch')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['freeze', 'run', 'preflight'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--pensim', type=Path)
    args = parser.parse_args()
    if args.phase == 'freeze':
        freeze(args.root.resolve(), args.pensim)
    elif args.phase == 'run':
        execute(args.root.resolve())
    else:
        preflight(args.root.resolve())
