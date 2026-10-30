"""Durable CMO ingestion records in the platform database.

Runs are stored as normalized rows (``src/lifesci/cmo_schema.py``) in the same
database as the platform: PostgreSQL when ``CMO_DATABASE_URL`` or
``LIFESCI_DATABASE_URL`` is a ``postgresql://`` URL, otherwise a local SQLite
file (development and tests). Every row is tenant-scoped; the tenant comes
from the request context (``tenant_scope``).

The pipeline still works with one run dictionary. ``save_run`` decomposes it
into rows and writes only what changed; ``get_run`` reassembles it and derives
everything that is a function of other stored facts (summary, coverage,
relationships, confidence, review receipts, model usage, superseded status).
Nothing in a run is dropped silently: an unknown field, a contradiction of a
derived value, an edit to an insert-only column or the disappearance of a
stored row raises instead.

Decisions are receipts in the platform ``audit`` table, hash-chained per
tenant (``prev_hash`` -> ``after_hash``).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ...lifesci.cmo_schema import CMO_SQLITE_DDL, TABLES
from ...lifesci.store import apply_sqlite_schema
from . import quality

GENESIS = '0'*64
_tenant: contextvars.ContextVar[str | None] = contextvars.ContextVar('cmo_tenant', default=None)


def utc(): return datetime.now(timezone.utc).isoformat()


def default_tenant():
    return os.getenv('CMO_DEFAULT_TENANT', '').strip() or 'demo-cdmo'


def current_tenant():
    return _tenant.get() or default_tenant()


def set_tenant(tenant):
    """Bind the tenant for the rest of the current context (request or task)."""
    _tenant.set(tenant or default_tenant())


@contextmanager
def tenant_scope(tenant):
    token = _tenant.set(tenant or default_tenant())
    try: yield
    finally: _tenant.reset(token)


def _j(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _u(text):
    return None if text is None else json.loads(text)


def audit_payload(at, action, data):
    """Hashed form of an audit entry; identical to the pre-normalization chain format."""
    return json.dumps({'at': at, 'action': action, **data}, sort_keys=True, allow_nan=False)


def chain_hash(prev, payload):
    return hashlib.sha256((prev+payload).encode()).hexdigest()


class Keep:
    """Column value placeholder: keep the stored value (insert ``fallback`` if new)."""
    def __init__(self, fallback): self.fallback = fallback


# Columns in insert order; the leading ``tenant_id`` is implicit.
COLUMNS = {
    'cmo_runs': ('id', 'cmo', 'configuration', 'requested_configuration', 'package_id', 'delivery_name', 'disclosure',
                 'status', 'synthetic', 'hosted_approved', 'hosted_basis', 'started_at', 'completed_at',
                 'runtime_seconds', 'error', 'human_minutes', 'human_time_status', 'project_id', 'case_id',
                 'store_path', 'ingestion', 'expectations_basis', 'superseded_by', 'carried_from_run',
                 'carried_skipped', 'elements_recorded'),
    'cmo_run_notes': ('run_id', 'kind', 'position', 'note'),
    'cmo_run_stages': ('run_id', 'position', 'stage', 'state', 'elapsed_seconds', 'duration_seconds'),
    'cmo_documents': ('run_id', 'source_id', 'position', 'path', 'doc_type', 'classification_method',
                      'classification_evidence', 'sha256', 'extraction_status'),
    'cmo_layouts': ('run_id', 'fingerprint', 'position', 'sheet', 'headers', 'mapping', 'decisions', 'template_id',
                    'based_on', 'example_source_id', 'records'),
    'cmo_elements': ('run_id', 'id', 'position', 'source_id', 'sheet', 'source_column', 'source_row', 'page', 'state'),
    'cmo_issues': ('run_id', 'id', 'position', 'rule_code', 'status', 'context', 'actor', 'reason', 'resolved_at',
                   'grouped_with', 'covered_by', 'carried_from'),
    'cmo_measurements': ('run_id', 'id', 'position', 'evidence_id', 'source_id', 'source', 'parameter', 'batch',
                         'time_value', 'value_raw', 'unit_raw', 'unit_declared', 'value', 'unit', 'fingerprint',
                         'parser', 'source_verified', 'status', 'extraction_confidence', 'extraction_spans',
                         'extraction_review_reasons', 'supersedes'),
    'cmo_measurement_rules': ('run_id', 'measurement_id', 'rule_code'),
    'cmo_extraction_reviews': ('run_id', 'position', 'source_id', 'review'),
}
KEYS = {'cmo_runs': ('id',), 'cmo_run_notes': ('run_id', 'kind', 'position'), 'cmo_run_stages': ('run_id', 'position'),
        'cmo_documents': ('run_id', 'source_id'), 'cmo_layouts': ('run_id', 'fingerprint'),
        'cmo_elements': ('run_id', 'id'), 'cmo_issues': ('run_id', 'id'), 'cmo_measurements': ('run_id', 'id'),
        'cmo_measurement_rules': ('run_id', 'measurement_id', 'rule_code'),
        'cmo_extraction_reviews': ('run_id', 'position')}
ORDER = {'cmo_runs': 'id', 'cmo_run_notes': 'kind, position', 'cmo_run_stages': 'position',
         'cmo_documents': 'position', 'cmo_layouts': 'position', 'cmo_elements': 'position',
         'cmo_issues': 'position', 'cmo_measurements': 'position, id',
         'cmo_measurement_rules': 'measurement_id, rule_code', 'cmo_extraction_reviews': 'position'}
BOOLEAN = {'synthetic', 'hosted_approved', 'source_verified', 'elements_recorded'}
# The position of a measurement only orders the current list; a corrected value
# takes the place of the one it supersedes.
REORDERABLE = {('cmo_measurements', 'position')}

RUN_FIELDS = {'id', 'cmo', 'configuration', 'requested_configuration', 'configuration_notes', 'package_ref',
              'package_id', 'hosted_inference', 'started_at', 'status', 'synthetic', 'stages', 'layouts',
              'measurements', 'issues', 'documents', 'model_usage', 'extraction_reviews', 'human_minutes',
              'human_time_status', 'reviews', 'elements', 'project_tenant', 'project_id', 'case_id', 'store',
              'ingestion', 'expectations_basis', 'relationships', 'coverage', 'summary', 'runtime_seconds',
              'completed_at', 'error', 'unavailable_reasons', 'superseded_measurements', 'carried_over',
              'superseded_by', 'disclosure', 'delivery_name'}
MEASUREMENT_FIELDS = {'id', 'evidence_id', 'source_id', 'source', 'source_sha256', 'parameter', 'batch', 'time',
                      'value_raw', 'unit_raw', 'unit_declared', 'value', 'unit', 'template_id', 'fingerprint', 'parser',
                      'source_verified', 'status', 'rule_codes', 'extraction_confidence', 'extraction_spans',
                      'extraction_review_reasons', 'confidence', 'supersedes', 'superseded_by'}
LAYOUT_FIELDS = {'fingerprint', 'kind', 'sheet', 'headers', 'mapping', 'decisions', 'template_id', 'template_version',
                 'confirmed', 'template_origin', 'based_on', 'example_source_id', 'path', 'records'}
DOCUMENT_FIELDS = {'source_id', 'path', 'doc_type', 'classification_method', 'classification_evidence', 'sha256',
                   'route', 'extraction_status'}
ELEMENT_FIELDS = {'id', 'path', 'sheet', 'column', 'row', 'page', 'state'}
STAGE_FIELDS = {'stage', 'state', 'elapsed_seconds', 'duration_seconds'}
DISPOSITION = ('actor', 'reason', 'at', 'grouped_with', 'covered_by', 'carried_from')
DERIVED_ISSUE = {'ignore_rules'}
TEMPLATE_COLUMNS = ['id', 'cmo', 'fingerprint', 'kind', 'version', 'mapping', 'headers', 'actor', 'at', 'origin']
RULE_COLUMNS = ['id', 'cmo', 'pattern', 'actor', 'reason', 'at', 'run_id', 'issue_id']
DELIVERY_FIELDS = {'id', 'cmo', 'name', 'created', 'dataset', 'condition', 'synthetic', 'files', 'disclosure'}


def _unknown(kind, item, allowed):
    extra = set(item)-allowed
    if extra: raise ValueError(f'{kind} has fields without a storage column: {sorted(extra)}')


def _check(condition, message):
    if not condition: raise ValueError(message)


class _Tx:
    def __init__(self, conn, backend, tenant):
        self.conn, self.backend, self.tenant = conn, backend, tenant

    def _sql(self, sql):
        return sql.replace('?', '%s') if self.backend == 'postgresql' else sql

    def execute(self, sql, params=()):
        return self.conn.execute(self._sql(sql), params)

    def executemany(self, sql, rows):
        if not rows: return
        if self.backend == 'postgresql':
            with self.conn.cursor() as cur: cur.executemany(self._sql(sql), rows)
        else: self.conn.executemany(sql, rows)

    def fetchall(self, sql, params=()):
        return [tuple(r) for r in self.execute(sql, params).fetchall()]

    def fetchone(self, sql, params=()):
        row = self.execute(sql, params).fetchone()
        return tuple(row) if row is not None else None


class Repository:
    def __init__(self, url):
        self._local = threading.local(); self._chain_lock = threading.RLock()
        if url.startswith(('postgresql://', 'postgres://')):
            import psycopg
            self._psycopg = psycopg; self.url = url; self.backend = 'postgresql'
        else:
            self.path = Path(url[len('sqlite:///'):] if url.startswith('sqlite:///') else url)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.backend = 'sqlite'
            con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            try:
                con.execute('PRAGMA journal_mode=WAL')
                apply_sqlite_schema(con)
                con.executescript(CMO_SQLITE_DDL)
            finally: con.close()

    # --- transactions -----------------------------------------------------------------
    def _connect(self):
        if self.backend == 'postgresql':
            return self._psycopg.connect(self.url, connect_timeout=15)
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.execute('PRAGMA foreign_keys=ON')
        return con

    @contextmanager
    def transaction(self):
        """One unit of work for the current tenant. Nested calls on the same thread join it."""
        tenant = current_tenant(); outer = getattr(self._local, 'tx', None)
        if outer is not None:
            if outer.tenant != tenant: raise PermissionError('A transaction cannot span customers')
            yield outer; return
        conn = self._connect()
        try:
            tx = _Tx(conn, self.backend, tenant)
            if self.backend == 'postgresql':
                tx.execute("SELECT set_config('app.tenant_id', ?, true)", (tenant,))
            else: conn.execute('BEGIN IMMEDIATE')
            self._local.tx = tx
            try:
                yield tx
            except BaseException:
                conn.rollback() if self.backend == 'postgresql' else conn.execute('ROLLBACK')
                raise
            finally: self._local.tx = None
            conn.commit() if self.backend == 'postgresql' else conn.execute('COMMIT')
        finally: conn.close()

    def _workspace(self, tx, cmo):
        _check(isinstance(cmo, str) and cmo.strip(), 'CMO name is required')
        tx.execute('INSERT INTO cmo_workspaces (tenant_id, name, created_at) VALUES (?,?,?) ON CONFLICT DO NOTHING',
                   (tx.tenant, cmo, utc()))

    # --- runs: write ------------------------------------------------------------------
    def save_run(self, run, *, check=True):
        rows = self._decompose(run, check=check)
        with self.transaction() as tx:
            self._workspace(tx, run['cmo'])
            if check: self._check_templates(tx, run)
            for table, items in rows.items(): self._sync(tx, table, run['id'], items)

    def _decompose(self, run, *, check):
        _unknown('Run', run, RUN_FIELDS)
        rid = run['id']; tenant = current_tenant()
        if check and run.get('project_tenant') is not None:
            _check(run['project_tenant'] == tenant, 'Run belongs to another customer context')
        if run.get('package_id') is not None and run.get('package_ref') is not None:
            _check(run['package_id'] == run['package_ref'], 'package_id and package_ref disagree')
        hosted = run.get('hosted_inference') or {}
        if check and hosted: _check(bool(hosted.get('synthetic')) == bool(run.get('synthetic')), 'hosted_inference.synthetic disagrees with synthetic')
        carried = run.get('carried_over')
        opt = lambda key: _j(run[key]) if key in run else None
        rows = {table: [] for table in COLUMNS}
        rows['cmo_runs'].append({
            'id': rid, 'cmo': run['cmo'], 'configuration': run['configuration'],
            'requested_configuration': run.get('requested_configuration'),
            'package_id': run.get('package_id') if run.get('package_id') is not None else run.get('package_ref'),
            'delivery_name': run.get('delivery_name'), 'disclosure': run.get('disclosure'), 'status': run['status'],
            'synthetic': bool(run.get('synthetic')), 'hosted_approved': bool(hosted.get('approved')),
            'hosted_basis': hosted.get('basis'), 'started_at': run['started_at'], 'completed_at': run.get('completed_at'),
            'runtime_seconds': run.get('runtime_seconds'), 'error': run.get('error'),
            'human_minutes': run.get('human_minutes'), 'human_time_status': run.get('human_time_status'),
            'project_id': run.get('project_id'), 'case_id': run.get('case_id'), 'store_path': run.get('store'),
            'ingestion': opt('ingestion'), 'expectations_basis': opt('expectations_basis'),
            'superseded_by': run.get('superseded_by'), 'carried_from_run': carried['from_run'] if carried else None,
            'carried_skipped': _j(carried.get('skipped', [])) if carried else None,
            # Runs from before the element ledger existed must not claim complete coverage.
            'elements_recorded': 'elements' in run})
        for kind, key in (('configuration', 'configuration_notes'), ('unavailable', 'unavailable_reasons')):
            rows['cmo_run_notes'] += [{'run_id': rid, 'kind': kind, 'position': i, 'note': note}
                                      for i, note in enumerate(run.get(key) or [])]
        for i, stage in enumerate(run.get('stages', [])):
            _unknown('Stage', stage, STAGE_FIELDS)
            rows['cmo_run_stages'].append({'run_id': rid, 'position': i, 'stage': stage['stage'], 'state': stage['state'],
                'elapsed_seconds': stage['elapsed_seconds'], 'duration_seconds': stage.get('duration_seconds')})
        routes = {r['path']: r for r in (run.get('ingestion') or {}).get('routes', [])}
        sources = {}; docs = {}
        for i, doc in enumerate(run.get('documents', [])):
            _unknown('Document', doc, DOCUMENT_FIELDS)
            if check: _check(doc.get('route', {}) == routes.get(doc['path'], {}), f"Document route for {doc['path']} disagrees with the parser report")
            sources[doc['path']] = doc['source_id']; docs[doc['source_id']] = doc
            rows['cmo_documents'].append({'run_id': rid, 'source_id': doc['source_id'], 'position': i, 'path': doc['path'],
                'doc_type': doc['doc_type'], 'classification_method': doc.get('classification_method'),
                'classification_evidence': _j(doc.get('classification_evidence')), 'sha256': doc['sha256'],
                'extraction_status': doc.get('extraction_status')})
        layouts = {}
        for i, layout in enumerate(run.get('layouts', [])):
            _unknown('Layout', layout, LAYOUT_FIELDS)
            example = docs.get(layout['example_source_id'])
            _check(example is not None, f"Layout {layout['fingerprint'][:12]} cites an unknown document")
            if check:
                _check(layout.get('kind', example['doc_type']) == example['doc_type'], 'Layout kind disagrees with its document')
                _check(layout.get('path', example['path']) == example['path'], 'Layout path disagrees with its document')
                _check(layout.get('confirmed', layout['template_id'] is not None) == (layout['template_id'] is not None),
                       'Layout confirmation disagrees with its template')
            layouts[layout['fingerprint']] = layout
            rows['cmo_layouts'].append({'run_id': rid, 'fingerprint': layout['fingerprint'], 'position': i,
                'sheet': layout.get('sheet'), 'headers': _j(layout['headers']), 'mapping': _j(layout['mapping']),
                'decisions': _j(layout.get('decisions', [])), 'template_id': layout.get('template_id'),
                'based_on': _j(layout.get('based_on')), 'example_source_id': layout['example_source_id'],
                'records': layout.get('records')})
        for i, element in enumerate(run.get('elements', [])):
            _unknown('Element', element, ELEMENT_FIELDS)
            _check(element['path'] in sources, f"Element {element['id']} cites an unknown document")
            rows['cmo_elements'].append({'run_id': rid, 'id': element['id'], 'position': i,
                'source_id': sources[element['path']], 'sheet': element.get('sheet'),
                'source_column': element.get('column'), 'source_row': element.get('row'), 'page': element.get('page'),
                'state': element['state']})
        for i, issue in enumerate(run.get('issues', [])):
            context = {k: v for k, v in issue.items() if k not in {'id', 'rule_code', 'status', *DISPOSITION, *DERIVED_ISSUE}}
            rows['cmo_issues'].append({'run_id': rid, 'id': issue['id'], 'position': i, 'rule_code': issue['rule_code'],
                'status': issue['status'], 'context': _j(context), 'actor': issue.get('actor'),
                'reason': issue.get('reason'), 'resolved_at': issue.get('at'),
                'grouped_with': issue.get('grouped_with'), 'covered_by': issue.get('covered_by'),
                'carried_from': issue.get('carried_from')})
        current = run.get('measurements', []); superseded = run.get('superseded_measurements', [])
        current_ids = {m['id'] for m in current}
        successors = {m['supersedes']: m['id'] for m in [*current, *superseded] if m.get('supersedes')}
        for i, (m, retired) in enumerate([*((m, False) for m in current), *((m, True) for m in superseded)]):
            _unknown('Measurement', m, MEASUREMENT_FIELDS)
            _check(m['source_id'] in docs, f"Measurement {m['id'][:12]} cites an unknown document")
            if check:
                _check(m.get('source_sha256', docs[m['source_id']]['sha256']) == docs[m['source_id']]['sha256'],
                       'Measurement file hash disagrees with its document')
                layout = layouts.get(m['fingerprint'])
                _check(layout is not None, f"Measurement {m['id'][:12]} cites an unknown layout")
                _check(m.get('template_id') == layout.get('template_id'), 'Measurement template disagrees with its layout')
                if retired:
                    _check(m['id'] not in current_ids and successors.get(m['id']) == m.get('superseded_by'),
                           'Superseded measurement has no matching successor')
            rows['cmo_measurements'].append({'run_id': rid, 'id': m['id'],
                'position': Keep(i) if retired else i, 'evidence_id': m['evidence_id'], 'source_id': m['source_id'],
                'source': _j(m['source']), 'parameter': m['parameter'], 'batch': m['batch'], 'time_value': m['time'],
                'value_raw': m['value_raw'], 'unit_raw': m.get('unit_raw'), 'unit_declared': m.get('unit_declared'),
                'value': m['value'], 'unit': m['unit'], 'fingerprint': m['fingerprint'], 'parser': m.get('parser'),
                'source_verified': bool(m['source_verified']),
                'status': Keep(m['status']) if retired else m['status'],
                'extraction_confidence': _j(m.get('extraction_confidence')),
                'extraction_spans': _j(m.get('extraction_spans')),
                'extraction_review_reasons': _j(m.get('extraction_review_reasons', [])),
                'supersedes': m.get('supersedes')})
            rows['cmo_measurement_rules'] += [{'run_id': rid, 'measurement_id': m['id'], 'rule_code': code}
                                              for code in sorted(set(m.get('rule_codes', [])))]
        for i, review in enumerate(run.get('extraction_reviews', [])):
            _check(review['path'] in sources, 'Extraction review cites an unknown document')
            rows['cmo_extraction_reviews'].append({'run_id': rid, 'position': i, 'source_id': sources[review['path']],
                'review': _j({k: v for k, v in review.items() if k != 'path'})})
        return rows

    def _check_templates(self, tx, run):
        ids = {l['template_id'] for l in run.get('layouts', []) if l.get('template_id')}
        if not ids: return
        found = {r[0]: r for r in tx.fetchall(
            f"SELECT id, version, origin FROM cmo_templates WHERE tenant_id=? AND id IN ({','.join('?'*len(ids))})",
            (tx.tenant, *ids))}
        for layout in run.get('layouts', []):
            if not layout.get('template_id'): continue
            _check(layout['template_id'] in found, 'Layout cites an unknown template')
            _, version, origin = found[layout['template_id']]
            _check(layout.get('template_version', version) == version and layout.get('template_origin', origin) == origin,
                   'Layout template version or origin disagrees with the template')

    def _sync(self, tx, table, run_id, items):
        columns = COLUMNS[table]; keys = KEYS[table]; mutable = set(TABLES[table]['mutable'])
        owner = 'id' if table == 'cmo_runs' else 'run_id'
        stored = {}
        for row in tx.fetchall(f"SELECT {', '.join(columns)} FROM {table} WHERE tenant_id=? AND {owner}=?", (tx.tenant, run_id)):
            record = dict(zip(columns, row))
            for c in BOOLEAN & record.keys():
                if record[c] is not None: record[c] = bool(record[c])
            stored[tuple(record[k] for k in keys)] = record
        inserts = []; updates = []; seen = set()
        for item in items:
            key = tuple(item[k] for k in keys); seen.add(key)
            old = stored.get(key)
            if old is None:
                inserts.append(tuple(v.fallback if isinstance(v, Keep) else v for v in (item[c] for c in columns)))
                continue
            changed = [c for c in columns if not isinstance(item[c], Keep) and item[c] != old[c]]
            frozen = [c for c in changed if c not in mutable and (table, c) not in REORDERABLE]
            _check(not frozen, f"{table} {key[-1]}: {', '.join(frozen)} cannot change after it is recorded")
            if changed: updates.append((changed, [item[c] for c in changed] + [tx.tenant, *key]))
        missing = set(stored) - seen
        _check(not missing, f'{table}: saving would drop {len(missing)} stored row(s) for run {run_id}')
        tx.executemany(f"INSERT INTO {table} (tenant_id, {', '.join(columns)}) VALUES ({','.join('?'*(len(columns)+1))})",
                       [(tx.tenant, *row) for row in inserts])
        where = ' AND '.join(f'{k}=?' for k in keys)
        for changed, params in updates:
            tx.execute(f"UPDATE {table} SET {', '.join(f'{c}=?' for c in changed)} WHERE tenant_id=? AND {where}", tuple(params))

    def update_run(self, run_id, **fields):
        """Change header fields of a run without reloading its rows."""
        allowed = set(TABLES['cmo_runs']['mutable'])
        _check(fields and set(fields) <= allowed, 'Only mutable run fields can be updated')
        with self.transaction() as tx:
            cur = tx.execute(f"UPDATE cmo_runs SET {', '.join(f'{c}=?' for c in fields)} WHERE tenant_id=? AND id=?",
                             (*fields.values(), tx.tenant, run_id))
            if cur.rowcount != 1: raise KeyError('Unknown run')

    # --- runs: read -------------------------------------------------------------------
    def get_run(self, run_id):
        runs = self._load(run_id=run_id)
        if not runs: raise KeyError('Unknown run')
        return runs[0]

    def runs(self, cmo=None):
        return self._load(cmo=cmo)

    def run_headers(self, cmo=None):
        with self.transaction() as tx:
            rows = tx.fetchall('SELECT id, cmo, status, started_at, superseded_by FROM cmo_runs WHERE tenant_id=? '
                               'AND (CAST(? AS TEXT) IS NULL OR cmo=?) ORDER BY started_at, id', (tx.tenant, cmo, cmo))
        return [dict(zip(('id', 'cmo', 'status', 'started_at', 'superseded_by'), r)) for r in rows]

    def _rows(self, tx, table, scope, params):
        columns = COLUMNS[table]
        owner = 'id' if table == 'cmo_runs' else 'run_id'
        result = {}
        for row in tx.fetchall(f"SELECT {', '.join(columns)} FROM {table} WHERE tenant_id=? AND {owner} IN ({scope}) "
                               f"ORDER BY {ORDER[table]}", (tx.tenant, *params)):
            record = dict(zip(columns, row))
            for c in BOOLEAN & record.keys():
                if record[c] is not None: record[c] = bool(record[c])
            result.setdefault(record.get('run_id', record.get('id')), []).append(record)
        return result

    def _load(self, *, run_id=None, cmo=None):
        with self.transaction() as tx:
            if run_id is not None: scope, params = '?', (run_id,)
            else: scope, params = 'SELECT id FROM cmo_runs WHERE tenant_id=? AND (CAST(? AS TEXT) IS NULL OR cmo=?)', (tx.tenant, cmo, cmo)
            data = {table: self._rows(tx, table, scope, params) for table in COLUMNS}
            templates = {r[0]: r for r in tx.fetchall('SELECT id, version, origin FROM cmo_templates WHERE tenant_id=?', (tx.tenant,))} \
                if any(data['cmo_layouts'].values()) else {}
            rules = {}
            for rule in tx.fetchall(f'SELECT run_id, issue_id, id FROM cmo_ignore_rules WHERE tenant_id=? AND run_id IN ({scope}) '
                                    'AND issue_id IS NOT NULL ORDER BY at, id', (tx.tenant, *params)):
                rules.setdefault((rule[0], rule[1]), []).append(rule[2])
            receipts = {}
            for aggregate, action, at, details in tx.fetchall(
                    "SELECT aggregate_id, action, occurred_at, details FROM audit WHERE tenant_id=? AND aggregate_kind='cmo_run' "
                    f"AND aggregate_id IN ({scope}) AND action IN ('measurement_review','model_call') AND prev_hash IS NOT NULL "
                    'ORDER BY seq', (tx.tenant, *params)):
                receipts.setdefault(aggregate, []).append((action, at, json.loads(details)))
        runs = [self._assemble(tx.tenant, header, data, templates, rules, receipts.get(header['id'], []))
                for header in [h[0] for h in data['cmo_runs'].values()]]
        return sorted(runs, key=lambda r: (r['started_at'], r['id']))

    def _assemble(self, tenant, h, data, templates, rules, receipts):
        rid = h['id']; part = lambda table: data[table].get(rid, [])
        run = {'id': rid, 'cmo': h['cmo'], 'configuration': h['configuration'],
               'requested_configuration': h['requested_configuration'],
               'configuration_notes': [n['note'] for n in part('cmo_run_notes') if n['kind'] == 'configuration'],
               'package_ref': h['package_id'],
               'hosted_inference': {'approved': h['hosted_approved'], 'synthetic': h['synthetic'], 'basis': h['hosted_basis']},
               'started_at': h['started_at'], 'status': h['status'], 'synthetic': h['synthetic']}
        run['stages'] = [{'stage': s['stage'], 'state': s['state'], 'elapsed_seconds': s['elapsed_seconds'],
                          **({'duration_seconds': s['duration_seconds']} if s['duration_seconds'] is not None else {})}
                         for s in part('cmo_run_stages')]
        ingestion = _u(h['ingestion'])
        routes = {r['path']: r for r in (ingestion or {}).get('routes', [])}
        docs = {}; documents = []
        for d in part('cmo_documents'):
            doc = {'source_id': d['source_id'], 'path': d['path'], 'doc_type': d['doc_type'],
                   'classification_method': d['classification_method'],
                   'classification_evidence': _u(d['classification_evidence']), 'sha256': d['sha256'],
                   'route': routes.get(d['path'], {}), 'extraction_status': d['extraction_status']}
            docs[d['source_id']] = doc; documents.append(doc)
        layouts = []; by_fingerprint = {}
        for l in part('cmo_layouts'):
            template = templates.get(l['template_id'])
            example = docs[l['example_source_id']]
            layout = {'fingerprint': l['fingerprint'], 'kind': example['doc_type'], 'sheet': l['sheet'],
                      'headers': _u(l['headers']), 'mapping': _u(l['mapping']), 'decisions': _u(l['decisions']),
                      'template_id': l['template_id'], 'template_version': template[1] if template else None,
                      'confirmed': template is not None, 'template_origin': template[2] if template else None,
                      'based_on': _u(l['based_on']), 'example_source_id': l['example_source_id'],
                      'path': example['path'], 'records': l['records']}
            layouts.append(layout); by_fingerprint[l['fingerprint']] = layout
        rule_codes = {}
        for r in part('cmo_measurement_rules'): rule_codes.setdefault(r['measurement_id'], []).append(r['rule_code'])
        rows = part('cmo_measurements')
        successor = {m['supersedes']: m['id'] for m in rows if m['supersedes']}
        validated = h['status'] == 'complete'
        measurements = []; superseded = []
        for m in rows:
            item = {'id': m['id'], 'evidence_id': m['evidence_id'], 'source_id': m['source_id'], 'source': _u(m['source']),
                    'source_sha256': docs[m['source_id']]['sha256'], 'parameter': m['parameter'], 'batch': m['batch'],
                    'time': m['time_value'], 'value_raw': m['value_raw'], 'unit_raw': m['unit_raw'],
                    'unit_declared': m['unit_declared'], 'value': m['value'], 'unit': m['unit'],
                    'template_id': by_fingerprint[m['fingerprint']]['template_id'], 'fingerprint': m['fingerprint'],
                    'parser': m['parser'], 'source_verified': m['source_verified'], 'status': m['status'],
                    'rule_codes': sorted(rule_codes.get(m['id'], [])),
                    'extraction_confidence': _u(m['extraction_confidence']), 'extraction_spans': _u(m['extraction_spans']),
                    'extraction_review_reasons': _u(m['extraction_review_reasons'])}
            if validated: item['confidence'] = quality.confidence(item)
            if m['supersedes']: item['supersedes'] = m['supersedes']
            if m['id'] in successor:
                superseded.append({**item, 'status': 'superseded', 'superseded_by': successor[m['id']]})
            else: measurements.append(item)
        issues = []
        for i in part('cmo_issues'):
            issue = {'id': i['id'], 'rule_code': i['rule_code'], 'status': i['status'], **_u(i['context'])}
            for key, column in (('actor', 'actor'), ('reason', 'reason'), ('at', 'resolved_at'), ('grouped_with', 'grouped_with'),
                                ('covered_by', 'covered_by'), ('carried_from', 'carried_from')):
                if i[column] is not None: issue[key] = i[column]
            if i['status'] == 'resolved' and not (i['grouped_with'] or i['covered_by'] or i['carried_from']):
                issue['ignore_rules'] = rules.get((rid, i['id']), [])
            issues.append(issue)
        reviews = [details_without(d, 'run_id') for action, _, d in receipts if action == 'measurement_review']
        run.update(layouts=layouts, measurements=measurements, issues=issues, documents=documents,
                   model_usage=[details_without(d, 'run_id', 'prompt', 'response') for action, _, d in receipts if action == 'model_call'],
                   extraction_reviews=[{'path': docs[r['source_id']]['path'], **_u(r['review'])} for r in part('cmo_extraction_reviews')],
                   human_minutes=h['human_minutes'], human_time_status=h['human_time_status'], reviews=reviews)
        if h['elements_recorded']:
            run['elements'] = [{'id': e['id'], 'path': docs[e['source_id']]['path'], 'sheet': e['sheet'],
                                'column': e['source_column'], 'row': e['source_row'], 'page': e['page'], 'state': e['state']}
                               for e in part('cmo_elements')]
        if h['project_id'] is not None: run.update(project_tenant=tenant, project_id=h['project_id'], case_id=h['case_id'])
        run['store'] = h['store_path']
        if h['ingestion'] is not None: run['ingestion'] = ingestion
        if h['expectations_basis'] is not None: run['expectations_basis'] = _u(h['expectations_basis'])
        for key in ('runtime_seconds', 'completed_at', 'error', 'superseded_by', 'disclosure', 'delivery_name'):
            if h[key] is not None: run[key] = h[key]
        if h['package_id'] is not None: run['package_id'] = h['package_id']
        unavailable = [n['note'] for n in part('cmo_run_notes') if n['kind'] == 'unavailable']
        if unavailable: run['unavailable_reasons'] = unavailable
        if superseded: run['superseded_measurements'] = superseded
        if h['carried_from_run'] is not None:
            run['carried_over'] = {'from_run': h['carried_from_run'],
                                   'reviews': sum((r.get('carried_from') or {}).get('run_id') == h['carried_from_run'] for r in reviews),
                                   'skipped': _u(h['carried_skipped'])}
        if validated: quality.summarize(run)
        return run

    # --- templates, ignore rules, deliveries --------------------------------------------
    def template(self, cmo, fingerprint):
        with self.transaction() as tx:
            row = tx.fetchone(f"SELECT {', '.join(TEMPLATE_COLUMNS)} FROM cmo_templates WHERE tenant_id=? AND cmo=? "
                              'AND fingerprint=? ORDER BY version DESC LIMIT 1', (tx.tenant, cmo, fingerprint))
        return dict(zip(TEMPLATE_COLUMNS, row)) if row else None

    def templates(self, cmo, kind=None):
        with self.transaction() as tx:
            rows = tx.fetchall(f"SELECT {', '.join(TEMPLATE_COLUMNS)} FROM cmo_templates WHERE tenant_id=? AND cmo=? "
                               'AND (CAST(? AS TEXT) IS NULL OR kind=?) ORDER BY at, id', (tx.tenant, cmo, kind, kind))
        return [dict(zip(TEMPLATE_COLUMNS, r)) for r in rows]

    def insert_template(self, template):
        _unknown('Template', template, set(TEMPLATE_COLUMNS))
        with self.transaction() as tx:
            self._workspace(tx, template['cmo'])
            tx.execute(f"INSERT INTO cmo_templates (tenant_id, {', '.join(TEMPLATE_COLUMNS)}) VALUES ({','.join('?'*(len(TEMPLATE_COLUMNS)+1))})",
                       (tx.tenant, *[template[c] for c in TEMPLATE_COLUMNS]))

    def ignore_rules(self, cmo):
        with self.transaction() as tx:
            rows = tx.fetchall(f"SELECT {', '.join(RULE_COLUMNS)} FROM cmo_ignore_rules WHERE tenant_id=? AND cmo=? ORDER BY at, id",
                               (tx.tenant, cmo))
        return [dict(zip(RULE_COLUMNS, r)) for r in rows]

    def add_ignore_rule(self, rule):
        _unknown('Ignore rule', rule, set(RULE_COLUMNS))
        with self.transaction() as tx:
            self._workspace(tx, rule['cmo'])
            tx.execute(f"INSERT INTO cmo_ignore_rules (tenant_id, {', '.join(RULE_COLUMNS)}) VALUES ({','.join('?'*(len(RULE_COLUMNS)+1))})",
                       (tx.tenant, *[rule.get(c) for c in RULE_COLUMNS]))

    def deliveries(self):
        with self.transaction() as tx:
            rows = tx.fetchall('SELECT id, cmo, name, created_at, dataset, condition, synthetic, disclosure FROM cmo_deliveries '
                               'WHERE tenant_id=? ORDER BY created_at, id', (tx.tenant,))
            files = {}
            for delivery, path, size, sha in tx.fetchall('SELECT delivery_id, path, size_bytes, sha256 FROM cmo_delivery_files '
                                                         'WHERE tenant_id=? ORDER BY delivery_id, position', (tx.tenant,)):
                files.setdefault(delivery, []).append({'path': path, 'size': size, 'sha256': sha})
        return [{'id': i, 'cmo': cmo, 'name': name, 'created': created, 'dataset': dataset, 'condition': condition,
                 'synthetic': None if synthetic is None else bool(synthetic), 'files': files.get(i, []), 'disclosure': disclosure}
                for i, cmo, name, created, dataset, condition, synthetic, disclosure in rows]

    def save_delivery(self, item):
        """Deliveries are immutable; only new files can be appended."""
        _unknown('Delivery', item, DELIVERY_FIELDS)
        header = (item['cmo'], item.get('name'), item.get('dataset'), item.get('condition'),
                  None if item.get('synthetic') is None else bool(item['synthetic']), item.get('disclosure'))
        with self.transaction() as tx:
            self._workspace(tx, item['cmo'])
            row = tx.fetchone('SELECT cmo, name, dataset, condition, synthetic, disclosure FROM cmo_deliveries WHERE tenant_id=? AND id=?',
                              (tx.tenant, item['id']))
            if row is None:
                tx.execute('INSERT INTO cmo_deliveries (tenant_id, id, cmo, name, created_at, dataset, condition, synthetic, disclosure) '
                           'VALUES (?,?,?,?,?,?,?,?,?)', (tx.tenant, item['id'], header[0], header[1], item.get('created') or utc(), *header[2:]))
            else:
                stored = (*row[:4], None if row[4] is None else bool(row[4]), row[5])
                _check(stored == header, 'A delivery cannot be changed after it is created')
            existing = [r[0] for r in tx.fetchall('SELECT path FROM cmo_delivery_files WHERE tenant_id=? AND delivery_id=? ORDER BY position',
                                                  (tx.tenant, item['id']))]
            paths = [f['path'] for f in item.get('files', [])]
            _check(paths[:len(existing)] == existing, 'Files cannot be removed from or reordered in a delivery')
            tx.executemany('INSERT INTO cmo_delivery_files (tenant_id, delivery_id, position, path, size_bytes, sha256) VALUES (?,?,?,?,?,?)',
                           [(tx.tenant, item['id'], i, f['path'], f['size'], f['sha256'])
                            for i, f in enumerate(item.get('files', [])) if i >= len(existing)])

    # --- audit ------------------------------------------------------------------------
    def append_audit(self, action, data, *, at=None):
        """Append a decision receipt to the tenant's hash chain in the platform audit table."""
        at = data.get('at') or at or utc()
        payload = audit_payload(at, action, data)
        kind, ident = audit_subject(data)
        actor = data.get('actor') if isinstance(data.get('actor'), str) and data.get('actor') else 'cmo-ingestion'
        reason = data.get('reason') if isinstance(data.get('reason'), str) else None
        with self._chain_lock, self.transaction() as tx:
            if self.backend == 'postgresql':
                tx.execute('SELECT pg_advisory_xact_lock(hashtext(?))', ('cmo_audit_chain:'+tx.tenant,))
            row = tx.fetchone('SELECT after_hash FROM audit WHERE tenant_id=? AND prev_hash IS NOT NULL ORDER BY seq DESC LIMIT 1',
                              (tx.tenant,))
            prev = row[0] if row else GENESIS
            hashed = chain_hash(prev, payload)
            tx.execute('INSERT INTO audit (tenant_id, actor_id, action, aggregate_kind, aggregate_id, revision, before_hash, '
                       'after_hash, reason, occurred_at, details, prev_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (tx.tenant, actor, action, kind, ident, 0, None, hashed, reason, at, _j(data), prev))
        return hashed

    def audit_entries(self):
        with self.transaction() as tx:
            rows = tx.fetchall('SELECT action, occurred_at, details, prev_hash, after_hash FROM audit '
                               'WHERE tenant_id=? AND prev_hash IS NOT NULL ORDER BY seq', (tx.tenant,))
        return [{'payload': audit_payload(at, action, json.loads(details)), 'prev_hash': prev, 'hash': hashed}
                for action, at, details, prev, hashed in rows]

    def verify_audit(self):
        prev = GENESIS
        for row in self.audit_entries():
            if row['prev_hash'] != prev or row['hash'] != chain_hash(prev, row['payload']): return False
            prev = row['hash']
        return True

    def tenants(self):
        """Customers whose runs may need recovery after a restart."""
        if self.backend == 'sqlite':
            con = self._connect()
            try: return sorted({r[0] for r in con.execute('SELECT DISTINCT tenant_id FROM cmo_runs')} | {default_tenant()})
            finally: con.close()
        configured = os.getenv('LIFESCI_TENANTS', os.getenv('DEPLOYMENT_TENANT', ''))
        return sorted({t.strip() for t in configured.split(',') if t.strip()} | {default_tenant()})


def details_without(data, *keys):
    return {k: v for k, v in data.items() if k not in keys}


def audit_subject(data):
    if data.get('run_id'): return 'cmo_run', data['run_id']
    if data.get('delivery_id'): return 'cmo_delivery', data['delivery_id']
    if isinstance(data.get('delivery'), dict): return 'cmo_delivery', data['delivery']['id']
    rule = data.get('rule')
    if isinstance(rule, dict): return ('cmo_run', rule['run_id']) if rule.get('run_id') else ('cmo_workspace', rule['cmo'])
    return 'cmo_workspace', '-'


def database_url(root):
    for name in ('CMO_DATABASE_URL', 'LIFESCI_DATABASE_URL'):
        url = os.getenv(name, '').strip()
        if url.startswith(('postgresql://', 'postgres://')) or (name == 'CMO_DATABASE_URL' and url): return url
    return str(Path(root)/'cmo.sqlite')


def repository(root):
    return Repository(database_url(root))
