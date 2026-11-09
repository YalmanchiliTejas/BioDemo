"""Prescribed cooling, monodisperse seed and four population moments per m³ liquid."""
import numpy as np

from .common import Model, Input, positive, temperature, duration, integrate, series


def cooling(c):
    if c["end_temperature_k"] > c["start_temperature_k"]:
        raise ValueError("growth-only model supports cooling, not heating/dissolution")
    solubility = lambda t: c["solubility_ref_kg_m3"] * np.exp(c["solubility_slope_k_inv"]*(t-c["reference_temperature_k"]))
    if c["initial_solute_kg_m3"] < solubility(c["start_temperature_k"]):
        raise ValueError("initial undersaturation needs seed dissolution physics, which is not included")
    rho, kv, seed, size = c["crystal_density_kg_m3"], c["shape_factor"], c["seed_number_m3"], c["seed_size_m"]
    initial = [c["initial_solute_kg_m3"], seed, seed*size, seed*size**2, seed*size**3]
    inventory = initial[0] + rho*kv*initial[4]
    def rhs(t, y):
        temp = c["start_temperature_k"]+(c["end_temperature_k"]-c["start_temperature_k"])*t/c["duration_s"]
        supersat = max(y[0]/solubility(temp)-1, 0.)
        growth = c["growth_rate_m_s"]*supersat**c["growth_exponent"]
        birth = c["nucleation_rate_m3_s"]*supersat**c["nucleation_exponent"]
        ln = c["nucleus_size_m"]
        moment_rates = [birth, growth*y[1]+birth*ln,
                        2*growth*y[2]+birth*ln**2, 3*growth*y[3]+birth*ln**3]
        return [-rho*kv*moment_rates[-1], *moment_rates]
    t, y, _ = integrate(c, rhs, initial, atol=[1e-8, 1., 1e-6, 1e-12, 1e-17])
    if np.min(y[0]) < -1e-6 or np.min(y[1:]) < -1e-12:
        raise ValueError("invalid concentration or population moment")
    solid = rho*kv*y[4]
    mean_size = np.divide(y[2], y[1], out=np.zeros_like(y[2]), where=y[1]>0)
    d32 = np.divide(y[4], y[3], out=np.zeros_like(y[4]), where=y[3]>0)
    return {"trajectory": series(t, solute_kg_m3=y[0], crystal_kg_m3=solid,
                                  number_mean_size_m=mean_size, surface_volume_size_m=d32),
            "final_crystal_mass_kg": float(solid[-1]*c["liquid_volume_m3"]),
            "final_dissolved_mass_kg": float(y[0,-1]*c["liquid_volume_m3"]),
            "recovered_fraction_including_seed": float(solid[-1]/inventory),
            "maximum_inventory_error_kg_m3": float(np.max(np.abs(y[0]+solid-inventory))),
            "final_number_mean_size_m": float(mean_size[-1]), "final_surface_volume_size_m": float(d32[-1]),
            "final_moments": [float(v) for v in y[1:,-1]],
            "warnings": ["Recovery denominator includes seed mass; moments do not reconstruct a unique full size distribution"]}


MODELS = [Model("crystal.cooling_moments", "crystallization", "Cooling crystallizer with population moments",
    {"liquid_volume_m3": positive("m³", 1000), "initial_solute_kg_m3": positive("kg/m³", 2000),
     "start_temperature_k": temperature(), "end_temperature_k": temperature(), "reference_temperature_k": temperature(),
     "solubility_ref_kg_m3": positive("kg/m³", 2000), "solubility_slope_k_inv": Input("1/K", 0, .2),
     "crystal_density_kg_m3": positive("kg/m³", 10000), "shape_factor": positive("dimensionless", 10),
     "seed_number_m3": positive("1/m³", 1e16), "seed_size_m": positive("m", .01),
     "nucleus_size_m": positive("m", .001), "growth_rate_m_s": Input("m/s", 0, .001),
     "growth_exponent": Input("dimensionless", 1, 5), "nucleation_rate_m3_s": Input("1/(m³ s)", 0, 1e16),
     "nucleation_exponent": Input("dimensionless", 1, 5), "duration_s": duration()},
    {"solute_kg_m3": "kg/m³", "crystal_kg_m3": "kg/m³", "number_mean_size_m": "m", "surface_volume_size_m": "m"},
    "dmj/dt=j G m(j-1)+B Ln^j; dc/dt=-rho kv dm3/dt; prescribed cooling and exponential solubility",
    ("Well-mixed dilute suspension, constant liquid volume, no agglomeration/breakage/dissolution/polymorphism.",
     "Temperature profile is prescribed; receiving cooling capability is not solved.",
     "Kinetics/solubility require compound-specific measurements; seed-inclusive recovery is not purity."),
    cooling, "https://pharmapy.readthedocs.io/en/latest/docstrings/unit_operations.html")]
