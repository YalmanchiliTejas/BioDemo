"""Published-summary checks, unit contracts, leakage boundaries and existing OS integration."""
from copy import deepcopy
import json
import math
import pytest
from fastapi.testclient import TestClient
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from src.lifesci.devseed import seed,TENANT
from src.lifesci.api import create_app
from src.lifesci.fermentation.data import project,DATA
from src.lifesci.fermentation.model import calculate,fit_source,compression_kw,transfer_point
from src.lifesci.fermentation.schemas import Assumptions
from src.lifesci.process_engineering.catalog import ModelCatalog

@pytest.fixture
def env():
    p=Platform(RecordStore(),providers={});seed(p)
    return p,p.identity.context_for(TENANT,'priya')

def test_sources_and_frozen_split_are_not_targets_in_agent_inputs():
    s=project('sulfolobus'); p=project('pichia')
    assert {r['id'] for r in s['calibration']}=={'source_ring_355','source_ring_500'}
    assert all(r['working_volume_l']==2 for r in s['calibration'])
    assert len(p['calibration'])==1 and p['calibration'][0]['nominal_reactor_volume_l']==10
    assert all('kla_h_inv' not in e for e in s['equipment'])
    assert 'published_rpm' not in json.dumps(s)
    assert 'table2_scaleup' not in p and 'terminal_1000L' not in p
    assert s['equipment'][2]['tank_diameter_m'] is None
    assert '200 L viability was not measured' in ' '.join(s['limitations'])
    assert all(f['sha256'] for f in p['source_manifest']['files'])
    # Perturbing evaluator-only answers cannot change tool forecasts.
    before=calculate(s)
    targets=json.loads((DATA/'validation.evaluator.json').read_text())
    assert len(targets['sulfolobus'])==2
    assert before==calculate(deepcopy(s))

def test_agent_model_tool_never_reads_evaluator_targets(monkeypatch):
    from pathlib import Path
    original=Path.read_text
    def guard(path,*args,**kwargs):
        if path.name=='validation.evaluator.json': raise AssertionError('agent tool read a target file')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',guard)
    for case in ('sulfolobus','pichia'):
        assert calculate(project(case))['case_id']==case

def test_source_fit_and_hydrodynamic_scaling():
    p=project('sulfolobus'); fit=fit_source(p)
    assert fit['power_exponent']==pytest.approx(.18837574403622928)
    assert not fit['gas_exponent_identified'] and fit['residual_degrees_of_freedom']==0
    ref=transfer_point(p,20,200,.25); doubled=transfer_point(p,20,400,.25)
    assert doubled['power_w_m3']==pytest.approx(8*ref['power_w_m3'])
    assert doubled['tip_speed_m_s']==pytest.approx(2*ref['tip_speed_m_s'])
    output=calculate(p)
    assert output['biology_prediction'] is None and output['oxygen_capacity'] is None
    assert all(r['rated_equipment_feasibility']=='unknown' for r in output['recommendations'])
    assert all('requires_characterization' in r['status'] for r in output['scenarios'] if r['meets_nominal_kla_target'] and r['within_assumed_power_screen'])

def test_absolute_pressure_and_economic_dimensional_balance():
    p=project('pichia'); prediction=calculate(p)
    assert prediction['pressure_saturation_ratio_air_only']==pytest.approx(201.325/151.325)
    a,b=prediction['scenarios']
    assert b['otr_mg_l_h']==pytest.approx(20*max(0,b['cstar_mg_l']-1.5))
    assert b['compressor_kw']>a['compressor_kw']
    assert compression_kw(36,0,101.325,.65)==0
    no_oxygen=calculate(p,{'oxygen_nm3_h':0})
    assert no_oxygen['economics']['oxygen_delivery_savings_usd_h']<0
    twice=calculate(p,{'air_nm3_h':72})
    assert twice['scenarios'][1]['compressor_kw']==pytest.approx(2*b['compressor_kw'])
    assert prediction['economics']['net_after_extra_feed_usd'] is None
    feed=calculate(p,{'extra_methanol_l':1000})
    assert feed['economics']['net_after_extra_feed_usd']<0
    assert prediction['biology_prediction'] is None
    assert not prediction['equipment_pressure_rating_verified']
    supersaturated=calculate(p,{'dissolved_oxygen_mg_l':30})
    assert supersaturated['scenarios'][1]['otr_mg_l_h']<0 # desorption must not be hidden by clamping

@pytest.mark.parametrize('bad',[{'gas_exponent':float('nan')},{'pressure_gauge_kpa':-5},{'compressor_efficiency':0},{'air_nm3_h':-1}])
def test_invalid_units_and_nonfinite_inputs_rejected(bad):
    with pytest.raises(ValueError): calculate(project('pichia'),bad)

def test_catalog_reuse_does_not_replace_drying_models():
    assert len(ModelCatalog().snapshot())==2
    fermentation=ModelCatalog('aerobic_fermentation')
    assert len(fermentation.snapshot())==2
    assert not fermentation.get('fermentation.oxygen_transfer').applicability({'equipment':{}})['applicable']
    with pytest.raises(ValueError): project('../validation.evaluator')

def test_existing_flow_evidence_review_and_stale_boundaries(env):
    p,ctx=env
    result=p.fermentation.evaluate(ctx,'sulfolobus',{})
    assert result['execution_status']=='completed'
    assert result['validation']['rows'][0]['measured']==40.5
    assert result['validation']['rows'][1]['measured']==41.1
    assert result['validation']['rows'][1]['relative_error']<-.3 # keep failure visible; no target fitting
    assert p.store.read().require(TENANT,'data_flow_run',result['flow_run_id']).state['status']=='completed'
    proposal=p.fermentation.review(ctx,result['id'],'priya')
    assert proposal['required_roles']==['engineering'] and proposal['execution_status']=='not_started'
    assert not p.store.read().list(TENANT,'action_intent')
    # Declared assumption changes invalidate old calculations and review proposals.
    p.fermentation.evaluate(ctx,'sulfolobus',{'assumptions':{'gas_exponent':.2}})
    assert p.fermentation.get(ctx,result['id'])['status']=='stale'
    assert p.store.read().require(TENANT,'proposal',proposal['proposal_id']).state['status']=='stale'
    with pytest.raises(ValueError):p.fermentation.review(ctx,result['id'],'priya')

def test_failed_simulation_is_preserved(env):
    p,ctx=env
    result=p.fermentation.evaluate(ctx,'sulfolobus',{'assumptions':{'selected_receiver_l':1000}})
    assert result['execution_status']=='failed' and result['issues']
    assert p.store.read().require(TENANT,'data_flow_run',result['flow_run_id']).state['status']=='blocked'
    assert p.fermentation.get(ctx,result['id'])['prediction'] is None

def test_api_contract_idempotency_permissions_and_agent_unavailability(env,monkeypatch):
    monkeypatch.setattr('src.lifesci.fermentation.benchmark.hosted_research_profile', lambda: None)
    p,ctx=env; client=TestClient(create_app(p));headers={'X-Tenant-Id':TENANT,'X-Actor-Id':'priya','Idempotency-Key':'fermentation-evaluate-1'}
    listing=client.get('/v1/process-model/fermentation/projects',headers=headers)
    assert listing.status_code==200 and len(listing.json()['projects'])==2
    url='/v1/process-model/fermentation/projects/pichia/evaluate'
    first=client.post(url,headers=headers,json={}); assert first.status_code==200,first.text
    assert first.json()['id']==client.post(url,headers=headers,json={}).json()['id']
    headers['Idempotency-Key']='fermentation-agent-1'
    outcome=client.post('/v1/process-model/fermentation/projects/pichia/agent-assessment',headers=headers,json={})
    assert outcome.status_code==200
    assert outcome.json()['status']=='unresolved' and outcome.json()['scientific_scores'] is None
    assert outcome.json()['output'] is None
    outsider={'X-Tenant-Id':'other-tenant','X-Actor-Id':'priya'}
    assert client.get('/v1/process-model/fermentation/results/'+first.json()['id'],headers=outsider).status_code in (401,403,404)


def test_blinded_prime_attempt_fails_closed_before_starting_unsafe_network_trial(tmp_path):
    from src.lifesci.fermentation.benchmark import ExistingIsolatedPrime
    host=ExistingIsolatedPrime(project('pichia'),tmp_path)
    with pytest.raises(RuntimeError,match='provider-only network isolation'):
        host.run(incident_id='test',problem='Assess',new_evidence_ids=[],as_of='2026-10-27T00:00:00Z')
    assert host.last_output is None and not (tmp_path/'agent_input').exists()


def test_research_workspace_paths_survive_worker_cwd_change(tmp_path,monkeypatch):
    from pathlib import Path
    from src.lifesci.fermentation.benchmark import ExistingIsolatedPrime
    monkeypatch.chdir(tmp_path)
    captured={}
    def isolated(package,problem,as_of,configuration):
        assert package.is_absolute() and package.is_dir()
        assert Path(configuration['state_directory']).is_absolute()
        assert Path(configuration['artifact_directory']).is_absolute()
        captured.update(configuration)
        return {'analysis':{},'usage':{}}
    monkeypatch.setattr('benchmarks.common.isolated_runner.run_isolated',isolated)
    host=ExistingIsolatedPrime(project('pichia'),Path('relative-runtime'),blinded=False)
    host.model='modal/test'
    host.run(incident_id='test',problem='Assess',new_evidence_ids=[],as_of='2026-10-27T00:00:00Z')
    assert captured['prime_model']=='modal/test'
    from src.prime_runtime.bridge import finalization_reserve
    seconds=captured['budgets']['wall_clock_seconds']
    assert seconds-finalization_reserve(seconds)>=300, 'Research must allow source reconstruction and a solver call before finalization closes exploration'
    assert not (tmp_path/'relative-runtime/benchmark-case-fermentation-pichia/agent_input/validation.evaluator.json').exists()


def test_research_auth_failure_has_recovery_message_and_retains_logs(tmp_path,monkeypatch):
    from src.lifesci.fermentation.benchmark import ExistingIsolatedPrime
    def isolated(package,*args):
        log=package.parent/'runtime-artifacts/test.stderr'
        log.parent.mkdir();log.write_text('Modal proxy authentication is missing or has the wrong format')
        raise RuntimeError(f'stderr: {{error_path}} tools: {{tools_path}}\nRuntimeError: stderr: {log} tools: retained.tools')
    monkeypatch.setattr('benchmarks.common.isolated_runner.run_isolated',isolated)
    host=ExistingIsolatedPrime(project('pichia'),tmp_path,blinded=False)
    with pytest.raises(RuntimeError,match='Set MODAL_PROXY_TOKEN'):
        host.run(incident_id='auth',problem='Assess',new_evidence_ids=[],as_of='2026-10-27T00:00:00Z')
    assert (tmp_path/'benchmark-case-fermentation-pichia/runtime-artifacts/test.stderr').is_file()


def test_same_prime_adapter_receives_the_registered_fermentation_tool(tmp_path,monkeypatch):
    """Contract double only, never an AI-performance result."""
    from src.prime_runtime.harness import PrimeManufacturingHarness
    from benchmarks.common.full_agent_adapter import FullManufacturingOS
    from benchmarks.common.agent_adapter import InvestigationInput
    package=tmp_path/'agent_input';package.mkdir()
    (package/'model-input.json').write_text(json.dumps(project('pichia')))
    seen=[]
    class HarnessDouble:
        additional_tools={}
        model=None
        def run(self,**kwargs):
            calculated=self.additional_tools['fermentation_transfer'](assumptions={'oxygen_nm3_h':0})
            assert calculated['status']=='completed'
            assert calculated['output']['economics']['oxygen_delivery_savings_usd_h']<0
            seen.append(calculated)
            return {'evidence_ids':[],'verification':{'evidence_checks':{}},'rollout_metrics':{}}
    monkeypatch.setattr(PrimeManufacturingHarness,'from_env',lambda **kwargs:HarnessDouble())
    request=InvestigationInput(package,'Assess oxygen alternatives',None,{'mode':'full_rlm','scientific_tool_family':'aerobic_fermentation',
        'state_directory':str(tmp_path/'state'),'evaluation_time':'2026-10-28T00:00:00Z','budgets':{'wall_clock_seconds':30}})
    result=FullManufacturingOS().run_investigation(request)
    assert len(seen)==1 and len(result['scientific_tool_results'])==1
    assert result['constraints']['gmp_actions_available'] is False
