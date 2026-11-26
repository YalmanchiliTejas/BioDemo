"""Runnable synthetic development studies; no customer/experimental validation."""

from copy import deepcopy
import argparse
import json
from pathlib import Path
import numpy as np
from .catalog import ModelCatalog
from . import hybrid, uncertainty
from .contracts import predict


def synthetic_runs(model_id, *, seed=12, receiver=False):
    rng = np.random.default_rng(seed)
    out = []
    roles = ["train"] * (4 if receiver else 8) + ["selection"] * 3 + ["calibration"] * 10 + ["test"] * 3
    for i, role in enumerate(roles):
        if model_id == "chemical.parallel_batch":
            from ..chemical_reactor.demo import example
            from ..chemical_reactor.model import simulate

            c = example()
            temperature = float(rng.uniform(310, 330))
            c["recipe"].update(
                duration_s=2400.0, sample_interval_s=100.0, initial_temperature_k=temperature, temperature_limit_k=380.0
            )
            c["equipment"].update(
                coolant_temperature_k=temperature, heat_transfer_coefficient_w_m2_k=300.0 if receiver else 200.0
            )
            c["chemistry"].update(
                reference_temperature_k=320.0,
                product_rate_ref_s_inv=0.00015,
                impurity_rate_ref_s_inv=0.00004,
                product_activation_j_mol=20000.0,
                impurity_activation_j_mol=30000.0,
                product_enthalpy_j_mol=0.0,
                impurity_enthalpy_j_mol=0.0,
            )

            def truth(state, cfg):
                a = state[0] / (cfg.recipe.initial_a_mol_m3 * cfg.equipment.working_volume_m3)
                return [1.4 + 0.5 * a + 0.0005 * cfg.equipment.heat_transfer_coefficient_w_m2_k, 0.7 + 0.7 * (1 - a)]

            raw = simulate(c, kinetic_model=truth)
            obs = []
            for t in np.linspace(0, 2400, 17):
                for field, unit, scale in [
                    ("a_mol", "mol", 30.0),
                    ("product_mol", "mol", 30.0),
                    ("impurity_mol", "mol", 10.0),
                    ("temperature_k", "K", 10.0),
                ]:
                    value = float(
                        np.interp(t, [r["time_s"] for r in raw["trajectory"]], [r[field] for r in raw["trajectory"]])
                    )
                    std = 0.0 if field == "temperature_k" else 0.0001 * scale
                    obs.append(
                        {
                            "coordinate": float(t),
                            "observable": field,
                            "unit": unit,
                            "value": value + float(rng.normal(0, std)),
                            "scale": scale,
                            "measurement_std": std,
                        }
                    )
        else:
            from ..fermentation.data import project
            from ..fermentation.model import sulfolobus

            c = {
                "project": project("sulfolobus"),
                "assumptions": {
                    "selected_receiver_l": 20 if i % 2 else 200,
                    "rpm": float(rng.uniform(160, 220)),
                    "airflow_vvm": float(rng.uniform(0.15, 0.35)),
                    "gas_exponent": 0.5,
                },
            }

            def truth(power, vvm, eq):
                return float(
                    np.clip(
                        1.3
                        + 0.08 * np.log(power / 100)
                        + 0.1 * np.log(vvm / 0.2)
                        + 0.0002 * eq["impeller_diameter_mm"],
                        0.25,
                        4.0,
                    )
                )

            raw = sulfolobus(c, kla_model=truth)
            v = raw["selected_scenario"]["predicted_kla_h_inv"]
            obs = [
                {
                    "coordinate": 0.0,
                    "observable": "selected_scenario.predicted_kla_h_inv",
                    "unit": "1/h",
                    "value": v + float(rng.normal(0, 0.05)),
                    "scale": 100.0,
                    "measurement_std": 0.05,
                }
            ]
        out.append(
            {
                "run_id": f"{seed}-{i}",
                "batch_id": f"{seed}-batch-{i}",
                "site_id": "NF2" if receiver else "NF1",
                "role": role,
                "config": c,
                "observations": obs,
                "source_refs": [f"authored-synthetic-run-{seed}-{i}"],
                "independent_run_ref": f"synthetic-draw-{seed}-{i}",
                "evidence_classification": "synthetic_development",
                "evidence_cutoff": 2400.0 if model_id == "chemical.parallel_batch" else 0.0,
            }
        )
    return out


def interval_rows(run):
    # Explicit common endpoint grid/basis, separated from training observations.
    field = "product_mol" if "chemistry" in run["config"] else "selected_scenario.predicted_kla_h_inv"
    rows = [r for r in run["observations"] if r["observable"] == field]
    return [rows[-1]]


def example_campaign(output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    summary = {}
    for mid in hybrid.SUPPORTED:
        adapter = ModelCatalog(None).get(mid)
        runs = synthetic_runs(mid)
        checkpoint = hybrid.train(adapter, runs, ensemble_size=3)
        adapted_runs = synthetic_runs(mid, seed=44, receiver=True)
        adapted = hybrid.train(adapter, adapted_runs, parent=checkpoint, ensemble_size=3)
        partition = hybrid.partition(runs)
        cal_runs = deepcopy(partition["calibration"])
        test_runs = deepcopy(partition["test"])
        for r in cal_runs + test_runs:
            r["observations"] = interval_rows(r)
        # Physics intervals are intentionally included to demonstrate discrepancy
        # calibration independently of whether neural support is adequate.
        calibration = uncertainty.calibrate_intervals(adapter, cal_runs, mode="physics", samples=3)
        evaluation = uncertainty.evaluate_intervals(adapter, test_runs, calibration)
        hybrid_calibration = uncertainty.calibrate_intervals(
            adapter, cal_runs, checkpoint=checkpoint, mode="hybrid", samples=3
        )
        hybrid_evaluation = uncertainty.evaluate_intervals(
            adapter, test_runs, hybrid_calibration, checkpoint=checkpoint
        )
        final = {
            mode: hybrid.score(adapter, partition["test"], checkpoint, mode) for mode in ("physics", "refit", "hybrid")
        }
        record = {
            "model_id": mid,
            "classification": "synthetic_executable_development_only",
            "runs": runs,
            "source_checkpoint": checkpoint,
            "receiver_runs": adapted_runs,
            "adapted_checkpoint": adapted,
            "physics_interval_calibration": calibration,
            "physics_interval_evaluation": evaluation,
            "hybrid_interval_calibration": hybrid_calibration,
            "hybrid_interval_evaluation": hybrid_evaluation,
            "final_test_comparison": final,
        }
        (root / (mid + ".json")).write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
        summary[mid] = {
            "final_test_comparison": final,
            "source_selected": checkpoint["selected_model"],
            "negative_transfer": adapted["negative_transfer"],
            "physics_intervals": evaluation,
            "hybrid_interval_status": hybrid_calibration["status"],
            "hybrid_intervals": hybrid_evaluation,
            "calibration_independent_groups": calibration["independent_calibration_groups"],
        }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(example_campaign(args.output), indent=2))
