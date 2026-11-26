"""Synthetic, isolated monitoring: source facts are never formal deviations."""
import json

import pytest

from src.lifesci.container import Platform
from src.lifesci.store import RecordStore


@pytest.fixture
def p(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('CMO_DATABASE_URL', '')
    platform = Platform(RecordStore(), providers={})
    platform.identity.assign_role('T', 'qa', 'qa', site_id='S')
    return platform


def spec(p, **kwargs):
    return p.specifications.create(p.identity.context_for('T', 'qa'), site_id='S', parameter='temperature',
                                   unit='degC', high=30, reason='Synthetic approved test rule', **kwargs)


def check(p, value, minute=0, **kwargs):
    return p.signals.check_value('T', site_id='S', parameter='temperature', value=value, unit=kwargs.pop('unit', 'degC'),
                                 batch_id=kwargs.pop('batch_id', 'B1'),
                                 event_time=f'2026-11-15T00:{minute:02d}:00+00:00', **kwargs)


def test_duration_uses_source_time_and_resets_on_recovery(p):
    spec(p, duration_seconds=120, max_observation_gap_seconds=90)
    assert check(p, 31, 0) is None
    assert check(p, 31, 1) is None
    assert check(p, 20, 2) is None
    assert check(p, 32, 3) is None
    assert check(p, 32, 4) is None
    signal = check(p, 32, 5)
    assert signal['severity'] == 'action'
    assert signal['observations'][-1]['event_time'] == '2026-11-15T00:05:00+00:00'
    assert signal['rule_version'] and signal['limit']['duration_seconds'] == 120
    assert p.store.read().list('T', 'case') == []


def test_duration_does_not_bridge_unsampled_gap(p):
    spec(p, duration_seconds=120, max_observation_gap_seconds=90)
    assert check(p, 31, 0) is None
    assert check(p, 31, 5) is None


def test_converts_units_and_retains_original_observation(p):
    spec(p)
    assert check(p, 293.15, unit='kelvin') is None
    hit = check(p, 313.15, 1, unit='kelvin')
    assert hit['value'] == pytest.approx(40)
    assert hit['unit'] == 'degC'
    assert hit['observations'][-1]['original_value'] == 313.15
    assert hit['observations'][-1]['original_unit'] == 'kelvin'


def test_unknown_unit_is_visible_and_not_compared(p):
    spec(p)
    hit = check(p, 300, unit='g/L')
    assert hit['kind'] == 'evaluation_issue'
    assert hit['evaluation_issues'][0]['code'] == 'unit_mismatch'
    assert p.store.read().list('T', 'spec_series') == []


def test_exact_redelivery_does_not_change_series_or_occurrences(p):
    spec(p)
    hit = check(p, 31, evidence_ref={'kind': 'evidence', 'id': 'H:1', 'revision': 1})
    before = p.signals.get(p.identity.context_for('T', 'qa'), hit['signal_id'])
    repeat = check(p, 31, evidence_ref={'kind': 'evidence', 'id': 'H:1', 'revision': 1})
    assert repeat['signal_id'] == hit['signal_id']
    assert repeat['revision'] == before['revision'] and repeat['occurrences'] == 1
    [series] = p.store.read().list('T', 'spec_series')
    assert len(series.state['observations']) == 1


def test_out_of_order_and_late_are_distinct_and_not_current_alarm(p):
    spec(p, allowed_lateness_seconds=60)
    check(p, 20, 3)
    hit = check(p, 31, 1)
    assert hit['kind'] == 'evaluation_issue'
    codes = {issue['code'] for issue in hit['evaluation_issues']}
    assert {'out_of_order', 'late_observation'} <= codes
    [series] = p.store.read().list('T', 'spec_series')
    assert [o['value'] for o in series.state['observations']] == [31, 20]


def test_naive_event_time_is_visible_issue(p):
    spec(p)
    hit = p.signals.check_value('T', site_id='S', parameter='temperature', value=31, unit='degC',
                                event_time='2026-11-15T00:00:00')
    assert hit['kind'] == 'evaluation_issue'
    assert hit['evaluation_issues'][0]['code'] == 'invalid_event_time'


def test_evidence_product_matching_and_associations(p):
    specific = spec(p, product_id='P1')
    ctx = p.identity.context_for('T', 'qa')
    p.evidence.ingest(ctx, source_system='HISTORIAN', source_record_id='H1', content=b'31',
                      media_type='text/plain', site_id='S', event_time='2026-11-15T00:00:00Z',
                      source_revision='r7', mapping_version='m3',
                      metadata={'mapped': {'parameter': 'temperature', 'value': 31, 'unit': 'degC',
                                           'batch_id': 'B1', 'product_id': 'P1', 'equipment_id': 'E1', 'material_id': 'M1'}})
    [signal] = p.signals.list(ctx)
    assert signal['spec_ref']['spec_id'] == specific['spec_id']
    assert signal['associations']['product_id'] == 'P1'
    assert signal['associations']['material_id'] == 'M1'
    assert signal['source']['revision'] == 'r7' and signal['source']['mapping_version'] == 'm3'


def test_cross_batch_trend_requires_distinct_summaries_and_explicit_baseline(p):
    p.specifications.create(p.identity.context_for('T', 'qa'), site_id='S', parameter='yield', unit='%', low=70,
                            product_id='P1', reason='Synthetic yield rule',
                            cross_batch_trend={'baseline': [94, 95, 96], 'window_batches': 3, 'minimum_drop': 5})
    def yield_(batch, value, minute, summary=True):
        return p.signals.check_value('T', site_id='S', parameter='yield', value=value, unit='%', batch_id=batch,
                                     product_id='P1', event_time=f'2026-11-15T00:{minute:02d}:00Z',
                                     observation_type='batch_summary' if summary else 'measurement')
    assert yield_('B0', 85, 0, False) is None
    assert yield_('B1', 89, 1) is None
    assert yield_('B1', 88, 2) is None  # a batch cannot become two batches
    assert yield_('B2', 87, 3) is None
    signal = yield_('B3', 85, 4)
    assert signal['kind'] == 'trend' and signal['severity'] == 'warning'
    assert signal['subject'] == {'kind': 'product', 'id': 'P1'}
    assert {o['batch_id'] for o in signal['observations']} == {'B1', 'B2', 'B3'}
    assert p.store.read().list('T', 'case') == []


@pytest.mark.parametrize('record_type,status,kind', [
    ('calibration', 'overdue', 'equipment_exception'),
    ('cleaning', 'failed', 'procedural_exception'),
    ('environmental_monitoring', 'out_of_limits', 'environmental_exception'),
    ('visual_inspection', 'failed', 'quality_exception'),
    ('stability', 'out_of_limits', 'post_release_exception'),
])
def test_mapped_explicit_failure_facts_raise_categorical_signal(p, record_type, status, kind):
    ctx = p.identity.context_for('T', 'qa')
    fields = {'record_type': record_type, 'status': status, 'equipment_id': 'E1', 'batch_id': 'B1', 'product_id': 'P1'}
    p.evidence.ingest(ctx, source_system='MES', source_record_id='F1', content=json.dumps(fields).encode(),
                      media_type='application/json', site_id='S', event_time='2026-11-15T00:00:00Z',
                      metadata={'mapped': fields})
    [hit] = p.signals.list(ctx)
    assert hit['kind'] == kind and hit['severity'] == 'action'
    assert hit['associations']['equipment_id'] == 'E1'
    assert hit['observations'][0]['status'] == status
    assert hit['evidence_refs'][0]['revision'] == 1


def test_description_does_not_invent_categorical_failure(p):
    ctx = p.identity.context_for('T', 'qa')
    p.evidence.ingest(ctx, source_system='MES', source_record_id='F1', content=b'calibration overdue?',
                      media_type='text/plain', site_id='S', event_time=None,
                      metadata={'mapped': {'record_type': 'calibration', 'description': 'calibration overdue?'}})
    assert p.signals.list(ctx) == []


def test_native_lab_oos_keeps_original_limits_on_unit_mismatch(p):
    from src.lifesci.store import Event
    spec(p, critical_high=35, product_id='P1')
    payload = {'site_id': 'S', 'result_id': 'R1', 'sample_id': 'S1', 'batch_id': 'B1', 'product_id': 'P1',
               'analyte': 'temperature', 'value': 300, 'unit': 'g/L', 'low': 1, 'high': 200,
               'limit_evaluation': 'out_of_limits', 'event_time': '2026-11-15T00:00:00Z'}
    p.signals.on_event(Event('E1', 'T', 'lab.result_recorded', 'result', 'R1', 1, payload, '2026-11-15T00:01:00Z'))
    [hit] = p.signals.list(p.identity.context_for('T', 'qa'))
    assert hit['kind'] == 'lab_oos' and hit['severity'] == 'action'
    assert hit['value'] == 300 and hit['limit'] == {'low': 1, 'high': 200}
    assert hit['evaluation_issues'][0]['code'] == 'unit_mismatch'
    assert hit['associations']['product_id'] == 'P1'


def test_native_lab_normalized_critical_comparison(p):
    from src.lifesci.store import Event
    spec(p, critical_high=35)
    payload = {'site_id': 'S', 'result_id': 'R1', 'sample_id': 'S1', 'analyte': 'temperature',
               'value': 293.15, 'unit': 'kelvin', 'low': 295, 'high': 310, 'limit_evaluation': 'out_of_limits'}
    p.signals.on_event(Event('E1', 'T', 'lab.result_recorded', 'result', 'R1', 1, payload, '2026-11-15T00:01:00Z'))
    [hit] = p.signals.list(p.identity.context_for('T', 'qa'))
    assert hit['severity'] == 'action'  # 20 degC is not above 35 degC
    assert hit['observations'][0]['normalized_value'] == pytest.approx(20)


@pytest.mark.parametrize('options,observation_type', [
    ({'duration_seconds': 120, 'max_observation_gap_seconds': 90}, 'measurement'),
    ({'cross_batch_trend': {'baseline': [20, 21, 22], 'window_batches': 3, 'minimum_drop': 2}, 'product_id': 'P1'}, 'batch_summary'),
])
def test_time_scoped_rules_do_not_invent_missing_timestamps(p, options, observation_type):
    spec(p, **options)
    hit = p.signals.check_value('T', site_id='S', parameter='temperature', value=31 if observation_type == 'measurement' else 20,
                                unit='degC', batch_id='B1', product_id='P1', observation_type=observation_type)
    assert hit['kind'] == 'evaluation_issue'
    assert hit['evaluation_issues'][0]['code'] in ('missing_event_time', 'incomplete_batch_summary')


def test_confirmed_calibration_is_not_a_failure(p):
    ctx = p.identity.context_for('T', 'qa')
    p.evidence.ingest(ctx, source_system='MES', source_record_id='OK', content=b'calibration confirmed',
                      media_type='text/plain', site_id='S', event_time=None,
                      metadata={'mapped': {'record_type': 'calibration', 'status': 'confirmed'}})
    assert p.signals.list(ctx) == []


def test_new_specification_version_does_not_relabel_prior_detection(p):
    first_spec = spec(p)
    first = check(p, 31, 0)
    second_spec = spec(p)
    second = check(p, 32, 1)
    assert second['spec_ref']['version'] == 2
    assert first['signal_id'] != second['signal_id']
    prior = p.signals.get(p.identity.context_for('T', 'qa'), first['signal_id'])
    assert prior['spec_ref'] == {'spec_id': first_spec['spec_id'], 'version': 1}
    assert second['spec_ref']['spec_id'] == second_spec['spec_id']


def test_in_order_delay_does_not_mean_out_of_order(p):
    spec(p, allowed_lateness_seconds=60)
    check(p, 20, 0)
    hit = check(p, 31, 3)
    assert hit['kind'] == 'spec_excursion' and hit['evaluation_issues'] == []


def test_cross_batch_unit_mismatch_never_enters_summary_trend(p):
    p.specifications.create(p.identity.context_for('T', 'qa'), site_id='S', parameter='yield', unit='%', low=70,
                            product_id='P1', reason='Synthetic yield rule',
                            cross_batch_trend={'baseline': [94, 95, 96], 'window_batches': 3, 'minimum_drop': 5})
    hit = p.signals.check_value('T', site_id='S', parameter='yield', value=89, unit='g', product_id='P1',
                                batch_id='B1', event_time='2026-11-15T00:00:00Z', observation_type='batch_summary')
    assert hit['kind'] == 'evaluation_issue'
    assert p.store.read().list('T', 'spec_series') == []


def test_mapped_lab_oos_preserves_source_result_evidence(p):
    ctx = p.identity.context_for('T', 'qa')
    fields = {'record_type': 'lab_result', 'status': 'out_of_limits', 'batch_id': 'B1',
              'test': 'purity', 'value': 94.2, 'unit': '%', 'low': 98, 'high': 100}
    p.evidence.ingest(ctx, source_system='LIMS', source_record_id='R1', content=json.dumps(fields).encode(),
                      media_type='application/json', site_id='S', event_time='2026-11-15T00:00:00Z',
                      metadata={'mapped': fields})
    [hit] = p.signals.list(ctx)
    assert hit['kind'] == 'lab_oos' and hit['severity'] == 'action'
    assert hit['value'] == 94.2 and hit['limit'] == {'low': 98, 'high': 100}
    assert hit['observations'][0]['facts']['status'] == 'out_of_limits'


def test_mapped_observation_time_is_normalized_with_original_preserved(p):
    ctx = p.identity.context_for('T', 'qa')
    p.evidence.ingest(ctx, source_system='MES', source_record_id='F2', content=b'failed',
                      media_type='text/plain', site_id='S', event_time='2026-11-15T01:00:00+01:00',
                      metadata={'mapped': {'record_type': 'cleaning', 'status': 'failed'}})
    [hit] = p.signals.list(ctx)
    assert hit['event_time'] == '2026-11-15T00:00:00+00:00'
    assert hit['observations'][0]['event_time'] == '2026-11-15T00:00:00+00:00'
    assert hit['observations'][0]['original_event_time'] == '2026-11-15T01:00:00+01:00'


def test_duration_signal_exposes_all_supporting_evidence_references(p):
    spec(p, duration_seconds=120, max_observation_gap_seconds=90)
    check(p, 31, 0, evidence_ref={'kind': 'evidence', 'id': 'H:0', 'revision': 1})
    check(p, 31, 1, evidence_ref={'kind': 'evidence', 'id': 'H:1', 'revision': 1})
    hit = check(p, 31, 2, evidence_ref={'kind': 'evidence', 'id': 'H:2', 'revision': 1})
    assert {ref['id'] for ref in hit['evidence_refs']} == {'H:0', 'H:1', 'H:2'}


def test_duration_longer_than_fifty_samples_raises_with_complete_evidence(p):
    from datetime import datetime, timedelta, timezone
    spec(p, duration_seconds=3600, max_observation_gap_seconds=90, trend_rules=False)
    start = datetime(2026, 11, 15, tzinfo=timezone.utc)
    hit = None
    for minute in range(62):
        hit = p.signals.check_value('T', site_id='S', parameter='temperature', value=31, unit='degC', batch_id='B1',
                                    event_time=(start + timedelta(minutes=minute)).isoformat(),
                                    evidence_ref={'kind': 'evidence', 'id': f'H:{minute}', 'revision': 1})
        if minute < 60:
            assert hit is None
        else:
            assert hit['kind'] == 'spec_excursion'
    assert hit['occurrences'] == 2
    assert {ref['id'] for ref in hit['evidence_refs']} == {f'H:{minute}' for minute in range(62)}
    assert {o['evidence_ref']['id'] for o in hit['observations']} == {f'H:{minute}' for minute in range(62)}
    persisted = p.signals.get(p.identity.context_for('T', 'qa'), hit['signal_id'])
    assert len(persisted['observations']) == 62
    [series] = p.store.read().list('T', 'spec_series')
    timestamps = [datetime.fromisoformat(o['event_time']) for o in series.state['observations']]
    assert (max(timestamps) - min(timestamps)).total_seconds() >= 3600


@pytest.mark.parametrize('reset', ['recovery', 'gap', 'version'])
def test_long_duration_history_resets_on_recovery_gap_and_version(p, reset):
    from datetime import datetime, timedelta, timezone
    options = {'duration_seconds': 3600, 'max_observation_gap_seconds': 90, 'trend_rules': False}
    spec(p, **options)
    start = datetime(2026, 11, 15, tzinfo=timezone.utc)
    def reading(minute, value=31):
        return p.signals.check_value('T', site_id='S', parameter='temperature', value=value, unit='degC', batch_id='B1',
                                     event_time=(start + timedelta(minutes=minute)).isoformat(),
                                     evidence_ref={'kind': 'evidence', 'id': f'H:{minute}', 'revision': 1})
    for minute in range(55):
        assert reading(minute) is None
    if reset == 'recovery':
        reading(55, 20)
        next_start = 56
    elif reset == 'gap':
        next_start = 57  # exceeds the explicit maximum sample gap
    else:
        spec(p, **options)
        next_start = 55
    for minute in range(next_start, next_start + 60):
        assert reading(minute) is None
    hit = reading(next_start + 60)
    assert hit['kind'] == 'spec_excursion'
    assert {ref['id'] for ref in hit['evidence_refs']} == {f'H:{minute}' for minute in range(next_start, next_start + 61)}
