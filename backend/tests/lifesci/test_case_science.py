"""Synthetic, provider-free scientific work through the ordinary case and Prime paths."""
import io
import json
import math
import zipfile
import pytest
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore, ConflictError

@pytest.fixture
def env(monkeypatch):
    for key in ('DATABASE_URL','LIFESCI_DATABASE_URL','CMO_DATABASE_URL','CMO_TEST_DATABASE_URL'):
        monkeypatch.setenv(key, '')
    monkeypatch.delenv('INVESTIGATION_EXECUTOR', raising=False)
    p = Platform(RecordStore(), providers={})
    for actor, role in [('owner','msat'),('qa','qa_reviewer')]:
        p.identity.assign_role('T',actor,role,site_id='S')
    return p, p.identity.context_for('T','owner'), p.identity.context_for('T','qa')

def packet():
    # No reaction/feed: the existing energy solver must reproduce exponential cooling.
    config = dict(reference_temperature_k=300., product_rate_ref_s_inv=0., impurity_rate_ref_s_inv=0.,
        product_activation_j_mol=0., impurity_activation_j_mol=0., product_enthalpy_j_mol=0., impurity_enthalpy_j_mol=0.,
        density_kg_m3=1000., heat_capacity_j_kg_k=4000., initial_volume_m3=1., maximum_volume_m3=2.,
        initial_a_mol_m3=1., initial_temperature_k=320., heat_transfer_area_m2=10., heat_transfer_coefficient_w_m2_k=100.,
        coolant_temperature_k=300., feed_flow_m3_s=0., feed_a_mol_m3=0., feed_temperature_k=300., feed_until_s=0.,
        temperature_limit_k=350., duration_s=4000., evidence_classification='synthetic_assumption', source_refs=['synthetic calorimetry'])
    return {'scientific_models':[{'id':'cooling','model_id':'chemical.semi_batch','config':config,
        'assumptions':['Constant heat capacity and prescribed coolant; synthetic inputs'],
        'uncertainty':['No calibrated prediction interval'],
        'observations':[{'observable':'temperature_k','coordinate':4000.,'value':307.5,'unit':'K'}]}]}

def setup(p, ctx, document=None):
    out=p.evidence.ingest(ctx,source_system='synthetic',source_record_id='thermal',content=json.dumps(document or packet()).encode(),
        media_type='application/json',site_id='S',event_time=None)
    ref={'kind':'evidence','id':out['evidence_id'],'revision':out['revision'],'site_id':'S'}
    w=p.quality_workflow.create(ctx,case_id='C',site_id='S',title='Synthetic heat excursion',owner_id='owner',qa_reviewer_id='qa',
        discovery_refs=[ref],idempotency_key='create')
    return ref,w

def test_case_runs_existing_heat_solver_and_persists_comparison_idempotently(env):
    p,ctx,_=env
    ref,w=setup(p,ctx)
    result=p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='science')
    science=result['workflow']['science']
    run=science['model_runs'][0]
    assert run['status']=='completed'
    assert run['comparison'][0]['predicted']==pytest.approx(300+20/math.e,rel=1e-7)
    assert run['comparison'][0]['observed']==307.5
    assert run['comparison'][0]['unit']=='K'
    assert run['source_refs']==[ref]
    assert run['model']['implementation_digest']
    assert science['assessment']['root_cause_status']=='unresolved'
    assert science['advisory'] is True
    assert p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='science')['revision']==result['revision']
    assert len(p.store.read().list('T','physical_analysis_result'))==1

def test_missing_inputs_and_percent_do_are_withheld(env):
    p,ctx,_=env
    doc=packet(); del doc['scientific_models'][0]['config']['heat_capacity_j_kg_k']
    ref,w=setup(p,ctx,doc)
    result=p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='missing')
    run=result['workflow']['science']['model_runs'][0]
    assert run['status']=='withheld' and 'heat_capacity' in str(run['missing_inputs'])
    assert not run.get('comparison')
    from src.prime_runtime.science import FrozenScience
    doc=packet(); doc['scientific_models'][0]['observations'][0]['unit']='%'
    frozen=FrozenScience.from_documents([(ref,doc)])
    run=frozen.run('cooling')
    assert run['status']=='withheld' and 'unit' in str(run['issues']).lower()

def test_manifest_pins_sources_and_ordinary_tools_are_discoverable(env,tmp_path):
    p,ctx,_=env;ref,w=setup(p,ctx)
    data,meta=p.investigations.snapshot(ctx,site_id='S',case_ids=['C'])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest=json.loads(z.read('snapshot-manifest.json'))
        assert any(i['id']==ref['id'] for i in manifest['items'])
    from src.prime_runtime.science import FrozenScience
    frozen=FrozenScience.from_package(data)
    assert frozen.tools()['scientific_model_run'](configuration_id='cooling')['status']=='completed'
    assert frozen.catalog()['configurations'][0]['id']=='cooling'
    with pytest.raises((ValueError,ConflictError)):
        p.investigations.snapshot(ctx,site_id='S',record_refs=[{**ref,'revision':999}])
    from src.manufacturing_data import ManufacturingStore
    from src.state import BlackboardStore
    from src.workflows import ManufacturingInvestigationWorkflow
    from src.prime_runtime.bridge import ManufacturingBridge
    store=ManufacturingStore(tmp_path/'store'); boards=BlackboardStore(tmp_path/'boards')
    flow=ManufacturingInvestigationWorkflow(tmp_path/'flow',store,scope='S',blackboards=boards)
    bridge=ManufacturingBridge(store=store,blackboards=boards,workflow=flow,scope='S',incident_id='test',objective='heat',
        as_of='2026-11-15T00:00:00+00:00',seed_ids=[],additional_tools=frozen.tools())
    assert 'scientific_model_run' in bridge.context()['tool_names']
    assert bridge.context()['additional_tool_contracts']['scientific_model_run']['required']==['configuration_id']
    assert bridge.tool('scientific_model_run',{'configuration_id':'cooling'})['status']=='completed'

def test_science_review_lock_and_snapshot_immutability(env):
    p,ctx,qa=env;ref,w=setup(p,ctx)
    w=p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='s')
    before=w['workflow']['science']
    w=p.quality_workflow.transition(ctx,'C',transition='submit_technical',reason='Inspect',expected_revision=w['revision'],idempotency_key='submit')
    with pytest.raises(ValueError,match='return'):
        p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='blocked')
    assert p.quality_workflow.get(ctx,'C')['workflow']['science']==before


def test_source_refresh_marks_scientific_draft_stale_and_keeps_review(env):
    p,ctx,qa=env;ref,w=setup(p,ctx)
    w=p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='science')
    w=p.quality_workflow.transition(ctx,'C',transition='submit_technical',reason='Inspect',expected_revision=w['revision'],idempotency_key='submit')
    reviewed=w['workflow']['reviews'][0]
    w=p.quality_workflow.transition(qa,'C',transition='return',reason='Correct source',expected_revision=w['revision'],idempotency_key='return')
    document=packet();document['scientific_models'][0]['config']['heat_capacity_j_kg_k']=4100.
    p.evidence.ingest(ctx,source_system='synthetic',source_record_id='thermal',content=json.dumps(document).encode(),media_type='application/json',site_id='S',event_time=None)
    w=p.quality_workflow.prepare(ctx,'C',expected_revision=w['revision'],idempotency_key='refresh')
    assert w['workflow']['science']['status']=='stale_requires_rerun'
    assert w['workflow']['reviews'][0]==reviewed


def test_scientific_api_is_direct_and_list_compatibility(env):
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    p,ctx,_=env;ref,w=setup(p,ctx)
    client=TestClient(create_app(p));headers={'X-Tenant-Id':'T','X-Actor-Id':'owner'}
    catalog=client.get('/v1/quality/workspaces/C/science/catalog',headers=headers)
    assert catalog.status_code==200 and catalog.json()['configurations'][0]['id']=='cooling'
    response=client.post('/v1/quality/workspaces/C/science/analyze',headers={**headers,'Idempotency-Key':'direct'},json={'expected_revision':w['revision']})
    assert response.status_code==200 and response.json()['science']['model_runs'][0]['status']=='completed'
    response=client.get('/v1/investigation-runs',headers=headers)
    assert response.json()['items']==response.json()['runs']


def test_queued_science_runs_on_existing_runtime_and_resumes_source_change(env):
    p,ctx,_=env;ref,w=setup(p,ctx)
    w=p.case_science.queue(ctx,'C',expected_revision=w['revision'],idempotency_key='queued')
    assert w['science']['status']=='queued'
    assert not p.store.read().list('T','physical_analysis_result')
    p.runtime.track('T');p.runtime.tick()
    w=p.quality_workflow.get(ctx,'C')
    assert w['science']['model_runs'][0]['status']=='completed'
    first=w['science']['model_runs'][0]['result_ref']
    assert p.missions.get(ctx,w['workflow']['mission_id'])['obligations'][-1]['status']=='done'
    document=packet();document['scientific_models'][0]['config']['heat_capacity_j_kg_k']=4100.
    p.evidence.ingest(ctx,source_system='synthetic',source_record_id='thermal',content=json.dumps(document).encode(),media_type='application/json',site_id='S',event_time=None)
    p.runtime.tick()
    w=p.quality_workflow.get(ctx,'C')
    assert w['science']['model_runs'][0]['source_refs'][0]['revision']==2
    assert w['science']['model_runs'][0]['result_ref']!=first
    count=len(p.store.read().list('T','physical_analysis_result'))
    p.runtime.tick()
    assert len(p.store.read().list('T','physical_analysis_result'))==count


def test_reviewed_science_is_preserved_on_source_arrival_until_human_return(env):
    p,ctx,qa=env;ref,w=setup(p,ctx)
    w=p.case_science.queue(ctx,'C',expected_revision=w['revision'],idempotency_key='q')
    p.runtime.tick();w=p.quality_workflow.get(ctx,'C')
    w=p.quality_workflow.transition(ctx,'C',transition='submit_technical',reason='Review',expected_revision=w['revision'],idempotency_key='submit')
    saved=w['science']
    document=packet();document['scientific_models'][0]['config']['heat_capacity_j_kg_k']=4100.
    p.evidence.ingest(ctx,source_system='synthetic',source_record_id='thermal',content=json.dumps(document).encode(),media_type='application/json',site_id='S',event_time=None)
    p.runtime.tick();w=p.quality_workflow.get(ctx,'C')
    assert w['science']==saved
    assert w['workflow']['scientific_refresh']['status']=='pending_review_return'
    w=p.quality_workflow.transition(qa,'C',transition='return',reason='Refresh',expected_revision=w['revision'],idempotency_key='return')
    assert w['science']['status']=='stale_requires_rerun'
    p.runtime.tick();w=p.quality_workflow.get(ctx,'C')
    assert w['science']['status']=='ready_for_assessment'
    assert w['science']['model_runs'][0]['source_refs'][0]['revision']==2


def test_queued_no_configuration_is_visible_waiting_not_success(env):
    p,ctx,_=env;ref,w=setup(p,ctx,{'evidence_classification':'synthetic_assumption','note':'No model inputs'})
    w=p.case_science.queue(ctx,'C',expected_revision=w['revision'],idempotency_key='q')
    p.runtime.tick();w=p.quality_workflow.get(ctx,'C')
    assert w['science']['status']=='waiting_for_configuration'
    assert w['science']['unknowns']
    assert not w['science']['model_runs']
    assert p.missions.get(ctx,w['workflow']['mission_id'])['obligations'][-1]['runtime_status']=='blocked'


@pytest.mark.parametrize('execution_path',['local','cloud'])
@pytest.mark.parametrize('configuration',['cooling','oxygen_mixed'])
def test_ordinary_executor_registers_and_invokes_snapshot_model_tools(env,tmp_path,monkeypatch,execution_path,configuration):
    from src.prime_runtime.harness import PrimeManufacturingHarness
    p,ctx,_=env;ref,w=setup(p,ctx,oxygen_packet() if configuration=='oxygen_mixed' else packet())
    extra=[]
    if configuration=='oxygen_mixed':
        content=json.dumps([{'parameter':'DO','value':20.,'unit':'%','classification':'synthetic observation only'}]).encode()
        ordinary=p.evidence.ingest(ctx,source_system='synthetic',source_record_id='observation-array',content=content,
            media_type='application/json',site_id='S',event_time=None)
        extra=[{'kind':'evidence','id':ordinary['evidence_id'],'revision':ordinary['revision'],'site_id':'S'}]
    data,meta=p.investigations.snapshot(ctx,site_id='S',case_ids=['C'],record_refs=extra)
    if extra:
        from src.prime_runtime.science import FrozenScience
        array_item=next(i for i in meta['items'] if i['id']==extra[0]['id'])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert archive.read(array_item['path'])==content
        frozen=FrozenScience.from_package(data)
        assert [c['id'] for c in frozen.catalog()['configurations']]==['oxygen']
        assert frozen.run('oxygen')['comparison'][0]['predicted']==pytest.approx(100.)
    seen={}
    class ProbeHarness:
        def __init__(self,store): self.additional_tools={};self.store=store
        def run(self,**kwargs):
            catalog=self.additional_tools['scientific_model_catalog']()
            seen['models']=catalog['models']
            result=self.additional_tools['scientific_model_run'](configuration_id='oxygen' if extra else 'cooling')
            assert result['status']=='completed'
            if extra:
                assert result['comparison'][0]['predicted']==pytest.approx(100.)
                assert any(source['path']==array_item['path'] for source in self.store.visible_sources(scopes=('investigation',)))
            # Actual ingestion row is mapped to the original frozen platform source.
            rows=self.store.visible(scopes=('investigation',),limit=1000)
            cited=next(r['id'] for r in rows if r['source_ref']['path'].startswith('evidence/'))
            return {'hypotheses':[{'supporting_evidence_ids':[cited]}]}
    monkeypatch.setattr(PrimeManufacturingHarness,'from_env',classmethod(lambda cls,**kw:ProbeHarness(kw['store'])))
    if execution_path=='local':
        import threading
        from src.lifesci.local_executor import LocalExecutor
        executor=LocalExecutor(tmp_path/'exec');executor.upload('p',meta['sha256'],data)
        executor._job_dir('job').mkdir(parents=True,exist_ok=True)
        result=executor._run_prime('job',{'sha256':meta['sha256'],'objective':'Synthetic thermal screen','as_of':'2026-11-15T00:00:00+00:00'},lambda e:None,threading.Event(),{})
    else:
        import time
        from src.cloud_backend import agent,crypto
        class Response(io.BytesIO):
            status=200
        output=[]
        def fake_urlopen(request,timeout):
            if isinstance(request,str): return Response(data)
            output.append(json.loads(request.data));return Response(b'')
        monkeypatch.setattr(agent,'urlopen',fake_urlopen)
        monkeypatch.setattr(crypto,'unseal',lambda *args:data)
        monkeypatch.setattr(crypto,'seal',lambda key,path,body:body)
        monkeypatch.setattr(agent,'_EMITTER',None)
        agent.execute({'input_url':'unused-local-input','input_key':'','input_path':'input','sha256':meta['sha256'],
            'scope':'investigation','deadline':time.time()+600,'max_tool_calls':30,'objective':'Synthetic thermal screen',
            'id':'job','as_of':'2026-11-15T00:00:00+00:00','version_id':'v1','output_key':'','output_path':'out','output_url':'https://unused.local/output'},tmp_path)
        result=output[0]['report']
    assert seen['models']
    assert result['scientific_model_runs'][0]['output']['model_id']==('fermentation.pressure_cost' if extra else 'chemical.semi_batch')
    assert next(iter(result['snapshot_citation_map'].values()))['path'].startswith('evidence/')


def test_changed_source_during_solver_cannot_persist_result(env,monkeypatch):
    from src.prime_runtime.science import FrozenScience
    p,ctx,_=env;ref,w=setup(p,ctx)
    original=FrozenScience.run
    def corrected(self,configuration_id):
        result=original(self,configuration_id)
        document=packet();document['scientific_models'][0]['config']['heat_capacity_j_kg_k']=4100.
        p.evidence.ingest(ctx,source_system='synthetic',source_record_id='thermal',content=json.dumps(document).encode(),media_type='application/json',site_id='S',event_time=None)
        return result
    monkeypatch.setattr(FrozenScience,'run',corrected)
    with pytest.raises((ValueError,ConflictError)):
        p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='racing')
    assert not p.store.read().list('T','physical_analysis_result')
    assert not p.quality_workflow.get(ctx,'C')['science']


def test_do_percent_never_uses_fermentation_scenario_defaults(env):
    from src.prime_runtime.science import FrozenScience
    p,ctx,_=env;ref,w=setup(p,ctx)
    frozen=FrozenScience.from_documents([(ref,{'scientific_models':[{'id':'do','model_id':'fermentation.pressure_cost',
        'config':{'project':{'id':'pichia'},'observations':[{'value':20.,'unit':'%'}]},
        'assumptions':[],'uncertainty':['Saturation and calibration absent']} ]})])
    result=frozen.run('do')
    assert result['status']=='withheld' and 'defaults' in str(result['issues'])
    assert 'output' not in result and 'comparison' not in result


def test_duplicate_pinned_reference_cannot_hide_revision_mismatch(env):
    p,ctx,_=env;ref,w=setup(p,ctx)
    with pytest.raises((ValueError,ConflictError)):
        p.investigations.snapshot(ctx,site_id='S',record_refs=[ref,{**ref,'revision':999}])


def test_owner_delegate_runs_advisory_science_and_unrelated_delegate_is_denied(env):
    from src.lifesci.roles import agent_context_for
    p,ctx,_=env;ref,w=setup(p,ctx)
    delegated=agent_context_for(ctx,p.identity)
    out=p.case_science.analyze(delegated,'C',expected_revision=w['revision'],idempotency_key='delegate')
    assert out['science']['advisory'] is True
    assert out['science']['model_runs'][0]['status']=='completed'
    qa=p.identity.context_for('T','qa')
    with pytest.raises(PermissionError):
        p.case_science.analyze(agent_context_for(qa,p.identity),'C',expected_revision=out['revision'],idempotency_key='wrong')


def oxygen_packet():
    # At 150 kPa absolute and declared baseline pressure, kLa=10/h and C*=8*1.5=12 mg/L.
    # OTR=10*(12-2)=100 mg/(L h); source observation is 95 mg/(L h).
    return {'scientific_models':[{'id':'oxygen','model_id':'fermentation.pressure_cost',
        'config':{'evidence_classification':'synthetic_assumption','source_refs':['synthetic oxygen characterization'],
                  'assumptions':{'gas_exponent':.5,'pressure_gauge_kpa':50.,'ambient_kpa':100.,'air_nm3_h':36.,
                    'oxygen_nm3_h':0.,'compressor_efficiency':.65,'compressor_inlet_temperature_k':300.,
                    'electricity_usd_kwh':0.,'oxygen_usd_nm3':0.,'air_saturation_mg_l':8.,'broth_solubility_factor':1.,
                    'kla_h_inv':10.,'dissolved_oxygen_mg_l':2.,'our_mg_l_h':40.,'kla_baseline_pressure_gauge_kpa':50.}},
        'assumptions':['Synthetic uniform-DO conditional calculation; kLa measured at declared 50 kPa gauge baseline'],
        'uncertainty':['No calibrated prediction interval; saturation and broth correction are synthetic'],
        'observations':[{'observable':'scenarios.1.otr_mg_l_h','coordinate':0.,'value':95.,'unit':'mg/(L h)'}]}]}


def test_queued_source_complete_oxygen_executes_registered_solver_and_compares(env):
    p,ctx,_=env;ref,w=setup(p,ctx,oxygen_packet())
    w=p.case_science.queue(ctx,'C',expected_revision=w['revision'],idempotency_key='oxygen')
    p.runtime.tick();w=p.quality_workflow.get(ctx,'C')
    run=w['science']['model_runs'][0]
    assert run['status']=='completed'
    assert run['comparison'][0]['predicted']==pytest.approx(100.)
    assert run['comparison'][0]['observed']==95. and run['comparison'][0]['residual']==pytest.approx(-5.)
    assert run['output']['scenarios'][1]['our_margin_mg_l_h']==pytest.approx(60.)
    assert run['source_refs']==[ref]
    assert run['model']['id']=='fermentation.pressure_cost'
    assert run['model']['implementation_digest']
    assert w['science']['assessment']['root_cause_status']=='unresolved'
    assert p.evidence.read_derived(ctx,'physical_analysis_result',run['result_ref']['id'])['inputs']==[ref]


@pytest.mark.parametrize('problem',['missing_absolute_do','percent_observation','missing_baseline'])
def test_oxygen_missing_or_unit_incompatible_inputs_are_withheld(env,problem):
    p,ctx,_=env;document=oxygen_packet();entry=document['scientific_models'][0]
    if problem=='missing_absolute_do': del entry['config']['assumptions']['dissolved_oxygen_mg_l']
    elif problem=='missing_baseline': del entry['config']['assumptions']['kla_baseline_pressure_gauge_kpa']
    else: entry['observations'][0]['unit']='%'
    ref,w=setup(p,ctx,document)
    w=p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='oxygen-invalid')
    run=w['science']['model_runs'][0]
    assert run['status']=='withheld' and run['issues']
    assert 'output' not in run and 'comparison' not in run
    if problem!='percent_observation': assert run['missing_inputs']


@pytest.mark.parametrize('bad_row',[None,42,'bad',[],{}, {'observable':[], 'coordinate':0.,'value':2.,'unit':'K'}])
def test_queued_malformed_observation_rows_are_inspectably_withheld(env,bad_row):
    p,ctx,_=env;document=packet();document['scientific_models'][0]['observations']=[bad_row]
    ref,w=setup(p,ctx,document)
    p.case_science.queue(ctx,'C',expected_revision=w['revision'],idempotency_key='bad-row')
    p.runtime.tick();w=p.quality_workflow.get(ctx,'C')
    run=w['science']['model_runs'][0]
    assert run['status']=='withheld' and 'observation' in str(run['issues']).lower()
    assert 'output' not in run and 'comparison' not in run
    assert w['science']['status']=='waiting_for_inputs'


@pytest.mark.parametrize('field,bad_value',[('config',None),('config',[]),('config',42),('observations',None),('observations',{}),('assumptions',{}),('assumptions',{'kind':'evidence','id':'unattached','revision':1}),('uncertainty','unknown'),('model_id',[])])
def test_identified_bad_configuration_shapes_are_withheld(env,field,bad_value):
    p,ctx,_=env;document=packet();document['scientific_models'][0][field]=bad_value
    ref,w=setup(p,ctx,document)
    w=p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='bad-shape')
    run=w['science']['model_runs'][0]
    assert run['status']=='withheld' and run['issues']
    assert 'output' not in run


@pytest.mark.parametrize('document',[{'scientific_models':None},{'scientific_models':{}},{'scientific_models':'bad'},
    {'scientific_models':[None]},{'scientific_models':[42]},{'scientific_models':[{}]}, {'configuration_request':42},
    {'scientific_models':None,'configuration_request':{'model_id':'chemical.semi_batch','config':{}}},
    {'scientific_models':[None],'configuration_request':{'model_id':'chemical.semi_batch','config':{}}}])
def test_unidentifiable_scientific_containers_return_domain_error(env,document):
    p,ctx,_=env
    # setup's fallback applies only to omitted fixtures; preserve the malformed JSON original here.
    ref,w=setup(p,ctx,{'scientific_models':[]})
    p.evidence.ingest(ctx,source_system='synthetic',source_record_id='thermal',content=json.dumps(document).encode(),
                     media_type='application/json',site_id='S',event_time=None)
    w=p.quality_workflow.prepare(ctx,'C',expected_revision=w['revision'],idempotency_key='refresh-shape')
    with pytest.raises(ValueError,match='(?i)(document|scientific_models|configuration)'):
        p.case_science.analyze(ctx,'C',expected_revision=w['revision'],idempotency_key='unidentified')
    assert not p.store.read().list('T','physical_analysis_result')


def test_native_quality_sources_flow_through_mounted_science_and_ordinary_snapshot(env):
    from fastapi.testclient import TestClient
    from src.lifesci.api import create_app
    from src.lifesci.ownership import Ownership
    from src.prime_runtime.science import FrozenScience
    p, ctx, _ = env
    for role in ('admin', 'operator'):
        p.identity.assign_role('T', 'owner', role, site_id='S')
    ctx = p.identity.context_for('T', 'owner')
    for record_class in ('batch_record', 'lab_record'):
        p.ownership.assign('T', Ownership(record_class, 'S', 'native', None, (), intended_use='Synthetic'), by='test', reason='Synthetic')
    p.execution.create_native(ctx, 'batch', 'B', {'batch_id':'B'}, site_id='S')
    sample = p.lab.register_sample(ctx, 'B', None, 'test', 'sample')
    result = p.lab.record_result(ctx, sample['sample_id'], 'potency', 4., 'mg/mL')
    p.lab.register_instrument(ctx, 'I', {'batch_id':'B'}, site_id='S')
    p.execution.create_native(ctx, 'material_lot', 'LOT', {'batch_id':'B'}, site_id='S')
    # Work orders and raw signals share the existing authorized native record contract.
    with p.store.transaction('synthetic-fixture') as tx:
        for kind in ('work_order', 'signal'):
            tx.put('T', kind, kind+'-B', {'site_id':'S','batch_id':'B'}, expected_revision=None, action='synthetic-fixture')
    ref, _ = setup(p, ctx)
    with p.store.transaction('synthetic-fixture') as tx:
        c = tx.require('T','case','C')
        tx.put('T','case','C',{**c.state,'associations':{'batch_id':'B'}}, expected_revision=c.revision, action='synthetic-fixture')
    client = TestClient(create_app(p)); headers={'X-Tenant-Id':'T','X-Actor-Id':'owner'}
    w = client.get('/v1/quality/workspaces/C',headers=headers).json()
    response = client.post('/v1/quality/workspaces/C/prepare',headers={**headers,'Idempotency-Key':'native-prepare'},json={'expected_revision':w['revision']})
    assert response.status_code == 200
    w = response.json()
    assert {'result','instrument','material_lot','work_order','signal'} <= {s['ref']['kind'] for s in w['sources']}
    catalog = client.get('/v1/quality/workspaces/C/science/catalog',headers=headers)
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()['configurations'][0]['id'] == 'cooling'
    response = client.post('/v1/quality/workspaces/C/science/analyze',headers={**headers,'Idempotency-Key':'native-science'},json={'expected_revision':w['revision']})
    assert response.status_code == 200, response.text
    assert response.json()['science']['model_runs'][0]['comparison'][0]['predicted'] == pytest.approx(300+20/math.e,rel=1e-7)
    data, meta = p.investigations.snapshot(ctx,site_id='S',case_ids=['C'])
    assert {s['ref']['id'] for s in w['sources']} <= {i['id'] for i in meta['items']}
    assert FrozenScience.from_package(data).run('cooling')['status'] == 'completed'
    with pytest.raises(ConflictError):
        p.investigations.snapshot(ctx,site_id='S',record_refs=[{'kind':'result','id':result['result_id'],'revision':999}])
    with pytest.raises(PermissionError):
        p.investigations.snapshot(ctx,site_id='OTHER',record_refs=[{'kind':'result','id':result['result_id'],'revision':1}])
    p.identity.grant('T',grantee_id='limited',resource_kind='case',resource_id='C',actions=['read'],site_id='S')
    limited=p.identity.context_for('T','limited')
    with pytest.raises(PermissionError):
        p.investigations.snapshot(limited,site_id='S',record_refs=[{'kind':'result','id':result['result_id'],'revision':1}])
