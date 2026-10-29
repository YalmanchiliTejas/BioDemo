"""Opt-in corrected forecast semantics; original v1 runs remain replayable.

This changes calibration applicability and provenance, not physical equations.
It is not evidence of a corrected AI A/B outcome or real-world model accuracy.
"""
from copy import deepcopy
import hashlib,json,math


def evidence_hash(history):
    return hashlib.sha256(json.dumps(history,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def initial_state_is_observed(full,result):
    from .upstream import MAB_NAMES
    context=full.get('model_execution_context',{})
    if context.get('initialization')!='observed_source_state_shared_with_receiver':
        raise ValueError('Observed initial state policy requires explicit initialization context')
    if context.get('residual_origin')!='nominal_initialization_difference':
        raise ValueError('Observed initial state correction requires declared residual origin')
    source=full.get('source_history',[])
    if not source or source[0]['time_h']!=0. or not set(MAB_NAMES)<=set(source[0]['state']):
        raise ValueError('Complete observed initial state is required')
    rows=result.get('trace',[])
    if not rows or rows[0]['time_h']!=0. or not set(MAB_NAMES)<=set(rows[0]['state']):
        raise ValueError('Model execution must retain its actual initial state')
    for key in MAB_NAMES:
        observed=source[0]['state'][key];used=rows[0]['state'][key]
        if not math.isfinite(observed) or not math.isclose(used,observed,rel_tol=1e-10,abs_tol=1e-12):
            raise ValueError('Model initial state differs from declared observation: '+key)


def validate_case_source_calibration(full):
    cal=full['source_calibration']
    if cal.get('evidence_scope')!='completed_source_before_receiving' or cal.get('source_history_sha256')!=evidence_hash(full['source_history']):
        raise ValueError('Current-case source calibration evidence does not match the completed source history')
    fit=cal.get('physical_parameter_fit',{})
    if fit.get('method')=='source_trajectory_kinetics_v2':
        if fit.get('source_history_sha256')!=cal['source_history_sha256'] or fit.get('source_operating_plan')!=full.get('source_operating_plan'):
            raise ValueError('Physical fit source calibration lineage or operating plan mismatch')
        if cal['product_ratio']!=1. or cal['indicator_offset']!=0.:
            raise ValueError('Trajectory kinetics cannot also apply endpoint output corrections')
        if full.get('oxygen_policy')=='continuous_nonnegative_ODE' and fit.get('oxygen_policy')!='continuous_nonnegative_ODE':
            raise ValueError('Physical fit oxygen policy differs from model execution')


def response_v2(full,action,result):
    from .challenges import values,evaluate
    if action=='abstain':return {'classification':'no_operation','action_id':action,'predictions':{},'feasibility':'abstain_no_product'}
    raw=values(result,full['forecast_targets']);predictions=deepcopy(raw)
    if full['simulator']=='mab':
        initial_state_is_observed(full,result)
        calibration={'applied':False,'reason':'Observed-state initialization replaces the old nominal-initialization residual correction.',
            'historical_calibration_retained':deepcopy(full['source_calibration'])}
    elif full['simulator']=='pensim':
        validate_case_source_calibration(full)
        cal=full['source_calibration']
        for field,target in full['forecast_targets'].items():
            if target['state']=='P':predictions[field]*=cal['product_ratio']
            else:predictions[field]+=cal['indicator_offset']
        calibration={'applied':True,'evidence_scope':cal['evidence_scope'],'source_history_sha256':cal['source_history_sha256'],
            'warning':'Source-only provenance does not establish multi-horizon or changed-plan accuracy. Validate the full trajectory separately.'}
        if cal.get('physical_parameter_fit',{}).get('method')=='source_trajectory_kinetics_v2':
            calibration['physical_fit']=deepcopy(cal['physical_parameter_fit'])
    else:raise ValueError('Unsupported simulator for forecast contract v2')
    return {'classification':'physics_prediction_not_observation','forecast_contract_version':2,'action_id':action,
        'predictions':predictions,'raw_ODE_predictions':raw,'calibration':calibration,
        'prediction_plan_action_id':action,'submission_forecast_plan_required':'keep',
        'operating_consequences':evaluate(full['simulator'],result,full['constraints']),
        'limits':'Shared equations with evaluator. Fixing this wrapper does not establish independent physical accuracy or an AI improvement.'}


def explicit_plan_context(full):
    """Make already declared source and receiving schedules unambiguous."""
    if 'source_operating_plan' not in full:
        raise ValueError('Forecast contract v2 requires an explicit completed-source operating plan')
    return {'completed_source_plan':deepcopy(full['source_operating_plan']),
        'receiving_KEEP_plan':deepcopy(full['action_plans']['keep']),
        'receiving_before_change':{
            key:deepcopy(value) for key,value in full['operating_specification'].items()
            if key.startswith('prechange_')},
        'forecast_plan_required':'keep',
        'warning':'Completed-source observations used different commands unless the two plans explicitly agree. Receiving observations stop before the declared future change.'}
