"""Independent case fixtures: actual ingestion/calculations, no cached findings."""
import io
import json
import time
import uuid
import zipfile

import pytest

from src.manufacturing_data.cmo.cases import CaseService
from src.manufacturing_data.cmo.pipeline import digest

DATA=b'batch_id,elapsed_h,temperature [K],pH [pH],product [g/L]\nDEV-A,0,305,7,0\nDEV-A,2,306,7.1,2\nDEV-B,0,305,7,0\nDEV-B,2,306,6.9,1\n'


def execute(service,ident):
    lease=uuid.uuid4().hex
    with service.connect() as con:con.execute("UPDATE pharma_jobs SET status='running',lease=?,attempt=attempt+1 WHERE id=?",(lease,ident))
    service.execute(ident,lease)
    job=service.job(ident,'tenant-a')
    assert job['status']=='complete',job.get('error')
    return job


@pytest.fixture
def case(tmp_path):
    service=CaseService(tmp_path/'runtime')
    project=service.create_project('tenant-a','Fermentation')
    case=service.create_case(project['id'],'tenant-a','Compare batches','Describe product observations; identify missing comparability evidence.')
    return service,project,case


def imported(case):
    service,_,record=case
    imported=service.import_bytes(record['id'],'tenant-a','fermentation.csv',DATA)
    execute(service,imported['job_id'])
    return imported


def reviewed(service,ident):
    run=service.ingestion.get(ident)
    for m in list(run['measurements']):
        service.ingestion.review(ident,m['id'],'accept','fixture-reviewer','Test protocol checks printed source cell',binding=digest(m))
    return service.ingestion.get(ident)


def test_real_intake_verified_analysis_review_handoff_and_restart(case):
    service,project,record=case; item=imported(case)
    with pytest.raises(ValueError,match='Review'):service.analyze(record['id'],'tenant-a')
    reviewed(service,item['job_id'])
    analysis=execute(service,service.analyze(record['id'],'tenant-a',parameters=['product'])['job_id'])
    findings=analysis['result']['findings']
    assert [f['calculation']['mean']['value'] for f in findings]==[1,.5]
    assert [f['calculation']['last_minus_first']['value'] for f in findings]==[2,1]
    assert all(len(f['sources'])==2 and f['sources'][0]['source']['row'] for f in findings)
    result=service.review_finding(analysis['id'],'tenant-a',findings[0]['id'],'accept','qa','Arithmetic/source review complete',analysis['result']['version'])
    assert result['reviews'][0]['decision']=='accept'
    action=service.action(record['id'],'tenant-a','Obtain feed and volume context','MSAT','Needed before interpreting yield',[findings[0]['sources'][0]['id']])
    for status in ['reviewed','in_progress','outcome_recorded']:
        service.action_status(action,'tenant-a',status,'qa','Context requested; outcome remains an observed record')
    restarted=CaseService(service.root)
    assert restarted.case(record['id'],'tenant-a')['problem']==record['problem']
    handoff=restarted.export(record['id'],'tenant-a')
    assert 'mean 1' in handoff and 'SHA-256' in handoff and 'MSAT' in handoff and 'Arithmetic/source review complete' in handoff
    assert restarted.actions(record['id'],'tenant-a')[0]['status']=='outcome_recorded'


def test_duplicate_idempotency_new_content_version_and_staleness(case):
    service,_,record=case; item=imported(case); reviewed(service,item['job_id'])
    analysis=execute(service,service.analyze(record['id'],'tenant-a')['job_id'])
    same=service.import_bytes(record['id'],'tenant-a','fermentation.csv',DATA)
    assert same['duplicate'] and same['job_id']==item['job_id']
    changed=service.import_bytes(record['id'],'tenant-a','fermentation.csv',DATA.replace(b'DEV-A,2,306,7.1,2',b'DEV-A,2,306,7.1,3'))
    assert changed['version']==2 and changed['job_id']!=item['job_id']
    assert service.job(analysis['id'],'tenant-a')['stale']
    assert 'STALE' in service.export(record['id'],'tenant-a')


def test_correction_preserves_snapshot_and_invalidates_review(case):
    service,_,record=case; item=imported(case); run=reviewed(service,item['job_id'])
    analysis=execute(service,service.analyze(record['id'],'tenant-a',parameters=['product'])['job_id'])
    original=json.dumps(analysis['result'],sort_keys=True)
    m=next(m for m in run['measurements'] if m['parameter']=='product' and m['value']==2)
    service.ingestion.review(run['id'],m['id'],'correct','qa','Correct source transcription',binding=digest(m),value='3',unit='g/L')
    stale=service.job(analysis['id'],'tenant-a')
    assert stale['stale'] and json.dumps(stale['result'],sort_keys=True)==original
    with pytest.raises(ValueError,match='stale'):service.review_finding(analysis['id'],'tenant-a',stale['result']['findings'][0]['id'],'accept','qa','Old version',stale['result']['version'])


def test_project_isolation_and_zip_guards(case):
    service,project,record=case
    with pytest.raises(KeyError):service.case(record['id'],'tenant-b')
    with pytest.raises(KeyError):service.import_bytes(record['id'],'tenant-b','x.csv',DATA)
    for name in ['../escape.csv','nested.zip','run.exe']:
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as book:book.writestr(name,DATA)
        with pytest.raises(ValueError):service.import_bytes(record['id'],'tenant-a','package.zip',out.getvalue())
    other=service.create_project('tenant-b','Other')
    assert other['id']!=project['id'] and len(service.projects('tenant-a'))==1


def test_cancellation_retry_and_restart_state(case):
    service,_,record=case
    item=service.import_bytes(record['id'],'tenant-a','fermentation.csv',DATA)
    assert service.cancel(item['job_id'],'tenant-a')['status']=='cancelled'
    assert service.resume(item['job_id'],'tenant-a')['status']=='queued'
    with service.connect() as con:con.execute("UPDATE pharma_jobs SET status='running',lease='old' WHERE id=?",(item['job_id'],))
    service.start(); service.stop()
    assert service.job(item['job_id'],'tenant-a')['status']=='interrupted'


def test_api_ownership_token_and_import_transports(case,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from src.manufacturing_data.cmo.case_api import case_router
    from src.manufacturing_data.cmo.api import router
    service,_,record=case; item=imported(case)
    monkeypatch.setenv('CMO_INGESTION_ROOT',str(service.root)); monkeypatch.setenv('CMO_API_TOKEN','fixture-token')
    def identity():return SimpleNamespace(tenant_id='tenant-a',actor_id='qa',roles=['admin'])
    app=FastAPI(); app.include_router(case_router(service,identity)); app.include_router(router(service.root))
    client=TestClient(app)
    url=f'/api/pharma/package-upload/{record["id"]}?filename=fermentation.csv'
    assert client.post(url,content=DATA).status_code==401
    assert client.post(url,content=DATA,headers={'X-CMO-Token':'fixture-token'}).json()['duplicate']
    original=service.ingestion.get(item['job_id'])['measurements'][0]
    src=f'/api/cmo-ingestion/runs/{item["job_id"]}/sources/{original["source_id"]}'
    assert client.get(src,headers={'X-CMO-Token':'fixture-token','X-Tenant-Id':'tenant-b'}).status_code==404
    assert client.get(src,headers={'X-CMO-Token':'fixture-token','X-Tenant-Id':'tenant-a'}).status_code==200


def test_watched_folder_settling_and_restart_idempotency(case,tmp_path,monkeypatch):
    service,_,record=case
    folder=tmp_path/'drop'; folder.mkdir(); monkeypatch.setenv('PHARMA_WATCH_ROOT',str(folder))
    service.watch(record['id'],'tenant-a',folder,settle_seconds=2)
    (folder/'fermentation.csv').write_bytes(DATA)
    service._scan_watches(); assert not service.imports(record['id'],'tenant-a')
    with service.connect() as con:
        row=con.execute('SELECT * FROM pharma_watches').fetchone(); seen=json.loads(row['seen'])
        seen['fermentation.csv']['since']-=3
        con.execute('UPDATE pharma_watches SET seen=? WHERE id=?',(json.dumps(seen),row['id']))
    service._scan_watches(); assert len(service.imports(record['id'],'tenant-a'))==1
    CaseService(service.root)._scan_watches(); assert len(service.imports(record['id'],'tenant-a'))==1


def test_renamed_identical_import_is_idempotent(case):
    service,_,record=case; item=imported(case)
    renamed=service.import_bytes(record['id'],'tenant-a','renamed.csv',DATA)
    assert renamed['duplicate'] and renamed['job_id']==item['job_id']


def test_real_excursion_can_be_corrected_with_a_review_warning(case):
    service,_,_=case; item=imported(case)
    m=next(m for m in service.ingestion.get(item['job_id'])['measurements'] if m['parameter']=='temperature')
    updated=service.ingestion.review(item['job_id'],m['id'],'correct','fixture-reviewer','Actual source excursion confirmed by reviewer',binding=digest(m),value='401',unit='K')
    changed=next(v for v in updated['measurements'] if v.get('supersedes')==m['id'])
    assert changed['value']==401 and changed['status']=='corrected' and 'RANGE' in changed['rule_codes']


@pytest.mark.parametrize('payload',['=HYPERLINK("https://invalid.example")',' @SUM(1,2)','\n=1+1','\t+1'])
def test_spreadsheet_export_escapes_imported_formula_text(case,payload):
    service,_,record=case; item=imported(case); run=reviewed(service,item['job_id'])
    run['measurements'][0]['batch']=payload
    service.ingestion.save(run)
    import csv
    exported=service.ingestion.export(run['id'])
    row=next(csv.DictReader(io.StringIO(exported.decode())))
    assert row['batch']=="'"+payload


def test_cross_package_conflicts_are_not_averaged_as_replicates(case):
    service,_,record=case; first=imported(case); reviewed(service,first['job_id'])
    second=service.import_bytes(record['id'],'tenant-a','fermentation-other.csv',DATA.replace(b'DEV-A,2,306,7.1,2',b'DEV-A,2,306,7.1,9'))
    execute(service,second['job_id']); reviewed(service,second['job_id'])
    snapshot=service.snapshot(record['id'],'tenant-a')
    assert not snapshot['measurements']
    assert any('Conflicting values' in gap and 'product' in gap for gap in snapshot['gaps'])
    assert any('Repeated records' in gap for gap in snapshot['gaps'])
    with pytest.raises(ValueError,match='Review'):service.analyze(record['id'],'tenant-a')


def test_running_worker_cancellation_terminates_actual_child(case):
    service,_,record=case
    header,_,body=DATA.partition(b'\n')
    item=service.import_bytes(record['id'],'tenant-a','fermentation-cancel.csv',header+b'\n'+body*1000)
    service.start()
    try:
        deadline=time.monotonic()+10
        while service._process is None and time.monotonic()<deadline:time.sleep(.01)
        child=service._process
        assert child is not None and child.poll() is None
        service.cancel(item['job_id'],'tenant-a')
        deadline=time.monotonic()+10
        while child.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        assert child.poll() is not None
        assert service.job(item['job_id'],'tenant-a')['status']=='cancelled'
    finally:service.stop()
