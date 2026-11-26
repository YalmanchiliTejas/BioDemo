"""Explicit equipment screens; none supplies a universal scale-up correlation."""
import math
import numpy as np

from .common import Model, Input, positive, temperature, duration, grid, series


def mixing(c):
    re = c["density_kg_m3"]*c["speed_s_inv"]*c["impeller_diameter_m"]**2/c["viscosity_pa_s"]
    if re < 10000:
        raise ValueError("constant turbulent power-number screen requires Re >= 10,000; use another correlation")
    if c["impeller_count"] != int(c["impeller_count"]):
        raise ValueError("impeller count must be integral")
    power = c["impeller_count"]*c["power_number"]*c["density_kg_m3"]*c["speed_s_inv"]**3*c["impeller_diameter_m"]**5
    return {"reynolds_number":re, "power_w":power, "power_density_w_m3":power/c["working_volume_m3"],
            "tip_speed_m_s":math.pi*c["speed_s_inv"]*c["impeller_diameter_m"],
            "mixing_time_s":c["measured_dimensionless_mixing_time"]/c["speed_s_inv"],
            "warnings":["Dimensionless mixing time is supplied characterisation, not derived from power alone"]}


def vacuum(c):
    t = grid(c)
    equilibrium = 8.314462618*c["gas_temperature_k"]*c["gas_load_mol_s"]/c["effective_pumping_m3_s"]
    if c["target_pressure_pa"] >= c["initial_pressure_pa"]:
        raise ValueError("target pressure must be lower than initial pressure")
    pressure = equilibrium+(c["initial_pressure_pa"]-equilibrium)*np.exp(-c["effective_pumping_m3_s"]*t/c["chamber_volume_m3"])
    attainable = equilibrium < c["target_pressure_pa"]
    time = -c["chamber_volume_m3"]/c["effective_pumping_m3_s"]*math.log((c["target_pressure_pa"]-equilibrium)/(c["initial_pressure_pa"]-equilibrium)) if attainable else None
    reached = attainable and time <= c["duration_s"]
    return {"trajectory":series(t, pressure_pa=pressure), "steady_pressure_pa":equilibrium,
            "time_to_target_s":time if reached else None, "target_reachable_at_steady_state":attainable,
            "violations":[] if reached else ["target_pressure_not_reached_in_horizon"],
            "status":"completed" if reached else "incomplete"}


MODELS = [
    Model("utility.turbulent_mixing", "equipment_utilities", "Turbulent stirred-vessel power screen",
          {"density_kg_m3":positive("kg/m³",10000), "viscosity_pa_s":positive("Pa s",1000),
           "speed_s_inv":positive("1/s",100), "impeller_diameter_m":positive("m",10),
           "impeller_count":positive("count",20), "power_number":positive("dimensionless",100),
           "working_volume_m3":positive("m³",1000), "measured_dimensionless_mixing_time":positive("dimensionless",1e6)},
          {"power_w":"W", "power_density_w_m3":"W/m³", "mixing_time_s":"s"},
          "Re=rho N D²/mu; P=nimp Np rho N³D⁵; tm=(measured N tm)/N",
          ("Requires matched impeller/baffle geometry and turbulent characterised power number.",
           "No CFD, local shear, gas dispersion or oxygen-transfer prediction.",
           "Adding impeller powers assumes independent contributions; interaction is not resolved."),
          mixing, "Turbulent impeller power-number relation; mixing time requires measured correlation", axis="none"),
    Model("utility.ideal_vacuum", "equipment_utilities", "Ideal chamber pump-down with constant gas load",
          {"chamber_volume_m3":positive("m³",10000), "effective_pumping_m3_s":positive("m³/s",1000),
           "initial_pressure_pa":positive("Pa",2e5), "target_pressure_pa":positive("Pa",2e5),
           "gas_load_mol_s":Input("mol/s",0,100), "gas_temperature_k":temperature(), "duration_s":duration()},
          {"pressure_pa":"Pa"}, "V dP/dt=R T ndot-S P; constant T, load and effective pumping speed",
          ("Ideal-gas, isothermal, constant effective chamber pumping speed.",
           "No pressure-dependent pump curve, conductance network, condensation or sublimation coupling.",
           "Not a replacement for the existing freeze-drying pressure/capacity assessment."),
          vacuum, "Ideal-gas inventory balance")]
