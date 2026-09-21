from __future__ import annotations

from benchmark.factory.state import FactoryState


class CMMS:
    name = "CMMS"

    def __init__(self, state: FactoryState) -> None:
        self.state = state
        self.work_orders: list[dict] = []

    def get_equipment_history(self, asset_id: str) -> dict:
        asset = self.state.equipment[asset_id]
        return {"asset_id": asset_id, "health": asset.health, "work_orders": [w for w in self.work_orders if w["asset_id"] == asset_id]}

    def create_work_order(self, asset_id: str, hour: int, priority: str, description: str) -> str:
        work_order_id = f"WO-{len(self.work_orders) + 1:04d}"
        self.work_orders.append({"work_order_id": work_order_id, "asset_id": asset_id, "hour": hour, "priority": priority, "description": description})
        return work_order_id

