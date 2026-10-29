"""PostgreSQL (Supabase) persistence for CMO ingestion.

Runs only with CMO_TEST_DATABASE_URL pointing at a DISPOSABLE database: the
test drops and recreates the cmo_* tables."""
from __future__ import annotations

import csv
import os

import pytest

URL=os.getenv('CMO_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='set CMO_TEST_DATABASE_URL to a disposable PostgreSQL database')


@pytest.fixture
def service(tmp_path,monkeypatch):
    import psycopg
    with psycopg.connect(URL,autocommit=True) as con:
        for table in ['cmo_runs','cmo_templates','cmo_ignore_rules','cmo_deliveries','cmo_events']:
            con.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
    monkeypatch.setenv('CMO_DATABASE_URL',URL); monkeypatch.setenv('CMO_DATABASE_MIGRATE','true')
    from src.manufacturing_data.cmo.pipeline import IngestionService
    return IngestionService(tmp_path/'runtime')


def test_postgres_round_trip_templates_audit_and_append_only(service,tmp_path):
    import psycopg
    from src.manufacturing_data.cmo import quality
    raw=tmp_path/'d'; raw.mkdir()
    with (raw/'process.csv').open('w',newline='') as stream:
        csv.writer(stream).writerows([['batch_id','elapsed_h','pH [pH]'],['B',0,7],['B',1,7.1]])
    assert service.repo.backend=='postgresql'
    first=service.run(raw,'acme','D')
    assert first['status']=='complete',first.get('error')
    layout=first['layouts'][0]
    service.confirm_template(first['id'],layout['fingerprint'],layout['mapping'],'qa','Checked')
    second=service.run(raw,'acme','D')
    assert second['summary']['auto_accepted']==2 and second['summary']['verified_package']
    assert [r['id'] for r in service.runs('acme')]==[first['id'],second['id']]
    assert service.get(second['id'])['coverage']['unaccounted']==0 and quality.guarantee(service.get(second['id']))['holds']
    service.repo.save_delivery({'id':'delivery-x','cmo':'acme','files':[]})
    assert service.repo.deliveries()[0]['id']=='delivery-x'
    assert service.verify_audit()
    with psycopg.connect(URL,autocommit=True) as con:
        for statement in ["UPDATE cmo_events SET hash='x'","DELETE FROM cmo_templates","UPDATE cmo_ignore_rules SET pattern='x'"]:
            with pytest.raises(psycopg.errors.RaiseException): con.execute(statement)
