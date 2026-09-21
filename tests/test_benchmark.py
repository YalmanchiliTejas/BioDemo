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
            self.assertEqual(sum(record["scenario_id"] is not None and record["event_failure"] != "traditional_intervention" for record in records), 12)
            self.assertEqual(sum(record["event_failure"] == "traditional_intervention" for record in records), 12)
            self.assertTrue((output / "campaign.json").exists())
            self.assertTrue((output / "summary.json").exists())

    def test_unimplemented_modes_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only the Traditional"):
            BenchmarkSimulation(mode="agentic")

    def test_fault_evidence_and_quality_gates(self) -> None:
        simulation = BenchmarkSimulation(seed=20250921)
        simulation.run()
        points = simulation.systems.historian.points
        self.assertTrue(any(p.get("pH", 0) > simulation.process.limits.ph_high for p in points))
        self.assertTrue(any(p.get("DO_pct", 100) < simulation.process.limits.do_low_pct for p in points))
        self.assertTrue(any(p.get("pressure_bar", 0) > simulation.process.limits.chromatography_pressure_high_bar for p in points))
        self.assertTrue(any(s["result"] == "OOS" for s in simulation.systems.lims.samples))
        self.assertTrue(all(
            all(s["result"] == "pass" and s["reported_hour"] <= batch.released_hour
                for s in simulation.systems.lims.get_qc_results(batch.plan.batch_id))
            for batch in simulation.state.batches.values() if batch.stage == "released"
        ))

    def test_material_quarantine_substitutes_before_consumption(self) -> None:
        simulation = BenchmarkSimulation(seed=20250921)
        simulation.run()
        self.assertEqual(simulation.state.materials["RM-003"].status, "quarantined")
        self.assertTrue(all(
            batch.material_lot_id != "RM-003"
            for batch in simulation.state.batches.values()
            if batch.material_consumed and batch.plan.material_lot_id == "RM-003"
        ))
        self.assertEqual(simulation.state.batches["BATCH-06"].stage, "rejected")
        self.assertTrue(any(s["result"] == "OOS" for s in simulation.systems.lims.get_qc_results("BATCH-06")))

    def test_qms_as_of_hides_future_closure(self) -> None:
        simulation = BenchmarkSimulation(seed=20250921)
        simulation.run()
        deviation = simulation.systems.qms.deviations[0]
        visible = simulation.systems.qms.get_prior_deviations(as_of_hour=deviation["opened_hour"])
        self.assertIsNone(visible[0]["closed_hour"])

    def test_compound_incident_has_equipment_and_material_evidence(self) -> None:
        simulation = BenchmarkSimulation(seed=20250921)
        simulation.run()
        self.assertEqual(simulation.state.materials["BUF-001"].status, "quarantined")
        self.assertTrue(any(work["asset_id"] == "PUMP-01" for work in simulation.systems.cmms.work_orders))
        self.assertEqual(simulation.state.batches["BATCH-11"].buffer_lot_id, "BUF-002")
        self.assertTrue(simulation.state.batches["BATCH-11"].buffer_consumed)


if __name__ == "__main__":
    unittest.main()
