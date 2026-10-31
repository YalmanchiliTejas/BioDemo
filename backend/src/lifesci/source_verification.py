"""Durable live-source review over the same rules used by file deliveries.

Transport intake preserves every original payload. This service adds a separate,
version-bound acceptance state; collecting a record never implies verifying it.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from ..ingestion.schema import VOCAB, alias
from ..ingestion.verification import VERSION, validate_collection, validate_measurement
from .evidence import EvidenceRef
from .ids import content_hash, iso, utc_now
from .store import ConflictError

ACCEPTED = {'auto_accepted', 'accepted'}
DYNAMIC = {'DUPLICATE_CONFLICT', 'DUPLICATE_RECORD', 'ROW_CONFLICT', 'BATCH_MISMATCH'}
# A review reason cannot turn an unreadable/undefined value into a usable value.
HARD_BLOCKS = {'VALUE_INVALID', 'UNIT_UNKNOWN', 'UNIT_CONVERT', 'PARAMETER_UNKNOWN',
               'MISSING_FIELD', 'TIME_ORDER', 'MAPPING_ERROR', 'SOURCE_REVIEW', 'DUPLICATE_CONFLICT'}
DOC_TYPES = {'HISTORIAN': 'instrument_export', 'LIMS': 'lab_results', 'MES': 'batch_record',
             'QMS': 'deviation_report', 'CMMS': 'maintenance'}


class SourceVerificationService:
    def __init__(self, store, identity, evidence):
        self.store, self.identity, self.evidence = store, identity, evidence

    def configure(self, ctx, connector_id, template, *, site_id, confirmed=False, source_group=None):
        self.identity.require(ctx, 'configure', 'connector', connector_id, site_id=site_id)
        state = {'connector_id': connector_id, 'site_id': site_id,
                 'source_group': source_group or connector_id,
                 'template': template.to_dict(), 'mapping_confirmed': bool(confirmed), 'rule_version': VERSION}
        with self.store.transaction(ctx.actor_id) as tx:
            current = tx.get(ctx.tenant_id, 'intake_mapping', connector_id)
            if current and current.state == state:
                return current
            if current:
                self.evidence.invalidate(ctx, 'intake_mapping', connector_id, 'source mapping or verification policy changed')
            return tx.put(ctx.tenant_id, 'intake_mapping', connector_id, state,
                          expected_revision=current.revision if current else None, action='configure_intake_mapping')

    def record(self, ctx, connector_id, record, mapped, source, mapping):
        """Accept structured observations directly; no serialization to CSV or OCR."""
        ref = EvidenceRef('evidence', source['evidence_id'], source['revision'], source.get('site_id'))
        refs = [ref, EvidenceRef('intake_mapping', connector_id, mapping.revision, source.get('site_id'))]
        ident = content_hash([connector_id, ref.id])[:40]
        current = self.store.read().get(ctx.tenant_id, 'intake_record', ident)
        inputs = [r.to_dict() for r in refs]
        if current and current.state.get('status') == 'current' and current.state['inputs'] == inputs:
            return current.state
        if current:
            self.evidence.invalidate(ctx, 'intake_record', ident, 'source observation or mapping revised')
        fields = deepcopy(mapped['fields'])
        base_codes = []
        if mapped['errors']:
            base_codes.append('MAPPING_ERROR')
        if mapped['unmapped']:
            base_codes.append('UNMAPPED_FIELD')
        if not fields:
            base_codes.append('MISSING_FIELD')
        if not mapping.state['mapping_confirmed']:
            base_codes.append('DRAFT_MAPPING')
        location = {'path': f"{record.source_system}/{record.source_record_id}", 'row': 1,
                    'source_record_id': record.source_record_id, 'source_revision': source.get('source_revision'),
                    'evidence_id': ref.id, 'evidence_revision': ref.revision, 'digest': source['digest']}
        observations = []
        long_parameter = fields.get('parameter', fields.get('test', fields.get('tag')))
        candidates = [(name, value, mapped['units'].get(name), name) for name, value in fields.items() if name in VOCAB]
        if 'value' in fields and (long_parameter is not None or mapping.state['template']['system'] in {'LIMS', 'HISTORIAN'}):
            # Unknown parameters remain reviewable; they are never guessed into a public quantity.
            parameter = alias(f"{long_parameter} [{fields['unit']}]") if fields.get('unit') else alias(long_parameter)
            candidates.append((parameter or str(long_parameter or ''), fields['value'],
                               mapped['units'].get('value') or fields.get('unit'), 'value'))
        for parameter, value, unit, field_key in candidates:
            from .integrations import _get_path
            fm = next((f for f in mapping.state['template']['fields'] if f['canonical'] == field_key), None)
            raw_value = _get_path(record.payload, fm['source']) if fm else value
            raw_unit = (fm.get('unit') or (_get_path(record.payload, fm['unit_field']) if fm.get('unit_field') else None)) if fm else None
            raw_unit = raw_unit or unit
            observation = {'id': content_hash([ident, parameter])[:40], 'evidence_id': ref.id,
                           'source_id': ref.id, 'source': {**location, 'column': parameter},
                           'source_sha256': source['digest'], 'parameter': parameter,
                           'batch': str(fields.get('batch_id', fields.get('batch', ''))).strip().upper(),
                           'time': str(fields.get('elapsed_h', fields.get('time', source['event_time']))),
                           'value_raw': raw_value, 'unit_raw': raw_unit, 'value': None, 'unit': None,
                           'source_verified': True, 'template_id': mapping.id if mapping.state['mapping_confirmed'] else None,
                           'status': 'needs_review', 'rule_codes': []}
            validate_measurement(observation, mapping_confirmed=mapping.state['mapping_confirmed'], raw_unit=raw_unit)
            observations.append(observation)
        codes = sorted(set(base_codes + [code for m in observations for code in m['rule_codes']]))
        payload = {'connector_id': connector_id, 'site_id': source.get('site_id'),
                   'source_group': mapping.state['source_group'], 'source_record_id': record.source_record_id,
                   'source_system': record.source_system, 'event_time': source['event_time'],
                   'fields': fields, 'unmapped': mapped['unmapped'], 'mapping_errors': mapped['errors'],
                   'measurements': observations, 'base_codes': codes, 'rule_codes': codes,
                   'doc_type': DOC_TYPES.get(mapping.state['template']['system'], 'other'),
                   'review_state': 'needs_review' if codes else 'auto_accepted', 'reviews': [],
                   'collection': 'open', 'rule_version': VERSION}
        return self.evidence.record_derived(ctx, 'intake_record', payload, inputs=refs,
            produced_by={'actor_id': ctx.actor_id, 'method': VERSION}, artifact_id=ident)

    def recheck(self, ctx, connector_id):
        """Reapply an edited mapping to retained originals, without rewinding a live cursor."""
        import json
        from .integrations import ConnectorTemplate, apply_mapping, record_from_dict
        mapping = self.store.read().require(ctx.tenant_id, 'intake_mapping', connector_id)
        template = ConnectorTemplate.from_dict(mapping.state['template'])
        for prior in self.store.read().list(ctx.tenant_id, 'intake_record'):
            if prior.state['connector_id'] != connector_id:
                continue
            source_ref = next(r for r in prior.state['inputs'] if r['kind'] == 'evidence')
            source = self.store.read().require(ctx.tenant_id, 'evidence', source_ref['id'])
            payload = json.loads(self.evidence.original(ctx, source.id))
            rec = record_from_dict({'source_record_id': source.state['source_record_id'],
                'source_system': source.state['source_system'], 'occurred_at': source.state['event_time'],
                'payload': payload, 'site_id': source.state['site_id']})
            self.record(ctx, connector_id, rec, apply_mapping(template, payload),
                        {**source.state, 'revision': source.revision}, mapping)
        self.refresh(ctx, connector_id)

    def _records(self, ctx, mapping):
        out = []
        for r in self.store.read().list(ctx.tenant_id, 'intake_record'):
            s = r.state
            if s['source_group'] != mapping.state['source_group'] or s['site_id'] != mapping.state['site_id']:
                continue
            self.identity.require(ctx, 'read', 'intake_record', r.id, site_id=s['site_id'])
            # Stale mappings/sources must be re-collected; old review decisions never carry silently.
            out.append(r)
        return out

    def refresh(self, ctx, connector_id):
        mapping = self.store.read().require(ctx.tenant_id, 'intake_mapping', connector_id)
        records = self._records(ctx, mapping)
        run = {'measurements': [], 'documents': [], 'issues': []}
        for r in records:
            if r.state.get('status') != 'current' or r.state['review_state'] == 'rejected':
                continue
            self.identity.validate_refs(ctx, r.state['inputs'], require_current=True)
            for m in r.state['measurements']:
                row = deepcopy(m); row['rule_codes'] = [c for c in row['rule_codes'] if c not in DYNAMIC]
                run['measurements'].append(row)
                run['documents'].append({'source_id': row['source_id'], 'path': row['source']['path'],
                                         'doc_type': r.state['doc_type']})
        def issue(code, **context):
            run['issues'].append({'rule_code': code, 'status': 'open', **context})
        # All current records in the same tenant/site/source-group are compared, including earlier polls.
        validate_collection(run, issue, complete=False, ordered=False)
        observations = {m['id']: m for m in run['measurements']}
        for r in records:
            if r.state.get('status') != 'current' or r.state['review_state'] == 'rejected':
                continue
            measures = [observations[m['id']] for m in r.state['measurements']]
            codes = sorted(set(r.state['base_codes'] + [c for m in measures for c in m['rule_codes']]))
            reviewed = r.state['review_state'] == 'accepted'
            state = {**r.state, 'measurements': measures, 'rule_codes': codes,
                     'review_state': 'accepted' if reviewed else 'needs_review' if codes else 'auto_accepted'}
            if state != r.state:
                if any(c in HARD_BLOCKS for c in codes):
                    state['review_state'] = 'needs_review'
                self.evidence.invalidate(ctx, 'intake_record', r.id, 'collection checks changed')
                with self.store.transaction(ctx.actor_id) as tx:
                    tx.put(ctx.tenant_id, 'intake_record', r.id, state, expected_revision=r.revision,
                           action='verify_source_collection')
        return run['issues']

    def summary(self, ctx, connector_id):
        mapping = self.store.read().require(ctx.tenant_id, 'intake_mapping', connector_id)
        self.identity.require(ctx, 'read', 'connector', connector_id, site_id=mapping.state['site_id'])
        records = self._records(ctx, mapping)
        states = Counter(r.state['review_state'] if r.state.get('status') == 'current' else 'stale' for r in records)
        return {'connector_id': connector_id, 'source_group': mapping.state['source_group'], 'collection': 'open',
                'complete': False, 'records': len(records), 'states': dict(states),
                'needs_review': states['needs_review'], 'accepted': sum(states[s] for s in ACCEPTED),
                'stale': states['stale'], 'rule_version': VERSION}

    def list_for(self, ctx, connector_id):
        mapping = self.store.read().require(ctx.tenant_id, 'intake_mapping', connector_id)
        return {'summary': self.summary(ctx, connector_id),
                'items': [{'id': r.id, 'revision': r.revision, **r.state,
                           'can_accept': r.state.get('status') == 'current' and not HARD_BLOCKS.intersection(r.state['rule_codes'])}
                          for r in self._records(ctx, mapping)]}

    def review(self, ctx, connector_id, record_id, *, expected_revision, decision, reason):
        r = self.store.read().require(ctx.tenant_id, 'intake_record', record_id)
        self.identity.require(ctx, 'approve', 'intake_record', record_id, site_id=r.state['site_id'])
        if ctx.actor_kind != 'person':
            raise PermissionError('source verification requires a human reviewer')
        mapping = self.store.read().require(ctx.tenant_id, 'intake_mapping', connector_id)
        if r.state['source_group'] != mapping.state['source_group'] or r.state['site_id'] != mapping.state['site_id']:
            raise PermissionError('record does not belong to this source group and site')
        if r.revision != expected_revision:
            raise ConflictError('source record changed; reload it before reviewing')
        if decision not in {'accept', 'reject'} or not reason.strip():
            raise ValueError('choose accept or reject and give a review reason')
        if r.state.get('status') != 'current':
            raise ValueError('source record is stale; sync it again before reviewing')
        if decision == 'accept' and HARD_BLOCKS.intersection(r.state['rule_codes']):
            raise ValueError('invalid or conflicting values require source/mapping correction or rejection')
        with self.store.transaction(ctx.actor_id) as tx:
            self.identity.validate_refs(ctx, r.state['inputs'], require_current=True, tx=tx)
            self.evidence.invalidate(ctx, 'intake_record', record_id, 'human source review changed')
            receipt = {'actor': ctx.actor_id, 'decision': decision, 'reason': reason.strip(),
                       'at': iso(utc_now()), 'basis': r.state['inputs'], 'record_revision': r.revision}
            result = tx.put(ctx.tenant_id, 'intake_record', record_id,
                {**r.state, 'review_state': 'accepted' if decision == 'accept' else 'rejected',
                 'reviews': [*r.state['reviews'], receipt]}, expected_revision=expected_revision,
                action='review_source_record', reason=reason.strip())
        self.refresh(ctx, connector_id)
        return {'id': result.id, 'revision': result.revision, **result.state}

    def publish(self, ctx, connector_id):
        """Publish an accepted observation snapshot through the existing dataset contract."""
        self.refresh(ctx, connector_id)
        mapping = self.store.read().require(ctx.tenant_id, 'intake_mapping', connector_id)
        site = mapping.state['site_id']
        self.identity.require(ctx, 'export', 'intake_record', site_id=site)
        records = self._records(ctx, mapping)
        if not records or any(r.state.get('status') != 'current' or r.state['review_state'] not in ACCEPTED | {'rejected'} for r in records):
            raise ValueError('source group has pending or stale verification; review or resync it before publishing')
        for r in records:
            self.identity.validate_refs(ctx, r.state['inputs'], require_current=True)
            if r.state['review_state'] in ACCEPTED and HARD_BLOCKS.intersection(r.state['rule_codes']):
                raise ValueError('source group still contains invalid or conflicting observations')
        connectors = {r.state['connector_id'] for r in records}
        for cid in connectors:
            config = self.store.read().get(ctx.tenant_id, 'connector', cid)
            if config and (config.state.get('last_error') or
                           (config.state.get('last_result') or {}).get('rejected_records')):
                raise ValueError('source group has a collection error or rejected source rows; resolve it before publishing')
            cursor = self.store.read().get(ctx.tenant_id, 'connector_cursor', cid)
            if cursor and cursor.state.get('gap_streams'):
                raise ValueError('source group has unresolved collection gaps')
        accepted = [r for r in records if r.state['review_state'] in ACCEPTED]
        if not accepted:
            raise ValueError('source group has no accepted records')
        inputs = [EvidenceRef('intake_record', r.id, r.revision, site).to_dict() for r in records]
        # Keep both the verification revision and original source basis pinned.
        inputs += [ref for r in records for ref in r.state['inputs']]
        inputs = list({(r['kind'], r['id'], r['revision']): r for r in inputs}.values())
        self.identity.validate_refs(ctx, inputs, require_current=True)
        measurements = [{**m, 'status': r.state['review_state']} for r in accepted for m in r.state['measurements']]
        run_id = content_hash(inputs)[:32]
        coverage = {'collection': 'open', 'complete': False, 'records_seen': len(records),
                    'accepted': len(accepted), 'rejected': len(records)-len(accepted), 'unaccounted': 0}
        body = {'run_id': run_id, 'cmo': mapping.state['source_group'], 'package_id': None,
                'delivery_name': f"Live observations: {mapping.state['source_group']}",
                'completed_at': max(r.updated_at for r in records), 'coverage': coverage,
                'disclosure': 'Accepted source observations from an open collection; not a claim of batch or delivery completeness.',
                'guarantee': {'holds': True, 'checks': [
                    {'id': 'accepted_current_basis', 'label': 'Every included value has a current verified basis', 'passed': True},
                    {'id': 'review_accounting', 'label': 'Every excluded record has an attributed rejection', 'passed': True}]},
                'measurements': measurements}
        from .cmo_datasets import CLASSIFICATION, dataset_content, listing
        if measurements and all(r.state['measurements'] for r in accepted):
            content = dataset_content(body)
            classification = CLASSIFICATION
        else:
            from .ids import canonical_json
            content = canonical_json({**body, 'records': [r.state['fields'] for r in accepted]}).encode()
            classification = 'verified_source_dataset'
        # Serialize publication with validation to avoid publishing an obsolete review/source basis.
        with self.store.transaction(ctx.actor_id) as tx:
            self.identity.validate_refs(ctx, inputs, require_current=True, tx=tx)
            ev = self.evidence.ingest(ctx, source_system='verified-source-snapshot', source_record_id=run_id,
                content=content, media_type='application/json', site_id=site, event_time=body['completed_at'],
                mapping_version=VERSION, metadata={'classification': classification, 'cmo': body['cmo'],
                    'delivery_name': body['delivery_name'], 'measurements': len(measurements),
                    'batches': sorted({m['batch'] for m in measurements}),
                    'parameters': sorted({m['parameter'] for m in measurements}),
                    'verification_basis': inputs, 'collection': 'open', 'complete': False})
            for ref in inputs:
                tx.add_edge(ctx.tenant_id, (ref['kind'], ref['id']), ('evidence', ev['evidence_id']), 'verified_snapshot_input')
        return listing(self.store.read().require(ctx.tenant_id, 'evidence', ev['evidence_id']))
