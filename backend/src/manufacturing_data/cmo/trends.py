"""Accepted values across every delivery, shaped for charts and export.

Pure functions over stored runs: no model call, no new store. A batch is identified
by the delivery it arrived in, so the same batch ID in two deliveries stays two series
and every point keeps the ID of the measurement (and so the source cell) it came from.
"""
from __future__ import annotations

import json
from datetime import datetime
from statistics import fmean

ACCEPTED = {'auto_accepted', 'accepted', 'corrected'}
# Points returned per batch for one chart. The summary is always computed from every value.
POINT_LIMIT = 2000
LAYOUTS = {'long', 'wide', 'summary'}


def _stamp(value):
    try:
        return float(str(value).replace(',', '.')), None
    except (TypeError, ValueError):
        pass
    try:
        return None, datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None, None


def batches(runs):
    """One entry per batch per current, completed delivery, oldest delivery first.

    Time is hours as recorded; a batch recorded with timestamps is placed on hours since
    its own first reading, and says so, so both kinds can share an axis."""
    result = []
    current = [r for r in runs if r.get('status') == 'complete' and not r.get('superseded_by')]
    for run in sorted(current, key=lambda r: (r.get('completed_at') or r.get('started_at') or '', r['id'])):
        grouped = {}
        for m in run.get('measurements') or []:
            if m.get('status') in ACCEPTED and isinstance(m.get('value'), (int, float)) and not isinstance(m.get('value'), bool):
                grouped.setdefault(m.get('batch') or '', []).append(m)
        for batch, items in sorted(grouped.items()):
            stamps = [_stamp(m.get('time')) for m in items]
            dated = [s[1] for s in stamps if s[1] is not None]
            origin = None
            if dated:
                # Naive and zone-aware timestamps cannot be subtracted; compare each kind with its own first reading.
                aware = [d for d in dated if d.tzinfo is not None]
                naive = [d for d in dated if d.tzinfo is None]
                origin = (min(aware) if aware else None, min(naive) if naive else None)
            rows = []
            for m, (number, moment) in zip(items, stamps):
                if number is None and moment is not None:
                    start = origin[0] if moment.tzinfo is not None else origin[1]
                    number = (moment - start).total_seconds() / 3600
                rows.append({'measurement': m, 'time_h': number})
            result.append({'key': f"{run['id']}:{batch}", 'batch': batch, 'run_id': run['id'], 'cmo': run.get('cmo'),
                           'delivery_name': run.get('delivery_name'), 'completed_at': run.get('completed_at'),
                           'delivery_verified': bool((run.get('summary') or {}).get('verified_package')),
                           'time_basis': 'hours_since_first_reading' if dated else 'recorded_hours', 'rows': rows, 'run': run})
    return result


def _public(entry):
    return {k: entry[k] for k in ('key', 'batch', 'run_id', 'cmo', 'delivery_name', 'completed_at', 'delivery_verified', 'time_basis')}


def catalogue(entries):
    """What can be plotted: every parameter with how many batches and values carry it."""
    parameters = {}
    for entry in entries:
        seen = set()
        for row in entry['rows']:
            m = row['measurement']
            item = parameters.setdefault(m['parameter'], {'id': m['parameter'], 'units': [], 'batches': 0, 'values': 0})
            item['values'] += 1
            if m.get('unit') not in item['units']: item['units'].append(m.get('unit'))
            if m['parameter'] not in seen:
                seen.add(m['parameter']); item['batches'] += 1
    return {'parameters': sorted(parameters.values(), key=lambda p: p['id']), 'batches': [_public(e) for e in entries],
            'deliveries': len({e['run_id'] for e in entries})}


def _summary(rows):
    ordered = sorted(rows, key=lambda r: (r['time_h'] is None, r['time_h'] or 0.0))
    values = [r['measurement']['value'] for r in ordered]
    low, high = min(ordered, key=lambda r: r['measurement']['value']), max(ordered, key=lambda r: r['measurement']['value'])
    point = lambda r: {'time_h': r['time_h'], 'value': r['measurement']['value'], 'id': r['measurement']['id']}
    return ordered, {'n': len(values), 'mean': fmean(values), 'min': point(low), 'max': point(high),
                     'first': point(ordered[0]), 'last': point(ordered[-1])}


def series(entries, parameter):
    """Every batch that carries ``parameter``: its points in time order and the figures a cross-batch chart needs."""
    result = []
    for entry in entries:
        rows = [r for r in entry['rows'] if r['measurement']['parameter'] == parameter]
        if not rows: continue
        ordered, summary = _summary(rows)
        timed = [r for r in ordered if r['time_h'] is not None]
        step = -(-len(timed) // POINT_LIMIT) if len(timed) > POINT_LIMIT else 1
        shown = timed[::step]
        if step > 1 and shown[-1] is not timed[-1]: shown.append(timed[-1])
        result.append({**_public(entry), 'unit': rows[0]['measurement'].get('unit'), 'summary': summary,
                       'points': [[r['time_h'], r['measurement']['value'], r['measurement']['id']] for r in shown],
                       'points_total': len(ordered), 'points_without_time': len(ordered) - len(timed), 'sampled_every': step})
    return result


def _source(source):
    source = source or {}
    if source.get('sheet') and source.get('cell'): return f"{source.get('path')} · {source['sheet']}!{source['cell']}"
    if source.get('row'): return f"{source.get('path')} · row {source['row']}" + (f" · {source['column']}" if source.get('column') else '')
    if source.get('page'): return f"{source.get('path')} · page {source['page']}"
    return str(source.get('path', ''))


def select(entries, *, parameters=None, keys=None):
    """Narrow to the chosen batches and parameters; an unknown choice is an error, never an empty file."""
    known_keys = {e['key'] for e in entries}
    known_parameters = {r['measurement']['parameter'] for e in entries for r in e['rows']}
    if keys is not None and (missing := sorted(set(keys) - known_keys)): raise ValueError(f'Unknown batch: {missing[0]}')
    if parameters is not None and (missing := sorted(set(parameters) - known_parameters)): raise ValueError(f'Unknown parameter: {missing[0]}')
    chosen = []
    for entry in entries:
        if keys is not None and entry['key'] not in keys: continue
        rows = [r for r in entry['rows'] if parameters is None or r['measurement']['parameter'] in parameters]
        if rows: chosen.append({**entry, 'rows': rows})
    return chosen


def export_rows(entries, layout='long'):
    """Rows for a file. ``long``: one value per row with its source. ``wide``: one row per batch and time,
    one column per parameter. ``summary``: one row per batch and parameter."""
    if layout not in LAYOUTS: raise ValueError('Unsupported export layout')
    rows = []
    for entry in entries:
        lead = {'batch': entry['batch'], 'delivery': entry['delivery_name'] or entry['run_id'], 'cdmo': entry['cmo'],
                'delivery_verified': entry['delivery_verified']}
        if layout == 'summary':
            by_parameter = {}
            for r in entry['rows']: by_parameter.setdefault(r['measurement']['parameter'], []).append(r)
            for name, items in sorted(by_parameter.items()):
                _ordered, s = _summary(items)
                rows.append({**lead, 'parameter': name, 'unit': items[0]['measurement'].get('unit'), 'readings': s['n'],
                             'first': s['first']['value'], 'last': s['last']['value'], 'minimum': s['min']['value'],
                             'minimum_at_h': s['min']['time_h'], 'maximum': s['max']['value'], 'maximum_at_h': s['max']['time_h'],
                             'mean': s['mean'], 'time_basis': entry['time_basis'], 'run_id': entry['run_id']})
            continue
        ordered = sorted(entry['rows'], key=lambda r: (r['time_h'] is None, r['time_h'] or 0.0, r['measurement']['parameter']))
        if layout == 'long':
            for r in ordered:
                m = r['measurement']
                rows.append({**lead, 'time': m.get('time'), 'time_h': r['time_h'], 'time_basis': entry['time_basis'],
                             'parameter': m['parameter'], 'value': m['value'], 'unit': m.get('unit'), 'value_as_printed': m.get('value_raw'),
                             'unit_as_printed': m.get('unit_raw'), 'status': m.get('status'), 'source': _source(m.get('source')),
                             'source_reference': json.dumps(m.get('source'), sort_keys=True), 'source_sha256': m.get('source_sha256'),
                             'measurement_id': m['id'], 'run_id': entry['run_id']})
            continue
        groups = {}
        for r in ordered:
            m = r['measurement']; name = m['parameter']
            group = groups.setdefault(m.get('time'), {**lead, 'time': m.get('time'), 'time_h': r['time_h'], 'time_basis': entry['time_basis']})
            if name in group and group[name] != m['value']:
                raise ValueError(f"Batch {entry['batch']} has two accepted {name} values at time {m.get('time')}; "
                                 'use the one-value-per-row layout, which keeps both with their sources')
            group[name] = m['value']; group[name + '_unit'] = m.get('unit')
        rows.extend({**g, 'run_id': entry['run_id']} for g in groups.values())
    return rows
