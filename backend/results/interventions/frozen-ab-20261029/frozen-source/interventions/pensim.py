"""PenSim oxygen interventions. Host-only truth; process-isolated execution.

Existing ODEs/controllers and continuous oxygen correction are reused. Parameter
shifts and operating/measurement limits are benchmark assumptions until reviewed.
No shared simulator state may be accessed concurrently from multiple threads.
"""
from copy import deepcopy
from pathlib import Path
import math
import numpy as np
from benchmarks.external_simulators.upstream import pen_module,pen_recipe,monitor_pen
from benchmarks.external_simulators.oxygen import preserve_oxygen

ACTIONS={'keep':(1.,1.),'reduce_feed':(.8,1.),'increase_air':(1.,1.15),'combined':(.8,1.15),'strong_feed_reduction':(.6,1.15),'stop':None}
FIELDS=('P','S','DO2','V','T')


def simulate(paths,*,seed,factors,disturbance_h=48.,transfer_multiplier=1.,action='keep',decision_h=56.,hours=96.,solver='native',rtol=1e-7,kinetics_reference='realization'):
    if action not in ACTIONS:raise ValueError('Action outside frozen menu')
    if not 0<=disturbance_h<=decision_h<hours<=96:raise ValueError('Invalid clocks or unqualified horizon')
    if set(factors)!={'kla_factor','growth_factor','production_factor'}:raise ValueError('Explicit complete kinetics required')
    if any(not math.isfinite(v) or v<=0 for v in [*factors.values(),transfer_multiplier]):raise ValueError('Finite positive factors required')
    module=pen_module(Path(paths['pensim']),Path(paths['native']))
    env=module.PenSimEnv(pen_recipe(),fast=True);env.random_seed_ref=seed;env.ctrl_flags.Raman_spec=0;env.ctrl_flags.Dis=0
    _,state=env.reset()
    if kinetics_reference not in ('realization','seed0'):raise ValueError('Unknown kinetics reference')
    if kinetics_reference=='seed0':
        nominal=module.PenSimEnv(pen_recipe(),fast=True);nominal.random_seed_ref=0;nominal.reset()
        env.param_list[:3]=nominal.param_list[:3]
    for key,index in [('kla_factor',2),('growth_factor',1),('production_factor',0)]:env.param_list[index]*=factors[key]
    trace=[];changed=False;stopped=False
    with monitor_pen(module,rtol=rtol,solver=solver) as (audit,_):
        with preserve_oxygen(module,audit,True) as restore:
            for k in range(1,int(round(hours/.2))+1):
                t=k*.2
                if t>disturbance_h and not changed:env.param_list[2]*=transfer_multiplier;changed=True
                if action=='stop' and t>decision_h:stopped=True;break
                commands=env.recipe_combo.get_values_dict_at(t)
                if t>decision_h:
                    feed,air=ACTIONS[action];commands['Fs']*=feed;commands['Fg']*=air
                _,state,_,_=env.step(k,state,**commands);restore(state,k)
                trace.append({'time_h':t,'state':{f:float(getattr(state,f).y[k-1]) for f in FIELDS},'commands':commands})
    return {'trace':trace,'audit':deepcopy(audit),'stopped':stopped,'decision_h':decision_h,'action_id':action,'classification':'simulation_only'}


def outcomes(run,*,minimum_do=2.):
    rows=run['trace'];post=[r for r in rows if r['time_h']>run['decision_h']+1e-8]
    terminal=rows[-1]['state'];dt=.2
    def violation(part):
        return {'below_limit_h':sum(r['state']['DO2']<minimum_do for r in part)*dt,
            'oxygen_deficit_mg_h_l':sum(max(0.,minimum_do-r['state']['DO2']) for r in part)*dt,
            'minimum_do_mg_l':min((r['state']['DO2'] for r in part),default=None)}
    return {'action_id':run['action_id'],'stopped':run['stopped'],
        'product_mass_kg':0. if run['stopped'] else terminal['P']*terminal['V']/1000.,
        'terminal_concentration_g_l':terminal['P'],'terminal_volume_l':terminal['V'],
        'pre_decision':violation([r for r in rows if r['time_h']<=run['decision_h']+1e-8]),
        'post_decision':violation(post),'whole_process':violation(rows),
        'post_decision_feasible':not run['stopped'] and bool(post) and all(r['state']['DO2']>=minimum_do for r in post),
        'stop_avoided_further_operation':run['stopped'],'measured_product_quality':None,
        'constraint_classification':'Assumed simulated oxygen operating limit, not measured product quality.',
        'mass_definition':'Terminal product inventory P[g/L]*V[L]/1000. No harvest occurs before96h; stopped batches count zero produced/released product.'}


def observations(run,cutoff,*,noise_seed):
    """Published sampling clocks; noise magnitudes remain explicit assumptions.

    Goldrick2019: online DO12min, offline P12h with4h analysis delay.
    S is a hidden model state, never an exact public substrate measurement.
    """
    rng=np.random.default_rng(noise_seed);result=[]
    for row in run['trace']:
        t=row['time_h']
        if t<=cutoff+1e-8:
            result.append({'time_h':t,'available_at_h':t,'field':'DO2',
                'value':max(0.,row['state']['DO2']+float(rng.normal(0,.15))),
                'unit':'mg/L','measurement_kind':'simulated_online_sensor'})
        if abs(t/12.-round(t/12.))<1e-7 and t+4<=cutoff+1e-8:
            result.append({'time_h':t,'available_at_h':t+4.,'field':'P',
                'value':max(0.,row['state']['P']+float(rng.normal(0,.03))),
                'unit':'g/L','measurement_kind':'simulated_delayed_assay'})
    return sorted(result,key=lambda r:(r['available_at_h'],r['field']))


def optimizer(predictions):
    """Conventional finite-grid mass optimizer; no agent or true outcomes."""
    feasible=[(key,p) for key,p in predictions.items() if key!='stop' and p['post_decision_feasible']]
    return max(feasible,key=lambda x:(x[1]['product_mass_kg'],x[0]))[0] if feasible else 'stop'


def stop_classification(selected,all_actions):
    return {'unnecessary_stop':selected=='stop' and any(v['post_decision_feasible'] for v in all_actions.values()),
        'stopped_while_original_recipe_feasible':selected=='stop' and all_actions['keep']['post_decision_feasible'],
        'correct_stop_within_action_menu':selected=='stop' and not any(v['post_decision_feasible'] for v in all_actions.values())}
