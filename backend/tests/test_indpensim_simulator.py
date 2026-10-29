"""Simulator boundary checks run without installing optional native solver code."""
import math
from types import SimpleNamespace

import pytest

from benchmarks.autonomous import simulator


def test_rejects_unsafe_controls_and_zero_recipe_escalation():
    baseline = dict.fromkeys(simulator.CONTROLS, 10.0)
    baseline['discharge'] = 0
    for proposed in ({'Fs': math.nan}, {'Fs': math.inf}, {'Fs': True},
                     {'Fs': '10'}, {'Fs': 10.2}, {'Fs': -1},
                     {'discharge': 0.001}, {'hidden_state': 1}):
        with pytest.raises(ValueError):
            simulator.validate_action(baseline, proposed)
    assert simulator.validate_action(baseline, {'Fs': 10.1})['Fs'] == 10.1


class Environment:
    def __init__(self):
        self.recipe_combo = SimpleNamespace(get_values_dict_at=lambda time: dict.fromkeys(simulator.CONTROLS, 10.0))
        self.state = SimpleNamespace(V=SimpleNamespace(y=[100.0] * 1150),
                                     P=SimpleNamespace(y=[7.0] * 1150),
                                     future_fault='SECRET_FUTURE_FAULT')
        self.invalid = False

    def reset(self):
        return [(key, 1.0) for key in simulator.OBSERVABLES] + [('secret', 42)], self.state

    def step(self, step, state, **commands):
        values = [(key, 1.0) for key in simulator.OBSERVABLES]
        if self.invalid:
            values[0] = (values[0][0], math.nan)
        return values, self.state, 999999, False


def test_policy_receives_only_present_measurements_and_never_hidden_reward(monkeypatch):
    env = Environment()
    monkeypatch.setattr(simulator, '_make_environment', lambda *args: env)
    session = simulator.SimulatorSession(1)
    assert set(session.observe()['measurements']) == set(simulator.OBSERVABLES)
    assert session.evaluator_outcome()['status'] == 'not_evaluated'
    with pytest.raises(ValueError, match='next 12-minute'):
        session.advance(step=2)
    assert session.advance({'Fs': 10.1}, step=1)['time_h'] == 0.2
    assert 'SECRET' not in str(session.observe()) and '999999' not in str(session.observe())
    assert session.evaluator_outcome()['terminal_concentration_g_L'] is None


def test_invalid_state_closes_session_without_numeric_result(monkeypatch):
    env = Environment()
    monkeypatch.setattr(simulator, '_make_environment', lambda *args: env)
    session = simulator.SimulatorSession(1)
    env.invalid = True
    with pytest.raises(simulator.InvalidTrajectory):
        session.advance()
    assert session.observe()['failed'] is True
    with pytest.raises(simulator.InvalidTrajectory, match='closed'):
        session.advance()
    assert session.evaluator_outcome()['terminal_concentration_g_L'] is None


def test_paired_gate_reports_negative_episode_and_never_calls_it_optimization(monkeypatch, tmp_path):
    calls = []
    def episode(seed, fast, change_step, path, timeout_seconds):
        calls.append((seed, fast, change_step))
        return {'status': 'failed', 'trace': [], 'solver': str(fast),
                'seed': seed, 'terminal_concentration_g_L': None}
    monkeypatch.setattr(simulator, '_bounded_episode', episode)
    report = simulator.run_gate(tmp_path, seeds=(8,))
    assert calls == [(8, True, None), (8, True, None), (8, True, 100),
                     (8, False, None), (8, False, None), (8, False, 100)]
    assert report['gate_passed'] is False
    assert report['optimization_status'] == 'not_evaluated'
    assert len(list(tmp_path.glob('*.json'))) == 7


def test_native_solver_timeout_is_explicit_and_does_not_invent_progress(monkeypatch, tmp_path):
    import subprocess
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(simulator.subprocess, 'run', timeout)
    result = simulator._bounded_episode(1, True, None, tmp_path / 'timeout.json', 0.01)
    assert result['status'] == 'failed'
    assert result['completed_steps'] is None
    assert result['terminal_concentration_g_L'] is None
    assert 'TimeoutExpired' in result['error']
