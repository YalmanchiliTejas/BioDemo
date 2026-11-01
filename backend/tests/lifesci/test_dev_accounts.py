from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.lifesci import devaccounts  # noqa: E402
from src.lifesci.api import create_app  # noqa: E402
from src.lifesci.container import Platform  # noqa: E402
from src.lifesci.store import RecordStore  # noqa: E402

T = devaccounts.TENANT


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LIFESCI_AUTH_MODE", "development")
    monkeypatch.delenv("LIFESCI_DEV_PASSWORD", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    return TestClient(create_app(Platform(RecordStore(), providers={})))


def _sign_in(client, email, password=devaccounts.DEFAULT_PASSWORD):
    return client.post("/v1/dev/session", json={"email": email, "password": password})


def _headers(session):
    return {"X-Tenant-Id": session["tenant_id"], "X-Actor-Id": session["actor_id"]}


def test_local_sign_in_requires_the_shared_password(client):
    assert _sign_in(client, "admin@sievance.local", "wrong").status_code == 401
    assert _sign_in(client, "nobody@sievance.local").status_code == 401
    session = _sign_in(client, "ADMIN@sievance.local").json()
    assert session == {"tenant_id": T, "actor_id": "dev-admin", "email": "admin@sievance.local", "name": "Alex Morgan"}


def test_password_can_be_overridden(client, monkeypatch):
    monkeypatch.setenv("LIFESCI_DEV_PASSWORD", "another-secret")
    assert _sign_in(client, "admin@sievance.local").status_code == 401
    assert _sign_in(client, "admin@sievance.local", "another-secret").status_code == 200


def test_accounts_hold_stored_roles_and_see_their_organization(client):
    admin = _headers(_sign_in(client, "admin@sievance.local").json())
    operator = _headers(_sign_in(client, "operator@sievance.local").json())
    orgs = client.get("/v1/account", headers=admin).json()["organizations"]
    assert [(o["id"], o["roles"], o["site_ids"], o["onboarding_complete"]) for o in orgs] == [(T, ["admin"], [], True)]
    assert client.get("/v1/account", headers=operator).json()["organizations"][0]["site_ids"] == ["NF1"]
    members = client.get("/v1/organization/members", headers=admin).json()["items"]
    assert {m["email"] for m in members} >= {a.email for a in devaccounts.ACCOUNTS}
    assert client.get("/v1/organization/members", headers=operator).status_code == 403
    assert client.get("/v1/account").status_code == 401


def test_revoked_role_is_not_restored_by_signing_in_again(client):
    admin = _headers(_sign_in(client, "admin@sievance.local").json())
    revoke = {"actor_id": "dev-qa", "role": "qa", "site_id": None, "operation": "revoke"}
    assert client.post("/v1/organization/members", headers=admin, json=revoke).status_code == 200
    qa = _headers(_sign_in(client, "qa@sievance.local").json())
    assert client.get("/v1/account", headers=qa).json()["organizations"] == []
    grant = {"email": "qa@sievance.local", "role": "qa", "operation": "grant"}
    assert client.post("/v1/organization/members", headers=admin, json=grant).status_code == 200
    assert client.get("/v1/account", headers=qa).json()["organizations"][0]["roles"] == ["qa"]


def test_local_accounts_are_absent_outside_development(monkeypatch):
    monkeypatch.setenv("LIFESCI_AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("DEPLOYMENT_TENANT", "acme")
    client = TestClient(create_app(Platform(RecordStore(), providers={})))
    assert client.post("/v1/dev/session", json={"email": "admin@sievance.local",
                                                "password": devaccounts.DEFAULT_PASSWORD}).status_code == 404
    assert client.get("/v1/dev/accounts").status_code == 404
