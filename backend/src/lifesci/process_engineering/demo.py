"""Reproducible model-selection/pipeline demonstration with honest agent attempts."""
import argparse
import json
import os
from pathlib import Path

from ..container import Platform
from ..devseed import TENANT, seed
from ..store import RecordStore


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("docs/process-simulation/model-selection-artifacts"))
    args = parser.parse_args()
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=True)
    p = Platform(RecordStore())
    seed(p); ctx = p.identity.context_for(TENANT, "priya")
    source = p.process_models.context(ctx, audience="cdmo_operation", samples=2)
    service = p.process_models.analysis
    request = {"simulation_id": source["id"], "candidate_index": 0,
        "objective": "Compare quasi-steady and transient primary-drying models, quantify holdout discrepancies and identify required characterization.",
        "thermal_assumptions": {"vial_heat_capacity_j_k": 3., "initial_temperature_c": -43.}}
    planning = service.agent_plan(ctx, request)
    print("Actual agent-planning attempt:", planning["status"], flush=True)
    if planning["plan"] is not None:
        plan = planning["plan"]
    else:
        # Explicitly engineer-authored; never reported as an agent choice.
        plan = service.prepare(ctx, {**request, "models": [
            {"model_id": "lyo.kv_rp", "rationale": "Screen primary drying using the established heat/mass balance and inspect its quasi-steady assumption."},
            {"model_id": "lyo.transient_lumped", "rationale": "Compare finite thermal storage at a scheduled shelf change; thermal inputs remain uncharacterized assumptions."}],
            "calibration": "kv_scale", "samples": 4, "seed": 2025})
    result = service.execute(ctx, plan["id"])
    assessment = service.interpret(ctx, result["id"])
    review = service.propose_review(ctx, result["id"], "priya")
    for name, data in [("source.json", source), ("catalog.json", service.models(ctx)), ("agent-planning-attempt.json", planning),
                       ("plan.json", plan), ("analysis.json", result), ("agent-assessment-attempt.json", assessment), ("review-proposal.json", review)]:
        save(root/name, data)
    (root/".cache").mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(root/".cache"))
    os.environ.setdefault("XDG_CACHE_HOME", str(root/".cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    for model in result["models"]:
        if model["status"] != "completed":
            continue
        for ax, key, label in [(axes[0, 0], "interface_temperature_c", "Interface temperature (°C)"),
                               (axes[1, 0], "remaining_ice_kg_per_vial", "Remaining ice (kg/vial)"),
                               (axes[1, 1], "capacity_margin_kg_h", "Vapor capacity margin (kg/h)")]:
            rows = model["prediction"]["trajectory"]
            ax.plot([r["time_h"] for r in rows], [r[key] for r in rows], label=model["model_id"])
            ax.set(xlabel="Primary drying time (h)", ylabel=label); ax.grid(alpha=.15)
        pairs = model["holdout_evaluation"]["pairs"]
        axes[0, 1].plot([r["time_h"] for r in pairs], [r["residual_c"] for r in pairs], label=model["model_id"])
    axes[0, 0].axhline(-28, ls="--", color="firebrick", lw=1)
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].set(xlabel="Holdout observation time (h)", ylabel="Predicted minus observed (°C)")
    axes[0, 1].axhline(0, color="gray", ls=":")
    axes[1, 1].axhline(0, color="firebrick", ls="--", lw=1)
    fig.suptitle("Executed model-selection pipeline · synthetic observations · unqualified models")
    for ext in ("png", "svg"):
        fig.savefig(root/f"model-comparison.{ext}", dpi=150)
    plt.close(fig)
    lines = ["# Executed physical model-selection pipeline", "",
        f"Plan authored by **{plan['authored_by']['kind']}**. Actual agent planning: **{planning['status']}**; actual agent result assessment: **{assessment['status']}**.", "",
        "No agent selection or assessment was fabricated when the existing model route was unavailable. The engineer-authored example uses the same typed plan and numerical runner available to the agent tools.", "",
        "| Physical model | Status | Training Kv scale | Holdout RMSE °C | Holdout coverage | Completion h |",
        "|---|---|---:|---:|---:|---:|"]
    for model in result["models"]:
        if model["status"] == "completed":
            lines.append(f"| {model['model_id']} | completed | {model['calibration'].get('estimate', 1):.3f} | {model['holdout_evaluation']['rmse_c']:.3f} | {model['holdout_evaluation']['coverage']:.2f} | {model['prediction']['completion_time_h']:.2f} |")
        else:
            lines.append(f"| {model['model_id']} | {model['status']} | unavailable | unavailable | unavailable | unavailable |")
    lines.extend(["", f"Resource use: {result['resource_usage']['solver_calls']} solver calls, {result['resource_usage']['runtime_seconds']:.2f} s. Seed: {plan['spec']['seed']}.", "",
        "Training uses observations through 3 h. Holdout observations are later than 3 h and available by 6 h. Earlier full-window diagnostic fits are discarded. Holdout scoring uses observed operating history; prospective interventions are not graded as executed measurements. All observations in this example are synthetic, not independent experimental validation.", "",
        "![Executed comparisons](model-comparison.png)", "", "The transient model adds a lumped thermal state and requires assumed vial heat capacity (3 J/K) and initial temperature (−43°C); constant ice specific heat is approximated as 2100 J/(kg K). These inputs require characterization. Greater complexity or lower synthetic holdout error does not qualify a model.", "",
        "The live 3D review uses saved diameter/fill geometry and executed ice-front/temperature states. Glass body height and shelf are schematic. Color represents one interface temperature, not a resolved 3D temperature or flow field. The geometry frames, solver versions, parameter snapshots, training/holdout rows, random seed, model code hashes and runner hashes are retained in analysis.json and plan.json.", "",
        f"Engineering review proposal: {review['proposal_id']}; state {review['status']}; execution {review['execution_status']}. No manufacturing change or scientific qualification was applied.", "",
        "New models can be proposed through the adapter review tool/API. Proposals retain equations, required inputs and units, source/license information, intended-use limits and a verification/independent-validation plan. They neither register models nor execute generated code.", "",
        "Reproduce: `PYTHONPATH=backend .venv/bin/python -m src.lifesci.process_engineering.demo`.", "",
        "See [workflow and integration guide](../model-selection.md) for API/tool contracts, UI usage, testing and limitations.", ""])
    (root/"report.md").write_text("\n".join(lines))
    print(root/"report.md", flush=True)


if __name__ == "__main__":
    main()
