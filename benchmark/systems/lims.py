from __future__ import annotations


class LIMS:
    name = "LIMS"

    def __init__(self) -> None:
        self.samples: list[dict] = []

    def request_qc_test(self, batch_id: str, assay: str, hour: int, due_hour: int) -> str:
        sample_id = f"S-{len(self.samples) + 1:04d}"
        self.samples.append({"sample_id": sample_id, "batch_id": batch_id, "assay": assay, "requested_hour": hour, "due_hour": due_hour, "status": "pending", "result": None})
        return sample_id

    def set_result(self, sample_id: str, result: str) -> None:
        sample = next(s for s in self.samples if s["sample_id"] == sample_id)
        sample.update(status="complete", result=result)

    def get_qc_results(self, batch_id: str) -> list[dict]:
        return [s.copy() for s in self.samples if s["batch_id"] == batch_id]

