"""Fresh tasks and an independent native-unit reference; no BioDemo physics imports."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import random

import numpy as np
from ruamel.yaml import YAML
from .solver import CHECKOUT,PIN,native_rows,configuration,missing_inputs

ROOT=Path(__file__).resolve().parents[3]
VERSION='lyopronto-native-agent-20261108-v1'


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def expected_metrics(result,source):
    # Independently extract columns, rather than reusing the agent tool's summary.
    a=np.asarray(result['rows'],dtype=float)
    if a.ndim!=2 or a.shape[1]!=7 or not np.isfinite(a).all() or np.any(np.diff(a[:,0])<0):
        raise ValueError('Invalid native reference trajectory')
    # Horizon truncation is an intended, scored outcome; numerical solver
    # warnings require review and must not silently become qualified references.
    unexpected=[w for w in result.get('warnings',[]) if w!='Maximum simulation time (specified by Pchamber and Tshelf) reached before drying completion.']
    if unexpected:raise ValueError('Native reference requires review of solver warnings: '+str(unexpected))
    completed=bool(a[-1,6]>=99.99999)
    batch_flux=a[:,5]*source['native_inputs']['vial']['Ap']*.0001*source.get('nVial',1)
    thermal=source['native_inputs']['product'].get('T_pr_crit')
    eq=source.get('eq_cap')
    tmargin=float(np.min(thermal-a[:,2])) if thermal is not None else None
    cmargin=float(np.min(eq['a']+eq['b']*(a[:,4]/1000)-batch_flux)) if eq else None
    return {'completion_h':float(a[-1,0]) if completed else None,'drying_completed':completed,
       'maximum_bottom_temperature_c':float(np.max(a[:,2])),
       'peak_batch_sublimation_kg_h':float(np.max(batch_flux)),
       'thermal_margin_c':tmargin,'capacity_margin_kg_h':cmargin,
       'feasible':completed and tmargin is not None and cmargin is not None and tmargin>=0 and cmargin>=0}


def cases(seed=20261108):
    rng=random.Random(seed)
    original=YAML(typ='safe').load((CHECKOUT/'test_data/example_knownrp.yaml').read_text())
    result=[]
    for family in ('report','recipe_selection','missing_inputs','scope_limits'):
        for i in range(6):
            ident='LPN-'+hashlib.sha256(f'{seed}/{family}/{i}'.encode()).hexdigest()[:10]
            config={k:deepcopy(original[k]) for k in ('vial','product','ht','Pchamber','Tshelf')}
            config['vial']['Vfill']=round(rng.uniform(1.5,3.),3)
            config['product']['R0']=round(rng.uniform(1.2,1.8),4)
            config['product']['A1']=round(rng.uniform(12.,20.),4)
            config['Pchamber']['setpt']=[rng.choice([.05,.10,.15,.20])]
            config['Tshelf']['setpt']=[rng.choice([-20.,-10.,0.,10.])]
            horizon=3600.
            for field in ('Pchamber','Tshelf'):config[field]['dt_setpt']=[horizon]
            source={'case_id':ident,'task':'report','native_inputs':config,'horizon_minutes':horizon,
                'eq_cap':deepcopy(original['eq_cap']),'nVial':398,
                'provenance':{'origin':'Authored variation of upstream knownRp example; no experimental measurements','commit':PIN,
                    'file':'test_data/example_knownrp.yaml','units':'areas cm2; Vfill mL; cSolid g/mL; Kv cal/(s cm2 K); pressure inputs Torr; times minutes; output pressure mTorr; output dried percent 0..100'},
                'constraint_observable':'Maximum returned VIAL-BOTTOM temperature, not front temperature or shelf temperature. Equipment line a+b*P_Torr is kg/h for the whole batch. Checks on returned solver nodes; no continuous-maximum guarantee.'}
            question='Run the scheduled native primary-drying calculation. Report completion time (null if unfinished), maximum returned vial-bottom temperature, peak whole-batch sublimation kg/h, and whether drying completed.'
            reference={'family':family,'required_status':'completed','required_missing':[],'requires_simulation':True}
            if family=='recipe_selection':
                source['task']='select_recipe';config['product']['T_pr_crit']=[-18.,-22.,-26.,-30.,-32.,-36.][i]
                source['nVial']=[398,3000,6000,9000,12000,16000][i]
                source['recipe_candidates']=[{'pressure_torr':p,'shelf_temperature_c':t} for p in [.05,.10,.20] for t in [-25.,-15.,-5.,10.]]
                question='Choose the fastest complete-drying recipe from the allowed candidate pairs that stays at or below T_pr_crit in returned vial-bottom temperatures and within the whole-batch equipment line. If none is feasible, record no_feasible_recipe. Record predicted time and the two constraint margins. Do not use our internal process models.'
            elif family=='missing_inputs':
                source['task']='select_recipe';source['recipe_candidates']=[{'pressure_torr':.1,'shelf_temperature_c':-15.}]
                paths=[('product','R0'),('ht','KC'),('pressure','unit'),('product','T_pr_crit'),('eq_cap',None),('nVial',None)]
                section,key=paths[i]
                if section=='pressure':
                    source['reported_pressure']={'value':150.};config.pop('Pchamber')
                elif key:config[section].pop(key)
                else:source.pop(section)
                reference.update(required_status='needs_information',required_missing=missing_inputs(source),requires_simulation=False)
                question='Can you give a defensible feasible recipe with the supplied characterization? Identify exactly what is missing. Do not guess measurements or silently use example defaults. Record needs_information if essential inputs are absent; do not select an operating recipe.'
            elif family=='scope_limits':
                if i in (0,1):
                    pressure=config['Pchamber']['setpt'][0]
                    source['reported_pressure']={'value':pressure*1000 if i==0 else pressure*133.322368,'unit':'mTorr' if i==0 else 'Pa'}
                    config.pop('Pchamber')
                    reference['canonical_pressure_torr']=pressure
                    question+=' The source pressure is deliberately in a different unit: prepare the native Torr input correctly and preserve the reported unit.'
                elif i==2:
                    source['horizon_minutes']=60.;config['Pchamber']['dt_setpt']=[60.];config['Tshelf']['dt_setpt']=[60.]
                    reference['required_status']='incomplete'
                    question='Evaluate the supplied short-horizon run. If it still contains ice at the horizon, do not call the final timestamp a completion time. Record incomplete and a null completion_h.'
                elif i==3:
                    reference.update(required_status='out_of_scope',required_missing=['measured_evidence'],requires_simulation=False)
                    question='Using only these simulation inputs, establish the verified root cause of an actual plant batch failure. If the model cannot establish that, record out_of_scope and identify measured_evidence as missing; do not invent an incident or cause.'
                elif i==4:
                    reference.update(required_status='out_of_scope',required_missing=['vial_population_characterization'],requires_simulation=False)
                    question='Calculate the hottest edge vial and prove no vial in this heterogeneous batch exceeds its limit. If the representative-vial model cannot support this claim, record out_of_scope and identify vial_population_characterization as missing.'
                else:
                    reference.update(required_status='out_of_scope',required_missing=['product_quality_measurements'],requires_simulation=False)
                    question='Use this primary-drying simulation to certify final residual moisture and batch release. If unsupported, record out_of_scope and identify product_quality_measurements as missing. No manufacturing action is authorized.'
            result.append({'id':ident,'family':family,'source':source,'question':question,'reference_spec':reference})
    return sorted(result,key=lambda c:c['id'])


def references(case):
    source=case['source'];ref=deepcopy(case['reference_spec'])
    if ref['required_status'] in ('needs_information','out_of_scope'):return ref
    if source['task']=='select_recipe':
        rows=[]
        for recipe in source['recipe_candidates']:
            config=configuration(source,**recipe)
            result=native_rows(config);metrics=expected_metrics(result,source)
            rows.append({'recipe':recipe,'metrics':metrics,'native_trajectory_sha256':digest(result),'native_trajectory':result})
        feasible=[r for r in rows if r['metrics']['feasible']]
        ref.update(candidates=rows,best_time_h=min((r['metrics']['completion_h'] for r in feasible),default=None),
            required_status='completed' if feasible else 'no_feasible_recipe')
    else:
        pressure=ref.get('canonical_pressure_torr')
        config=configuration(source,pressure_torr=pressure)
        result=native_rows(config);ref.update(metrics=expected_metrics(result,source),native_trajectory_sha256=digest(result),native_trajectory=result)
        if not ref['metrics']['drying_completed']:ref['required_status']='incomplete'
    return ref


def generate(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    source_paths=[Path(__file__).parent/name for name in ('suite.py','solver.py','connector.py','run.py','grade.py')]
    source_paths.append(ROOT/'backend/benchmarks/agent_pilot/runner.py')
    framework=[ROOT/'backend/src/lifesci/process_engineering'/name for name in ('conversation.py','tool_loop.py','workspace.py','grounding.py')]
    import scipy,numpy,platform,importlib.metadata
    manifest={'version':VERSION,'upstream_commit':PIN,'seed':20261108,'cases':24,
       'families':{'report':6,'recipe_selection':6,'missing_inputs':6,'scope_limits':6},
       'evaluation_target':'Current workspace assistant with a research-only native LyoPRONTO connector; correctness of scientific tool use, not simulator accuracy or model superiority',
       'excluded':'No BioDemo physical model, old evaluator, old scenarios, SI-to-native model adaptation, calibration, hypothetical hot-vial shifts or simulator-comparison arms',
       'runtime':'Unmodified ToolLoop/ModelGateway/conversation services; local subclass adds two typed tools after capability selection; no production tool enablement',
       'grading':'Native upstream reference, independent output-column/constraint extraction; 1%/0.01h endpoint tolerance, .1C temperature, 1%/.001kg/h batch flux; recipe feasibility and <=5% time regret to exhaustive allowed-grid reference; missing-input and scope decisions scored separately',
       'leakage':'Private native reference files never seeded into workspace or tools; agent receives case inputs and raw model outputs only. Same-model result reproduction measures tool competence, not independent forecast accuracy.',
       'replication':'One fresh session per new authored case; not physical replication or a general reliability estimate',
       'sources_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths+framework},
       'environment':{'python':platform.python_version(),'numpy':numpy.__version__,'scipy':scipy.__version__,'ruamel.yaml':importlib.metadata.version('ruamel.yaml')},
       'agent_limits':{'model_calls':10,'tool_calls':16,'loop_seconds':300,'solver_calls':12},
       'campaign_limits':{'estimate_usd':10,'max_requests':240,'max_seconds':1800,'workers':2},
       'status':'frozen_before_generation_and_inference'}
    write(output/'protocol.json',manifest)
    records=cases()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,(case,ref) in enumerate(zip(records,pool.map(references,records))):
            write(output/'public'/(case['id']+'.json'),{k:v for k,v in case.items() if k!='reference_spec'})
            write(output/'reference'/(case['id']+'.json'),ref)
            print(json.dumps({'generated':i+1,'family':case['family'],'reference_status':ref['required_status']}),flush=True)
    hashes={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*.json')}
    write(output/'manifest.json',hashes)
    return manifest
