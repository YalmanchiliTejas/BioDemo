"""Fresh fourth-package score and preserved snapshots for the existing CHO evaluator.

Run from the repository root with PYTHONPATH=backend. The underlying pipeline
and scorer are unchanged. Automated mapping confirmations are study protocol,
not human review; unresolved issues and verification flags remain untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

for name in ('CMO_DATABASE_URL', 'LIFESCI_DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'):
    os.environ[name] = ''
os.environ['CMO_HOSTED_INFERENCE_APPROVED'] = '0'

from benchmarks.cmo_ingestion.evaluate import confirm_in_place, implementation_hash, score
from fastapi import HTTPException
from src.manufacturing_data.cmo.api import router
from src.manufacturing_data.cmo.pipeline import IngestionService
from src.manufacturing_data.cmo import quality

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
PACKAGES = REPO / 'backend/benchmarks/cmo_ingestion/demo'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    started = time.monotonic()
    code_hash = implementation_hash()
    catalog = [x for x in json.loads((PACKAGES / 'catalog.json').read_text()) if x['dataset'] == 'cho']
    input_hashes = {str(p.relative_to(PACKAGES)): sha(p) for item in catalog
                    for p in sorted((PACKAGES / item['id']).rglob('*'))
                    if p.is_file() and p.name != '.DS_Store'}
    archive = REPO / 'backend/.cache/cho-source/Dataset.zip'
    manifest = json.loads((REPO / 'backend/benchmarks/cho/source_manifest.json').read_text())
    assert sha(archive) == manifest['archive_sha256']
    report = json.loads((ROOT / 'heldout/report.json').read_text())
    assert report['implementation_sha256'] == code_hash
    calibration = next(x for x in catalog if x['condition'] == 'calibration')
    service = IngestionService(ROOT / 'calibration-store')
    initial = service.run(PACKAGES / calibration['id'] / 'raw', calibration['cmo'], 'D', synthetic=False)
    runs = [('calibration', initial)]
    if initial['status'] == 'complete' and confirm_in_place(service, initial):
        confirmed = service.run(PACKAGES / calibration['id'] / 'raw', calibration['cmo'], 'D', synthetic=False)
        runs.append(('calibration+confirmed', confirmed))
    # Source keys enter only this scoring phase, after extraction is complete.
    keys = {item['condition']: json.loads((PACKAGES / item['id'] / 'evaluation/answer_key.json').read_text())
            for item in catalog}
    for item in catalog:
        for f in keys[item['condition']]['files']:
            assert sha(PACKAGES / item['id'] / 'raw' / f['path']) == f['sha256']
    rows = [{'configuration': 'D', 'dataset': 'cho', 'condition': label, **score(run, keys['calibration'])}
            for label, run in runs] + report['results']
    apis = {}
    condition_timing = {}
    snapshots = ROOT / 'snapshots'
    snapshots.mkdir(exist_ok=False)
    for row in rows:
        condition = row['condition'].split('+')[0]
        if condition == 'calibration':
            owner = service
        else:
            owner = IngestionService(ROOT / 'heldout/stores' / f'D-cho-{condition}')
        run = owner.get(row['run_id'])
        snapshot = snapshots / f'{row["condition"]}.json'
        write(snapshot, run)
        row['snapshot'] = str(snapshot.relative_to(REPO))
        row['service_root'] = str(owner.root.relative_to(REPO))
        row['started_at'] = run['started_at']
        row['completed_at'] = run.get('completed_at')
        row['verified_package'] = run['summary']['verified_package']
        row['audit_valid'] = owner.verify_audit()
        row['guarantee'] = quality.guarantee(run, audit_valid=row['audit_valid'])
        row['open_issue_counts'] = dict(Counter(i['rule_code'] for i in run['issues'] if i['status'] == 'open'))
        if condition not in apis:
            os.environ['CMO_INGESTION_ROOT'] = str(owner.root)
            apis[condition] = router(REPO / 'backend')
            executions = owner.runs()
            target_runs = [x for x in executions if x['configuration'] == 'D']
            calibration_runs = [x for x in executions if x['configuration'] == 'preview']
            parse = datetime.fromisoformat
            condition_timing[condition] = {
                'calibration_service_seconds': sum(x['runtime_seconds'] for x in calibration_runs),
                'calibration_run_ids': [x['id'] for x in calibration_runs],
                'target_service_seconds_including_confirmation_reruns': sum(x['runtime_seconds'] for x in target_runs),
                'all_service_seconds': sum(x['runtime_seconds'] for x in executions),
                'execution_span_seconds': (max(parse(x['completed_at']) for x in executions)
                                           - min(parse(x['started_at']) for x in executions)).total_seconds(),
                'execution_span_includes': 'Calibration, template confirmation and target reruns; excludes final scoring/export and process startup.',
            }
        try:
            payload = apis[condition].verified_payload(run['id'], tenant='benchmark')
            row['actual_verified_payload_gate'] = {'status_code': 200, 'verified': payload['verified']}
        except HTTPException as exc:
            row['actual_verified_payload_gate'] = {'status_code': exc.status_code, 'detail': exc.detail}
        row['field_identity_precision'] = row['matched_fields'] / row['extracted_fields']
        row['field_identity_f1'] = 2 * row['matched_fields'] / (row['expected_present_fields'] + row['extracted_fields'])
    primary = [r for r in rows if '+' not in r['condition']]
    tp = sum(r['matched_fields'] for r in primary)
    expected = sum(r['expected_present_fields'] for r in primary)
    predicted = sum(r['extracted_fields'] for r in primary)
    heldout = [r for r in primary if r['condition'] != 'calibration']
    heldout_tp = sum(r['matched_fields'] for r in heldout)
    heldout_expected = sum(r['expected_present_fields'] for r in heldout)
    heldout_predicted = sum(r['extracted_fields'] for r in heldout)
    summary = {
        'protocol': 'existing-cmo-1-plus-fresh-calibration-score',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'scope': '24 cultivation runs in 12 real CHO experiments, repackaged into 4 fictional CMO deliveries and 24 files.',
        'disclosure': calibration['disclosure'],
        'source': {'doi': manifest['doi'], 'source_url': manifest['source_url'], 'license': manifest['license'],
                   'archive_path': str(archive.relative_to(REPO)), 'archive_sha256_verified': manifest['archive_sha256']},
        'python': platform.python_version(), 'implementation_sha256': code_hash,
        'input_sha256': input_hashes,
        'timing_by_condition': condition_timing,
        'heldout_primary_aggregate': {
            'cultivations': 18, 'packages': len(heldout), 'raw_files': 16,
            'expected_present_fields': heldout_expected, 'extracted_fields': heldout_predicted,
            'matched_fields': heldout_tp, 'recall': heldout_tp / heldout_expected,
            'precision': heldout_tp / heldout_predicted,
            'f1': 2 * heldout_tp / (heldout_predicted + heldout_expected),
            'verified_packages': sum(r['verified_package'] for r in heldout),
            'verified_payload_409_count': sum(r['actual_verified_payload_gate']['status_code'] == 409 for r in heldout),
            'target_service_seconds': sum(r['end_to_end_seconds'] for r in heldout),
            'calibration_service_seconds': sum(condition_timing[r['condition']]['calibration_service_seconds'] for r in heldout),
        },
        'scoring': {'field_recall': 'Matched nonempty expected source fields / nonempty expected source fields.',
                    'value_and_unit_accuracy': 'Correct value with exact canonical unit / matched fields; math.isclose(rtol=0.005, atol=1e-30).',
                    'field_identity_precision': 'Matched expected fields / all extracted fields; the injected duplicate contributes seven unmatched fields.',
                    'source_provenance_accuracy': 'Exact spreadsheet sheet/row/header or CSV row/header; PDF page + field identity. Original-workbook-to-fixture lineage is not this metric.',
                    'defect_detection': 'Matching rule and path; the evaluator does not enforce batch identity for the missing-CoA defect.'},
        'primary_aggregate': {'packages': len(primary), 'expected_present_fields': expected,
                              'extracted_fields': predicted, 'matched_fields': tp,
                              'recall': tp / expected, 'precision': tp / predicted,
                              'f1': 2 * tp / (predicted + expected),
                              'silent_errors': sum(r['silent_errors'] for r in primary),
                              'silent_omissions': sum(r['silent_omissions'] for r in primary),
                              'verified_packages': sum(r['verified_package'] for r in primary),
                              'model_calls': sum(r['model_calls'] for r in primary),
                              'inference_cost_usd': sum(r['inference_cost_usd'] for r in primary)},
        'results': rows,
        'limitations': [
            'No paid model calls; configuration D is deterministic, not agent reasoning.',
            'Existing fixture is scored freshly; all fixture file hashes and the pinned source archive hash are verified.',
            'Returning/changed use public-vocabulary mappings confirmed automatically on disjoint calibration runs.',
            '+confirmed rows simulate accepting every layout proposal without edits; no human review or timing study occurred.',
            'Calibration is a descriptive fourth-package score, not an independent held-out case.',
            'The existing heldout/report.json scope text mentions 100 batches and Raman channels; that static text does not apply to the CHO-only selection.',
            'Ingestion keys and generator share task semantics and artificial layouts; these are not blinded real enterprise deliveries.',
            'No defect false-positive rate, scientific diagnosis, prediction, action effectiveness or production latency is validated.',
            'Missing cells and other open issues remain review blockers. No verification flags or review receipts were fabricated.'
        ],
        'supplement_runtime_seconds': time.monotonic() - started,
    }
    assert implementation_hash() == code_hash
    assert all(sha(PACKAGES / path) == value for path, value in input_hashes.items())
    summary['code_and_inputs_unchanged'] = True
    write(ROOT / 'summary.json', summary)
    print(json.dumps(summary['primary_aggregate'], indent=2))


if __name__ == '__main__':
    main()
