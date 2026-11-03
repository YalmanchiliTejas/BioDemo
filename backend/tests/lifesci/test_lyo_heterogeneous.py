"""Physical invariants and applicability for the explicit population model."""
from copy import deepcopy
import math

import numpy as np
import pytest

from src.lifesci.lyophilization.case import source_config
from src.lifesci.lyophilization import model
from src.lifesci.lyophilization.heterogeneous import simulate as run


def config():
    c = source_config()
    c["populations"] = [{"weight": .8, "kv_scale": .8, "rp_scale": 1.1},
                        {"weight": .2, "kv_scale": 1.7, "rp_scale": .8}]
    c["thermal"] = {"vial_heat_capacity_j_k": 3., "initial_temperature_c": -43.}
    c["equipment"]["vapor_capacity_kg_h"] = 10.
    return c


def test_mass_is_conserved_and_completion_waits_for_every_population():
    c = config()
    result = run(c, sample_step_h=.01)
    assert result["numerical_status"] == "completed"
    completion = result["population_completion_time_h"]
    assert all(t is not None for t in completion)
    assert result["completion_time_h"] == max(completion)
    assert max(completion) - min(completion) > 5
    assert result["completion_time_h"] > sum(p["weight"]*t for p, t in zip(c["populations"], completion))
    rows = result["trajectory"]
    assert all(r["remaining_ice_kg_per_vial"] >= 0 for r in rows)
    for i in range(2):
        masses = [r["populations"][i]["remaining_ice_kg_per_vial"] for r in rows]
        assert all(a >= b-1e-12 for a, b in zip(masses, masses[1:]))
        assert masses[-1] == 0
    integrated = np.trapezoid([r["sublimation_kg_h"] for r in rows], [r["time_h"] for r in rows])
    assert integrated == pytest.approx(result["initial_ice_kg_per_vial"]*c["load_vials"], rel=.002)
    assert rows[-1]["time_h"] == c["duration_h"]
    assert rows[-1]["active_max_temperature_c"] is None
    assert rows[-1]["critical_margin_c"] is None
    assert rows[-1]["sublimation_kg_h"] == 0


def test_hot_active_edge_can_fail_while_weighted_thermometry_is_safe():
    c = config()
    c["populations"] = [{"weight": .95, "kv_scale": .7, "rp_scale": 1.},
                        {"weight": .05, "kv_scale": 2.5, "rp_scale": 1.5}]
    c["duration_h"] = 15.
    c["schedule"][0]["shelf_temperature_c"] = -15.
    result = run(c)
    hidden = [r for r in result["trajectory"] if r["active_max_temperature_c"] is not None
              and r["active_max_temperature_c"] > -28 > r["product_temperature_c"]]
    assert hidden
    assert result["minimum_critical_margin_c"] < 0
    assert any(v["constraint"] == "critical_temperature" for v in result["violations"])


def test_dry_vials_continue_warming_without_becoming_active_thermal_violations():
    c = config()
    result = run(c)
    mixed = [r for r in result["trajectory"] if sum(p["active"] for p in r["populations"]) == 1]
    assert mixed
    for row in mixed:
        active = [p["temperature_c"] for p in row["populations"] if p["active"]]
        assert row["active_max_temperature_c"] == max(active)
        assert row["product_temperature_c"] == pytest.approx(sum(p["weight"]*r["temperature_c"] for p, r in zip(c["populations"], row["populations"])))
    assert mixed[-1]["product_temperature_c"] > mixed[-1]["active_max_temperature_c"]


def test_homogeneous_population_split_and_small_thermal_storage_limit():
    c = config()
    c["populations"] = [{"weight": 1., "kv_scale": 1., "rp_scale": 1.}]
    c["thermal"] = {"vial_heat_capacity_j_k": .1, "initial_equilibrium": True}
    one = run(c)
    c["populations"] = [{"weight": .2, "kv_scale": 1., "rp_scale": 1.},
                        {"weight": .8, "kv_scale": 1., "rp_scale": 1.}]
    split = run(c)
    assert one["completion_time_h"] == pytest.approx(split["completion_time_h"], rel=1e-5)
    steady = model.simulate(c)
    assert one["completion_time_h"] == pytest.approx(steady["completion_time_h"], rel=.015)
    assert one["trajectory"][0]["product_temperature_c"] == pytest.approx(steady["trajectory"][0]["interface_temperature_c"], abs=1e-6)


@pytest.mark.parametrize("capacity,value,constraint", [("vapor_capacity_kg_h", .001, "vapor_capacity"),
                                                       ("condenser_capacity_kg", .1, "condenser_ice_capacity")])
def test_capacity_crossing_invalidates_prescribed_pressure_prediction(capacity, value, constraint):
    c = config()
    c["equipment"][capacity] = value
    result = run(c)
    assert result["numerical_status"] == "completed"
    assert result["applicability_status"] == "invalid_after_capacity_exceedance"
    assert 0 <= result["prediction_valid_until_h"] < result["completion_time_h"]
    assert result["diagnostic_trajectory"] is True
    assert result["valid_completion_time_h"] is None
    assert result["primary_drying_throughput_vials_h"] is None
    assert any(v["constraint"] == constraint for v in result["violations"])
    assert any("diagnostic" in warning for warning in result["warnings"])
    assert all(r["prediction_valid"] is False for r in result["trajectory"] if r["time_h"] > result["prediction_valid_until_h"])


def test_step_boundary_uses_new_pressure_and_continuous_thermal_state():
    c = config()
    c["duration_h"] = 2.
    c["schedule"] += [{"time_h": 1., "shelf_temperature_c": -10., "chamber_pressure_pa": 15.}]
    coarse = run(c)
    fine = run(c, rtol=1e-8, max_step_s=30.)
    boundary = next(r for r in coarse["trajectory"] if r["time_h"] == 1.)
    assert boundary["chamber_pressure_pa"] == 15.
    c["duration_h"] = 1.
    c["schedule"] = c["schedule"][:1]
    left = run(c)["trajectory"][-1]
    assert boundary["product_temperature_c"] == pytest.approx(left["product_temperature_c"], abs=1e-4)
    assert coarse["trajectory"][-1]["product_temperature_c"] == pytest.approx(fine["trajectory"][-1]["product_temperature_c"], abs=.002)


@pytest.mark.parametrize("field,value", [
    ("populations", None), ("populations", []),
    ("populations", [{"weight": .9, "kv_scale": 1., "rp_scale": 1.}]),
    ("populations", [{"weight": 1., "kv_scale": 0., "rp_scale": 1.}]),
    ("populations", [{"weight": 1., "kv_scale": float("nan"), "rp_scale": 1.}]),
    ("populations", [{"weight": 1., "kv_scale": True, "rp_scale": 1.}]),
    ("populations", [{"weight": 1/21, "kv_scale": 1., "rp_scale": 1.}]*21),
    ("thermal", {}), ("thermal", None),
    ("thermal", {"vial_heat_capacity_j_k": 3., "initial_temperature_c": 5.}),
    ("thermal", {"vial_heat_capacity_j_k": 3., "initial_equilibrium": "yes"}),
    ("thermal", {"vial_heat_capacity_j_k": 3., "initial_temperature_c": -43., "initial_equilibrium": True}),
])
def test_explicit_finite_population_and_thermal_inputs_required(field, value):
    c = config()
    c[field] = deepcopy(value)
    with pytest.raises(ValueError):
        run(c)


def test_initially_dry_has_no_active_temperature_and_no_spurious_failure():
    c = config()
    c["initial_dried_fraction"] = 1.
    c["schedule"][0]["shelf_temperature_c"] = 20.
    result = run(c)
    assert result["completion_time_h"] == 0.
    assert result["numerical_status"] == "completed"
    assert result["minimum_critical_margin_c"] is None
    assert all(r["active_max_temperature_c"] is None for r in result["trajectory"])
    assert result["trajectory"][-1]["product_temperature_c"] == pytest.approx(20., abs=.01)


def test_sensible_heat_storage_matches_analytical_cold_no_sublimation_solution():
    """Omitting ice heat capacity or population heat scaling breaks this limit."""
    c = config()
    c["duration_h"] = .1
    c["thermal"]["initial_temperature_c"] = -65.
    c["schedule"] = [{"time_h": 0., "shelf_temperature_c": -60., "chamber_pressure_pa": 100.}]
    result = run(c)
    row = result["trajectory"][-1]
    # Independently evaluate the analytical exponential with the fixture's SI
    # geometry and constants. At -65..-60 C, ice vapor pressure is below 100 Pa.
    area_product = math.pi*.020**2/4
    area_vial = math.pi*.022**2/4
    frozen_height = 2.5e-6*(1-.897+.897*1000/918)/area_product
    mass = frozen_height*918*.897*area_product
    heat_capacity = 3.+mass*2100.
    for population, state in zip(c["populations"], row["populations"]):
        conductance = area_vial*(2.57+2.33*100/(1+.03*100))*population["kv_scale"]
        conductance /= 1+conductance*frozen_height/(area_product*2.4)
        expected = -60.-5.*math.exp(-conductance*.1*3600/heat_capacity)
        assert state["temperature_c"] == pytest.approx(expected, abs=.0002)
        assert state["remaining_ice_kg_per_vial"] == pytest.approx(mass, abs=1e-12)
    assert row["sublimation_kg_h"] == 0


def test_completion_and_capacity_event_converge_independently_of_output_grid():
    c = config()
    c["equipment"]["condenser_capacity_kg"] = .1
    coarse = run(c, sample_step_h=2.)
    fine = run(c, sample_step_h=.01, rtol=1e-8, max_step_s=30.)
    assert coarse["completion_time_h"] == pytest.approx(fine["completion_time_h"], abs=.0001)
    assert coarse["prediction_valid_until_h"] == pytest.approx(fine["prediction_valid_until_h"], abs=.0001)
    assert coarse["minimum_critical_margin_c"] == pytest.approx(fine["minimum_critical_margin_c"], abs=.001)
