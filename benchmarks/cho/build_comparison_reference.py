from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def build() -> dict:
    """Create descriptive reactor comparisons; no significance or causal labels."""
    source = json.loads((ROOT / "reference/objective_summaries.json").read_text(encoding="utf-8"))
    cultivations = source["cultivations"]
    experiments = {}
    for experiment in sorted({row["experiment"] for row in cultivations.values()}):
        left = cultivations[f"{experiment}_R01"]
        right = cultivations[f"{experiment}_R02"]
        comparisons = {}
        for name in sorted(set(left["measurements"]) & set(right["measurements"])):
            a, b = left["measurements"][name], right["measurements"][name]
            span = max(a["max"], b["max"]) - min(a["min"], b["min"])
            comparisons[name] = {
                "kind": a["kind"], "r01_count": a["count"], "r02_count": b["count"],
                "r01_mean": a["mean"], "r02_mean": b["mean"],
                "mean_delta_r02_minus_r01": b["mean"]-a["mean"],
                "mean_delta_over_pair_range": (b["mean"]-a["mean"])/span if span else None,
                "r01_last": a["last"], "r02_last": b["last"],
                "last_delta_r02_minus_r01": b["last"]-a["last"],
                "source_files": [left["sources"][a["kind"]]["file"],
                                 right["sources"][b["kind"]]["file"]],
            }
        experiments[experiment] = {"process_mode": left["process_mode"],
                                   "reactors": ["R01", "R02"], "measurements": comparisons}
    result = {"version": "cho-descriptive-comparison-v1",
              "method": "pair each experiment's R01 and R02 publication-aligned summaries; compare means and last reported values",
              "interpretation_limit": "Descriptive differences only. No independence assumption, significance test, relevance label, or causal truth.",
              "experiments": experiments}
    destination = ROOT / "reference/process_comparison.json"
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    output = build()
    print(len(output["experiments"]), "experiments", sum(len(item["measurements"]) for item in output["experiments"].values()), "comparisons")
