from __future__ import annotations

import json
import tempfile
from itertools import combinations
from pathlib import Path

from benchmarks.common.isolated_runner import run_isolated
from benchmarks.common.leakage_audit import print_audit
from benchmarks.fresenius.build_multimodal_package import build_package
from benchmarks.fresenius.build_tasks import build_tasks


ROOT = Path(__file__).resolve().parents[2]


def run_first_signal_repeats(runs: int = 3) -> dict:
    task = next(item for item in build_tasks() if item["id"] == "FRE-02")
    with tempfile.TemporaryDirectory(prefix="fresenius-reliability-") as temporary:
        staged = Path(temporary) / "agent_input"
        build_package(staged, as_of=task["as_of"],
                      map_output=ROOT / "benchmarks/fresenius/ground_truth/replay_maps/FRE-02.json")
        if not print_audit(staged, as_of=task["as_of"]):
            raise RuntimeError("leakage audit failed")
        outputs = [run_isolated(staged, task["objective"], task["as_of"], {"mode": "retrieval_llm"})
                   for _ in range(runs)]
    citations = [set(output["analysis"].get("evidence_ids", [])) for output in outputs]
    similarities = [len(a & b)/len(a | b) if a | b else 1.0 for a,b in combinations(citations, 2)]
    result = {"task": task, "runs": runs, "citation_sets": [sorted(ids) for ids in citations],
              "pairwise_citation_jaccard": similarities,
              "trigger_cited_each_run": [task["trigger_record_id"] in ids for ids in citations],
              "hypothesis_counts": [len(output["analysis"].get("hypotheses", [])) for output in outputs],
              "uncertainty_counts": [len(output["analysis"].get("uncertainties", [])) for output in outputs],
              "usage": [output["usage"] for output in outputs],
              "assessments": [output["analysis"].get("assessment") for output in outputs]}
    path = ROOT / "results/fresenius/reliability_first_signal.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    result = run_first_signal_repeats()
    print(json.dumps({"runs": result["runs"], "pairwise_citation_jaccard": result["pairwise_citation_jaccard"],
                      "trigger_cited_each_run": result["trigger_cited_each_run"]}, indent=2))
