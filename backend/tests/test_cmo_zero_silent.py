"""Zero-silent-error guarantees for CMO deliveries: nothing dropped without a
flag, nothing accepted without a confirmed mapping or a named reviewer, and
setup/review work that does not repeat. Small independent fixtures; no network."""
from __future__ import annotations

import csv
import io
import json
import time
import zipfile

import httpx
import pytest
from openpyxl import Workbook

from benchmarks.cmo_ingestion.generate import write_pdf
from src.manufacturing_data.cmo import quality
from src.manufacturing_data.cmo.classify import by_content
from src.manufacturing_data.cmo.evidence import SupabaseEvidence
from src.manufacturing_data.cmo.pipeline import IngestionService, digest
from src.manufacturing_data.cmo.schema import draft_mapping, header_parts, normalize, time_key


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as stream:
        writer=csv.writer(stream); writer.writerow(headers); writer.writerows(rows)


def pdf(path, lines):
    path.parent.mkdir(parents=True,exist_ok=True); write_pdf(path,lines)


def workbook(path, sheets):
    path.parent.mkdir(parents=True,exist_ok=True)
    book=Workbook(); book.remove(book.active)
    for name,rows in sheets.items():
        sheet=book.create_sheet(name)
        for row in rows: sheet.append(row)
    book.save(path)


def confirm_all(service, run, **extra):
    for layout in run['layouts']:
        mapping={**layout['mapping'],**extra.get(layout['fingerprint'],{})}
        service.confirm_template(run['id'],layout['fingerprint'],mapping,'qa-test','Compared mapping with original source')


@pytest.fixture
def service(tmp_path): return IngestionService(tmp_path/'store')


def test_real_world_headers_units_and_identifiers():
    assert header_parts('Temperature (°C)')==('Temperature','°C')
    assert header_parts('Run (2)')==('Run (2)',None)
    mapping=draft_mapping(['Lot No.','Elapsed time (h)','Temperature (°C)','pH','DO (mg/L)'])
    assert mapping.batch_column=='Lot No.' and mapping.time_column=='Elapsed time (h)'
    assert mapping.columns=={'Temperature (°C)':'temperature','pH':'pH','DO (mg/L)':'dissolved_oxygen'}
    assert normalize('37','°C','temperature')[0]==pytest.approx(310.15)
    assert normalize('7.0',None,'pH')==(7.0,'pH')
    with pytest.raises(ValueError): normalize('37',None,'temperature')
    assert normalize('14.5','psi','pressure')[0]==pytest.approx(0.99974,rel=1e-4)
    assert time_key('2026-10-01T08:00:00Z')<time_key('2026-10-01T09:00:00+00:00')
    with pytest.raises(ValueError,match='offset'): time_key('2026-10-01 08:00')


def test_content_classification_without_tidy_filenames():
    assert by_content(['ACME Biologics','Certificate of Analysis','Lot: 2231'])[0]=='coa'
    assert by_content(['Deviation Report DEV-0042','Root cause: pending'])[0]=='deviation_report'
    assert by_content(['Quarterly newsletter'])[0]=='other'
    assert by_content([],['Lot','Elapsed time (h)','pH','Temperature (°C)'])[0]=='instrument_export'
    assert by_content([],['Batch','Time (h)','Viable air (CFU/m3)'])[0]=='environmental_monitoring'
    assert by_content([],['Lot','Time (h)','pH','Temperature (°C)','DO (mg/L)','Bioburden (CFU/mL)'])[0]=='instrument_export'


def test_text_sheet_is_flagged_not_dropped_and_blocks_verification(service, tmp_path):
    raw=tmp_path/'delivery'
    workbook(raw/'export_2231.xlsx',{'Process':[['Lot','Elapsed time (h)','Temperature (°C)','pH'],['L-1',0,37,7.0],['L-1',1,37.2,7.01]],
                                     'Notes':[['Comment'],['Probe recalibrated at hour 1']]})
    run=service.run(raw,'acme','D')
    assert run['status']=='complete',run.get('error')
    assert run['documents'][0]['doc_type']=='instrument_export' and run['documents'][0]['classification_method']=='content'
    notes=next(i for i in run['issues'] if i['rule_code']=='UNRECOGNIZED_TABLE')
    assert notes['sheet']=='Notes'
    assert run['coverage']['flagged']==1 and run['coverage']['unaccounted']==0
    assert run['coverage']['measurement']==4 and run['coverage']['identifier']==4
    check=quality.guarantee(run)
    assert check['holds'],check
    # Confirm the process sheet; ignoring the notes table is an explicit decision.
    process=next(l for l in run['layouts'] if l['sheet']=='Process'); notes_layout=next(l for l in run['layouts'] if l['sheet']=='Notes')
    service.confirm_template(run['id'],process['fingerprint'],process['mapping'],'qa','Checked mapping')
    service.confirm_template(run['id'],notes_layout['fingerprint'],{'columns':{},'ignored_columns':['Comment']},'qa','Free-text notes; read, not process data')
    again=service.run(raw,'acme','D')
    assert again['summary']['auto_accepted']==4 and again['coverage']['ignored']==1
    assert again['summary']['verified_package'] and quality.guarantee(again)['holds']


def test_confirm_once_reprocess_and_carry_forward_decisions(service, tmp_path):
    raw=tmp_path/'d1'
    write_csv(raw/'process.csv',['batch_id','elapsed_h','temperature [degC]','raman 1800 [unspecified]'],
              [['B-1',0,35,10],['B-1',1,36,11],['B-2',0,35,12]])
    first=service.run(raw,'acme','D')
    assert first['summary']['needs_review']==6 and first['summary']['review_groups']==2
    raman=[m for m in first['measurements'] if m['parameter']=='raman_1800']
    service.review(first['id'],raman[0]['id'],'reject','qa','Saturated detector at this point',binding=digest(raman[0]))
    layout=first['layouts'][0]
    service.confirm_template(first['id'],layout['fingerprint'],{**layout['mapping'],'units':{'raman 1800 [unspecified]':'unspecified'}},
                             'qa','Raman intensity is in arbitrary detector units')
    second=service.run(raw,'acme','D')
    second=service.carry_over(first['id'],second)
    assert second['summary']['auto_accepted']==5, second['summary']
    rejected=[m for m in second['measurements'] if m['status']=='rejected']
    assert len(rejected)==1 and second['carried_over']['reviews']==1
    assert 'Carried forward' in second['reviews'][0]['reason'] and second['reviews'][0]['actor']=='qa'
    assert service.get(first['id'])['superseded_by']==second['id']
    assert second['summary']['verified_package'] and quality.guarantee(second)['holds']


def test_changed_layout_reuses_confirmed_meanings_and_reports_diff(service, tmp_path):
    write_csv(tmp_path/'d1'/'process.csv',['batch_id','elapsed_h','temperature [degC]','pH [pH]','pressure [bar]'],[['B-1',0,35,7,1.1]])
    confirm_all(service,service.run(tmp_path/'d1','acme','D'))
    write_csv(tmp_path/'d2'/'process.csv',['batch_id','elapsed_h','temperature [degC]','pH [pH]','Vessel pressure (kPa)','Operator'],[['B-2',0,36,7.1,110,'JS']])
    run=service.run(tmp_path/'d2','acme','D')
    layout=run['layouts'][0]
    assert layout['based_on']['added_headers']==['Vessel pressure (kPa)','Operator']
    assert layout['based_on']['removed_headers']==['pressure [bar]']
    assert layout['mapping']['columns']['temperature [degC]']=='temperature'
    assert layout['mapping']['columns']['Vessel pressure (kPa)']=='pressure'
    assert {'LAYOUT_CHANGED','UNMAPPED_FIELD'}<={i['rule_code'] for i in run['issues']}
    assert run['summary']['auto_accepted']==0 and run['coverage']['unaccounted']==0
    confirm_all(service,run,**{layout['fingerprint']:{'ignored_columns':['Operator']}})
    again=service.run(tmp_path/'d2','acme','D')
    assert again['summary']['auto_accepted']==3 and again['summary']['verified_package']
    pressure=next(m for m in again['measurements'] if m['parameter']=='pressure')
    assert pressure['value']==pytest.approx(1.1)


def test_bulk_review_writes_one_receipt_per_value_and_reports_stale(service, tmp_path):
    write_csv(tmp_path/'d'/'p.csv',['batch_id','elapsed_h','pH [pH]'],[['B',0,7],['B',1,7.1],['B',2,7.2]])
    run=service.run(tmp_path/'d','acme','D'); m=run['measurements']
    stale={'measurement_id':m[2]['id'],'binding':'0'*64}
    result=service.review_many(run['id'],[{'measurement_id':x['id'],'binding':digest(x)} for x in m[:2]]+[stale],'accept','qa','Spot-checked against CSV rows 2-3')
    assert result['applied']==2 and result['failed'][0]['measurement_id']==m[2]['id']
    after=service.get(run['id'])
    assert len(after['reviews'])==2 and all(r['actor']=='qa' for r in after['reviews'])
    assert quality.guarantee(after)['holds']


def test_boilerplate_ignored_once_then_clean_next_delivery(service, tmp_path):
    lines=['ACME Biologics - Confidential','Certificate of Analysis','Page 1 of 1','Batch: B-1 | Hour: 0 | product [g/L]: 2.1']
    pdf(tmp_path/'d1'/'coa.pdf',lines)
    run=service.run(tmp_path/'d1','acme','D')
    leftover=next(i for i in run['issues'] if i['rule_code']=='UNACCOUNTED_CONTENT')
    assert leftover['count']==3 and run['coverage']['unaccounted']==0
    assert not run['summary']['verified_package']
    with pytest.raises(ValueError,match='bare number'): service.add_ignore_rule('acme','# #','qa','x')
    service.resolve_issue(run['id'],leftover['id'],'qa','Letterhead and pagination only',ignore_in_future=True)
    pdf(tmp_path/'d2'/'coa.pdf',[*lines[:3],'Batch: B-2 | Hour: 0 | product [g/L]: 2.4'])
    nxt=service.run(tmp_path/'d2','acme','D')
    assert not any(i['rule_code']=='UNACCOUNTED_CONTENT' for i in nxt['issues'])
    assert nxt['coverage']['ignored']==3


def test_missing_document_versus_previous_verified_delivery(service, tmp_path):
    write_csv(tmp_path/'d1'/'process.csv',['batch_id','elapsed_h','pH [pH]'],[['B-1',0,7]])
    pdf(tmp_path/'d1'/'coa.pdf',['Batch: B-1 | Hour: 0 | product [g/L]: 2.1'])
    first=service.run(tmp_path/'d1','acme','D'); confirm_all(service,first)
    verified=service.run(tmp_path/'d1','acme','D')
    assert verified['summary']['verified_package'],[i for i in verified['issues'] if i['status']=='open']
    write_csv(tmp_path/'d2'/'process.csv',['batch_id','elapsed_h','pH [pH]'],[['B-2',0,7.1]])
    run=service.run(tmp_path/'d2','acme','D')
    codes={i['rule_code']:i for i in run['issues']}
    assert codes['EXPECTED_DOCUMENT_MISSING']['doc_type']=='coa'
    assert codes['EXPECTED_PARAMETER_MISSING']['parameter']=='product'
    assert run['expectations_basis']['run_id']==verified['id'] and not run['summary']['verified_package']


def test_per_batch_document_gap_detected(service, tmp_path):
    write_csv(tmp_path/'d'/'process.csv',['batch_id','elapsed_h','pH [pH]'],[['B-1',0,7],['B-2',0,7],['B-3',0,7]])
    pdf(tmp_path/'d'/'coa.pdf',['Batch: B-1 | Hour: 0 | product [g/L]: 2','Batch: B-2 | Hour: 0 | product [g/L]: 2.2'])
    run=service.run(tmp_path/'d','acme','D')
    gaps=[i for i in run['issues'] if i['rule_code']=='BATCH_DOCUMENT_MISSING']
    assert [(g['batch'],g['doc_type']) for g in gaps]==[('B-3','coa')]


def test_guarantee_detects_rule_violations(service, tmp_path):
    write_csv(tmp_path/'d'/'p.csv',['batch_id','elapsed_h','pH [pH]'],[['B',0,7]])
    run=service.run(tmp_path/'d','acme','D')
    forged={**run,'measurements':[{**run['measurements'][0],'status':'auto_accepted'}]}
    assert not quality.guarantee(forged)['holds']
    dropped={**run,'elements':[*run['elements'],{'id':'x','path':'p.csv','sheet':None,'column':'Mystery','row':2,'page':None,'state':'pending'}]}
    failed={c['id']:c['passed'] for c in quality.guarantee(dropped)['checks']}
    assert failed['content_accounted'] is False


def test_timestamps_require_offsets_before_acceptance(service, tmp_path):
    write_csv(tmp_path/'d'/'p.csv',['Lot','Time (h)','pH'],[['L',0,7]])
    write_csv(tmp_path/'e'/'p.csv',['batch_id','timestamp','pH [pH]'],[['L','2026-10-01 08:00',7]])
    run=service.run(tmp_path/'d','acme','D')
    assert run['measurements'][0]['rule_codes']==['DRAFT_MAPPING']
    local=service.run(tmp_path/'e','other','D')
    assert local['status']=='complete'


def test_supabase_evidence_restores_and_verifies(tmp_path):
    objects={}
    def handler(request):
        key=request.url.path.split('/object/cmo-evidence/',1)[1]
        if request.method=='POST':
            if key in objects: return httpx.Response(400,json={'error':'Duplicate','message':'The resource already exists'})
            objects[key]=request.content; return httpx.Response(200,json={'Key':key})
        return httpx.Response(200,content=objects[key]) if key in objects else httpx.Response(404)
    store=SupabaseEvidence('https://project.supabase.co','service-key','cmo-evidence')
    store.client=httpx.Client(transport=httpx.MockTransport(handler))
    from src.manufacturing_data.cmo.evidence import IntegrityError, restore, sha256_file
    source=tmp_path/'a.csv'; source.write_text('x,y\n1,2\n'); sha=sha256_file(source)
    store.put('originals/aa/'+sha+'.csv',source); store.put('originals/aa/'+sha+'.csv',source)
    restored=restore(store,'originals/aa/'+sha+'.csv',tmp_path/'cache'/'a.csv',sha)
    assert restored.read_text()=='x,y\n1,2\n'
    objects['originals/aa/'+sha+'.csv']=b'tampered'
    (tmp_path/'cache'/'a.csv').unlink()
    with pytest.raises(IntegrityError): restore(store,'originals/aa/'+sha+'.csv',tmp_path/'cache'/'a.csv',sha)


def test_api_delivery_upload_auto_config_bulk_and_reprocess(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.manufacturing_data.cmo.api import router
    for name in ['OPENAI_API_KEY','CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_AUTH_TOKEN','SUPABASE_URL','CMO_DATABASE_URL']: monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv('CMO_INGESTION_ROOT',str(tmp_path/'runtime')); monkeypatch.setenv('CMO_PACKAGES_ROOT',str(tmp_path/'none'))
    monkeypatch.setenv('CMO_API_TOKEN','t'); monkeypatch.setenv('CMO_HOSTED_INFERENCE_APPROVED','true')
    app=FastAPI(); app.include_router(router(tmp_path)); client=TestClient(app); client.headers['X-CMO-Token']='t'
    delivery=client.post('/api/cmo-ingestion/deliveries',json={'cmo':'Acme CDMO','name':'October lots'}).json()
    body=io.StringIO(); csv.writer(body).writerows([['Lot','Elapsed time (h)','pH','Temperature (°C)'],['L-1',0,7.0,37],['L-1',1,7.1,37.1]])
    added=client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files",params={'filename':'lot export.csv'},content=body.getvalue().encode())
    assert added.status_code==200 and added.json()['files'][0]['sha256']
    assert client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files",params={'filename':'run.exe'},content=b'x').status_code==400
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z: z.writestr('../evil.csv','a')
    assert client.post(f"/api/cmo-ingestion/deliveries/{delivery['id']}/files",params={'filename':'p.zip'},content=archive.getvalue()).status_code==400
    def wait(ident):
        for _ in range(200):
            run=client.get('/api/cmo-ingestion/runs/'+ident).json()
            if run['status'] not in {'queued','running'}: return run
            time.sleep(.02)
        raise AssertionError('run did not finish')
    run=wait(client.post('/api/cmo-ingestion/runs',json={'package_id':delivery['id']}).json()['id'])
    assert run['status']=='complete' and run['requested_configuration']=='auto' and run['configuration']=='D'
    assert run['configuration_notes'] and run['hosted_inference']['approved']
    assert 'elements' not in run and run['guarantee']['holds'] and len(run['review_groups'])==2
    group=run['review_groups'][0]; bindings={m['id']:m['review_binding'] for m in run['measurements']}
    items=[{'measurement_id':i,'binding':bindings[i]} for i in group['measurement_ids']]
    # Rejecting needs a reason; accepting records a default one.
    assert client.post(f"/api/cmo-ingestion/runs/{run['id']}/reviews/bulk",json={'items':items,'decision':'reject','actor':'Parker'}).status_code==400
    bulk=client.post(f"/api/cmo-ingestion/runs/{run['id']}/reviews/bulk",json={'items':items,'decision':'accept','actor':'Parker'}).json()
    assert bulk['applied']==2 and not bulk['failed']
    receipts=client.get('/api/cmo-ingestion/runs/'+run['id']).json()['reviews']
    assert receipts[0]['reason']=='Accepted after checking the source' and receipts[0]['actor']=='Parker'
    layout=run['layouts'][0]
    assert client.post(f"/api/cmo-ingestion/runs/{run['id']}/templates",json={'fingerprint':layout['fingerprint'],'mapping':layout['mapping'],
                       'actor':'Parker'}).status_code==200
    newer=wait(client.post(f"/api/cmo-ingestion/runs/{run['id']}/reprocess",json={'actor':'Parker'}).json()['id'])
    # Earlier acceptances are not re-applied: the confirmed mapping now accepts
    # these values on its own rules; only rejections/corrections override it.
    assert newer['summary']['verified_package'] and newer['carried_over']['reviews']==0
    assert newer['summary']['auto_accepted']==4 and newer['guarantee']['holds']
    assert client.post(f"/api/cmo-ingestion/runs/{run['id']}/reprocess",json={'actor':'Parker'}).status_code==409
    listed=client.get('/api/cmo-ingestion/runs',params={'cmo':'Acme CDMO'}).json()['runs']
    assert [r['id'] for r in listed]==[newer['id'],run['id']]
    assert client.get(f"/api/cmo-ingestion/runs/{newer['id']}/verified").json()['guarantee']['holds']
    catalog=client.get('/api/cmo-ingestion/catalog').json()
    assert 'Acme CDMO' in catalog['cmos'] and catalog['storage']=={'records':'sqlite','originals':'local'}
    assert client.get('/api/cmo-ingestion/vocabulary').json()['parameters']
    # Dismissing missing information needs a typed reason.
    other=client.post('/api/cmo-ingestion/deliveries',json={'cmo':'Gap CDMO'}).json()
    rows=io.StringIO(); csv.writer(rows).writerows([['batch_id','elapsed_h','pH [pH]'],['B',0,7],['B',1,'']])
    client.post(f"/api/cmo-ingestion/deliveries/{other['id']}/files",params={'filename':'p.csv'},content=rows.getvalue().encode())
    gap=wait(client.post('/api/cmo-ingestion/runs',json={'package_id':other['id']}).json()['id'])
    missing=next(i for i in gap['issues'] if i['rule_code']=='MISSING_FIELD')
    url=f"/api/cmo-ingestion/runs/{gap['id']}/issues"
    assert client.post(url,json={'issue_id':missing['id'],'actor':'Parker'}).status_code==400
    assert client.post(url,json={'issue_id':missing['id'],'actor':'Parker','reason':'Sample not taken at hour 1'}).status_code==200
