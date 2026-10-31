"""Supabase Auth access tokens as the identity source for a single-tenant deployment.

The token proves who the person is (``sub``); it never carries authorization. Roles
and site scope always come from stored, revocable ``role_assignment`` records.

- Asymmetric keys (ES256/RS256) come from the project's JWKS; the algorithm must
  match the published key. HS256 is accepted only when ``SUPABASE_JWT_SECRET`` is
  configured (legacy shared-secret projects). ``none`` is never accepted.
- The tenant is fixed by ``DEPLOYMENT_TENANT``. ``app_metadata.tenant_id`` (writable
  only with the service role) must match it when present; ``user_metadata`` is
  user-editable and is ignored.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

MAX_TOKEN_BYTES = 16 * 1024
AUDIENCE = "authenticated"
JWKS_ALGORITHMS = frozenset({"ES256", "RS256"})


def _unauthorized(message: str = "Invalid or expired token") -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})


def _project_url(supabase_url: str | None) -> str:
    url = (supabase_url or "").strip().rstrip("/")
    parts = urlsplit(url)
    if not url or parts.scheme not in ("https", "http") or not parts.netloc:
        raise RuntimeError("SUPABASE_URL must be the project URL, e.g. https://<ref>.supabase.co")
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost"):
        raise RuntimeError("SUPABASE_URL must use HTTPS outside local development")
    return url


class SupabaseVerifier:
    def __init__(self, supabase_url: str, tenant: str, *, jwt_secret: str | None = None,
                 jwks_client: Any = None) -> None:
        if not tenant:
            raise RuntimeError("DEPLOYMENT_TENANT is required for Supabase authentication")
        base = _project_url(supabase_url)
        self.issuer = f"{base}/auth/v1"
        self.tenant = tenant
        self.jwt_secret = jwt_secret or None
        self.keys = jwks_client or PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True,
                                               lifespan=300, timeout=5)

    @classmethod
    def from_env(cls) -> "SupabaseVerifier":
        return cls(os.environ.get("SUPABASE_URL", ""), os.environ.get("DEPLOYMENT_TENANT", "").strip(),
                   jwt_secret=os.environ.get("SUPABASE_JWT_SECRET") or None)

    def verify(self, authorization: str | None) -> dict[str, Any]:
        """Return verified claims, or raise 401 (503 if the key set cannot be fetched)."""
        if not authorization:
            raise _unauthorized("Bearer token required")
        if len(authorization.encode()) > MAX_TOKEN_BYTES + 7:
            raise _unauthorized()
        scheme, _, token = authorization.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            raise _unauthorized("Bearer token required")
        try:
            alg = jwt.get_unverified_header(token).get("alg")
            if alg == "HS256" and self.jwt_secret:
                key: Any = self.jwt_secret
            elif alg in JWKS_ALGORITHMS:
                signing_key = self.keys.get_signing_key_from_jwt(token)
                if signing_key.algorithm_name != alg:
                    raise _unauthorized()
                key = signing_key.key
            else:
                raise _unauthorized()
            claims = jwt.decode(token, key, algorithms=[alg], audience=AUDIENCE, issuer=self.issuer,
                                options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        except jwt.PyJWKClientConnectionError as exc:
            raise HTTPException(503, "Identity provider keys unavailable") from exc
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise _unauthorized() from exc
        sub = claims.get("sub")
        if claims.get("role") != AUDIENCE or not isinstance(sub, str) or not sub or len(sub) > 128:
            raise _unauthorized()
        app_metadata = claims.get("app_metadata")
        if app_metadata is not None and not isinstance(app_metadata, dict):
            raise _unauthorized()
        tenant = (app_metadata or {}).get("tenant_id")
        if os.environ.get("LIFESCI_MULTI_TENANT") != "1" and tenant is not None and tenant != self.tenant:
            raise _unauthorized("Account is not enabled for this deployment")
        return claims


def supabase_resolver(platform: Any, verifier: SupabaseVerifier | None = None) -> Callable[[Any], Any]:
    verifier = verifier or SupabaseVerifier.from_env()

    def resolve(request: Any) -> Any:
        claims = verifier.verify(request.headers.get("authorization"))
        tenant = verifier.tenant
        if os.environ.get("LIFESCI_MULTI_TENANT") == "1":
            from .organizations import OrganizationService
            service = OrganizationService(platform.store, platform.identity, verifier.tenant)
            organizations = service.organizations(claims["sub"])
            requested = request.headers.get("x-organization-id")
            if requested:
                if requested not in {o["id"] for o in organizations}:
                    raise HTTPException(403, "No active membership in this organization")
                tenant = requested
            elif len(organizations) == 1:
                tenant = organizations[0]["id"]
            else:
                raise HTTPException(403, "Select an organization or create one to continue")
        elif request.headers.get("x-organization-id") not in (None, tenant):
            raise HTTPException(403, "Organization does not match this deployment")
        return platform.identity.context_for(tenant, claims["sub"])
    resolve.verifier = verifier
    return resolve


# --- operator tooling: map an email to the Supabase user id --------------------------
def lookup_user_id_by_email(email: str, *, supabase_url: str | None = None, service_role_key: str | None = None,
                            per_page: int = 200, max_pages: int = 500) -> str:
    """Find a Supabase Auth user by exact (case-insensitive) email via the admin API."""
    base = _project_url(supabase_url if supabase_url is not None else os.environ.get("SUPABASE_URL"))
    key = service_role_key if service_role_key is not None else os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required to look up users by email")
    wanted = email.strip().lower()
    if not wanted or "@" not in wanted:
        raise ValueError(f"not an email address: {email!r}")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    for page in range(1, max_pages + 1):
        url = f"{base}/auth/v1/admin/users?{urlencode({'page': page, 'per_page': per_page})}"
        with urlopen(Request(url, headers=headers), timeout=15) as response:  # noqa: S310 (fixed https URL)
            body = json.loads(response.read().decode())
        users = body.get("users", []) if isinstance(body, dict) else []
        for user in users:
            if str(user.get("email") or "").lower() == wanted:
                return str(uuid.UUID(str(user["id"])))
        if len(users) < per_page:
            break
    raise LookupError(f"no Supabase user with email {email!r}; the person must sign up or be invited first")
