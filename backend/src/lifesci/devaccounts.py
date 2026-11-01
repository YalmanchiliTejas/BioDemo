"""Local test accounts for development-header mode only.

They let the UI sign in against a local API without Supabase. Credentials are a
shared local password (``LIFESCI_DEV_PASSWORD``), and the accounts are ordinary
stored role assignments in a synthetic organization, so permissions behave exactly
as they do for real members. Never installed outside development-header mode,
which already refuses to run on AWS Lambda.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any

from .container import Platform
from .ids import iso, utc_now
from .organizations import OrganizationService

TENANT = "demo-northfield"
ORGANIZATION_NAME = "Northfield Biologics (synthetic)"
DEFAULT_PASSWORD = "sievance-local"


@dataclass(frozen=True)
class DevAccount:
    actor_id: str
    email: str
    name: str
    role: str
    site_id: str | None = None


ACCOUNTS = (
    DevAccount("dev-admin", "admin@sievance.local", "Alex Morgan", "admin"),
    DevAccount("dev-qa", "qa@sievance.local", "Quinn Reyes", "qa"),
    DevAccount("dev-msat", "msat@sievance.local", "Priya Shah", "msat"),
    # Site-scoped on purpose, to exercise restricted access.
    DevAccount("dev-operator", "operator@sievance.local", "Olu Bello", "operator", "NF1"),
)


def password() -> str:
    return os.environ.get("LIFESCI_DEV_PASSWORD", "").strip() or DEFAULT_PASSWORD


def by_email(email: str) -> DevAccount | None:
    email = email.strip().lower()
    return next((a for a in ACCOUNTS if a.email == email), None)


def authenticate(email: str, supplied: str) -> DevAccount | None:
    account = by_email(email)
    # Compare even for unknown emails so both failures take the same path.
    matches = hmac.compare_digest(supplied.encode(), password().encode())
    return account if account and matches else None


def ensure_seeded(platform: Platform, organizations: OrganizationService) -> None:
    """Idempotent: creates the synthetic organization, roles, member emails and directory entries."""
    with platform.store.transaction("devaccounts") as tx:
        if tx.get(TENANT, "organization", TENANT) is None:
            tx.put(TENANT, "organization", TENANT,
                   {"name": ORGANIZATION_NAME, "created_by": "devaccounts", "created_at": iso(utc_now()),
                    "onboarding_complete": True, "synthetic": True},
                   expected_revision=None, action="create_organization")
        for account in ACCOUNTS:
            if tx.get(TENANT, "organization_member", account.actor_id) is None:
                tx.put(TENANT, "organization_member", account.actor_id, {"email": account.email},
                       expected_revision=None, action="record_member")
    for account in ACCOUNTS:
        # Seed once. A role revoked while testing stays revoked, as it would for a real member.
        assignment = f"{account.actor_id}:{account.role}:{account.site_id or '*'}"
        if platform.store.read().get(TENANT, "role_assignment", assignment) is None:
            platform.identity.assign_role(TENANT, account.actor_id, account.role, site_id=account.site_id,
                                          by="devaccounts", reason="Local test account")
        organizations.remember(account.actor_id, TENANT)


def session(account: DevAccount) -> dict[str, Any]:
    return {"tenant_id": TENANT, "actor_id": account.actor_id, "email": account.email, "name": account.name}


def listing() -> list[dict[str, Any]]:
    return [{"email": a.email, "name": a.name, "role": a.role, "site_id": a.site_id} for a in ACCOUNTS]
