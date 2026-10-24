"""Hierarchical spend budgets (task -> mission -> tenant) with atomic reservation.

A call reserves its worst-case cost across every applicable scope in one
transaction before running, then reconciles to measured usage. Exhaustion is
an explicit, resumable state; it never relaxes routing or review controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ids import new_id
from ..store import RecordStore


class BudgetExceeded(Exception):
    def __init__(self, scope: str, remaining: float, requested: float) -> None:
        super().__init__(f"budget {scope} exhausted: remaining ${remaining:.4f}, requested ${requested:.4f}")
        self.scope, self.remaining, self.requested = scope, remaining, requested


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    scopes: tuple[str, ...]
    amount: float


class BudgetLedger:
    KIND = "budget"

    def __init__(self, store: RecordStore) -> None:
        self.store = store

    def set_limit(self, tenant_id: str, scope: str, limit_usd: float, *, by: str = "system") -> None:
        with self.store.transaction(by) as tx:
            current = tx.get(tenant_id, self.KIND, scope)
            state = {"scope": scope, "limit": float(limit_usd),
                     "spent": current.state["spent"] if current else 0.0,
                     "reserved": current.state["reserved"] if current else 0.0,
                     "calls": current.state["calls"] if current else 0}
            tx.put(tenant_id, self.KIND, scope, state, expected_revision=current.revision if current else None,
                   action="set_budget")

    def status(self, tenant_id: str, scope: str) -> dict[str, Any] | None:
        rec = self.store.read().get(tenant_id, self.KIND, scope)
        if rec is None:
            return None
        s = rec.state
        return {**s, "remaining": s["limit"] - s["spent"] - s["reserved"]}

    def reserve(self, tenant_id: str, scopes: list[str], amount: float, *, by: str = "gateway") -> Reservation:
        """All-or-nothing reservation across scopes. Scopes without a configured limit are unbounded."""
        with self.store.transaction(by) as tx:
            for scope in scopes:
                rec = tx.get(tenant_id, self.KIND, scope)
                if rec is None:
                    continue
                s = rec.state
                remaining = s["limit"] - s["spent"] - s["reserved"]
                if amount > remaining + 1e-12:
                    raise BudgetExceeded(scope, remaining, amount)
                tx.put(tenant_id, self.KIND, scope, {**s, "reserved": s["reserved"] + amount},
                       expected_revision=rec.revision, action="reserve")
        return Reservation(new_id("rsv"), tuple(scopes), amount)

    def settle(self, tenant_id: str, reservation: Reservation, actual: float, *, by: str = "gateway") -> None:
        """Release the reservation and record measured spend (actual may exceed the estimate)."""
        with self.store.transaction(by) as tx:
            for scope in reservation.scopes:
                rec = tx.get(tenant_id, self.KIND, scope)
                if rec is None:
                    continue
                s = rec.state
                tx.put(tenant_id, self.KIND, scope,
                       {**s, "reserved": max(s["reserved"] - reservation.amount, 0.0),
                        "spent": s["spent"] + actual, "calls": s["calls"] + 1},
                       expected_revision=rec.revision, action="settle")
