from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package
from src.manufacturing_data.session import ManufacturingSession


def test_excel_blank_rows_mixed_cells_and_exact_locations(tmp_path):
    package=tmp_path/'package'; package.mkdir()
    workbook=Workbook(); sheet=workbook.active; sheet.title='R01'
    sheet.append(['batch_id','equipment_id','available_at','value','mixed','flag','date'])
    sheet.append([None]*7)
    sheet.append(['B1','EQ1','2024-01-02T00:00:00Z',1.25,'text',True,datetime(2024,1,1)])
    sheet.append(['B1','EQ1','2024-01-03T00:00:00Z',2.5,8,False,datetime(2024,1,2)])
    workbook.save(package/'EXP001.xlsx')
    store=ManufacturingStore(tmp_path/'store')
    result=ingest_package(package,store,workers=2)
    assert result['errors']==[]
    rows=store.visible(limit=None)
    assert len(rows)==14
    values=[r for r in rows if r['name']=='value']
    assert {r['source_ref']['cell'] for r in values}=={'D3','D4'}
    assert {r['value_number'] for r in values}=={1.25,2.5}
    tools=ManufacturingTools(store)
    for row in rows:
        assert tools.verify_evidence(observation_id=row['id'])['value_matches'],row
    assert 'EQ1' in tools.get_process_context(entity_id='B1')['related_entities']
    assert len(ManufacturingSession(store,as_of='2024-01-02T12:00:00Z',scopes=('default',)).get([r['id'] for r in rows]))==7
    with store.connect() as con:
        assert con.execute('SELECT count(*) FROM observations').fetchone()[0]==0
        assert con.execute('SELECT row_count FROM sheets').fetchone()[0]==3


def test_query_cannot_bypass_scope_or_cutoff_through_internal_views(tmp_path):
    package=tmp_path/'package'; package.mkdir()
    (package/'data.csv').write_text('available_at,value\n2024-01-01T00:00:00Z,1\n2025-01-01T00:00:00Z,999\n')
    store=ManufacturingStore(tmp_path/'store')
    ingest_package(package,store,access_scope='a')
    ingest_package(package,store,access_scope='b')
    tools=ManufacturingTools(store,scopes=('a',),as_of='2024-06-01T00:00:00Z')
    assert tools.query_data(sql='SELECT sum(value_number) FROM observations')['rows']==[[1.0]]
    for sql in ['SELECT x.* FROM observations o JOIN _all_observations x ON TRUE',
                "SELECT * FROM observations UNION ALL SELECT * FROM query_table('_all_observations')",
                "SELECT * FROM observations UNION ALL SELECT * FROM read_parquet('secret.parquet')"]:
        with pytest.raises(ValueError): tools.query_data(sql=sql)
    assert ManufacturingTools(store,scopes=('none',)).query_data(sql='SELECT count(*) FROM observations')['rows']==[[0]]


def test_reindex_publishes_new_partitions_without_old_rows_and_skips_unchanged(tmp_path):
    package=tmp_path/'package'; package.mkdir()
    path=package/'data.csv'; path.write_text('batch_id,value\nB1,1\nB2,2\n')
    store=ManufacturingStore(tmp_path/'store')
    assert ingest_package(package,store)['observations']==4
    first_ids={r['id'] for r in store.visible(limit=None)}
    assert ingest_package(package,store)['unchanged']==1
    assert {r['id'] for r in store.visible(limit=None)}==first_ids
    path.write_text('batch_id,value\nB3,3\n')
    assert ingest_package(package,store)['observations']==2
    assert ManufacturingTools(store).query_data(sql='SELECT sum(value_number) FROM observations')['rows']==[[3.0]]
    assert len(list(store.measurements.glob('*.parquet')))==1
    with store.connect() as con:
        assert not list(con.execute('SELECT * FROM relations'))


def test_duplicate_headers_fail_instead_of_losing_source_columns(tmp_path):
    package=tmp_path/'package'; package.mkdir()
    workbook=Workbook(); sheet=workbook.active
    sheet.append(['value','value']); sheet.append([1,2]); workbook.save(package/'duplicate.xlsx')
    store=ManufacturingStore(tmp_path/'store')
    result=ingest_package(package,store)
    assert len(result['errors'])==1 and 'duplicate headers' in result['errors'][0]['error']
    assert not store.visible()
    assert not list(store.measurements.glob('*.parquet'))


def test_original_region_respects_row_and_field_publication_times(tmp_path):
    import csv
    package=tmp_path/'package'; package.mkdir()
    with (package/'data.csv').open('w',newline='') as handle:
        writer=csv.writer(handle)
        writer.writerow(['available_at','value','field_available_at'])
        writer.writerow(['2024-01-01T00:00:00Z',8,json.dumps({'value':'2025-01-01T00:00:00Z'})])
        writer.writerow(['2025-01-01T00:00:00Z',999,''])
    store=ManufacturingStore(tmp_path/'store'); ingest_package(package,store)
    source=store.visible_sources()[0]['id']
    tools=ManufacturingTools(store,as_of='2024-06-01T00:00:00Z')
    assert 'value' not in tools.extract_region(source_id=source,row=2)['data']
    assert tools.extract_region(source_id=source,row=3)['status']=='region_not_found'
    with pytest.raises(PermissionError): tools.query_data(sql='SELECT * FROM observations',as_of=None)
    with pytest.raises(PermissionError): tools.inspect_data(as_of=None)
