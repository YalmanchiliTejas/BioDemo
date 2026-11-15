"""The skills, each built from a real dataset, each with its own way of being wrong.

A case asks the product for something through its typed tasks (no model involved) and scores the response against
a reference calculated here from the publisher's values. For "analyst questions" a question counts as answered
only if the product states the answer in its result; raw points a person could work it out from do not count,
because working it out is the job being measured.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any

from benchmarks.workflow_trial.run import expected_comparison

from .core import Case, Skill
from .worlds import TABLET_NO_UNITS, TABLET_WITH_UNITS, lot_format, split_header

SKILLS = {s.id: s for s in (
    Skill('compare_runs', 'Compare runs', 'Given two runs and a parameter, are the differences the product reports the right ones?',
          'workspace task "compare"', ('cho',)),
    Skill('analyst_questions', 'Analyst questions', 'Does the product state the answer to the questions an engineer asks of a run: '
          'a value at a time, the peak and when, an average over a window, when a threshold was crossed, how much it changed?',
          'workspace tasks "reconcile" and "compare", delivery profile', ('cho',)),
    Skill('fair_comparison', 'Fair comparison', 'When batches of different product or scale are compared, does the product say so, '
          'and does it avoid calling unrecorded context the same?', 'workspace task "compare" context check', ('tablet',)),
    Skill('gaps', 'Missing results', 'Against what the site requires for every batch, does the product report exactly the results that are missing?',
          'workspace task "check_gaps" against approved specifications', ('tablet',)),
    Skill('trace_usage', 'Trace a lot through batches', 'Given a raw-material lot, does the product return exactly the batches recorded as using it, '
          'and say when the genealogy is incomplete?', 'workspace task "trace_impact" recorded usage', ('tablet',)),
    Skill('find_identifier', 'Find a record by lot number', 'Given a lot number as a firm wrote it, does search return the reports that name it?',
          'workspace task "find_records"', ('fda_drug_recalls',)),
    Skill('trace_mention', 'Link records by lot number', 'Given the same lot number, does tracing return the reports that mention it, as mentions?',
          'workspace task "trace_impact" identifier links', ('fda_drug_recalls',)),
    Skill('intent_abstention', 'Decide or abstain (decision model)', 'Asked which of 20 intents a real request means, does the decision model pick the right one, '
          'say "unknown" for a request that fits none, and is its probability a usable signal?', 'gateway decision adapter (Jev)', ('clinc150',)),
)}


def call(world, request) -> dict[str, Any]:
    """One typed task, calculated without saving. A refusal by the product is a response, not a crash."""
    body = {'site_id': world['site'], 'include_unverified': True, 'use_decision_model': False, 'limit': 100, **request}
    try:
        return {'ok': True, 'result': world['p'].workspace_tasks.compute(world['ctx'], body)}
    except (ValueError, PermissionError, KeyError, LookupError) as exc:
        return {'ok': False, 'message': str(exc).splitlines()[0][:200]}


def close(a, b, rel=1e-6) -> bool:
    return isinstance(a, (int, float)) and not isinstance(a, bool) and b is not None and math.isclose(a, b, rel_tol=rel, abs_tol=1e-9)


def refused(response) -> tuple[str, str] | None:
    if response['ok']:
        return None
    message = response['message']
    if any(word in message for word in ('exceeds', 'at most', 'limit', 'partition')):
        return 'not_supported', 'the data is larger than a direct task accepts'
    return 'error', message


# --- compare runs (CHO) ------------------------------------------------------------------------------------------
def score_compare(case, response):
    bad = refused(response)
    if bad:
        return bad
    result, expected = response['result'], case.reference
    summary = (result['data'].get('comparison_summary') or [None])[0]
    codes = [i['code'] for i in result['issues']]
    if expected is None or not expected['matched_times']:
        return ('correct', '') if summary is None else ('false_alarm', 'compared runs that share no sample time')
    if summary is None:
        return 'abstained_unnecessarily', (result['issues'][0]['message'] if result['issues'] else 'no comparison returned')
    if not any(r['id'] in case.request['dataset_ids'] for r in result['source_refs']):
        return 'wrong_record', 'the selected delivery is not cited'
    if summary['matched_times'] != expected['matched_times']:
        return 'wrong_value', f"paired {summary['matched_times']} samples, reference pairs {expected['matched_times']}"
    scale = case.reference.get('scale', 1.0)
    largest = summary['largest_difference']
    if not close(summary['mean_difference'], expected['mean_difference'] * scale):
        return 'wrong_value', 'mean difference differs from the reference'
    if not close(abs(largest['difference']), expected['largest_abs_difference'] * scale) or largest['time_h'] not in expected['largest_at']:
        return 'wrong_value', 'largest difference or its time differs from the reference'
    deviation = summary['statistics'].get('standard_deviation')
    if expected['standard_deviation'] is not None and not close(deviation, expected['standard_deviation'] * scale):
        return 'wrong_value', 'spread of the differences differs from the reference'
    if 'conflicting_measurements' in codes:
        return 'false_alarm', 'reported conflicting values where the source has none'
    return 'correct', ''


def compare_cases(world) -> list[Case]:
    ref, full, out = {'present': world['reference']}, {'present': world['reference_full']}, []
    run = lambda case, w: call(w, case.request)
    def add(ident, tags, request, expected, scale=1.0):
        out.append(Case(f'compare:{ident}', 'compare_runs', 'cho', tuple(tags), {'operation': 'compare', **request},
                        None if expected is None else {**expected, 'scale': scale}, run, score_compare))
    experiments = sorted(world['experiments'])
    for exp in experiments:
        info = world['experiments'][exp]
        a, b = info['batches']
        offline, inline = world['deliveries'][(exp, 'offline')]['id'], world['deliveries'][(exp, 'inline')]['id']
        for parameter in ('VCD Mean', 'Viability Mean', 'Glucose', 'Lactate', 'Ammonium', 'Osmolality'):
            ta, tb = set(world['reference'].get((a, parameter), {})), set(world['reference'].get((b, parameter), {}))
            if not ta or not tb:
                continue
            tags = ['offline samples', info['mode'], 'same sample times' if ta == tb else 'different sample times']
            add(f'{exp}:{parameter}', tags, {'dataset_ids': [offline], 'parameter': parameter, 'batches': [a, b]},
                expected_comparison(ref, parameter, a, b))
        for parameter in ('pH', 'Temperature', 'Dissolved O2'):
            add(f'{exp}:{parameter}', ['process data every 10 minutes', info['mode'], 'over 1,000 samples per run'],
                {'dataset_ids': [inline], 'parameter': parameter, 'batches': [a, b]}, expected_comparison(ref, parameter, a, b))
        # the same comparison asked for in another unit: a difference in K equals the difference in degC; g/L to mg/L is x1000
        add(f'{exp}:Temperature:kelvin', ['process data every 10 minutes', 'unit conversion'],
            {'dataset_ids': [inline], 'parameter': 'Temperature', 'batches': [a, b], 'target_unit': 'K'},
            expected_comparison(ref, 'Temperature', a, b))
        add(f'{exp}:Glucose:mg', ['offline samples', 'unit conversion'],
            {'dataset_ids': [offline], 'parameter': 'Glucose', 'batches': [a, b], 'target_unit': 'mg/L'},
            expected_comparison(ref, 'Glucose', a, b), scale=1000.0)
        # inside a time window
        times = sorted(world['reference'][(a, 'Glucose')])
        window = (times[len(times) // 4], times[3 * len(times) // 4])
        add(f'{exp}:Glucose:window', ['offline samples', 'time window'],
            {'dataset_ids': [offline], 'parameter': 'Glucose', 'batches': [a, b], 'time_from_h': window[0], 'time_to_h': window[1]},
            expected_comparison(ref, 'Glucose', a, b, window=window))
    # runs of different experiments, from two deliveries, paired within three hours
    for left, right in zip(experiments, experiments[1:]):
        a, b = world['experiments'][left]['batches'][0], world['experiments'][right]['batches'][0]
        expected = expected_comparison(ref, 'VCD Mean', a, b, tolerance=3.0)
        if expected is None:
            continue  # two samples equally near: the reference pairing is ambiguous, so the case is not scored
        add(f'{left}-{right}:VCD Mean:aligned', ['offline samples', 'two deliveries', 'samples paired within 3 h'],
            {'dataset_ids': [world['deliveries'][(left, 'offline')]['id'], world['deliveries'][(right, 'offline')]['id']],
             'parameter': 'VCD Mean', 'batches': [a, b], 'align_tolerance_h': 3.0}, expected)
    # the same experiment at the resolution it was recorded: more than a direct task accepts
    a, b = world['experiments']['EXP001']['batches']
    for parameter in ('pH', 'Temperature', 'Dissolved O2'):
        add(f'EXP001:{parameter}:every-minute', ['process data every minute', 'over the direct-task size limit'],
            {'dataset_ids': [world['deliveries'][('EXP001', 'inline_full')]['id']], 'parameter': parameter, 'batches': [a, b]},
            expected_comparison(full, parameter, a, b))
    return out


# --- analyst questions (CHO) ----------------------------------------------------------------------------------------
def analyst_cases(world) -> list[Case]:
    out = []
    series_of = lambda response: (response['result']['data'].get('series') or [None])[0] if response['ok'] else None

    def score(case, response):
        bad = refused(response['raw'])
        if bad:
            return bad
        stated, expected = response['stated'], case.reference['value']
        if stated is None:
            return 'not_supported', case.reference['missing']
        same = stated == expected if isinstance(expected, str) else close(stated, expected)
        return ('correct', '') if same else ('wrong_value', f'states {stated}, reference {expected}')

    def add(kind, ident, request, pick, value, missing, tags=()):
        def run(case, w, request=request, pick=pick):
            raw = call(w, request)
            return {'raw': raw, 'stated': pick(raw) if raw['ok'] else None}
        out.append(Case(f'ask:{kind}:{ident}', 'analyst_questions', 'cho', (kind, *tags), request, {'value': value, 'missing': missing}, run, score))

    for exp in sorted(world['experiments']):
        a, b = world['experiments'][exp]['batches']
        delivery = world['deliveries'][(exp, 'offline')]['id']
        for parameter in ('Glucose', 'VCD Mean'):
            points = world['reference'].get((a, parameter), {})
            other = world['reference'].get((b, parameter), {})
            if len(points) < 6:
                continue
            times = sorted(points)
            base = {'operation': 'reconcile', 'dataset_ids': [delivery], 'parameter': parameter, 'batches': [a]}
            ident = f'{a}:{parameter}'
            mid = times[len(times) // 2]
            add('value at a time', ident, {**base, 'time_from_h': mid, 'time_to_h': mid},
                lambda r: (series_of(r) or {}).get('points', [[None, None]])[0][1] if series_of(r) and series_of(r)['n'] == 1 else None,
                points[mid], 'the value at one sample time')
            add('number of samples', ident, base, lambda r: (series_of(r) or {}).get('n'), len(times), 'the number of samples')
            peak = max(points.values())
            add('highest value', ident, base, lambda r: (series_of(r) or {}).get('max'), peak, 'the highest value')
            add('when the highest value occurred', ident, base, lambda r: (series_of(r) or {}).get('max_at_h'),
                min(t for t in times if points[t] == peak), 'when the highest value occurred')
            lo, hi = times[len(times) // 4], times[3 * len(times) // 4]
            inside = [points[t] for t in times if lo <= t <= hi]
            add('average over a window', ident, {**base, 'time_from_h': lo, 'time_to_h': hi}, lambda r: (series_of(r) or {}).get('mean'),
                sum(inside) / len(inside), 'the average of the values in a time window')
            threshold = (min(points.values()) + peak) / 2
            falling = parameter == 'Glucose'
            crossed = next((t for t in times if (points[t] < threshold if falling else points[t] > threshold)), None)
            add('when a threshold was crossed', ident, base,
                lambda r: ((r['result']['data'].get('threshold_crossings') or [{}])[0].get('time_h') if r['ok'] else None),
                crossed, 'when a value first crossed a threshold (no way to give one)')
            add('change over the run', ident, base, lambda r: (series_of(r) or {}).get('change'),
                points[times[-1]] - points[times[0]], 'the change between two times of one run')
            shared = sorted(set(points) & set(other))
            if shared:
                t = shared[len(shared) // 2]
                add('difference between runs at a time', ident,
                    {'operation': 'compare', 'dataset_ids': [delivery], 'parameter': parameter, 'batches': [a, b], 'time_from_h': t, 'time_to_h': t},
                    lambda r: ((r['result']['data'].get('comparison_summary') or [{}])[0].get('largest_difference') or {}).get('difference') if r['ok'] else None,
                    other[t] - points[t], 'the difference between two runs at one time')
            if other:
                add('which run peaked higher', ident, {**base, 'batches': [a, b]},
                    lambda r: ((r['result']['data'].get('ranking') or [{}])[0].get('batch') if r['ok'] else None),
                    a if peak >= max(other.values()) else b, 'which run had the higher peak')
    return out


# --- fair comparison and gaps (tablet) --------------------------------------------------------------------------------
def fair_comparison_cases(world, pairs: int = 150, seed: int = 417) -> list[Case]:
    rng, names, out = random.Random(seed), sorted(world['batches']), []
    parameter = split_header(TABLET_WITH_UNITS[0])[0]
    delivery = world['deliveries']['with_units']['id']
    wanted = {'same product and size': [], 'different product, same size': [], 'different size': []}
    while any(len(v) < pairs // 3 for v in wanted.values()):
        a, b = rng.sample(names, 2)
        x, y = world['batches'][a], world['batches'][b]
        if (a, parameter) not in world['values'] or (b, parameter) not in world['values']:
            continue
        kind = ('different size' if x['size'] != y['size'] else
                'same product and size' if (x['code'], x['strength']) == (y['code'], y['strength']) else 'different product, same size')
        if len(wanted[kind]) < pairs // 3:
            wanted[kind].append((a, b))

    def score(case, response):
        bad = refused(response)
        if bad:
            return bad
        data, expected = response['result']['data'], case.reference
        cohort, summary = data.get('cohort') or {}, (data.get('comparison_summary') or [None])[0]
        if summary is None:
            return 'abstained_unnecessarily', (response['result']['issues'][0]['message'] if response['result']['issues'] else 'no comparison')
        if not close(summary['largest_difference']['difference'], expected['difference']):
            return 'wrong_value', 'the difference between the two batches differs from the reference'
        found = sorted(cohort.get('differs') or [])
        if found != expected['differs']:
            missed = sorted(set(expected['differs']) - set(found))
            return ('missed', f"did not report a difference in {', '.join(missed).lower()}") if missed else \
                   ('false_alarm', f"reported a difference in {', '.join(sorted(set(found) - set(expected['differs']))).lower()} that the records do not show")
        if cohort.get('verdict') == 'same_context':
            return 'wrong_value', 'called the context the same although process version, equipment and stage are not recorded'
        flagged = 'cohort_differs' in [i['code'] for i in response['result']['issues']]
        if flagged != bool(expected['differs']):
            return ('missed', 'the difference in context is not raised as something to check') if expected['differs'] else \
                   ('false_alarm', 'raised a context difference that the records do not show')
        return 'correct', ''

    for kind, items in wanted.items():
        for a, b in items:
            x, y = world['batches'][a], world['batches'][b]
            differs = sorted((['Product'] if (x['code'], x['strength']) != (y['code'], y['strength']) else [])
                             + (['Scale'] if x['size'] != y['size'] else []))
            out.append(Case(f'context:{a}:{b}', 'fair_comparison', 'tablet', (kind,),
                            {'operation': 'compare', 'dataset_ids': [delivery], 'parameter': parameter, 'batches': [a, b]},
                            {'differs': differs, 'difference': world['values'][(b, parameter)] - world['values'][(a, parameter)]},
                            lambda case, w: call(w, case.request), score))
    return out


def gap_cases(world, chunk: int = 15, extra: int = 15, seed: int = 417) -> list[Case]:
    rng, names, out = random.Random(seed), sorted(world['batches']), []
    with_units = [split_header(c)[0] for c in TABLET_WITH_UNITS]
    chunks = [names[i:i + chunk] for i in range(0, len(names), chunk)]
    truly_missing = {b for parameter in TABLET_NO_UNITS for b in world['missing'].get(parameter, ())}

    def score(case, response):
        bad = refused(response)
        if bad:
            return bad
        data = response['result']['data']
        found = {(g.get('batch'), g.get('parameter'), g['status']) for g in data.get('gaps') or []}
        if data.get('gaps_truncated'):
            return 'false_alarm', f"reported {data['gap_count']} missing results, more than can be listed; the reference has {len(case.reference)}"
        extra_found, not_found = found - case.reference, case.reference - found
        if extra_found:
            statuses = sorted({s for _, _, s in extra_found})
            return 'false_alarm', f"reported {len(extra_found)} results as {' / '.join(statuses).replace('_', ' ')} that are present in the delivery"
        if not_found:
            return 'missed', f'{len(not_found)} missing results were not reported'
        return 'correct', ''

    def add(kind, batches, delivery, parameters, absent, tags):
        reference = {(None, p, 'unavailable') for p in absent}
        reference |= {(b, p, 'required_missing') for p in parameters for b in batches if b in world['missing'].get(p, ())}
        out.append(Case(f'gaps:{kind}:{batches[0]}', 'gaps', 'tablet', tuple(tags),
                        {'operation': 'check_gaps', 'dataset_ids': [world['deliveries'][delivery]['id']], 'batches': batches},
                        reference, lambda case, w: call(w, case.request), score))

    with_missing = [c for c in chunks if truly_missing & set(c)]
    without = rng.sample([c for c in chunks if not truly_missing & set(c)], extra)
    for batches in with_missing:
        add('no-units', batches, 'no_units', TABLET_NO_UNITS, with_units, ['results without a stated unit', 'a result is really missing'])
    for batches in without:
        add('no-units', batches, 'no_units', TABLET_NO_UNITS, with_units, ['results without a stated unit', 'nothing is missing'])
    for batches in rng.sample(chunks, extra):
        add('units', batches, 'with_units', with_units, TABLET_NO_UNITS, ['results with a stated unit', 'nothing is missing'])
    return out


# --- lot tracing (tablet) ------------------------------------------------------------------------------------------------
def trace_usage_cases(world, api_lots: int = 60, seed: int = 417) -> list[Case]:
    rng, out = random.Random(seed), []
    lots = sorted(world['usage'])
    chosen = [lot for lot in lots if not lot.startswith('API-')] + rng.sample([lot for lot in lots if lot.startswith('API-')], api_lots)

    def score(case, response):
        bad = refused(response)
        if bad:
            return bad
        data = response['result']['data']
        found, expected = set(data.get('affected_batches') or []), case.reference
        if found - expected:
            return 'false_alarm', f'{len(found - expected)} batches returned that are not recorded as using the lot'
        if expected - found:
            return 'missed', f'{len(expected - found)} of {len(expected)} batches recorded as using the lot were not returned'
        if (data.get('genealogy') or {}).get('complete') is not False:
            return 'wrong_value', 'the genealogy is reported complete although some batches have no usage record'
        if data.get('exposure_confirmed') is not False or any(u.get('basis') != 'recorded_usage' for u in data.get('recorded_usage') or []):
            return 'false_alarm', 'usage is presented as confirmed exposure'
        return 'correct', ''

    for lot in chosen:
        n = len(world['usage'][lot])
        size = 'used in over 100 batches' if n > 100 else 'used in 11 to 100 batches' if n > 10 else 'used in 10 batches or fewer'
        out.append(Case(f'trace:{lot}', 'trace_usage', 'tablet', (lot.split('-')[0].lower() + ' lot', size),
                        {'operation': 'trace_impact', 'record_id': lot}, set(world['usage'][lot]), lambda case, w: call(w, case.request), score))
    return out


# --- lot numbers in free text (FDA recalls) ---------------------------------------------------------------------------------
def recall_cases(world) -> list[Case]:
    out = []

    def score_find(case, response):
        bad = refused(response)
        if bad:
            return bad
        found = {r['id'] for r in response['result']['data'].get('records') or []}
        missing = set(case.reference) - found
        return ('correct', '') if not missing else ('missed', f'{len(missing)} of {len(case.reference)} reports naming the lot were not returned')

    def score_trace(case, response):
        bad = refused(response)
        if bad:
            return bad
        data = response['result']['data']
        found = {r['id'] for r in data.get('records') or []}
        if data.get('affected_batches') or data.get('exposure_confirmed') is not False:
            return 'false_alarm', 'a mention in a report was presented as recorded usage'
        missing = set(case.reference) - found
        return ('correct', '') if not missing else ('missed', 'the lot number, as written in the report, is not recognised as an identifier')

    for lot in world['queries']:
        tags = (lot_format(lot), 'named in several reports' if len(world['reference'][lot]) > 1 else 'named in one report')
        out.append(Case(f'find:{lot}', 'find_identifier', 'fda_drug_recalls', tags,
                        {'operation': 'find_records', 'query': lot, 'kinds': ['evidence']}, world['reference'][lot],
                        lambda case, w: call(w, case.request), score_find))
        out.append(Case(f'link:{lot}', 'trace_mention', 'fda_drug_recalls', tags,
                        {'operation': 'trace_impact', 'record_id': lot}, world['reference'][lot],
                        lambda case, w: call(w, case.request), score_trace))
    return out


def timed(case, world):
    started = time.perf_counter()
    response = case.run(case, world)
    return response, time.perf_counter() - started
