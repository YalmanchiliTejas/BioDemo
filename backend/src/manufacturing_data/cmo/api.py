"""Local demo API mounted in the existing application; no arbitrary server paths."""
from __future__ import annotations

import csv
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

from .pipeline import CONFIGURATIONS, IngestionService, digest


class RunInput(BaseModel):
    package_id: str
    configuration: str = 'clairic_decisions'


class TemplateInput(BaseModel):
    fingerprint: str
    mapping: dict
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    origin: Literal['human','study_protocol'] = 'human'


class ReviewInput(BaseModel):
    measurement_id: str
    binding: str
    decision: str
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    value: str | None = None
    parameter: str | None = None
    unit: str | None = None
    batch: str | None = None
    time: str | None = None


class DispositionInput(BaseModel):
    issue_id: str
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ActivityInput(BaseModel):
    session_id: str
    screen: str
    action: str


def router(repository: Path):
    from .settings import load_local_settings
    load_local_settings()
    def authorize(request:Request,x_cmo_token: str | None = Header(default=None),x_tenant_id:str=Header(default='demo-cdmo')):
        import secrets
        expected=os.getenv('CMO_API_TOKEN')
        if expected and (not x_cmo_token or not secrets.compare_digest(expected,x_cmo_token)):
            raise HTTPException(401,'CMO API token required')
        # Case-owned source/review/export routes must not bypass case isolation.
        parts=request.url.path.split('/')
        if 'runs' in parts:
            index=parts.index('runs')
            if len(parts)>index+1:
                try: owner=service.get(parts[index+1]).get('project_tenant')
                except KeyError: owner=None
                if owner and owner!=x_tenant_id: raise HTTPException(404,'Run unavailable in this customer context')
    api=APIRouter(prefix='/api/cmo-ingestion',dependencies=[Depends(authorize)])
    root=Path(os.getenv('CMO_INGESTION_ROOT',str(repository/'.cache'/'cmo-ingestion')))
    packages=Path(os.getenv('CMO_PACKAGES_ROOT',str(repository/'benchmarks'/'cmo_ingestion'/'generated')))
    service=IngestionService(root)
    jobs={}; activity={}; lock=threading.RLock()

    def guard(function):
        try: return function()
        except KeyError as exc: raise HTTPException(404,str(exc)) from exc
        except (ValueError,PermissionError) as exc: raise HTTPException(400,str(exc)) from exc

    def catalog():
        entries=json.loads((packages/'catalog.json').read_text()) if (packages/'catalog.json').exists() else []
        uploads=root/'uploads'
        for file in sorted(uploads.glob('*/delivery.json')):
            entries.append(json.loads(file.read_text()))
        return entries

    def find(package_id):
        item=next((i for i in catalog() if i['id']==package_id),None)
        if not item: raise KeyError('Unknown package')
        if package_id.startswith('upload-'): path=root/'uploads'/package_id/'raw.zip'
        else:
            if Path(package_id).name!=package_id: raise ValueError('Invalid package ID')
            path=packages/package_id/'raw'
        return item,path

    @api.get('/catalog')
    def list_packages():
        return {'packages':catalog(),'configurations':CONFIGURATIONS,
                'availability':{c:service.availability(c,synthetic=True) for c in CONFIGURATIONS},
                'deployment':'Local demonstration. Set CMO_API_TOKEN before exposing beyond loopback.'}

    @api.post('/runs')
    def start(value:RunInput):
        item,path=guard(lambda:find(value.package_id))
        if value.configuration not in CONFIGURATIONS: raise HTTPException(400,'Unknown configuration')
        run_id=uuid.uuid4().hex
        with lock: jobs[run_id]={'id':run_id,'status':'queued','stages':[]}
        def worker():
            def stage(event):
                with lock: jobs[run_id]['stages'].append(event); jobs[run_id]['status']='running'
            try:
                result=service.run(path,item['cmo'],value.configuration,synthetic=item['synthetic'],
                                   run_id=run_id,on_stage=stage)
                result.update(package_id=item['id'],disclosure=item['disclosure']); service.save(result)
                with lock: jobs[run_id]={'id':run_id,'status':result['status'],'stages':result['stages']}
            except Exception as exc:
                with lock: jobs[run_id].update(status='failed',error=f'{type(exc).__name__}: {exc}')
        threading.Thread(target=worker,daemon=True,name='cmo-ingestion-'+run_id[:8]).start()
        return {'id':run_id,'status':'queued'}

    @api.get('/runs/{run_id}')
    def get_run(run_id:str):
        with lock: job=jobs.get(run_id)
        if job and job['status'] in {'queued','running'}: return job
        if job and job['status']=='failed' and 'error' in job: return job
        result=guard(lambda:service.get(run_id))
        # Private store paths are not a public API field.
        result.pop('store',None)
        for m in result['measurements']: m['review_binding']=digest(m)
        return result

    @api.post('/runs/{run_id}/templates')
    def confirm(run_id:str,value:TemplateInput):
        return guard(lambda:service.confirm_template(run_id,value.fingerprint,value.mapping,value.actor,value.reason,origin=value.origin))

    @api.post('/runs/{run_id}/reviews')
    def review(run_id:str,value:ReviewInput):
        result=guard(lambda:service.review(run_id,value.measurement_id,value.decision,value.actor,value.reason,
                        binding=value.binding,value=value.value,parameter=value.parameter,unit=value.unit,batch=value.batch,time_value=value.time))
        return {'summary':result['summary']}

    @api.post('/runs/{run_id}/issues')
    def disposition(run_id:str,value:DispositionInput):
        result=guard(lambda:service.resolve_issue(run_id,value.issue_id,value.actor,value.reason))
        return {'summary':result['summary']}

    @api.get('/runs/{run_id}/sources/{source_id}')
    def source(run_id:str,source_id:str):
        path,doc=guard(lambda:service.original(run_id,source_id))
        return FileResponse(path,filename=doc['path'],content_disposition_type='inline')

    @api.get('/runs/{run_id}/cells/{measurement_id}')
    def cell(run_id:str,measurement_id:str):
        run=guard(lambda:service.get(run_id)); m=next((m for m in run['measurements'] if m['id']==measurement_id),None)
        if not m: raise HTTPException(404,'Unknown measurement')
        path,doc=guard(lambda:service.original(run_id,m['source_id'])); ref=m['source']
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
        return {'source':ref,'headers':headers,'values':values,'source_sha256':doc['sha256']}

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
                                    headers={'X-Page-Width':str(width),'X-Page-Height':str(height)})
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
                     'X-Open-Issues':str(run['summary']['open_issues'])})

    @api.get('/runs/{run_id}/verified')
    def verified(run_id:str):
        run=guard(lambda:service.get(run_id))
        if run['status']!='complete' or not run.get('summary',{}).get('verified_package'):
            raise HTTPException(409,'Package still requires verification; downstream consumption is blocked')
        measurements=[m for m in run['measurements'] if m['status'] in {'auto_accepted','accepted','corrected'}]
        for sid in {m['source_id'] for m in measurements}: guard(lambda:service.original(run_id,sid))
        return {'schema_version':'verified-cmo-1','run_id':run_id,'cmo':run['cmo'],'verified':True,
                'measurements':measurements,'relationships':run.get('relationships',[])}

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
            run=service.get(run_id)
            run['human_minutes']=(run['human_minutes'] or 0)+seconds/60
            run['human_time_status']='observed_interaction_partial; not a completed human study'
            service.audit('human_activity',run_id=run_id,screen=value.screen,action_name=value.action,
                          session_id=value.session_id,credited_seconds=seconds)
            service.save(run)
        return {'human_minutes':run['human_minutes'],'status':run['human_time_status']}

    @api.get('/comparison')
    def comparison():
        report=Path(os.getenv('CMO_REPORT_PATH',str(repository/'results'/'cmo_ingestion'/'report.json')))
        return json.loads(report.read_text()) if report.exists() else {'results':[],'human_study':'No executed benchmark report is available. Run the evaluator first.'}

    @api.get('/audit')
    def audit(): return {'valid':service.verify_audit()}

    return api
