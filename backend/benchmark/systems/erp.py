from __future__ import annotations

from benchmark.factory.state import FactoryState


class ERP:
    name = "ERP"

    def __init__(self, state: FactoryState) -> None:
        self.state = state
        self.suppliers = {"cell culture media": "SUPPLIER-A", "purification buffer": "SUPPLIER-B"}

    def get_material_lot(self, lot_id: str) -> dict:
        lot = self.state.materials[lot_id]
        return {"lot_id": lot.lot_id, "material": lot.material, "quantity": lot.quantity, "status": lot.status, "supplier": self.suppliers[lot.material]}

    def set_lot_status(self, lot_id: str, status: str) -> None:
        self.state.materials[lot_id].status = status
