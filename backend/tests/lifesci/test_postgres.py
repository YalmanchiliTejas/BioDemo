"""Runs the record store against a throwaway local PostgreSQL cluster (skipped if binaries are absent).

Verifies D23/LS-068 at the database layer: a non-owner runtime role is confined by
row-level security even if application code omits or forges a tenant predicate, and
audit/revision tables are append-only.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

from src.lifesci.actions import ActionService  # noqa: E402
from src.lifesci.evidence import EvidenceService  # noqa: E402
from src.lifesci.identity import IdentityService  # noqa: E402
from src.lifesci.ownership import Ownership, OwnershipRegistry  # noqa: E402
from src.lifesci.store import RecordStore, migrate_postgres  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("initdb") or not shutil.which("pg_ctl"),
                                reason="local PostgreSQL binaries not installed")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def pg():
    root = Path(tempfile.mkdtemp(prefix="lifesci-pg-"))
    data, port = root / "data", _port()
    subprocess.run(["initdb", "-D", str(data), "-U", "owner", "--auth=trust", "-E", "UTF8", "--locale=C"], check=True,
                   capture_output=True)
    subprocess.run(["pg_ctl", "-D", str(data), "-o", f"-p {port} -k {root} -c listen_addresses=127.0.0.1",
                    "-l", str(root / "log"), "start"], check=True, capture_output=True)
    owner = f"postgresql://owner@127.0.0.1:{port}/postgres"
    for _ in range(50):
        try:
            psycopg.connect(owner).close()
            break
        except psycopg.OperationalError:
            time.sleep(0.1)
    with psycopg.connect(owner, autocommit=True) as c:
        c.execute("CREATE ROLE lifesci_app LOGIN NOSUPERUSER NOBYPASSRLS")
    migrate_postgres(owner, app_role="lifesci_app")
    yield SimpleURLs(owner, f"postgresql://lifesci_app@127.0.0.1:{port}/postgres")
    subprocess.run(["pg_ctl", "-D", str(data), "stop", "-m", "immediate"], capture_output=True)
    shutil.rmtree(root, ignore_errors=True)


class SimpleURLs:
    def __init__(self, owner: str, app: str) -> None:
        self.owner, self.app = owner, app


def test_core_flow_on_postgres_as_app_role(pg):
    s = RecordStore(pg.app, migrate=False)
    idn, own = IdentityService(s), OwnershipRegistry(s)
    ev, act = EvidenceService(s, idn), ActionService(s, idn, own)
    for a, r in [("op", "operator"), ("sup", "supervisor")]:
        idn.assign_role("pg-a", a, r, site_id="S1")
    op = idn.context_for("pg-a", "op")
    e = ev.ingest(op, source_system="LIMS", source_record_id="1", content=b"v1", media_type="t", site_id="S1",
                  event_time=None)
    own.assign("pg-a", Ownership("place_hold", "S1", "external", "MES", ("place_hold",)), by="a", reason="c")
    p = act.propose(op, target_system="MES", operation="place_hold", target_id="B", payload={},
                    basis=[{"kind": "evidence", "id": e["evidence_id"], "revision": 1, "site_id": "S1"}],
                    rationale="r", expected_result="e", owner_id="sup", site_id="S1")
    out = act.decide(idn.context_for("pg-a", "sup"), p["proposal_id"], expected_revision=1, decision="approved",
                     role="supervisor")
    assert out["intent"]["status"] == "queued"
    ev.ingest(op, source_system="LIMS", source_record_id="1", content=b"v2", media_type="t", site_id="S1",
              event_time=None)
    assert s.read().get("pg-a", "proposal", p["proposal_id"]).state["status"] == "stale"
    assert ev.original(op, e["evidence_id"]) == b"v2"


def test_LS068_rls_blocks_cross_tenant_reads_and_writes(pg):
    a = RecordStore(pg.app, migrate=False)
    with a.transaction("x") as tx:
        tx.put("tenant-1", "secret", "s", {"v": "tenant-1 data"}, expected_revision=None, action="c")
    conn = psycopg.connect(pg.app, autocommit=True)
    conn.execute("SELECT set_config('app.tenant_id', 'tenant-2', false)")
    # application predicate deliberately omitted: RLS must still hide other tenants' rows
    assert conn.execute("SELECT count(*) FROM aggregates WHERE kind='secret'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM audit WHERE aggregate_kind='secret'").fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO aggregate_revisions (tenant_id, kind, id, revision, state, content_hash, recorded_at) "
                     "VALUES ('tenant-1','secret','forged',1,'{}','h','now')")
    conn.execute("SELECT set_config('app.tenant_id', '', false)")
    assert conn.execute("SELECT count(*) FROM aggregates").fetchone()[0] == 0  # unbound session sees nothing
    conn.close()


def test_audit_and_revisions_append_only(pg):
    s = RecordStore(pg.app, migrate=False)
    with s.transaction("x") as tx:
        tx.put("tenant-3", "thing", "t", {"v": 1}, expected_revision=None, action="c")
    owner = psycopg.connect(pg.owner, autocommit=True)  # even the owner hits the triggers
    owner.execute("SELECT set_config('app.tenant_id', 'tenant-3', false)")
    with pytest.raises(psycopg.errors.RaiseException):
        owner.execute("UPDATE audit SET actor_id='forged' WHERE tenant_id='tenant-3'")
    with pytest.raises(psycopg.errors.RaiseException):
        owner.execute("DELETE FROM aggregate_revisions WHERE tenant_id='tenant-3'")
    owner.close()


def test_ensure_runtime_role_is_unprivileged_and_migrated(pg):
    from src.lifesci.store import ensure_postgres_role, verify_postgres_role

    runtime_url = pg.app.replace("lifesci_app", "lifesci_pw_app")
    ensure_postgres_role(pg.owner, "lifesci_pw_app", "correct horse battery staple")
    migrate_postgres(pg.owner, app_role="lifesci_pw_app")
    assert verify_postgres_role(runtime_url) == "lifesci_pw_app"
    with psycopg.connect(pg.owner, autocommit=True) as conn:
        attrs = conn.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname = 'lifesci_pw_app'"
        ).fetchone()
    assert attrs == (False, False, False, False)


def test_upgrade_from_denormalized_schema_keeps_every_record(pg):
    """A database created before normalization is upgraded in place without losing records."""
    from src.lifesci.store import _PG_UPGRADE

    legacy = pg.owner.rsplit("/", 1)[0] + "/legacy"
    with psycopg.connect(pg.owner, autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS legacy")
        c.execute("CREATE DATABASE legacy")
    with psycopg.connect(legacy, autocommit=True) as c:
        c.execute("CREATE TABLE aggregate_revisions (tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, "
                  "revision INTEGER NOT NULL, state TEXT NOT NULL, content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL, "
                  "PRIMARY KEY (tenant_id, kind, id, revision))")
        c.execute("CREATE TABLE aggregates (tenant_id TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, "
                  "state TEXT NOT NULL, content_hash TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, kind, id))")
        c.execute("CREATE TABLE idx (tenant_id TEXT, kind TEXT, field TEXT, value TEXT, id TEXT)")
        c.execute("CREATE TABLE audit (seq BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL)")
        for rev, state in [(1, '{"proposal_id":"P1","v":1}'), (2, '{"proposal_id":"P1","v":2}')]:
            c.execute("INSERT INTO aggregate_revisions VALUES ('t','approval','A',%s,%s,%s,'2026-01-0%sT00:00:00')",
                      (rev, state, f"h{rev}", rev))
        c.execute("""INSERT INTO aggregates VALUES ('t','approval','A',2,'{"proposal_id":"P1","v":2}','h2','2026-01-02T00:00:00')""")
        c.execute(_PG_UPGRADE)
        c.execute(_PG_UPGRADE)  # idempotent
        assert c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='aggregates' "
                         "ORDER BY ordinal_position").fetchall() == [("tenant_id",), ("kind",), ("id",), ("revision",)]
        assert c.execute("SELECT to_regclass('idx')").fetchone()[0] is None
        with pytest.raises(psycopg.errors.ForeignKeyViolation):  # the pointer must name a recorded revision
            c.execute("UPDATE aggregates SET revision=3")
    with psycopg.connect(pg.owner, autocommit=True) as c:
        c.execute("DROP DATABASE legacy")


def test_upgrade_refuses_when_current_copy_differs(pg):
    from src.lifesci.store import _PG_UPGRADE

    drifted = pg.owner.rsplit("/", 1)[0] + "/drifted"
    with psycopg.connect(pg.owner, autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS drifted")
        c.execute("CREATE DATABASE drifted")
    with psycopg.connect(drifted, autocommit=True) as c:
        c.execute("CREATE TABLE aggregate_revisions (tenant_id TEXT, kind TEXT, id TEXT, revision INTEGER, state TEXT, "
                  "content_hash TEXT, recorded_at TEXT, PRIMARY KEY (tenant_id, kind, id, revision))")
        c.execute("CREATE TABLE aggregates (tenant_id TEXT, kind TEXT, id TEXT, revision INTEGER, state TEXT, "
                  "content_hash TEXT, updated_at TEXT, PRIMARY KEY (tenant_id, kind, id))")
        c.execute("CREATE TABLE audit (seq BIGSERIAL PRIMARY KEY)")
        c.execute("INSERT INTO aggregate_revisions VALUES ('t','k','A',1,'{\"v\":1}','h1','now')")
        c.execute("INSERT INTO aggregates VALUES ('t','k','A',1,'{\"v\":\"edited\"}','h1','now')")
        with pytest.raises(psycopg.errors.RaiseException, match="differ"):
            c.execute(_PG_UPGRADE)
        assert c.execute("SELECT state FROM aggregates").fetchone()[0] == '{"v":"edited"}'
    with psycopg.connect(pg.owner, autocommit=True) as c:
        c.execute("DROP DATABASE drifted")


def test_find_uses_current_revision_content(pg):
    s = RecordStore(pg.app, migrate=False)
    with s.transaction("x") as tx:
        tx.put("tenant-4", "approval", "A1", {"proposal_id": "P1"}, expected_revision=None, action="c")
        tx.put("tenant-4", "approval", "A1", {"proposal_id": "P2"}, expected_revision=1, action="u")
    tx = s.read()
    assert [r.id for r in tx.find("tenant-4", "approval", "proposal_id", "P2")] == ["A1"]
    assert tx.find("tenant-4", "approval", "proposal_id", "P1") == []  # earlier revisions are history, not matches


@pytest.fixture
def cmo_service(pg, tmp_path, monkeypatch):
    pytest.importorskip("polars")
    for name in ["OPENAI_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_AUTH_TOKEN", "SUPABASE_URL", "CMO_API_TOKEN"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CMO_DATABASE_URL", pg.app)
    from src.manufacturing_data.cmo.pipeline import IngestionService
    return IngestionService(tmp_path / "runtime")


def test_cmo_records_round_trip_on_postgres_as_app_role(cmo_service, tmp_path):
    import csv

    from src.manufacturing_data.cmo import quality
    from src.manufacturing_data.cmo.persistence import tenant_scope
    from src.manufacturing_data.cmo.pipeline import digest

    raw = tmp_path / "d"; raw.mkdir()
    with (raw / "process.csv").open("w", newline="") as stream:
        csv.writer(stream).writerows([["batch_id", "elapsed_h", "pH [pH]"], ["B", 0, 7], ["B", 1, 7.1]])
    service = cmo_service
    assert service.repo.backend == "postgresql"
    with tenant_scope("pg-cmo-a"):
        first = service.run(raw, "acme", "D")
        assert first["status"] == "complete", first.get("error")
        assert service.get(first["id"])["measurements"] == first["measurements"]  # bindings survive a reload
        layout = first["layouts"][0]
        service.confirm_template(first["id"], layout["fingerprint"], layout["mapping"], "qa", "Checked")
        second = service.run(raw, "acme", "D")
        assert second["summary"]["auto_accepted"] == 2 and second["summary"]["verified_package"]
        m = service.get(first["id"])["measurements"][0]
        corrected = service.review(first["id"], m["id"], "correct", "qa", "Read from source", binding=digest(m),
                                   value="7.2", unit="pH")
        stored = service.get(first["id"])
        assert stored["superseded_measurements"][0]["superseded_by"] == stored["measurements"][0]["id"]
        assert stored["reviews"] == corrected["reviews"] and stored["summary"] == corrected["summary"]
        assert [r["id"] for r in service.runs("acme")] == [first["id"], second["id"]]
        assert quality.guarantee(service.get(second["id"]))["holds"] and service.verify_audit()
        service.repo.save_delivery({"id": "delivery-x", "cmo": "acme", "files": [{"path": "a.csv", "size": 3, "sha256": "x"}]})
        assert service.repo.deliveries()[0]["files"][0]["path"] == "a.csv"
    with tenant_scope("pg-cmo-b"):  # another customer sees none of it
        assert service.runs() == [] and service.repo.deliveries() == [] and service.repo.template("acme", layout["fingerprint"]) is None
        with pytest.raises(KeyError):
            service.get(first["id"])
        assert service.verify_audit()


def test_cmo_decisions_are_append_only_and_app_role_is_limited(cmo_service, pg, tmp_path):
    import csv

    from src.manufacturing_data.cmo.persistence import tenant_scope

    raw = tmp_path / "d"; raw.mkdir()
    with (raw / "process.csv").open("w", newline="") as stream:
        csv.writer(stream).writerows([["batch_id", "elapsed_h", "pH [pH]"], ["B", 0, 7]])
    with tenant_scope("pg-cmo-c"):
        run = cmo_service.run(raw, "acme", "D")
        layout = run["layouts"][0]
        cmo_service.confirm_template(run["id"], layout["fingerprint"], layout["mapping"], "qa", "Checked")
    app = psycopg.connect(pg.app, autocommit=True)
    app.execute("SELECT set_config('app.tenant_id', 'pg-cmo-c', false)")
    for statement in ["UPDATE cmo_templates SET actor='x'", "DELETE FROM cmo_measurements", "UPDATE cmo_documents SET path='x'",
                      "UPDATE audit SET actor_id='x'"]:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute(statement)
    app.close()
    owner = psycopg.connect(pg.owner, autocommit=True)
    for statement in ["UPDATE cmo_templates SET actor='x'", "DELETE FROM cmo_templates", "UPDATE audit SET actor_id='x'"]:
        with pytest.raises(psycopg.errors.RaiseException):
            owner.execute(statement)
    owner.close()


def test_cmo_schema_sets_aside_tables_from_the_retired_layout(pg):
    """Old 0001 tables share names with the new ones but lack tenant_id; they are renamed, not dropped."""
    from src.lifesci.cmo_schema import CMO_PG_DDL

    url = pg.owner.rsplit("/", 1)[0] + "/retired"
    with psycopg.connect(pg.owner, autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS retired")
        c.execute("CREATE DATABASE retired")
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("CREATE TABLE cmo_runs (id text PRIMARY KEY, cmo text NOT NULL, config text NOT NULL, result text NOT NULL)")
        c.execute("CREATE INDEX cmo_runs_cmo_idx ON cmo_runs (cmo)")
        c.execute("INSERT INTO cmo_runs VALUES ('r1', 'acme', 'D', '{}')")
        c.execute(CMO_PG_DDL)
        c.execute(CMO_PG_DDL)  # idempotent
        assert c.execute("SELECT id FROM legacy_cmo_runs").fetchall() == [("r1",)]
        assert c.execute("SELECT count(*) FROM information_schema.columns WHERE table_name='cmo_runs' "
                         "AND column_name='tenant_id'").fetchone()[0] == 1
    with psycopg.connect(pg.owner, autocommit=True) as c:
        c.execute("DROP DATABASE retired")
