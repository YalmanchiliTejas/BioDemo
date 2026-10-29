"""Authenticated, additive routes in the existing physical-model namespace."""
from fastapi import Depends, Header
from .schemas import EvaluateIn, ReviewIn

def install_fermentation_api(p,app,ctx_dep,idempotent):
    @app.get('/v1/process-model/fermentation/projects')
    def projects(site_id: str='NF1',ctx=Depends(ctx_dep)):
        return p.fermentation.projects(ctx,site_id)
    @app.post('/v1/process-model/fermentation/projects/{case_id}/evaluate')
    def evaluate(case_id: str,body:EvaluateIn,ctx=Depends(ctx_dep),key:str|None=Header(None,alias='Idempotency-Key')):
        return idempotent(ctx,key,'fermentation:'+case_id,body.model_dump(),lambda:p.fermentation.evaluate(ctx,case_id,body))
    @app.post('/v1/process-model/fermentation/projects/{case_id}/agent-assessment')
    def agent(case_id:str,body:EvaluateIn,ctx=Depends(ctx_dep),key:str|None=Header(None,alias='Idempotency-Key')):
        return idempotent(ctx,key,'fermentation-agent:'+case_id,body.model_dump(),lambda:p.fermentation.agent_assessment(ctx,case_id,body.site_id,body.assumptions.model_dump()))
    @app.get('/v1/process-model/fermentation/results/{result_id}')
    def get(result_id:str,ctx=Depends(ctx_dep)):
        return p.fermentation.get(ctx,result_id)
    @app.post('/v1/process-model/fermentation/results/{result_id}/review')
    def review(result_id:str,body:ReviewIn,ctx=Depends(ctx_dep),key:str|None=Header(None,alias='Idempotency-Key')):
        return idempotent(ctx,key,'fermentation-review:'+result_id,body.model_dump(),lambda:p.fermentation.review(ctx,result_id,body.owner_id))
