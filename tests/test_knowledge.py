from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from benchmark.knowledge import InMemoryDocumentStore, InMemoryGraphStore, KnowledgeBase, KnowledgeRule


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = InMemoryGraphStore()
        self.documents = InMemoryDocumentStore()
        self.knowledge = KnowledgeBase(self.graph, self.documents)
        self.start = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def event(self, hour: int, event_type: str, info: list[str]) -> dict:
        return {
            "timestamp": (self.start + timedelta(hours=hour)).isoformat(),
            "event_failure": event_type,
            "actor_agent_action": "inspect equipment",
            "decision": "continue investigation",
            "information_available": info,
            "plant_state": {"active_batches": {"BATCH-01": "upstream"}, "unavailable_assets": []},
            "scenario_id": "SCN-01",
        }

    def test_ingestion_is_idempotent_and_links_previous_event_per_entity(self) -> None:
        first = self.knowledge.ingest_event(self.event(1, "alarm", ["BIOREACTOR-01"]))
        second = self.knowledge.ingest_event(self.event(2, "intervention", ["BIOREACTOR-01"]))
        duplicate = self.knowledge.ingest_event(self.event(2, "intervention", ["BIOREACTOR-01"]))

        self.assertEqual(second.event_id, duplicate.event_id)
        self.assertEqual(len(self.graph.events), 2)
        self.assertEqual(self.graph.previous[("BIOREACTOR-01", second.event_id)], first.event_id)
        self.assertEqual(len(self.documents.documents), 2)

    def test_late_event_repairs_the_entity_timeline(self) -> None:
        first = self.knowledge.ingest_event(self.event(1, "alarm", ["BIOREACTOR-01"]))
        third = self.knowledge.ingest_event(self.event(3, "resolved", ["BIOREACTOR-01"]))
        second = self.knowledge.ingest_event(self.event(2, "inspection", ["BIOREACTOR-01"]))

        self.assertEqual(self.graph.previous[("BIOREACTOR-01", second.event_id)], first.event_id)
        self.assertEqual(self.graph.previous[("BIOREACTOR-01", third.event_id)], second.event_id)

    def test_context_is_time_bounded_and_returns_latest_applicable_rule(self) -> None:
        first = self.knowledge.ingest_event(self.event(1, "alarm", ["BIOREACTOR-01"]))
        self.knowledge.ingest_event(self.event(5, "alarm", ["BIOREACTOR-01"]))
        self.knowledge.update_rule(KnowledgeRule(
            "RULE-PH", 1, "Escalate pH alarms", ("BIOREACTOR-01",), ("alarm",), self.start,
        ))
        self.knowledge.update_rule(KnowledgeRule(
            "RULE-PH", 2, "Hold the batch and escalate pH alarms", ("BIOREACTOR-01",), ("alarm",),
            self.start + timedelta(hours=4), supersedes_version=1,
        ))

        early = self.knowledge.context(
            "pH alarm", entity_ids=["BIOREACTOR-01"], event_type="alarm",
            at=self.start + timedelta(hours=2),
        )
        late = self.knowledge.context(
            "pH alarm", entity_ids=["BIOREACTOR-01"], event_type="alarm",
            at=self.start + timedelta(hours=6),
        )

        self.assertEqual([event.event_id for event in early.events], [first.event_id])
        self.assertEqual(early.rules[0].version, 1)
        self.assertEqual(late.rules[0].version, 2)
        self.assertEqual(late.previous_event_by_entity["BIOREACTOR-01"], late.events[0].event_id)

    def test_rule_versions_must_be_sequential(self) -> None:
        with self.assertRaisesRegex(ValueError, "next rule version"):
            self.knowledge.update_rule(KnowledgeRule("RULE-1", 3, "invalid", supersedes_version=1))


if __name__ == "__main__":
    unittest.main()
