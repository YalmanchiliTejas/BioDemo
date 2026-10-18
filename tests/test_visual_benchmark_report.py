import json

from benchmark.case_comparison.visual_report import load_runs, run_charts


def recorded_run(run_id="abc123", **changes):
    return {
        "run_id": run_id, "version": "manufacturing-evaluation-v2",
        "benchmark_id": "cho", "case_id": "CHO-04", "condition": "raw",
        "mode": "full_rlm", "status": "completed", "started_at": "2026-10-17",
        "wall_clock_seconds": 600,
        "objective_scores": {"data_preparation": {
            "field_accuracy": {"value": 1}, "field_coverage": {"value": 0.31},
        }}, **changes,
    }


def test_perfect_emitted_accuracy_does_not_hide_missing_fields_or_failed_attempts():
    page = run_charts([recorded_run(), recorded_run("failed", status="failed", objective_scores=None)])
    assert "100.0%" in page
    assert "31.0%" in page
    assert "1 completed · 1 failed" in page
    assert "CHO-04 · failed" in page
    assert "Machine wall time, not human effort" in page


def test_runs_refresh_without_summary_and_tolerate_partial_writes(tmp_path):
    root = tmp_path / "results/evaluation"
    for name, data in (("first", recorded_run()), ("foreign", recorded_run(benchmark_id="fresenius"))):
        path = root / name / "run.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(data))
    partial = root / "partial/run.json"
    partial.parent.mkdir()
    partial.write_text('{"status":')
    assert [r["run_id"] for r in load_runs(tmp_path)] == ["abc123"]
    partial.write_text(json.dumps(recorded_run("second")))
    assert len(load_runs(tmp_path)) == 2
    assert not (root / "summary.json").exists()


def test_conditions_and_methods_are_not_pooled_into_an_accuracy_score():
    page = run_charts([recorded_run(), recorded_run("updated", condition="updated"),
                       recorded_run("baseline", mode="conventional")])
    assert "CHO-04 / raw / Manufacturing OS" in page
    assert "CHO-04 / updated / Manufacturing OS" in page
    assert "CHO-04 / raw / Conventional" in page
    assert page.count("1 scored outputs") == 3
