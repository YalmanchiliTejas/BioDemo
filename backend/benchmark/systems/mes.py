from __future__ import annotations

from benchmark.factory.state import FactoryState


class MES:
    name = "MES/eBR"

    def __init__(self, state: FactoryState) -> None:
        self.state = state
        self.operator_actions: list[dict] = []

    def get_batch(self, batch_id: str) -> dict:
        batch = self.state.batches[batch_id]
        return {
            "batch_id": batch_id,
            "recipe": "MAB-DEMO-v1",
            "stage": batch.stage,
            "material_lot_id": batch.material_lot_id,
            "buffer_lot_id": batch.buffer_lot_id,
            "yield_fraction": batch.yield_fraction,
            "operator_actions": [a for a in self.operator_actions if a["batch_id"] == batch_id],
        }

    def record_operator_action(self, batch_id: str, hour: int, action: str) -> None:
        self.operator_actions.append({"batch_id": batch_id, "hour": hour, "action": action})
