"""Explicit UI-contract fixture: scripted planner, real solvers, no live AI claim.

Only run against a development database. Qualification is confined to the
in-memory test registry; it does not qualify or alter the live server's routes.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path
import runpy

from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.store import RecordStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='Development SQLite file served by the local API')
    parser.add_argument('--output', default='../docs/process-simulation/conversation-artifacts/contract-results.json')
    args = parser.parse_args()
    helpers = runpy.run_path(str(Path(__file__).with_name('test_engineering_conversation.py')))
    fake, send, node, plan, binding = [helpers[k] for k in ('fake_planner', 'send', 'node', 'plan', 'binding')]
    p = Platform(RecordStore(args.database), providers={})
    seed(p)
    ctx = p.identity.context_for(TENANT, 'priya')
    service = p.engineering_conversations
    fake(p, [{'reply': 'TEST PLANNER · UI contract check. I will run the real primary-drying solver on the published/reconstructed example. This scripted plan is not measured live AI performance.',
        'workflow': helpers['simulate_workflow']()}])
    thread = send(p, ctx, service.create(ctx, {}), '[UI CONTRACT TEST — scripted planner] Assess the reconstructed freeze-drying transfer with charts and a 3D review.', enable_demo=True)
    if thread['turns'][-1]['status'] != 'completed': raise RuntimeError(thread['turns'][-1]['issues'])
    result = next(a for a in thread['turns'][0]['artifacts'] if a['kind'] == 'physical_analysis_result')
    fake(p, [{'reply': 'TEST PLANNER · I will compare the saved forecast with a 6,000-vial scenario using the real solver. Operating changes remain unvalidated what-if assumptions.',
        'workflow': [node('lower_load', 'physical_context_variant', {'source_id': thread['source_ids'][0], 'label': '6000-vial scenario',
            'rationale': 'Assess vapor-handling trade-offs of lower loading without changing the original equipment record', 'load_vials': 6000}),
            node('select_lower', 'physical_pipeline_prepare', plan(binding('lower_load')), ['lower_load']),
            node('simulate_lower', 'physical_pipeline_execute', {'plan_id': binding('select_lower')}, ['select_lower']),
            node('compare', 'physical_results_compare', {'result_ids': [result['id'], binding('simulate_lower')]}, ['simulate_lower'])]}])
    thread = send(p, ctx, thread, '[UI CONTRACT TEST] Compare 6000 vials with the original forecast.')
    if thread['turns'][-1]['status'] != 'completed': raise RuntimeError(thread['turns'][-1]['issues'])
    comparison = service.artifact(ctx, thread['id'], 'physical_analysis_comparison', thread['turns'][-1]['artifacts'][-1]['id'])
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'classification': 'test_planner_real_numerical_solvers_not_AI_performance',
        'conversation_id': thread['id'], 'workflow_steps_per_turn': [len(t['steps']) for t in thread['turns']],
        'models': p.process_models.analysis.catalog.snapshot(), 'comparison': comparison,
        'solver_calls_per_turn': [t['solver_calls_used'] for t in thread['turns']],
        'turn_statuses': [t['status'] for t in thread['turns']]}, indent=2))
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'biodemo-chat-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    for series in comparison['series']:
        rows = series['trajectory']
        axes[0].plot([r['time_h'] for r in rows], [r['interface_temperature_c'] for r in rows], label=series['id'])
        axes[1].plot([r['time_h'] for r in rows], [r['capacity_margin_kg_h'] for r in rows], label=series['id'])
    axes[0].set_ylabel('Interface temperature (°C)')
    axes[1].set_ylabel('Vapor capacity margin (kg/h)')
    axes[1].set_xlabel('Elapsed primary-drying time (h)')
    axes[1].axhline(0, color='black', linewidth=.8)
    axes[0].legend(fontsize=8)
    for ax in axes: ax.grid(alpha=.2)
    fig.suptitle('UI contract: scripted planner / real numerical calculations')
    fig.text(.5, .005, 'Reconstructed inputs; prescribed pressure. Predictions outside equipment limits require a richer model.', ha='center', fontsize=8)
    fig.tight_layout(rect=[0, .025, 1, .96])
    for suffix in ('png', 'svg'): fig.savefig(target.parent/('scenario-plots.'+suffix), dpi=150)
    plt.close(fig)
    print(thread['id'])

if __name__ == '__main__':
    main()
