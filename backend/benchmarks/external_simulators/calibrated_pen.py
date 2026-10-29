"""Versioned PenSim parameter estimation from visible completed-source data.

No evaluator seed, receiving outcome, endpoint multiplier, or additive DO bias.
The original equations and controllers are retained. This is an effective
parameter fit, not identification of the true hidden biological parameters.
"""
from copy import deepcopy
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from .upstream import pen_module, pen_recipe, monitor_pen
from .forecast_contract import evidence_hash

METHOD = 'source_trajectory_kinetics_v2'
PARAMETERS = ('kla_factor', 'growth_factor', 'production_factor')
BOUNDS = ([.5, .7, .65], [1.5, 1.3, 1.35])
FIELDS = ('P', 'DO2', 'S')
SCALES = {'P': 1., 'DO2': 2., 'S': 5.}


def simulate(paths, plan, fit=None, *, hours=96., rtol=1e-7, solver='native'):
    module = pen_module(Path(paths['pensim']), Path(paths['native']))
    env = module.PenSimEnv(pen_recipe(), fast=True)
    env.random_seed_ref = 0
    env.ctrl_flags.Raman_spec = 0
    env.ctrl_flags.Dis = 0
    _, state = env.reset()
    fit = fit or {}
    for key, index in [('kla_factor', 2), ('growth_factor', 1), ('production_factor', 0)]:
        factor = fit.get(key, 1.)
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError('Positive finite physical parameter factor required')
        env.param_list[index] *= factor
    trace = []
    feed = gas = 0.
    with monitor_pen(module, rtol=rtol, solver=solver) as (audit, samples):
        for step in range(1, int(round(hours/.2))+1):
            time = step*.2
            u = env.recipe_combo.get_values_dict_at(time)
            if time > plan['apply_after_h']:
                u['Fs'] *= plan['feed_factor']
                u['Fg'] *= plan['air_factor']
                feed += u['Fs']*.2
                gas += u['Fg']*.2
            _, state, _, _ = env.step(step, state, **u)
            trace.append({'time_h': time, 'state': {
                k: float(getattr(state, k).y[step-1])
                for k in ('P', 'S', 'DO2', 'V', 'T', 'Viscosity')}, 'commands': u})
    return {'trace': trace, 'terminal': trace[-1]['state'],
        'objective': trace[-1]['state']['P'], 'audit': deepcopy(audit),
        'resources': {'feed_factor': plan['feed_factor'], 'air_factor': plan['air_factor'],
            'integrated_feed_command_times_h': feed, 'integrated_air_command_times_h': gas}}


def source_residual(result, rows):
    times = [r['time_h'] for r in rows]
    model_times = [r['time_h'] for r in result['trace']]
    return np.concatenate([
        (np.interp(times, model_times, [r['state'][field] for r in result['trace']])
            - np.array([r['state'][field] for r in rows]))/SCALES[field]
        for field in FIELDS])


def fit_source(source_history, paths, *, source_plan=None):
    """Three fixed effective kinetic factors; all three trajectories enter loss."""
    plan = source_plan or {'feed_factor': 1., 'air_factor': 1., 'apply_after_h': 60.}
    rows = [r for r in source_history if r['time_h'] >= 20.]
    if len(rows) < 6 or any(not all(k in r['state'] for k in FIELDS) for r in rows):
        raise ValueError('Completed-source P, DO2 and S trajectories required')
    evaluations = []
    def residual(logpars):
        factors = dict(zip(PARAMETERS, map(float, np.exp(logpars))))
        result = simulate(paths, plan, factors)
        errors = source_residual(result, rows)
        evaluations.append(float(np.linalg.norm(errors)))
        return errors
    solved = least_squares(residual, np.zeros(3),
        bounds=(np.log(BOUNDS[0]), np.log(BOUNDS[1])), diff_step=1e-3,
        max_nfev=60, loss='soft_l1', f_scale=1.)
    factors = dict(zip(PARAMETERS, map(float, np.exp(solved.x))))
    replay = simulate(paths, plan, factors)
    errors = source_residual(replay, rows).reshape(len(FIELDS), len(rows))
    return {**factors, 'method': METHOD, 'bounds': dict(zip(PARAMETERS, zip(*BOUNDS))),
        'fit_fields': list(FIELDS), 'residual_scales': SCALES,
        'fit_source_times_h': [r['time_h'] for r in rows],
        'source_history_sha256': evidence_hash(source_history),
        'evidence_scope': 'completed_source_before_receiving',
        'source_operating_plan': plan, 'optimizer_success': bool(solved.success),
        'optimizer_message': solved.message, 'cost': float(solved.cost),
        'evaluations': len(evaluations), 'source_MAE': {
            field: float(np.mean(np.abs(errors[i]))*SCALES[field]) for i, field in enumerate(FIELDS)},
        'limitations': 'Effective constant kinetics; hidden morphology and future disturbances remain unknown. Source fit is not future validation.'}
