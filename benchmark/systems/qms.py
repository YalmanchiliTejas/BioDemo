from __future__ import annotations


class QMS:
    name = "QMS"

    def __init__(self) -> None:
        self.deviations: list[dict] = []

    def create_deviation(self, batch_id: str | None, scenario_id: str, hour: int, description: str) -> str:
        deviation_id = f"DEV-{len(self.deviations) + 1:04d}"
        self.deviations.append({"deviation_id": deviation_id, "batch_id": batch_id, "scenario_id": scenario_id, "opened_hour": hour, "closed_hour": None, "description": description})
        return deviation_id

    def close_deviation(self, deviation_id: str, hour: int) -> None:
        next(d for d in self.deviations if d["deviation_id"] == deviation_id)["closed_hour"] = hour

    def get_prior_deviations(self, description_contains: str = "") -> list[dict]:
        needle = description_contains.lower()
        return [d.copy() for d in self.deviations if needle in d["description"].lower()]

