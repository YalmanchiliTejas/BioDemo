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


def test_multi_org_signup_isolation_and_rbac(monkeypatch, platform):
    monkeypatch.setenv('LIFESCI_AUTH_MODE', 'supabase')
    monkeypatch.setenv('LIFESCI_MULTI_TENANT', '1')
    monkeypatch.setenv('SUPABASE_URL', URL)
    monkeypatch.setenv('DEPLOYMENT_TENANT', TENANT)
    monkeypatch.setattr(supabase_auth, 'PyJWKClient', FakeJWKS)
    client = TestClient(create_app(platform))
    alice, bob, outsider = (str(uuid.uuid4()) for _ in range(3))
    def headers(actor, org=None):
        h = {'Authorization': f'Bearer {es256(sub=actor)}'}
        if org: h['X-Organization-Id'] = org
        return h
    assert client.get('/v1/account', headers=headers(alice)).json()['organizations'] == []
    a = client.post('/v1/account/organizations', headers=headers(alice), json={'name': 'Alice company'})
    assert a.status_code == 201, a.text
    org_a = a.json()['id']
    b = client.post('/v1/account/organizations', headers=headers(bob), json={'name': 'Bob company'})
    org_b = b.json()['id']
    assert org_a != org_b
    assert client.post('/v1/account/organizations', headers=headers(alice), json={'name': 'Retry'}).json()['id'] == org_a
    assert client.get('/v1/me', headers=headers(alice, org_a)).json()['roles'] == ['admin']
    initial_members = client.get('/v1/organization/members', headers=headers(alice, org_a)).json()['items']
    assert initial_members[0]['email'] == 'qa@example.com'
    assert client.get('/v1/me', headers=headers(alice, org_b)).status_code == 403
    assert client.get('/v1/organization/members', headers=headers(outsider, org_a)).status_code == 403
    monkeypatch.setattr('src.lifesci.organization_api.lookup_user_id_by_email', lambda email: outsider)
    grant = {'email': 'new@example.com', 'role': 'operator', 'site_id': 'S1'}
    assert client.post('/v1/organization/members', headers=headers(alice, org_a), json=grant).status_code == 200
    listed = client.get('/v1/organization/members', headers=headers(alice, org_a)).json()['items']
    assert next(m for m in listed if m['actor_id'] == outsider)['email'] == 'new@example.com'
    me = client.get('/v1/me', headers=headers(outsider, org_a)).json()
    assert me['roles'] == ['operator'] and me['site_ids'] == ['S1']
    assert client.get('/v1/organization/members', headers=headers(outsider, org_a)).status_code == 403
    assert client.post('/v1/organization/members', headers=headers(outsider, org_a), json={**grant, 'role':'admin'}).status_code == 403
    assert client.post('/v1/organization/members', headers=headers(alice, org_a), json={**grant, 'role':'agent'}).status_code == 400
    revoke = {'actor_id': outsider, 'role': 'operator', 'site_id': 'S1', 'operation': 'revoke'}
    assert client.post('/v1/organization/members', headers=headers(alice, org_a), json=revoke).status_code == 200
    assert client.get('/v1/me', headers=headers(outsider, org_a)).status_code == 403
    assert client.post('/v1/organization/members', headers=headers(alice, org_a), json={'actor_id': alice, 'role':'admin', 'operation':'revoke'}).status_code == 400
    assert not client.get('/v1/account', headers=headers(alice)).json()['organizations'][0]['onboarding_complete']
    assert client.post('/v1/organization/onboarding/complete', headers=headers(alice, org_a)).status_code == 200
    assert client.get('/v1/account', headers=headers(alice)).json()['organizations'][0]['onboarding_complete']
    assert client.get('/v1/account', headers={'X-Actor-Id':alice,'X-Tenant-Id':org_a}).status_code == 401
    # User-controlled profile metadata cannot select an organization or grant a role.
    forged = {'Authorization': 'Bearer ' + es256(sub=bob, user_metadata={'tenant_id':org_a,'roles':['admin']})}
    forged['X-Organization-Id'] = org_a
    assert client.get('/v1/me', headers=forged).status_code == 403


def test_roles_do_not_inherit_other_roles_site_scopes(platform):
    platform.identity.assign_role(TENANT, SUB, 'operator', site_id='S2')
    ctx = platform.identity.context_for(TENANT, SUB)
    assert platform.identity.check(ctx, 'approve', 'proposal', site_id='S1')
    assert not platform.identity.check(ctx, 'approve', 'proposal', site_id='S2')
    assert platform.identity.check(ctx, 'propose', 'proposal', site_id='S2')
