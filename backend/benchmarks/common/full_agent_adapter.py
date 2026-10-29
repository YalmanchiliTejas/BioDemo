"""Raw-package adapter for the existing Prime SDK runtime, shared by both datasets."""
from __future__ import annotations

import json
import shutil
from contextlib import nullcontext
import tempfile
import time
from pathlib import Path

from .agent_adapter import InvestigationInput
from .trace import TraceSink


class FullManufacturingOS:
    def run_investigation(self, request: InvestigationInput):
        from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package
        from src.state import BlackboardStore
        from src.workflows import ManufacturingInvestigationWorkflow
        from src.prime_runtime.harness import PrimeManufacturingHarness
        cfg=request.configuration
        sink=TraceSink(cfg['trace_path'],cfg['case_id'],cfg['run_id'],budgets=cfg.get('budgets')) if cfg.get('trace_path') else None
        started=time.monotonic()
        with (nullcontext(cfg['state_directory']) if cfg.get('state_directory') else tempfile.TemporaryDirectory(prefix='evaluation-prime-')) as temp:
            work=Path(cfg.get('state_directory') or temp)
            store=ManufacturingStore(work/'store')
            scope=cfg.get('access_scope','evaluation')
            tick=time.monotonic()
            if sink:
                with sink.interval(actor='pipeline',stage='ingestion',action='ingest_authorized_package') as detail:
                    ingested=ingest_package(request.input_package,store,access_scope=scope,document_backend=cfg.get('document_backend','auto'))
                    detail.update(indexed_files=ingested['files_indexed'],errors=len(ingested['errors']))
            else:
                ingested=ingest_package(request.input_package,store,access_scope=scope,document_backend=cfg.get('document_backend','auto'))
            ingestion_seconds=time.monotonic()-tick
            if ingested['errors'] and not cfg.get('allow_partial_ingestion', False):
                raise RuntimeError('ingestion errors prevent a complete benchmark investigation')
            boards=BlackboardStore(work/'blackboards')
            workflow=ManufacturingInvestigationWorkflow(work/'workflow',store,scope=scope,blackboards=boards,triage_policy=cfg.get('operational_triage_policy'))
            harness=PrimeManufacturingHarness.from_env(store=store,blackboards=boards,workflow=workflow,scope=scope)
            if cfg.get('prime_model'):
                harness.model=cfg['prime_model']
            scientific_calls=[]
            if cfg.get('scientific_tool_family') == 'aerobic_fermentation':
                # Same Prime host, bridge and scoped retrieval; only a bounded scientific tool is added.
                from src.lifesci.fermentation.model import calculate, VERSION
                from src.lifesci.fermentation.schemas import Assumptions
                public=json.loads((request.input_package/'model-input.json').read_text())
                def fermentation_transfer(*, assumptions=None, as_of=None, scopes=None):
                    settings=Assumptions.model_validate({**cfg.get('scientific_default_assumptions',{}),**(assumptions or {})}).model_dump()
                    prediction=calculate(public,settings)
                    call={'assumptions':settings,'prediction':prediction,'model_version':VERSION}
                    scientific_calls.append(call)
                    return {'status':'completed','output':prediction,'evidence_ids':[],
                            'provenance':'Registered deterministic characterization; scenario assumptions are not measurements.'}
                harness.additional_tools={'fermentation_transfer':fermentation_transfer}
            harness.trace_sink=sink
            harness.evaluation_mode=True
            harness.rlm_max_depth=cfg.get('rlm_max_depth')
            harness.max_tool_calls=cfg.get('budgets',{}).get('tool_calls',48)
            harness.execution_policy=cfg.get('execution_policy',{'mode':'fixed_v1'})
            harness.timeout_seconds=max(1,cfg.get('budgets',{}).get('wall_clock_seconds',900)-(time.monotonic()-started))
            cutoff=request.as_of or cfg['evaluation_time']
            incident=cfg.get('state_key','evaluation-case')
            tick=time.monotonic()
            try:
                report=harness.run(incident_id=incident,problem=request.objective,new_evidence_ids=[],as_of=cutoff)
            finally:
                logs=work/'blackboards/prime-runtime/logs'
                if cfg.get('artifact_directory') and logs.exists():
                    artifact_dir=Path(cfg['artifact_directory']);artifact_dir.mkdir(parents=True,exist_ok=True)
                    for log in logs.iterdir():
                        if log.is_file():shutil.copyfile(log,artifact_dir/log.name)
                    for name in ('analysis-preparation.json','investigation-checkpoint.json'):
                        preparation=work/'blackboards/prime-runtime/workspaces'/incident/name
                        if preparation.is_file():shutil.copyfile(preparation,artifact_dir/name)
            report['triage']=report.get('workflow',{}).get('triage',{})
            report['evidence_requests']=report.get('pending_evidence_requests',[])
            report['follow_up_actions']=report.get('actions_now',[])
            for key in ('prime_log','prime_tool_calls'):
                if report.get('rollout_metrics',{}).get(key):
                    report['rollout_metrics'][key]='runtime-artifacts/'+Path(report['rollout_metrics'][key]).name
            agent_seconds=time.monotonic()-tick
            tools=ManufacturingTools(store,as_of=cutoff,scopes=(scope,))
            # Include every sheet's first two physical data rows. A global 1000-cell
            # cap previously omitted most frozen CHO transcription checks.
            previews=store.select('SELECT * FROM observations WHERE source_row<=3 LIMIT 100001',as_of=cutoff,scopes=(scope,))
            preview_truncated=len(previews)>100000
            previews=previews[:100000]
            for row in previews:
                row['source_ref']=json.loads(row['source_ref'])
            cited={str(i) for i in report.get('evidence_ids',[])}
            citations=[]
            cited_rows={row['id']:row for row in store.get_many(cited,as_of=cutoff,scopes=(scope,))}
            verified_rows=dict(report.get('verification',{}).get('evidence_checks',{}))
            verified_rows.update(tools.verify_many([row for identifier,row in cited_rows.items() if identifier not in verified_rows]))
            for identifier in cited:
                row=cited_rows.get(identifier)
                if row is None or identifier not in verified_rows:
                    raise ValueError('Submitted report references unavailable or unverified evidence: '+identifier)
                verified=verified_rows[identifier]
                if row:
                    citations.append({'evidence_id':identifier, 'source':row['source_ref'],
                                      'verification':verified})
            if report.get('analysis_preparation_artifact'):
                report['analysis_preparation_artifact']='runtime-artifacts/analysis-preparation.json'
            sources=store.visible_sources(as_of=cutoff,scopes=(scope,))
            return {'mode':'full_rlm','objective':request.objective,'as_of':request.as_of,
                    'analysis':report,'citations':citations,'observations':previews,
                    'files':[{'path':s['path'],'type':s['format'],'sha256':s['sha256'],'status':s['extraction_status']} for s in sources],
                    'records':[], 'ingestion':ingested,'preview_truncated':preview_truncated,
                    'usage':{**report.get('rollout_metrics',{}),'runtime_seconds':time.monotonic()-started,
                             'ingestion_seconds':ingestion_seconds,'agent_runtime_seconds':agent_seconds,
                             'usage_scope':'root_sdk_session_only; child, OCR and tool costs may be missing'},
                    'scientific_tool_results':scientific_calls,
                    'constraints':{'gmp_actions_available':False,'scope':scope,'as_of':cutoff}}
