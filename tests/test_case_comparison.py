"""Tests for the evidence-backed case-comparison dashboard.

Coverage: alignment/divergence math, scorecard delta and missing-data
handling, Fresenius replay time-validity, CHO recorded-pilot and
missing-AI-run behavior, evidence attribution, series downsampling, and
the API surface.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmark.case_comparison import CASE_ORDER, ComparisonService
from benchmark.case_comparison.alignment import (
    TraceEvent,
    detect_divergences,
    normalize_track,
    parse_time,
    seconds_between,
)
from benchmark.case_comparison.report import build_report, main as report_main, write_report
from benchmark.case_comparison.scorecard import (
    CLASSIFICATIONS,
    NOT_MEASURED,
    count_side,
    delta,
    format_duration_seconds,
    metric,
    not_measured,
    side,
)
from benchmark.case_comparison.sources import REPOSITORY, ArtifactStore, default_artifacts


class ScorecardTests(unittest.TestCase):
    def test_lower_is_better_improvement_is_positive(self) -> None:
        result = delta(10.0, 5.0, "lower")
        self.assertEqual(result["absolute_change"], -5.0)
        self.assertEqual(result["improvement_percent"], 50.0)
        self.assertEqual(result["verdict"], "better")
        self.assertEqual(result["glyph"], "▲")

    def test_higher_is_better_worse_is_negative(self) -> None:
        result = delta(1.0, 0.5, "higher")
        self.assertEqual(result["verdict"], "worse")
        self.assertEqual(result["improvement_percent"], -50.0)

    def test_equal_within_tolerance(self) -> None:
        result = delta(2.0, 2.0, "lower")
        self.assertEqual(result["verdict"], "equal")
        self.assertEqual(result["absolute_change"], 0.0)
        self.assertEqual(result["improvement_percent"], 0.0)

    def test_zero_baseline_produces_no_percentage(self) -> None:
        result = delta(0.0, 5.0, "higher")
        self.assertIsNone(result["relative_percent_change"])
        self.assertIsNone(result["improvement_percent"])
        self.assertEqual(result["verdict"], "better")

    def test_missing_value_produces_no_delta(self) -> None:
        self.assertIsNone(delta(None, 5.0, "lower"))
        self.assertIsNone(delta(5.0, None, "lower"))

    def test_invalid_direction_rejected(self) -> None:
        with self.assertRaises(ValueError):
            delta(1.0, 0.0, "sideways")

    def test_side_requires_valid_classification(self) -> None:
        with self.assertRaises(ValueError):
            side(1.0, classification="guessed")
        measured = side(1.5, classification="observed")
        self.assertTrue(measured["available"])
        withheld = not_measured("no recorded run")
        self.assertFalse(withheld["available"])
        self.assertEqual(withheld["display"], "Not measured")
        self.assertEqual(withheld["classification"], NOT_MEASURED)

    def test_metric_only_computes_delta_from_numeric_sides(self) -> None:
        computed = metric(
            id="m1", label="M", group="G", definition="d",
            traditional=side(10.0), ai=side(4.0), direction="lower",
        )
        self.assertIsNotNone(computed["delta"])
        withheld = metric(
            id="m2", label="M", group="G", definition="d",
            traditional=not_measured("none"), ai=not_measured("none"), direction="lower",
        )
        self.assertIsNone(withheld["delta"])
        self.assertEqual(count_side(None, None)["classification"], "not_measured")
        self.assertEqual(count_side(1, 5)["display"], "1/5")
        self.assertEqual(count_side(1300.0, 1300.0)["display"], "1300/1300")

    def test_duration_formatting(self) -> None:
        self.assertEqual(format_duration_seconds(30), "30.0 s")
        self.assertEqual(format_duration_seconds(600), "10.0 min")
        self.assertEqual(format_duration_seconds(7200), "2.0 h")
        self.assertEqual(format_duration_seconds(172800), "2.0 days")


class AlignmentTests(unittest.TestCase):
    def event(self, event_id: str, kind: str, offset: float | None, milestone: bool = True) -> TraceEvent:
        return TraceEvent(
            id=event_id, track="test", kind=kind, title=kind, detail="",
            offset_seconds=offset, milestone=milestone,
        )

    def test_normalize_track_orders_by_offset(self) -> None:
        events = [self.event("b", "x", 20.0), self.event("a", "y", 10.0)]
        normalized = normalize_track(events, clock_start=None)
        self.assertEqual([item["id"] for item in normalized], ["a", "b"])
        self.assertEqual(normalized[0]["offset_seconds"], 10.0)

    def test_normalize_track_derives_offset_from_timestamps(self) -> None:
        event = TraceEvent(
            id="e1", track="t", kind="k", title="t", detail="",
            timestamp="2025-01-02T00:00:00Z", milestone=True,
        )
        normalized = normalize_track([event], clock_start="2025-01-01T00:00:00Z")
        self.assertEqual(normalized[0]["offset_seconds"], 86400.0)
        self.assertEqual(seconds_between("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"), 86400.0)
        self.assertEqual(parse_time("2025-01-01T00:00:00Z").tzinfo is not None, True)

    def test_divergence_verdicts(self) -> None:
        traditional = normalize_track([
            self.event("t1", "ack", 100.0),
            self.event("t2", "close", 500.0),
            self.event("t3", "equal_case", 700.0),
        ], None)
        ai = normalize_track([
            self.event("a1", "ack", 50.0),
            self.event("a2", "only_ai", 400.0),
            self.event("a3", "equal_case", 700.0),
        ], None)
        divergences = {item["kind"]: item for item in detect_divergences(traditional, ai)}
        self.assertEqual(divergences["ack"]["verdict"], "ai_first")
        self.assertEqual(divergences["close"]["verdict"], "traditional_only")
        self.assertIsNone(divergences["close"]["ai"])
        self.assertEqual(divergences["only_ai"]["verdict"], "ai_only")
        # The equal verdict must resolve without a KeyError and report zero difference.
        self.assertEqual(divergences["equal_case"]["verdict"], "equal")
        self.assertEqual(divergences["equal_case"]["difference_seconds"], 0.0)
        self.assertTrue(divergences["equal_case"]["verdict_label"])

    def test_non_milestone_events_ignored(self) -> None:
        traditional = normalize_track([self.event("t1", "noise", 10.0, milestone=False)], None)
        ai = normalize_track([self.event("a1", "noise", 20.0, milestone=False)], None)
        self.assertEqual(detect_divergences(traditional, ai), [])

    def test_milestone_meta_kinds_are_detected(self) -> None:
        ai = normalize_track([
            TraceEvent(
                id="a1", track="ai", kind="escalation_decision", title="esc", detail="",
                offset_seconds=100.0, milestone=True,
                meta={"milestones": ["cross_batch_pattern", "escalation_decision"]},
            ),
        ], None)
        kinds = {item["kind"] for item in detect_divergences([], ai)}
        self.assertIn("cross_batch_pattern", kinds)
        self.assertIn("escalation_decision", kinds)


class FreseniusCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = ComparisonService()
        cls.case = cls.service.case("fresenius")

    def test_replay_tracks_are_aligned_and_sorted(self) -> None:
        replay = self.case["replay"]
        self.assertEqual(replay["status"], "ok")
        clock = replay["clock"]
        self.assertFalse(clock["is_wall_clock"])
        traditional = replay["tracks"]["traditional"]
        ai = replay["tracks"]["ai"]
        self.assertGreater(len(traditional), 0)
        self.assertEqual(len(ai), 13)
        for track in (traditional, ai):
            offsets = [item["offset_seconds"] for item in track]
            self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(traditional[0]["offset_seconds"], 0.0)
        # Every AI event maps to a recorded chronology cutoff.
        timeline = {item["timestamp"] for item in traditional}
        self.assertTrue({item["timestamp"] for item in ai} <= timeline)

    def test_replay_never_cites_future_evidence(self) -> None:
        from benchmark.incident_demo.service import IncidentDemoService

        incident = IncidentDemoService()
        for event in self.case["replay"]["tracks"]["ai"]:
            if not event["milestone"]:
                continue
            cursor = event["meta"]["cursor"]
            visible = set(incident.visible_state(cursor)["evidence_by_id"].keys())
            self.assertTrue(set(event["evidence"]) <= visible, f"future evidence cited at cursor {cursor}")

    def test_replay_milestones_and_divergences(self) -> None:
        replay = self.case["replay"]
        milestones = replay["milestones"]
        self.assertEqual(milestones["cross_batch_pattern"]["ai"]["event_id"], "AI-EVT-006")
        cross_batch = next(item for item in replay["divergences"] if item["kind"] == "cross_batch_pattern")
        self.assertEqual(cross_batch["verdict"], "ai_only")
        self.assertIsNotNone(cross_batch["offset_seconds"])
        self.assertEqual(replay["cursor_state"]["6"]["triage_level"], "L3")

    def test_issue_chain_is_time_valid(self) -> None:
        chain = self.case["issue_chain"]
        self.assertEqual(chain["status"], "ok")
        self.assertEqual(chain["moment"]["cursor"], 6)
        cutoff = chain["moment"]["cutoff"]
        for card in chain["evidence_available"]["records"]:
            if card.get("timestamp"):
                self.assertLessEqual(parse_time(card["timestamp"]), parse_time(cutoff))
        available = chain["evidence_available"]
        self.assertLessEqual(len(available["records"]), available["preview_limit"])
        self.assertEqual(available["truncated"], available["count"] > available["preview_limit"])
        self.assertTrue(chain["competing_hypotheses"])
        self.assertTrue(chain["recommended_investigation"])

    def test_scorecard_classifications_and_deltas(self) -> None:
        scorecard = self.case["scorecard"]
        for row in scorecard["metrics"]:
            for key in ("traditional", "ai"):
                self.assertIn(row[key]["classification"], CLASSIFICATIONS)
            if row["delta"]:
                self.assertIsNotNone(row["traditional"]["value"])
                self.assertIsNotNone(row["ai"]["value"])
                self.assertIn(row["delta"]["verdict"], {"better", "worse", "equal"})
        headline = {row["id"] for row in scorecard["headline"]}
        self.assertEqual(headline, {"correct_work_per_human_hour"})
        diagnosis = next(row for row in scorecard["metrics"] if row["id"] == "time_to_diagnosis")
        self.assertAlmostEqual(diagnosis["traditional"]["value"], 14.0)
        self.assertAlmostEqual(diagnosis["ai"]["value"], 4.67)
        detection = next(row for row in scorecard["metrics"] if row["id"] == "incident_detection_recall")
        self.assertEqual(detection["traditional"]["display"], "1/5")

    def test_evidence_matrix_attribution(self) -> None:
        evidence = self.case["evidence"]
        statuses = set(evidence["statuses"])
        for row in evidence["rows"]:
            for key in ("traditional", "ai"):
                self.assertIn(row[key]["status"], statuses)
            self.assertIsInstance(row["pilot_cited"], bool)
            self.assertTrue(row["sources"])
            self.assertTrue(row["influence"])

    def test_differences_reference_real_events(self) -> None:
        event_ids = {
            item["id"]
            for track in self.case["replay"]["tracks"].values()
            for item in track
        }
        for entry in self.case["differences"]:
            self.assertTrue(entry["refs"])
            for ref in entry["refs"]:
                if ref["kind"] == "replay_event":
                    self.assertIn(ref["id"], event_ids)


class ChoCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = ComparisonService()
        cls.case = cls.service.case("cho")

    def test_scored_ai_side_values_stay_not_measured(self) -> None:
        scorecard = self.case["scorecard"]
        for row in scorecard["metrics"]:
            if row["id"] in {"ai_pilot_run", "model_cost"}:
                # Recorded pilot execution / usage rows are observed, not scored values.
                continue
            self.assertEqual(row["ai"]["classification"], "not_measured", row["id"])
            self.assertTrue(row["ai"]["detail"], row["id"])
            self.assertIsNone(row["delta"])
        for row in self.case["evidence"]["rows"]:
            self.assertEqual(row["ai"]["status"], "not_measured")

    def test_recorded_prime_pilot_is_wired(self) -> None:
        replay = self.case["replay"]
        ai_run = replay.get("ai_run")
        self.assertIsNotNone(ai_run, "run the pilot or restore runs/cho-comparison")
        comparison = json.loads(
            (REPOSITORY / "runs/cho-comparison/comparison.json").read_text(encoding="utf-8")
        )
        with_agent = comparison["with_agent"]
        self.assertTrue(ai_run["recorded"])
        self.assertEqual(ai_run["cited_evidence_count"], with_agent["cited_evidence_count"])
        self.assertEqual(ai_run["hypothesis_count"], with_agent["hypothesis_count"])
        self.assertAlmostEqual(ai_run["ingestion_seconds"], with_agent["ingestion"]["runtime_seconds"])
        self.assertAlmostEqual(ai_run["investigation_seconds"], with_agent["investigation_seconds"])
        pilot_row = next(row for row in self.case["scorecard"]["metrics"] if row["id"] == "ai_pilot_run")
        self.assertEqual(pilot_row["ai"]["classification"], "observed")
        self.assertEqual(pilot_row["traditional"]["classification"], "not_measured")
        model_row = next(row for row in self.case["scorecard"]["metrics"] if row["id"] == "model_cost")
        self.assertEqual(model_row["ai"]["classification"], "observed")
        self.assertEqual(model_row["ai"]["value"], with_agent["rollout_metrics"]["model_calls"])
        hypotheses = next(entry for entry in self.case["differences"] if entry["id"] == "DIFF-PILOT-HYPOTHESES")
        self.assertEqual(hypotheses["classification"], "observed")
        self.assertIn(str(int(with_agent["hypothesis_count"])), hypotheses["detail"])
        unavailable = self.case["presentation"]["unavailable_findings"]
        self.assertTrue(any("No scored AI-side benchmark values" in item for item in unavailable))
        self.assertTrue(any("Recorded AI OS pilot run" in item for item in self.case["presentation"]["modeled_findings"]))

    def test_recorded_values_match_artifacts(self) -> None:
        artifact = json.loads(
            (REPOSITORY / "results/cho/baseline_results.json").read_text(encoding="utf-8")
        )
        raw = artifact["tasks"][1]["metrics"]["full_series_within_tolerance_fraction"]
        reconstruction = next(
            row for row in self.case["scorecard"]["metrics"] if row["id"] == "full_series_reconstruction"
        )
        self.assertAlmostEqual(reconstruction["traditional"]["value"], round(raw, 6))
        total = next(row for row in self.case["scorecard"]["metrics"] if row["id"] == "machine_execution_total")
        self.assertEqual(total["traditional"]["display"], "269.823 s")
        alignment = next(row for row in self.case["scorecard"]["metrics"] if row["id"] == "time_zero_match")
        self.assertEqual(alignment["traditional"]["display"], "1300/1300")

    def test_replay_is_explicitly_process_only(self) -> None:
        replay = self.case["replay"]
        self.assertEqual(replay["status"], "process_only")
        self.assertEqual(replay["tracks"], {"traditional": [], "ai": []})
        self.assertIn("no synchronized two-workflow replay", replay["reason"].lower())
        if replay.get("ai_run"):
            self.assertIn("one-off", replay["reason"])
        else:
            self.assertIn("no AI OS run", replay["reason"])
        recorded = {entry["task"]: entry["seconds"] for entry in replay["execution"]["entries"]}
        self.assertAlmostEqual(recorded["CHO-01"], 105.808)
        self.assertIsNone(recorded["CHO-03"])
        for divergence in replay["divergences"]:
            self.assertEqual(divergence["verdict"], "descriptive")
            self.assertIsNotNone(divergence["normalized_delta"])

    def test_process_view_flags_constant_channels(self) -> None:
        process = self.case["replay"]["process"]
        self.assertEqual(len(process["experiments"]), 12)
        self.assertEqual(len(process["cultivations"]), 24)
        self.assertIn("flags_note", process)
        self.assertTrue(all("flags" in item for item in process["experiments"][0]["largest_differences"]))

    def test_cultivation_experiment_ids_match_experiment_rows(self) -> None:
        """The process view joins reactor pairs by experiment id, so both sides must use the same id."""
        process = self.case["replay"]["process"]
        experiment_ids = {row["id"] for row in process["experiments"]}
        for row in process["cultivations"]:
            self.assertIn(row["experiment"], experiment_ids, row)
        for experiment_id in experiment_ids:
            pair = [row for row in process["cultivations"] if row["experiment"] == experiment_id]
            self.assertGreaterEqual(len(pair), 2, experiment_id)

    def test_series_downsampling_and_errors(self) -> None:
        series = self.service.series("EXP001_batch_R01", ["pH"], max_points=50)
        self.assertEqual(series["cultivation"], "EXP001_batch_R01")
        points = series["variables"]["pH"]["points"]
        self.assertLessEqual(len(points), 51)
        self.assertEqual(series["role"], "publisher-aligned reference (evaluation-only)")
        with self.assertRaises(KeyError):
            self.service.series("NOT-A-CULTIVATION", ["pH"])

    def test_issue_chain_reports_missing_hypotheses(self) -> None:
        chain = self.case["issue_chain"]
        self.assertEqual(chain["status"], "partial")
        self.assertEqual(chain["observation"]["hypotheses"]["status"], "not_measured")
        self.assertTrue(self.case["presentation"]["unavailable_findings"])
        modeled = self.case["presentation"]["modeled_findings"]
        if self.case["replay"].get("ai_run"):
            self.assertTrue(modeled)  # recorded pilot findings, clearly labeled unscored
        else:
            self.assertEqual(modeled, [])


class MissingArtifactTests(unittest.TestCase):
    def test_missing_artifacts_degrade_to_not_measured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            placeholder = Path(temporary)
            artifacts = {
                key: placeholder / f"{key}.missing.json"
                for key in default_artifacts(placeholder)
            }
            service = ComparisonService(placeholder, store=ArtifactStore(placeholder, artifacts=artifacts))
            for case_id in CASE_ORDER:
                payload = service.case(case_id)
                for section in payload:
                    if section == "id":
                        continue
                    self.assertIsNotNone(payload[section], f"{case_id}.{section}")
            fresenius = service.case("fresenius")
            self.assertEqual(fresenius["replay"]["status"], "not_measured")
            self.assertEqual(fresenius["issue_chain"]["status"], "not_measured")
            self.assertIn("incomplete", fresenius["scorecard"]["conclusion"].lower())
            cho = service.case("cho")
            self.assertIn("incomplete", cho["scorecard"]["conclusion"].lower())
            self.assertIsNone(cho["replay"]["clock"]["end"])
            self.assertIsNone(cho["replay"]["ai_run"])
            self.assertIn("no AI OS run", cho["replay"]["reason"])
            self.assertTrue(all("No AI OS run" in row["ai"]["detail"]
                                for row in cho["evidence"]["rows"]))
            for row in cho["scorecard"]["metrics"]:
                if row["id"] == "ai_pilot_run":
                    continue  # only present when a pilot artifact exists
                self.assertEqual(row["ai"]["classification"], "not_measured", row["id"])
                self.assertIsNone(row["delta"])


class ReportTests(unittest.TestCase):
    """The static benchmark report must stay self-contained, complete, and current."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = ComparisonService()
        cls.html = build_report(cls.service)

    def test_report_is_self_contained(self) -> None:
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertIn("<style>", self.html)
        self.assertNotIn("<script", self.html)
        self.assertNotIn("fonts.googleapis", self.html)
        self.assertNotIn('rel="stylesheet"', self.html)
        self.assertNotIn('src="', self.html)

    def test_report_covers_both_cases_classifications_and_recorded_values(self) -> None:
        for case_id in CASE_ORDER:
            self.assertIn(f'id="{case_id}"', self.html)
        for label in ("Verified", "Observed", "Modeled", "Predicted", "Not measured"):
            self.assertIn(label, self.html)
        # Recorded values surface unchanged; nothing here is recomputed.
        self.assertIn("99.905%", self.html)      # CHO trajectory agreement
        self.assertIn("1300/1300", self.html)    # CHO time-zero matches
        self.assertIn("1/5", self.html)          # Fresenius detection recall baseline
        self.assertIn("AI-EVT-006", self.html)   # cross-batch milestone event
        self.assertIn("python -m benchmark.case_comparison.report", self.html)

    def test_report_marks_cho_ai_run_state_and_disclaimers(self) -> None:
        cho_replay = self.service.case("cho")["replay"]
        if cho_replay.get("ai_run"):
            self.assertIn("AI OS run: recorded pilot", self.html)
            self.assertIn("Recorded AI OS pilot run (unscored)", self.html)
            self.assertIn("No scored AI-side benchmark values", self.html)
        else:
            self.assertIn("AI OS run: not recorded", self.html)
            self.assertIn("No AI OS run", self.html)
        self.assertIn("does not establish", self.html)  # Fresenius retrospective disclaimer
        self.assertIn("no causal claim", self.html)

    def test_report_generation_is_deterministic(self) -> None:
        self.assertEqual(build_report(self.service), self.html)

    def test_report_degrades_with_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            placeholder = Path(temporary)
            artifacts = {
                key: placeholder / f"{key}.missing.json"
                for key in default_artifacts(placeholder)
            }
            service = ComparisonService(placeholder, store=ArtifactStore(placeholder, artifacts=artifacts))
            rendered = build_report(service)
        self.assertIn("Not measured", rendered)
        self.assertIn('id="cho"', rendered)
        self.assertIn("AI OS run: not recorded", rendered)
        self.assertNotIn("Recorded AI OS pilot run (unscored)", rendered)
        self.assertNotIn("Traceback", rendered)

    def test_write_report_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "report.html"
            written = write_report(target)
            self.assertEqual(written, target)
            self.assertTrue(target.read_text(encoding="utf-8").startswith("<!doctype html>"))
            cli_target = Path(temporary) / "cli.html"
            self.assertEqual(report_main(["--output", str(cli_target)]), 0)
            self.assertTrue(cli_target.is_file())

    def test_committed_static_report_is_current(self) -> None:
        committed = Path(__file__).resolve().parents[1] / "benchmark/application/static/benchmark-report.html"
        self.assertTrue(committed.is_file(),
                        "regenerate with: python -m benchmark.case_comparison.report")
        self.assertEqual(committed.read_text(encoding="utf-8"), self.html)


def test_case_comparison_api(tmp_path, monkeypatch) -> None:
    import pytest

    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):  # starlette 1.x needs httpx2 (or httpx)
        pytest.skip("fastapi TestClient requires httpx2 (or httpx)")

    from benchmark.application.api import create_app
    from benchmark.application.bootstrap import build_demo_services

    monkeypatch.delenv("BIODEMO_MANUFACTURING_STORE", raising=False)
    monkeypatch.delenv("BIODEMO_MANUFACTURING_SCOPE", raising=False)
    client = TestClient(create_app(build_demo_services(tmp_path / "evidence")))

    index = client.get("/api/case-comparison")
    assert index.status_code == 200
    assert index.json()["order"] == ["fresenius", "cho"]

    fresenius = client.get("/api/case-comparison/fresenius")
    assert fresenius.status_code == 200
    assert fresenius.json()["replay"]["status"] == "ok"

    cho = client.get("/api/case-comparison/cho")
    assert cho.status_code == 200
    assert cho.json()["replay"]["status"] == "process_only"

    series = client.get(
        "/api/case-comparison/cho/series",
        params={"cultivation": "EXP001_batch_R01", "variables": "pH", "max_points": 40},
    )
    assert series.status_code == 200
    assert series.json()["variables"]["pH"]["points"]

    missing = client.get("/api/case-comparison/cho/series", params={"cultivation": "NOPE"})
    assert missing.status_code == 404

    unknown = client.get("/api/case-comparison/does-not-exist")
    assert unknown.status_code == 404

    summary = client.get("/comparison")
    assert summary.status_code == 200
    assert "text/html" in summary.headers["content-type"]
    assert "Lotic · Demo" in summary.text
    assert 'href="/benchmark"' in summary.text
    assert "/comparison/detail" not in summary.text

    detail = client.get("/comparison/detail")
    assert detail.status_code == 200
    assert detail.text == summary.text

    home = client.get("/")
    assert home.text == summary.text
    assert client.get("/landing", follow_redirects=False).headers["location"] == "/"
    assert client.get("/platform", follow_redirects=False).headers["location"] == "/"
    demo = client.get("/api/demo")
    assert demo.status_code == 200
    assert [case["id"] for case in demo.json()["cases"]] == ["fresenius", "cho"]
    assert len(demo.json()["cases"][0]["stages"]) == 6
    assert len(demo.json()["cases"][1]["stages"]) == 5

    report = client.get("/benchmark-report")
    assert report.status_code == 200
    assert "text/html" in report.headers["content-type"]
    assert "Benchmark report" in report.text
    assert client.get("/benchmark").text == report.text


if __name__ == "__main__":
    unittest.main()
