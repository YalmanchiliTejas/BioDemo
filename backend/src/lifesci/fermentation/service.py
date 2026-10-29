"""Additive domain service composed from existing evidence, flow, catalog and review services."""
import json
import hashlib
from pathlib import Path
from time import perf_counter
from ..evidence import EvidenceRef
from ..ids import content_hash, new_id
from ..process_engineering.catalog import ModelCatalog
from ..process_engineering.engine import SolverBudget
from .data import project, CASE_IDS
from .schemas import EvaluateIn
from .model import VERSION

class FermentationService:
    def __init__(self, platform):
        self.p=platform
        self.catalog=ModelCatalog('aerobic_fermentation')
        platform.flows.register_operator('fermentation_transfer_analysis',VERSION,self._execute)

    def projects(self,ctx,site_id='NF1'):
        self.p.identity.require(ctx,'read','physical_analysis_context',site_id=site_id)
        return {'projects':[project(case_id) for case_id in CASE_IDS],'models':self.catalog.snapshot()}

    def evaluate(self,ctx,case_id,request):
        request=EvaluateIn.model_validate(request)
        public=project(case_id); site=request.site_id
        self.p.identity.require(ctx,'propose','physical_analysis_plan',site_id=site)
        adapter=self.catalog.get('fermentation.oxygen_transfer' if case_id=='sulfolobus' else 'fermentation.pressure_cost')
        software={'model':adapter.describe(),'service_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        refs=[]
        for source_id, data, classification in [
            ('literature-'+case_id, public,'reviewed_published_summary'),
            ('assumptions-'+case_id, request.assumptions.model_dump(),'user_declared_scenario_assumptions'),
            ('software-'+case_id, software,'versioned_scientific_software')]:
            evidence=self.p.evidence.ingest(ctx,source_system='fermentation-transfer',source_record_id=site+':'+source_id,
                content=json.dumps(data,sort_keys=True).encode(),media_type='application/json',site_id=site,event_time=None,
                metadata={'classification':classification,'doi':public['doi']})
            refs.append(EvidenceRef('evidence',evidence['evidence_id'],evidence['revision'],site))
        plan=self.p.evidence.record_derived(ctx,'physical_analysis_plan',{'site_id':site,'process_family':'aerobic_fermentation',
            'project':public,'spec':request.model_dump(),'model_manifest':[adapter.describe()],
            'plan_hash':content_hash({'project_hash':public['data_hash'],'request':request.model_dump(),'software':software}),
            'review_state':'requires_engineering_review'},inputs=refs,produced_by={'method':VERSION})
        mission=self.p.missions.start_or_resume(ctx,objective='Review literature-grounded '+case_id+' technology transfer',owner_id=ctx.actor_id,
            scope={'site_ids':[site]},constraints=['Literature assessment only; no equipment control','Independent characterization and human review required'])
        flow_id=new_id('ferflow')
        self.p.flows.save(ctx,flow_id,site_id=site,nodes=[{'node_id':'characterize','task_kind':'fermentation_transfer_analysis','payload':{'plan_id':plan['id']}}])
        run=self.p.flows.create_run(ctx,flow_id,inputs=[{'kind':'physical_analysis_plan','id':plan['id'],'revision':1,'site_id':site}])
        outcome=self.p.flows.run(ctx,run['run_id'])
        node=outcome['results'].get('characterize',{})
        result=node.get('output')
        if not result: return {'execution_status':'blocked','issues':outcome.get('issues',[]),'flow_run_id':run['run_id']}
        return {**result,'flow_run_id':run['run_id'],'mission_id':mission['mission_id']}

    def _execute(self,ctx,payload):
        plan=self.p.evidence.read_derived(ctx,'physical_analysis_plan',payload['plan_id'])
        site=plan['site_id']; self.p.identity.require(ctx,'propose','physical_analysis_result',site_id=site)
        ref=EvidenceRef('physical_analysis_plan',payload['plan_id'],plan['revision'],site)
        self.p.identity.validate_refs(ctx,[ref.to_dict()])
        pin=plan['model_manifest'][0]; adapter=self.catalog.get(pin['id'])
        if pin!=adapter.describe(): raise ValueError('Model changed; prepare a new plan')
        request=EvaluateIn.model_validate(plan['spec']); budget=SolverBudget(4,10)
        started=perf_counter()
        try:
            prediction=budget.run(adapter,{'project':plan['project'],'assumptions':request.assumptions.model_dump()})
            from .evaluation import grade
            evaluation=grade(plan['project'],prediction,request.assumptions)
            status='completed'; issues=[]
        except (ValueError,RuntimeError,ArithmeticError) as exc:
            prediction=None; evaluation=None; status='failed'; issues=[str(exc)]
        result=self.p.evidence.record_derived(ctx,'physical_analysis_result',{'site_id':site,'process_family':'aerobic_fermentation',
            'case_id':plan['project']['id'],'project':plan['project'],'assumptions':request.assumptions.model_dump(),
            'plan_hash':plan['plan_hash'],'model_manifest':plan['model_manifest'],'prediction':prediction,'validation':evaluation,
            'execution_status':status,'issues':issues,'review_state':'requires_engineering_review',
            'resource_usage':{'solver_calls':budget.calls,'runtime_seconds':perf_counter()-started,'inference_cost_usd':0,'human_preparation_minutes':None},
            'warnings':plan['project']['limitations']},inputs=[ref],produced_by={'method':VERSION,'implementation_digest':adapter.digest})
        return {'status':'completed' if status=='completed' else 'blocked','output':result,'issues':issues}

    def get(self,ctx,result_id):
        result=self.p.evidence.read_derived(ctx,'physical_analysis_result',result_id)
        if result.get('process_family')!='aerobic_fermentation': raise ValueError('not a fermentation result')
        self.p.identity.require(ctx,'read','physical_analysis_result',result_id,site_id=result['site_id'])
        return result

    def review(self,ctx,result_id,owner_id):
        result=self.get(ctx,result_id)
        if result['status']!='current' or result['execution_status']!='completed': raise ValueError('A current completed analysis is required')
        basis=[{'kind':'physical_analysis_result','id':result_id,'revision':result['revision'],'site_id':result['site_id']}]
        self.p.identity.validate_refs(ctx,basis)
        return self.p.actions.propose(ctx,target_system='engineering-review',operation='review_physical_analysis',target_id=result_id,
            payload={'analysis_result_id':result_id,'model_manifest':result['model_manifest'],'plan_hash':result['plan_hash'],
                     'mode':'literature_transfer_review_only','questions':result['project']['missing']},basis=basis,
            rationale='Review source applicability, withheld discrepancies, equipment ratings and scenario assumptions.',
            expected_result='Document engineering characterization and acceptance criteria; no manufacturing change or qualification.',
            owner_id=owner_id,site_id=result['site_id'],constraints=result['warnings'],
            follow_up_measure='Independent receiver kLa/OUR and replicated productivity under the proposed conditions')

    def agent_assessment(self,ctx,case_id,site_id='NF1',assumptions=None):
        from .benchmark import attempt
        self.p.identity.require(ctx,'propose','physical_analysis_plan',site_id=site_id)
        public=project(case_id)
        # Only calibration-side inputs reach Prime. UI validation outputs are deliberately not forwarded.
        directory=Path('.cache/fermentation-prime')/content_hash({'tenant':ctx.tenant_id,'actor':ctx.actor_id,'site':site_id})
        directory.mkdir(parents=True,exist_ok=True)
        outcome=attempt(self.p,ctx,public,directory,blinded=False,assumptions=assumptions)
        return {'case_id':case_id,**outcome}
