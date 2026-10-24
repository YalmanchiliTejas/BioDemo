"""Record-ownership registry (ADR 0001, LS-062).

For each tenant, site and record class, exactly one of: an external system is
authoritative (we hold a projection), or a native module is explicitly enabled
as the owner. Adapters default to read access; a write to an externally owned
record class requires configured write scope and an approval reference. The
registry is consulted before any outbound write and before native execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ids import iso, utc_now
from .store import RecordStore, Transaction

OWNER_EXTERNAL = "external"
OWNER_NATIVE = "native"
OWNER_PROJECTION = "projection"  # read-only mirror, no owner assigned to us


@dataclass(frozen=True)
class Ownership:
    record_class: str
    site_id: str
    owner: str                      # external | native | projection
    system: str | None              # external system name when owner != native
    write_scope: tuple[str, ...]    # operations we may write back (empty = read-only)
    requires_approval: bool = True
    intended_use: str | None = None
    qualification_ref: str | None = None  # evidence that native use is qualified

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "write_scope": list(self.write_scope)}


class OwnershipViolation(PermissionError):
    pass


class OwnershipRegistry:
    def __init__(self, store: RecordStore) -> None:
        self.store = store

    @staticmethod
    def _id(record_class: str, site_id: str) -> str:
        return f"{record_class}@{site_id}"

    def assign(self, tenant_id: str, ownership: Ownership, *, by: str, reason: str) -> None:
        if ownership.owner not in (OWNER_EXTERNAL, OWNER_NATIVE, OWNER_PROJECTION):
            raise ValueError("owner must be external, native or projection")
        if ownership.owner == OWNER_NATIVE and not ownership.intended_use:
            raise ValueError("native ownership requires a stated intended use")
        if ownership.owner != OWNER_NATIVE and not ownership.system:
            raise ValueError("external ownership requires the owning system")
        with self.store.transaction(by) as tx:
            rid = self._id(ownership.record_class, ownership.site_id)
            current = tx.get(tenant_id, "ownership", rid)
            tx.put(tenant_id, "ownership", rid, {**ownership.to_dict(), "assigned_at": iso(utc_now())},
                   expected_revision=current.revision if current else None, action="assign_ownership",
                   reason=reason, event_type="ownership.assigned",
                   event_payload={"record_class": ownership.record_class, "site_id": ownership.site_id,
                                  "owner": ownership.owner, "system": ownership.system})

    def resolve(self, tenant_id: str, record_class: str, site_id: str, tx: Transaction | None = None) -> Ownership:
        tx = tx or self.store.read()
        rec = tx.get(tenant_id, "ownership", self._id(record_class, site_id)) or \
            tx.get(tenant_id, "ownership", self._id(record_class, "*"))
        if rec is None:
            # Unassigned classes are projections: nothing may be written back.
            return Ownership(record_class, site_id, OWNER_PROJECTION, None, ())
        s = rec.state
        return Ownership(s["record_class"], s["site_id"], s["owner"], s.get("system"), tuple(s.get("write_scope", ())),
                         s.get("requires_approval", True), s.get("intended_use"), s.get("qualification_ref"))

    def check_write(self, tenant_id: str, record_class: str, site_id: str, operation: str,
                    *, approval_ref: str | None, tx: Transaction | None = None) -> Ownership:
        """Raise unless this operation is inside configured write scope with approval where required."""
        own = self.resolve(tenant_id, record_class, site_id, tx)
        if own.owner == OWNER_PROJECTION:
            raise OwnershipViolation(f"{record_class}@{site_id} is a read-only projection; no owner assigned")
        if own.owner == OWNER_EXTERNAL and operation not in own.write_scope:
            raise OwnershipViolation(
                f"{operation} on {record_class}@{site_id} is outside write scope {list(own.write_scope)} of {own.system}")
        if own.requires_approval and not approval_ref:
            raise OwnershipViolation(f"{operation} on {record_class}@{site_id} requires an approval reference")
        return own

    def check_native(self, tenant_id: str, record_class: str, site_id: str, tx: Transaction | None = None) -> Ownership:
        own = self.resolve(tenant_id, record_class, site_id, tx)
        if own.owner != OWNER_NATIVE:
            raise OwnershipViolation(f"native execution of {record_class}@{site_id} is not enabled; owner is {own.owner}")
        return own
