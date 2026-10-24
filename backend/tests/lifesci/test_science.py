from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from src.lifesci import science as sci
from src.lifesci.gateway import FakeProvider, ModelGateway, TaskRequest, default_registry
from src.lifesci.gateway.registry import Qualification
from src.lifesci.identity import IdentityService
from src.lifesci.store import RecordStore

T = "tenant-a"
BASE = [0.5, -0.4, 0.3, -0.6, 0.4, -0.3, 0.6, -0.5, 0.2, -0.2]
SPEC = (90.0, 110.0)


def _env_keys(r):
    assert {"method", "method_version", "inputs_hash", "result", "validity_limits", "warnings", "classification"} <= set(r)
    assert r["classification"] == "calculated" and r["validity_limits"]


def _drift():
    return [100 + b for b in BASE] + [100 + 0.4 * i + (0.3 if i % 2 else -0.3) for i in range(1, 16)]


def _reversed():
    return _drift() + [100 + b for b in BASE] * 2


# ---------------------------------------------------------------- control charts
def test_LS031_imr_limits_reference():
    x = [10, 12, 11, 13, 12, 10, 11, 12]
    r = sci.imr_chart(x)
    _env_keys(r)
    res = r["result"]
    mrbar = np.mean(np.abs(np.diff(x)))
    assert res["center"] == pytest.approx(11.375)
    assert res["sigma_hat"] == pytest.approx(mrbar / 1.128)
    assert res["ucl"] == pytest.approx(11.375 + 3 * mrbar / 1.128)
    assert res["mr_ucl"] == pytest.approx(3.267 * mrbar)
    assert r["inputs_hash"] == sci.imr_chart(x)["inputs_hash"]


def test_LS031_western_electric_rules_indices():
    base = [100, 101, 99, 100, 101, 99, 100, 101, 99, 100]
    r = sci.imr_chart(base + [110, 100, 100], baseline_n=10)["result"]["rule_violations"]
    assert r["WE1_beyond_3sigma"] == [10]
    eight = sci.imr_chart(base + [101.1] * 8, baseline_n=10)["result"]["rule_violations"]
    assert eight["WE4_8_same_side"] == [17]
    two3 = sci.imr_chart(base + [103, 100, 103], baseline_n=10)["result"]["rule_violations"]
    assert two3["WE2_2of3_beyond_2sigma"] == [12]
    four5 = sci.imr_chart(base + [101.8, 101.8, 100, 101.8, 101.8], baseline_n=10)["result"]["rule_violations"]
    assert four5["WE3_4of5_beyond_1sigma"] == [14]


def test_LS031_ewma_and_cusum_detect_small_shift():
    x = [100 + b for b in BASE] + [101.2 + b for b in BASE * 2]
    ew = sci.ewma_chart(x, baseline_n=10)["result"]
    cu = sci.cusum_chart(x, baseline_n=10)["result"]
    assert ew["alarm_indices"] and min(ew["alarm_indices"]) >= 10
    assert cu["alarm_indices"] and min(cu["alarm_indices"]) >= 10
    quiet = [100 + b for b in BASE * 3]
    assert sci.ewma_chart(quiet, baseline_n=10)["result"]["alarm_indices"] == []
    assert sci.cusum_chart(quiet, baseline_n=10)["result"]["alarm_indices"] == []


def test_LS031_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        sci.imr_chart([1, 2])
    with pytest.raises(ValueError):
        sci.imr_chart([1, 2, float("nan"), 4])
    with pytest.raises(ValueError):
        sci.imr_chart([5, 5, 5, 5])


# ---------------------------------------------------------------- emerging concern
def test_LS077_emerging_concern_before_deviation():
    r = sci.detect_emerging_concern(_drift(), SPEC, baseline_n=10)
    res = r["result"]
    assert all(SPEC[0] <= v <= SPEC[1] for v in _drift())
    assert res["status"] == "emerging_concern_not_deviation" and res["concern"]
    assert res["evidence_indices"] and min(res["evidence_indices"]) >= 10
    assert set(res["signals"]) & {"EWMA", "CUSUM"}
    assert res["recommendation"]["requires_human_decision"]
    assert res["basis"]["evidence_indices"]


def test_LS077_no_concern_and_out_of_spec_distinguished():
    assert sci.detect_emerging_concern([100 + b for b in BASE * 2], SPEC, baseline_n=10)["result"]["status"] == "no_concern"
    out = sci.detect_emerging_concern(_drift() + [111.0], SPEC, baseline_n=10)["result"]
    assert out["status"] == "out_of_spec_handle_via_deviation_process" and not out["concern"]


def test_LS077_recommendation_basis_updates_when_trend_reverses():
    prev = sci.detect_emerging_concern(_drift(), SPEC, baseline_n=10)
    upd = sci.update_recommendation_basis(prev, _reversed())["result"]
    assert upd["previous_status"] == "emerging_concern_not_deviation"
    assert upd["new_status"] == "historical_signal_not_active"
    assert upd["recommendation_status"] == "withdrawn_basis_changed" and upd["basis_changed"]
    assert upd["previous_inputs_hash"] != upd["new_inputs_hash"]
    same = sci.update_recommendation_basis(prev, _drift() + [106.2])["result"]
    assert same["recommendation_status"] == "reaffirmed_basis_updated"


# ---------------------------------------------------------------- cohorts and yield
def _cohort(cid, vals, **meta):
    base = {"process_stage": "harvest", "scale": "2000L", "process_version": "v3", "site": "S1", "raw_material_lot": "L1",
            "equipment": "BR-1", "start_time": "2026-01-01T00:00:00+00:00"}
    return {"id": cid, "unit": "%", "values": vals, "metadata": {**base, **meta}}


def test_LS076_refuses_non_stage_compatible():
    r = sci.compare_cohorts([_cohort("A", [80, 82, 81]), _cohort("B", [70, 71, 72], scale="200L")])["result"]
    assert r["status"] == "not_comparable" and any("scale differs" in x for x in r["reasons"])
    assert "p_value" not in r and r["causal_claim_supported"] is False
    r2 = sci.compare_cohorts([_cohort("A", [80, 82, 81]), _cohort("B", [70, 71, 72], process_stage="fill")])["result"]
    assert r2["status"] == "not_comparable"
    r3 = sci.compare_cohorts([_cohort("A", [80, 82, 81]), _cohort("B", [70, 71, 72], process_version="v4")])["result"]
    assert r3["status"] == "not_comparable"


def test_LS076_welch_reference_with_confounders_and_missing():
    a, b = [80.0, 82.0, 81.0, 79.0, 83.0], [75.0, 77.0, 74.0, 76.0, 78.0, None]
    r = sci.compare_cohorts([_cohort("A", a), _cohort("B", b, site="S2", equipment="BR-9",
                                                      start_time="2026-02-01T00:00:00+00:00")])
    res = r["result"]
    from scipy import stats
    ref = stats.ttest_ind(a, b[:5], equal_var=False)
    assert res["status"] == "compared"
    assert res["welch_t"] == pytest.approx(ref.statistic) and res["p_value"] == pytest.approx(ref.pvalue)
    lo, hi = res["ci_mean_difference"]
    ci = ref.confidence_interval(0.95)
    assert (lo, hi) == pytest.approx((ci.low, ci.high))
    sp = math.sqrt((np.var(a, ddof=1) + np.var(b[:5], ddof=1)) / 2)
    assert res["hedges_g"] == pytest.approx((np.mean(a) - np.mean(b[:5])) / sp * (1 - 3 / (4 * 10 - 9)))
    facs = {c["factor"]: c for c in res["confounders"]}
    assert {"site", "equipment", "start_time"} <= set(facs) and facs["start_time"]["time_gap_days"] == pytest.approx(31)
    assert res["missing_data"]["B"]["missing"] == 1 and res["causal_claim_supported"] is False
    assert any("confounded" in w for w in r["warnings"])


def test_LS076_unit_mismatch_and_unauthorized():
    x = _cohort("A", [1, 2, 3])
    y = _cohort("B", [1, 2, 3])
    y["unit"] = "g/L"
    with pytest.raises(ValueError):
        sci.compare_cohorts([x, y])
    s = RecordStore()
    idn = IdentityService(s)
    idn.assign_role(T, "eng1", "engineering", site_id="S1")
    ctx = idn.context_for(T, "eng1")
    a = {**_cohort("A", [80, 82, 81]), "sources": [{"kind": "batch", "id": "B1", "site_id": "S1"}]}
    b = {**_cohort("B", [70, 72, 71], site="S2"), "sources": [{"kind": "batch", "id": "B2", "site_id": "S2"}]}
    r = sci.compare_cohorts_authorized(idn, ctx, [a, b])["result"]
    assert r["status"] == "not_authorized" and "B" in r["reasons"] and "p_value" not in r


def test_LS076_yield_calculations_and_units():
    y = sci.step_yield(2.0, 1500, "kg", "g")["result"]
    assert y["yield_percent"] == pytest.approx(75.0)
    c = sci.cumulative_yield([{"name": "a", "input": 100, "output": 80, "unit": "g"},
                              {"name": "b", "input": 80, "output": 0.072, "unit": "g", "output_unit": "kg"}])["result"]
    assert c["cumulative_percent"] == pytest.approx(72.0)
    assert sci.step_yield(1, 1.2, "g")["warnings"]
    with pytest.raises(ValueError):
        sci.step_yield(1, 1, "g", "L")


# ---------------------------------------------------------------- OEE
def test_LS031_oee_reference_and_validation():
    r = sci.oee(480, 420, 0.5, 700, 665)["result"]
    assert r["availability"] == pytest.approx(0.875)
    assert r["performance"] == pytest.approx(350 / 420)
    assert r["quality"] == pytest.approx(0.95)
    assert r["oee"] == pytest.approx(0.875 * 350 / 420 * 0.95)
    assert sci.oee(480, 420, 30, 700, 665, cycle_time_unit="s")["result"]["performance"] == pytest.approx(350 / 420)
    for bad in [(480, 500, 0.5, 700, 665), (480, 420, 0.5, 700, 701), (480, 420, 0.5, 700, float("nan")), (0, 1, 1, 1, 1)]:
        with pytest.raises(ValueError):
            sci.oee(*bad)


# ---------------------------------------------------------------- curve fitting
def test_LS030_4pl_recovers_reference_parameters():
    x = np.logspace(-2, 4, 12)
    y = 0 + 100 / (1 + (10 / x) ** 1)
    r = sci.fit_4pl(x, y)
    _env_keys(r)
    p = r["result"]["params"]
    assert (p["bottom"], p["top"], p["ec50"], p["hill"]) == pytest.approx((0, 100, 10, 1), abs=1e-3)
    assert r["result"]["ec50"] == pytest.approx(10, rel=1e-4) and r["result"]["r_squared"] > 0.99999
    noisy = y + np.random.default_rng(1).normal(0, 1.0, y.size)
    rn = sci.fit_4pl(x, noisy)["result"]
    assert rn["ec50"] == pytest.approx(10, rel=0.15) and 0.5 < rn["residual_se"] < 2.5 and rn["r_squared"] > 0.99
    with pytest.raises(ValueError):
        sci.fit_4pl([0, 1, 2, 3, 4], [1, 2, 3, 4, 5])
    with pytest.raises(ValueError):
        sci.fit_4pl([1, 2, 3, 4], [1, 2, 3, 4])


# ---------------------------------------------------------------- qPCR
def test_LS030_qpcr_standard_curve_efficiency_reference():
    q = np.array([1e1, 1e2, 1e3, 1e4, 1e5, 1e6])
    ct = -3.32 * np.log10(q) + 38.0
    r = sci.qpcr_standard_curve(q, ct)
    res = r["result"]
    assert res["slope"] == pytest.approx(-3.32) and res["intercept"] == pytest.approx(38.0)
    assert res["r_squared"] == pytest.approx(1.0) and res["efficiency"] == pytest.approx(1.0, abs=0.005)
    assert not r["warnings"]
    quant = sci.qpcr_quantify(res["slope"], res["intercept"], [-3.32 * 3 + 38, -3.32 * 8 + 38], res["log10_range"])
    assert quant["result"]["quantities"][0] == pytest.approx(1000)
    assert quant["warnings"]
    low = sci.qpcr_standard_curve(q, -2.5 * np.log10(q) + 38)
    assert low["warnings"]
    with pytest.raises(ValueError):
        sci.qpcr_standard_curve(q, np.full(6, 25.0) + np.log10(q))


def test_LS030_qpcr_delta_delta_ct():
    r = sci.qpcr_delta_delta_ct([22, 22.2], [18, 18.2], [25, 25.2], [18, 18.2])["result"]
    assert r["delta_ct_sample"] == pytest.approx(4.0) and r["delta_ct_control"] == pytest.approx(7.0)
    assert r["delta_delta_ct"] == pytest.approx(-3.0) and r["fold_change"] == pytest.approx(8.0)
    assert r["fold_change_range"][0] < 8 < r["fold_change_range"][1]
    with pytest.raises(ValueError):
        sci.qpcr_delta_delta_ct([float("nan")], [1], [1], [1])


# ---------------------------------------------------------------- chromatography
def _gauss(t, area, mu, sigma):
    return area / (sigma * math.sqrt(2 * math.pi)) * np.exp(-0.5 * ((t - mu) / sigma) ** 2)


def test_LS030_chromatography_known_areas_and_plates():
    t = np.linspace(0, 20, 4001)
    y = _gauss(t, 50.0, 5.0, 0.15) + _gauss(t, 120.0, 9.0, 0.25) + _gauss(t, 30.0, 14.0, 0.3)
    r = sci.chromatography_analysis(t, y)
    peaks = r["result"]["peaks"]
    assert len(peaks) == 3
    for p, (area, mu, sig) in zip(peaks, [(50, 5, 0.15), (120, 9, 0.25), (30, 14, 0.3)]):
        assert p["area"] == pytest.approx(area, rel=0.01)
        assert p["retention_time"] == pytest.approx(mu, abs=0.01)
        assert p["plate_count_half_height"] == pytest.approx(5.54 * (mu / (2.3548 * sig)) ** 2, rel=0.01)
        assert p["plate_count_usp"] == pytest.approx(16 * (mu / (4 * sig)) ** 2, rel=0.02)
        assert p["tailing_factor"] == pytest.approx(1.0, abs=0.02)
    assert peaks[1]["resolution_from_previous"] == pytest.approx(2 * 4 / (4 * 0.15 + 4 * 0.25), rel=0.02)


def test_LS030_chromatography_overlapping_peaks_and_formulas():
    t = np.linspace(0, 10, 3001)
    y = _gauss(t, 10, 4.0, 0.2) + _gauss(t, 10, 4.8, 0.2) + 0.5
    peaks = sci.chromatography_analysis(t, y, baseline=0.5)["result"]["peaks"]
    assert len(peaks) == 2
    assert peaks[0]["area"] + peaks[1]["area"] == pytest.approx(20, rel=0.03)
    assert sci.usp_plate_count(10, 0.5)["result"]["plate_count"] == pytest.approx(16 * 400)
    assert sci.usp_plate_count(10, 0.5, "half_height")["result"]["plate_count"] == pytest.approx(5.54 * 400)
    assert sci.resolution(4, 5, 0.4, 0.6)["result"]["resolution"] == pytest.approx(2.0)
    with pytest.raises(ValueError):
        sci.resolution(5, 4, 1, 1)
    with pytest.raises(ValueError):
        sci.chromatography_analysis([0, 1, 1, 2, 3], [0, 1, 2, 1, 0])
    tail = np.exp(-0.5 * ((t - 5) / np.where(t < 5, 0.2, 0.4)) ** 2)
    t_factor = sci.chromatography_analysis(t, tail)["result"]["peaks"][0]["tailing_factor"]
    assert t_factor == pytest.approx(1.5, abs=0.05)


# ---------------------------------------------------------------- DOE
def test_LS031_full_factorial_and_effects_reference():
    d = sci.full_factorial({"temp": (30, 40), "ph": (6.5, 7.5), "feed": (1, 2)})["result"]
    assert d["runs"] == 8 and d["coded"][0] == [-1, -1, -1] and d["coded"][1] == [1, -1, -1]
    assert d["actual"][1] == {"temp": 40, "ph": 6.5, "feed": 1}
    assert len({tuple(r) for r in d["coded"]}) == 8
    X = sci.full_factorial(["A", "B", "C"])["result"]["coded"]
    y = [10 + 3 * a - 2 * b + 1.5 * a * b for a, b, c in X]
    r = sci.analyze_factorial(X, y, ["A", "B", "C"])
    eff = r["result"]["effects"]
    assert eff["A"] == pytest.approx(6) and eff["B"] == pytest.approx(-4) and eff["A:B"] == pytest.approx(3)
    assert eff["C"] == pytest.approx(0, abs=1e-9) and r["result"]["coefficients"]["Intercept"] == pytest.approx(10)


def test_LS031_doe_warns_when_runs_below_parameters():
    X = sci.full_factorial(["A", "B", "C", "D"])["result"]["coded"][:6]
    r = sci.analyze_factorial(X, [1, 2, 3, 4, 5, 7])
    assert any("runs (6) < parameters" in w for w in r["warnings"])
    with pytest.raises(ValueError):
        sci.analyze_factorial([[0, 1], [1, 1]], [1, 2])
    with pytest.raises(ValueError):
        sci.full_factorial(["A", "A"])


# ---------------------------------------------------------------- liquid handler and plate assay
def test_LS031_liquid_handler_cv_and_bias():
    ch = {"1": [49.0, 50.0, 51.0, 50.0], "2": [52.0, 52.0, 53.0, 51.0]}
    r = sci.liquid_handler_performance(50, ch, "uL", cv_limit_percent=2.0, bias_limit_percent=3.0)["result"]
    sd1 = np.std(ch["1"], ddof=1)
    assert r["channels"]["1"]["cv_percent"] == pytest.approx(100 * sd1 / 50) and r["channels"]["1"]["bias_percent"] == pytest.approx(0)
    assert r["channels"]["2"]["bias_percent"] == pytest.approx(4.0) and r["channels"]["2"]["within_bias_limit"] is False
    assert sci.liquid_handler_performance(0.05, {"1": [50, 50.5]}, "uL", "mL")["result"]["channels"]["1"]["bias_percent"] == pytest.approx(0.5, abs=1)
    with pytest.raises(ValueError):
        sci.liquid_handler_performance(50, {"1": [50.0]})
    with pytest.raises(ValueError):
        sci.liquid_handler_performance(50, {"1": [50, 51]}, "uL", "g")


def test_LS031_z_prime_and_plate_map():
    pos, neg = [100, 102, 98, 101, 99], [10, 11, 9, 10, 10]
    z = sci.z_prime(pos, neg)["result"]
    exp = 1 - 3 * (np.std(pos, ddof=1) + np.std(neg, ddof=1)) / abs(np.mean(pos) - np.mean(neg))
    assert z["z_prime"] == pytest.approx(exp) and z["signal_to_background"] == pytest.approx(10.0)
    assert sci.z_prime([10, 20, 30], [12, 22, 32])["warnings"]
    wells = ([{"well": f"A{i}", "role": "positive", "value": v} for i, v in enumerate(pos, 1)]
             + [{"well": f"B{i}", "role": "negative", "value": v} for i, v in enumerate(neg, 1)]
             + [{"well": "C1", "role": "sample", "value": 50}])
    assert sci.plate_assay(96, wells)["result"]["z_prime"] == pytest.approx(exp)
    assert sci.validate_plate_map(96, wells)["result"]["wells_unmapped"] == 96 - 11
    bad = sci.validate_plate_map(96, wells + [{"well": "A1", "role": "sample"}, {"well": "I1", "role": "sample"},
                                              {"well": "A13", "role": "sample"}])["result"]
    assert not bad["valid"] and any("duplicate" in i for i in bad["issues"]) and any("invalid well" in i for i in bad["issues"])
    assert sci.validate_plate_map(384, [{"well": "P24", "role": "sample"}])["result"]["wells_mapped"] == 1
    assert any("positive" in i for i in sci.validate_plate_map(384, [{"well": "P24", "role": "sample"}])["result"]["issues"])
    with pytest.raises(ValueError):
        sci.plate_assay(96, wells + [{"well": "A1", "role": "sample", "value": 1}])
    with pytest.raises(ValueError):
        sci.validate_plate_map(48, [])


# ---------------------------------------------------------------- drift monitoring
def test_LS089_psi_reference():
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 2000)
    same = sci.population_stability_index(ref, rng.normal(0, 1, 2000))["result"]
    shifted = sci.population_stability_index(ref, rng.normal(1.5, 1, 2000))["result"]
    assert same["psi"] < 0.1 and same["band"] == "stable"
    assert shifted["psi"] > 0.25 and shifted["band"] == "major_shift"
    assert sci.population_stability_index(ref, ref)["result"]["psi"] == pytest.approx(0, abs=1e-9)
    with pytest.raises(ValueError):
        sci.population_stability_index(ref[:5], ref)


@pytest.fixture
def mon():
    s = RecordStore()
    reg = default_registry()
    reg.qualify(Qualification("document_classification", "anthropic-haiku", "e1", True, {"acc": 0.95}, {"acc": 0.9}, "site S1", "1"))
    reg.qualify(Qualification("document_classification", "openai-luna", "e2", True, {"acc": 0.94}, {"acc": 0.9}, "site S1", "1"))
    return SimpleNamespace(s=s, reg=reg, m=sci.ProfileMonitor(s, reg))


def test_LS089_suspends_on_psi_without_touching_approved_results(mon):
    with mon.s.transaction("qa1") as tx:
        tx.put(T, "analysis_result", "r1", {"status": "approved", "value": 42}, expected_revision=None, action="approve")
    before = mon.s.read().get(T, "analysis_result", "r1")
    rng = np.random.default_rng(3)
    ok = mon.m.evaluate(T, "document_classification", "anthropic-haiku", reference=rng.normal(0, 1, 500),
                        current=rng.normal(0, 1, 500), corrected=1, total=50)
    assert ok["status"] == "active" and not ok["newly_suspended"]
    r = mon.m.evaluate(T, "document_classification", "anthropic-haiku", reference=rng.normal(0, 1, 500),
                       current=rng.normal(2, 1, 500), corrected=1, total=50)
    assert r["status"] == "suspended" and "PSI" in r["reason"] and r["newly_suspended"]
    assert ("document_classification", "anthropic-haiku") not in mon.reg.qualifications
    assert r["replacement_candidates"] == ["openai-luna"]
    after = mon.s.read().get(T, "analysis_result", "r1")
    assert (after.state, after.revision, after.content_hash) == (before.state, before.revision, before.content_hash)
    assert after.state["status"] == "approved"
    stored = mon.m.get(T, "document_classification", "anthropic-haiku")
    assert stored["status"] == "suspended" and len(stored["observations"]) == 2 and stored["revision"] == 2
    again = mon.m.evaluate(T, "document_classification", "anthropic-haiku", corrected=0, total=50)
    assert again["status"] == "suspended" and not again["newly_suspended"]


def test_LS089_suspends_on_correction_rate_and_requires_min_samples(mon):
    few = mon.m.evaluate(T, "document_classification", "openai-luna", corrected=5, total=5)
    assert few["status"] == "active" and few["warnings"]
    r = mon.m.evaluate(T, "document_classification", "openai-luna", corrected=15, total=50)
    assert r["status"] == "suspended" and "correction rate" in r["reason"] and r["latest_correction_rate"] == pytest.approx(0.3)
    assert [p.profile_id for p in mon.reg.qualified_profiles("document_classification")] == ["anthropic-haiku"]
    with pytest.raises(ValueError):
        mon.m.evaluate(T, "document_classification", "x")
    with pytest.raises(ValueError):
        mon.m.evaluate(T, "document_classification", "x", corrected=9, total=3)


def test_LS089_works_without_registry():
    m = sci.ProfileMonitor(RecordStore())
    assert m.evaluate(T, "k", "p", corrected=30, total=50)["status"] == "suspended"


# ---------------------------------------------------------------- gateway C0 handlers
@pytest.fixture
def gw():
    s = RecordStore()
    idn = IdentityService(s)
    idn.assign_role(T, "eng1", "engineering")
    fake = FakeProvider()
    g = ModelGateway(s, idn, default_registry(), {"fake": fake})
    sci.register_handlers(g)
    return SimpleNamespace(g=g, ctx=idn.context_for(T, "eng1"), fake=fake)


def test_LS056_statistics_runs_deterministically_at_c0_without_model(gw):
    payload = {"method": "oee", "params": {"planned_time": 480, "run_time": 420, "ideal_cycle_time": 0.5,
                                           "total_count": 700, "good_count": 665}}
    r1 = gw.g.run(TaskRequest("statistics", gw.ctx, payload=payload))
    r2 = gw.g.run(TaskRequest("statistics", gw.ctx, payload=payload))
    assert r1.status == "completed" and r1.route["tier"] == "C0" and r1.cost_usd == 0
    assert gw.fake.calls == [] and r1.output == r2.output
    assert r1.output["result"]["oee"] == pytest.approx(0.875 * 350 / 420 * 0.95)
    assert r1.output["classification"] == "calculated"
    stat = gw.g.run(TaskRequest("statistics", gw.ctx, payload={"method": "z_prime", "params": {
        "positive": [100, 102, 98], "negative": [10, 11, 9]}}))
    assert stat.output["result"]["z_prime"] > 0.5
    assert gw.g.run(TaskRequest("statistics", gw.ctx, payload={"method": "nope"})).status == "unresolved"
    assert gw.g.run(TaskRequest("statistics", gw.ctx, payload={"method": "oee", "params": {
        "planned_time": 1, "run_time": 2, "ideal_cycle_time": 1, "total_count": 1, "good_count": 1}})).status == "unresolved"
    assert gw.fake.calls == []


def test_LS056_limit_check_and_unit_conversion_handlers(gw):
    ok = gw.g.run(TaskRequest("limit_check", gw.ctx, payload={"value": 0.0105, "unit": "L", "low": 10, "high": 11,
                                                               "limit_unit": "mL"}))
    assert ok.status == "completed" and ok.route["tier"] == "C0"
    assert ok.output["result"]["status"] == "within_limits" and ok.output["result"]["value_in_limit_unit"] == pytest.approx(10.5)
    hi = gw.g.run(TaskRequest("limit_check", gw.ctx, payload={"value": 11.5, "unit": "mL", "high": 11}))
    assert hi.output["result"]["status"] == "above_high"
    lo = gw.g.run(TaskRequest("limit_check", gw.ctx, payload={"value": 9.9, "unit": "mL", "low": 10}))
    assert lo.output["result"]["status"] == "below_low"
    mism = gw.g.run(TaskRequest("limit_check", gw.ctx, payload={"value": 5, "unit": "mg", "low": 1, "high": 9, "limit_unit": "mL"}))
    assert mism.status == "unresolved"
    conv = gw.g.run(TaskRequest("unit_conversion", gw.ctx, payload={"value": 2.5, "from_unit": "kg", "to_unit": "g"}))
    assert conv.output["result"]["value"] == pytest.approx(2500)
    bad = gw.g.run(TaskRequest("unit_conversion", gw.ctx, payload={"value": 1, "from_unit": "kg", "to_unit": "L"}))
    assert bad.status == "unresolved" and gw.fake.calls == []
