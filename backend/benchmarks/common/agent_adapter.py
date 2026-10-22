from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class InvestigationInput:
    input_package: Path
    objective: str
    as_of: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)


class InvestigationAgent(Protocol):
    def run_investigation(self, request: InvestigationInput) -> dict[str, Any]: ...


def run_investigation(input_package: str | Path, objective: str,
                      as_of: str | None = None,
                      configuration: dict[str, Any] | None = None) -> dict[str, Any]:
    """Common interface. The input path must be a staged, allowlisted source package."""
    from benchmarks.baselines.conventional_extraction import ConventionalExtraction
    request = InvestigationInput(Path(input_package).resolve(), objective, as_of, configuration or {})
    if not request.input_package.is_dir():
        raise ValueError("input_package must be a directory")
    mode = request.configuration.get("mode", "conventional")
    if request.configuration.get('investigation_baselines') and mode in {'conventional','retrieval_llm'}:
        from benchmarks.baselines.investigation import run_automated
        return run_automated(request,single_pass=mode=='retrieval_llm')
    if mode == "conventional":
        return ConventionalExtraction().run_investigation(request)
    if mode == "retrieval_llm":
        from benchmarks.baselines.retrieval_llm import RetrievalLLM
        return RetrievalLLM().run_investigation(request)
    if mode == "full_rlm":
        from benchmarks.common.full_agent_adapter import FullManufacturingOS
        return FullManufacturingOS().run_investigation(request)
    raise ValueError(f"unknown mode: {mode}")
