"""Export the synthetic Fresenius replay into a JSON file for the Tremor UI.

Run from the repository root:  .venv/bin/python ui/scripts/export_data.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from benchmark.case_comparison import ComparisonService
from benchmark.case_comparison.demo import build_demo
from benchmark.incident_demo import IncidentDemoService

OUTPUT = Path(__file__).resolve().parents[1] / "src/data/fresenius.json"


def main() -> None:
    case = ComparisonService().case("fresenius")
    demo = build_demo(case)
    view = demo["plant_view"]
    # Presentation rounding only; frozen event dates and benchmark outputs stay intact.
    view['lead_days'] = round((datetime.fromisoformat(view['recognized']['time'].replace('Z','+00:00'))
                              - datetime.fromisoformat(view['escalation']['time'].replace('Z','+00:00'))).total_seconds()/86400)
    for kpi in view['kpis']:
        if kpi['kind']=='date':kpi['delta']=f"About {view['lead_days']} days in simulation"
    data = IncidentDemoService().agent_data
    escalation = view["escalation"]["time"]
    affected = {lot["batch"] for lot in view["lots"]}

    labs: dict[str, dict] = {}
    for row in data["lab_results"]:
        labs.setdefault(row["batch_id"], {})[row["test_name"]] = row
    batches = []
    for batch in sorted(data["batches"], key=lambda b: b["start_time"]):
        bio = labs.get(batch["batch_id"], {}).get("relative_bioburden_signal", {})
        endo = labs.get(batch["batch_id"], {}).get("relative_endotoxin_signal", {})
        flagged = batch["batch_id"] in affected
        held = flagged and batch["disposition_time"] > escalation
        batches.append({
            "id": batch["batch_id"], "line": batch["production_line"], "start": batch["start_time"],
            "released": batch["disposition_time"], "shipped": batch["first_ship_time"],
            "bioburden": bio.get("numerical_result"), "bioburden_status": bio.get("status", "missing"),
            "endotoxin": endo.get("numerical_result"),
            "flagged": flagged,
            "recorded": "released",
            "projected": "held" if held else ("flagged_shipped" if flagged else "released"),
        })

    # Modeled projection: paired simulation with assumed per-deviation delays
    # (benchmark/controllers/*.py). Not a measurement of agent runs.
    comparison = json.loads((Path(__file__).resolve().parents[2] / "runs/comparison/comparison.json").read_text())
    per_run = comparison["scenario_count_per_run"]
    ends = comparison["endpoints"]
    projection = {
        "claim_status": comparison["claim_status"],
        "paired_runs": comparison["paired_runs"],
        "events_per_run": per_run,
        "hours": [
            {"metric": label, "Today": ends[key]["traditional_mean"] / div, "With agent": ends[key]["agent_assisted_mean"] / div}
            for key, label, div in (
                ("time_to_diagnose_hours", "Time to diagnose", 1),
                ("time_to_intervention_hours", "Time to intervene", 1),
                ("deviation_closure_hours", "Time to close deviation", 1),
                ("engineer_hours", "Engineer hours per deviation", per_run),
            )
        ],
        "assumptions": "Projected with a 30-run paired simulation of 12 deviation types. Today’s delays and the agent-assisted delays "
                       "are planning assumptions (benchmark/controllers), to be confirmed in a shadow pilot.",
    }

    tracks = case["replay"]["tracks"]
    simplify = lambda rows: [{"id": r["id"], "time": r["timestamp"], "kind": r.get("kind"), "title": r["title"],
                              "severity": r.get("severity"), "detail": r.get("detail", "")} for r in rows]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "disclosure": "Synthetic reconstruction informed by public FDA materials. Background, production, lab, complaint and QA "
                      "event timestamps are simulation assumptions, including the 2024 dates. Public first-ship calendar dates "
                      "and the November 2025 recall posting anchor the scenario; time of day is assumed. "
                      "Not Fresenius internal data; the with-agent side is a deterministic projected replay.",
        "plant_view": view,
        "projection": projection,
        "batches": batches,
        "recorded_events": simplify(tracks["traditional"]),
        "agent_events": simplify(tracks["ai"]),
    }, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(batches)} batches)")


if __name__ == "__main__":
    main()
