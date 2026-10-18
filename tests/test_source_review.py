import hashlib
import json
from pathlib import Path
import pytest
from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package
from src.manufacturing_data.models import Observation, SourceRef
from src.manufacturing_data.source_review import review_packet, page_image, record_review
from benchmarks.common.objective_scores import validate_citation


@pytest.fixture
def sources(tmp_path):
    from PIL import Image, ImageDraw
    package=tmp_path/'sources';package.mkdir()
    (package/'manifest.json').write_text('{\n\n  "dataset": "synthetic",\n  "count": 100\n}\n')
    image=Image.new('RGB',(500,150),'white');ImageDraw.Draw(image).text((20,30),'Sample result: 1.23',fill='black')
    image.save(package/'scan.pdf','PDF')
    store=ManufacturingStore(tmp_path/'store')
    ingest_package(package,store,access_scope='review-scope')
    source=next(s for s in store.visible_sources(scopes=('review-scope',)) if s['path']=='scan.pdf')
    store.add_observations([Observation(observation_id='ocr-review-test',
        source=SourceRef(source_id=source['id'],path='scan.pdf',page=1,span='line:1'),
        name='document_text',value_text='Sample result: 1.23',extraction_method='tesseract',
        validation_status='unverified',access_scope='review-scope',available_at='2024-01-01T00:00:00Z')])
    return store,package,{'as_of':'2030-01-01T00:00:00Z','scopes':('review-scope',)}


def test_json_original_lines_and_changed_value_rejection(sources):
    store,package,visibility=sources;tools=ManufacturingTools(store,**visibility)
    rows=[r for r in store.visible(**visibility,limit=None) if r['source_ref']['path']=='manifest.json']
    assert rows and all(c['value_matches'] is True for c in tools.verify_many(rows).values())
    row=next(r for r in rows if r['source_ref']['span']=='line:3')
    assert review_packet(store,row['id'],**visibility)['original_line']=='  "dataset": "synthetic",'
    changed={**row,'value_text':'  "dataset": "authentic",'}
    assert tools.verify_many([changed])[row['id']]['value_matches'] is False
    bad={**row,'source_ref':{**row['source_ref'],'span':'line:300'}}
    assert tools.verify_many([bad])[row['id']]['value_matches'] is None
    allowlist={'manifest.json':{'sha256':hashlib.sha256((package/'manifest.json').read_bytes()).hexdigest()}}
    check=validate_citation({'source':row['source_ref']},package,allowlist)
    assert check['pass']
    assert not validate_citation({'source':bad['source_ref']},package,allowlist)['pass']


def test_scanned_page_review_is_not_automatic_verification(sources):
    store,package,visibility=sources
    packet=review_packet(store,'ocr-review-test',**visibility)
    assert packet['review_status']=='human_review_pending'
    assert page_image(store,'ocr-review-test',**visibility).startswith(b'\x89PNG')
    receipt=record_review(store,'ocr-review-test',**visibility,packet_sha256=packet['packet_sha256'],
        reviewer_id='qa-reviewer',decision='matches',note='Compared the extracted result with the original page image.')
    assert not receipt['independent_scientific_qualification']
    assert review_packet(store,'ocr-review-test',**visibility)['human_reviews']==[receipt]
    assert ManufacturingTools(store,**visibility).verify_evidence(observation_id='ocr-review-test')['value_matches'] is None
    from src.manufacturing_data.session import ManufacturingSession
    from src.workflows.report_verification import verify_report
    report={'observed_facts':[{'statement':'Source record extracted.','evidence_ids':['ocr-review-test']}]}
    _,_,verified=verify_report(report,ManufacturingSession(store,**visibility),ManufacturingTools(store,**visibility),{'ocr-review-test'})
    assert verified['source_verification_status']=='verified_with_human_review'
    assert verified['unverified_source_count']==1 and verified['pending_source_review_count']==0
    allowlist={'scan.pdf':{'sha256':hashlib.sha256((package/'scan.pdf').read_bytes()).hexdigest()}}
    check=validate_citation({'source':packet['source_ref']},package,allowlist)
    assert not check['pass'] and check['verification_status']=='human_review_pending'
    check=validate_citation({'source':{**packet['source_ref'],'page':99}},package,allowlist)
    assert not check['pass'] and check['verification_status']=='failed'
    record_review(store,'ocr-review-test',**visibility,packet_sha256=packet['packet_sha256'],
        reviewer_id='qa-reviewer',decision='does_not_match',note='Corrected review: extracted text differs.')
    with pytest.raises(ValueError,match='immutable original'):
        verify_report(report,ManufacturingSession(store,**visibility),ManufacturingTools(store,**visibility),{'ocr-review-test'})


def test_review_binding_scope_and_original_integrity(sources):
    store,_,visibility=sources;packet=review_packet(store,'ocr-review-test',**visibility)
    with pytest.raises(KeyError):review_packet(store,'ocr-review-test',as_of=visibility['as_of'],scopes=('other-tenant',))
    with pytest.raises(KeyError):review_packet(store,'ocr-review-test',as_of='2023-01-01T00:00:00Z',scopes=visibility['scopes'])
    with pytest.raises(ValueError,match='changed'):
        record_review(store,'ocr-review-test',**visibility,packet_sha256='stale',reviewer_id='qa',decision='matches',note='Checked')
    digest=packet['source_sha256'];original=store.originals/digest[:2]/(digest+'.pdf');original.chmod(0o600);original.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash changed'):review_packet(store,'ocr-review-test',**visibility)


def test_pdf_preview_cannot_expose_future_text_on_visible_page(sources):
    store,_,visibility=sources;packet=review_packet(store,'ocr-review-test',**visibility)
    store.add_observations([Observation(observation_id='future-page-text',
        source=SourceRef(**packet['source_ref']),name='document_text',value_text='Future result',
        extraction_method='tesseract',access_scope='review-scope',available_at='2040-01-01T00:00:00Z')])
    with pytest.raises(PermissionError,match='unavailable'):page_image(store,'ocr-review-test',**visibility)


def test_complete_investigation_can_await_source_review(tmp_path,monkeypatch):
    from tests.test_investigation_review import case, complete_report
    bridge,tools,prepared,rows=case.__wrapped__(tmp_path)
    report=complete_report(prepared)
    actual=tools.verify_many
    # Simulate an unsupported source receipt, without bypassing any false-value
    # or integrity failure. All report and scope checks still execute.
    def pending(selected):
        checks=actual(selected);first=next(iter(checks.values()))
        first.update(value_matches=None,verification_status='human_review_pending')
        return checks
    monkeypatch.setattr(bridge.tools,'verify_many',pending)
    result=bridge.submit_report(report)
    assert result['investigation_status']=='complete'
    assert result['source_verification_status']=='human_review_pending'
    assert result['scientific_validation_status']=='independent_review_pending'
    assert result['verification']['unverified_source_count']==1


def test_source_review_api_scope_roles_and_packet_binding(sources,monkeypatch,tmp_path):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from benchmark.application.api import create_app
    from benchmark.application.bootstrap import build_demo_services
    from src.prime_runtime import PrimeManufacturingHarness
    store,_,visibility=sources
    monkeypatch.setenv('BIODEMO_MANUFACTURING_STORE',str(store.root));monkeypatch.setenv('BIODEMO_MANUFACTURING_SCOPE','review-scope')
    monkeypatch.setattr(PrimeManufacturingHarness,'from_env',classmethod(lambda cls,**kwargs:object()))
    client=TestClient(create_app(build_demo_services(tmp_path/'app')))
    headers={'X-Tenant-Id':'review-scope','X-Actor-Id':'qa-test','X-Roles':'qa'}
    base='/api/manufacturing-os/evidence/ocr-review-test';params={'as_of':visibility['as_of']}
    packet=client.get(base+'/review-packet',params=params,headers=headers).json()
    assert packet['packet_sha256']
    assert client.get(base+'/page-image',params=params,headers=headers).headers['content-type']=='image/png'
    assert client.get('/manufacturing-source-review/ocr-review-test',params=params,headers=headers).status_code==200
    body={'packet_sha256':packet['packet_sha256'],'decision':'unreadable','note':'Image needs domain reviewer.'}
    assert client.post(base+'/source-review',params=params,headers={**headers,'X-Roles':'operator'},json=body).status_code==403
    assert client.get(base+'/review-packet',params=params,headers={**headers,'X-Tenant-Id':'other'}).status_code==403
    response=client.post(base+'/source-review',params=params,headers=headers,json=body)
    assert response.status_code==200 and response.json()['reviewer_id']=='qa-test'


def test_unchecked_visual_citation_is_pending_not_scientific_failure():
    from benchmarks.common.quality import score_review
    run={'attempted':True,'audit':{'pass':True},'isolation_audit':{'pass':True},
         'run_id':'source-pending','status':'incomplete','investigation_status':'complete',
         'case':{'quality_policy_sha256':'policy','required_deliverables':[]},
         'output':{'analysis':{'report_status':'complete_for_available_evidence','source_verification_status':'human_review_pending'}},
         'objective_scores':{'evidence':{'citation_checks':[{'pass':False,'verification_status':'human_review_pending'}]}}}
    policy={'dimensions':[],'score_scale':[0,4],'integrity_gates':[]}
    result=score_review(run,policy)
    assert result['status']=='pending_review' and result['qualified'] is None
    run['objective_scores']['evidence']['citation_checks'][0]['verification_status']='failed'
    assert score_review(run,policy)['status']=='failed'
