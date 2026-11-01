"""Frozen controlled trials and baseline comparisons before a manufacturer pilot.

Reuses case_runner, its isolation/scorers, and the observed human-work ledger.
This module schedules experiments; it does not manufacture reference answers.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import random
import shutil
import uuid

from .case_protocol import ROOT, digest, load_case, save, stable_hash
from .trace import instant, now

VERSION = 'manufacturer-pilot-benchmark-v1'
METHODS = ('conventional', 'retrieval_llm', 'full_rlm', 'manual')
AUTOMATED = METHODS[:3]


def implementation_hash():
    """Include SDK host, parsers, prompts, tools and evaluators; exclude run data."""
    files = [p for base in ('src', 'prime_skills', 'benchmarks/common', 'benchmarks/baselines')
             for p in (ROOT / base).rglob('*')
             if p.is_file() and p.suffix in {'.py', '.mjs', '.md', '.json'} and '__pycache__' not in p.parts]
    return stable_hash({str(p.relative_to(ROOT)): digest(p) for p in sorted(files)})


def runtime_configuration():
    """Fingerprint relevant runtime settings without reading or retaining credentials."""
    from src.paths import DEFAULT_PRIME_BUNDLE
    bundle = Path(os.environ.get('PRIME_AGENT_BUNDLE_ROOT', DEFAULT_PRIME_BUNDLE))
    settings_path = Path.home() / '.prime/agent/settings.json'
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    return {'sdk_sha256': {name: digest(bundle / name) if (bundle / name).is_file() else None
                           for name in ('packages/coding-agent/dist/index.js', 'packages/ai/dist/index.js')},
            'default_provider': settings.get('defaultProvider'), 'default_model': settings.get('defaultModel'),
            'compaction_target_tokens': os.environ.get('BIODEMO_COMPACTION_TARGET_TOKENS', '128000')}


@contextmanager
def provider_environment(path=None):
    """Load only inference credentials, never database/admin keys, into workers."""
    previous = {}
    if path:
        from dotenv import dotenv_values
        values = dotenv_values(path)
        for name in ('OPENAI_API_KEY', 'MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_BASE_URL'):
            if values.get(name) and name not in os.environ:
                previous[name] = None
                os.environ[name] = values[name]
    try:
        yield
    finally:
        for name in previous:
            os.environ.pop(name, None)


def _sealed(value):
    value['sha256'] = stable_hash({k: v for k, v in value.items() if k != 'sha256'})
    return value


def _load(path):
    value = json.loads(Path(path).read_text())
    if value.get('sha256') != stable_hash({k: v for k, v in value.items() if k != 'sha256'}):
        raise ValueError('Frozen protocol checksum mismatch')
    return value


def default_manifests():
    return [ROOT / 'benchmarks/manifests' / benchmark / f'{case_id}-raw/case.json'
            for benchmark, prefix, count in (('cho', 'CHO', 5), ('fresenius', 'FRE', 6))
            for case_id in (f'{prefix}-{i:02}' for i in range(1, count + 1))]


def freeze(destination, manifests=None, *, repeats=2, seed=42, quality_policy=None,
           full_model=None, baseline_model=None, filename_challenges=True, refresh_rendered=False):
    """Snapshot metadata only; existing content-addressed inputs hydrate on execution."""
    from .format_challenge import transform_references
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Choose a fresh suite directory; frozen suites are never overwritten')
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be positive')
    runtime = runtime_configuration()
    full_model = full_model or os.environ.get('BIODEMO_PRIME_MODEL')
    if not full_model and runtime['default_provider'] and runtime['default_model']:
        full_model = f"{runtime['default_provider']}/{runtime['default_model']}"
    baseline_model = baseline_model or full_model or 'gpt-6-luna'
    originals = [(Path(p).resolve(), load_case(p)) for p in (manifests or default_manifests())]
    identities = [(c['benchmark_id'], c['case_id'], c['condition']) for _, c in originals]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate case/condition assignment')
    if any(c.get('condition_status') != 'ready' or c.get('update_requires_prior_run') for _, c in originals):
        raise ValueError('Suite accepts ready independent cases; persistent updates use the existing --prior-run trial')
    policy = json.loads(Path(quality_policy).read_text()) if quality_policy else None
    if policy:
        from .quality import validate_policy_approval
        validate_policy_approval(policy, require_approved=True)
    destination.mkdir(parents=True, mode=0o700)
    cases = []
    for source, original in originals:
        historical_parent = original['task_spec_sha256']
        if refresh_rendered and original['benchmark_id'] == 'fresenius':
            # Rendering libraries can change XLSX container bytes. A new snapshot
            # keeps the strict byte audit and the old experiment intact.
            from .case_protocol import prepare_case
            prepared = prepare_case('fresenius', original['case_id'], condition=original['condition'],
                                    destination=destination / 'rendered-snapshots' / f"{original['case_id']}-{original['condition']}")
            fresh = load_case(prepared)
            if any(fresh.get(k) != original.get(k) for k in ('objective', 'as_of', 'required_deliverables')):
                raise ValueError('Refreshed renderer changes the task; freeze it as a separate explicitly reviewed case')
            old_reference = json.loads((source.parent / original['reference']).read_text())
            new_reference = json.loads((prepared.parent / fresh['reference']).read_text())
            if old_reference != new_reference:
                raise ValueError('Refreshed renderer changes evaluator references; independent review required')
            source, original = prepared, fresh
        conditions = [False, True] if filename_challenges and original['condition'] == 'raw' else [False]
        for challenge in conditions:
            case = dict(original)
            condition = 'held_out' if challenge else original['condition']
            key = f"{case['benchmark_id']}-{case['case_id']}-{condition}"
            directory = destination / 'cases' / key
            directory.mkdir(parents=True)
            for name in (case['reference'], case['quality_policy'], case['triage_policy'],
                         *([case['transform']] if case.get('transform') else [])):
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source.parent / name, target)
            if policy:
                save(directory / case['quality_policy'], policy)
                case['quality_policy_sha256'] = digest(directory / case['quality_policy'])
            if challenge:
                names = [f['path'] for f in case['allowlist'] if f['path'] != 'package_manifest.json']
                transform = {'version': 'filename-challenge-v1', 'seed': seed,
                             'files': {name: f'sources/input_{i:04d}{Path(name).suffix}' for i, name in enumerate(sorted(names))},
                             'novelty': 'Filename robustness on inspected observations; not independent incident or biological holdouts.'}
                reference = json.loads((directory / case['reference']).read_text())
                transform_references(reference, transform)
                save(directory / case['reference'], reference)
                case['reference_sha256'] = digest(directory / case['reference'])
                case['allowlist'] = [{**f, 'path': transform['files'].get(f['path'], f['path'])} for f in case['allowlist']]
                # The existing rename transform also rewrites the package index.
                # Freeze those changed bytes rather than keeping the raw index hash.
                metadata_entry = next((f for f in original['allowlist'] if f['path'] == 'package_manifest.json'), None)
                if metadata_entry:
                    local = source.parent / original['input_root'] / metadata_entry['path']
                    if local.is_file():
                        metadata = json.loads(local.read_text())
                    else:
                        from .input_store import execution_inputs, fetch, cache_dir
                        with execution_inputs(source):
                            fetch([metadata_entry['sha256']])
                            metadata = json.loads((cache_dir() / metadata_entry['sha256']).read_text())
                    for row in metadata['files']:
                        row['path'] = transform['files'].get(row['path'], row['path'])
                    target = directory / case['input_root'] / 'package_manifest.json'
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(metadata, indent=2))
                    case['allowlist'] = [{**f, 'sha256': digest(target), 'bytes': target.stat().st_size}
                                         if f['path'] == 'package_manifest.json' else f for f in case['allowlist']]
                save(directory / 'transform.json', transform)
                case.update(transform='transform.json', transform_sha256=digest(directory / 'transform.json'),
                            format_challenge=transform['novelty'])
            case.update(condition=condition, frozen_at=now(), parent_case_sha256=original['task_spec_sha256'],
                        historical_parent_case_sha256=historical_parent,
                        generalization_claim_eligible=False, package_sha256=stable_hash(case['allowlist']),
                        execution_policy={'mode': 'adaptive_v1', 'soft_tool_calls': 48},
                        budgets={**case['budgets'], 'tool_calls': 72},
                        model_configuration={'prime_model': full_model, 'baseline_model': baseline_model})
            case['task_spec_sha256'] = stable_hash({k: v for k, v in case.items() if k not in ('frozen_at', 'task_spec_sha256')})
            save(directory / 'case.json', case)
            load_case(directory / 'case.json')
            # Link any available local inputs; absent ones remain in the existing checksum store.
            for before, after in zip(original['allowlist'], case['allowlist']):
                local = source.parent / original['input_root'] / before['path']
                if local.is_file() and not local.is_symlink() and digest(local) == before['sha256']:
                    target = directory / case['input_root'] / after['path']
                    if target.exists():
                        continue  # transformed package index already has its frozen bytes
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(local, target)
            cases.append({'key': key, 'manifest': str((directory / 'case.json').relative_to(destination)),
                          'task_spec_sha256': case['task_spec_sha256'], 'benchmark_id': case['benchmark_id'],
                          'case_id': case['case_id'], 'condition': condition})
    schedule = []
    rng = random.Random(seed)
    for case in cases:
        for repeat in range(repeats):
            methods = list(METHODS)
            rng.shuffle(methods)
            pair_id = f"{case['key']}-r{repeat + 1}"
            schedule.extend({'assignment_id': f'{pair_id}-{method}', 'pair_id': pair_id,
                             'case_key': case['key'], 'method': method, 'repeat': repeat + 1} for method in methods)
    protocol = _sealed({'version': VERSION, 'created_at': now(), 'seed': seed, 'repeats': repeats,
                        'cases': cases, 'schedule': schedule, 'implementation_sha256': implementation_hash(),
                        'runtime_configuration': runtime,
                        'model_configuration': {'prime_model': full_model, 'baseline_model': baseline_model},
                        'runtime_differences': ['Evaluation uses a fresh SDK resource directory without global memories or extensions.',
                                                'Evaluation requires a claim ledger and applies OS evidence-read denial.',
                                                'Runtime budgets are frozen per case; cloud deadlines must be compared separately.'],
                        'limits': ['Existing datasets have been inspected; all results are exploratory.',
                                   'Filename variants and repeats are not new independent manufacturing cases.',
                                   'Different model assignments confound a pure orchestration comparison.',
                                   'Independent case annotations and domain-approved quality thresholds are still required.']})
    save(destination / 'protocol.json', protocol)
    for p in (destination / 'cases').rglob('*.json'):
        if 'agent_input' not in p.parts:
            p.chmod(0o444)
    (destination / 'protocol.json').chmod(0o444)
    save(destination / 'state.json', {'version': VERSION, 'assignments': {}})
    return destination / 'protocol.json'


def load_suite(directory, *, check_code=False):
    directory = Path(directory).resolve()
    protocol = _load(directory / 'protocol.json')
    if protocol.get('version') != VERSION:
        raise ValueError('Unsupported suite version')
    if check_code and implementation_hash() != protocol['implementation_sha256']:
        raise ValueError('Implementation changed after freeze; create a new suite')
    if check_code and runtime_configuration() != protocol['runtime_configuration']:
        raise ValueError('SDK or runtime settings changed after freeze; create a new suite')
    for entry in protocol['cases']:
        path = (directory / entry['manifest']).resolve()
        if not path.is_relative_to(directory):
            raise ValueError('Manifest escapes suite')
        if load_case(path)['task_spec_sha256'] != entry['task_spec_sha256']:
            raise ValueError('Case changed after suite freeze')
    return directory, protocol


@contextmanager
def locked(directory):
    with (Path(directory) / '.suite.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another process is updating this suite') from exc
        yield


def execute(directory, *, methods=AUTOMATED, limit=None, operator_id=None):
    """Resume pending assignments. A failed attempt is terminal, never silently retried."""
    from .case_runner import run_case
    directory, protocol = load_suite(directory, check_code=True)
    if not set(methods) <= set(AUTOMATED):
        raise ValueError('Automated execution only; use record-manual for observed engineer work')
    if limit is not None and limit < 1:
        raise ValueError('limit must be positive')
    with locked(directory):
        state = json.loads((directory / 'state.json').read_text())
        cases = {c['key']: c for c in protocol['cases']}
        completed = 0
        for assignment in protocol['schedule']:
            identifier = assignment['assignment_id']
            if assignment['method'] not in methods or identifier in state['assignments']:
                continue
            if (directory / 'STOP').exists() or (limit is not None and completed >= limit):
                break
            # Receipt precedes work. An interrupted assignment stays visible for adjudication.
            receipt = {'status': 'running', 'started_at': now(), 'assignment': assignment}
            state['assignments'][identifier] = receipt
            save(directory / 'state.json', state)
            try:
                path = run_case(directory / cases[assignment['case_key']]['manifest'], assignment['method'],
                                output_root=directory / 'runs', operator_id=operator_id)
                run = json.loads(path.read_text())
                run.update(pair_id=assignment['pair_id'], assignment_id=identifier,
                           suite_sha256=protocol['sha256'])
                save(path, run)
                receipt.update(status='recorded', run_path=str(path.relative_to(directory)))
            except Exception as exc:
                receipt.update(status='runner_error', error_code=type(exc).__name__, reason=str(exc)[-1000:])
            finally:
                receipt['ended_at'] = now()
                save(directory / 'state.json', state)
            completed += 1
        return state


def record_manual(directory, assignment_id, output_path, session_path):
    """Import an observed human output; source-access attestation is explicit, not an OS test."""
    from .case_audit import audit_case
    from .case_runner import blinded_packet, review_template
    from .human_work import template
    from .input_store import execution_inputs, materialize
    from .objective_scores import score_objective
    from .quality import score_review
    from .trace import TraceSink
    directory, protocol = load_suite(directory, check_code=True)
    assignment = next((a for a in protocol['schedule'] if a['assignment_id'] == assignment_id and a['method'] == 'manual'), None)
    if assignment is None:
        raise ValueError('Unknown manual assignment')
    session = json.loads(Path(session_path).read_text())
    if not session.get('operator_id') or not session.get('evidence_ref') or any(session.get(k) is not True for k in ('authorized_evidence_only', 'no_future_leakage')):
        raise ValueError('Observed session needs operator, evidence reference and source/cutoff attestations')
    if instant(session['ended_at']) < instant(session['started_at']):
        raise ValueError('Session ends before it starts')
    with locked(directory):
        state = json.loads((directory / 'state.json').read_text())
        if assignment_id in state['assignments']:
            raise ValueError('Assignment already recorded; never replace an attempt')
        entry = next(c for c in protocol['cases'] if c['key'] == assignment['case_key'])
        manifest = directory / entry['manifest']
        case = load_case(manifest)
        output = json.loads(Path(output_path).read_text())
        if not isinstance(output.get('analysis'), dict):
            raise ValueError('Manual output needs a structured analysis with the same deliverables')
        run_id = uuid.uuid4().hex
        target = directory / 'runs' / run_id
        target.mkdir(parents=True)
        shutil.copyfile(manifest.parent / case['quality_policy'], target / 'quality-policy.json')
        shutil.copyfile(manifest, target / 'case.json')
        policy = json.loads((target / 'quality-policy.json').read_text())
        save(target / 'output.json', output)
        run = {'version': case['version'], 'run_id': run_id, 'case_id': case['case_id'],
               'benchmark_id': case['benchmark_id'], 'condition': case['condition'], 'case': case,
               'mode': 'manual', 'attempted': True, 'status': 'completed', 'output': output,
               'output_sha256': digest(target / 'output.json'), 'quality_policy': policy,
               'started_at': session['started_at'], 'ended_at': session['ended_at'],
               'operator_id': session['operator_id'], 'manual_session': session,
               'isolation_audit': {'pass': True, 'mechanism': 'observed_human_attestation; not OS isolation',
                                   'evidence_ref': session['evidence_ref']},
               'pair_id': assignment['pair_id'], 'assignment_id': assignment_id, 'suite_sha256': protocol['sha256']}
        with execution_inputs(manifest) as staged:
            materialize(staged)
            run['audit'] = audit_case(staged)
            if run['audit']['pass']:
                reference = json.loads((staged.parent / case['reference']).read_text())
                run['objective_scores'] = score_objective(output, reference, case, staged.parent / case['input_root'])
        sink = TraceSink(target / 'trace.jsonl', case['case_id'], run_id)
        sink.emit(actor='evaluator', stage='verification', action='import_observed_manual_work', source_refs=[session['evidence_ref']])
        run.update(trace_path='trace.jsonl', trace_sha256=digest(sink.path), qualification=score_review(run, policy))
        save(target / 'run.json', run)
        save(target / 'review-template.json', review_template(run))
        save(target / 'blinded-review-packet.json', blinded_packet(run))
        save(target / 'human-work-template.json', template([run_id]))
        state['assignments'][assignment_id] = {'status': 'recorded', 'assignment': assignment,
                                              'run_path': str((target / 'run.json').relative_to(directory))}
        save(directory / 'state.json', state)
        return target / 'run.json'


def export_reviews(directory, destination):
    """Only reviewer-facing packets go to destination; the identity key stays private."""
    from .case_runner import blinded_packet, review_template
    directory, protocol = load_suite(directory)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Review export must use a fresh directory')
    if directory == destination or directory.is_relative_to(destination):
        raise ValueError('Review destination must not contain the private suite')
    with locked(directory):
        state = json.loads((directory / 'state.json').read_text())
        destination.mkdir(parents=True, mode=0o700)
        private = {}
        records = [r for r in state['assignments'].values() if r.get('run_path')]
        random.SystemRandom().shuffle(records)
        for receipt in records:
            run = json.loads((directory / receipt['run_path']).read_text())
            if not run.get('output'):
                continue
            packet_id = uuid.uuid4().hex
            packet = blinded_packet(run)
            packet['packet_id'] = packet_id
            packet['source_package_id'] = run['case']['task_spec_sha256']
            packet['rubric'] = {k: run['quality_policy'].get(k) for k in ('dimensions', 'score_scale', 'anchors', 'integrity_gates')}
            form = review_template(run)
            for key in ('run_id', 'output_sha256', 'policy_sha256'):
                form.pop(key, None)
            form['packet_id'] = packet_id
            save(destination / f'{packet_id}.packet.json', packet)
            save(destination / f'{packet_id}.review.json', form)
            private[packet_id] = {'run_path': receipt['run_path'], 'output_sha256': run['output_sha256'],
                                  'policy_sha256': run['case']['quality_policy_sha256']}
        # Separate key per export allows completed packets to return in any order.
        key = directory / 'review-keys' / f'{uuid.uuid4().hex}.json'
        save(key, _sealed({'suite_sha256': protocol['sha256'], 'packets': private}))
        return {'packets': len(private), 'private_key': str(key), 'review_directory': str(destination)}


def export_inputs(directory, destination, case_key=None):
    """Distribute authorized evidence for engineers/reviewers without evaluator files."""
    from .case_audit import audit_case
    from .input_store import execution_inputs, materialize
    directory, protocol = load_suite(directory)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Evidence export needs a fresh directory')
    if directory == destination or directory.is_relative_to(destination):
        raise ValueError('Evidence destination must not contain the private suite')
    selected = [c for c in protocol['cases'] if case_key is None or c['key'] == case_key]
    if not selected:
        raise ValueError('Unknown case key')
    destination.mkdir(parents=True, mode=0o700)
    packages = []
    for entry in selected:
        manifest = directory / entry['manifest']
        case = load_case(manifest)
        package_id = case['task_spec_sha256']
        target = destination / package_id
        with execution_inputs(manifest) as staged:
            materialize(staged)
            audit = audit_case(staged)
            if not audit['pass']:
                raise ValueError('Evidence export audit failed: ' + '; '.join(audit['failures']))
            target.mkdir()
            for item in case['allowlist']:
                output = target / item['path']
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(staged.parent / case['input_root'] / item['path'], output)
                output.chmod(0o444)
        packages.append({'source_package_id': package_id, 'objective': case['objective'], 'as_of': case.get('as_of'),
                         'required_deliverables': case['required_deliverables'], 'files': case['allowlist']})
    save(destination / 'packages.json', packages)
    return {'packages': len(packages), 'destination': str(destination)}


def import_review(directory, review_path, key_path):
    from .case_runner import evaluate_run
    directory, protocol = load_suite(directory)
    key = _load(key_path)
    if key['suite_sha256'] != protocol['sha256']:
        raise ValueError('Review key belongs to another suite')
    review = json.loads(Path(review_path).read_text())
    entry = key['packets'].get(review.get('packet_id'))
    if entry is None:
        raise ValueError('Unknown blinded packet')
    run_path = (directory / entry['run_path']).resolve()
    if not run_path.is_relative_to(directory / 'runs'):
        raise ValueError('Review run escapes suite')
    with locked(directory):
        run = json.loads(run_path.read_text())
        if run.get('output_sha256') != entry['output_sha256'] or run['case']['quality_policy_sha256'] != entry['policy_sha256']:
            raise ValueError('Reviewed output or policy changed')
        bound = {**review, 'run_id': run['run_id'], 'output_sha256': entry['output_sha256'], 'policy_sha256': entry['policy_sha256']}
        save(run_path.parent / 'returned-review.json', bound)
        return evaluate_run(run_path, run_path.parent / 'returned-review.json')


def report(directory, human_logs=None):
    from .case_report import summarize_runs
    from .case_runner import evaluate_run
    from .human_work import aggregate_effort, produce_comparison, template
    directory, protocol = load_suite(directory)
    with locked(directory):
        state = json.loads((directory / 'state.json').read_text())
        runs, problems = [], []
        schedule = {a['assignment_id']: a for a in protocol['schedule']}
        for identifier, receipt in state['assignments'].items():
            if identifier not in schedule:
                raise ValueError('Unknown assignment in state')
            if not receipt.get('run_path'):
                problems.append(f"{identifier}: {receipt['status']}")
                continue
            path = (directory / receipt['run_path']).resolve()
            if not path.is_relative_to(directory / 'runs'):
                raise ValueError('Run path escapes suite')
            evaluate_run(path)  # Recheck output/trace/policy hashes and persisted reviews.
            run = json.loads(path.read_text())
            if run.get('assignment_id') != identifier or run.get('suite_sha256') != protocol['sha256'] or run.get('pair_id') != schedule[identifier]['pair_id']:
                raise ValueError('Run does not match frozen assignment')
            if run['case']['task_spec_sha256'] != next(c['task_spec_sha256'] for c in protocol['cases'] if c['key'] == schedule[identifier]['case_key']) or run['mode'] != schedule[identifier]['method']:
                raise ValueError('Run case or method differs from frozen assignment')
            runs.append(run)
        logs = json.loads(Path(human_logs).read_text()) if human_logs else template()
        summary = summarize_runs(runs, logs)
        for benchmark, conditions in summary['cohorts'].items():
            for condition, cohort in conditions.items():
                selected = [r for r in runs if r['benchmark_id'] == benchmark and r['condition'] == condition]
                effort = aggregate_effort(selected, logs, allocation_universe=runs)
                cohort['automated_comparisons'] = {m: produce_comparison(selected, effort, baseline=m) for m in AUTOMATED[:2]}
        pending = [a['assignment_id'] for a in protocol['schedule'] if a['assignment_id'] not in state['assignments']]
        full = [r for r in runs if r['mode'] == 'full_rlm']
        all_effort = aggregate_effort(runs, logs)
        blockers = []
        if pending: blockers.append(f'{len(pending)} scheduled assignments have not run.')
        blockers.extend(problems)
        if not full or any(r['qualification'].get('qualified') is not True for r in full):
            blockers.append('Full-agent cases have failed checks or still need independent qualification.')
        if any(r['qualification'].get('qualified') is None for r in runs):
            blockers.append('Baseline or manual outcomes still need independent review.')
        if not runs or any(e['status'] != 'observed' for e in all_effort['per_run'].values()):
            blockers.append('Complete observed human effort is missing, including failed attempts.')
        for benchmark, conditions in summary['cohorts'].items():
            for condition, cohort in conditions.items():
                if cohort['runs'] and cohort['comparison']['status'] != 'observed':
                    blockers.append(f'{benchmark}/{condition}: no qualified, timed, noninferior manual/full-agent comparison.')
        if implementation_hash() != protocol['implementation_sha256']:
            blockers.append('Implementation differs from the frozen experiment.')
        if runtime_configuration() != protocol['runtime_configuration']:
            blockers.append('SDK or runtime settings differ from the frozen experiment.')
        if not protocol['model_configuration']['prime_model']:
            blockers.append('Full-agent model assignment was not pinned.')
        readiness = {'status': 'not_ready' if blockers else 'ready_for_pilot_review', 'blockers': blockers,
                     'meaning': 'Internal evidence for a human pilot decision; not production or regulatory validation.'}
        summary.update(suite_sha256=protocol['sha256'], planned_assignments=len(protocol['schedule']),
                       recorded_runs=len(runs), pending_assignments=pending, runner_problems=problems,
                       readiness=readiness, runtime_differences=protocol['runtime_differences'], limits=protocol['limits'])
        save(directory / 'summary.json', summary)
        save(directory / 'human-work-template.json', template([r['run_id'] for r in runs]))
        lines = ['# Manufacturer pilot benchmark', '', f"Readiness: **{readiness['status']}**.", '',
                 f"{len(protocol['cases'])} case/condition packages; {protocol['repeats']} repeats; "
                 f"{len(runs)}/{len(protocol['schedule'])} recorded assignments. Repeats and filename variants are not independent cases.", '',
                 *['- ' + b for b in blockers], '',
                 '| Dataset | Condition | Method | Planned | Recorded | Qualified | Failed | Pending review |',
                 '|---|---|---|---:|---:|---:|---:|---:|']
        for benchmark in ('cho', 'fresenius'):
            for condition in sorted({c['condition'] for c in protocol['cases'] if c['benchmark_id'] == benchmark}):
                keys = {c['key'] for c in protocol['cases'] if c['benchmark_id'] == benchmark and c['condition'] == condition}
                for method in METHODS:
                    planned = sum(a['case_key'] in keys and a['method'] == method for a in protocol['schedule'])
                    selected = [r for r in runs if r['benchmark_id'] == benchmark and r['condition'] == condition and r['mode'] == method]
                    q = [r['qualification'].get('qualified') for r in selected]
                    lines.append(f'| {benchmark} | {condition} | {method} | {planned} | {len(selected)} | {q.count(True)} | {q.count(False)} | {q.count(None)} |')
        lines.extend(['', 'Comparisons, objective metrics, machine usage, and all-attempt human effort are in summary.json.',
                      'No measured labor-savings claim is supported until matched qualified outcomes have complete observed timing.', '',
                      *['- ' + limit for limit in protocol['limits']], '', *['- ' + difference for difference in protocol['runtime_differences']]])
        (directory / 'report.md').write_text('\n'.join(lines) + '\n')
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'run', 'report', 'export-reviews', 'export-inputs', 'import-review', 'record-manual'])
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, action='append')
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--quality-policy', type=Path)
    parser.add_argument('--full-model', default=os.environ.get('BIODEMO_PRIME_MODEL'))
    parser.add_argument('--baseline-model')
    parser.add_argument('--no-filename-challenges', action='store_true')
    parser.add_argument('--refresh-rendered', action='store_true', help='Freeze new Fresenius renderer bytes; reject changes to objectives, cutoffs or references')
    parser.add_argument('--methods', nargs='+', choices=AUTOMATED, default=list(AUTOMATED))
    parser.add_argument('--limit', type=int)
    parser.add_argument('--operator-id')
    parser.add_argument('--human-logs', type=Path)
    parser.add_argument('--provider-env', type=Path, help='run only: load inference credentials from this file; database keys are excluded')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--key', type=Path)
    parser.add_argument('--assignment')
    parser.add_argument('--case-key')
    parser.add_argument('--output-json', type=Path)
    parser.add_argument('--session', type=Path)
    args = parser.parse_args()
    required = {'export-reviews': ('destination',), 'export-inputs': ('destination',), 'import-review': ('review', 'key'),
                'record-manual': ('assignment', 'output_json', 'session')}
    for name in required.get(args.action, ()):
        if not getattr(args, name): parser.error(f'{args.action} requires --{name.replace("_", "-")}')
    if args.action == 'freeze':
        result = freeze(args.suite, args.manifest, repeats=args.repeats, seed=args.seed, quality_policy=args.quality_policy,
                        full_model=args.full_model, baseline_model=args.baseline_model, filename_challenges=not args.no_filename_challenges,
                        refresh_rendered=args.refresh_rendered)
    elif args.action == 'run':
        with provider_environment(args.provider_env):
            result = execute(args.suite, methods=args.methods, limit=args.limit, operator_id=args.operator_id)
    elif args.action == 'report': result = report(args.suite, args.human_logs)
    elif args.action == 'export-reviews': result = export_reviews(args.suite, args.destination)
    elif args.action == 'export-inputs': result = export_inputs(args.suite, args.destination, args.case_key)
    elif args.action == 'import-review': result = import_review(args.suite, args.review, args.key)
    else: result = record_manual(args.suite, args.assignment, args.output_json, args.session)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
