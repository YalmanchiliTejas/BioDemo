"""Make a shareable scientific figure from recomputed evaluation results."""
import argparse
import json
from pathlib import Path
import os

os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/sievance-matplotlib-20261101')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(analysis_path, output):
    data = json.loads(analysis_path.read_text())
    groups = data['summaries']
    arms = ['A', 'B', 'model_only']
    labels = ['GLM-5.3\nagent', 'GLM-5.3\n+ model', 'Model-only\nselector']
    colors = ['#64748b', '#0284c7', '#0f766e']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#334155', 'text.color': '#0f172a',
                         'axes.edgecolor': '#cbd5e1', 'xtick.color': '#334155', 'ytick.color': '#334155'})
    fig, axes = plt.subplots(1, 3, figsize=(15, 6.4))
    fig.patch.set_facecolor('#ffffff')
    n = len(data['cases'])
    fig.suptitle('Does a mechanistic model improve agent decisions?', x=.06, y=.97,
                 ha='left', fontsize=21, fontweight='bold')
    fig.text(.06, .89, f'EXPLORATORY SIMULATION  ·  {n} scenarios  ·  same GLM-5.3 and evidence in both agent arms',
             fontsize=12, color='#475569')
    metrics = [('correct', 'Correct constrained decisions', 'Decisions (%)'),
               ('violating_operation', 'Constraint-violating operations', 'Decisions (%)'),
               ('mean_feasible_mass_kg', 'Constraint-feasible inventory', 'Mean simulated inventory (kg)')]
    for ax, (key, title, ylabel) in zip(axes, metrics):
        values = [groups[a][key] / n * 100 if key in ['correct', 'violating_operation'] else groups[a][key] for a in arms]
        bars = ax.bar(np.arange(3), values, color=colors, width=.62, zorder=3)
        ax.set_xticks(np.arange(3), labels)
        ax.set_title(title, loc='left', fontsize=12, fontweight='bold', pad=16)
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', color='#e2e8f0', zorder=0)
        ceiling = 115 if key in ['correct', 'violating_operation'] else max(values) * 1.22 + 1
        ax.set_ylim(0, ceiling)
        for bar, value, arm in zip(bars, values, arms):
            label = f"{groups[arm][key]}/{n}" if key in ['correct', 'violating_operation'] else f'{value:.1f}'
            ax.text(bar.get_x()+bar.get_width()/2, value+ceiling*.025, label, ha='center', fontweight='bold')
    effect = data['paired_contrasts']['correct']
    if effect:
        delta = effect['mean'] * 100
        lo, hi = [v * 100 for v in effect['interval95']]
        fig.text(.06, .16, f'Paired improvement in correct decisions: {delta:+.1f} percentage points  '
                 f'(descriptive 95% interval {lo:+.1f} to {hi:+.1f})', fontsize=12, fontweight='bold')
    fig.text(.06, .095, 'Correct = feasible operation, or stop when no permitted plan is feasible. Failed submissions count incorrect.',
             fontsize=10, color='#475569')
    fig.text(.06, .055, 'Inventory counts zero for stops/violations; no product-quality or real-plant benefit is established. '
             'Prior real CHO forecasts showed no model-access benefit.', fontsize=9.5, color='#475569')
    fig.subplots_adjust(left=.065, right=.98, top=.77, bottom=.32, wspace=.36)
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output/'decision-results.png', dpi=180, facecolor='white')
    fig.savefig(output/'decision-results.svg', facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--analysis', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    plot(a.analysis, a.output)
