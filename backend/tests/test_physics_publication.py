"""Publication integrity using explicitly scripted, temporary test receipts."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from benchmarks.physics_value.generate import digest, dump, generate
from benchmarks.physics_value.run_agents import HostTools, aggregate
from frontend.scripts.export_physics_value import export


@pytest.fixture(scope='module')
def dataset(tmp_path_factory):
    path = tmp_path_factory.mktemp('physics-publication-fixture') / 'dataset'
    generate(path, seed=111, replicates=1, plots=False)
    return path


def fixture_run(dataset, directory):
    case = next(c for c in json.loads((dataset / 'evaluator/catalogue.json').read_text())
                if c['domain'] == 'oxygen' and c['family'] == 'nominal')
    protocol = {'tasks': ['diagnosis', 'optimization', 'resolution', 'pretransfer'],
                'model': 'scripted-unit-fixture/no-inference',
                'planned_attempts': 2, 'case_ids': [case['case_id']],
                'dataset_manifest_sha256': digest(dataset / 'manifest.json'), 'runner_sha256': {}}
    rows = []
    for arm in ('A', 'B'):
        host = HostTools(dataset, case['case_id'], 'optimization', arm, directory / arm, 10)
        submission = {'hypotheses': ['nominal'], 'action_id': 'keep',
                      'rationale': 'SCRIPTED TEST FIXTURE ONLY', 'uncertainty': 'Not an agent response', 'evidence': []}
        assert host.call('submit_decision', submission)['accepted']
        rows.append({'case_id': case['case_id'], 'task': 'optimization', 'arm': arm,
                     'status': 'completed', 'submission': submission, 'score': host.score,
                     'common_input_sha256': {'packet.json': 'same-test-input'},
                     'wall_seconds': 1., 'model_calls': 0, 'tool_calls': 1, 'physical_model_calls': 0})
    value = aggregate(rows, protocol, status='complete')
    value['test_fixture_only'] = True
    dump(directory / 'results.json', value)
    dump(directory / 'protocol.json', protocol)
    dump(directory / 'isolation.json', {'passed': True, 'test_fixture_only': True})
    return value


def test_export_retains_exact_source_snapshot_and_does_not_pool_objective_units(dataset, tmp_path):
    run = tmp_path / 'run'
    fixture_run(dataset, run)
    expected = (run / 'results.json').read_bytes()
    destination = tmp_path / 'public'
    result = export(dataset, run, destination)
    payload = json.loads((destination / 'physics-value.json').read_text())
    assert result['source_sha256'] == hashlib.sha256(expected).hexdigest()
    assert payload['attempted'] == 2 and payload['completed'] == 2
    assert payload['tasks']['optimization']['A']['mean_feasible_grid_regret'] is None
    assert payload['domain_tasks']['oxygen']['optimization']['A']['mean_feasible_grid_regret'] is not None
    assert payload['observed_engineer_hours_saved'] is None
    assert payload['findings']['paired_completed_sensitivity']['optimization']['pairs'] == 1
    assert payload['findings']['paired_completed_sensitivity']['optimization']['A']['feasible_actions'] == 1
    assert payload['findings']['paired_completed_sensitivity']['optimization']['B']['feasible_actions'] == 1
    assert not payload['findings']['B_warned_every_case']
    with zipfile.ZipFile(destination / 'physics-value/reproducibility.zip') as archive:
        assert archive.read('agent-run/results.json') == expected
        assert not any(Path(n).name.startswith('.env') or 'auth.json' in n for n in archive.namelist())


def test_publication_refuses_mismatched_inputs_or_failed_isolation(dataset, tmp_path):
    run = tmp_path / 'run'
    value = fixture_run(dataset, run)
    value['pair_inputs_match'] = False
    dump(run / 'results.json', value)
    with pytest.raises(ValueError, match='inputs differ'):
        export(dataset, run, tmp_path / 'public')
    value['pair_inputs_match'] = True
    dump(run / 'results.json', value)
    dump(run / 'isolation.json', {'passed': False})
    with pytest.raises(ValueError, match='isolation'):
        export(dataset, run, tmp_path / 'public')
