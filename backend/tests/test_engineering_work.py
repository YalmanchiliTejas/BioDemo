import copy
import math

import pytest

from benchmarks.common.engineering_work import GATES, PHASES, score, template
from benchmark.case_comparison.service import ComparisonService


def completed_ledger():
    ledger = template("cho")
    for run in ledger["runs"]:
        run.update(package_sha256="a" * 64, task_spec_sha256="b" * 64,
                   output_ref="outputs/investigation.json", effort_complete=True)
        for phase in PHASES:
            run["human_effort"][phase] = {"person_minutes": 12, "manual_steps": 2}
        run["review"] = {"reviewer": "domain-reviewer", "evidence_ref": "reviews/1.json",
                         "gates": {gate: True for gate in GATES}}
    return ledger


def test_template_does_not_invent_measurements():
    result = score(template("fresenius"))
    assert all(e["status"] == "not_measured" for e in result["experiments"])
    assert result["primary"]["sides"]["ai"]["value"] is None


def test_failed_work_counts_in_denominator_and_cannot_be_hidden():
    ledger = completed_ledger()
    failed = copy.deepcopy(ledger["runs"][1])
    failed.update(run_id="A-ai-2", pair_id="A-2")
    failed["review"]["gates"]["evidence_supported"] = False
    ledger["runs"].append(failed)
    primary = score(ledger)["primary"]
    assert primary["sides"]["ai"]["value"] == 0.5
    assert primary["sides"]["ai"]["correctly_completed"] == 1
    assert primary["sides"]["ai"]["manual_steps"] == 20
    assert primary["sides"]["ai"]["gate_failures"]["evidence_supported"] == 1
    assert not primary["paired"]  # unmatched extra attempt prevents a delta
    failed["review"]["gates"]["complete"] = None
    assert score(ledger)["primary"]["sides"]["ai"]["value"] is None


@pytest.mark.parametrize("bad", [None, -1, math.inf, math.nan, True])
def test_missing_or_invalid_effort_withholds_rate(bad):
    ledger = completed_ledger()
    ledger["runs"][1]["human_effort"]["verification"]["person_minutes"] = bad
    assert score(ledger)["primary"]["sides"]["ai"]["value"] is None


def test_zero_time_is_undefined_but_reviewed_failure_is_zero():
    ledger = completed_ledger()
    ledger["runs"][1]["review"]["gates"]["escalation_correct"] = False
    assert score(ledger)["primary"]["sides"]["ai"]["value"] == 0
    for phase in PHASES:
        ledger["runs"][1]["human_effort"][phase]["person_minutes"] = 0
    assert score(ledger)["primary"]["sides"]["ai"]["value"] is None


def test_pairing_requires_identical_packages_and_specs():
    ledger = completed_ledger()
    assert score(ledger)["primary"]["paired"]
    ledger["runs"][1]["package_sha256"] = "c" * 64
    assert not score(ledger)["primary"]["paired"]
    ledger["runs"][1]["package_sha256"] = "a" * 64
    ledger["runs"][1]["task_spec_sha256"] = "c" * 64
    assert not score(ledger)["primary"]["paired"]


def test_duplicate_assignment_rejected():
    ledger = completed_ledger()
    duplicate = copy.deepcopy(ledger["runs"][0])
    duplicate["run_id"] = "different-id"
    ledger["runs"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate workflow assignment"):
        score(ledger)


def test_comparison_reads_raw_ledger_and_only_pairs_matching_work(tmp_path):
    import json

    target = tmp_path / "results/cho/engineering_work.json"
    target.parent.mkdir(parents=True)
    ledger = completed_ledger()
    target.write_text(json.dumps(ledger))
    card = ComparisonService(tmp_path).section("cho", "scorecard")
    assert card["headline"][0]["ai"]["value"] == 1
    assert card["headline"][0]["delta"]["verdict"] == "equal"
    ledger["runs"][1]["task_spec_sha256"] = "c" * 64
    target.write_text(json.dumps(ledger))
    assert ComparisonService(tmp_path).section("cho", "scorecard")["headline"][0]["delta"] is None


def test_existing_artifacts_do_not_establish_human_productivity():
    service = ComparisonService()
    for benchmark in ("fresenius", "cho"):
        headline = service.section(benchmark, "scorecard")["headline"]
        assert len(headline) == 1
        assert headline[0]["id"] == "correct_work_per_human_hour"
        assert headline[0]["traditional"]["value"] is None
        assert headline[0]["ai"]["value"] is None


def test_report_and_summary_expose_new_experiments():
    from benchmark.case_comparison.report import build_report

    html = build_report()
    for label in ("Engineering work experiments", "Total effort", "Unfamiliar data", "Trustworthiness"):
        assert label in html
    assert "failed attempts remain in total effort" in html
    assert "not an untouched holdout" in html
