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
        self.assertTrue({"BATCH-075", "BATCH-084", "BATCH-099"} <= ids)
        self.assertFalse({"6133156", "6133194", "6133388"} & ids)
        self.assertEqual(len(batches), 100)
        self.assertTrue(any(batch["status"] == "released" for batch in batches))
        self.assertFalse(any(batch["status"] == "recalled" for batch in batches))
        normal_line_a = [batch for batch in batches if batch["batch_id"].startswith("SYN-") and batch["production_line"] == "LINE-A"]
        self.assertGreaterEqual(len(normal_line_a), 50)

    def test_primary_replay_has_no_memory_or_scripted_agent_win(self) -> None:
        service = IncidentDemoService()
        self.assertEqual(service.data["incident_memory"], [])
        titles = {event["title"] for event in service.data["replay_events"]}
        self.assertNotIn("Recurring pattern surfaced", titles)
        self.assertNotIn("Broader pattern recognized manually", titles)

    def test_replay_state_does_not_leak_final_recall_outcome(self) -> None:
        service = IncidentDemoService()
        state = service.visible_state(5)
        serialized = json.dumps(state).lower()
        self.assertNotIn("recalled", serialized)
        self.assertNotIn("pf-005", serialized)
        batch = next(item for item in state["batches"] if item["batch_id"] == "BATCH-075")
        self.assertEqual(batch["disposition"], "released")

    def test_severity_increases_only_as_evidence_accumulates(self) -> None:
        service = IncidentDemoService()
        first = service.assessment(3)["assessment"]
        repeated = service.assessment(9)["assessment"]
        self.assertEqual((first["severity"], first["triage_level"]), ("medium", "L2"))
        self.assertEqual((repeated["severity"], repeated["triage_level"]), ("high", "L3"))
        service.complete_task("TASK-MICRO-01", "Gram-negative organism confirmed.")
        confirmed = service.assessment(10)["assessment"]
        self.assertEqual(confirmed["severity"], "critical")
        self.assertIn("LR-HUMAN-001", confirmed["observations"][-1]["evidence_ids"])

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

    def test_comparison_is_derived_from_frozen_benchmark(self) -> None:
        comparison = IncidentDemoService().comparison()
        self.assertEqual(comparison["label"], "SIMULATED BENCHMARK RESULT")
        self.assertTrue(comparison["dataset_fingerprint"])
        without = dict(comparison["without_os"]["metrics"])
        with_os = dict(comparison["with_os"]["metrics"])
        self.assertIn("Incident recall", without)
        self.assertIn("Incident recall", with_os)
        self.assertGreaterEqual(float(with_os["Incident recall"].rstrip("%")), float(without["Incident recall"].rstrip("%")))


if __name__ == "__main__":
    unittest.main()
