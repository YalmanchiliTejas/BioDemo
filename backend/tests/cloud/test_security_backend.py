import base64
import hashlib
import io
import json
import os
import time
from types import SimpleNamespace

import pytest
pytest.importorskip("jwt")
pytest.importorskip("cryptography")
pytest.importorskip("psycopg")
import jwt
import psycopg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.cloud_backend.auth import Identity, Verifier
from src.cloud_backend.crypto import object_key, seal, unseal
from src.cloud_backend.store import Conflict, Store


@pytest.fixture
def store():
    dsn = os.getenv("CLOUD_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set CLOUD_TEST_DATABASE_URL to an isolated PostgreSQL database")
    service = Store(dsn)
    service.migrate()
    with service.connect() as con:
        con.execute("TRUNCATE cloud_jobs, cloud_audit RESTART IDENTITY")
    return service


def request():
    return {"sha256": "a" * 64, "version_id": "version-1", "objective": "Investigate synthetic measurements",
            "as_of": "2026-10-22T00:00:00Z", "timeout_seconds": 60, "max_tool_calls": 10}


def test_verified_claims_and_algorithm_confusion():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = Verifier("https://id.example/", "biodemo", "https://id.example/keys", "tenant")
    verifier.keys = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key()))
    claims = {"iss": "https://id.example/", "aud": "biodemo", "sub": "alice", "iat": int(time.time()),
              "exp": int(time.time()) + 60, "tenant_id": "tenant", "projects": {"project": "operator"}}
    signed = lambda c: "Bearer " + jwt.encode(c, key, algorithm="RS256")
    assert verifier.verify(signed(claims)).subject == "alice"
    for changed in ({"aud": "other"}, {"iss": "https://evil/"}, {"exp": 1}, {"tenant_id": "other"},
                    {"projects": {"project": "admin"}}, {"sub": ""}):
        with pytest.raises(HTTPException) as error:
            verifier.verify(signed({**claims, **changed}))
        assert error.value.status_code == 401
    for token in (None, "Bearer " + jwt.encode(claims, "attacker" * 8, algorithm="HS256"),
                  "Bearer " + jwt.encode(claims, key="", algorithm="none")):
        with pytest.raises(HTTPException):
            verifier.verify(token)


def test_encryption_is_object_scoped_and_authenticated():
    master = b"k" * 32
    path = "tenant/project/inputs/hash.zip"
    key = object_key(master, path)
    data = b"private evidence"
    first, second = seal(key, path, data), seal(key, path, data)
    assert first != second and data not in first
    assert unseal(key, path, first) == data
    with pytest.raises(InvalidTag):
        unseal(object_key(master, "other/project"), "other/project", first)
    with pytest.raises(InvalidTag):
        unseal(key, path, first[:-1] + bytes([first[-1] ^ 1]))


def test_idempotency_scope_cancellation_and_fencing(store):
    job = store.submit("tenant", "one", "alice", "unique-key", request())
    assert store.submit("tenant", "one", "alice", "unique-key", request())["id"] == job["id"]
    with pytest.raises(Conflict):
        store.submit("tenant", "one", "alice", "unique-key", {**request(), "objective": "Different"})
    assert store.get("other", "one", job["id"], "alice") is None
    assert store.get("tenant", "two", job["id"], "alice") is None
    with store.connect() as con:
        active = store.claim(con, 1)
    assert not store.finish(job["id"], "stale-fence", "succeeded")
    store.cancel("tenant", "one", job["id"], "alice")
    assert not store.finish(job["id"], active["fence"], "succeeded")
    assert store.get("tenant", "one", job["id"], "alice")["state"] == "cancelled"
    assert Store(store.dsn).get("tenant", "one", job["id"], "alice")["id"] == job["id"]
    with store.connect() as con:
        actions = [r["action"] for r in con.execute("SELECT action FROM cloud_audit").fetchall()]
        assert actions.count("job.submitted") == 1
    with pytest.raises(psycopg.errors.RaiseException), store.connect() as con:
        con.execute("DELETE FROM cloud_audit")


class FakeSpaces:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body
        return {"VersionId": "version-1"}

    def get_object(self, **kwargs):
        return {"Body": io.BytesIO(self.objects[kwargs["Key"]]), "VersionId": "version-1"}

    def generate_presigned_url(self, action, **kwargs):
        return f"https://bucket.nyc3.digitaloceanspaces.com/{action}"


@pytest.fixture
def api(store, monkeypatch):
    from src.cloud_backend.api import create_app
    monkeypatch.setenv("DEPLOYMENT_TENANT", "tenant")
    monkeypatch.setenv("ARTIFACT_BUCKET", "private")

    class TestVerifier:
        def verify(self, authorization):
            if authorization not in ("Bearer operator", "Bearer viewer", "Bearer auditor"):
                raise HTTPException(401, "Invalid token")
            return Identity("alice", "tenant", {"project": authorization.split()[1]})

    spaces = FakeSpaces()
    return TestClient(create_app(store, TestVerifier(), spaces, b"k" * 32)), spaces


def test_api_no_header_spoofing_and_project_roles(api, store):
    client, spaces = api
    endpoint = "/v1/projects/project/jobs"
    assert client.post(endpoint, json=request(), headers={"X-Tenant-ID": "tenant", "X-Roles": "operator"}).status_code == 401
    assert client.post(endpoint, json=request(), headers={"Authorization": "Bearer viewer", "Idempotency-Key": "test-key"}).status_code == 403
    headers = {"Authorization": "Bearer operator", "Idempotency-Key": "test-key"}
    created = client.post(endpoint, json=request(), headers=headers)
    assert created.status_code == 202, created.text
    ident = created.json()["id"]
    assert client.get(f"/v1/projects/other/jobs/{ident}", headers=headers).status_code == 403
    assert client.get(f"{endpoint}/{ident}", headers={"Authorization": "Bearer viewer"}).status_code == 200
    assert client.get("/v1/projects/project/audit", headers=headers).status_code == 403
    assert client.get("/v1/projects/project/audit", headers={"Authorization": "Bearer auditor"}).status_code == 200
    assert client.post(endpoint, content=b"x" * 20000, headers=headers).status_code == 413
    assert client.post(endpoint, json={**request(), "as_of": "2026-10-22T00:00:00"}, headers=headers).status_code == 422
    assert client.get("/api/pharma/projects", headers=headers).status_code == 404
    assert created.headers["cache-control"] == "no-store"
    with store.connect() as con:
        assert con.execute("SELECT count(*) AS n FROM cloud_audit WHERE action='access.denied'").fetchone()["n"] >= 3


def test_api_encrypts_upload_and_pins_result_version(api, store):
    from src.cloud_backend.api import input_key
    client, spaces = api
    data = b"synthetic ZIP bytes"
    sha = hashlib.sha256(data).hexdigest()
    headers = {"Authorization": "Bearer operator"}
    response = client.put(f"/v1/projects/project/inputs/{sha}", content=data, headers=headers)
    assert response.status_code == 200, response.text
    path = input_key("tenant", "project", sha)
    assert data not in spaces.objects[path]
    assert unseal(object_key(b"k" * 32, path), path, spaces.objects[path]) == data
    assert client.put(f'/v1/projects/project/inputs/{"a"*64}', content=data, headers=headers).status_code == 422
    job = store.submit("tenant", "project", "alice", "test-result", request())
    with store.connect() as con:
        active = store.claim(con, 2)
    result_path = "tenant/project/results/result.json"
    spaces.objects[result_path] = seal(object_key(b"k"*32, result_path), result_path, b'{"report":"review me"}')
    store.finish(job["id"], active["fence"], "succeeded", result_key=result_path, result_version="version-1")
    assert client.get(f'/v1/projects/project/jobs/{job["id"]}/result', headers=headers).json() == {"report": "review me"}


def test_runtime_roles_cannot_rewrite_audit_or_schema(store):
    from pathlib import Path
    with store.connect() as con:
        con.execute((Path(__file__).resolve().parents[2] / "src/cloud_backend/runtime_roles.sql").read_text())
    for role in ("cloud_api", "cloud_dispatcher"):
        for statement in ("DELETE FROM cloud_audit", "UPDATE cloud_audit SET action='rewritten'", "TRUNCATE cloud_audit",
                          "DROP TABLE cloud_jobs", "CREATE TABLE public.attack (id integer)"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), store.connect() as con:
                con.execute("SET ROLE " + role)
                con.execute(statement)


def test_runtime_roles_can_execute_the_real_job_lifecycle(store):
    from pathlib import Path
    from psycopg.conninfo import make_conninfo
    with store.connect() as con:
        con.execute((Path(__file__).resolve().parents[2] / "src/cloud_backend/runtime_roles.sql").read_text())
    api = Store(make_conninfo(store.dsn, options="-c role=cloud_api"))
    worker = Store(make_conninfo(store.dsn, options="-c role=cloud_dispatcher"))
    job = api.submit("tenant", "project", "alice", "runtime-roles", request())
    with worker.connect() as con:
        active = worker.claim(con, 1)
    assert worker.finish(job["id"], active["fence"], "failed", error="test")
    assert api.get("tenant", "project", job["id"], "alice")["state"] == "failed"


@pytest.mark.parametrize("exit_code", [0, 1])
def test_streamed_backup_round_trip_and_failed_dump_rejection(monkeypatch, tmp_path, exit_code):
    pytest.importorskip("docker")
    from src.cloud_backend import backup
    snapshot = b"PGDMP synthetic PostgreSQL snapshot" * 100
    engine = SimpleNamespace(
        containers=SimpleNamespace(list=lambda **_: [SimpleNamespace(id="db")]),
        api=SimpleNamespace(exec_create=lambda *_: {"Id": "dump"},
                            exec_start=lambda *a, **k: [(snapshot[:50], None), (snapshot[50:], None)],
                            exec_inspect=lambda *_: {"ExitCode": exit_code}))
    uploaded = {}

    def upload(file, bucket, key):
        from pathlib import Path
        uploaded.update(key=key, data=Path(file).read_bytes())

    original_tempdir = backup.tempfile.TemporaryDirectory
    monkeypatch.setattr(backup.tempfile, "TemporaryDirectory", lambda **_: original_tempdir(dir=tmp_path))
    monkeypatch.setattr(backup.docker, "from_env", lambda: engine)
    monkeypatch.setattr(backup, "spaces_client", lambda: SimpleNamespace(upload_file=upload))
    monkeypatch.setattr(backup, "master_key", lambda: b"k" * 32)
    monkeypatch.setenv("DEPLOYMENT_TENANT", "tenant")
    monkeypatch.setenv("ARTIFACT_BUCKET", "backups")
    if exit_code:
        with pytest.raises(RuntimeError):
            backup.main()
        assert not uploaded
    else:
        backup.main()
        assert snapshot not in uploaded["data"]
        assert unseal(object_key(b"k" * 32, uploaded["key"]), uploaded["key"], uploaded["data"]) == snapshot
