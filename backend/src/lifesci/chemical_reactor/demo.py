"""Reproducible learning exercise. All chemistry and observations are synthetic.

From backend/: python -m src.lifesci.chemical_reactor.demo --output /tmp/reactor-learning
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform

import numpy as np
import scipy

from ..ids import content_hash
from .analysis import compare_sites, fit_parameters, sensitivity
from .model import VERSION, simulate


def example():
    # Values chosen to teach heat-removal/competing-reaction behaviour.
    # They are NOT published kinetics or specifications for any medicine.
    return {
        "chemistry": {"reference_temperature_k": 298.15,
                      "product_rate_ref_s_inv": .00035, "impurity_rate_ref_s_inv": .000015,
                      "product_activation_j_mol": 50000., "impurity_activation_j_mol": 85000.,
                      "product_enthalpy_j_mol": -70000., "impurity_enthalpy_j_mol": -90000.,
                      "density_kg_m3": 1000., "heat_capacity_j_kg_k": 3500.},
        "equipment": {"working_volume_m3": .01, "heat_transfer_area_m2": .12,
                      "heat_transfer_coefficient_w_m2_k": 350., "coolant_temperature_k": 293.15},
        "recipe": {"initial_a_mol_m3": 3000., "initial_temperature_k": 298.15,
                   "duration_s": 7200., "temperature_limit_k": 345.,
                   "maximum_impurity_fraction": .1, "sample_interval_s": 15.},
        "evidence_classification": "synthetic_learning_assumptions_not_customer_measurements",
        "source_refs": ["authored-learning-example:no-experimental-data"],
    }


def receiver_example(source):
    receiver = deepcopy(source)
    receiver["equipment"].update(working_volume_m3=.1, heat_transfer_area_m2=.35,
                                  heat_transfer_coefficient_w_m2_k=150.)
    return receiver


def synthetic_observations(config, seed=20261108):
    result = simulate(config)
    if result["status"] != "completed":
        raise ValueError("synthetic calibration run must complete")
    t = np.arange(0., config["recipe"]["duration_s"]+1., 180.)
    temp = np.interp(t, [r["time_s"] for r in result["trajectory"]],
                     [r["temperature_k"] for r in result["trajectory"]])
    noise = np.random.default_rng(seed).normal(0, .08, len(t))
    noise[0] = 0.
    return [{"time_s": float(h), "temperature_k": float(v),
             "source_ref": f"synthetic-seed-{seed}:row-{i}"} for i, (h, v) in enumerate(zip(t, temp+noise))]


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output directory must be empty; preserve previous run receipts")
    donor = example()
    receiver = receiver_example(donor)
    comparison = compare_sites(donor, receiver, allowed_yield_loss_fraction=.02)
    cooler = deepcopy(receiver)
    cooler["equipment"]["coolant_temperature_k"] = 283.15
    characterized = deepcopy(receiver)
    characterized["equipment"]["heat_transfer_coefficient_w_m2_k"] = 450.
    alternative = deepcopy(receiver)
    alternative["equipment"].update(heat_transfer_area_m2=1.2, heat_transfer_coefficient_w_m2_k=350.)
    # This is a hypothetical measured improvement, not an implementable controller action.
    candidates = {"cooler_coolant_hypothesis": compare_sites(donor, cooler, allowed_yield_loss_fraction=.02),
                  "improved_U_characterization_hypothesis": compare_sites(donor, characterized, allowed_yield_loss_fraction=.02),
                  "alternate_receiver_geometry_hypothesis": compare_sites(donor, alternative, allowed_yield_loss_fraction=.02)}
    observations = synthetic_observations(donor)
    initial = deepcopy(donor)
    initial["equipment"]["heat_transfer_coefficient_w_m2_k"] = 280.
    fit = fit_parameters(initial, observations, fields=["heat_transfer_coefficient_w_m2_k"],
                         bounds={"heat_transfer_coefficient_w_m2_k": [200., 600.]}, training_until_s=3600.)
    receipt = {"classification": "synthetic_numerical_learning_exercise_not_experimental_validation",
               "model_version": VERSION, "environment": {"python": platform.python_version(),
                    "numpy": np.__version__, "scipy": scipy.__version__},
               "inputs": {"donor": donor, "receiver": receiver},
               "baseline_comparison": comparison, "candidate_comparisons": candidates,
               "calibration": fit, "sensitivity": sensitivity(donor),
               "data_hash": content_hash(observations),
               "model_source_hash": content_hash(Path(__file__).with_name("model.py").read_bytes())}
    (output/"results.json").write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
    (output/"synthetic_temperature_measurements.json").write_text(json.dumps(observations, indent=2)+"\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for label, result in (("Donor: 10 L", comparison["donor"]), ("Receiver: 100 L", comparison["receiver"]),
                          ("Receiver: hypothetical higher U", candidates["improved_U_characterization_hypothesis"]["receiver"])):
        rows = result["trajectory"]
        hours = [r["time_s"]/3600 for r in rows]
        axes[0].plot(hours, [r["temperature_k"]-273.15 for r in rows], label=label)
        axes[1].plot(hours, [100*r["product_yield_fraction"] for r in rows], label=label)
    axes[0].axhline(donor["recipe"]["temperature_limit_k"]-273.15, color="black", ls="--", label="Task temperature limit")
    axes[0].set_ylabel("Reactor temperature (°C)")
    axes[1].set_ylabel("Desired-product molar yield (%)")
    for ax in axes:
        ax.set_xlabel("Elapsed time (h)")
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.suptitle("Synthetic learning example · stopped trajectories do not predict final yield")
    fig.tight_layout()
    fig.savefig(output/"site_comparison.png", dpi=170)
    plt.close(fig)
    lines = ["# Chemical reactor learning run", "", "Synthetic inputs and measurements; no customer or experimental validation.", "",
             "| Scenario | Status | Yield (%) | Impurity (%) | Peak returned T (°C) |", "|---|---|---:|---:|---:|"]
    for name, result in [("Donor", comparison["donor"]), ("Receiver", comparison["receiver"]),
                         *[(k, v["receiver"]) for k, v in candidates.items()]]:
        fmt = lambda x: "withheld" if x is None else f"{100*x:.2f}"
        lines.append(f"| {name} | {result['status']} | {fmt(result['product_yield_fraction'])} | {fmt(result['impurity_fraction'])} | {result['maximum_temperature_k_at_returned_points']-273.15:.2f} |")
    lines += ["", f"Source U fit: {fit['estimates']['heat_transfer_coefficient_w_m2_k']:.2f} W/(m² K).",
              f"Training RMSE: {fit['training_rmse_k']:.4f} K; later holdout RMSE: {fit['holdout_rmse_k']:.4f} K.",
              "The synthetic truth uses U=350 W/(m² K). Recovery tests code consistency, not real-world identifiability or prediction accuracy.",
              "", "Next: replace assumptions with independently reviewed kinetics, calorimetry, heat-transfer measurements and product/impurity assays.",
              "No proposed utility or U change is a qualified manufacturing recommendation."]
    (output/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"report": str(output/"report.md"), "baseline_assessment": comparison["assessment"],
                      "fit_U_w_m2_k": fit["estimates"]["heat_transfer_coefficient_w_m2_k"]}, indent=2))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    run(parser.parse_args().output)
