"""Execute unmodified upstream dictionaries/units in a separate process."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

PIN='c6a9225a9e551ae4e7c11c1ef056b67c6204afbd'
CHECKOUT=Path(os.environ.get('LYOPRONTO_CHECKOUT','/private/tmp/lyohub-rerun-source'))
REQUIRED={'vial':('Av','Ap','Vfill'),'product':('cSolid','R0','A1','A2'),'ht':('KC','KP','KD')}


def missing_inputs(source):
    config=source['native_inputs'];missing=[]
    for section,keys in REQUIRED.items():
        for key in keys:
            if config.get(section,{}).get(key) is None:missing.append(section+'.'+key)
    if source.get('reported_pressure'):
        if not source['reported_pressure'].get('unit'):missing.append('pressure_unit')
    elif not config.get('Pchamber',{}).get('setpt'):missing.append('Pchamber.setpt')
    if not config.get('Tshelf',{}).get('setpt'):missing.append('Tshelf.setpt')
    if source['task']=='select_recipe':
        if config.get('product',{}).get('T_pr_crit') is None:missing.append('product.T_pr_crit')
        if not source.get('eq_cap'):missing.append('eq_cap')
        if not source.get('nVial'):missing.append('nVial')
    return missing


def configuration(source,pressure_torr=None,shelf_temperature_c=None):
    missing=missing_inputs(source)
    if missing:raise ValueError('Missing characterized inputs: '+', '.join(missing))
    c=deepcopy(source['native_inputs'])
    if source.get('reported_pressure') and pressure_torr is None:raise ValueError('Pass pressure_torr explicitly, interpreting the reported pressure and its unit.')
    horizon=source['horizon_minutes']
    if pressure_torr is not None:
        if not .02<=pressure_torr<=.30:raise ValueError('pressure_torr outside declared benchmark envelope .02.. .30 Torr')
        c['Pchamber']={'setpt':[pressure_torr],'dt_setpt':[horizon],'ramp_rate':.5}
    if shelf_temperature_c is not None:
        if not -50<=shelf_temperature_c<=25:raise ValueError('shelf_temperature_c outside declared benchmark envelope -50..25 C')
        c['Tshelf']={'init':c['Tshelf'].get('init',-35.),'setpt':[shelf_temperature_c],'dt_setpt':[horizon],'ramp_rate':c['Tshelf'].get('ramp_rate',1.)}
    if source['task']=='select_recipe':
        recipe={'pressure_torr':c['Pchamber']['setpt'][0],'shelf_temperature_c':c['Tshelf']['setpt'][0]}
        if recipe not in source['recipe_candidates']:raise ValueError('Recipe must be one of the explicitly allowed candidate pairs')
    c['dt']=None
    return c


def native_rows(config):
    head=subprocess.check_output(['git','-c','core.fsmonitor=false','-C',str(CHECKOUT),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-c','core.fsmonitor=false','-C',str(CHECKOUT),'status','--porcelain','--untracked-files=no'],text=True).strip()
    if head!=PIN or dirty:raise ValueError('Unmodified pinned upstream checkout required')
    process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(CHECKOUT)],input=json.dumps(config,allow_nan=False),
        text=True,capture_output=True,timeout=40,env={**{k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT')},
        'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','MPLCONFIGDIR':'/private/tmp/lyopronto-native-mpl','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    try:result=json.loads(process.stdout)
    except ValueError:raise RuntimeError('Native solver process failed') from None
    if process.returncode or result.get('error'):raise ValueError(result.get('error','Native solver error'))
    return result


def tool_summary(result,config):
    rows=result['rows']
    return {'model':'LyoPRONTO 1.2.0','upstream_commit':PIN,'native_input_sha256':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
        'last_elapsed_h':rows[-1][0],'last_dried_percent':rows[-1][6],
        'maximum_returned_front_temperature_c':max(r[1] for r in rows),
        'maximum_returned_bottom_temperature_c':max(r[2] for r in rows),
        'maximum_returned_flux_kg_h_m2':max(r[5] for r in rows),
        'pressure_output_mtorr':rows[0][4],
        'columns':['elapsed_h','front_temperature_c','bottom_temperature_c','shelf_temperature_c','pressure_mtorr','flux_kg_h_m2','dried_percent'],
        'trajectory_sample':[rows[i] for i in sorted(set([0,len(rows)-1,*range(0,len(rows),max(1,len(rows)//12))]))],
        'warnings':result['warnings'],'qualification':'Native solver result, not an experimental observation or approval; no continuous-maximum guarantee; forward mode does not enforce thermal/equipment limits.'}


if __name__=='__main__':
    import contextlib,io,warnings
    try:
        sys.path.insert(0,sys.argv[2])
        import numpy as np
        from lyopronto import calc_knownRp
        c=json.loads(sys.stdin.read())
        with warnings.catch_warnings(record=True) as caught,contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter('always')
            rows=calc_knownRp.dry(c['vial'],c['product'],c['ht'],c['Pchamber'],c['Tshelf'],None)
        if rows.ndim!=2 or rows.shape[1]!=7 or not np.isfinite(rows).all():raise ValueError('Invalid native trajectory')
        print(json.dumps({'rows':rows.tolist(),'warnings':list(dict.fromkeys(str(w.message) for w in caught))},allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__+': '+str(exc)}));raise SystemExit(1)
