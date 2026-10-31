"""Shared verification regressions over synthetic connected source records."""
import json
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from src.lifesci.cmo_datasets import require_dataset, conversation_source

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('LIFESCI_CONNECTOR_FILE_ROOT', str(tmp_path))
    p=Platform(RecordStore(),providers={})
    for tenant,actor,role,site in [('T','admin','admin','S1'),('T','qa','qa','S1'),('T','op','operator','S1'),('T','other','qa','S2'),('OTHER','qa','qa','S1')]:
        p.identity.assign_role(tenant,actor,role,site_id=site)
    c=TestClient(create_app(p));h=lambda actor='admin',tenant='T':{'X-Tenant-Id':tenant,'X-Actor-Id':actor}
    yield p,c,h,tmp_path
    p.connectors.close()

def row(ident='r1',**changes):
    return {'id':ident,'timestamp':'2026-10-30T12:00:00Z','batch_id':'B1','elapsed_h':0,'test':'temperature','value':37,'unit':'degC',**changes}

def connect(env,rows,*,cid='lims',confirmed=True,group='cdmo-a',family='LIMS'):
    p,c,h,root=env;folder=root/cid;folder.mkdir(exist_ok=True)
    (folder/'records.json').write_text(json.dumps(rows))
    fields=[{'source':name,'canonical':name,'required':True} for name in ('batch_id','elapsed_h','test','value','unit')]
    cfg={'connector_id':cid,'family':family,'transport':'file','site_id':'S1','owner':'admin','source_group':group,'mapping_confirmed':confirmed,'options':{'directory':str(folder)},'mapping':{'template_id':f'{cid}-1','version':'1','system':family,'record_type':'lab_result','fields':fields}}
    r=c.post('/v1/connectors',headers=h(),json=cfg);assert r.status_code==201,r.text
    return cfg,folder

def sync(env,cid='lims'):
    _,c,h,_=env;r=c.post(f'/v1/connectors/{cid}/sync',headers=h());assert r.status_code==200,r.text
    return r.json()

def view(env,cid='lims'):
    _,c,h,_=env;r=c.get(f'/v1/connectors/{cid}/verification',headers=h());assert r.status_code==200,r.text
    return r.json()

def test_shared_units_ranges_and_originals(env):
    p,c,h,_=env;connect(env,[row(),row('bad',elapsed_h=1,value=200)])
    result=sync(env);assert result['verification']['accepted']==1 and result['verification']['needs_review']==1
    records=view(env)['items'];normal=next(r for r in records if r['source_record_id']=='r1');bad=next(r for r in records if r['source_record_id']=='bad')
    assert normal['measurements'][0]['value']==pytest.approx(310.15)
    assert normal['measurements'][0]['value_raw']==37 and normal['measurements'][0]['unit_raw']=='degC'
    assert 'RANGE' in bad['rule_codes']
    assert c.post('/v1/connectors/lims/verification/publish',headers=h()).status_code==400
    assert b'200' in p.evidence.original(p.identity.context_for('T','admin'),'LIMS@lims:bad')
    from src.ingestion.verification import validate_measurement
    file_value=deepcopy(normal['measurements'][0]);file_value.update(value=None,rule_codes=[])
    validate_measurement(file_value,mapping_confirmed=True,raw_unit='degC')
    assert file_value['value']==normal['measurements'][0]['value']

def test_review_publish_and_correction_invalidate_agent_dataset(env):
    p,c,h,_=env;_,folder=connect(env,[row()],confirmed=False);sync(env);r=view(env)['items'][0]
    body={'record_id':r['id'],'expected_revision':r['revision'],'decision':'accept','reason':'Compared source record and mapping'}
    assert c.post('/v1/connectors/lims/verification/review',headers=h('op'),json=body).status_code==403
    approved=c.post('/v1/connectors/lims/verification/review',headers=h('qa'),json=body);assert approved.status_code==200,approved.text
    assert c.post('/v1/connectors/lims/verification/review',headers=h('qa'),json=body).status_code==409
    pub=c.post('/v1/connectors/lims/verification/publish',headers=h('qa'));assert pub.status_code==200,pub.text
    dataset=pub.json()['id'];ctx=p.identity.context_for('T','qa');require_dataset(p,ctx,dataset,'S1')
    entry,_=conversation_source(p,ctx,dataset,'S1');assert entry['measurement_count']==1 and entry['coverage']['complete'] is False
    assert c.post('/v1/connectors/lims/verification/publish',headers=h('qa')).json()['id']==dataset
    (folder/'records.json').write_text(json.dumps([row(value=38)]));sync(env);new=view(env)['items'][0]
    assert new['review_state']=='needs_review' and new['reviews']==[] and new['measurements'][0]['value']==pytest.approx(311.15)
    with pytest.raises((ValueError,PermissionError)):require_dataset(p,ctx,dataset,'S1')
    entries=c.get('/v1/cmo-datasets',params={'site_id':'S1'},headers=h('qa')).json()['datasets']
    assert next(d for d in entries if d['id']==dataset)['status']=='stale_basis'
    assert c.get('/v1/cmo-datasets/'+dataset,headers=h('qa')).status_code==409
    assert c.get('/v1/connectors/lims/verification',headers=h('other')).status_code==403
    assert c.get('/v1/connectors/lims/verification',headers=h('qa','OTHER')).status_code==404

def test_cross_poll_cross_connector_conflicts_and_rejection(env):
    _,c,h,_=env;connect(env,[row()],cid='lab');sync(env,'lab')
    connect(env,[row('r2',value=40)],cid='process',family='HISTORIAN');sync(env,'process');records=view(env,'lab')['items']
    assert len(records)==2 and all('DUPLICATE_CONFLICT' in r['rule_codes'] and r['review_state']=='needs_review' for r in records)
    assert c.post('/v1/connectors/lab/verification/publish',headers=h()).status_code==400
    r=next(r for r in records if r['source_record_id']=='r2');body={'record_id':r['id'],'expected_revision':r['revision'],'decision':'reject','reason':'Source owner confirms invalid reading'}
    resp=c.post('/v1/connectors/lab/verification/review',headers=h('qa'),json=body);assert resp.status_code==200,resp.text
    remaining=next(r for r in view(env,'lab')['items'] if r['source_record_id']=='r1')
    assert remaining['review_state']=='auto_accepted' and 'DUPLICATE_CONFLICT' not in remaining['rule_codes']
    assert c.post('/v1/connectors/lab/verification/publish',headers=h('qa')).status_code==200

def test_mapping_recheck_preserves_cursor(env):
    p,c,h,_=env;cfg,_=connect(env,[row()],confirmed=False);sync(env);before=p.connectors.intake.cursor('T','lims')['checkpoint']
    cfg['mapping_confirmed']=True;r=c.post('/v1/connectors',headers=h(),json=cfg);assert r.status_code==201,r.text
    assert view(env)['items'][0]['review_state']=='auto_accepted'
    assert p.connectors.intake.cursor('T','lims')['checkpoint']==before
    assert sync(env)['ingested']==0 and view(env)['summary']['records']==1

def test_open_collection_does_not_infer_missing_deliveries_or_bad_arrival_order(env):
    connect(env,[row('r1',elapsed_h=2),row('r2',elapsed_h=1,timestamp='2026-10-30T11:00:00Z')]);sync(env);v=view(env)
    assert v['summary']['collection']=='open' and v['summary']['complete'] is False
    assert all(r['review_state']=='auto_accepted' for r in v['items'])
    assert all(not {'TIME_ORDER','EXPECTED_DOCUMENT_MISSING','BATCH_DOCUMENT_MISSING'}.intersection(r['rule_codes']) for r in v['items'])

def test_wide_measurements_use_shared_offset_conversion_and_keep_raw_value(env):
    p,c,h,_=env
    cfg,_=connect(env,[row()])
    cfg['mapping']['fields']=[{'source':name,'canonical':name,'required':True} for name in ('batch_id','elapsed_h')]+[
        {'source':'value','canonical':'temperature','unit':'degC','required':True}]
    cfg['mapping']['ignore_fields']=['test','unit']
    assert c.post('/v1/connectors',headers=h(),json=cfg).status_code==201
    sync(env);record=view(env)['items'][0]
    assert record['review_state']=='auto_accepted'
    m=record['measurements'][0]
    assert m['value_raw']==37 and m['unit_raw']=='degC' and m['value']==pytest.approx(310.15)


def test_missing_context_and_unmapped_payload_are_retained_for_review(env):
    p,c,h,_=env
    raw=row();del raw['batch_id'];raw['unexpected']='retained source detail'
    connect(env,[raw]);sync(env);record=view(env)['items'][0]
    assert record['review_state']=='needs_review'
    assert 'MISSING_FIELD' in record['rule_codes'] and record['unmapped']['unexpected']=='retained source detail'
    body={'record_id':record['id'],'expected_revision':record['revision'],'decision':'accept','reason':'Attempted override'}
    assert c.post('/v1/connectors/lims/verification/review',headers=h('qa'),json=body).status_code==400
    assert c.post('/v1/connectors/lims/verification/publish',headers=h()).status_code==400


def test_duplicate_poll_is_idempotent_and_rejection_revokes_published_basis(env):
    p,c,h,_=env;connect(env,[row()]);sync(env);record=view(env)['items'][0]
    pub=c.post('/v1/connectors/lims/verification/publish',headers=h('qa')).json()
    sync(env);assert view(env)['items'][0]['revision']==record['revision']
    ctx=p.identity.context_for('T','qa');require_dataset(p,ctx,pub['id'],'S1')
    body={'record_id':record['id'],'expected_revision':record['revision'],'decision':'reject','reason':'Source owner withdrew this reading'}
    assert c.post('/v1/connectors/lims/verification/review',headers=h('qa'),json=body).status_code==200
    with pytest.raises((ValueError,PermissionError)):require_dataset(p,ctx,pub['id'],'S1')


def test_source_groups_do_not_mix_same_batch_ids(env):
    connect(env,[row()],cid='a',group='cdmo-a');sync(env,'a')
    connect(env,[row(value=40)],cid='b',group='cdmo-b');sync(env,'b')
    assert view(env,'a')['summary']['records']==1
    assert view(env,'b')['summary']['accepted']==1
    assert all('DUPLICATE_CONFLICT' not in r['rule_codes'] for r in view(env,'a')['items'])

def test_rejected_transport_rows_block_publication_instead_of_disappearing(env):
    _,c,h,_=env
    connect(env,[row(),row('unreadable',timestamp='not-a-time')]);result=sync(env)
    assert result['rejected_records']
    pub=c.post('/v1/connectors/lims/verification/publish',headers=h('qa'))
    assert pub.status_code==400 and 'rejected source rows' in pub.json()['detail']

def test_public_measurement_mapping_rejects_incompatible_target_contract(env):
    from src.lifesci.integrations import ConnectorTemplate, FieldMap
    template=ConnectorTemplate('bad-target','LIMS','lab_result',
        (FieldMap('value','temperature',unit='degC',target_unit='degC'),))
    assert any('shared canonical unit K' in p for p in template.problems())
    ph=ConnectorTemplate('ph','LIMS','lab_result',(FieldMap('value','pH',unit='pH'),))
    assert ph.problems()==[]

def test_nonmeasurement_objects_are_not_forced_into_quantity_vocabulary(env):
    p,c,h,root=env;folder=root/'qms';folder.mkdir()
    payload={'id':'case-1','timestamp':'2026-10-30T12:00:00Z','value':'Requires investigation','status':'open'}
    (folder/'records.json').write_text(json.dumps([payload]))
    cfg={'connector_id':'qms','family':'QMS','transport':'file','site_id':'S1','owner':'admin',
         'mapping_confirmed':True,'options':{'directory':str(folder)},
         'mapping':{'template_id':'quality','system':'QMS','record_type':'quality_record',
                    'fields':[{'source':n,'canonical':n,'required':True} for n in ('value','status')]}}
    assert c.post('/v1/connectors',headers=h(),json=cfg).status_code==201
    sync(env,'qms');record=view(env,'qms')['items'][0]
    assert record['review_state']=='auto_accepted' and record['measurements']==[]
    pub=c.post('/v1/connectors/qms/verification/publish',headers=h())
    assert pub.status_code==200,pub.text
    evidence=p.store.read().require('T','evidence',pub.json()['id'])
    assert evidence.state['metadata']['classification']=='verified_source_dataset'
    assert b'Requires investigation' in p.evidence.original(p.identity.context_for('T','admin'),evidence.id)
