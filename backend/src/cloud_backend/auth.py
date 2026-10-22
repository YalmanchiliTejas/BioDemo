"""Identity comes only from verified issuer claims, never request scope headers."""
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant: str
    projects: dict[str, str]

    def require(self, project: str, roles: set[str]) -> None:
        if self.projects.get(project) not in roles:
            raise HTTPException(403, "Project permission required")


class Verifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str, tenant: str):
        if any(urlsplit(url).scheme != "https" for url in (issuer, jwks_url)):
            raise ValueError("Issuer and JWKS must use HTTPS")
        if not audience or not tenant:
            raise ValueError("Audience and deployment tenant are required")
        self.issuer, self.audience, self.tenant = issuer, audience, tenant
        self.keys = jwt.PyJWKClient(jwks_url, timeout=5, lifespan=300)

    def verify(self, authorization: str | None) -> Identity:
        if not authorization or len(authorization) > 16384 or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required")
        token = authorization[7:]
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], issuer=self.issuer,
                                audience=self.audience,
                                options={"require": ["exp", "iat", "sub", "iss", "aud"]})
            projects = claims["projects"]
            if (claims["tenant_id"] != self.tenant or
                    not isinstance(claims["sub"], str) or not claims["sub"] or
                    not isinstance(projects, dict) or
                    any(not isinstance(k, str) or v not in ("viewer", "operator", "auditor")
                        for k, v in projects.items())):
                raise ValueError("Invalid scope")
            return Identity(claims["sub"], self.tenant, projects)
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(401, "Invalid or expired token") from exc
