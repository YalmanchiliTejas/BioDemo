from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def validate() -> dict:
    split = json.loads((ROOT / "benchmarks/configs/scenario_splits.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "benchmarks/cho/data_inventory.json").read_text(encoding="utf-8"))
    available_experiments = {"EXP" + row["experiment"] for row in inventory["workbooks"]}
    development = set(split["cho"]["development_experiments"])
    evaluation = set(split["cho"]["evaluation_experiments"])
    from benchmarks.fresenius.build_tasks import build_tasks
    available_tasks = {row["id"] for row in build_tasks()}
    fresenius_development = set(split["fresenius"]["development_tasks"])
    fresenius_evaluation = set(split["fresenius"]["evaluation_tasks"])
    result = {"cho_disjoint": not development & evaluation,
              "cho_covers_all_experiments": development | evaluation == available_experiments,
              "fresenius_disjoint": not fresenius_development & fresenius_evaluation,
              "fresenius_covers_all_tasks": fresenius_development | fresenius_evaluation == available_tasks,
              "historically_untouched_holdout": False}
    result["pass"] = all(value for key, value in result.items() if key not in {"pass", "historically_untouched_holdout"})
    return result


if __name__ == "__main__":
    report = validate()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
