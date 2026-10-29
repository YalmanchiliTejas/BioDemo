"""A lost SDK pipe must not discard the experiment's other planned attempts."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from benchmarks.external_simulators import run_agents as runner
from benchmarks.external_simulators.experiment import dump,sha


def test_unexpected_worker_failure_is_retained_and_other_arm_still_runs(tmp_path,monkeypatch):
    dataset=tmp_path/'dataset';output=tmp_path/'run'
    items=[{'case_id':f'NC-{i}','simulator':'mab','task':'prediction'} for i in (1,2)]
    dump(dataset/'public/catalogue.json',items)
    dump(dataset/'protocol.json',{'paths':{}})
    for item in items:dump(dataset/'public'/item['case_id']/'packet.json',dict(item,allowed_actions=['keep']))
    dump(dataset/'manifest.json',{'files_sha256':{str(p.relative_to(dataset)):sha(p) for p in dataset.rglob('*.json')}})
    monkeypatch.setattr(runner,'load_env_file',lambda *_:None)
    monkeypatch.setattr(runner,'hosted_research_profile',lambda:SimpleNamespace(provider='fixture',model='fixture'))
    monkeypatch.setattr(runner,'common_evidence',lambda packet:packet)
    monkeypatch.setattr(runner,'isolation',lambda *_:{'passed':True,'fixture':True})
    invoked=[]
    def attempt(dataset,output,item,arm,protocol):
        invoked.append((item['case_id'],arm))
        if (item['case_id'],arm)==('NC-1','A'):raise BrokenPipeError('Fixture: SDK closed while returning tool result')
        return {'case_id':item['case_id'],'simulator':'mab','task':'prediction','arm':arm,'repeat':1,'score':None,
            'wall_seconds':0.,'common_input_sha256':protocol['common_packet_sha256'][item['case_id']],'capability_audit':None,
            'status':'fixture_failure','physical_model_calls':0}
    monkeypatch.setattr(runner,'attempt',attempt)
    result=runner.execute(dataset,output,workers=2,repeats=1)
    assert len(result['records'])==4
    assert len(invoked)==4
    errors=[r for r in result['records'] if r['status']=='runner_error']
    assert len(errors)==1 and errors[0]['case_id']=='NC-1' and errors[0]['arm']=='A'
    assert 'BrokenPipeError' in errors[0]['error']
    assert list((output/'attempts/NC-1/repeat-01/A').glob('runner-error.json'))
