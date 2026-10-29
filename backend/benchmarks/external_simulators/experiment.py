"""Freeze, execute and score an exploratory comparison on external simulators.

The evaluator holds actual-seed trajectories; the agent tool uses seed-zero
nominal trajectories and calibration from completed SOURCE observations only.
No evaluator trajectory, target or chosen-action ranking is a tool response.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np

from .upstream import (MAB_COMMANDS,MAB_NAMES,MAB_UNITS,mab_run,read_mab,pen_run,
                       pen_module)

VERSION='external-simulator-pilot-4-shared-nominal-assumptions'
ACTIONS={'pensim':['keep','feed_down','feed_up','air_up'],
         'mab':['keep','flow_down','flow_up','cool']}
TASKS=['prediction','outcome','transfer']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def sources(pensim,smpl,native):
    return {'pensim':str(pensim.resolve()),'smpl':str(smpl.resolve()),'native':str(native.resolve())}


def scenario(simulator,seed,capability,action,task,paths,*,rtol=1e-7,solver=None,nominal=False,parameter_overrides=None):
    if simulator=='pensim':
        return pen_run(Path(paths['pensim']),Path(paths['native']),seed=seed,action=action,
                       start_h=0. if task=='transfer' else 80.,aeration_factor=capability,
                       rtol=rtol,solver=solver or 'native',hours=96.,nominal=nominal,parameter_overrides=parameter_overrides)
    _,xss,uss=read_mab(Path(paths['smpl']))
    rng=np.random.default_rng(seed)
    initial=xss.copy()
    # This is controlled synthetic initial-culture variation, NOT a biological site label.
    if not nominal:
        for indices in ([0,8],[1,9],[2,10],[3,11],[4,12],[5,13],[6,14]):
            initial[indices]*=float(rng.uniform(.95,1.05))
    initial[16]=36.8
    u=uss.copy();u[:4]*=capability
    if action=='flow_down': u[:4]*=.99
    elif action=='flow_up': u[:4]*=1.01
    elif action=='cool': u[6]-=.5
    elif action!='keep': raise ValueError('unknown mAb action')
    cutoff=0. if task=='transfer' else 6.
    if cutoff:
        initial_part=mab_run(Path(paths['smpl']),initial=initial,command=np.r_[uss[:4]*capability,uss[4:]],
                             hours=cutoff,solver=solver or 'BDF',rtol=rtol)
        initial=np.array([initial_part['terminal'][n] for n in MAB_NAMES])
    result=mab_run(Path(paths['smpl']),initial=initial,command=u,hours=24.-cutoff,
                   solver=solver or 'BDF',rtol=rtol)
    if cutoff:
        for row in result['trace']: row['time_h']+=cutoff
        result['trace']=initial_part['trace']+result['trace'][1:]
        # Objective includes only future product leaving upstream after the decision.
    result.update(seed=seed,capability=capability,action=action,task=task,
                  physical_commands=dict(zip(MAB_COMMANDS,map(float,u))))
    return result


def metrics(simulator,result,*,cutoff=0.):
    if simulator=='pensim':
        rows=[r for r in result['trace'] if r['time_h']>=cutoff]
        return {'product_concentration':result['terminal']['P'],
                'process_indicator':result['terminal']['DO2'],
                'objective':result['terminal']['P'],
                'minimum_indicator':min(r['state']['DO2'] for r in rows),
                'maximum_volume_l':max(r['state']['V'] for r in rows),
                'upstream_do_floor_events':result['audit']['dissolved_oxygen_floor_events']}
    rows=[r for r in result['trace'] if r['time_h']>=cutoff]
    return {'product_concentration':result['terminal']['mAb_reactor'],
            'process_indicator':result['terminal']['viable_cells_reactor'],
            'objective':result['product_mass_mg'],
            'minimum_indicator':min(r['state']['viable_cells_reactor'] for r in rows),
            'maximum_temperature_c':max(r['state']['temperature'] for r in rows)}


def qualify(paths,out):
    """Numerical consistency only; this does not establish experimental accuracy."""
    receipts=[]
    for simulator in ('pensim','mab'):
        try:
            base=scenario(simulator,17,1.,'keep','outcome',paths,rtol=1e-7)
            repeat=scenario(simulator,17,1.,'keep','outcome',paths,rtol=1e-7)
            tighter=scenario(simulator,17,1.,'keep','outcome',paths,rtol=1e-9)
            alternate=scenario(simulator,17,1.,'keep','outcome',paths,rtol=1e-8,
                               solver='python' if simulator=='pensim' else 'Radau')
            changed=scenario(simulator,17,1.,ACTIONS[simulator][1],'outcome',paths)
            mb=metrics(simulator,base)
            repeat_equal=base['trace']==repeat['trace']
            def discrepancy(other):
                return {key:abs(metrics(simulator,other)[key]-mb[key])/max(abs(mb[key]),1e-9)
                        for key in ('product_concentration','process_indicator','objective')}
            tight_error=discrepancy(tighter); alternate_error=discrepancy(alternate)
            changed_response=abs(metrics(simulator,changed)['objective']-mb['objective'])>1e-9
            item={'simulator':simulator,'repeat_identical':repeat_equal,
                  'tighter_solver_relative_error':tight_error,'alternate_solver_relative_error':alternate_error,
                  'changed_command_changes_objective':changed_response,
                  'numerical_gate_passed':repeat_equal and max(tight_error.values())<.005 and max(alternate_error.values())<.005 and changed_response,
                  'experimental_accuracy':'not_independently_validated',
                  'upstream_corrections_and_switches':base.get('audit')}
            for name,value in [('baseline',base),('tighter',tighter),('alternate',alternate),('changed',changed)]:
                dump(out/simulator/(name+'.json'),value)
        except Exception as exc:
            item={'simulator':simulator,'numerical_gate_passed':False,
                  'error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc(),
                  'experimental_accuracy':'not_independently_validated'}
        receipts.append(item)
        print(json.dumps(item),flush=True)
    dump(out/'qualification.json',{'results':receipts,'all_passed':all(r['numerical_gate_passed'] for r in receipts)})
    return receipts


def short_trace(simulator,result,*,cutoff=None):
    rows=[r for r in result['trace'] if cutoff is None or r['time_h']<=cutoff+1e-8]
    stride=max(1,len(rows)//16)
    selected=rows[::stride]
    if selected[-1]!=rows[-1]: selected.append(rows[-1])
    return deepcopy(selected)


def generate(output,paths,seeds=(101,202),*,corrected=False):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a fresh output directory')
    output.mkdir(parents=True,exist_ok=True)
    protocol={'version':VERSION,'classification':'exploratory_external_simulator_experiment',
        'simulators':['PenSimPy corrected native port of IndPenSim','SMPL original 17-state upstream helper'],
        'seeds':list(seeds),'receiving_capabilities':[.95,.9],'tasks':TASKS,
        'planned_pairs':len(seeds)*2*2*len(TASKS),
        'frozen_before_inference':True,'scoring':'Separate product/indicator normalized absolute forecast errors; paired objective change versus keep; finite-grid regret.',
        'prediction_target':'Terminal product concentration and process indicator under KEEP, even when choosing another action.',
        'objective':{'pensim':'Maximize concentration at96h g/L: partial-process endpoint, NOT full-batch optimization, yield or economics.',
                     'mab':'Maximize integrated separator product outflow mg during the post-decision horizon; NOT downstream recovery.'},
        'transfer_scope':'Same simulated geometry/strain; receiving aeration or balanced-flow capability changes. No receiving observations. This is recipe transfer under changed operating limits, NOT validated site transfer or scale-up.',
        'common_information':'Identical source history, permitted receiving history, nominal equations, specifications, actions and source-derived calibration. B alone can execute the nominal forward-model tool.',
        'nominal_model':'Published fixed nominal initialization (no SMPL random perturbations), PenSim seed0 known parameters with future disturbances disabled. Product multiplicative and indicator additive correction using completed source endpoint only.',
        'boundary':'Tool outputs are nominal predictions, not evaluator replay. Realization seed, receiving futures and action outcomes remain evaluator-only.',
        'known_limits':['Small inspected development pilot; no untouched holdout or statistical power.',
                        'Full230h PenSimPy gate failed before this bounded96h design; this is a disclosed development response, not a successful full-batch result.',
                        'Forward tool and evaluator share model equations; this is not independent scientific validation.',
                        'Ideal synthetic process observations; no validated human effort or real batches saved.',
                        'PenSim retains upstream positivity/DO switches; floor events are reported.',
                        'SMPL uses upstream subsystem only; no downstream quality, oxygen-transfer or mixing-gradient model.',
                        'No manufacturing safety or GMP qualification is claimed.'],
        'runtime':{'python':sys.version,'platform':platform.platform()},'paths':paths,
        'source_revisions':{key:subprocess.check_output(['git','-C',paths[key],'rev-parse','HEAD'],text=True).strip() for key in ('pensim','smpl')},
        'native_build':json.loads((Path(paths['native'])/'build.json').read_text()),
        'code_sha256':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')}}
    if corrected:
        protocol.update(version='corrected-fresh-20261028-v1',seeds=list(seeds),
            receiving_capabilities='One factor per seed, .95 for odd and .9 for even seeds',
            planned_pairs=len(seeds)*2*len(TASKS),
            common_information='Identical raw source and receiving observations/settings. Only B receives the host physics tool.',
            nominal_model='PenSim source-only fitted kLa/growth factors inside ODE, no additive oxygen offset. Product endpoint ratio. SMPL unchanged.',
            sampling='Fresh seeds3001..3012; independent seed clusters, three AI session repeats per case; repeats are not independent biological samples.',
            known_limits=protocol['known_limits'][1:])
    dump(output/'protocol.json',protocol)
    dump(output/'generation-status.json',{'status':'running'})
    try:
        qualification=qualify(paths,output/'qualification')
        if not all(r['numerical_gate_passed'] for r in qualification):
            raise ValueError('External simulator numerical gate failed; no agent comparison may start')
        library={};cases=[]
        for simulator in ('pensim','mab'):
            nominal_source=scenario(simulator,0,1.,'keep','transfer',paths,nominal=True)
            for seed in seeds:
                source=scenario(simulator,seed,1.,'keep','transfer',paths)
                sm=metrics(simulator,source);nm=metrics(simulator,nominal_source)
                calibration={'product_ratio':sm['product_concentration']/nm['product_concentration'],
                             'indicator_offset':sm['process_indicator']-nm['process_indicator'],
                             'provenance':'Completed source batch endpoint; no receiving futures used.'}
                factors=None
                if corrected and simulator=='pensim':
                    from .diagnose import fit_oxygen
                    fitted=fit_oxygen(short_trace(simulator,source),paths)
                    factors={k:fitted[k] for k in ('kla_factor','growth_factor')}
                    calibration['physical_parameter_fit']=fitted
                    calibration['indicator_offset']=0.
                    calibration['method']='source_fitted_kla_growth_v1'
                    fitted_source=scenario(simulator,0,1.,'keep','transfer',paths,nominal=True,parameter_overrides=factors)
                    calibration['product_ratio']=sm['product_concentration']/metrics(simulator,fitted_source)['product_concentration']
                caps=((.95 if seed%2 else .9),) if corrected else (.95,.9)
                for cap in caps:
                    for task in TASKS:
                        case_id='EX-'+hashlib.sha256(f'{simulator}-{seed}-{cap}-{task}'.encode()).hexdigest()[:12]
                        actual={};model={}
                        for action in ACTIONS[simulator]:
                            # Prediction task cannot choose an intervention.
                            if task=='prediction' and action!='keep': continue
                            key=f'{simulator}/{cap}/{task}/{action}/{json.dumps(factors,sort_keys=True)}'
                            if key not in library:
                                library[key]=scenario(simulator,0,cap,action,task,paths,nominal=True,parameter_overrides=factors)
                            model[action]=metrics(simulator,library[key],cutoff=80. if simulator=='pensim' and task!='transfer' else 0.)
                            actual[action]=scenario(simulator,seed,cap,action,task,paths)
                        cutoff=0. if task=='transfer' else (80. if simulator=='pensim' else 6.)
                        if simulator=='pensim':
                            module=pen_module(Path(paths['pensim']),Path(paths['native']))
                            equation=Path(module.indpensim_ode_py.__code__.co_filename).read_text()
                            specifications={'receiving_nominal_aeration_factor_vs_source':cap,'maximum_allowed_aeration_factor':cap*1.01,'horizon_h':96.,'geometry':'Fixed original 100000L model geometry; no scale-up.',
                                            'nominal_source_model_seed':0,'clock_unit':'h',
                                            'actions':{'feed_down':'Sugar recipe x0.99 after decision','feed_up':'Sugar recipe x1.01 after decision','air_up':'Aeration recipe x1.01 after decision','keep':'Keep receiving plan'},
                                            'process_indicator':'Terminal dissolved oxygen mg/L; upstream DO floor is an explicit model limitation.'}
                            from .upstream import pen_recipe
                            recipe=pen_recipe()
                            specifications['nominal_recipe']={name:[{'time_h':sp.time,'value':sp.value} for sp in value.sp_list]
                                                                for name,value in recipe.recipe_dict.items()}
                            specifications['nominal_equation_initial_state']=nominal_source['rhs_samples'][0]['state']
                            specifications['nominal_equation_initial_parameters']=nominal_source['rhs_samples'][0]['parameters']
                            specifications['nominal_control_flags']=nominal_source['nominal_control_flags']
                            specifications['nominal_disturbances']='Disabled (Dis=0); there are no hidden nominal future disturbance samples. Actual receiving disturbances remain unknown.'
                            specifications['driver_endpoint_correction']='Integrate exactly t[k-1] to t[k] on the0.2h clock. Remove the extra h_ode from upstream step integration; channel .t offsets are not used.'
                            specifications['native_exponent_correction']='Use a0**(1/3) as in the supplied Python differential equations, rather than C++ integer division1/3=0.'
                            import inspect
                            specifications['nominal_controller_equations']=inspect.getsource(module.PenSimEnv.integrate_control_strategy)
                            specifications['nominal_step_equations']=inspect.getsource(module.PenSimEnv.step)
                            specifications['discharge_unit_notice']='Upstream metadata saysL/h; equation uses density conversion consistent with massflow. Fixed pilot command only; no mass-yield interpretation.'
                        else:
                            model_class,xss,uss=read_mab(Path(paths['smpl']))
                            tree=Path(paths['smpl'])/'smpl/envs/helpers/mab_helpers.py'
                            import ast
                            parsed=ast.parse(tree.read_text())
                            cls=next(n for n in parsed.body if isinstance(n,ast.ClassDef) and n.name=='UpModelHelper')
                            equation=ast.get_source_segment(tree.read_text(),cls)
                            specifications={'receiving_nominal_balanced_flow_factor_vs_source':cap,'maximum_allowed_flow_factor':cap*1.01,'horizon_h':24.,'geometry':'Same reactor/separator volumes; changed pump throughput, not physical scale-up.',
                                            'nominal_source_initial':nominal_source['trace'][0]['state'],
                                            'nominal_source_commands':dict(zip(MAB_COMMANDS,map(float,uss))),
                                            'state_units':dict(zip(MAB_NAMES,MAB_UNITS)),'clock_unit':'hours in packet; equations use MINUTES.',
                                            'actions':{'flow_down':'Multiply all four receiving flows by0.99, preserving volume balances','flow_up':'All four flows x1.01','cool':'Coolant -0.5 degC','keep':'Keep receiving plan'},
                                            'process_indicator':'Terminal viable cells in reactor cells/L'}
                        packet={'case_id':case_id,'simulator':simulator,'task':task,'decision_time_h':cutoff,
                            'objective':'Predict terminal KEEP product_concentration and process_indicator; choose the allowed action maximizing the declared objective. Distinguish predictions from observations.',
                            'allowed_actions':['keep'] if task=='prediction' else ACTIONS[simulator],
                            'source_history':short_trace(simulator,source),
                            'receiving_observations':[] if task=='transfer' else short_trace(simulator,actual['keep'],cutoff=cutoff),
                            'receiving_specifications':specifications,'nominal_model_equations':equation,
                            'source_calibration':calibration,
                            'product_concentration_unit':'g/L' if simulator=='pensim' else 'mg/L',
                            'indicator_unit':'mg/L' if simulator=='pensim' else 'cells/L',
                            'objective_definition':protocol['objective'][simulator],
                            'nominal_model_limitations':protocol['known_limits'],
                            'time_definition':'Source history is a completed earlier batch. Receiving time starts separately; future receiving measurements are never included.'}
                        dump(output/'public'/case_id/'packet.json',packet)
                        dump(output/'model-library'/case_id/'nominal.json',model)
                        truth={'case_id':case_id,'seed':seed,'capability':cap,'simulator':simulator,'task':task,
                               'baseline':metrics(simulator,actual['keep']),
                               'actions':{a:metrics(simulator,r) for a,r in actual.items()},
                               'complete_trajectories':actual}
                        dump(output/'evaluator'/case_id/'truth.json',truth)
                        cases.append({'case_id':case_id,'simulator':simulator,'task':task})
                        print('generated '+case_id+' '+simulator+' '+task,flush=True)
        dump(output/'public/catalogue.json',cases)
        dump(output/'evaluator/catalogue.json',cases)
        manifest={'version':VERSION,'files_sha256':{str(p.relative_to(output)):sha(p) for p in output.rglob('*.json') if p.name not in ('manifest.json','generation-status.json')}}
        dump(output/'manifest.json',manifest)
        dump(output/'generation-status.json',{'status':'complete','case_packets':len(cases),'agent_runs_executed':False})
    except Exception as exc:
        dump(output/'generation-status.json',{'status':'failed','error':str(exc),'traceback':traceback.format_exc()})
        raise


def checked(dataset,relative):
    manifest=json.loads((dataset/'manifest.json').read_text())
    path=dataset/relative
    if manifest['files_sha256'].get(relative)!=sha(path):
        raise ValueError('Frozen dataset checksum mismatch: '+relative)
    return json.loads(path.read_text())


def model_prediction(packet,nominal,action):
    if packet.get('experiment_version','').startswith('operating-challenges-'):
        from .challenges import cached
        return cached(packet,nominal,action)
    if packet.get('simulator')=='cho_real':
        return {'classification':'fitted_mechanistic_forecast_not_observation','action_id':action,'predictions':deepcopy(nominal[action])}
    if action not in packet['allowed_actions'] or action not in nominal:
        raise ValueError('Action outside public grid')
    value=deepcopy(nominal[action]);cal=packet['source_calibration']
    value['product_concentration']*=cal['product_ratio']
    value['process_indicator']+=cal['indicator_offset']
    # Nominal objective is not source-calibrated: do not present it as a true outcome.
    return {'classification':'nominal_model_prediction_not_observation',
            'action_id':action,'predictions':value,'calibration':cal,
            'limits':'Shared upstream equations; nominal batch, not evaluator realization. No optimal-action ranking.'}


def score(packet,truth,submission):
    if packet.get('experiment_version','').startswith('operating-challenges-'):
        from .challenges import score as challenge_score
        return challenge_score(packet,truth,submission)
    if packet.get('simulator')=='cho_real':
        from .cho_real import score as cho_score
        return cho_score(packet,truth,submission)
    action=submission.get('action_id')
    if action not in packet['allowed_actions']:
        raise ValueError('Unknown action')
    predictions=submission.get('predictions',{})
    errors={}
    for key in ('product_concentration','process_indicator'):
        value=predictions.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or value<0:
            raise ValueError('Finite nonnegative prediction required: '+key)
        actual=truth['baseline'][key]
        errors[key]={'predicted':value,'actual':actual,'absolute_error':abs(value-actual),
                     'normalized_absolute_error':abs(value-actual)/max(abs(actual),1e-9)}
    selected=truth['actions'][action]['objective'];base=truth['baseline']['objective']
    best=max(v['objective'] for v in truth['actions'].values())
    return {'prediction_errors':errors,'selected_action':action,'objective':selected,
            'baseline_objective':base,'objective_change':selected-base,
            'objective_change_percent':100*(selected-base)/max(abs(base),1e-9),
            'finite_grid_regret':best-selected,'chosen_outcome':truth['actions'][action],
            'classification':'external_simulated_outcome_not_real_manufacturing_validation',
            'real_batches_saved':None,'observed_engineer_hours_saved':None}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pensim',type=Path,required=True)
    parser.add_argument('--smpl',type=Path,required=True)
    parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--corrected',action='store_true')
    parser.add_argument('--seeds',type=int,nargs='+',default=[101,202])
    args=parser.parse_args()
    generate(args.output,sources(args.pensim,args.smpl,args.native),seeds=tuple(args.seeds),corrected=args.corrected)
