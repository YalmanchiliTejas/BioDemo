"""Versioned record store with append-only audit, transactional outbox and leases.

One transaction commits the aggregate revision, its audit entry and any outbox
events together (decision D06). Consumers deduplicate through the inbox table.
Optimistic concurrency rejects writes whose expected revision is stale
(decision D05). Leases provide monotonic fencing tokens so an obsolete worker
cannot publish over a newer checkpoint (LS-084).

SQLite is used for local development and tests; the same SQL shape runs on
PostgreSQL through psycopg when a ``postgresql://`` URL is configured. Row
level security policies for PostgreSQL are declared in ``schema.sql``; the
application-level tenant predicate is enforced here on every query regardless
of backend.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from .ids import canonical_json, content_hash, iso, new_id, utc_now


# Secondary indexes maintained transactionally on every put: kind -> indexed state fields.
DEFAULT_INDEXES: dict[str, tuple[str, ...]] = {
    "grant": ("grantee_id",),
    "role_assignment": ("actor_id",),
    "approval": ("proposal_id",),
    "outcome": ("proposal_id",),
    "proposal": ("mission_id",),
    "signature": ("record_id",),
}


class ConflictError(Exception):
    """Expected revision did not match the stored revision."""


class NotFoundError(KeyError):
    pass


class CrossTenantError(PermissionError):
    pass


class LeaseError(Exception):
    """A fencing token is stale or the lease is held by another owner."""


@dataclass(frozen=True)
class Record:
    tenant_id: str
    kind: str
    id: str
    revision: int
    state: dict[str, Any]
    content_hash: str
    updated_at: str

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)


@dataclass(frozen=True)
class Event:
    event_id: str
    tenant_id: str
    type: str
    aggregate_kind: str
    aggregate_id: str
    revision: int
    payload: dict[str, Any]
    occurred_at: str
    schema_version: int = 1
    causation_id: str | None = None
    correlation_id: str | None = None
    scope: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    tenant_id: str
    actor_id: str
    action: str
    aggregate_kind: str
    aggregate_id: str
    revision: int
    before_hash: str | None
    after_hash: str
    reason: str | None
    occurred_at: str
    details: dict[str, Any]


# Each fact is stored once. A record's content lives only in its immutable
# revisions; ``aggregates`` holds just the pointer to the current revision.
# ``prev_hash`` is set on hash-chained audit entries (CMO verification decisions).
_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS aggregate_revisions (
  tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
  state TEXT NOT NULL, content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, kind, id, revision));
CREATE TABLE IF NOT EXISTS aggregates (
  tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, kind, id),
  CONSTRAINT aggregates_current_revision FOREIGN KEY (tenant_id, kind, id, revision)
    REFERENCES aggregate_revisions (tenant_id, kind, id, revision));
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  action TEXT NOT NULL, aggregate_kind TEXT NOT NULL, aggregate_id TEXT NOT NULL,
  revision INTEGER NOT NULL, before_hash TEXT, after_hash TEXT NOT NULL, reason TEXT,
  occurred_at TEXT NOT NULL, details TEXT NOT NULL, prev_hash TEXT);
CREATE INDEX IF NOT EXISTS audit_aggregate ON audit (tenant_id, aggregate_kind, aggregate_id);
CREATE TABLE IF NOT EXISTS outbox (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, tenant_id TEXT NOT NULL,
  type TEXT NOT NULL, aggregate_kind TEXT NOT NULL, aggregate_id TEXT NOT NULL,
  revision INTEGER NOT NULL, payload TEXT NOT NULL, occurred_at TEXT NOT NULL,
  published_at TEXT);
CREATE INDEX IF NOT EXISTS outbox_pending ON outbox (published_at, seq);
CREATE TABLE IF NOT EXISTS inbox (
  consumer TEXT NOT NULL, event_id TEXT NOT NULL, processed_at TEXT NOT NULL,
  PRIMARY KEY (consumer, event_id));
CREATE TABLE IF NOT EXISTS leases (
  tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
  token INTEGER NOT NULL, expires_at TEXT NOT NULL, PRIMARY KEY (tenant_id, kind, id));
CREATE TABLE IF NOT EXISTS edges (
  tenant_id TEXT NOT NULL, up_kind TEXT NOT NULL, up_id TEXT NOT NULL,
  down_kind TEXT NOT NULL, down_id TEXT NOT NULL, relation TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, up_kind, up_id, down_kind, down_id, relation));
CREATE INDEX IF NOT EXISTS edges_down ON edges (tenant_id, down_kind, down_id);
CREATE TABLE IF NOT EXISTS blobs (
  tenant_id TEXT NOT NULL, digest TEXT NOT NULL, content BLOB NOT NULL, media_type TEXT,
  stored_at TEXT NOT NULL, PRIMARY KEY (tenant_id, digest));
"""

_PG_DDL = (
    _SQLITE_DDL.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    .replace("BLOB", "BYTEA")
)

_CURRENT = ("FROM aggregates a JOIN aggregate_revisions r ON r.tenant_id=a.tenant_id AND r.kind=a.kind "
            "AND r.id=a.id AND r.revision=a.revision")

# Event fields held in their own outbox columns; the payload column stores only the rest.
_EVENT_COLUMNS = ("event_id", "tenant_id", "type", "aggregate_kind", "aggregate_id", "revision", "occurred_at")
_OUTBOX_SELECT = "SELECT seq, " + ", ".join(_EVENT_COLUMNS) + ", payload FROM outbox"


def _event_from_row(row: tuple) -> tuple[int, Event]:
    body = json.loads(row[-1])
    body.update(zip(_EVENT_COLUMNS, row[1:-1]))
    body["revision"] = int(body["revision"])
    return int(row[0]), Event(**body)


_FIELD_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _indexed_fields() -> list[str]:
    fields = sorted({f for names in DEFAULT_INDEXES.values() for f in names})
    if any(not _FIELD_NAME.match(f) for f in fields):
        raise ValueError("indexed field names must be lowercase identifiers")
    return fields


def _upgrade_sqlite(conn: sqlite3.Connection) -> None:
    """Bring a database created by an earlier schema to the normalized shape.

    Earlier versions copied the current state, hash and timestamp into
    ``aggregates`` and kept a derived ``idx`` table. The copy is dropped only
    after every row is shown to equal its recorded revision.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(aggregates)")}
    if "state" in columns:
        drift = conn.execute(
            "SELECT COUNT(*) FROM aggregates a LEFT JOIN aggregate_revisions r ON r.tenant_id=a.tenant_id "
            "AND r.kind=a.kind AND r.id=a.id AND r.revision=a.revision "
            "WHERE r.state IS NULL OR r.state<>a.state OR r.content_hash<>a.content_hash").fetchone()[0]
        if drift:
            raise RuntimeError(f"{drift} current record(s) differ from their recorded revision; refusing to drop the copy")
        conn.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE aggregates_v2 (
              tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
              PRIMARY KEY (tenant_id, kind, id),
              CONSTRAINT aggregates_current_revision FOREIGN KEY (tenant_id, kind, id, revision)
                REFERENCES aggregate_revisions (tenant_id, kind, id, revision));
            INSERT INTO aggregates_v2 (tenant_id, kind, id, revision) SELECT tenant_id, kind, id, revision FROM aggregates;
            DROP TABLE aggregates;
            ALTER TABLE aggregates_v2 RENAME TO aggregates;
            COMMIT;
        """)
    if "prev_hash" not in {row[1] for row in conn.execute("PRAGMA table_info(audit)")}:
        conn.execute("ALTER TABLE audit ADD COLUMN prev_hash TEXT")
    conn.execute("DROP TABLE IF EXISTS idx")


# Same append-only guarantee PostgreSQL enforces with lifesci_no_mutation().
_SQLITE_APPEND_ONLY = "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_{op.lower()} BEFORE {op} ON {t} "
    f"BEGIN SELECT RAISE(ABORT, 'append-only table {t}'); END;\n"
    for t in ("audit", "aggregate_revisions") for op in ("UPDATE", "DELETE"))


def apply_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SQLITE_DDL)
    _upgrade_sqlite(conn)
    conn.executescript(_SQLITE_APPEND_ONLY)
    conn.execute("CREATE INDEX IF NOT EXISTS audit_chain ON audit (tenant_id, seq) WHERE prev_hash IS NOT NULL")


# Idempotent upgrade of databases created before normalization. Runs as the
# schema owner; row_security=off makes it fail loudly rather than verify an
# RLS-filtered (empty) view of the data.
_PG_UPGRADE = """
DO $$ BEGIN
  PERFORM set_config('row_security', 'off', true);
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
             AND table_name = 'aggregates' AND column_name = 'state') THEN
    IF EXISTS (SELECT 1 FROM aggregates a LEFT JOIN aggregate_revisions r ON r.tenant_id = a.tenant_id
               AND r.kind = a.kind AND r.id = a.id AND r.revision = a.revision
               WHERE r.state IS DISTINCT FROM a.state OR r.content_hash IS DISTINCT FROM a.content_hash) THEN
      RAISE EXCEPTION 'current records differ from their recorded revision; refusing to drop the copy';
    END IF;
    ALTER TABLE aggregates DROP COLUMN state, DROP COLUMN content_hash, DROP COLUMN updated_at;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'aggregates_current_revision') THEN
    ALTER TABLE aggregates ADD CONSTRAINT aggregates_current_revision FOREIGN KEY (tenant_id, kind, id, revision)
      REFERENCES aggregate_revisions (tenant_id, kind, id, revision);
  END IF;
END $$;
DROP INDEX IF EXISTS aggregates_kind;
DROP TABLE IF EXISTS idx;
ALTER TABLE audit ADD COLUMN IF NOT EXISTS prev_hash TEXT;
CREATE INDEX IF NOT EXISTS audit_chain ON audit (tenant_id, seq) WHERE prev_hash IS NOT NULL;
""" + "".join(
    f"CREATE INDEX IF NOT EXISTS revisions_by_{f} ON aggregate_revisions (tenant_id, kind, ((state::jsonb) ->> '{f}'));\n"
    for f in _indexed_fields())


class _Sqlite:
    paramstyle = "?"

    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
        apply_sqlite_schema(self.conn)
        self.lock = threading.RLock()

    @staticmethod
    def json_text(column: str, field: str) -> str:
        return f"json_extract({column}, '$.{field}')"

    def begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self.conn.execute("COMMIT")

    def rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    def execute(self, sql: str, params: tuple = ()) -> Any:
        with self.lock:
            return self.conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def last_seq(self, cursor: Any) -> int:
        return int(cursor.lastrowid)

    def bind_tenant(self, tenant_id: str, local: bool) -> None:
        pass  # SQLite relies on the application predicate and transaction binding


_PG_RLS = """
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['aggregates','aggregate_revisions','audit','outbox','leases','blobs','edges'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)) '
                   'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))', t);
  END LOOP;
END $$;
CREATE OR REPLACE FUNCTION lifesci_no_mutation() RETURNS trigger LANGUAGE plpgsql AS
$$ BEGIN RAISE EXCEPTION 'append-only table %', TG_TABLE_NAME; END $$;
DROP TRIGGER IF EXISTS audit_append_only ON audit;
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION lifesci_no_mutation();
DROP TRIGGER IF EXISTS revisions_append_only ON aggregate_revisions;
CREATE TRIGGER revisions_append_only BEFORE UPDATE OR DELETE ON aggregate_revisions
  FOR EACH ROW EXECUTE FUNCTION lifesci_no_mutation();
"""


def migrate_postgres(owner_url: str, app_role: str | None = None) -> None:
    """Apply schema, RLS policies and append-only triggers as the schema owner.

    The runtime should connect as ``app_role`` (non-owner, no BYPASSRLS) so policies apply.
    """
    import psycopg

    from .cmo_schema import CMO_PG_DDL, CMO_PG_POLICIES, cmo_grants

    with psycopg.connect(owner_url, autocommit=True) as conn:
        conn.execute(_PG_DDL)
        conn.execute(_PG_UPGRADE)
        conn.execute(_PG_RLS)
        conn.execute(CMO_PG_DDL)
        conn.execute(CMO_PG_POLICIES)
        if app_role:
            for statement in platform_grants(app_role) + cmo_grants(app_role):
                conn.execute(statement)


def platform_grants(role: str) -> list[str]:
    return [
        f'GRANT USAGE ON SCHEMA public TO "{role}"',
        f'GRANT SELECT, INSERT, UPDATE ON aggregates, outbox, leases, inbox, edges TO "{role}"',
        f'GRANT SELECT, INSERT ON aggregate_revisions, audit, blobs TO "{role}"',
        f'GRANT USAGE ON SEQUENCE audit_seq_seq, outbox_seq_seq TO "{role}"',
    ]


_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_PROTECTED_ROLES = {"postgres"}


def ensure_postgres_role(owner_url: str, role: str, password: str) -> None:
    """Create or update the non-owner login role used by the application.

    The role gets LOGIN but no superuser, database creation, role creation or
    BYPASSRLS, so row-level security applies to every query it runs.
    """
    import psycopg
    from psycopg import sql

    if role in _PROTECTED_ROLES:
        raise ValueError(f"refusing to manage the privileged role {role!r}")
    if not _ROLE_NAME.match(role):
        raise ValueError("role must be 1-63 lowercase letters, digits or underscores, starting with a letter")
    if len(password) < 16:
        raise ValueError("app role passwords must be at least 16 characters")

    with psycopg.connect(owner_url, autocommit=True) as conn:
        ident = sql.Identifier(role)
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        if exists:
            conn.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(ident, sql.Literal(password)))
        else:
            conn.execute(sql.SQL(
                "CREATE ROLE {} WITH LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
            ).format(ident, sql.Literal(password)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(ident))


def verify_postgres_role(url: str) -> str:
    """Check that the runtime role can query the schema but is not above RLS.

    Returns the connected role name. Raises if the connection cannot read the
    platform tables or if the role bypasses row-level security.
    """
    import psycopg

    with psycopg.connect(url, connect_timeout=15) as conn:
        who = conn.execute("SELECT current_user").fetchone()[0]
        privileged = conn.execute(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()[0]
        if privileged:
            raise RuntimeError(f"{who} is a superuser or bypasses row-level security")
        conn.execute("SELECT count(*) FROM aggregates").fetchone()
        return who


class _Postgres:
    paramstyle = "%s"

    def __init__(self, url: str, migrate: bool) -> None:
        import psycopg  # optional dependency

        if migrate:
            migrate_postgres(url)
        self.conn = psycopg.connect(url, autocommit=True)
        self.lock = threading.RLock()

    def begin(self) -> None:
        self.conn.execute("BEGIN")

    def commit(self) -> None:
        self.conn.execute("COMMIT")

    def rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    def bind_tenant(self, tenant_id: str, local: bool) -> None:
        self.conn.execute("SELECT set_config('app.tenant_id', %s, %s)", (tenant_id, local))

    @staticmethod
    def json_text(column: str, field: str) -> str:
        # Matches the revisions_by_<field> expression indexes.
        return f"(({column})::jsonb ->> '{field}')"

    def execute(self, sql: str, params: tuple = ()) -> Any:
        cur = self.conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self.execute(sql, params).fetchall()

    def last_seq(self, cursor: Any) -> int:
        return int(cursor.fetchone()[0])


class Transaction:
    """Unit of work: reads, versioned writes, audit entries and outbox events commit together."""

    def __init__(self, store: "RecordStore", actor_id: str, correlation_id: str | None, *,
                 writable: bool = True) -> None:
        self.store = store
        self.actor_id = actor_id
        self.correlation_id = correlation_id or new_id("corr")
        self.events: list[Event] = []
        self._db = store._db
        self._writable = writable
        self.tenant_id: str | None = None

    def _bind(self, tenant_id: str) -> None:
        """A write transaction belongs to exactly one tenant; on PostgreSQL this also scopes RLS."""
        if self.tenant_id == tenant_id:
            return
        if self.tenant_id is not None and self._writable:
            raise CrossTenantError(f"transaction bound to {self.tenant_id} cannot touch {tenant_id}")
        self._db.bind_tenant(tenant_id, self._writable)
        self.tenant_id = tenant_id

    def get(self, tenant_id: str, kind: str, id: str) -> Record | None:
        self._bind(tenant_id)
        row = self._db.fetchone(
            f"SELECT a.revision, r.state, r.content_hash, r.recorded_at {_CURRENT} WHERE a.tenant_id=? AND a.kind=? AND a.id=?",
            (tenant_id, kind, id),
        )
        if row is None:
            return None
        return Record(tenant_id, kind, id, int(row[0]), json.loads(row[1]), row[2], row[3])

    def require(self, tenant_id: str, kind: str, id: str) -> Record:
        self._bind(tenant_id)
        record = self.get(tenant_id, kind, id)
        if record is None:
            raise NotFoundError(f"{kind}:{id}")
        return record

    def list(self, tenant_id: str, kind: str, predicate: Callable[[dict], bool] | None = None,
             limit: int | None = None) -> list[Record]:
        self._bind(tenant_id)
        rows = self._db.fetchall(
            f"SELECT a.id, a.revision, r.state, r.content_hash, r.recorded_at {_CURRENT} "
            "WHERE a.tenant_id=? AND a.kind=? ORDER BY r.recorded_at, a.id",
            (tenant_id, kind),
        )
        out = []
        for id, revision, state, digest, updated in rows:
            parsed = json.loads(state)
            if predicate is None or predicate(parsed):
                out.append(Record(tenant_id, kind, id, int(revision), parsed, digest, updated))
                if limit and len(out) >= limit:
                    break
        return out

    def find(self, tenant_id: str, kind: str, field: str, value: Any) -> list[Record]:
        """Lookup by a declared field of the current revision (see DEFAULT_INDEXES).

        Reads the field from the stored content itself (indexed by expression on
        PostgreSQL), so there is no separate copy that could fall out of date.
        """
        self._bind(tenant_id)
        if field not in self.store.indexes.get(kind, ()) or not _FIELD_NAME.match(field):
            raise KeyError(f"{kind}.{field} is not indexed")
        rows = self._db.fetchall(
            f"SELECT a.id, a.revision, r.state, r.content_hash, r.recorded_at {_CURRENT} "
            f"WHERE a.tenant_id=? AND a.kind=? AND r.kind=? AND {self._db.json_text('r.state', field)}=? ORDER BY a.id",
            (tenant_id, kind, kind, str(value)))
        return [Record(tenant_id, kind, r[0], int(r[1]), json.loads(r[2]), r[3], r[4]) for r in rows]

    def revision(self, tenant_id: str, kind: str, id: str, revision: int) -> Record | None:
        self._bind(tenant_id)
        row = self._db.fetchone(
            "SELECT state, content_hash, recorded_at FROM aggregate_revisions WHERE tenant_id=? AND kind=? AND id=? AND revision=?",
            (tenant_id, kind, id, revision),
        )
        if row is None:
            return None
        return Record(tenant_id, kind, id, revision, json.loads(row[0]), row[1], row[2])

    def put(self, tenant_id: str, kind: str, id: str, state: dict[str, Any], *,
            expected_revision: int | None, action: str, reason: str | None = None,
            details: dict[str, Any] | None = None, event_type: str | None = None,
            event_payload: dict[str, Any] | None = None) -> Record:
        """Write a new revision. ``expected_revision`` None means create-only."""
        current = self.get(tenant_id, kind, id)
        if expected_revision is None and current is not None:
            raise ConflictError(f"{kind}:{id} already exists at revision {current.revision}")
        if expected_revision is not None and (current is None or current.revision != expected_revision):
            actual = current.revision if current else None
            raise ConflictError(f"{kind}:{id} expected revision {expected_revision}, found {actual}")
        revision = (current.revision + 1) if current else 1
        now = iso(utc_now())
        digest = content_hash(state)
        encoded = canonical_json(state)
        self._db.execute(
            "INSERT INTO aggregate_revisions (tenant_id, kind, id, revision, state, content_hash, recorded_at) VALUES (?,?,?,?,?,?,?)",
            (tenant_id, kind, id, revision, encoded, digest, now),
        )
        if current is None:
            self._db.execute("INSERT INTO aggregates (tenant_id, kind, id, revision) VALUES (?,?,?,?)",
                             (tenant_id, kind, id, revision))
        else:
            self._db.execute("UPDATE aggregates SET revision=? WHERE tenant_id=? AND kind=? AND id=? AND revision=?",
                             (revision, tenant_id, kind, id, expected_revision))
        self._db.execute(
            "INSERT INTO audit (tenant_id, actor_id, action, aggregate_kind, aggregate_id, revision, before_hash, after_hash, reason, occurred_at, details) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (tenant_id, self.actor_id, action, kind, id, revision,
             current.content_hash if current else None, digest, reason, now, canonical_json(details or {})),
        )
        if event_type:
            self.emit(tenant_id, event_type, kind, id, revision, event_payload or {})
        return Record(tenant_id, kind, id, revision, state, digest, now)

    def emit(self, tenant_id: str, type: str, kind: str, id: str, revision: int,
             payload: dict[str, Any], scope: dict[str, Any] | None = None) -> Event:
        self._bind(tenant_id)
        event = Event(new_id("evt"), tenant_id, type, kind, id, revision, payload, iso(utc_now()),
                      correlation_id=self.correlation_id, scope=scope or {})
        self._db.execute(
            "INSERT INTO outbox (event_id, tenant_id, type, aggregate_kind, aggregate_id, revision, payload, occurred_at) VALUES (?,?,?,?,?,?,?,?)",
            (event.event_id, tenant_id, type, kind, id, revision,
             canonical_json({k: v for k, v in event.to_dict().items() if k not in _EVENT_COLUMNS}), event.occurred_at),
        )
        self.events.append(event)
        return event

    def audit(self, tenant_id: str, kind: str, id: str, limit: int = 200) -> list[AuditEntry]:
        self._bind(tenant_id)
        rows = self._db.fetchall(
            "SELECT seq, actor_id, action, revision, before_hash, after_hash, reason, occurred_at, details FROM audit "
            "WHERE tenant_id=? AND aggregate_kind=? AND aggregate_id=? ORDER BY seq DESC LIMIT ?",
            (tenant_id, kind, id, limit),
        )
        return [AuditEntry(int(r[0]), tenant_id, r[1], r[2], kind, id, int(r[3]), r[4], r[5], r[6], r[7], json.loads(r[8]))
                for r in rows]

    def put_blob(self, tenant_id: str, content: bytes, media_type: str | None = None) -> str:
        self._bind(tenant_id)
        digest = content_hash(content)
        if self._db.fetchone("SELECT 1 FROM blobs WHERE tenant_id=? AND digest=?", (tenant_id, digest)) is None:
            self._db.execute(
                "INSERT INTO blobs (tenant_id, digest, content, media_type, stored_at) VALUES (?,?,?,?,?)",
                (tenant_id, digest, content, media_type, iso(utc_now())),
            )
        return digest

    def get_blob(self, tenant_id: str, digest: str) -> bytes | None:
        self._bind(tenant_id)
        row = self._db.fetchone("SELECT content FROM blobs WHERE tenant_id=? AND digest=?", (tenant_id, digest))
        return bytes(row[0]) if row else None

    def acquire_lease(self, tenant_id: str, kind: str, id: str, owner: str, ttl_seconds: int = 300) -> int:
        """Return a monotonic fencing token; raises LeaseError if another live owner holds it."""
        self._bind(tenant_id)
        now = utc_now()
        row = self._db.fetchone(
            "SELECT owner, token, expires_at FROM leases WHERE tenant_id=? AND kind=? AND id=?", (tenant_id, kind, id))
        expires = iso(now + timedelta(seconds=ttl_seconds))
        if row is None:
            self._db.execute(
                "INSERT INTO leases (tenant_id, kind, id, owner, token, expires_at) VALUES (?,?,?,?,?,?)",
                (tenant_id, kind, id, owner, 1, expires))
            return 1
        held_by, token, held_until = row
        if held_by != owner and held_until > iso(now):
            raise LeaseError(f"{kind}:{id} leased by {held_by} until {held_until}")
        token = int(token) + 1
        self._db.execute(
            "UPDATE leases SET owner=?, token=?, expires_at=? WHERE tenant_id=? AND kind=? AND id=?",
            (owner, token, expires, tenant_id, kind, id))
        return token

    def expire_lease(self, tenant_id: str, kind: str, id: str) -> None:
        """Force-expire a lease (worker declared lost); its token stays stale because the next acquire increments it."""
        self._bind(tenant_id)
        self._db.execute("UPDATE leases SET expires_at=? WHERE tenant_id=? AND kind=? AND id=?",
                         (iso(utc_now() - timedelta(seconds=1)), tenant_id, kind, id))

    def check_lease(self, tenant_id: str, kind: str, id: str, owner: str, token: int) -> None:
        self._bind(tenant_id)
        row = self._db.fetchone(
            "SELECT owner, token FROM leases WHERE tenant_id=? AND kind=? AND id=?", (tenant_id, kind, id))
        if row is None or row[0] != owner or int(row[1]) != token:
            raise LeaseError(f"stale fencing token {token} for {kind}:{id}")

    def add_edge(self, tenant_id: str, up: tuple[str, str], down: tuple[str, str], relation: str) -> None:
        self._bind(tenant_id)
        if self._db.fetchone(
            "SELECT 1 FROM edges WHERE tenant_id=? AND up_kind=? AND up_id=? AND down_kind=? AND down_id=? AND relation=?",
            (tenant_id, up[0], up[1], down[0], down[1], relation)) is None:
            self._db.execute(
                "INSERT INTO edges (tenant_id, up_kind, up_id, down_kind, down_id, relation, created_at) VALUES (?,?,?,?,?,?,?)",
                (tenant_id, up[0], up[1], down[0], down[1], relation, iso(utc_now())))

    def edges_from(self, tenant_id: str, kind: str, id: str) -> list[tuple[str, str, str]]:
        self._bind(tenant_id)
        return [(r[0], r[1], r[2]) for r in self._db.fetchall(
            "SELECT down_kind, down_id, relation FROM edges WHERE tenant_id=? AND up_kind=? AND up_id=?",
            (tenant_id, kind, id))]

    def edges_to(self, tenant_id: str, kind: str, id: str) -> list[tuple[str, str, str]]:
        self._bind(tenant_id)
        return [(r[0], r[1], r[2]) for r in self._db.fetchall(
            "SELECT up_kind, up_id, relation FROM edges WHERE tenant_id=? AND down_kind=? AND down_id=?",
            (tenant_id, kind, id))]

    def inbox_claim(self, consumer: str, event_id: str) -> bool:
        """Return False if the consumer already processed this event (idempotent handling)."""
        if self._db.fetchone("SELECT 1 FROM inbox WHERE consumer=? AND event_id=?", (consumer, event_id)):
            return False
        self._db.execute("INSERT INTO inbox (consumer, event_id, processed_at) VALUES (?,?,?)",
                         (consumer, event_id, iso(utc_now())))
        return True


class RecordStore:
    def __init__(self, url: str = ":memory:", *, migrate: bool = True) -> None:
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            self._db: Any = _Postgres(url, migrate)
        else:
            path = url
            if url.startswith("sqlite:///"):
                path = url[len("sqlite:///"):]
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._db = _Sqlite(path)
        self.backend = "postgresql" if isinstance(self._db, _Postgres) else "sqlite"
        self.indexes: dict[str, tuple[str, ...]] = dict(DEFAULT_INDEXES)
        self._listeners: list[Callable[[Event], None]] = []
        self._local = threading.local()

    @contextmanager
    def transaction(self, actor_id: str = "system", correlation_id: str | None = None) -> Iterator[Transaction]:
        """Open a unit of work. A nested call on the same thread joins the outer transaction,
        so services that each open a transaction compose atomically (one commit or one rollback)."""
        outer = getattr(self._local, "tx", None)
        if outer is not None:
            yield outer
            return
        with self._db.lock:
            self._db.begin()
            tx = Transaction(self, actor_id, correlation_id)
            self._local.tx = tx
            try:
                yield tx
            except BaseException:
                self._local.tx = None
                self._db.rollback()
                raise
            self._local.tx = None
            self._db.commit()
        for event in tx.events:
            for listener in self._listeners:
                listener(event)

    def read(self) -> Transaction:
        """Read-only unit of work (no commit); for single lookups outside a transaction."""
        return Transaction(self, "reader", None, writable=False)

    def subscribe(self, listener: Callable[[Event], None]) -> None:
        """In-process listener invoked after commit; durable consumers should use ``drain_outbox``."""
        self._listeners.append(listener)

    def drain_outbox(self, publish: Callable[[Event], None], limit: int = 500, *, tenant_id: str | None = None) -> int:
        """At-least-once publication of committed events. Marks published only after the publisher returns.

        Under PostgreSQL RLS the app role drains per tenant; a cross-tenant dispatcher needs its own role.
        """
        with self._db.lock:
            if tenant_id:
                self._db.bind_tenant(tenant_id, False)
                rows = self._db.fetchall(f"{_OUTBOX_SELECT} WHERE published_at IS NULL AND tenant_id=? "
                                         "ORDER BY seq LIMIT ?", (tenant_id, limit))
            else:
                rows = self._db.fetchall(
                    f"{_OUTBOX_SELECT} WHERE published_at IS NULL ORDER BY seq LIMIT ?", (limit,))
        count = 0
        for row in rows:
            seq, event = _event_from_row(row)
            publish(event)
            with self._db.lock:
                self._db.begin()
                if tenant_id:
                    self._db.bind_tenant(tenant_id, True)
                self._db.execute("UPDATE outbox SET published_at=? WHERE seq=?", (iso(utc_now()), seq))
                self._db.commit()
            count += 1
        return count

    def pending_outbox(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) FROM outbox WHERE published_at IS NULL")
        return int(row[0]) if row else 0

    def events_since(self, tenant_id: str, after_seq: int = 0, limit: int = 500,
                     types: tuple[str, ...] | None = None) -> list[tuple[int, Event]]:
        """Cursor-based event replay for reconnecting clients (LS-069)."""
        with self._db.lock:
            self._db.bind_tenant(tenant_id, False)
            rows = self._db.fetchall(
                f"{_OUTBOX_SELECT} WHERE tenant_id=? AND seq>? ORDER BY seq LIMIT ?",
                (tenant_id, after_seq, limit))
        out = []
        for row in rows:
            seq, event = _event_from_row(row)
            if types is None or event.type in types:
                out.append((seq, event))
        return out

    def head_seq(self, tenant_id: str) -> int:
        with self._db.lock:
            self._db.bind_tenant(tenant_id, False)
            row = self._db.fetchone("SELECT COALESCE(MAX(seq),0) FROM outbox WHERE tenant_id=?", (tenant_id,))
        return int(row[0]) if row else 0
