"""New challenge scenarios around unchanged, hashed physical models.

Only operating inputs, initial observed states, task packets and scoring change.
No coefficient fitting, ODE/controller edits, or test-dependent case selection.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib,json,math
from pathlib import Path
import traceback
import numpy as np
from .experiment import dump,sha,checked
from .upstream import pen_module,pen_recipe,monitor_pen,read_mab,mab_run,MAB_NAMES,MAB_COMMANDS

VERSION='operating-challenges-20261028-v1'
SYSTEM='''You are a process forecasting and decision research agent. Use only this packet and the available tools. All evidence is simulated. Both arms receive the same raw source history, receiving history, complete operating plans, action choices, units and constraints. Source and receiving clocks are separate. Transfer has no receiving observations.
Predict every forecast target at the exact requested time UNDER KEEP, even if choosing another action. Choose one allowed operating plan. Prediction tasks allow only keep. For outcome/transfer choose a feasible plan maximizing the stated product objective. Study resource/state bounds are explicit; they do not certify manufacturing safety. If no process plan can meet the limits, select abstain; abstain does not operate or produce product. Explain any infeasibility and model limitations. A physics tool, if available, gives model predictions, not actual receiving futures or an optimal-action ranking. Its coefficients/calibration are frozen from an earlier source case and may be inaccurate here; they are not refitted on this case. Use common source evidence to judge applicability. Submit exactly once. No real manufacturing, full-batch or site-transfer validation is established.'''

SYSTEM_V2=SYSTEM.replace('Its coefficients/calibration are frozen from an earlier source case and may be inaccurate here; they are not refitted on this case.',
    'PenSim tool kinetics are fitted only to this completed source history (product, oxygen and substrate trajectories), with no receiving future or seed. SMPL initializes from the common observed source initial state, shared with the receiver by the scenario. Model results may still be inaccurate. Source operating commands and receiving KEEP commands are separate: use operating_plan_context. A tool response predicts its requested action; submit forecasts from KEEP separately from your selected action.')


def system_prompt(version):
    return SYSTEM_V2 if str(version).endswith(('model-repair-v2','model-repair-v3')) else SYSTEM

COMMON=('case_id','simulator','task','experiment_version','decision_time_h','allowed_actions','source_history','receiving_observations','operating_specification','action_plans','constraints','forecast_targets','forecast_fields','field_units','objective','objective_definition','time_definition','stratum','source_reference_history')

def common(full):
    packet={k:deepcopy(full[k]) for k in COMMON if k in full}
    if full.get('forecast_contract_version')==2:
        from .forecast_contract import explicit_plan_context
        packet['operating_plan_context']=explicit_plan_context(full)
    packet['constraint_interpretation']='These are permitted-plan/resource requirements, not an unmodeled actuator saturation law. KEEP forecasts are counterfactual if KEEP violates these requirements; such a plan cannot be selected as a successful feasible operation.'
    return packet

def targets(sim):
    times=[64.,72.,96.] if sim=='pensim' else [8.,12.,24.]
    fields={}
    for index,time in enumerate(times):
        fields['product_concentration' if index==2 else f'product_at_{int(time)}h']={'time_h':time,'state':'P' if sim=='pensim' else 'mAb_reactor','unit':'g/L' if sim=='pensim' else 'mg/L'}
        fields['process_indicator' if index==2 else f'indicator_at_{int(time)}h']={'time_h':time,'state':'DO2' if sim=='pensim' else 'viable_cells_reactor','unit':'mg/L' if sim=='pensim' else 'cells/L'}
    return fields

def action_plans(sim,spec):
    if sim=='pensim':
        values={'keep':(spec['feed_factor'],spec['air_factor']),
          'lean':(.85,1.15),'standard':(1.,1.15),'rich':(1.15,1.15),
          'lean_low_gas':(.85,1.),'standard_low_gas':(1.,1.)}
        plans={a:{'feed_factor':f,'air_factor':g,'apply_after_h':60.} for a,(f,g) in values.items()}
    else:
        values={'keep':(spec['flow_factor'],spec['nutrient_factor'])}
        values.update({f'f{int(round(f*100))}_n{int(round(n*100))}':(f,n) for f in (.8,.9,1.) for n in (.8,.9,1.)})
        plans={a:{'flow_factor':f,'nutrient_factor':n,'apply_after_h':spec['apply_after_h']} for a,(f,n) in values.items()}
    plans['abstain']={'operation':'no run; product objective0; no process-state prediction'}
    return plans

def pen_scenario(paths,seed,plan,*,nominal=False,calibration=None,rtol=1e-7,solver='native'):
    module=pen_module(Path(paths['pensim']),Path(paths['native']))
    env=module.PenSimEnv(pen_recipe(),fast=True);env.random_seed_ref=seed;env.ctrl_flags.Raman_spec=0
    if nominal:env.ctrl_flags.Dis=0
    _,state=env.reset()
    if nominal and calibration:
        fit=calibration['physical_parameter_fit'];env.param_list[2]*=fit['kla_factor'];env.param_list[1]*=fit['growth_factor']
    trace=[];feed=0.;gas=0.
    with monitor_pen(module,rtol=rtol,solver=solver) as (audit,samples):
        for step in range(1,481):
            time=step*.2;u=env.recipe_combo.get_values_dict_at(time)
            if time>60:
                u['Fs']*=plan['feed_factor'];u['Fg']*=plan['air_factor']
                if not (7<=u['Fs']<=151 and 29<=u['Fg']<=76):raise ValueError('Operating commands outside frozen study envelope')
                feed+=u['Fs']*.2;gas+=u['Fg']*.2
            _,state,_,_=env.step(step,state,**u)
            trace.append({'time_h':time,'state':{k:float(getattr(state,k).y[step-1]) for k in ('P','S','DO2','V','T','Viscosity')},'commands':u})
    return {'trace':trace,'terminal':trace[-1]['state'],'objective':trace[-1]['state']['P'],'audit':deepcopy(audit),
        'resources':{'feed_factor':plan['feed_factor'],'air_factor':plan['air_factor'],'integrated_feed_command_times_h':feed,'integrated_air_command_times_h':gas}}

def mab_scenario(paths,initial,spec,plan,*,rtol=1e-7,solver='BDF'):
    _,_,uss=read_mab(Path(paths['smpl']));u=uss.copy()
    before=spec['prechange_flow_factor'];u[:4]*=before;u[4:6]*=spec['prechange_nutrient_factor']
    cutoff=plan['apply_after_h'];prefix=None;state=np.array(initial,dtype=float)
    if cutoff:
        prefix=mab_run(Path(paths['smpl']),initial=state,command=u,hours=cutoff,rtol=rtol,solver=solver)
        state=np.array([prefix['terminal'][k] for k in MAB_NAMES])
    u=uss.copy();u[:4]*=plan['flow_factor'];u[4:6]*=plan['nutrient_factor']
    result=mab_run(Path(paths['smpl']),initial=state,command=u,hours=24.-cutoff,rtol=rtol,solver=solver)
    for row in result['trace']:row['time_h']+=cutoff
    future=result['trace']
    trace=(prefix['trace']+future[1:]) if prefix else future
    result.update(trace=trace,objective=result['product_mass_mg'],audit={'dissolved_oxygen_floor_events':0},
        resources={'flow_factor':plan['flow_factor'],'nutrient_factor':plan['nutrient_factor'],
            'nutrient_input_relative_source':plan['flow_factor']*plan['nutrient_factor']})
    return result

def values(result,forecast_targets):
    out={}
    for field,target in forecast_targets.items():
        matches=[row for row in result['trace'] if abs(row['time_h']-target['time_h'])<1e-7]
        if len(matches)!=1:raise ValueError('Forecast target not an exact simulator output time')
        out[field]=matches[0]['state'][target['state']]
    return out

def evaluate(sim,result,limits):
    if result.get('failed'):return {'qualified':False,'feasible':False,'objective':None,'error':result['error'],'violations':['solver_or_domain_failure']}
    reasons=[];resources=result['resources'];future=[r for r in result['trace'] if r['time_h']>limits['constraint_start_h']+1e-8]
    qualified=not result['audit'].get('dissolved_oxygen_floor_events',0)
    if not qualified:reasons.append('oxygen_floor_model_domain')
    if sim=='pensim':
        if resources['feed_factor']>limits['maximum_feed_factor']+1e-9:reasons.append('feed_delivery_limit')
        if resources['air_factor']>limits['maximum_air_factor']+1e-9:reasons.append('aeration_delivery_limit')
        if min(r['state']['DO2'] for r in future)<limits['minimum_do_mg_l']:reasons.append('dissolved_oxygen_study_limit')
    else:
        if resources['flow_factor']>limits['maximum_flow_factor']+1e-9:reasons.append('pump_delivery_limit')
        if resources['nutrient_input_relative_source']>limits['maximum_nutrient_input_relative_source']+1e-9:reasons.append('nutrient_resource_limit')
        if min(r['state']['viable_cells_reactor'] for r in future)<limits['minimum_viable_cells_l']*(1-1e-9):reasons.append('viable_cell_study_limit')
        if any(not 33<=r['state']['temperature']<=37.0001 for r in future):reasons.append('temperature_study_limit')
    return {'qualified':qualified,'feasible':qualified and not reasons,'objective':result['objective'],'violations':reasons,
        'resources':resources,'audit':result['audit']}

def run_action(full,action,paths,*,nominal=False,seed=None,initial=None,rtol=1e-7,solver=None):
    if action=='abstain':return None
    plan=full['action_plans'][action];sim=full['simulator']
    if sim=='pensim':
        from .oxygen import run_continuous
        continuous=full.get('oxygen_policy')=='continuous_nonnegative_ODE'
        if nominal and full.get('forecast_contract_version')==2:
            from .forecast_contract import validate_case_source_calibration
            from .calibrated_pen import simulate
            validate_case_source_calibration(full)
            fit=full['source_calibration']['physical_parameter_fit']
            if continuous:return run_continuous(paths,simulate,paths,plan,fit,rtol=rtol,solver=solver or 'native')
            return simulate(paths,plan,fit,rtol=rtol,solver=solver or 'native')
        if continuous:return run_continuous(paths,pen_scenario,paths,0 if nominal else seed,plan,nominal=nominal,calibration=full['source_calibration'],rtol=rtol,solver=solver or 'native')
        return pen_scenario(paths,0 if nominal else seed,plan,nominal=nominal,calibration=full['source_calibration'],rtol=rtol,solver=solver or 'native')
    # All initial-state components are observed/common source evidence. Transfer
    # assumes the explicitly stated same inoculum state; this is optimistic.
    state=full['source_history'][0]['state'] if initial is None else initial
    state=[state[k] for k in MAB_NAMES] if isinstance(state,dict) else state
    return mab_scenario(paths,state,full['operating_specification'],plan,rtol=rtol,solver=solver or 'BDF')

def response(full,action,result):
    if full.get('forecast_contract_version')==2:
        from .forecast_contract import response_v2
        return response_v2(full,action,result)
    if full.get('forecast_contract_version') not in (None,1):
        raise ValueError('Unsupported forecast contract version')
    if action=='abstain':return {'classification':'no_operation','action_id':action,'predictions':{},'feasibility':'abstain_no_product'}
    predictions=values(result,full['forecast_targets']);cal=full['source_calibration']
    for field,target in full['forecast_targets'].items():
        if target['state'] in ('P','mAb_reactor'):predictions[field]*=cal['product_ratio']
        else:predictions[field]+=cal['indicator_offset']
    return {'classification':'frozen_physics_prediction_not_observation','action_id':action,'predictions':predictions,
        'operating_consequences':evaluate(full['simulator'],result,full['constraints']),
        'limits':'Previously fitted coefficients and calibration frozen; no refitting to this case. Same equations as evaluator; no independent physical validation.'}

def forward(full,action,paths):
    if action not in full['allowed_actions']:raise ValueError('Action outside public grid')
    return response(full,action,run_action(full,action,paths,nominal=True))

def cached(full,library,action):
    return deepcopy(library[action])

def score(packet,truth,submission):
    predictions=submission['predictions'];errors={}
    for key in packet['forecast_fields']:
        value=predictions[key]
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Invalid forecast')
        actual=truth['forecasts'][key]
        errors[key]={'predicted':value,'actual':actual,'absolute_error':abs(value-actual),
            'normalized_absolute_error':abs(value-actual)/truth['normalization_scales'][key]}
    action=submission['action_id'];chosen=truth['actions'][action];base=truth['actions']['keep']
    feasible=[(a,v) for a,v in truth['actions'].items() if a!='abstain' and v.get('feasible')]
    best=max((v['objective'] for a,v in feasible),default=0.)
    abstained=action=='abstain';correct_abstention=abstained and not feasible
    feasible_choice=not abstained and chosen.get('feasible',False)
    utility=(chosen['objective']/best if feasible_choice and best>0 else (1. if correct_abstention else 0.))
    raw=chosen.get('objective') if not abstained else 0.;base_value=base.get('objective')
    change=(raw-base_value) if raw is not None and base_value is not None else None
    return {'prediction_errors':errors,'selected_action':action,'decision_score':utility,
        'feasible_choice':feasible_choice,'correct_abstention':correct_abstention,'unnecessary_abstention':abstained and bool(feasible),
        'invalid_decision':not abstained and not feasible_choice,'no_feasible_process_action':not feasible,
        'objective':raw,'objective_change':change if change is not None else 0.,
        'objective_change_percent':100*change/max(abs(base_value),1e-9) if change is not None else 0.,
        'objective_change_is_qualified':feasible_choice and base.get('qualified',False) and base.get('feasible',False),
        'finite_grid_regret':max(0.,best-(raw if feasible_choice else 0.)),
        'chosen_outcome':chosen,'classification':'controlled_mechanistic_simulation_only'}

def thinning(result,cutoff=None):
    rows=[r for r in result['trace'] if cutoff is None or r['time_h']<=cutoff+1e-8]
    selected=rows[::max(1,len(rows)//16)]
    if selected[-1]!=rows[-1]:selected.append(rows[-1])
    return deepcopy(selected)

def setup(output,old,n,seed_start=7001,source_air_factor=1.,require_source_admission=False,continuous_oxygen=False):
    if output.exists():raise ValueError('Fresh dataset path required')
    output.mkdir(parents=True)
    p=checked(old,'protocol.json');paths=p['paths'];catalogue=checked(old,'public/catalogue.json')
    templates={}
    for sim in ('pensim','mab'):
        c=next(r for r in catalogue if r['simulator']==sim and r['task']=='prediction')
        templates[sim]=checked(old,f"public/{c['case_id']}/packet.json")
    physical=[Path(__file__).with_name('upstream.py'),Path(__file__).with_name('diagnose.py'),Path(__file__).with_name('native.py'),Path(__file__).with_name('cho_real.py'),Path(paths['pensim'])/'pensimpy/ode/indpensim_ode_py.py',Path(paths['pensim'])/'pensimpy/peni_env_setup.py',Path(paths['smpl'])/'smpl/envs/helpers/mab_helpers.py']
    frozen={str(f):sha(f) for f in physical}
    protocol={'version':VERSION,'classification':'exploratory_fixed_sample_challenge_benchmark','paths':paths,
        'independent_cases_per_process':n,'case_seeds':list(range(seed_start,seed_start+n)), 'tasks':['prediction','outcome','transfer'],
        'source_air_factor':source_air_factor,'require_source_admission':require_source_admission,
        'oxygen_policy':'continuous_nonnegative_ODE' if continuous_oxygen else 'legacy_reset',
        'AI_repeats':2,'planned_agent_attempts':n*2*3*2*2,
        'sampling':'Deterministic balanced cycling of predeclared regimes; no outcome-dependent selection/resampling. Same seed across tasks, cluster accordingly.',
        'strata':'Every fourth case is ordinary; remaining cases involve declared transitions/constraints.',
        'frozen_model_files_sha256':frozen,'frozen_calibrations':{sim:templates[sim]['source_calibration'] for sim in templates},
        'model_freeze':'Existing coefficients/calibrations from the FIRST prior prediction case by catalogue order per process. No new fit or tuning. Operating input/state changes only.',
        'minimum_useful_effects':{'prediction_relative_error_reduction':.20,'operating_decision_score_B_minus_A':.05,'transfer_decision_score_B_minus_A':.05},
        'claim_rule':'All three primary aspects must exceed their useful-effect threshold with a cluster bootstrap95% lower bound above it, completion>=95%, and all cases scorable/admitted. Each process reported separately; no manufacturing claim.',
        'power':'Fixed bounded48/cases per process by default; exploratory, not a prospectively power-qualified definitive study. No optional extension until favorable.',
        'failures':'All selected seeds retained. Failed receiving KEEP/domain case is a coverage failure, blocks confirmation. Invalid selected action scores0. Correct abstention when grid has no feasible process action scores1, otherwise0.',
        'observation_boundary':'No receiving future, realization seed, action outcomes or scores returned. Source and receiving clocks separate. SMPL explicitly shares measured initial inoculum state across source/receiving; optimistic same-geometry test.',
        'scope':'PenSim96h partial process, SMPL24h upstream. Simulated transfer proxy, not vessel/site transfer. No real CHO data or real intervention in new suite.',
        'known_design_findings':'Earlier development found oxygen-floor artifacts and monotone SMPL action rankings. Fixed challenge grid includes admitted alternatives and explicit infeasibility/abstention; easy controls retained. No guarantee of decision diversity or B benefit.',
        'runner_source_sha256':{f.name:sha(f) for f in Path(__file__).parent.glob('*') if f.suffix in ('.py','.mjs')}}
    dump(output/'protocol.json',protocol);return paths,templates,physical,frozen

def admit_source(result):
    if result['audit'].get('dissolved_oxygen_floor_events',0):
        raise ValueError('Completed source has oxygen-floor model-domain artifacts')


def generate(output,old,n=48,seed_start=7001,source_air_factor=1.,require_source_admission=False,continuous_oxygen=False):
    paths,templates,physical,frozen=setup(output,old,n,seed_start,source_air_factor,require_source_admission,continuous_oxygen);cases=[];coverage=[];nominal_cache={};physical_nominal_cache={}
    _,xss,uss=read_mab(Path(paths['smpl']))
    for sim in ('pensim','mab'):
        for index,seed in enumerate(range(seed_start,seed_start+n)):
            ordinary=index%4==0;stratum='ordinary' if ordinary else 'challenge'
            if sim=='pensim':
                spec={'feed_factor':1. if ordinary else (.9,1.05,1.1)[index%3],'air_factor':1.15,'change_after_h':60.,'endpoint_h':96.,
                    'physical_input_units':{'Fs':'source sugar-feed command unit/hour, as upstream','Fg':'source volumetric gas-flow command unit, as upstream'},
                    'source_operating_schedule':templates[sim]['receiving_specifications']['nominal_recipe'],
                    'geometry':'Original fixed geometry; no site/scale change'}
                try:
                    plan={'feed_factor':1.,'air_factor':source_air_factor,'apply_after_h':60.}
                    if continuous_oxygen:
                        from .oxygen import run_continuous
                        source=run_continuous(paths,pen_scenario,paths,seed,plan)
                    else:source=pen_scenario(paths,seed,plan)
                    if require_source_admission:admit_source(source)
                except Exception as exc:
                    for task in ('prediction','outcome','transfer'):
                        coverage.append({'simulator':sim,'seed':seed,'task':task,'reason':'Completed source simulation failed','error':str(exc)})
                    continue
                initial=None
            else:
                cells=1. if ordinary else (.8,.9,1.)[index%3];inhibitor=1. if ordinary else (.8,1.2)[(index//3)%2]
                initial=xss.copy();initial[[0,1,8,9]]*=cells;initial[[4,5,12,13]]*=inhibitor
                # Independent seeded mild state variation, bounded within the published study initial envelope.
                rng=np.random.default_rng(seed);factor=float(rng.uniform(.99,1.01));initial[[2,3,10,11]]*=factor;initial[16]=36.8
                spec={'flow_factor':.9 if ordinary else (.8,.9,1.)[index%3],'nutrient_factor':.9,
                    'prechange_flow_factor':.9,'prechange_nutrient_factor':1.,'apply_after_h':6.,'endpoint_h':24.,
                    'source_operating_commands':dict(zip(MAB_COMMANDS,map(float,uss))),
                    'geometry':'Same reactor/separator volumes and measured initial inoculum state as source; no site/scale change'}
                source=mab_scenario(paths,initial,dict(spec,apply_after_h=0.),{'flow_factor':1.,'nutrient_factor':1.,'apply_after_h':0.})
            actual_cache={}
            for task in ('prediction','outcome','transfer'):
                case='NC-'+hashlib.sha256(f'{sim}/{seed}/{task}'.encode()).hexdigest()[:12]
                cutoff=0. if task=='transfer' else (60. if sim=='pensim' else 6.)
                operating=deepcopy(spec)
                if sim=='mab' and task=='transfer':operating['apply_after_h']=0.
                plans=action_plans(sim,operating)
                limits={'constraint_start_h':60. if sim=='pensim' else operating['apply_after_h'],
                    'definition':'Declared simulation study bounds/resources only; not validated manufacturing safety limits.'}
                if sim=='pensim':limits.update(maximum_feed_factor=1.15 if ordinary else (.9,1.,1.15)[(index//3)%3],maximum_air_factor=1.15 if index%3 else 1.,minimum_do_mg_l=2.)
                else:limits.update(maximum_flow_factor=1. if ordinary else (.8,.9,1.)[(index//2)%3],maximum_nutrient_input_relative_source=.9,
                    minimum_viable_cells_l=float(.8*xss[0]))
                full={'case_id':case,'simulator':sim,'task':task,'experiment_version':VERSION,'stratum':stratum,
                    'oxygen_policy':'continuous_nonnegative_ODE' if continuous_oxygen and sim=='pensim' else 'legacy_reset',
                    'decision_time_h':cutoff,'operating_specification':operating,'constraints':limits,'action_plans':plans,
                    'allowed_actions':['keep'] if task=='prediction' else list(plans),
                    'source_history':thinning(source),'receiving_observations':[],
                    'source_simulation_audit':deepcopy(source['audit']),
                    'source_reference_history':templates[sim]['source_history'],
                    'source_calibration':deepcopy(templates[sim]['source_calibration']),
                    'forecast_targets':targets(sim),'forecast_fields':list(targets(sim)),
                    'field_units':{k:v['unit'] for k,v in targets(sim).items()},
                    'objective':'Forecast every KEEP target. For decision tasks choose feasible product-maximizing plan; abstain if no process action is feasible.',
                    'objective_definition':'PenSim terminal product concentration g/L, not yield; SMPL post-change separator product outflow mg. Feasibility takes priority.',
                    'time_definition':'Completed source is earlier than receiving time zero. Transfer has no receiving history. SMPL source initial state also defines receiving inoculum, disclosed identically to both arms.'}
                actual={};results={}
                for action in full['allowed_actions']:
                    if action=='abstain':actual[action]={'feasible':True,'qualified':True,'objective':0.,'violations':[],'abstention':True};continue
                    try:
                        action_key=json.dumps({'plan':plans[action],'spec':operating},sort_keys=True) if sim=='mab' else json.dumps(plans[action],sort_keys=True)
                        if action_key not in actual_cache:actual_cache[action_key]=run_action(full,action,paths,seed=seed,initial=initial)
                        result=actual_cache[action_key]
                        results[action]=result;actual[action]=evaluate(sim,result,limits)
                    except Exception as exc:actual[action]={'feasible':False,'qualified':False,'objective':None,'error':type(exc).__name__+': '+str(exc),'violations':['solver_or_domain_failure']}
                keep=results.get('keep')
                if keep is None:
                    coverage.append({'case_id':case,'simulator':sim,'seed':seed,'task':task,'reason':'KEEP simulation failed','detail':actual['keep']});continue
                if not actual['keep']['qualified']:
                    coverage.append({'case_id':case,'simulator':sim,'seed':seed,'task':task,'reason':'KEEP oxygen-floor/model-domain failure','detail':actual['keep']});continue
                full['receiving_observations']=[] if task=='transfer' else thinning(keep,cutoff)
                forecasts=values(keep,full['forecast_targets'])
                # Training/source scales, never receiving future values.
                scales={k:max(float(np.median([r['state'][v['state']] for r in full['source_history']])),1e-6) for k,v in full['forecast_targets'].items()}
                model={}
                for action in full['allowed_actions']:
                    key=json.dumps({'sim':sim,'spec':operating,'plan':plans[action],'limits':limits,'initial':full['source_history'][0]['state'] if sim=='mab' else None},sort_keys=True)
                    if key not in nominal_cache:
                        try:
                            physical_key=json.dumps(plans[action],sort_keys=True) if sim=='pensim' else key
                            physical_key=sim+physical_key
                            if physical_key not in physical_nominal_cache:physical_nominal_cache[physical_key]=run_action(full,action,paths,nominal=True)
                            nominal_cache[key]=response(full,action,physical_nominal_cache[physical_key])
                        except Exception as exc:nominal_cache[key]={'classification':'frozen_model_execution_failure','action_id':action,'predictions':{},'error':type(exc).__name__+': '+str(exc)}
                    model[action]=nominal_cache[key]
                # Always source observations/nominal assumptions only in host packet.
                dump(output/'public'/case/'packet.json',full)
                dump(output/'model-library'/case/'nominal.json',model)
                dump(output/'evaluator'/case/'truth.json',{'seed':seed,'case_id':case,'stratum':stratum,'forecasts':forecasts,'normalization_scales':scales,
                    'actions':actual,'baseline':{'product_concentration':forecasts['product_concentration'],'process_indicator':forecasts['process_indicator']},'complete_trajectories':results})
                cases.append({'case_id':case,'simulator':sim,'task':task});print(json.dumps({'generated':len(cases),'case':case,'simulator':sim,'task':task}),flush=True)
    assert frozen=={str(f):sha(f) for f in physical},'Frozen physical code changed'
    dump(output/'coverage-failures.json',coverage);dump(output/'public/catalogue.json',cases);dump(output/'evaluator/catalogue.json',cases)
    dump(output/'manifest.json',{'files_sha256':{str(f.relative_to(output)):sha(f) for f in output.rglob('*.json') if f.name not in ('manifest.json','generation-status.json')}})
    dump(output/'generation-status.json',{'status':'complete','scorable_case_packets':len(cases),'planned_case_packets':n*2*3,'coverage_failures':len(coverage),'new_model_fits':0,'model_files_unchanged':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prior-dataset',type=Path,required=True);p.add_argument('--cases',type=int,default=48);a=p.parse_args();generate(a.output,a.prior_dataset,a.cases)
