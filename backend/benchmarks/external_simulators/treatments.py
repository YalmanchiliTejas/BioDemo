"""Common process evidence for AI with/without a supplied physics-model tool.

The former comparison exposed model equations and calibration to both arms.
That tested executable access, not the requested no-supplied-model baseline.
This projection is frozen before inference and used byte-for-byte in both arms.
All model specification and calibration stays behind B's typed host tool.
"""
from copy import deepcopy


COMMON_FIELDS=('case_id','simulator','task','decision_time_h','objective',
               'allowed_actions','source_history','receiving_observations',
               'product_concentration_unit','indicator_unit','objective_definition','time_definition')
SPEC_FIELDS=('horizon_h','geometry','clock_unit','actions','process_indicator',
             'receiving_nominal_aeration_factor_vs_source','maximum_allowed_aeration_factor',
             'receiving_nominal_balanced_flow_factor_vs_source','maximum_allowed_flow_factor',
             'state_units','discharge_unit_notice')


def common_evidence(full):
    """Keep observations/planned settings; exclude equations/coefficients/calibration."""
    if full.get('experiment_version','').startswith('operating-challenges-'):
        from .challenges import common
        return common(full)
    if full['simulator']=='cho_real':
        fields=('case_id','simulator','task','condition','culture','fold','allowed_actions','decision_time_h','forecast_fields','forecast_times_h','field_units','objective','training_cultures','test_prefix','cultivation_mode')
        return {k:deepcopy(full[k]) for k in fields}
    common={key:deepcopy(full[key]) for key in COMMON_FIELDS if key in full}
    specs=full['receiving_specifications']
    receiving={key:deepcopy(specs[key]) for key in SPEC_FIELDS if key in specs}
    if full['simulator']=='pensim':
        source=deepcopy(specs['nominal_recipe'])
        # These are actual operating commands, not a kinetic or physical model.
        common['source_operating_schedule']=source
        planned=deepcopy(source)
        for point in planned['Fg']:
            point['value']*=receiving['receiving_nominal_aeration_factor_vs_source']
        receiving['planned_operating_schedule']=planned
    else:
        source=deepcopy(specs['nominal_source_commands'])
        common['source_operating_commands']=source
        planned=deepcopy(source)
        for name in ('inlet_flow','reactor_outlet_flow','recycle_flow','product_outlet_flow'):
            planned[name]*=receiving['receiving_nominal_balanced_flow_factor_vs_source']
        receiving['planned_operating_commands']=planned
    common['receiving_specifications']=receiving
    common['evaluation_scope']=(
        'Simulated process outcomes only. PenSim horizon96h is not a full230h batch; '
        'SMPL horizon24h is upstream only. Transfer means changed receiving operating '
        'conditions in the same geometry, not real-site transfer or scale-up.')
    return common


def assert_no_supplied_model(common):
    forbidden=('cho_model','parameters','source_calibration','nominal_model_equations','nominal_model_limitations',
               'nominal_source_initial','nominal_equation_initial_state',
               'nominal_equation_initial_parameters','nominal_control_flags',
               'nominal_controller_equations','nominal_step_equations',
               'nominal_disturbances','driver_endpoint_correction','native_exponent_correction')
    def visit(value):
        if isinstance(value,dict):
            if set(value).intersection(forbidden):
                raise ValueError('Model information found in common process packet')
            for nested in value.values():visit(nested)
        elif isinstance(value,list):
            for nested in value:visit(nested)
    visit(common)
    return True
