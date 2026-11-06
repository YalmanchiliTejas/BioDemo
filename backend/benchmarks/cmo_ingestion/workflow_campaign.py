"""Repeat real local ingestion with hidden-key scoring and bounded temporary storage.

This measures the deterministic ingestion service, not LLM or deployed API latency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import resource
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.cmo_ingestion.evaluate import implementation_hash, score
from src.manufacturing_data.cmo.pipeline import IngestionService
from src.manufacturing_data.cmo.persistence import set_tenant

set_tenant('benchmark')  # ponytail: stores are tenant-scoped; benchmarks run as one fixed tenant


def quantiles(values):
    ordered = sorted(values)
    return {f'p{p}': ordered[math.ceil(p / 100 * len(ordered)) - 1] if ordered else None
            for p in (50, 90, 95, 99)}


def run(packages: Path, output: Path, repeats: int):
    if repeats < 1:
        raise ValueError('repeats must be positive')
    output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads((packages / 'catalog.json').read_text())
    calibration = next(c for c in catalog if c['dataset'] == 'cho' and c['condition'] == 'calibration')
    cases = [next(c for c in catalog if c['dataset'] == 'cho' and c['condition'] == condition)
             for condition in ('unseen', 'returning', 'changed')]
    # Freeze every input byte before any execution. Answer keys never enter service inputs.
    files = {str(p.relative_to(packages)): hashlib.sha256(p.read_bytes()).hexdigest()
             for c in [calibration, *cases] for p in sorted((packages / c['id']).rglob('*')) if p.is_file()}
    code_hash = implementation_hash()
    schedule = [(item, rep + 1) for rep in range(repeats) for item in cases]
    random.Random(20261031).shuffle(schedule)
    protocol = {
        'version': 'local-ingestion-workflow-v1', 'started_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Actual deterministic IngestionService, local disk persistence; no API/network/model calls.',
        'configuration': 'D', 'python': platform.python_version(), 'platform': platform.platform(),
        'concurrency': 1, 'repeats_per_case': repeats, 'distinct_packages': len(cases),
        'implementation_sha256': code_hash, 'input_sha256': files,
        'schedule': [{'package_id': c['id'], 'repeat': rep} for c, rep in schedule],
        'timing': 'Target service.run only, including parse/validation/persistence. Setup and calibration excluded.',
        'calibration': 'Automated confirmation on a disjoint calibration package; no observed human review.',
        'cache': 'Fresh service/store per attempt; OS filesystem and interpreter caches uncontrolled/warm after first use.',
        'limits': ['Three correlated packages, not independent manufacturing incidents.',
                   'Empirical percentiles are exploratory local service measurements, not production agent SLOs.',
                   'No annotation adjudication, scientific root-cause evaluation or human-time study.',
                   'Only configuration D: paid model/OCR configurations excluded.'],
    }
    (output / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    rows = []
    with (output / 'attempts.jsonl').open('x') as ledger:
        for index, (item, repeat) in enumerate(schedule):
            row = {'package_id': item['id'], 'condition': item['condition'], 'repeat': repeat,
                   'configuration': 'D', 'model_calls': 0}
            started = None
            try:
                with tempfile.TemporaryDirectory(prefix='sievance-ingestion-trial-') as temporary:
                    service = IngestionService(Path(temporary) / 'store')
                    if item['condition'] != 'unseen':
                        prepared = service.run(packages / calibration['id'] / 'raw', calibration['cmo'],
                                               'preview', synthetic=calibration['synthetic'])
                        if prepared['status'] != 'complete':
                            raise RuntimeError('Calibration did not complete')
                        for layout in prepared['layouts']:
                            mapping = layout['mapping']
                            if mapping['columns'] and mapping['batch_column'] and mapping['time_column']:
                                service.confirm_template(prepared['id'], layout['fingerprint'], mapping,
                                    'automated-study-protocol', 'Automated disjoint calibration confirmation; not human review.',
                                    origin='study_protocol')
                    started = time.monotonic()
                    result = service.run(packages / item['id'] / 'raw', item['cmo'], 'D', synthetic=item['synthetic'])
                    row['elapsed_seconds'] = time.monotonic() - started
                    # Scoring happens strictly after the pipeline has returned.
                    key = json.loads((packages / item['id'] / 'evaluation' / 'answer_key.json').read_text())
                    for file in key['files']:
                        actual = hashlib.sha256((packages / item['id'] / 'raw' / file['path']).read_bytes()).hexdigest()
                        if actual != file['sha256']:
                            raise ValueError('Source does not match frozen answer key')
                    metrics = score(result, key)
                    row.update(status='completed' if result['status'] == 'complete' else 'failed', metrics=metrics)
                    if result['status'] == 'complete':
                        tp, predicted, expected = metrics['matched_fields'], metrics['extracted_fields'], metrics['expected_present_fields']
                        row['field_identity'] = {'tp': tp, 'fp': predicted - tp, 'fn': expected - tp,
                            'precision': tp / predicted if predicted else None,
                            'recall': tp / expected if expected else None,
                            'f1': 2 * tp / (predicted + expected) if predicted + expected else None}
            except Exception as exc:
                row.update(status='error', error_type=type(exc).__name__, error=str(exc)[:500])
                if started is not None:
                    row.setdefault('elapsed_seconds', time.monotonic() - started)
            rows.append(row)
            ledger.write(json.dumps(row, sort_keys=True) + '\n')
            ledger.flush()
            if (index + 1) % 10 == 0:
                print(json.dumps({'attempts': index + 1, 'planned': len(schedule),
                                  'failures': sum(r['status'] != 'completed' for r in rows)}), flush=True)
    unchanged = implementation_hash() == code_hash and all(
        hashlib.sha256((packages / p).read_bytes()).hexdigest() == digest for p, digest in files.items())
    summary = {'protocol': protocol['version'], 'integrity_pass': unchanged, 'families': {},
               'new_paid_inference_calls': 0,
               'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if platform.system() == 'Darwin' else 1024)}
    for item in cases:
        selected = [r for r in rows if r['package_id'] == item['id']]
        completed = [r for r in selected if r['status'] == 'completed']
        summary['families'][item['condition']] = {
            'attempts': len(selected), 'completed': len(completed), 'failed': len(selected) - len(completed),
            'completion_rate': len(completed) / len(selected),
            'completed_service_latency_seconds': quantiles([r['elapsed_seconds'] for r in completed]),
            'maximum_completed_seconds': max((r['elapsed_seconds'] for r in completed), default=None),
            'first_execution_metrics': completed[0]['metrics'] if completed else None,
            'first_execution_field_identity': completed[0]['field_identity'] if completed else None,
            'repeated_metrics_identical': all(r.get('field_identity') == completed[0]['field_identity'] for r in completed) if completed else None,
        }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not unchanged:
        raise RuntimeError('Code or inputs changed during campaign: results invalid')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=100)
    args = parser.parse_args()
    result = run(args.packages.resolve(), args.output.resolve(), args.repeats)
    print(json.dumps(result, indent=2))
