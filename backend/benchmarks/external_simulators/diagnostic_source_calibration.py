"""Retrospective PenSim ablations using source evidence only; never deploy/refit silently."""
from pathlib import Path
from copy import deepcopy
import argparse,json
import numpy as np
from .experiment import checked,dump,sha
from .challenges import pen_scenario,response,values
from .diagnose import fit_oxygen


def error(full,truth,pred):
    return float(np.mean([abs(pred[k]-truth['forecasts'][k])/truth['normalization_scales'][k] for k in full['forecast_fields']]))


def run(root,out):
    dataset=root/'dataset';protocol=checked(dataset,'protocol.json');catalogue=checked(dataset,'public/catalogue.json');paths=protocol['paths']
    selected=[]
    # Fixed first ordinary/challenge prediction cases, never chosen for a benefit.
    for stratum in ('ordinary','challenge'):
        for item in catalogue:
            if item['simulator']!='pensim' or item['task']!='prediction':continue
            p=checked(dataset,f"public/{item['case_id']}/packet.json")
            if p['stratum']==stratum:selected.append((item,p));break
    results=[]
    for item,full in selected:
        case=item['case_id'];original=checked(dataset,f'model-library/{case}/nominal.json')['keep']['predictions']
        plan=full['action_plans']['keep'];source=full['source_history']
        # Build alternative predictions BEFORE looking up the receiver targets.
        published=pen_scenario(paths,0,plan,nominal=True,calibration=None)
        published_values=values(published,full['forecast_targets'])
        # Only output P is aligned to the already observed current P, to measure
        # the baseline-offset component. This is diagnostic, not a physical fix.
        legacy=pen_scenario(paths,0,plan,nominal=True,calibration=full['source_calibration'])
        observed=full['receiving_observations'][-1]['state']['P']
        model_at60=next(r['state']['P'] for r in legacy['trace'] if abs(r['time_h']-60)<1e-8)*full['source_calibration']['product_ratio']
        anchored={k:v+(observed-model_at60 if full['forecast_targets'][k]['state']=='P' else 0.) for k,v in original.items()}
        fit=fit_oxygen(source,paths)
        current=deepcopy(full);current['source_calibration']['physical_parameter_fit']=fit
        model_source=pen_scenario(paths,0,{'feed_factor':1.,'air_factor':1.,'apply_after_h':60.},nominal=True,calibration=current['source_calibration'])
        current['source_calibration']['product_ratio']=source[-1]['state']['P']/model_source['terminal']['P']
        fitted=pen_scenario(paths,0,plan,nominal=True,calibration=current['source_calibration'])
        fitted_values=response(current,'keep',fitted)['predictions']
        # Evaluation only now. No receiver target influenced fit or anchoring.
        truth=checked(dataset,f'evaluator/{case}/truth.json')
        predictions={'original_frozen_other_batch_calibration':original,'published_nominal_no_fitted_factors_or_output_bias':published_values,
            'diagnostic_observed_product_offset_only':anchored,'existing_method_fitted_only_to_this_completed_source':fitted_values}
        rows={name:{'mean_source_normalized_error':error(full,truth,pred),'by_field':{k:abs(pred[k]-truth['forecasts'][k])/truth['normalization_scales'][k] for k in pred},'predictions':pred} for name,pred in predictions.items()}
        results.append({'case':case,'stratum':full['stratum'],'comparisons':rows,'source_only_fit':current['source_calibration'],
            'source_history_sha256':sha(dataset/f'public/{case}/packet.json'), 'receiver_targets_used_for_fit':False,
            'offset_warning':'P offset only is an explanatory ablation, not mass-balanced state assimilation. Do not use as a production fix.'})
        dump(out,{'scope':'Two already inspected development cases. No AI rerun, no physical source file changes, no prospective accuracy claim. Existing fitting routine, fixed bounds; receiver targets evaluation-only.', 'cases':results})
        print(json.dumps({'case':case,'errors':{k:v['mean_source_normalized_error'] for k,v in rows.items()}}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.root,a.output)
