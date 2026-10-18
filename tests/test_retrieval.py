import json
import numpy as np
import pytest
from src.manufacturing_data import ManufacturingStore,ManufacturingTools,ingest_package
from src.manufacturing_data.terminology import canonical

@pytest.fixture
def data(tmp_path):
    package=tmp_path/'package';package.mkdir()
    (package/'data.csv').write_text('batch_id,Time (h),VCD (cells/mL),Glucose (g/L),notes,Status,available_at\n'
        'B1,0,10,5,contamination investigated,Ok,2024-01-01T00:00:00Z\n'
        'B1,2,20,3,contamination contamination confirmed,Warning,2024-01-01T00:00:00Z\n'
        'B2,4,30,1,future contamination,Ok,2025-01-01T00:00:00Z\n')
    store=ManufacturingStore(tmp_path/'store');ingest_package(package,store,access_scope='tenant_a')
    tools=ManufacturingTools(store,scopes=('tenant_a',),as_of='2024-06-01T00:00:00Z')
    return package,store,tools

def test_structured_alias_filters_and_time_provenance(data):
    _,_,tools=data
    r=tools.search_evidence(query='viable cell density',entity_id='B1',time_min=1,time_max=3,time_basis='elapsed_hours')
    assert r['retrieval_route']=='structured'
    assert [o['value_number'] for o in r['records']]==[20]
    assert all(o['source_ref']['row']==3 for o in r['records'])
    assert r['records'][0]['time_evidence_id'] in r['evidence_ids']
    assert len(r['evidence_ids'])==2
    assert tools.search_evidence(query='glc',entity_id='B1')['records'][0]['name']=='Glucose (g/L)'

def test_exact_and_no_scope_or_cutoff_bypass(data):
    _,store,tools=data
    identifier=tools.search_evidence(query='vcd')['records'][0]['id']
    assert tools.search_evidence(query=identifier)['records'][0]['id']==identifier
    assert not tools.search_evidence(query=identifier,source_id='unknown')['records']
    hidden=ManufacturingTools(store,scopes=('tenant_a',)).search_evidence(query='vcd',entity_id='B2')['records'][0]['id']
    assert not tools.search_evidence(query=hidden)['records']
    assert not ManufacturingTools(store,scopes=('tenant_b',)).search_evidence(query=identifier)['records']
    for kwargs in [{'as_of':None},{'as_of':'2026-01-01T00:00:00Z'},{'scopes':['tenant_b']}]:
        with pytest.raises(PermissionError):tools.search_evidence(query='contamination',**kwargs)

def test_fts_ranking_pagination_and_metadata_exclusion(data):
    _,store,tools=data
    r=tools.search_evidence(query='contamination',evidence_type='narrative')
    assert len(r['records'])==2
    assert r['records'][0]['source_ref']['row']==3
    assert all(o['name']=='notes' for o in r['records'])
    assert tools.search_evidence(query='contamination',limit=1,offset=1)['records']==r['records'][1:]
    assert tools.search_evidence(query='contamination')['evidence_ids']==r['evidence_ids']
    assert not ManufacturingTools(store,scopes=('tenant_b',)).search_evidence(query='contamination')['records']
    assert tools.search_evidence(query='Ok',metric='Status',evidence_type='structured')['records']
    status=tools.search_evidence(query='Status',value_text='Warning')['records']
    assert len(status)==1 and status[0]['source_ref']['row']==3
    with tools._retrieval.connect() as con:
        assert not con.execute("SELECT 1 FROM documents WHERE name IN ('Status','VCD (cells/mL)')").fetchone()

def test_text_index_updates_and_removes_old_version(data):
    package,_,tools=data
    assert tools.search_evidence(query='contamination')['records']
    (package/'data.csv').write_text('batch_id,notes,available_at\nB1,cleaning completed,2024-01-01T00:00:00Z\n')
    ingest_package(package,tools.store,access_scope='tenant_a')
    assert not tools.search_evidence(query='contamination')['records']
    assert tools.search_evidence(query='cleaning')['records']

def test_semantic_persistence_incremental_updates_and_scope(data):
    package,store,tools=data
    tools.search_evidence(query='contamination')
    class Model:
        def __init__(self):self.calls=[]
        def embed(self,texts):
            texts=list(texts);self.calls.append(texts)
            return iter([np.array([1,1 if 'contamination' in t else 0],dtype=np.float32) for t in texts])
    model=Model();tools._retrieval._model=model
    r=tools.search_evidence(query='infection',mode='semantic')
    assert len(r['records'])==2
    assert len(model.calls[0])==2 # future text must not be embedded
    tools.search_evidence(query='infection',mode='semantic')
    assert [len(x) for x in model.calls]==[2,1,1]
    other=ManufacturingTools(store,scopes=('tenant_a',),as_of=tools.as_of)
    other.search_evidence(query='contamination');other._retrieval._model=model
    other.search_evidence(query='infection',mode='hybrid')
    assert len(model.calls[-1])==1 # persisted across tool instances
    (package/'data.csv').write_text('batch_id,notes,available_at\nB1,new cleaning,2024-01-01T00:00:00Z\n')
    ingest_package(package,store,access_scope='tenant_a')
    r=tools.search_evidence(query='infection',mode='semantic')
    assert r['records'][0]['value_text']=='new cleaning'
    assert model.calls[-2]==['new cleaning']

def test_schema_sampling_is_repeatable_and_canonical_is_conservative(data):
    _,_,tools=data
    a=tools.inspect_data();assert a['evidence_ids']==tools.inspect_data()['evidence_ids']
    assert canonical('DO',None)['status']=='ambiguous'
    assert canonical('DO (%)','%')['canonical_name']=='dissolved_oxygen'
    assert canonical('dCO2 (mmHg)','mmHg')['canonical_name']=='dissolved_carbon_dioxide'
    mappings=tools.infer_schema()['mappings']
    assert next(m for m in mappings if m['source_name']=='VCD (cells/mL)')['terminology'][0]['canonical_name']=='viable_cell_density'

def test_readonly_and_input_validation(data):
    _,_,tools=data
    with pytest.raises(ValueError):tools.search_evidence(query='vcd',time_min=2,time_max=1)
    with pytest.raises(ValueError):tools.search_evidence(query='note',evidence_type='narrative',time_min=1)
    with pytest.raises(ValueError):tools.query_data(sql="SELECT * FROM observations UNION ALL SELECT * FROM read_parquet('/tmp/x')")

def test_coordinate_projection_and_exact_time_filters(data):
    _,store,tools=data
    source=store.visible_sources(scopes=('tenant_a',))[0]['id']
    r=tools.search_evidence(query='vcd',source_id=source,source_row=3)
    assert len(r['records'])==1 and r['records'][0]['value_number']==20
    assert not tools.search_evidence(query=r['records'][0]['id'],time_min=3)['records']
    assert tools.search_evidence(query=source)['retrieval_route']=='structured'

def test_mixed_numeric_text_and_legacy_document_ids(data):
    package,store,tools=data
    (package/'mixed.csv').write_text('batch_id,result,available_at\nB1,12,2024-01-01T00:00:00Z\nB1,unexpected contamination,2024-01-01T00:00:00Z\n')
    ingest_package(package,store,access_scope='tenant_a')
    r=tools.search_evidence(query='unexpected',evidence_type='narrative')
    assert len(r['records'])==1 and r['records'][0]['name']=='result'
    from src.manufacturing_data.models import Observation,SourceRef
    source=store.visible_sources(scopes=('tenant_a',))[0]['id']
    store.add_observations([Observation(observation_id='legacy-document',
        source=SourceRef(source_id=source,path='notes.txt'),name='document_text',
        value_text='unexpected maintenance',available_at='2024-01-01T00:00:00Z',
        access_scope='tenant_a',extraction_method='text')])
    assert tools.search_evidence(query='legacy-document')['search_method']=='exact_id'
    r=tools.search_evidence(query='maintenance',evidence_type='narrative')
    assert r['records'][0]['id']=='legacy-document'
