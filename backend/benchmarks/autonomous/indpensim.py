"""Lossless selected-variable historical projection and descriptive fault screen.

The original 2.56 GB publisher CSV remains immutable. Fault/control labels are
evaluator-only; control groups are never treated as matched interventions.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics
import zipfile
from pathlib import Path

from benchmarks.cmo_ingestion.generate import ARCHIVE_SHA, FIELDS, sha
from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package
from .generate import save


def project(archive, destination):
    from benchmarks.common.artifact_store import asset_path, publish_generated
    with asset_path(archive) as local:
        if str(destination).startswith('dagshub:'):
            import tempfile
            with tempfile.TemporaryDirectory(prefix='biodemo-project-') as directory:
                result = _project(local, Path(directory)/'data')
                result['remote_artifact'] = publish_generated(Path(directory)/'data', str(destination).split(':',1)[1])
                return result
        return _project(local, destination)


def _project(archive, destination):
    archive = Path(archive); destination = Path(destination)
    if sha(archive) != ARCHIVE_SHA: raise ValueError('publisher archive checksum mismatch')
    if destination.exists() and any(destination.iterdir()): raise ValueError('destination must be empty')
    raw = destination / 'raw'; raw.mkdir(parents=True)
    hidden = destination / 'evaluator'; hidden.mkdir(mode=0o700)
    member = 'Mendeley_data/100_Batches_IndPenSim_V3.csv'
    handles = {}; writers = {}; counts = {}; labels = {}; samples = []; summaries = {}
    try:
        with zipfile.ZipFile(archive) as zipped:
            reader = csv.reader(io.TextIOWrapper(zipped.open(member), encoding='utf-8-sig', newline=''))
            headers = next(reader)
            if headers[33:36] != ['1- No Raman spec',' 1-Raman spec recorded','2-PAT control(PAT_ref:PAT ref)']:
                raise ValueError('publisher header changed')
            headers[33:36] = [','.join(headers[33:36])]
            for _, (index, expected, _) in FIELDS.items():
                if headers[index] != expected: raise ValueError('schema mismatch: ' + expected)
            names = ['batch_id', 'time(h)', 'original_member', 'original_row'] + [f'{key}({unit})' for key, (_, _, unit) in FIELDS.items()]
            for physical_row, row in enumerate(reader, 2):
                if len(row) != len(headers): raise ValueError(f'CSV width mismatch at row {physical_row}')
                number = int(float(row[34])); batch = f'IP-{number:03d}'
                if batch not in writers:
                    handles[batch] = (raw / f'{batch}.csv').open('w', newline='')
                    writers[batch] = csv.writer(handles[batch]); writers[batch].writerow(names)
                    counts[batch] = 0
                    summaries[batch] = {'time': [], **{key: [] for key in FIELDS}}
                    labels[batch] = {'fault_reference': set(), 'fault_flag': set(), 'control_reference': set()}
                values = [row[index] for index, _, _ in FIELDS.values()]
                writers[batch].writerow([batch, row[0], member, physical_row, *values]); counts[batch] += 1
                labels[batch]['fault_reference'].add(row[31]); labels[batch]['fault_flag'].add(row[36]); labels[batch]['control_reference'].add(row[32])
                summaries[batch]['time'].append(float(row[0]))
                for key, (index, _, _) in FIELDS.items(): summaries[batch][key].append(float(row[index]))
                if counts[batch] == 1:
                    samples.append({'batch': batch, 'row': physical_row, 'raw_values': dict(zip(names[4:], values))})
    finally:
        for handle in handles.values(): handle.close()
    if set(counts) != {f'IP-{i:03d}' for i in range(1, 101)}: raise ValueError('expected 100 batches')
    save(hidden / 'labels.json', {key: {k: sorted(v) for k, v in value.items()} for key, value in labels.items()})
    save(hidden / 'raw_samples.json', samples)
    save(hidden / 'descriptive_series.json', summaries)
    manifest = {'source': 'Stephen Goldrick, IndPenSim v2', 'doi': '10.17632/pdnjz7zz5x.2',
                'license': 'CC BY 4.0', 'archive_sha256': ARCHIVE_SHA, 'original_member': member,
                'projection': 'All physical rows; 14 original process/Raman variables; original decimal strings unchanged.',
                'header_repair': 'Join original unquoted PAT header fields 34..36; no numeric-row changes.',
                'excluded_from_agent': ['fault_reference', 'fault_flag', 'control_reference', 'PAT reference'],
                'rows_by_batch': counts, 'rows': sum(counts.values()), 'files': len(counts),
                'units': {key: unit for key, (_, _, unit) in FIELDS.items()},
                'limitations': ['Selected variables, not the full 2200-channel Raman spectrum.',
                                'Groups have different historical controllers; no randomized or matched causal comparison.']}
    save(destination / 'manifest.json', manifest)
    return manifest


def investigate(destination, output):
    from benchmarks.common.artifact_store import asset_path, publish_generated
    with asset_path(destination) as local:
        if str(output).startswith('dagshub:'):
            import tempfile
            with tempfile.TemporaryDirectory(prefix='biodemo-investigate-') as directory:
                result = _investigate(local, Path(directory)/'result')
                result['remote_artifact'] = publish_generated(Path(directory)/'result', str(output).split(':',1)[1])
                return result
        return _investigate(local, output)


def _investigate(destination, output):
    destination = Path(destination); output = Path(output); output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((destination / 'manifest.json').read_text())
    store = ManufacturingStore(output / 'store')
    coverage = ingest_package(destination / 'raw', store, access_scope='indpensim', document_backend='pypdf')
    tools = ManufacturingTools(store, scopes=('indpensim',))
    # Fixed descriptive screen, chosen before examining evaluator fault labels.
    # It deliberately reports ordinary control-group differences as possible
    # false positives; the evaluator measures them rather than masking them.
    queries = {}; series = {}
    for metric in ('temperature(K)', 'pH(pH)', 'dissolved_oxygen(mg/L)', 'product(g/L)'):
        query = tools.query_data(sql=f"SELECT entity_id, min(value_number) AS minimum, max(value_number) AS maximum, avg(value_number) AS mean, arg_max(value_number,time_value) AS final_observed, max(time_value) AS last_observed_hour FROM observations WHERE name = '{metric}' GROUP BY entity_id", limit=1000)
        queries[metric] = query
        series[metric] = {r[0]: {'min': r[1], 'max': r[2], 'mean': r[3], 'final': r[4]} for r in query['rows']}
    flags = []; details = []
    for i in range(1, 101):
        batch = f'IP-{i:03d}'; reasons = []
        for metric in ('temperature(K)', 'pH(pH)', 'dissolved_oxygen(mg/L)'):
            population = [series[metric][f'IP-{j:03d}']['mean'] for j in range(1, 31) if f'IP-{j:03d}' in series[metric]]
            if batch not in series[metric] or not population: continue
            center = statistics.median(population); mad = statistics.median(abs(x - center) for x in population)
            value = series[metric][batch]['mean']
            if abs(value - center) > max(6 * 1.4826 * mad, .01): reasons.append(metric)
        if reasons:
            flags.append(batch); details.append({'batch': batch, 'departures': reasons,
                                               'interpretation': 'Descriptive group-relative departure; not a verified fault or cause.'})
    labels = json.loads((destination / 'evaluator/labels.json').read_text())
    # Publisher batch groups identify 91..100 as faults. Keep those labels out of tools.
    expected = {batch for batch, label in labels.items() if any(float(v) > 0 for v in label['fault_flag'])}
    if expected != {f'IP-{i:03d}' for i in range(91, 101)}: raise ValueError('Source fault flags disagree with documented historical groups')
    predicted = set(flags)
    sample_values = json.loads((destination / 'evaluator/raw_samples.json').read_text())
    checks = []
    sample_batches = [s['batch'] for s in sample_values[:8]]
    sampled_rows = store.select('SELECT * FROM observations WHERE source_row=2 AND entity_id IN (' +
                                ','.join('?' for _ in sample_batches) + ')', sample_batches, scopes=('indpensim',))
    sampled_lookup = {(r['entity_id'], r['name']): r for r in sampled_rows}
    for sample in sample_values[:8]:
        # Compare source-preserved decimals against ingested numerical values.
        for name, value in sample['raw_values'].items():
            row = sampled_lookup.get((sample['batch'], name))
            checks.append(bool(row and float(row['value_number']) == float(value)))
    correlations = {}
    for metric in ('temperature(K)', 'pH(pH)', 'dissolved_oxygen(mg/L)'):
        batches = sorted(set(series[metric]) & set(series['product(g/L)']))
        correlations[metric] = {'pearson_r': statistics.correlation([series[metric][b]['mean'] for b in batches],
                                                                  [series['product(g/L)'][b]['final'] for b in batches]),
                                'n_batches': len(batches), 'outcome': 'final observed penicillin concentration (g/L)',
                                'limitation': 'Descriptive confounded association across historical controllers and faults; not causal.'}
    result = {'status': 'completed', 'method': 'deterministic descriptive screen; not Prime Agent',
              'descriptive_correlations': correlations,
              'indexed_source_count': len([s for s in store.visible_sources(scopes=('indpensim',)) if s['extraction_status'] == 'indexed']),
              'source_manifest': manifest, 'ingestion': coverage, 'queries': queries, 'findings': details,
              'metrics': {'fault_group_recall': len(predicted & expected) / len(expected),
                          'fault_group_precision': len(predicted & expected) / len(predicted) if predicted else None,
                          'false_positive_batches': sorted(predicted - expected), 'missed_fault_batches': sorted(expected - predicted),
                          'sampled_numeric_value_accuracy': sum(checks) / len(checks) if checks else None,
                          'sampled_fields_checked': len(checks), 'suspicious_interval_accuracy': 'not_evaluated',
                          'causal_accuracy': 'not_evaluated'},
              'optimization': {'status': 'not_evaluated', 'reason': 'Requires separately passed simulator feasibility gate and matched-seed experiments.'},
              'limitations': ['Labels describe batch-level fault groups, not independently annotated fault onset intervals.',
                              'Full-batch means miss transient faults. Controller differences can produce false positives.',
                              'No concentration difference is called a yield improvement.']}
    save(output / 'investigation.json', result)
    print(json.dumps({'ingestion': {k: v for k, v in coverage.items() if k != 'routes'}, 'metrics': result['metrics']}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); commands = parser.add_subparsers(dest='command', required=True)
    extract = commands.add_parser('project'); extract.add_argument('archive'); extract.add_argument('destination')
    analyze = commands.add_parser('investigate'); analyze.add_argument('destination'); analyze.add_argument('output')
    args = parser.parse_args()
    if args.command == 'project': print(json.dumps(project(args.archive, args.destination)))
    else: investigate(args.destination, args.output)
