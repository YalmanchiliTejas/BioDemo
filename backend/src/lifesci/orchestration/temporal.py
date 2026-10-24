"""Temporal activities, scheduler port implementation and worker wiring (D09, D40).

Activities run as a *delegated agent* of the mission owner (``roles.agent_context_for``):
they can read and checkpoint within the owner's current site scope and can never
approve, sign, release or execute. Authority is rechecked at every activation, so a
revoked owner stops the mission from progressing.

``TemporalScheduler`` implements ``missions.MissionScheduler``. If Temporal is
unreachable, the wake-up is written to an ``orchestration_backlog`` record (mission
state itself is already durable) and ``replay_backlog`` re-sends it later; nothing is
silently lost.
"""

from __future__ import annotations

import asyncio
import threading
from contextvars import copy_context
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Iterable

from temporalio import activity
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.worker import Replayer, Worker

from ..container import Platform
from ..identity import AccessContext
from ..ids import iso, new_id, utc_now
from ..missions import Activation, MissionService
from ..roles import agent_context_for
from ..store import LeaseError
from .temporal_workflows import (ACTIVITY_ACTIVATE, ACTIVITY_NEXT_DUE, ActivationRequest, ActivationResult,
                                 MissionInput, MissionWorkflow)

TASK_QUEUE = "lifesci-missions"
Coordinator = Callable[[Platform, AccessContext, Activation, list[str], str], None]


def _utc(value: str) -> str:
    """Normalize the workflow's ISO time to the store's UTC ISO format for string comparison."""
    return iso(datetime.fromisoformat(value))


def workflow_id(tenant_id: str, mission_id: str) -> str:
    return f"lifesci-mission:{tenant_id}:{mission_id}"


def default_coordinator(platform: Platform, ctx: AccessContext, act: Activation, reasons: list[str],
                        as_of: str) -> None:
    from ..runtime import run_coordinator
    run_coordinator(platform, ctx, act, reasons, as_of)


class MissionActivities:
    def __init__(self, platform: Platform, coordinator: Coordinator = default_coordinator) -> None:
        self.platform = platform
        self.coordinator = coordinator

    def _ctx(self, tenant_id: str, mission_id: str) -> AccessContext:
        rec = self.platform.store.read().require(tenant_id, "mission", mission_id)
        owner = self.platform.identity.context_for(tenant_id, rec.state["owner_id"])
        return agent_context_for(owner, self.platform.identity)

    @activity.defn(name=ACTIVITY_NEXT_DUE)
    def next_due_at(self, req: ActivationRequest) -> str | None:
        mission = self.platform.missions.get(self._ctx(req.tenant_id, req.mission_id), req.mission_id)
        return MissionService.next_unsurfaced_due(mission)

    @activity.defn(name=ACTIVITY_ACTIVATE)
    def activate(self, req: ActivationRequest) -> ActivationResult:
        ctx = self._ctx(req.tenant_id, req.mission_id)
        mission = self.platform.missions.get(ctx, req.mission_id)
        if mission["status"] in ("cancelled", "archived"):
            return ActivationResult(mission["status"], "terminal")
        # Stable per mission workflow (survives retries and continue-as-new); a different holder
        # (e.g. a manual coordinator) raises LeaseError and Temporal retries with backoff.
        worker = f"temporal:{workflow_id(req.tenant_id, req.mission_id)}"
        activity.heartbeat("activating")  # a lost worker is detected within the heartbeat timeout
        act = self.platform.missions.activate(ctx, req.mission_id, worker)
        stop = threading.Event()
        context = copy_context()
        def pulse() -> None:
            while not stop.wait(10):
                activity.heartbeat("coordinator_running")
        heartbeat = threading.Thread(target=lambda: context.run(pulse), daemon=True)
        heartbeat.start()
        try:
            self.coordinator(self.platform, ctx, act, req.reasons, req.as_of)
        finally:
            stop.set()
            heartbeat.join(timeout=1)
            try:
                self.platform.missions.release(act)
            except LeaseError:
                pass  # superseded during the activation; the newer holder owns the mission
        return ActivationResult(self.platform.missions.get(ctx, req.mission_id)["status"], "activated")


class TemporalScheduler:
    """Synchronous ``MissionScheduler`` facade over the async Temporal client."""

    def __init__(self, client: Client, platform: Platform, task_queue: str = TASK_QUEUE,
                 loop: asyncio.AbstractEventLoop | None = None, timeout_s: float = 10.0) -> None:
        self.client = client
        self.platform = platform
        self.task_queue = task_queue
        self.timeout_s = timeout_s
        self._own_loop = loop is None
        self._loop = loop or asyncio.new_event_loop()
        if self._own_loop:
            threading.Thread(target=self._loop.run_forever, daemon=True, name="temporal-scheduler").start()

    @classmethod
    def connect(cls, address: str, platform: Platform, *, namespace: str = "default",
                task_queue: str = TASK_QUEUE) -> "TemporalScheduler":
        """Create the client on the scheduler's own loop thread (for synchronous callers such as the API)."""
        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_forever, daemon=True, name="temporal-scheduler").start()
        client = asyncio.run_coroutine_threadsafe(Client.connect(address, namespace=namespace), loop).result(30)
        scheduler = cls(client, platform, task_queue=task_queue, loop=loop)
        scheduler._own_loop = True
        return scheduler

    def _run(self, coro: Any) -> Any:
        fut: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(self.timeout_s)

    async def _signal(self, tenant_id: str, mission_id: str, reason: str) -> None:
        await self.client.start_workflow(
            MissionWorkflow.run, MissionInput(tenant_id, mission_id), id=workflow_id(tenant_id, mission_id),
            task_queue=self.task_queue, start_signal="wake", start_signal_args=[reason],
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING)

    def schedule_wakeup(self, tenant_id: str, mission_id: str, reason: str) -> None:
        try:
            self._run(self._signal(tenant_id, mission_id, reason))
        except Exception as exc:  # orchestrator unreachable: persist the intent to wake
            with self.platform.store.transaction("temporal-scheduler") as tx:
                tx.put(tenant_id, "orchestration_backlog", new_id("wake"),
                       {"mission_id": mission_id, "reason": reason, "error": str(exc)[:300],
                        "status": "pending", "at": iso(utc_now())}, expected_revision=None, action="backlog")

    def schedule_timer(self, tenant_id: str, mission_id: str, at: datetime, reason: str) -> None:
        # Due times live on obligations in the store; the workflow recomputes its durable timer.
        self.schedule_wakeup(tenant_id, mission_id, "obligations_changed")

    def replay_backlog(self, tenant_id: str) -> int:
        sent = 0
        for rec in self.platform.store.read().list(tenant_id, "orchestration_backlog",
                                                    lambda s: s["status"] == "pending"):
            self._run(self._signal(tenant_id, rec.state["mission_id"], rec.state["reason"]))
            with self.platform.store.transaction("temporal-scheduler") as tx:
                cur = tx.require(tenant_id, "orchestration_backlog", rec.id)
                tx.put(tenant_id, "orchestration_backlog", rec.id, {**cur.state, "status": "sent", "sent_at": iso(utc_now())},
                       expected_revision=cur.revision, action="backlog_sent")
            sent += 1
        return sent

    def handle(self, tenant_id: str, mission_id: str) -> WorkflowHandle:
        return self.client.get_workflow_handle(workflow_id(tenant_id, mission_id))

    def close(self) -> None:
        if self._own_loop:
            self._loop.call_soon_threadsafe(self._loop.stop)


def build_worker(client: Client, platform: Platform, *, coordinator: Coordinator = default_coordinator,
                 task_queue: str = TASK_QUEUE, max_activity_threads: int = 8,
                 max_cached_workflows: int | None = None) -> Worker:
    """Activities do blocking store I/O, so they run on a bounded thread pool, not the event loop.

    ``max_cached_workflows=0`` disables sticky execution (used in tests that replace workers).
    """
    acts = MissionActivities(platform, coordinator)
    extra = {} if max_cached_workflows is None else {"max_cached_workflows": max_cached_workflows}
    return Worker(client, task_queue=task_queue, workflows=[MissionWorkflow],
                  activities=[acts.next_due_at, acts.activate],
                  activity_executor=ThreadPoolExecutor(max_workers=max_activity_threads), **extra)


async def verify_replay(histories: Iterable[Any]) -> int:
    """Replay recorded histories against the current workflow code; raises on nondeterminism.

    Run before deploying workflow changes (V12): in-flight missions must replay cleanly.
    """
    replayer = Replayer(workflows=[MissionWorkflow])
    count = 0
    for history in histories:
        await replayer.replay_workflow(history)
        count += 1
    return count


def attach(platform: Platform, scheduler: TemporalScheduler) -> None:
    """Route MissionService wake-ups and timers through Temporal."""
    platform.missions.scheduler = scheduler


__all__ = ["MissionActivities", "TemporalScheduler", "build_worker", "verify_replay", "attach", "workflow_id",
           "default_coordinator", "MissionService", "TASK_QUEUE"]
