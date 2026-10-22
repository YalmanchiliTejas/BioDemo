"""Ingestion safety regressions, using independent small source fixtures, no network."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest

from benchmarks.cmo_ingestion.evaluate import score
from benchmarks.cmo_ingestion.generate import build_package, write_pdf
from src.manufacturing_data.cmo.pipeline import IngestionService, digest, fingerprint
from src.manufacturing_data.cmo.providers import Provider, Unavailable
from src.manufacturing_data.cmo.schema import Mapping, normalize


def process(tmp_path,name,rows,headers=None):
    folder=tmp_path/name; folder.mkdir()
    with (folder/'bioreactor.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(headers or ['batch_id','elapsed_h','temperature [degC]','pH [pH]'])
        writer.writerows(rows)
    return folder


@pytest.fixture
def setup(tmp_path):
    service=IngestionService(tmp_path/'store')
    raw=process(tmp_path,'calibration',[['LOCAL-1',0,35,7],['LOCAL-1',1,36,7.1]])
    return service,raw


def confirm_all(service,run):
    for layout in run['layouts']:
        service.confirm_template(run['id'],layout['fingerprint'],layout['mapping'],'qa-test','Compared original source and mapping')


def test_confirmed_template_reuse_zero_calls_and_exact_sources(setup,tmp_path,monkeypatch):
    service,raw=setup
    first=service.run(raw,'local')
    assert first['status']=='complete',first.get('error')
    assert first['summary']['auto_accepted']==0
    assert first['summary']['needs_review']==4
    confirm_all(service,first)
    returning=process(tmp_path,'returning',[['LOCAL-2',0,32,6.8],['LOCAL-2',1,33,6.9]])
    def forbidden(*a,**k): raise AssertionError('Returning layout invoked a model')
    monkeypatch.setattr(Provider,'call',forbidden)
    result=service.run(returning,'local','D')
    assert result['summary']['auto_accepted']==4 and result['summary']['model_calls']==0
    assert result['summary']['verified_package']
    temperatures=[m for m in result['measurements'] if m['parameter']=='temperature']
    assert sorted(m['value'] for m in temperatures)==pytest.approx([305.15,306.15])
    assert all(m['source']['row'] in {2,3} and m['source']['column']=='temperature [degC]' and m['source_verified'] for m in temperatures)
    assert service.verify_audit()


def test_changed_layout_missing_conflicts_and_review_block(setup,tmp_path):
    service,raw=setup; confirm_all(service,service.run(raw,'local'))
    changed=process(tmp_path,'changed',[['LOCAL-3',0,'',7],['LOCAL-3',1,33,7.1],['LOCAL-3',1,40,7.1]])
    run=service.run(changed,'local','D')
    codes={i['rule_code'] for i in run['issues']}
    assert {'MISSING_FIELD','DUPLICATE_CONFLICT'}<=codes
    assert run['summary']['auto_accepted']==0
    drift=process(tmp_path,'drift',[['LOCAL-4',0,36,7]],['batch_id','elapsed_h','Unqualified [degC]','pH [pH]'])
    result=service.run(drift,'local','D')
    assert {'LAYOUT_CHANGED','UNMAPPED_FIELD'}<={i['rule_code'] for i in result['issues']}
    assert result['summary']['auto_accepted']==0


def test_same_fingerprint_different_data_and_cmo_isolation(setup,tmp_path):
    service,raw=setup; first=service.run(raw,'local'); confirm_all(service,first)
    second=service.run(raw,'other','D')
    assert first['layouts'][0]['fingerprint']==second['layouts'][0]['fingerprint']
    assert second['summary']['auto_accepted']==0
    assert fingerprint('instrument_export','A',['pH [pH]','temperature [K]'],'.xlsx')!=fingerprint('instrument_export','B',['pH [pH]','temperature [K]'],'.xlsx')


def test_source_tampering_blocks_export_and_immutable_review(setup):
    service,raw=setup; run=service.run(raw,'local'); m=run['measurements'][0]
    corrected=service.review(run['id'],m['id'],'correct','qa-test','Source correction',binding=digest(m),value='310',unit='K',parameter='temperature')
    assert corrected['reviews'][0]['before']['value']==m['value']
    assert corrected['measurements'][0]['value']==310
    with pytest.raises(ValueError,match='binding changed'):
        service.review(run['id'],m['id'],'accept','qa-test','Stale browser',binding=digest(m))
    path,_=service.original(run['id'],m['source_id']); path.chmod(0o600); path.write_text('changed')
    with pytest.raises(ValueError,match='integrity'): service.export(run['id'])
    with service.connect() as con:
        with pytest.raises(sqlite3.IntegrityError): con.execute("UPDATE events SET hash='tampered'")


def test_byte_identical_normalized_exports_after_confirmation(setup):
    service,raw=setup; confirm_all(service,service.run(raw,'local'))
    first=service.run(raw,'local','D'); second=service.run(raw,'local','D')
    assert service.export(first['id'])==service.export(second['id'])
    assert b'source_sha256' in service.export(first['id'])
    assert service.export(first['id'],format='xlsx')[:2]==b'PK'
    assert service.export(first['id'],wide=True)


def test_oracle_sibling_never_used_for_ingestion(setup,tmp_path):
    service,raw=setup
    evaluation=raw.parent/'evaluation'; evaluation.mkdir()
    (evaluation/'answer_key.json').write_text('{"temperature":"FAKE ORACLE"}')
    first=service.run(raw,'local')
    (evaluation/'answer_key.json').write_text('this is intentionally invalid JSON')
    second=service.run(raw,'local')
    comparable=lambda r:[{k:m[k] for k in ['batch','parameter','time','value','unit','source']} for m in r['measurements']]
    assert comparable(first)==comparable(second)


@pytest.mark.parametrize('raw,unit,parameter,expected',[
    ('35','degC','temperature',308.15),('2,5','mg/mL','product',2.5),('100','kPa','pressure',1),
    ('100','mL/min','sugar_feed',6),('20','mg/L','dissolved_oxygen',20)])
def test_units(raw,unit,parameter,expected): assert normalize(raw,unit,parameter)[0]==pytest.approx(expected)


@pytest.mark.parametrize('raw,unit', [('NaN','K'),('inf','K'),('5','bar'),('10','unknown')])
def test_bad_units_and_nonfinite_rejected(raw,unit):
    with pytest.raises(ValueError): normalize(raw,unit,'temperature')


def test_invalid_ocr_time_requires_source_correction(setup):
    service,raw=setup; run=service.run(raw,'local'); m=run['measurements'][0]
    m['time']='@'; service.save(run)
    with pytest.raises(ValueError,match='process hour'):
        service.review(run['id'],m['id'],'accept','qa','Checked source',binding=digest(m))
    corrected=service.review(run['id'],m['id'],'correct','qa','Read hour from original source',binding=digest(m),
                             value=str(m['value']),unit=m['unit'],time_value='0')
    assert corrected['measurements'][0]['time']=='0'
    assert corrected['superseded_measurements'][0]['time']=='@'


def test_missing_page_and_batch_identifier_mismatch(setup):
    service,raw=setup
    write_pdf(raw/'coa.pdf',['Document type: coa','Page 1 of 2','Batch: TYPO | Hour: 0 | product [g/L]: 2'])
    run=service.run(raw,'local')
    assert {'MISSING_PAGE','BATCH_MISMATCH'}<={i['rule_code'] for i in run['issues']}
    pdf=next(m for m in run['measurements'] if m['source']['path']=='coa.pdf')
    assert pdf['source']['page']==1 and pdf['source_verified']


def test_unknown_backend_is_unavailable_not_fake_success(setup,monkeypatch):
    service,raw=setup
    monkeypatch.setenv('CMO_MAPPING_PROVIDER','compatible')
    for role in ['MAPPING','CLAIRIC','JEV']: monkeypatch.delenv('CMO_'+role+'_URL',raising=False)
    for config in ['A','B','C']:
        run=service.run(raw,'local',config,synthetic=True)
        assert run['status']=='unavailable' and not run['measurements']
        assert score(run,{'fields':[]})['status']=='unavailable'


def test_docling_keeps_page_and_box_and_does_not_auto_verify(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    from src.manufacturing_data.ingest import _document_observations
    monkeypatch.delenv('DOCLING_ARTIFACTS_PATH',raising=False)
    item=SimpleNamespace(text='Batch: LOCAL | Hour: 1 | pH [pH]: 7',
        prov=[SimpleNamespace(page_no=3,bbox=SimpleNamespace(l=10,t=20,r=30,b=40))])
    doc=SimpleNamespace(iterate_items=lambda:iter([(item,0)]))
    monkeypatch.setitem(sys.modules,'docling.document_converter',SimpleNamespace(
        DocumentConverter=lambda:SimpleNamespace(convert=lambda _:SimpleNamespace(document=doc))))
    rows=list(_document_observations('source','record.pdf',tmp_path/'record.pdf','local',None,'docling'))
    assert len(rows)==1 and rows[0].source.page==3 and rows[0].source.region==(10,20,30,40)
    assert rows[0].validation_status=='unverified'


def test_endpoint_allowlist_and_customer_data_gate(monkeypatch):
    monkeypatch.setenv('CMO_DECISIONS_URL','https://not-approved.invalid/v1/decisions')
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setenv('CMO_ALLOWED_ORIGINS','http://localhost:8001')
    with pytest.raises(Unavailable,match='Unexpected outbound'): Provider('mapping',lambda r:None,synthetic=True)
    monkeypatch.setenv('CMO_ALLOWED_ORIGINS','https://not-approved.invalid')
    with pytest.raises(Unavailable,match='Hosted inference'): Provider('mapping',lambda r:None)


def test_mapping_schema_validation_retries_and_usage_audit(monkeypatch):
    monkeypatch.delenv('CMO_DECISIONS_INPUT_USD_PER_MILLION',raising=False)
    monkeypatch.delenv('CMO_MAPPING_OUTPUT_USD_PER_MILLION',raising=False)
    monkeypatch.setenv('CMO_DECISIONS_URL','http://localhost:8001/v1/decisions')
    monkeypatch.setenv('CMO_ALLOWED_ORIGINS','http://localhost:8001')
    attempts=[]
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self,*args): self.close()
    class Opener:
        def open(self,*args,**kwargs):
            return Response(json.dumps({'answers':[], 'usage':{'input_tokens':12,'output_tokens':0}}).encode())
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:Opener())
    with pytest.raises(Unavailable,match='Decisions validation'):
        Provider('mapping',attempts.append).call('map_headers',{'headers':['X']},Mapping)
    assert len(attempts)==3 and all(r['input_tokens']==12 and r['cost_usd'] is None for r in attempts)


def test_generator_reproducible_and_explicitly_synthetic(tmp_path):
    records=[{'batch':'SYN-ONLY','time':'1','fields':{p:{'raw':str(v),'value':v,'unit':u} for p,v,u in
             [('pH',7,'pH'),('temperature',310,'K'),('dissolved_oxygen',5,'mg/L'),('product',2,'g/L'),
              ('pressure',2,'bar'),('bioburden',8,'CFU/mL'),('environment_cfu',3,'CFU/m3')]}}]*2
    one=build_package(tmp_path/'one','sanofi','changed',records)
    two=build_package(tmp_path/'two','sanofi','changed',records)
    assert one['files']==two['files'] and one['synthetic'] and 'NOT actual Sanofi' in one['disclosure']
    raw=tmp_path/'one'/'sanofi-changed'/'raw'
    assert not list(raw.glob('*answer*'))
    with zipfile.ZipFile(raw/'bioreactor_process.xlsx') as book:
        assert b'2026-01-01T00:00:00Z</dcterms:modified>' in book.read('docProps/core.xml')
    from pypdf import PdfReader
    assert not PdfReader(raw/'microbiology.pdf').pages[0].extract_text().strip()


def test_evaluator_false_acceptances_and_malformed_ocr():
    field={'batch':'X','time':'1','parameter':'pH','value':7,'unit':'pH','present':True,
           'source':{'path':'p.csv','row':2,'column':'pH [pH]'}}
    run={'status':'complete','measurements':[{**field,'value':12,'status':'auto_accepted','parser':'csv'}],
         'issues':[],'documents':[{'path':'p.csv','doc_type':'instrument_export'}],
         'summary':{'needs_review':0,'open_issues':0,'corrections':0,'model_calls':0,'input_tokens':0,'output_tokens':0,'inference_cost_usd':0},
         'human_minutes':None,'human_time_status':'not_measured','runtime_seconds':1,'id':'test'}
    key={'fields':[field],'documents':{'p.csv':'instrument_export'},'defects':[]}
    result=score(run,key)
    assert result['field_recall']==1 and result['incorrect_auto_accepted_count']==1 and result['auto_accepted_value_accuracy']==0
    assert result['human_minutes'] is None
    run['measurements'][0]['time']='@'
    assert score(run,key)['field_recall']==0


def test_api_real_job_upload_source_review_and_export(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    packages=tmp_path/'packages'; p=process(packages if packages.exists() else tmp_path,'raw',[['API-1',0,35,7]])
    folder=packages/'test'; folder.mkdir(parents=True); p.rename(folder/'raw')
    (packages/'catalog.json').write_text(json.dumps([{'id':'test','dataset':'indpensim','condition':'unseen','cmo':'api','synthetic':False,'disclosure':'Test fixture only','files':[{'path':'bioreactor.csv'}]}]))
    monkeypatch.setenv('CMO_INGESTION_ROOT',str(tmp_path/'runtime')); monkeypatch.setenv('CMO_PACKAGES_ROOT',str(packages)); monkeypatch.setenv('CMO_API_TOKEN','test-token')
    app=FastAPI(); app.include_router(router(tmp_path)); client=TestClient(app)
    assert client.get('/api/cmo-ingestion/catalog').status_code==401
    client.headers['X-CMO-Token']='test-token'
    ident=client.post('/api/cmo-ingestion/runs',json={'package_id':'test','configuration':'preview'}).json()['id']
    for _ in range(100):
        response=client.get('/api/cmo-ingestion/runs/'+ident); run=response.json()
        if run['status'] not in {'queued','running'}: break
        time.sleep(.02)
    assert run['status']=='complete',run
    m=run['measurements'][0]
    cells=client.get(f'/api/cmo-ingestion/runs/{ident}/cells/{m["id"]}').json()
    assert cells['source']['row']==2 and cells['values'][0]=='API-1'
    review={'measurement_id':m['id'],'binding':m['review_binding'],'decision':'accept','actor':'api-reviewer','reason':'Inspected raw CSV cell'}
    assert client.post(f'/api/cmo-ingestion/runs/{ident}/reviews',json=review).status_code==200
    exported=client.get(f'/api/cmo-ingestion/runs/{ident}/export')
    assert b'API-1' in exported.content and exported.headers['x-package-complete']=='false'
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive: archive.writestr('../evil.csv','a\n1')
    assert client.post('/api/cmo-ingestion/upload',content=buffer.getvalue()).status_code==400
    assert client.get('/api/cmo-ingestion/audit').json()['valid']


def test_api_pdf_page_rendering_uses_original_hash_and_page_bounds(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    runtime=tmp_path/'runtime'; service=IngestionService(runtime)
    raw=tmp_path/'raw'; raw.mkdir()
    write_pdf(raw/'batch_record.pdf',['Page 1 of 1','Batch: LOCAL | Hour: 1 | pH [pH]: 7'])
    run=service.run(raw,'local'); m=run['measurements'][0]
    monkeypatch.setenv('CMO_INGESTION_ROOT',str(runtime)); monkeypatch.delenv('CMO_API_TOKEN',raising=False)
    app=FastAPI(); app.include_router(router(tmp_path)); client=TestClient(app)
    base=f'/api/cmo-ingestion/runs/{run["id"]}/pages/{m["source_id"]}'
    response=client.get(base+'/1')
    assert response.content.startswith(b'\x89PNG') and float(response.headers['x-page-height'])==640
    assert client.get(base+'/2').status_code==400
