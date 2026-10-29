"""Fresh frozen physics-repair experiment; retain precursor and all failures."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import argparse,json,shutil,time
from .experiment import checked,dump,sha
from .challenges import generate,run_action,response
from .calibrated_pen import fit_source
from .forecast_contract import evidence_hash

VERSION='operating-challenges-20261028-model-repair-v3'


def fit_job(history,paths,source_plan):
    start=time.monotonic()
    from .oxygen import run_continuous
    try:return {'fit':run_continuous(paths,fit_source,history,paths,source_plan=source_plan),'seconds':time.monotonic()-start,'error':None}
    except Exception as exc:return {'fit':None,'seconds':time.monotonic()-start,'error':type(exc).__name__+': '+str(exc)}


def prepare(root,prior):
    base=root/'precursor-dataset';output=root/'dataset'
    if output.exists():raise ValueError('Fresh repaired dataset required')
    if not base.exists():generate(base,prior,48,9001,source_air_factor=1.15,require_source_admission=True,continuous_oxygen=True)
    catalogue=checked(base,'public/catalogue.json');protocol=checked(base,'protocol.json');paths=protocol['paths']
    histories={}
    for item in catalogue:
        if item['simulator']=='pensim':
            p=checked(base,f"public/{item['case_id']}/packet.json")
            histories[evidence_hash(p['source_history'])]=p['source_history']
    fits={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        source_plan={'feed_factor':1.,'air_factor':protocol['source_air_factor'],'apply_after_h':60.}
        pending={pool.submit(fit_job,h,paths,source_plan):digest for digest,h in histories.items()}
        for future in as_completed(pending):
            digest=pending[future];fits[digest]=future.result()
            dump(root/'fits'/(digest+'.json'),fits[digest])
            print(json.dumps({'source_fits':len(fits),'planned':len(histories),'error':fits[digest]['error']}),flush=True)
    output.mkdir(parents=True)
    calibration_hashes={};model_errors=[]
    for index,item in enumerate(catalogue):
        case=item['case_id'];full=checked(base,f'public/{case}/packet.json')
        full['experiment_version']=VERSION;full['forecast_contract_version']=2
        if item['simulator']=='pensim':
            digest=evidence_hash(full['source_history']);fit=fits[digest]['fit']
            full['source_operating_plan']={'feed_factor':1.,'air_factor':protocol['source_air_factor'],'apply_after_h':60.}
            full['source_calibration']={'physical_parameter_fit':fit,'product_ratio':1.,'indicator_offset':0.,
                'source_history_sha256':digest,'evidence_scope':'completed_source_before_receiving'}
        else:
            full['source_operating_plan']={'flow_factor':1.,'nutrient_factor':1.,'apply_after_h':0.}
            full['model_execution_context']={'initialization':'observed_source_state_shared_with_receiver','residual_origin':'nominal_initialization_difference'}
        calibration_hashes[case]=evidence_hash(full['source_calibration'])
        library={}
        for action in full['allowed_actions']:
            try:library[action]=response(full,action,run_action(full,action,paths,nominal=True))
            except Exception as exc:
                library[action]={'classification':'frozen_model_execution_failure','action_id':action,'predictions':{},'error':type(exc).__name__+': '+str(exc)}
                model_errors.append({'case_id':case,'action':action,'error':library[action]['error']})
        dump(output/'public'/case/'packet.json',full)
        dump(output/'model-library'/case/'nominal.json',library)
        target=output/'evaluator'/case/'truth.json';target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(base/f'evaluator/{case}/truth.json',target)
        if index%12==0:print(json.dumps({'repaired_packets':index+1,'planned':len(catalogue)}),flush=True)
    protocol.update(version=VERSION,classification='exploratory_fresh_cases_after_diagnostic_model_repairs',
        model_freeze='Algorithm and bounds frozen before new cases; per-case source-only kinetic fit. SMPL observed-state initialization, no stale output bias.',
        frozen_calibrations=None,case_calibration_sha256=calibration_hashes,
        preparation={'source_fits':len(fits),'fit_failures':sum(bool(v['error']) for v in fits.values()),'fit_compute_seconds':sum(v['seconds'] for v in fits.values()),'model_action_errors':model_errors},
        precursor_manifest_sha256=sha(base/'manifest.json'),
        fixes=['PenSim current-source full P/DO/S trajectory fit with coupled production kinetics; no output offsets',
            'SMPL remove nominal-initialization correction after observed-state initialization',
            'explicit common source/receiving plans and action-specific forecast labels'],
        unresolved=['Full230h empirical viscosity law','Independent empirical physical validity','Hidden morphology/future disturbances','Same-biology fixed-geometry transfer proxy'])
    physical=list(protocol['frozen_model_files_sha256'])
    physical += [str(Path(__file__).with_name(name).resolve()) for name in ('calibrated_pen.py','forecast_contract.py','challenges.py','repair_study.py','oxygen.py')]
    physical += [str(p) for p in Path(paths['native']).glob('*.so')]
    protocol['frozen_model_files_sha256']={f:sha(f) for f in physical}
    protocol['runner_source_sha256']={f.name:sha(f) for f in Path(__file__).parent.glob('*') if f.suffix in ('.py','.mjs')}
    dump(output/'protocol.json',protocol)
    for relative in ('coverage-failures.json','public/catalogue.json','evaluator/catalogue.json'):
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/relative,target)
    dump(output/'manifest.json',{'files_sha256':{str(p.relative_to(output)):sha(p) for p in output.rglob('*.json') if p.name!='manifest.json'}})
    dump(output/'generation-status.json',{'status':'complete','cases':len(catalogue),'model_errors':model_errors})
    print(json.dumps({'generation':'complete','cases':len(catalogue),'model_errors':len(model_errors)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--prior',type=Path,required=True);a=p.parse_args();prepare(a.root,a.prior)
