"""Tenant-fair work scheduling with backpressure and resource ceilings (LS-087, V16).

- Urgent work (required notifications, review commands) has its own lane and is
  always selected before normal/background work; long analysis cannot block it.
- Normal/background lanes use weighted deficit round-robin across tenants, so a
  busy tenant cannot starve others.
- Per-tenant running ceilings and per-mission fan-out limits bound resource use.
- A full queue rejects submission with an explicit Backpressure signal; work is
  never silently dropped. Items persist in the record store and are recovered
  after restart.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from .ids import iso, new_id, parse_iso, utc_now
from .store import RecordStore

LANES = ("urgent", "normal", "background")


class Backpressure(Exception):
    def __init__(self, tenant_id: str, reason: str, retry_after_s: float) -> None:
        super().__init__(f"{tenant_id}: {reason}; retry after {retry_after_s}s")
        self.tenant_id, self.reason, self.retry_after_s = tenant_id, reason, retry_after_s


@dataclass
class QueuePolicy:
    max_queued_per_tenant: int = 1_000
    max_running_per_tenant: int = 4
    max_children_per_mission: int = 8
    tenant_weights: dict[str, int] | None = None
    quantum: int = 1


class WorkQueue:
    KIND = "work_item"

    def __init__(self, store: RecordStore, policy: QueuePolicy | None = None) -> None:
        self.store = store
        self.policy = policy or QueuePolicy()
        self._queues: dict[str, dict[str, deque[str]]] = {lane: defaultdict(deque) for lane in LANES}
        self._running: dict[str, set[str]] = defaultdict(set)
        self._children: dict[str, int] = defaultdict(int)
        self._deficit: dict[str, int] = defaultdict(int)
        self._rr: dict[str, deque[str]] = {lane: deque() for lane in LANES}
        self._tenants: set[str] = set()

    def submit(self, tenant_id: str, *, task: str, lane: str = "normal", payload: dict[str, Any] | None = None,
               mission_id: str | None = None, parent_item_id: str | None = None) -> str:
        if lane not in LANES:
            raise ValueError(lane)
        queued = sum(len(self._queues[l][tenant_id]) for l in LANES)
        if lane != "urgent" and queued >= self.policy.max_queued_per_tenant:
            raise Backpressure(tenant_id, "tenant queue full", retry_after_s=30)
        if parent_item_id and mission_id:
            if self._children[mission_id] >= self.policy.max_children_per_mission:
                raise Backpressure(tenant_id, f"mission {mission_id} fan-out limit reached", retry_after_s=10)
            self._children[mission_id] += 1
        item_id = new_id("wi")
        state = {"item_id": item_id, "task": task, "lane": lane, "payload": payload or {}, "mission_id": mission_id,
                 "parent_item_id": parent_item_id, "status": "queued", "queued_at": iso(utc_now()),
                 "started_at": None, "finished_at": None}
        with self.store.transaction("workqueue") as tx:
            tx.put(tenant_id, self.KIND, item_id, state, expected_revision=None, action="enqueue")
        self._enqueue(tenant_id, lane, item_id)
        return item_id

    def _enqueue(self, tenant_id: str, lane: str, item_id: str) -> None:
        self._queues[lane][tenant_id].append(item_id)
        self._tenants.add(tenant_id)
        if tenant_id not in self._rr[lane]:
            self._rr[lane].append(tenant_id)

    def next(self) -> tuple[str, dict[str, Any]] | None:
        """Pick the next runnable item: urgent first, then fair across tenants."""
        for lane in LANES:
            picked = self._pick(lane)
            if picked:
                tenant_id, item_id = picked
                with self.store.transaction("workqueue") as tx:
                    rec = tx.require(tenant_id, self.KIND, item_id)
                    out = tx.put(tenant_id, self.KIND, item_id,
                                 {**rec.state, "status": "running", "started_at": iso(utc_now())},
                                 expected_revision=rec.revision, action="start")
                self._running[tenant_id].add(item_id)
                return tenant_id, out.state
        return None

    def _pick(self, lane: str) -> tuple[str, str] | None:
        rr = self._rr[lane]
        weights = self.policy.tenant_weights or {}
        for _ in range(len(rr) * 2 + 1):
            if not rr:
                return None
            tenant = rr[0]
            q = self._queues[lane][tenant]
            if not q:
                rr.popleft()
                self._deficit[f"{lane}:{tenant}"] = 0
                continue
            # urgent work ignores the running ceiling so required notices are never blocked by analysis load
            if lane != "urgent" and len(self._running[tenant]) >= self.policy.max_running_per_tenant:
                rr.rotate(-1)
                continue
            key = f"{lane}:{tenant}"
            self._deficit[key] += self.policy.quantum * weights.get(tenant, 1)
            if self._deficit[key] >= 1:
                self._deficit[key] -= 1
                item = q.popleft()
                rr.rotate(-1)
                return tenant, item
            rr.rotate(-1)
        return None

    def complete(self, tenant_id: str, item_id: str, *, status: str = "done", result: dict[str, Any] | None = None) -> None:
        with self.store.transaction("workqueue") as tx:
            rec = tx.require(tenant_id, self.KIND, item_id)
            tx.put(tenant_id, self.KIND, item_id, {**rec.state, "status": status, "result": result,
                                                    "finished_at": iso(utc_now())},
                   expected_revision=rec.revision, action="complete")
            if rec.state.get("parent_item_id") and rec.state.get("mission_id"):
                self._children[rec.state["mission_id"]] = max(self._children[rec.state["mission_id"]] - 1, 0)
        self._running[tenant_id].discard(item_id)

    def recover(self, tenant_ids: list[str]) -> int:
        """Rebuild the in-memory index after restart; running items with no worker return to the queue."""
        count = 0
        for tenant_id in tenant_ids:
            for rec in self.store.read().list(tenant_id, self.KIND, lambda s: s["status"] in ("queued", "running")):
                if rec.state["status"] == "running":
                    with self.store.transaction("workqueue") as tx:
                        cur = tx.require(tenant_id, self.KIND, rec.id)
                        tx.put(tenant_id, self.KIND, rec.id, {**cur.state, "status": "queued"},
                               expected_revision=cur.revision, action="requeue_after_restart")
                self._enqueue(tenant_id, rec.state["lane"], rec.id)
                count += 1
        return count

    def metrics(self) -> dict[str, Any]:
        now = utc_now()
        out: dict[str, Any] = {}
        tx = self.store.read()
        for tenant in sorted(self._tenants):
            lanes = {}
            for lane in LANES:
                ages = []
                for item_id in self._queues[lane][tenant]:
                    rec = tx.get(tenant, self.KIND, item_id)
                    if rec:
                        ages.append((now - parse_iso(rec.state["queued_at"])).total_seconds())
                ages.sort()
                lanes[lane] = {"depth": len(ages),
                               "oldest_age_s": ages[-1] if ages else 0.0,
                               "p50_age_s": ages[len(ages) // 2] if ages else 0.0,
                               "p95_age_s": ages[int(len(ages) * 0.95)] if ages else 0.0}
            out[tenant] = {"running": len(self._running[tenant]), "lanes": lanes}
        return out
