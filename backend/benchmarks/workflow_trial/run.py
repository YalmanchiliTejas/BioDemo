"""Trial of the direct workflows (B) and the optional decision model (C) on real CHO deliveries.

Run from the repository root:

    PYTHONPATH=backend .venv/bin/python -m benchmarks.workflow_trial.run --output backend/results/<new-directory>

What runs
- The three held-out CHO deliveries are read by the real ingestion service (deterministic configuration D, no
  model calls) after the documented calibration protocol on a fourth, disjoint delivery. None of them is verified,
  so each is shared as provisional evidence, exactly as a person would do from the product.
- Every request goes through the HTTP API in this process: the eight jobs as typed tasks, and typed sentences
  through the request router. The time of each request is measured at the caller and compared with the target.
- Reference answers are calculated here from the deliveries' answer keys. The keys are opened only after ingestion
  has finished and are never given to the application.

What does not run
- The reasoning model: its entry points are blocked, and any attempt fails the run. The current assistant's
  time on comparable questions is in results/evaluation-20261114 (four cases, 148-285 s).
- The decision model, unless LIFESCI_DECISION_ADAPTER=jev and TYPESAFE_API_KEY are set. A run without them
  reports C as not run; it never substitutes a stand-in.

This is a small trial on laboratory-scale public data repackaged as fictional deliveries. It measures request
time and agreement with reference calculations. It does not establish production latency, cause-finding ability
or manufacturing validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform as host_platform
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
DEMO = BACKEND / 'benchmarks' / 'cmo_ingestion' / 'demo'
TENANT, ACTOR, SITE, OTHER_ACTOR, OTHER_SITE = 'workflow-trial', 'trial-engineer', 'TRIAL-SITE', 'other-engineer', 'OTHER-SITE'
QA_ACTOR, MES_ACTOR = 'trial-qa', 'trial-mes'
ABSENT_PARAMETER, USED_LOT, COHORT_PAIR = 'titer', 'LOT-TRIAL-1', ('CHO-004-R01', 'CHO-004-R02')
HEADERS = {'X-Tenant-Id': TENANT, 'X-Actor-Id': ACTOR}
TARGETS = ('cho-returning', 'cho-changed', 'cho-unseen')
RTOL = 0.005  # the relative tolerance of the existing ingestion scoring rule
ISOLATED = ('CMO_DATABASE_URL', 'LIFESCI_DATABASE_URL', 'LIFESCI_MIGRATION_DATABASE_URL', 'SUPABASE_URL',
            'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_DB_URL', 'SUPABASE_ANON_KEY')
COMPARED = ('glucose', 'viable_cell_density', 'pH')
SYNONYMS = {'glucose': ('sugar', 'glc'), 'viable_cell_density': ('VCD', 'live cell count'), 'pH': ('acidity',)}


def close(actual, expected) -> bool:
    return (isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and math.isclose(actual, expected, rel_tol=RTOL, abs_tol=1e-9))


# --- preparation: real ingestion, then provisional evidence ---------------------------------------------------
def prepare(workdir: Path) -> dict[str, Any]:
    for name in ISOLATED:  # never a configured production database or project
        os.environ[name] = ''
    os.environ['CMO_HOSTED_INFERENCE_APPROVED'] = '0'
    os.environ['CMO_REPOSITORY_ROOT'] = str(workdir / 'repository')
    os.environ.pop('ASSISTANT_LOOP', None)
    from src.lifesci.cmo_datasets import share_provisional
    from src.lifesci.container import Platform
    from src.lifesci.store import RecordStore
    from src.manufacturing_data.cmo import quality
    from src.manufacturing_data.cmo.persistence import tenant_scope
    from src.manufacturing_data.cmo.pipeline import IngestionService

    catalog = {c['id']: c for c in json.loads((DEMO / 'catalog.json').read_text())}
    timings, runs = {}, {}
    with tenant_scope(TENANT):
        service = IngestionService(workdir / 'ingestion')
        if service.repo.backend != 'sqlite':
            raise RuntimeError('the trial must use its own local store')
        item = catalog['cho-calibration']
        t0 = time.perf_counter()
        calibration = service.run(DEMO / item['id'] / 'raw', item['cmo'], 'preview', synthetic=item['synthetic'])
        if calibration['status'] != 'complete':
            raise RuntimeError(calibration.get('error'))
        confirmed = 0
        for layout in calibration['layouts']:
            mapping = layout['mapping']
            if mapping['columns'] and mapping['batch_column'] and mapping['time_column']:
                service.confirm_template(calibration['id'], layout['fingerprint'], mapping, 'automated-study-protocol',
                    'Public vocabulary draft confirmed by the automated calibration protocol; not a human interaction.',
                    origin='study_protocol')
                confirmed += 1
        timings['calibration_seconds'] = time.perf_counter() - t0
        for package in TARGETS:
            item = catalog[package]
            t0 = time.perf_counter()
            run = service.run(DEMO / package / 'raw', item['cmo'], 'D', synthetic=item['synthetic'])
            if run['status'] != 'complete':
                raise RuntimeError(f'{package}: {run.get("error")}')
            timings[f'{package}_ingestion_seconds'] = time.perf_counter() - t0
            run['package_id'], run['delivery_name'] = package, item['name']
            runs[package] = run
    payloads = {package: quality.provisional_payload(run) for package, run in runs.items()}
    decoy_payload = quality.provisional_payload({**runs['cho-returning'], 'id': runs['cho-returning']['id'] + '-other-site'})

    def platform(providers=None, allow_unqualified=False):
        """A fresh application holding the same evidence. Every arm of the trial starts from this."""
        p = Platform(RecordStore(), providers={} if providers is None else providers, allow_unqualified=allow_unqualified)
        for actor, role, site in ((ACTOR, 'msat', SITE), (OTHER_ACTOR, 'msat', OTHER_SITE), (QA_ACTOR, 'qa', SITE),
                                  (MES_ACTOR, 'manufacturing_systems', SITE)):
            p.identity.assign_role(TENANT, actor, role, site_id=site)
        ctx, other = p.identity.context_for(TENANT, ACTOR), p.identity.context_for(TENANT, OTHER_ACTOR)
        deliveries = {}
        for package, payload in payloads.items():
            shared = share_provisional(p, ctx, payload, SITE)
            deliveries[package] = {'id': shared['evidence_id'], 'revision': shared['revision'], 'name': runs[package]['delivery_name'],
                                   'review': payload['review'], 'values': len(payload['measurements']),
                                   'statuses': dict(Counter(m['status'] for m in payload['measurements']))}
        # The same delivery at a site this engineer cannot read: it must never appear in any result.
        decoy = share_provisional(p, other, decoy_payload, OTHER_SITE)['evidence_id']
        return p, ctx, deliveries, decoy

    p, ctx, deliveries, decoy = platform()
    constructed = construct_context(p, ctx)
    # Only after ingestion: open the keys, check the packages are the ones the keys describe.
    keys = {}
    for package in TARGETS:
        key = json.loads((DEMO / package / 'evaluation' / 'answer_key.json').read_text())
        for file in key['files']:
            if hashlib.sha256((DEMO / package / 'raw' / file['path']).read_bytes()).hexdigest() != file['sha256']:
                raise ValueError(f'{package} changed since its answer key was generated')
        keys[package] = key
    return {'platform': p, 'ctx': ctx, 'deliveries': deliveries, 'decoy': decoy, 'keys': keys, 'catalog': catalog,
            'new_platform': platform, 'constructed': constructed,
            'preparation': {**timings, 'templates_confirmed_by_protocol': confirmed, 'ingestion_model_calls': 0}}


def construct_context(p, ctx) -> dict[str, Any]:
    """Context the CHO deliveries do not carry, added so the checks that need it have something to check.
    These records are constructed for the trial and say so; the measurements stay the real CHO values."""
    for parameter, unit, limits in (('glucose', 'g/L', {'low': 0.0, 'high': 60.0}), ('lactate', 'g/L', {'high': 20.0}),
                                    (ABSENT_PARAMETER, 'g/L', {'low': 0.0})):
        p.specifications.create(ctx, site_id=SITE, parameter=parameter, unit=unit, source='manual',
                                source_ref='constructed for the workflow trial', reason='Trial requirement, not a real limit', **limits)
    mes = p.identity.context_for(TENANT, MES_ACTOR)
    left, right = COHORT_PAIR
    for name, equipment in ((left, 'BR-01'), (right, 'BR-07')):
        p.execution.project_external(mes, 'batch', name, {
            'batch_id': name, 'product': 'CHO trial product', 'status': 'completed', 'process_version': 'trial-v1',
            'scale': '0.8 L', 'equipment_id': equipment, 'process_stage': 'cultivation'},
            source_system='trial-mes', source_ref=f'constructed/{name}', site_id=SITE)
    with p.store.transaction(ACTOR) as tx:  # one executed step, in the shape the execution service records
        tx.put(TENANT, 'procedure_instance', 'trial-instance-1', {'site_id': SITE, 'context': {'batch_id': left}, 'status': 'completed'},
               expected_revision=None, action='construct_trial_context')
        tx.put(TENANT, 'step_execution', 'trial-instance-1:feed:1', {
            'instance_id': 'trial-instance-1', 'step_id': 'feed', 'performed_at': '2026-10-02T09:00:00Z',
            'resources': {'lots': [{'lot_id': USED_LOT}], 'equipment': [{'equipment_id': 'BR-01'}]}},
            expected_revision=None, action='construct_trial_context')
    return {'specifications': ['glucose', 'lactate', ABSENT_PARAMETER], 'batch_records': list(COHORT_PAIR),
            'differs_in': ['Equipment'], 'used_lot': USED_LOT, 'used_in': left,
            'note': 'Constructed for the trial: three specifications, two batch records that differ only in equipment, '
                    'and one recorded use of a lot. Not real limits, equipment or usage.'}


# --- reference answers from the keys ------------------------------------------------------------------------------
def reference(key: dict) -> dict[str, Any]:
    present: dict[tuple, dict[float, float]] = defaultdict(dict)
    absent: dict[tuple, set[float]] = defaultdict(set)
    units, batches = {}, set()
    conflicts = {(d['batch'], d['parameter'], float(d['time'])) for d in key['defects'] if d['rule_code'] == 'DUPLICATE_CONFLICT'}
    for f in key['fields']:
        identity, t = (f['batch'], f['parameter']), float(f['time'])
        batches.add(f['batch'])
        units[f['parameter']] = f['unit']
        if not f['present']:
            absent[identity].add(t)
        elif (f['batch'], f['parameter'], t) not in conflicts:
            present[identity][t] = float(f['value'])
    return {'present': present, 'absent': absent, 'units': units, 'batches': sorted(batches), 'conflicts': conflicts}


def expected_comparison(ref, parameter, left, right, window=None, tolerance=0.0):
    """The reference comparison, calculated here from the key with plain arithmetic.
    Returns None when nearest-sample pairing would be ambiguous (two samples equally near): such a case is not scored."""
    inside = lambda t: window is None or window[0] <= t <= window[1]
    a = {t: v for t, v in ref['present'].get((left, parameter), {}).items() if inside(t)}
    b = {t: v for t, v in ref['present'].get((right, parameter), {}).items() if inside(t)}
    if tolerance:
        pairs = []
        for t in sorted(a):
            near = sorted((abs(u - t), u) for u in b if abs(u - t) <= tolerance)
            if len(near) > 1 and math.isclose(near[0][0], near[1][0], abs_tol=1e-9):
                return None
            if near:
                pairs.append((t, near[0][1]))
    else:
        pairs = [(t, t) for t in sorted(set(a) & set(b))]
    differences = [b[u] - a[t] for t, u in pairs]
    largest = max((abs(d) for d in differences), default=None)
    n = len(differences)
    mean = sum(differences) / n if n else None
    return {'matched_times': n, 'mean_difference': mean, 'largest_abs_difference': largest,
            'standard_deviation': math.sqrt(sum((d - mean) ** 2 for d in differences) / (n - 1)) if n > 1 else None,
            'largest_at': [t for (t, _), d in zip(pairs, differences) if largest is not None and math.isclose(abs(d), largest, rel_tol=1e-9)]}


def build_tasks(world) -> list[dict]:
    tasks = []
    for package in TARGETS:
        ref = reference(world['keys'][package])
        dataset, name = world['deliveries'][package]['id'], world['deliveries'][package]['name']
        base = {'site_id': SITE, 'dataset_ids': [dataset], 'include_unverified': True, 'limit': 100}
        add = lambda job, ident, request, check: tasks.append(
            {'id': f'{package}:{ident}', 'job': job, 'package': package, 'request': request, 'check': check, 'dataset': dataset})
        pairs = [(a, b) for a, b in combinations(ref['batches'], 2) if a.rsplit('-', 1)[0] == b.rsplit('-', 1)[0]]
        first = ref['batches'][0]

        # 04 compare: the paired runs of each experiment, three parameters
        for left, right in pairs:
            for parameter in COMPARED:
                if (left, parameter) not in ref['present'] or (right, parameter) not in ref['present']:
                    continue
                expected = expected_comparison(ref, parameter, left, right)
                conflicted = any(c[1] == parameter and c[0] in (left, right) for c in ref['conflicts'])
                cohort = 'differs' if (left, right) == COHORT_PAIR else 'not_established'
                add('04 compare', f'compare:{parameter}:{left}:{right}',
                    {**base, 'operation': 'compare', 'parameter': parameter, 'batches': [left, right]},
                    {'kind': 'compare', 'expected': expected, 'conflict_expected': conflicted, 'cohort': cohort})
        # 04 compare, inside a time window and with samples paired up to two hours apart
        left, right = pairs[0]
        span = sorted(ref['present'][(left, 'glucose')])
        window = (span[len(span) // 4], span[3 * len(span) // 4])
        add('04 compare', f'compare-window:glucose:{left}:{right}',
            {**base, 'operation': 'compare', 'parameter': 'glucose', 'batches': [left, right], 'time_from_h': window[0], 'time_to_h': window[1]},
            {'kind': 'compare', 'expected': expected_comparison(ref, 'glucose', left, right, window=window),
             'cohort': 'differs' if (left, right) == COHORT_PAIR else 'not_established',
             'conflict_expected': any(c[1] == 'glucose' and c[0] in (left, right) and window[0] <= c[2] <= window[1] for c in ref['conflicts'])})
        cross = (ref['batches'][0], ref['batches'][2])  # runs of different experiments: sample times need not coincide
        aligned = expected_comparison(ref, 'pH', *cross, tolerance=2.0)
        if aligned is not None and aligned['matched_times']:
            add('04 compare', f'compare-aligned:pH:{cross[0]}:{cross[1]}',
                {**base, 'operation': 'compare', 'parameter': 'pH', 'batches': list(cross), 'align_tolerance_h': 2.0},
                {'kind': 'compare', 'expected': aligned, 'conflict_expected': False, 'cohort': 'not_established'})
        # 06 gaps against what the site approved (constructed specifications), with nothing typed
        approved = [{'parameter': ABSENT_PARAMETER, 'status': 'unavailable', 'batch': None}]
        approved += [{'parameter': parameter, 'status': 'required_missing', 'batch': b} for parameter in ('glucose', 'lactate')
                     for b in ref['batches'] if not ref['present'].get((b, parameter))]
        add('06 find gaps', 'gaps:approved-requirements', {**base, 'operation': 'check_gaps'},
            {'kind': 'approved_gaps', 'expected': approved})
        # prepared profile of the delivery
        add('prepared profile', 'profile', None, {'kind': 'profile', 'values': world['deliveries'][package]['values'],
                                                  'batches': ref['batches']}, )
        tasks[-1]['get'] = f"/v1/workspace-tasks/deliveries/{dataset}/profile?site_id={SITE}"
        # the three tasks of one working question, run together as a flow
        add('template as a flow', f'template:glucose:{left}:{right}', None,
            {'kind': 'template', 'expected': expected_comparison(ref, 'glucose', left, right)})
        tasks[-1]['post'] = ('/v1/workspace-tasks/templates/batch_picture/run',
                             {'selection': {**base, 'parameter': 'glucose', 'batches': [left, right]}})
        # 03 reconcile: unit conversion checked value by value
        for parameter, target, convert in (('glucose', 'mg/L', lambda v: v * 1000), ('temperature', 'degC', lambda v: v - 273.15)):
            if (first, parameter) in ref['present']:
                add('03 reconcile', f'reconcile:{parameter}:{first}',
                    {**base, 'operation': 'reconcile', 'parameter': parameter, 'batches': [first], 'target_unit': target},
                    {'kind': 'reconcile', 'unit': target,
                     'points': {t: convert(v) for t, v in ref['present'][(first, parameter)].items()}})
        # 06 gaps: the key says which expected offline samples are absent from the source
        times = sorted(set(ref['present'].get((first, 'lactate'), {})) | ref['absent'].get((first, 'lactate'), set()))
        missing = [{'parameter': parameter, 'time_h': t} for parameter in ('lactate', 'glucose') for t in times
                   if t not in ref['present'].get((first, parameter), {})]
        add('06 find gaps', f'gaps:{first}',
            {**base, 'operation': 'check_gaps', 'batches': [first], 'expected_parameters': ['lactate', 'glucose'], 'expected_times': times},
            {'kind': 'gaps', 'missing': missing})
        # 01 find records: by delivery name and by a batch named inside it; never the other site's copy
        for label, query in (('name', name), ('batch', first)):
            add('01 find records', f'find:{label}', {'site_id': SITE, 'operation': 'find_records', 'query': query, 'kinds': ['evidence']},
                {'kind': 'find', 'must_include': dataset})
        # 02 applicability: stated batch matches, a foreign batch is excluded, an unrecorded date stays unknown
        ref_spec = [{'kind': 'evidence', 'id': dataset, 'revision': world['deliveries'][package]['revision'], 'site_id': SITE}]
        for label, extra, verdict in (('match', {'batches': [first]}, 'matches_requested_criteria'),
                                      ('other-batch', {'batches': ['CHO-999-R01']}, 'excluded'),
                                      ('no-date', {'effective_at': '2026-10-01T00:00:00Z'}, 'unknown')):
            add('02 select evidence', f'applicability:{label}',
                {'site_id': SITE, 'operation': 'select_evidence', 'record_refs': ref_spec, **extra},
                {'kind': 'applicability', 'verdict': verdict})
        # 07 impact: the delivery names the batch; a mention is never confirmed exposure
        add('07 trace impact', f'impact:{first}', {'site_id': SITE, 'operation': 'trace_impact', 'record_id': first},
            {'kind': 'impact', 'must_include': dataset})
        # 05 causes: nothing in these deliveries records a cause, so the only correct outcome is no claim
        add('05 suggest causes', f'causes:{first}', {'site_id': SITE, 'operation': 'suggest_causes', 'record_id': first},
            {'kind': 'causes'})
        # 08 review packet
        add('08 prepare review', 'review', {**base, 'operation': 'prepare_review'}, {'kind': 'review', 'must_include': dataset})
        # 08 from a result to a proposal that waits for an authorized person, and a working file that records it
        add('08 propose action', f'propose:{left}:{right}', None, {'kind': 'proposal'})
        tasks[-1]['perform'] = lambda client, world, base=base, left=left, right=right: propose_and_approve(client, world, base, left, right)
        # the trust gate: without the person's choice, values still in review are not used
        add('trust gate', 'in-review-refused', {'site_id': SITE, 'dataset_ids': [dataset], 'operation': 'compare',
                                               'parameter': 'glucose', 'batches': list(pairs[0])},
            {'kind': 'refused'})
    # 07 impact: recorded usage (one constructed step) is told apart from mentions; the genealogy is said to be incomplete
    lot = world['constructed']
    tasks.append({'id': 'constructed:usage', 'job': '07 trace impact', 'package': 'cho-returning', 'dataset': None,
                  'request': {'site_id': SITE, 'operation': 'trace_impact', 'record_id': lot['used_lot']},
                  'check': {'kind': 'usage', 'batches': [lot['used_in']]}})
    return tasks


def propose_and_approve(client, world, base, left, right):
    """Save a comparison, draft a proposal from it, keep it in a working file, then have QA approve it.
    Timed: everything the engineer does (three requests). The QA approval is a different person and is not timed."""
    p = world['platform']
    intents_before = len(p.store.read().list(TENANT, 'action_intent'))
    t0 = time.perf_counter()
    result = client.post('/v1/workspace-tasks/run', headers=HEADERS, json={**base, 'operation': 'compare', 'parameter': 'glucose',
                                                                           'batches': [left, right], 'use_decision_model': False}).json()
    proposal = client.post(f"/v1/workspace-tasks/results/{result['id']}/propose", headers=HEADERS, json={
        'operation': 'close_deviation', 'target_id': f'TRIAL-DEV-{left}', 'rationale': 'Trial proposal from a comparison.',
        'expected_result': 'Deviation closed with the comparison attached.'}).json()
    plan = client.post('/v1/work-plans', headers=HEADERS, json={'site_id': SITE, 'title': f'glucose {left} / {right}', 'selection': base}).json()
    plan = client.post(f"/v1/work-plans/{plan['id']}/steps", headers=HEADERS, json={
        'expected_revision': plan['revision'], 'kind': 'action', 'text': 'Close the deviation', 'result_id': result['id'],
        'proposal_id': proposal['proposal_id']}).json()
    seconds = time.perf_counter() - t0
    waiting = client.get(f"/v1/workspace-tasks/results/{result['id']}", headers=HEADERS).json()
    intents_at_proposal = len(p.store.read().list(TENANT, 'action_intent')) - intents_before  # proposing carries nothing out
    refused = None
    try:  # the engineer who proposed it cannot approve it
        p.actions.decide(world['ctx'], proposal['proposal_id'], expected_revision=1, decision='approved', role='qa',
                         authentication={'method': 'trial'})
    except Exception as exc:
        refused = type(exc).__name__
    p.actions.decide(p.identity.context_for(TENANT, QA_ACTOR), proposal['proposal_id'], expected_revision=1, decision='approved',
                     role='qa', authentication={'method': 'trial'})
    after = client.get(f"/v1/workspace-tasks/results/{result['id']}", headers=HEADERS).json()
    plan_after = client.get(f"/v1/work-plans/{plan['id']}", headers=HEADERS).json()
    return seconds, {**result, 'trial': {
        'proposal_status': proposal.get('status'), 'required_roles': proposal.get('required_roles'),
        'basis_first': (proposal.get('basis') or [{}])[0], 'constraints': proposal.get('constraints'),
        'work_status_waiting': waiting.get('work_status'), 'step_stands_waiting': plan['steps'][0]['stands'],
        'intents_at_proposal': intents_at_proposal, 'proposer_approval_refused': refused,
        'work_status_after': after.get('work_status'), 'proposal_after': (after.get('proposals') or [{}])[0].get('status'),
        'step_stands_after': plan_after['steps'][0]['stands']}}


def check(task, result, world) -> list[str]:
    """Reasons this result is wrong. Empty means every supplied expectation held."""
    spec, data, problems = task['check'], result.get('data') or {}, []
    refs = {(r['kind'], r['id']): r for r in result.get('source_refs') or []}
    if result.get('model_calls') != 0:
        problems.append('a reasoning-model call was reported')
    if any(r['id'] == world['decoy'] or r.get('site_id') == OTHER_SITE for r in result.get('source_refs') or []):
        problems.append('wrong-site record in the sources')
    if world['decoy'] in json.dumps(data):
        problems.append('wrong-site record in the result')
    dataset = task['dataset']
    if spec['kind'] in ('compare', 'reconcile', 'gaps', 'review'):
        ref = refs.get(('evidence', dataset))
        if ref is None or ref['revision'] != world['deliveries'][task['package']]['revision']:
            problems.append('the result does not cite the selected delivery at its current revision')
        if spec['kind'] != 'review' and result.get('evidence_state') != 'provisional':
            problems.append('values in review were used without saying so')
    codes = [i['code'] for i in result.get('issues') or []]
    if spec['kind'] == 'compare':
        expected = spec['expected']
        summary = (data.get('comparison_summary') or [None])[0]
        if summary is None:
            return problems + ['no comparison summary']
        if summary['matched_times'] != expected['matched_times'] or data.get('comparison_count') != expected['matched_times']:
            problems.append(f"matched times {summary['matched_times']} != {expected['matched_times']}")
        if not close(summary['mean_difference'], expected['mean_difference']):
            problems.append(f"mean difference {summary['mean_difference']} != {expected['mean_difference']}")
        largest = summary['largest_difference']
        if not close(abs(largest['difference']), expected['largest_abs_difference']) or largest['time_h'] not in expected['largest_at']:
            problems.append(f"largest difference {largest} != {expected['largest_abs_difference']} at {expected['largest_at']}")
        if len(data.get('series') or []) != 2 or not data.get('series_complete') or data.get('truncated'):
            problems.append('the result does not hold both complete series')
        if spec['conflict_expected'] != ('conflicting_measurements' in codes):
            problems.append('conflicting duplicate ' + ('not reported' if spec['conflict_expected'] else 'reported where none exists'))
        deviation = summary['statistics'].get('standard_deviation')
        if expected['standard_deviation'] is not None and not close(deviation, expected['standard_deviation']):
            problems.append(f"standard deviation of the differences {deviation} != {expected['standard_deviation']}")
        cohort = data.get('cohort') or {}
        if spec.get('cohort') and cohort.get('verdict') != spec['cohort']:
            problems.append(f"context check {cohort.get('verdict')} != {spec['cohort']}")
        if spec.get('cohort') == 'differs' and (cohort.get('differs') != world['constructed']['differs_in'] or 'cohort_differs' not in codes):
            problems.append('the difference in context was not reported')
        if cohort.get('verdict') == 'same_context' and cohort.get('not_recorded'):
            problems.append('context that is not recorded was treated as the same')
        flagged = spec['conflict_expected'] or spec.get('cohort') == 'differs'
        if result['task_status'] != ('needs_information' if flagged else 'completed'):
            problems.append(f"status {result['task_status']}")
    elif spec['kind'] == 'reconcile':
        series = data.get('series') or []
        points = {t: v for t, v in series[0]['points']} if len(series) == 1 else {}
        wrong = [t for t, v in spec['points'].items() if not close(points.get(t), v)]
        if set(points) != set(spec['points']) or wrong:
            problems.append(f'{len(wrong)} of {len(spec["points"])} converted values differ; {len(set(points) ^ set(spec["points"]))} times differ')
        if series and series[0]['unit'] != spec['unit']:
            problems.append('wrong unit')
    elif spec['kind'] == 'gaps':
        found = {(g.get('parameter'), g.get('time_h')) for g in data.get('gaps') or []}
        expected = {(g['parameter'], g['time_h']) for g in spec['missing']}
        if found != expected:
            problems.append(f'gaps: {len(expected - found)} missed, {len(found - expected)} reported that are present')
        if data.get('gap_count') != len(expected):
            problems.append('gap count differs')
    elif spec['kind'] in ('find', 'impact', 'review'):
        ids = [r.get('id') for r in data.get('records') or []]
        if spec['must_include'] not in ids:
            problems.append('the delivery is not among the records returned')
        if spec['kind'] == 'impact' and (data.get('exposure_confirmed') is not False or data.get('causal_claim_supported') is not False):
            problems.append('a mention was presented as confirmed exposure or cause')
        if spec['kind'] == 'review' and data.get('review_state') != 'draft_requires_review':
            problems.append('the packet is not marked as a draft for review')
    elif spec['kind'] == 'applicability':
        verdicts = [r.get('applicability') for r in data.get('records') or []]
        if verdicts != [spec['verdict']]:
            problems.append(f'applicability {verdicts} != {spec["verdict"]}')
        if (result['task_status'] == 'completed') != (spec['verdict'] == 'matches_requested_criteria'):
            problems.append('an unresolved applicability was reported as complete')
    elif spec['kind'] == 'causes':
        if data.get('causal_claim_supported') is not False or data.get('causal_status') != 'hypotheses_only':
            problems.append('a cause was claimed')
        if any(h.get('kind') not in ('hypothesis', 'precedent_hypothesis') or not h.get('not_established') for h in data.get('hypotheses') or []):
            problems.append('a candidate is not labelled as a hypothesis with what is not established')
        if result['task_status'] != 'needs_information':
            problems.append('reported complete although the subject is not a stored record')
    elif spec['kind'] == 'approved_gaps':
        found = sorted((g.get('parameter'), g.get('batch'), g['status']) for g in data.get('gaps') or [])
        expected = sorted((g['parameter'], g['batch'], g['status']) for g in spec['expected'])
        if found != [tuple(x) for x in expected] or data.get('expectation_basis') != 'approved_specifications':
            problems.append(f'gaps against approved requirements {found} != {expected}')
        if not (data.get('draft_request') or {}).get('status') == 'draft_not_sent':
            problems.append('no draft request, or a request was sent without the person')
        if not any(r['kind'] == 'specification' for r in result.get('source_refs') or []):
            problems.append('the requirements checked are not cited')
    elif spec['kind'] == 'usage':
        if data.get('affected_batches') != spec['batches'] or any(u.get('basis') != 'recorded_usage' for u in data.get('recorded_usage') or []):
            problems.append(f"recorded usage {data.get('affected_batches')} != {spec['batches']}")
        if (data.get('genealogy') or {}).get('complete') is not False or data.get('exposure_confirmed') is not False:
            problems.append('an incomplete genealogy was presented as complete, or exposure as confirmed')
    elif spec['kind'] == 'profile':
        if result.get('values') != spec['values'] or result.get('batches') != spec['batches'] or result.get('verification') != 'provisional':
            problems.append(f"profile holds {result.get('values')} values of {spec['values']}")
        return [x for x in problems if 'reasoning-model' not in x]  # a profile is not a task result
    elif spec['kind'] == 'template':
        results = result.get('results') or {}
        summary = ((results.get('compare') or {}).get('data', {}).get('comparison_summary') or [None])[0]
        if result.get('status') != 'completed' or set(results) != {'reconcile', 'compare', 'gaps'} or not all(r.get('id') for r in results.values()):
            problems.append('the template did not complete and save its three results')
        elif summary is None or summary['matched_times'] != spec['expected']['matched_times'] or not close(summary['mean_difference'], spec['expected']['mean_difference']):
            problems.append('the comparison inside the template differs from the reference')
        if world['platform'].store.read().require(TENANT, 'data_flow_run', result['flow_run_id']).state['status'] != 'completed':
            problems.append('the flow run was not recorded as completed')
        return [x for x in problems if 'reasoning-model' not in x] + ([] if result.get('model_calls') == 0 else ['model call reported'])
    elif spec['kind'] == 'proposal':
        t = result['trial']
        expected = {'proposal_status': 'proposed', 'required_roles': ['qa'], 'work_status_waiting': 'needs_approval',
                    'step_stands_waiting': 'waiting for approval', 'intents_at_proposal': 0, 'proposal_after': 'approved',
                    'step_stands_after': 'approved, not yet carried out'}
        problems += [f'{k}: {t.get(k)!r} != {v!r}' for k, v in expected.items() if t.get(k) != v]
        if not t.get('proposer_approval_refused'):
            problems.append('the proposer approved their own QA action')
        if t['basis_first'].get('kind') != 'workspace_task_result' or not any('still in review' in c for c in t.get('constraints') or []):
            problems.append('the proposal does not rest on the result, or hides that its values are in review')
    elif spec['kind'] == 'refused':
        if codes[:1] != ['unverified_dataset'] or data.get('comparison_count') or result['task_status'] != 'needs_information':
            problems.append('values in review were used without the person asking')
    return problems


# --- typed sentences through the router ----------------------------------------------------------------------------
def build_requests(world) -> list[dict]:
    """Sentences a person might type. `expect` is the task that would be right, or None when the request needs the
    assistant. `family` is the phrasing family; `split` holds out phrasings and one whole delivery for calibration."""
    out = []
    for package in TARGETS:
        ref = reference(world['keys'][package])
        dataset, name = world['deliveries'][package]['id'], world['deliveries'][package]['name']
        a, b = ref['batches'][0], ref['batches'][1]
        held_out = package == 'cho-unseen'
        def add(family, text, expect, split='fit'):
            out.append({'id': f'{package}:{family}:{len(out)}', 'package': package, 'family': family, 'text': text,
                        'expect': expect, 'split': 'held_out' if held_out or split == 'held_out' else 'fit'})
        task = lambda operation, parameter, batches: {'operation': operation, 'dataset_ids': [dataset], 'parameter': parameter, 'batches': batches}
        for parameter in COMPARED:
            spoken = parameter.replace('_', ' ')
            add('exact', f'Compare {spoken} between {a} and {b}', task('compare', parameter, [a, b]))
            add('exact', f'compare {spoken} across all batches in the {name} delivery', task('compare', parameter, []))
            add('exact', f'Reconcile {spoken} for {a}', task('reconcile', parameter, [a]))
            for i, synonym in enumerate(SYNONYMS[parameter]):
                add('synonym', f'Compare {synonym} between {a} and {b}', task('compare', parameter, [a, b]), 'held_out' if i else 'fit')
            add('paraphrase', f'How do {a} and {b} differ on {spoken}', task('compare', parameter, [a, b]))
            add('paraphrase', f'Put {a} next to {b} for {spoken}', task('compare', parameter, [a, b]), 'held_out')
            add('reasoning', f'Why is {spoken} different between {a} and {b}?', None)
            add('reasoning', f'Is {spoken} in {a} acceptable?', None, 'held_out')
        add('reasoning', f'Summarize the {name} delivery', None)
        add('unsupported', f'Compare {COMPARED[0]} between {a} and {b} after 48 h', None)
        add('unsupported', f'Compare {COMPARED[0]} for {a}', None, 'held_out')
    return out


def same_task(task, expect) -> bool:
    return (task is not None and task['operation'] == expect['operation'] and task['dataset_ids'] == expect['dataset_ids']
            and task['parameter'] == expect['parameter'] and sorted(task['batches']) == sorted(expect['batches']))


def calibrate(samples: list[dict], *, target_precision: float = 1.0, minimum_accepted: int = 10) -> dict[str, Any]:
    """Pick the lowest probability threshold at which every fit-split suggestion at or above it was right, then
    report what that threshold does on the held-out split. samples: {probability, correct, split}."""
    fit = sorted((s for s in samples if s['split'] == 'fit'), key=lambda s: -s['probability'])
    held = [s for s in samples if s['split'] == 'held_out']
    threshold = None
    for i, sample in enumerate(fit):
        accepted = fit[:i + 1]
        if sum(s['correct'] for s in accepted) / len(accepted) < target_precision:
            break
        if len(accepted) >= minimum_accepted and (i + 1 == len(fit) or fit[i + 1]['probability'] < sample['probability']):
            threshold = sample['probability']
    def at(rows):
        accepted = [s for s in rows if threshold is not None and s['probability'] >= threshold]
        return {'n': len(rows), 'accepted': len(accepted), 'accepted_correct': sum(s['correct'] for s in accepted),
                'precision': sum(s['correct'] for s in accepted) / len(accepted) if accepted else None,
                'coverage': len(accepted) / len(rows) if rows else None}
    return {'threshold': None if threshold is None else max(0.5, threshold), 'target_precision': target_precision,
            'minimum_accepted': minimum_accepted, 'fit': at(fit), 'held_out': at(held)}


# --- running and timing ---------------------------------------------------------------------------------------------
class Blocked:
    """The reasoning model must not run in this trial. Any attempt is counted and fails the request."""
    def __init__(self, platform):
        self.attempts = 0
        platform.gateway.run = platform.gateway.converse = self
        platform.agent_memory.embedder = self
        self.model = 'inference-blocked'

    def __call__(self, *args, **kwargs):
        self.attempts += 1
        raise RuntimeError('the reasoning model is blocked in this trial')

    embed = __call__


def timed(client, path, body):
    t0 = time.perf_counter()
    response = client.post(path, headers=HEADERS, json=body)
    seconds = time.perf_counter() - t0
    return seconds, response


def run_tasks(client, world, tasks, mode, repeats) -> list[dict]:
    rows = []
    for repeat in range(1, repeats + 1):
        for task in tasks:
            row = {'mode': mode, 'task_id': task['id'], 'job': task['job'], 'package': task['package'], 'repeat': repeat,
                   'outcome': 'error'}
            try:
                if task.get('perform'):
                    seconds, result = task['perform'](client, world)
                    status = 200
                elif task.get('get'):
                    t0 = time.perf_counter()
                    response = client.get(task['get'], headers=HEADERS)
                    seconds, status, result = time.perf_counter() - t0, response.status_code, response.json()
                else:
                    path, body = task.get('post') or ('/v1/workspace-tasks/run', {**task['request'], 'use_decision_model': mode == 'C'})
                    seconds, response = timed(client, path, body)
                    status, result = response.status_code, response.json()
                row['request_seconds'] = seconds
                if status != 200:
                    row['error'] = {'status': status, 'body': json.dumps(result)[:600]}
                else:
                    problems = check(task, result, world)
                    cacheable = task.get('request') and task['request'].get('operation') in ('compare', 'reconcile') and mode == 'B'
                    hit = (result.get('cache') or {}).get('hit')
                    if cacheable and task['check']['kind'] != 'refused' and hit is not (repeat > 1):
                        problems.append('first calculation was not fresh' if repeat == 1 else 'an identical repeat was recalculated instead of reused')
                    row.update(outcome='failed' if problems else 'passed', problems=problems,
                               task_status=result.get('task_status'), server_timing=result.get('timing'), cache_hit=hit,
                               decision_model_calls=result.get('decision_model_calls', 0),
                               decisions=result.get('decisions') or [], result_id=result.get('id'),
                               issue_codes=dict(Counter(i['code'] for i in result.get('issues') or [])))
            except Exception as exc:  # a failed request stays in the report
                row['error'] = {'type': type(exc).__name__, 'message': str(exc)[:600]}
            rows.append(row)
    return rows


def run_requests(client, requests, mode, repeats) -> list[dict]:
    rows = []
    for repeat in range(1, repeats + 1):
        for request in requests:
            row = {'mode': mode, 'request_id': request['id'], 'family': request['family'], 'package': request['package'],
                   'split': request['split'], 'repeat': repeat, 'text': request['text'], 'outcome': 'error'}
            try:
                seconds, response = timed(client, '/v1/workspace-tasks/route', {
                    'site_id': SITE, 'text': request['text'], 'include_unverified': True, 'use_decision_model': mode == 'C'})
                routed = response.json()
                expect, task = request['expect'], routed.get('task')
                total = seconds
                if routed['route'] == 'direct':
                    run_seconds, ran = timed(client, '/v1/workspace-tasks/run', task)
                    total += run_seconds
                    row['ran_status'] = ran.status_code
                suggestion = routed.get('suggested_task')
                row.update(
                    request_seconds=total, route_seconds=seconds, route=routed['route'], basis=routed['basis'], reason=routed['reason'],
                    # The four outcomes that matter: ran the right task; ran a wrong one (the serious error);
                    # rightly left it to the assistant; left a routine request to the assistant (slower, not wrong).
                    outcome=('direct_correct' if same_task(task, expect) else 'direct_wrong') if routed['route'] == 'direct' and expect
                            else 'direct_wrong' if routed['route'] == 'direct'
                            else 'assistant_correct' if expect is None else 'assistant_routine_missed',
                    suggestion_correct=None if suggestion is None or expect is None else same_task(suggestion, expect),
                    suggestion_given=suggestion is not None,
                    probability=min((a['probability'] for d in routed.get('decisions') or [] for a in d.get('answers') or []
                                     if a.get('probability') is not None), default=None),
                    decision_statuses=dict(Counter(d['status'] for d in routed.get('decisions') or [])),
                    decision_ms=sum(d.get('latency_ms') or 0 for d in routed.get('decisions') or []))
            except Exception as exc:
                row['error'] = {'type': type(exc).__name__, 'message': str(exc)[:600]}
            rows.append(row)
    return rows


def spread(values, target) -> dict[str, Any]:
    from src.lifesci.latency import distribution
    return distribution(values, target=target)


def summarize(rows, key, target) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    out = []
    for name, items in sorted(groups.items()):
        timed_rows = [r['request_seconds'] for r in items if 'request_seconds' in r]
        out.append({key: name, 'requests': len(items), 'outcomes': dict(Counter(r['outcome'] for r in items)),
                    'cold_first_repeat': spread([r['request_seconds'] for r in items if r['repeat'] == 1 and 'request_seconds' in r], target),
                    'all': spread(timed_rows, target)})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', required=True, type=Path, help='A new directory; an existing one is never overwritten.')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--decision-model', action='store_true', help='Read the decision-model settings (TYPESAFE_API_KEY, '
                        'LIFESCI_DECISION_*) from backend/.env.local and run arm C. Sends the requests and delivery names to TypeSafe.')
    parser.add_argument('--write-calibration', type=Path, help='With the decision model on: write a calibration file '
                        'for route_request if the held-out split meets the target precision.')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('the output directory already exists; choose a new one')
    if args.repeats < 1:
        parser.error('repeats must be at least 1')
    sys.path.insert(0, str(BACKEND))
    if args.decision_model:
        from src.lifesci.envfile import parse_env
        local = BACKEND / '.env.local'
        for name, value in (parse_env(local.read_text()) if local.is_file() else {}).items():
            if (name.startswith(('TYPESAFE_', 'LIFESCI_DECISION_'))) and value:
                os.environ.setdefault(name, value)
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    from src.lifesci.gateway.decisions import DecisionAdapter
    from src.lifesci.latency import ANSWER_TARGET_SECONDS as target

    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='workflow-trial-') as tmp:
        world = prepare(Path(tmp))
        p = world['platform']
        blocked = Blocked(p)
        configured = p.gateway.decisions  # read from the environment when the platform was built
        client = TestClient(create_app(p))
        tasks, requests = build_tasks(world), build_requests(world)
        rows, routed = [], []
        # B: host rules only.
        p.gateway.decisions = DecisionAdapter(p.gateway)
        rows += run_tasks(client, world, tasks, 'B', args.repeats)
        routed += run_requests(client, requests, 'B', args.repeats)
        # C: the same requests with the decision model, only if it is really configured.
        c_state: dict[str, Any] = {'status': 'not_run', 'reason': configured.configuration_issue or
                                   'LIFESCI_DECISION_ADAPTER=jev and TYPESAFE_API_KEY are not set; nothing was substituted.'}
        if configured.enabled:
            p.gateway.decisions = configured
            rows += run_tasks(client, world, tasks, 'C', args.repeats)
            routed += run_requests(client, requests, 'C', 1)  # one pass: each sentence is one paid request
            samples = [{'probability': r['probability'], 'correct': bool(r['suggestion_correct'] or r['outcome'] == 'direct_correct'),
                        'split': r['split']} for r in routed if r['mode'] == 'C' and r.get('probability') is not None
                       and (r.get('suggestion_given') or r['route'] == 'direct')]
            c_state = {'status': 'run', 'adapter': configured.describe(), 'calibration': calibrate(samples),
                       'cost_usd': sum(r.state['cost_usd'] for r in p.store.read().list(TENANT, 'model_run')
                                       if r.state['task_kind'] == 'bounded_decision'),
                       'requests': sum(1 for r in p.store.read().list(TENANT, 'model_run') if r.state['task_kind'] == 'bounded_decision')}
            held = c_state['calibration']['held_out']
            if args.write_calibration and c_state['calibration']['threshold'] is not None and held['accepted'] and held['precision'] == 1.0:
                args.write_calibration.write_text(json.dumps({'tasks': {'route_request': {
                    'model': configured.model, 'threshold': c_state['calibration']['threshold'],
                    'eval_id': f'workflow-trial-{started[:10]}', 'held_out_n': held['n'],
                    'precision_at_threshold': held['precision'], 'held_out_accepted': held['accepted']}}}, indent=2) + '\n')
                c_state['calibration_file'] = str(args.write_calibration)
        window = client.get('/v1/latency', headers=HEADERS).json()
        p.store.release_connections()

    def by_mode(mode):
        t = [r for r in rows if r['mode'] == mode]
        q = [r for r in routed if r['mode'] == mode]
        if not t:
            return None
        return {'tasks': {'requests': len(t), 'passed': sum(r['outcome'] == 'passed' for r in t),
                          'failed': [{'task_id': r['task_id'], 'repeat': r['repeat'], 'problems': r.get('problems'), 'error': r.get('error')}
                                     for r in t if r['outcome'] != 'passed'],
                          'unresolved_rate': sum(r.get('task_status') == 'needs_information' for r in t) / len(t),
                          'time': spread([r['request_seconds'] for r in t if 'request_seconds' in r], target),
                          'by_job': summarize(t, 'job', target), 'by_delivery': summarize(t, 'package', target)},
                'typed_requests': {'requests': len(q), 'outcomes': dict(Counter(r['outcome'] for r in q)),
                                   'by_family': {family: dict(Counter(r['outcome'] for r in q if r['family'] == family))
                                                 for family in sorted({r['family'] for r in q})},
                                   'suggestions': {'given': sum(bool(r.get('suggestion_given')) for r in q),
                                                   'correct': sum(bool(r.get('suggestion_correct')) for r in q)},
                                   'time_when_run_directly': spread([r['request_seconds'] for r in q if r.get('route') == 'direct'], target),
                                   'time_to_decide_route': spread([r['route_seconds'] for r in q if 'route_seconds' in r], target)}}
    report = {
        'schema_version': 'workflow-trial-report-v1', 'started_at': started,
        'protocol': {
            'python': host_platform.python_version(), 'platform': host_platform.platform(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'repeats': args.repeats,
            'target_seconds': target, 'reference_tolerance_relative': RTOL,
            'data': 'Real CHO cultivation measurements (Zenodo 20829178, CC BY 4.0) repackaged as fictional CMO deliveries; '
                    'company names, layouts, certificates and the injected defects are constructed.',
            'constructed_context': world['constructed'],
            'reuse': 'An identical comparison or reconciliation repeated by the same person is reused from the result cache after '
                     'access and source revisions are rechecked; the first repeat is always a fresh calculation.',
            'held_out': 'The three deliveries are disjoint from the calibration delivery by experiment and month; one has an '
                        'unseen layout and one a changed layout with injected defects. One site only.',
            'timing': 'request_seconds is wall time of the HTTP request measured at the caller, in process: authorization, '
                      'validation, retrieval, calculation, saving the result and serialization. Network and browser time are '
                      'not included. The first repeat reads each delivery cold; later repeats reuse the parsed delivery.',
            'limits': ['Small trial: three deliveries, one site, laboratory scale. Repeats measure variation, not new cases.',
                       'Percentiles of a sample this size do not establish a production figure.',
                       'Cause-finding is not scored: these deliveries record no reviewed cause. Job 05 is checked only for making no claim.',
                       'The assistant and the explanation model are not run here; they are measured by benchmarks.workflow_trial.live.',
                       'The deliveries are still in review, so every calculation here is on provisional values and says so.'],
        },
        'preparation': world['preparation'], 'deliveries': world['deliveries'],
        'reasoning_model': {'calls': 0, 'blocked_attempts': blocked.attempts, 'cost_usd': 0},
        'B_direct_workflows': by_mode('B'), 'C_decision_model': {**c_state, **({'results': by_mode('C')} if by_mode('C') else {})},
        'server_latency_window': window, 'task_rows': rows, 'typed_request_rows': routed,
    }
    args.output.mkdir(parents=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str, allow_nan=False) + '\n')
    b = report['B_direct_workflows']
    lines = ['# Workflow trial', '', f"Started {started}. Target: an answer within {target:g} s.", '',
             f"**B, direct workflows:** {b['tasks']['passed']}/{b['tasks']['requests']} requests matched their reference; "
             f"mean {b['tasks']['time']['mean']:.3f} s, p95 {b['tasks']['time']['p95']:.3f} s, slowest {b['tasks']['time']['max']:.3f} s; "
             f"{b['tasks']['time']['over_target']} over the target. Reasoning-model calls: 0 (blocked attempts: {blocked.attempts}).", '',
             '| Job | Requests | Passed | Mean s | p95 s | Slowest s | Over target |', '|---|---:|---:|---:|---:|---:|---:|']
    for job in b['tasks']['by_job']:
        lines.append(f"| {job['job']} | {job['requests']} | {job['outcomes'].get('passed', 0)} | {job['all']['mean']:.3f} | "
                     f"{job['all']['p95']:.3f} | {job['all']['max']:.3f} | {job['all']['over_target']} |")
    q = b['typed_requests']
    lines += ['', f"**Typed sentences, host rules:** {q['requests']} requests: {json.dumps(q['outcomes'])}. "
              f"A wrong task run directly is the serious error; a routine request left to the assistant is only slower.", '',
              f"**C, decision model:** {c_state['status']}" + (f" ({c_state['reason']})" if c_state['status'] == 'not_run' else ''), '',
              'Limits: ' + ' '.join(report['protocol']['limits']), '']
    (args.output / 'report.md').write_text('\n'.join(lines))
    print('\n'.join(lines))
    failed = b['tasks']['requests'] - b['tasks']['passed'] + q['outcomes'].get('direct_wrong', 0) + q['outcomes'].get('error', 0)
    return 0 if failed == 0 and blocked.attempts == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
