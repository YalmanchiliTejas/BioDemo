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
    rows = []
    with LIMS.open(encoding='utf-8') as stream:
        for line, record in enumerate(csv.DictReader(stream), start=2):
            for column, (parameter, unit) in COLUMNS.items():
                raw = (record.get(column) or '').strip()
                if not raw:
                    continue
                rows.append({'id': f"{record['Sample ID']}-{parameter}", 'source_id': 'lims-september', 'batch': record['Batch'],
                             'time': record['Time (h)'], 'parameter': parameter, 'value': float(raw), 'unit': unit,
                             'value_raw': raw, 'unit_raw': unit, 'status': 'auto_accepted',
                             'source': {'path': LIMS.name, 'row': line}, 'source_sha256': 'synthetic-sample'})
    content = json.dumps({'schema_version': 'platform-verified-cmo-1', 'run_id': 'demo-september', 'synthetic': True,
                          'cmo': 'Northfield Biologics (synthetic)', 'delivery_name': 'September (synthetic sample)',
                          'guarantee': {'holds': True, 'checks': []}, 'measurements': rows}, sort_keys=True).encode()
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
    platform.cases.open(qa, 'DEV-31', visitor, SEED_QA, SITE)
    platform.cases.add_timeline_event(qa, 'DEV-31', '2026-11-03T04:10:00+00:00',
                                      f'Foaming at 4 h in B-117 on BR-07; DO below 30 %; antifoam lot L-8812 in use. ({NOTE})')

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
    return {'dataset_id': dataset['evidence_id'], 'cases': ['DEV-12', 'DEV-19', 'DEV-31'], 'site_id': SITE, 'persona': persona}
