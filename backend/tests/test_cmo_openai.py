"""Decisions contract tests with offline transport; no live API calls."""
import io
import json
import os
import pytest
from src.manufacturing_data.cmo import settings
from src.manufacturing_data.cmo.pipeline import IngestionService
from src.manufacturing_data.cmo.providers import Provider, Unavailable
from src.manufacturing_data.cmo.schema import Mapping, Classification

@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith(('OPENAI_','CMO_DECISIONS_','CLOUDFLARE_','CMO_CLAIRIC_')) or name=='CMO_ALLOWED_ORIGINS':
            monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv('OPENAI_API_KEY','test-secret')

def transport(monkeypatch,choices):
    requests=[]
    class Opener:
        def open(self,request,**_):
            requests.append(request)
            body=json.loads(request.data)
            answers=[]
            for q in body['questions']:
                value,confidence=choices[q['name']]
                answers.append({'type':'refusal','name':q['name']} if value is None else
                    {'type':'choice','name':q['name'],'choice':value,'confidence':confidence})
            return io.BytesIO(json.dumps({'model':'gpt-6-luna','answers':answers,
                'usage':{'input_tokens':100,'output_tokens':0,'input_tokens_details':{'cached_tokens':20}}}).encode())
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:Opener())
    return requests

def test_service_loads_env_local_and_shell_precedence(tmp_path,monkeypatch):
    file=tmp_path/'.env.local'
    file.write_text('OPENAI_API_KEY=file-key\nOPENAI_MODEL=gpt-6-luna\nCMO_DECISIONS_MIN_CONFIDENCE=.97\nUNRELATED_CREDENTIAL=ignored\n')
    loader=settings.load_local_settings
    monkeypatch.setattr(settings,'load_local_settings',lambda:loader(file))
    IngestionService(tmp_path/'runtime')
    provider=Provider('mapping',lambda _:None,synthetic=True)
    assert provider.url=='https://api.openai.com/v1/decisions'
    assert provider.api_key=='test-secret' and provider.threshold==.97
    assert 'UNRELATED_CREDENTIAL' not in os.environ

def test_file_key_loaded_without_shell_export(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY')
    file=tmp_path/'.env.local'; file.write_text('OPENAI_API_KEY=local-key\n')
    settings.load_local_settings(file)
    assert os.environ['OPENAI_API_KEY']=='local-key'

def test_decisions_only_contract_usage_and_secret_redaction(monkeypatch):
    monkeypatch.setenv('CMO_DECISIONS_INPUT_USD_PER_MILLION','.10')
    requests=transport(monkeypatch,{'column_0':('__batch__',.99),'column_1':('__time__',.99),'column_2':('temperature',.99)})
    receipts=[]
    result=Provider('mapping',receipts.append,synthetic=True).call('map_headers',
        {'headers':['batch_id','elapsed_h','Temp [degC]']},Mapping)
    assert result.columns=={'Temp [degC]':'temperature'} and result.batch_column=='batch_id'
    body=json.loads(requests[0].data)
    assert set(body)=={'model','input','questions'} and requests[0].full_url.endswith('/v1/decisions')
    assert requests[0].get_header('Authorization')=='Bearer test-secret'
    assert receipts[0]['cost_usd']==pytest.approx(.000008)
    assert 'test-secret' not in json.dumps(receipts)

@pytest.mark.parametrize('choice,confidence',[(None,0),('__unknown__',.99),('temperature',.8)])
def test_uncertain_answers_preserve_review(monkeypatch,choice,confidence):
    requests=transport(monkeypatch,{'column_0':(choice,confidence)})
    provider=Provider('mapping',lambda _:None,synthetic=True)
    result=provider.call('map_headers',{'headers':['Mystery [degC]']},Mapping)
    assert not result.columns and provider.last_decisions[0]['status']=='review' and len(requests)==1

@pytest.mark.parametrize('choice,confidence',[('invented_field',.99),('temperature',float('nan')),('temperature',1.5)])
def test_invalid_model_answers_rejected(monkeypatch,choice,confidence):
    requests=transport(monkeypatch,{'column_0':(choice,confidence)})
    with pytest.raises(Unavailable):
        Provider('mapping',lambda _:None,synthetic=True).call('map_headers',{'headers':['X']},Mapping)
    assert len(requests)==3

def test_classification_and_batching(monkeypatch):
    transport(monkeypatch,{'document_type':('microbiology',.99)})
    assert Provider('classification',lambda _:None,synthetic=True).call('classify',{'text':['laboratory']},Classification).doc_type=='microbiology'
    requests=transport(monkeypatch,{f'column_{i}':('__unknown__',.99) for i in range(101)})
    provider=Provider('mapping',lambda _:None,synthetic=True)
    provider.call('map_headers',{'headers':[f'X{i}' for i in range(101)]},Mapping)
    assert [len(json.loads(r.data)['questions']) for r in requests]==[100,1]
    assert len(provider.last_decisions)==101

def test_ambiguous_identifiers_are_reviewed(monkeypatch):
    transport(monkeypatch,{'column_0':('__batch__',.99),'column_1':('__batch__',.99)})
    provider=Provider('mapping',lambda _:None,synthetic=True)
    result=provider.call('map_headers',{'headers':['batch','lot']},Mapping)
    assert result.batch_column is None and all(a['status']=='review' for a in provider.last_decisions)

def test_no_legacy_provider_or_endpoint_fallback(monkeypatch):
    for role in ['jev','clairic']:
        with pytest.raises(Unavailable): Provider(role,lambda _:None,synthetic=True)
    monkeypatch.setenv('CMO_DECISIONS_URL','https://api.openai.com/v1/chat/completions')
    with pytest.raises(ValueError): Provider('mapping',lambda _:None,synthetic=True)

def test_customer_gate_and_missing_key(monkeypatch):
    with pytest.raises(Unavailable,match='Hosted inference'): Provider('mapping',lambda _:None)
    monkeypatch.delenv('OPENAI_API_KEY')
    with pytest.raises(Unavailable,match='OPENAI_API_KEY'): Provider('mapping',lambda _:None,synthetic=True)


def test_decisions_pipeline_confirmed_layout_reuses_without_any_model_calls(tmp_path,monkeypatch):
    import csv
    service=IngestionService(tmp_path/'runtime')
    monkeypatch.setattr(service,'availability',lambda *a,**k:[])
    raw=tmp_path/'raw'; raw.mkdir()
    with (raw/'unknown.csv').open('w',newline='') as f:
        writer=csv.writer(f); writer.writerow(['batch_id','elapsed_h','Temp [degC]'])
        writer.writerow(['LOCAL',0,32])
    requests=transport(monkeypatch,{'document_type':('instrument_export',.99),
        'column_0':('__batch__',.99),'column_1':('__time__',.99),'column_2':('temperature',.99)})
    run=service.run(raw,'local','decisions',synthetic=True)
    assert run['status']=='complete' and len(requests)==2
    layout=run['layouts'][0]
    assert layout['decisions'][2]['choice']=='temperature'
    service.confirm_template(run['id'],layout['fingerprint'],layout['mapping'],'qa','Checked original source')
    count=len(requests)
    returning=service.run(raw,'local','decisions',synthetic=True)
    assert returning['summary']['model_calls']==0 and len(requests)==count
    assert returning['summary']['auto_accepted']==1


def cloudflare_result(body, *, mode='valid'):
    state=body['state']; answers={}
    texts={'batch_id':'B','elapsed_hours_text':'0','measurement_label':'pH [pH]','measurement_value_text':'7'}
    for name,spec in body['fields'].items():
        if spec['type']=='text':
            text=texts[name]; start=state.index(text)
            answers[name]={'type':'text','value':text,'span':[start,start+len(text)],'confidence':.99,'p_null':.001}
        else:
            answers[name]={'type':'number','value':0 if name=='elapsed_hours' else 7,'confidence':.99,'p_null':.001}
    if mode=='span': answers['measurement_value_text']['span']=[0,1]
    if mode=='null': answers={k:{'type':v['type'],'value':None,'guess':'DO-NOT-USE'} for k,v in answers.items()}
    if mode=='low': answers['measurement_value']['confidence']=.4
    if mode=='computed': answers['measurement_value']['value']=8
    if mode=='missing_batch': answers['batch_id']['value']=None
    result={'answers':answers,'truncated':mode=='truncated','usage':{'input_tokens':100,'output_tokens':0}}
    return {'success':mode!='error','result':result}


@pytest.mark.parametrize('mode',['valid','span','null','low','computed','missing_batch','truncated','error'])
def test_clairic_native_cloudflare_contract(monkeypatch,mode):
    from src.manufacturing_data.cmo.providers import ClairicProvider
    from src.manufacturing_data.cmo.schema import Extraction
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID','test-account')
    monkeypatch.setenv('CLOUDFLARE_AUTH_TOKEN','test-cf-secret')
    monkeypatch.setenv('CMO_ALLOWED_ORIGINS','https://api.cloudflare.com')
    monkeypatch.setenv('CMO_CLAIRIC_INPUT_USD_PER_MILLION','.10')
    requests=[]; receipts=[]
    class Opener:
        def open(self,request,**_):
            requests.append(request)
            return io.BytesIO(json.dumps(cloudflare_result(json.loads(request.data),mode=mode)).encode())
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:Opener())
    provider=ClairicProvider(receipts.append,synthetic=True)
    payload={'elements':[{'evidence_id':'e1','text':'Batch: B | Hour: 0 | pH [pH]: 7'}]}
    reply=provider.call('extract',payload,Extraction)
    assert len(reply.fields)==(0 if mode in {'span','null','truncated','error'} else 1)
    assert bool(reply.reviews)==(mode!='valid')
    if reply.fields:
        assert reply.fields[0].value_raw=='7'
        if mode=='missing_batch': assert reply.fields[0].batch==''
    body=json.loads(requests[0].data)
    assert set(body)=={'model','state','fields'} and body['model']=='clairic'
    assert all(v['type']!='list' for v in body['fields'].values())
    assert requests[0].full_url=='https://api.cloudflare.com/client/v4/accounts/test-account/ai/run/@cf/cloudflare/clairic'
    assert requests[0].get_header('Authorization')=='Bearer test-cf-secret'
    if mode=='error': assert receipts[0]['cost_usd'] is None
    else: assert receipts[0]['cost_usd']==pytest.approx(.00001)
    assert 'test-cf-secret' not in json.dumps(receipts)


def test_clairic_record_failures_do_not_discard_other_records(monkeypatch):
    from src.manufacturing_data.cmo.providers import ClairicProvider
    from src.manufacturing_data.cmo.schema import Extraction
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID','test-account')
    monkeypatch.setenv('CLOUDFLARE_AUTH_TOKEN','test-cf-secret')
    monkeypatch.setenv('CMO_ALLOWED_ORIGINS','https://api.cloudflare.com')
    bodies=[]
    class Opener:
        def open(self,request,**_):
            body=json.loads(request.data); bodies.append(body)
            return io.BytesIO(json.dumps(cloudflare_result(body,mode='span' if len(bodies)==1 else 'valid')).encode())
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:Opener())
    state='Batch: B | Hour: 0 | pH [pH]: 7\nBatch: B | Hour: 0 | pH [pH]: 7'
    result=ClairicProvider(lambda _:None,synthetic=True).call('extract',{'elements':[{'evidence_id':'e1','text':state}]},Extraction)
    assert len(bodies)==2 and len(result.fields)==1 and len(result.reviews)==1
    assert result.fields[0].source_spans['measurement_value_text'][0]>state.index('\n')


def test_cloudflare_env_local_loading_and_gate(tmp_path,monkeypatch):
    from src.manufacturing_data.cmo.providers import ClairicProvider
    file=tmp_path/'.env.local'
    file.write_text('CLOUDFLARE_ACCOUNT_ID=account\nCLOUDFLARE_AUTH_TOKEN=token\nCMO_ALLOWED_ORIGINS=https://api.cloudflare.com\n')
    settings.load_local_settings(file)
    provider=ClairicProvider(lambda _:None,synthetic=True)
    assert provider.api_key=='token'
    with pytest.raises(Unavailable,match='Hosted inference'): ClairicProvider(lambda _:None)
    monkeypatch.delenv('CLOUDFLARE_AUTH_TOKEN')
    with pytest.raises(Unavailable,match='CLOUDFLARE_AUTH_TOKEN'): ClairicProvider(lambda _:None,synthetic=True)


def test_combined_pipeline_calls_clairic_for_documents(tmp_path,monkeypatch):
    import src.manufacturing_data.cmo.pipeline as pipeline
    from src.manufacturing_data.cmo.providers import ClairicProvider
    from src.manufacturing_data.cmo.schema import Extraction
    from reportlab.pdfgen.canvas import Canvas
    raw=tmp_path/'raw'; raw.mkdir()
    page=Canvas(str(raw/'batch_record.pdf'))
    page.drawString(30,700,'Batch: B | Hour: 0 | pH [pH]: 7'); page.save()
    service=IngestionService(tmp_path/'runtime')
    monkeypatch.setattr(service,'availability',lambda *a,**k:[])
    original_ingest=pipeline.ingest_package
    def native_fixture(*args,**kwargs):
        kwargs['document_backend']='pypdf'
        return original_ingest(*args,**kwargs)
    monkeypatch.setattr(pipeline,'ingest_package',native_fixture)
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID','test-account')
    monkeypatch.setenv('CLOUDFLARE_AUTH_TOKEN','test-cf-secret')
    monkeypatch.setenv('CMO_ALLOWED_ORIGINS','https://api.cloudflare.com,https://api.openai.com')
    extracted=[]
    def extract(self,task,payload,schema):
        extracted.append(payload)
        return Extraction(fields=[{'evidence_id':payload['elements'][0]['evidence_id'],
            'header':'pH [pH]','value_raw':'7','batch':'B','time':'0'}])
    monkeypatch.setattr(ClairicProvider,'call',extract)
    requests=transport(monkeypatch,{'column_0':('__batch__',.99),'column_1':('__time__',.99),'column_2':('pH',.99)})
    run=service.run(raw,'local','clairic_decisions',synthetic=True)
    assert len(extracted)==1 and len(requests)==1
    assert len(run['measurements'])==1 and run['summary']['auto_accepted']==0
    assert run['layouts'][0]['mapping']['columns']=={'pH [pH]':'pH'}


def test_clairic_unit_boundary_expansion_uses_only_adjacent_source(monkeypatch):
    from src.manufacturing_data.cmo.providers import ClairicProvider
    from src.manufacturing_data.cmo.schema import Extraction
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID','test-account')
    monkeypatch.setenv('CLOUDFLARE_AUTH_TOKEN','test-cf-secret')
    monkeypatch.setenv('CMO_ALLOWED_ORIGINS','https://api.cloudflare.com')
    class Opener:
        def open(self,request,**_):
            body=json.loads(request.data); result=cloudflare_result(body)
            label=result['result']['answers']['measurement_label']
            label['value']='pH [pH'; label['span'][1]-=1
            return io.BytesIO(json.dumps(result).encode())
    monkeypatch.setattr('urllib.request.build_opener',lambda *_:Opener())
    state='Batch: B | Hour: 0 | pH [pH]: 7'
    result=ClairicProvider(lambda _:None,synthetic=True).call('extract',{'elements':[{'evidence_id':'e1','text':state}]},Extraction)
    field=result.fields[0]
    assert field.header=='pH [pH]'
    start,end=field.source_spans['measurement_label']
    assert state[start:end]==field.header and result.reviews
    assert field.confidence['measurement_label']==.99
