"""Independent limiting cases, inventories, transfer stops and calibration leakage."""
from copy import deepcopy
import math
import unittest

import numpy as np

from src.lifesci.process_models.registry import models, get
from src.lifesci.process_models.examples import examples
from src.lifesci.process_models.analysis import fit_parameter, compare, parameter_scenarios
from src.lifesci.process_models.flowsheets import purification_train
from src.lifesci.process_engineering.catalog import ModelCatalog
from src.lifesci.chemical_reactor.demo import example as batch_example
from src.lifesci.chemical_reactor.model import simulate as batch_simulate


class LibraryChecks(unittest.TestCase):
    def setUp(self): self.cases=examples()

    def run_model(self,mid,**changes):
        c=self.cases[mid]; c.update(changes)
        return get(mid).run(c)

    def test_every_model_has_example_units_evidence_and_unchanged_inputs(self):
        self.assertEqual(set(models()),set(self.cases))
        self.assertEqual(len(models()),16)
        for mid,config in self.cases.items():
            with self.subTest(model=mid):
                before=deepcopy(config)
                result=get(mid).run(config)
                self.assertEqual(config,before)
                self.assertEqual(result["status"],"completed")
                self.assertTrue(result["input_hash"])
                self.assertEqual(set(get(mid).describe()["required_inputs"]),set(config)-{"source_refs","evidence_classification"})

    def test_invalid_nan_bool_unknown_and_missing_evidence_fail_for_all_models(self):
        for mid,model in models().items():
            key=next(iter(model.inputs))
            for value in (float("nan"),True):
                c=deepcopy(self.cases[mid]); c[key]=value
                with self.subTest(model=mid,value=str(value)),self.assertRaises(ValueError): model.run(c)
            c=deepcopy(self.cases[mid]); c["invented_parameter"]=1.
            with self.assertRaises(ValueError): model.run(c)
            c=deepcopy(self.cases[mid]); c["source_refs"]=[]
            with self.assertRaises(ValueError): model.run(c)

    def test_existing_catalog_families_preserved_and_new_families_registered(self):
        self.assertEqual(len(ModelCatalog().snapshot()),2)
        self.assertEqual(len(ModelCatalog("aerobic_fermentation").snapshot()),2)
        self.assertEqual(len(ModelCatalog("chemical_batch_reaction").snapshot()),1)
        for model in models().values():
            self.assertEqual(ModelCatalog(model.family).get(model.id).id,model.id)

    def test_semibatch_zero_feed_matches_existing_batch_solver(self):
        c=self.cases["chemical.semi_batch"]
        b=batch_example()
        c.update(initial_a_mol_m3=b["recipe"]["initial_a_mol_m3"],feed_flow_m3_s=0.,
                 heat_transfer_area_m2=b["equipment"]["heat_transfer_area_m2"])
        a=get("chemical.semi_batch").run(c); expected=batch_simulate(b)
        self.assertAlmostEqual(a["product_yield_fraction"],expected["product_yield_fraction"],places=6)
        self.assertLess(a["maximum_a_equivalent_mole_error"],1e-6)

    def test_semibatch_feed_enthalpy_and_species_inventory(self):
        c=self.cases["chemical.semi_batch"]
        c.update(product_rate_ref_s_inv=0.,impurity_rate_ref_s_inv=0.,heat_transfer_coefficient_w_m2_k=0.,feed_temperature_k=310.)
        r=get("chemical.semi_batch").run(c)
        expected_t=(c["initial_volume_m3"]*c["initial_temperature_k"]+c["feed_flow_m3_s"]*c["feed_until_s"]*310.)/r["final_volume_m3"]
        self.assertAlmostEqual(r["trajectory"][-1]["temperature_k"],expected_t,places=5)
        self.assertLess(r["maximum_a_equivalent_mole_error"],1e-6)

    def test_semibatch_volume_stop_and_thermal_stop_withhold_yield(self):
        for changes,reason in (({"maximum_volume_m3":.0101},"volume_limit_reached"),
                               ({"temperature_limit_k":298.2,"initial_a_mol_m3":3000.},"temperature_limit_reached")):
            c=deepcopy(self.cases["chemical.semi_batch"]); c.update(changes)
            r=get("chemical.semi_batch").run(c)
            self.assertEqual(r["status"],"stopped")
            self.assertIn(reason,r["violations"])
            self.assertIsNone(r["product_yield_fraction"])

    def test_crystallizer_inventory_and_moments(self):
        r=self.run_model("crystal.cooling_moments",nucleation_rate_m3_s=0.)
        self.assertLess(r["maximum_inventory_error_kg_m3"],1e-6)
        m0,m1,m2,m3=r["final_moments"]
        size=m1/m0
        self.assertAlmostEqual(m2/(m0*size**2),1.,places=5)
        self.assertAlmostEqual(m3/(m0*size**3),1.,places=5)

    def test_crystallizer_no_kinetics_cannot_create_crystals(self):
        r=self.run_model("crystal.cooling_moments",growth_rate_m_s=0.,nucleation_rate_m3_s=0.)
        c=self.cases["crystal.cooling_moments"]
        initial=c["crystal_density_kg_m3"]*c["shape_factor"]*c["seed_number_m3"]*c["seed_size_m"]**3*c["liquid_volume_m3"]
        self.assertAlmostEqual(r["final_crystal_mass_kg"],initial,places=9)

    def test_crystallizer_rejects_dissolution_domain(self):
        with self.assertRaises(ValueError): self.run_model("crystal.cooling_moments",initial_solute_kg_m3=1.)

    def test_filter_medium_only_matches_darcy_flow(self):
        c=self.cases["isolation.cake_filter"]
        r=self.run_model("isolation.cake_filter",cake_resistance_m_kg=0.)
        expected=c["target_filtrate_m3"]*c["viscosity_pa_s"]*c["medium_resistance_m_inv"]/(c["filter_area_m2"]*c["pressure_difference_pa"])
        self.assertAlmostEqual(r["completion_time_s"],expected)

    def test_filter_incomplete_is_visible_and_pressure_scaling(self):
        mid="isolation.cake_filter"; first=get(mid).run(self.cases[mid])
        second=self.run_model(mid,pressure_difference_pa=self.cases[mid]["pressure_difference_pa"]*2)
        self.assertAlmostEqual(second["completion_time_s"],first["completion_time_s"]/2)
        r=self.run_model(mid,duration_s=1.)
        self.assertEqual(r["status"],"incomplete"); self.assertIsNone(r["completion_time_s"])

    def test_wash_api_inventory_and_one_pore_volume_clearance(self):
        c=self.cases["isolation.cake_wash"]
        r=self.run_model("isolation.cake_wash",duration_s=c["retained_liquid_m3"]/c["wash_flow_m3_s"])
        self.assertAlmostEqual(r["retained_product_kg"]+r["product_loss_kg"],c["initial_crystal_kg"])
        self.assertAlmostEqual(r["retained_impurity_kg"]/c["initial_pore_impurity_kg"],math.exp(-1))

    def test_dryer_solvent_matches_first_order_limit(self):
        mid="isolation.cake_dryer"; c=self.cases[mid]; r=get(mid).run(c)
        expected=c["equilibrium_solvent_kg_kg_dry"]+(c["initial_solvent_kg_kg_dry"]-c["equilibrium_solvent_kg_kg_dry"])*math.exp(-c["drying_rate_s_inv"]*c["duration_s"])
        self.assertAlmostEqual(r["final_solvent_kg_kg_dry"],expected,places=7)

    def test_dryer_adiabatic_latent_heat_balance(self):
        c=self.cases["isolation.cake_dryer"]
        c.update(ua_w_k=0.,initial_temperature_k=330.,initial_solvent_kg_kg_dry=.01)
        r=get("isolation.cake_dryer").run(c)
        cooling=(330-r["trajectory"][-1]["temperature_k"])*c["dry_solids_kg"]*c["solid_heat_capacity_j_kg_k"]
        latent=r["evaporated_solvent_kg"]*c["latent_heat_j_kg"]
        self.assertAlmostEqual(cooling,latent,places=5)

    def test_dryer_temperature_event_and_unreachable_dryness(self):
        r=self.run_model("isolation.cake_dryer",temperature_limit_k=294.)
        self.assertEqual(r["status"],"stopped"); self.assertIsNone(r["final_solvent_kg_kg_dry"])
        with self.assertRaises(ValueError): self.run_model("isolation.cake_dryer",target_solvent_kg_kg_dry=0.)

    def test_blender_step_cannot_change_pre_step_history(self):
        mid="powder.continuous_blender"; a=get(mid).run(self.cases[mid]); b=self.run_model(mid,inlet_after_fraction=.9)
        before_a=[r["outlet_fraction"] for r in a["trajectory"] if r["time_s"]<=200]
        before_b=[r["outlet_fraction"] for r in b["trajectory"] if r["time_s"]<=200]
        self.assertEqual(before_a,before_b)
        self.assertAlmostEqual(a["residence_time_s"],100.)

    def test_mill_no_breakage_and_bin_mass_conservation(self):
        r=self.run_model("powder.two_bin_mill",breakage_rate_s_inv=0.)
        self.assertAlmostEqual(r["final_coarse_fraction"],.8)
        self.assertEqual(r["maximum_mass_fraction_error"],0.)

    def test_granulator_solid_inventory_and_zero_aggregation(self):
        r=self.run_model("powder.aggregation_granulator",aggregation_coefficient_m3_s=0.)
        sizes=[r["equivalent_diameter_m"] for r in r["trajectory"]]
        self.assertAlmostEqual(min(sizes),max(sizes))
        self.assertLess(r["maximum_solid_inventory_error_kg_m3"],1e-8)

    def test_compaction_zero_pressure_and_monotonicity(self):
        r=get("tablet.heckel_compaction").run(self.cases["tablet.heckel_compaction"])
        rows=r["trajectory"]
        self.assertAlmostEqual(rows[0]["relative_density"],.4)
        self.assertTrue(all(a["relative_density"]<=b["relative_density"]<=1 for a,b in zip(rows,rows[1:])))

    def test_coating_deposition_balance(self):
        c=self.cases["tablet.coating_deposition"]; r=get("tablet.coating_deposition").run(c)
        last=r["trajectory"][-1]
        sprayed=c["suspension_flow_kg_s"]*c["suspension_solids_fraction"]*c["duration_s"]
        self.assertAlmostEqual(last["deposited_coat_kg"]+last["lost_coat_solids_kg"],sprayed)
        self.assertAlmostEqual(last["mean_coat_thickness_m"]*c["coat_density_kg_m3"]*c["total_surface_area_m2"],last["deposited_coat_kg"])

    def test_dissolution_respects_finite_solubility_and_inventory(self):
        r=self.run_model("tablet.shrinking_area_dissolution",medium_volume_m3=1e-5)
        self.assertLessEqual(r["final_dissolved_fraction"],.10000001)
        fractions=[row["dissolved_fraction"] for row in r["trajectory"]]
        self.assertTrue(all(a<=b+1e-10 for a,b in zip(fractions,fractions[1:])))

    def test_resin_equilibrium_inventory_and_capacity(self):
        c=self.cases["downstream.equilibrium_capture"]; r=get("downstream.equilibrium_capture").run(c)
        self.assertLess(r["maximum_inventory_error_kg"],1e-9)
        self.assertLessEqual(r["bound_product_kg"],c["resin_mass_kg"]*c["capacity_kg_kg_resin"])
        self.assertLessEqual(r["recovered_product_kg"],r["bound_product_kg"])

    def test_ultrafiltration_perfect_retention_and_full_passage_limits(self):
        mid="membrane.ultrafiltration"; c=self.cases[mid]
        retained=self.run_model(mid,product_sieving=0.)
        self.assertAlmostEqual(retained["recovery_fraction"],1.)
        passed=self.run_model(mid,product_sieving=1.)
        self.assertAlmostEqual(passed["retained_product_kg"]/passed["final_volume_m3"],c["initial_product_kg"]/c["initial_volume_m3"])
        self.assertAlmostEqual(passed["retained_product_kg"]+passed["permeate_product_kg"],c["initial_product_kg"])

    def test_diafiltration_zero_sieving_preserves_product_and_one_clears_impurity(self):
        r=self.run_model("membrane.diafiltration",product_sieving=0.)
        self.assertAlmostEqual(r["recovery_fraction"],1.)
        self.assertAlmostEqual(r["impurity_remaining_fraction"],math.exp(-5))
        self.assertAlmostEqual(r["buffer_volume_m3"],.025)

    def test_mixing_power_cubic_speed_and_rejects_laminar_domain(self):
        mid="utility.turbulent_mixing"; a=get(mid).run(self.cases[mid]); b=self.run_model(mid,speed_s_inv=10.)
        self.assertAlmostEqual(b["power_w"],8*a["power_w"])
        with self.assertRaises(ValueError): self.run_model(mid,viscosity_pa_s=10.)

    def test_vacuum_gas_free_analytic_time_and_unattainable_pressure(self):
        r=self.run_model("utility.ideal_vacuum",gas_load_mol_s=0.)
        self.assertAlmostEqual(r["time_to_target_s"],100*math.log(1000))
        r=self.run_model("utility.ideal_vacuum",gas_load_mol_s=1.)
        self.assertFalse(r["target_reachable_at_steady_state"])
        self.assertIsNone(r["time_to_target_s"])

    def test_shared_fit_recovers_rate_without_holdout_leakage(self):
        mid="powder.two_bin_mill"; c=self.cases[mid]
        times=np.arange(0,1801,90)
        observations=[{"coordinate":float(t),"value":float(.8*math.exp(-.002*t)),"source_ref":"synthetic-analytic"} for t in times]
        guess=deepcopy(c); guess["breakage_rate_s_inv"]=.001
        kwargs=dict(parameter="breakage_rate_s_inv",bounds=[.0001,.005],observable="coarse_mass_fraction",observations=observations,training_until=900.)
        fit=fit_parameter(mid,guess,**kwargs)
        self.assertAlmostEqual(fit["estimate"],.002,delta=1e-6)
        poison=deepcopy(observations)
        for row in poison:
            if row["coordinate"]>900: row["value"]+=1.
        kwargs["observations"]=poison
        other=fit_parameter(mid,guess,**kwargs)
        self.assertEqual(fit["estimate"],other["estimate"])
        self.assertNotEqual(fit["holdout_hash"],other["holdout_hash"])
        self.assertGreater(other["holdout_rmse"],.9)

    def test_sensitivity_preserves_failed_scenarios(self):
        r=parameter_scenarios("powder.two_bin_mill",self.cases["powder.two_bin_mill"],parameter="breakage_rate_s_inv",
                              values=[-.1,.001,.002],metrics=["final_coarse_fraction"])
        self.assertEqual(r["rows"][0]["status"],"failed")
        self.assertEqual(len(r["rows"]),3)

    def test_compaction_fit_uses_pressure_axis_and_recovers_inverse_pressure_units(self):
        mid="tablet.heckel_compaction"
        c=deepcopy(self.cases[mid]); c["heckel_coefficient_pa_inv"]=5e-9
        observations=[{"coordinate":float(p),"value":float(1-.6*math.exp(-1e-8*p)),"source_ref":"synthetic-heckel"}
                      for p in np.arange(0.,200000001.,20000000.)]
        fitted=fit_parameter(mid,c,parameter="heckel_coefficient_pa_inv",bounds=[1e-10,3e-8],
                             observable="relative_density",observations=observations,training_until=100000000.)
        self.assertEqual(fitted["axis"],"pressure_pa")
        self.assertAlmostEqual(fitted["estimate"],1e-8,delta=1e-12)
        self.assertLess(fitted["holdout_rmse"],1e-5)

    def test_comparison_withholds_incomplete_endpoint_differences(self):
        a=self.cases["isolation.cake_filter"]; b=deepcopy(a); b["duration_s"]=1.
        r=compare("isolation.cake_filter",a,b,metrics=["completion_time_s"])
        self.assertIsNone(r["receiver_minus_donor"]["completion_time_s"])

    def test_purification_train_accounts_api_and_stops_on_incomplete_filter(self):
        kwargs=dict(crystal=self.cases["crystal.cooling_moments"],filtration=self.cases["isolation.cake_filter"],
                    wash=self.cases["isolation.cake_wash"],dryer=self.cases["isolation.cake_dryer"],
                    retained_liquid_m3=.00005,liquid_density_kg_m3=800.)
        r=purification_train(**kwargs)
        self.assertLess(r["api_inventory_accounting_error_kg"],1e-9)
        self.assertEqual(len(r["stages"]),4)
        bad=deepcopy(kwargs); bad["filtration"]["duration_s"]=1.
        r=purification_train(**bad)
        self.assertEqual(r["status"],"blocked")
        self.assertEqual(len(r["stages"]),2)


if __name__=="__main__": unittest.main()
