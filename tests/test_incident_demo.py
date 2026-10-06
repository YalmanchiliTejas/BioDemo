from __future__ import annotations

import json
import unittest

from benchmark.incident_demo.service import IncidentDemoService


class InvalidEvidenceProvider:
    provider_id = "test.invalid-evidence"

    def complete(self, request: dict) -> dict:
        valid = request["valid_evidence_ids"][0]
        return {
            "severity": "high",
            "triage_level": "L3",
            "summary": "Test response",
            "observations": [
                {"statement": "Mixed references", "evidence_ids": [valid, "FUTURE-RECALL"]}
            ],
            "related_events": [],
            "hypotheses": [{
                "title": "Test hypothesis",
                "confidence": 1.7,
                "supporting_evidence_ids": [valid, "MADE-UP-ID"],
                "contradicting_evidence_ids": [],
            }],
            "recommended_actions": [],
            "teams_to_notify": ["QA"],
        }


class IncidentDemoTests(unittest.TestCase):
    def test_seed_contains_public_lots_and_normal_batches(self) -> None:
        service = IncidentDemoService()
        batches = service.data["batches"]
        ids = {batch["batch_id"] for batch in batches}
        self.assertTrue({"6133156", "6133194", "6133388"} <= ids)
        self.assertGreaterEqual(len(batches), 10)
        self.assertTrue(any(batch["status"] == "released" for batch in batches))

    def test_replay_state_does_not_leak_final_recall_outcome(self) -> None:
        service = IncidentDemoService()
        state = service.visible_state(5)
        serialized = json.dumps(state).lower()
        self.assertNotIn("recalled", serialized)
        self.assertNotIn("pf-005", serialized)
        batch = next(item for item in state["batches"] if item["batch_id"] == "6133156")
        self.assertEqual(batch["disposition"], "not_available_at_current_cutoff")

    def test_severity_increases_only_as_evidence_accumulates(self) -> None:
        service = IncidentDemoService()
        first = service.assessment(3)["assessment"]
        repeated = service.assessment(9)["assessment"]
        self.assertEqual((first["severity"], first["triage_level"]), ("medium", "L2"))
        self.assertEqual((repeated["severity"], repeated["triage_level"]), ("high", "L3"))
        service.complete_task("TASK-MICRO-01", "Gram-negative organism confirmed.")
        confirmed = service.assessment(9)["assessment"]
        self.assertEqual(confirmed["severity"], "critical")
        self.assertIn("LR-004", confirmed["observations"][-1]["evidence_ids"])

    def test_invalid_model_evidence_ids_are_removed(self) -> None:
        service = IncidentDemoService(provider=InvalidEvidenceProvider())
        result = service.assessment(3, live=True)
        assessment = result["assessment"]
        visible_ids = set(result["visible_state"]["evidence_by_id"])
        returned_ids = {
            evidence_id
            for observation in assessment["observations"]
            for evidence_id in observation["evidence_ids"]
        }
        self.assertTrue(returned_ids <= visible_ids)
        self.assertNotIn("FUTURE-RECALL", returned_ids)
        self.assertEqual(assessment["hypotheses"][0]["confidence"], 1.0)

    def test_comparison_is_derived_from_timeline_anchors(self) -> None:
        comparison = IncidentDemoService().comparison()
        self.assertEqual(comparison["without_os"]["pattern_recognition_minutes"], 19 * 60)
        self.assertEqual(comparison["with_os"]["pattern_recognition_minutes"], 3)
        self.assertEqual(comparison["label"], "SIMULATED DEMO RESULTS")


if __name__ == "__main__":
    unittest.main()
