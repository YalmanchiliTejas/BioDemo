"""Family-specific observables on the one existing catalogue and analysis runner."""

from copy import deepcopy
import math

import numpy as np
from scipy.optimize import least_squares


def value_at(data, path):
    for key in path.split("."):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def set_value(data, path, value):
    keys = path.split(".")
    for key in keys[:-1]:
        data = data[key]
    data[keys[-1]] = value


# Terms a fit may estimate: rates, transfer coefficients, resistances, efficiencies, i.e. what is uncertain and
# characterised from run data. Sizes, charges, set points and recipe settings come from records and are never fitted.
# A model absent here, or with an empty set, has nothing designated to fit; the fit is refused.
FITTABLE = {
    "chemical.semi_batch": ("product_rate_ref_s_inv", "impurity_rate_ref_s_inv", "product_activation_j_mol",
                            "impurity_activation_j_mol", "heat_transfer_coefficient_w_m2_k"),
    "crystal.cooling_moments": ("growth_rate_m_s", "growth_exponent", "nucleation_rate_m3_s", "nucleation_exponent"),
    "isolation.cake_filter": ("medium_resistance_m_inv", "cake_resistance_m_kg"),
    "isolation.cake_wash": (),  # screening displacement model: no rate term to estimate
    "isolation.cake_dryer": ("drying_rate_s_inv", "ua_w_k"),
    "powder.continuous_blender": ("hold_up_kg",),
    "powder.two_bin_mill": ("breakage_rate_s_inv",),
    "powder.aggregation_granulator": ("aggregation_coefficient_m3_s",),
    "tablet.heckel_compaction": ("heckel_coefficient_pa_inv", "zero_porosity_strength_pa", "strength_porosity_coefficient"),
    "tablet.coating_deposition": ("deposition_efficiency",),
    "tablet.shrinking_area_dissolution": ("mass_transfer_m_s",),
    "downstream.equilibrium_capture": ("capacity_kg_kg_resin", "affinity_m3_kg"),
    "membrane.ultrafiltration": ("permeate_flux_m_s", "product_sieving"),
    "membrane.diafiltration": ("permeate_flux_m_s", "product_sieving", "impurity_sieving"),
    "utility.turbulent_mixing": ("power_number",),
    "utility.ideal_vacuum": ("effective_pumping_m3_s", "gas_load_mol_s"),
}


def contract(adapter):
    d = adapter.describe()
    mid = adapter.id
    if hasattr(adapter, "outputs"):
        axis = adapter.axis
        units = dict(adapter.outputs)
        fit = {
            k: {"unit": v.unit, "bounds": [v.minimum, v.maximum]}
            for k, v in adapter.inputs.items()
            if k in FITTABLE.get(mid, ())
        }
    elif mid.startswith("lyo."):
        axis = "time_h"
        units = {
            "interface_temperature_c": "degC",
            "bottom_temperature_c": "degC",
            "remaining_ice_kg_per_vial": "kg/vial",
            "sublimation_kg_h": "kg/h",
        }
        fit = {
            "equipment.kv_scale": {"unit": "dimensionless", "bounds": [0.5, 1.5]},
            "product.rp_scale": {"unit": "dimensionless", "bounds": [0.5, 1.5]},
        }
    elif mid == "chemical.parallel_batch":
        axis = "time_s"
        units = {
            "a_mol": "mol",
            "product_mol": "mol",
            "impurity_mol": "mol",
            "temperature_k": "K",
            "product_yield_fraction": "fraction",
            "impurity_fraction": "fraction",
        }
        fit = {
            "chemistry.product_rate_ref_s_inv": {"unit": "1/s", "bounds": [0.0, 0.1]},
            "equipment.heat_transfer_coefficient_w_m2_k": {"unit": "W/(m2 K)", "bounds": [0.0, 10000.0]},
        }
    elif mid == "fermentation.oxygen_transfer":
        axis = "none"
        units = {"selected_scenario.predicted_kla_h_inv": "1/h", "selected_scenario.power_w_m3": "W/m3"}
        fit = {"assumptions.gas_exponent": {"unit": "dimensionless", "bounds": [0.0, 0.8]}}
    elif mid == "fermentation.pressure_cost":
        axis = "none"
        units = {"scenarios.1.otr_mg_l_h": "mg/(L h)", "scenarios.1.our_margin_mg_l_h": "mg/(L h)"}
        fit = {"assumptions.kla_h_inv": {"unit": "1/h", "bounds": [1.0, 1000.0]}}
    elif mid == "cho.monod_batch":
        axis = "time_h"
        units = {"viable_cell_density": "million cells/mL", "glucose": "g/L"}
        fit = {}
    else:
        raise ValueError("Adapter lacks an explicit observable contract")
    return {
        "axis": axis,
        "observables": units,
        "fit_parameters": fit,
        "model_kind": d.get(
            "model_kind", "semimechanistic" if mid.startswith(("fermentation.", "cho.")) else "reduced_mechanistic"
        ),
        "quality_scope": "Only declared observables; conversion is not desired-product yield.",
    }


def completed(result):
    return result.get("status", result.get("numerical_status", "completed")) == "completed"


def predict(adapter, config, observations, *, runner=None):
    spec = contract(adapter)
    out = []
    for row in observations:
        if spec["observables"].get(row.get("observable")) != row.get("unit"):
            raise ValueError("Observable/unit incompatible with model contract")
    result = (runner or adapter.run)(config)
    if not completed(result):
        raise ValueError("Solver did not complete; metrics and extrapolated predictions withheld")
    for row in observations:
        field = row["observable"]
        if spec["observables"].get(field) != row["unit"]:
            raise ValueError("Observable/unit incompatible with model contract")
        if spec["axis"] == "none":
            if row["coordinate"] != 0:
                raise ValueError("Algebraic screen uses coordinate 0, not a fabricated time trajectory")
            val = value_at(result, field)
        else:
            curve = result.get("trajectory", [])
            x = [r[spec["axis"]] for r in curve]
            if not x or not x[0] <= row["coordinate"] <= x[-1]:
                raise ValueError("Observation outside returned solver domain")
            val = float(np.interp(row["coordinate"], x, [r[field] for r in curve]))
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError("Unavailable/nonfinite observable")
        out.append(float(val))
    return np.asarray(out), result


def fit_runs(adapter, runs, parameter, bounds, budget):
    """Fit an explicit scalar using training batches only; fail on no excitation."""
    spec = contract(adapter)
    if parameter not in spec["fit_parameters"]:
        raise ValueError("Parameter not designated identifiable/fittable for this adapter")
    lo, hi = map(float, bounds)
    allowed = spec["fit_parameters"][parameter]["bounds"]
    if not math.isfinite(lo + hi) or not allowed[0] <= lo < hi <= allowed[1]:
        raise ValueError("Invalid physical fit bounds")

    def residual(z):
        error = []
        for run in runs:
            c = deepcopy(run["config"])
            set_value(c, parameter, lo + (hi - lo) * z[0])
            obs = run["observations"]
            p, _ = predict(adapter, c, obs, runner=lambda cfg: budget.run(adapter, cfg))
            error.extend(
                (p - np.array([r["value"] for r in obs]))
                / np.array([r.get("scale", max(abs(r["value"]), 1.0)) for r in obs])
            )
        return np.asarray(error)

    if not runs:
        raise ValueError("Training runs required")
    start = (value_at(runs[0]["config"], parameter) - lo) / (hi - lo)
    fit = least_squares(residual, [np.clip(start, 0.001, 0.999)], bounds=([0.0], [1.0]), max_nfev=25)
    sensitivity = float(np.linalg.norm(fit.jac))
    if not fit.success or sensitivity < 1e-7:
        raise ValueError("Parameter unidentifiable on supplied training observations")
    return {
        "parameter": parameter,
        "estimate": float(lo + (hi - lo) * fit.x[0]),
        "unit": spec["fit_parameters"][parameter]["unit"],
        "bounds": [lo, hi],
        "at_bound": bool(np.any(fit.active_mask)),
        "local_sensitivity_norm": sensitivity,
        "identifiability": "nonzero_local_sensitivity_only",
        "training_batch_ids": sorted({r["batch_id"] for r in runs}),
        "training_rmse_scaled": float(np.sqrt(np.mean(fit.fun**2))),
        "calibrated_uncertainty": False,
    }


def input_units(adapter):
    if hasattr(adapter, "inputs"):
        return {k: v.unit for k, v in adapter.inputs.items()}
    units = {k: v["unit"] for k, v in contract(adapter)["fit_parameters"].items()}
    if adapter.id == "chemical.parallel_batch":
        units.update(
            {
                "recipe.initial_temperature_k": "K",
                "recipe.initial_a_mol_m3": "mol/m3",
                "equipment.coolant_temperature_k": "K",
                "equipment.working_volume_m3": "m3",
                "equipment.heat_transfer_area_m2": "m2",
            }
        )
    return units
