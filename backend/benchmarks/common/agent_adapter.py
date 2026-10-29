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
    if mode in {'keyword_rules', 'linked_rules'}:
        from benchmarks.common.directory_discovery import run_directory
        return run_directory(request)
    if mode == 'directory_rag':
        import os
        if not os.environ.get('OPENAI_API_KEY'):
            raise RuntimeError('directory_rag requires OPENAI_API_KEY; no model call executed')
        from dataclasses import replace
        from benchmarks.common.directory_discovery import run_directory
        from benchmarks.baselines.retrieval_llm import RetrievalLLM
        retrieved = run_directory(replace(request, configuration={**request.configuration, 'mode': 'keyword_rules'}))
        retrieved['files'] = []
        retrieved['records'] = [{'record_id': c['evidence_id'], 'source': c['source']['path'],
                                 'values': {'text': c['text'], 'source_ref': c['source']}}
                                for c in retrieved['citations']]
        result = RetrievalLLM().run_investigation(replace(request, configuration={**request.configuration, 'preextracted': retrieved}))
        selected = set(result.get('analysis', {}).get('evidence_ids', []))
        if selected - {c['evidence_id'] for c in retrieved['citations']}:
            raise ValueError('RAG report cited inaccessible evidence')
        result['citations'] = [c for c in retrieved['citations'] if c['evidence_id'] in selected]
        result['usage']['api_cost_usd'] = None
        return result
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
