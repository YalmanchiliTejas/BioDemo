from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from collections import defaultdict
from typing import Any
from pathlib import Path

from benchmarks.common.agent_adapter import InvestigationInput
from .conventional_extraction import ConventionalExtraction


class RetrievalLLM:
    """One bounded, single-pass analysis over the same extracted package."""

    def run_investigation(self, request: InvestigationInput) -> dict[str, Any]:
        started = time.monotonic()
        extracted = request.configuration.get("preextracted") or ConventionalExtraction().run_investigation(request)
        extracted["objective"] = request.objective
        extracted["as_of"] = request.as_of
        key = os.environ.get("OPENAI_API_KEY")
        query_terms = set(request.objective.lower().split())
        trigger_ids = set(re.findall(r"\b[A-Z]+-\d+\b", request.objective))
        source_summaries = [
            {"record_id": f"{file['path']}#{file['sheet']}", "source": file["path"],
             "sheet": file["sheet"], "values": {"records": file["records"],
                 "columns": file["columns"], "numeric_summary": file.get("numeric_summary", {})}}
            for file in extracted["files"] if file["type"] == "xlsx" and file.get("numeric_summary")
        ]
        def score(row: dict) -> int:
            content = json.dumps(row["values"]).lower()
            return 20 * (row.get("record_id") in trigger_ids) + sum(term in content for term in query_terms) + 5 * sum(token in content for token in
                ('"status": "action"', '"status": "out_of_specification"', '"severity": "high"', '"severity": "critical"'))
        ranked = sorted(source_summaries or extracted["records"], key=score, reverse=True)
        limit = int(request.configuration.get("retrieval_max_records", 80))
        if source_summaries:
            by_file: dict[str, list[dict]] = defaultdict(list)
            for row in ranked:
                by_file[row["source"]].append(row)
            selected = []
            while len(selected) < limit and any(by_file.values()):
                for source in sorted(by_file):
                    if by_file[source] and len(selected) < limit:
                        selected.append(by_file[source].pop(0))
        else:
            selected = ranked[:limit]
        extracted["retrieved_record_ids"] = sorted({row["record_id"] for row in selected if row.get("record_id")})
        if source_summaries:
            extracted["source_summary_count"] = len(source_summaries)
        if not key:
            from src.rlm.provider import CodexRLMProvider
            schema = {"type": "object", "additionalProperties": False,
                      "properties": {"assessment": {"type": "string"},
                                     "evidence_ids": {"type": "array", "items": {"type": "string"}},
                                     "hypotheses": {"type": "array", "items": {"type": "string"}},
                                     "uncertainties": {"type": "array", "items": {"type": "string"}},
                                     "human_review_actions": {"type": "array", "items": {"type": "string"}}},
                      "required": ["assessment", "evidence_ids", "hypotheses", "uncertainties", "human_review_actions"]}
            provider = CodexRLMProvider(Path(__file__).resolve().parents[2])
            analysis = provider._complete("single_pass_raw_source_baseline",
                                          {"objective": request.objective, "as_of": request.as_of,
                                           "evidence": selected}, schema)
            extracted["mode"] = "retrieval_llm"
            extracted["analysis"] = analysis
            extracted["usage"].update(provider.snapshot())
            extracted["usage"]["retrieved_records"] = len(selected)
            extracted["usage"]["inference_cost_usd"] = None
            extracted["usage"]["runtime_seconds"] = round(time.monotonic()-started, 3)
            return extracted
        body = {"model": request.configuration.get("model", "gpt-6-luna"),
                "input": [{"role": "system", "content": "Investigate only supplied evidence. Cite exact source paths and row/page. Separate observation, hypothesis and uncertainty. Recommend human review for regulated decisions. Return JSON."},
                          {"role": "user", "content": json.dumps({"objective": request.objective,
                                                                   "as_of": request.as_of,
                                                                   "evidence": selected}, default=str)}]}
        http = urllib.request.Request("https://api.openai.com/v1/responses",
                                      data=json.dumps(body).encode(),
                                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(http, timeout=120) as response:
            result = json.load(response)
        extracted["mode"] = "retrieval_llm"
        extracted["analysis"] = "\n".join(part.get("text", "") for item in result.get("output", [])
                                            for part in item.get("content", []) if part.get("type") == "output_text")
        extracted["usage"].update(result.get("usage", {}))
        extracted["usage"]["model_calls"] = 1
        extracted["usage"]["inference_cost_usd"] = None
        extracted["usage"]["runtime_seconds"] = round(time.monotonic()-started, 3)
        return extracted
