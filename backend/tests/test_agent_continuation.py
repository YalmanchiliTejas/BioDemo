import importlib.util
from pathlib import Path


def test_only_proven_unexecuted_cases_may_resume():
    path=Path(__file__).resolve().parents[1]/'scripts/continue_agent_accuracy.py'
    spec=importlib.util.spec_from_file_location('agent_continuation',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    blocked=[{'role':'assistant','content':[],'usage':{'input':0,'output':0,'cacheRead':0}}]
    assert module.eligible(blocked,'Campaign admission cap reached')
    assert not module.eligible(blocked,'Agent output was malformed')
    assert not module.eligible([{'role':'assistant','content':[],'usage':{'input':10}}],'Campaign admission cap reached')
    assert not module.eligible([{'role':'assistant','content':[{'type':'text','text':'prediction'}],'usage':{}}],'Campaign admission cap reached')
