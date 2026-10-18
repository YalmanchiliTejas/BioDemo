"""Per-run, time-scoped HTTP bridge for a Prime Agent Python skill."""

from __future__ import annotations

import json
import secrets
import threading
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.data.temporal_store import parse_time
from src.manufacturing_data import ManufacturingStore, ManufacturingTools
from src.manufacturing_data.session import ManufacturingSession
from src.state import BlackboardStore, CausalHypothesisGraph, DecisionGraph
from src.workflows import ManufacturingInvestigationWorkflow
from src.workflows.proposals import ProposalContext, create_investigation_task, request_new_evidence


class ManufacturingBridge:
    """The skill calls scoped evidence/analysis tools and submits a verified report."""

    def __init__(self, *, store: ManufacturingStore, blackboards: BlackboardStore,
                 workflow: ManufacturingInvestigationWorkflow, scope: str,
                 incident_id: str, objective: str, as_of: str,
                 seed_ids: list[str], max_tool_calls: int = 48, trace_sink=None) -> None:
        if not incident_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in incident_id):
            raise ValueError("invalid incident id")
        parse_time(as_of)
        self.store, self.blackboards, self.workflow = store, blackboards, workflow
        self.scope, self.incident_id, self.objective, self.as_of = scope, incident_id, objective, as_of
        self.session = ManufacturingSession(store, as_of=as_of, scopes=(scope,))
        self.tools = ManufacturingTools(store, as_of=as_of, scopes=(scope,))
        self.seed_ids = list(dict.fromkeys(map(str, seed_ids)))
        if len(self.session.get(self.seed_ids)) != len(self.seed_ids):
            raise ValueError("seed evidence is unavailable at this scope and timestamp")
        self.board = blackboards.load_or_create(incident_id)
        if len(self.session.get(self.board.evidence_ids)) != len(set(self.board.evidence_ids)):
            raise ValueError("stored incident evidence is unavailable at this scope and timestamp")
        if any(parse_time(str(item["as_of"])) > parse_time(as_of)
               for item in self.board.rollout_history if item.get("as_of")):
            raise ValueError("stored incident state contains future information")
        if any(parse_time(str(item["recorded_at"])) > parse_time(as_of)
               for item in self.board.outcomes if item.get("recorded_at")):
            raise ValueError("stored incident outcome contains future information")
        self.seen_ids = set(self.seed_ids) | set(self.board.evidence_ids)
        self.max_tool_calls = max_tool_calls
        self.tool_calls = 0
        self.tool_history: list[dict[str, Any]] = []
        self.trace_sink = trace_sink
        self.result: dict[str, Any] | None = None
        self._lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.preparation = None
        self.preparation_path = None
        self.started_monotonic=time.monotonic()
        self.time_budget_seconds=None
        self.lead_tool_reserve=min(6,max_tool_calls//4)
        self.subreports=[]
        self.checkpoint_path=None
        self.preparation_exposures=[]
        self.require_claim_ledger=False
        self.finalization_reserve_seconds=90
        self.execution_policy='fixed_v1'
        self.soft_tool_limit=max_tool_calls
        self.specialist_grants=0
        self.coordinator=None
        self._packet_cache={}
        self.last_validation=None

    def configure_execution(self, policy):
        if policy.get('mode','fixed_v1') not in {'fixed_v1','adaptive_v1'}:raise ValueError('unknown execution policy')
        soft=policy.get('soft_tool_calls',self.max_tool_calls)
        if type(soft) is not int or not 1<=soft<=self.max_tool_calls:raise ValueError('soft tool budget must fit hard budget')
        if policy.get('mode','fixed_v1')=='fixed_v1' and soft!=self.max_tool_calls:raise ValueError('Fixed policy must use its frozen hard limit')
        self.execution_policy=policy.get('mode','fixed_v1');self.soft_tool_limit=soft

    def _coord(self):
        if self.coordinator is None:
            from .coordination import InvestigationCoordinator
            self.coordinator=InvestigationCoordinator(self.tools.analysis().prepare())
        return self.coordinator

    def work_queue(self, limit=20):
        if type(limit) is not int or not 0<=limit<=100:raise ValueError('queue limit must be 0..100')
        return {**self._coord().queue(limit),'convergence':self._coord().convergence(),'budget':self.budget()}

    def allocate_work(self, task_ids, owner, reason, calls=0, extend=False, caller_depth=0):
        with self._lock:
            if caller_depth:raise ValueError('Only the lead can allocate work or transfer reserved calls')
            if not isinstance(task_ids,list) or not task_ids or len(task_ids)>64 or any(not self._coord().task_open(t) for t in task_ids):
                raise ValueError('Allocation requires named open source/unit/candidate/repair tasks')
            if not isinstance(owner,str) or not owner.strip() or not isinstance(reason,str) or not reason.strip():raise ValueError('owner and reason are required')
            if type(calls) is not int or not 0<=calls<=8 or type(extend) is not bool:raise ValueError('Allocate 0..8 calls per request')
            if self.budget()['phase']=='finalization':raise ValueError('Exploration cannot extend into finalization reserve')
            if extend:
                if self.execution_policy!='adaptive_v1':raise ValueError('This frozen configuration has a fixed budget')
                if not calls or self.soft_tool_limit>=self.max_tool_calls:raise ValueError('No extension available')
                self.soft_tool_limit=min(self.max_tool_calls,self.soft_tool_limit+calls)
            # Grant specialists access to some existing lead-reserved allowance.
            # The shared limit and wall-clock deadline still apply to all callers.
            self.specialist_grants=min(self.lead_tool_reserve,self.specialist_grants+calls)
            entry={'task_ids':task_ids,'owner':owner,'reason':reason,'calls':calls,'extended':extend,
                   'tool_calls_at_allocation':self.tool_calls,'active_limit':self.soft_tool_limit}
            self._coord().extensions.append(entry)
            for task in task_ids:self._coord().assignments[task]={'owner':owner,'reason':reason}
            self._checkpoint()
            return {'status':'allocated','allocation':entry,'budget':self.budget()}

    def save_progress(self, update, caller_depth=0):
        with self._lock:
            from .coordination import merge_report
            from src.workflows.report_verification import collect_citations
            from src.workflows.investigation_review import review_investigation
            # Children submit scoped checkpoints; the lead explicitly imports
            # them. A child cannot overwrite the shared final draft.
            if caller_depth:return self.submit_subreport(update,caller_depth)
            draft=merge_report(self._coord().draft,update)
            ids=collect_citations(draft)
            if not set(ids)<=self.seen_ids:raise ValueError('Draft cites evidence not exposed in this run')
            # Validate coverage and source ownership before saving. Source-value
            # and full scientific checks still run at final submission.
            review_investigation({'coverage':draft.get('coverage',[]),'candidate_reviews':draft.get('candidate_reviews',[]),'report_type':'checkpoint'},self.tools.analysis().prepare(),self.session.get(ids))
            self._coord().draft=draft
            self.last_validation=None
            self._checkpoint()
            return {'status':'progress_saved','queue':self.work_queue(8)}

    def assemble_report(self, overrides=None, subreport_ids=None, caller_depth=0):
        with self._lock:
            if caller_depth:raise ValueError('Only the lead assembles the final report')
            from .coordination import merge_report
            from copy import deepcopy
            assembled=deepcopy(self._coord().draft)
            for identifier in subreport_ids or []:
                found=next((s for s in self.subreports if s['subreport_id']==identifier),None)
                if found is None:raise ValueError('Unknown specialist checkpoint')
                # Explicit import, with no invented coverage/claims. Conflicting
                # records require a lead decision rather than last-writer wins.
                from .coordination import KEYED_SECTIONS
                for section,key in KEYED_SECTIONS.items():
                    incoming=found.get(section,[]);existing={i[key]:i for i in assembled.get(section,[]) if key in i}
                    for item in incoming:
                        if item.get(key) in existing and existing[item[key]]!=item:raise ValueError('Conflicting specialist '+section+'; resolve explicitly with save_progress')
                    if incoming:assembled=merge_report(assembled,{section:incoming})
                for section in ('open_questions','evidence_requests','tasks','follow_up_actions'):
                    combined=assembled.get(section,[])[:]
                    for item in found.get(section,[]):
                        if item not in combined:combined.append(deepcopy(item))
                    if combined:assembled[section]=combined
            if overrides:assembled=merge_report(assembled,overrides)
            return {'report':assembled,'convergence':self._coord().convergence(),
                    'status':'draft_only; validate_and_submit_required'}

    def stopping_decision(self, candidate_id, evidence_ids, reason, next_evidence, expected_to_change_action, available_in_scope, caller_depth=0):
        with self._lock:
            if caller_depth:raise ValueError('Only lead can record convergence decisions')
            if candidate_id not in self._coord().candidates:raise ValueError('Unknown candidate')
            if type(available_in_scope) is not bool or type(expected_to_change_action) is not bool or not isinstance(reason,str) or not reason.strip() or not isinstance(next_evidence,str) or not next_evidence.strip():raise ValueError('Explicit stopping reason, next evidence, availability and marginal-value judgment are required')
            if not isinstance(evidence_ids,list) or not evidence_ids or not set(evidence_ids)<=self.seen_ids:raise ValueError('Stopping decisions require exposed evidence')
            anchors=set(self._coord().candidates[candidate_id]['evidence_ids'])
            if not anchors.intersection(evidence_ids):raise ValueError('Stopping decision must reference candidate evidence')
            entry={'candidate_id':candidate_id,'evidence_ids':evidence_ids,'reason':reason,'next_evidence':next_evidence,'expected_to_change_action':expected_to_change_action,'available_in_scope':available_in_scope}
            self._coord().decisions=[d for d in self._coord().decisions if d['candidate_id']!=candidate_id]+[entry]
            self._checkpoint()
            return {'status':'decision_saved','convergence':self._coord().convergence()}

    def _evidence_packet(self, requests, **_bounded):
        if not isinstance(requests,list) or not 1<=len(requests)<=8:raise ValueError('Packet needs 1..8 scoped requests')
        packets=[];ids=[]
        for request in requests:
            if not isinstance(request,dict) or set(request)-{'unit_id','source_id','sheet','row','page','name','limit','offset'}:raise ValueError('Unsupported packet selector')
            unit=self._coord().units.get(request.get('unit_id'))
            if 'unit_id' in request and unit is None:raise ValueError('Unknown coverage unit')
            sid=request.get('source_id',unit['source_id'] if unit else None)
            if sid not in self._coord().sources or (unit and sid!=unit['source_id']):raise ValueError('Source is outside the requested scope')
            limit=request.get('limit',32)
            if type(limit) is not int or not 1<=limit<=32:raise ValueError('Packet selector limit must be 1..32')
            offset=request.get('offset',0)
            if type(offset) is not int or not 0<=offset<=1_000_000:raise ValueError('Packet offset must be 0..1000000')
            clauses=['source_id=?'];params=[sid]
            if unit and unit['entity_id'] is not None:clauses.append('entity_id=?');params.append(unit['entity_id'])
            for field in ('sheet','row','page'):
                if field in request:
                    if field in {'row','page'} and (type(request[field]) is not int or request[field]<1):raise ValueError('row/page must be positive integers')
                    if field=='sheet':clauses.append('sheet IS NOT DISTINCT FROM ?')
                    else:clauses.append("TRY_CAST(json_extract_string(source_ref,'$."+field+"') AS BIGINT)=?")
                    params.append(request[field])
            if 'name' in request:clauses.append('name=?');params.append(request['name'])
            selected=self.store.select('SELECT id FROM observations WHERE '+' AND '.join(clauses)+' ORDER BY source_row,id LIMIT ? OFFSET ?',params+[limit+1,offset],as_of=self.as_of,scopes=(self.scope,))
            records=self.session.get([r['id'] for r in selected[:limit]])
            ids.extend(r['id'] for r in records)
            packets.append({'request':request,'records':[{k:r.get(k) for k in ('id','source_id','entity_id','name','value_number','value_text','unit','source_ref','time_value','time_basis','time_evidence_id')} for r in records],
                            'truncated':len(selected)>limit,'next_offset':offset+limit if len(selected)>limit else None,'verification':'source_coordinates_supplied; original_value_checks_at_submission'})
        return {'packets':packets,'evidence_ids':list(dict.fromkeys(ids)),'status':'evidence_supplied',
                'requests_executed':len(requests),'record_count':sum(len(p['records']) for p in packets)}

    def prepare_analysis(self, artifact_path=None):
        if self.preparation is None:
            analysis=self.tools.analysis()
            self.preparation=analysis.compact()
            from src.workflows.report_verification import evidence_scope
            representatives={}
            for series in analysis.prepare()['series']:
                if series['entity_id'] not in representatives:representatives[series['entity_id']]=series['minimum_id']
            self.preparation['examined_scope']=evidence_scope(self.session.get(representatives.values()))
            self.preparation['examined_scope']['basis']='deterministic_series_coverage; not affected-unit adjudication'
            # The complete deterministic artifact is made available to the lead
            # and children; its source-backed anchors count as supplied evidence.
            self.seen_ids.update(self.preparation['evidence_ids'])
        if artifact_path is not None:
            from pathlib import Path
            target=Path(artifact_path)
            target.write_text(json.dumps(self.tools.analysis().prepare(),indent=2)+'\n')
            target.chmod(0o600)
            self.preparation_path=str(target)
            exposed=self.tools.analysis().prepare()['evidence_ids']
            self.seen_ids.update(exposed)
            self.preparation_exposures=[{'kind':'complete_citable_screening_artifact',
                'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'evidence_count':len(exposed)}]
        return self.preparation

    def context(self, caller_depth=0) -> dict[str, Any]:
        return {"incident_id": self.incident_id, "objective": self.objective,
                "as_of": self.as_of, "scope": self.scope,
                "seed_evidence": self.session.get(self.seed_ids),
                "blackboard": self.board.to_dict(),
                "tool_names": list(self.tools.handlers())+['evidence_packet'],
                "remaining_tool_calls": self.budget(caller_depth)['shared_tool_calls_remaining'],
                "max_tool_calls": self.max_tool_calls,
                "budget":self.budget(caller_depth),
                "work_queue":self.work_queue(12),
                "coordination_contract":{'packet':'evidence_packet(requests=[{unit_id or source_id, optional row/sheet/page/name/offset/limit}]); max 8 selectors, 32 cells each. Follow next_offset when truncated.',
                    'progress':'save_progress upserts explicit coverage, claims, metrics and findings into a durable draft; no automatic review.',
                    'allocation':'Lead allocate_work(task_ids,owner,reason,calls<=8,extend=False) transfers reserved calls. extend=True requests a bounded adaptive extension for named open work.',
                    'convergence':'Lead stopping_decision per candidate declares evidence, next evidence, availability and whether it could change action; missing external evidence stays explicit.',
                    'assembly':'assemble_report explicitly imports selected subreports, retaining keyed findings; conflicting records require lead resolution. validate_report/submit_report remain mandatory.'},
                "sub_investigations":[{k:entry[k] for k in ('subreport_id','caller_depth','report_type','assessment','verification')}|{'observed_facts':entry['observed_facts'][:6],
                    'calculated_metrics':[{k:m[k] for k in ('metric_id','value','display_value','specification') if k in m} for m in entry['calculated_metrics'][:8]],
                    'coverage_count':len(entry['coverage']),'candidate_review_count':len(entry['candidate_reviews']),
                    'full_checkpoint_artifact':str(self.checkpoint_path) if self.checkpoint_path else None,
                    'total_observed_facts':len(entry['observed_facts'])} for entry in self.subreports],
                "preparation_exposures":self.preparation_exposures,
                "query_data_contract": {
                    "table": "observations",
                    "columns": ["id", "source_id", "name", "value_number", "unit",
                                "occurred_at", "available_at", "entity_id", "access_scope",
                                "sheet", "source_row", "row_id", "time_value", "time_basis", "time_evidence_id"],
                    "numeric_only": True,
                    "rules": ["single SELECT starting with SELECT", "no CTEs (no WITH)",
                              "no semicolons", "must contain FROM observations",
                              "limit <= 1000"],
                },
                "text_search_tool": "search_evidence",
                "search_evidence_contract": {
                    "evidence_type": ["auto", "exact", "structured", "narrative"],
                    "mode": ["lexical", "semantic", "hybrid"],
                    "filters": ["observation_id", "source_id", "entity_id", "metric", "value_text", "sheet",
                                "source_row", "time_min", "time_max", "time_basis"],
                    "time_units": "hours; specify elapsed_hours or calendar_hours; never row indices",
                    "text_index": "meaningful narrative text; excludes numeric cells and categorical metadata",
                    "metric_aliases": "infer_schema returns proposed canonical names; units and source contexts remain separate",
                },
                "analysis_preparation":self.prepare_analysis(),
                "analysis_preparation_artifact":self.preparation_path,
                "report_completion_contract":{
                    'lead_only_final':True,'children':'submit_subreport; never fills final report slot',
                    'report_type':['final_investigation','partial_investigation','sub_investigation'],
                    'coverage':'Each screening unit_id needs status, reason, evidence_ids; screening is not agent review.',
                    'candidate_reviews':'Disposition and evidence for every priority candidate; other evidence remains open for exploration.',
                    'cross_scope_synthesis':'Explain shared patterns, exceptions and limits across the reviewed scope.',
                    'temporal_claims':'claim_id, earlier_observation_id, later_observation_id, relation before/coincident, tolerance_hours; cite both source clock cells.',
                    'preflight':'validate_report returns missing work without publishing or consuming a retrieval call',
                    'partial':'Persist useful partial results, but they remain incomplete and cannot qualify.'},
                "calculation_contract":{'max_metrics_per_call':32,'max_metrics_per_report':64,
                    'operations':['mean','sem','sample_sd','sum','minimum','maximum','count','percentage','percent_change','ratio','difference','yield'],
                    'zero_denominator':'undefined; do not substitute zero or a different statistic',
                    'batching':'Chunk requests into at most 32 metrics; prefer already computed screening statistics.'},
                "report_contract":{
                    "claims":"Every substantive observation, interpretation and hypothesis needs a claim_id and a matching claims entry: classification observed/derived/association/hypothesis, statement, evidence_ids, contradicting_evidence_ids, counterevidence_search, metric_ids, temporal_basis, uncertainty, missing_information. verified_cause is unavailable without independent review. No numerical confidence probabilities.",
                    "sections":["observed_facts","calculated_metrics","interpretations","hypotheses"],
                    "hypothesis_absence":"empty supporting/contradicting arrays require evidence_status none_found/not_searched and evidence_absence_reason",
                    "numerical_verification":"calculated_metrics must declare claimed_value and a calculate_metrics specification; values are recomputed at submission",
                    "severity":"agent severity is advisory; routing and final severity come from the configured policy"}}

    def budget(self, caller_depth=0):
        active=min(self.soft_tool_limit,self.max_tool_calls)
        remaining=max(0,active-self.tool_calls)
        elapsed=time.monotonic()-self.started_monotonic
        return {'shared_tool_calls_remaining':remaining,'lead_reserved_calls':max(0,self.lead_tool_reserve-self.specialist_grants),
                'policy':self.execution_policy,'active_tool_limit':active,'hard_tool_limit':self.max_tool_calls,
                'caller_depth':caller_depth,'caller_role':'lead' if caller_depth==0 else 'specialist',
                'specialist_calls_available':max(0,remaining-self.lead_tool_reserve+self.specialist_grants),
                'elapsed_seconds':elapsed,
                'remaining_seconds':max(0,self.time_budget_seconds-elapsed) if self.time_budget_seconds is not None else None,
                'finalization_reserve_seconds':self.finalization_reserve_seconds,
                'phase':'finalization' if self.time_budget_seconds is not None and self.time_budget_seconds-elapsed<=self.finalization_reserve_seconds else 'investigation',
                'five_minute_target_is_not_a_stopping_rule':True}

    def _checkpoint(self):
        if self.checkpoint_path is None:return
        target=Path(self.checkpoint_path);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version':'investigation-checkpoint-v2','incident_id':self.incident_id,
            'scope':self.scope,'as_of':self.as_of,'status':'final_report_persisted' if self.result else 'incomplete',
            'budget':self.budget(),'sub_investigations':self.subreports,
            'coordination':self.coordinator.snapshot() if self.coordinator else None,
            'final_investigation_review':self.result.get('investigation_review') if self.result else None},default=str,indent=2)+'\n')
        temporary.chmod(0o600);temporary.replace(target)

    def validate_report(self, report=None, record=True):
        with self._lock:return self._validate_report(report,record)

    def _validate_report(self, report=None, record=True):
        """Cheap structural/source-clock check; never certifies original values."""
        from src.workflows.report_verification import collect_citations
        from src.workflows.investigation_review import review_investigation
        if report is None:report=self.assemble_report()['report']
        if not isinstance(report,dict):raise ValueError('report must be an object')
        ids=collect_citations(report)
        if not set(ids)<=self.seen_ids:raise ValueError('report cites evidence not retrieved in this run')
        for fact in report.get('observed_facts',[]):
            if 'claimed_value' in fact and len(collect_citations(fact))!=1:
                raise ValueError('a direct claimed source value requires exactly one observation')
        self.prepare_analysis()
        rows=self.session.get(ids)
        if len(rows)!=len(ids):raise ValueError('report cites unavailable evidence')
        review=review_investigation(report,self.tools.analysis().prepare(),rows)
        if self.require_claim_ledger or 'claims' in report:
            from src.workflows.claim_verification import check_claims
            claims=check_claims(report,rows,report.get('calculated_metrics',[]))
            review['claim_verification']=claims
            review['issues'].extend(claims['issues'])
            ledger={c.get('claim_id'):c for c in report.get('claims',[])}
            for section in ('observed_facts','interpretations','findings','hypotheses'):
                for item in report.get(section,[]):
                    claim=ledger.get(item.get('claim_id'))
                    if not claim or claim.get('statement')!=item.get('statement'):
                        review['issues'].append({'code':'material_statement_missing_from_claim_ledger','section':section})
            if review['issues']:review['report_status']='incomplete'
        if record:
            from copy import deepcopy
            from .coordination import KEYED_SECTIONS,LIST_SECTIONS,SCALARS
            self._coord().draft={k:deepcopy(v) for k,v in report.items() if k in KEYED_SECTIONS or k in LIST_SECTIONS or k in SCALARS}
        if self.execution_policy=='adaptive_v1' and report.get('report_type')=='final_investigation':
            convergence=self._coord().convergence()
            if convergence['unread_sources']:review['issues'].append({'code':'sources_not_read','count':convergence['unread_sources']})
            if convergence['candidates_without_stopping_reason'] or convergence['candidates_needing_more_evidence']:
                review['issues'].append({'code':'convergence_not_established','candidate_ids':convergence['candidates_without_stopping_reason']+convergence['candidates_needing_more_evidence']})
            if review['issues']:review['report_status']='incomplete'
        if record:
            review['repair_tasks']=self._coord().repair_queue(review)
            self.last_validation=review
            self._checkpoint()
        return {**review,'preflight_only':True,'original_source_verification':'not_run',
                'numerical_metric_verification':'not_run','budget':self.budget()}

    def submit_subreport(self, report, caller_depth=1):
        with self._lock:
            if not isinstance(report,dict):raise ValueError('subreport must be an object')
            identifier=str(report.get('subreport_id') or f'specialist-{len(self.subreports)+1}')
            if len(self.subreports)>=16 and not any(s['subreport_id']==identifier for s in self.subreports):raise ValueError('maximum 16 specialist checkpoints; consolidate existing findings')
            report={**report,'report_type':'sub_investigation'}
            review=self.validate_report(report,record=False)
            from src.workflows.report_verification import collect_citations
            entry={'subreport_id':identifier,
                   'caller_depth':caller_depth,'report_type':'sub_investigation',
                   'assessment':str(report.get('assessment',''))[:4000],
                   'observed_facts':report.get('observed_facts',[]),
                   'hypotheses':report.get('hypotheses',[]),'interpretations':report.get('interpretations',[]),
                   'calculated_metrics':report.get('calculated_metrics',[]),'temporal_claims':report.get('temporal_claims',[]),
                   'coverage':report.get('coverage',[]),'candidate_reviews':report.get('candidate_reviews',[]),
                   'open_questions':report.get('open_questions',[]),'evidence_ids':collect_citations(report),
                   'claims':report.get('claims',[]),'evidence_requests':report.get('evidence_requests',[]),'tasks':report.get('tasks',[]),
                   'verification':'scoped citations checked; original values and scientific claims pending lead validation'}
            self.subreports=[s for s in self.subreports if s['subreport_id']!=identifier]+[entry];self._checkpoint()
            return {'status':'sub_investigation_saved','final_report_submitted':False,
                    'subreport_id':entry['subreport_id'],'budget':self.budget(caller_depth)}

    def tool(self, name: str, arguments: dict[str, Any], caller_depth=0) -> dict[str, Any]:
        with self._lock:
            trace_start = datetime.now(timezone.utc).isoformat()
            handlers = self.tools.handlers()
            handlers['evidence_packet']=self._evidence_packet
            packet_key=json.dumps(arguments,sort_keys=True,default=str) if name=='evidence_packet' else None
            if packet_key in self._packet_cache:
                cached=self._packet_cache[packet_key]
                self.tool_history.append({'name':name,'arguments':dict(arguments),'ok':True,
                    'budget_admitted':False,'cache_hit':True,'caller_depth':caller_depth,
                    'tool_call':None,'evidence_ids':cached.get('evidence_ids',[])})
                self._trace_tool(name,trace_start,cached.get('evidence_ids',[]),diagnostics={'cache_hit':True})
                return {**self._packet_cache[packet_key],'cache_hit':True,'budget':self.budget(caller_depth)}
            if self.budget(caller_depth)['phase']=='finalization' and name not in {'verify_evidence','calculate_metrics','extract_region'}:
                self._checkpoint()
                self._trace_tool(name,trace_start,[],'FinalizationReserve')
                return {'status':'finalization_required','evidence_ids':[],
                        'next_step':'Use existing evidence and saved subreports. Validate and submit the final report, or explicitly submit partial_investigation. Exploration is closed.',
                        'budget':self.budget(caller_depth)}
            if caller_depth>0 and self.budget(caller_depth)['specialist_calls_available']==0:
                self.tool_history.append({'name':name,'ok':False,'budget_admitted':False,'caller_depth':caller_depth,
                    'tool_call':None,'error_category':'lead_reserve','error':'Remaining calls are reserved for lead verification.'})
                self._trace_tool(name,trace_start,[],'LeadReserveExceeded')
                return {'status':'budget_exhausted','evidence_ids':[], 'next_step':'Save submit_subreport and notify lead with the named remaining task. Lead can transfer reserved calls using allocate_work.', 'budget':self.budget(caller_depth)}
            if name not in handlers:
                error = f"ValueError: tool is not an allowed manufacturing data tool: {name}"
                self.tool_history.append({"name": str(name), "arguments": dict(arguments),
                                          "ok": False, "error": error, "tool_call": self.tool_calls + 1})
                self._trace_tool(str(name), trace_start, [], "ValueError")
                raise ValueError("tool is not an allowed manufacturing data tool")
            if self.budget(caller_depth)['shared_tool_calls_remaining']==0:
                error = "RuntimeError: Prime manufacturing tool budget exceeded"
                self.tool_history.append({"name": name, "arguments": dict(arguments),
                                          "ok": False, "error": error, "tool_call": None,'budget_admitted':False})
                self._trace_tool(name, trace_start, [], "RuntimeError")
                return {'status':'budget_exhausted','evidence_ids':[], 'next_step':'Lead may request allocate_work(..., extend=True) for named open work if adaptive allowance remains. Otherwise validate and submit an explicit partial investigation.', 'budget':self.budget(caller_depth)}
            if caller_depth and self.budget(caller_depth)['shared_tool_calls_remaining']<=self.lead_tool_reserve and self.specialist_grants:
                self.specialist_grants-=1
            self.tool_calls += 1
            # The model cannot widen its historical cutoff or access scope.
            bounded = {**arguments, "as_of": self.as_of, "scopes": [self.scope]}
            try:
                result = handlers[name](**bounded)
                ids = {str(value) for value in result.get("evidence_ids", [])}
                visible = {row["_evidence_id"] for row in self.session.get(ids)}
                if not ids <= visible:
                    raise ValueError("tool returned unavailable evidence")
                self.seen_ids.update(ids)
                fresh=self._coord().record_evidence(self.session.get(ids))
                if result.get('source_id') and (result.get('data') or result.get('text')):self._coord().source_reads.add(result['source_id'])
                if packet_key is not None:self._packet_cache[packet_key]=result
                self.tool_history.append({"name": name, "arguments": bounded,
                                          "ok": True, "evidence_ids": sorted(ids),
                                          "tool_call": self.tool_calls,'budget_admitted':True,'caller_depth':caller_depth,
                                          'new_evidence_count':fresh,'packet_requests':result.get('requests_executed')})
                self._trace_tool(name, trace_start, sorted(ids), diagnostics=result.get('diagnostics'))
                self._checkpoint()
                return {**result,'budget':self.budget(caller_depth),'next_work':self._coord().queue(3)}
            except Exception as exc:
                self.tool_history.append({"name": name, "arguments": bounded,
                                          "ok": False,
                                          "error": f"{type(exc).__name__}: {exc}",
                                          "tool_call": self.tool_calls,'budget_admitted':True,'caller_depth':caller_depth})
                self._trace_tool(name, trace_start, [], type(exc).__name__)
                raise

    def _trace_tool(self, name, started_at, ids, error_code=None, diagnostics=None):
        if self.trace_sink is None:
            return
        stage = {"infer_schema": "mapping", "reconcile_entities": "mapping", "normalize_measurements": "mapping",
                 "verify_evidence": "verification", "extract_region": "verification", "query_data": "analysis"}.get(name, "investigation")
        self.trace_sink.emit(actor="agent", stage=stage, action="manufacturing_tool", tool=name,
                             started_at=started_at, evidence_ids=ids, error_code=error_code,
                             status="error" if error_code else "success", retrieval_diagnostics=diagnostics)

    def submit_report(self, report: dict[str, Any] | None=None, caller_depth=0) -> dict[str, Any]:
        with self._lock:
            if report is None:report=self.assemble_report(caller_depth=caller_depth)['report']
            if not isinstance(report,dict):raise ValueError('report must be an object')
            if caller_depth>0 or report.get('report_type')=='sub_investigation':
                return self.submit_subreport(report,caller_depth)
            if self.result is not None:
                raise ValueError("this Prime run already submitted a report")
            if not isinstance(report, dict):
                raise ValueError("report must be an object")
            for key in ("evidence_ids", "hypotheses", "findings", "resolved_questions",
                        "open_questions", "evidence_requests", "tasks", "decision_branches"):
                if not isinstance(report.get(key, []), list):
                    raise ValueError(f"{key} must be a list")
            if not str(report.get("assessment", "")).strip():
                raise ValueError("assessment is required")
            review=self.validate_report(report)
            if report.get('report_type')=='final_investigation' and review['report_status']=='incomplete':
                saved=self.submit_subreport({**report,'subreport_id':'lead-preflight-checkpoint'},caller_depth=0)
                return {'status':'needs_more_work','report_status':'incomplete','final_report_submitted':False,
                        'investigation_review':review,'checkpoint':saved,
                        'next_step':'Resolve listed issues, or submit report_type partial_investigation explicitly if resources are exhausted.'}
            from src.workflows.report_verification import verify_report,evidence_scope
            report,_verified_rows,verification=verify_report(report,self.session,self.tools,self.seen_ids)
            review.update(preflight_only=False,original_source_verification='checked; see verification.evidence_checks',
                          numerical_metric_verification='checked; see verification.numerical_metrics_verified')
            source_review_only=(verification['status']=='requires_source_review' and
                not verification.get('unlinked_numeric_literal_count') and
                not verification.get('claim_verification',{}).get('issues'))
            if source_review_only:
                # A complete submitted investigation may await visual source
                # review. Preserve that gate explicitly without denying durable
                # submission or certifying the unchecked values.
                review['source_review_pending']=verification['pending_source_reviews']
                self._coord().repair_queue(review,verification)
            elif verification['status']!='checks_passed; scientific_review_required':
                review['issues'].append({'code':'verification_review_outstanding','status':verification['status']})
                review['report_status']='incomplete'
                review['repair_tasks']=self._coord().repair_queue(review,verification)
                if report.get('report_type')=='final_investigation':
                    saved=self.submit_subreport({**report,'subreport_id':'lead-verification-checkpoint'},caller_depth=0)
                    return {'status':'needs_more_work','report_status':'incomplete','final_report_submitted':False,
                            'investigation_review':review,'verification':verification,'checkpoint':saved,
                            'next_step':'Resolve verification flags or explicitly submit a partial_investigation.'}
            else:self._coord().repair_queue(review,verification)
            cited = report['evidence_ids']
            board = type(self.board).from_dict(self.board.to_dict())
            all_ids = list(dict.fromkeys(board.evidence_ids + cited))
            valid = set(all_ids)
            graph = CausalHypothesisGraph()
            for item in report.get("hypotheses", [])[:12]:
                if not isinstance(item, dict):
                    raise ValueError("hypotheses must be objects")
                if not str(item.get("hypothesis_id", "")).strip() or not str(item.get("statement", "")).strip():
                    raise ValueError("hypothesis id and statement are required")
                links = set(map(str, item.get("supporting_evidence_ids", []))) | set(map(str, item.get("contradicting_evidence_ids", [])))
                if not links <= valid:
                    raise ValueError("hypothesis cites evidence not retrieved in this run")
                graph.upsert(item, valid)
            errors = graph.validate(valid)
            if errors:
                raise ValueError("invalid causal graph: " + "; ".join(errors))
            board.causal_hypotheses = graph.to_list()
            board.evidence_ids = all_ids
            board.open_questions = [str(value) for value in report.get("open_questions", [])]
            for item in report.get("findings", [])[:100]:
                if not isinstance(item, dict):
                    raise ValueError("findings must be objects")
                item_ids = list(dict.fromkeys(map(str, item.get("evidence_ids", []))))
                if not set(item_ids) <= valid:
                    raise ValueError("finding cites evidence not retrieved in this run")
                finding = {"statement": str(item.get("statement", "")),
                           "evidence_ids": item_ids,
                           "uncertainties": [str(value) for value in item.get("uncertainties", [])]}
                if finding not in board.completed_investigations:
                    board.completed_investigations.append(finding)
            for item in report.get("resolved_questions", [])[:100]:
                if not isinstance(item, dict):
                    raise ValueError("resolved questions must be objects")
                item_ids = list(dict.fromkeys(map(str, item.get("evidence_ids", []))))
                if not set(item_ids) <= valid:
                    raise ValueError("resolved question cites evidence not retrieved in this run")
                resolved = {"question": str(item.get("question", "")),
                            "finding": str(item.get("finding", "")), "evidence_ids": item_ids}
                if resolved not in board.resolved_questions:
                    board.resolved_questions.append(resolved)
            severity = str(report.get("severity", "LOW")).upper()
            if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                raise ValueError("invalid severity")
            board.severity = severity
            rows = self.session.get(all_ids)
            batches = sorted({str(row["batch_id"]) for row in rows if row.get("batch_id")})
            equipment = sorted({str(row["equipment_id"]) for row in rows if row.get("equipment_id")})
            board.scope=evidence_scope(rows)
            runs=board.scope['run_ids']
            experiments=board.scope['experiment_ids']
            affected=list(dict.fromkeys(map(str,report.get('affected_entity_ids',[]))))
            if not set(affected)<={str(r['entity_id']) for r in rows if r.get('entity_id')}:
                raise ValueError('affected scope requires citations from every declared entity')
            board.scope['agent_proposed_affected_entity_ids']=affected
            board.observed_facts=report.get('observed_facts',[])
            board.calculated_metrics=report.get('calculated_metrics',[])
            board.interpretations=report.get('interpretations',[])
            board.verification=verification
            board.investigation_review=review
            board.cross_scope_synthesis=str(report.get('cross_scope_synthesis',''))
            context = ProposalContext(self.session, board)
            for item in report.get("evidence_requests", [])[:6]:
                if not isinstance(item, dict):
                    raise ValueError("evidence requests must be objects")
                request_new_evidence(context, item)
            for item in report.get("tasks", [])[:6]:
                if not isinstance(item, dict):
                    raise ValueError("tasks must be objects")
                task_ids = set(map(str, item.get("evidence_ids", [])))
                if not task_ids <= valid:
                    raise ValueError("task cites evidence not retrieved in this run")
                create_investigation_task(context, item)
            decisions = DecisionGraph()
            for item in report.get("decision_branches", [])[:12]:
                if not isinstance(item, dict):
                    raise ValueError("decision branches must be objects")
                if not str(item.get("decision_id", "")).strip() or not str(item.get("condition", "")).strip():
                    raise ValueError("decision id and condition are required")
                decisions.upsert(item)
            errors = decisions.validate({item["request_id"] for item in board.pending_evidence})
            if errors:
                raise ValueError("invalid decision graph: " + "; ".join(errors))
            board.decision_branches = decisions.to_list()
            board.status = "suspended_pending_evidence" if board.pending_evidence else "awaiting_human_review"
            output = {
                "report_type":review['report_type'],"report_status":review['report_status'],
                "investigation_status":'complete' if review['report_status']=='complete_for_available_evidence' else 'incomplete',
                "source_verification_status":verification['source_verification_status'],
                "scientific_validation_status":"independent_review_pending",
                "investigation_review":review,"cross_scope_synthesis":board.cross_scope_synthesis,
                "temporal_claims":review['temporal_claims'],
                "assessment": str(report.get("assessment", "")), "severity": severity,
                "agent_proposed_severity":severity,
                "observed_facts":board.observed_facts,"calculated_metrics":board.calculated_metrics,
                "interpretations":board.interpretations,"verification":verification,
                "claims":report.get('claims',[]),
                "coordination":self._coord().snapshot(),
                "related_runs":runs,"related_experiments":experiments,
                "analysis_preparation":self.preparation,
                "examined_scope":self.preparation.get("examined_scope") if self.preparation else None,
                "analysis_preparation_artifact":self.preparation_path,
                "scope": board.scope, "causal_hypotheses": board.causal_hypotheses,
                "evidence_ids": all_ids, "related_batches": batches,
                "related_equipment": equipment, "resolved_questions": board.resolved_questions,
                "open_questions": board.open_questions, "actions_now": board.recommended_actions,
                "pending_evidence_requests": board.pending_evidence,
                "decision_branches": board.decision_branches, "teams": board.teams_involved,
                "continue_investigation": bool(board.open_questions or board.pending_evidence),
                "rollout_metrics": {"provider_id": "prime-agent", "tool_calls": self.tool_calls,
                                    "model_calls": None, "rlm_recursion_depth": None,
                                    "subtasks_spawned": None},
            }
            board.rollout_history.append({"as_of": self.as_of, "mode": "prime-agent",
                                          "new_evidence_ids": self.seed_ids,
                                          "metrics": output["rollout_metrics"], "status": board.status})
            output["workflow"] = self.workflow.record_rollout(
                self.incident_id, self.as_of, self.objective, output,sync_blackboard=False)
            output['severity']=output['workflow']['severity']
            output['triage']=output['workflow']['triage']
            board.severity=output['severity']
            board.evidence_ids=list(dict.fromkeys(all_ids+output['workflow']['workflow_discovered_evidence_ids']))
            self.blackboards.save(board)
            self.board, self.result = board, output
            self._checkpoint()
            if self.trace_sink is not None:
                self.trace_sink.emit(actor="agent", stage="triage", action="submit_reviewable_investigation",
                                     evidence_ids=all_ids, output_refs=["output.json#analysis"])
                self.trace_sink.emit(actor="agent", stage="coordination", action="propose_human_reviewed_work",
                                     output_refs=["output.json#analysis/workflow"],
                                     evidence_request_count=len(board.pending_evidence), task_count=len(board.recommended_actions))
            return output

    def start(self) -> "ManufacturingBridge":
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if not secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {bridge.token}"):
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length > 1_000_000:
                        raise ValueError("request too large")
                    value = json.loads(self.rfile.read(length))
                    caller=value.pop('_caller',{})
                    depth=caller.get('depth',0)
                    if type(depth) is not int or depth<0:raise ValueError('invalid runtime caller depth')
                    if self.path == "/context":
                        result = bridge.context(depth)
                    elif self.path == '/execution-status':
                        with bridge._lock:
                            result={'final_report_submitted':bridge.result is not None,
                                    'report_status':bridge.result.get('report_status') if bridge.result else None,
                                    'budget':bridge.budget()}
                    elif self.path == "/tool":
                        result = bridge.tool(str(value["name"]), dict(value.get("arguments", {})),depth)
                    elif self.path == "/report":
                        result = bridge.submit_report(value,depth)
                    elif self.path == '/subreport':
                        result=bridge.submit_subreport(value,depth)
                    elif self.path == '/validate-report':
                        result=bridge.validate_report(value,record=depth==0)
                    elif self.path == '/work-queue':result=bridge.work_queue(**value)
                    elif self.path == '/allocate-work':result=bridge.allocate_work(**value,caller_depth=depth)
                    elif self.path == '/progress':result=bridge.save_progress(value,depth)
                    elif self.path == '/assemble-report':result=bridge.assemble_report(**value,caller_depth=depth)
                    elif self.path == '/stopping-decision':result=bridge.stopping_decision(**value,caller_depth=depth)
                    else:
                        self.send_error(404)
                        return
                    body = json.dumps(result, default=str).encode()
                    self.send_response(200)
                except Exception as exc:
                    body = json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode()
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        if self.server is None:
            raise RuntimeError("bridge has not started")
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
