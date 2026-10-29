"""Static scientific figure, regenerated from the independent report analysis."""
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(report):
 d=json.loads((report/'analysis.json').read_text())
 fig,axes=plt.subplots(2,3,figsize=(14,8))
 colors=('#476878','#c26c35')
 def panel(ax,title,rows,labels,unit,scale=1):
  x=np.arange(len(rows));w=.32
  ax.bar(x-w/2,[r['A']*scale for r in rows],w,color=colors[0],label='AI alone')
  ax.bar(x+w/2,[r['B']*scale for r in rows],w,color=colors[1],label='Same AI + physics')
  ax.set_xticks(x,labels);ax.set_title(title,fontsize=12,loc='left',fontweight='bold');ax.set_ylabel(unit,fontsize=10)
  ax.axhline(0,color='#637078',lw=.6);ax.spines[['top','right']].set_visible(False)
  ax.set_axisbelow(True);ax.yaxis.grid(True,alpha=.2)
  for idx,r in enumerate(rows):
   for delta,arm in [(-w/2,'A'),(w/2,'B')]:
    val=r[arm]*scale
    ax.annotate(f'{val:.3g}',(idx+delta,val),xytext=(0,4 if val>=0 else -13),textcoords='offset points',ha='center',fontsize=9)
  ax.margins(y=.25)
 sim=d['simulated']['summary'];cho=d['real_CHO']['summary']
 for col,process in enumerate(('pensim','mab')):
  pred=[r for r in sim if r['simulator']==process and r['task']=='prediction' and r['metric']=='normalized_absolute_error']
  labels=['Product','Oxygen'] if process=='pensim' else ['Antibody','Viable cells']
  panel(axes[0,col],('PenSimPy' if process=='pensim' else 'SMPL upstream')+' predictions',pred,labels,'Mean absolute error (% actual), lower better',100)
  actions=[r for task in ('outcome','transfer') for r in sim if r['simulator']==process and r['task']==task and r['metric']=='objective_change_percent']
  panel(axes[1,col],('PenSimPy' if process=='pensim' else 'SMPL upstream')+' decisions',actions,['Operating change','Recipe transfer'],'Change vs KEEP (%), higher better')
 for ax,field,title,unit in [(axes[0,2],'viable_cells_million_per_ml','Real CHO: viable-cell forecast','MAE (million cells/mL), lower better'),(axes[1,2],'glucose_g_per_l','Real CHO: glucose forecast','MAE (g/L), lower better')]:
  row=next(r for r in cho if r['field']==field and r['metric']=='absolute_error')
  panel(ax,title,[row],['Whole conditions held out'],unit)
 handles,labels=axes[0,0].get_legend_handles_labels()
 fig.legend(handles,labels,loc='upper right',bbox_to_anchor=(.99,.995),ncol=2,frameon=False)
 fig.suptitle('Does supplying physics improve the same AI?',x=.04,y=.985,ha='left',fontsize=17,fontweight='bold')
 fig.text(.04,.025,'Simulator: 12 seed clusters per task; 3 AI repetitions. Real CHO: 8 conditions, 16 cultures; 2 repetitions.\nCluster-weighted paired means. Failures retained separately. Descriptive intervals and exact denominators are in the report. No plant validation.',fontsize=9,color='#46545a')
 fig.tight_layout(rect=(.02,.09,.99,.93));fig.savefig(report/'comparison.png',dpi=160);plt.close(fig)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('report',type=Path);a=p.parse_args();plot(a.report)
