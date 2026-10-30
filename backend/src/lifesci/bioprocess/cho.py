"""Simple CHO batch growth / glucose model fitted to a verified CMO delivery.

Same equations as the real-CHO experiment (``benchmarks/external_simulators/cho_real.py``):
Monod glucose-limited growth with first-order death and a glucose mass balance. That file is
part of a frozen experiment protocol, so the few lines of model code are repeated here rather
than imported from benchmark code.

The fit uses only the verified dataset it is given. Batches other than the forecast batch train
the parameters; the forecast batch contributes only readings at or before the cutoff. Later
readings of the forecast batch are compared with the forecast and are never used to fit.
"""
from __future__ import annotations

from statistics import fmean, median
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

VERSION = 'cho-monod-batch-1'
FIELDS = ('viable_cell_density', 'glucose')
UNITS = {'viable_cell_density': 'million cells/mL', 'glucose': 'g/L'}
SCALE = {'viable_cell_density': 1e-6, 'glucose': 1.0}
SOURCE_UNITS = {'viable_cell_density': 'cells/mL', 'glucose': 'g/L'}
NAMES = ['mu_max_per_h', 'death_per_h', 'Ks_g_l', 'yield_million_cells_ml_per_g_l', 'maintenance_g_l_per_million_cells_ml_h']
BOUNDS = ([.005, 1e-7, .01, .1, .00001], [.08, .03, 10., 10., .1])
STARTS = ([.035, .003, .5, 2., .005], [.05, .01, 2., 3., .01], [.025, .001, .1, 1., .001])
EQUATIONS = 'mu = mu_max·G/(Ks+G); dX/dt = (mu − kd)·X; dG/dt = −(mu/Y + m·G/(Ks+G))·X'
LIMITATIONS = [
    'Constant lumped kinetics. Other nutrients, metabolites, stress, pH and temperature effects are not modelled.',
    'Batch growth phase only. Readings after the horizon (death phase, feeding) are excluded from fitting and forecasting.',
    'Parameters may be weakly identifiable; they are effective values, not measured biology.',
    'In the earlier real-CHO experiment this model made glucose forecasts worse (MAE 0.60 → 0.72 g/L). Treat forecasts as a rough reference.',
]


def _hours(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def series(measurements: list[dict[str, Any]], horizon_h: float) -> dict[str, list[dict[str, Any]]]:
    """Per batch, one reading per (time, field) in model units, keeping every source location."""
    grouped: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    for m in measurements:
        t = _hours(m.get('time'))
        if m.get('parameter') not in FIELDS or t is None or t > horizon_h or not isinstance(m.get('value'), (int, float)):
            continue
        if m.get('unit') != SOURCE_UNITS[m['parameter']] or m['value'] <= 0:
            continue
        grouped.setdefault((str(m['batch']), t, m['parameter']), []).append(m)
    out: dict[str, list[dict[str, Any]]] = {}
    for (batch, t, field), items in sorted(grouped.items()):
        # The same reading can arrive twice (LIMS export and certificate). Identical values collapse;
        # differing duplicates are averaged and flagged.
        values = sorted({float(i['value']) for i in items})
        out.setdefault(batch, []).append({
            'time_h': t, 'field': field, 'value': fmean(values) * SCALE[field],
            'duplicates_differ': len(values) > 1,
            'sources': sorted({_label(i.get('source')) for i in items}), 'measurement_ids': sorted(i['id'] for i in items)})
    return out


def _label(source: dict[str, Any] | None) -> str:
    source = source or {}
    if source.get('sheet') and source.get('cell'):
        return f"{source['path']} · {source['sheet']}!{source['cell']}"
    if source.get('row'):
        return f"{source['path']} · row {source['row']}"
    if source.get('page'):
        return f"{source['path']} · page {source['page']}"
    return str(source.get('path', ''))


def _initial(rows: list[dict[str, Any]]) -> tuple[float, list[float]] | None:
    """Earliest time with both fields measured."""
    by_time: dict[float, dict[str, float]] = {}
    for r in rows:
        by_time.setdefault(r['time_h'], {})[r['field']] = r['value']
    for t in sorted(by_time):
        if all(f in by_time[t] for f in FIELDS):
            return t, [by_time[t][f] for f in FIELDS]
    return None


def integrate(parameters, state, start, times):
    mu_max, kd, ks, yield_xg, maintenance = parameters

    def rhs(t, z):
        x, g = np.exp(z)
        mu = mu_max * g / (ks + g)
        return [mu - kd, -(mu_max / yield_xg + maintenance) * x / (ks + g)]
    times = np.array(times, dtype=float)
    if not len(times):
        return np.empty((0, 2))
    if times[-1] == start:
        return np.tile(state, (len(times), 1))
    sol = solve_ivp(rhs, [start, times[-1]], np.log(np.maximum(state, 1e-9)), t_eval=times, method='LSODA', rtol=1e-7, atol=1e-9)
    if not sol.success or not np.all(np.isfinite(sol.y)):
        raise ValueError('CHO model integration failed')
    return np.exp(sol.y.T)


def fit(training: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    usable = {b: rows for b, rows in training.items() if _initial(rows) and len(rows) >= 4}
    if len(usable) < 2:
        raise ValueError('at least two other batches with viable cell density and glucose readings are needed to fit the model')

    def residual(logpars):
        pars = np.exp(logpars)
        errors = []
        for rows in usable.values():
            start, state = _initial(rows)
            rows = [r for r in rows if r['time_h'] >= start]
            times = sorted({r['time_h'] for r in rows})
            pred = {t: p for t, p in zip(times, integrate(pars, state, start, times))}
            for r in rows:
                v = pred[r['time_h']][FIELDS.index(r['field'])]
                errors.append(np.log(max(v, 1e-12) / r['value']) if r['field'] == FIELDS[0] else (v - r['value']) / 7.)
        return np.array(errors)
    fits = [least_squares(residual, np.log(s), bounds=(np.log(BOUNDS[0]), np.log(BOUNDS[1])), max_nfev=120, loss='soft_l1')
            for s in STARTS]
    best = min(fits, key=lambda f: f.cost)
    params = np.exp(best.x)
    at_bound = [NAMES[i] for i, v in enumerate(params) if np.isclose(v, BOUNDS[0][i], rtol=1e-3) or np.isclose(v, BOUNDS[1][i], rtol=1e-3)]
    return {'parameters': dict(zip(NAMES, params.tolist())), 'training_batches': sorted(usable),
            'optimizer_converged': bool(best.success), 'cost': float(best.cost), 'parameters_at_bounds': at_bound}


def forecast(dataset: dict[str, Any], batch: str, cutoff_h: float = 72., horizon_h: float = 120.) -> dict[str, Any]:
    data = series(dataset['measurements'], horizon_h)
    if batch not in data:
        raise ValueError(f'batch {batch} has no viable cell density or glucose readings up to {horizon_h:g} h')
    model = fit({b: rows for b, rows in data.items() if b != batch})
    params = list(model['parameters'].values())
    rows = data[batch]
    known = [r for r in rows if r['time_h'] <= cutoff_h]
    first = _initial(known)
    if first is None:
        raise ValueError(f'batch {batch} needs a reading of both fields at or before {cutoff_h:g} h')
    # Assimilate readings up to the cutoff with fitted parameters fixed.
    start, state = first
    state = np.array(state)
    for t in sorted({r['time_h'] for r in known if r['time_h'] >= start}):
        state = integrate(params, state, start, [t])[0]
        for r in known:
            if r['time_h'] == t:
                state[FIELDS.index(r['field'])] = r['value']
        start = t
    later = [r for r in rows if r['time_h'] > cutoff_h]
    grid = sorted({*np.linspace(start, horizon_h, 49).round(3).tolist(), *[r['time_h'] for r in later]})
    traj = integrate(params, state, start, grid)
    lookup = dict(zip(grid, traj))
    comparisons = []
    for r in later:
        predicted = float(lookup[r['time_h']][FIELDS.index(r['field'])])
        comparisons.append({'time_h': r['time_h'], 'field': r['field'], 'unit': UNITS[r['field']], 'measured': r['value'],
                            'predicted': predicted, 'absolute_error': abs(predicted - r['value']), 'sources': r['sources']})
    errors = {f: {'readings': len(c), 'mean_absolute_error': fmean(e['absolute_error'] for e in c),
                  'median_measured': median(e['measured'] for e in c), 'unit': UNITS[f]}
              for f in FIELDS if (c := [e for e in comparisons if e['field'] == f])}
    flagged = sorted({r['time_h'] for r in rows if r['duplicates_differ']})
    return {
        'model_version': VERSION, 'equations': EQUATIONS, 'limitations': LIMITATIONS,
        'batch': batch, 'cutoff_h': cutoff_h, 'horizon_h': horizon_h, 'fit': model,
        'observed': [{k: r[k] for k in ('time_h', 'field', 'value', 'sources', 'duplicates_differ')} for r in rows],
        'trajectory': [{'time_h': t, **{f: float(v[i]) for i, f in enumerate(FIELDS)}} for t, v in zip(grid, traj)],
        'holdout_comparison': comparisons, 'holdout_errors': errors, 'units': UNITS,
        'warnings': (['Duplicate readings with different values were averaged at ' + ', '.join(f'{t:g} h' for t in flagged) + '.'] if flagged else [])
        + ([] if comparisons else ['No readings after the cutoff within the horizon, so the forecast cannot be checked.']),
    }
