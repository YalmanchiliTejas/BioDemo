from benchmark.case_comparison import ComparisonService
from benchmark.case_comparison.demo import build_demo
from benchmark.case_comparison.sources import ArtifactStore, default_artifacts


def test_fresenius_demo_uses_time_valid_source_events():
    case = ComparisonService().case("fresenius")
    demo = build_demo(case)
    events = {row["id"]: row for track in case["replay"]["tracks"].values() for row in track}
    assert len(demo["stages"]) == 6
    times = [stage["time"] for stage in demo["stages"]]
    assert times == sorted(times)
    for stage in demo["stages"]:
        for side in ("without", "with"):
            for identifier in stage[side]["source_ids"]:
                assert events[identifier]["timestamp"] <= stage["time"]
    assert demo["stages"][1]["with"]["source_ids"] == ["AI-EVT-006"]
    assert "diverge here" in demo["stages"][1]["divergence"]
    assert demo["improvements"] == []
    assert demo["productivity"]["sides"]["ai"]["value"] is None
    fork = demo["stages"][1]["comparison"]
    assert [row["id"] for row in fork["evidence"]] == ["LAB-0225", "LAB-0255"]
    assert [row["value"] for row in fork["evidence"]] == [1.23, 1.48]
    assert fork["with"]["scope"] == "BATCH-075 + BATCH-084"
    assert "human approval" in fork["with"]["decision"]
    assert "unconfirmed" in fork["with"]["decision"]
    for stage in demo["stages"]:
        for record in stage["comparison"]["evidence"]:
            assert record["time"] <= stage["time"]
        for action in stage["comparison"]["without"]["actions"]:
            assert action["time"] <= stage["time"]
    assert "not evidence of agent productivity" in demo["measurement_note"]


def test_cho_storyboard_does_not_invent_recorded_os_timing_or_gains():
    demo = build_demo(ComparisonService().case("cho"))
    assert demo["improvements"] == []
    assert "Illustrative workflow" in demo["badge"]
    for stage in demo["stages"]:
        assert stage["time"] is None
        assert stage["with"]["time"] is None
        assert stage["with"]["source_ids"] == []
        assert stage["with"]["kind"] == "Illustrative OS workflow"
        assert "awaiting" in stage["comparison"]["with"]["decision"]
    assert "not measured gains" in demo["improvement_note"]


def test_missing_fresenius_artifacts_do_not_create_timeline(tmp_path):
    artifacts = {key: tmp_path / f"{key}.json" for key in default_artifacts(tmp_path)}
    service = ComparisonService(tmp_path, store=ArtifactStore(tmp_path, artifacts))
    demo = build_demo(service.case("fresenius"))
    assert demo["stages"] == []
    assert all(row["ai"]["value"] is None for row in demo["improvements"])


def test_benchmark_numbers_follow_source_artifacts_and_missing_stays_missing(tmp_path):
    import json

    store = ArtifactStore(tmp_path)
    values = {
        "campaign_representative_traditional": {"msat_process_engineering": {"mean_engineer_hours_per_investigation": 17.25}},
        "campaign_representative_assisted": {"msat_process_engineering": {"mean_engineer_hours_per_investigation": 4.1}},
        "fresenius_pilot": {"without_agent": {"human_minutes": 73, "extraction_seconds": 2.5},
                            "with_agent": {"human_minutes_including_review_and_correction": 18}},
    }
    for key, value in values.items():
        path = store.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    rows = {row["id"]: row for row in ComparisonService(tmp_path, store=store).section("fresenius", "scorecard")["metrics"]}
    assert rows["engineer_hours_per_investigation"]["traditional"]["display"] == "17.25 h"
    assert rows["engineer_hours_per_investigation"]["ai"]["display"] == "4.10 h"
    assert rows["human_review_minutes"]["ai"]["value"] == 18
    assert rows["human_review_minutes"]["delta"] is None
    assert rows["systems_accessed"]["ai"]["display"] == "Not measured"
    assert rows["machine_execution_time"]["traditional"]["value"] == 2.5


def test_served_demo_story_contains_current_evidence_and_no_savings_cards():
    import json
    from pathlib import Path

    service = ComparisonService()
    story = json.loads((Path(__file__).resolve().parents[1] / "benchmark/application/static/demo-story.json").read_text())
    assert story == {"cases": [build_demo(service.case(case)) for case in ("fresenius", "cho")]}
    assert all(case["improvements"] == [] for case in story["cases"])
