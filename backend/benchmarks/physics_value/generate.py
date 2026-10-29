"""Generate a fresh, reproducible synthetic pilot; never run or imitate agents."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
from time import perf_counter

import numpy as np
import scipy

from .domains import (DOMAIN_FAMILIES, TASKS, actions, apply_action, make_case,
                      measurement_catalog, nominal_mechanism, observe, outcome, run_reference)
from .public_models import notes

VERSION = "physical-model-value-synthetic-pilot-2"


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hypothesis_classes(domain):
    return (["nominal", "low_transfer", "high_demand", "sensor_bias", "gas_response", "unknown_mechanism"]
            if domain == "oxygen" else
            ["nominal", "high_heat_transfer", "high_resistance", "sensor_bias", "low_capacity", "unknown_mechanism"])


def truth_causes(domain, family):
    if family == "mixed":
        return ["low_transfer", "high_demand"] if domain == "oxygen" else ["high_heat_transfer", "high_resistance"]
    return ["gas_response" if family == "gas_lag" else family]


def packet_for(case_id, domain, config, source_config, source_rows, rows, task):
    cutoff = 0. if task == "pretransfer" else 6.
    return {"schema_version": VERSION, "case_id": case_id, "domain": domain, "task": task,
            "classification": "synthetic_manufacturing_challenge_not_factory_data",
            "decision_time_h": cutoff,
            "objective": {
                "diagnosis": "Rank plausible causes, cite observations and propose a discriminating measurement. Do not force an identifiable cause from ambiguous data.",
                "optimization": "Select an allowed action with the best feasible declared objective. State uncertainty and required verification.",
                "resolution": "Request measurements, revise hypotheses, choose an intervention and verify its outcome. Experimental time and human work are synthetic assumptions.",
                "pretransfer": "Before a receiving batch starts, predict transfer risks and propose a receiving plan or characterization. No receiving measurements are available.",
            }[task],
            "receiving_configuration": config, "source_configuration": source_config,
            "source_observations": source_rows,
            "clock_definition": "Source observations are completed historical source-batch hours. Receiving observations and decision time use a separate receiving-batch clock; source history is already available before receiving time zero.",
            "receiving_observations": [] if task == "pretransfer" else [r for r in rows if r["available_at_h"] <= cutoff],
            "allowed_actions": actions(domain, pretransfer=task == "pretransfer"),
            "decision_options": ["proceed", "characterize", "abstain"] if task == "pretransfer" else ["choose_action_or_request_measurement"],
            "measurement_catalog": measurement_catalog(domain),
            "hypothesis_classes": hypothesis_classes(domain),
            "objective_definition": ("Minimize partial utility cost plus declared synthetic feed-curtailment penalty, subject to DO >= 1.5 mg/L for the full batch. Penalty is $0.05 per unit of curtailed mg/L/h integrated over hours. This is not commercial COGS."
                                     if domain == "oxygen" else
                                     "Maximize load/completion_time over the allowed action grid, subject to complete primary drying, hottest-active-vial temperature below the formulation limit and vapor capacity. This excludes secondary drying and turnaround."),
            "parameter_provenance": "Synthetic nominal configurations; freeze-drying starts from the existing published-parameter reconstruction. All random variation, mechanisms, noise and assay times are synthetic assumptions.",
            "observation_noise": {"routine_standard_deviation": .08 if domain == "oxygen" else .12,
                                  "unit": "mg/L" if domain == "oxygen" else "degrees C",
                                  "sensor_bias_possible": True},
            "model_notes": notes(domain),
            "authorization": "Simulation only. Recommendations are neither approved nor executed manufacturing actions."}


def _generate(output: Path, *, seed: int = 20261027, replicates: int = 2, plots: bool = True) -> dict:
    output = Path(output)
    if type(seed) is not int or seed < 0 or type(replicates) is not int or not 1 <= replicates <= 20:
        raise ValueError("nonnegative seed and 1..20 replicates required")
    if output.exists() and any(output.iterdir()):
        raise ValueError("use a fresh output directory; frozen runs are never overwritten")
    output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    protocol = {"version": VERSION, "status": "exploratory_pilot_not_confirmatory_preregistration",
                "seed": seed, "replicates_per_family": replicates,
                "tasks": list(TASKS), "agent_arms": {"A": "same data, equations and normal tools",
                                                     "B": "same data, equations and normal tools plus executable forward models"},
                "difference": "Executable forward-model access only; no diagnosis or optimization oracle is an agent tool.",
                "agent_runs_executed": False, "agent_uplift": None,
                "truth": "synthetic host evaluator; never independent experimental validation",
                "limits": ["Case-family parameter ranges and scenario catalogue are development material.",
                           "Reserved mechanism families are candidate evaluation cases, not untouched confirmatory holdouts.",
                           "File separation is not an enforced agent security boundary.",
                           "Human/assay times are assumptions, not measured engineer savings."]}
    # This receipt precedes all numerical execution. It is not a statistical preregistration.
    dump(output / "protocol.json", protocol)
    dump(output / "generation-status.json", {"status": "running", "expected_cases": 12*replicates})
    records, catalogue = [], []
    for domain, families in DOMAIN_FAMILIES.items():
        for family in families:
            for replicate in range(replicates):
                identity = f"{VERSION}:{seed}:{domain}:{family}:{replicate}"
                hashed = hashlib.sha256(identity.encode()).hexdigest()
                case_id = "PV-" + hashed[:12]
                rng = np.random.default_rng(int(hashed[:16], 16))
                config, mechanism, source = make_case(domain, family, rng)
                result = run_reference(domain, config, mechanism)
                source_truth = run_reference(domain, source, nominal_mechanism(domain))
                rows = observe(domain, result, mechanism, rng)
                source_rows = observe(domain, source_truth, nominal_mechanism(domain), rng)
                case = {"case_id": case_id, "domain": domain, "family": family,
                        "replicate": replicate, "mechanism": mechanism, "config": config,
                        "reference": result, "observations": rows,
                        "causes": truth_causes(domain, family),
                        "causal_label_scope": "authored synthetic mechanism, not independently adjudicated real root cause",
                        "initial_unique_cause_identifiability": "not_established",
                        "pool": "candidate_evaluation" if family in ("sensor_bias", "mixed", "gas_lag", "low_capacity") else "development"}
                counterfactuals = {}
                for task, decision in (("optimization", 6.), ("pretransfer", 0.)):
                    counterfactuals[task] = {}
                    for action in actions(domain, pretransfer=task == "pretransfer"):
                        c = apply_action(domain, config, action, decision, pretransfer=task == "pretransfer")
                        r = result if action["id"] == "keep" else run_reference(domain, c, mechanism)
                        counterfactuals[task][action["id"]] = outcome(domain, r, c, decision)
                case["counterfactuals"] = counterfactuals
                dump(output / "evaluator" / "cases" / f"{case_id}.json", case)
                for task in TASKS:
                    packet = packet_for(case_id, domain, config, source, source_rows, rows, task)
                    directory = output / "public" / case_id / task
                    dump(directory / "packet.json", packet)
                    for name, visible in (("source-traces.csv", packet["source_observations"]),
                                          ("receiving-traces.csv", packet["receiving_observations"])):
                        if visible:
                            with (directory / name).open("w", newline="") as stream:
                                writer = csv.DictWriter(stream, fieldnames=list(visible[0]))
                                writer.writeheader()
                                writer.writerows(visible)
                    catalogue.append({"case_id": case_id, "domain": domain, "task": task,
                                      "path": str((directory / "packet.json").relative_to(output))})
                records.append(case)
                print(json.dumps({"generated": case_id, "domain": domain, "completed_cases": len(records)}), flush=True)
    dump(output / "public" / "catalogue.json", catalogue)
    dump(output / "evaluator" / "catalogue.json", [{k: c[k] for k in ("case_id", "domain", "family", "replicate", "pool")} for c in records])
    summary = summarize(records)
    dump(output / "evaluator" / "simulation-summary.json", summary)
    if plots:
        plot_examples(records, output / "evaluator" / "simulation-overview.png")
    (output / "report.md").write_text(report(summary, plots))
    code = [*Path(__file__).parent.glob("*.py")]
    from src.lifesci.lyophilization import reference as reference_module, model as lyo_model, case as lyo_case
    from src.lifesci.fermentation import model as fermentation_model
    code += [Path(module.__file__) for module in (reference_module, lyo_model, lyo_case, fermentation_model)]
    manifest = {"version": VERSION, "seed": seed,
                "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
                "code_sha256": {str(p.relative_to(Path(__file__).resolve().parents[3])): digest(p) for p in code},
                "files_sha256": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*"))
                                 if p.is_file() and p.name != "generation-status.json"},
                "case_count": len(records), "task_packet_count": len(catalogue),
                "agent_runs_executed": False, "agent_uplift": None}
    dump(output / "manifest.json", manifest)
    dump(output / "generation-status.json", {"status": "complete", "case_count": len(records),
                                            "task_packet_count": len(catalogue),
                                            "generation_wall_seconds": perf_counter()-started})
    return {**summary, "output": str(output), "generation_wall_seconds": perf_counter()-started}


def generate(output: Path, *, seed: int = 20261027, replicates: int = 2, plots: bool = True) -> dict:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("use a fresh output directory; frozen runs are never overwritten")
    try:
        return _generate(output, seed=seed, replicates=replicates, plots=plots)
    except BaseException as exc:
        if (output / "generation-status.json").exists():
            dump(output / "generation-status.json", {
                "status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                "completed_cases": len(list((output / "evaluator/cases").glob("*.json"))),
                "error_type": type(exc).__name__, "error": str(exc),
                "agent_runs_executed": False})
        raise


def summarize(records):
    domains = {}
    for domain in DOMAIN_FAMILIES:
        cases = [r for r in records if r["domain"] == domain]
        keep = [c["counterfactuals"]["pretransfer"]["keep"] for c in cases]
        domains[domain] = {"cases": len(cases), "planned_issue_cases": sum(r["first_issue_h"] is not None for r in keep),
                           "thermal_or_oxygen_violation_cases": sum(r["thermal_or_oxygen_onset_h"] is not None for r in keep),
                           "capacity_violation_cases": sum(r["capacity_onset_h"] is not None for r in keep),
                           "nominal_plan_feasible_cases": sum(r["feasible_full_batch"] for r in keep),
                           "cases_with_feasible_pretransfer_action": sum(any(o["feasible_full_batch"] for o in c["counterfactuals"]["pretransfer"].values()) for c in cases),
                           "cases_with_feasible_action_at_6h": sum(any(o["feasible_full_batch"] for o in c["counterfactuals"]["optimization"].values()) for c in cases),
                           "sensor_fault_cases": sum(c["family"] == "sensor_bias" for c in cases),
                           "mixed_mechanism_cases": sum(c["family"] == "mixed" for c in cases)}
    return {"version": VERSION, "classification": "synthetic_dataset_audit_not_agent_performance",
            "case_count": len(records), "task_packet_count": len(records)*len(TASKS), "domains": domains,
            "agent_runs_executed": False, "agent_uplift": None,
            "real_engineer_hours_saved": None, "real_failed_batches_avoided": None}


def plot_examples(records, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 6, figsize=(20, 7), constrained_layout=True)
    for i, domain in enumerate(DOMAIN_FAMILIES):
        for j, family in enumerate(DOMAIN_FAMILIES[domain]):
            case = next(c for c in records if c["domain"] == domain and c["family"] == family)
            rows, observed = case["reference"]["trajectory"], case["observations"]
            key = "dissolved_oxygen_mg_l" if domain == "oxygen" else "product_temperature_c"
            ax = axes[i, j]
            ax.plot([r["time_h"] for r in rows], [r[key] for r in rows], label="Hidden physical trajectory", color="#17685d")
            ax.scatter([r["time_h"] for r in observed[::4]], [r[key] for r in observed[::4]], s=6, label="Noisy sensor", color="#b17b3d")
            if domain == "freeze_drying":
                active = [r for r in rows if r["active_max_temperature_c"] is not None]
                ax.plot([r["time_h"] for r in active], [r["active_max_temperature_c"] for r in active], linestyle=":", color="#b04444", label="Hottest active vial")
            threshold = 1.5 if domain == "oxygen" else -28.
            ax.axhline(threshold, color="#b04444", linewidth=.8)
            ax.axvline(6., color="#53657c", linestyle="--", linewidth=.8)
            ax.set(title=domain.replace("_", " ")+" / "+family.replace("_", " "), xlabel="Simulated hours")
            ax.set_ylabel("DO mg/L" if domain == "oxygen" else "Temperature °C")
    handles, labels = axes[1, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, frameon=False)
    fig.suptitle("Evaluator view: synthetic pilot mechanisms and observations — no agent results", fontsize=15)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def report(summary, plots):
    lines = ["# Generated physical-model experiment pilot", "",
             "Synthetic data only. No agents were executed. These simulations do not establish model-assisted agent accuracy, engineer time savings or prevention of real batch failures.", "",
             f"Generated **{summary['case_count']} process cases / {summary['task_packet_count']} decision packets** across oxygen supply and freeze-drying.", "",
             "Every process case supplies diagnosis, optimization, sequential-resolution and pre-transfer tasks. Pre-transfer packets contain source traces and receiving specifications, with zero receiving observations. Routine traces have seeded noise; sensor faults and mixed mechanisms are retained.", "",
             "| Domain | Cases | Planned simulated issues | Feasible original plan | Feasible option before transfer | Feasible full-batch option at 6 h |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for domain, values in summary["domains"].items():
        lines.append(f"| {domain} | {values['cases']} | {values['planned_issue_cases']} | {values['nominal_plan_feasible_cases']} | {values['cases_with_feasible_pretransfer_action']} | {values['cases_with_feasible_action_at_6h']} |")
    lines += ["", "These counts describe the generated environment, not detection or optimization performance. Feasible means satisfying this pilot's synthetic full-batch constraints; prior excursions cannot be erased by a later action. Some cases intentionally have no feasible option in the finite action grid.", "",
              "`public/` contains common agent packets. `evaluator/` contains hidden mechanisms, full futures and independently replayed candidate outcomes. Stage only one task at a time; the full dataset and source tree must not be mounted in an agent worker. File separation alone does not enforce that isolation.", "",
              "The oxygen reference integrates dynamic oxygen storage and gas response; its public tool uses a steady balance. Freeze-drying extends the existing heterogeneous transient equations with explicit ice-depletion events; the public tool is the existing representative-vial quasi-steady model. Shared physical laws and authored scenarios limit independence. These are independent implementations for a synthetic pilot, not independent real experimental validation.", "",
              "All observed cases are development/audit material. Candidate evaluation families are separated by mechanism, but a fresh independently authored holdout and reviewer-approved endpoints are needed for a confirmatory thesis test.", "",
              "Manifest hashes preserve code, source parameters, packets, hidden trajectories and outcomes. See the benchmark README for staging, measurement sessions, scoring and reproduction."]
    if plots:
        lines += ["", "![Synthetic evaluator trajectories](evaluator/simulation-overview.png)"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument("--replicates", type=int, default=2)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    print(json.dumps(generate(args.output, seed=args.seed, replicates=args.replicates, plots=not args.no_plots), indent=2))
