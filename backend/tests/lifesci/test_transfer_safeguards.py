"""Checks that stop an unsupported transfer conclusion before it is reported."""
from copy import deepcopy

from src.lifesci.chemical_reactor.demo import example, receiver_example
from src.lifesci.process_engineering import capability, decisions
from src.lifesci.process_engineering.catalog import ModelCatalog
from src.lifesci.process_engineering.library_examples import synthetic_runs

YIELD = {"metric": "product_yield_fraction", "unit": "fraction", "role": "yield", "operator": ">=",
         "basis": "desired_product_mol_per_initial_reactant_mol", "limit": 0.2}


def _corner(result, value, name):
    corner = deepcopy(result)
    corner["product_yield_fraction"] = value
    corner["assignment"] = {"equipment.heat_transfer_coefficient_w_m2_k": name}
    return corner


def test_corner_runs_do_not_decide_when_the_response_peaks_inside_the_tolerances():
    adapter = ModelCatalog(None).get("chemical.parallel_batch")
    result = adapter.run(synthetic_runs(adapter.id)[0]["config"])
    nominal = result["product_yield_fraction"]
    assert nominal > 0.23
    verdict = lambda low, high: decisions.transfer_assessment(  # noqa: E731
        adapter, result, result, [YIELD],
        receiver_corners=[_corner(result, low, 1.0), _corner(result, high, 2.0)])["checks"][0]
    # Both corners sit below the nominal: yield has a maximum inside the tolerances, so the corners bound nothing.
    peaked = verdict(nominal - 0.02, nominal - 0.01)
    assert peaked["status"] == "inconclusive" and peaked["response_within_tolerances"] == "not_monotonic"
    # A response that moves one way across the tolerances still gets its verdict.
    assert verdict(nominal - 0.01, nominal + 0.01)["status"] == "model_based_pass"
    assert verdict(0.05, 0.1)["status"] == "inconclusive"  # nominal above both corners again
    assert verdict(0.1, nominal + 0.01)["status"] == "inconclusive"  # straddles the limit


def test_heat_removal_is_adequate_only_when_the_receiving_run_stays_inside_its_limits():
    adapter = ModelCatalog(None).get("chemical.parallel_batch")
    donor = example()
    donor_result = adapter.run(donor)
    same = capability.capabilities(adapter, donor, donor_result, donor, donor_result)["checks"][0]
    assert same["status"] == "sufficient" and same["receiving_margin_fraction"] > 0
    # Same comparison of need and capacity, but the receiving run broke a limit: adequacy is not shown.
    stopped = {**donor_result, "status": "stopped", "violations": ["temperature limit exceeded"]}
    unshown = capability.capabilities(adapter, donor, donor_result, donor, stopped)["checks"][0]
    assert unshown["status"] == "unknown" and "adequacy is not shown" in unshown["reason"]
    receiver = receiver_example(donor)
    short = capability.capabilities(adapter, donor, donor_result, receiver, adapter.run(receiver))["checks"][0]
    assert short["status"] == "short" and short["receiving_need"] >= short["sending_need"] * (
        receiver["equipment"]["working_volume_m3"] / donor["equipment"]["working_volume_m3"]) * (1 - 1e-9)


def _coarse_run(adapter, picks=5):
    """Noise-free observations of the unmodified physics model, sampled far apart in reaction time."""
    config = synthetic_runs(adapter.id)[0]["config"]
    rows = adapter.run(config)["trajectory"]
    step = (len(rows) - 1) // (picks - 1)
    units = {"a_mol": "mol", "product_mol": "mol", "impurity_mol": "mol", "temperature_k": "K"}
    observations = [{"coordinate": row["time_s"], "observable": name, "unit": unit, "value": row[name]}
                    for row in rows[::step][:picks] for name, unit in units.items()]
    return {"run_id": "r", "batch_id": "b", "site_id": "s", "config": config, "observations": observations}, rows


def test_kinetic_multiplier_estimate_is_unbiased_when_samples_are_far_apart():
    from src.lifesci.process_engineering import hybrid
    adapter = ModelCatalog(None).get("chemical.parallel_batch")
    run, rows = _coarse_run(adapter)
    assert rows[0]["a_mol"] / rows[-1]["a_mol"] > 1.2  # the reactant really is consumed between samples
    _, targets, _ = hybrid.estimate_terms(adapter.id, [run])
    # The data come from the physics model itself, so every multiplier is 1; a trapezoid reads low here.
    assert abs(targets - 1).max() < 0.01


def test_a_learned_term_worse_than_physics_is_withheld_even_without_a_parent(monkeypatch):
    from src.lifesci.process_engineering import hybrid
    adapter = ModelCatalog(None).get("chemical.parallel_batch")
    real = hybrid.score
    worse = lambda a, runs, checkpoint=None, mode="physics", budget=None: {  # noqa: E731
        **real(a, runs, checkpoint, mode, budget), **({"rmse_scaled": 9.0} if mode == "hybrid" else {})}
    monkeypatch.setattr(hybrid, "score", worse)
    checkpoint = hybrid.train(adapter, synthetic_runs(adapter.id), ensemble_size=2)
    assert checkpoint["negative_transfer"] and checkpoint["promotion"] == "withheld_negative_transfer"
    assert checkpoint["selected_model"] != "hybrid"


def test_solver_budget_exhaustion_is_not_scored_as_a_model_failure():
    import pytest
    from src.lifesci.process_engineering import hybrid
    from src.lifesci.process_engineering.engine import BudgetExceeded, SolverBudget
    adapter = ModelCatalog(None).get("chemical.parallel_batch")
    runs = [r for r in synthetic_runs(adapter.id) if r["role"] == "selection"]
    with pytest.raises(BudgetExceeded):
        hybrid.score(adapter, runs, budget=SolverBudget(0, 60))


def _cho_dataset(parameters=(.035, .003, .5, 2.5, .004)):
    import numpy as np
    from src.lifesci.bioprocess import cho
    times = [0., 24., 48., 72., 96., 120.]
    rows, n = [], 0
    for batch, (x0, g0) in {"B1": (.3, 6.), "B2": (.4, 7.), "B3": (.35, 6.5)}.items():
        states = cho.integrate(list(parameters), np.array([x0, g0]), 0., times)
        for t, (x, g) in zip(times, states):
            for field, value in (("viable_cell_density", x * 1e6), ("glucose", g)):
                n += 1
                rows.append({"id": f"m{n}", "batch": batch, "time": t, "parameter": field, "value": float(value),
                             "unit": cho.SOURCE_UNITS[field], "source": {"path": "synthetic.csv"}})
    return {"measurements": rows}


def test_cho_forecast_reports_readings_it_left_out_and_what_the_fit_cannot_determine():
    from src.lifesci.bioprocess import cho
    data = _cho_dataset()
    data["measurements"] += [
        {"id": "z1", "batch": "B1", "time": 110., "parameter": "glucose", "value": 0.0, "unit": "g/L", "source": {"path": "s.csv"}},
        {"id": "u1", "batch": "B2", "time": 12., "parameter": "glucose", "value": 30.0, "unit": "mmol/L", "source": {"path": "s.csv"}}]
    result = cho.forecast(data, "B1")
    text = " ".join(result["warnings"])
    assert "1 glucose reading(s) in mmol/L were left out" in text
    assert "1 glucose reading(s) at or below zero were left out" in text and "glucose depletion" in text
    assert "not separately determined" in text
    fit = result["fit"]
    assert fit["not_separately_determined"] == ["yield_million_cells_ml_per_g_l", "maintenance_g_l_per_million_cells_ml_h"]
    # The data were generated with mu_max/Y + m = .035/2.5 + .004; that sum is what the fit recovers.
    assert abs(fit["glucose_uptake_coefficient_g_l_per_million_cells_ml_h"] - (.035 / 2.5 + .004)) < 0.002


def test_cho_yield_and_maintenance_pairs_with_the_same_sum_are_indistinguishable():
    import numpy as np
    from src.lifesci.bioprocess import cho
    times = [24., 72., 120.]
    one = cho.integrate([.035, .003, .5, 2.5, .004], np.array([.3, 6.]), 0., times)
    other = cho.integrate([.035, .003, .5, 7.0, .013], np.array([.3, 6.]), 0., times)  # .035/7 + .013 = .018
    assert np.allclose(one, other, rtol=1e-9)


def test_cho_forecast_warns_when_the_fit_stops_at_the_edge_of_its_allowed_range():
    from src.lifesci.bioprocess import cho
    fast = cho.forecast(_cho_dataset((.10, .003, .5, 2.5, .004)), "B1")  # growth faster than the model allows
    assert "mu_max_per_h" in fast["fit"]["parameters_at_bounds"]
    assert any("edge of the allowed range" in w for w in fast["warnings"])


def _lyo_observations(config, scale_key, scale, cutoff=6.):
    """Temperatures the model itself produces under a changed equipment or product term."""
    from copy import deepcopy as copy
    from src.lifesci.lyophilization.model import simulate
    changed = copy(config)
    block = "equipment" if scale_key == "kv_scale" else "product"
    changed[block][scale_key] = scale
    changed["duration_h"] = cutoff
    changed["schedule"] = [s for s in changed["schedule"] if s["time_h"] <= cutoff]
    rows = simulate(changed, sample_step_h=.25)["trajectory"]
    return [{"time_h": r["time_h"], "product_temperature_c": r["interface_temperature_c"]} for r in rows if 0 < r["time_h"] <= cutoff]


def test_freeze_drying_estimate_at_the_edge_of_its_search_range_is_not_acted_on():
    from src.lifesci.lyophilization.case import receiving_config
    from src.lifesci.lyophilization.workflows import operations
    config = receiving_config()
    inside = operations(config, _lyo_observations(config, "kv_scale", 1.25))
    assert inside["diagnosis"]["estimate_reliable"]
    # A heat-transfer change well beyond what the search covers: the estimate stops at the limit.
    outside = operations(config, _lyo_observations(config, "kv_scale", 2.4))
    diagnosis = outside["diagnosis"]
    assert not diagnosis["estimate_reliable"] and outside["recommended_index"] is None
    assert "edge of its search range" in outside["intervention_boundary"]
    assert any(h["estimate_at_search_limit"] for h in diagnosis["hypotheses"])


def test_freeze_drying_diagnosis_survives_a_small_vapor_capacity():
    from copy import deepcopy as copy
    from src.lifesci.lyophilization.case import receiving_config
    from src.lifesci.lyophilization.workflows import diagnose
    config = receiving_config()
    observations = _lyo_observations(config, "kv_scale", 1.1)
    small = copy(config)
    small["equipment"]["vapor_capacity_kg_h"] = .2
    capacity = next(h for h in diagnose(small, observations, 6.)["hypotheses"] if h["hypothesis"] == "reduced_vapor_capacity")
    assert capacity["estimate"] is None and not capacity["identifiable"]


def test_simulations_report_their_own_balance_checks():
    from src.lifesci.chemical_reactor import model as reactor
    from src.lifesci.lyophilization import model as lyo
    from src.lifesci.lyophilization.case import source_config
    dried = lyo.simulate(source_config())
    assert dried["numerical_status"] == "completed" and dried["mass_balance_relative_error"] < lyo.MASS_TOLERANCE
    run = reactor.simulate(example())
    assert run["status"] == "completed" and run["energy_balance_relative_error"] < reactor.ENERGY_TOLERANCE


def test_a_reactor_run_whose_energy_balance_does_not_close_is_not_reported_as_completed(monkeypatch):
    from src.lifesci.chemical_reactor import model as reactor
    monkeypatch.setattr(reactor, "ENERGY_TOLERANCE", 1e-12)  # tighter than any integration achieves
    run = reactor.simulate(example())
    assert run["status"] == "stopped_or_failed" and "energy_balance_not_closed" in run["violations"]
    assert run["product_yield_fraction"] is None


def _process_model(model_id, **changes):
    from src.lifesci.process_models.examples import examples
    return ModelCatalog(None).get(model_id), {**examples()[model_id], **changes}


def test_unfinished_separation_steps_do_not_report_end_of_step_figures():
    adapter, config = _process_model("membrane.ultrafiltration")
    assert adapter.run(config)["recovery_fraction"] is not None
    short = adapter.run({**config, "duration_s": config["duration_s"] / 1e4})
    assert short["status"] == "incomplete" and short["recovery_fraction"] is None and short["final_volume_m3"] is None
    assert short["at_end_of_duration"]["retentate_volume_m3"] > config["target_volume_m3"]
    adapter, config = _process_model("isolation.cake_filter")
    short = adapter.run({**config, "duration_s": config["duration_s"] / 1e4})
    assert short["status"] == "incomplete" and short["final_filtrate_m3"] is None
    assert 0 <= short["filtrate_at_end_of_duration_m3"] < config["target_filtrate_m3"]


def test_dryer_does_not_claim_dryness_on_heat_it_never_received():
    adapter, config = _process_model("isolation.cake_dryer")
    assert adapter.run(config)["solvent_target_met"]
    cold = adapter.run({**config, "wall_temperature_k": 260.})  # a wall colder than the cake supplies no heat
    assert not cold["solvent_target_met"] and "evaporation_exceeds_heat_supplied" in cold["violations"]


def test_crystallizer_refuses_a_slurry_outside_its_dilute_assumption():
    import pytest
    adapter, config = _process_model("crystal.cooling_moments")
    adapter.run(config)
    with pytest.raises(ValueError, match="dilute-suspension"):
        adapter.run({**config, "seed_number_m3": 1e14, "seed_size_m": 50e-6})
