from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from collections import defaultdict
from typing import Any

from benchmarks.common.agent_adapter import InvestigationInput
from .conventional_extraction import ConventionalExtraction

SYSTEM_PROMPT = (
    "Investigate only supplied evidence. Cite exact source paths and row/page. "
    "Separate observation, hypothesis and uncertainty. Recommend human review "
    "for regulated decisions. Return JSON with assessment, evidence_ids, citations "
    "(evidence_id, source path, sheet and row for spreadsheets, row for CSVs, page for PDFs), "
    "hypotheses (statement, supporting_evidence_ids, contradicting_evidence_ids, discriminating_checks, status=hypothesis), "
    "scope (batch_ids), triage, evidence_requests, follow_up_actions and open_questions. "
    "Do not assert verified causation or execute regulated actions."
)


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
        ranked = sorted(source_summaries + extracted["records"], key=score, reverse=True)
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
        extracted["ranked_record_ids"] = list(dict.fromkeys(row["record_id"] for row in selected if row.get("record_id")))
        if source_summaries:
            extracted["source_summary_count"] = len(source_summaries)
        if not key:
            raise RuntimeError("retrieval_llm baseline requires OPENAI_API_KEY")
        body = {"model": request.configuration.get("model", "gpt-6-luna"),
                "input": [{"role": "system", "content": SYSTEM_PROMPT},
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
        raw_analysis = extracted["analysis"].strip()
        if raw_analysis.startswith("```"):
            raw_analysis = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_analysis)
        extracted["analysis"] = json.loads(raw_analysis)
        if not isinstance(extracted["analysis"], dict):
            raise ValueError("single-pass baseline returned no structured investigation")
        extracted["usage"].update(result.get("usage", {}))
        extracted["usage"]["model_calls"] = 1
        extracted["usage"]["inference_cost_usd"] = None
        extracted["usage"]["runtime_seconds"] = round(time.monotonic()-started, 3)
        return extracted
