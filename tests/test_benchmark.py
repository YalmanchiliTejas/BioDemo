from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmark.campaign import standard_campaign
from benchmark.factory import build_factory
from benchmark.scenarios import build_scenario_manifest
from benchmark.simulation import BenchmarkSimulation
from benchmark.systems import SystemRegistry


class BenchmarkTests(unittest.TestCase):
    def test_campaign_matches_mvp_scope(self) -> None:
        campaign = standard_campaign()
        self.assertEqual(campaign.duration_hours, 720)
        self.assertEqual(len(campaign.batches), 12)
        self.assertEqual(len(build_factory(campaign.batches).equipment), 5)

    def test_manifest_is_deterministic_and_has_ground_truth(self) -> None:
        first = build_scenario_manifest(1234)
        second = build_scenario_manifest(1234)
        different = build_scenario_manifest(1235)
        self.assertEqual(first, second)
        self.assertEqual(len(first.scenarios), 12)
        self.assertTrue(all(s.ground_truth_cause for s in first.scenarios))
        self.assertNotEqual(first.fingerprint, different.fingerprint)

    def test_traditional_run_is_reproducible(self) -> None:
        first = BenchmarkSimulation(seed=77).run()
        second = BenchmarkSimulation(seed=77).run()
        self.assertEqual(first.metrics, second.metrics)
        self.assertEqual([e.to_dict() for e in first.events], [e.to_dict() for e in second.events])

    def test_all_required_systems_and_api_methods_exist(self) -> None:
        state = build_factory(standard_campaign().batches)
        systems = SystemRegistry(state)
        self.assertEqual(len(systems.names), 8)
        methods = (
            (systems.mes, "get_batch"),
            (systems.historian, "get_process_history"),
            (systems.lims, "get_qc_results"),
            (systems.erp, "get_material_lot"),
            (systems.cmms, "get_equipment_history"),
            (systems.qms, "get_prior_deviations"),
            (systems.qms, "create_deviation"),
            (systems.cmms, "create_work_order"),
            (systems.scheduler, "reschedule_batch"),
            (systems.lms, "allocate_operator"),
            (systems.lims, "request_qc_test"),
        )
        self.assertTrue(all(callable(getattr(obj, name, None)) for obj, name in methods))

    def test_event_log_is_complete_and_replayable(self) -> None:
        required = {
            "timestamp", "plant_state", "event_failure", "information_available",
            "actor_agent_action", "tool_used", "decision", "approval_required",
            "time_consumed_hours", "production_impact", "quality_impact", "financial_impact",
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = BenchmarkSimulation(seed=88).run(output)
            records = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), len(result.events))
            self.assertTrue(all(required <= record.keys() for record in records))
            self.assertEqual(sum(record["scenario_id"] is not None for record in records), 12)
            self.assertTrue((output / "campaign.json").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_unimplemented_modes_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only the Traditional"):
            BenchmarkSimulation(mode="agentic")


if __name__ == "__main__":
    unittest.main()
