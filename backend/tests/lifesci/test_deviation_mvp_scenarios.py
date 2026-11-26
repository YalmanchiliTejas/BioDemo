"""Provider-free acceptance using original synthetic JSON records and mounted API/runtime."""
import json
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from test_case_science import oxygen_packet

@pytest.fixture
def env(monkeypatch, request):
    import os
    for key in os.environ:
        if 'DATABASE' in key or key.endswith('DB_URL'):
            monkeypatch.setenv(key, '')
    p = Platform(RecordStore(), providers={})
    for actor, role in [('owner','msat'),('qa','qa_reviewer'),('operator','operator'),('admin','admin')]:
        p.identity.assign_role('T',actor,role,site_id=None if actor=='admin' else 'S')
    import sys,time
    from pathlib import Path
    output=os.getenv('DEVIATION_ACCEPTANCE_OUTPUT')
    spans=[];active={};previous=sys.getprofile()
    targets={('EvidenceService','ingest'):'source_ingestion',('QualityEvidence','collect'):'evidence_retrieval',
             ('InvestigationService','snapshot'):'frozen_source_retrieval',('FrozenScience','run'):'deterministic_model_tool',
             ('Runtime','tick'):'runtime_activation'}
    def profile(frame,event,arg):
        self=frame.f_locals.get('self');key=(type(self).__name__,frame.f_code.co_name)
        if key not in targets:return
        if event=='call':active[id(frame)]=time.perf_counter()
        elif event=='return' and id(frame) in active:
            spans.append({'phase':targets[key],'seconds':time.perf_counter()-active.pop(id(frame))})
    started=time.perf_counter()
    if output:sys.setprofile(profile)
    try:yield p, TestClient(create_app(p))
    finally:
        if output:
            sys.setprofile(previous);path=Path(output);path.mkdir(parents=True,exist_ok=True)
            with (path/'timings.jsonl').open('a') as stream:stream.write(json.dumps({'test':request.node.name,'completion_seconds':time.perf_counter()-started,
                'spans':spans,'inference':{'status':'not_run','seconds':None},'measurement_note':'Wall-clock spans may overlap; do not add them as end-to-end latency'})+'\n')
        p.store.release_connections()

def ctx(p, actor='owner'):
    return p.identity.context_for('T',actor)

def ingest(p, rid, fields, *, packet=None, event='2026-11-15T10:00:00Z', system='MES'):
    document={'synthetic':True, 'record':fields, **(packet or {})}
    raw=json.dumps(document,sort_keys=True).encode()
    out=p.evidence.ingest(ctx(p),source_system=system,source_record_id=rid,content=raw,
        media_type='application/json',site_id='S',event_time=event,metadata={'mapped':fields},source_revision='synthetic-'+rid,mapping_version='acceptance-1')
    ref={'kind':'evidence','id':out['evidence_id'],'revision':out['revision'],'site_id':'S'}
    assert p.evidence.original(ctx(p),ref['id'],ref['revision'])==raw
    return ref

def api(client, method, path, body=None, actor='owner', status=200):
    import uuid
    r=client.request(method,'/v1/'+path,headers={'X-Tenant-Id':'T','X-Actor-Id':actor,'Idempotency-Key':str(uuid.uuid4())},json=body)
    assert r.status_code==status, r.text
    return r.json()

def create(client, case='C', refs=(), **extra):
    return api(client,'POST','quality/workspaces',dict(case_id=case,site_id='S',title='Synthetic acceptance '+case,
        owner_id='owner',qa_reviewer_id='qa',associations={'batch_id':'B1'},discovery_refs=list(refs),**extra))

def mutate(client, operation, *, case='C',actor='owner',status=200,**body):
    w=api(client,'GET','quality/workspaces/'+case,actor=actor)
    return api(client,'POST',f'quality/workspaces/{case}/{operation}',dict(expected_revision=w['revision'],**body),actor,status)

def assess(client, case='C'):
    return mutate(client,'assessment',case=case,assessment={'technical_summary':'Observed event; no established root cause',
        'root_cause_status':'unresolved','limitations':['Synthetic inputs; no causal or qualification evidence'],
        'impact':{'status':'assessed','summary':'B1 and equipment-related candidates reviewed; external disposition pending'}})

def review(client, case='C'):
    mutate(client,'transition',case=case,transition='submit_technical',reason='Submit exact evidence basis')
    return mutate(client,'transition',case=case,transition='submit_qa',reason='Human technical assessment complete')

def test_stable_monitoring_baseline_does_not_crash_and_recovery_remains_observable(env,caplog):
    p,_=env
    p.specifications.create(ctx(p,'qa'),site_id='S',parameter='temperature',unit='degC',high=30,reason='Synthetic rule')
    for minute,value in enumerate([20]*9+[31,20]):
        ingest(p,str(minute),{'batch_id':'B1','parameter':'temperature','value':value,'unit':'degC'},event=f'2026-11-15T10:{minute:02d}:00Z')
    signals=p.signals.list(ctx(p))
    assert len(signals)==1 and signals[0]['kind']=='spec_excursion'
    assert len(p.store.read().list('T','spec_series')[0].state['observations'])==11
    assert 'deviation detection failed' not in caplog.text

def test_sourced_oot_is_warning_distinct_from_oos(env):
    p,_=env
    ref=ingest(p,'oot',{'record_type':'lab_result','status':'out_of_trend','batch_id':'B1','test':'purity','value':98.5,'unit':'%','low':98,'high':100},system='LIMS')
    signals=p.signals.list(ctx(p))
    assert len(signals)==1 and signals[0]['kind']=='lab_oot' and signals[0]['severity']=='warning'
    assert signals[0]['evidence_refs'][0]['id']==ref['id']

@pytest.mark.parametrize('source_status',['out_of_trend','within_limits'])
def test_lab_advisory_status_does_not_suppress_local_specification_excursion(env,source_status):
    p,c=env
    spec=p.specifications.create(ctx(p,'qa'),site_id='S',parameter='purity',unit='%',low=98,high=100,
        reason='Synthetic independently configured purity limits')
    ref=ingest(p,'purity-90',{'record_type':'lab_result','status':source_status,'batch_id':'B1',
        'test':'purity','value':90,'unit':'%','low':98,'high':100},system='LIMS')
    signals={s['kind']:s for s in api(c,'GET','signals')['signals']}
    expected={'spec_excursion','lab_oot'} if source_status=='out_of_trend' else {'spec_excursion'}
    assert set(signals)==expected
    excursion=signals['spec_excursion']
    assert excursion['severity']=='action' and excursion['value']==90 and excursion['unit']=='%'
    assert excursion['spec_ref']=={'spec_id':spec['spec_id'],'version':1}
    assert excursion['limit']['low']==98 and excursion['limit']['high']==100
    assert any(r['id']==ref['id'] and r['revision']==1 for r in excursion['evidence_refs'])
    if source_status=='out_of_trend':
        advisory=signals['lab_oot']
        assert advisory['severity']=='warning' and advisory['spec_ref'] is None
        assert advisory['observations'][0]['facts']['status']=='out_of_trend'
        assert any(r['id']==ref['id'] and r['revision']==1 for r in advisory['evidence_refs'])
    assert json.loads(p.evidence.original(ctx(p),ref['id'],1))['record']['status']==source_status


def test_mapped_only_clock_labels_timeline_consistently(env):
    p,c=env
    ref=ingest(p,'mapped-clock',{'batch_id':'B1','event_time':'2026-11-15T09:00:00Z'},event=None)
    create(c,refs=[ref]);w=mutate(c,'prepare')
    assert w['timeline'][0]['event_time']=='2026-11-15T09:00:00Z'
    assert w['timeline'][0]['time_basis']=='source_event_time'
    assert not any(g['code']=='event_time_unknown' for g in w['completeness']['gaps'])

@pytest.mark.parametrize('actor',['operator','admin'])
def test_offered_owner_can_complete_technical_review_or_assignment_is_rejected(env,actor):
    p,c=env
    items=api(c,'GET','quality/workspaces/assignees?site_id=S')['items']
    assert not next(i for i in items if i['actor_id']==actor)['eligible_owner']
    api(c,'POST','quality/workspaces',{'case_id':'BAD','site_id':'S','title':'Cannot finish review','owner_id':actor,'qa_reviewer_id':'qa'},status=400)
    assert p.store.read().get('T','case','BAD') is None

@pytest.mark.parametrize('entry',['signal','signals','generic','generic-list','inbox','mark-read','dismiss'])
def test_source_revocation_hides_signal_and_notification_at_every_entry(env,entry):
    p,c=env
    ref=ingest(p,'oos',{'record_type':'lab_result','status':'out_of_limits','batch_id':'B1','value':90,'unit':'%'})
    signal=p.signals.list(ctx(p))[0];sid=signal['signal_id']
    p.identity.grant('T',grantee_id='limited',resource_kind='deviation_signal',resource_id=sid,actions=['read','propose'],site_id='S')
    grant=p.identity.grant('T',grantee_id='limited',resource_kind='evidence',resource_id=ref['id'],actions=['read'],site_id='S')
    p.alerts._inbox('T','limited',signal)
    p.alerts.notify('T','limited',key='plain',kind='plain',title='Ordinary notice',link='/')
    inbox=p.alerts.inbox(ctx(p,'limited'));iid=next(i['inbox_id'] for i in inbox['items'] if i['signal_id'])
    assert len(inbox['items'])==2
    p.identity.revoke_grant('T',grant)
    if entry=='signal': api(c,'GET',f'signals/{sid}',actor='limited',status=403)
    elif entry=='signals': assert api(c,'GET','signals',actor='limited')['signals']==[]
    elif entry=='generic': api(c,'GET',f'records/deviation_signal/{sid}',actor='limited',status=403)
    elif entry=='generic-list': assert api(c,'GET','records/deviation_signal',actor='limited')['items']==[]
    elif entry=='dismiss': api(c,'POST',f'signals/{sid}/dismiss',{'reason':'Cannot read underlying source'},actor='limited',status=403)
    elif entry=='inbox':
        out=p.alerts.inbox(ctx(p,'limited'))
        assert len(out['items'])==1 and out['items'][0]['title']=='Ordinary notice' and out['unread']==1
    else:
        with pytest.raises(PermissionError):p.alerts.mark_read(ctx(p,'limited'),iid)


def test_export_records_local_package_audit_without_claiming_external_receipt(env):
    p,c=env;ref=ingest(p,'base',{'batch_id':'B1'});create(c,refs=[ref])
    before=api(c,'GET','quality/workspaces/C')['revision']
    package=api(c,'GET','quality/workspaces/C/export',actor='qa')
    exports=p.store.read().list('T','quality_export')
    assert len(exports)==1
    assert exports[0].state['case_id']=='C' and exports[0].state['case_revision']==before
    assert exports[0].state['external_status']=='pending_external_approval'
    assert exports[0].state['source_manifest']==package['source_manifest']
    api(c,'GET',f'records/quality_export/{exports[0].id}',actor='operator',status=404)
    assert p.store.read().audit('T','quality_export',exports[0].id)[0].actor_id=='qa'
    assert package['external_receipt'] is None and api(c,'GET','quality/workspaces/C')['revision']==before

@pytest.mark.parametrize('event,status,expected',[('2026-11-15T12:00:00Z','within_limits',False),('2026-11-15T12:00:00Z','out_of_limits',True),('2026-11-15T09:00:00Z','out_of_limits',False),(None,'out_of_limits',True)])
def test_F_only_adverse_post_action_or_uncertain_events_raise_effectiveness_concern(env,event,status,expected):
    p,c=env;ref=ingest(p,'initial',{'batch_id':'B1','record_type':'lab_result','status':'out_of_limits'})
    create(c,refs=[ref]);mutate(c,'prepare',queued=True);p.runtime.tick()
    w=mutate(c,'actions',action={'description':'Synthetic documented correction','kind':'capa','owner_id':'owner','due_at':'2026-12-01T00:00:00Z'})
    aid=w['actions'][0]['id']
    mutate(c,'actions',action={'id':aid,'status':'completed','completion_refs':[ref],'completed_at':'2026-11-15T11:00:00Z'})
    new=ingest(p,'later',{'batch_id':'B1','record_type':'lab_result','status':status},event=event)
    p.runtime.tick();w=api(c,'GET','quality/workspaces/C')
    concerns=w['workflow']['effectiveness_concerns']
    assert bool(concerns)==expected
    if expected:
        assert concerns[0]['action_id']==aid and new in concerns[0]['evidence_refs']
        assert concerns[0]['timing_status']==('uncertain' if event is None else 'after_action_completion')
    assert w['actions'][0]['effectiveness_status']=='not_assessed'
    record_acceptance('F-'+('unknown' if event is None else event[11:13])+'-'+status,p,c,'C',{'adverse_status':status,'event_time':event,'expected_concern':expected,'inference':'not_run'})


def test_A_complete_excursion_to_handoff_uses_original_rows_and_registered_oxygen_model(env):
    p,c=env
    p.alerts.save_route(ctx(p,'admin'),{'route_id':'responsible','site_id':'S','min_severity':'action','roles':['msat'],'channels':['in_app'],'enabled':True})
    p.specifications.create(ctx(p,'qa'),site_id='S',parameter='dissolved_oxygen',unit='mg/L',low=3,
        duration_seconds=120,max_observation_gap_seconds=90,reason='Synthetic approved absolute DO excursion rule')
    refs=[]
    for minute,value in enumerate([4,3.5,2.5,2.2,2]):
        fields={'batch_id':'B1','equipment_id':'E1','product_id':'P1','parameter':'dissolved_oxygen','value':value,'unit':'mg/L','event_time':f'2026-11-15T10:{minute:02d}:00Z'}
        refs.append(ingest(p,f'do-{minute}',fields,event=fields['event_time'],packet=oxygen_packet() if minute==4 else None,system='HISTORIAN'))
    signal=p.signals.list(ctx(p))[0]
    assert signal['kind']=='spec_excursion' and signal['limit']['duration_seconds']==120
    assert signal['rule_version'] and signal['spec_ref']['version']==1
    assert len(signal['observations'])==3
    for observation in signal['observations']:
        ref=observation['evidence_ref'];row=json.loads(p.evidence.original(ctx(p),ref['id'],ref['revision']))['record']
        assert row['value']==observation['value'] and row['unit']==observation['unit']
        assert observation['original_event_time']==row['event_time']
    assert any(i['signal_id']==signal['signal_id'] for i in p.alerts.inbox(ctx(p))['items'])
    assert p.store.read().list('T','case')==[]
    related=ingest(p,'related-batch',{'batch_id':'B2','equipment_id':'E1','product_id':'P1','status':'within_limits','distribution_status':'not_released'})
    sref={'kind':'deviation_signal','id':signal['signal_id'],'revision':signal['revision'],'site_id':'S'}
    w=api(c,'POST','quality/workspaces',{'case_id':'A','site_id':'S','title':'Synthetic DO event','owner_id':'owner','qa_reviewer_id':'qa','associations':{'batch_id':'B1','equipment_id':'E1'},'discovery_refs':[sref]})
    mutate(c,'transition',case='A',transition='assign',reason='Engineer explicitly begins local preparation')
    mutate(c,'prepare',case='A',queued=True);p.runtime.tick()
    w=api(c,'GET','quality/workspaces/A')
    assert w['workflow']['preparation']['status']=='completed'
    assert any(v['identifiers'].get('batch_id')=='B2' for v in w['impact']['candidates'])
    mutate(c,'science/analyze',case='A',queued=True);p.runtime.tick();w=api(c,'GET','quality/workspaces/A')
    run=w['science']['model_runs'][0]
    assert run['comparison'][0]['predicted']==pytest.approx(100) and run['comparison'][0]['observed']==95
    assert run['output']['scenarios'][1]['our_margin_mg_l_h']==pytest.approx(60)
    assert run['source_refs']==[refs[-1]] and run['model']['implementation_digest']
    assess(c,'A')
    mutate(c,'actions',case='A',action={'description':'Investigate DO sensor and oxygen balance under approved change process','kind':'corrective_action','owner_id':'owner','due_at':'2026-12-01T00:00:00Z','rationale':'Positive calculated OTR margin does not establish declining DO cause'})
    review(c,'A');w=mutate(c,'transition',case='A',actor='qa',transition='approve_local',reason='Complete local package reviewed; external approval pending')
    assert w['workflow']['state']=='handoff_pending'
    package=api(c,'GET','quality/workspaces/A/export',actor='qa')
    assert package['external_receipt'] is None and package['external_status']=='pending_external_approval'
    assert len(package['source_records'])==len(package['source_manifest'])
    assert any(s['ref']==refs[-1] and json.loads(s['content_text'])['scientific_models'] for s in package['source_records'])
    record_acceptance('A',p,c,'A',{'signal':signal,'conditional_otr':100,'observed_otr':95,'our_margin':60,'inference':'not_run'})


def test_B_original_oos_survives_lab_review_and_expanded_manufacturing_investigation(env):
    p,c=env
    original=ingest(p,'OOS-1',{'record_type':'lab_result','status':'out_of_limits','test':'purity','value':94.2,'unit':'%','low':98,'high':100,'batch_id':'B1','sample_id':'SAMPLE1'},system='LIMS')
    original_bytes=p.evidence.original(ctx(p),original['id'],1)
    signal=p.signals.list(ctx(p))[0];assert signal['kind']=='lab_oos'
    create(c,refs=[original],category='oos');mutate(c,'transition',transition='assign',reason='Human opens OOS investigation')
    mutate(c,'prepare',queued=True);p.runtime.tick()
    assert 'initial_lab_assessment' in api(c,'GET','quality/workspaces/C')['completeness']['missing']
    mutate(c,'assessment',assessment={'initial_lab_assessment':{'conclusion':'expanded_investigation','rationale':'Initial review has no supported assignable lab error; manufacturing context required','evidence_refs':[original]}})
    manufacturing=ingest(p,'batch-execution',{'batch_id':'B1','record_type':'batch_record','equipment_id':'E1','status':'completed','temperature_max_c':31.2})
    p.runtime.tick();w=api(c,'GET','quality/workspaces/C');assert manufacturing in w['workflow']['sources']
    assess(c);w=review(c)
    assert w['workflow']['state']=='qa_review' and w['assessment']['initial_lab_assessment']['original_oos_preserved']
    assert p.evidence.original(ctx(p),original['id'],1)==original_bytes
    assert json.loads(original_bytes)['record']['status']=='out_of_limits'
    record_acceptance('B',p,c,'C',{'original_oos':original,'manufacturing':manufacturing,'inference':'not_run'})


def test_C_distinct_yield_batches_have_advisory_screening_and_clear_no_deviation_outcome(env):
    p,c=env
    p.specifications.create(ctx(p,'qa'),site_id='S',parameter='yield',unit='%',low=70,product_id='P1',reason='Synthetic baseline rule',cross_batch_trend={'baseline':[94,95,96],'window_batches':3,'minimum_drop':5})
    for index,value in enumerate([89,87,85]):
        ingest(p,f'yield-{index}',{'batch_id':f'Y{index}','product_id':'P1','parameter':'yield','value':value,'unit':'%','observation_type':'batch_summary'},event=f'2026-11-{12+index}T10:00:00Z')
    signal=p.signals.list(ctx(p))[0]
    assert signal['kind']=='trend' and signal['severity']=='warning' and len(signal['observations'])==3
    assert p.store.read().list('T','case')==[]
    # A local assessment workspace is explicitly chosen by a person. It is not an automatic formal deviation.
    ref={'kind':'deviation_signal','id':signal['signal_id'],'revision':signal['revision'],'site_id':'S'}
    create(c,refs=[ref],category='risk_assessment');mutate(c,'prepare',queued=True);p.runtime.tick()
    mutate(c,'science/analyze',queued=True);p.runtime.tick();w=api(c,'GET','quality/workspaces/C')
    assert w['science']['advisory'] and w['science']['status']=='waiting_for_configuration'
    w=mutate(c,'transition',transition='no_formal_deviation',reason='Engineer retains trend follow-up; no formal escalation based on this limited synthetic series')
    assert w['workflow']['state']=='assessed_no_formal_deviation'
    assert 'submit_technical' not in w['allowed_actions'] and 'assign' in w['allowed_actions']
    package=api(c,'GET','quality/workspaces/C/export')
    assert package['external_status']=='not_requested' and 'No formal deviation' in package['label']
    record_acceptance('C',p,c,'C',{'signal':signal,'inference':'not_run','scientific_screening':'No source-supplied model configuration; explicitly withheld'})


def test_D_E_missing_calibration_resumes_and_QA_return_keeps_exact_old_submission(env):
    p,c=env
    original=ingest(p,'impact',{'batch_id':'B1','equipment_id':'E1','distribution_status':'unknown'})
    create(c,refs=[original]);mutate(c,'transition',transition='assign',reason='Investigate event')
    mutate(c,'prepare',queued=True);p.runtime.tick()
    w=mutate(c,'evidence-requests',request={'description':'Calibration certificate for E1','owner_id':'owner','required':True});rid=w['requests'][0]['id']
    review(c);first=deepcopy(api(c,'GET','quality/workspaces/C')['reviews'][0])
    blocked=mutate(c,'transition',actor='qa',transition='approve_local',reason='Check complete basis',status=400)
    assert 'incomplete' in str(blocked)
    mutate(c,'transition',actor='qa',transition='return',reason='Provide calibration and distribution assessment')
    old_reviews=deepcopy(api(c,'GET','quality/workspaces/C')['reviews'])
    calibration=ingest(p,'calibration',{'batch_id':'B1','equipment_id':'E1','record_type':'calibration','status':'confirmed','certificate_id':'SYN-CAL-1','calibrated_at':'2026-11-14T12:00:00Z'},event='2026-11-15T11:00:00Z')
    correction=ingest(p,'impact',{'batch_id':'B1','equipment_id':'E1','distribution_status':'not_released'},event='2026-11-15T11:01:00Z')
    p.runtime.tick();w=api(c,'GET','quality/workspaces/C')
    assert calibration in w['workflow']['sources'] and correction in w['workflow']['sources']
    assert w['reviews']==old_reviews and w['reviews'][0]==first
    mutate(c,'evidence-requests',request={'id':rid,'status':'resolved','evidence_refs':[calibration]})
    assess(c);review(c);w=mutate(c,'transition',actor='qa',transition='approve_local',reason='Current complete submission accepted locally')
    submissions=[r for r in w['reviews'] if r['decision']=='submitted']
    assert len(submissions)==2 and submissions[0]==first
    assert original in submissions[0]['snapshot']['sources'] and correction in submissions[1]['snapshot']['sources']
    assert w['reviews'][-1]['submission_id']==submissions[1]['id']
    package=api(c,'GET','quality/workspaces/C/export',actor='qa')
    assert original in package['source_manifest'] and correction in package['source_manifest']
    assert 'unknown' in api(c,'GET',f"quality/workspaces/C/evidence/evidence/{original['id']}?revision=1")['content_text']
    record_acceptance('D_E',p,c,'C',{'request_id':rid,'original_submission_id':first['id'],'current_submission_id':submissions[1]['id'],'inference':'not_run'})


def test_same_source_correction_retains_signal_history_and_resumes_science_current_basis(env):
    p,c=env
    p.specifications.create(ctx(p,'qa'),site_id='S',parameter='dissolved_oxygen',unit='mg/L',low=3,reason='Synthetic correction test')
    fields={'batch_id':'B1','parameter':'dissolved_oxygen','value':2,'unit':'mg/L'}
    first=ingest(p,'oxygen',fields,packet=oxygen_packet());signal=p.signals.list(ctx(p))[0]
    sref={'kind':'deviation_signal','id':signal['signal_id'],'revision':signal['revision'],'site_id':'S'}
    create(c,refs=[sref,first]);mutate(c,'transition',transition='assign',reason='Assess correction');mutate(c,'prepare',queued=True);p.runtime.tick()
    mutate(c,'science/analyze',queued=True);p.runtime.tick();w=api(c,'GET','quality/workspaces/C')
    old_run=deepcopy(w['science']['model_runs'][0]);assert old_run['status']=='completed'
    assess(c);review(c);submission=deepcopy(api(c,'GET','quality/workspaces/C')['reviews'][0])
    document=oxygen_packet();document['scientific_models'][0]['observations'][0]['value']=96
    corrected=ingest(p,'oxygen',fields,packet=document)
    current_signal=p.signals.list(ctx(p))[0]
    assert {r['revision'] for r in current_signal['evidence_refs']}=={1,2}
    p.runtime.tick();w=api(c,'GET','quality/workspaces/C')
    assert w['reviews'][0]==submission and w['science']['model_runs'][0]==old_run
    mutate(c,'transition',actor='qa',transition='return',reason='Reassess corrected original observation')
    p.runtime.tick();w=api(c,'GET','quality/workspaces/C')
    assert w['science']['status']=='ready_for_assessment'
    assert w['science']['model_runs'][0]['source_refs']==[corrected]
    assert w['science']['model_runs'][0]['comparison'][0]['observed']==96
    assert w['reviews'][0]==submission
    assert json.loads(p.evidence.original(ctx(p),first['id'],1))['scientific_models'][0]['observations'][0]['value']==95
    record_acceptance('correction',p,c,'C',{'original':first,'corrected':corrected,'preserved_submission':submission['id'],'inference':'not_run'})


def record_acceptance(name,p,c,case,details):
    import os
    from pathlib import Path
    output=os.getenv('DEVIATION_ACCEPTANCE_OUTPUT')
    if not output:return
    path=Path(output);path.mkdir(parents=True,exist_ok=True)
    workspace=api(c,'GET','quality/workspaces/'+case)
    package=api(c,'GET',f'quality/workspaces/{case}/export',actor='qa')
    (path/(name+'.json')).write_text(json.dumps({'scenario':name,'proof_mode':'mounted API + actual source services + runtime + registered deterministic models when configured',
        'details':details,'workspace':workspace,'package':package},indent=2))


def test_legacy_ineligible_owner_is_explicit_and_current_owner_revocation_blocks_completion(env):
    p,c=env
    p.cases.open(ctx(p),'LEG','operator','qa','S')
    adoption=api(c,'GET','quality/workspaces/LEG/adoption-context')
    assert 'operator' in adoption['assignment_issues'][0]
    assert 'technical-review approval' in adoption['assignment_issues'][0]
    ref=ingest(p,'base',{'batch_id':'B1'});create(c,refs=[ref]);mutate(c,'transition',transition='assign',reason='Investigate')
    mutate(c,'prepare');assess(c);review(c)
    p.identity.revoke_role('T','owner','msat',site_id='S')
    w=api(c,'GET','quality/workspaces/C',actor='qa')
    assert 'owner_authority' in w['completeness']['missing']
    mutate(c,'transition',actor='qa',transition='approve_local',reason='Must not approve with revoked owner',status=400)


def test_signal_adoption_deduplicates_identical_refs_without_losing_revisions(env):
    p,c=env
    first=ingest(p,'adoption-oos',{'record_type':'lab_result','status':'out_of_limits','batch_id':'B1'})
    signal=p.signals.list(ctx(p))[0]
    p.signals.open_case(ctx(p),signal['signal_id'],owner_id='owner',qa_reviewer_id='qa',case_id='ADOPT')
    basis=api(c,'GET','quality/workspaces/ADOPT/adoption-context')
    keys=[(r['kind'],r['id'],r['revision']) for r in basis['discovery_refs']]
    assert len(keys)==len(set(keys))
    corrected=ingest(p,'adoption-oos',{'record_type':'lab_result','status':'out_of_limits','batch_id':'B1','correction':'changed source note'})
    basis=api(c,'GET','quality/workspaces/ADOPT/adoption-context')
    basis['discovery_refs'].extend([corrected,corrected])
    w=api(c,'POST','quality/workspaces',{'case_id':'ADOPT','expected_case_revision':basis['case']['revision'],'site_id':'S','title':'Adopt actual signal','owner_id':'owner','qa_reviewer_id':'qa','discovery_refs':basis['discovery_refs']})
    assert len(w['sources'])==3
    assert {r['ref']['revision'] for r in w['sources'] if r['ref']['id']==first['id']}=={1,2}


def test_constant_baseline_can_be_reassessed_without_inventing_statistical_support():
    from src.lifesci.science import detect_emerging_concern, update_recommendation_basis
    initial=detect_emerging_concern([20]*10,(None,30))
    preserved=deepcopy(initial)
    updated=update_recommendation_basis(initial,[20]*10+[31])
    assert initial==preserved and initial['result']['status']=='insufficient_baseline_variation'
    assert updated['result']['recommendation_status']=='superseded_by_out_of_spec_deviation_process'
    assert updated['result']['basis_changed']
    assert updated['result']['new_analysis']['out_of_spec_indices']==[10]
