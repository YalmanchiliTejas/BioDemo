"""Bounded, source-backed work shared by direct UI actions, routines and the agent.

These host functions never generate code or invoke a model. Findings describe the
selected evidence; applicability, missing knowledge and causation remain explicit.
"""
from __future__ import annotations

import json
import math
import time
from collections import OrderedDict, defaultdict
from itertools import combinations
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cmo_datasets import require_dataset
from .evidence import EvidenceRef
from .ids import iso, new_id, parse_iso, utc_now
from .memory import principal
from .process_engineering.workspace import KINDS, WorkspaceTools


Operation = Literal['find_records', 'select_evidence', 'reconcile', 'compare', 'check_gaps',
                    'trace_impact', 'prepare_review', 'review_changes']


class SourceRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str = Field(min_length=1, max_length=100)
    id: str = Field(min_length=1, max_length=500)
    revision: int = Field(ge=1)
    site_id: str | None = None


class SeriesSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str = Field(min_length=1, max_length=500)
    batch: str = Field(min_length=1, max_length=300)


class TaskSpec(BaseModel):
    """Run a bounded source-backed task without model-based planning or calculation."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    operation: Operation
    site_id: str = Field(default='NF1', min_length=1, max_length=100)
    query: str = Field(default='', max_length=2000)
    kinds: list[str] = Field(default_factory=list, max_length=30)
    record_refs: list[SourceRef] = Field(default_factory=list, max_length=100)
    dataset_ids: list[str] = Field(default_factory=list, max_length=10)
    series: list[SeriesSelection] = Field(default_factory=list, max_length=30)
    batches: list[str] = Field(default_factory=list, max_length=30)
    parameter: str | None = Field(default=None, max_length=300)
    target_unit: str | None = Field(default=None, max_length=100)
    expected_parameters: list[str] = Field(default_factory=list, max_length=100)
    expected_document_kinds: list[str] = Field(default_factory=list, max_length=30)
    expected_times: list[float] = Field(default_factory=list, max_length=3000)
    process_stage: str | None = Field(default=None, max_length=300)
    effective_at: str | None = Field(default=None, max_length=100)
    record_id: str | None = Field(default=None, max_length=500)
    record_kind: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode='after')
    def series_scope(self):
        keys = [(s.dataset_id, s.batch) for s in self.series]
        if len(keys) != len(set(keys)) or any(s.dataset_id not in self.dataset_ids for s in self.series):
            raise ValueError('selected series must be unique and belong to selected datasets')
        if self.batches and any(s.batch not in self.batches for s in self.series):
            raise ValueError('selected series must belong to the selected batches')
        return self

    @field_validator('kinds')
    @classmethod
    def supported_kinds(cls, values):
        if any(k not in KINDS for k in values):
            raise ValueError('unsupported workspace record kind')
        return values

    @field_validator('effective_at')
    @classmethod
    def valid_date(cls, value):
        if value and parse_iso(value) is None:
            raise ValueError('effective_at must be an ISO timestamp')
        return value


CATALOG = [
    ('find_records', 'Find records', 'Search authorized records and source text.', False),
    ('select_evidence', 'Check applicability', 'Check batch, process stage and effective dates.', False),
    ('reconcile', 'Reconcile measurements', 'Convert units and surface conflicting or missing values.', True),
    ('compare', 'Compare batches', 'Compare observed values at matching elapsed times.', True),
    ('check_gaps', 'Check missing evidence', 'Check selected evidence against your stated expectations.', False),
    ('trace_impact', 'Trace related records', 'Find documented identifiers; distinguish mentions from exposure.', False),
    ('prepare_review', 'Prepare a review', 'Assemble current evidence and questions for review.', False),
    ('review_changes', 'Review changed evidence', 'Prepare changed source records for investigation.', False),
]
MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 100_000


def _ref(rec):
    return {'kind': rec.kind, 'id': rec.id, 'revision': rec.revision, 'site_id': rec.state.get('site_id')}


def _unique_refs(refs):
    return list({(r['kind'], r['id'], r['revision']):
                 {k: r[k] for k in ('kind', 'id', 'revision', 'site_id') if k in r} for r in refs}.values())


class WorkspaceTaskService:
    def __init__(self, platform):
        self.p = platform
        self.workspace = WorkspaceTools(platform)
        # Source bytes are immutable per revision. Authorization is checked before every cache lookup.
        self._parsed: OrderedDict[tuple, tuple[int, dict]] = OrderedDict()
        self._cache_lock = RLock()
        platform.flows.register_operator('workspace_task_compute', 'v1', self._flow_compute, parallel_safe=True)

    def _flow_compute(self, ctx, payload):
        result = self.compute(ctx, payload)
        return {'status': 'completed', 'output': result, 'issues': []}

    @staticmethod
    def catalog():
        return {'operations': [dict(id=i, title=t, description=d, requires_dataset=r) for i, t, d, r in CATALOG]}

    def _current_context(self, ctx, site_id):
        owner = self.p.identity.context_for(ctx.tenant_id, principal(ctx),
                    actor_kind='person' if ctx.delegated_from else ctx.actor_kind,
                    partner_org_id=ctx.partner_org_id)
        self.p.identity.require(owner, 'read', 'evidence', site_id=site_id)
        self.p.identity.require(ctx, 'read', 'evidence', site_id=site_id)
        return owner

    def _validate(self, ctx, refs, site_id, *, tx=None, current=True):
        owner = self._current_context(ctx, site_id)
        if not refs:
            return []
        refs = self.p.identity.validate_refs(owner, refs, tx=tx, require_current=current)
        refs = self.p.identity.validate_refs(ctx, refs, tx=tx, require_current=current)
        if any(r.get('site_id') != site_id for r in refs):
            raise PermissionError('all selected records must belong to this site')
        return refs

    def compute(self, ctx, request: TaskSpec | dict) -> dict:
        started = time.perf_counter()
        spec = request if isinstance(request, TaskSpec) else TaskSpec.model_validate(request)
        owner = self._current_context(ctx, spec.site_id)
        scope = {'site_id': spec.site_id, 'owner_id': principal(ctx)}
        refs = self._validate(ctx, [r.model_dump(exclude_none=True) for r in spec.record_refs], spec.site_id)
        issues: list[dict] = []
        data: dict[str, Any]
        if spec.operation in ('find_records', 'select_evidence'):
            if refs:
                records = [self.workspace._summary(self.p.store.read().require(ctx.tenant_id, r['kind'], r['id']), r) for r in refs]
                data = {'records': records, 'coverage': 'Only the explicitly selected records were checked.'}
            else:
                data = self.workspace.search(owner, scope, kinds=spec.kinds, query=spec.query, limit=spec.limit)
                refs.extend(data['records'])
            if spec.operation == 'select_evidence':
                self._applicability(ctx, spec, data['records'], issues)
            if data.get('truncated'):
                issues.append({'code': 'partial_search', 'message': 'Search limits were reached; narrow the query.'})
        elif spec.operation in ('reconcile', 'compare', 'check_gaps'):
            measurements, dataset_refs = self._measurements(owner, spec, issues)
            refs.extend(dataset_refs)
            observed_batches = {row['batch'] for row in measurements}
            observed_series = {(row.get('dataset_id'), row['batch']) for row in measurements}
            for selected in spec.series:
                if (selected.dataset_id, selected.batch) not in observed_series:
                    issues.append({'code': 'missing_requested_series', **selected.model_dump(),
                                   'message': 'No usable measurements for this selected delivery and batch.'})
            for batch in dict.fromkeys(spec.batches):
                if batch not in observed_batches:
                    issues.append({'code': 'missing_requested_batch', 'batch': batch,
                                   'message': 'No usable measurements for this requested batch in the selected data.'})
            if spec.parameter and not measurements:
                issues.append({'code': 'missing_requested_parameter', 'parameter': spec.parameter,
                               'message': 'No usable measurements for this requested parameter in the selected data.'})
            if spec.operation == 'reconcile' and spec.dataset_ids and not measurements and not issues:
                issues.append({'code': 'no_measurements', 'message': 'The selected data contains no usable measurements.'})
            data = {'measurements': measurements[:spec.limit], 'measurement_count': len(measurements),
                    'truncated': len(measurements) > spec.limit, 'source_measurements_modified': False,
                    'time_basis': 'elapsed hours as supplied in the verified delivery; no clock or phase alignment inferred'}
            if spec.operation == 'compare':
                data.update(self._compare(spec, measurements, issues))
            elif spec.operation == 'check_gaps':
                data.update(self._gaps(ctx, spec, measurements, refs, issues))
            elif not spec.dataset_ids:
                issues.append({'code': 'dataset_required', 'message': 'Select a verified dataset to reconcile.'})
        elif spec.operation == 'trace_impact':
            if not spec.record_id:
                data = {'records': []}
                issues.append({'code': 'record_required', 'message': 'Select a record or identifier to trace.'})
            else:
                data = self.workspace.links(owner, scope, kind=spec.record_kind, record_id=spec.record_id, limit=spec.limit)
                refs.extend(data.get('records', []))
                if data.get('target'):
                    refs.append(data['target'])
            data.update(causal_claim_supported=False, exposure_confirmed=False,
                        limitation='Shared identifiers are candidate links. Confirm material/equipment usage and time windows in the source system.')
        else:
            for dataset_id in spec.dataset_ids:
                refs.append(_ref(require_dataset(self.p, owner, dataset_id, spec.site_id)))
            if not refs and spec.query:
                search = self.workspace.search(owner, scope, kinds=spec.kinds, query=spec.query, limit=spec.limit)
                refs.extend(search['records'])
                if search.get('truncated'):
                    issues.append({'code': 'partial_search', 'message': 'Some matches were outside the bounded review.'})
            records = []
            selected = _unique_refs(refs)
            if len(selected) > spec.limit:
                issues.append({'code': 'partial_review', 'message': 'The review limit omitted selected records; narrow the scope or increase the limit.',
                               'selected_count': len(selected), 'reviewed_count': spec.limit})
            for ref in selected[:spec.limit]:
                opened = self.workspace.read(owner, scope, kind=ref['kind'], record_id=ref['id'], revision=ref['revision'])
                records.append(opened['record'])
                refs.extend(opened['source_refs'])
            data = {'records': records, 'selected_record_count': len(selected), 'truncated': len(selected) > spec.limit,
                    'review_state': 'draft_requires_review', 'causal_claim_supported': False,
                    'next_step': 'Review the cited evidence; use the assistant for hypotheses, counterevidence and proposed follow-up.'}
            if not records:
                issues.append({'code': 'evidence_required', 'message': 'Select evidence or provide a search query.'})
        refs = _unique_refs(refs)
        self._validate(ctx, refs, spec.site_id)
        if not refs and not issues:
            issues.append({'code': 'no_matches', 'message': 'No matching authorized records were found in this scope.'})
        return {'operation': spec.operation, 'site_id': spec.site_id, 'owner_id': principal(ctx),
                'task_status': 'needs_information' if issues else 'completed',
                'summary': self._summary(spec, data, issues), 'data': data, 'issues': issues[:100],
                'issue_count': len(issues), 'issues_truncated': len(issues) > 100,
                'source_refs': refs, 'elapsed_seconds': time.perf_counter() - started, 'model_calls': 0}

    def execute(self, ctx, request, *, commit_guard=None, on_commit=None):
        started = time.perf_counter()
        spec = request if isinstance(request, TaskSpec) else TaskSpec.model_validate(request)
        result = self.compute(ctx, spec)
        with self.p.store.transaction(ctx.actor_id) as tx:
            self._validate(ctx, result['source_refs'], spec.site_id, tx=tx)
            if commit_guard:
                commit_guard(tx)
            rid = new_id('wreq')
            tx.put(ctx.tenant_id, 'workspace_task_request', rid,
                   {'site_id': spec.site_id, 'owner_id': principal(ctx), 'task': spec.model_dump(), 'created_at': iso(utc_now())},
                   expected_revision=None, action='request_task', event_type='workspace_task.requested',
                   event_payload={'site_id': spec.site_id, 'id': rid})
            inputs = [EvidenceRef(**r) for r in result['source_refs']]
            inputs.append(EvidenceRef('workspace_task_request', rid, 1, spec.site_id))
            result['elapsed_seconds'] = time.perf_counter() - started
            saved = self.p.evidence.record_derived(ctx, 'workspace_task_result',
                {**result, 'task': spec.model_dump(), 'created_at': iso(utc_now())}, inputs=inputs,
                produced_by={'method': 'workspace_tasks:v1', 'actor_id': ctx.actor_id})
            if on_commit:
                on_commit(tx, saved)
        return saved

    def get(self, ctx, result_id):
        rec = self.p.store.read().require(ctx.tenant_id, 'workspace_task_result', result_id)
        self._current_context(ctx, rec.state['site_id'])
        self.p.memory.require_record(ctx, rec.kind, rec.state)
        self._validate(ctx, rec.state['source_refs'], rec.state['site_id'], current=False)
        result = self.p.evidence.read_derived(ctx, rec.kind, result_id)
        # Some operational record updates have no evidence-invalidation hook.
        # Historical packets remain inspectable, but their label must reflect
        # actual revisions before the UI or agent relies on them as current.
        try:
            self._validate(ctx, result['source_refs'], rec.state['site_id'], current=True)
        except ValueError:
            result = {**result, 'status': 'stale', 'stale_reasons': [
                *result.get('stale_reasons', []), 'Selected source versions changed; rerun the task before using it.']}
        return result

    def _applicability(self, ctx, spec, records, issues):
        for item in records:
            rec = self.p.store.read().require(ctx.tenant_id, item['kind'], item['id'])
            metadata = {**rec.state, **(rec.state.get('metadata') or {})}
            reasons, unknown = [], []
            for requested, key in ((spec.process_stage, 'process_stage'), (spec.batches, 'batches')):
                if not requested:
                    continue
                actual = metadata.get(key) or (metadata.get('batch_id') if key == 'batches' else None)
                if not actual:
                    unknown.append(f'{key} metadata unavailable')
                elif key == 'batches':
                    actual = actual if isinstance(actual, list) else [actual]
                    if not set(requested).intersection(actual):
                        reasons.append('different batch')
                elif actual != requested:
                    reasons.append('different process stage')
            if spec.effective_at:
                moment = parse_iso(spec.effective_at)
                start, end = metadata.get('effective_from'), metadata.get('effective_to')
                if not start:
                    unknown.append('effective date unavailable')
                try:
                    if start and parse_iso(start) > moment:
                        reasons.append('not yet effective at the requested time')
                    if end and parse_iso(end) <= moment:
                        reasons.append('expired at the requested time')
                except (ValueError, TypeError):
                    unknown.append('invalid source effective date')
            if not any((spec.effective_at, spec.process_stage, spec.batches)):
                unknown.append('no applicability criteria supplied')
            item.update(applicability='excluded' if reasons else 'unknown' if unknown else 'matches_requested_criteria',
                        applicability_reasons=reasons + unknown)
            if reasons or unknown:
                issues.append({'code': 'applicability_unresolved', 'id': rec.id,
                               'message': '; '.join(reasons + unknown)})

    def _payload(self, ctx, rec):
        key = (ctx.tenant_id, rec.id, rec.revision)
        with self._cache_lock:
            if key in self._parsed:
                self._parsed.move_to_end(key)
                return self._parsed[key][1]
        if rec.state.get('size', 0) > MAX_BYTES:
            raise ValueError('dataset exceeds the 10 MiB direct-task limit; select a smaller verified partition')
        raw = self.p.evidence.original(ctx, rec.id, revision=rec.revision)
        if len(raw) > MAX_BYTES:
            raise ValueError('dataset exceeds the direct-task size limit')
        payload = json.loads(raw)
        if payload.get('schema_version') != 'platform-verified-cmo-1' or not payload.get('guarantee', {}).get('holds'):
            raise ValueError('dataset must use the verified delivery schema')
        with self._cache_lock:
            self._parsed[key] = (len(raw), payload)
            while sum(n for n, _ in self._parsed.values()) > 2 * MAX_BYTES:
                self._parsed.popitem(last=False)
        return payload

    def _measurements(self, ctx, spec, issues):
        from .science import _units
        groups, refs, target_units = defaultdict(list), [], {}
        selected_series = {(s.dataset_id, s.batch) for s in spec.series}
        seen = 0
        for evidence_id in dict.fromkeys(spec.dataset_ids):
            rec = require_dataset(self.p, ctx, evidence_id, spec.site_id)
            self._validate(ctx, [_ref(rec)], spec.site_id)
            refs.append(_ref(rec))
            rows = self._payload(ctx, rec).get('measurements', [])
            seen += len(rows)
            if seen > MAX_ROWS:
                raise ValueError('direct tasks accept at most 100,000 source rows; partition the selected data')
            for row in rows:
                batch, parameter = row.get('batch'), row.get('parameter')
                if selected_series and (evidence_id, batch) not in selected_series:
                    continue
                if spec.batches and batch not in spec.batches or spec.parameter and parameter != spec.parameter:
                    continue
                origin = {'evidence_id': rec.id, 'revision': rec.revision, 'measurement_id': row.get('id'),
                          'source': row.get('source'), 'source_sha256': row.get('source_sha256')}
                if row.get('status') not in (None, 'accepted', 'auto_accepted', 'corrected'):
                    issues.append({'code': 'unaccepted_measurement', 'message': 'This row is not accepted for analysis.', **origin})
                    continue
                if not batch or not parameter:
                    issues.append({'code': 'missing_identity', 'message': 'A measurement has no batch or parameter.', **origin})
                    continue
                unit = row.get('unit')
                if not unit:
                    issues.append({'code': 'missing_unit', 'message': 'A measurement has no declared unit.', **origin})
                    continue
                try:
                    if isinstance(row.get('value'), bool) or isinstance(row.get('time'), bool):
                        raise ValueError('boolean measurement')
                    value, t = float(row['value']), float(row['time'])
                    if not math.isfinite(value) or not math.isfinite(t):
                        raise ValueError('non-finite measurement')
                except (KeyError, TypeError, ValueError):
                    issues.append({'code': 'invalid_measurement', 'message': 'Value and elapsed time must be finite numbers.', **origin})
                    continue
                target = spec.target_unit or target_units.setdefault(parameter, unit)
                try:
                    # Equal declared units need no conversion. Domain scales
                    # such as pH/OD600 and cell-count labels are not SI symbols;
                    # notably Pint parses "pH" as picohenry, not acidity.
                    if unit == target:
                        converted = value
                    elif parameter.casefold() == 'ph' or str(unit).casefold() == 'ph' or str(target).casefold() == 'ph':
                        raise ValueError('pH is a domain scale, not an inductance unit')
                    else:
                        converted = float(_units().Quantity(value, unit).to(target).magnitude)
                except Exception:
                    issues.append({'code': 'incompatible_unit', 'message': f'Cannot convert {unit} to {target}.', **origin})
                    continue
                if not math.isfinite(converted):
                    issues.append({'code': 'invalid_measurement', 'message': 'Conversion produced a non-finite value.', **origin})
                    continue
                groups[(evidence_id if selected_series else '', batch, parameter, t)].append({
                    **({'dataset_id': evidence_id} if selected_series else {}), 'batch': batch, 'parameter': parameter, 'time_h': t,
                    'value': converted, 'unit': target, 'original_value': row['value'], 'original_unit': unit, 'sources': [origin]})
        out = []
        for (dataset_id, batch, parameter, t), group in sorted(groups.items()):
            if any(not math.isclose(g['value'], group[0]['value'], rel_tol=1e-12, abs_tol=1e-12) for g in group[1:]):
                issues.append({'code': 'conflicting_measurements', 'message': 'Conflicting duplicates require source review.',
                               **({'dataset_id': dataset_id} if dataset_id else {}),
                               'batch': batch, 'parameter': parameter, 'time_h': t, 'values': group[:10],
                               'conflicting_row_count': len(group)})
            else:
                out.append({**group[0], 'sources': [s for g in group for s in g['sources']]})
        return out, refs

    @staticmethod
    def _compare(spec, rows, issues):
        batches = ([(s.dataset_id, s.batch) for s in spec.series] if spec.series else
                   [(None, b) for b in spec.batches or sorted({r['batch'] for r in rows})])
        identity = lambda r: (r.get('dataset_id') if spec.series else None, r['batch'])
        parameters = [spec.parameter] if spec.parameter else sorted({r['parameter'] for r in rows})
        comparisons, matched, observed = [], defaultdict(set), defaultdict(set)
        comparison_count = 0
        for parameter in parameters:
            table = {(identity(r), r['time_h']): r for r in rows if r['parameter'] == parameter}
            for (batch, t) in table:
                observed[batch].add((parameter, t))
            for left, right in combinations(batches, 2):
                for t in sorted({t for b, t in table if b == left} & {t for b, t in table if b == right}):
                    a, b = table[(left, t)], table[(right, t)]
                    matched[left].add((parameter, t)); matched[right].add((parameter, t))
                    comparison_count += 1
                    if len(comparisons) < spec.limit:
                        comparisons.append({'parameter': parameter, 'left_batch': left[1], 'right_batch': right[1],
                            **({'left_dataset_id': left[0], 'right_dataset_id': right[0]} if spec.series else {}),
                            'time_h': t, 'left_value': a['value'], 'right_value': b['value'],
                            'difference': b['value'] - a['value'], 'unit': a['unit']})
        if not comparisons:
            issues.append({'code': 'no_comparable_samples', 'message': 'Select at least two batches with matching measured times and compatible units.'})
        label = lambda b: f'{b[1]} ({b[0]})' if spec.series else b[1]
        return {'comparisons': comparisons, 'comparison_count': comparison_count,
                'comparisons_truncated': comparison_count > spec.limit,
                'unmatched_times': {label(b): sorted({t for _, t in observed[b] - matched[b]})[:spec.limit] for b in batches},
                'unmatched_samples': {label(b): [{'parameter': p, 'time_h': t} for p, t in sorted(observed[b] - matched[b])[:spec.limit]] for b in batches},
                'causal_claim_supported': False,
                'limitations': ['Descriptive comparison only; equipment, scale and process-phase equivalence have not been established.',
                               'Only exact elapsed-time matches are compared; no interpolation or aggregation.']}

    def _gaps(self, ctx, spec, rows, refs, issues):
        gaps, count = [], 0
        identities = ([s.model_dump() for s in spec.series] if spec.series else
                      [{'batch': b} for b in spec.batches or sorted({r['batch'] for r in rows})])
        times_by = defaultdict(set)
        for row in rows:
            times_by[(row.get('dataset_id') if spec.series else None, row['batch'], row['parameter'])].add(row['time_h'])
        def append_gap(gap):
            nonlocal count
            count += 1
            if len(gaps) < spec.limit:
                gaps.append(gap)
        for selected in identities:
            for parameter in spec.expected_parameters:
                times = times_by[(selected.get('dataset_id'), selected['batch'], parameter)]
                if not times:
                    append_gap({**selected, 'parameter': parameter, 'status': 'not_in_selected_data'})
                else:
                    for t in sorted(set(spec.expected_times) - times):
                        append_gap({**selected, 'parameter': parameter, 'time_h': t, 'status': 'not_in_selected_data'})
        present = set()
        for ref in refs:
            rec = self.p.store.read().require(ctx.tenant_id, ref['kind'], ref['id'])
            present.add((rec.state.get('metadata') or {}).get('document_kind'))
        for k in spec.expected_document_kinds:
            if k not in present:
                append_gap({'document_kind': k, 'status': 'not_in_selected_data'})
        if not (spec.expected_parameters or spec.expected_document_kinds):
            issues.append({'code': 'expectations_required', 'message': 'Specify expected parameters or document kinds; absence cannot be inferred without a requirement.'})
        if spec.expected_parameters and not (spec.batches or rows):
            issues.append({'code': 'batches_required', 'message': 'Select batches or a dataset to check parameter coverage.'})
        if gaps:
            issues.append({'code': 'missing_expected_evidence', 'message': 'Expected evidence is absent from the selected inputs; it may exist elsewhere.'})
        return {'gaps': gaps, 'gap_count': count, 'gaps_truncated': count > spec.limit,
                'expectation_basis': 'user_supplied', 'coverage': 'Selected datasets and records only; not a finding of absence in other systems or SME knowledge.'}

    @staticmethod
    def _summary(spec, data, issues):
        if spec.operation == 'compare':
            text = f"Compared {data.get('comparison_count', 0)} measured pairs."
        elif spec.operation == 'check_gaps':
            text = f"Found {data.get('gap_count', 0)} gaps against your stated expectations."
        elif spec.operation == 'reconcile':
            text = f"Reconciled {data.get('measurement_count', 0)} measurements."
        else:
            text = f"Prepared {len(data.get('records', []))} records."
        return text + (f' {len(issues)} checks need attention.' if issues else '')
