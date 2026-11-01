"""Summarize executed workflow evidence without substituting tests for agent scores."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


def summarize(root, public_output=None):
    ingestion = json.loads((root / 'ingestion-repeated/summary.json').read_text())
    baseline = []
    agent = []
    reservations = []
    for suite in sorted(root.iterdir()):
        if not suite.is_dir():
            continue
        for path in sorted((suite / 'runs').glob('*/run.json')):
            run = json.loads(path.read_text())
            evidence = run.get('objective_scores', {}).get('evidence', {})
            row = {'case_id': run['case_id'], 'method': run['mode'], 'status': run['status'],
                   'suite': suite.name,
                   'reason': run.get('reason'), 'run_path': str(path.relative_to(root)),
                   'source_audit_pass': run.get('audit', {}).get('pass'),
                   'isolation_pass': run.get('isolation_audit', {}).get('pass'),
                   'independently_qualified': run.get('qualification', {}).get('qualified', False),
                   'usage': run.get('usage'),
                   'evidence_precision': evidence.get('evidence_precision'),
                   'critical_evidence_recall': evidence.get('critical_evidence_recall'),
                   'citation_location_validity': evidence.get('citation_location_validity')}
            errors = '\n'.join(p.read_text() for p in (path.parent / 'runtime-artifacts').glob('*.stderr'))
            row['failure_category'] = ('credential_not_loaded' if 'Modal proxy authentication is missing' in errors
                else 'benchmark_gate_token_field_incompatibility' if 'Unbounded model/output request rejected' in errors
                else 'benchmark_request_cap' if 'Campaign request cap reached' in errors
                else 'benchmark_admission_cap' if 'Campaign admission cap reached' in errors
                else None)
            ledger_path = suite / 'modal-admission.jsonl'
            policy_path = suite / 'modal-budget-policy.json'
            if ledger_path.exists() and policy_path.exists():
                events = [json.loads(line) for line in ledger_path.read_text().splitlines()]
                policy = json.loads(policy_path.read_text())
                row['admitted_requests'] = sum(e['event'] == 'reserved' for e in events)
                row['request_limit'] = policy['maximum_admitted_requests']
                if any(e['event'] == 'denied' for e in events) and row['admitted_requests'] >= row['request_limit']:
                    row['failure_category'] = 'benchmark_request_cap'
                elif row['failure_category'] == 'benchmark_admission_cap':
                    active = set()
                    for event in events:
                        if event['event'] == 'reserved': active.add(event['ordinal'])
                        elif event['event'] == 'finished': active.discard(event['ordinal'])
                        elif event['event'] == 'denied' and active:
                            row['failure_category'] = 'benchmark_reservation_concurrency'
                            break
            token_files = list((path.parent / 'runtime-artifacts').glob('*.usage.json'))
            own = [session.get('own_tokens', {}) for p in token_files
                   for session in json.loads(p.read_text()).get('sessions', [])]
            row['usage_based_uncached_estimate_usd'] = sum(
                ((t.get('input', 0) + t.get('cacheRead', 0) + t.get('cacheWrite', 0)) * 1.4
                 + t.get('output', 0) * 4.4) / 1e6 for t in own) if own else None
            (baseline if run['mode'] == 'conventional' else agent).append(row)
        path = suite / 'modal-admission.jsonl'
        if path.exists():
            records = [json.loads(line) for line in path.read_text().splitlines()]
            reserved = [r for r in records if r['event'] == 'reserved']
            reservations.append({'suite': suite.name, 'admitted_requests': len(reserved),
                                 'reserved_usd': next((r['total_reserved_usd'] for r in reversed(records) if 'total_reserved_usd' in r), 0),
                                 'usage_based_uncached_estimate_usd': sum(r['conservative_cost_usd'] for r in records if r['event'] == 'settled'),
                                 'http_statuses': dict(Counter(str(r.get('http_status')) for r in records if r['event'] == 'finished'))})
    tests = ElementTree.parse(root / 'regression.xml').getroot()
    regression = {k: sum(int(s.attrib.get(k, 0)) for s in tests.iter('testsuite'))
                  for k in ('tests', 'failures', 'errors', 'skipped')}
    result = {'status': 'partial_workflow_evaluation', 'generated_at': datetime.now(timezone.utc).isoformat(),
              'ingestion': ingestion, 'deterministic_investigations': baseline, 'agent_attempts': agent,
              'modal_reservations': reservations, 'regression_checks': regression,
              'deviation_detection': {'status': 'not_benchmarked', 'reason': 'No admitted independently labeled agent deviation suite; regression checks are separate.'},
              'manufacturing_scheduling': {'status': 'not_benchmarked', 'reason': 'No executable manufacturing resource optimizer found; orchestration timers are not production scheduling.'},
              'limitations': ['300 ingestion trials repeat only three public-data packages.',
                             'Local service quantiles exclude setup/calibration, network/API and model inference; OS caches uncontrolled.',
                             'Ingestion layouts, companies, certificates and injected defects are synthetic.',
                             'Evidence precision/recall without defensible labels remains null.',
                             'Scientific and human review remain pending; no labor savings or production validation.',
                             'Modal reservations are conservative bounds, not an invoice.']}
    (root / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Manufacturing workflow execution results', '',
             'Partial evaluation. Physical simulations excluded. Results remain local; no deployment performed.', '',
             '## Ingestion: 300 actual service executions', '',
             '| Layout | Completed / attempted | Field precision | Recall | F1 | p90 seconds | p99 seconds |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for condition, family in ingestion['families'].items():
        identity = family['first_execution_field_identity']
        latency = family['completed_service_latency_seconds']
        lines.append(f"| {condition} | {family['completed']}/{family['attempts']} | {identity['precision']:.2%} | {identity['recall']:.2%} | {identity['f1']:.2%} | {latency['p90']:.3f} | {latency['p99']:.3f} |")
    lines += ['', 'Three packages, 100 executions each. Accuracy counts describe the package, not 100 independent incidents.',
              'Changed layouts: 2,106 true-positive fields, seven extra fields, zero missed present fields.',
              'Timing covers target IngestionService.run with local persistence, excluding setup and disjoint calibration.',
              f"Source/code integrity passed: {ingestion['integrity_pass']}. Peak campaign process RSS: {ingestion['process_peak_rss_bytes']/1048576:.1f} MiB.",
              'New/changed layouts route most fields to review. No measured human-time savings.', '',
              '## Deterministic investigation baseline', '',
              '| Case | Status | Critical evidence recall | Citation location validity |',
              '|---|---|---:|---:|']
    def metric(value):
        v = (value or {}).get('value')
        return 'unscored' if v is None else f'{v:.2%}'
    for row in sorted(baseline, key=lambda r: r['case_id']):
        lines.append(f"| {row['case_id']} | {row['status']} | {metric(row['critical_evidence_recall'])} | {metric(row['citation_location_validity'])} |")
    lines += ['', 'These are fixed deterministic reports, not GLM agent performance. Independent qualification remains pending.',
              'Citation location validity does not establish that a narrative claim is true or supported.', '',
              '## Actual GLM agent attempts', '']
    for row in agent:
        count = f" {row['admitted_requests']}/{row['request_limit']} model requests forwarded." if row.get('admitted_requests') is not None else ''
        lines.append(f"- {row['case_id']}: **{row['status']}**, category `{row['failure_category'] or 'see receipt'}`, receipt `{row['run_path']}`.{count} Failures and retries retained.")
    if not agent:
        lines.append('No terminal actual-agent receipt yet.')
    lines += ['', f"Forwarded Modal requests: {sum(r['admitted_requests'] for r in reservations)}; retained conservative reservations: ${sum(r['reserved_usd'] for r in reservations):.2f}. Actual invoice not reconciled.",
              f"Saved session-usage estimate at uncached list rates: ${sum(r['usage_based_uncached_estimate_usd'] or 0 for r in agent):.4f}; see per-attempt nulls where telemetry is unavailable.",
              '', '## Coverage gaps and regression checks', '',
              f"Regression checks: {regression['tests']} tests, {regression['failures']} failures, {regression['errors']} errors. These are not agent accuracy observations.",
              'Deviation detection precision/recall and manufacturing scheduling are not benchmarked yet.',
              'The proposed 60-task, four-workflow agent campaign is not complete.', '',
              '## Limits', '', *['- ' + item for item in result['limitations']]]
    (root / 'report.md').write_text('\n'.join(lines) + '\n')
    files = [root / name for name in ('summary.json', 'report.md', 'ingestion-repeated/protocol.json',
                                     'ingestion-repeated/summary.json', 'ingestion-repeated/attempts.jsonl', 'regression.xml')]
    (root / 'checksums.json').write_text(json.dumps({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                                  for p in files}, indent=2) + '\n')
    if public_output:
        public_output.mkdir(parents=True, exist_ok=True)
        def public_attempt(row):
            return {key: row.get(key) for key in ('case_id', 'method', 'status', 'failure_category',
                                             'critical_evidence_recall', 'citation_location_validity',
                                             'admitted_requests', 'request_limit')}
        public = {'version': 'manufacturing-workflow-results-v1', 'status': result['status'],
                  'ingestion': ingestion, 'baseline': [public_attempt(r) for r in baseline],
                  'agent_attempts': [public_attempt(r) for r in agent],
                  'regression_checks': regression, 'limits': result['limitations'],
                  'source_sha256': hashlib.sha256((root / 'summary.json').read_bytes()).hexdigest()}
        # Only these explicitly selected fields and authored report are public.
        # Credentials, runtime traces, raw errors and session logs stay private.
        (public_output / 'summary.json').write_text(json.dumps(public, indent=2) + '\n')
        (public_output / 'report.md').write_text((root / 'report.md').read_text())
        (public_output / 'checksums.json').write_text(json.dumps({name: hashlib.sha256((public_output / name).read_bytes()).hexdigest()
                                                                for name in ('summary.json', 'report.md')}, indent=2) + '\n')
    print(json.dumps({'report': str(root / 'report.md'), 'agent_attempts': len(agent),
                      'admitted_requests': sum(r['admitted_requests'] for r in reservations)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--public-output', type=Path)
    args = parser.parse_args()
    summarize(args.root.resolve(), args.public_output.resolve() if args.public_output else None)
