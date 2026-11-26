"""Replay four previously inspected cases separately from the frozen cohort."""
from copy import deepcopy
import argparse
from pathlib import Path

from benchmarks.physics_value.lyo_reference import reference
from src.lifesci.lyophilization.reference import operation_config
from src.lifesci.lyophilization.heterogeneous import simulate
from .study import ACTIONS, dump, predict, write_new_directory


def replay(output):
    output=Path(output);write_new_directory(output)
    results=[]
    for label,kv,rp,capacity in [('S01',1.,1.,1.),('S02',1.25,1.,1.),('S03',1.,1.4,1.),('S04',1.,1.,.42)]:
        config=operation_config();config['duration_h']=90.
        config['populations']=[{'weight':.8,'kv_scale':.95,'rp_scale':1.05},{'weight':.2,'kv_scale':1.2,'rp_scale':.9}]
        config['thermal']={'vial_heat_capacity_j_k':3.,'initial_equilibrium':True}
        actual=reference(config,{'kv_scale':kv,'rp_scale':rp,'capacity_scale':capacity})
        observations=[{k:r[k] for k in ['time_h','available_at_h','product_temperature_c','remaining_ice_kg_per_vial','chamber_pressure_pa']}
                      for r in actual['trajectory'] if r['time_h']<=6.]
        packet={'case_id':label,'task':'forecast','config':config,'cutoff_h':6.,'observations':observations,'allowed_actions':ACTIONS}
        predictions={arm:predict(packet,arm,'keep') for arm in ('B','C')}
        row={'case_id':label,'classification':'previously inspected development case; not scored-cohort evidence',
             'changes_from_original':'additional mass and pressure channels; event-safe evaluator; same applicability gate B/C',
             'packet':packet,'reference':actual,'predictions':predictions}
        dump(output/(label+'.json'),row);results.append(row)
    dump(output/'summary.json',[{'case_id':r['case_id'],'truth':{k:r['reference'][k] for k in ('first_critical_h','first_capacity_h','completion_time_h')},
         'predictions':{a:{k:v[k] for k in ('thermal_warning','capacity_warning','completion_time_h')} for a,v in r['predictions'].items()}} for r in results])
    draw(results[1],output)


def draw(case,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.lifesci.lyophilization.model import simulate as legacy
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
    truth=[r for r in case['reference']['trajectory'] if r['active_max_temperature_c'] is not None]
    ax.plot([r['time_h'] for r in truth],[r['active_max_temperature_c'] for r in truth],color='#b03a2e',label='Reference hottest active population',linewidth=2)
    ax.plot([r['time_h'] for r in truth],[r['product_temperature_c'] for r in truth],color='#777777',linestyle=':',label='Reference mean thermal node')
    for arm,name,color,style in [('B','Legacy representative vial','#327b8a','--'),('C','Revised hottest active population','#276749','-')]:
        config=deepcopy(case['packet']['config']);fit=case['predictions'][arm]['calibration']
        config['equipment']['kv_scale']=fit['kv_scale'];config['product']['rp_scale']=fit['rp_scale']
        run=(legacy if arm=='B' else simulate)(config)
        field='interface_temperature_c' if arm=='B' else 'active_max_temperature_c'
        rows=[r for r in run['trajectory'] if r.get(field) is not None and r['time_h']>=6.]
        ax.plot([r['time_h'] for r in rows],[r[field] for r in rows],color=color,linestyle=style,label=name)
    ax.axhline(-28,color='#b03a2e',linestyle='--',alpha=.6,label='Declared critical temperature')
    ax.axvline(6,color='black',linestyle=':',label='Evidence cutoff (6 h)')
    ax.set(xlim=(0,32),ylim=(-45,-24),xlabel='Elapsed primary-drying time (h)',ylabel='Thermal-node temperature (°C)',
           title='Why an average-vial forecast can miss a hot population')
    ax.legend(fontsize=8,loc='lower right');ax.spines[['right','top']].set_visible(False)
    fig.supxlabel('Previously inspected synthetic S02 development case; shared physics; additional mass/pressure observations. Not experimental validation.',fontsize=8)
    for ext in ('png','svg'):fig.savefig(output/f'hot-population-example.{ext}',dpi=180)
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    replay(parser.parse_args().output)
