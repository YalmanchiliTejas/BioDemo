"""Records from the pre-normalization cmo.sqlite are copied without loss and re-chained."""
import csv
import hashlib
import json
import sqlite3

import pytest

from src.manufacturing_data.cmo.legacy import import_legacy
from src.manufacturing_data.cmo.persistence import Repository, tenant_scope
from src.manufacturing_data.cmo.pipeline import IngestionService, digest

LEGACY_SCHEMA = '''
CREATE TABLE runs(id TEXT PRIMARY KEY, cmo TEXT, config TEXT, result TEXT NOT NULL);
CREATE TABLE templates(id TEXT PRIMARY KEY, cmo TEXT, fingerprint TEXT, kind TEXT, version INTEGER, mapping TEXT,
  headers TEXT, actor TEXT, at TEXT, origin TEXT);
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE ignore_rules(id TEXT PRIMARY KEY, cmo TEXT NOT NULL, pattern TEXT NOT NULL, actor TEXT NOT NULL,
  reason TEXT NOT NULL, at TEXT NOT NULL, run_id TEXT);
CREATE TABLE deliveries(id TEXT PRIMARY KEY, created TEXT NOT NULL, item TEXT NOT NULL);
'''


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    """Produce runs with today's pipeline, then store them the way the old layout did."""
    for name in ['OPENAI_API_KEY', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_AUTH_TOKEN', 'SUPABASE_URL', 'CMO_DATABASE_URL', 'LIFESCI_DATABASE_URL']:
        monkeypatch.delenv(name, raising=False)
    raw = tmp_path / 'raw'; raw.mkdir()
    with (raw / 'process.csv').open('w', newline='') as stream:
        csv.writer(stream).writerows([['batch_id', 'elapsed_h', 'pH [pH]'], ['B', 0, 7], ['B', 1, 7.1]])
    service = IngestionService(tmp_path / 'producer')
    run = service.run(raw, 'acme', 'D')
    m = run['measurements'][0]
    run = service.review(run['id'], m['id'], 'accept', 'qa', 'Checked source', binding=digest(m))
    events = []
    prev = '0' * 64
    for entry in service.repo.audit_entries():
        events.append((entry['payload'], prev, entry['hash'])); prev = entry['hash']
    path = tmp_path / 'old.sqlite'
    con = sqlite3.connect(path); con.executescript(LEGACY_SCHEMA)
    con.execute('INSERT INTO runs VALUES (?,?,?,?)', (run['id'], 'acme', run['configuration'], json.dumps(run)))
    con.executemany('INSERT INTO events(payload,prev_hash,hash) VALUES (?,?,?)', events)
    con.execute('INSERT INTO deliveries VALUES (?,?,?)', ('delivery-1', '2026-10-01', json.dumps(
        {'id': 'delivery-1', 'cmo': 'acme', 'name': 'Oct', 'created': '2026-10-01', 'files': [{'path': 'a.csv', 'size': 1, 'sha256': 'x'}]})))
    con.commit(); con.close()
    return path, run


def test_legacy_runs_round_trip_and_receipts_rechain(legacy, tmp_path):
    path, original = legacy
    repo = Repository(str(tmp_path / 'new.sqlite'))
    report = import_legacy(path, repo, default='demo-cdmo')
    result = report['tenants']['demo-cdmo']
    assert result['runs'] == 1 and result['deliveries'] == 1 and result['audit_chain_valid']
    assert result['runs_with_differences'] == {}
    with tenant_scope('demo-cdmo'):
        stored = repo.get_run(original['id'])
        assert stored['reviews'] == original['reviews'] and stored['summary'] == original['summary']
        assert repo.deliveries()[0]['files'][0]['path'] == 'a.csv'
    assert import_legacy(path, repo, default='demo-cdmo')['tenants']['demo-cdmo'] == {'skipped': 'already imported'}


def test_broken_legacy_chain_imports_nothing(legacy, tmp_path):
    path, _ = legacy
    con = sqlite3.connect(path)
    con.execute("UPDATE events SET payload=replace(payload, 'Checked source', 'Forged') WHERE seq=(SELECT max(seq) FROM events)")
    con.commit(); con.close()
    repo = Repository(str(tmp_path / 'new.sqlite'))
    with pytest.raises(ValueError, match='broken'):
        import_legacy(path, repo, default='demo-cdmo')
    with tenant_scope('demo-cdmo'):
        assert repo.runs() == [] and repo.audit_entries() == []
