# Model passports

All new examples are synthetic. Input bounds are numerical/task bounds, not experimentally qualified operating envelopes.

## chemical.semi_batch

Fed chemical reactor with competing impurity

**Family:** chemical_synthesis; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `dNA/dt=Q CAfeed-(kB+kI)NA; dNB/dt=kB NA; V=V0+Q min(t,tfeed); energy includes feed sensible heat`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `reference_temperature_k` | K | >= 250; <= 450 |
| `product_rate_ref_s_inv` | 1/s | >= 0; <= 0.1 |
| `impurity_rate_ref_s_inv` | 1/s | >= 0; <= 0.1 |
| `product_activation_j_mol` | J/mol | >= 0; <= 150000 |
| `impurity_activation_j_mol` | J/mol | >= 0; <= 150000 |
| `product_enthalpy_j_mol` | J/mol | >= -300000; <= 300000 |
| `impurity_enthalpy_j_mol` | J/mol | >= -300000; <= 300000 |
| `density_kg_m3` | kg/m³ | > 0; <= 10000 |
| `heat_capacity_j_kg_k` | J/(kg K) | > 0; <= 10000 |
| `initial_volume_m3` | m³ | > 0; <= 1000 |
| `maximum_volume_m3` | m³ | > 0; <= 1000 |
| `initial_a_mol_m3` | mol/m³ | > 0; <= 100000 |
| `initial_temperature_k` | K | >= 250; <= 450 |
| `heat_transfer_area_m2` | m² | > 0; <= 10000 |
| `heat_transfer_coefficient_w_m2_k` | W/(m² K) | >= 0; <= 10000 |
| `coolant_temperature_k` | K | >= 250; <= 450 |
| `feed_flow_m3_s` | m³/s | >= 0; <= 1 |
| `feed_a_mol_m3` | mol/m³ | >= 0; <= 100000 |
| `feed_temperature_k` | K | >= 250; <= 450 |
| `feed_until_s` | s | >= 0; <= 604800 |
| `temperature_limit_k` | K | >= 250; <= 450 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `a_mol` | mol |
| `product_mol` | mol |
| `impurity_mol` | mol |
| `temperature_k` | K |
| `volume_m3` | m³ |
| `product_yield_fraction` | fraction |

Limitations:

- Reuses existing batch chemistry rate laws, constant density/Cp, no evaporation or nonideal mixing.
- Prescribed wetted area and coolant boundary; no jacket, chiller or area-vs-fill model.
- Two irreversible 1:1 pathways; not arbitrary reaction networks or validated isolated yield.

Method context: Conservation balances; shared kinetics from chemical_reactor/model.py

## crystal.cooling_moments

Cooling crystallizer with population moments

**Family:** crystallization; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `dmj/dt=j G m(j-1)+B Ln^j; dc/dt=-rho kv dm3/dt; prescribed cooling and exponential solubility`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `liquid_volume_m3` | m³ | > 0; <= 1000 |
| `initial_solute_kg_m3` | kg/m³ | > 0; <= 2000 |
| `start_temperature_k` | K | >= 250; <= 450 |
| `end_temperature_k` | K | >= 250; <= 450 |
| `reference_temperature_k` | K | >= 250; <= 450 |
| `solubility_ref_kg_m3` | kg/m³ | > 0; <= 2000 |
| `solubility_slope_k_inv` | 1/K | >= 0; <= 0.2 |
| `crystal_density_kg_m3` | kg/m³ | > 0; <= 10000 |
| `shape_factor` | dimensionless | > 0; <= 10 |
| `seed_number_m3` | 1/m³ | > 0; <= 1e+16 |
| `seed_size_m` | m | > 0; <= 0.01 |
| `nucleus_size_m` | m | > 0; <= 0.001 |
| `growth_rate_m_s` | m/s | >= 0; <= 0.001 |
| `growth_exponent` | dimensionless | >= 1; <= 5 |
| `nucleation_rate_m3_s` | 1/(m³ s) | >= 0; <= 1e+16 |
| `nucleation_exponent` | dimensionless | >= 1; <= 5 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `solute_kg_m3` | kg/m³ |
| `crystal_kg_m3` | kg/m³ |
| `number_mean_size_m` | m |
| `surface_volume_size_m` | m |

Limitations:

- Well-mixed dilute suspension, constant liquid volume, no agglomeration/breakage/dissolution/polymorphism.
- Temperature profile is prescribed; receiving cooling capability is not solved.
- Kinetics/solubility require compound-specific measurements; seed-inclusive recovery is not purity.

Method context: https://pharmapy.readthedocs.io/en/latest/docstrings/unit_operations.html

## isolation.cake_filter

Constant-pressure incompressible cake filter

**Family:** api_isolation; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `t=mu Rm Vf/(A dP)+mu alpha c Vf²/(2 A² dP)`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `filter_area_m2` | m² | > 0; <= 1000 |
| `pressure_difference_pa` | Pa | > 0; <= 1e+07 |
| `viscosity_pa_s` | Pa s | > 0; <= 100 |
| `medium_resistance_m_inv` | 1/m | > 0; <= 1e+15 |
| `cake_resistance_m_kg` | m/kg | >= 0; <= 1e+16 |
| `solids_per_filtrate_kg_m3` | kg/m³ | > 0; <= 2000 |
| `target_filtrate_m3` | m³ | > 0; <= 1000 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `filtrate_m3` | m³ |
| `cake_solids_kg` | kg |

Limitations:

- Incompressible cake, constant pressure/viscosity, complete solids capture.
- No breakthrough, cloth fouling evolution, deliquoring or API dissolution.

Method context: https://pmc.ncbi.nlm.nih.gov/articles/PMC11225065/

## isolation.cake_wash

Well-mixed pore washing with solubility loss screen

**Family:** api_isolation; **type:** mechanistic_plus_screening_assumption; **axis:** time_s.

Equation: `Mimp=Mimp0 exp(-Vwash/Vpore); product dissolution=min(Mproduct0,Csat Vwash)`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `retained_liquid_m3` | m³ | > 0; <= 100 |
| `wash_flow_m3_s` | m³/s | > 0; <= 1 |
| `initial_pore_impurity_kg` | kg | >= 0; <= 1e+06 |
| `initial_crystal_kg` | kg | > 0; <= 1e+06 |
| `product_solubility_in_wash_kg_m3` | kg/m³ | >= 0; <= 2000 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `retained_impurity_kg` | kg |
| `retained_product_kg` | kg |
| `wash_volume_m3` | m³ |

Limitations:

- Mixed-pore approximation, no displacement/channeling/adsorption.
- Product loss assumes each wash increment reaches solubility: screening assumption, not coupled dissolution kinetics.

Method context: https://pmc.ncbi.nlm.nih.gov/articles/PMC11225065/

## isolation.cake_dryer

Lumped first-order cake solvent drying

**Family:** api_isolation; **type:** semi_mechanistic; **axis:** time_s.

Equation: `dX/dt=-k(X-Xeq); Ms Cp dT/dt=UA(Twall-T)-Ms(-dX/dt)L`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `dry_solids_kg` | kg | > 0; <= 1e+06 |
| `initial_solvent_kg_kg_dry` | kg/kg | >= 0; <= 10 |
| `equilibrium_solvent_kg_kg_dry` | kg/kg | >= 0; <= 10 |
| `target_solvent_kg_kg_dry` | kg/kg | >= 0; <= 10 |
| `drying_rate_s_inv` | 1/s | > 0; <= 0.1 |
| `ua_w_k` | W/K | >= 0; <= 1e+07 |
| `latent_heat_j_kg` | J/kg | > 0; <= 1e+07 |
| `solid_heat_capacity_j_kg_k` | J/(kg K) | > 0; <= 10000 |
| `initial_temperature_k` | K | >= 250; <= 450 |
| `wall_temperature_k` | K | >= 250; <= 450 |
| `temperature_limit_k` | K | >= 250; <= 450 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `solvent_kg_kg_dry` | kg/kg |
| `temperature_k` | K |

Limitations:

- Effective drying coefficient needs experiments; no moisture spatial profile or vapor-pressure coupling.
- Constant solid thermal capacity; prescribed wall, no solvent-vapor transport/utility model.
- May leave the temperature envelope when heat is insufficient; final outcome is then withheld.

Method context: https://pmc.ncbi.nlm.nih.gov/articles/PMC11225065/

## powder.continuous_blender

Ideal continuous blender composition response

**Family:** powder_processing; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `M dx/dt=F(xin-x); constant holdup and a single inlet-composition step`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `hold_up_kg` | kg | > 0; <= 1e+06 |
| `mass_flow_kg_s` | kg/s | > 0; <= 1000 |
| `initial_fraction` | fraction | >= 0; <= 1 |
| `inlet_before_fraction` | fraction | >= 0; <= 1 |
| `inlet_after_fraction` | fraction | >= 0; <= 1 |
| `step_time_s` | s | >= 0; <= 604800 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `outlet_fraction` | mass fraction |
| `inlet_fraction` | mass fraction |

Limitations:

- Ideal CSTR residence-time approximation; no segregation, dead zones or particle-level variability.
- No claim of individual-dose content uniformity; requires measured residence-time validation.

Method context: https://doi.org/10.3390/pr7040234

## powder.two_bin_mill

Two-size-class milling reduction

**Family:** powder_processing; **type:** lumped_kinetic; **axis:** time_s.

Equation: `dfcoarse/dt=-k fcoarse; ffine=1-fcoarse`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `initial_coarse_fraction` | fraction | >= 0; <= 1 |
| `breakage_rate_s_inv` | 1/s | >= 0; <= 1 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `coarse_mass_fraction` | mass fraction |
| `fine_mass_fraction` | mass fraction |

Limitations:

- Two mass bins with complete transfer from coarse to fine; not a resolved particle size distribution.
- No heat, wear, overmilling or mechanistic speed-to-breakage relationship.

Method context: https://doi.org/10.3390/pr1020067

## powder.aggregation_granulator

Constant-kernel granule aggregation screen

**Family:** powder_processing; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `dN/dt=-K N²; rho kv N d³=constant solids inventory`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `initial_number_m3` | 1/m³ | > 0; <= 1e+16 |
| `aggregation_coefficient_m3_s` | m³/s | >= 0; <= 1e-06 |
| `solids_kg_m3` | kg/m³ | > 0; <= 2000 |
| `solid_density_kg_m3` | kg/m³ | > 0; <= 10000 |
| `shape_factor` | dimensionless | > 0; <= 10 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `granule_number_m3` | 1/m³ |
| `equivalent_diameter_m` | m |

Limitations:

- Monodisperse-equivalent aggregation, no breakage, binder redistribution, wetting or moisture dynamics.
- K is an effective fitted parameter; not a transferable equipment-speed correlation.

Method context: https://doi.org/10.3390/pr1020067

## tablet.heckel_compaction

Heckel density and empirical strength screen

**Family:** tablet_manufacturing; **type:** empirical; **axis:** pressure_pa.

Equation: `1-D=(1-D0) exp(-K P); strength=strength0 exp(-b porosity)`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `initial_relative_density` | fraction | >= 0.01; <= 0.99 |
| `heckel_coefficient_pa_inv` | 1/Pa | > 0; <= 1e-05 |
| `maximum_pressure_pa` | Pa | > 0; <= 1e+09 |
| `zero_porosity_strength_pa` | Pa | > 0; <= 1e+09 |
| `strength_porosity_coefficient` | dimensionless | > 0; <= 100 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `relative_density` | fraction |
| `porosity` | fraction |
| `tensile_strength_pa` | Pa |

Limitations:

- Empirical formulation-specific relationships; not first-principles deformation.
- No dwell-time, elastic recovery, lubrication, capping, lamination or dissolution linkage.
- Use only within experimentally fitted pressure intervals.

Method context: https://doi.org/10.3390/pr1020067

## tablet.coating_deposition

Mean film-coat deposition balance

**Family:** tablet_manufacturing; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `mcoat=eta F xsolid t; mean thickness=mcoat/(rho area)`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `suspension_flow_kg_s` | kg/s | > 0; <= 10 |
| `suspension_solids_fraction` | fraction | >= 0; <= 1 |
| `deposition_efficiency` | fraction | >= 0; <= 1 |
| `coat_density_kg_m3` | kg/m³ | > 0; <= 10000 |
| `total_surface_area_m2` | m² | > 0; <= 1e+06 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `deposited_coat_kg` | kg |
| `mean_coat_thickness_m` | m |
| `lost_coat_solids_kg` | kg |

Limitations:

- Thin uniform-film mean only; fixed area, no spray/bed distribution or solvent drying.
- Efficiency must be characterised; mean thickness does not establish dose uniformity or release performance.

Method context: mass conservation with explicitly assumed deposition efficiency

## tablet.shrinking_area_dissolution

Finite-medium shrinking-area dissolution

**Family:** tablet_manufacturing; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `dm/dt=k A0(1-m/m0)^(2/3)(Csat-m/Vmedium)`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `initial_drug_mass_kg` | kg | > 0; <= 1 |
| `initial_area_m2` | m² | > 0; <= 10000 |
| `mass_transfer_m_s` | m/s | > 0; <= 0.1 |
| `solubility_kg_m3` | kg/m³ | > 0; <= 2000 |
| `medium_volume_m3` | m³ | > 0; <= 10 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `dissolved_drug_kg` | kg |
| `dissolved_fraction` | fraction |

Limitations:

- Equivalent shrinking surface with constant solubility and mass-transfer coefficient.
- No tablet disintegration, swelling, diffusion through a matrix, precipitation, pH changes or absorption.
- Not automatically coupled to compaction/coating: that mapping requires formulation-specific evidence.

Method context: https://pubmed.ncbi.nlm.nih.gov/16421665/

## downstream.equilibrium_capture

Langmuir batch resin capture screen

**Family:** biologics_downstream; **type:** reduced_mechanistic; **axis:** none.

Equation: `Mtotal=V C+Mresin qmax K C/(1+K C); recovered=bound times specified elution recovery`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `initial_product_kg` | kg | > 0; <= 1e+06 |
| `liquid_volume_m3` | m³ | > 0; <= 1000 |
| `resin_mass_kg` | kg | > 0; <= 1e+06 |
| `capacity_kg_kg_resin` | kg/kg | > 0; <= 10 |
| `affinity_m3_kg` | m³/kg | > 0; <= 1e+09 |
| `elution_recovery_fraction` | fraction | >= 0; <= 1 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `recovery_fraction` | fraction |
| `recovered_product_kg` | kg |

Limitations:

- Single-solute equilibrium batch adsorption, not a dynamic chromatography column.
- No impurity selectivity or competition; recovery does not establish purification.
- Elution recovery is supplied empirical evidence, not a prediction of elution.

Method context: Langmuir equilibrium isotherm and finite-volume material balance

## membrane.ultrafiltration

Constant-flux ultrafiltration concentration

**Family:** biologics_downstream; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `dV/dt=-A J; dM/dt=-S A J M/V; M=M0(V/V0)^S`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `initial_volume_m3` | m³ | > 0; <= 1000 |
| `target_volume_m3` | m³ | > 0; <= 1000 |
| `initial_product_kg` | kg | > 0; <= 1e+06 |
| `membrane_area_m2` | m² | > 0; <= 10000 |
| `permeate_flux_m_s` | m/s | > 0; <= 0.001 |
| `product_sieving` | fraction | >= 0; <= 1 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `retentate_volume_m3` | m³ |
| `retentate_product_kg` | kg |
| `product_concentration_kg_m3` | kg/m³ |

Limitations:

- Well-mixed ideal membrane balance with constant flux and sieving coefficients.
- No fouling, concentration polarisation, binding, viscosity or transmembrane-pressure prediction.
- Product loss is modelled passage only; degradation/aggregation/adsorption need separate evidence.

Method context: https://www.merckmillipore.com/deepweb/assets/sigmaaldrich/product/documents/272/805/rf1159en-ms.pdf

## membrane.diafiltration

Constant-volume ideal diafiltration

**Family:** biologics_downstream; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `N=A J t/V; Mi=Mi0 exp(-Si N); buffer inflow equals permeate outflow`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `retentate_volume_m3` | m³ | > 0; <= 1000 |
| `initial_product_kg` | kg | > 0; <= 1e+06 |
| `initial_impurity_kg` | kg | >= 0; <= 1e+06 |
| `membrane_area_m2` | m² | > 0; <= 10000 |
| `permeate_flux_m_s` | m/s | > 0; <= 0.001 |
| `product_sieving` | fraction | >= 0; <= 1 |
| `impurity_sieving` | fraction | >= 0; <= 1 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `diavolumes` | dimensionless |
| `retained_product_kg` | kg |
| `retained_impurity_kg` | kg |

Limitations:

- Well-mixed ideal membrane balance with constant flux and sieving coefficients.
- No fouling, concentration polarisation, binding, viscosity or transmembrane-pressure prediction.
- Product loss is modelled passage only; degradation/aggregation/adsorption need separate evidence.

Method context: https://www.merckmillipore.com/deepweb/assets/sigmaaldrich/product/documents/272/805/rf1159en-ms.pdf

## utility.turbulent_mixing

Turbulent stirred-vessel power screen

**Family:** equipment_utilities; **type:** reduced_mechanistic; **axis:** none.

Equation: `Re=rho N D²/mu; P=nimp Np rho N³D⁵; tm=(measured N tm)/N`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `density_kg_m3` | kg/m³ | > 0; <= 10000 |
| `viscosity_pa_s` | Pa s | > 0; <= 1000 |
| `speed_s_inv` | 1/s | > 0; <= 100 |
| `impeller_diameter_m` | m | > 0; <= 10 |
| `impeller_count` | count | > 0; <= 20 |
| `power_number` | dimensionless | > 0; <= 100 |
| `working_volume_m3` | m³ | > 0; <= 1000 |
| `measured_dimensionless_mixing_time` | dimensionless | > 0; <= 1e+06 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `power_w` | W |
| `power_density_w_m3` | W/m³ |
| `mixing_time_s` | s |

Limitations:

- Requires matched impeller/baffle geometry and turbulent characterised power number.
- No CFD, local shear, gas dispersion or oxygen-transfer prediction.
- Adding impeller powers assumes independent contributions; interaction is not resolved.

Method context: Turbulent impeller power-number relation; mixing time requires measured correlation

## utility.ideal_vacuum

Ideal chamber pump-down with constant gas load

**Family:** equipment_utilities; **type:** reduced_mechanistic; **axis:** time_s.

Equation: `V dP/dt=R T ndot-S P; constant T, load and effective pumping speed`

| Required numeric input | Unit | Numeric bounds |
|---|---|---|
| `chamber_volume_m3` | m³ | > 0; <= 10000 |
| `effective_pumping_m3_s` | m³/s | > 0; <= 1000 |
| `initial_pressure_pa` | Pa | > 0; <= 200000 |
| `target_pressure_pa` | Pa | > 0; <= 200000 |
| `gas_load_mol_s` | mol/s | >= 0; <= 100 |
| `gas_temperature_k` | K | >= 250; <= 450 |
| `duration_s` | s | > 0; <= 604800 |

Also required: `evidence_classification` and a nonempty `source_refs` list.

| Observable | Unit |
|---|---|
| `pressure_pa` | Pa |

Limitations:

- Ideal-gas, isothermal, constant effective chamber pumping speed.
- No pressure-dependent pump curve, conductance network, condensation or sublimation coupling.
- Not a replacement for the existing freeze-drying pressure/capacity assessment.

Method context: Ideal-gas inventory balance
