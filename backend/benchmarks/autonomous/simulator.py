"""Optional PenSimPy numerical feasibility gate; never controls physical equipment.

The simulator dependency belongs in an isolated environment. Its hidden batch state
and terminal objective are evaluator-only, never part of policy observations.
"""
from __future__ import annotations

import argparse
import json
import math
import numbers
import subprocess
import sys
import time
from pathlib import Path


OBSERVABLES = ('Foil', 'Fw', 'Fs', 'Fa', 'Fb', 'Fc', 'Fh', 'Fg', 'Wt',
               'discharge', 'DO2', 'T', 'O2', 'pressure', 'pH')
CONTROLS = ('Fs', 'Foil', 'Fg', 'pressure', 'discharge', 'Fw', 'Fpaa')
STEP_HOURS = 0.2
NUM_STEPS = 1150
MAX_RELATIVE_CHANGE = 0.01  # Conservative envelope from upstream RL example.


class InvalidTrajectory(RuntimeError):
    """Fail the feasibility gate rather than converting invalid states into results."""


def validate_action(baseline: dict, proposed: dict) -> dict:
    """Accept partial absolute commands within 1% of the known recipe at this step.

    Zero baseline commands remain zero. This envelope is a simulator demonstration
    constraint, not an experimentally established manufacturing safety limit.
    """
    if set(proposed) - set(CONTROLS):
        raise ValueError('Unknown control variable')
    result = dict(baseline)
    for name, value in proposed.items():
        if isinstance(value, bool) or not isinstance(value, numbers.Real) or not math.isfinite(value):
            raise ValueError(f'Nonfinite or nonnumeric control: {name}')
        nominal = float(baseline[name])
        if value < 0 or abs(value - nominal) > abs(nominal) * MAX_RELATIVE_CHANGE + 1e-12:
            raise ValueError(f'Control exceeds recipe-relative bounds: {name}')
        result[name] = float(value)
    return result


def _make_environment(seed: int, fast: bool):
    from pensimpy.examples.recipe import Recipe, RecipeCombo
    from pensimpy.peni_env_setup import PenSimEnv
    from pensimpy.data import constants as c
    profiles = (c.FS_DEFAULT_PROFILE, c.FOIL_DEFAULT_PROFILE, c.FG_DEFAULT_PROFILE,
                c.PRESS_DEFAULT_PROFILE, c.DISCHARGE_DEFAULT_PROFILE,
                c.WATER_DEFAULT_PROFILE, c.PAA_DEFAULT_PROFILE)
    recipe = RecipeCombo({name: Recipe(profile, name) for name, profile in zip(CONTROLS, profiles)})
    env = PenSimEnv(recipe, fast=fast)
    env.random_seed_ref = seed
    env.yield_pre = 0
    return env


class SimulatorSession:
    """Sequential local simulator boundary. Never expose this object to a model.

    Bind only observe()/advance() outputs to agent tools; the Python object itself
    is not a security sandbox. PenSimPy has process-global native parameters, so
    episodes must run serially or in separate processes, never concurrent threads.
    """

    def __init__(self, seed: int = 1, *, fast: bool = True):
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError('Seed must be a nonnegative integer')
        self.__env = _make_environment(seed, fast)
        observation, self.__state = self.__env.reset()
        self.__observation = self._public(observation)
        self.__step = 0
        self.__failed = False

    @staticmethod
    def _public(observation):
        raw = dict(observation)
        return {key: float(raw[key]) for key in OBSERVABLES}

    def observe(self):
        return {'time_h': self.__step * STEP_HOURS,
                'measurements': dict(self.__observation),
                'done': self.__step == NUM_STEPS,
                'failed': self.__failed}

    def next_recipe(self):
        if self.__failed or self.__step >= NUM_STEPS:
            raise InvalidTrajectory('Episode is closed')
        return dict(self.__env.recipe_combo.get_values_dict_at((self.__step + 1) * STEP_HOURS))

    def advance(self, proposed: dict | None = None, *, step: int | None = None):
        if step is not None and step != self.__step + 1:
            raise ValueError('Control must target the next 12-minute interval')
        commands = validate_action(self.next_recipe(), proposed or {})
        self.__step += 1
        try:
            observation, self.__state, _reward, _done = self.__env.step(
                self.__step, self.__state, **commands)
            public = self._public(observation)
            # Source nan_to_num masks V/P failures; independently check positive V.
            volume = float(self.__state.V.y[self.__step - 1])
            product = float(self.__state.P.y[self.__step - 1])
            if not all(math.isfinite(v) for v in public.values()) or not math.isfinite(volume) or volume <= 0 or not math.isfinite(product) or product < 0:
                raise InvalidTrajectory(f'Invalid numerical state at {self.__step * STEP_HOURS:g} h')
            self.__observation = public
        except Exception:
            self.__failed = True
            raise
        return self.observe()

    def evaluator_outcome(self):
        """Evaluator-only terminal concentration; not supplied to policy callbacks."""
        if self.__failed or self.__step != NUM_STEPS:
            return {'terminal_concentration_g_L': None, 'status': 'not_evaluated'}
        return {'terminal_concentration_g_L': float(self.__state.P.y[-1]), 'status': 'measured'}


def run_episode(seed: int, *, fast: bool = True, change_step: int | None = None):
    started = time.perf_counter()
    trace = []
    result = {'seed': seed, 'solver': 'fastodeint' if fast else 'scipy_odeint',
              'policy': 'fixed_one_step_Fs_plus_1_percent' if change_step else 'published_recipe',
              'change_step': change_step, 'action_count': 0,
              'constraint_violations': 0, 'model_calls': 0, 'inference_cost_usd': 0,
              'objective': 'terminal penicillin concentration', 'objective_unit': 'g/L'}
    try:
        session = SimulatorSession(seed, fast=fast)
        for step in range(1, NUM_STEPS + 1):
            action = {}
            if step == change_step:
                action = {'Fs': session.next_recipe()['Fs'] * 1.01}
                result['action_count'] += 1
            observation = session.advance(action, step=step)
            trace.append({'observation': observation, 'intervention': action})
        result.update(session.evaluator_outcome())
    except Exception as exc:
        result.update(status='failed', terminal_concentration_g_L=None,
                      error=f'{type(exc).__name__}: {exc}', failed_step=len(trace) + 1)
    result.update(wall_seconds=time.perf_counter() - started, completed_steps=len(trace), trace=trace)
    return result


def _bounded_episode(seed, fast, change_step, path, timeout_seconds):
    started = time.perf_counter()
    command = [sys.executable, '-m', 'benchmarks.autonomous.simulator',
               '--output', str(path), '--episode-seed', str(seed),
               '--solver', 'fast' if fast else 'scipy']
    if change_step:
        command.extend(['--change-step', str(change_step)])
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
        if completed.returncode:
            raise RuntimeError(completed.stderr[-2000:])
        return json.loads(path.read_text())
    except Exception as exc:
        episode = {'seed': seed, 'solver': 'fastodeint' if fast else 'scipy_odeint',
                   'status': 'failed', 'trace': [], 'terminal_concentration_g_L': None,
                   'error': f'{type(exc).__name__}: {exc}',
                   'wall_seconds': time.perf_counter() - started,
                   'timeout_seconds': timeout_seconds, 'completed_steps': None}
        path.write_text(json.dumps(episode, indent=2))
        return episode


def run_gate(output: Path, seeds=(1, 2), timeout_seconds=20):
    """Matched seeds/recipes/disturbances; fixed intervention is not an agent policy."""
    output.mkdir(parents=True, exist_ok=True)
    summary = {'optimization_status': 'not_evaluated', 'episodes': []}
    for fast in (True, False):
        for seed in seeds:
            prefix = f'{"fast" if fast else "scipy"}-seed-{seed}'
            baseline = _bounded_episode(seed, fast, None, output / f'{prefix}-baseline.json', timeout_seconds)
            repeat = _bounded_episode(seed, fast, None, output / f'{prefix}-repeat.json', timeout_seconds)
            changed = _bounded_episode(seed, fast, 100, output / f'{prefix}-changed.json', timeout_seconds)
            comparable = min(len(baseline['trace']), len(changed['trace']))
            # A changed actuator readback alone does not establish process response.
            response = any(any(baseline['trace'][i]['observation']['measurements'][key] != changed['trace'][i]['observation']['measurements'][key]
                               for key in ('Wt', 'DO2', 'T', 'O2', 'pH'))
                           for i in range(99, comparable))
            entry = {'seed': seed, 'solver': baseline['solver'],
                     'repeat_trace_identical': bool(baseline['trace']) and baseline['trace'] == repeat['trace'],
                     'observed_response_to_control_change': response,
                     'full_baseline_valid': baseline['status'] == 'measured',
                     'full_changed_episode_valid': changed['status'] == 'measured'}
            for name, episode in [('baseline', baseline), ('repeat', repeat), ('changed', changed)]:
                path = output / f'{prefix}-{name}.json'
                path.write_text(json.dumps(episode, indent=2, allow_nan=False))
                entry[name] = {k: v for k, v in episode.items() if k != 'trace'}
                entry[name]['artifact'] = str(path.resolve())
            summary['episodes'].append(entry)
    summary['gate_passed'] = all(e['full_baseline_valid'] and e['full_changed_episode_valid'] and e['repeat_trace_identical'] and e['observed_response_to_control_change'] for e in summary['episodes'])
    if not summary['gate_passed']:
        summary['blocker'] = 'Unmodified simulator did not produce valid reproducible full baseline trajectories; optimization withheld.'
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--episode-seed', type=int)
    parser.add_argument('--solver', choices=('fast', 'scipy'), default='fast')
    parser.add_argument('--change-step', type=int)
    parser.add_argument('--timeout-seconds', type=float, default=20)
    args = parser.parse_args()
    if args.episode_seed is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(run_episode(args.episode_seed, fast=args.solver == 'fast', change_step=args.change_step), indent=2, allow_nan=False))
    else:
        print(json.dumps(run_gate(args.output, timeout_seconds=args.timeout_seconds), indent=2))
