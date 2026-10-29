"""Infrastructure recovery cannot select better scores or mix treatment pairs."""
import json
from pathlib import Path
import pytest
from benchmarks.external_simulators.experiment import dump
from benchmarks.external_simulators.challenge_transport_retry import make_view


def setup(tmp):
    original=tmp/'original';recovery=tmp/'recovery';view=tmp/'view'
    (original/'common-inputs').mkdir(parents=True);(original/'runner-source').mkdir()
    def row(case,arm,score):return {'case_id':case,'repeat':1,'arm':arm,'score':{'value':score} if score is not None else None,'model':'fixture','common_input_sha256':case}
    first=[row('NC-1','A',.99),row('NC-1','B',None),row('NC-2','A',.8),row('NC-2','B',.7)]
    second=[row('NC-1','A',.1),row('NC-1','B',.2)]
    for root,records in ((original,first),(recovery,second)):
        for r in records:(root/'attempts'/r['case_id']/'repeat-01'/r['arm']).mkdir(parents=True)
    dump(original/'results.json',{'status':'complete','records':first,'completed':3,'protocol':{'model':'fixture'}})
    dump(recovery/'results.json',{'status':'complete','records':second,'completed':2,'protocol':{'recovery_selection':'fixed connection pairs'}})
    return original,recovery,view


def test_both_retry_arms_replace_original_even_if_new_score_is_worse(tmp_path):
    original,recovery,view=setup(tmp_path)
    result=make_view(original,recovery,view)
    a=next(r for r in result['records'] if r['case_id']=='NC-1' and r['arm']=='A')
    assert a['score']['value']==.1
    assert json.loads((original/'results.json').read_text())['records'][0]['score']['value']==.99
    assert (view/'attempts/NC-1/repeat-01/A').resolve()==(recovery/'attempts/NC-1/repeat-01/A').resolve()


def test_incomplete_or_changed_input_pair_is_rejected(tmp_path):
    original,recovery,view=setup(tmp_path)
    data=json.loads((recovery/'results.json').read_text());data['records']=data['records'][:1];dump(recovery/'results.json',data)
    with pytest.raises(ValueError,match='complete pair'):make_view(original,recovery,view)
