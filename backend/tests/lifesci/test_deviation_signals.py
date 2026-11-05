"""Deviation signals: detected automatically, declared by people. Specs are approved and versioned."""
from __future__ import annotations

import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.identity import AuthorizationError
from src.lifesci.signals import SignalService, register_signal_listeners, signal_routes
from src.lifesci.specifications import SpecificationService, parameter_key
from src.lifesci.store import Event, RecordStore


@pytest.fixture
def p():
    platform = Platform(RecordStore(), providers={})
    for actor, role in (('qa1', 'qa'), ('op', 'operator'), ('far', 'qa')):
        platform.identity.assign_role('T', actor, role, site_id='NF2' if actor == 'far' else 'NF1')
    platform.identity.assign_role('T', 'bot', 'agent', site_id='NF1', actor_kind='agent')
    platform.specifications = SpecificationService(platform.store, platform.identity)
    platform.signals = SignalService(platform)
    register_signal_listeners(platform)
    return platform


def ctx(p, who, kind='person'):
    return p.identity.context_for('T', who, actor_kind=kind)


def do_spec(p, **extra):
    return p.specifications.create(ctx(p, 'qa1'), site_id='NF1', parameter='DO [%]', unit='%', low=30, high=80,
                                   critical_low=15, reason='Batch record BR-07 v3', **extra)


def signals(p):
    return p.signals.list(ctx(p, 'qa1'))


def historian(p, value, seq, equipment='BR-07', batch='B-117'):
    content = json.dumps({'tag': 'DO', 'value': value, 'seq': seq}).encode()
    return p.evidence.ingest(ctx(p, 'op'), source_system='HISTORIAN', source_record_id=f'DO-{seq}', content=content,
                             media_type='application/json', site_id='NF1', event_time=None,
                             metadata={'mapped': {'tag': 'DO', 'value': value, 'equipment_id': equipment, 'batch_id': batch},
                                       'units': {'value': '%'}})


def test_parameter_key_ignores_units_and_case_not_meaning():
    assert parameter_key('DO [%]') == parameter_key('do') == 'do'
    assert parameter_key('Dissolved oxygen') != 'do'


def test_specs_are_approved_by_people_with_a_reason_and_versioned(p):
    with pytest.raises(AuthorizationError):
        p.specifications.create(ctx(p, 'bot', 'agent'), site_id='NF1', parameter='DO', low=30, reason='x')
    with pytest.raises(PermissionError):  # operators may not approve specifications
        p.specifications.create(ctx(p, 'op'), site_id='NF1', parameter='DO', low=30, reason='x')
    with pytest.raises(ValueError):
        p.specifications.create(ctx(p, 'qa1'), site_id='NF1', parameter='DO', low=30, reason=' ')
    with pytest.raises(ValueError):
        p.specifications.create(ctx(p, 'qa1'), site_id='NF1', parameter='DO', low=50, high=40, reason='x')
    first = do_spec(p)
    second = do_spec(p)
    assert first['spec_id'] == second['spec_id'] and second['version'] == 2 and len(second['history']) == 1


def test_value_below_spec_raises_action_and_below_critical_escalates_one_signal(p):
    do_spec(p)
    historian(p, 24, 1)
    [s] = signals(p)
    assert (s['kind'], s['severity'], s['status']) == ('spec_excursion', 'action', 'open')
    assert s['spec_ref']['version'] == 1 and '< low 30' in s['rule'] and s['subject'] == {'kind': 'batch', 'id': 'B-117'}
    historian(p, 12, 2)
    [s] = signals(p)  # coalesced: same parameter, subject and rule
    assert s['severity'] == 'critical' and s['occurrences'] == 2 and len(s['evidence_refs']) == 2
    types = [e.type for _, e in p.store.events_since('T', 0) if e.type.startswith('signal.')]
    assert types == ['signal.raised', 'signal.escalated']


def test_in_spec_values_raise_nothing_and_no_spec_means_no_evaluation(p):
    historian(p, 5, 1)  # no specification: plausibility is not a GMP limit
    assert signals(p) == []
    do_spec(p)
    historian(p, 55, 2)
    assert signals(p) == []


def test_drift_toward_the_limit_raises_a_warning_not_an_excursion(p):
    do_spec(p, trend_rules=True)
    for i, v in enumerate([60, 61, 59, 60, 61, 60, 59, 60, 61, 60, 52, 47, 43, 39, 36], 1):
        historian(p, v, i)
    found = signals(p)
    assert found and all(s['kind'] == 'trend' and s['severity'] == 'warning' for s in found)
    assert 'still within spec' in found[0]['rule']


def test_qms_deviation_record_is_a_critical_signal_and_other_qms_records_are_not(p):
    def qms(rid, record_type):
        return p.evidence.ingest(ctx(p, 'op'), source_system='QMS', source_record_id=rid, content=rid.encode(),
                                 media_type='text/plain', site_id='NF1', event_time=None,
                                 metadata={'mapped': {'case_id': rid, 'record_type': record_type, 'batch_id': 'B-117',
                                                      'description': 'Foaming at 4 h'}})
    qms('QMS-1', 'CAPA')
    assert signals(p) == []
    qms('QMS-2', 'Deviation')
    [s] = signals(p)
    assert (s['kind'], s['severity']) == ('qms_deviation', 'critical')
    assert s['source'] == {'system': 'QMS', 'record_id': 'QMS-2'} and 'Foaming' in s['rule']
    # (With the wired platform, triage then stores its own request as evidence; pick the QMS record's event.)
    event = [e for _, e in p.store.events_since('T', 0) if e.type == 'evidence.ingested' and e.aggregate_id == 'QMS:QMS-2'][-1]
    assert event.payload['source_system'] == 'QMS' and event.payload['record_type'] == 'Deviation'


def test_step_exception_and_lab_oos_events_become_signals(p):
    def emit(type_, **payload):
        p.signals.on_event(Event('e-' + type_, 'T', type_, 'x', 'x', 1, payload, '2026-11-05T00:00:00+00:00'))
    emit('exec.exception', instance_id='PI-1', step_id='s3', exception_id='PI-1:s3:1:exc', parameter='pH', value=6.1,
         low=6.8, high=7.4, site_id='NF1', batch_id='B-117')
    emit('lab.result_recorded', result_id='RES:S1:titer', sample_id='S1', site_id='NF1', batch_id='B-117', analyte='titer',
         value=2.1, unit='g/L', low=3.0, high=None, limit_evaluation='out_of_limits')
    emit('lab.result_recorded', result_id='RES:S2:titer', sample_id='S2', site_id='NF1', batch_id='B-118', analyte='titer',
         value=3.5, unit='g/L', low=3.0, high=None, limit_evaluation='within_limits')
    kinds = {(s['kind'], s['severity'], s['subject']['id']) for s in signals(p)}
    assert kinds == {('step_exception', 'critical', 'B-117'), ('lab_oos', 'action', 'B-117')}


def test_detection_failure_never_breaks_the_writer(p, monkeypatch):
    do_spec(p)
    monkeypatch.setattr(p.signals, 'check_value', lambda *a, **k: 1 / 0)
    assert historian(p, 10, 1)['evidence_id'] == 'HISTORIAN:DO-1'  # ingest still succeeds


def test_only_people_change_the_lifecycle_and_dismissal_needs_a_reason(p):
    do_spec(p)
    historian(p, 24, 1)
    [s] = signals(p)
    with pytest.raises(AuthorizationError):
        p.signals.acknowledge(ctx(p, 'bot', 'agent'), s['signal_id'])
    with pytest.raises(ValueError):
        p.signals.dismiss(ctx(p, 'qa1'), s['signal_id'], ' ')
    assert p.signals.acknowledge(ctx(p, 'qa1'), s['signal_id'])['status'] == 'acknowledged'
    done = p.signals.dismiss(ctx(p, 'qa1'), s['signal_id'], 'Probe recalibrated; reading was a sensor fault')
    assert done['status'] == 'dismissed' and done['history'][-1]['by'] == 'qa1'
    historian(p, 24, 2)  # a dismissed signal does not swallow new data: a new one opens
    assert len([x for x in signals(p) if x['status'] == 'open']) == 1


def test_open_case_is_a_persons_decision_and_links_both_ways(p):
    do_spec(p)
    historian(p, 24, 1)
    [s] = signals(p)
    with pytest.raises(AuthorizationError):
        p.signals.open_case(ctx(p, 'bot', 'agent'), s['signal_id'], owner_id='qa1', qa_reviewer_id='qa1')
    out = p.signals.open_case(ctx(p, 'qa1'), s['signal_id'], owner_id='qa1', qa_reviewer_id='qa1', case_id='DEV-31')
    assert out['signal']['status'] == 'case_opened' and out['signal']['case_id'] == 'DEV-31'
    case = p.cases.get(ctx(p, 'qa1'), 'DEV-31')
    assert s['signal_id'] in case['timeline'][0]['description']
    with pytest.raises(ValueError):
        p.signals.open_case(ctx(p, 'qa1'), s['signal_id'], owner_id='qa1', qa_reviewer_id='qa1')


def test_signals_are_site_scoped(p):
    do_spec(p)
    historian(p, 24, 1)
    assert p.signals.list(ctx(p, 'far')) == []
    [s] = signals(p)
    with pytest.raises(PermissionError):
        p.signals.get(ctx(p, 'far'), s['signal_id'])


def test_cmo_delivery_values_are_checked_against_specs(p):
    do_spec(p)
    hits = p.signals.check_delivery_measurements('T', site_id='NF1', delivery_ref={'kind': 'cmo_dataset', 'id': 'D1'},
                                                 measurements=[{'parameter': 'DO [%]', 'value': 20, 'batch_id': 'B-9'},
                                                               {'parameter': 'DO [%]', 'value': 50, 'batch_id': 'B-10'}])
    assert [h['kind'] for h in hits] == ['delivery_excursion'] and hits[0]['subject']['id'] == 'B-9'


def test_routes(p):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.lifesci.identity import AuthorizationError as AE
    app = FastAPI()

    @app.exception_handler(PermissionError)
    async def _perm(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc)}, status_code=403)

    @app.exception_handler(ValueError)
    async def _bad(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc)}, status_code=400)

    signal_routes(app, p, lambda: ctx(p, 'qa1'))
    client = TestClient(app)
    spec = client.post('/v1/specifications', json={'site_id': 'NF1', 'parameter': 'DO', 'low': 30, 'reason': 'BR v3'})
    assert spec.status_code == 201
    historian(p, 24, 1)
    listed = client.get('/v1/signals', params={'min_severity': 'action'}).json()['signals']
    assert len(listed) == 1
    sid = listed[0]['signal_id']
    assert client.post(f'/v1/signals/{sid}/dismiss', json={'reason': ''}).status_code == 422
    assert client.post(f'/v1/signals/{sid}/acknowledge').json()['status'] == 'acknowledged'
    opened = client.post(f'/v1/signals/{sid}/open-case', json={'owner_id': 'qa1', 'qa_reviewer_id': 'qa1'})
    assert opened.status_code == 201 and opened.json()['case']['case_id'].startswith('DEV-')
    assert AE  # imported for parity with the app's handler set
