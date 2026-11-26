"""Authored learning assumptions, never published or customer measurements."""
from copy import deepcopy

from ..chemical_reactor.demo import example as batch_example


def examples():
    chemistry=batch_example()["chemistry"]
    cases={
        "chemical.semi_batch":{**chemistry,"initial_volume_m3":.01,"maximum_volume_m3":.03,
            "initial_a_mol_m3":1000.,"initial_temperature_k":298.15,"heat_transfer_area_m2":.15,
            "heat_transfer_coefficient_w_m2_k":350.,"coolant_temperature_k":293.15,
            "feed_flow_m3_s":1e-6,"feed_a_mol_m3":2000.,"feed_temperature_k":293.15,
            "feed_until_s":1800.,"temperature_limit_k":345.,"duration_s":7200.},
        "crystal.cooling_moments":{"liquid_volume_m3":.01,"initial_solute_kg_m3":100.,
            "start_temperature_k":313.15,"end_temperature_k":293.15,"reference_temperature_k":313.15,
            "solubility_ref_kg_m3":100.,"solubility_slope_k_inv":.03,"crystal_density_kg_m3":1500.,
            "shape_factor":.5235987756,"seed_number_m3":1e10,"seed_size_m":50e-6,
            "nucleus_size_m":1e-6,"growth_rate_m_s":2e-8,"growth_exponent":1.,
            "nucleation_rate_m3_s":1e8,"nucleation_exponent":2.,"duration_s":7200.},
        "isolation.cake_filter":{"filter_area_m2":.02,"pressure_difference_pa":80000.,"viscosity_pa_s":.001,
            "medium_resistance_m_inv":1e10,"cake_resistance_m_kg":1e10,"solids_per_filtrate_kg_m3":50.,
            "target_filtrate_m3":.01,"duration_s":1800.},
        "isolation.cake_wash":{"retained_liquid_m3":.001,"wash_flow_m3_s":1e-6,
            "initial_pore_impurity_kg":.01,"initial_crystal_kg":1.,"product_solubility_in_wash_kg_m3":.5,"duration_s":3600.},
        "isolation.cake_dryer":{"dry_solids_kg":10.,"initial_solvent_kg_kg_dry":.2,
            "equilibrium_solvent_kg_kg_dry":.001,"target_solvent_kg_kg_dry":.01,"drying_rate_s_inv":.0005,
            "ua_w_k":100.,"latent_heat_j_kg":800000.,"solid_heat_capacity_j_kg_k":1500.,
            "initial_temperature_k":293.15,"wall_temperature_k":313.15,"temperature_limit_k":350.,"duration_s":7200.},
        "powder.continuous_blender":{"hold_up_kg":10.,"mass_flow_kg_s":.1,"initial_fraction":.1,
            "inlet_before_fraction":.1,"inlet_after_fraction":.2,"step_time_s":200.,"duration_s":1000.},
        "powder.two_bin_mill":{"initial_coarse_fraction":.8,"breakage_rate_s_inv":.002,"duration_s":1800.},
        "powder.aggregation_granulator":{"initial_number_m3":1e10,"aggregation_coefficient_m3_s":1e-13,
            "solids_kg_m3":200.,"solid_density_kg_m3":1500.,"shape_factor":.5235987756,"duration_s":1800.},
        "tablet.heckel_compaction":{"initial_relative_density":.4,"heckel_coefficient_pa_inv":1e-8,
            "maximum_pressure_pa":2e8,"zero_porosity_strength_pa":1e7,"strength_porosity_coefficient":8.},
        "tablet.coating_deposition":{"suspension_flow_kg_s":.001,"suspension_solids_fraction":.1,
            "deposition_efficiency":.8,"coat_density_kg_m3":1200.,"total_surface_area_m2":10.,"duration_s":3600.},
        "tablet.shrinking_area_dissolution":{"initial_drug_mass_kg":.0001,"initial_area_m2":.001,
            "mass_transfer_m_s":1e-5,"solubility_kg_m3":1.,"medium_volume_m3":.0009,"duration_s":3600.},
        "downstream.equilibrium_capture":{"initial_product_kg":.1,"liquid_volume_m3":.01,
            "resin_mass_kg":2.,"capacity_kg_kg_resin":.1,"affinity_m3_kg":1.,"elution_recovery_fraction":.95},
        "membrane.ultrafiltration":{"initial_volume_m3":.02,"target_volume_m3":.005,"initial_product_kg":.1,
            "membrane_area_m2":.5,"permeate_flux_m_s":1e-5,"product_sieving":.02,"duration_s":3600.},
        "membrane.diafiltration":{"retentate_volume_m3":.005,"initial_product_kg":.1,"initial_impurity_kg":.01,
            "membrane_area_m2":.5,"permeate_flux_m_s":1e-5,"product_sieving":.02,"impurity_sieving":1.,"duration_s":5000.},
        "utility.turbulent_mixing":{"density_kg_m3":1000.,"viscosity_pa_s":.001,"speed_s_inv":5.,
            "impeller_diameter_m":.1,"impeller_count":1.,"power_number":5.,"working_volume_m3":.01,
            "measured_dimensionless_mixing_time":30.},
        "utility.ideal_vacuum":{"chamber_volume_m3":1.,"effective_pumping_m3_s":.01,"initial_pressure_pa":100000.,
            "target_pressure_pa":100.,"gas_load_mol_s":.00001,"gas_temperature_k":298.15,"duration_s":1200.},
    }
    for model_id,c in cases.items():
        c.update(evidence_classification="synthetic_learning_assumptions_not_experimental_data",
                 source_refs=["authored-process-library-example:"+model_id])
    return deepcopy(cases)
