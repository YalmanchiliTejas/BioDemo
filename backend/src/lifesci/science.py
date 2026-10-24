"""Deterministic scientific and process analytics (LS-030, LS-031, LS-056, LS-076, LS-077, LS-089).

Every calculation is a pure numpy/scipy function returning an envelope with
``method``, ``method_version``, ``inputs_hash``, ``result``, ``validity_limits``,
``warnings`` and ``classification="calculated"``. Results are arithmetic on the
supplied inputs; they are not interpretations, not causal claims, and carry no
claim of validation for any particular intended use. Invalid inputs raise
``ValueError``. ``ProfileMonitor`` persists method/model profile drift state as
versioned ``method_profile`` records and never rewrites previously approved results.
"""

from __future__ import annotations

import itertools
import math
import re
from typing import Any, Callable, Sequence

import numpy as np
from scipy import integrate, optimize, signal, stats

from .ids import content_hash, iso, parse_iso, utc_now
from .store import RecordStore

METHOD_VERSION = "lifesci-science-1.0"
D2 = 1.128  # expected range of two consecutive observations (n=2)
D3_UCL = 3.267  # 1 + 3*0.853/1.128, upper limit factor for the moving-range chart

_ureg: Any = None


def _units() -> Any:
    global _ureg
    if _ureg is None:
        import pint
        _ureg = pint.UnitRegistry()
    return _ureg


def _py(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        return [_py(x) for x in v.tolist()]
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, dict):
        return {str(k): _py(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_py(x) for x in v]
    return v


def _envelope(method: str, inputs: Any, result: Any, limits: Sequence[str], warnings: Sequence[str] = ()) -> dict[str, Any]:
    return {"method": method, "method_version": METHOD_VERSION, "inputs_hash": content_hash(_py(inputs)),
            "result": _py(result), "validity_limits": list(limits), "warnings": list(warnings),
            "classification": "calculated"}


def _arr(x: Any, name: str, min_n: int = 2) -> np.ndarray:
    try:
        a = np.asarray(x, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if a.ndim != 1 or a.size < min_n:
        raise ValueError(f"{name} requires a 1-D sequence of at least {min_n} values")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} contains NaN or infinite values")
    return a


def _num(x: Any, name: str, *, positive: bool = False, nonneg: bool = False) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float, np.number)) or not math.isfinite(float(x)):
        raise ValueError(f"{name} must be a finite number")
    x = float(x)
    if (positive and x <= 0) or (nonneg and x < 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")
    return x


def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
    u = _units()
    try:
        return float(u.Quantity(float(value), from_unit).to(to_unit).magnitude)
    except Exception as exc:  # pint raises several unrelated types
        raise ValueError(f"cannot convert {from_unit!r} to {to_unit!r}: {exc}") from exc


# ---------------------------------------------------------------- control charts (LS-031)
def _baseline(x: np.ndarray, baseline_n: int | None, mu0: float | None, sigma: float | None) -> tuple[float, float, int]:
    n = baseline_n or x.size
    if n < 2 or n > x.size:
        raise ValueError("baseline_n must be between 2 and the series length")
    b = x[:n]
    mu = float(b.mean()) if mu0 is None else float(mu0)
    sd = float(np.abs(np.diff(b)).mean() / D2) if sigma is None else float(sigma)
    if not sd > 0:
        raise ValueError("zero or invalid variation in baseline; control limits undefined")
    return mu, sd, n


def _we_rules(x: np.ndarray, mu: float, sd: float) -> dict[str, list[int]]:
    z = (x - mu) / sd
    out: dict[str, list[int]] = {"WE1_beyond_3sigma": [], "WE2_2of3_beyond_2sigma": [],
                                 "WE3_4of5_beyond_1sigma": [], "WE4_8_same_side": []}
    for i in range(z.size):
        if abs(z[i]) > 3:
            out["WE1_beyond_3sigma"].append(i)
        for side in (1, -1):
            s = side * z
            if i >= 2 and s[i] > 2 and np.sum(s[i - 2:i + 1] > 2) >= 2:
                out["WE2_2of3_beyond_2sigma"].append(i)
            if i >= 4 and s[i] > 1 and np.sum(s[i - 4:i + 1] > 1) >= 4:
                out["WE3_4of5_beyond_1sigma"].append(i)
            if i >= 7 and np.all(s[i - 7:i + 1] > 0):
                out["WE4_8_same_side"].append(i)
    return {k: sorted(set(v)) for k, v in out.items()}


def _ewma(x: np.ndarray, mu: float, sd: float, lam: float, L: float) -> dict[str, Any]:
    if not 0 < lam <= 1 or L <= 0:
        raise ValueError("lambda must be in (0, 1] and L positive")
    z = np.empty_like(x)
    prev = mu
    for i, v in enumerate(x):
        prev = lam * v + (1 - lam) * prev
        z[i] = prev
    half = L * sd * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * (np.arange(x.size) + 1))))
    alarms = np.nonzero(np.abs(z - mu) > half)[0]
    return {"ewma": z, "ucl": mu + half, "lcl": mu - half, "alarm_indices": alarms.tolist()}


def _cusum(x: np.ndarray, mu: float, sd: float, k: float, h: float) -> dict[str, Any]:
    cp = cm = 0.0
    hi, lo, alarms, upward, downward = [], [], [], [], []
    for i, v in enumerate(x):
        cp = max(0.0, cp + (v - mu) - k * sd)
        cm = max(0.0, cm + (mu - v) - k * sd)
        hi.append(cp)
        lo.append(cm)
        if cp > h * sd or cm > h * sd:
            alarms.append(i)
            (upward if cp > h * sd else downward).append(i)
            cp = cm = 0.0  # restart after signalling so each alarm marks a new episode
    return {"c_plus": hi, "c_minus": lo, "alarm_indices": alarms, "upward_alarms": upward, "downward_alarms": downward}


def imr_chart(values: Sequence[float], baseline_n: int | None = None, center: float | None = None,
              sigma: float | None = None) -> dict[str, Any]:
    x = _arr(values, "values", 3)
    mu, sd, n = _baseline(x, baseline_n, center, sigma)
    mr = np.abs(np.diff(x))
    mrbar = float(np.abs(np.diff(x[:n])).mean())
    rules = _we_rules(x, mu, sd)
    res = {"center": mu, "sigma_hat": sd, "ucl": mu + 3 * sd, "lcl": mu - 3 * sd, "moving_ranges": mr,
           "mr_bar": mrbar, "mr_ucl": D3_UCL * mrbar, "mr_violations": np.nonzero(mr > D3_UCL * mrbar)[0] + 1,
           "baseline_n": n, "rule_violations": rules,
           "violation_indices": sorted({i for v in rules.values() for i in v})}
    warn = ["fewer than 20 baseline points; limits are uncertain"] if n < 20 else []
    return _envelope("imr_chart", {"values": x, "baseline_n": n, "center": center, "sigma": sigma}, res,
                     ["sigma estimated as MR-bar/1.128 assuming independent, approximately normal observations",
                      "WE/Nelson rules 1-4: >3σ; 2 of 3 >2σ same side; 4 of 5 >1σ same side; 8 in a row same side",
                      "rule index is the point that completes the pattern", "limits are not specification limits"], warn)


def ewma_chart(values: Sequence[float], baseline_n: int | None = None, mu0: float | None = None,
               sigma: float | None = None, lam: float = 0.2, L: float = 3.0) -> dict[str, Any]:
    x = _arr(values, "values", 3)
    mu, sd, n = _baseline(x, baseline_n, mu0, sigma)
    res = {"mu0": mu, "sigma": sd, "lambda": lam, "L": L, "baseline_n": n, **_ewma(x, mu, sd, lam, L)}
    return _envelope("ewma_chart", {"values": x, "baseline_n": n, "mu0": mu0, "sigma": sigma, "lam": lam, "L": L}, res,
                     ["exact time-varying EWMA limits; assumes independent observations with in-control σ = sigma",
                      "sensitive to small sustained shifts, slower for large single shifts"])


def cusum_chart(values: Sequence[float], baseline_n: int | None = None, target: float | None = None,
                sigma: float | None = None, k: float = 0.5, h: float = 5.0) -> dict[str, Any]:
    x = _arr(values, "values", 3)
    mu, sd, n = _baseline(x, baseline_n, target, sigma)
    res = {"target": mu, "sigma": sd, "k": k, "h": h, "baseline_n": n, **_cusum(x, mu, sd, k, h)}
    return _envelope("cusum_chart", {"values": x, "baseline_n": n, "target": target, "sigma": sigma, "k": k, "h": h}, res,
                     ["tabular CUSUM with reference value k·σ and decision interval h·σ; counters restart after an alarm",
                      "default k=0.5, h=5 targets ~1σ mean shifts under independent normal data"])


# ---------------------------------------------------------------- emerging concern (LS-077)
def detect_emerging_concern(series: Sequence[float], spec_limits: tuple[float | None, float | None],
                            baseline_n: int | None = None, lam: float = 0.2, L: float = 3.0, k: float = 0.5,
                            h: float = 5.0, recent_window: int = 5) -> dict[str, Any]:
    x = _arr(series, "series", 8)
    lo, hi = (None if v is None else _num(v, "spec limit") for v in spec_limits)
    if lo is None and hi is None:
        raise ValueError("at least one specification limit is required")
    if lo is not None and hi is not None and lo >= hi:
        raise ValueError("lower specification limit must be below upper")
    n = baseline_n or min(10, x.size // 2)
    mu, sd, n = _baseline(x, n, None, None)
    out_of_spec = [i for i, v in enumerate(x) if (lo is not None and v < lo) or (hi is not None and v > hi)]
    rules, ew, cu = _we_rules(x, mu, sd), _ewma(x, mu, sd, lam, L), _cusum(x, mu, sd, k, h)
    signals = {name: idx for name, idx in {**rules, "EWMA": ew["alarm_indices"], "CUSUM": cu["alarm_indices"]}.items() if idx}
    evidence = sorted({i for v in signals.values() for i in v})
    cutoff = x.size - recent_window
    active = {name: [i for i in idx if i >= cutoff] for name, idx in signals.items()}
    active = {name: idx for name, idx in active.items() if idx}
    slope = stats.linregress(np.arange(x.size), x)
    margins = [(hi - v) / sd for v in x if hi is not None] + [(v - lo) / sd for v in x if lo is not None]
    if out_of_spec:
        status = "out_of_spec_handle_via_deviation_process"
    elif active:
        status = "emerging_concern_not_deviation"
    elif evidence:
        status = "historical_signal_not_active"
    else:
        status = "no_concern"
    res = {"status": status, "concern": status == "emerging_concern_not_deviation", "evidence_indices": evidence,
           "signals": signals, "active_signals": active, "first_signal_index": evidence[0] if evidence else None,
           "out_of_spec_indices": out_of_spec, "minimum_margin_to_spec_sigma": min(margins),
           "trend_slope_per_point": float(slope.slope), "trend_p_value": float(slope.pvalue),
           "parameters": {"spec_limits": [lo, hi], "baseline_n": n, "lam": lam, "L": L, "k": k, "h": h,
                          "recent_window": recent_window},
           "basis": {"signals": sorted(active), "evidence_indices": sorted({i for v in active.values() for i in v}),
                     "series_hash": content_hash(x.tolist()), "n_points": int(x.size)}}
    if res["concern"]:
        res["recommendation"] = {"proposal": "review_process_trend_before_deviation", "requires_human_decision": True,
                                 "basis": res["basis"]}
    return _envelope("detect_emerging_concern", {"series": x, "spec_limits": [lo, hi], "baseline_n": n, "lam": lam, "L": L,
                                                 "k": k, "h": h, "recent_window": recent_window}, res,
                     ["limits from the first baseline_n points, assumed in control and representative",
                      "a signal is statistical evidence of change, not a cause and not a formal deviation",
                      "out-of-spec points are outside this method; use the deviation process"],
                     ["baseline shorter than 20 points"] if n < 20 else [])


def update_recommendation_basis(prev_result: dict[str, Any], new_series: Sequence[float]) -> dict[str, Any]:
    if prev_result.get("method") != "detect_emerging_concern":
        raise ValueError("prev_result must be a detect_emerging_concern result")
    p = prev_result["result"]["parameters"]
    new = detect_emerging_concern(new_series, tuple(p["spec_limits"]), p["baseline_n"], p["lam"], p["L"], p["k"], p["h"],
                                  p["recent_window"])
    prev, cur = prev_result["result"], new["result"]
    had = prev["status"] == "emerging_concern_not_deviation"
    if cur["status"] == "out_of_spec_handle_via_deviation_process":
        rec = "superseded_by_out_of_spec_deviation_process"
    elif cur["concern"]:
        rec = "reaffirmed_basis_updated" if had else "newly_supported"
    else:
        rec = "withdrawn_basis_changed" if had else "no_recommendation"
    res = {"recommendation_status": rec, "basis_changed": prev["basis"] != cur["basis"], "previous_status": prev["status"],
           "new_status": cur["status"], "previous_basis": prev["basis"], "new_basis": cur["basis"],
           "previous_inputs_hash": prev_result["inputs_hash"], "new_inputs_hash": new["inputs_hash"],
           "new_analysis": cur, "recommendation": cur.get("recommendation")}
    return _envelope("update_recommendation_basis", {"prev_inputs_hash": prev_result["inputs_hash"],
                                                     "new_series": new_series}, res,
                     new["validity_limits"] + ["a withdrawn recommendation reflects the new data only; earlier data remain on record"])


# ---------------------------------------------------------------- cohorts and yield (LS-076)
def _clean(vals: Sequence[Any]) -> tuple[np.ndarray, int]:
    keep = [float(v) for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not all(math.isfinite(v) for v in keep):
        raise ValueError("cohort values contain infinite entries")
    return np.asarray(keep, dtype=float), len(vals) - len(keep)


def compare_cohorts(cohorts: Sequence[dict[str, Any]], process_stage_key: str = "process_stage",
                    compat_keys: Sequence[str] = ("scale", "process_version"),
                    confounder_keys: Sequence[str] = ("site", "scale", "raw_material_lot", "equipment", "start_time"),
                    alpha: float = 0.05) -> dict[str, Any]:
    if len(cohorts) != 2:
        raise ValueError("compare_cohorts compares exactly two cohorts")
    ids = [str(c.get("id")) for c in cohorts]
    metas = [c.get("metadata") or {} for c in cohorts]
    units = {c.get("unit") for c in cohorts}
    if len(units) != 1 or None in units:
        raise ValueError("cohorts must declare one identical unit; convert before comparing")
    reasons = []
    for key in (process_stage_key, *compat_keys):
        vals = [m.get(key) for m in metas]
        if any(v is None for v in vals):
            reasons.append(f"{key} missing for {[i for i, v in zip(ids, vals) if v is None]}")
        elif vals[0] != vals[1]:
            reasons.append(f"{key} differs: {dict(zip(ids, vals))}")
    cleaned = [_clean(c.get("values") or []) for c in cohorts]
    missing = {i: {"missing": m, "used": int(a.size), "supplied": int(a.size) + m} for i, (a, m) in zip(ids, cleaned)}
    confounders = []
    for key in confounder_keys:
        vals = [m.get(key) for m in metas]
        if any(v is None for v in vals):
            confounders.append({"factor": key, "status": "unknown", "values": dict(zip(ids, vals))})
        elif vals[0] != vals[1]:
            entry = {"factor": key, "status": "differs", "values": dict(zip(ids, vals))}
            t = [parse_iso(str(v)) if key.endswith("time") else None for v in vals]
            if all(t):
                entry["time_gap_days"] = abs((t[0] - t[1]).total_seconds()) / 86400  # type: ignore[operator]
            confounders.append(entry)
    base = {"cohort_ids": ids, "unit": units.pop(), "process_stage_key": process_stage_key, "confounders": confounders,
            "missing_data": missing, "causal_claim_supported": False}
    limits = ["compares only cohorts with identical process stage and compat_keys metadata",
              "Welch t-test assumes independent, approximately normal batches; batch values are not randomized",
              "listed confounders are only those present in metadata; unlisted differences cannot be excluded",
              "an observed difference does not establish that site, scale or any factor caused it"]
    inputs = {"cohorts": [{"id": i, "metadata": m, "values": c.get("values")} for i, m, c in zip(ids, metas, cohorts)],
              "process_stage_key": process_stage_key, "compat_keys": list(compat_keys), "alpha": alpha}
    if reasons:
        return _envelope("compare_cohorts", inputs, {**base, "status": "not_comparable", "reasons": reasons}, limits)
    (a, _), (b, _) = cleaned
    if a.size < 2 or b.size < 2:
        raise ValueError("each cohort needs at least 2 non-missing values")
    n1, n2, v1, v2 = a.size, b.size, a.var(ddof=1), b.var(ddof=1)
    diff, se = float(a.mean() - b.mean()), math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        raise ValueError("zero variance in both cohorts; test undefined")
    df = se ** 4 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    t = diff / se
    p = float(2 * stats.t.sf(abs(t), df))
    tc = float(stats.t.ppf(1 - alpha / 2, df))
    sp = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    g = (diff / sp) * (1 - 3 / (4 * (n1 + n2) - 9)) if sp > 0 else None
    seg = math.sqrt((n1 + n2) / (n1 * n2) + g ** 2 / (2 * (n1 + n2))) if g is not None else None
    z = float(stats.norm.ppf(1 - alpha / 2))
    res = {**base, "status": "compared", "means": {ids[0]: float(a.mean()), ids[1]: float(b.mean())}, "mean_difference": diff,
           "welch_t": t, "df": df, "p_value": p, "ci_level": 1 - alpha, "ci_mean_difference": [diff - tc * se, diff + tc * se],
           "hedges_g": g, "hedges_g_ci_approx": None if g is None else [g - z * seg, g + z * seg]}  # type: ignore[operator]
    warn = [f"{c['factor']} {c['status']} between cohorts; difference may be confounded" for c in confounders]
    warn += [f"{i}: {v['missing']} missing value(s) excluded" for i, v in missing.items() if v["missing"]]
    return _envelope("compare_cohorts", inputs, res, limits, warn)


def compare_cohorts_authorized(identity: Any, ctx: Any, cohorts: Sequence[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    """Compare only cohorts whose every source record the caller may read; otherwise return no statistics."""
    denied = {}
    for c in cohorts:
        d = identity.check_derived(ctx, c.get("sources") or [])
        if not d:
            denied[str(c.get("id"))] = d.reason
    if denied:
        return _envelope("compare_cohorts", {"cohort_ids": [c.get("id") for c in cohorts]},
                         {"status": "not_authorized", "reasons": denied, "causal_claim_supported": False},
                         ["no statistics are computed when any cohort source is unauthorized"])
    return compare_cohorts(cohorts, **kw)


def step_yield(input_amount: float, output_amount: float, input_unit: str, output_unit: str | None = None) -> dict[str, Any]:
    i, o = _num(input_amount, "input_amount", positive=True), _num(output_amount, "output_amount", nonneg=True)
    o = convert_unit(o, output_unit or input_unit, input_unit)
    warn = ["yield exceeds 100%: check units, assay basis or accounting"] if o > i * (1 + 1e-9) else []
    return _envelope("step_yield", {"input": i, "output": output_amount, "input_unit": input_unit, "output_unit": output_unit},
                     {"yield_fraction": o / i, "yield_percent": 100 * o / i, "basis_unit": input_unit},
                     ["output is converted to the input unit; both must be the same quantity (e.g. mass of product)"], warn)


def cumulative_yield(steps: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not steps:
        raise ValueError("at least one step is required")
    rows, cum, warns = [], 1.0, []
    for s in steps:
        y = step_yield(s["input"], s["output"], s["unit"], s.get("output_unit"))
        f = y["result"]["yield_fraction"]
        cum *= f
        warns += [f"{s.get('name', '?')}: {w}" for w in y["warnings"]]
        rows.append({"name": s.get("name"), "yield_percent": 100 * f, "cumulative_percent": 100 * cum})
    return _envelope("cumulative_yield", {"steps": steps}, {"steps": rows, "cumulative_fraction": cum,
                                                           "cumulative_percent": 100 * cum},
                     ["cumulative yield is the product of step yields and assumes each step's yield is on a comparable basis"], warns)


# ---------------------------------------------------------------- OEE (LS-031)
def oee(planned_time: float, run_time: float, ideal_cycle_time: float, total_count: float, good_count: float,
        time_unit: str = "min", cycle_time_unit: str | None = None) -> dict[str, Any]:
    pt, rt = _num(planned_time, "planned_time", positive=True), _num(run_time, "run_time", positive=True)
    ct = convert_unit(_num(ideal_cycle_time, "ideal_cycle_time", positive=True), cycle_time_unit or time_unit, time_unit)
    tot, good = _num(total_count, "total_count", positive=True), _num(good_count, "good_count", nonneg=True)
    if rt > pt:
        raise ValueError("run_time cannot exceed planned_time")
    if good > tot:
        raise ValueError("good_count cannot exceed total_count")
    a, p, q = rt / pt, ct * tot / rt, good / tot
    warn = ["performance > 1: ideal cycle time is likely too long or counts are wrong"] if p > 1 else []
    return _envelope("oee", {"planned_time": pt, "run_time": rt, "ideal_cycle_time": ideal_cycle_time, "total_count": tot,
                             "good_count": good, "time_unit": time_unit, "cycle_time_unit": cycle_time_unit},
                     {"availability": a, "performance": p, "quality": q, "oee": a * p * q},
                     ["OEE = availability × performance × quality with the supplied ideal cycle time",
                      "values are only comparable between equipment using the same ideal-rate definition"], warn)


# ---------------------------------------------------------------- curve fitting (LS-030)
def _logistic4(x: np.ndarray, bottom: float, top: float, ec50: float, hill: float) -> np.ndarray:
    return bottom + (top - bottom) / (1 + (ec50 / x) ** hill)


def fit_4pl(x: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    xs, ys = _arr(x, "x", 5), _arr(y, "y", 5)
    if xs.size != ys.size:
        raise ValueError("x and y must have equal length")
    if np.any(xs <= 0):
        raise ValueError("x (concentration/dose) must be positive")
    p0 = [ys.min(), ys.max(), float(np.median(xs)), 1.0]
    try:
        popt, pcov = optimize.curve_fit(_logistic4, xs, ys, p0=p0, bounds=([-np.inf, -np.inf, 1e-12, 0.05],
                                        [np.inf, np.inf, np.inf, 20.0]), maxfev=20000)
    except (RuntimeError, optimize.OptimizeWarning) as exc:
        raise ValueError(f"4PL fit did not converge: {exc}") from exc
    resid = ys - _logistic4(xs, *popt)
    ss_res, ss_tot = float(resid @ resid), float(((ys - ys.mean()) ** 2).sum())
    se = np.sqrt(np.diag(pcov)) if np.all(np.isfinite(pcov)) else [None] * 4
    names = ("bottom", "top", "ec50", "hill")
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    warn = []
    if xs.min() > popt[2] or xs.max() < popt[2]:
        warn.append("EC50 lies outside the tested range (extrapolated)")
    if r2 is not None and r2 < 0.95:
        warn.append("R² below 0.95; model may not describe the data")
    return _envelope("fit_4pl", {"x": xs, "y": ys},
                     {"params": dict(zip(names, popt)), "param_se": dict(zip(names, se)), "ec50": popt[2],
                      "r_squared": r2, "residual_se": math.sqrt(ss_res / (xs.size - 4)) if xs.size > 4 else None,
                      "n": xs.size}, ["y = bottom + (top - bottom)/(1 + (EC50/x)^hill), hill in [0.05, 20]",
                                      "standard errors are asymptotic and unreliable with few points or high noise",
                                      "a local least-squares optimum; check the fit visually"], warn)


# ---------------------------------------------------------------- qPCR (LS-030)
def qpcr_standard_curve(quantities: Sequence[float], ct: Sequence[float]) -> dict[str, Any]:
    q, c = _arr(quantities, "quantities", 3), _arr(ct, "ct", 3)
    if q.size != c.size:
        raise ValueError("quantities and ct must have equal length")
    if np.any(q <= 0):
        raise ValueError("quantities must be positive")
    lq = np.log10(q)
    if np.ptp(lq) == 0:
        raise ValueError("standards need at least two distinct quantities")
    r = stats.linregress(lq, c)
    if r.slope >= 0:
        raise ValueError("Ct must decrease with quantity; slope is not negative")
    eff = 10 ** (-1 / r.slope) - 1
    warn = []
    if not 0.9 <= eff <= 1.1:
        warn.append(f"amplification efficiency {eff:.3f} outside 0.90-1.10")
    if r.rvalue ** 2 < 0.98:
        warn.append("R² below 0.98")
    return _envelope("qpcr_standard_curve", {"quantities": q, "ct": c},
                     {"slope": r.slope, "intercept": r.intercept, "r_squared": r.rvalue ** 2, "efficiency": eff,
                      "efficiency_percent": 100 * eff, "log10_range": [lq.min(), lq.max()]},
                     ["Ct = slope·log10(quantity) + intercept; efficiency = 10^(-1/slope) - 1",
                      "linear only within the tested standard range"], warn)


def qpcr_quantify(slope: float, intercept: float, ct_values: Sequence[float],
                  log10_range: Sequence[float] | None = None) -> dict[str, Any]:
    s, i, c = _num(slope, "slope"), _num(intercept, "intercept"), _arr(ct_values, "ct_values", 1)
    if s >= 0:
        raise ValueError("slope must be negative")
    lq = (c - i) / s
    warn = []
    if log10_range is not None:
        out = np.nonzero((lq < min(log10_range)) | (lq > max(log10_range)))[0].tolist()
        warn = [f"samples at indices {out} are outside the standard range (extrapolated)"] if out else []
    return _envelope("qpcr_quantify", {"slope": s, "intercept": i, "ct_values": c, "log10_range": log10_range},
                     {"quantities": 10 ** lq, "log10_quantities": lq},
                     ["valid only for the same assay, plate chemistry and within the standard range"], warn)


def qpcr_delta_delta_ct(sample_target: Sequence[float], sample_ref: Sequence[float], control_target: Sequence[float],
                        control_ref: Sequence[float]) -> dict[str, Any]:
    st, sr, ct, cr = (_arr(v, n, 1) for v, n in [(sample_target, "sample_target"), (sample_ref, "sample_ref"),
                                                 (control_target, "control_target"), (control_ref, "control_ref")])
    d_s, d_c = st.mean() - sr.mean(), ct.mean() - cr.mean()
    dd = d_s - d_c
    sds = [a.std(ddof=1) if a.size > 1 else None for a in (st, sr, ct, cr)]
    sd = math.sqrt(sum(v * v for v in sds)) if all(v is not None for v in sds) else None
    res = {"delta_ct_sample": d_s, "delta_ct_control": d_c, "delta_delta_ct": dd, "fold_change": 2.0 ** (-dd),
           "fold_change_range": None if sd is None else [2.0 ** (-(dd + sd)), 2.0 ** (-(dd - sd))]}
    return _envelope("qpcr_delta_delta_ct", {"sample_target": st, "sample_ref": sr, "control_target": ct, "control_ref": cr}, res,
                     ["2^-ΔΔCt assumes ~100% and equal amplification efficiency for target and reference",
                      "reference gene must be stable across conditions"],
                     [] if sd is not None else ["single replicate: no dispersion estimate"])


# ---------------------------------------------------------------- chromatography (LS-030)
def usp_plate_count(retention_time: float, width: float, basis: str = "tangent") -> dict[str, Any]:
    t, w = _num(retention_time, "retention_time", positive=True), _num(width, "width", positive=True)
    if basis == "tangent":
        n = 16 * (t / w) ** 2
    elif basis == "half_height":
        n = 5.54 * (t / w) ** 2
    else:
        raise ValueError("basis must be 'tangent' or 'half_height'")
    return _envelope("usp_plate_count", {"retention_time": t, "width": w, "basis": basis}, {"plate_count": n, "basis": basis},
                     ["retention time and width must share one unit", "width is baseline (tangent) width W or half-height width W½"])


def resolution(t1: float, t2: float, w1: float, w2: float) -> dict[str, Any]:
    a, b, x, y = (_num(v, n, positive=True) for v, n in [(t1, "t1"), (t2, "t2"), (w1, "w1"), (w2, "w2")])
    if b <= a:
        raise ValueError("t2 must be later than t1")
    return _envelope("resolution", {"t1": a, "t2": b, "w1": x, "w2": y}, {"resolution": 2 * (b - a) / (x + y)},
                     ["Rs = 2(t2 - t1)/(w1 + w2) with baseline peak widths in the time unit of t"])


def chromatography_analysis(time: Sequence[float], signal_values: Sequence[float], baseline: float = 0.0,
                            min_prominence_fraction: float = 0.05) -> dict[str, Any]:
    t, y = _arr(time, "time", 5), _arr(signal_values, "signal", 5)
    if t.size != y.size or np.any(np.diff(t) <= 0):
        raise ValueError("time must be strictly increasing and match signal length")
    y = y - _num(baseline, "baseline")
    if np.ptp(y) <= 0:
        raise ValueError("signal is flat")
    idx, _ = signal.find_peaks(y, prominence=min_prominence_fraction * np.ptp(y))
    if idx.size == 0:
        return _envelope("chromatography_analysis", {"time": t, "signal": signal_values, "baseline": baseline},
                         {"peaks": []}, ["no peaks above the prominence threshold"], ["no peaks detected"])
    grid = np.arange(t.size)
    at = lambda ip: float(np.interp(ip, grid, t))  # noqa: E731
    half = signal.peak_widths(y, idx, rel_height=0.5)
    w4 = signal.peak_widths(y, idx, rel_height=0.8647)  # width at e^-2 height = 4σ for a Gaussian
    t05 = signal.peak_widths(y, idx, rel_height=0.95)
    edge = signal.peak_widths(y, idx, rel_height=0.995)
    peaks = []
    for n, p in enumerate(idx):
        lo = max(int(math.floor(edge[2][n])), int(idx[n - 1] + np.argmin(y[idx[n - 1]:p + 1])) if n else 0)
        hi = min(int(math.ceil(edge[3][n])), int(p + np.argmin(y[p:idx[n + 1] + 1])) if n + 1 < idx.size else t.size - 1)
        w_half, w_base = at(half[3][n]) - at(half[2][n]), at(w4[3][n]) - at(w4[2][n])
        front, w05 = t[p] - at(t05[2][n]), at(t05[3][n]) - at(t05[2][n])
        peaks.append({"index": int(p), "retention_time": float(t[p]), "height": float(y[p]),
                      "area": float(integrate.trapezoid(y[lo:hi + 1], t[lo:hi + 1])), "width_half_height": w_half,
                      "width_base_4sigma": w_base, "plate_count_half_height": 5.54 * (t[p] / w_half) ** 2,
                      "plate_count_usp": 16 * (t[p] / w_base) ** 2,
                      "tailing_factor": w05 / (2 * front) if front > 0 else None})
    for a, b in itertools.pairwise(peaks):
        b["resolution_from_previous"] = 2 * (b["retention_time"] - a["retention_time"]) / (a["width_base_4sigma"] + b["width_base_4sigma"])
    return _envelope("chromatography_analysis", {"time": t, "signal": signal_values, "baseline": baseline,
                                                 "min_prominence_fraction": min_prominence_fraction},
                     {"peaks": peaks, "baseline_subtracted": baseline},
                     ["trapezoidal area over each peak's valley/0.5%-height window; tails beyond are excluded",
                      "base width estimated from the e^-2 height width (exact for Gaussian, approximate otherwise)",
                      "closely overlapping peaks are split at the valley (perpendicular drop), not deconvolved",
                      "retention time is the sampled apex; time resolution limits its precision"],
                     [] if np.median(np.diff(t)) * 10 <= min(p["width_half_height"] for p in peaks) else
                     ["sampling interval is coarse relative to peak width; area/width may be imprecise"])


# ---------------------------------------------------------------- DOE (LS-031)
def full_factorial(factors: Sequence[str] | dict[str, Sequence[float]]) -> dict[str, Any]:
    names = list(factors)
    if not 1 <= len(names) <= 10 or len(set(names)) != len(names):
        raise ValueError("2^k design needs 1-10 uniquely named factors")
    rows = [[-1 + 2 * ((i >> j) & 1) for j in range(len(names))] for i in range(2 ** len(names))]
    actual = None
    if isinstance(factors, dict):
        for n in names:
            if len(factors[n]) != 2 or not factors[n][0] < factors[n][1]:
                raise ValueError(f"{n}: provide (low, high) levels")
        actual = [{n: factors[n][(r[i] + 1) // 2] for i, n in enumerate(names)} for r in rows]
    return _envelope("full_factorial", {"factors": factors},
                     {"factors": names, "runs": len(rows), "coded": rows, "actual": actual},
                     ["2-level full factorial in standard order; randomize run order before execution",
                      "assumes factors can be set independently over the stated levels"])


def analyze_factorial(coded: Sequence[Sequence[float]], response: Sequence[float], factor_names: Sequence[str] | None = None,
                      interactions: bool = True) -> dict[str, Any]:
    X = np.asarray(coded, dtype=float)
    y = _arr(response, "response", 2)
    if X.ndim != 2 or X.shape[0] != y.size or not np.all(np.isin(X, (-1.0, 1.0))):
        raise ValueError("coded must be an n×k matrix of -1/+1 matching the response length")
    k = X.shape[1]
    names = list(factor_names or [chr(65 + i) for i in range(k)])
    if len(names) != k:
        raise ValueError("factor_names length must equal the number of factors")
    cols, terms = [np.ones(y.size)], ["Intercept"]
    for i in range(k):
        cols.append(X[:, i]); terms.append(names[i])
    if interactions:
        for i, j in itertools.combinations(range(k), 2):
            cols.append(X[:, i] * X[:, j]); terms.append(f"{names[i]}:{names[j]}")
    M = np.column_stack(cols)
    beta, _, rank, _ = np.linalg.lstsq(M, y, rcond=None)
    n, p = M.shape
    warn = []
    if n < p:
        warn.append(f"runs ({n}) < parameters ({p}): model not estimable; minimum-norm solution, effects are not unique")
    elif rank < p:
        warn.append("design matrix is rank deficient: some effects are aliased")
    elif n == p:
        warn.append("saturated model: no degrees of freedom for error")
    df = n - rank
    rse = float(np.sqrt(((y - M @ beta) ** 2).sum() / df)) if df > 0 else None
    return _envelope("analyze_factorial", {"coded": X, "response": y, "factor_names": names, "interactions": interactions},
                     {"terms": terms, "coefficients": dict(zip(terms, beta)),
                      "effects": {t: 2 * b for t, b in zip(terms[1:], beta[1:])}, "rank": int(rank), "n_runs": n,
                      "n_parameters": p, "residual_df": df, "residual_se": rse},
                     ["effect = 2 × coefficient for ±1 coding; least-squares solution",
                      "no significance is claimed without replicates or error df",
                      "main effects and 2-factor interactions only; higher-order terms are ignored"], warn)


# ---------------------------------------------------------------- liquid handler and plate assays (LS-031)
def liquid_handler_performance(target_volume: float, measurements: dict[str, Sequence[float]], volume_unit: str = "uL",
                               target_unit: str | None = None, cv_limit_percent: float | None = None,
                               bias_limit_percent: float | None = None) -> dict[str, Any]:
    tv = convert_unit(_num(target_volume, "target_volume", positive=True), target_unit or volume_unit, volume_unit)
    if not measurements:
        raise ValueError("measurements by channel are required")
    ch, warn = {}, []
    for name, vals in measurements.items():
        a = _arr(vals, f"channel {name}", 2)
        mean, sd = float(a.mean()), float(a.std(ddof=1))
        if mean == 0:
            raise ValueError(f"channel {name}: mean is zero; CV undefined")
        cv, bias = 100 * sd / abs(mean), 100 * (mean - tv) / tv
        ch[name] = {"n": int(a.size), "mean": mean, "sd": sd, "cv_percent": cv, "bias_percent": bias,
                    "within_cv_limit": None if cv_limit_percent is None else cv <= cv_limit_percent,
                    "within_bias_limit": None if bias_limit_percent is None else abs(bias) <= bias_limit_percent}
        if len(a) < 10:
            warn.append(f"channel {name}: fewer than 10 replicates; CV is imprecise")
    return _envelope("liquid_handler_performance", {"target_volume": tv, "measurements": measurements,
                                                    "volume_unit": volume_unit, "cv_limit": cv_limit_percent,
                                                    "bias_limit": bias_limit_percent},
                     {"target_volume": tv, "unit": volume_unit, "channels": ch},
                     ["measurements must be the dispensed volume in one unit (e.g. gravimetric/photometric, converted)",
                      "CV% uses the sample SD; bias% = (mean - target)/target", "limits are caller-supplied, not built in"], warn)


def z_prime(positive: Sequence[float], negative: Sequence[float]) -> dict[str, Any]:
    p, n = _arr(positive, "positive", 3), _arr(negative, "negative", 3)
    mp, mn = float(p.mean()), float(n.mean())
    if mp == mn:
        raise ValueError("control means are identical; Z' undefined")
    z = 1 - 3 * (p.std(ddof=1) + n.std(ddof=1)) / abs(mp - mn)
    warn = ["Z' < 0.5: assay window is marginal for screening"] if z < 0.5 else []
    return _envelope("z_prime", {"positive": p, "negative": n},
                     {"z_prime": z, "signal_to_background": mp / mn if mn != 0 else None, "mean_positive": mp,
                      "mean_negative": mn, "sd_positive": float(p.std(ddof=1)), "sd_negative": float(n.std(ddof=1))},
                     ["Z' = 1 - 3(σp + σn)/|μp - μn| using sample SDs", "assumes approximately normal control wells"], warn)


_PLATES = {96: (8, 12), 384: (16, 24)}


def validate_plate_map(plate_format: int, wells: Sequence[dict[str, Any]], min_controls: int = 3) -> dict[str, Any]:
    if plate_format not in _PLATES:
        raise ValueError("plate_format must be 96 or 384")
    rows, cols = _PLATES[plate_format]
    seen: dict[str, int] = {}
    invalid, bad_role = [], []
    roles = {"positive", "negative", "sample", "blank"}
    for w in wells:
        wid = str(w.get("well", "")).upper()
        m = re.fullmatch(r"([A-P])(\d{1,2})", wid)
        if not m or ord(m[1]) - 64 > rows or not 1 <= int(m[2]) <= cols:
            invalid.append(wid)
            continue
        wid = f"{m[1]}{int(m[2])}"
        seen[wid] = seen.get(wid, 0) + 1
        if w.get("role") not in roles:
            bad_role.append(wid)
    dup = sorted(w for w, c in seen.items() if c > 1)
    count = lambda r: sum(1 for w in wells if w.get("role") == r)  # noqa: E731
    issues = [f"invalid well ids: {invalid}"] * bool(invalid) + [f"duplicate wells: {dup}"] * bool(dup) + \
             [f"invalid roles at: {bad_role}"] * bool(bad_role)
    for r in ("positive", "negative"):
        if count(r) < min_controls:
            issues.append(f"fewer than {min_controls} {r} control wells")
    return _envelope("validate_plate_map", {"plate_format": plate_format, "wells": wells, "min_controls": min_controls},
                     {"valid": not issues, "issues": issues, "wells_expected": rows * cols, "wells_mapped": len(seen),
                      "wells_unmapped": rows * cols - len(seen)}, ["checks identifiers, duplicates, roles and control counts only",
                                                                  "does not check physical layout or edge effects"])


def plate_assay(plate_format: int, wells: Sequence[dict[str, Any]]) -> dict[str, Any]:
    report = validate_plate_map(plate_format, wells)["result"]
    if not report["valid"]:
        raise ValueError("invalid plate map: " + "; ".join(report["issues"]))
    vals = {r: [] for r in ("positive", "negative", "blank")}
    for w in wells:
        v = _num(w.get("value"), f"value for {w['well']}")
        if w["role"] in vals:
            vals[w["role"]].append(v)
    z = z_prime(vals["positive"], vals["negative"])
    res = {**z["result"], "plate_format": plate_format, "plate_map": report,
           "blank_mean": float(np.mean(vals["blank"])) if vals["blank"] else None}
    return _envelope("plate_assay", {"plate_format": plate_format, "wells": wells}, res, z["validity_limits"], z["warnings"])


# ---------------------------------------------------------------- drift monitoring (LS-089)
def population_stability_index(reference: Sequence[float], current: Sequence[float], bins: int = 10) -> dict[str, Any]:
    r, c = _arr(reference, "reference", 10), _arr(current, "current", 10)
    if bins < 2:
        raise ValueError("bins must be at least 2")
    edges = np.unique(np.quantile(r, np.linspace(0, 1, bins + 1)[1:-1]))
    edges = np.concatenate([[-np.inf], edges, [np.inf]])
    pr = np.maximum(np.histogram(r, edges)[0] / r.size, 1e-4)
    pc = np.maximum(np.histogram(c, edges)[0] / c.size, 1e-4)
    psi = float(np.sum((pc - pr) * np.log(pc / pr)))
    band = "stable" if psi < 0.1 else "moderate_shift" if psi < 0.25 else "major_shift"
    return _envelope("population_stability_index", {"reference": r, "current": c, "bins": bins},
                     {"psi": psi, "band": band, "bin_edges": edges[1:-1], "reference_fractions": pr, "current_fractions": pc},
                     ["bins are reference quantiles; empty bins are floored at 1e-4",
                      "bands (<0.1, <0.25, ≥0.25) are conventional rules of thumb, not validated acceptance criteria",
                      "detects input distribution shift, not whether outputs are correct"],
                     ["fewer than 100 points in a sample; PSI is noisy"] if min(r.size, c.size) < 100 else [])


class ProfileMonitor:
    """Persists per-profile drift state; suspension is prospective and never edits approved results."""
    KIND = "method_profile"

    def __init__(self, store: RecordStore, registry: Any | None = None, psi_threshold: float = 0.25,
                 correction_rate_threshold: float = 0.2, min_samples: int = 20) -> None:
        self.store, self.registry = store, registry
        self.psi_threshold, self.rate_threshold, self.min_samples = psi_threshold, correction_rate_threshold, min_samples

    @staticmethod
    def _id(task_kind: str, profile_id: str) -> str:
        return f"{task_kind}:{profile_id}"

    def get(self, tenant_id: str, task_kind: str, profile_id: str) -> dict[str, Any] | None:
        rec = self.store.read().get(tenant_id, self.KIND, self._id(task_kind, profile_id))
        return dict(rec.state, revision=rec.revision) if rec else None

    def evaluate(self, tenant_id: str, task_kind: str, profile_id: str, *, reference: Sequence[float] | None = None,
                 current: Sequence[float] | None = None, corrected: int | None = None, total: int | None = None,
                 by: str = "system", bins: int = 10) -> dict[str, Any]:
        psi = population_stability_index(reference, current, bins)["result"]["psi"] if reference is not None and current is not None else None
        rate = None
        warnings: list[str] = []
        if total is not None:
            if corrected is None or not 0 <= corrected <= total or total <= 0:
                raise ValueError("corrected must be within 0..total and total positive")
            rate = corrected / total
            if total < self.min_samples:
                warnings.append(f"only {total} findings; correction rate not used for suspension (min {self.min_samples})")
        if psi is None and rate is None:
            raise ValueError("provide a PSI input pair or correction counts")
        reasons = []
        if psi is not None and psi > self.psi_threshold:
            reasons.append(f"PSI {psi:.3f} > {self.psi_threshold}")
        if rate is not None and total >= self.min_samples and rate > self.rate_threshold:  # type: ignore[operator]
            reasons.append(f"correction rate {rate:.3f} > {self.rate_threshold}")
        pid, newly = self._id(task_kind, profile_id), False
        with self.store.transaction(by) as tx:
            rec = tx.get(tenant_id, self.KIND, pid)
            state = dict(rec.state) if rec else {"profile_id": profile_id, "task_kind": task_kind, "status": "active",
                                                 "reason": None, "observations": [], "policy": "prospective_only"}
            obs = {"at": iso(utc_now()), "psi": psi, "correction_rate": rate, "corrected": corrected, "total": total}
            state["observations"] = [*state["observations"], obs][-100:]
            state.update(latest_psi=psi if psi is not None else state.get("latest_psi"),
                         latest_correction_rate=rate if rate is not None else state.get("latest_correction_rate"))
            if reasons and state["status"] == "active":
                state.update(status="suspended", reason="; ".join(reasons), suspended_at=obs["at"])
                newly = True
            tx.put(tenant_id, self.KIND, pid, state, expected_revision=rec.revision if rec else None,
                   action="suspend" if newly else "evaluate", reason=state["reason"] if newly else None,
                   event_type="method_profile.suspended" if newly else "method_profile.evaluated",
                   event_payload={"task_kind": task_kind, "profile_id": profile_id, "status": state["status"]})
        if newly and self.registry is not None:
            self.registry.suspend(task_kind, profile_id)
        candidates = [p.profile_id for p in self.registry.qualified_profiles(task_kind)] if self.registry is not None and state["status"] == "suspended" else []
        return {**state, "newly_suspended": newly, "warnings": warnings, "replacement_candidates": candidates,
                "replacement_note": "candidates require their own evaluation and approval; approved results are unchanged"
                if state["status"] == "suspended" else None}


# ---------------------------------------------------------------- C0 gateway handlers (LS-056)
STATISTICS_METHODS: dict[str, Callable[..., dict[str, Any]]] = {
    f.__name__: f for f in (imr_chart, ewma_chart, cusum_chart, detect_emerging_concern, compare_cohorts, step_yield,
                            cumulative_yield, oee, fit_4pl, qpcr_standard_curve, qpcr_quantify, qpcr_delta_delta_ct,
                            usp_plate_count, resolution, chromatography_analysis, full_factorial, analyze_factorial,
                            liquid_handler_performance, z_prime, plate_assay, validate_plate_map,
                            population_stability_index)}


def statistics_handler(payload: dict[str, Any]) -> dict[str, Any]:
    fn = STATISTICS_METHODS.get(payload.get("method", ""))
    if fn is None:
        raise ValueError(f"unknown statistics method {payload.get('method')!r}; available: {sorted(STATISTICS_METHODS)}")
    return fn(**(payload.get("params") or {}))


def limit_check_handler(payload: dict[str, Any]) -> dict[str, Any]:
    value, unit = _num(payload["value"], "value"), payload["unit"]
    limit_unit = payload.get("limit_unit") or unit
    low, high = payload.get("low"), payload.get("high")
    if low is None and high is None:
        raise ValueError("at least one of low/high is required")
    low = None if low is None else _num(low, "low")
    high = None if high is None else _num(high, "high")
    if low is not None and high is not None and low > high:
        raise ValueError("low limit exceeds high limit")
    v = convert_unit(value, unit, limit_unit)
    status = "below_low" if low is not None and v < low else "above_high" if high is not None and v > high else "within_limits"
    return _envelope("limit_check", payload, {"status": status, "value_in_limit_unit": v, "unit": limit_unit,
                                              "margin_to_low": None if low is None else v - low,
                                              "margin_to_high": None if high is None else high - v},
                     ["limits are inclusive; unit conversion uses the pint default registry",
                      "the check compares numbers only; it does not decide disposition"])


def unit_conversion_handler(payload: dict[str, Any]) -> dict[str, Any]:
    out = convert_unit(_num(payload["value"], "value"), payload["from_unit"], payload["to_unit"])
    return _envelope("unit_conversion", payload, {"value": out, "unit": payload["to_unit"]},
                     ["offset units (e.g. degC) are converted as absolute temperatures", "pint default registry definitions"])


def register_handlers(gateway: Any) -> None:
    gateway.register_handler("statistics", statistics_handler, METHOD_VERSION)
    gateway.register_handler("limit_check", limit_check_handler, METHOD_VERSION)
    gateway.register_handler("unit_conversion", unit_conversion_handler, METHOD_VERSION)
