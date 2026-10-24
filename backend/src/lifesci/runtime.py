"""Mission execution and a recoverable per-tenant event pump shared by API and workers."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from .evidence import EvidenceRef
from .gateway import TaskRequest
from .ids import content_hash, iso, parse_iso, utc_now
from .missions import Activation, InProcessScheduler
from .roles import agent_context_for
from .store import ConflictError, LeaseError

log = logging.getLogger(__name__)


def run_coordinator(platform: Any, ctx: Any, act: Activation, reasons: list[str], as_of: str) -> None:
    """Run configured obligations; artifacts remain drafts and actions still need human approval."""
    mission = platform.missions.get(ctx, act.mission_id)
    if mission["status"] != "active":
        return
    now = iso(parse_iso(as_of)) if as_of else iso(utc_now())
    due = [o for o in mission["obligations"] if o["status"] == "open" and o.get("due_at")
           and o["due_at"] <= now and o.get("surfaced_due_at") != o["due_at"]]
    completed, blocked = [], []
    for ob in due:
        oid = ob["obligation_id"]
        try:
            refs = platform.identity.validate_refs(ctx, ob["inputs"]) if ob.get("inputs") else []
            output = None
            if not ob.get("artifact_kind"):
                if not ob.get("task_kind"):
                    raise ValueError("configure a task_kind or an artifact_kind and case_id")
                result = platform.gateway.run(TaskRequest(ob["task_kind"], ctx, prompt=ob["description"],
                                                         payload=ob.get("payload", {}), inputs=refs,
                                                         mission_id=act.mission_id))
                if result.status != "completed":
                    raise ValueError("; ".join(result.issues) or result.status)
                output = result
            with platform.store.transaction(ctx.actor_id) as tx:
                tx.check_lease(ctx.tenant_id, "mission", act.mission_id, act.worker_id, act.token)
                latest = platform.missions.get(ctx, act.mission_id)
                current = next(o for o in latest["obligations"] if o["obligation_id"] == oid)
                if current["status"] != "open" or current["due_at"] != ob["due_at"]:
                    continue  # a retried activation already committed this occurrence
                if refs:
                    platform.identity.validate_refs(ctx, refs, tx=tx)
                if ob.get("artifact_kind"):
                    from .quality import ArtifactService
                    if not ob.get("case_id"):
                        raise ValueError("artifact generation requires a case_id")
                    artifact = ArtifactService(platform.store, platform.identity, platform.evidence).generate(
                        ctx, ob["case_id"], ob["artifact_kind"])
                else:
                    manifest = refs or [{"kind": "mission", "id": act.mission_id,
                                         "revision": latest["revision"]}]
                    artifact = platform.evidence.record_derived(
                        ctx, "draft_artifact", {"mission_id": act.mission_id, "task_kind": ob["task_kind"],
                            "artifact_kind": "report", "sections": {"result": output.output},
                            "run_id": output.run_id, "review_state": "draft_requires_review"},
                        inputs=[EvidenceRef(r["kind"], r["id"], r["revision"], r.get("site_id")) for r in manifest],
                        produced_by={"actor_id": ctx.actor_id, "method": "mission_coordinator:v1"},
                        artifact_id=content_hash([act.mission_id, oid, ob["due_at"]])[:40])
                platform.missions.complete_obligation(ctx, act.mission_id, oid,
                    artifact_ref={"kind": "draft_artifact", "id": artifact["id"]})
            completed.append(oid)
        except (ValueError, KeyError, PermissionError) as exc:
            platform.missions.block_obligation(ctx, act.mission_id, oid, [str(exc)])
            blocked.append(oid)
    latest = platform.missions.get(ctx, act.mission_id)
    remaining = [w for w in latest["remaining_work"] if w not in {f"obligation:{o}" for o in completed}]
    remaining = list(dict.fromkeys([*remaining, *(f"obligation:{o}" for o in blocked)]))
    platform.missions.checkpoint(act, progress={"reasons": reasons, "completed_obligations": completed,
        "blocked_obligations": blocked}, consumed_event_ids=list(act.pending_event_ids),
        remaining_work=remaining, surfaced_obligations=blocked)


class Runtime:
    """Bounded polling recovers missed commit notifications without requiring cross-tenant DB privileges."""

    def __init__(self, platform: Any) -> None:
        self.platform = platform
        self._tenants = {t.strip() for t in os.environ.get("LIFESCI_TENANTS", "").split(",") if t.strip()}
        if os.environ.get("DEPLOYMENT_TENANT"):
            self._tenants.add(os.environ["DEPLOYMENT_TENANT"])
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        platform.store.subscribe(self._committed)

    def track(self, tenant: str) -> None:
        with self._lock:
            self._tenants.add(tenant)

    def _committed(self, event: Any) -> None:
        self.track(event.tenant_id)
        if event.type.startswith("mission.") or event.type.startswith("identity."):
            return
        try:
            self.platform.missions.deliver_events(event.tenant_id)
        except Exception:
            log.exception("Mission event delivery deferred to runtime poll")

    def tick(self) -> None:
        with self._lock:
            tenants = tuple(self._tenants)
        for tenant in tenants:
            try:
                self.platform.connectors.poll(tenant)
                self.platform.missions.deliver_events(tenant)
                scheduler = self.platform.missions.scheduler
                if hasattr(scheduler, "replay_backlog"):
                    scheduler.replay_backlog(tenant)
                elif isinstance(scheduler, InProcessScheduler):
                    self._run_local(tenant, scheduler)
            except Exception:
                log.exception("Runtime tick failed; persisted work will be retried")

    def _run_local(self, tenant: str, scheduler: InProcessScheduler) -> None:
        for rec in self.platform.store.read().list(tenant, "mission"):
            if rec.state["status"] != "active":
                continue
            due = self.platform.missions.next_unsurfaced_due(rec.state)
            reasons = [r for t, m, r in scheduler.wakeups if t == tenant and m == rec.id]
            if due and parse_iso(due) <= utc_now():
                reasons.append("timer:obligations_due")
            if not reasons and not rec.state["pending_event_ids"]:
                continue
            ctx = agent_context_for(self.platform.identity.context_for(tenant, rec.state["owner_id"]),
                                    self.platform.identity)
            act = None
            try:
                act = self.platform.missions.activate(ctx, rec.id, f"local:{os.getpid()}")
                run_coordinator(self.platform, ctx, act, reasons or ["events"], iso(utc_now()))
                scheduler.wakeups[:] = [(t, m, r) for t, m, r in scheduler.wakeups
                                       if (t, m) != (tenant, rec.id) or r not in reasons]
            except (ConflictError, LeaseError, PermissionError):
                continue
            finally:
                if act:
                    try:
                        self.platform.missions.release(act)
                    except LeaseError:
                        pass  # a replacement coordinator already holds the newer fence

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        def pump() -> None:
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(1.0)
        self._thread = threading.Thread(target=pump, daemon=True, name="lifesci-runtime")
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=65)
        self.platform.connectors.close()
