"""Three skills from one real plant: catching a deviation, pointing at a change, and ranking possible causes.

Batch distillation plant, RPTU Kaiserslautern-Landau (Zenodo 10.5281/zenodo.17395544, CC BY 4.0): 119 runs, 82 with
faults that the operators induced on purpose and then labelled: when each anomaly began and ended, which sensor showed
it, what was done to cause it, and when that began. Not pharmaceutical, and the faults are induced, but the labels
are real and the plant is real.

How the dataset is put to the product:
- **Deviation detection.** The product raises a signal when a value leaves an approved range, or trends toward it.
  The dataset has no ranges, so the range of each sensor is taken from a run of the same operating point that the
  operators labelled normal. The anomalous run is then replayed through the product's own check, value by value.
- **Pointing at the change.** The Trends page lists the largest changes in a series. Does one of them fall inside
  the labelled anomaly?
- **Ranking causes.** Each anomaly becomes a record, alongside the operator log of that run and a note of what was
  actually done to the plant. "Suggest causes to check" is asked about the anomaly. The true cause is known.

The dataset records time of day only; a fixed date is attached so records can be ordered.
"""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import datasets, worlds
from .core import Case, Skill

ROOT = datasets.CACHE / 'distillation' / 'tables'
DATE = '2022-10-01'
STEP = 10          # replay every tenth second: the plant records every second
GRACE_BEFORE, GRACE_AFTER = 30, 60  # seconds either side of a labelled window that still count as the anomaly
WIDTHS = {'limits: range of one normal run': 0.0, 'limits: that range widened by half': 0.5}

SKILLS = {s.id: s for s in (
    Skill('detect_deviation', 'Catch a deviation', 'Replaying a real run with a labelled anomaly through the product\'s own check, '
          'is a signal raised during the anomaly, and not before it?', 'deviation signals: specification limits and trend rules',
          ('distillation',)),
    Skill('point_at_change', 'Point at the change', 'Of the largest changes the Trends page lists for a series, does one fall inside the labelled anomaly, '
          'and can it say when a run is unremarkable?', 'trend standouts', ('distillation',)),
    Skill('rank_causes', 'Rank possible causes', 'Asked what might have caused a labelled anomaly, is the action that actually caused it '
          'among the first candidates?', 'workspace task "suggest_causes"', ('distillation',)),
)}


def seconds(clock: str) -> int:
    h, m, s = (int(x) for x in str(clock).split(':'))
    return h * 3600 + m * 60 + s


def stamp(clock: str) -> str:
    return f'{DATE}T{clock}Z'


def family(sensor: str) -> str:
    return ('temperature sensor' if sensor.startswith('T') else 'flow sensor' if sensor.startswith('F') else
            'pressure sensor' if sensor.startswith('P') else 'level sensor')


def load() -> list[dict[str, Any]]:
    """Every run: its operating point, whether the operators labelled it normal, its anomalies, and its file paths."""
    import yaml
    runs = []
    for meta in sorted((ROOT / '00_Timeseries_Label_Anomaly_Metadata').rglob('*.yaml')):
        relative = meta.relative_to(ROOT / '00_Timeseries_Label_Anomaly_Metadata' / 'Operation')
        mixture, point = relative.parts[0], relative.parts[1]
        normal = meta.name.startswith('train_normal')
        number = meta.stem.rsplit('_', 1)[-1]
        run_id = f"OP{point.rsplit('_', 1)[-1]}-{'N' if normal else 'A'}{number}"
        anomalies: dict[str, dict[str, Any]] = {}
        for entry in (yaml.safe_load(meta.read_text()) or {}).get('anomalies') or []:
            ident = entry.get('id')
            if not ident or entry.get('hasBeginning') in (None, '00:00:00'):
                continue
            begins = entry['hasBeginning'] if isinstance(entry['hasBeginning'], list) else [entry['hasBeginning']]
            ends = entry['hasEnd'] if isinstance(entry['hasEnd'], list) else [entry['hasEnd']]
            item = anomalies.setdefault(ident, {
                'id': ident, 'confirmed': entry.get('class') == 'ConfirmedAnomaly', 'category': entry.get('hasCategory'),
                'windows': [(seconds(b), seconds(e)) for b, e in zip(begins, ends) if b and e], 'first': min(begins),
                'cause': entry.get('Perturbation'), 'mode': (entry.get('PerturbationMode') or {}).get('label'),
                'cause_began': (entry.get('PerturbationMode') or {}).get('hasBeginning'), 'observations': []})
            observation = (entry.get('wasOriginatedBy') or {}).get('Observation') or {}
            sensor = ((observation.get('madeBySensor') or {}).get('Sensor') or {}).get('id')
            if sensor:
                item['observations'].append({'sensor': sensor, 'label': observation.get('label')})
        log = ROOT / '07_Tabular_Operation_Logs' / relative.with_suffix('.csv').relative_to(Path('Operation')) \
            if relative.parts[0] == 'Operation' else ROOT / '07_Tabular_Operation_Logs' / relative.with_suffix('.csv')
        runs.append({'run_id': run_id, 'mixture': mixture, 'point': point, 'normal': normal, 'anomalies': list(anomalies.values()),
                     'sensors': ROOT / '01_Timeseries_Sensors' / 'Operation' / relative.with_suffix('.csv'), 'log': log})
    return runs


def series(path: Path, step: int = STEP) -> dict[str, list[tuple[int, float]]]:
    out: dict[str, list[tuple[int, float]]] = defaultdict(list)
    with path.open(encoding='utf-8-sig') as stream:
        for n, row in enumerate(csv.DictReader(stream)):
            if n % step:
                continue
            t = seconds(row['Time'])
            for name, value in row.items():
                if name != 'Time' and value not in ('', None):
                    try:
                        out[name].append((t, float(value)))
                    except ValueError:
                        continue
    return out


def world() -> dict[str, Any]:
    runs = load()
    by_point: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for run in runs:
        by_point[(run['mixture'], run['point'])].append(run)
    # --- one small application per operating point, holding the normal range of each sensor as a specification ---
    points = {}
    for key, members in by_point.items():
        normal = [r for r in members if r['normal'] and r['sensors'].exists()]
        anomalous = [r for r in members if not r['normal'] and r['sensors'].exists()]
        if not normal or not anomalous:
            continue
        reference = series(normal[0]['sensors'])
        ranges = {s: (min(v for _, v in vs), max(v for _, v in vs)) for s, vs in reference.items()
                  if len(vs) >= 20 and min(v for _, v in vs) != max(v for _, v in vs)}
        platforms = {}
        # One run's range is a tight limit: another normal run may sit slightly outside it. So the same replay is also
        # done with the range widened by half its width on each side, to see what the answer depends on.
        for label, widen in WIDTHS.items():
            p = worlds.platform()
            ctx = worlds.person(p, 'DISTILLATION')
            for sensor, (low, high) in ranges.items():
                margin = (high - low) * widen
                p.specifications.create(ctx, site_id='DISTILLATION', parameter=sensor, low=low - margin, high=high + margin, source='manual',
                                        source_ref=f"range of {normal[0]['run_id']}, a run the operators labelled normal",
                                        reason='Added by the skill benchmark from a labelled-normal run; not a plant limit')
            platforms[label] = p
        points[key] = {'platforms': platforms, 'normal_run': normal[0]['run_id'], 'ranges': ranges,
                       'anomalous': anomalous, 'other_normal': normal[1:]}
    # --- one application holding every run's anomalies, operator log and the note of what was actually done ---
    p = worlds.platform()
    ctx = worlds.person(p, 'DISTILLATION')
    causes = []

    def record(name, when, **metadata):
        return p.evidence.ingest(ctx, source_system='distillation-plant', source_record_id=name, content=name.encode(),
                                 media_type='text/plain', site_id='DISTILLATION', event_time=stamp(when), metadata=metadata)['evidence_id']

    for run in runs:
        confirmed = [a for a in run['anomalies'] if a['confirmed'] and a['cause'] and a['cause_began'] not in (None, '00:00:00')]
        if not confirmed or not run['log'].exists():
            continue
        with run['log'].open(encoding='utf-8-sig') as stream:
            events = [r for r in csv.DictReader(stream) if r.get('Time') and r.get('Property')]
        for n, event in enumerate(events):
            record(f"{run['run_id']}:log:{n}", event['Time'], run_id=run['run_id'], note=f"{event['Property'].strip()} {event.get('Value') or ''}".strip())
        noted = {}
        for anomaly in confirmed:
            # What was done to the plant is one fact per run and time, however many anomalies it led to.
            key = (anomaly['cause'], anomaly['cause_began'])
            if key not in noted:
                noted[key] = record(f"{run['run_id']}:action:{len(noted)}", anomaly['cause_began'], run_id=run['run_id'], note=anomaly['cause'])
            if seconds(anomaly['cause_began']) > seconds(anomaly['first']):
                continue  # the dataset records the action after the anomaly began: not a case with a usable reference
            subject = record(f"{run['run_id']}:anomaly:{anomaly['id']}", anomaly['first'], run_id=run['run_id'],
                             note='; '.join(sorted({o['label'] or '' for o in anomaly['observations']})) or 'anomaly')
            causes.append({'run': run['run_id'], 'anomaly': anomaly, 'subject': subject, 'cause_record': noted[key],
                           'events_before': sum(seconds(e['Time']) <= seconds(anomaly['first']) for e in events)})
    return {'p': p, 'ctx': ctx, 'site': 'DISTILLATION', 'points': points, 'causes': causes, 'runs': runs,
            'added': 'A sensor range per operating point, taken from one run the operators labelled normal; a fixed date for '
                     'the recorded times of day. Anomalies, causes, operator logs and sensor values are the dataset\'s own.'}


# --- catch a deviation --------------------------------------------------------------------------------------------
def replay(point, width: str, run_id: str, sensor: str, values: list[tuple[int, float]]) -> dict[str, Any]:
    """The product's own check, one value at a time, as the plant would have sent them."""
    p, first, kind, signals = point['platforms'][width], None, None, 0
    for t, value in values:
        hit = p.signals.check_value(worlds.TENANT, site_id='DISTILLATION', parameter=sensor, value=value, batch_id=run_id)
        if hit is not None:
            signals += 1
            if first is None:
                first, kind = t, hit['kind']
    return {'first': first, 'kind': kind, 'values_flagged': signals, 'values': len(values)}


def score_detection(case, response):
    windows = case.reference['windows']
    first = response['first']
    if not windows:  # a run the operators labelled normal
        return ('correct', '') if first is None else (
            'false_alarm', f"{'the trend rule' if response['kind'] == 'trend' else 'a limit'} raised a signal on a run the operators labelled normal")
    start = min(a for a, _ in windows)
    rule = 'the trend rule' if response['kind'] == 'trend' else 'a limit'
    if first is None:
        return 'missed', 'no signal during the anomaly: the values stayed inside the limits'
    if first < start - GRACE_BEFORE:
        return 'false_alarm', f'{rule} raised a signal before the anomaly began'
    if any(a - GRACE_BEFORE <= first <= b + GRACE_AFTER for a, b in windows):
        return 'correct', ''
    return 'missed', 'the first signal came only after the anomaly had ended'


def detection_cases(w) -> list[Case]:
    out, loaded = [], {}
    def values(run, sensor):
        if run['run_id'] not in loaded:
            loaded.clear()                      # one run in memory at a time
            loaded[run['run_id']] = series(run['sensors'])
        return loaded[run['run_id']].get(sensor, [])
    for key, point in sorted(w['points'].items()):
        for width in WIDTHS:
            for run in point['anomalous']:
                for anomaly in run['anomalies']:
                    for sensor in sorted({o['sensor'] for o in anomaly['observations']}):
                        if sensor not in point['ranges']:
                            continue
                        tags = (width, family(sensor), 'confirmed anomaly' if anomaly['confirmed'] else 'unconfirmed anomaly')
                        out.append(Case(f"detect:{run['run_id']}:{anomaly['id']}:{sensor}:{WIDTHS[width]}", 'detect_deviation', 'distillation', tags,
                                        {'run': run['run_id'], 'sensor': sensor}, {'windows': anomaly['windows']},
                                        lambda case, _w, point=point, run=run, sensor=sensor, width=width:
                                            replay(point, width, f"{run['run_id']}:{case.id}", sensor, values(run, sensor)),
                                        score_detection))
            for run in point['other_normal']:
                for sensor in ('PY23', 'T702', 'FT703'):
                    if sensor in point['ranges']:
                        out.append(Case(f"detect:{run['run_id']}:normal:{sensor}:{WIDTHS[width]}", 'detect_deviation', 'distillation',
                                        (width, family(sensor), 'run labelled normal'), {'run': run['run_id'], 'sensor': sensor}, {'windows': []},
                                        lambda case, _w, point=point, run=run, sensor=sensor, width=width:
                                            replay(point, width, f"{run['run_id']}:{case.id}", sensor, values(run, sensor)),
                                        score_detection))
    return out


# --- point at the change ---------------------------------------------------------------------------------------------
def change_cases(w) -> list[Case]:
    from src.manufacturing_data.cmo import trends
    out = []

    def run_standouts(case, _w, run, sensor):
        points = [(t / 3600, v) for t, v in series(run['sensors']).get(sensor, [])]
        found = trends.standouts({run['run_id']: points}, top=3)
        return {'changes': found.get('largest_changes_between_consecutive_samples', []),
                'says_unremarkable': bool(found.get('nothing_stands_out'))}

    def score(case, response):
        windows = case.reference['windows']
        if not windows:
            return ('correct', '') if response['says_unremarkable'] else \
                   ('not_supported', 'it always lists the largest changes; it cannot say that a run is unremarkable')
        inside = [c for c in response['changes']
                  if any(a - GRACE_BEFORE <= c['to_h'] * 3600 <= b + GRACE_AFTER for a, b in windows)]
        return ('correct', '') if inside else ('missed', 'none of the three largest changes falls inside the labelled anomaly')

    for run in w['runs']:
        if not run['sensors'].exists():
            continue
        if run['normal']:
            out.append(Case(f"change:{run['run_id']}:normal", 'point_at_change', 'distillation', ('run labelled normal',),
                            {'run': run['run_id'], 'sensor': 'PY23'}, {'windows': []},
                            lambda case, _w, run=run: run_standouts(case, _w, run, 'PY23'), score))
            continue
        for anomaly in run['anomalies']:
            for sensor in sorted({o['sensor'] for o in anomaly['observations']}):
                tags = (family(sensor), 'confirmed anomaly' if anomaly['confirmed'] else 'unconfirmed anomaly',
                        f"{anomaly['category'] or 'uncategorised'} anomaly")
                out.append(Case(f"change:{run['run_id']}:{anomaly['id']}:{sensor}", 'point_at_change', 'distillation', tags,
                                {'run': run['run_id'], 'sensor': sensor}, {'windows': anomaly['windows']},
                                lambda case, _w, run=run, sensor=sensor: run_standouts(case, _w, run, sensor), score))
    return out


# --- rank possible causes ---------------------------------------------------------------------------------------------
def cause_cases(w) -> list[Case]:
    from .skills import call, refused
    out = []

    def score(case, response):
        bad = refused(response)
        if bad:
            return bad
        data = response['result']['data']
        if data.get('causal_claim_supported') is not False:
            return 'false_alarm', 'a cause was stated as established'
        factors = {f['id']: f['record']['id'] for f in data.get('chronology') or []}
        hypotheses = [factors.get(h.get('factor_id')) for h in data.get('hypotheses') or [] if h.get('kind') == 'hypothesis']
        truth = case.reference['cause_record']
        if truth not in factors.values():
            return 'missed', 'the action that caused the anomaly is not among the linked records'
        if truth not in hypotheses:
            return 'missed', 'the action that caused the anomaly was linked but set aside'
        position = hypotheses.index(truth) + 1
        if position <= 3:
            return 'correct', ''
        return 'wrong_value', 'the true cause is listed, but not among the first three: candidates are in time order, with nothing to rank them'

    for item in w['causes']:
        n = item['events_before']
        tags = (item['anomaly']['mode'] or 'cause not categorised',
                'over 30 earlier events in the log' if n > 30 else '11 to 30 earlier events in the log' if n > 10 else '10 or fewer earlier events in the log')
        request = {'operation': 'suggest_causes', 'record_id': item['subject'], 'record_kind': 'evidence', 'limit': 100}
        out.append(Case(f"cause:{item['run']}:{item['anomaly']['id']}", 'rank_causes', 'distillation', tags, request,
                        {'cause_record': item['cause_record'], 'cause': item['anomaly']['cause']},
                        lambda case, _w: call(_w, case.request), score))
    return out


def position_summary(rows, w) -> dict[str, Any]:
    """Where the true cause sits in the product's list, across all cases: the figure behind the outcomes."""
    from .skills import call
    positions, sizes, nearest = [], [], []
    for item in w['causes']:
        response = call(w, {'operation': 'suggest_causes', 'record_id': item['subject'], 'record_kind': 'evidence', 'limit': 100})
        if not response['ok']:
            continue
        data = response['result']['data']
        factors = {f['id']: f['record']['id'] for f in data.get('chronology') or []}
        hypotheses = [factors.get(h.get('factor_id')) for h in data.get('hypotheses') or [] if h.get('kind') == 'hypothesis']
        sizes.append(len(hypotheses))
        if item['cause_record'] in hypotheses:
            positions.append(hypotheses.index(item['cause_record']) + 1)
            # The same candidates, latest before the anomaly first: where the true cause would then sit.
            nearest.append(len(hypotheses) - hypotheses.index(item['cause_record']))
    return {'cases': len(sizes), 'true_cause_listed': len(positions),
            'median_position_of_true_cause': statistics.median(positions) if positions else None,
            'median_candidates_listed': statistics.median(sizes) if sizes else None,
            'listed_first': sum(p == 1 for p in positions), 'listed_in_first_three': sum(p <= 3 for p in positions),
            'if_ordered_latest_before_the_anomaly_first': {
                'median_position': statistics.median(nearest) if nearest else None,
                'in_first_three': sum(p <= 3 for p in nearest), 'first': sum(p == 1 for p in nearest),
                'note': 'Not something the product does. It shows how far ordering by closeness in time alone would go.'}}


def limits_alone(w) -> dict[str, Any]:
    """What the same limits would do with no trend rule, worked out here from the values: not something the product
    offers as a setting. It separates two questions the product's result mixes: are the limits any use, and does the
    trend rule help or hurt on a process that is still moving?"""
    out = {}
    for width, widen in WIDTHS.items():
        counts = {'correct': 0, 'missed': 0, 'false_alarm': 0}
        for point in w['points'].values():
            for run in point['anomalous']:
                values = series(run['sensors'])
                for anomaly in run['anomalies']:
                    for sensor in sorted({o['sensor'] for o in anomaly['observations']}):
                        if sensor not in point['ranges']:
                            continue
                        low, high = point['ranges'][sensor]
                        margin = (high - low) * widen
                        first = next((t for t, v in values.get(sensor, []) if v < low - margin or v > high + margin), None)
                        outcome, _ = score_detection(None, {'first': first, 'kind': 'spec_excursion'}) if False else (
                            ('missed', '') if first is None else
                            ('false_alarm', '') if first < min(a for a, _ in anomaly['windows']) - GRACE_BEFORE else
                            ('correct', '') if any(a - GRACE_BEFORE <= first <= b + GRACE_AFTER for a, b in anomaly['windows']) else ('missed', ''))
                        counts[outcome] += 1
        out[width] = counts
    return out
