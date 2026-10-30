"""Experiment models and demo data in the engineering assistant (FakeProvider: orchestration only)."""
import hashlib
import json

import numpy as np
import pytest

from src.lifesci.bioprocess import cho
from src.lifesci.bioprocess.service import DEMO, demo_index, packet
from src.lifesci.bioprocess.simulators import SimulatorWorker
from src.lifesci.cmo_datasets import CLASSIFICATION, SOURCE_SYSTEM
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.store import RecordStore
from tests.lifesci.test_engineering_conversation import fake_planner, node, send

PENSIM_CASE = 'NC-03ce17b48c95'  # PenSim operating decision, challenge stratum


class FakeWorker:
    """Shaped like the experiment's forward-model output; numbers are placeholders."""
    def __init__(self):
        self.calls = []

    def status(self):
        return {'available': True, 'missing': [], 'note': None}

    def forward(self, p, action):
        self.calls.append(action)
        if action == 'rich':
            raise RuntimeError('simulator failed for action rich: test failure')
        return {'predictions': {f: 1.0 for f in p['forecast_fields']},
                'operating_consequences': {'feasible': action != 'keep', 'violations': ['aeration_delivery_limit'] if action == 'keep' else [],
                                           'objective': 5.0},
                'calibration': {'applied': True, 'physical_fit': {'kla_factor': 1.1, 'growth_factor': 1.0, 'production_factor': .9, 'method': 'test'}}}


@pytest.fixture
def env():
    p = Platform(RecordStore(), providers={})
    seed(p)
    p.bioprocess.worker = FakeWorker()
    return p, p.identity.context_for(TENANT, 'priya')


def test_demo_cases_are_the_public_experiment_packets_only():
    index = demo_index()
    assert len(index['cases']) == 12
    for case in index['cases']:
        raw = (DEMO / f"{case['case_id']}.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == case['packet_sha256']
        assert not {'truth', 'targets', 'evaluator'} & set(json.loads(raw))


def test_assistant_loads_a_demo_case_and_runs_experiment_model_with_lineage(env, monkeypatch):
    p, ctx = env
    seen = []
    original = p.gateway.run
    monkeypatch.setattr(p.gateway, 'run', lambda req: seen.append(json.loads(req.prompt)) or original(req))
    fake_planner(p, [
        {'reply': 'I will load the case and compare the current plan with two alternatives.', 'workflow': [
            node('case', 'bioprocess_demo_case', {'case_id': PENSIM_CASE}),
            node('forecast', 'bioprocess_forecast', {'case_id': PENSIM_CASE, 'actions': ['keep', 'lean_low_gas', 'rich', 'abstain'],
                                                     'rationale': 'Air is limited to 1.0x, so compare low-gas plans with the current one'}, ['case'])]},
        {'reply': 'The low-gas plan stays within the limits in this simulated case.'}])
    thread = p.engineering_conversations.create(ctx, {})
    result = send(p, ctx, thread, 'Which plan should we run after 60 h?', enable_demo=True)
    turn = result['turns'][0]
    assert turn['status'] == 'completed', turn['issues']
    assert [a['kind'] for a in turn['artifacts']] == ['bioprocess_case', 'bioprocess_forecast']
    assert any('rich' in i for i in turn['steps'][1]['issues'])  # partial failures are reported, not hidden
    catalog = seen[0]['bioprocess_models_and_demo_cases']
    assert {m['id'] for m in catalog['models']} == {'pensim.calibrated_fed_batch', 'smpl.mab_upstream', 'cho.monod_batch'}
    forecast = p.engineering_conversations.artifact(ctx, thread['id'], 'bioprocess_forecast', turn['artifacts'][1]['id'])
    assert [r['action'] for r in forecast['rows']] == ['keep', 'lean_low_gas', 'rich']  # abstain never runs
    assert forecast['rows'][0]['violations'] == ['aeration_delivery_limit'] and forecast['rows'][2]['status'] == 'failed'
    assert forecast['inputs'][0]['id'] == f'simulated-bioprocess-case:{PENSIM_CASE}'
    evidence = p.store.read().require(TENANT, 'evidence', forecast['inputs'][0]['id'])
    assert evidence.state['metadata']['classification'] == 'simulated_demo_case_not_measurement'
    # The follow-up sees the loaded case and a bounded summary of the earlier forecast.
    result = send(p, ctx, p.engineering_conversations.get(ctx, thread['id']), 'Why is keep infeasible?')
    assert any(s.get('kind') == 'simulated_bioprocess_case' for s in seen[1]['authorized_sources'])
    computed = seen[1]['conversation'][0]['computed_artifacts'][0]
    assert computed['model'] == 'pensim.calibrated_fed_batch' and 'observed' not in computed


def test_demo_cases_need_the_users_consent(env):
    p, ctx = env
    fake_planner(p, [{'reply': 'Running the case.', 'workflow': [
        node('forecast', 'bioprocess_forecast', {'case_id': PENSIM_CASE, 'actions': ['keep'], 'rationale': 'Forecast current plan'})]}])
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Forecast the PenSim case')
    turn = result['turns'][0]
    assert turn['status'] == 'blocked' and not turn['artifacts'] and not p.bioprocess.worker.calls


def _verified_dataset(p, ctx):
    params = [.03, .002, .4, 2.5, .004]
    rows = []
    for b, (x0, g0) in enumerate([(.4, 6.), (.5, 5.5), (.45, 6.2), (.42, 5.8)]):
        times = [0, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120]
        for t, (x, g) in zip(times, cho.integrate(params, np.array([x0, g0]), 0, times)):
            for field, value, unit in (('viable_cell_density', x * 1e6, 'cells/mL'), ('glucose', g, 'g/L')):
                rows.append({'id': f'{b}-{t}-{field}', 'source_id': 's', 'batch': f'CHO-00{b}-R01', 'time': f'{t:.2f}', 'parameter': field,
                             'value': float(value), 'unit': unit, 'value_raw': str(value), 'unit_raw': unit, 'status': 'auto_accepted',
                             'source': {'path': 'LIMS.csv', 'row': len(rows) + 2}, 'source_sha256': 'x'})
    content = json.dumps({'schema_version': 'platform-verified-cmo-1', 'run_id': 'abc12345', 'cmo': 'Northfield', 'delivery_name': 'October',
                          'guarantee': {'holds': True, 'checks': []}, 'measurements': rows}).encode()
    ev = p.evidence.ingest(ctx, source_system=SOURCE_SYSTEM, source_record_id='abc12345', content=content, media_type='application/json',
                           site_id='NF1', event_time=None, metadata={'classification': CLASSIFICATION, 'cmo': 'Northfield'})
    return ev['evidence_id']


def test_cho_model_is_fitted_to_an_attached_verified_delivery(env):
    p, ctx = env
    dataset = _verified_dataset(p, ctx)
    fake_planner(p, [{'reply': 'Fitting the CHO model to the other batches.', 'workflow': [
        node('fit', 'cho_dataset_forecast', {'dataset_id': dataset, 'batch': 'CHO-001-R01', 'cutoff_h': 60,
                                             'rationale': 'Forecast growth and glucose from the first 60 h'})]}])
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Forecast batch 1', dataset_ids=[dataset])
    turn = result['turns'][0]
    assert turn['status'] == 'completed', turn['issues']
    record = p.engineering_conversations.artifact(ctx, result['id'], 'bioprocess_cho_forecast', turn['artifacts'][0]['id'])
    assert record['fit']['training_batches'] == ['CHO-000-R01', 'CHO-002-R01', 'CHO-003-R01']
    assert all(c['time_h'] > 60 for c in record['holdout_comparison'])
    # Synthetic data generated by the same equations should be reproduced closely.
    assert record['holdout_errors']['glucose']['mean_absolute_error'] < .2
    assert record['inputs'][0]['id'] == dataset


def test_cho_model_refuses_datasets_not_attached(env):
    p, ctx = env
    dataset = _verified_dataset(p, ctx)
    fake_planner(p, [{'reply': 'Fitting.', 'workflow': [
        node('fit', 'cho_dataset_forecast', {'dataset_id': dataset, 'batch': 'CHO-001-R01', 'rationale': 'Forecast growth'})]}])
    result = send(p, ctx, p.engineering_conversations.create(ctx, {}), 'Forecast batch 1')
    assert result['turns'][0]['status'] == 'blocked' and not result['turns'][0]['artifacts']


@pytest.mark.skipif(not SimulatorWorker.from_env().status()['available'], reason='simulator environment not installed')
def test_real_experiment_model_runs_in_its_worker():
    out = SimulatorWorker.from_env().forward(packet(PENSIM_CASE), 'lean_low_gas')
    assert set(out['predictions']) == set(packet(PENSIM_CASE)['forecast_fields'])
    assert out['operating_consequences']['feasible'] in (True, False)
