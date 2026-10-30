"""Each fact is stored once: no current-state copy, no derived index, outbox columns not repeated in payloads."""
import json
import sqlite3

import pytest

from src.lifesci.store import RecordStore
from src.lifesci.supabase_sql import MIGRATIONS, render


def test_current_state_lives_only_in_its_revision(tmp_path):
    store = RecordStore(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with store.transaction("a") as tx:
        tx.put("t", "approval", "A", {"proposal_id": "P1"}, expected_revision=None, action="create")
        tx.put("t", "approval", "A", {"proposal_id": "P2"}, expected_revision=1, action="update", event_type="changed")
    con = sqlite3.connect(tmp_path / "db.sqlite")
    con.execute("PRAGMA foreign_keys=ON")  # per connection in SQLite; the store always enables it
    assert [r[1] for r in con.execute("PRAGMA table_info(aggregates)")] == ["tenant_id", "kind", "id", "revision"]
    assert con.execute("SELECT name FROM sqlite_master WHERE name='idx'").fetchone() is None
    payload = json.loads(con.execute("SELECT payload FROM outbox").fetchone()[0])
    assert not {"event_id", "tenant_id", "type", "aggregate_id", "revision", "occurred_at"} & set(payload)
    with pytest.raises(sqlite3.IntegrityError):  # the pointer must name a recorded revision
        con.execute("UPDATE aggregates SET revision=9")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE aggregate_revisions SET state='{}'")
    con.close()
    tx = store.read()
    assert tx.get("t", "approval", "A").state == {"proposal_id": "P2"}
    assert [r.id for r in tx.find("t", "approval", "proposal_id", "P2")] == ["A"]
    assert tx.find("t", "approval", "proposal_id", "P1") == []
    [(_, event)] = store.events_since("t")
    assert (event.type, event.aggregate_id, event.revision, event.tenant_id) == ("changed", "A", 2, "t")


def _legacy_sqlite(path, current_state):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE aggregates (tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
          state TEXT NOT NULL, content_hash TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, kind, id));
        CREATE TABLE aggregate_revisions (tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
          state TEXT NOT NULL, content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY (tenant_id, kind, id, revision));
        CREATE TABLE audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, actor_id TEXT NOT NULL,
          action TEXT NOT NULL, aggregate_kind TEXT NOT NULL, aggregate_id TEXT NOT NULL, revision INTEGER NOT NULL,
          before_hash TEXT, after_hash TEXT NOT NULL, reason TEXT, occurred_at TEXT NOT NULL, details TEXT NOT NULL);
        CREATE TABLE idx (tenant_id TEXT, kind TEXT, field TEXT, value TEXT, id TEXT);
        INSERT INTO aggregate_revisions VALUES ('t','approval','A',1,'{"proposal_id":"P1"}','h1','2026-10-01');
    """)
    con.execute("INSERT INTO aggregates VALUES ('t','approval','A',1,?,'h1','2026-10-01')", (current_state,))
    con.commit(); con.close()


def test_sqlite_database_from_before_normalization_is_upgraded(tmp_path):
    _legacy_sqlite(tmp_path / "old.sqlite", '{"proposal_id":"P1"}')
    store = RecordStore(f"sqlite:///{tmp_path / 'old.sqlite'}")
    assert store.read().get("t", "approval", "A").state == {"proposal_id": "P1"}
    assert [r.id for r in store.read().find("t", "approval", "proposal_id", "P1")] == ["A"]


def test_sqlite_upgrade_refuses_when_current_copy_differs(tmp_path):
    _legacy_sqlite(tmp_path / "drift.sqlite", '{"proposal_id":"edited"}')
    with pytest.raises(RuntimeError, match="differ"):
        RecordStore(f"sqlite:///{tmp_path / 'drift.sqlite'}")


def test_supabase_migrations_match_the_schema():
    """Regenerate with `python -m src.lifesci supabase-sql` after changing the schema."""
    for name, text in render().items():
        assert (MIGRATIONS / name).read_text() == text, f"{name} is stale"
