"""Equilibrium resin screen and ideal membrane balances, not column hydraulics."""
import numpy as np
from scipy.optimize import brentq

from .common import Model, Input, positive, fraction, duration, grid, series


def capture(c):
    total = c["initial_product_kg"]
    def bound(concentration):
        return c["resin_mass_kg"]*c["capacity_kg_kg_resin"]*c["affinity_m3_kg"]*concentration/(1+c["affinity_m3_kg"]*concentration)
    concentration = brentq(lambda x: c["liquid_volume_m3"]*x+bound(x)-total,
                           0.,total/c["liquid_volume_m3"],xtol=1e-14)
    loaded = bound(concentration)
    recovered = loaded*c["elution_recovery_fraction"]
    return {"equilibrium_liquid_concentration_kg_m3":concentration,
            "bound_product_kg":loaded, "unbound_product_kg":concentration*c["liquid_volume_m3"],
            "recovered_product_kg":recovered, "elution_loss_kg":loaded-recovered,
            "recovery_fraction":recovered/total,
            "maximum_inventory_error_kg":abs(total-loaded-concentration*c["liquid_volume_m3"]),
            "warnings":["Equilibrium batch contact only: no chromatography breakthrough or purity forecast"]}


def ultrafiltration(c):
    volume0, volume1 = c["initial_volume_m3"], c["target_volume_m3"]
    if volume1 >= volume0:
        raise ValueError("concentration phase requires target volume below initial volume")
    q = c["membrane_area_m2"]*c["permeate_flux_m_s"]
    completion = (volume0-volume1)/q
    t = np.unique(np.r_[grid(c),min(completion,c["duration_s"])])
    volumes = np.maximum(volume0-q*t,volume1)
    mass = c["initial_product_kg"]*(volumes/volume0)**c["product_sieving"]
    done = completion <= c["duration_s"]
    return {"trajectory":series(t, retentate_volume_m3=volumes, retentate_product_kg=mass,
                                  product_concentration_kg_m3=mass/volumes),
            "status":"completed" if done else "incomplete", "completion_time_s":completion if done else None,
            "retained_product_kg":float(mass[-1]), "permeate_product_kg":float(c["initial_product_kg"]-mass[-1]),
            "final_volume_m3":float(volumes[-1]), "recovery_fraction":float(mass[-1]/c["initial_product_kg"]),
            "violations":[] if done else ["target_volume_not_reached"]}


def diafiltration(c):
    t = grid(c)
    n = c["membrane_area_m2"]*c["permeate_flux_m_s"]*t/c["retentate_volume_m3"]
    product = c["initial_product_kg"]*np.exp(-c["product_sieving"]*n)
    impurity = c["initial_impurity_kg"]*np.exp(-c["impurity_sieving"]*n)
    return {"trajectory":series(t, diavolumes=n, retained_product_kg=product, retained_impurity_kg=impurity),
            "final_diavolumes":float(n[-1]), "buffer_volume_m3":float(n[-1]*c["retentate_volume_m3"]),
            "retained_product_kg":float(product[-1]), "retained_impurity_kg":float(impurity[-1]),
            "recovery_fraction":float(product[-1]/c["initial_product_kg"]),
            "permeate_product_kg":float(c["initial_product_kg"]-product[-1]),
            "impurity_remaining_fraction":float(np.exp(-c["impurity_sieving"]*n[-1]))}


MEMBRANE_LIMITS = ("Well-mixed ideal membrane balance with constant flux and sieving coefficients.",
                   "No fouling, concentration polarisation, binding, viscosity or transmembrane-pressure prediction.",
                   "Product loss is modelled passage only; degradation/aggregation/adsorption need separate evidence.")
MODELS = [
    Model("downstream.equilibrium_capture", "biologics_downstream", "Langmuir batch resin capture screen",
          {"initial_product_kg":positive("kg",1e6), "liquid_volume_m3":positive("m³",1000),
           "resin_mass_kg":positive("kg",1e6), "capacity_kg_kg_resin":positive("kg/kg",10),
           "affinity_m3_kg":positive("m³/kg",1e9), "elution_recovery_fraction":fraction()},
          {"recovery_fraction":"fraction", "recovered_product_kg":"kg"},
          "Mtotal=V C+Mresin qmax K C/(1+K C); recovered=bound times specified elution recovery",
          ("Single-solute equilibrium batch adsorption, not a dynamic chromatography column.",
           "No impurity selectivity or competition; recovery does not establish purification.",
           "Elution recovery is supplied empirical evidence, not a prediction of elution."),
          capture, "Langmuir equilibrium isotherm and finite-volume material balance", axis="none"),
    Model("membrane.ultrafiltration", "biologics_downstream", "Constant-flux ultrafiltration concentration",
          {"initial_volume_m3":positive("m³",1000), "target_volume_m3":positive("m³",1000),
           "initial_product_kg":positive("kg",1e6), "membrane_area_m2":positive("m²",10000),
           "permeate_flux_m_s":positive("m/s",.001), "product_sieving":fraction(), "duration_s":duration()},
          {"retentate_volume_m3":"m³", "retentate_product_kg":"kg", "product_concentration_kg_m3":"kg/m³"},
          "dV/dt=-A J; dM/dt=-S A J M/V; M=M0(V/V0)^S", MEMBRANE_LIMITS,
          ultrafiltration, "https://www.merckmillipore.com/deepweb/assets/sigmaaldrich/product/documents/272/805/rf1159en-ms.pdf"),
    Model("membrane.diafiltration", "biologics_downstream", "Constant-volume ideal diafiltration",
          {"retentate_volume_m3":positive("m³",1000), "initial_product_kg":positive("kg",1e6),
           "initial_impurity_kg":Input("kg",0,1e6), "membrane_area_m2":positive("m²",10000),
           "permeate_flux_m_s":positive("m/s",.001), "product_sieving":fraction(),
           "impurity_sieving":fraction(), "duration_s":duration()},
          {"diavolumes":"dimensionless", "retained_product_kg":"kg", "retained_impurity_kg":"kg"},
          "N=A J t/V; Mi=Mi0 exp(-Si N); buffer inflow equals permeate outflow", MEMBRANE_LIMITS,
          diafiltration, "https://www.merckmillipore.com/deepweb/assets/sigmaaldrich/product/documents/272/805/rf1159en-ms.pdf")]
