from __future__ import annotations

from benchmark.factory.state import FactoryState


class Scheduler:
    name = "Scheduler"

    def __init__(self, state: FactoryState) -> None:
        self.state = state
        self.changes: list[dict] = []

    def get_schedule(self) -> list[dict]:
        return [{"batch_id": b.plan.batch_id, "planned_start_hour": b.plan.planned_start_hour, "stage": b.stage} for b in self.state.batches.values()]

    def reschedule_batch(self, batch_id: str, new_start_hour: int, reason: str) -> None:
        batch = self.state.batches[batch_id]
        self.changes.append({"batch_id": batch_id, "old_start_hour": batch.plan.planned_start_hour, "new_start_hour": new_start_hour, "reason": reason})
        batch.hold_until_hour = max(batch.hold_until_hour, new_start_hour)

