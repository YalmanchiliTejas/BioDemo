"""Prepared data and context that direct work reads instead of recomputing.

- A delivery profile is calculated once per delivery revision (DuckDB over every row) and saved as a derived record:
  what is in the delivery, per batch and parameter, before anyone asks. It is made when a delivery is published or
  shared, and on first use otherwise.
- Statistics and bounded time alignment for comparisons (Polars).
- The context a comparison needs to be fair: product, process version, equipment, scale and stage of each batch,
  read from the batch records. Missing context is reported as not recorded, never assumed equal.
- Approved requirements (active specifications) that a delivery is checked against for gaps.
- Recorded usage of lots and equipment by batch, from executed procedure steps: what was actually used, as
  distinct from a record that merely mentions an identifier.

Nothing here calls a model or writes to a manufacturing system.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from ..manufacturing_data.knowledge import canonical
from .evidence import EvidenceRef
from .ids import content_hash

PROFILE_KIND = 'workspace_prepared_delivery'
PROFILE_VERSION = 'delivery-profile-1'
COHORT_ATTRIBUTES = (('product', 'Product'), ('process_version', 'Process version'), ('equipment_id', 'Equipment'),
                     ('scale', 'Scale'), ('process_stage', 'Process stage'))


def _number(value) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def build_profile(payload: dict[str, Any]) -> dict[str, Any]:
    """Per-batch, per-parameter figures over every row of one delivery."""
    import duckdb
    import polars as pl

    rows = [{'batch': str(m.get('batch') or ''), 'parameter': str(m.get('parameter') or ''), 'unit': str(m.get('unit') or ''),
             'time_h': _number(m.get('time')), 'value': _number(m.get('value')), 'status': str(m.get('status') or 'accepted')}
            for m in payload.get('measurements', [])]
    frame = pl.DataFrame(rows, schema={'batch': pl.Utf8, 'parameter': pl.Utf8, 'unit': pl.Utf8, 'time_h': pl.Float64,
                                       'value': pl.Float64, 'status': pl.Utf8})
    con = duckdb.connect()
    try:
        con.register('m', frame.to_arrow())
        usable = "batch <> '' and parameter <> '' and value is not null and time_h is not null and status <> 'rejected'"
        series = con.execute(f"""
            select batch, parameter, min(unit), count(distinct unit), count(*), min(time_h), max(time_h), min(value), max(value),
                   avg(value), sum(case when status = 'needs_review' then 1 else 0 end)
            from m where {usable} group by batch, parameter order by batch, parameter""").fetchall()
        repeated = con.execute(f"""
            select count(*), coalesce(sum(case when distinct_values > 1 then 1 else 0 end), 0) from (
                select count(distinct value) as distinct_values from m where {usable}
                group by batch, parameter, time_h having count(*) > 1)""").fetchone()
        unusable = con.execute(f"select count(*) from m where not ({usable})").fetchone()[0]
    finally:
        con.close()
    parameters: dict[str, dict[str, Any]] = {}
    out_series = []
    for batch, parameter, unit, units, n, first, last, low, high, mean, in_review in series:
        out_series.append({'batch': batch, 'parameter': parameter, 'unit': unit, 'mixed_units': units > 1, 'n': n,
                           'first_time_h': first, 'last_time_h': last, 'min': low, 'max': high, 'mean': mean,
                           'values_in_review': int(in_review)})
        entry = parameters.setdefault(parameter, {'parameter': parameter, 'units': set(), 'batches': 0, 'values': 0})
        entry['units'].add(unit)
        entry['batches'] += 1
        entry['values'] += n
    times = [t for s in out_series for t in (s['first_time_h'], s['last_time_h'])]
    return {'profile_version': PROFILE_VERSION, 'values': sum(s['n'] for s in out_series), 'rows': len(rows),
            'rows_not_usable': int(unusable), 'batches': sorted({s['batch'] for s in out_series}),
            'parameters': [{**p, 'units': sorted(p['units'])} for _, p in sorted(parameters.items())],
            'series': out_series, 'time_range_h': [min(times), max(times)] if times else None,
            'values_in_review': sum(s['values_in_review'] for s in out_series),
            'repeated_sample_times': int(repeated[0]), 'conflicting_sample_times': int(repeated[1]),
            'basis': 'Calculated once for this revision of the delivery from every row; nothing is interpolated.'}


def prepared_profile(p, ctx, rec, payload_of) -> dict[str, Any]:
    """The saved profile of this delivery revision; calculated and saved if this revision has none yet."""
    artifact_id = 'prep_' + content_hash([rec.id, rec.revision, PROFILE_VERSION])[:28]
    existing = p.store.read().get(ctx.tenant_id, PROFILE_KIND, artifact_id)
    if existing is not None and existing.state.get('status') == 'current':
        return {**p.evidence.read_derived(ctx, PROFILE_KIND, artifact_id), 'prepared': 'reused'}
    meta = rec.state.get('metadata') or {}
    profile = {**build_profile(payload_of(rec)), 'site_id': rec.state.get('site_id'), 'delivery_id': rec.id,
               'delivery_revision': rec.revision, 'delivery_name': meta.get('delivery_name') or meta.get('cmo'),
               'verification': 'provisional' if meta.get('classification') == 'provisional_cmo_dataset' else 'verified',
               'review': meta.get('review')}
    saved = p.evidence.record_derived(ctx, PROFILE_KIND, profile, artifact_id=artifact_id,
                                      inputs=[EvidenceRef('evidence', rec.id, rec.revision, rec.state.get('site_id'))],
                                      produced_by={'method': PROFILE_VERSION, 'actor_id': ctx.actor_id})
    return {**saved, 'prepared': 'calculated'}


# --- comparison: alignment and statistics --------------------------------------------------------------------
def aligned_pairs(left: dict[float, float], right: dict[float, float], tolerance_h: float) -> list[tuple[float, float, float, float]]:
    """(left time, right time, left value, right value) for each left sample and its nearest right sample within the
    tolerance. Zero tolerance is exact matching. A right sample may serve two left samples; nothing is interpolated."""
    import polars as pl

    if not left or not right:
        return []
    a = pl.DataFrame({'time_h': sorted(left), 'left': [left[t] for t in sorted(left)]}, schema={'time_h': pl.Float64, 'left': pl.Float64})
    b = pl.DataFrame({'time_h': sorted(right), 'right': [right[t] for t in sorted(right)]}, schema={'time_h': pl.Float64, 'right': pl.Float64})
    b = b.with_columns(pl.col('time_h').alias('right_time_h'))
    joined = a.join_asof(b, on='time_h', strategy='nearest', tolerance=float(tolerance_h)).drop_nulls('right')
    return [(row['time_h'], row['right_time_h'], row['left'], row['right']) for row in joined.iter_rows(named=True)]


def difference_statistics(differences: list[float]) -> dict[str, Any]:
    """Descriptive figures of the paired differences. No significance test: samples of one run are not independent."""
    import polars as pl

    if not differences:
        return {'n': 0}
    d = pl.Series('d', differences, dtype=pl.Float64)
    return {'n': d.len(), 'mean': d.mean(), 'median': d.median(), 'standard_deviation': d.std(ddof=1) if d.len() > 1 else None,
            'min': d.min(), 'max': d.max(), 'root_mean_square': float((d ** 2).mean() ** 0.5),
            'share_positive': float((d > 0).sum()) / d.len(),
            'note': 'Descriptive only. Successive samples of one run are not independent, so no significance test is reported.'}


# --- batch records -------------------------------------------------------------------------------------------------
def site_batches(p, ctx, site_id: str) -> dict[str, Any]:
    """Batch records at this site this person can read, by the batch name people use. A record projected from an
    MES is stored under "<system>:<batch>", so the name is taken from its batch_id, then from its own id."""
    out: dict[str, Any] = {}
    for rec in p.store.read().find(ctx.tenant_id, 'batch', 'site_id', site_id):
        if p.identity.check(ctx, 'read', 'batch', rec.id, site_id=site_id):
            name = str(rec.state.get('batch_id') or rec.id.rsplit(':', 1)[-1])
            out.setdefault(name, rec)
    return out


# --- comparison: is it a fair comparison? ----------------------------------------------------------------------
def cohort_context(p, ctx, site_id: str, batches: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Product, process version, equipment, scale and stage of each batch, from the batch records this person can read.
    Returns the checks and the record references they rest on."""
    values: dict[str, dict[str, Any]] = {}
    refs = []
    records = site_batches(p, ctx, site_id)
    for batch in batches:
        rec = records.get(batch)
        if rec is None:
            values[batch] = {}
            continue
        state = {**(rec.state.get('identity_fields') or {}), **rec.state}
        values[batch] = {'product': state.get('product'), 'process_version': state.get('process_version') or state.get('recipe_id'),
                         'equipment_id': state.get('equipment_id'), 'scale': state.get('scale'),
                         'process_stage': state.get('process_stage')}
        refs.append({'kind': 'batch', 'id': rec.id, 'revision': rec.revision, 'site_id': site_id})
    attributes = []
    for key, label in COHORT_ATTRIBUTES:
        per_batch = {batch: values[batch].get(key) for batch in batches}
        known = [v for v in per_batch.values() if v not in (None, '')]
        verdict = ('not_recorded' if len(known) < len(batches) else 'same' if len({str(v) for v in known}) == 1 else 'differs')
        attributes.append({'attribute': key, 'label': label, 'values': per_batch, 'verdict': verdict})
    differs = [a['label'] for a in attributes if a['verdict'] == 'differs']
    missing = [a['label'] for a in attributes if a['verdict'] == 'not_recorded']
    return ({'attributes': attributes, 'batch_records_found': len(refs), 'batches': len(batches),
             'verdict': 'differs' if differs else 'not_established' if missing else 'same_context',
             'differs': differs, 'not_recorded': missing,
             'meaning': 'A difference between batches made under different conditions may come from those conditions. '
                        'Context that is not recorded is not assumed equal.'}, refs)


# --- gaps: what the site has approved as required ------------------------------------------------------------------
def approved_requirements(p, ctx, site_id: str) -> list[dict[str, Any]]:
    """Active approved specifications at this site: each names a parameter that is expected to be measured."""
    out = []
    for spec in p.specifications.list(ctx, site_id=site_id):
        if spec.get('status') == 'active':
            out.append({'parameter': spec['parameter'], 'parameter_key': spec['parameter_key'], 'unit': spec.get('unit'),
                        'spec_id': spec['spec_id'], 'revision': spec['revision'], 'product_id': spec.get('product_id'),
                        'equipment_id': spec.get('equipment_id'), 'approved_by': spec.get('approved_by'),
                        'source': spec.get('source_ref') or spec.get('source')})
    return out


# --- impact: what was actually used -----------------------------------------------------------------------------------
def recorded_usage(p, ctx, site_id: str) -> dict[str, Any]:
    """Lots and equipment recorded as used in executed procedure steps, by batch.

    ponytail: built per request by reading the site's step executions; keep a maintained index when a site has
    more executions than a request should scan."""
    tx = p.store.read()
    instances: dict[str, Any] = {}
    by_identifier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    batches_with_usage: set[str] = set()
    for execution in tx.list(ctx.tenant_id, 'step_execution'):
        state = execution.state
        instance_id = state.get('instance_id')
        if instance_id not in instances:
            inst = tx.get(ctx.tenant_id, 'procedure_instance', instance_id)
            readable = (inst is not None and inst.state.get('site_id') == site_id
                        and p.identity.check(ctx, 'read', 'procedure_instance', inst.id, site_id=site_id))
            instances[instance_id] = inst if readable else None
        inst = instances[instance_id]
        if inst is None:
            continue
        batch_id = (inst.state.get('context') or {}).get('batch_id')
        resources = state.get('resources') or {}
        used = ([('material lot', lot.get('lot_id')) for lot in resources.get('lots', [])]
                + [('equipment', eq.get('equipment_id')) for eq in resources.get('equipment', [])])
        for kind, identifier in used:
            if not identifier or not batch_id:
                continue
            batches_with_usage.add(batch_id)
            by_identifier[canonical(identifier)].append({
                'identifier': identifier, 'used_as': kind, 'batch_id': batch_id, 'step_id': state.get('step_id'),
                'performed_at': state.get('performed_at'), 'basis': 'recorded_usage',
                'record': {'kind': 'procedure_instance', 'id': inst.id, 'revision': inst.revision, 'site_id': site_id}})
    all_batches = set(site_batches(p, ctx, site_id))
    return {'by_identifier': by_identifier, 'batches_with_usage': batches_with_usage,
            'batches_without_usage': sorted(all_batches - batches_with_usage)}
