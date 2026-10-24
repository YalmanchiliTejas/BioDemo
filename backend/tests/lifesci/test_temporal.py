"""Temporal orchestration against the SDK's time-skipping test server (downloaded on first use).

Skipped when temporalio is not installed or the test server cannot start.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest

temporalio = pytest.importorskip("temporalio")
from temporalio.client import WorkflowExecutionStatus  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402

from src.lifesci.container import Platform  # noqa: E402
from src.lifesci.ids import iso, utc_now  # noqa: E402
from src.lifesci.orchestration.temporal import (TemporalScheduler, attach, build_worker,  # noqa: E402
                                                default_coordinator, verify_replay, workflow_id)
from src.lifesci.orchestration.temporal_workflows import MissionInput, MissionWorkflow  # noqa: E402
from src.lifesci.store import RecordStore  # noqa: E402

T = "tenant-t"


@pytest.fixture(scope="module")
def env():
    loop = asyncio.new_event_loop()
    try:
        environment = loop.run_until_complete(WorkflowEnvironment.start_time_skipping())
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Temporal test server unavailable: {exc}")
    yield loop, environment
    loop.run_until_complete(environment.shutdown())
    loop.close()


def platform_with_mission():
    p = Platform(RecordStore(), providers={})
    p.identity.assign_role(T, "owner", "msat", site_id="S1")
    ctx = p.identity.context_for(T, "owner")
    m = p.missions.start_or_resume(ctx, objective="Daily trend review", owner_id="owner", scope={"site_ids": ["S1"]})
    return p, ctx, m["mission_id"]


class Recorder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, platform, ctx, act, reasons, as_of):
        self.calls.append(list(reasons))
        default_coordinator(platform, ctx, act, reasons, as_of)


async def wait_for(predicate, timeout=20.0):
    for _ in range(int(timeout / 0.05)):
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not reached")


def test_durable_obligation_timer_fires_after_time_skip(env):
    loop, environment = env

    async def scenario():
        p, ctx, mid = platform_with_mission()
        due = iso(utc_now() + timedelta(hours=12))
        p.missions.add_obligation(ctx, mid, description="12h review", due_at=due)
        rec = Recorder()
        tq = f"tq-{uuid.uuid4()}"
        async with build_worker(environment.client, p, coordinator=rec, task_queue=tq):
            handle = await environment.client.start_workflow(MissionWorkflow.run, MissionInput(T, mid),
                                                             id=workflow_id(T, mid), task_queue=tq)
            await environment.sleep(timedelta(hours=11))
            assert rec.calls == []  # not due yet: no activation, no wasted work
            await environment.sleep(timedelta(hours=2))
            await wait_for(lambda: rec.calls)
            assert rec.calls[0] == ["timer:obligations_due"]
            await environment.sleep(timedelta(hours=5))
            assert len(rec.calls) == 1  # surfaced once; an overdue obligation does not re-fire in a loop
            await handle.signal(MissionWorkflow.stop)
            assert await handle.result() == "stopped"
        m = p.missions.get(ctx, mid)
        assert m["checkpoint"] is not None and any(w.startswith("obligation:") for w in m["remaining_work"])

    loop.run_until_complete(scenario())


def test_wakeups_coalesce_and_survive_worker_loss(env):
    loop, environment = env

    async def scenario():
        p, ctx, mid = platform_with_mission()
        tq = f"tq-{uuid.uuid4()}"
        handle = await environment.client.start_workflow(MissionWorkflow.run, MissionInput(T, mid),
                                                         id=workflow_id(T, mid), task_queue=tq)
        # No worker running: signals are durably recorded by Temporal.
        for reason in ["events", "events", "decision:d1", "events"]:
            await handle.signal(MissionWorkflow.wake, reason)
        rec = Recorder()
        async with build_worker(environment.client, p, coordinator=rec, task_queue=tq, max_cached_workflows=0):
            await wait_for(lambda: rec.calls)
            assert sorted(rec.calls[0]) == ["decision:d1", "events"]  # coalesced, nothing dropped
            await handle.signal(MissionWorkflow.wake, "correction:c1")
            await wait_for(lambda: len(rec.calls) >= 2)
        # worker stopped (possibly mid-activity); a new worker continues the same workflow
        await handle.signal(MissionWorkflow.wake, "events:late")
        rec2 = Recorder()
        async with build_worker(environment.client, p, coordinator=rec2, task_queue=tq, max_cached_workflows=0):
            await wait_for(lambda: any("events:late" in c for c in rec2.calls), timeout=60)
            seen = {r for c in rec.calls + rec2.calls for r in c}
            assert {"events", "decision:d1", "correction:c1", "events:late"} <= seen  # no reason lost
            await handle.signal(MissionWorkflow.stop)
            await handle.result()

    loop.run_until_complete(scenario())


def test_continue_as_new_keeps_mission_identity_and_replays(env):
    loop, environment = env

    async def scenario():
        p, ctx, mid = platform_with_mission()
        tq = f"tq-{uuid.uuid4()}"
        rec = Recorder()
        async with build_worker(environment.client, p, coordinator=rec, task_queue=tq):
            handle = await environment.client.start_workflow(MissionWorkflow.run, MissionInput(T, mid, max_iterations=2),
                                                             id=workflow_id(T, mid), task_queue=tq)
            first_run = (await handle.describe()).run_id
            for i in range(3):
                await handle.signal(MissionWorkflow.wake, f"events:{i}")
                await wait_for(lambda i=i: len(rec.calls) >= i + 1)
            latest = environment.client.get_workflow_handle(workflow_id(T, mid))
            await wait_for(lambda: True)
            desc = await latest.describe()
            assert desc.run_id != first_run and desc.status == WorkflowExecutionStatus.RUNNING
            first_history = await environment.client.get_workflow_handle(workflow_id(T, mid), run_id=first_run).fetch_history()
            assert await verify_replay([first_history]) == 1  # current code replays the recorded run
            await latest.signal(MissionWorkflow.stop)
            await latest.result()
        assert p.missions.get(ctx, mid)["attempts"] >= 3

    loop.run_until_complete(scenario())


def test_scheduler_port_signal_with_start_and_backlog(env):
    loop, environment = env
    p, ctx, mid = platform_with_mission()
    tq = f"tq-{uuid.uuid4()}"
    sched = TemporalScheduler(environment.client, p, task_queue=tq, loop=loop)

    async def run_worker_until(predicate):
        rec = Recorder()
        async with build_worker(environment.client, p, coordinator=rec, task_queue=tq):
            await wait_for(lambda: predicate(rec))
        return rec

    # MissionService wake-ups (e.g. a recorded correction) route through Temporal.
    attach(p, sched)
    loop.run_until_complete(sched._signal(T, mid, "manual"))
    rec = loop.run_until_complete(run_worker_until(lambda r: r.calls))
    assert rec.calls[0] == ["manual"]

    class Down:
        async def start_workflow(self, *a, **k):
            raise ConnectionError("temporal unreachable")

    down = TemporalScheduler(Down(), p, task_queue=tq, loop=loop)  # type: ignore[arg-type]
    down.schedule_wakeup(T, mid, "events")
    backlog = p.store.read().list(T, "orchestration_backlog")
    assert len(backlog) == 1 and backlog[0].state["status"] == "pending"
    sched2 = TemporalScheduler(environment.client, p, task_queue=tq)  # own loop thread
    assert sched2.replay_backlog(T) == 1
    sched2.close()
    assert p.store.read().list(T, "orchestration_backlog")[0].state["status"] == "sent"
    loop.run_until_complete(environment.client.get_workflow_handle(workflow_id(T, mid)).signal(MissionWorkflow.stop))


def test_activation_runs_as_delegated_agent_and_rechecks_owner(env):
    loop, environment = env

    async def scenario():
        p, ctx, mid = platform_with_mission()
        seen = []
        tq = f"tq-{uuid.uuid4()}"

        def coord(platform, actx, act, reasons, as_of):
            seen.append((actx.actor_kind, actx.delegated_from))
            default_coordinator(platform, actx, act, reasons, as_of)

        async with build_worker(environment.client, p, coordinator=coord, task_queue=tq):
            handle = await environment.client.start_workflow(MissionWorkflow.run, MissionInput(T, mid, ["events"]),
                                                             id=workflow_id(T, mid), task_queue=tq)
            await wait_for(lambda: seen)
            assert seen[0] == ("agent", "owner")
            p.identity.revoke_role(T, "owner", "msat", site_id="S1")
            await handle.signal(MissionWorkflow.wake, "events")
            await asyncio.sleep(1.0)
            assert len(seen) == 1  # owner lost scope: activation is refused (retried, not run)
            await handle.terminate("test cleanup")

    loop.run_until_complete(scenario())
