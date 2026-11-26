"""Formulation-dependent compaction, coating deposition and shrinking-area dissolution."""
import numpy as np

from .common import Model, Input, positive, fraction, duration, grid, integrate, series


def compaction(c):
    pressures = np.linspace(0,c["maximum_pressure_pa"],201)
    porosity = (1-c["initial_relative_density"])*np.exp(-c["heckel_coefficient_pa_inv"]*pressures)
    tensile = c["zero_porosity_strength_pa"]*np.exp(-c["strength_porosity_coefficient"]*porosity)
    return {"trajectory":[{"pressure_pa":float(p), "relative_density":float(1-e), "porosity":float(e),
                           "tensile_strength_pa":float(s)} for p,e,s in zip(pressures,porosity,tensile)],
            "final_relative_density":float(1-porosity[-1]), "final_tensile_strength_pa":float(tensile[-1]),
            "warnings":["Pressure is the independent axis; dwell time/press speed are not represented"]}


def coating(c):
    t = grid(c)
    sprayed = c["suspension_flow_kg_s"]*c["suspension_solids_fraction"]*t
    deposited = sprayed*c["deposition_efficiency"]
    thickness = deposited/(c["coat_density_kg_m3"]*c["total_surface_area_m2"])
    return {"trajectory":series(t, deposited_coat_kg=deposited, mean_coat_thickness_m=thickness,
                                  lost_coat_solids_kg=sprayed-deposited),
            "final_mean_coat_thickness_m":float(thickness[-1]), "deposited_coat_kg":float(deposited[-1])}


def dissolution(c):
    m0, cap = c["initial_drug_mass_kg"], c["solubility_kg_m3"]*c["medium_volume_m3"]
    def rhs(t,y):
        remaining = max(1-y[0]/m0,0.)
        driving = max(c["solubility_kg_m3"]-y[0]/c["medium_volume_m3"],0.)
        return [c["mass_transfer_m_s"]*c["initial_area_m2"]*remaining**(2/3)*driving]
    t, y, _ = integrate(c,rhs,[0.],atol=m0*1e-10)
    dissolved = y[0]
    if dissolved.min() < -1e-8*m0 or dissolved.max() > min(m0,cap)+1e-7*m0:
        raise ValueError("dissolution exceeded drug inventory or solubility capacity")
    dissolved = np.minimum(np.maximum(dissolved,0.),min(m0,cap))
    return {"trajectory":series(t, dissolved_drug_kg=dissolved, dissolved_fraction=dissolved/m0),
            "final_dissolved_fraction":float(dissolved[-1]/m0),
            "equilibrium_capacity_fraction":float(min(1,cap/m0)),
            "warnings":["No inference of bioequivalence, bioavailability or in-vivo efficacy"]}


MODELS = [
    Model("tablet.heckel_compaction", "tablet_manufacturing", "Heckel density and empirical strength screen",
          {"initial_relative_density":Input("fraction",.01,.99), "heckel_coefficient_pa_inv":positive("1/Pa",1e-5),
           "maximum_pressure_pa":positive("Pa",1e9), "zero_porosity_strength_pa":positive("Pa",1e9),
           "strength_porosity_coefficient":positive("dimensionless",100)},
          {"relative_density":"fraction", "porosity":"fraction", "tensile_strength_pa":"Pa"},
          "1-D=(1-D0) exp(-K P); strength=strength0 exp(-b porosity)",
          ("Empirical formulation-specific relationships; not first-principles deformation.",
           "No dwell-time, elastic recovery, lubrication, capping, lamination or dissolution linkage.",
           "Use only within experimentally fitted pressure intervals."),
          compaction, "https://doi.org/10.3390/pr1020067", "empirical", axis="pressure_pa"),
    Model("tablet.coating_deposition", "tablet_manufacturing", "Mean film-coat deposition balance",
          {"suspension_flow_kg_s":positive("kg/s",10), "suspension_solids_fraction":fraction(),
           "deposition_efficiency":fraction(), "coat_density_kg_m3":positive("kg/m³",10000),
           "total_surface_area_m2":positive("m²",1e6), "duration_s":duration()},
          {"deposited_coat_kg":"kg", "mean_coat_thickness_m":"m", "lost_coat_solids_kg":"kg"},
          "mcoat=eta F xsolid t; mean thickness=mcoat/(rho area)",
          ("Thin uniform-film mean only; fixed area, no spray/bed distribution or solvent drying.",
           "Efficiency must be characterised; mean thickness does not establish dose uniformity or release performance."),
          coating, "mass conservation with explicitly assumed deposition efficiency"),
    Model("tablet.shrinking_area_dissolution", "tablet_manufacturing", "Finite-medium shrinking-area dissolution",
          {"initial_drug_mass_kg":positive("kg",1), "initial_area_m2":positive("m²",1e4),
           "mass_transfer_m_s":positive("m/s",.1), "solubility_kg_m3":positive("kg/m³",2000),
           "medium_volume_m3":positive("m³",10), "duration_s":duration()},
          {"dissolved_drug_kg":"kg", "dissolved_fraction":"fraction"},
          "dm/dt=k A0(1-m/m0)^(2/3)(Csat-m/Vmedium)",
          ("Equivalent shrinking surface with constant solubility and mass-transfer coefficient.",
           "No tablet disintegration, swelling, diffusion through a matrix, precipitation, pH changes or absorption.",
           "Not automatically coupled to compaction/coating: that mapping requires formulation-specific evidence."),
          dissolution, "https://pubmed.ncbi.nlm.nih.gov/16421665/")]
