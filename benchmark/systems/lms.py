from __future__ import annotations

from benchmark.factory.state import FactoryState


class LMS:
    name = "LMS"

    def __init__(self, state: FactoryState) -> None:
        self.state = state
        self.allocations: list[dict] = []

    def qualified_operators(self, qualification: str) -> list[str]:
        return [op.operator_id for op in self.state.operators.values() if op.available and qualification in op.qualifications]

    def allocate_operator(self, qualification: str, batch_id: str, hour: int) -> str | None:
        candidates = self.qualified_operators(qualification)
        if not candidates:
            return None
        operator_id = candidates[0]
        self.allocations.append({"operator_id": operator_id, "qualification": qualification, "batch_id": batch_id, "hour": hour})
        return operator_id

