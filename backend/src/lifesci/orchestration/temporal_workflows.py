"""Deterministic Temporal workflow for one manufacturing mission.

Workflow history contains only ids and wake reasons. All reads/writes of mission
state happen in activities against the record store (ADR 0003): Temporal owns
"when to run", the domain store owns "what is true".

Behavior:
- ``wake`` signals are coalesced: duplicate reasons collapse, distinct reasons are
  never dropped, and signals arriving during an activation are kept for the next.
- The next obligation due time (from an activity) becomes a durable timer.
- After ``max_iterations`` activations, or when Temporal suggests it, the workflow
  continues-as-new with the same workflow id and any pending reasons, bounding history.
- Changes to this file must stay replay-compatible with running histories; use
  ``workflow.patched(...)`` for behavior changes and run ``verify_replay`` in CI.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

ACTIVITY_NEXT_DUE = "lifesci_mission_next_due_at"
ACTIVITY_ACTIVATE = "lifesci_mission_activate"


@dataclass
class MissionInput:
    tenant_id: str
    mission_id: str
    pending_reasons: list[str] = field(default_factory=list)
    max_iterations: int = 200


@dataclass
class ActivationRequest:
    tenant_id: str
    mission_id: str
    reasons: list[str]
    workflow_run_id: str
    as_of: str = ""  # workflow time; activities judge "due" against this, not the worker's clock


@dataclass
class ActivationResult:
    mission_status: str
    detail: str = ""


TERMINAL = ("cancelled", "archived")


@workflow.defn(name="LifesciMissionWorkflow")
class MissionWorkflow:
    def __init__(self) -> None:
        self._reasons: list[str] = []
        self._stop = False
        self._activations = 0

    @workflow.signal
    def wake(self, reason: str) -> None:
        if reason not in self._reasons:
            self._reasons.append(reason)

    @workflow.signal
    def stop(self) -> None:
        self._stop = True

    @workflow.query
    def pending(self) -> list[str]:
        return list(self._reasons)

    @workflow.query
    def activations(self) -> int:
        return self._activations

    @workflow.run
    async def run(self, inp: MissionInput) -> str:
        for reason in inp.pending_reasons:
            self.wake(reason)
        retry = RetryPolicy(initial_interval=timedelta(seconds=1), backoff_coefficient=2.0,
                            maximum_interval=timedelta(minutes=1), maximum_attempts=10)
        last_fired: str | None = None
        while not self._stop:
            due_iso: str | None = await workflow.execute_activity(
                ACTIVITY_NEXT_DUE, ActivationRequest(inp.tenant_id, inp.mission_id, [], workflow.info().run_id,
                                                     workflow.now().isoformat()),
                start_to_close_timeout=timedelta(seconds=30), retry_policy=retry, result_type=str | None)
            timeout = None
            if due_iso:
                delta = datetime.fromisoformat(due_iso) - workflow.now()
                # A due time that already fired but was not surfaced must not spin the loop.
                floor = timedelta(minutes=1) if due_iso == last_fired else timedelta(0)
                timeout = max(delta, floor)
            try:
                await workflow.wait_condition(lambda: bool(self._reasons) or self._stop, timeout=timeout)
            except asyncio.TimeoutError:
                last_fired = due_iso
                self.wake("timer:obligations_due")
            if self._stop:
                break
            reasons, self._reasons = self._reasons, []
            result: ActivationResult = await workflow.execute_activity(
                ACTIVITY_ACTIVATE, ActivationRequest(inp.tenant_id, inp.mission_id, reasons, workflow.info().run_id,
                                                     workflow.now().isoformat()),
                start_to_close_timeout=timedelta(minutes=15), heartbeat_timeout=timedelta(seconds=30),
                retry_policy=retry, result_type=ActivationResult)
            self._activations += 1
            if result.mission_status in TERMINAL:
                return result.mission_status
            if self._activations >= inp.max_iterations or workflow.info().is_continue_as_new_suggested():
                await workflow.wait_condition(workflow.all_handlers_finished)
                workflow.continue_as_new(MissionInput(inp.tenant_id, inp.mission_id, list(self._reasons),
                                                      inp.max_iterations))
        return "stopped"
