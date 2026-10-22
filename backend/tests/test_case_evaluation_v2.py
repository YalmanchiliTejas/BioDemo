"""Behavioral acceptance tests for the README_benchmarks.md evaluation contract."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from benchmarks.common.case_protocol import ROOT, VERSION, digest, save, stable_hash, load_case
from benchmarks.common.case_audit import audit_case
from benchmarks.common.case_runner import run_case
from benchmarks.common.objective_scores import score_objective, compare_sets, validate_citation
from benchmarks.common.quality import score_review
from benchmarks.common.human_work import PHASES, aggregate_effort, produce_comparison, template
from benchmarks.common.trace import TraceSink, validate_event


def fixture_case(tmp_path, benchmark='fresenius'):
    """Independent test labels frozen before any output; not product results."""
    package=tmp_path/'agent_input';package.mkdir(parents=True)
    source=package/'records.csv';source.write_text('record_id,batch_id,value\nR-1,B-1,1.25\nR-2,B-2,0.25\n')
    policy=json.loads((ROOT/'benchmarks/rubrics/investigation-v2.json').read_text())
    policy.update(status='approved',reviewed_by=['fixture-domain-reviewer'],minimum_quality_score=3,noninferiority_margin=.25)
    save(tmp_path/'quality-policy.json',policy);save(tmp_path/'triage-policy.json',{'status':'approved','reviewed_by':['fixture-reviewer']})
    reference={'field_checks':[{'source':'records.csv','row':2,'column':'value','expected':1.25,'rtol':1e-6,'atol':1e-8}],
               'critical_evidence_ids':['R-1'], 'scope_ids':['B-1'], 'negative_controls':['B-2'],
               'negative_controls_reviewed_by':['fixture-reviewer'], 'triage_labels':{'case':'L3'},
               'triage_reviewed_by':['fixture-reviewer'],'causal_labels':None}
    save(tmp_path/'reference.json',reference)
    files=[{'path':'records.csv','sha256':digest(source),'bytes':source.stat().st_size,'available_at':None}]
    case={'version':VERSION,'benchmark_id':benchmark,'case_id':'fixture-01','condition':'raw','condition_status':'ready',
          'objective':'Investigate the measurements and propose reviewable follow-up.','as_of':None,'input_root':'agent_input',
          'allowlist':files,'package_sha256':stable_hash(files),'reference':'reference.json','reference_sha256':digest(tmp_path/'reference.json'),
          'quality_policy':'quality-policy.json','quality_policy_sha256':digest(tmp_path/'quality-policy.json'),
          'triage_policy':'triage-policy.json','triage_policy_sha256':digest(tmp_path/'triage-policy.json'),
          'budgets':{'wall_clock_seconds':30,'tool_calls':6},'access_scope':'evaluation','tenant':'fixture',
          'seed':42,'frozen_at':'2026-01-01T00:00:00Z','required_deliverables':['assessment','scope'],
          'triage_rubric_status':'approved'}
    case['task_spec_sha256']=stable_hash({k:v for k,v in case.items() if k not in ('frozen_at','task_spec_sha256')})
    save(tmp_path/'case.json',case)
    return case,reference,policy


def output():
    return {'files':[{'path':'records.csv'}], 'records':[{'source':'records.csv','row':2,'values':{'value':1.25}}],
            'analysis':{'assessment':'One signal warrants further investigation; cause remains uncertain.',
                        'evidence_ids':['R-1'],'scope':{'batch_ids':['B-1']},'triage_by_case':{'case':'L1'},
                        'escalated_batches':['B-2'],'hypotheses':[]},
            'citations':[{'evidence_id':'R-1','record_id':'R-1','source':{'path':'records.csv','row':2,'column':'value'}}]}


def artifact(case,policy,run_id='run-1',mode='full_rlm'):
    return {'version':VERSION,'run_id':run_id,'benchmark_id':case['benchmark_id'],'case_id':case['case_id'],
            'case':case,'condition':'raw','mode':mode,'attempted':True,'status':'completed',
            'started_at':'2026-02-01T00:00:00Z','audit':{'pass':True},'isolation_audit':{'pass':True},
            'operator_id':'operator','output_sha256':'f'*64,'output':output(),'quality_policy':policy}


def review(run,policy):
    return {'run_id':run['run_id'],'output_sha256':run['output_sha256'],'policy_sha256':run['case']['quality_policy_sha256'],
            'reviewers':[{'reviewer_id':'independent-reviewer','independent_of_operator':True,'blind_to_method':True,
                          'evidence_ref':'fixture-review.json','scores':{d:3 for d in policy['dimensions']}}],
            'objective_checks_pass':True,'deliverables':{d:True for d in run['case']['required_deliverables']},
            'integrity_gates':{g:True for g in policy['integrity_gates']}}


def measured_logs(runs):
    logs=template([r['run_id'] for r in runs])
    for row in logs['runs']:
        row.update(effort_complete=True,evidence_ref='observed-timer-log.json')
        row['phases']={p:{'active_seconds':60,'manual_actions':1} for p in PHASES}
    return logs


def test_frozen_case_is_reproducible_and_tampering_invalidates(tmp_path):
    case,_,_=fixture_case(tmp_path)
    assert load_case(tmp_path/'case.json')==case
    assert audit_case(tmp_path/'case.json')['pass']
    (tmp_path/'agent_input/records.csv').write_text('changed source')
    assert not audit_case(tmp_path/'case.json')['pass']
    case['objective']='Changed after freeze';save(tmp_path/'case.json',case)
    with pytest.raises(ValueError,match='checksum'):load_case(tmp_path/'case.json')


def test_unknown_historical_availability_fails_closed(tmp_path):
    case,_,_=fixture_case(tmp_path)
    case['as_of']='2025-01-01T00:00:00Z'
    case['task_spec_sha256']=stable_hash({k:v for k,v in case.items() if k not in ('frozen_at','task_spec_sha256')})
    save(tmp_path/'case.json',case)
    result=audit_case(tmp_path/'case.json')
    assert not result['pass']
    assert 'historical availability' in ' '.join(result['failures'])


def test_scoring_uses_emitted_values_not_original_input_as_predictions(tmp_path):
    case,reference,_=fixture_case(tmp_path)
    result=score_objective(output(),reference,case,tmp_path/'agent_input')
    assert result['data_preparation']['field_accuracy']['value']==1
    altered=output();altered['records'][0]['values']['value']=99
    result=score_objective(altered,reference,case,tmp_path/'agent_input')
    assert result['data_preparation']['field_accuracy']['value']==0
    assert result['objective_checks']['field_values_correct'] is False
    altered['records']=[]
    result=score_objective(altered,reference,case,tmp_path/'agent_input')
    assert result['data_preparation']['field_accuracy']['value'] is None
    assert result['data_preparation']['field_coverage']['value']==0


def test_grounding_requires_location_version_and_permitted_source(tmp_path):
    case,_,_=fixture_case(tmp_path);allowed={r['path']:r for r in case['allowlist']}
    cite=output()['citations'][0]
    assert validate_citation(cite,tmp_path/'agent_input',allowed)['pass']
    for mutation in ({'source':{'path':'records.csv'}},{'source':{'path':'records.csv','row':50}},
                     {'source':{'path':'../reference.json','row':2}}, {'source':{'path':'records.csv','row':2,'sha256':'0'*64}}):
        assert not validate_citation({**cite,**mutation},tmp_path/'agent_input',allowed)['pass']


def test_negative_controls_and_routing_under_escalation_count(tmp_path):
    case,reference,_=fixture_case(tmp_path)
    scores=score_objective(output(),reference,case,tmp_path/'agent_input')['investigation']
    assert scores['negative_control_false_positive_rate']['value']==1
    assert scores['triage_confusion_matrix']['L3']['L1']==1
    assert scores['unsafe_under_escalation_rate']['value']==1
    reference['triage_labels']=None;reference['scope_ids']=None
    scores=score_objective(output(),reference,case,tmp_path/'agent_input')['investigation']
    assert scores['triage_agreement']['status']=='not_applicable'
    assert scores['affected_scope']['recall']['status']=='not_applicable'
    assert scores['root_cause_accuracy']['status']=='not_applicable'


def test_zero_retrieval_is_zero_recall_but_absent_labels_are_na():
    assert compare_sets([],['known'])['recall']['value']==0
    assert compare_sets(['guess'],None)['recall']['status']=='not_applicable'


def test_no_qualification_without_frozen_review_and_integrity_gates(tmp_path):
    case,reference,policy=fixture_case(tmp_path);run=artifact(case,policy)
    run['objective_scores']=score_objective(output(),reference,case,tmp_path/'agent_input')
    assert score_review(run,policy)['status']=='pending_review'
    checked=review(run,policy)
    assert score_review(run,policy,checked)['qualified'] is True
    checked['reviewers'][0]['reviewer_id']='operator'
    assert score_review(run,policy,checked)['qualified'] is None
    checked=review(run,policy);checked['integrity_gates']['no_future_leakage']=False
    assert score_review(run,policy,checked)['qualified'] is False
    checked=review(run,policy);run['audit']['pass']=False
    assert score_review(run,policy,checked)['status']=='invalid'


def test_unsupported_causal_certainty_and_invalid_citations_fail_quality(tmp_path):
    case,reference,policy=fixture_case(tmp_path)
    for mutate in ('cause','citation'):
        run=artifact(case,policy)
        if mutate=='cause':run['output']['analysis']['assessment']='The root cause is confirmed.'
        else:run['output']['citations'][0]['source']['row']=999
        run['objective_scores']=score_objective(run['output'],reference,case,tmp_path/'agent_input')
        assert score_review(run,policy,review(run,policy))['qualified'] is False


def test_failed_attempts_and_shared_setup_remain_in_effort_denominator(tmp_path):
    case,_,policy=fixture_case(tmp_path)
    runs=[artifact(case,policy,run_id='1'),artifact(case,policy,run_id='2')]
    runs[0]['qualification']={'status':'qualified','qualified':True,'quality_score':3}
    runs[1]['qualification']={'status':'failed','qualified':False}
    logs=measured_logs(runs)
    logs['setup_groups']=[{'id':'setup-1','active_seconds':3600,'run_ids':['1','2'],'measured_case_count':2,
                           'allocation':'equal','time_source':'observed','evidence_ref':'setup-timer.json'}]
    result=aggregate_effort(runs,logs);group=result['groups']['full_rlm']
    assert group['quality_qualified_rate']==.5
    assert group['human_hours_per_qualified_case']==pytest.approx(1+14/60)
    assert result['per_run']['1']['allocated_setup_hours']==.5
    assert result['per_run']['1']['first_case_hours']==pytest.approx(1+7/60)
    assert result['per_run']['2']['repeat_case_hours']==pytest.approx(6/60)
    runs[0]['qualification']={'status':'failed','qualified':False}
    group=aggregate_effort(runs,logs)['groups']['full_rlm']
    assert group['quality_qualified_rate']==0
    assert group['human_hours_per_qualified_case'] is None
    assert group['effort_per_qualified_status']=='undefined'


def test_unobserved_time_estimates_and_hypothetical_amortization_withhold_savings(tmp_path):
    case,_,policy=fixture_case(tmp_path);runs=[artifact(case,policy)]
    runs[0]['qualification']={'status':'qualified','qualified':True,'quality_score':3}
    for change in ('missing','self_reported','future_setup'):
        logs=measured_logs(runs)
        if change=='missing':logs['runs'][0]['phases']['verification']['active_seconds']=None
        elif change=='self_reported':logs['runs'][0]['time_source']='self_reported'
        else:logs['setup_groups']=[{'run_ids':['run-1','future-run'],'measured_case_count':2,'active_seconds':100,'allocation':'equal','time_source':'observed','evidence_ref':'setup'}]
        assert aggregate_effort(runs,logs)['groups']['full_rlm']['human_hours_per_qualified_case'] is None


def test_paired_percentage_requires_matching_qualified_noninferior_outcomes(tmp_path):
    case,_,policy=fixture_case(tmp_path)
    runs=[artifact(case,policy,'manual','manual'),artifact(case,policy,'os','full_rlm')]
    for r in runs:r['qualification']={'status':'qualified','qualified':True,'quality_score':3}
    logs=measured_logs(runs)
    for value in logs['runs'][1]['phases'].values():value['active_seconds']=30
    effort=aggregate_effort(runs,logs);comparison=produce_comparison(runs,effort)
    assert comparison['paired_sample_size']==1
    assert comparison['paired_human_effort_reduction_pct']==50
    runs[1]['qualification']['quality_score']=2
    assert produce_comparison(runs,effort)['paired_human_effort_reduction_pct'] is None
    runs[1]['qualification']['quality_score']=3;runs[1]['case']=copy.deepcopy(case);runs[1]['case']['package_sha256']='different'
    assert produce_comparison(runs,effort)['paired_sample_size']==0


def test_trace_active_work_is_separate_from_machine_runtime_and_raw_content(tmp_path):
    sink=TraceSink(tmp_path/'trace.jsonl','case','run',budgets={'tool_calls':4})
    event=sink.emit(actor='pipeline',stage='ingestion',action='parse',source_refs=['records.csv'])
    assert event['active_human_seconds']==0
    assert 'value' not in event and event['budgets']['tool_calls']==4
    event.update(active_human_seconds=5)
    with pytest.raises(ValueError):validate_event(event)


def test_same_case_runner_and_adapter_contract_on_both_datasets(tmp_path):
    class Adapter:
        def run_investigation(self,request):
            assert request.input_package.name=='agent_input'
            assert not (request.input_package/'reference.json').exists()
            return output()
    for benchmark in ('cho','fresenius'):
        base=tmp_path/benchmark;fixture_case(base,benchmark)
        path=run_case(base/'case.json','full_rlm',output_root=tmp_path/'runs',agent_adapter=Adapter())
        result=json.loads(path.read_text())
        assert result['status']=='completed'
        assert result['qualification']['status']=='invalid'  # injected adapters cannot publish scores
        assert result.get('objective_scores') is None


def test_inaccessible_competitor_is_not_tested(tmp_path):
    fixture_case(tmp_path/'case')
    path=run_case(tmp_path/'case/case.json','incumbent',output_root=tmp_path/'runs')
    result=json.loads(path.read_text())
    assert result['status']=='not_tested'
    assert result['attempted'] is False
    assert result['qualification']['qualified'] is None


def test_fresenius_replay_metadata_and_binary_tampering_is_rejected(tmp_path):
    from benchmarks.common.case_protocol import prepare_case
    path=prepare_case('fresenius','FRE-02',destination=tmp_path/'case')
    assert audit_case(path)['pass']
    pdf=tmp_path/'case/agent_input/quality/source_review.pdf';pdf.chmod(0o644);pdf.write_bytes(pdf.read_bytes()+b' future metadata')
    assert not audit_case(path)['pass']


@pytest.mark.skipif(sys.platform!='darwin' or not shutil.which('sandbox-exec'),reason='macOS isolation integration')
def test_os_denies_reference_and_other_tenant_but_allows_staged_sources():
    from benchmarks.common.isolated_runner import run_isolated
    with tempfile.TemporaryDirectory(prefix='benchmark-case-') as temp:
        package=Path(temp)/'agent_input';package.mkdir();(package/'records.csv').write_text('value\n1\n')
        try:result=run_isolated(package,'Read source evidence',None,{'mode':'conventional','budgets':{'wall_clock_seconds':30}})
        except RuntimeError as exc:
            if 'sandbox_apply' in str(exc):pytest.skip('Outer sandbox prevents nested sandbox-exec; run this test with escalation')
            raise
        assert result['isolation_audit']['pass']
        assert any('unauthorized-tenant.txt' in p for p in result['isolation_audit']['denied_read_probes'])
        assert result['records'][0]['values']['value']=='1'


def test_full_prime_adapter_reuses_real_ingestion_for_both_source_formats(tmp_path,monkeypatch):
    pytest.importorskip('polars');pytest.importorskip('pandera')
    from benchmarks.common.full_agent_adapter import FullManufacturingOS
    from benchmarks.common.agent_adapter import InvestigationInput
    from src.prime_runtime.harness import PrimeManufacturingHarness
    class SDKFixture:
        def __init__(self,store):self.store=store
        def run(self,**request):
            ids=[row['id'] for row in self.store.visible(scopes=('evaluation',),as_of=request['as_of'],limit=1)]
            assert ids
            return {'assessment':'Fixture report; not a product accuracy result.','evidence_ids':ids,
                    'causal_hypotheses':[],'actions_now':[],'workflow':{},'rollout_metrics':{}}
    monkeypatch.setattr(PrimeManufacturingHarness,'from_env',classmethod(lambda cls,**kwargs:SDKFixture(kwargs['store'])))
    adapter=FullManufacturingOS()
    for benchmark in ('cho','fresenius'):
        folder=tmp_path/benchmark;folder.mkdir()
        if benchmark=='cho':
            from openpyxl import Workbook
            book=Workbook();book.active.append(['Time (h)','Reading (g/L)']);book.active.append([0,1.25]);book.save(folder/'experiment.xlsx')
        else:(folder/'records.csv').write_text('batch_id,numerical_result\nB-1,1.25\n')
        result=adapter.run_investigation(InvestigationInput(folder,'Investigate supplied evidence',configuration={
            'case_id':'fixture','run_id':benchmark,'evaluation_time':'2099-01-01T00:00:00Z','access_scope':'evaluation'}))
        assert result['mode']=='full_rlm'
        assert result['ingestion']['files_indexed']==1
        assert result['citations'][0]['source']['row']==2


def test_filename_challenge_preserves_measurements_and_hidden_mapping(tmp_path):
    from benchmarks.common.case_protocol import prepare_case
    raw=prepare_case('fresenius','FRE-02',destination=tmp_path/'raw')
    variant=prepare_case('fresenius','FRE-02',condition='held_out',destination=tmp_path/'variant')
    assert audit_case(variant)['pass']
    raw_case=load_case(raw);challenge=load_case(variant)
    assert raw_case['package_sha256']!=challenge['package_sha256']
    assert challenge['generalization_claim_eligible'] is False
    transform=json.loads((variant.parent/'transform.json').read_text())
    for original,renamed in transform['files'].items():
        assert digest(raw.parent/'agent_input'/original)==digest(variant.parent/'agent_input'/renamed)
    assert not (variant.parent/'agent_input/transform.json').exists()


def test_setup_is_allocated_across_actual_conditions_without_silent_omission(tmp_path):
    from benchmarks.common.case_report import summarize_runs
    case,_,policy=fixture_case(tmp_path)
    runs=[artifact(case,policy,'raw'),artifact(copy.deepcopy(case),policy,'update')]
    runs[1]['condition']='updated';runs[1]['case']['condition']='updated'
    for run in runs:run['qualification']={'status':'qualified','qualified':True,'quality_score':3};run['wall_clock_seconds']=1
    logs=measured_logs(runs)
    logs['setup_groups']=[{'run_ids':['raw','update'],'active_seconds':3600,'measured_case_count':2,
                          'allocation':'equal','evidence_ref':'observed-setup','time_source':'observed'}]
    summary=summarize_runs(runs,logs)
    for condition in ('raw','updated'):
        group=summary['cohorts']['fresenius'][condition]['effort']['groups']['full_rlm']
        assert group['total_human_hours_all_attempts']==pytest.approx(.5+7/60)


def test_clean_diagnostic_retains_source_values_and_stays_separate_from_raw(tmp_path):
    from benchmarks.common.case_protocol import prepare_case
    path=prepare_case('fresenius','FRE-02',condition='clean',destination=tmp_path/'clean')
    case=load_case(path)
    assert case['condition']=='clean'
    assert case['condition_status']=='ready'
    assert all(r['path'].endswith('.csv') or r['path']=='package_manifest.json' for r in case['allowlist'])
    assert audit_case(path)['pass']


def test_active_timer_pauses_and_keeps_human_stages_separate(tmp_path):
    from benchmarks.common.human_work import ActiveWorkTimer,import_trace
    sink=TraceSink(tmp_path/'human.jsonl','fixture','run-1')
    timer=ActiveWorkTimer(sink,participant_id='fixture-operator',effort_stage='verification')
    timer.action();timer.pause()
    with pytest.raises(ValueError):timer.action()
    timer.resume();event=timer.stop()
    assert event['actor']=='human' and len(event['active_intervals'])==2
    assert event['manual_actions']==1
    ledger=import_trace(tmp_path/'human.jsonl',['run-1'])
    assert ledger['runs'][0]['phases']['verification']['manual_actions']==1
    assert ledger['runs'][0]['phases']['data_preparation']['active_seconds'] is None


def test_review_cannot_accept_deliverable_absent_from_output(tmp_path):
    case,_,policy=fixture_case(tmp_path);run=artifact(case,policy)
    run['output']['analysis'].pop('assessment')
    assert score_review(run,policy,review(run,policy))['qualified'] is False


def test_publisher_value_without_raw_observation_is_na_not_agent_failure(tmp_path):
    case,reference,_=fixture_case(tmp_path)
    (tmp_path/'agent_input/records.csv').write_text('record_id,batch_id,value\nR-1,B-1,\nR-2,B-2,0.25\n')
    scores=score_objective({'files':[{'path':'records.csv'}],'records':[]},reference,case,tmp_path/'agent_input')
    field=scores['data_preparation']['field_accuracy']
    assert field['checked']==0 and field['reference_unavailable']==1
    assert field['value'] is None


def test_invalid_citation_cannot_receive_critical_evidence_credit(tmp_path):
    case,reference,_=fixture_case(tmp_path)
    prediction=output();prediction['citations'][0]['source']['row']=1000
    scores=score_objective(prediction,reference,case,tmp_path/'agent_input')
    assert scores['evidence']['critical_evidence_recall']['value']==0
    assert scores['evidence']['citation_location_validity']['value']==0


def test_disagreement_stays_visible_after_adjudication(tmp_path):
    case,reference,policy=fixture_case(tmp_path);run=artifact(case,policy)
    checked=review(run,policy);second=copy.deepcopy(checked['reviewers'][0]);second['reviewer_id']='second-reviewer'
    second['scores']={d:4 for d in policy['dimensions']};checked['reviewers'].append(second)
    checked['adjudication']=None
    assert score_review(run,policy,checked)['qualified'] is None
    checked['adjudication']={'reviewer_id':'third-reviewer','evidence_ref':'adjudicated-review','scores':{d:3 for d in policy['dimensions']}}
    result=score_review(run,policy,checked)
    assert result['qualified'] is True and result['adjudicated'] is True
    assert result['review_agreement'] is False
