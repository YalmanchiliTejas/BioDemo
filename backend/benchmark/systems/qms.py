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

    def get_prior_deviations(self, description_contains: str = "", as_of_hour: int | None = None) -> list[dict]:
        needle = description_contains.lower()
        visible = []
        for deviation in self.deviations:
            if needle not in deviation["description"].lower():
                continue
            if as_of_hour is not None and deviation["opened_hour"] > as_of_hour:
                continue
            record = deviation.copy()
            if as_of_hour is not None and record["closed_hour"] is not None and record["closed_hour"] > as_of_hour:
                record["closed_hour"] = None
            visible.append(record)
        return visible
