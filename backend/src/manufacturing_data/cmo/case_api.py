"""Shared case API; mounted in the existing application with its identity adapter."""
from __future__ import annotations

import os
import secrets
import zipfile
from pathlib import Path

from fastapi import APIRouter,Depends,Header,HTTPException,Request
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field

from .cases import CaseService


class ProjectInput(BaseModel):
    name:str=Field(min_length=1,max_length=200)


class CaseInput(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    problem:str=Field(min_length=1,max_length=8000)


class AnalysisInput(BaseModel):
    starter:str='batch_comparison'
    parameters:list[str]=Field(default_factory=list)


class FindingReviewInput(BaseModel):
    finding_id:str
    decision:str
    reason:str=Field(min_length=1,max_length=4000)
    version:str


class ActionInput(BaseModel):
    title:str
    owner:str
    rationale:str
    evidence:list[str]=Field(default_factory=list)


class ActionStatusInput(BaseModel):
    status:str
    reason:str=Field(min_length=1,max_length=4000)


class WatchInput(BaseModel):
    path:str
    settle_seconds:int=Field(10,ge=2,le=3600)


def case_router(service:CaseService,identity):
    def token(x_cmo_token:str|None=Header(default=None)):
        configured=os.getenv('CMO_API_TOKEN')
        if configured and (not x_cmo_token or not secrets.compare_digest(configured,x_cmo_token)):
            raise HTTPException(401,'API token required')
    api=APIRouter(prefix='/api/pharma',dependencies=[Depends(token)])

    def guard(call):
        try:return call()
        except KeyError as exc:raise HTTPException(404,str(exc)) from exc
        except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
        except (ValueError,RuntimeError,zipfile.BadZipFile) as exc:raise HTTPException(409,str(exc)) from exc

    @api.get('/projects')
    def projects(access=Depends(identity)):return service.projects(access.tenant_id)

    @api.post('/projects')
    def create_project(value:ProjectInput,access=Depends(identity)):return guard(lambda:service.create_project(access.tenant_id,value.name))

    @api.get('/projects/{project_id}/cases')
    def cases(project_id:str,access=Depends(identity)):return guard(lambda:service.cases(project_id,access.tenant_id))

    @api.post('/projects/{project_id}/cases')
    def create_case(project_id:str,value:CaseInput,access=Depends(identity)):return guard(lambda:service.create_case(project_id,access.tenant_id,value.title,value.problem))

    @api.get('/cases/{case_id}')
    def detail(case_id:str,access=Depends(identity)):
        def load():
            case=service.case(case_id,access.tenant_id)
            snapshot=service.snapshot(case_id,access.tenant_id)
            return {'case':case,'imports':service.imports(case_id,access.tenant_id),
                    'runs':service.jobs(case_id,access.tenant_id),'actions':service.actions(case_id,access.tenant_id),
                    'data_gaps':snapshot['gaps'],'verified_parameters':sorted({m['parameter'] for m in snapshot['measurements']})}
        return guard(load)

    async def import_request(case_id,request,filename,access):
        guard(lambda:service.case(case_id,access.tenant_id))
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>64*1024*1024:raise HTTPException(413,'Upload limit is 64 MiB')
        return guard(lambda:service.import_bytes(case_id,access.tenant_id,filename,bytes(data)))

    @api.post('/cases/{case_id}/files')
    async def upload(case_id:str,request:Request,filename:str,access=Depends(identity)):
        return await import_request(case_id,request,filename,access)

    @api.post('/package-upload/{case_id}')
    async def package_upload(case_id:str,request:Request,filename:str,x_cmo_token:str|None=Header(default=None),access=Depends(identity)):
        # Machine transport is always authenticated, even when the loopback web
        # demo uses its existing development identity without a configured token.
        if not os.getenv('CMO_API_TOKEN') or not x_cmo_token:raise HTTPException(503,'Administrator must configure CMO_API_TOKEN for package-upload API')
        return await import_request(case_id,request,filename,access)

    @api.post('/cases/{case_id}/analyze')
    def analyze(case_id:str,value:AnalysisInput,access=Depends(identity)):return guard(lambda:service.analyze(case_id,access.tenant_id,value.starter,value.parameters))

    @api.get('/jobs/{job_id}')
    def job(job_id:str,access=Depends(identity)):return guard(lambda:service.job(job_id,access.tenant_id))

    @api.post('/jobs/{job_id}/cancel')
    def cancel(job_id:str,access=Depends(identity)):return guard(lambda:service.cancel(job_id,access.tenant_id))

    @api.post('/jobs/{job_id}/retry')
    def retry(job_id:str,access=Depends(identity)):return guard(lambda:service.resume(job_id,access.tenant_id))

    @api.post('/jobs/{job_id}/review')
    def review(job_id:str,value:FindingReviewInput,access=Depends(identity)):
        return guard(lambda:service.review_finding(job_id,access.tenant_id,value.finding_id,value.decision,access.actor_id,value.reason,value.version))

    @api.post('/cases/{case_id}/actions')
    def action(case_id:str,value:ActionInput,access=Depends(identity)):
        return {'id':guard(lambda:service.action(case_id,access.tenant_id,value.title,value.owner,value.rationale,value.evidence,access.actor_id))}

    @api.post('/actions/{action_id}/status')
    def action_status(action_id:str,value:ActionStatusInput,access=Depends(identity)):
        return guard(lambda:service.action_status(action_id,access.tenant_id,value.status,access.actor_id,value.reason))

    @api.get('/cases/{case_id}/handoff')
    def handoff(case_id:str,access=Depends(identity)):
        content=guard(lambda:service.export(case_id,access.tenant_id))
        return Response(content,media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="investigation-{case_id}.md"'})

    @api.get('/cases/{case_id}/watches')
    def watches(case_id:str,access=Depends(identity)):
        guard(lambda:service.case(case_id,access.tenant_id))
        with service.connect() as con:return [dict(r) for r in con.execute('SELECT id,path,status,error,settle_seconds FROM pharma_watches WHERE case_id=?',(case_id,))]

    @api.post('/cases/{case_id}/watches')
    def watch(case_id:str,value:WatchInput,access=Depends(identity)):
        if not {'admin','supervisor'}&set(access.roles):raise HTTPException(403,'Administrator role required to configure a watched folder')
        return {'id':guard(lambda:service.watch(case_id,access.tenant_id,value.path,value.settle_seconds))}

    @api.get('/sample')
    def sample(access=Depends(identity)):
        # Independent labeled fixture, generated at request time, never a fake run.
        text='batch_id,elapsed_h,temperature [K],pH [pH],product [g/L]\nDEV-A,0,305,7,0\nDEV-A,2,306,7.1,2\nDEV-B,0,305,7,0\nDEV-B,2,306,6.9,1\n'
        return Response(text,media_type='text/csv',headers={'Content-Disposition':'attachment; filename="fermentation-synthetic.csv"'})

    return api
