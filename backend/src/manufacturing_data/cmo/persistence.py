"""Durable CMO ingestion records: runs, confirmed templates, ignore rules,
deliveries and a hash-chained audit trail.

``CMO_DATABASE_URL`` selects the backend. ``postgresql://`` (for example the
Supabase connection string) uses PostgreSQL; otherwise a local SQLite file is
used. Templates, ignore rules and audit events are append-only in both.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def utc(): return datetime.now(timezone.utc).isoformat()


def _chain(prev, payload):
    return hashlib.sha256((prev+payload).encode()).hexdigest()


SQLITE_SCHEMA='''
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, cmo TEXT, config TEXT, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS templates(id TEXT PRIMARY KEY, cmo TEXT, fingerprint TEXT,
  kind TEXT, version INTEGER, mapping TEXT, headers TEXT, actor TEXT, at TEXT, origin TEXT);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ignore_rules(id TEXT PRIMARY KEY, cmo TEXT NOT NULL, pattern TEXT NOT NULL,
  actor TEXT NOT NULL, reason TEXT NOT NULL, at TEXT NOT NULL, run_id TEXT);
CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY, created TEXT NOT NULL, item TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_templates_update BEFORE UPDATE ON templates BEGIN SELECT RAISE(ABORT,'version templates'); END;
CREATE TRIGGER IF NOT EXISTS immutable_templates_delete BEFORE DELETE ON templates BEGIN SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_ignore_update BEFORE UPDATE ON ignore_rules BEGIN SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_ignore_delete BEFORE DELETE ON ignore_rules BEGIN SELECT RAISE(ABORT,'append only'); END;
'''

TEMPLATE_COLUMNS=['id','cmo','fingerprint','kind','version','mapping','headers','actor','at','origin']


class SQLiteRepository:
    backend='sqlite'

    def __init__(self, path):
        self.path=Path(path); self._lock=threading.RLock()
        with self.connect() as con: con.executescript(SQLITE_SCHEMA)

    def connect(self):
        con=sqlite3.connect(self.path,timeout=30); con.row_factory=sqlite3.Row
        return con

    def save_run(self, run):
        with self.connect() as con:
            con.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?)',
                        (run['id'],run['cmo'],run['configuration'],json.dumps(run,allow_nan=False)))

    def get_run(self, run_id):
        with self.connect() as con: row=con.execute('SELECT result FROM runs WHERE id=?',(run_id,)).fetchone()
        if not row: raise KeyError('Unknown run')
        return json.loads(row[0])

    def runs(self, cmo=None):
        with self.connect() as con:
            rows=con.execute('SELECT result FROM runs WHERE (? IS NULL OR cmo=?) ORDER BY rowid',(cmo,cmo)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def template(self, cmo, fingerprint):
        with self.connect() as con:
            row=con.execute('SELECT * FROM templates WHERE cmo=? AND fingerprint=? ORDER BY version DESC LIMIT 1',(cmo,fingerprint)).fetchone()
        return dict(row) if row else None

    def templates(self, cmo, kind=None):
        with self.connect() as con:
            rows=con.execute('SELECT * FROM templates WHERE cmo=? AND (? IS NULL OR kind=?) ORDER BY at',(cmo,kind,kind)).fetchall()
        return [dict(r) for r in rows]

    def insert_template(self, template):
        with self.connect() as con:
            con.execute('INSERT INTO templates VALUES (:id,:cmo,:fingerprint,:kind,:version,:mapping,:headers,:actor,:at,:origin)',template)

    def ignore_rules(self, cmo):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT * FROM ignore_rules WHERE cmo=? ORDER BY at',(cmo,))]

    def add_ignore_rule(self, rule):
        with self.connect() as con:
            con.execute('INSERT INTO ignore_rules VALUES (:id,:cmo,:pattern,:actor,:reason,:at,:run_id)',rule)

    def deliveries(self):
        with self.connect() as con:
            return [json.loads(r[0]) for r in con.execute('SELECT item FROM deliveries ORDER BY created')]

    def save_delivery(self, item):
        with self.connect() as con:
            con.execute('INSERT OR REPLACE INTO deliveries VALUES (?,?,?)',(item['id'],item.get('created') or utc(),json.dumps(item)))

    def append_event(self, payload):
        with self._lock, self.connect() as con:
            row=con.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            prev=row[0] if row else '0'*64
            hashed=_chain(prev,payload)
            con.execute('INSERT INTO events(payload,prev_hash,hash) VALUES (?,?,?)',(payload,prev,hashed))
        return hashed

    def events(self):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT payload,prev_hash,hash FROM events ORDER BY seq')]


POSTGRES_SCHEMA=(Path(__file__).resolve().parents[3]/'deploy'/'supabase'/'migrations'/'0001_cmo_ingestion.sql')


class PostgresRepository:
    """PostgreSQL (Supabase) implementation. The schema is applied by the
    migration in ``deploy/supabase/migrations``; the runtime role needs only
    SELECT/INSERT (plus UPDATE on runs and deliveries)."""
    backend='postgresql'

    def __init__(self, url, *, migrate=False):
        import psycopg
        from psycopg.rows import dict_row
        self._psycopg=psycopg; self.url=url; self._lock=threading.RLock()
        self._row=dict_row
        if migrate:
            with psycopg.connect(url,autocommit=True) as con: con.execute(POSTGRES_SCHEMA.read_text())

    def connect(self):
        return self._psycopg.connect(self.url,row_factory=self._row,connect_timeout=15)

    def save_run(self, run):
        with self.connect() as con:
            con.execute('''INSERT INTO cmo_runs(id,cmo,config,result,updated) VALUES (%s,%s,%s,%s,now())
                           ON CONFLICT (id) DO UPDATE SET cmo=excluded.cmo,config=excluded.config,result=excluded.result,updated=now()''',
                        (run['id'],run['cmo'],run['configuration'],json.dumps(run,allow_nan=False)))

    def get_run(self, run_id):
        with self.connect() as con: row=con.execute('SELECT result FROM cmo_runs WHERE id=%s',(run_id,)).fetchone()
        if not row: raise KeyError('Unknown run')
        return json.loads(row['result'])

    def runs(self, cmo=None):
        with self.connect() as con:
            rows=con.execute('SELECT result FROM cmo_runs WHERE (%s::text IS NULL OR cmo=%s) ORDER BY created',(cmo,cmo)).fetchall()
        return [json.loads(r['result']) for r in rows]

    def template(self, cmo, fingerprint):
        with self.connect() as con:
            row=con.execute('SELECT * FROM cmo_templates WHERE cmo=%s AND fingerprint=%s ORDER BY version DESC LIMIT 1',(cmo,fingerprint)).fetchone()
        return {k:row[k] for k in TEMPLATE_COLUMNS} if row else None

    def templates(self, cmo, kind=None):
        with self.connect() as con:
            rows=con.execute('SELECT * FROM cmo_templates WHERE cmo=%s AND (%s::text IS NULL OR kind=%s) ORDER BY at',(cmo,kind,kind)).fetchall()
        return [{k:r[k] for k in TEMPLATE_COLUMNS} for r in rows]

    def insert_template(self, template):
        with self.connect() as con:
            con.execute('INSERT INTO cmo_templates(id,cmo,fingerprint,kind,version,mapping,headers,actor,at,origin) VALUES (%(id)s,%(cmo)s,%(fingerprint)s,%(kind)s,%(version)s,%(mapping)s,%(headers)s,%(actor)s,%(at)s,%(origin)s)',template)

    def ignore_rules(self, cmo):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT id,cmo,pattern,actor,reason,at,run_id FROM cmo_ignore_rules WHERE cmo=%s ORDER BY at',(cmo,))]

    def add_ignore_rule(self, rule):
        with self.connect() as con:
            con.execute('INSERT INTO cmo_ignore_rules(id,cmo,pattern,actor,reason,at,run_id) VALUES (%(id)s,%(cmo)s,%(pattern)s,%(actor)s,%(reason)s,%(at)s,%(run_id)s)',rule)

    def deliveries(self):
        with self.connect() as con:
            return [json.loads(r['item']) for r in con.execute('SELECT item FROM cmo_deliveries ORDER BY created')]

    def save_delivery(self, item):
        with self.connect() as con:
            con.execute('''INSERT INTO cmo_deliveries(id,item) VALUES (%s,%s)
                           ON CONFLICT (id) DO UPDATE SET item=excluded.item''',(item['id'],json.dumps(item)))

    def append_event(self, payload):
        with self._lock, self.connect() as con:
            # Serialize chain extension across API processes.
            con.execute("SELECT pg_advisory_xact_lock(hashtext('cmo_events_chain'))")
            row=con.execute('SELECT hash FROM cmo_events ORDER BY seq DESC LIMIT 1').fetchone()
            prev=row['hash'] if row else '0'*64
            hashed=_chain(prev,payload)
            con.execute('INSERT INTO cmo_events(payload,prev_hash,hash) VALUES (%s,%s,%s)',(payload,prev,hashed))
        return hashed

    def events(self):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT payload,prev_hash,hash FROM cmo_events ORDER BY seq')]


def repository(root):
    url=os.getenv('CMO_DATABASE_URL','').strip()
    if url.startswith(('postgresql://','postgres://')):
        return PostgresRepository(url,migrate=os.getenv('CMO_DATABASE_MIGRATE','').lower() in {'1','true','yes'})
    return SQLiteRepository(Path(root)/'cmo.sqlite')
