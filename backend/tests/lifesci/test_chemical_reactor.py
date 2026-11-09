"""Independent limits, physical invariants, data partitions and catalog regression."""
from copy import deepcopy
import math
import unittest

from src.lifesci.chemical_reactor.model import simulate, validate
from src.lifesci.chemical_reactor.demo import example, receiver_example, synthetic_observations
from src.lifesci.chemical_reactor.analysis import fit_parameters, compare_sites
from src.lifesci.process_engineering.catalog import ModelCatalog


class ReactorChecks(unittest.TestCase):
    def test_isothermal_matches_closed_form_and_molar_balance(self):
        c = example()
        c["chemistry"].update(product_enthalpy_j_mol=0., impurity_enthalpy_j_mol=0.)
        c["equipment"]["coolant_temperature_k"] = c["recipe"]["initial_temperature_k"]
        r = simulate(c)
        kb, ki = c["chemistry"]["product_rate_ref_s_inv"], c["chemistry"]["impurity_rate_ref_s_inv"]
        expected = kb/(kb+ki)*(1-math.exp(-(kb+ki)*c["recipe"]["duration_s"]))
        self.assertEqual(r["status"], "completed")
        self.assertAlmostEqual(r["product_yield_fraction"], expected, places=6)
        self.assertLess(r["maximum_a_equivalent_mole_error"], 1e-7)

    def test_no_reaction_cooling_matches_independent_solution(self):
        c = example()
        c["chemistry"].update(product_rate_ref_s_inv=0., impurity_rate_ref_s_inv=0.)
        r = simulate(c)
        e, ch = c["equipment"], c["chemistry"]
        decay = e["heat_transfer_area_m2"]*e["heat_transfer_coefficient_w_m2_k"]/(ch["density_kg_m3"]*e["working_volume_m3"]*ch["heat_capacity_j_kg_k"])
        expected = e["coolant_temperature_k"] + (c["recipe"]["initial_temperature_k"]-e["coolant_temperature_k"])*math.exp(-decay*c["recipe"]["duration_s"])
        self.assertAlmostEqual(r["trajectory"][-1]["temperature_k"], expected, places=5)
        self.assertEqual(r["product_yield_fraction"], 0.)

    def test_adiabatic_energy_balance(self):
        c = example()
        c["equipment"]["heat_transfer_coefficient_w_m2_k"] = 0.
        c["recipe"]["temperature_limit_k"] = 440.
        result = simulate(c)
        self.assertEqual(result["status"], "completed")
        row = result["trajectory"][-1]
        ch, eq = c["chemistry"], c["equipment"]
        generated = -ch["product_enthalpy_j_mol"]*row["product_mol"]-ch["impurity_enthalpy_j_mol"]*row["impurity_mol"]
        stored = ch["density_kg_m3"]*eq["working_volume_m3"]*ch["heat_capacity_j_kg_k"]*(row["temperature_k"]-c["recipe"]["initial_temperature_k"])
        self.assertLess(abs(generated-stored), 1e-3)

    def test_thermal_stop_withholds_final_yield(self):
        c = receiver_example(example())
        c["recipe"]["temperature_limit_k"] = 310.
        r = simulate(c)
        self.assertEqual(r["status"], "stopped_or_failed")
        self.assertIsNone(r["product_yield_fraction"])
        self.assertIn("temperature_limit_reached", r["violations"])
        self.assertFalse(r["within_declared_constraints"])
        self.assertLess(r["completed_duration_s"], c["recipe"]["duration_s"])

    def test_invalid_inputs_and_unknown_fields(self):
        for field, value in (("working_volume_m3", -1.), ("coolant_temperature_k", float("nan")),
                             ("heat_transfer_coefficient_w_m2_k", True)):
            c = example()
            c["equipment"][field] = value
            with self.assertRaises(ValueError): validate(c)
        c = example()
        c["equipment"]["pressure_bar"] = 2.
        with self.assertRaises(ValueError): validate(c)

    def test_no_temperature_excitation_is_not_identifiable(self):
        c = example()
        c["chemistry"].update(product_enthalpy_j_mol=0., impurity_enthalpy_j_mol=0.)
        c["equipment"]["coolant_temperature_k"] = c["recipe"]["initial_temperature_k"]
        rows = [{"time_s": float(t), "temperature_k": 298.15, "source_ref": "synthetic-no-excitation"}
                for t in range(0, 7201, 600)]
        fit = fit_parameters(c, rows, fields=["heat_transfer_coefficient_w_m2_k"],
                             bounds={"heat_transfer_coefficient_w_m2_k": [200., 600.]}, training_until_s=3600.)
        self.assertEqual(fit["identifiability_diagnostic"], "weak_or_rank_deficient")

    def test_holdout_changes_cannot_change_fitted_parameter(self):
        c = example()
        rows = synthetic_observations(c)
        initial = deepcopy(c)
        initial["equipment"]["heat_transfer_coefficient_w_m2_k"] = 280.
        kwargs = dict(fields=["heat_transfer_coefficient_w_m2_k"],
                      bounds={"heat_transfer_coefficient_w_m2_k": [200., 600.]}, training_until_s=3600.)
        fit = fit_parameters(initial, rows, **kwargs)
        changed = deepcopy(rows)
        for row in changed:
            if row["time_s"] > 3600: row["temperature_k"] += 10.
        other = fit_parameters(initial, changed, **kwargs)
        self.assertEqual(fit["estimates"], other["estimates"])
        self.assertEqual(fit["training_data_hash"], other["training_data_hash"])
        self.assertNotEqual(fit["holdout_data_hash"], other["holdout_data_hash"])
        self.assertGreater(other["holdout_rmse_k"], 9.)
        self.assertAlmostEqual(fit["estimates"]["heat_transfer_coefficient_w_m2_k"], 350., delta=5.)

    def test_catalog_addition_preserves_existing_families(self):
        cat = ModelCatalog("chemical_batch_reaction")
        self.assertTrue(cat.get("chemical.parallel_batch").applicability(example())["applicable"])
        self.assertFalse(cat.get("chemical.parallel_batch").applicability({})["applicable"])
        self.assertEqual(len(ModelCatalog().snapshot()), 2)
        self.assertEqual(len(ModelCatalog("aerobic_fermentation").snapshot()), 2)

    def test_yield_screen_rejects_changed_chemistry(self):
        c = example()
        self.assertEqual(compare_sites(c, c, allowed_yield_loss_fraction=0.)["assessment"], "conditional_model_screen_pass")
        other = deepcopy(c)
        other["chemistry"]["product_rate_ref_s_inv"] *= 2
        with self.assertRaises(ValueError): compare_sites(c, other, allowed_yield_loss_fraction=.02)


if __name__ == "__main__":
    unittest.main()
