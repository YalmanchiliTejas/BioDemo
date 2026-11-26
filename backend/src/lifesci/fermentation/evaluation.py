"""Evaluator-only endpoints; never imported by the deterministic agent tool."""
import json
import math
from pathlib import Path
from ..ids import content_hash
from .model import transfer_point
from .data import DATA


# Declared before comparison as a screening tolerance on relative error; not a validated acceptance criterion.
TOLERANCE = .20


def grade(public, prediction, assumptions):
    # prediction is already complete. Read targets only after its commitment hash exists.
    commitment=content_hash(prediction)
    targets=json.loads((DATA/'validation.evaluator.json').read_text())
    rows=[]
    if public['id']=='sulfolobus':
        for actual in targets['sulfolobus']:
            simulated=transfer_point(public,actual['working_volume_l'],actual['agitation_rpm'],actual['airflow_l_min']/actual['working_volume_l'],assumptions.gas_exponent)
            measured=actual['kla_h_inv']; predicted=simulated['predicted_kla_h_inv']
            rows.append({'receiver_l':actual['working_volume_l'],'metric':'kLa','unit':'h^-1','measured':measured,'predicted':predicted,
                         'residual':predicted-measured,'relative_error':(predicted-measured)/measured,
                         'sensitivity_low':simulated['sensitivity_low_h_inv'],'sensitivity_high':simulated['sensitivity_high_h_inv'],
                         'predicted_gas_velocity_basis':simulated['gas_velocity_basis_kla_h_inv'],
                         'within_sensitivity_range':simulated['sensitivity_low_h_inv']<=measured<=simulated['sensitivity_high_h_inv'],
                         'published_rpm':actual['agitation_rpm'],'published_airflow_l_min':actual['airflow_l_min'],
                         'source_location':actual['source_location'],'classification':'withheld_experimental_water_summary',
                         'uncertainty':'Overall reported kLa measurement SD1.17h^-1; not a receiver prediction interval'})
        conclusion='Source-only correlation does not identify receiver sparger/geometry response. Error is reported even when it challenges the model; characterize receiver water and broth kLa before relying on settings.'
    else:
        for actual in targets['pichia']:
            observed=actual['outcomes']['volumetric_enzyme_production']
            predicted=prediction['empirical_baseline']['enzyme_production_mg_l']
            rows.append({'receiver_l':actual['nominal_reactor_volume_l'],'metric':'enzyme mass, constant10L empirical baseline','unit':'mg/L',
                         'measured':observed['value'],'measured_sd':observed['uncertainty']['value'],'predicted':predicted,
                         'residual':predicted-observed['value'],'relative_error':(predicted-observed['value'])/observed['value'],
                         'source_location':actual['source_location'],'classification':'withheld_assay_derived_summary_not_mechanistic_prediction',
                         'activity_u_l':actual['outcomes']['volumetric_enzyme_activity']['value']})
        conclusion='No measured kLa/OUR or calibrated Pichia kinetics: absolute oxygen transfer and mechanistic productivity validation are unavailable. Constant10L endpoint error is an empirical comparator only; changes in feeding, DO and biomass confound pressure effects.'
    for row in rows:
        row['within_tolerance']=abs(row['relative_error'])<=TOLERANCE
    failed=[row for row in rows if not row['within_tolerance']]
    verdict={'status':'fails_withheld_comparison' if failed else 'within_declared_tolerance','tolerance':TOLERANCE,
             'worst_relative_error':max((row['relative_error'] for row in rows),key=abs),
             'rows_outside_tolerance':[row['receiver_l'] for row in failed],
             'rows_outside_sensitivity_range':[row['receiver_l'] for row in rows if row.get('within_sensitivity_range') is False],
             'basis':'Relative error of each prediction against the withheld published summary. A screening tolerance declared in advance; passing it does not validate the model.'}
    return {'verdict':verdict,'split':targets['protocol'],'protocol_hash':content_hash(targets['protocol']),'target_hash':content_hash(targets),
            'prediction_commitment':commitment,'rows':rows,'rmse':math.sqrt(sum(r['residual']**2 for r in rows)/len(rows)),
            'mechanistic_productivity_validated':False,'independent_calibration_and_receiving_summaries':True,'conclusion':conclusion,
            'published_outcomes':targets.get('pichia_30l_comparison') if public['id']=='pichia' else targets.get('sulfolobus_biological_summary')}
