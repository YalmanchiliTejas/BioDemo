"""Turn each public dataset into what the product works on: deliveries, batch records, recorded usage, records.

Nothing here goes through file ingestion. The values are loaded as deliveries that are still in review, exactly as
recorded by their publishers, so these benchmarks measure what the product does with data once it has it. Reading
messy files is measured separately (benchmarks/cmo_ingestion).

What is real and what is added is stated per world, and repeated in the report:
- measurements, batch attributes, raw-material lots and recall texts are the publishers' own;
- batch and lot names get a readable prefix where the publisher anonymised them to bare integers;
- "requirements" (specifications) are added by the benchmark so that a gap has something to be judged against.
"""
from __future__ import annotations

import csv
import io
import json
import os
import random
import re
import zipfile
from collections import defaultdict
from typing import Any

from . import datasets

TENANT, ACTOR, MES = 'skill-benchmark', 'benchmark-engineer', 'benchmark-mes'
ISOLATED = ('CMO_DATABASE_URL', 'LIFESCI_DATABASE_URL', 'LIFESCI_MIGRATION_DATABASE_URL', 'SUPABASE_URL',
            'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_DB_URL', 'SUPABASE_ANON_KEY')
CHO_OFFLINE = ('VCD Mean (cells/mL)', 'Viability Mean (%)', 'Glucose (g/L)', 'Lactate (g/L)', 'Ammonium (mM)', 'Osmolality (mOsmol/kg)')
CHO_INLINE = ('pH', 'Dissolved O2 (% air sat)', 'Temperature (°C)', 'Liquid volume (L)', 'Dissolved CO2 (%-sat)')
HEADER = re.compile(r'^(.*?)\s*\(([^()]*)\)\s*$')


def platform():
    for name in ISOLATED:  # never a configured production database or project
        os.environ[name] = ''
    from src.lifesci.container import Platform
    from src.lifesci.store import RecordStore
    return Platform(RecordStore(), providers={})


def person(p, site: str):
    p.identity.assign_role(TENANT, ACTOR, 'msat', site_id=site)
    p.identity.assign_role(TENANT, MES, 'manufacturing_systems', site_id=site)
    return p.identity.context_for(TENANT, ACTOR)


def share(p, ctx, site: str, name: str, rows: list[dict], note: str) -> dict[str, Any]:
    """One delivery, still in review: the publisher's values, nothing accepted on anyone's behalf."""
    from src.lifesci.cmo_datasets import share_provisional
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    payload = {'schema_version': 'provisional-cmo-1', 'run_id': slug, 'cmo': 'public dataset', 'verified': False,
               'package_id': slug, 'delivery_name': name, 'completed_at': '2026-01-01T00:00:00Z', 'superseded_by': None,
               'disclosure': note, 'coverage': {},
               'review': {'verified_package': False, 'pending_values': len(rows), 'rejected_values': 0, 'open_issues': 0,
                          'open_issue_counts': {}},
               'measurements': rows}
    saved = share_provisional(p, ctx, payload, site)
    return {'id': saved['evidence_id'], 'revision': saved['revision'], 'name': name, 'values': len(rows)}


def split_header(header: str) -> tuple[str, str | None]:
    """"Glucose (g/L)" -> ("Glucose", "g/L"). A header with no unit in brackets keeps its name and has no unit,
    except pH, whose name is its scale."""
    match = HEADER.match(header)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return header.strip(), 'pH' if header.strip() == 'pH' else None


def _number(text: str) -> float | None:
    try:
        value = float(text)
        return value if value == value and abs(value) != float('inf') else None
    except (TypeError, ValueError):
        return None


# --- CHO cultivations -------------------------------------------------------------------------------------------
def cho_world() -> dict[str, Any]:
    """24 real cultivations. Per experiment: the offline analyses of both reactors as one delivery, and the inline
    process data thinned to every tenth minute as another. One experiment is also loaded at its full one-minute
    resolution, which is larger than a direct task accepts: that case is there to show the limit."""
    site = 'CHO-LAB'
    p = platform()
    ctx = person(p, site)
    archive = zipfile.ZipFile(datasets.path('cho', 'Dataset.zip'))
    reference: dict[tuple[str, str], dict[float, float]] = defaultdict(dict)   # (batch, parameter) -> {hours: value}
    units: dict[str, str | None] = {}
    experiments: dict[str, dict[str, Any]] = {}
    full: dict[tuple[str, str], dict[float, float]] = defaultdict(dict)
    for member in sorted(n for n in archive.namelist() if n.endswith('.csv')):
        stem = member.rsplit('/', 1)[-1][:-4]                 # EXP001_batch_R01_inline
        exp, mode, reactor, kind = stem.split('_')
        batch = f'{exp}-{reactor}'
        rows = list(csv.reader(io.TextIOWrapper(archive.open(member), encoding='utf-8-sig')))
        header, body = rows[0], rows[1:]
        wanted = CHO_OFFLINE if kind == 'offline' else CHO_INLINE
        entry = experiments.setdefault(exp, {'mode': mode, 'batches': [], 'offline': [], 'inline': [], 'inline_full': []})
        if batch not in entry['batches']:
            entry['batches'].append(batch)
        for column in wanted:
            if column not in header:
                continue
            index = header.index(column)
            name, unit = split_header(column)
            units[name] = unit
            for n, row in enumerate(body):
                t, v = _number(row[0]), _number(row[index]) if index < len(row) else None
                if t is None or v is None:
                    continue
                item = {'id': f'{stem}:{n + 2}:{index}', 'batch': batch, 'time': t, 'parameter': name, 'value': v, 'unit': unit,
                        'status': 'needs_review', 'source': {'path': member.rsplit('/', 1)[-1], 'row': n + 2, 'column': column}}
                if kind == 'offline':
                    entry['offline'].append(item)
                    reference[(batch, name)][t] = v
                else:
                    if exp == 'EXP001':
                        entry['inline_full'].append(item)
                        full[(batch, name)][t] = v
                    if n % 10 == 0:
                        entry['inline'].append(item)
                        reference[(batch, name)][t] = v
    note = 'CHO-K1 cultivations, Zenodo 10.5281/zenodo.20829178 (CC BY 4.0); publisher-aligned values, not yet reviewed.'
    deliveries = {}
    for exp, entry in experiments.items():
        deliveries[(exp, 'offline')] = share(p, ctx, site, f'{exp} offline analyses', entry['offline'], note)
        deliveries[(exp, 'inline')] = share(p, ctx, site, f'{exp} process data every 10 minutes', entry['inline'], note)
    deliveries[('EXP001', 'inline_full')] = share(p, ctx, site, 'EXP001 process data every minute',
                                                 experiments['EXP001']['inline_full'], note)
    return {'p': p, 'ctx': ctx, 'site': site, 'deliveries': deliveries, 'reference': reference, 'reference_full': full,
            'units': units, 'experiments': {e: {'mode': v['mode'], 'batches': v['batches']} for e, v in experiments.items()},
            'added': 'Nothing added. Inline data is thinned to every tenth minute, except one experiment kept at one minute.'}


# --- tablet manufacturing ------------------------------------------------------------------------------------------
TABLET_WITH_UNITS = ('Drug release average (%)', 'Drug release min (%)')      # unit stated in the publisher's header
TABLET_NO_UNITS = ('tbl_min_weight', 'tbl_max_weight', 'api_content', 'api_total_impurities', 'api_l_impurity', 'batch_yield')
MATERIALS = (('api_batch', 'API'), ('smcc_batch', 'SMCC'), ('lactose_batch', 'LACTOSE'), ('starch_batch', 'STARCH'))


def tablet_world(without_usage_every: int = 20) -> dict[str, Any]:
    """1,005 real production batches of one manufacturer: laboratory results, product code, strength, batch size and
    the raw-material lots of each batch.

    Added by the benchmark, and only this: readable names for the anonymised batches and lots ("TB-0001", "API-2");
    a specification per laboratory result, so a missing result can be judged as a gap; and no usage record for
    every twentieth batch, as if its batch record had not been received."""
    site = 'TABLET-PLANT'
    p = platform()
    ctx = person(p, site)
    mes = p.identity.context_for(TENANT, MES)
    read = lambda name: list(csv.DictReader(open(datasets.path('tablet', name), encoding='utf-8-sig'), delimiter=';'))
    laboratory, process = read('Laboratory.csv'), {r['batch']: r for r in read('Process.csv')}
    batches, with_units, no_units, usage, missing = {}, [], [], defaultdict(set), defaultdict(set)
    recorded = set()
    for n, row in enumerate(laboratory):
        name = f"TB-{int(row['batch']):04d}"
        batches[name] = {'code': row['code'], 'strength': row['strength'], 'size': row['size'], 'start': row['start']}
        for column in TABLET_WITH_UNITS:
            value = _number(process[row['batch']].get(column))
            parameter, unit = split_header(column)
            if value is not None:
                with_units.append({'id': f'p:{name}:{parameter}', 'batch': name, 'time': 0.0, 'parameter': parameter, 'value': value,
                                   'unit': unit, 'status': 'needs_review', 'source': {'path': 'Process.csv', 'row': n + 2, 'column': column}})
            else:
                missing[parameter].add(name)
        for column in TABLET_NO_UNITS:
            value = _number(row.get(column))
            if value is not None:
                # The publisher's file states no unit for this column, so none is recorded here.
                no_units.append({'id': f'l:{name}:{column}', 'batch': name, 'time': 0.0, 'parameter': column, 'value': value,
                                 'unit': None, 'status': 'needs_review', 'source': {'path': 'Laboratory.csv', 'row': n + 2, 'column': column}})
            else:
                missing[column].add(name)
        lots = [f'{prefix}-{row[column]}' for column, prefix in MATERIALS if row.get(column)]
        p.execution.project_external(mes, 'batch', name, {
            'batch_id': name, 'product': f"code {row['code']}, {row['strength']}", 'status': 'completed',
            'scale': f"{row['size']} tablets"}, source_system='tablet-mes', source_ref=f'Laboratory.csv#{n + 2}', site_id=site)
        if n % without_usage_every != without_usage_every - 1:
            recorded.add(name)
            for lot in lots:
                usage[lot].add(name)
            with p.store.transaction(ACTOR) as tx:  # one executed step, in the shape the execution service records
                tx.put(TENANT, 'procedure_instance', f'run-{name}', {'site_id': site, 'context': {'batch_id': name}, 'status': 'completed'},
                       expected_revision=None, action='load_public_dataset')
                tx.put(TENANT, 'step_execution', f'run-{name}:dispense:1', {
                    'instance_id': f'run-{name}', 'step_id': 'dispense', 'performed_at': None,
                    'resources': {'lots': [{'lot_id': lot} for lot in lots], 'equipment': []}},
                    expected_revision=None, action='load_public_dataset')
    note = 'Tablet manufacturing data, figshare 10.6084/m9.figshare.c.5645578 (CC BY 4.0); batch-level values, not yet reviewed.'
    deliveries = {'with_units': share(p, ctx, site, 'Drug release results', with_units, note),
                  'no_units': share(p, ctx, site, 'Laboratory results without stated units', no_units, note)}
    for parameter in [split_header(c)[0] for c in TABLET_WITH_UNITS] + list(TABLET_NO_UNITS):
        p.specifications.create(ctx, site_id=site, parameter=parameter, low=0.0, source='manual',
                                source_ref='benchmark requirement: a result is expected for every batch',
                                reason='Added by the skill benchmark; not a real limit')
    return {'p': p, 'ctx': ctx, 'site': site, 'deliveries': deliveries, 'batches': batches, 'usage': usage, 'recorded': recorded,
            'missing': missing, 'values': {(r['batch'], r['parameter']): r['value'] for r in with_units + no_units},
            'added': 'Readable names for anonymised batches and lots; one specification per laboratory result; '
                     f'no usage record for every {without_usage_every}th batch.'}


# --- recall records ---------------------------------------------------------------------------------------------------
LOT = re.compile(r'\b[Ll]ots?\s*(?:#|[Nn]o\.?|[Nn]umbers?)?\s*:?\s*([A-Za-z0-9][A-Za-z0-9/\-]{3,19})(?![A-Za-z0-9/\-])')


def lot_format(lot: str) -> str:
    if re.fullmatch(r'\d+', lot):
        return 'lot is digits only'
    if re.search(r'[/\-]', lot):
        return 'lot has a separator'
    if re.fullmatch(r'[A-Za-z]{1,8}\d{1,8}', lot):
        return 'lot is letters then digits'
    return 'lot starts with a digit' if lot[0].isdigit() else 'lot mixes letters and digits'


def recall_world(records: int = 500, queries: int = 150, seed: int = 417) -> dict[str, Any]:
    """Real FDA drug recall reports as records at one site. Lot numbers appear only inside free text, in whatever
    form the firm wrote them. Each query is a lot taken from the text of one report; the reference is every sampled
    report whose text contains that lot as a whole token."""
    site = 'RECALLS'
    p = platform()
    ctx = person(p, site)
    archive = zipfile.ZipFile(datasets.path('fda_drug_recalls', 'drug-enforcement.json.zip'))
    everything = json.load(archive.open(archive.namelist()[0]))['results']
    rng = random.Random(seed)
    sample = rng.sample([r for r in everything if r.get('code_info') and r.get('recall_number')], records)
    ids = {}
    for record in sample:
        saved = p.evidence.ingest(ctx, source_system='openfda-drug-enforcement', source_record_id=record['recall_number'],
                                  content=json.dumps(record, sort_keys=True).encode(), media_type='application/json', site_id=site,
                                  event_time=None, metadata={
                                      'recall_number': record['recall_number'], 'code_info': record['code_info'][:4000],
                                      'reason_for_recall': record.get('reason_for_recall', '')[:1000],
                                      'product_description': record.get('product_description', '')[:500]})
        ids[record['recall_number']] = saved['evidence_id']
    lots = {}
    for record in sample:
        found = LOT.search(record['code_info'])
        if found and any(c.isdigit() for c in found.group(1)) and found.group(1).lower() not in ('number', 'numbers'):
            lots.setdefault(found.group(1), record['recall_number'])
    chosen = rng.sample(sorted(lots), min(queries, len(lots)))
    token = lambda lot: re.compile(r'(?<![A-Za-z0-9])' + re.escape(lot) + r'(?![A-Za-z0-9])')
    reference = {lot: sorted(ids[r['recall_number']] for r in sample if token(lot).search(r['code_info'])) for lot in chosen}
    return {'p': p, 'ctx': ctx, 'site': site, 'queries': chosen, 'reference': reference, 'records': len(sample),
            'added': 'Nothing added. A seeded sample of the reports; lots are taken from the reports\' own text.'}
