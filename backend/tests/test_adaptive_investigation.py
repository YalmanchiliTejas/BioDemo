"""Regression tests for measured budget/coverage and report-validation failures."""
import copy
import json
import time
import pytest
from tests.test_investigation_review import case, complete_report
from src.prime_runtime.coordination import merge_report
from src.workflows.investigation_review import review_investigation
from src.workflows.claim_verification import check_claims


def test_named_reserve_transfer_and_bounded_adaptive_extension(case):
    bridge,_,_,_=case
    bridge.max_tool_calls=8;bridge.soft_tool_limit=6;bridge.lead_tool_reserve=2
    bridge.configure_execution({'mode':'adaptive_v1','soft_tool_calls':6})
    bridge.tool_calls=4
    assert bridge.tool('inspect_data',{},1)['status']=='budget_exhausted'
    task=bridge.work_queue()['tasks'][0]['task_id']
    with pytest.raises(ValueError,match='lead'):bridge.allocate_work([task],'child','Read missing source',1,caller_depth=1)
    bridge.allocate_work([task],'child','Read missing source',1)
    assert bridge.tool('inspect_data',{},1)['sources']
    assert bridge.tool_calls==5
    # Allocate a still-open unit/candidate after inspect_data supplies anchors.
    task=bridge.work_queue()['tasks'][0]['task_id']
    bridge.allocate_work([task],'lead','Finish named coverage',2,extend=True)
    assert bridge.budget()['active_tool_limit']==8
    bridge.tool_calls=8
    assert bridge.tool('inspect_data',{'limit':5})['status']=='budget_exhausted'
    # An identical earlier request is served from the run cache, not re-retrieved.
    assert bridge.tool('inspect_data',{})['cache_hit']
    assert bridge.tool_calls==8
    with pytest.raises(ValueError,match='No extension'):bridge.allocate_work([task],'lead','No extra allowance',1,extend=True)


def test_fixed_policy_and_deadline_cannot_be_extended(case):
    bridge,_,_,_=case;task=bridge.work_queue()['tasks'][0]['task_id']
    with pytest.raises(ValueError,match='fixed budget'):bridge.allocate_work([task],'lead','More work',1,extend=True)
    with pytest.raises(ValueError,match='frozen hard'):bridge.configure_execution({'mode':'fixed_v1','soft_tool_calls':4})
    bridge.configure_execution({'mode':'adaptive_v1','soft_tool_calls':4})
    bridge.time_budget_seconds=100;bridge.started_monotonic=time.monotonic()-20
    with pytest.raises(ValueError,match='finalization'):bridge.allocate_work([task],'lead','More work',1,extend=True)
    assert bridge.tool('evidence_packet',{'requests':[{'source_id':next(iter(bridge._coord().sources))}]})['status']=='finalization_required'


def test_packet_narrative_numeric_pagination_cache_and_scope(case):
    bridge,_,prepared,_=case
    sid=prepared['source_versions'][0]['source_id']
    request={'requests':[{'source_id':sid,'limit':2}]}
    first=bridge.tool('evidence_packet',request)
    packet=first['packets'][0]
    assert len(packet['records'])==2 and packet['truncated'] and packet['next_offset']==2
    assert all(r['source_ref'] for r in packet['records'])
    calls=bridge.tool_calls
    assert bridge.tool('evidence_packet',request,1)['cache_hit']
    assert bridge.tool_calls==calls and bridge.tool_history[-1]['cache_hit']
    records=bridge.tool('evidence_packet',{'requests':[{'source_id':sid,'limit':32}]})['packets'][0]['records']
    assert any(r['value_text'] for r in records) and any(r['value_number'] is not None for r in records)
    with pytest.raises(ValueError,match='outside'):bridge.tool('evidence_packet',{'requests':[{'source_id':'other-tenant'}]})
    with pytest.raises(ValueError,match='1..8'):bridge.tool('evidence_packet',{'requests':[{'source_id':sid}]*9})
    with pytest.raises(ValueError,match='1..32'):bridge.tool('evidence_packet',{'requests':[{'source_id':sid,'limit':33}]})
    assert bridge.work_queue()['convergence']['unresolved_units']==len(prepared['screening']['coverage_units'])


def test_packet_enforces_historical_visibility(tmp_path):
    from tests.test_prime_runtime import setup_case
    from src.prime_runtime.bridge import ManufacturingBridge
    store,boards,workflow,early,future=setup_case(tmp_path)
    bridge=ManufacturingBridge(store=store,blackboards=boards,workflow=workflow,
        scope='tenant_a',incident_id='packet-cutoff',objective='Review available records',
        as_of='2024-02-01T00:00:00Z',seed_ids=[early])
    sid=bridge.session.get([early])[0]['source_id']
    result=bridge.tool('evidence_packet',{'requests':[{'source_id':sid}]})
    assert early in result['evidence_ids'] and future not in result['evidence_ids']
    assert all(r['entity_id']!='B2' for r in result['packets'][0]['records'])


def test_saved_keyed_sections_and_explicit_specialist_import(case):
    bridge,_,prepared,_=case
    report=complete_report(prepared)
    bridge.save_progress({'coverage':report['coverage'][:1]})
    bridge.save_progress({'coverage':report['coverage'][1:]})
    assert len(bridge.assemble_report()['report']['coverage'])==len(report['coverage'])
    saved=json.loads(bridge.checkpoint_path.read_text())
    assert saved['coordination']['draft_report']['coverage']
    bridge.validate_report(report)
    repairs=copy.deepcopy(bridge._coord().repairs)
    bridge.submit_subreport({'subreport_id':'specialist','assessment':'Scoped finding',
        'open_questions':['Missing recipe'],'evidence_requests':[{'reason':'Need recipe'}]})
    assert bridge._coord().repairs==repairs
    assert 'Missing recipe' in bridge.assemble_report(subreport_ids=['specialist'])['report']['open_questions']
    conflicting=copy.deepcopy(report['coverage'][0]);conflicting['reason']='Different reasoning'
    bridge.submit_subreport({'subreport_id':'conflict','coverage':[conflicting]})
    # Naming a checkpoint takes its record over the lead's draft, and says so.
    imported=bridge.assemble_report(subreport_ids=['conflict'])
    assert imported['replaced_draft_entries']==[{'section':'coverage','id':conflicting['unit_id'],'subreport_id':'conflict'}]
    # Two specialists that disagree still need an explicit lead decision.
    other=copy.deepcopy(conflicting);other['reason']='A third reading'
    bridge.submit_subreport({'subreport_id':'other','coverage':[other]})
    with pytest.raises(ValueError,match='Conflicting'):bridge.assemble_report(subreport_ids=['conflict','other'])
    with pytest.raises(ValueError,match='duplicate'):merge_report({}, {'coverage':[conflicting,conflicting]})


def test_convergence_requires_reading_dispositions_and_stopping_decisions(case):
    bridge,_,prepared,_=case
    bridge.configure_execution({'mode':'adaptive_v1','soft_tool_calls':48})
    report=complete_report(prepared)
    assert bridge.validate_report(report)['report_status']=='incomplete'
    for source in prepared['source_versions']:
        bridge.tool('evidence_packet',{'requests':[{'source_id':source['source_id']}]})
    for candidate in prepared['screening']['priority_candidates']:
        bridge.stopping_decision(candidate['candidate_id'],candidate['evidence_ids'],
            'Descriptive comparison complete; mechanism unverified','Recipe review',False,False)
    review=bridge.validate_report(report)
    assert not review['issues']
    assert bridge.work_queue()['convergence']['operationally_converged']
    assert bridge.work_queue()['convergence']['scientific_qualification']=='independent_review_pending'
    candidate=prepared['screening']['priority_candidates'][0]
    bridge.stopping_decision(candidate['candidate_id'],candidate['evidence_ids'],
        'Additional data may change action','Recipe review',True,True)
    assert not bridge.work_queue()['convergence']['operationally_converged']


def timestamp_rows():
    return [{'id':'sample','source_id':'lab','entity_id':'B1','name':'sample_collected_at','value_text':'2024-01-01T01:00:00Z'},
            {'id':'review','source_id':'review','entity_id':'B2','name':'available_at','value_text':'2024-01-01T03:00:00+00:00'}]


def temporal_check(rows, **kwargs):
    return review_investigation({'temporal_claims':[{'claim_id':'T','earlier_observation_id':'sample',
        'later_observation_id':'review',**kwargs}]}, {}, rows)['temporal_claims'][0]


def test_document_timestamp_order_is_separate_from_process_alignment():
    rows=timestamp_rows();result=temporal_check(rows,clock_basis='record_timestamps')
    assert result['gap_hours']==2 and result['clock_evidence_ids']==['sample','review']
    assert result['time_basis']=='explicit_record_timestamps'
    assert 'record timestamps only' in result['limitation']
    assert temporal_check(rows,require_process_alignment=True)['verification']=='unverified_source_clock'
    rows[1]['entity_id']='B1'
    assert temporal_check(rows,require_process_alignment=True)['gap_hours']==2
    rows[1]['value_text']='2024-01-01T00:00:00Z'
    with pytest.raises(ValueError,match='contradicts'):temporal_check(rows)


@pytest.mark.parametrize('value',['2024-01-01T03:00:00','2024-01-01','Text 2024-01-01T03:00:00Z'])
def test_missing_or_ambiguous_timestamp_never_uses_availability_metadata(value):
    rows=timestamp_rows();rows[1]['value_text']=value;rows[1]['available_at']='2024-01-01T03:00:00Z'
    assert temporal_check(rows,clock_basis='record_timestamps')['verification']=='unverified_source_clock'


def test_declared_rounding_allows_only_referenced_computed_value():
    claim={'claim_id':'C','classification':'derived','statement':'Ratio was 1.557.',
        'evidence_ids':['a'],'metric_ids':['ratio'],'uncertainty':'Sampling limits',
        'missing_information':'Recipe unknown','temporal_basis':'Same source sample',
        'counterevidence_search':'No contradictory ratio found'}
    rows=[{'id':'a','value_number':1.23}];metrics=[{'metric_id':'ratio','value':1.5569620253164556}]
    assert check_claims({'claims':[claim]},rows,metrics)['issues']
    claim['display_decimals']=3
    assert not check_claims({'claims':[claim]},rows,metrics)['issues']
    claim['statement']='Ratio was 1.558.'
    assert any(i['code']=='claim_numeric_literals_unlinked' for i in check_claims({'claims':[claim]},rows,metrics)['issues'])
    claim['display_decimals']=True
    with pytest.raises(ValueError,match='display_decimals'):check_claims({'claims':[claim]},rows,metrics)


def test_numeric_literal_at_sentence_end_is_not_skipped():
    from src.workflows.claim_verification import NUMBER
    assert NUMBER.findall('Ratio was 1.557.')==['1.557']
    assert NUMBER.findall('Result 999.')==['999.']
    assert NUMBER.findall('B-123 and 2024-01-01T01:00:00Z')==[]


def test_adaptive_case_variant_preserves_frozen_inputs_and_labels(tmp_path):
    from benchmarks.common.execution_policy import freeze_execution_variant
    from benchmarks.common.case_protocol import load_case, stable_hash, digest, VERSION, save
    original=tmp_path/'original';original.mkdir()
    for name in ('reference','quality_policy','triage_policy'):save(original/(name+'.json'),{'untouched':True})
    data={'version':VERSION,'condition':'raw','budgets':{'tool_calls':48,'wall_clock_seconds':900}}
    for name in ('reference','quality_policy','triage_policy'):
        data[name]=name+'.json';data[name+'_sha256']=digest(original/(name+'.json'))
    data['task_spec_sha256']=stable_hash(data);save(original/'case.json',data)
    before=digest(original/'case.json')
    path=freeze_execution_variant(original/'case.json',tmp_path/'adaptive')
    updated=load_case(path)
    assert updated['execution_policy']=={'mode':'adaptive_v1','soft_tool_calls':48}
    assert updated['budgets']=={'tool_calls':72,'wall_clock_seconds':900}
    assert updated['parent_case_sha256']==data['task_spec_sha256']
    assert digest(original/'case.json')==before
    assert all(updated[k+'_sha256']==data[k+'_sha256'] for k in ('reference','quality_policy','triage_policy'))
    assert freeze_execution_variant(original/'case.json',tmp_path/'adaptive')==path
    with pytest.raises(ValueError,match='differs'):freeze_execution_variant(original/'case.json',tmp_path/'adaptive',hard=80)
    longer=freeze_execution_variant(original/'case.json',tmp_path/'thirty-minutes',
        soft=48,hard=48,mode='fixed_v1',wall_clock_seconds=1800)
    assert load_case(longer)['budgets']=={'tool_calls':48,'wall_clock_seconds':1800}
    assert digest(original/'case.json')==before
    with pytest.raises(ValueError,match='differs'):
        freeze_execution_variant(original/'case.json',tmp_path/'thirty-minutes',soft=48,hard=48,mode='fixed_v1',wall_clock_seconds=900)
    with pytest.raises(ValueError,match='positive'):
        freeze_execution_variant(original/'case.json',tmp_path/'invalid',wall_clock_seconds=0)


def test_public_example_excludes_audit_without_recorded_run(tmp_path):
    from scripts.build_publication import example
    audit=tmp_path/'results/verification/detached';audit.mkdir(parents=True)
    (audit/'summary.json').write_text(json.dumps({'run_id':'missing'}))
    (audit/'verification.json').write_text(json.dumps({'status':'requires_review','evidence_checks':{}}))
    assert example(tmp_path) is None
