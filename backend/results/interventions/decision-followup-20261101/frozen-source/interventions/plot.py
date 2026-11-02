"""Separate scientific outcome plots; no aggregate success score."""
from pathlib import Path
import argparse,json,os
import numpy as np


def plot(report):
    os.environ.setdefault('MPLCONFIGDIR','/private/tmp/biodemo-intervention-mpl')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d=json.loads((report/'analysis.json').read_text());g=d['groups'];labels=['AI alone','AI + physics'];colors=['#64748b','#167365']
    fig,axes=plt.subplots(2,3,figsize=(14,8))
    panels=[('mean_product_mass_kg','Product inventory','kg; stopped batches count zero'),('mean_post_decision_violation_h','Oxygen violations after decision','hours below 2 mg/L; lower better'),('mean_whole_process_violation_h','Whole-process oxygen violations','hours; earlier violations stay counted'),('mean_wall_seconds','Agent execution time','wall seconds, not engineer time'),('mean_measurement_delay_h','Waiting for requested assays','simulated hours, separate from CPU time')]
    for ax,(key,title,unit) in zip(axes.flat,panels):
        values=[g[a][key] or 0 for a in ['A','B']];ax.bar(labels,values,color=colors);ax.set_title(title,loc='left',fontsize=11,fontweight='bold');ax.set_ylabel(unit,fontsize=9)
        for i,v in enumerate(values):ax.annotate(f'{v:.2f}',(i,v),xytext=(0,5),textcoords='offset points',ha='center',fontsize=10)
        ax.set_ylim(0,max(max(values)*1.25,.1));ax.spines[['top','right']].set_visible(False)
    ax=axes[1,2];xs=np.arange(2)
    recover=d.get('outcomes_by_recoverability',{}).get('no_feasible_operating_plan',{})
    missed=[recover.get(a,{}).get('decisions',0)-recover.get(a,{}).get('stops',0) for a in ['A','B']]
    ax.bar(xs,missed,color='#b77931',label='Continued despite no feasible plan')
    for i,v in enumerate(missed):ax.annotate(str(v),(i,v),xytext=(0,5),textcoords='offset points',ha='center')
    ax.set_xticks(xs,labels);ax.set_title('Missed necessary stops',loc='left',fontsize=11,fontweight='bold');ax.set_ylabel('Decisions in13 no-feasible-plan scenarios',fontsize=9);ax.set_ylim(0,max(max(missed)*1.25,1));ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Intervention A/B with an imperfect receiving-process model',x=.045,ha='left',fontweight='bold',fontsize=15)
    fig.text(.045,.025,f"{d['protocol']['independent_scenarios']} independent scenarios; two repetitions/arm. Means condition on completed submissions.\n{len(d['numerical_domain_failure_cases'])} numerical-domain coverage failures retained. Simulated operating constraints, no measured product-quality outcome.",fontsize=9)
    fig.tight_layout(rect=(.01,.09,1,.94));fig.savefig(report/'outcomes.png',dpi=160);plt.close(fig)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);a=p.parse_args();plot(a.report)
