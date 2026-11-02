import json
from pathlib import Path
import numpy as np
import pytest
from benchmarks.interventions.followup import table, expand, unpack, TablePredictor, POLICY
from benchmarks.interventions.followup_diagnosis import stopping_failures
from benchmarks.interventions.pensim import simulate, outcomes

REPO = Path(__file__).resolve().parents[2]
OLD = REPO / 'backend/results/interventions/frozen-ab-20261029'


def test_table_preserves_real_source_and_receiving_evidence_exactly():
    source = json.loads((OLD / 'source-qualification.json').read_text())['source_measurements']
    assert expand(table(source)) == source
    assert len(json.dumps(table(source))) < len(json.dumps(source)) * .5
    assert expand(table([])) == []


def test_model_gets_same_rows_and_cannot_receive_future_measurements_through_table():
    from benchmarks.interventions.model import ReceivingModel
    predictor = TablePredictor(ReceivingModel({}, {'factors': {}}))
    packet = {'decision_time_h': 52., 'source_observations': table([]),
              'receiving_observations': table([{'time_h': 48., 'available_at_h': 53., 'field': 'P', 'value': 1.}])}
    with pytest.raises(ValueError, match='Future observation'):
        predictor(packet, 'keep')


def test_real_recorded_policy_failure_is_detected():
    data = json.loads((OLD / 'results.json').read_text())
    failures = stopping_failures(data)
    assert len(failures) == 26
    assert all(f['central_prediction_infeasible'] for f in failures)


def test_zero_drift_reproduces_frozen_hidden_outcome():
    protocol = json.loads((OLD / 'protocol.json').read_text())
    restored = Path('/private/tmp/sievance-pensim-20261101')
    if not (Path(protocol['paths']['pensim']) / 'pensimpy/peni_env_setup.py').exists() and restored.exists():
        from benchmarks.external_simulators.experiment import sha
        for relative in ['pensimpy/ode/indpensim_ode_py.py', 'pensimpy/peni_env_setup.py']:
            assert sha(restored / relative) == protocol['code_sha256'][str(Path(protocol['paths']['pensim']) / relative)]
        protocol['paths']['pensim'] = str(restored)
    if not Path(protocol['paths']['pensim']).exists():
        pytest.skip('Pinned native simulator not installed')
    item = json.loads((OLD / 'private-catalogue.json').read_text())[2]
    records = json.loads((OLD / 'results.json').read_text())['cases']
    case = next(c for c in records if c['case_id'] == item['case_id'])
    record = next(r for r in case['records'] if r.get('evaluation'))
    action = record['evaluation']['proposal']['action_id']
    current = outcomes(simulate(protocol['paths'], **item['hidden'], action=action, transfer_drift_per_h=0.))
    original = record['evaluation']['outcome']
    assert np.isclose(current['product_mass_kg'], original['product_mass_kg'], rtol=1e-8)
    assert current['post_decision_feasible'] == original['post_decision_feasible']


def test_invalid_drift_rejected_before_simulator_load():
    with pytest.raises(ValueError, match='Transfer drift'):
        simulate({}, seed=1, factors={'kla_factor': 1., 'growth_factor': 1., 'production_factor': 1.},
                 transfer_drift_per_h=-.1)


def test_admission_usage_records_server_reported_model_without_content():
    from scripts.run_bounded_agent_benchmark import response_usage
    wire = b'data: {"model":"zai-org/GLM-5.3","choices":[{"text":"private"}]}\n\ndata: {"usage":{"prompt_tokens":100,"completion_tokens":20}}\n\ndata: [DONE]\n'
    value = response_usage(wire)
    assert value['response_models'] == ['zai-org/GLM-5.3']
    assert value['conservative_cost_usd'] == pytest.approx(.000228)
    assert 'private' not in json.dumps(value)
