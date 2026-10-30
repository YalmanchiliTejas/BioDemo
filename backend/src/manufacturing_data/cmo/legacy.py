"""One-time copy of CMO records from the pre-normalization storage.

The old layout kept each run as one JSON document (``runs`` in ``cmo.sqlite``
or ``cmo_runs`` in PostgreSQL) with a separate hash-chained ``events`` log. The
import verifies that chain first, writes everything through the normalized
repository in one transaction per customer, re-chains the receipts in the
platform audit table, then reloads every run and reports any difference from
the original document. Nothing is deleted from the source.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .persistence import GENESIS, _check, chain_hash, default_tenant, tenant_scope

# Stored values that the normalized model derives on read instead.
DERIVED = {'summary', 'coverage', 'relationships', 'model_usage', 'reviews'}


def _read(source):
    if str(source).startswith(('postgresql://', 'postgres://')):
        import psycopg
        with psycopg.connect(source) as con:
            # 0003_cmo_records.sql renames the old tables to legacy_cmo_*; accept either name.
            prefix = 'legacy_' if con.execute("SELECT to_regclass('legacy_cmo_runs')").fetchone()[0] else ''
            q = lambda sql: [tuple(r) for r in con.execute(sql.replace('cmo_', prefix+'cmo_')).fetchall()]
            return {'runs': [json.loads(r[0]) for r in q('SELECT result FROM cmo_runs ORDER BY created')],
                    'templates': q('SELECT id,cmo,fingerprint,kind,version,mapping,headers,actor,at,origin FROM cmo_templates ORDER BY at'),
                    'rules': q('SELECT id,cmo,pattern,actor,reason,at,run_id FROM cmo_ignore_rules ORDER BY at'),
                    'deliveries': [json.loads(r[0]) for r in q('SELECT item FROM cmo_deliveries ORDER BY created')],
                    'events': q('SELECT payload,prev_hash,hash FROM cmo_events ORDER BY seq')}
    path = Path(source)
    if not path.is_file(): raise FileNotFoundError(f'No legacy CMO database at {path}')
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        q = lambda sql: [tuple(r) for r in con.execute(sql).fetchall()]
        return {'runs': [json.loads(r[0]) for r in q('SELECT result FROM runs ORDER BY rowid')],
                'templates': q('SELECT id,cmo,fingerprint,kind,version,mapping,headers,actor,at,origin FROM templates ORDER BY at'),
                'rules': q('SELECT id,cmo,pattern,actor,reason,at,run_id FROM ignore_rules ORDER BY at'),
                'deliveries': [json.loads(r[0]) for r in q('SELECT item FROM deliveries ORDER BY created')],
                'events': q('SELECT payload,prev_hash,hash FROM events ORDER BY seq')}
    finally: con.close()


IDENTITY = {'measurements': 'id', 'issues': 'id', 'documents': 'source_id', 'layouts': 'fingerprint',
            'elements': 'id', 'stages': None, 'extraction_reviews': None}


def _differences(original, stored):
    """Fields of the original run document that did not survive the round trip.

    Fields older versions never recorded come back as explicit empty values;
    only fields the original held are compared."""
    found = []
    for key, value in original.items():
        if key in DERIVED: continue
        if key in IDENTITY and isinstance(value, list):
            ident = IDENTITY[key]
            mine = {item[ident]: item for item in stored.get(key, [])} if ident else dict(enumerate(stored.get(key, [])))
            for position, item in enumerate(value):
                other = mine.get(item[ident] if ident else position)
                label = f"{key[:-1]} {str(item[ident] if ident else position)[:12]}"
                if other is None: found.append(f'{label} missing'); continue
                diff = sorted(k for k in item if k != 'confidence' and item[k] != other.get(k)
                              and not (k == 'rule_codes' and sorted(set(item[k])) == other.get(k)))
                if diff: found.append(f'{label}: {diff}')
        elif stored.get(key) != value:
            found.append(key)
    return found


def _collapse_duplicates(run):
    """Older pipeline versions could append the same issue twice. Identical copies
    are one fact; differing copies under one ID are a conflict to resolve by hand."""
    collapsed = 0
    for key, ident in (('issues', 'id'), ('measurements', 'id'), ('documents', 'source_id'), ('layouts', 'fingerprint')):
        seen = {}; kept = []
        for item in run.get(key, []):
            prior = seen.get(item[ident])
            if prior is None: seen[item[ident]] = item; kept.append(item)
            elif prior == item: collapsed += 1
            else: raise ValueError(f"Run {run['id']} holds two different {key} with id {item[ident]}; nothing was imported")
        if key in run: run[key] = kept
    return collapsed


def import_legacy(source, repo, *, default=None):
    default = default or default_tenant()
    data = _read(source)
    collapsed = {r['id']: n for r in data['runs'] if (n := _collapse_duplicates(r))}
    prev = GENESIS
    for index, (payload, previous, hashed) in enumerate(data['events']):
        if previous != prev or hashed != chain_hash(prev, payload):
            raise ValueError(f'Legacy audit chain is broken at entry {index}; nothing was imported')
        prev = hashed
    fingerprint = hashlib.sha256(json.dumps([prev, len(data['runs']), len(data['events'])]).encode()).hexdigest()

    run_tenant = {r['id']: r.get('project_tenant') or default for r in data['runs']}
    # The old rule table did not record which issue created a rule; the issue did.
    origin = {rule: (r['id'], i['id']) for r in data['runs'] for i in r.get('issues', []) for rule in i.get('ignore_rules', [])}
    by_cmo = {}
    for r in data['runs']: by_cmo.setdefault(r['cmo'], set()).add(run_tenant[r['id']])
    cmo_tenant = lambda cmo: next(iter(by_cmo[cmo])) if len(by_cmo.get(cmo, ())) == 1 else default

    def event_tenant(data_):
        if data_.get('run_id') in run_tenant: return run_tenant[data_['run_id']]
        rule = data_.get('rule')
        if isinstance(rule, dict): return run_tenant.get(rule.get('run_id')) or cmo_tenant(rule['cmo'])
        template = data_.get('template')
        if isinstance(template, dict): return cmo_tenant(template['cmo'])
        return default

    tenants = sorted({default, *run_tenant.values()})
    report = {'source': str(source), 'legacy_chain_head': prev, 'identical_duplicates_collapsed': collapsed, 'tenants': {}}
    for tenant in tenants:
        with tenant_scope(tenant):
            done = [e for e in repo.audit_entries() if json.loads(e['payload']).get('action') == 'legacy_import'
                    and json.loads(e['payload']).get('fingerprint') == fingerprint]
            if done:
                report['tenants'][tenant] = {'skipped': 'already imported'}; continue
            counts = dict.fromkeys(['templates', 'runs', 'ignore_rules', 'deliveries', 'audit_entries'], 0)
            runs = [r for r in data['runs'] if run_tenant[r['id']] == tenant]
            with repo.transaction():
                for row in data['templates']:
                    template = dict(zip(['id', 'cmo', 'fingerprint', 'kind', 'version', 'mapping', 'headers', 'actor', 'at', 'origin'], row))
                    if cmo_tenant(template['cmo']) == tenant:
                        repo.insert_template(template); counts['templates'] += 1
                for run in runs:
                    repo.save_run({k: v for k, v in run.items() if k not in DERIVED}, check=False); counts['runs'] += 1
                for row in data['rules']:
                    rule = dict(zip(['id', 'cmo', 'pattern', 'actor', 'reason', 'at', 'run_id'], row))
                    if rule['id'] in origin:
                        _check(origin[rule['id']][0] == rule['run_id'], f"Ignore rule {rule['id']} cites a different run than its issue")
                        rule['issue_id'] = origin[rule['id']][1]
                    if (run_tenant.get(rule['run_id']) or cmo_tenant(rule['cmo'])) == tenant:
                        repo.add_ignore_rule(rule); counts['ignore_rules'] += 1
                for item in data['deliveries']:
                    if cmo_tenant(item['cmo']) == tenant:
                        repo.save_delivery(item); counts['deliveries'] += 1
                for payload, _, _ in data['events']:
                    entry = json.loads(payload)
                    action = entry.pop('action')
                    # Review receipts carry their own time; other entries were stamped by the log.
                    at = entry['at'] if action == 'measurement_review' else entry.pop('at')
                    if event_tenant(entry) == tenant:
                        repo.append_audit(action, entry, at=at); counts['audit_entries'] += 1
                repo.append_audit('legacy_import', {'fingerprint': fingerprint, 'legacy_chain_head': prev,
                                                    'source': Path(str(source)).name, **counts})
            mismatched = {}
            for run in runs:
                differences = _differences(run, repo.get_run(run['id']))
                if differences: mismatched[run['id']] = differences
            report['tenants'][tenant] = {**counts, 'audit_chain_valid': repo.verify_audit(), 'runs_with_differences': mismatched}
    return report
