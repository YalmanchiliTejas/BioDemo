"""Signatures and record controls (LS-002, LS-035, LS-046).

A signature binds actor, time, meaning and the exact content hash of a
specific record revision. Changing the record invalidates the binding: a
signature is only valid for the revision whose hash it carries. The signing
action itself is authenticated through the caller's identity provider; this
module records and verifies the binding and never claims regulatory
compliance by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .identity import AccessContext, IdentityService
from .ids import content_hash, iso, new_id, utc_now
from .store import ConflictError, RecordStore, Transaction

SIGNATURE_MEANINGS = frozenset({"authored", "reviewed", "approved", "verified", "performed", "witnessed", "released"})


@dataclass(frozen=True)
class Signature:
    signature_id: str
    tenant_id: str
    record_kind: str
    record_id: str
    record_revision: int
    content_hash: str
    actor_id: str
    meaning: str
    signed_at: str
    reason: str | None
    authentication: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class SignatureService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def sign(self, ctx: AccessContext, record_kind: str, record_id: str, *, expected_revision: int,
             meaning: str, reason: str | None = None, authentication: dict[str, Any] | None = None,
             site_id: str | None = None) -> Signature:
        if meaning not in SIGNATURE_MEANINGS:
            raise ValueError(f"unknown signature meaning {meaning}")
        auth = authentication or {}
        if not auth.get("method"):
            raise PermissionError("signature requires an authenticated signing method (e.g. sso_reauth, mfa)")
        with self.store.transaction(ctx.actor_id) as tx:
            self.identity.require(ctx, "sign", record_kind, record_id, site_id=site_id, tx=tx)
            record = tx.require(ctx.tenant_id, record_kind, record_id)
            if record.revision != expected_revision:
                raise ConflictError(
                    f"{record_kind}:{record_id} is at revision {record.revision}; signature targeted {expected_revision}")
            sig = Signature(new_id("sig"), ctx.tenant_id, record_kind, record_id, record.revision, record.content_hash,
                            ctx.actor_id, meaning, iso(utc_now()), reason,
                            {"method": auth["method"], "assurance": auth.get("assurance", "unspecified")})
            tx.put(ctx.tenant_id, "signature", sig.signature_id, sig.to_dict(), expected_revision=None,
                   action="sign", reason=reason, event_type="record.signed",
                   event_payload={"record_kind": record_kind, "record_id": record_id,
                                  "revision": record.revision, "meaning": meaning, "actor_id": ctx.actor_id})
        return sig

    def signatures_for(self, tenant_id: str, record_kind: str, record_id: str,
                       tx: Transaction | None = None) -> list[dict[str, Any]]:
        tx = tx or self.store.read()
        return [r.state for r in tx.find(tenant_id, "signature", "record_id", record_id)
                if r.state["record_kind"] == record_kind]

    def verify(self, tenant_id: str, signature_id: str, tx: Transaction | None = None) -> dict[str, Any]:
        """Report whether the signed revision still exists unchanged and whether the record moved on."""
        tx = tx or self.store.read()
        sig = tx.require(tenant_id, "signature", signature_id).state
        signed = tx.revision(tenant_id, sig["record_kind"], sig["record_id"], sig["record_revision"])
        current = tx.get(tenant_id, sig["record_kind"], sig["record_id"])
        intact = signed is not None and signed.content_hash == sig["content_hash"]
        return {
            "signature_id": signature_id,
            "binding_intact": intact,
            "signed_revision": sig["record_revision"],
            "current_revision": current.revision if current else None,
            "covers_current_content": bool(intact and current and current.content_hash == sig["content_hash"]),
            "meaning": sig["meaning"], "actor_id": sig["actor_id"], "signed_at": sig["signed_at"],
        }

    def required_signatures_present(self, tenant_id: str, record_kind: str, record_id: str,
                                    meanings: list[str], tx: Transaction | None = None) -> dict[str, bool]:
        tx = tx or self.store.read()
        current = tx.require(tenant_id, record_kind, record_id)
        present = {s["meaning"] for s in self.signatures_for(tenant_id, record_kind, record_id, tx)
                   if s["content_hash"] == current.content_hash}
        return {m: m in present for m in meanings}


def record_digest(state: dict[str, Any]) -> str:
    return content_hash(state)
