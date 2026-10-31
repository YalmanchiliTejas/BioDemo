from __future__ import annotations

import io
import json
import sys
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.lifesci import supabase_auth  # noqa: E402
from src.lifesci.api import create_app  # noqa: E402
from src.lifesci.container import Platform  # noqa: E402
from src.lifesci.store import RecordStore  # noqa: E402

URL = "https://proj.supabase.co"
ISS = f"{URL}/auth/v1"
TENANT = "acme"
SUB = str(uuid.uuid4())
SECRET = "legacy-shared-secret-at-least-32-bytes!!"
KEY = ec.generate_private_key(ec.SECP256R1())
JWK = {**json.loads(jwt.algorithms.ECAlgorithm.to_jwk(KEY.public_key())), "kid": "k1", "alg": "ES256", "use": "sig"}


class FakeJWKS(jwt.PyJWKClient):
    def fetch_data(self):  # no network
        return {"keys": [JWK]}


def claims(**over):
    now = int(time.time())
    base = {"iss": ISS, "aud": "authenticated", "sub": SUB, "role": "authenticated", "iat": now, "exp": now + 600,
            "email": "qa@example.com"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def es256(**over):
    return jwt.encode(claims(**over), KEY, algorithm="ES256", headers={"kid": "k1"})


@pytest.fixture
def platform():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role(TENANT, SUB, "qa", site_id="S1")
    return p


def verifier(secret=None):
    return supabase_auth.SupabaseVerifier(URL, TENANT, jwt_secret=secret, jwks_client=FakeJWKS(f"{ISS}/.well-known/jwks.json"))


def resolve(platform, token, secret=None):
    request = type("R", (), {"headers": {"authorization": f"Bearer {token}"}})()
    return supabase_auth.supabase_resolver(platform, verifier(secret))(request)


def rejected(platform, token, secret=None):
    with pytest.raises(HTTPException) as exc:
        resolve(platform, token, secret)
    assert exc.value.status_code == 401 and exc.value.headers == {"WWW-Authenticate": "Bearer"}
    return exc.value


def test_valid_token_loads_stored_roles(platform):
    ctx = resolve(platform, es256())
    assert (ctx.tenant_id, ctx.actor_id, ctx.roles, ctx.site_ids) == (TENANT, SUB, frozenset({"qa"}), frozenset({"S1"}))


@pytest.mark.parametrize("over", [{"aud": "anon"}, {"iss": "https://evil.supabase.co/auth/v1"},
                                  {"exp": int(time.time()) - 3600}, {"role": "anon"}, {"role": "service_role"},
                                  {"exp": None}, {"iat": None}, {"sub": None}])
def test_invalid_claims_rejected(platform, over):
    rejected(platform, es256(**over))


def test_alg_none_hs256_without_secret_and_oversize_rejected(platform):
    rejected(platform, jwt.encode(claims(), None, algorithm="none"))
    rejected(platform, jwt.encode(claims(), SECRET, algorithm="HS256"))
    rejected(platform, es256(padding="x" * 17_000))
    rejected(platform, "not-a-jwt")
    other = ec.generate_private_key(ec.SECP256R1())
    rejected(platform, jwt.encode(claims(), other, algorithm="ES256", headers={"kid": "k1"}))


def test_hs256_only_with_configured_secret(platform):
    token = jwt.encode(claims(), SECRET, algorithm="HS256")
    assert resolve(platform, token, secret=SECRET).roles == {"qa"}
    rejected(platform, jwt.encode(claims(), "wrong-secret-wrong-secret-wrong!!", algorithm="HS256"), secret=SECRET)


def test_tenant_from_app_metadata_only(platform):
    rejected(platform, es256(app_metadata={"tenant_id": "other"}))
    assert resolve(platform, es256(app_metadata={"tenant_id": TENANT})).tenant_id == TENANT
    ctx = resolve(platform, es256(user_metadata={"tenant_id": "other", "roles": ["admin"]}))
    assert ctx.tenant_id == TENANT and ctx.roles == {"qa"}


def test_missing_or_malformed_header(platform):
    v = verifier()
    for header in (None, "", "Basic abc", "Bearer "):
        with pytest.raises(HTTPException) as exc:
            v.verify(header)
        assert exc.value.status_code == 401


def test_lambda_refuses_development_mode(monkeypatch, platform):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "biodemo-api")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("LIFESCI_AUTH_MODE", raising=False)
    with pytest.raises(RuntimeError, match="Lambda"):
        create_app(platform)
    monkeypatch.setenv("LIFESCI_AUTH_MODE", "development")
    with pytest.raises(RuntimeError, match="Lambda"):
        create_app(platform)
    monkeypatch.setenv("LIFESCI_AUTH_MODE", "magic")
    with pytest.raises(RuntimeError, match="LIFESCI_AUTH_MODE"):
        create_app(platform)


def test_supabase_mode_end_to_end(monkeypatch, platform):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "biodemo-api")
    monkeypatch.setenv("LIFESCI_AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", URL + "/")
    monkeypatch.setenv("DEPLOYMENT_TENANT", TENANT)
    monkeypatch.setenv("LIFESCI_CORS_ORIGINS", "https://app.example.com")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setattr(supabase_auth, "PyJWKClient", FakeJWKS)
    client = TestClient(create_app(platform))
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {es256()}"})
    assert me.status_code == 200, me.text
    assert me.json()["auth_mode"] == "supabase" and me.json()["actor_id"] == SUB and me.json()["roles"] == ["qa"]
    bad = client.get("/v1/me", headers={"Authorization": f"Bearer {es256(aud='x')}"})
    assert bad.status_code == 401 and bad.headers["www-authenticate"] == "Bearer"
    assert "aud" not in bad.text.lower().replace("authenticated", "")
    spoof = client.get("/v1/me", headers={"X-Tenant-Id": TENANT, "X-Actor-Id": SUB})
    assert spoof.status_code == 401
    assert client.get("/v1/docs").status_code == 404
    pre = client.options("/v1/me", headers={"Origin": "https://app.example.com", "Access-Control-Request-Method": "GET",
                                            "Access-Control-Request-Headers": "authorization"})
    assert pre.headers.get("access-control-allow-origin") == "https://app.example.com"
    unknown = str(uuid.uuid4())
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {es256(sub=unknown)}"}).status_code == 403


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_admin_api(users, seen):
    def urlopen(request, timeout=None):
        seen.append((request.full_url, request.headers))
        page = int(request.full_url.split("page=")[1].split("&")[0])
        per_page = int(request.full_url.split("per_page=")[1])
        chunk = users[(page - 1) * per_page: page * per_page]
        return _Response(json.dumps({"users": chunk, "aud": "authenticated"}).encode())
    return urlopen


def test_email_lookup_paginates_and_matches_exactly(monkeypatch):
    target = str(uuid.uuid4())
    users = [{"id": str(uuid.uuid4()), "email": f"user{i}@example.com"} for i in range(250)]
    users += [{"id": str(uuid.uuid4()), "email": "qa@example.com.evil"}, {"id": target, "email": "QA@Example.com"}]
    seen = []
    monkeypatch.setattr(supabase_auth, "urlopen", fake_admin_api(users, seen))
    found = supabase_auth.lookup_user_id_by_email("qa@example.com", supabase_url=URL, service_role_key="srk")
    assert found == target and len(seen) == 2
    assert seen[0][0].startswith(f"{ISS}/admin/users?page=1&per_page=200")
    assert seen[0][1]["Apikey"] == "srk" and seen[0][1]["Authorization"] == "Bearer srk"
    with pytest.raises(LookupError):
        supabase_auth.lookup_user_id_by_email("nobody@example.com", supabase_url=URL, service_role_key="srk")


def test_cli_grant_list_revoke(monkeypatch, tmp_path, capsys):
    from src.lifesci import __main__ as cli

    target = str(uuid.uuid4())
    monkeypatch.setattr(supabase_auth, "urlopen", fake_admin_api([{"id": target, "email": "qa@example.com"}], []))
    monkeypatch.setenv("LIFESCI_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("LIFESCI_DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srk")
    monkeypatch.setenv("DEPLOYMENT_TENANT", TENANT)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["lifesci", *argv])
        cli.main()
        return capsys.readouterr().out

    assert "Assigned 'qa'" in run("grant-role", "--email", "qa@example.com", "--role", "qa", "--reason", "onboarding")
    assert json.loads(run("list-roles"))[0]["actor_id"] == target
    with pytest.raises(SystemExit, match="unknown role"):
        run("grant-role", "--user-id", target, "--role", "superuser")
    with pytest.raises(SystemExit, match="UUID"):
        run("grant-role", "--user-id", "alice", "--role", "qa")
    assert "Revoked 'qa'" in run("revoke-role", "--user-id", target, "--role", "qa")
    assert json.loads(run("list-roles")) == []
    p = Platform.from_env()
    assert p.identity.context_for(TENANT, target).roles == frozenset()
