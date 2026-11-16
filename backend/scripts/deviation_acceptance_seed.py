"""Synthetic originals and a deterministic local executor report for browser acceptance.

No provider transport, LLM response, citation fixture lookup or customer system is used.
The LocalExecutor runner computes registered models on the actual sealed source package.
"""
import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path


def seed(platform, output, name, packet):
    from src.lifesci.investigations import InvestigationService
    from src.lifesci.local_executor import LocalExecutor
    from src.prime_runtime.science import FrozenScience
    p=platform;tenant='demo-northfield';site='NF1';ctx=p.identity.context_for(tenant,'dev-msat')
    output=Path(output);manifest_path=output/f'{name}-manifest.json'
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    batch=f'SYN-{name}';equipment=f'SYN-V-{name}'
    spec=p.specifications.create(p.identity.context_for(tenant,'dev-qa'),site_id=site,parameter='dissolved_oxygen',unit='mg/L',low=3,
        equipment_id=equipment,duration_seconds=120,max_observation_gap_seconds=90,reason='Synthetic browser acceptance absolute DO rule')
    refs=[]
    for minute,value in enumerate([4,3.5,2.5,2.2,2]):
        fields={'batch_id':batch,'equipment_id':equipment,'parameter':'dissolved_oxygen','value':value,'unit':'mg/L','event_time':f'2026-11-15T10:{minute:02d}:00Z'}
        document={'synthetic':True,'record':fields,**(packet if minute==4 else {})}
        r=p.evidence.ingest(ctx,source_system='synthetic-historian',source_record_id=f'{name}-do-{minute}',content=json.dumps(document).encode(),
            media_type='application/json',site_id=site,event_time=fields['event_time'],source_revision='original-1',mapping_version='acceptance-1',metadata={'mapped':fields})
        refs.append({'kind':'evidence','id':r['evidence_id'],'revision':r['revision'],'site_id':site})
    signal=next(s for s in p.signals.list(ctx) if s['subject']['id']==batch)
    fields={'batch_id':batch,'equipment_id':equipment,'record_type':'calibration','status':'confirmed','certificate_id':'SYN-CAL-'+name,'calibrated_at':'2026-11-14T09:00:00Z'}
    r=p.evidence.ingest(ctx,source_system='synthetic-metrology',source_record_id=f'{name}-certificate',content=json.dumps({'synthetic':True,'record':fields}).encode(),
        media_type='application/json',site_id=site,event_time='2026-11-14T09:00:00Z',metadata={'mapped':fields})
    cal_ref={'kind':'evidence','id':r['evidence_id'],'revision':r['revision'],'site_id':site}
    metrics={'execution_mode':'deterministic registered-model runner through LocalExecutor; no Prime/LLM inference','inference':{'status':'not_run','seconds':None}}
    executor=LocalExecutor(output/f'{name}-executor')
    def deterministic_runner(job_id,job,write,cancelled,harnesses):
        started=time.perf_counter();package=(executor.root/'inputs'/f"{job['sha256']}.zip").read_bytes()
        with zipfile.ZipFile(io.BytesIO(package)) as z:
            manifest=json.loads(z.read('snapshot-manifest.json'))
        science=FrozenScience.from_package(package)
        metrics['source_retrieval_seconds']=time.perf_counter()-started
        started=time.perf_counter();runs=[science.run(key) for key in science.configurations]
        metrics['deterministic_tool_seconds']=time.perf_counter()-started
        source=next(item for item in manifest['items'] if item['id']==refs[-1]['id'])
        return {'summary':'Synthetic deterministic executor report. OTR calculation is not a DO trajectory prediction or root-cause diagnosis. No LLM inference ran.',
            'findings':[{'statement':'Source-supplied conditional oxygen calculation executed; human assessment required.','evidence_ids':['synthetic-oxygen-original']}],
            'scientific_model_runs':runs,'open_questions':['Root cause unresolved; synthetic inputs are not qualified plant evidence.'],
            'snapshot_citation_map':{'synthetic-oxygen-original':{'path':source['path'],'source_ref':{'json_pointer':'/scientific_models/0/observations/0'}}},
            'execution_disclosure':metrics}
    executor.runner=deterministic_runner
    p.investigations=InvestigationService(p,executor=executor)
    os.environ['INVESTIGATIONS_ENABLED_TENANTS']=tenant
    started=time.perf_counter()
    run=p.investigations.start(ctx,{'site_id':site,'objective':'Synthetic deterministic citation acceptance: execute declared oxygen calculation, no inference','record_refs':[refs[-1]]})
    executor._threads[run['run_id']].join(timeout=30)
    run=p.investigations.get(ctx,run['run_id'])
    assert run['status']=='awaiting_review',run
    report=p.investigations.report(ctx,run['run_id'])
    assert report['report']['scientific_model_runs'][0]['status']=='completed'
    metrics['executor_report_completion_seconds']=time.perf_counter()-started
    correction_equipment=equipment+'-CORRECTION'
    p.specifications.create(p.identity.context_for(tenant,'dev-qa'),site_id=site,parameter='dissolved_oxygen',unit='mg/L',low=3,
        equipment_id=correction_equipment,reason='Synthetic source correction and unit grouping check')
    for value,unit in [(2.,'mg/L'),(2.2,'mg/L'),(2100.,'ug/L')]:
        fields={'batch_id':batch+'-CORRECTION','equipment_id':correction_equipment,'parameter':'dissolved_oxygen','value':value,'unit':unit}
        p.evidence.ingest(ctx,source_system='synthetic-historian',source_record_id=name+'-corrected-point',content=json.dumps({'synthetic':True,'record':fields}).encode(),
            media_type='application/json',site_id=site,event_time='2026-11-15T10:05:00Z',metadata={'mapped':fields})
    correction_signal=next(s for s in p.signals.list(ctx) if s['subject']['id']==batch+'-CORRECTION')
    result={'signal_id':signal['signal_id'],'source_ref':refs[-1],'source_sha256':hashlib.sha256(p.evidence.original(ctx,refs[-1]['id'],1)).hexdigest(),
        'measurement_refs':refs,'calibration_ref':cal_ref,'batch':batch,'equipment':equipment,'specification':spec,'run_id':run['run_id'],
        'correction_signal_id':correction_signal['signal_id'],'citation_id':'synthetic-oxygen-original','metrics':metrics,'synthetic':True,'providers':[], 'api':'http://127.0.0.1:8158'}
    # Separate synthetic follow-up case: source events exercise the real preparation logic.
    recurrence_batch=batch+'-FOLLOWUP'
    def recurrence_source(label, when, status):
        fields={'batch_id':recurrence_batch,'status':status}
        r=p.evidence.ingest(ctx,source_system='synthetic-final-review',source_record_id=name+'-'+label,
            content=json.dumps({'synthetic':True,'record':fields}).encode(),media_type='application/json',
            site_id=site,event_time=when,metadata={'mapped':fields})
        return {'kind':'evidence','id':r['evidence_id'],'revision':r['revision'],'site_id':site}
    original=recurrence_source('completion','2026-01-01T00:00:00+00:00','normal')
    case_id='SYN-FOLLOWUP-'+name
    w=p.quality_workflow.create(ctx,case_id=case_id,site_id=site,title='Synthetic final-review follow-up',
        owner_id='dev-msat',qa_reviewer_id='dev-qa',associations={'batch_id':recurrence_batch},
        discovery_refs=[original],idempotency_key='seed-followup')
    def change(operation, **fields):
        w=p.quality_workflow.get(ctx,case_id)
        return getattr(p.quality_workflow,operation)(ctx,case_id,expected_revision=w['revision'],idempotency_key=operation+str(w['revision']),**fields)
    change('prepare')
    w=change('action',action={'description':'Synthetic calibration follow-up','kind':'corrective_action',
        'owner_id':'dev-msat','due_at':'2026-01-02T00:00:00+00:00'})
    action_id=w['actions'][0]['id']
    change('action',action={'id':action_id,'status':'completed','completion_refs':[original],'completed_at':'2026-01-02T00:00:00+00:00'})
    recurrence_refs={label:recurrence_source(label,when,status) for label,when,status in [
        ('normal','2026-01-03T00:00:00+00:00','normal'),
        ('preaction','2026-01-01T12:00:00+00:00','OOS'),
        ('adverse','2026-01-03T00:00:00+00:00','OOS'),('uncertain',None,'OOS')]}
    p.runtime.tick()
    result['followup']={'case_id':case_id,'action_id':action_id,'refs':recurrence_refs}
    manifest_path.write_text(json.dumps(result,indent=2));return result
