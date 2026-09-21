from __future__ import annotations


class Historian:
    name = "Historian/SCADA"

    def __init__(self) -> None:
        self.points: list[dict] = []

    def record(self, hour: int, batch_id: str, signals: dict[str, float]) -> None:
        self.points.append({"hour": hour, "batch_id": batch_id, **signals})

    def get_process_history(self, batch_id: str, start_hour: int = 0, end_hour: int = 10**9) -> list[dict]:
        return [p for p in self.points if p["batch_id"] == batch_id and start_hour <= p["hour"] <= end_hour]

