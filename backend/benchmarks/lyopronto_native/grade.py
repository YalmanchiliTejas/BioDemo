"""Deterministic agent grading against native reference, not a model-comparison scorer."""
import math


def close(value,expected,absolute,relative):
    return type(value) in (int,float) and math.isfinite(value) and abs(value-expected)<=max(absolute,relative*abs(expected))


def grade(case,reference,assessment,trace):
    checks={};source=case['source'];expected_status=reference['required_status']
    checks['recorded_assessment']=assessment is not None
    checks['no_manufacturing_action']=trace['action_intents']==0
    if assessment is None:
        return {'passed':False,'checks':checks,'classification':'missing_assessment','task':case['family']}
    checks['appropriate_status']=assessment['answer_status']==expected_status
    checks['simulation_evidence']=not reference['requires_simulation'] or bool(assessment['result_ids'])
    if expected_status in ('needs_information','out_of_scope'):
        checks['missing_evidence_identified']=set(reference['required_missing'])<=set(assessment['missing_inputs'])
        checks['no_invented_recommendation']=assessment['selected_recipe'] is None and assessment['completion_h'] is None
    elif source['task']=='select_recipe':
        simulations=trace.get('native_simulations',[])
        simulated=[{'pressure_torr':r['native_configuration']['Pchamber']['setpt'][0],
                    'shelf_temperature_c':r['native_configuration']['Tshelf']['setpt'][0]} for r in simulations]
        if expected_status=='no_feasible_recipe':
            checks['no_unsafe_recipe']=assessment['selected_recipe'] is None
            checks['all_candidates_checked']=all(r in simulated for r in source['recipe_candidates'])
        else:
            candidates=[r for r in reference['candidates'] if r['recipe']==assessment['selected_recipe']]
            checks['allowed_recipe']=len(candidates)==1
            metric=candidates[0]['metrics'] if candidates else None
            checks['feasible_selection']=bool(metric and metric['feasible'])
            checks['selected_recipe_simulated']=assessment['selected_recipe'] in simulated
            checks['time_regret_within_5pct']=bool(metric and metric['completion_h'] is not None and metric['completion_h']<=reference['best_time_h']*1.05)
            for field,abs_tol,rel_tol in [('completion_h',.01,.01),('thermal_margin_c',.1,0),('capacity_margin_kg_h',.001,.01)]:
                checks[field]=bool(metric and metric[field] is not None and close(assessment[field],metric[field],abs_tol,rel_tol))
    else:
        metric=reference['metrics']
        checks['correct_endpoint']=assessment['completion_h'] is None if metric['completion_h'] is None else close(assessment['completion_h'],metric['completion_h'],.01,.01)
        checks['bottom_not_front_temperature']=close(assessment['maximum_bottom_temperature_c'],metric['maximum_bottom_temperature_c'],.1,0)
        checks['whole_batch_not_per_vial_flux']=close(assessment['peak_batch_sublimation_kg_h'],metric['peak_batch_sublimation_kg_h'],.001,.01)
        used=trace['native_simulations']
        expected_pressure=reference.get('canonical_pressure_torr',source['native_inputs'].get('Pchamber',{}).get('setpt',[None])[0])
        checks['scheduled_inputs_preserved']=bool(used) and all(abs(r['native_configuration']['Pchamber']['setpt'][0]-expected_pressure)<=max(1e-6,.001*expected_pressure) and
            r['native_configuration']['Tshelf']['setpt']==source['native_inputs']['Tshelf']['setpt'] for r in used)
    correct=all(checks.values())
    return {'passed':correct,'checks':checks,'classification':'task_completed' if correct else 'agent_task_failure','task':case['family']}
