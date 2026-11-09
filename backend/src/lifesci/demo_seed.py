"""Synthetic data for one demo workspace. Every record is labelled SYNTHETIC; no model calls, no CMO pipeline run.

Built from repo fixtures through the normal services (so permissions, audit and listeners apply as in production):
- a verified CMO delivery dataset from the Northfield September sample (CHO runs, VCD / viability / glucose / lactate)
- one open deviation case (DEV-31) and two CLOSED precedent cases with root cause, CAPA and outcome
- a DO specification plus historian readings that raise an `action` signal
- a QMS deviation record that raises a `critical` signal
Auto-triage is paused by the caller before this runs, so signals never start a model call.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

SITE = 'NF1'
SEED_QA = 'synthetic-qa-lead'  # a synthetic colleague who holds `close`, so precedent cases can be closed
LIMS = (Path(__file__).resolve().parents[2] / 'benchmarks' / 'cmo_ingestion' / 'demo' / 'cho-calibration' / 'raw'
        / 'LIMS_offline_results_September.csv')
COLUMNS = {'VCD Mean (cells/mL)': ('viable_cell_density', 'cells/mL'), 'Viability Mean (%)': ('viability', '%'),
           'Glucose (g/L)': ('glucose', 'g/L'), 'Lactate (g/L)': ('lactate', 'g/L')}
NOTE = 'SYNTHETIC demo data'


def _verified_dataset() -> tuple[bytes, dict[str, Any]]:
    rows, digest, cells, samples = [], hashlib.sha256(LIMS.read_bytes()).hexdigest(), 0, 0
    with LIMS.open(encoding='utf-8') as stream:
        for line, record in enumerate(csv.DictReader(stream), start=2):
            cells += sum(1 for v in record.values() if (v or '').strip())
            samples += 1
            for column, (parameter, unit) in COLUMNS.items():
                raw = (record.get(column) or '').strip()
                if not raw:
                    continue
                rows.append({'id': f"{record['Sample ID']}-{parameter}", 'source_id': 'lims-september', 'batch': record['Batch'],
                             'time': record['Time (h)'], 'parameter': parameter, 'value': float(raw), 'unit': unit,
                             'value_raw': raw, 'unit_raw': unit, 'status': 'auto_accepted',
                             'source': {'path': LIMS.name, 'row': line}, 'source_sha256': digest})
    content = json.dumps({'schema_version': 'platform-verified-cmo-1', 'run_id': 'demo-september', 'synthetic': True,
                          'cmo': 'Northfield Biologics (synthetic)', 'delivery_name': 'September (synthetic sample)',
                          'coverage': {'elements': cells, 'measurement': len(rows), 'identifier': 3 * samples,  # batch, sample, time
                                       'ignored': cells - len(rows) - 3 * samples, 'flagged': 0, 'unaccounted': 0},
                          'guarantee': {'holds': True, 'checks': [
                              {'id': 'content_accounted', 'label': 'Every source cell and text line is converted, ignored by a confirmed rule, or flagged', 'passed': True},
                              {'id': 'auto_acceptance_rule', 'label': 'Values accepted without review come only from a confirmed mapping, match the original byte-for-byte and pass every check', 'passed': True}]}, 'measurements': rows}, sort_keys=True).encode()
    meta = {'classification': 'verified_cmo_dataset', 'cmo': 'Northfield Biologics (synthetic)', 'synthetic': True,
            'delivery_name': 'September (synthetic sample)', 'measurements': len(rows),
            'batches': sorted({r['batch'] for r in rows}), 'parameters': sorted({r['parameter'] for r in rows})}
    return content, meta


def seed(platform: Any, tenant: str, visitor: str, persona: str) -> dict[str, Any]:
    from .cmo_datasets import SOURCE_SYSTEM
    idn = platform.identity
    idn.assign_role(tenant, SEED_QA, 'qa', by='demo-seed', reason='synthetic colleague for demo data')
    qa = idn.context_for(tenant, SEED_QA)

    content, meta = _verified_dataset()
    dataset = platform.evidence.ingest(qa, source_system=SOURCE_SYSTEM, source_record_id='demo-september', content=content,
                                       media_type='application/json', site_id=SITE, event_time='2026-09-30T18:00:00+00:00',
                                       metadata=meta)

    # Precedents first: two closed foaming / low-DO cases on BR-07, then the open one.
    for case_id, when, story, closure in (
        ('DEV-12', '2026-06-14T03:20:00+00:00', 'Foaming at 5 h in B-088 on BR-07; DO fell to 26 %; antifoam added manually.',
         {'root_cause': 'Antifoam pump AF-2 seal worn; dosing lagged foam onset.', 'actions_taken': 'Seal replaced; AF-2 added to monthly PM.',
          'outcome': 'No foaming in the next 6 batches on BR-07.'}),
        ('DEV-19', '2026-08-02T22:40:00+00:00', 'DO dipped to 28 % at 4 h in B-101 on BR-07 after a new antifoam lot (L-8790).',
         {'root_cause': 'not established', 'actions_taken': 'Lot L-8790 quarantined; supplier CoA requested.',
          'outcome': 'Supplier confirmed lot within spec; no recurrence in 4 batches.'}),
    ):
        platform.cases.open(qa, case_id, visitor, SEED_QA, SITE)
        platform.cases.add_timeline_event(qa, case_id, when, f'{story} ({NOTE})')
        revision = platform.cases.get(qa, case_id)['revision']
        platform.cases.close(qa, case_id, expected_revision=revision, **closure)
        _backdate(platform, tenant, case_id, when)
    platform.cases.open(qa, 'DEV-31', visitor, SEED_QA, SITE)
    platform.cases.add_timeline_event(qa, 'DEV-31', '2026-11-03T04:10:00+00:00',
                                      f'Foaming at 4 h in B-117 on BR-07; DO below 30 %; antifoam lot L-8812 in use. ({NOTE})')
    _backdate(platform, tenant, 'DEV-31', '2026-11-03T04:10:00+00:00')
    _batch_context(platform, tenant, qa)

    # A DO limit and historian readings: the 24 % reading raises an `action` signal.
    platform.specifications.create(qa, site_id=SITE, parameter='DO [%]', unit='%', low=30, high=80, critical_low=15,
                                   source='document', source_ref='Batch record BR-07 v3 (synthetic)',
                                   reason='Demo workspace specification')
    for seq, value in enumerate((61, 44, 33, 24), start=1):
        platform.evidence.ingest(qa, source_system='HISTORIAN', source_record_id=f'BR-07-DO-{seq}',
                                 content=json.dumps({'tag': 'DO', 'value': value, 'seq': seq}).encode(), media_type='application/json',
                                 site_id=SITE, event_time=f'2026-11-03T0{seq}:00:00+00:00',
                                 metadata={'synthetic': True, 'mapped': {'tag': 'DO', 'value': value, 'equipment_id': 'BR-07',
                                                                         'batch_id': 'B-117'}, 'units': {'value': '%'}})
    # The QMS's own deviation record: a `critical` signal (the QMS stays the record of truth).
    platform.evidence.ingest(qa, source_system='QMS', source_record_id='DEV-31', content=b'DEV-31 synthetic QMS record',
                             media_type='text/plain', site_id=SITE, event_time='2026-11-03T04:30:00+00:00',
                             metadata={'synthetic': True, 'mapped': {'case_id': 'DEV-31', 'record_type': 'Deviation',
                                                                     'batch_id': 'B-117', 'equipment_id': 'BR-07',
                                                                     'description': 'Foaming at 4 h; DO below 30 % (synthetic)'}})
    contexts = seed_model_library(platform, qa, SITE)
    return {'dataset_id': dataset['evidence_id'], 'cases': ['DEV-12', 'DEV-19', 'DEV-31'], 'site_id': SITE,
            'persona': persona, 'model_library_contexts': contexts}


def seed_model_library(platform: Any, ctx: Any, site: str) -> list[str]:
    """Evidence-backed executable examples, scoped to this visitor; no inference or solver calls."""
    from .process_models.examples import examples
    from .chemical_reactor.demo import example
    from .fermentation.data import project

    configs = examples() | {
        'chemical.parallel_batch': example(),
        'fermentation.oxygen_transfer': {'project': project('sulfolobus'), 'assumptions': {}},
        'fermentation.pressure_cost': {'project': project('pichia'), 'assumptions': {}},
    }
    ids = []
    for model_id, config in configs.items():
        original = platform.evidence.ingest(
            ctx, source_system='pharmaceutical-synthetic-demo', source_record_id=model_id,
            content=json.dumps({'config': config, 'evidence_classification': 'synthetic_assumption'}, sort_keys=True).encode(),
            media_type='application/json', site_id=site, event_time=None,
            metadata={'synthetic': True})
        result = platform.process_models.analysis.create_configuration(ctx, {
            'model_id': model_id, 'site_id': site, 'label': 'SYNTHETIC · ' + model_id, 'config': config,
            'classification': 'synthetic_assumption',
            'assumptions': ['Authored executable example; not measured customer characterization or validation.'],
            'basis': [{'kind': 'evidence', 'id': original['evidence_id'], 'revision': original['revision'], 'site_id': site}],
        })
        ids.append(result['id'])
    return ids


def _backdate(platform: Any, tenant: str, case_id: str, occurred: str) -> None:
    """Seeded cases were opened when they happened, not when the demo was created (else every answer explains the gap)."""
    with platform.store.transaction('demo-seed') as tx:
        rec = tx.require(tenant, 'case', case_id)
        state = {**rec.state, 'opened_at': occurred}
        if state.get('closure'):
            state['closure'] = {**state['closure'], 'closed_at': occurred[:8] + '28T12:00:00+00:00'}
        tx.put(tenant, 'case', case_id, state, expected_revision=rec.revision, action='demo_seed_backdate')


# What an engineer checks after a DO drop: the batch, the antifoam lot, pump maintenance, probe calibration, dosing.
# Together they point at the new lot (like DEV-19), not the pump (DEV-12) or the probe.
CONTEXT = [
    ('ERP', 'LOT-L-8812', '2026-10-28T09:00:00+00:00', {'lot': 'L-8812', 'material': 'Antifoam C emulsion'},
     'Antifoam lot L-8812 received 2026-10-28 (supplier Silco). First issued to batch B-117 on 2026-11-03. '
     'Previous lot on BR-07 was L-8801, used in B-104 to B-116 with no foaming recorded.'),
    ('CMMS', 'PM-AF-2-2026-11', '2026-11-01T10:00:00+00:00', {'equipment_id': 'AF-2'},
     'Antifoam pump AF-2 (BR-07) preventive maintenance 2026-11-01: seal inspected, no wear; flow check 98 % of nominal. Pass.'),
    ('CMMS', 'CAL-DO-BR-07-2026-10', '2026-10-30T14:00:00+00:00', {'equipment_id': 'BR-07'},
     'DO probe on BR-07 calibrated 2026-10-30 (two-point: zero and air saturation). Post-calibration bump test passed.'),
    ('HISTORIAN', 'BR-07-AF-DOSING-B-117', '2026-11-03T04:00:00+00:00', {'batch_id': 'B-117', 'equipment_id': 'BR-07'},
     'B-117 antifoam dosing (AF-2, automatic on foam sensor): 02:10 2 mL, 03:05 3 mL, 03:40 foam-level alarm, 03:50 5 mL. '
     'Agitation 180 rpm and air sparge 0.5 L/min unchanged 00:00-04:30.'),
]


def _batch_context(platform: Any, tenant: str, qa: Any) -> None:
    with platform.store.transaction('demo-seed') as tx:
        tx.put(tenant, 'batch', 'B-117', {'batch_id': 'B-117', 'status': 'in_progress', 'product': 'mAb-7 (synthetic)',
               'recipe_id': 'RCP-CHO-12', 'equipment_id': 'BR-07', 'started_at': '2026-11-03T00:10:00+00:00',
               'site_id': SITE, 'synthetic': True}, expected_revision=None, action='demo_seed')
    for system, record_id, when, ids, text in CONTEXT:
        platform.evidence.ingest(qa, source_system=system, source_record_id=record_id, content=f'{text} ({NOTE})'.encode(),
                                 media_type='text/plain', site_id=SITE, event_time=when, metadata={'synthetic': True, **ids})
