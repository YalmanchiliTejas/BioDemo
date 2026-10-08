from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InvestigationQuestion:
    question_id: str
    question: str
    investigation_type: str
    depth: int
    batch_id: str | None = None
    equipment_id: str | None = None
    search_term: str | None = None


class RecursiveDecomposer:
    """Creates bounded questions from evidence characteristics, not named scenarios."""

    def decompose(
        self,
        problem: str,
        new_evidence: list[dict[str, Any]],
        open_questions: list[str],
        *,
        depth: int = 1,
        limit: int = 6,
    ) -> list[InvestigationQuestion]:
        latest = new_evidence[-1] if new_evidence else {}
        batch = latest.get("batch_id") or latest.get("linked_batch_id") or latest.get("lot")
        equipment = latest.get("equipment_id")
        term = (
            latest.get("test_name") or latest.get("parameter") or latest.get("category")
            or latest.get("event_type") or latest.get("sample_type") or "abnormal signal"
        )
        candidates = [
            ("historical", f"Has a similar {term} signal occurred previously?"),
            ("batch_context", f"What evidence is currently available for batch {batch or 'in scope'}?"),
            ("batch_comparison", "What distinguishes the affected batch from comparable successful or prior batches?"),
            ("process_environment", "Do process or environmental records show a correlated change?"),
            ("equipment_maintenance", "Does equipment condition or maintenance history support a causal path?"),
            ("quality_microbiology", "What quality evidence supports or contradicts the observed signal?"),
        ]
        known = {item["question"] for item in []}
        requested = []
        for index, (kind, question) in enumerate(candidates, 1):
            if question in known:
                continue
            requested.append(InvestigationQuestion(
                f"Q-D{depth}-{index}", question, kind, depth,
                str(batch) if batch else None, str(equipment) if equipment else None, str(term),
            ))
        for question in open_questions:
            if len(requested) >= limit:
                break
            requested.append(InvestigationQuestion(
                f"Q-D{depth}-{len(requested) + 1}", question, "evidence_verification", depth,
                str(batch) if batch else None, str(equipment) if equipment else None, str(term),
            ))
        return requested[:limit]

    def recurse(self, findings: list[dict[str, Any]], *, depth: int, limit: int) -> list[InvestigationQuestion]:
        questions: list[InvestigationQuestion] = []
        for finding in findings:
            for uncertainty in finding.get("uncertainties", []):
                if len(questions) >= limit:
                    return questions
                questions.append(InvestigationQuestion(
                    f"Q-D{depth}-{len(questions) + 1}",
                    f"Can existing evidence resolve this uncertainty: {uncertainty}?",
                    "evidence_verification", depth,
                    finding.get("batch_id"), finding.get("equipment_id"), finding.get("search_term"),
                ))
        return questions

