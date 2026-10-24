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
    subprocess.run(["initdb", "-D", str(data), "-U", "owner", "--auth=trust", "-E", "UTF8"], check=True,
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
        conn.execute("INSERT INTO aggregates (tenant_id, kind, id, revision, state, content_hash, updated_at) "
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
