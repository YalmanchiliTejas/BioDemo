"""Pre-freeze source-batch and time-holdout checks. No final receiver test data."""
from pathlib import Path
import json
import numpy as np
from .pensim import simulate,observations
from .model import fit_source
from benchmarks.external_simulators.experiment import dump


def qualify(paths,output):
    rows=[];batches=[]
    for i,seed in enumerate([22011,22012,22013]):
        factors={'kla_factor':[.96,1.,1.04][i],'growth_factor':[.98,1.,1.02][i],'production_factor':[1.02,1.,.98][i]}
        r=simulate(paths,seed=seed,factors=factors,decision_h=52.,kinetics_reference='seed0')
        obs=[dict(o,source_batch=f'source-{i+1}') for o in observations(r,100.,noise_seed=seed+40000)]
        rows.extend(obs);batches.append({'batch_id':f'source-{i+1}','measurements':obs})
    # Training/future split concerns completed-source time only, not receiver labels.
    training=[r for r in rows if r['time_h']<=72.]
    development_fit=fit_source(paths,training)
    pred=simulate(paths,seed=0,factors=development_fit['factors'],decision_h=52.)
    look={round(r['time_h'],6):r['state'] for r in pred['trace']}
    errors={field:[abs(look[round(r['time_h'],6)][field]-r['value']) for r in rows if r['field']==field and r['time_h']>72.] for field in ['P','DO2']}
    final_fit=fit_source(paths,rows)
    receipt={'classification':'source-only calibration qualification; not receiving-test accuracy','source_batches':3,
        'training_cutoff_h':72.,'heldout_source_MAE':{k:float(np.mean(v)) for k,v in errors.items()},
        'development_fit':development_fit,'final_source_fit':final_fit,'source_measurements':rows,
        'optimizer_converged':bool(development_fit['success'] and final_fit['success']),
        'limits':'Held-out time checks on three completed sources; not a unique-parameter recovery test or physical model validation.'}
    dump(output,receipt);return receipt
