"""CMO delivery API mounted in the existing application; no arbitrary server paths."""
from __future__ import annotations

import contextvars
import csv
import hashlib
import io
import json
import os
import threading
import time
import uuid
import zipfile
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import quality
from .evidence import restore
from .persistence import set_tenant, tenant_scope
from .pipeline import CONFIGURATIONS, IngestionService, digest, hosted_inference_approved, utc
from .schema import VOCAB

ALLOWED_FILES={'.pdf','.csv','.xlsx','.xlsm','.tsv','.txt','.log','.docx','.json','.png','.jpg','.jpeg','.tif','.tiff'}
DELIVERY_LIMIT=256*1024*1024


class RunInput(BaseModel):
    package_id: str
    configuration: str = 'auto'
    # Sample packages only: run under a separate CMO workspace (for example one
    # per demo visitor) so confirmed formats from other sessions do not apply.
    cmo: str | None = Field(default=None,min_length=1,max_length=120)


class DeliveryInput(BaseModel):
    cmo: str = Field(min_length=1,max_length=120)
    name: str = Field(default='',max_length=200)


# Routine actions get a descriptive default reason; a typed note is optional.
# Rejections, corrections and dismissing missing information need a reason.
DEFAULT_REASONS={'accept':'Accepted after checking the source','template':'Confirmed column mapping',
                 'acknowledge':'Read; not process data','reprocess':'Apply confirmed mappings'}
NEEDS_REASON={'EXPECTED_DOCUMENT_MISSING','EXPECTED_PARAMETER_MISSING','BATCH_DOCUMENT_MISSING','MISSING_PAGE','MISSING_FIELD',
              'PARSE_ERROR','DUPLICATE_CONFLICT','DUPLICATE_RECORD','BATCH_MISMATCH','TIME_ORDER'}


def reason_for(kind, reason):
    reason=(reason or '').strip()
    if reason: return reason
    if kind not in DEFAULT_REASONS: raise HTTPException(400,'A reason is required for this decision')
    return DEFAULT_REASONS[kind]


class TemplateInput(BaseModel):
    fingerprint: str
    mapping: dict
    actor: str = Field(min_length=1)
    reason: str = ''
    origin: Literal['human','study_protocol'] = 'human'


class ReviewInput(BaseModel):
    measurement_id: str
    binding: str
    decision: str
    actor: str = Field(min_length=1)
    reason: str = ''
    value: str | None = None
    parameter: str | None = None
    unit: str | None = None
    batch: str | None = None
    time: str | None = None


class BulkItem(BaseModel):
    measurement_id: str
    binding: str


class BulkReviewInput(BaseModel):
    items: list[BulkItem] = Field(min_length=1,max_length=20000)
    decision: Literal['accept','reject']
    actor: str = Field(min_length=1)
    reason: str = ''


class DispositionInput(BaseModel):
    issue_id: str
    actor: str = Field(min_length=1)
    reason: str = ''
    ignore_in_future: bool = False
    also: list[str] = Field(default_factory=list,max_length=5000)


class ReprocessInput(BaseModel):
    actor: str = Field(min_length=1)
    reason: str = ''


class ActivityInput(BaseModel):
    session_id: str
    screen: str
    action: str


def safe_member(name):
    path=Path(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or path.name.startswith('.'):
        raise ValueError('Unsafe file path')
    if path.suffix.lower() not in ALLOWED_FILES: raise ValueError(f'Unsupported file type: {path.suffix or "none"}')
    return path


def check_token(supplied):
    import secrets
    expected=os.getenv('CMO_API_TOKEN')
    if expected and (not supplied or not secrets.compare_digest(expected,supplied)):
        raise HTTPException(401,'CMO API token required')


def router(repository: Path, tenant_dependency=None):
    """``tenant_dependency`` resolves the caller's platform identity when mounted in
    the platform API; standalone deployments fall back to the X-Tenant-Id header.

    Every record query is scoped to the bound tenant (row-level security on
    PostgreSQL), so another customer's runs are simply not found. The
    dependency is async so the tenant it binds is inherited by the endpoint."""
    from .settings import load_local_settings
    load_local_settings()
    if tenant_dependency is None:
        async def authorize(x_cmo_token: str | None = Header(default=None),x_tenant_id: str | None = Header(default=None)):
            check_token(x_cmo_token); set_tenant(x_tenant_id)
    else:
        async def authorize(x_cmo_token: str | None = Header(default=None),ctx=Depends(tenant_dependency)):
            check_token(x_cmo_token); set_tenant(ctx.tenant_id)
    api=APIRouter(prefix='/api/cmo-ingestion',dependencies=[Depends(authorize)])
    root=Path(os.getenv('CMO_INGESTION_ROOT',str(repository/'.cache'/'cmo-ingestion')))
    packages=Path(os.getenv('CMO_PACKAGES_ROOT',str(repository/'benchmarks'/'cmo_ingestion'/'generated')))
    demo=Path(os.getenv('CMO_DEMO_ROOT',str(repository/'benchmarks'/'cmo_ingestion'/'demo')))
    service=IngestionService(root)
    jobs={}; activity={}; lock=threading.RLock()

    # Worker threads do not survive a restart; say so instead of showing a
    # run that is "running" forever.
    for tenant in service.repo.tenants():
        with tenant_scope(tenant):
            for stale in service.repo.run_headers():
                if stale['status'] in {'queued','running'}:
                    service.repo.update_run(stale['id'],status='interrupted',
                        error='The service restarted during processing. Start the run again; no partial results were accepted.')

    def guard(function):
        try: return function()
        except KeyError as exc: raise HTTPException(404,str(exc).strip("'")) from exc
        except FileNotFoundError as exc: raise HTTPException(410,str(exc)) from exc
        except (ValueError,PermissionError) as exc: raise HTTPException(400,str(exc)) from exc

    def catalog():
        entries=[]
        for folder in [demo,packages]:
            if (folder/'catalog.json').exists():
                entries.extend({**entry,'kind':'sample','root':str(folder)} for entry in json.loads((folder/'catalog.json').read_text())
                               if not any(e['id']==entry['id'] for e in entries))
        uploads=root/'uploads'
        for file in sorted(uploads.glob('*/delivery.json')):
            entries.append({'kind':'upload',**json.loads(file.read_text())})
        entries.extend({'kind':'delivery',**item} for item in service.repo.deliveries())
        return entries

    def public_entry(item):
        return {k:v for k,v in item.items() if k!='root'}

    def delivery_folder(ident):
        if not ident.startswith('delivery-') or Path(ident).name!=ident: raise ValueError('Invalid delivery ID')
        return root/'deliveries'/ident

    def find(package_id):
        item=next((i for i in catalog() if i['id']==package_id),None)
        if not item: raise KeyError('Unknown package')
        if item.get('kind')=='delivery':
            folder=delivery_folder(package_id)
            for file in item['files']:
                restore(service.evidence,f"deliveries/{package_id}/{file['path']}",folder/file['path'],file['sha256'])
            return item,folder
        if package_id.startswith('upload-'): path=root/'uploads'/package_id/'raw.zip'
        else:
            if Path(package_id).name!=package_id: raise ValueError('Invalid package ID')
            path=Path(item.get('root',packages))/package_id/'raw'
        return item,path

    def public(run):
        run=dict(run)
        # Private store paths and the per-element ledger are not public API fields.
        run.pop('store',None); elements=run.pop('elements',None)
        run['measurements']=[{**m,'review_binding':digest(m)} for m in run.get('measurements',[])]
        if run.get('status')=='complete':
            run['review_groups']=quality.review_groups(run)
            run['guarantee']=quality.guarantee({**run,'elements':elements})
        return run

    def launch(item,path,configuration,*,supersedes=None,cmo=None):
        if configuration not in CONFIGURATIONS: raise HTTPException(400,'Unknown configuration')
        run_id=uuid.uuid4().hex
        with lock: jobs[run_id]={'id':run_id,'status':'queued','stages':[]}
        # Public datasets may use hosted extraction; customer files need the deployment approval.
        approved=bool(item.get('public_data')) or (bool(hosted_inference_approved()) and not item.get('synthetic'))
        def worker():
            def stage(event):
                with lock: jobs[run_id]['stages'].append(event); jobs[run_id]['status']='running'
            try:
                result=service.run(path,cmo or item['cmo'],configuration,synthetic=item.get('synthetic',False),approved=approved,
                                   run_id=run_id,on_stage=stage,package_ref=item['id'])
                result.update(package_id=item['id'],disclosure=item.get('disclosure'),delivery_name=item.get('name'))
                if item.get('public_data') and result.get('hosted_inference'):
                    result['hosted_inference']['basis']='public dataset (CC BY 4.0); hosted extraction permitted'
                service.save(result)
                if supersedes and result['status']=='complete': result=service.carry_over(supersedes,result)
                with lock: jobs[run_id]={'id':run_id,'status':result['status'],'stages':result['stages']}
            except Exception as exc:
                with lock: jobs[run_id].update(status='failed',error=f'{type(exc).__name__}: {exc}')
        context=contextvars.copy_context()
        threading.Thread(target=context.run,args=(worker,),daemon=True,name='cmo-ingestion-'+run_id[:8]).start()
        return {'id':run_id,'status':'queued'}

    @api.get('/catalog')
    def list_packages():
        approved=hosted_inference_approved()
        return {'packages':[public_entry(i) for i in catalog()],'configurations':CONFIGURATIONS,
                'availability':{c:service.availability(c,synthetic=True) for c in CONFIGURATIONS},
                'customer_availability':{c:service.availability(c,approved=approved) for c in ['clairic_decisions','decisions']},
                'hosted_inference_approved':approved,
                'storage':{'records':service.repo.backend,'originals':service.evidence.backend},
                'cmos':sorted({r['cmo'] for r in service.repo.run_headers()}|{i['cmo'] for i in catalog() if i.get('kind')=='delivery'}),
                'deployment':'Set CMO_API_TOKEN before exposing beyond loopback.'}

    @api.get('/vocabulary')
    def vocabulary():
        return {'parameters':[{'id':p,'unit':v['unit'],'aliases':v['aliases'],'range':list(v['range'])} for p,v in VOCAB.items()]}

    @api.post('/deliveries')
    def create_delivery(value:DeliveryInput):
        ident='delivery-'+uuid.uuid4().hex[:16]
        item={'id':ident,'cmo':value.cmo.strip(),'name':value.name.strip() or f'{value.cmo.strip()} delivery','created':utc(),
              'dataset':'customer','condition':'delivery','synthetic':False,'files':[],
              'disclosure':'Customer delivery. Synthetic status and provenance are as stated by the uploader.'}
        delivery_folder(ident).mkdir(parents=True,mode=0o700)
        service.repo.save_delivery(item); service.audit('delivery_created',delivery=item)
        return item

    @api.post('/deliveries/{delivery_id}/files')
    async def add_file(delivery_id:str,request:Request,filename:str):
        item=next((i for i in service.repo.deliveries() if i['id']==delivery_id),None)
        if not item: raise HTTPException(404,'Unknown delivery')
        folder=guard(lambda:delivery_folder(delivery_id))
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>64*1024*1024: raise HTTPException(413,'Per-file upload limit is 64 MiB')
        def unpack():
            name=Path(filename).name
            if Path(name).suffix.lower()!='.zip':
                return [(safe_member(name),bytes(data))]
            entries=[]
            with zipfile.ZipFile(io.BytesIO(bytes(data))) as archive:
                members=[m for m in archive.infolist() if not m.is_dir()]
                if len(members)>500 or sum(m.file_size for m in members)>128*1024*1024: raise ValueError('ZIP exceeds expansion limits')
                for member in members:
                    if member.flag_bits&1 or (member.external_attr>>16)&0o170000==0o120000: raise ValueError('Encrypted or linked ZIP member')
                    if Path(member.filename).name.startswith('.') or '__MACOSX' in member.filename: continue
                    entries.append((safe_member(member.filename),archive.read(member)))
            return entries
        try: entries=unpack()
        except (ValueError,zipfile.BadZipFile) as exc: raise HTTPException(400,str(exc)) from exc
        with lock:
            item=next(i for i in service.repo.deliveries() if i['id']==delivery_id)
            existing={f['path'] for f in item['files']}
            if sum(f['size'] for f in item['files'])+sum(len(b) for _,b in entries)>DELIVERY_LIMIT:
                raise HTTPException(413,'Delivery exceeds 256 MiB')
            added=[]
            for path,content in entries:
                rel=path.as_posix()
                if rel in existing: raise HTTPException(409,f'{rel} is already in this delivery; start a new delivery for a revised file')
                target=folder/rel; target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(content); target.chmod(0o400)
                sha=hashlib.sha256(content).hexdigest()
                service.evidence.put(f'deliveries/{delivery_id}/{rel}',target)
                added.append({'path':rel,'size':len(content),'sha256':sha}); existing.add(rel)
            item['files']=[*item['files'],*added]
            service.repo.save_delivery(item)
        service.audit('delivery_files_added',delivery_id=delivery_id,files=added)
        return item

    @api.post('/runs')
    def start(value:RunInput):
        item,path=guard(lambda:find(value.package_id))
        if item.get('kind')=='delivery' and not item['files']: raise HTTPException(400,'Add at least one file to the delivery first')
        if value.cmo and item.get('kind')!='sample': raise HTTPException(400,'Only sample packages can run under another CMO workspace')
        return launch(item,path,value.configuration,cmo=value.cmo.strip() if value.cmo else None)

    @api.get('/runs')
    def list_runs(cmo:str|None=None):
        result=[]
        for run in service.runs(cmo):
            result.append({k:run.get(k) for k in ['id','cmo','status','configuration','requested_configuration','started_at','completed_at',
                                                 'package_id','delivery_name','superseded_by','runtime_seconds']}
                          |{'summary':run.get('summary'),'documents':len(run.get('documents',[]))})
        return {'runs':list(reversed(result))}

    @api.get('/runs/{run_id}')
    def get_run(run_id:str):
        with lock: job=jobs.get(run_id)
        if job and job['status'] in {'queued','running'}: return job
        if job and job['status']=='failed' and 'error' in job: return job
        run=guard(lambda:service.get(run_id))
        result=public(run)
        if result.get('guarantee') is not None:
            result['guarantee']['checks'].append({'id':'audit_chain','label':'The append-only audit chain verifies end to end',
                'passed':service.verify_audit(),'detail':'hash chain over every decision in this workspace'})
            result['guarantee']['holds']=all(c['passed'] for c in result['guarantee']['checks'])
        return result

    @api.post('/runs/{run_id}/templates')
    def confirm(run_id:str,value:TemplateInput):
        return guard(lambda:service.confirm_template(run_id,value.fingerprint,value.mapping,value.actor,reason_for('template',value.reason),origin=value.origin))

    @api.post('/runs/{run_id}/reprocess')
    def reprocess(run_id:str,value:ReprocessInput):
        old=guard(lambda:service.get(run_id))
        if old.get('superseded_by'): raise HTTPException(409,f"Already reprocessed as run {old['superseded_by']}")
        item,path=guard(lambda:find(old.get('package_ref') or old.get('package_id') or ''))
        service.audit('reprocess_requested',run_id=run_id,actor=value.actor,reason=reason_for('reprocess',value.reason))
        return launch(item,path,old.get('requested_configuration') or old['configuration'],supersedes=run_id,cmo=old['cmo'])

    @api.post('/runs/{run_id}/reviews')
    def review(run_id:str,value:ReviewInput):
        reason=reason_for(value.decision,value.reason)
        result=guard(lambda:service.review(run_id,value.measurement_id,value.decision,value.actor,reason,
                        binding=value.binding,value=value.value,parameter=value.parameter,unit=value.unit,batch=value.batch,time_value=value.time))
        return {'summary':result['summary']}

    @api.post('/runs/{run_id}/reviews/bulk')
    def bulk_review(run_id:str,value:BulkReviewInput):
        reason=reason_for(value.decision,value.reason)
        return guard(lambda:service.review_many(run_id,[i.model_dump() for i in value.items],value.decision,value.actor,reason))

    @api.post('/runs/{run_id}/issues')
    def disposition(run_id:str,value:DispositionInput):
        run=guard(lambda:service.get(run_id))
        issue=next((i for i in run['issues'] if i['id']==value.issue_id),None)
        kind='needs_reason' if issue and issue['rule_code'] in NEEDS_REASON else 'acknowledge'
        reason=reason_for(kind,value.reason)
        result=guard(lambda:service.resolve_issue(run_id,value.issue_id,value.actor,reason,ignore_in_future=value.ignore_in_future,also=value.also))
        return {'summary':result['summary']}

    @api.get('/runs/{run_id}/sources/{source_id}')
    def source(run_id:str,source_id:str):
        path,doc=guard(lambda:service.original(run_id,source_id))
        return FileResponse(path,filename=Path(doc['path']).name,content_disposition_type='inline')

    @api.get('/runs/{run_id}/cells/{measurement_id}')
    def cell(run_id:str,measurement_id:str):
        run=guard(lambda:service.get(run_id)); m=next((m for m in run['measurements'] if m['id']==measurement_id),None)
        if not m: raise HTTPException(404,'Unknown measurement')
        path,doc=guard(lambda:service.original(run_id,m['source_id'],run=run)); ref=m['source']
        if path.suffix.lower() in {'.xlsx','.xlsm'}:
            from openpyxl import load_workbook
            book=load_workbook(path,read_only=True,data_only=False)
            try:
                sheet=book[ref['sheet']]; row=ref['row']
                headers=[c.value for c in next(sheet.iter_rows(min_row=1,max_row=1))]
                values=[c.value for c in next(sheet.iter_rows(min_row=row,max_row=row))]
            finally: book.close()
        elif path.suffix.lower() in {'.csv','.tsv'}:
            with path.open(newline='',encoding='utf-8-sig') as stream:
                rows=csv.reader(stream,delimiter='\t' if path.suffix.lower()=='.tsv' else ',')
                headers=next(rows); values=next((r for i,r in enumerate(rows,2) if i==ref['row']),[])
        else: raise HTTPException(400,'Use the original PDF viewer for this measurement')
        return {'source':ref,'headers':headers,'values':[None if v is None else str(v) for v in values],'source_sha256':doc['sha256']}

    @api.get('/runs/{run_id}/pages/{source_id}/{page}')
    def page_image(run_id:str,source_id:str,page:int):
        path,_doc=guard(lambda:service.original(run_id,source_id))
        if path.suffix.lower()!='.pdf': raise HTTPException(400,'Source is not a PDF')
        import pypdfium2
        pdf=pypdfium2.PdfDocument(str(path))
        try:
            if not 1<=page<=len(pdf): raise HTTPException(400,'Page outside document')
            selected=pdf[page-1]
            try:
                width,height=selected.get_size()
                bitmap=selected.render(scale=1.5)
                try:
                    output=io.BytesIO(); bitmap.to_pil().save(output,format='PNG')
                    return Response(output.getvalue(),media_type='image/png',
                                    headers={'X-Page-Width':str(width),'X-Page-Height':str(height),'X-Page-Count':str(len(pdf))})
                finally: bitmap.close()
            finally: selected.close()
        finally: pdf.close()

    @api.get('/runs/{run_id}/export')
    def export(run_id:str,format:str='csv',wide:bool=False):
        content=guard(lambda:service.export(run_id,format=format,wide=wide))
        run=guard(lambda:service.get(run_id))
        return Response(content,media_type='text/csv' if format=='csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition':f'attachment; filename="verified-{run_id}.{format}"',
                     'X-Package-Complete':str(run['summary']['verified_package']).lower(),
                     'X-Open-Issues':str(run['summary']['open_issues']),
                     'X-Values-Pending':str(run['summary']['needs_review'])})

    def verified_payload(run_id:str,tenant:str|None=None):
        if tenant is not None:
            # Same-process callers (the platform API) pass their authenticated tenant.
            with tenant_scope(tenant): return verified_payload(run_id)
        run=guard(lambda:service.get(run_id))
        if run['status']!='complete' or not run.get('summary',{}).get('verified_package'):
            raise HTTPException(409,'Package still requires verification; downstream consumption is blocked')
        check=quality.guarantee(run)
        if not check['holds']: raise HTTPException(409,'Guarantee checks failed; downstream consumption is blocked')
        measurements=[m for m in run['measurements'] if m['status'] in {'auto_accepted','accepted','corrected'}]
        for sid in {m['source_id'] for m in measurements}: guard(lambda:service.original(run_id,sid,run=run))
        return {'schema_version':'verified-cmo-1','run_id':run_id,'cmo':run['cmo'],'verified':True,
                'package_id':run.get('package_id'),'delivery_name':run.get('delivery_name'),'completed_at':run.get('completed_at'),
                'superseded_by':run.get('superseded_by'),'disclosure':run.get('disclosure'),
                'coverage':{k:v for k,v in run['coverage'].items() if k!='by_document'},'guarantee':check,
                'measurements':measurements,'relationships':run.get('relationships',[])}

    @api.get('/runs/{run_id}/verified')
    def verified(run_id:str):
        return verified_payload(run_id)

    @api.post('/upload')
    async def upload(request:Request,dataset:str='sanofi'):
        if dataset not in {'sanofi','indpensim'}: raise HTTPException(400,'Unknown dataset')
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>64*1024*1024: raise HTTPException(413,'Demo ZIP upload limit is 64 MiB')
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members=archive.infolist()
                if len(members)>500 or sum(i.file_size for i in members)>128*1024*1024:
                    raise ValueError('ZIP exceeds demo expansion limits')
                allowed={'.pdf','.csv','.xlsx','.xlsm','.tsv','.txt','.log','.png','.jpg','.jpeg','.tif','.tiff'}
                for member in members:
                    p=Path(member.filename)
                    if p.is_absolute() or '..' in p.parts or '\\' in member.filename: raise ValueError('Unsafe ZIP path')
                    if not member.is_dir() and p.suffix.lower() not in allowed: raise ValueError('Unsupported ZIP file type')
        except (ValueError,zipfile.BadZipFile) as exc: raise HTTPException(400,str(exc)) from exc
        ident='upload-'+uuid.uuid4().hex; folder=root/'uploads'/ident; folder.mkdir(parents=True)
        (folder/'raw.zip').write_bytes(data)
        # Uploaded data is not implicitly approved for hosted inference.
        item={'id':ident,'dataset':dataset,'condition':'uploaded','cmo':dataset+'-upload',
              'synthetic':False,'disclosure':'User upload. Provenance and synthetic status have not been independently established.',
              'files':[{'path':m.filename,'size':m.file_size} for m in members if not m.is_dir()]}
        (folder/'delivery.json').write_text(json.dumps(item))
        return item

    @api.post('/runs/{run_id}/activity')
    def record_activity(run_id:str,value:ActivityInput):
        guard(lambda:service.get(run_id))
        if value.screen not in {'review','templates'} or value.action not in {'start','heartbeat','stop'}:
            raise HTTPException(400,'Invalid activity event')
        if not value.session_id or len(value.session_id)>100: raise HTTPException(400,'Invalid session ID')
        now=time.monotonic(); ident=(run_id,value.session_id)
        with lock, service._lock:
            previous=activity.get(ident)
            # Heartbeats every 10s, visibility/focus + real input required in UI.
            # Gaps >15s never count as active work. No client-supplied durations.
            seconds=(now-previous) if previous is not None and now-previous<=15 and value.action!='start' else 0
            if value.action=='stop': activity.pop(ident,None)
            else: activity[ident]=now
            with service.repo.transaction():
                run=service.get(run_id)
                minutes=(run['human_minutes'] or 0)+seconds/60
                status='observed_interaction_partial; not a completed human study'
                service.repo.update_run(run_id,human_minutes=minutes,human_time_status=status)
                service.audit('human_activity',run_id=run_id,screen=value.screen,action_name=value.action,
                              session_id=value.session_id,credited_seconds=seconds)
        return {'human_minutes':minutes,'status':status}

    @api.get('/comparison')
    def comparison():
        report=Path(os.getenv('CMO_REPORT_PATH',str(repository/'results'/'cmo_ingestion'/'report.json')))
        return json.loads(report.read_text()) if report.exists() else {'results':[],'human_study':'No executed benchmark report is available. Run the evaluator first.'}

    @api.get('/audit')
    def audit(): return {'valid':service.verify_audit()}

    # Same-process consumers (the platform API) read verified datasets without an HTTP hop.
    api.verified_payload=verified_payload
    api.ingestion_service=service
    return api
