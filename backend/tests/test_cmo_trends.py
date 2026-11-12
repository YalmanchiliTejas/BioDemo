"""Trends and cross-delivery export: accepted values only, traceable to their source, never silently merged."""
from __future__ import annotations

import csv
import io

import pytest

from src.manufacturing_data.cmo import trends
from src.manufacturing_data.cmo.pipeline import IngestionService


def delivery(tmp_path, name, rows):
    folder = tmp_path / name; folder.mkdir()
    with (folder / 'bioreactor.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['batch_id', 'elapsed_h', 'temperature [degC]', 'pH [pH]'])
        writer.writerows(rows)
    return folder


@pytest.fixture(autouse=True)
def bound_tenant():
    from src.manufacturing_data.cmo.persistence import tenant_scope
    with tenant_scope('test-cdmo'): yield


@pytest.fixture
def service(tmp_path):
    service = IngestionService(tmp_path / 'store')
    first = service.run(delivery(tmp_path, 'first', [['B-1', 0, 35, 7], ['B-1', 1, 36, 7.1], ['B-1', 2, 37, 7.2]]), 'local')
    for layout in first['layouts']:
        service.confirm_template(first['id'], layout['fingerprint'], layout['mapping'], 'qa-test', 'Compared original source and mapping')
    service.run(delivery(tmp_path, 'second', [['B-1', 0, 35, 7], ['B-1', 1, 36, 7.1], ['B-1', 2, 37, 7.2]]), 'local')
    service.run(delivery(tmp_path, 'third', [['B-2', 0, 34, 6.9], ['B-2', 1, 39, 7.0]]), 'local')
    return service


def test_only_accepted_values_from_current_deliveries_are_plotted(service):
    entries = trends.batches(service.runs())
    # The first delivery was read before its layout was confirmed: its values still await review, so it contributes nothing.
    assert [e['batch'] for e in entries] == ['B-1', 'B-2']
    assert all(r['measurement']['status'] in trends.ACCEPTED for e in entries for r in e['rows'])
    listing = trends.catalogue(entries)
    assert {p['id']: (p['batches'], p['values']) for p in listing['parameters']} == {'temperature': (2, 5), 'pH': (2, 5)}
    assert listing['deliveries'] == 2


def test_series_keeps_measurement_ids_and_summary_uses_every_value(service, monkeypatch):
    entries = trends.batches(service.runs())
    by_id = {r['measurement']['id']: r['measurement'] for e in entries for r in e['rows']}
    result = {s['batch']: s for s in trends.series(entries, 'temperature')}
    assert [p[:2] for p in result['B-1']['points']] == [[0.0, 308.15], [1.0, 309.15], [2.0, 310.15]]   # stored in the standard unit, K
    assert all(by_id[p[2]]['parameter'] == 'temperature' for s in result.values() for p in s['points'])
    assert result['B-2']['summary']['max']['value'] == pytest.approx(312.15) and result['B-2']['summary']['max']['time_h'] == 1
    assert result['B-1']['summary']['mean'] == pytest.approx(309.15) and result['B-1']['unit'] == 'K'
    monkeypatch.setattr(trends, 'POINT_LIMIT', 2)
    thinned = {s['batch']: s for s in trends.series(entries, 'temperature')}['B-1']
    assert thinned['sampled_every'] == 2 and thinned['points'][-1][0] == 2.0   # the last reading is always kept
    assert thinned['summary']['n'] == 3 and thinned['points_total'] == 3


def test_timestamps_become_hours_since_the_batch_started():
    run = {'id': 'r1', 'status': 'complete', 'cmo': 'x', 'summary': {'verified_package': True}, 'measurements': [
        {'id': 'a', 'batch': 'B', 'parameter': 'pH', 'value': 7.0, 'unit': 'pH', 'status': 'accepted', 'time': '2026-01-01T06:00:00+00:00'},
        {'id': 'b', 'batch': 'B', 'parameter': 'pH', 'value': 7.2, 'unit': 'pH', 'status': 'accepted', 'time': '2026-01-01T09:30:00Z'},
        {'id': 'c', 'batch': 'B', 'parameter': 'pH', 'value': 9.9, 'unit': 'pH', 'status': 'rejected', 'time': '2026-01-01T10:00:00Z'},
        {'id': 'd', 'batch': 'B', 'parameter': 'pH', 'value': None, 'unit': 'pH', 'status': 'accepted', 'time': '2026-01-01T10:00:00Z'}]}
    superseded = {**run, 'id': 'r0', 'superseded_by': 'r1'}
    [entry] = trends.batches([superseded, run])
    assert entry['time_basis'] == 'hours_since_first_reading' and entry['delivery_verified']
    assert [p[:2] for p in trends.series([entry], 'pH')[0]['points']] == [[0.0, 7.0], [3.5, 7.2]]


def test_export_layouts_and_unknown_choices(service):
    def rows(**kw): return list(csv.DictReader(io.StringIO(service.trend_export(**kw).decode())))
    long = rows()
    assert len(long) == 10 and {'measurement_id', 'source', 'source_sha256', 'delivery'} <= long[0].keys()
    assert 'row 2' in long[0]['source']
    key = next(e['key'] for e in trends.batches(service.runs()) if e['batch'] == 'B-2')
    wide = rows(layout='wide', keys=[key])
    assert [(r['time'], r['temperature'], r['pH']) for r in wide] == [('0', '307.15', '6.9'), ('1', '312.15', '7.0')]
    summary = rows(layout='summary', parameters=['temperature'])
    assert [(r['batch'], r['readings'], r['maximum'], r['maximum_at_h']) for r in summary] == [('B-1', '3', '310.15', '2.0'), ('B-2', '2', '312.15', '1.0')]
    assert service.trend_export(format='xlsx')[:2] == b'PK'
    for bad in ({'parameters': ['nope']}, {'keys': ['nope']}, {'layout': 'nope'}, {'format': 'pdf'}):
        with pytest.raises(ValueError): service.trend_export(**bad)


def test_export_refuses_when_a_source_no_longer_matches_its_hash(service):
    run = next(r for r in service.runs() if any(m['batch'] == 'B-2' for m in r['measurements']))
    path, _doc = service.original(run['id'], run['measurements'][0]['source_id'], run=run)
    path.chmod(0o600); path.write_text('tampered')
    with pytest.raises(ValueError, match='integrity'): service.trend_export()


def test_wide_export_refuses_to_merge_conflicting_values():
    def m(i, value): return {'id': i, 'batch': 'B', 'parameter': 'pH', 'value': value, 'unit': 'pH', 'status': 'accepted', 'time': '1'}
    entries = trends.batches([{'id': 'r', 'status': 'complete', 'cmo': 'x', 'measurements': [m('a', 7.0), m('b', 7.4)]}])
    with pytest.raises(ValueError, match='one-value-per-row'): trends.export_rows(entries, 'wide')
    assert len(trends.export_rows(entries, 'long')) == 2


def test_routes(tmp_path, monkeypatch, service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(tmp_path / 'store')); monkeypatch.delenv('CMO_API_TOKEN', raising=False)
    monkeypatch.setenv('CMO_ALLOW_UNAUTHENTICATED_TENANT_HEADER', '1')
    app = FastAPI(); app.include_router(router(tmp_path))
    client = TestClient(app, headers={'X-Tenant-Id': 'test-cdmo'})
    listing = client.get('/api/cmo-ingestion/trends').json()
    assert 'series' not in listing and len(listing['batches']) == 2 and 'run' not in listing['batches'][0]
    chart = client.get('/api/cmo-ingestion/trends', params={'parameter': 'pH'}).json()
    assert [s['batch'] for s in chart['series']] == ['B-1', 'B-2']
    assert client.get('/api/cmo-ingestion/trends', params={'parameter': 'nope'}).status_code == 404
    key = chart['series'][1]['key']
    exported = client.get('/api/cmo-ingestion/trends/export', params=[('batch', key), ('parameter', 'pH'), ('layout', 'long')])
    assert exported.status_code == 200 and exported.text.count('\n') == 3 and 'B-1' not in exported.text
    assert client.get('/api/cmo-ingestion/trends/export', params={'batch': 'nope'}).status_code == 400
    # Another workspace sees none of it.
    assert TestClient(app, headers={'X-Tenant-Id': 'someone-else'}).get('/api/cmo-ingestion/trends').json()['batches'] == []


def test_export_options_columns_units_time_window_and_json(service):
    import json

    def rows(**kw): return service.trend_rows(**kw)
    chosen = rows(parameters=['temperature'], columns=['batch', 'time_h', 'value', 'unit'], celsius=True, time_from=1, time_to=1)
    assert chosen == [{'batch': 'B-1', 'time_h': 1.0, 'value': 36.0, 'unit': '°C'}, {'batch': 'B-2', 'time_h': 1.0, 'value': 39.0, 'unit': '°C'}]
    stored = rows(parameters=['temperature'], time_from=1, time_to=1)[0]
    assert stored['value'] == pytest.approx(309.15) and stored['unit'] == 'K' and stored['value_as_printed'] == '36'   # as printed is never converted
    assert rows(parameters=['pH'], celsius=True)[0]['unit'] == 'pH'                      # only kelvin is converted
    summary = rows(layout='summary', parameters=['temperature'], celsius=True)
    assert [(r['batch'], r['maximum'], r['unit']) for r in summary] == [('B-1', 37.0, '°C'), ('B-2', 39.0, '°C')]
    wide = rows(layout='wide', celsius=True, time_to=0)
    assert [(r['batch'], r['temperature'], r['temperature_unit']) for r in wide] == [('B-1', 35.0, '°C'), ('B-2', 34.0, '°C')]
    assert rows(verified_only=True) == [] or all(r['delivery_verified'] for r in rows(verified_only=True))
    with pytest.raises(ValueError, match='Unknown column: nope'): rows(columns=['batch', 'nope'])
    exported = json.loads(service.trend_export(format='json', parameters=['pH'], columns=['batch', 'value']))
    assert len(exported) == 5 and exported[0] == {'batch': 'B-1', 'value': 7.0}


def test_preview_shows_the_first_rows_of_the_same_file_and_trends_carry_standouts(tmp_path, monkeypatch, service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(tmp_path / 'store')); monkeypatch.delenv('CMO_API_TOKEN', raising=False)
    monkeypatch.setenv('CMO_ALLOW_UNAUTHENTICATED_TENANT_HEADER', '1')
    app = FastAPI(); app.include_router(router(tmp_path))
    client = TestClient(app, headers={'X-Tenant-Id': 'test-cdmo'})
    query = [('parameter', 'temperature'), ('column', 'batch'), ('column', 'value'), ('celsius', 'true')]
    preview = client.get('/api/cmo-ingestion/trends/export', params=[*query, ('preview', '2')]).json()
    assert preview == {'columns': ['batch', 'value'], 'rows': [{'batch': 'B-1', 'value': 35.0}, {'batch': 'B-1', 'value': 36.0}], 'total_rows': 5}
    full = client.get('/api/cmo-ingestion/trends/export', params=[*query, ('format', 'json')])
    assert full.headers['content-type'].startswith('application/json') and full.json()[:2] == preview['rows'] and len(full.json()) == 5
    assert client.get('/api/cmo-ingestion/trends/export', params={'preview': 500}).status_code == 422
    assert client.get('/api/cmo-ingestion/trends/export', params={'format': 'pdf'}).status_code == 400
    found = client.get('/api/cmo-ingestion/trends', params={'parameter': 'temperature'}).json()['standouts']
    top = found['largest_changes_between_consecutive_samples'][0]
    assert (top['batch'], top['from_h'], top['to_h'], round(top['change'], 2)) == ('B-2', 0.0, 1.0, 5.0) and ':' in top['key']
    assert found['typical_change_between_samples'] == 1.0 and found['from_sampled_profiles'] is False
    assert 'largest_same_time_differences' not in found    # two batches: nothing to stand out from
