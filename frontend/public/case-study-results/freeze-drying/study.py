"""Reproducible synthetic study; evaluator access is confined to generation/scoring.

The public predict function reads only its supplied packet. No measured factory
outcome, calibrated risk probability or independently validated physics is implied.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.optimize import least_squares

from src.lifesci.lyophilization.case import receiving_config
from src.lifesci.lyophilization.model import simulate as legacy
from src.lifesci.lyophilization.heterogeneous import simulate as population

VERSION = 'lyo-comparison-20261102-v1'
ACTIONS = [{'id': 'keep', 'shelf_temperature_c': None},
           {'id': 'cool', 'shelf_temperature_c': -30.},
           {'id': 'moderate', 'shelf_temperature_c': -26.},
           {'id': 'warm', 'shelf_temperature_c': -22.},
           {'id': 'characterize', 'shelf_temperature_c': None}]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def dump(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def write_new_directory(path):
    Path(path).mkdir(parents=True, exist_ok=False)


def validate_packet(packet):
    cutoff = packet['cutoff_h']
    for row in packet['observations']:
        if row['time_h'] > cutoff or row.get('available_at_h', row['time_h']) > cutoff:
            raise ValueError('observation exceeds evidence cutoff')


def action_config(packet, action_id):
    config = deepcopy(packet['config'])
    if action_id == 'keep': return config
    allowed = {a['id']: a['shelf_temperature_c'] for a in packet['allowed_actions']}
    if action_id not in allowed or allowed[action_id] is None:
        raise ValueError('not a manufacturing action')
    cutoff = packet['cutoff_h']
    pc = next(s['chamber_pressure_pa'] for s in reversed(config['schedule']) if s['time_h'] <= cutoff)
    config['schedule'] = [s for s in config['schedule'] if s['time_h'] < cutoff]
    config['schedule'].append({'time_h': cutoff, 'shelf_temperature_c': allowed[action_id], 'chamber_pressure_pa': pc})
    return config


def target(result):
    capacity = result['first_capacity_h']
    thermal = result['first_critical_h']
    return {'completion_time_h': result['completion_time_h'] if capacity is None else None,
            'thermal_warning': bool(thermal is not None) if capacity is None else True if thermal is not None and thermal < capacity else None,
            'capacity_warning': capacity is not None,
            'capacity_censored': capacity is not None}


def feasible(result):
    return (result['completion_time_h'] is not None and result['first_capacity_h'] is None
            and result['first_critical_h'] is None)


def score(submission, outcomes, load):
    truth = target(outcomes['keep'])
    result = {'execution_completed': submission is not None, 'truth': truth,
              'completion_eligible': truth['completion_time_h'] is not None}
    for key in ('thermal', 'capacity'):
        observed = truth[key+'_warning']
        predicted = submission.get(key+'_warning') if submission else None
        result[key] = ('execution_failed' if submission is None else 'censored' if observed is None
                       else 'abstain' if predicted is None else ('T' if predicted == observed else 'F')+('P' if predicted else 'N'))
    predicted = submission.get('completion_time_h') if submission else None
    result['completion_absolute_error_h'] = abs(predicted-truth['completion_time_h']) if predicted is not None and result['completion_eligible'] else None
    result['completion_signed_error_h'] = predicted-truth['completion_time_h'] if result['completion_absolute_error_h'] is not None else None
    result['hindsight_capacity_invalid_completion'] = bool(submission and truth['capacity_censored'] and predicted is not None)
    action = submission.get('action_id') if submission else None
    result['selection_made'] = action in outcomes
    result['selected_feasible'] = action in outcomes and feasible(outcomes[action])
    result['unsafe_selection'] = bool(result['selection_made'] and not result['selected_feasible'])
    result['abstained_with_hindsight_feasible_action'] = action == 'characterize' and any(feasible(r) for r in outcomes.values())
    result['throughput_vials_h'] = load/outcomes[action]['completion_time_h'] if result['selected_feasible'] else 0.
    available = [load/r['completion_time_h'] for r in outcomes.values() if feasible(r)]
    result['best_grid_throughput_vials_h'] = max(available, default=0.)
    result['keep_throughput_vials_h'] = load/outcomes['keep']['completion_time_h'] if feasible(outcomes['keep']) else 0.
    result['feasible_selection_regret_vials_h'] = max(available)-result['throughput_vials_h'] if result['selected_feasible'] else None
    return result


def _simulate(config, arm):
    return (legacy if arm == 'B' else population)(config)


def _interpolate(run, times, field):
    rows = run['trajectory']
    key = 'interface_temperature_c' if field == 'product_temperature_c' and field not in rows[0] else field
    return np.interp(times, [r['time_h'] for r in rows], [r[key] for r in rows])


def _pressure_mismatch(packet):
    return any(abs(r['chamber_pressure_pa']-next(s['chamber_pressure_pa'] for s in reversed(packet['config']['schedule']) if s['time_h']<=r['time_h'])) > .5 for r in packet['observations'])


@lru_cache(maxsize=128)
def _fit(packet_json, arm):
    packet = json.loads(packet_json); validate_packet(packet)
    observations = packet['observations']
    config = deepcopy(packet['config'])
    if not observations:
        return {'kv_scale': 1., 'rp_scale': 1., 'status': 'nominal_pretransfer_no_receiving_measurements', 'nfev': 0}
    if _pressure_mismatch(packet):
        return {'kv_scale': 1., 'rp_scale': 1., 'status': 'invalid_observed_pressure_control', 'nfev': 0}
    config['duration_h'] = packet['cutoff_h']
    config['schedule'] = [s for s in config['schedule'] if s['time_h'] < config['duration_h']]
    times = [r['time_h'] for r in observations]
    def residual(x):
        candidate = deepcopy(config)
        candidate['equipment']['kv_scale'], candidate['product']['rp_scale'] = x.tolist()
        run = _simulate(candidate, arm)
        if run['numerical_status'] != 'completed': raise ValueError('calibration numerical failure')
        if any(v['constraint'] in ('vapor_capacity','condenser_ice_capacity') and v['first_time_h']<=max(times) for v in run['violations']):
            return np.full(2*len(times),1000.)
        # Same two observed channels and scales for both model arms. No future rows.
        return np.r_[(_interpolate(run, times, 'product_temperature_c')-[r['product_temperature_c'] for r in observations])/.12,
                     (_interpolate(run, times, 'remaining_ice_kg_per_vial')-[r['remaining_ice_kg_per_vial'] for r in observations])/1e-5]
    fit = least_squares(residual, [1., 1.], bounds=([.6, .6], [1.8, 1.8]),
                        loss='soft_l1', max_nfev=16, diff_step=.002, xtol=1e-5, ftol=1e-5, gtol=1e-5)
    return {'kv_scale': float(fit.x[0]), 'rp_scale': float(fit.x[1]), 'status': 'invalid_calibration_domain' if np.all(fit.fun==1000.) else 'converged' if fit.success else 'iteration_limit',
            'nfev': fit.nfev, 'normalized_residual_rms': float(np.sqrt(np.mean(fit.fun**2))),
            'interpretation': 'effective parameters from early thermometry and mass only; not a verified cause or unique parameter identification'}


@lru_cache(maxsize=512)
def _predict(packet_json, arm, action_id):
    if arm not in ('B', 'C'): raise ValueError('physical tool only in B/C')
    packet = json.loads(packet_json); validate_packet(packet)
    config = action_config(packet, action_id)
    fitted = _fit(packet_json, arm)
    config['equipment']['kv_scale'] = fitted['kv_scale']
    config['product']['rp_scale'] = fitted['rp_scale']
    run = _simulate(config, arm)
    if run['numerical_status'] != 'completed': raise ValueError('forward numerical failure: '+str(run.get('numerical_error')))
    rows = run['trajectory']
    capacity_time = min((v['first_time_h'] for v in run['violations'] if v['constraint'] in ('vapor_capacity','condenser_ice_capacity')), default=None)
    thermal_time = min((v['first_time_h'] for v in run['violations'] if v['constraint'] == 'critical_temperature'), default=None)
    # A recorded pressure deviation independently falsifies prescribed-pressure control.
    pressure_mismatch = _pressure_mismatch(packet)
    invalid_fit = fitted['status'].startswith('invalid')
    invalid = capacity_time is not None or pressure_mismatch or invalid_fit
    summary = {'action_id': action_id, 'model_version': run['model_version'], 'calibration': fitted,
               'capacity_warning': capacity_time is not None or pressure_mismatch,
               'thermal_warning': bool(thermal_time is not None),
               'completion_time_h': run['completion_time_h'],
               'minimum_critical_margin_c': run['minimum_critical_margin_c'],
               'minimum_capacity_margin_kg_h': run['minimum_capacity_margin_kg_h'],
               'warnings': run['warnings'], 'prediction_valid_until_h': capacity_time,
               'measured_pressure_mismatch': pressure_mismatch,
               'trajectory': [{k:r[k] for k in ('time_h','remaining_ice_kg_per_vial','chamber_pressure_pa','sublimation_kg_h')}
                              | {'product_temperature_c':r.get('product_temperature_c',r.get('interface_temperature_c'))}
                              for r in rows[::max(1,len(rows)//18)]],
               'diagnostic_completion_time_h': run['completion_time_h'],
               'applicability': 'prescribed_pressure_invalid' if invalid else 'within_declared_model_domain'}
    # SAME applicability policy for both models: isolates structural model difference.
    if invalid:
        summary['completion_time_h'] = None
        if pressure_mismatch or invalid_fit or thermal_time is None or (capacity_time is not None and thermal_time>=capacity_time):
            summary['thermal_warning'] = None
        summary['trajectory'] = [r for r in summary['trajectory'] if capacity_time is not None and r['time_h'] < capacity_time and not pressure_mismatch]
    summary['nominal_feasible'] = (not invalid and thermal_time is None and run['completion_time_h'] is not None)
    return summary


def predict(packet, arm, action_id='keep'):
    return deepcopy(_predict(json.dumps(packet,sort_keys=True),arm,action_id))


def verify_dataset(dataset):
    dataset=Path(dataset)
    status=json.loads((dataset/'generation-status.json').read_text())
    if status['status']!='complete':
        raise ValueError('dataset generation incomplete')
    manifest=json.loads((dataset/'manifest.json').read_text())
    if digest(manifest)!=status['manifest_sha256']:
        raise ValueError('manifest hash mismatch')
    for name,expected in manifest.items():
        if hashlib.sha256((dataset/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('dataset hash mismatch: '+name)
    root=Path(__file__).resolve().parents[3]
    for name,expected in json.loads((dataset/'protocol.json').read_text())['code_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('frozen implementation changed: '+name)
    return {'files_verified':len(manifest),'manifest_sha256':digest(manifest)}


def deterministic(packet, arm):
    predictions = {a['id']:predict(packet,arm,a['id']) for a in ACTIONS if a['id']!='characterize'}
    usable = [p for p in predictions.values() if p['nominal_feasible']]
    chosen = min(usable, key=lambda p:p['completion_time_h'])['action_id'] if usable else 'characterize'
    keep = predictions['keep']
    return {k:keep[k] for k in ('completion_time_h','thermal_warning','capacity_warning')} | {'action_id':chosen}, predictions


def generate(output, *, seed=20261102, replicates=4):
    from benchmarks.physics_value.lyo_reference import reference
    output=Path(output);write_new_directory(output)
    root=Path(__file__).resolve().parents[3]
    paths=[Path(__file__),root/'backend/src/lifesci/lyophilization/heterogeneous.py',root/'backend/src/lifesci/lyophilization/model.py',root/'backend/benchmarks/physics_value/lyo_reference.py']
    protocol={'version':VERSION,'seed':seed,'replicates_per_family':replicates,'status':'frozen_before_generation',
              'issue':'https://github.com/YalmanchiliTejas/BioDemo/issues/1','cases':6*replicates,'tasks':['forecast','pretransfer'],
              'arms':['A','B','C'],'actions':ACTIONS,'scope':'exploratory synthetic; shared constitutive physics; no plant validation',
              'treatment':'same raw observations and numerical characterization for all; executable old/new physical models only B/C',
              'reference_post_capacity':'completion and subsequent thermal outcomes censored; arbitrary reference pressure response',
              'fit':'two-channel soft_l1, scales .12 C and 1e-5 kg, bounds .6..1.8, initial 1/1, max_nfev16; no fit for pretransfer',
              'applicability_policy':'identical B/C: no valid completion after predicted overload or observed pressure discrepancy; invalid-domain fits prohibited',
              'case_sampling':'six deliberately balanced authored families; not manufacturing prevalence',
              'metrics':['completion MAE and coverage','thermal/capacity confusion and abstentions','selected feasibility and coverage','unsafe selections','feasible regret','throughput vs KEEP','cost/runtime'],
              'inference_budget_usd':10,'code_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    dump(output/'protocol.json',protocol)
    dump(output/'generation-status.json',{'status':'running'})
    rng=np.random.default_rng(seed); catalogue=[]
    families=['nominal','heat_transfer','product_resistance','capacity','sensor_bias','combined']
    for family in families:
        for replicate in range(replicates):
            ident='LYO-'+hashlib.sha256(f'{seed}/{family}/{replicate}'.encode()).hexdigest()[:10]
            load=int(rng.choice([4000,6500,9000,11000]))
            capacity=float(rng.uniform(1.1,1.7))
            config=receiving_config(shelf_c=float(rng.uniform(-33,-30)),load_vials=load,capacity_kg_h=capacity)
            config['duration_h']=90.
            config['schedule'].append({'time_h':8.,'shelf_temperature_c':float(rng.choice([-26,-24,-22,-20,-18])),'chamber_pressure_pa':8.})
            config['populations']=[{'weight':.8,'kv_scale':.95,'rp_scale':1.05},{'weight':.2,'kv_scale':1.20,'rp_scale':.90}]
            config['thermal']={'vial_heat_capacity_j_k':3.,'initial_equilibrium':True}
            mechanism={'kv_scale':float(rng.uniform(.97,1.03)),'rp_scale':float(rng.uniform(.97,1.03)),'capacity_scale':float(rng.uniform(.97,1.03))}
            bias=0.
            if family in ('heat_transfer','combined'): mechanism['kv_scale']*=float(rng.uniform(1.15,1.35))
            if family in ('product_resistance','combined'): mechanism['rp_scale']*=float(rng.uniform(1.18,1.40))
            if family in ('capacity','combined'): mechanism['capacity_scale']*=float(rng.uniform(.50,.75))
            if family=='sensor_bias': bias=float(rng.choice([-1.,1.]))*.7
            actual=reference(config,mechanism)
            early=[]
            for row in actual['trajectory']:
                if row['time_h']<=6 and abs(row['time_h']*2-round(row['time_h']*2))<1e-6:
                    early.append({k:row[k] for k in ('time_h','available_at_h','product_temperature_c','remaining_ice_kg_per_vial','chamber_pressure_pa')})
                    early[-1]['product_temperature_c']+=bias+float(rng.normal(0,.08))
                    early[-1]['remaining_ice_kg_per_vial']=max(0.,early[-1]['remaining_ice_kg_per_vial']+float(rng.normal(0,4e-6)))
                    early[-1]['chamber_pressure_pa']+=float(rng.normal(0,.04))
            for task,cutoff in [('forecast',6.),('pretransfer',0.)]:
                packet={'case_id':ident,'task':task,'cutoff_h':cutoff,'config':config,'observations':early if cutoff else [],
                        'allowed_actions':ACTIONS,'objective':'Forecast KEEP completion and thermal/capacity violations; choose highest primary-drying throughput among feasible actions, or characterize. No real equipment execution.',
                        'evidence_scope':'Synthetic characterization and synthetic observations. Population factors are approximate characterization, not exact receiving truth. Thermal channel is weighted lump/interface temperature, not bottom thermometry. Future schedule is a known plan.',
                        'unknowns':['effective receiving heat/product resistance shifts','actual receiving capacity','possible thermometry bias'],
                        'constraints':'Any past thermal/capacity excursion invalidates whole-batch rescue. Characterize earns no throughput. No post-overload physical forecast; primary drying only.'}
                validate_packet(packet);dump(output/'public'/ident/(task+'.json'),packet)
                outcomes={'keep':actual}
                for action in ACTIONS:
                    if action['id'] not in ('keep','characterize'):outcomes[action['id']]=reference(action_config(packet,action['id']),mechanism)
                dump(output/'evaluator'/ident/(task+'.json'),{'family':family,'mechanism':mechanism,'temperature_bias_c':bias,'outcomes':outcomes})
            catalogue.append(ident)
            print(json.dumps({'generated':len(catalogue),'of':6*replicates}),flush=True)
    dump(output/'evaluator/catalogue.json',catalogue)
    manifest={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*.json') if p.name!='generation-status.json'}
    dump(output/'manifest.json',manifest);dump(output/'generation-status.json',{'status':'complete','cases':len(catalogue),'manifest_sha256':digest(manifest)})


def evaluate_models(dataset, output):
    dataset=Path(dataset);output=Path(output);write_new_directory(output)
    dump(output/'verification.json',verify_dataset(dataset))
    records=[]
    for path in sorted((dataset/'public').glob('*/*.json')):
        packet=json.loads(path.read_text());truth=json.loads((dataset/'evaluator'/path.parent.name/path.name).read_text())
        for arm in ('B','C'):
            started=time.monotonic()
            try:
                submission,predictions=deterministic(packet,arm)
                error=None
            except Exception as exc:
                submission,predictions,error=None,{},str(exc)
            record={'case_id':packet['case_id'],'task':packet['task'],'arm':arm,'family':truth['family'],
                    'submission':submission,'predictions':predictions,'error':error,'wall_seconds':time.monotonic()-started,
                    'score':score(submission,truth['outcomes'],packet['config']['load_vials'])}
            dump(output/packet['case_id']/packet['task']/(arm+'.json'),record);records.append(record)
        print(json.dumps({'model_packets':len(records)//2}),flush=True)
    dump(output/'results.json',records)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['generate','models'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--dataset',type=Path)
    parser.add_argument('--seed',type=int,default=20261102);parser.add_argument('--replicates',type=int,default=4)
    args=parser.parse_args()
    if args.command=='generate':generate(args.output,seed=args.seed,replicates=args.replicates)
    else:evaluate_models(args.dataset,args.output)
