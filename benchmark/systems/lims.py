from __future__ import annotations


class LIMS:
    name = "LIMS"

    def __init__(self) -> None:
        self.samples: list[dict] = []

    def request_qc_test(self, batch_id: str, assay: str, hour: int, due_hour: int) -> str:
        sample_id = f"S-{len(self.samples) + 1:04d}"
        self.samples.append({"sample_id": sample_id, "batch_id": batch_id, "assay": assay, "requested_hour": hour, "due_hour": due_hour, "status": "pending", "result": None})
        return sample_id

    def set_result(self, sample_id: str, result: str, hour: int | None = None) -> None:
        sample = next(s for s in self.samples if s["sample_id"] == sample_id)
        if hour is not None and hour < sample["due_hour"]:
            raise ValueError("QC result cannot be reported before its due hour")
        sample.update(status="complete", result=result, reported_hour=hour)

    def defer_results(self, batch_id: str, delay_hours: int) -> None:
        for sample in self.samples:
            if sample["batch_id"] == batch_id and sample["status"] == "pending":
                sample["due_hour"] += delay_hours

    def complete_due_tests(self, hour: int) -> list[dict]:
        completed = []
        for sample in self.samples:
            if sample["status"] == "pending" and sample["due_hour"] <= hour:
                self.set_result(sample["sample_id"], "pass", hour)
                completed.append(sample.copy())
        return completed

    def get_qc_results(self, batch_id: str) -> list[dict]:
        return [s.copy() for s in self.samples if s["batch_id"] == batch_id]
