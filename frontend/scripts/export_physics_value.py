"""Export measured paired-run receipts to the static case-study page."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from benchmarks.physics_value.run_agents import arm_metrics

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(dataset: Path, run: Path, destination: Path | None = None):
    dataset, run = Path(dataset).resolve(), Path(run).resolve()
    destination = Path(destination or ROOT / 'frontend/public/case-study-results').resolve()
    source_bytes = (run / 'results.json').read_bytes()
    results = json.loads(source_bytes)
    if not results.get('protocol',{}).get('model'):
        raise ValueError('recorded model identity is required for publication')
    if results.get('status')=='complete' and results['attempted']!=results['planned_attempts']:
        raise ValueError('complete run does not account for every planned attempt')
    if (run / 'interruption.json').exists():
        raise ValueError('interrupted development run is not the primary publication source')
    manifest = read(dataset / 'manifest.json')
    if results['protocol']['dataset_manifest_sha256'] != sha(dataset / 'manifest.json'):
        raise ValueError('run does not reference this dataset')
    if not results['pair_inputs_match']:
        raise ValueError('paired agent inputs differ; publication export refused')
    if results.get('shared_tool_schemas_match') is False:
        raise ValueError('shared agent tool schemas differ; publication export refused')
    if not read(run / 'isolation.json')['passed']:
        raise ValueError('isolation did not pass')
    assets = destination / 'physics-value'
    assets.mkdir(parents=True, exist_ok=True)
    records = []
    for row in results['records']:
        value = {key: deepcopy(row.get(key)) for key in (
            'case_id', 'task', 'arm', 'model', 'status', 'wall_seconds', 'model_calls',
            'tool_calls', 'physical_model_calls', 'submission', 'score', 'capability_audit')}
        verification = (value.get('score') or {}).get('resolution_verification')
        if verification:
            verification.pop('post_action_observations', None)
        # Public error summaries omit raw SDK stack traces, home paths and
        # provider payloads. Failed status remains in every denominator.
        value['error'] = ('Execution did not produce a scored submission. See the recorded attempt status.'
                          if row['status'] != 'completed' else None)
        records.append(value)
    cases = []
    for entry in read(dataset / 'evaluator/catalogue.json'):
        if entry['case_id'] not in results['protocol']['case_ids']:
            continue
        case = read(dataset / f"evaluator/cases/{entry['case_id']}.json")
        end = case['reference']['completion_time_h'] or case['config']['duration_h']
        key = 'dissolved_oxygen_mg_l' if case['domain'] == 'oxygen' else 'active_max_temperature_c'
        observed_key = 'dissolved_oxygen_mg_l' if case['domain'] == 'oxygen' else 'product_temperature_c'
        cases.append({**entry, 'authored_causes': case['causes'], 'completion_h': end,
                      'action_labels': {task: {a['id']: a['description'] for a in read(dataset / f"public/{case['case_id']}/{task}/packet.json")['allowed_actions']} for task in results['protocol']['tasks']},
                      'constraint_value': case['config']['minimum_do_mg_l'] if case['domain']=='oxygen' else case['config']['product']['critical_temperature_c'],
                      'optimization_grid_has_feasible_action': any(value['feasible_full_batch'] for value in case['counterfactuals']['optimization'].values()),
                      'reference_trace': [{'time_h': r['time_h'], 'value': r[key]}
                                          for r in case['reference']['trajectory']
                                          if r['time_h'] <= end and r[key] is not None],
                      'observed_trace': [{'time_h': r['time_h'], 'value': r[observed_key]}
                                         for r in case['observations'] if r['time_h'] <= end],
                      'original_plan': case['counterfactuals']['pretransfer']['keep'],
                      'pretransfer_outcomes': case['counterfactuals']['pretransfer'],
                      'counterfactual_scope': 'Synthetic evaluator outcomes, revealed after agent evaluation.'})
    payload = {key: deepcopy(results[key]) for key in (
        'version', 'status', 'planned_attempts', 'attempted', 'completed', 'complete_pairs',
        'pair_inputs_match', 'tasks', 'publication_scope', 'independent_scientific_review')}
    payload['shared_tool_schemas_match'] = results.get('shared_tool_schemas_match')
    payload['schema_pairs_audited'] = results.get('schema_pairs_audited', 0)
    # Objectives have different units (dollars vs negative vials/hour). Pool
    # feasibility counts, but never average their numerical objective regrets.
    for arms in payload['tasks'].values():
        for metric in arms.values():
            if 'mean_feasible_grid_regret' in metric:
                metric['mean_feasible_grid_regret'] = None
                metric['regret_scope'] = 'Only comparable within a process domain; see domain_tasks.'
    domain_of = {case['case_id']: case['domain'] for case in cases}
    domain_tasks = {domain: {
        task: {arm: arm_metrics([row for row in results['records'] if row['task'] == task and
                                row['arm'] == arm and domain_of[row['case_id']] == domain], task)
               for arm in ('A', 'B')} for task in results['protocol']['tasks']}
        for domain in sorted(set(domain_of.values()))}
    sensitivity = {}
    for task in results['protocol']['tasks']:
        by_arm = {arm: {row['case_id']: row for row in results['records']
                        if row['task']==task and row['arm']==arm and row['status']=='completed'} for arm in ('A','B')}
        common = set(by_arm['A']) & set(by_arm['B'])
        sensitivity[task] = {'pairs': len(common)}
        for arm in ('A','B'):
            scores = [by_arm[arm][identity]['score'] for identity in common]
            sensitivity[task][arm] = {
                'top_rank_matches': sum(s['top_rank_matches_authored_cause'] is True for s in scores),
                'feasible_actions': sum((s.get('independently_replayed_outcome') or {}).get('feasible_full_batch',False) for s in scores),
                'verified_outcomes': sum(s.get('resolution_verification',{}).get('verified_process_constraint_resolution_h') is not None for s in scores) if task=='resolution' else None}
    findings = {'A_completed': sum(m['A']['completed'] for m in payload['tasks'].values()),
                'B_completed': sum(m['B']['completed'] for m in payload['tasks'].values()),
                'planned_per_arm': results['planned_attempts']//2,
                'control_cases': sum(c['original_plan']['feasible_full_batch'] for c in cases),
                'paired_completed_sensitivity': sensitivity,
                'sensitivity_scope': 'Descriptive post-run sensitivity analysis conditional on both arms submitting, alongside all-attempt primary counts.'}
    warnings = payload['tasks'].get('pretransfer',{}).get('B',{}).get('warnings',{})
    findings['B_warned_every_case'] = warnings.get('TP',0)+warnings.get('FP',0)==len(cases) and len(cases)>0
    payload.update(protocol=results['protocol'], records=records, cases=cases,
                   domain_tasks=domain_tasks,
                   findings=findings,
                   publication_export_sha256=sha(Path(__file__)),
                   dataset_cases=manifest['case_count'], dataset_task_packets=manifest['task_packet_count'],
                   source_record=str((run / 'results.json').relative_to(ROOT)) if run.is_relative_to(ROOT) else 'external-run/results.json',
                   source_sha256=hashlib.sha256(source_bytes).hexdigest(), dataset_manifest_sha256=sha(dataset / 'manifest.json'),
                   observed_engineer_hours_saved=None, real_batches_prevented=None,
                   notice='Exploratory comparison on synthetic development cases. Authored mechanism matches are not independently verified real-world causal accuracy. Simulated assay effort is not measured engineer time. Input preparation and model-setup effort were not timed. Failed attempts and abstentions remain visible.',
                   assets={'protocol': '/case-study-results/physics-value/protocol.json',
                           'dataset_manifest': '/case-study-results/physics-value/dataset-manifest.json',
                           'isolation': '/case-study-results/physics-value/isolation.json',
                           'summary': '/case-study-results/physics-value/results-summary.md',
                           'archive': '/case-study-results/physics-value/reproducibility.zip'})
    development = []
    for name in ('agent-connectivity-20261027', 'agent-connectivity-20261027-low', 'agent-comparison-20261027'):
        previous = run.parent / name
        if previous == run or not (previous / 'results.json').exists():
            continue
        actual = read(previous / 'results.json')
        stopped = read(previous / 'interruption.json') if (previous / 'interruption.json').exists() else None
        development.append({'name': name, 'attempted': actual['attempted'], 'completed': actual['completed'],
                            'status': stopped['status'] if stopped else actual['status'],
                            'reason': stopped.get('reason') if stopped else 'Provider/SDK connectivity calibration; separate protocol.',
                            'source_sha256': sha(previous / 'results.json')})
    payload['development_runs_excluded_from_primary_counts'] = development
    if development:
        payload['notice'] += ' Earlier calibration and interrupted interface-development runs are retained separately and excluded from the primary counts.'
    review_path = run / 'computational-review.json'
    if review_path.exists():
        review = read(review_path)
        if review['source_sha256'] != payload['source_sha256']:
            raise ValueError('computational review references a different result snapshot')
        if not review['passed']:
            raise ValueError('computational replay failed; publication export refused')
        payload['computational_review'] = review
        payload['assets']['computational_review'] = '/case-study-results/physics-value/computational-review.json'
    else:
        payload['computational_review'] = None
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'physics-value.json').write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n')
    shutil.copyfile(run / 'protocol.json', assets / 'protocol.json')
    shutil.copyfile(dataset / 'manifest.json', assets / 'dataset-manifest.json')
    shutil.copyfile(run / 'isolation.json', assets / 'isolation.json')
    if review_path.exists():
        shutil.copyfile(review_path, assets / 'computational-review.json')
    lines = ['# Physical-model comparison: case-study evidence sheet', '',
             f"Run status: **{payload['status']}**. {payload['attempted']}/{payload['planned_attempts']} attempts executed; {payload['completed']} scored submissions; {payload['complete_pairs']} pairs completed both arms.", '',
             f"Model in both arms: `{payload['protocol']['model']}`.", '',
             payload['notice'], '',
             '| Endpoint | A: numerical tools | B: numerical tools + physical models |',
             '| --- | --- | --- |']
    for task, label in (('diagnosis', 'Top-ranked authored mechanism matches'),
                        ('optimization', 'Feasible selected actions'),
                        ('resolution', 'Verified simulated full-batch outcomes'),
                        ('pretransfer', 'Warnings and abstentions')):
        cells = []
        for arm in ('A', 'B'):
            metric = payload['tasks'][task][arm]
            if task == 'pretransfer':
                w = metric['warnings']
                cells.append(f"{w['TP']} true warnings; {w['FP']} false alarms; {w['FN']} misses; {w['TN']} true negatives; {w['abstained']} abstentions")
            else:
                key = {'diagnosis': 'top_rank_matches', 'optimization': 'feasible_selected_actions',
                       'resolution': 'verified_simulated_resolutions'}[task]
                cells.append(f"{metric[key]} / {metric['attempted']} attempts")
        lines.append('| '+label+' | '+' | '.join(cells)+' |')
    lines += ['', 'Failed or unsubmitted attempts remain in the denominators. Diagnosis set sizes and execution coverage must accompany mechanism matches; these labels do not establish uniquely identifiable real causes.', '',
              'Pre-transfer characterization requests were recorded, not experimentally executed in this trial. A deferral is not proof that the agent discovered or prevented a receiving-site failure.', '',
              'Simulated resolution means satisfying the declared full-batch constraints and observing a synthetic verification endpoint. It is not proof of equipment repair, root-cause correction or measured engineer time saved.', '',
              'Optimization regret is meaningful within a process domain only; the dollar and vial-throughput objectives are not averaged together.', '',
              'These are inspected synthetic development cases with one run per condition and no independent scientific adjudication. Report the result as an exploratory restricted-tool agent comparison.', '',
              f"Exact source receipt SHA-256: `{payload['source_sha256']}`.",
              f"Dataset manifest SHA-256: `{payload['dataset_manifest_sha256']}`."]
    lines += ['', '## Completion and paired-quality sensitivity', '',
              f"Scored decisions: A {findings['A_completed']}/{findings['planned_per_arm']}; B {findings['B_completed']}/{findings['planned_per_arm']}.", '']
    for task,label,key in (('optimization','feasible actions','feasible_actions'),('resolution','verified simulated outcomes','verified_outcomes')):
        paired = sensitivity.get(task)
        if paired:
            lines.append(f"Among {paired['pairs']} same-case pairs with both submissions, {task}: A {paired['A'][key]}, B {paired['B'][key]} {label}.")
    lines += ['', findings['sensitivity_scope']]
    if findings['B_warned_every_case']:
        lines += ['', f"B warned on every case, including all {findings['control_cases']} physical-outcome controls. This matches an always-warn policy and does not establish useful pre-transfer discrimination."]
    if development:
        lines += ['', '## Separate development receipts', '']
        for item in development:
            lines.append(f"- {item['name']}: {item['attempted']} attempts, {item['completed']} scored submissions; {item['status']}. Excluded from the primary comparison.")
        lines += ['', 'The shared submission schema was revised to exact public-ID enums after identifying formatting-repair overhead. No data, physical model, outcome rubric or execution ceiling was changed for the final comparison.']
    (assets / 'results-summary.md').write_text('\n'.join(lines)+'\n')
    with zipfile.ZipFile(assets / 'reproducibility.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        # Explicit allowlist. No env files, auth stores, SDK memory or provider
        # configuration are included in the publication package.
        for relative in manifest['files_sha256']:
            path = dataset / relative
            if sha(path) != manifest['files_sha256'][relative]:
                raise ValueError('dataset artifact changed: '+relative)
            archive.write(path, 'dataset/'+relative)
        archive.write(dataset / 'manifest.json', 'dataset/manifest.json')
        for relative, expected in manifest['code_sha256'].items():
            path = ROOT / relative
            if not path.is_file() or sha(path) != expected:
                raise ValueError('frozen numerical implementation changed: '+relative)
            archive.write(path, 'source/frozen/'+relative)
        archive.writestr('agent-run/results.json', source_bytes)
        archive.write(assets / 'results-summary.md', 'agent-run/results-summary.md')
        for name in ('protocol.json', 'isolation.json'):
            archive.write(run / name, 'agent-run/'+name)
        attempt_hashes = {}
        for record in results['records']:
            relative = Path('attempts') / record['case_id'] / record['task'] / record['arm']
            for name in ('run.json', 'tools.json', 'events.json'):
                path = run / relative / name
                if path.exists():
                    member = str(Path('agent-run') / relative / name)
                    archive.write(path, member)
                    attempt_hashes[member] = sha(path)
        archive.writestr('agent-run/attempt-artifact-sha256.json', json.dumps(attempt_hashes, indent=2)+'\n')
        if review_path.exists():
            archive.write(review_path, 'agent-run/computational-review.json')
        for item in development:
            previous = run.parent / item['name']
            for name in ('protocol.json', 'results.json', 'interruption.json'):
                if (previous / name).exists():
                    archive.write(previous / name, 'development/'+item['name']+'/'+name)
        for path in sorted((ROOT / 'backend/benchmarks/physics_value').iterdir()):
            if path.suffix in ('.py', '.mjs', '.md'):
                frozen = run / 'runner-source' / path.name
                source = frozen if frozen.exists() else path
                expected = results['protocol']['runner_sha256'].get(path.name)
                if expected and sha(source) != expected:
                    raise ValueError('runner source differs from recorded experiment: '+path.name)
                archive.write(source, 'source/'+path.name)
        archive.writestr('REPRODUCE.md', '\n'.join([
            '# Evidence and replay inputs', '',
            'This archive contains the frozen synthetic dataset, actual agent-run receipts, tool histories, deterministic review (when complete), numerical source snapshots and runner code.', '',
            'Use the BioDemo repository environment and its existing Prime SDK installation to execute the package modules. The SDK, model weights, inference credentials and Python dependencies are not bundled. The archive is not a standalone execution environment.', '',
            'Restore numerical sources at the repository-relative paths in dataset/manifest.json; source/frozen contains those exact bytes. The files directly under source contain the experiment package, including frozen runner sources where recorded.', '',
            'Numerical replay: python -m benchmarks.physics_value.review_run --dataset <dataset> --run <agent-run>. Agent execution additionally requires the separately configured hosted model and macOS numerical sandbox. Provider sampling was not seeded, so fresh model runs may differ.', '',
            'Development receipts are separate from the primary comparison. Root summaries never establish independent scientific validation, real engineering labor savings or real manufacturing failures prevented.',
        ])+'\n')
        archive.write(Path(__file__), 'source/publication/export_physics_value.py')
    return {key: payload[key] for key in ('status', 'attempted', 'completed', 'complete_pairs', 'source_sha256')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--run', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.dataset, args.run), indent=2))
