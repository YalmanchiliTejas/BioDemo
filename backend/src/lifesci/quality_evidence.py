"""Bounded, local, permission-aware quality evidence assembly. No connector queries."""
from __future__ import annotations

from typing import Any

IDENTIFIERS = ('batch_id', 'equipment_id', 'product_id', 'material_id', 'lot_id', 'sample_id', 'supplier_id')
SOURCE_KINDS = ('evidence', 'batch', 'sample', 'result', 'instrument', 'work_order', 'signal', 'material_lot')


def identifiers(state: dict) -> set[str]:
    values = set()
    metadata = state.get('metadata') or {}
    for data in (state, metadata, metadata.get('mapped') or {}, state.get('associations') or {}):
        for key in IDENTIFIERS:
            if isinstance(data.get(key), (str, int)):
                values.add(str(data[key]))
        values.update(str(v) for v in data.get('batch_ids') or [] if isinstance(v, (str, int)))
    return values


def typed_identifiers(state: dict) -> set[str]:
    """Exact explicit identifiers only; do not equate aliases or identifier domains."""
    values = set()
    metadata = state.get('metadata') or {}
    for data in (state, metadata, metadata.get('mapped') or {}, state.get('associations') or {}):
        for key in IDENTIFIERS:
            if isinstance(data.get(key), (str, int)):
                values.add(f'{key}:{data[key]}')
        values.update(f'batch_id:{v}' for v in data.get('batch_ids') or [] if isinstance(v, (str, int)))
    return values


def refs_in(value: Any) -> list[dict]:
    """Find lineage wherever a science extension or submitted snapshot carries it."""
    out = []
    if isinstance(value, dict):
        if value.get('kind') and value.get('id') and isinstance(value.get('revision'), int):
            out.append({k: value[k] for k in ('kind', 'id', 'revision', 'site_id') if k in value})
        else:
            for child in value.values():
                out.extend(refs_in(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(refs_in(child))
    return list({(r['kind'], r['id'], r['revision']): r for r in out}.values())


def quality_lineage(kind: str, state: dict) -> list[dict]:
    """Known platform-owned lineage fields only; raw source document content is not a manifest."""
    if kind == 'case' and state.get('workflow'):
        return refs_in(state['workflow'])
    if kind == 'deviation_signal':
        refs = list(state.get('evidence_refs') or [])
        for observation in state.get('observations') or []:
            if observation.get('evidence_ref'):
                refs.append(observation['evidence_ref'])
        return refs
    return []


class QualityEvidence:
    def __init__(self, platform):
        self.p = platform

    def authorize(self, ctx, refs, *, current=False, action='read'):
        if not refs:
            return []
        pinned = self.p.identity.validate_refs(ctx, refs, require_current=current)
        pinned = list({(r['kind'], r['id'], r['revision']): r for r in pinned}.values())
        if action != 'read':
            for ref in pinned:
                self.p.identity.require(ctx, action, ref['kind'], ref['id'], site_id=ref.get('site_id'))
                tx = self.p.store.read()
                for rec in (tx.require(ctx.tenant_id, ref['kind'], ref['id']),
                            tx.revision(ctx.tenant_id, ref['kind'], ref['id'], ref['revision'])):
                    if rec.state.get('inputs'):
                        self.authorize(ctx, rec.state['inputs'], action=action)
                    lineage = quality_lineage(ref['kind'], rec.state)
                    if lineage:
                        self.authorize(ctx, lineage, action=action)
        return pinned

    def collect(self, ctx, case, limit=200):
        tx = self.p.store.read()
        scope = typed_identifiers(case)
        explicit = {(r['kind'], r['id']) for r in case['workflow']['discovery_refs']}
        refs = []
        truncated = False
        inaccessible = 0
        for kind in SOURCE_KINDS:
            count = 0
            for rec in tx.list(ctx.tenant_id, kind):
                if rec.state.get('site_id') != case['site_id']:
                    continue
                if (kind, rec.id) not in explicit and not scope.intersection(typed_identifiers(rec.state)):
                    continue
                try:
                    self.authorize(ctx, [{'kind': kind, 'id': rec.id, 'revision': rec.revision}])
                except PermissionError:
                    inaccessible += 1
                    continue
                if count >= limit:
                    truncated = True
                    continue
                count += 1
                refs.append({'kind': kind, 'id': rec.id, 'revision': rec.revision, 'site_id': case['site_id']})
        # Explicit sources may be other supported store records; never infer a connector query.
        for kind, rid in explicit - {(r['kind'], r['id']) for r in refs}:
            rec = tx.require(ctx.tenant_id, kind, rid)
            if rec.state.get('site_id') != case['site_id']:
                raise PermissionError('quality source outside case site')
            ref = {'kind': kind, 'id': rid, 'revision': rec.revision, 'site_id': case['site_id']}
            self.authorize(ctx, [ref])
            refs.append(ref)
        sources = self.views(ctx, refs)
        timeline, candidates, gaps = [], [], []
        for source in sources:
            state, ref = source['state'], source['ref']
            mapped = (state.get('metadata') or {}).get('mapped') or {}
            event_time = state.get('event_time') or mapped.get('event_time')
            timeline.append({'event_time': event_time,
                'recorded_at': state.get('recorded_at'), 'description': f"{ref['kind']}:{ref['id']}",
                'evidence_refs': [ref], 'time_basis': 'source_event_time' if event_time else 'event_time_unknown'})
            candidates.append({'identifiers': {k: mapped.get(k, state.get(k)) for k in IDENTIFIERS
                if mapped.get(k, state.get(k)) is not None}, 'evidence_refs': [ref],
                'status': 'candidate_requires_assessment', 'quality_status': mapped.get('status'),
                'distribution_status': mapped.get('distribution_status', 'unknown')})
            if not event_time:
                gaps.append({'code': 'event_time_unknown', 'evidence_refs': [ref]})
        timeline.sort(key=lambda v: v['event_time'] or v['recorded_at'] or '')
        if not refs:
            gaps.append({'code': 'no_matching_authorized_sources'})
        if truncated:
            gaps.append({'code': 'collection_truncated', 'limit_per_kind': limit})
        if inaccessible:
            gaps.append({'code': 'source_access_limited'})
        return {'sources': refs, 'timeline': timeline, 'candidates': candidates, 'gaps': gaps,
                'truncated': truncated}

    def views(self, ctx, refs):
        self.authorize(ctx, refs)
        tx = self.p.store.read()
        return [{'ref': ref, 'state': tx.revision(ctx.tenant_id, ref['kind'], ref['id'], ref['revision']).state,
                 'current_revision': tx.require(ctx.tenant_id, ref['kind'], ref['id']).revision,
                 'url': f"/v1/quality/workspaces/{{case_id}}/evidence/{ref['kind']}/{ref['id']}?revision={ref['revision']}"}
                for ref in refs]
