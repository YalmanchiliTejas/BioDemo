import copy
import json
from pathlib import Path

from benchmarks.workflow_agents.campaign import answer_from, fixture, freeze, optimum, score_answer


def test_wrong_and_missing_agent_answers_cannot_pass(tmp_path):
    for family in ('investigations','deviations','ingestion','scheduling'):
        _,gold=fixture(tmp_path/family,family,1,20261031)
        assert score_answer(family,None,gold)['exact'] is False
        assert score_answer(family,{},gold)['exact'] is False
    gold={'set_key':'affected_batch_ids','expected':['batch-a','batch-b']}
    score=score_answer('investigations',{'affected_batch_ids':['batch-a','unrelated']},gold)
    assert score['classification']=={'tp':1,'fp':1,'fn':1,'precision':.5,'recall':.5,'f1':.5}
    assert not score['exact']


def test_ingestion_scores_wrong_values_and_unsafe_acceptance_as_errors():
    gold={'values':{'a':1250.,'b':2.},'review':['c']}
    answer={'measurements':[{'record_id':'a','value_mg_per_l':1.25},{'record_id':'b','value_mg_per_l':2.},
                            {'record_id':'c','value_mg_per_l':3.}], 'review_record_ids':[]}
    result=score_answer('ingestion',answer,gold)
    assert result['classification']['tp']==1 and result['classification']['fp']==2 and result['classification']['fn']==1
    assert not result['exact']


def test_schedule_reference_and_checker_reject_overlap_and_false_infeasibility():
    jobs=[{'batch_id':'a','ready_hour':0,'due_hour':15,'duration_hours':3,'predecessor':''},
          {'batch_id':'b','ready_hour':0,'due_hour':15,'duration_hours':3,'predecessor':'a'}]
    best=optimum(jobs,[4,6]);assert best['makespan']==9
    gold={'jobs':jobs,'maintenance':[4,6],'optimum':best}
    assert score_answer('scheduling',{'feasible':True,'assignments':best['assignments']},gold)['exact']
    bad=copy.deepcopy(best['assignments']);bad[1].update(start_hour=2,end_hour=5)
    score=score_answer('scheduling',{'feasible':True,'assignments':bad},gold)
    assert not score['exact'] and 'resource_overlap' in score['violations'] and 'maintenance_overlap' in score['violations']
    assert not score_answer('scheduling',{'feasible':False,'assignments':[]},gold)['exact']


def test_answer_only_comes_from_submitted_agent_output():
    assert answer_from({'observations':[{'task_answer':{'affected_batch_ids':['a']}}]}) is None
    assert answer_from({'analysis':{'observed_facts':[{'task_answer':{'affected_batch_ids':['a']}}]}})=={'affected_batch_ids':['a']}


def test_frozen_keys_are_outside_raw_inputs_and_auditable(tmp_path):
    from benchmarks.common.case_audit import audit_case
    suite=tmp_path/'suite';protocol=freeze(suite,count=1)
    assert len(protocol['cases'])==4
    for case in protocol['cases']:
        manifest=suite/case['manifest']
        assert audit_case(manifest)['pass']
        assert not list((manifest.parent/'agent_input').rglob('*answer*'))
        assert json.loads((manifest.parent/'reference.json').read_text())['answer']
