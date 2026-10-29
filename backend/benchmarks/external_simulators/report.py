"""Human-readable results and independent arithmetic checks, never invent scores."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

from .experiment import checked,dump,model_prediction,sha


def baselines(dataset):
    records=[]
    for item in checked(dataset,'public/catalogue.json'):
        case=item['case_id'];packet=checked(dataset,f'public/{case}/packet.json')
        truth=checked(dataset,f'evaluator/{case}/truth.json')
        nominal=checked(dataset,f'model-library/{case}/nominal.json')
        names=('P','DO2') if item['simulator']=='pensim' else ('mAb_reactor','viable_cells_reactor')
        source=packet['receiving_observations'] or packet['source_history']
        persistence={key:source[-1]['state'][name] for key,name in zip(('product_concentration','process_indicator'),names)}
        trend=dict(persistence)
        if packet['receiving_observations']:
            rows=source[-4:];t=np.array([r['time_h'] for r in rows]);h=packet['receiving_specifications']['horizon_h']
            for key,name in zip(('product_concentration','process_indicator'),names):
                values=np.array([r['state'][name] for r in rows])
                slope,intercept=np.polyfit(t,values,1)
                trend[key]=max(0.,float(slope*h+intercept))
        physics=model_prediction(packet,nominal,'keep')['predictions']
        for label,values in [('last_available_measurement',persistence),('linear_extrapolation',trend),('nominal_physics_without_agent',physics)]:
            errors={key:abs(values[key]-truth['baseline'][key])/max(abs(truth['baseline'][key]),1e-9)
                    for key in ('product_concentration','process_indicator')}
            records.append({**item,'baseline':label,'predictions':values,'relative_errors':errors})
        selected=max(packet['allowed_actions'],key=lambda a:nominal[a]['objective'])
        base=truth['baseline']['objective'];objective=truth['actions'][selected]['objective']
        records.append({**item,'baseline':'nominal_grid_search_without_agent','action_id':selected,
                        'objective_change_percent':100*(objective-base)/max(abs(base),1e-9)})
    return records


def verify_arithmetic(dataset,result):
    errors=[];count=0
    for row in result['records']:
        if row['score'] is None:continue
        case=row['case_id'];truth=checked(dataset,f'evaluator/{case}/truth.json')
        submitted=row['submission'];record=row['score']
        for key in ('product_concentration','process_indicator'):
            actual=truth['baseline'][key];predicted=submitted['predictions'][key]
            calculated=abs(predicted-actual)/max(abs(actual),1e-9)
            if not np.isclose(calculated,record['prediction_errors'][key]['normalized_absolute_error'],rtol=1e-12,atol=1e-12):
                errors.append({'case':case,'arm':row['arm'],'error':'forecast arithmetic mismatch'})
            count+=1
        selected=truth['complete_trajectories'][submitted['action_id']]
        if row['simulator']=='pensim':
            independently_recomputed=selected['trace'][-1]['state']['P']
        else:
            cutoff=0. if row['task']=='transfer' else 6.
            rows=[r for r in selected['trace'] if r['time_h']>=cutoff-1e-8]
            independently_recomputed=float(np.trapz(
                [r['state']['mAb_separator']*selected['physical_commands']['product_outlet_flow'] for r in rows],
                [r['time_h']*60 for r in rows]))
        if not np.isclose(independently_recomputed,record['objective'],rtol=1e-10,atol=1e-5):
            errors.append({'case':case,'arm':row['arm'],'error':'physical objective arithmetic mismatch',
                           'recomputed':independently_recomputed,'reported':record['objective']})
        count+=1
    return {'checks':count,'passed':not errors,'errors':errors,
            'scope':'Independent arithmetic from saved physical trajectories and submissions; same upstream simulation data, not independent plant data.'}


def report(dataset,run,output):
    output.mkdir(parents=True,exist_ok=True)
    result=json.loads((run/'results.json').read_text())
    clean_ab=bool(result['protocol'].get('comparison_type'))
    data_protocol=checked(dataset,'protocol.json')
    controls=baselines(dataset)
    arithmetic=verify_arithmetic(dataset,result)
    if not arithmetic['passed']:raise ValueError('Result arithmetic audit failed: '+json.dumps(arithmetic))
    dump(output/'baselines.json',controls);dump(output/'arithmetic-audit.json',arithmetic)
    dump(output/'results.json',result)
    labels={'pensim':'PenSimPy 96 h','mab':'SMPL 24 h upstream'}
    tasklabels={'prediction':'Prediction','outcome':'Operating decision','transfer':'Simulated recipe transfer'}
    def pct(value):return 'unavailable' if value is None else f'{100*value:.3f}%'
    lines=['# Executed external-simulator agent pilot','',
        f'Run status: **{result["status"]}**. Completed **{result["completed"]}/{result["protocol"]["planned_attempts"]}** planned attempts. Model: `{result["protocol"]["model"]}`.','',
        '**All prediction targets and process outcomes here are simulated.** The final comparison uses two external process models. It does not use real CHO measurements, establish actual site-transfer accuracy, or demonstrate real manufacturing improvements.','',
        '**Critical limit:** complete230h PenSimPy evaluation failed its raw-state check. PenSimPy scores below apply only to a separately declared96h partial process. SMPL scores apply only to its17-state upstream reactor/separator for24h.','',
        '## What was compared','',
        'A: ordinary agent analysis with numerical Python. B: the same agent and public packet, plus live execution of a nominal physical model. Both have the same saved model, low reasoning setting,120s wall ceiling,8 model-call ceiling and10 analysis-tool ceiling. Actions and equations are common. Arm order is counterbalanced and sessions have no shared memory.','',
        'There are four process/regime combinations per simulator (two underlying seeds ×two receiving operating factors), each reused across three tasks. Each table cell has at most four attempts. These correlated development cases do not support statistical significance or broad generalization claims.','',
        'Prediction always targets the KEEP plan, even when the agent selects another action. Operating-decision actions start after receiving measurements (80h PenSimPy,6h SMPL). Transfer actions start before receiving measurements; source history and changed receiving operating specifications are available. Geometry and material/strain realization remain fixed: this is simulated recipe transfer under changed operating conditions, not demonstrated scale-up or a different factory.','',
        '## Prediction error','',
        'Lower is better. Values are mean absolute errors divided by the corresponding simulated actual endpoint, shown as percentages. Failures remain in completion counts; means use valid submissions only. Product and process-indicator errors are separate endpoints.','',
        '| Simulator | Task | Completed A/B | Product error A | Product error B | Indicator error A | Indicator error B |',
        '|---|---|---|---:|---:|---:|---:|']
    for sim in ('pensim','mab'):
        for task in ('prediction','outcome','transfer'):
            a=result['groups'][sim][task]['A'];b=result['groups'][sim][task]['B']
            lines.append(f'| {labels[sim]} | {tasklabels[task]} | {a["completed"]}/{a["attempted"]} / {b["completed"]}/{b["attempted"]} | {pct(a["mean_product_relative_error"])} | {pct(b["mean_product_relative_error"])} | {pct(a["mean_indicator_relative_error"])} | {pct(b["mean_indicator_relative_error"])} |')
    lines+=['','![Recorded product and process-indicator forecast errors](prediction-errors.png)']
    lines+=['','The indicator is endpoint dissolved oxygen (mg/L) for PenSimPy and viable cell concentration (cells/L) for SMPL. Product is penicillin g/L or reactor mAb mg/L, respectively.','',
        '## Did selected actions improve the simulated objective?','',
        'Positive changes beat KEEP in the same actual realization. These objectives are not product quality, commercial yield, validated safety, or real batch success. PenSimPy maximizes96h concentration. SMPL maximizes integrated physical product-outlet mass over the post-decision horizon (18h for an operating decision,24h for transfer).','',
        '| Simulator | Task | Improved actions A/B | Mean objective change A | Mean objective change B |',
        '|---|---|---|---:|---:|']
    for sim in ('pensim','mab'):
        for task in ('outcome','transfer'):
            a=result['groups'][sim][task]['A'];b=result['groups'][sim][task]['B']
            def fmt(value):return 'unavailable' if value is None else f'{value:+.4f}%'
            lines.append(f'| {labels[sim]} | {tasklabels[task]} | {a["actions_improving_objective"]}/{a["attempted"]} / {b["actions_improving_objective"]}/{b["attempted"]} | {fmt(a["mean_objective_change_percent"])} | {fmt(b["mean_objective_change_percent"])} |')
    lines+=['','## Baselines that do not use an AI','',
        'These are scored after freezing the agent run. A last-measurement baseline uses the latest receiving observation, or completed source endpoint for transfer. The nominal-physics baseline calls the same forward-model calculation without asking an agent to interpret it. For transfer, linear extrapolation intentionally reduces to the completed source endpoint because source and receiving clocks are distinct.','',
        '| Simulator | Task | Last-measurement product error | Linear-trend product error | Physics-only product error | Physics-only selected-action change |',
        '|---|---|---:|---:|---:|---:|']
    for sim in ('pensim','mab'):
        for task in ('prediction','outcome','transfer'):
            rows=[r for r in controls if r['simulator']==sim and r['task']==task]
            values={name:np.mean([r['relative_errors']['product_concentration'] for r in rows if r['baseline']==name]) for name in ('last_available_measurement','linear_extrapolation','nominal_physics_without_agent')}
            gain=np.mean([r['objective_change_percent'] for r in rows if r['baseline']=='nominal_grid_search_without_agent'])
            lines.append(f'| {labels[sim]} | {tasklabels[task]} | {pct(values["last_available_measurement"])} | {pct(values["linear_extrapolation"])} | {pct(values["nominal_physics_without_agent"])} | {gain:+.4f}% |')
    lines+=['','An agent that only copies or selects the model outputs has not demonstrated extra value over the physics-only baseline. The small action grid is deliberately limited and is not arbitrary autonomous process design.','',
        '## Integrity and numerical checks','',
        f'- Identical paired packet hashes: **{result["pair_inputs_match"]}**.',
        f'- Identical shared tool schemas: **{result["shared_tool_schemas_match"]}**.',
        f'- Independent arithmetic checks on submissions and physical trajectories: **{arithmetic["checks"]} passed**.',
        '- OS probes deny evaluator files, private source, nominal-model files and network access from numerical Python; SDK active tools are allowlisted.',
        '- Live physics workers receive the public packet and nominal model configuration, never the actual evaluation seed or targets. Workers have stripped credential environments and separate processes for native-global safety.',
        '- Nominal assumptions are common: SMPL exact initial state is published; PenSim nominal future disturbances are disabled and flags/initial conditions/recipe/driver corrections are published.',
        '- Both retain control/equation implementation convenience differences. A receives equations and physical assumptions, not an installed full native simulator inside its numerical sandbox. It is not a resource-matched test of abstract reasoning alone.',
        '- Numerical consistency checks compare repeats, tighter tolerances and alternate solvers. They are not independent experimental validation.',
        '- Shared upstream laws limit evaluator independence. Source-to-receiving realization reuse is optimistic. No independent blinded scientific adjudication was performed.','',
        '## Development failures and excluded runs','',
        '1. Stock native/source inspection revealed an integer-division cube-root discrepancy. The build preserves the original source hash and records the one-expression correction against the supplied Python equation.',
        '2. The full230h trial produced a negative raw viscosity state and was rejected. The96h pilot is an explicit development response, not a successful full-batch result.',
        '3. The first connectivity attempt could not apply nested sandboxing. The next exposed the temporary interpreter whitelist issue. Both failed before inference; isolation was fixed and reprobed.',
        '4. The earlier completed48-attempt comparison used incomplete shared nominal assumptions and cached nominal outputs. It is marked superseded, retained intact, and excluded from every table above. The final comparison uses live execution and explicitly shared nominal assumptions.',
        '5. All final unsubmitted/failed attempts, if any, remain visible in completion counts and per-attempt records.','',
        '## Reproduce and inspect','',
        f'- Dataset: `{dataset}`',f'- Final run: `{run}`',
        '- `protocol.json`: exact model, budgets, source commits, native build correction and hashes.',
        '- `public/*/packet.json`: exactly what both agents received.',
        '- `attempts/*/{A,B}/tools.json`: tool arguments, actual results and timing.',
        '- `attempts/*/{A,B}/run.json`: actual submitted decision, status, usage and score.',
        '- `evaluator/*/truth.json`: post-evaluation process traces and action outcomes; never agent input.',
        '- `baselines.json`, `arithmetic-audit.json`: non-AI controls and numerical verification.',
        '- See the external-simulators README and the independent source audit for commands and scientific limits.','',
        '**Unmeasured:** real engineer hours saved, actual failed batches prevented, plant-transfer readiness and provider monetary billing. A zero-priced SDK ledger is not evidence of free inference.','']
    rendered='\n'.join(lines)
    if clean_ab:
        rendered=rendered.replace('# Executed external-simulator agent pilot',
            '# AI with a physics model versus AI without a supplied physics model')
        rendered=rendered.replace(
            'A: ordinary agent analysis with numerical Python. B: the same agent and public packet, plus live execution of a nominal physical model.',
            '**A — no supplied physics model:** the AI receives source/receiving measurements, units, operating settings, schedules, objectives and allowed actions, plus ordinary numerical Python. It receives no supplied model equations, coefficients, calibration, predictions or simulator access.\n\n'
            '**B — physics enabled:** the same AI receives byte-identical process evidence/settings and ordinary numerical Python, plus the live physical-model tool. Model configuration and model-derived calibration are behind that tool.\n\n')
        rendered=rendered.replace('Actions and equations are common.','Raw process data, operating settings and allowed actions are common; no equations are included in either prompt.')
        rendered=rendered.replace('Both have the same saved model,','Both use the same saved AI model,')
        rendered=rendered.replace('## What was compared',
            'The underlying simulator trajectories, receiving cases, hidden targets and scoring rules are unchanged. '
            'The corrected run protocol defines the A/B treatment and freezes the projected process packets before inference. '
            'Older dataset-generation metadata is retained for provenance; its former both-arms-model-specification description does not define these corrected agent inputs.\n\n## What was compared',1)
        start=rendered.index('## Baselines that do not use an AI')
        end=rendered.index('## Integrity and numerical checks',start)
        rendered=rendered[:start]+(
            '## Reading the operating-decision result\n\n'
            'The main comparison has exactly two agent arms: A without a supplied physics model and B with the model tool. '
            'For both arms, an action improves the objective if it beats keeping the same operating plan in the same simulated realization. '
            'KEEP is the common reference for judging an action; it is not a third AI arm. '
            'Optional non-AI calculations are retained separately in `baselines.json` and do not replace or grade the main A/B comparison.\n\n'
        )+rendered[end:]
        rendered=rendered.replace(
            '- Nominal assumptions are common: SMPL exact initial state is published; PenSim nominal future disturbances are disabled and flags/initial conditions/recipe/driver corrections are published.',
            '- B\'s typed physics tool uses the nominal model parameterization plus calibration derived only from completed source history. It never uses actual receiving future outcomes. A receives none of the supplied model specification or calibration.')
        rendered=rendered.replace(
            '- Both retain control/equation implementation convenience differences. A receives equations and physical assumptions, not an installed full native simulator inside its numerical sandbox. It is not a resource-matched test of abstract reasoning alone.',
            '- A may use its learned knowledge or derive calculations from raw data. Installed process-simulator imports, model files and B\'s host configuration are blocked in numerical Python. The treatment is access to a supplied executable physics model, not removal of an AI\'s prior physics knowledge.')
        rendered=rendered.replace(
            '5. All final unsubmitted/failed attempts, if any, remain visible in completion counts and per-attempt records.',
            '5. The previous 47/48-submission run gave equations and model-derived calibration to A. It tested executable tool access against model information without the tool, not the requested clean no-supplied-model baseline. Those receipts remain historical; none is pooled into this corrected comparison.\n'
            '6. All corrected-run unsubmitted/failed attempts, if any, remain visible in completion counts and per-attempt records.')
        rendered=rendered.replace('The final comparison uses live execution and explicitly shared nominal assumptions.',
            'The corrected comparison uses live execution behind B\'s tool, with no model equations or calibration in common process inputs.')
        rendered=rendered.replace(
            '- `public/*/packet.json`: exactly what both agents received.',
            '- **`common-inputs/*/packet.json` and `attempts/*/{A,B}/agent-input/packet.json` in the run directory are the actual inputs both agents received.** All 24 are frozen and hashed before inference. The legacy dataset `public/` files include host model specifications and are NOT the no-model agent\'s inputs.')
    for before,after in [('complete230h','complete 230 h'),('full230h','full 230 h'),
                         ('declared96h','declared 96 h'),('The96h','The 96 h'),('PenSimPy96h','PenSimPy 96 h'),
                         ('SMPL24h','SMPL 24 h'),('its17-state','its 17-state'),('for24h','for 24 h'),
                         ('120s','120 s'),('setting,120','setting, 120'),('ceiling,8','ceiling, 8'),
                         ('and10','and 10'),('×two','× two'),('80h','80 h'),('6h','6 h'),
                         ('96h','96 h'),('18h','18 h'),('24h','24 h'),('completed48','completed 48')]:
        rendered=rendered.replace(before,after)
    if result['status']=='complete':
        pen=result['groups']['pensim'];mab=result['groups']['mab']
        takeaway=(
            '## What the results mean\n\n'
            f'On the prediction task, adding the tool reduced mean product error from {pct(pen["prediction"]["A"]["mean_product_relative_error"])} to {pct(pen["prediction"]["B"]["mean_product_relative_error"])} in PenSimPy, and from {pct(mab["prediction"]["A"]["mean_product_relative_error"])} to {pct(mab["prediction"]["B"]["mean_product_relative_error"])} in SMPL. '
            f'PenSimPy oxygen prediction error nevertheless increased from {pct(pen["prediction"]["A"]["mean_indicator_relative_error"])} to {pct(pen["prediction"]["B"]["mean_indicator_relative_error"])}.\n\n'
            'The model-assisted agent achieved small positive mean PenSimPy objective changes on operating and recipe-transfer tasks; SMPL action choices produced the same mean objective changes in both arms. The physics-only baseline frequently matched or exceeded the AI-assisted results. These observations support useful model access in this narrow virtual experiment, but do not establish that AI adds value beyond the model, that every prediction improves, or that the gains transfer to a real plant.\n\n')
        if clean_ab:
            b_rows=[r for r in result['records'] if r['arm']=='B']
            model_users=sum(r.get('physical_model_calls',0)>0 for r in b_rows)
            model_queries=sum(r.get('physical_model_calls',0) for r in b_rows)
            takeaway=(
                '## Direct answer to the A/B question\n\n'
                f'B had the physics tool available and used it in **{model_users}/{len(b_rows)} sessions**, making {model_queries} live simulator requests. A had no physics-model tool.\n\n'
                f'On the prediction task, mean product error was {pct(pen["prediction"]["A"]["mean_product_relative_error"])} without a supplied physics model versus {pct(pen["prediction"]["B"]["mean_product_relative_error"])} with the tool for PenSimPy, and {pct(mab["prediction"]["A"]["mean_product_relative_error"])} versus {pct(mab["prediction"]["B"]["mean_product_relative_error"])} for SMPL. '
                f'PenSimPy oxygen error was {pct(pen["prediction"]["A"]["mean_indicator_relative_error"])} versus {pct(pen["prediction"]["B"]["mean_indicator_relative_error"])}. Lower error is better.\n\n'
                'The tables below compare these same two AI arms for operating decisions and simulated recipe transfer. '
                'Failures remain visible. This small, correlated, previously inspected simulation pilot does not establish statistical significance or real-factory performance.\n\n')
        rendered=rendered.replace('## What was compared',takeaway+'## What was compared',1)
    (output/'report.md').write_text(rendered)
    dump(output/'provenance.json',{'dataset_manifest_sha256':sha(dataset/'manifest.json'),
        'run_results_sha256':sha(run/'results.json'),'report_sha256':sha(output/'report.md'),
        'data_protocol':data_protocol,'final_run_status':result['status']})
    # Publication-style static figure; values come only from recorded submissions.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(11,7))
    for column,sim in enumerate(('pensim','mab')):
        for row,(metric,heading) in enumerate((('mean_product_relative_error','Product'),('mean_indicator_relative_error','Oxygen' if sim=='pensim' else 'Viable cells'))):
            ax=axes[row,column];x=np.arange(3);width=.34
            for offset,arm,color in [(-width/2,'A','#536579'),(width/2,'B','#007f78')]:
                vals=[result['groups'][sim][task][arm][metric] for task in ('prediction','outcome','transfer')]
                ax.bar(x+offset,[100*v if v is not None else np.nan for v in vals],width,label=arm+(' ordinary agent' if arm=='A' else' + physical model'),color=color)
            ax.set_xticks(x,['Prediction','Decision task','Recipe transfer']);ax.set_title(labels[sim]+' · '+heading);ax.set_ylabel('Forecast error (%) · lower is better')
            ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0,0].legend(frameon=False,fontsize=8)
    fig.suptitle('Recorded agent comparison · synthetic outcomes · four attempts per group',fontsize=12)
    fig.text(.5,.01,'Means use submitted decisions; completion counts retain failures. PenSim: 96 h partial process; SMPL: 24 h upstream. No plant validation.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.04,1,.93));fig.savefig(output/'prediction-errors.png',dpi=160);plt.close(fig)
    return {'report':str(output/'report.md'),'arithmetic':arithmetic,'status':result['status']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();print(json.dumps(report(args.dataset.resolve(),args.run.resolve(),args.output.resolve()),indent=2))
