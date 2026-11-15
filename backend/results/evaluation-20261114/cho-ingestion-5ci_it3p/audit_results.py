"""Audit freshly scored snapshots and a reconstruction of the public fixture."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
PACKAGES = REPO / 'backend/benchmarks/cmo_ingestion/demo'


def load(path):
    return json.loads(path.read_text())


def field_key(field):
    source = field['source']
    return (field['batch'], float(field['time']), field['parameter'], source['path'],
            source.get('sheet'), source.get('row'), source.get('column'), source.get('page'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


summary = load(ROOT / 'summary.json')
changed = load(ROOT / 'snapshots/changed.json')
key = load(PACKAGES / 'cho-changed/evaluation/answer_key.json')
strict_defects = []
for defect in key['defects']:
    def matches(issue):
        if issue['rule_code'] != defect['rule_code'] or issue.get('path') != defect.get('path'):
            return False
        for attr in ('parameter', 'batch', 'doc_type'):
            if attr in defect and issue.get(attr) != defect[attr]:
                return False
        return 'time' not in defect or float(issue.get('time', 'nan')) == float(defect['time'])
    hits = [issue for issue in changed['issues'] if matches(issue)]
    strict_defects.append({'expected': defect, 'exact_scope_detected': bool(hits), 'actual_issues': hits})

lineage = []
value_audit = []
for condition in ('calibration', 'returning', 'changed', 'unseen'):
    original = load(PACKAGES / f'cho-{condition}/evaluation/answer_key.json')
    rebuilt = load(ROOT / f'source-rebuild/cho-{condition}/evaluation/answer_key.json')
    # File byte hashes include generated PDF/XLSX metadata. Compare all semantic
    # key content, including original source values, before/after regeneration.
    before = {k: v for k, v in original.items() if k != 'files'}
    after = {k: v for k, v in rebuilt.items() if k != 'files'}
    lineage.append({'condition': condition, 'fields': len(original['fields']),
                    'nonempty_fields': sum(x['present'] for x in original['fields']),
                    'all_key_semantics_reproduced_from_pinned_archive': before == after,
                    'rebuilt_key_sha256': sha(ROOT / f'source-rebuild/cho-{condition}/evaluation/answer_key.json')})
    run = load(ROOT / f'snapshots/{condition}.json')
    actual = {field_key(x): x for x in run['measurements']}
    expected = [x for x in original['fields'] if x['present']]
    errors = []
    relative = []
    missing = []
    wrong_units = []
    for target in expected:
        found = actual.get(field_key(target))
        if found is None:
            missing.append(field_key(target))
            continue
        if found['unit'] != target['unit']:
            wrong_units.append(field_key(target))
        errors.append(abs(found['value'] - target['value']))
        if target['value']:
            relative.append(errors[-1] / abs(target['value']))
    value_audit.append({'condition': condition, 'expected_nonempty_fields': len(expected),
                        'missing_exact_source_locations': len(missing), 'wrong_units': len(wrong_units),
                        'max_absolute_error_in_mixed_native_units': max(errors, default=None),
                        'max_relative_error_for_nonzero_expected_values': max(relative, default=None),
                        'exact_python_numeric_equal_count': sum(x == 0 for x in errors)})

result = {
    'recorded_at': datetime.now(timezone.utc).isoformat(),
    'strict_defect_scope_audit': strict_defects,
    'strict_defects_detected': sum(x['exact_scope_detected'] for x in strict_defects),
    'expected_injected_defects': len(strict_defects),
    'fixture_regeneration_audit': lineage,
    'matched_value_audit': value_audit,
    'source_archive_sha256': summary['source']['archive_sha256_verified'],
    'api_verified_gate': [{'condition': row['condition'], **row['actual_verified_payload_gate']}
                          for row in summary['results']],
    'commands_with_exit_zero': [
        'env CMO_DATABASE_URL= LIFESCI_DATABASE_URL= SUPABASE_URL= SUPABASE_SERVICE_ROLE_KEY= CMO_HOSTED_INFERENCE_APPROVED=0 PYTHONPATH=backend .venv/bin/python -m benchmarks.cmo_ingestion.evaluate --packages backend/benchmarks/cmo_ingestion/demo --output backend/results/evaluation-20261114/cho-ingestion-5ci_it3p/heldout --datasets cho --calibration-protocol --configurations D --confirm-proposals',
        'env PYTHONPATH=backend .venv/bin/python backend/results/evaluation-20261114/cho-ingestion-5ci_it3p/summarize_and_calibrate.py',
        'env PYTHONPATH=backend .venv/bin/python -m benchmarks.cmo_ingestion.cho_demo --archive backend/.cache/cho-source/Dataset.zip --output backend/results/evaluation-20261114/cho-ingestion-5ci_it3p/source-rebuild',
    ],
    'report_sha256': {str(p.relative_to(ROOT)): sha(p) for p in
                      [ROOT / 'heldout/report.json', ROOT / 'summary.json']},
    'limitations': [
        'Fixture regeneration proves repeatability of the existing transformation from the pinned archive, not independent clinical/scientific validity.',
        'The fixture samples six-hour process observations, joins later inline samples to offline times in the unseen package, and invents CMO certificates, IDs and document defects.',
        'Source provenance accuracy refers to repackaged source cells; it does not score original-workbook lineage.',
        'The original scorer allows 0.5% relative value error. This additional audit records observed numeric differences separately.',
    ],
}
assert all(x['exact_scope_detected'] for x in strict_defects)
assert all(x['all_key_semantics_reproduced_from_pinned_archive'] for x in lineage)
assert all(x['missing_exact_source_locations'] == 0 and x['wrong_units'] == 0 for x in value_audit)
with (ROOT / 'audit.json').open('x') as stream:
    json.dump(result, stream, indent=2, sort_keys=True)
    stream.write('\n')
print(json.dumps({'strict_defects': result['strict_defects_detected'],
                  'regenerated_packages_match': len(lineage), 'matched_value_audit': value_audit}, indent=2))
