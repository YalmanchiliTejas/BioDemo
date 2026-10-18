from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.prime_runtime.compare import run_comparison


def test_pilot_compare_runs_both_modes_without_inventing_savings(tmp_path: Path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    (package / "lab.csv").write_text("batch_id,available_at,status\nB1,2024-01-02T00:00:00Z,action\n")
    seen = []

    class FakePrime:
        def run(self, **kwargs):
            seen.append(kwargs)
            return {"assessment": "Review the action status", "severity": "HIGH",
                    "evidence_ids": ["source-1"], "causal_hypotheses": [],
                    "pending_evidence_requests": [],
                    "rollout_metrics": {"tool_calls": 2, "inference_cost_usd": 0.02}}

    monkeypatch.setattr("src.prime_runtime.compare.PrimeManufacturingHarness.from_env",
                        lambda **kwargs: FakePrime())
    output = tmp_path / "out"
    phases = []
    result = run_comparison(package=package, objective="Investigate status", output=output,
                            as_of="2024-02-01T00:00:00Z", progress=phases.append)
    assert phases == ["Reading source records", "Preparing the agent evidence store",
                      "Agent investigating evidence", "Saving the investigation report"]
    assert result["without_agent"]["parsed_files_or_sheets"] == 1
    assert result["with_agent"]["ingestion"]["observations"] == 3
    assert result["with_agent"]["cited_evidence_count"] == 1
    assert result["measured_value"]["net_value_usd"] is None
    assert seen[0]["as_of"] == "2024-02-01T00:00:00Z"
    assert json.loads((output / "comparison.json").read_text())["claim_status"].startswith("pilot_")


def test_pilot_compare_calculates_only_supplied_human_value(tmp_path: Path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    (package / "lab.csv").write_text("batch_id,status\nB1,action\n")

    class FakePrime:
        def run(self, **kwargs):
            return {"assessment": "Review", "rollout_metrics": {"inference_cost_usd": 0.01}}

    monkeypatch.setattr("src.prime_runtime.compare.PrimeManufacturingHarness.from_env",
                        lambda **kwargs: FakePrime())
    result = run_comparison(package=package, objective="Investigate", output=tmp_path / "out",
                            baseline_human_minutes=90, assisted_human_minutes=30,
                            loaded_hourly_rate_usd=120, total_agent_cost_usd=5)
    assert result["measured_value"]["human_minutes_saved"] == 60
    assert result["measured_value"]["net_value_usd"] == 115
    with pytest.raises(ValueError, match="provide both"):
        run_comparison(package=package, objective="Investigate", output=tmp_path / "other",
                       baseline_human_minutes=90)
