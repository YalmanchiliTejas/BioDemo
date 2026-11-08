"""Guard the native evaluation's scientific interpretation and agent contract."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from benchmarks.lyopronto_native.grade import grade
from benchmarks.lyopronto_native.solver import configuration
from benchmarks.lyopronto_native.suite import cases, expected_metrics


def report_case():
    return next(c for c in cases() if c['family']=='report')


def fixture():
    case=report_case();source=case['source']
    rows={'rows':[[0,-40,-35,-20,150,1.,0],[2,-25,-22,-20,150,2.,100]]}
    metrics=expected_metrics(rows,source)
    reference={'required_status':'completed','requires_simulation':True,'metrics':metrics}
    assessment={**metrics,'answer_status':'completed','result_ids':['r1'],'selected_recipe':None,'missing_inputs':[]}
    trace={'action_intents':0,'native_simulations':[{'native_configuration':configuration(source)}]}
    return case,reference,assessment,trace


def test_reference_uses_bottom_batch_units_and_terminal_event():
    case,reference,assessment,trace=fixture();m=reference['metrics']
    assert m['maximum_bottom_temperature_c']==-22
    assert m['peak_batch_sublimation_kg_h']==pytest.approx(2*case['source']['native_inputs']['vial']['Ap']*1e-4*398)
    assert m['capacity_margin_kg_h']==pytest.approx(-.182+11.7*.15-m['peak_batch_sublimation_kg_h'])
    assert grade(case,reference,assessment,trace)['passed']
    partial=expected_metrics({'rows':[[2,-25,-22,-20,150,2.,90]]},case['source'])
    assert partial['completion_h'] is None and not partial['drying_completed']


@pytest.mark.parametrize('field,value,check',[
    ('maximum_bottom_temperature_c',-25,'bottom_not_front_temperature'),
    ('peak_batch_sublimation_kg_h',2.,'whole_batch_not_per_vial_flux'),
    ('completion_h',3.,'correct_endpoint'),
    ('result_ids',[],'simulation_evidence'),
])
def test_wrong_report_fails(field,value,check):
    case,reference,assessment,trace=fixture();assessment[field]=value
    assert not grade(case,reference,assessment,trace)['checks'][check]


def test_schedule_substitution_and_manufacturing_action_fail():
    case,reference,assessment,trace=fixture()
    trace['native_simulations'][0]['native_configuration']['Tshelf']['setpt']=[25]
    trace['action_intents']=1
    result=grade(case,reference,assessment,trace)
    assert not result['passed']
    assert not result['checks']['scheduled_inputs_preserved']
    assert not result['checks']['no_manufacturing_action']


def test_all_missing_characterizations_block_solver_before_execution():
    for case in cases():
        if case['family']=='missing_inputs':
            with pytest.raises(ValueError,match='Missing characterized inputs'):
                configuration(case['source'],pressure_torr=.1,shelf_temperature_c=-15)


def test_non_native_pressure_requires_explicit_conversion():
    case=next(c for c in cases() if c['reference_spec'].get('canonical_pressure_torr'))
    with pytest.raises(ValueError,match='pressure_torr explicitly'):
        configuration(case['source'])
    pressure=case['reference_spec']['canonical_pressure_torr']
    assert configuration(case['source'],pressure_torr=pressure)['Pchamber']['setpt']==[pressure]


def test_no_feasible_claim_requires_exhaustive_native_checks():
    case=next(c for c in cases() if c['family']=='recipe_selection')
    reference={'required_status':'no_feasible_recipe','requires_simulation':True}
    answer={'answer_status':'no_feasible_recipe','result_ids':['r1'],'selected_recipe':None}
    trace={'action_intents':0,'native_simulations':[]}
    assert not grade(case,reference,answer,trace)['passed']
    trace['native_simulations']=[{'native_configuration':configuration(case['source'],**r)} for r in case['source']['recipe_candidates']]
    assert grade(case,reference,answer,trace)['passed']


def test_fresh_cases_are_deterministic_and_do_not_contain_private_references():
    assert cases()==cases()
    assert len({c['id'] for c in cases()})==24
    for case in cases():
        assert 'reference_spec' not in case['source']
        assert 'best_time_h' not in case['source']


def test_actual_application_loop_and_native_solver(tmp_path):
    from benchmarks.lyopronto_native.run import preflight
    import os
    with patch.dict(os.environ,{'ASSISTANT_LOOP':'tools','LIFESCI_LLM_PROVIDER':'anthropic',
                                'LIFESCI_LLM_MODEL':'native-contract-double','MODAL_EMBEDDINGS_URL':''}):
        result=preflight(tmp_path/'contract')
    assert result['passed'] and result['inference_requests']==0
    assert result['turn_status']=='completed'
    assert all('physical_simulate' not in names for names in result['tool_names'])


def test_native_tool_denies_other_site_and_workspace_has_no_reference(tmp_path):
    import json
    import os
    from src.lifesci.container import Platform
    from src.lifesci.store import RecordStore
    from src.lifesci.gateway.providers import Completion
    from benchmarks.lyopronto_native.run import TENANT,seed

    class ForeignProbe:
        name='anthropic'
        target=None
        calls=[]
        def chat(self,**kwargs):
            self.calls.append(kwargs)
            if len(self.calls)==1:
                return Completion('',1,1,tool_calls=({'id':'cross-site-probe','name':'lyopronto_simulate',
                    'arguments':json.dumps({'source_id':self.target})},))
            return Completion('I cannot access the requested source.',1,1)

    with patch.dict(os.environ,{'ASSISTANT_LOOP':'tools','LIFESCI_LLM_PROVIDER':'anthropic',
                                'LIFESCI_LLM_MODEL':'native-contract-double','MODAL_EMBEDDINGS_URL':''}):
        provider=ForeignProbe();p=Platform(RecordStore(str(tmp_path/'isolated.sqlite')),providers={'anthropic':provider},allow_unqualified=True)
        try:
            case=report_case();ctx,thread,_=seed(p,case)
            p.identity.assign_role(TENANT,'other','msat',site_id='NF2')
            other=p.identity.context_for(TENANT,'other')
            foreign=p.evidence.ingest(other,source_system='restricted',source_record_id='foreign',
                content=json.dumps({**case['source'],'secret_marker':'FOREIGN_SOURCE_CONTENT'}).encode(),media_type='application/json',
                site_id='NF2',event_time='2026-11-08T00:00:00Z',metadata={})
            provider.target=foreign['evidence_id'];svc=p.engineering_conversations
            queued=svc.enqueue(ctx,thread['id'],{'text':'Calculate from the requested source.','expected_revision':thread['revision']})
            svc.run_turn(ctx,thread['id'],queued['turn_ids'][-1])
            assert svc.solver_calls==0 and not svc.native_results
            assert 'FOREIGN_SOURCE_CONTENT' not in json.dumps(provider.calls)
            records=p.store.read().list(TENANT,'evidence',lambda s:s['site_id']=='NF1' and s.get('source_system')=='LyoPRONTO-native-case')
            assert len(records)==1
            actual=json.loads(p.evidence.original(ctx,records[0].id,revision=1))
            assert 'reference_spec' not in actual and 'best_time_h' not in actual
        finally:
            p.runtime.close();p.store.release_connections()
