"""Durable queue. Mutations and metadata-only audit records share a transaction."""
import hashlib
import json
import time
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class Conflict(Exception):
    pass


class Store:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5)

    def migrate(self):
        with self.connect() as con:
            con.execute(Path(__file__).with_name("schema.sql").read_text())

    @staticmethod
    def audit(con, tenant, project, actor, action, ident, details=None):
        con.execute("INSERT INTO cloud_audit (occurred,tenant,project,actor,action,object_id,details) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (time.time(), tenant, project, actor, action, ident, Jsonb(details or {})))

    def submit(self, tenant, project, actor, key, request):
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with self.connect() as con:
            ident = uuid.uuid4().hex
            row = con.execute(
                "INSERT INTO cloud_jobs (id,tenant,project,actor,idempotency_key,request_hash,request,created,updated) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (tenant,project,idempotency_key) DO NOTHING RETURNING *",
                (ident, tenant, project, actor, key, digest, Jsonb(request), time.time(), time.time())).fetchone()
            if row:
                self.audit(con, tenant, project, actor, "job.submitted", ident)
            else:
                row = con.execute("SELECT * FROM cloud_jobs WHERE tenant=%s AND project=%s AND idempotency_key=%s",
                                  (tenant, project, key)).fetchone()
                if row["request_hash"] != digest:
                    raise Conflict("Idempotency key already used with different input")
            return self.public(row)

    @staticmethod
    def public(row):
        return {k: row[k] for k in ("id", "project", "state", "attempt", "created", "updated", "error_code")}

    def get(self, tenant, project, ident, actor):
        with self.connect() as con:
            row = con.execute("SELECT * FROM cloud_jobs WHERE tenant=%s AND project=%s AND id=%s",
                              (tenant, project, ident)).fetchone()
            if row:
                self.audit(con, tenant, project, actor, "job.read", ident)
            return row

    def cancel(self, tenant, project, ident, actor):
        with self.connect() as con:
            row = con.execute("UPDATE cloud_jobs SET state='cancelled',updated=%s "
                              "WHERE tenant=%s AND project=%s AND id=%s AND state IN ('queued','running') RETURNING *",
                              (time.time(), tenant, project, ident)).fetchone()
            if row:
                self.audit(con, tenant, project, actor, "job.cancelled", ident)
            return row

    def history(self, tenant, project, actor):
        with self.connect() as con:
            self.audit(con, tenant, project, actor, "audit.read", project)
            return con.execute("SELECT * FROM cloud_audit WHERE tenant=%s AND project=%s ORDER BY id DESC LIMIT 200",
                               (tenant, project)).fetchall()

    def claim(self, con, capacity):
        # Dispatcher holds a session advisory lock, serializing admission across replicas.
        active = con.execute("SELECT count(*) AS n FROM cloud_jobs WHERE state='running'").fetchone()["n"]
        if active >= capacity:
            return None
        row = con.execute("SELECT * FROM cloud_jobs WHERE state='queued' ORDER BY created FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not row:
            return None
        fence = uuid.uuid4().hex
        row = con.execute("UPDATE cloud_jobs SET state='running',attempt=attempt+1,fence=%s,deadline=%s,updated=%s "
                          "WHERE id=%s RETURNING *", (fence, time.time() + row["request"]["timeout_seconds"],
                                                     time.time(), row["id"])).fetchone()
        self.audit(con, row["tenant"], row["project"], "dispatcher", "job.started", row["id"], {"attempt": row["attempt"]})
        return row

    def finish(self, ident, fence, state, result_key=None, result_version=None, error=None):
        with self.connect() as con:
            row = con.execute("UPDATE cloud_jobs SET state=%s,result_key=%s,result_version=%s,error_code=%s,updated=%s "
                              "WHERE id=%s AND fence=%s AND state='running' RETURNING *",
                              (state, result_key, result_version, error, time.time(), ident, fence)).fetchone()
            if row:
                self.audit(con, row["tenant"], row["project"], "dispatcher", "job." + state, ident,
                           {"attempt": row["attempt"], "error_code": error})
            return bool(row)


if __name__ == "__main__":
    import os
    Store(os.environ["DATABASE_URL"]).migrate()
