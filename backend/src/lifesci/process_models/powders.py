"""Reduced powder models; effective rates must be measured for the formulation."""
import numpy as np

from .common import Model, Input, positive, fraction, duration, grid, series


def blender(c):
    t = grid(c)
    tau = c["hold_up_kg"]/c["mass_flow_kg_s"]
    inlet = np.where(t < c["step_time_s"], c["inlet_before_fraction"], c["inlet_after_fraction"])
    before = c["inlet_before_fraction"]+(c["initial_fraction"]-c["inlet_before_fraction"])*np.exp(-np.minimum(t,c["step_time_s"])/tau)
    at_step = c["inlet_before_fraction"]+(c["initial_fraction"]-c["inlet_before_fraction"])*np.exp(-c["step_time_s"]/tau)
    after = c["inlet_after_fraction"]+(at_step-c["inlet_after_fraction"])*np.exp(-np.maximum(0,t-c["step_time_s"])/tau)
    output = np.where(t <= c["step_time_s"], before, after)
    return {"trajectory":series(t, inlet_fraction=inlet, outlet_fraction=output), "residence_time_s":tau,
            "final_outlet_fraction":float(output[-1]),
            "warnings":["Mean composition response is not tablet content-uniformity or segregation prediction"]}


def milling(c):
    t = grid(c)
    coarse = c["initial_coarse_fraction"]*np.exp(-c["breakage_rate_s_inv"]*t)
    fine = 1-coarse
    return {"trajectory":series(t, coarse_mass_fraction=coarse, fine_mass_fraction=fine),
            "final_coarse_fraction":float(coarse[-1]), "maximum_mass_fraction_error":float(np.max(np.abs(coarse+fine-1)))}


def granulation(c):
    if c["solids_kg_m3"] > c["solid_density_kg_m3"]:
        raise ValueError("solids inventory exceeds the available unit-volume solid capacity")
    t = grid(c)
    number = c["initial_number_m3"]/(1+c["aggregation_coefficient_m3_s"]*c["initial_number_m3"]*t)
    # dN/dt=-K N²; K includes the pair-count convention. Solid volume is conserved.
    diameter = (c["solids_kg_m3"]/(c["solid_density_kg_m3"]*c["shape_factor"]*number))**(1/3)
    return {"trajectory":series(t, granule_number_m3=number, equivalent_diameter_m=diameter),
            "final_equivalent_diameter_m":float(diameter[-1]),
            "maximum_solid_inventory_error_kg_m3":float(np.max(np.abs(c["solid_density_kg_m3"]*c["shape_factor"]*number*diameter**3-c["solids_kg_m3"])))}


MODELS = [
    Model("powder.continuous_blender", "powder_processing", "Ideal continuous blender composition response",
          {"hold_up_kg":positive("kg",1e6), "mass_flow_kg_s":positive("kg/s",1000),
           "initial_fraction":fraction(), "inlet_before_fraction":fraction(), "inlet_after_fraction":fraction(),
           "step_time_s":Input("s",0,604800), "duration_s":duration()},
          {"outlet_fraction":"mass fraction", "inlet_fraction":"mass fraction"},
          "M dx/dt=F(xin-x); constant holdup and a single inlet-composition step",
          ("Ideal CSTR residence-time approximation; no segregation, dead zones or particle-level variability.",
           "No claim of individual-dose content uniformity; requires measured residence-time validation."),
          blender, "https://doi.org/10.3390/pr7040234"),
    Model("powder.two_bin_mill", "powder_processing", "Two-size-class milling reduction",
          {"initial_coarse_fraction":fraction(), "breakage_rate_s_inv":Input("1/s",0,1), "duration_s":duration()},
          {"coarse_mass_fraction":"mass fraction", "fine_mass_fraction":"mass fraction"},
          "dfcoarse/dt=-k fcoarse; ffine=1-fcoarse",
          ("Two mass bins with complete transfer from coarse to fine; not a resolved particle size distribution.",
           "No heat, wear, overmilling or mechanistic speed-to-breakage relationship."),
          milling, "https://doi.org/10.3390/pr1020067", "lumped_kinetic"),
    Model("powder.aggregation_granulator", "powder_processing", "Constant-kernel granule aggregation screen",
          {"initial_number_m3":positive("1/m³",1e16), "aggregation_coefficient_m3_s":Input("m³/s",0,1e-6),
           "solids_kg_m3":positive("kg/m³",2000), "solid_density_kg_m3":positive("kg/m³",10000),
           "shape_factor":positive("dimensionless",10), "duration_s":duration()},
          {"granule_number_m3":"1/m³", "equivalent_diameter_m":"m"},
          "dN/dt=-K N²; rho kv N d³=constant solids inventory",
          ("Monodisperse-equivalent aggregation, no breakage, binder redistribution, wetting or moisture dynamics.",
           "K is an effective fitted parameter; not a transferable equipment-speed correlation."),
          granulation, "https://doi.org/10.3390/pr1020067")]
