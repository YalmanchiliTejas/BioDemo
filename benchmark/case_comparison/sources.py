"""Artifact loading for the comparison dashboard.

Every value shown in the comparison dashboard is read from a file listed here.
When an artifact is absent the loaders return ``None`` and the dashboard shows
"Not measured" with the reason instead of estimating a value.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[2]


def default_artifacts(repository: Path = REPOSITORY) -> dict[str, Path]:
    return {
        # Fresenius: modeled ablation benchmark over the frozen dataset
        "fresenius_simulation": repository / "benchmark/pharma_simulation/artifacts/benchmark_results.json",
        "fresenius_simulation_fingerprint": repository / "benchmark/pharma_simulation/artifacts/pharma_simulation.json",
        # Fresenius: paired 30-run traditional vs agent-assisted campaign projection
        "campaign_comparison": repository / "runs/comparison/comparison.json",
        "campaign_representative_traditional": repository / "runs/comparison/runs/20250939/traditional/summary.json",
        "campaign_representative_assisted": repository / "runs/comparison/runs/20250939/agent_assisted/summary.json",
        # Fresenius: recorded baseline runs over the raw source package
        "fresenius_parser": repository / "results/fresenius/baseline_results.json",
        "fresenius_retrieval": repository / "results/fresenius/retrieval_llm_results.json",
        "fresenius_reliability": repository / "results/fresenius/reliability_first_signal.json",
        # Fresenius: recorded Prime SDK pilot comparison over the same package
        "fresenius_pilot": repository / "runs/my-comparison/comparison.json",
        "fresenius_pilot_report": repository / "runs/my-comparison/agent_report.json",
        "fresenius_pilot_cited": repository / "runs/my-comparison/cited_evidence.json",
        # Fresenius: frozen case chronology and ground truth
        "fresenius_replay": repository / "benchmark/incident_demo/data/replay_ui.json",
        "fresenius_agent_data": repository / "benchmark/incident_demo/data/agent_data.json",
        "fresenius_ground_truth": repository / "benchmark/incident_demo/data/benchmark_ground_truth.json",
        "fresenius_public_truth": repository / "benchmark/incident_demo/data/public_ground_truth.json",
        # CHO: recorded conventional pipeline run and verification reports
        "cho_parser": repository / "results/cho/baseline_results.json",
        # CHO: recorded Prime pilot run over the same workbook package
        "cho_pilot": repository / "runs/cho-comparison/comparison.json",
        "cho_pilot_report": repository / "runs/cho-comparison/agent_report.json",
        "cho_pilot_cited": repository / "runs/cho-comparison/cited_evidence.json",
        "cho_full_series": repository / "benchmarks/cho/reports/full_series_comparison.json",
        "cho_perturbation": repository / "benchmarks/cho/reports/perturbation_validation.json",
        "cho_inventory": repository / "benchmarks/cho/data_inventory.json",
        "cho_objectives": repository / "benchmarks/cho/reference/objective_summaries.json",
        "cho_process_comparison": repository / "benchmarks/cho/reference/process_comparison.json",
        "cho_normalization_manifest": repository / "benchmarks/cho/tasks/normalized/manifest.json",
        "cho_config": repository / "benchmarks/configs/cho.json",
    }


def read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class ArtifactStore:
    """Loads comparison artifacts with graceful missing-data behavior."""

    def __init__(self, repository: Path = REPOSITORY, artifacts: dict[str, Path] | None = None) -> None:
        self.repository = Path(repository)
        self.artifacts = artifacts or default_artifacts(self.repository)
        self._cache: dict[str, Any] = {}
        self._missing: set[str] = set()

    def path(self, key: str) -> Path | None:
        return self.artifacts.get(key)

    def relative(self, key: str) -> str:
        path = self.artifacts.get(key)
        if path is None:
            return key
        try:
            return str(path.relative_to(self.repository))
        except ValueError:
            return str(path)

    def has(self, key: str) -> bool:
        path = self.artifacts.get(key)
        return bool(path and path.is_file())

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            return self._cache[key]
        path = self.artifacts.get(key)
        if path is None or not path.is_file():
            self._missing.add(key)
            return None
        value = read_json(path)
        self._cache[key] = value
        return value

    def digest(self, key: str, *, length: int = 12) -> str | None:
        path = self.artifacts.get(key)
        if path is None or not path.is_file():
            return None
        if path.suffix.lower() in {".json", ".jsonl"} and path.stat().st_size > 8 * 1024 * 1024:
            return None  # never hash large raw datasets on the request path
        try:
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()[:length]
        except OSError:
            return None

    def source(self, key: str, fields: list[str] | None = None) -> dict[str, Any]:
        """Describe where a value came from; used for metric traceability."""
        record: dict[str, Any] = {
            "artifact": key,
            "path": self.relative(key),
            "available": self.has(key),
        }
        if fields:
            record["fields"] = fields
        return record

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(sorted(self._missing))
