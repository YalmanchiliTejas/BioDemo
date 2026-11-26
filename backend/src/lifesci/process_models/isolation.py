"""Incompressible cake filtration, mixed-pore washing and lumped solvent drying."""
import numpy as np

from .common import Model, Input, positive, fraction, temperature, duration, grid, integrate, series


def filtration(c):
    a, dp, mu = c["filter_area_m2"], c["pressure_difference_pa"], c["viscosity_pa_s"]
    linear = mu*c["medium_resistance_m_inv"]/(a*dp)
    quadratic = mu*c["cake_resistance_m_kg"]*c["solids_per_filtrate_kg_m3"]/(2*a*a*dp)
    target = c["target_filtrate_m3"]
    completion = linear*target+quadratic*target**2
    t = np.unique(np.r_[grid(c), min(completion, c["duration_s"])])
    # Stable positive quadratic root; supports zero cake resistance.
    volume = 2*t/(linear+np.sqrt(linear*linear+4*quadratic*t))
    volume = np.minimum(volume, target)
    finished = completion <= c["duration_s"]
    return {"trajectory": series(t, filtrate_m3=volume, cake_solids_kg=volume*c["solids_per_filtrate_kg_m3"]),
            "completion_time_s": float(completion) if finished else None,
            "final_filtrate_m3": float(volume[-1]) if finished else None,
            "filtrate_at_end_of_duration_m3": float(volume[-1]), "status": "completed" if finished else "incomplete",
            "violations": [] if finished else ["target_filtrate_not_reached"]}


def washing(c):
    t = grid(c)
    wash = c["wash_flow_m3_s"]*t
    remaining = c["initial_pore_impurity_kg"]*np.exp(-wash/c["retained_liquid_m3"])
    dissolved_product = np.minimum(c["initial_crystal_kg"], c["product_solubility_in_wash_kg_m3"]*wash)
    product = c["initial_crystal_kg"]-dissolved_product
    return {"trajectory": series(t, wash_volume_m3=wash, retained_impurity_kg=remaining, retained_product_kg=product),
            "retained_product_kg": float(product[-1]), "product_loss_kg": float(dissolved_product[-1]),
            "retained_impurity_kg": float(remaining[-1]), "wash_volume_m3": float(wash[-1]),
            "product_recovery_fraction": float(product[-1]/c["initial_crystal_kg"])}


def drying(c):
    if c["initial_solvent_kg_kg_dry"] < c["equilibrium_solvent_kg_kg_dry"]:
        raise ValueError("initial solvent must be >= equilibrium solvent for a drying-only model")
    if c["target_solvent_kg_kg_dry"] < c["equilibrium_solvent_kg_kg_dry"]:
        raise ValueError("target below equilibrium solvent is unreachable")
    if c["initial_temperature_k"] >= c["temperature_limit_k"]:
        raise ValueError("initial temperature reaches the task limit")
    def rhs(t, y):
        loss = c["drying_rate_s_inv"]*max(y[0]-c["equilibrium_solvent_kg_kg_dry"], 0.)
        heat = c["ua_w_k"]*(c["wall_temperature_k"]-y[1])-c["dry_solids_kg"]*loss*c["latent_heat_j_kg"]
        return [-loss, heat/(c["dry_solids_kg"]*c["solid_heat_capacity_j_kg_k"])]
    def hot(t, y): return c["temperature_limit_k"]-y[1]
    def cold(t, y): return y[1]-250.
    hot.terminal = cold.terminal = True
    hot.direction = cold.direction = -1
    t, y, sol = integrate(c, rhs, [c["initial_solvent_kg_kg_dry"], c["initial_temperature_k"]], events=[hot,cold])
    stopped = any(len(e) for e in sol.t_events)
    # The drying rate here does not depend on temperature or heat supply. A cake that ends colder than both its
    # starting temperature and the wall was dried on heat it never received, so dryness is not shown.
    unheated = not stopped and y[1,-1] < min(c["initial_temperature_k"], c["wall_temperature_k"]) - 1e-6
    reached = not stopped and not unheated and y[0,-1] <= c["target_solvent_kg_kg_dry"]
    return {"trajectory": series(t, solvent_kg_kg_dry=y[0], temperature_k=y[1]),
            "status": "stopped" if stopped else "completed",
            "final_solvent_kg_kg_dry": None if stopped else float(y[0,-1]),
            "solvent_target_met": bool(reached),
            "evaporated_solvent_kg": float(c["dry_solids_kg"]*(c["initial_solvent_kg_kg_dry"]-y[0,-1])),
            "violations": (["temperature_envelope_reached"] if stopped else []) + (["evaporation_exceeds_heat_supplied"] if unheated else [])
                          + ([] if reached else ["dryness_not_demonstrated"])}


MODELS = [
    Model("isolation.cake_filter", "api_isolation", "Constant-pressure incompressible cake filter",
          {"filter_area_m2": positive("m²", 1000), "pressure_difference_pa": positive("Pa", 1e7),
           "viscosity_pa_s": positive("Pa s", 100), "medium_resistance_m_inv": positive("1/m", 1e15),
           "cake_resistance_m_kg": Input("m/kg", 0, 1e16), "solids_per_filtrate_kg_m3": positive("kg/m³", 2000),
           "target_filtrate_m3": positive("m³", 1000), "duration_s": duration()},
          {"filtrate_m3":"m³", "cake_solids_kg":"kg"},
          "t=mu Rm Vf/(A dP)+mu alpha c Vf²/(2 A² dP)",
          ("Incompressible cake, constant pressure/viscosity, complete solids capture.",
           "No breakthrough, cloth fouling evolution, deliquoring or API dissolution."),
          filtration, "https://pmc.ncbi.nlm.nih.gov/articles/PMC11225065/"),
    Model("isolation.cake_wash", "api_isolation", "Well-mixed pore washing with solubility loss screen",
          {"retained_liquid_m3": positive("m³", 100), "wash_flow_m3_s": positive("m³/s", 1),
           "initial_pore_impurity_kg": Input("kg", 0, 1e6), "initial_crystal_kg": positive("kg", 1e6),
           "product_solubility_in_wash_kg_m3": Input("kg/m³",0,2000), "duration_s":duration()},
          {"retained_impurity_kg":"kg", "retained_product_kg":"kg", "wash_volume_m3":"m³"},
          "Mimp=Mimp0 exp(-Vwash/Vpore); product dissolution=min(Mproduct0,Csat Vwash)",
          ("Mixed-pore approximation, no displacement/channeling/adsorption.",
           "Product loss assumes each wash increment reaches solubility: screening assumption, not coupled dissolution kinetics."),
          washing, "https://pmc.ncbi.nlm.nih.gov/articles/PMC11225065/", "mechanistic_plus_screening_assumption"),
    Model("isolation.cake_dryer", "api_isolation", "Lumped first-order cake solvent drying",
          {"dry_solids_kg":positive("kg",1e6), "initial_solvent_kg_kg_dry":Input("kg/kg",0,10),
           "equilibrium_solvent_kg_kg_dry":Input("kg/kg",0,10), "target_solvent_kg_kg_dry":Input("kg/kg",0,10),
           "drying_rate_s_inv":positive("1/s",.1), "ua_w_k":Input("W/K",0,1e7),
           "latent_heat_j_kg":positive("J/kg",1e7), "solid_heat_capacity_j_kg_k":positive("J/(kg K)",10000),
           "initial_temperature_k":temperature(), "wall_temperature_k":temperature(),
           "temperature_limit_k":temperature(), "duration_s":duration()},
          {"solvent_kg_kg_dry":"kg/kg", "temperature_k":"K"},
          "dX/dt=-k(X-Xeq); Ms Cp dT/dt=UA(Twall-T)-Ms(-dX/dt)L",
          ("Effective drying coefficient needs experiments; no moisture spatial profile or vapor-pressure coupling.",
           "Constant solid thermal capacity; prescribed wall, no solvent-vapor transport/utility model.",
           "May leave the temperature envelope when heat is insufficient; final outcome is then withheld."),
          drying, "https://pmc.ncbi.nlm.nih.gov/articles/PMC11225065/", "semi_mechanistic")]
