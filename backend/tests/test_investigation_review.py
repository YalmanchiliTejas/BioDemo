import copy
import json
from pathlib import Path
import pytest
from src.manufacturing_data import ManufacturingStore,ManufacturingTools,ingest_package
from src.prime_runtime.bridge import ManufacturingBridge
from src.state import BlackboardStore
from src.workflows import ManufacturingInvestigationWorkflow
from src.workflows.investigation_review import review_investigation

@pytest.fixture
def case(tmp_path):
    package=tmp_path/'sources';package.mkdir()
    for name,base in [('first',10),('second',20),('third',1)]:
        (package/f'{name}.csv').write_text('batch_id,Time (h),VCD (cells/mL),Glucose (g/L),available_at\n'+
            '\n'.join(f'{name}/{run},{t},{base*(1+t) if run=="R1" else base},{8-t},2024-01-01T00:00:00Z' for run in ('R1','R2') for t in (0,1,2)))
    store=ManufacturingStore(tmp_path/'store');ingest_package(package,store)
    tools=ManufacturingTools(store,as_of='2030-01-01T00:00:00Z');prepared=tools.analysis().prepare()
    rows=store.visible(as_of=tools.as_of,limit=None)
    bridge=ManufacturingBridge(store=store,blackboards=BlackboardStore(tmp_path/'boards'),
        workflow=ManufacturingInvestigationWorkflow(tmp_path/'workflow',store),scope='default',incident_id='case',
        objective='Investigate all available sources',as_of=tools.as_of,seed_ids=[r['id'] for r in rows])
    bridge.checkpoint_path=tmp_path/'checkpoint.json'
    return bridge,tools,prepared,rows

def complete_report(prepared):
    units=prepared['screening']['coverage_units'];candidates=prepared['screening']['priority_candidates']
    ids=list(dict.fromkeys([u['evidence_ids'][0] for u in units]+[c['evidence_ids'][0] for c in candidates]))
    return {'assessment':'Descriptive differences require design review; no cause established.',
        'report_type':'final_investigation','cross_scope_synthesis':'Reviewed sources have different profiles; operating design and acquisition reliability remain uncertain.',
        'coverage':[{'unit_id':u['unit_id'],'status':'investigated','reason':'Compared scoped source series and retained design uncertainty.','evidence_ids':[u['evidence_ids'][0]]} for u in units],
        'candidate_reviews':[{'candidate_id':c['candidate_id'],'status':'contextualized','reason':'Descriptive profile difference; no approved specification establishes a fault.','evidence_ids':[c['evidence_ids'][0]]} for c in candidates],
        'evidence_ids':ids,'observed_facts':[{'statement':'Source measurement recorded.','evidence_ids':[ids[0]]}],
        'hypotheses':[{'hypothesis_id':'H1','statement':'Operating design may explain differences.',
            'supporting_evidence_ids':[ids[0]],'contradicting_evidence_ids':[ids[-1]],'confidence':0.6,
            'unknowns':['Recipe records unavailable.']}],'open_questions':['Design intent remains unverified.'],
        'tasks':[],'evidence_requests':[]}

def test_child_submission_cannot_occupy_final_slot_and_checkpoint_survives(case):
    bridge,_,prepared,_=case
    child=complete_report(prepared)
    saved=bridge.submit_report(child,caller_depth=1)
    assert saved['final_report_submitted'] is False and bridge.result is None
    assert json.loads(Path(bridge.checkpoint_path).read_text())['status']=='incomplete'
    assert bridge.context()['sub_investigations'][0]['assessment']==child['assessment']
    result=bridge.submit_report(child)
    assert result['report_status']=='complete_for_available_evidence'
    assert result['causal_hypotheses'][0]['confidence'] is None
    assert result['causal_hypotheses'][0]['legacy_agent_confidence']==0.6
    assert json.loads(Path(bridge.checkpoint_path).read_text())['status']=='final_report_persisted'

def test_screening_and_one_source_citations_cannot_masquerade_as_completion(case):
    bridge,_,prepared,rows=case
    report=complete_report(prepared);report['coverage']=report['coverage'][:1]
    check=bridge.validate_report(report)
    assert check['report_status']=='incomplete' and check['missing_unit_ids']
    assert bridge.result is None and bridge.tool_calls==0
    result=bridge.submit_report(report)
    assert result['report_status']=='incomplete'
    assert result['status']=='needs_more_work' and bridge.result is None
    report['report_type']='partial_investigation'
    result=bridge.submit_report(report)
    assert result['workflow']['report_status']=='incomplete'

def test_wrong_entity_coverage_and_false_temporal_order_rejected(case):
    bridge,_,prepared,rows=case
    report=complete_report(prepared)
    unit=report['coverage'][0]
    wrong=next(r for r in rows if r['entity_id']!=prepared['screening']['coverage_units'][0]['entity_id'])
    unit['evidence_ids']=[wrong['id']];report['evidence_ids'].append(wrong['id'])
    with pytest.raises(ValueError,match='source/entity'):bridge.validate_report(report)
    values=sorted([r for r in rows if r['name']=='VCD (cells/mL)' and r['entity_id']=='first/R1'],key=lambda r:r['time_value'])
    report=complete_report(prepared)
    report['evidence_ids'] += [r['id'] for r in values]+[r['time_evidence_id'] for r in values]
    report['temporal_claims']=[{'claim_id':'T','earlier_observation_id':values[-1]['id'],'later_observation_id':values[0]['id']}]
    with pytest.raises(ValueError,match='contradicts'):bridge.validate_report(report)
    report['temporal_claims'][0].update(earlier_observation_id=values[0]['id'],later_observation_id=values[-1]['id'])
    check=bridge.validate_report(report)
    assert check['temporal_claims'][0]['gap_hours']==2
    assert check['temporal_claims'][0]['verification'].endswith('causality_not_established')

def test_grouped_flags_diverse_priorities_zero_denominators_and_stability(case):
    _,tools,p,_=case
    screen=p['screening']
    assert len(screen['coverage_units'])==6
    assert {c['source_id'] for c in screen['priority_candidates']}=={s['source_id'] for s in p['source_versions']}
    assert len({c['measurement_family'] for c in screen['priority_candidates']})>1
    assert screen['priority_candidates']==tools.analysis().prepare()['screening']['priority_candidates']
    from src.manufacturing_data.screening import build_screening
    anomaly={'source_id':'s','entity_id':'r','sheet':'clock','name':'a','flags':['duplicate_source_times'],'evidence_ids':['a']}
    grouped=build_screening([], [anomaly,{**anomaly,'name':'b','evidence_ids':['b']}],[],[])
    assert grouped['raw_anomaly_flag_count']==2 and grouped['grouped_quality_candidate_count']==1
    c={'source_id':'s','name':'unknown measurement','unit':'g/L','entity_ids':['r1','r2'],'peak_values':[0,1],'evidence_ids':['a','b']}
    zero=build_screening([],[anomaly],[c],[])['candidates'][-1]
    assert zero['symmetric_peak_difference_percent']==200

def test_shared_budget_reserve_and_source_clock_gaps_remain_incomplete(case):
    bridge,_,p,rows=case
    bridge.max_tool_calls=8;bridge.lead_tool_reserve=2;bridge.tool_calls=6
    assert bridge.tool('inspect_data',{},caller_depth=1)['status']=='budget_exhausted'
    assert bridge.tool_calls==6
    assert bridge.tool('inspect_data',{})['sources']
    report=complete_report(p)
    values=[r for r in rows if r['name']=='VCD (cells/mL)']
    report['temporal_claims']=[{'claim_id':'T','earlier_observation_id':values[0]['id'],'later_observation_id':next(r['id'] for r in values if r['entity_id']!=values[0]['entity_id'])}]
    report['evidence_ids']+= [report['temporal_claims'][0][k] for k in ('earlier_observation_id','later_observation_id')]
    assert any(i['code']=='temporal_claim_unverified' for i in bridge.validate_report(report)['issues'])

def test_counterevidence_not_searched_and_missing_synthesis_are_incomplete(case):
    bridge,_,p,_=case;r=complete_report(p)
    r['hypotheses'][0].update(contradicting_evidence_ids=[],contradicting_evidence_status='not_searched',contradicting_evidence_absence_reason='No recipe source available.')
    r['cross_scope_synthesis']=''
    check=bridge.validate_report(r)
    assert check['report_status']=='incomplete'
    assert {i['code'] for i in check['issues']} >= {'counterevidence_search_incomplete','required_deliverables_missing'}


def test_temporal_clock_reset_is_explicitly_unverified(case):
    bridge,_,p,rows=case
    r=complete_report(p);values=sorted([x for x in rows if x['name']=='VCD (cells/mL)' and x['entity_id']=='first/R1'],key=lambda x:x['time_value'])
    r['evidence_ids'] += [v['id'] for v in values]+[v['time_evidence_id'] for v in values]
    r['temporal_claims']=[{'claim_id':'T','earlier_observation_id':values[0]['id'],'later_observation_id':values[-1]['id']}]
    altered=copy.deepcopy(p)
    for series in altered['series']:
        if series['entity_id']=='first/R1':series['source_backwards_steps']=1
    review=review_investigation(r,altered,bridge.session.get(r['evidence_ids']))
    assert review['temporal_claims'][0]['verification']=='unverified_source_clock'
    assert review['report_status']=='incomplete'


def test_direct_fact_units_and_source_times_are_checked(case):
    bridge,tools,p,rows=case
    r=complete_report(p);value=next(x for x in rows if x['name']=='VCD (cells/mL)' and x['time_value']==1)
    r['evidence_ids'] += [value['id'],value['time_evidence_id']]
    r['observed_facts']=[{'statement':'Source value at its clock coordinate.',
        'observation_id':value['id'],'claimed_value':value['value_number'],'claimed_unit':'wrong-unit'}]
    with pytest.raises(ValueError,match='unit differs'):bridge.submit_report(r)
    r['observed_facts'][0].update(claimed_unit=value['unit'],claimed_time_value=1,claimed_time_basis='elapsed_hours')
    assert bridge.submit_report(r)['report_status']=='complete_for_available_evidence'


def test_partial_cannot_qualify_even_with_approving_reviews():
    from benchmarks.common.quality import score_review
    policy={'dimensions':[],'integrity_gates':[],'score_scale':[0,4],'status':'approved',
        'reviewed_by':['qa'],'minimum_quality_score':0}
    run={'attempted':True,'run_id':'r','audit':{'pass':True},'isolation_audit':{'pass':True},
        'status':'incomplete','mode':'full_rlm','output_sha256':'x',
        'output':{'analysis':{'report_status':'incomplete'}},
        'case':{'quality_policy_sha256':'p','required_deliverables':[]}}
    result=score_review(run,policy,{'run_id':'r','output_sha256':'x','policy_sha256':'p'})
    assert result['qualified'] is False and any('incomplete' in x for x in result['reasons'])


def test_sdk_depth_routes_child_over_http_and_lead_can_finalize(case,tmp_path,monkeypatch):
    import importlib.util
    bridge,_,prepared,_=case
    client_path=Path(__file__).resolve().parents[1]/'prime_skills/manufacturing_os/src/manufacturing_os/__init__.py'
    spec=importlib.util.spec_from_file_location('investigation_skill_test',client_path)
    client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
    bridge.start()
    try:
        config=tmp_path/'bridge-config.json';config.write_text(json.dumps({'url':bridge.url,'token':bridge.token}))
        monkeypatch.setenv('BIODEMO_PRIME_BRIDGE_CONFIG',str(config));monkeypatch.setenv('RLM_DEPTH','1')
        assert client.context()['budget']['caller_role']=='specialist'
        assert client.submit_report(complete_report(prepared))['final_report_submitted'] is False
        assert bridge.result is None
        # A saved specialist report cannot be mistaken for host completion.
        assert client._post('/execution-status',{})['final_report_submitted'] is False
        monkeypatch.setenv('RLM_DEPTH','0')
        assert client.validate_report(complete_report(prepared))['report_status']=='complete_for_available_evidence'
        assert client.submit_report(complete_report(prepared))['report_status']=='complete_for_available_evidence'
        status=client._post('/execution-status',{})
        assert status['final_report_submitted'] is True
        assert status['report_status']=='complete_for_available_evidence'
    finally:bridge.close()


def test_host_timeout_preserves_incomplete_checkpoint_and_partial_logs(case,tmp_path):
    import sys
    import subprocess
    from src.prime_runtime.harness import PrimeManufacturingHarness
    bridge,_,_,_=case
    host=tmp_path/'host.py';host.write_text('import time\nprint("host initialized",flush=True)\ntime.sleep(10)\n')
    harness=PrimeManufacturingHarness(command=[sys.executable,str(host)],store=bridge.store,
        blackboards=bridge.blackboards,workflow=bridge.workflow,scope=bridge.scope,runtime_root=tmp_path/'runtime')
    harness.timeout_seconds=3
    with pytest.raises(subprocess.TimeoutExpired):
        harness.run(incident_id='cancelled',problem='Investigate available evidence',new_evidence_ids=[],as_of=bridge.as_of)
    checkpoint=json.loads((tmp_path/'runtime/workspaces/cancelled/investigation-checkpoint.json').read_text())
    assert checkpoint['status']=='incomplete'
    assert any('host initialized' in p.read_text() for p in (tmp_path/'runtime/logs').glob('*.jsonl'))


def test_verification_review_does_not_consume_final_slot(case):
    bridge,_,prepared,_=case
    r=complete_report(prepared);r['assessment']='Unlinked numerical summary 987654321.123 requires checking.'
    result=bridge.submit_report(r)
    assert result['status']=='needs_more_work' and bridge.result is None
    assert result['verification']['unlinked_numeric_literal_count']>0
    r['assessment']='Source patterns require independent review; no cause established.'
    assert bridge.submit_report(r)['report_status']=='complete_for_available_evidence'


def test_finalization_reserve_closes_exploration_without_spending_calls(case):
    import time
    bridge,_,_,_=case
    bridge.time_budget_seconds=100
    bridge.started_monotonic=time.monotonic()-20
    assert bridge.budget()['phase']=='finalization'
    for _ in range(3):
        result=bridge.tool('search_evidence',{'query':'new investigation'})
        assert result['status']=='finalization_required'
    assert bridge.tool_calls==0
    assert bridge.result is None
    checkpoint=json.loads(Path(bridge.checkpoint_path).read_text())
    assert checkpoint['status']=='incomplete'


def test_required_claim_ledger_blocks_missing_and_unsupported_claims(case):
    bridge,_,prepared,_=case
    bridge.require_claim_ledger=True
    r=complete_report(prepared)
    checked=bridge.validate_report(r)
    assert checked['report_status']=='incomplete'
    assert any(i['code']=='claim_ledger_missing' for i in checked['issues'])
    assert bridge.result is None


def test_benchmark_follow_up_actions_field_is_a_required_deliverable(case):
    bridge,_,prepared,_=case
    r=complete_report(prepared);r.pop('tasks');r['follow_up_actions']=[]
    assert bridge.validate_report(r)['required_structure']['follow_up_actions'] is True


def test_verified_cause_classification_cannot_bypass_hypothesis_guard(case):
    bridge,_,prepared,_=case
    r=complete_report(prepared);r['hypotheses'][0]['status']='verified_cause'
    with pytest.raises(ValueError,match='verified root cause'):
        bridge.submit_report(r)
