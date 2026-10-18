"""Matched automated methods using the investigator's authorized evidence tools.

Fixed statistical analysis is available to both methods. The conventional
method assembles a descriptive investigation; the LLM gets one synthesis call.
Neither gets evaluator references or domain-qualified causal labels.
"""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package
from src.manufacturing_data.session import ManufacturingSession
from src.workflows.investigation_review import review_investigation
from src.workflows.report_verification import verify_report, collect_citations, evidence_scope

PROMPT = """Investigate the objective using the supplied authorized evidence and deterministic statistics.
Return only a JSON object. No source is a hidden reference answer. All source IDs and
coordinates are supplied. Do not invent IDs. Address the full objective and every coverage
unit and priority candidate. Highest-priority candidates need supporting and contradicting
evidence, competing hypotheses, scope, uncertainty, next checks and human-review tasks.
Log termination is not proof of physical interruption; reactor differences may be intended;
DO/CO2 associations do not establish cause; sampled summaries do not establish exact onset.
Use qualitative uncertainty, never probability-like confidence or verified causation.
Required keys: report_type (final_investigation or partial_investigation), assessment,
cross_scope_synthesis, coverage (unit_id,status investigated/reviewed_no_material_signal/deferred/unresolved,
reason,evidence_ids), candidate_reviews (candidate_id,status investigated/contextualized/deferred/unresolved,
reason,evidence_ids), observed_facts, hypotheses (hypothesis_id,statement,supporting_evidence_ids,
contradicting_evidence_ids,contradicting_evidence_status found/none_found/not_searched,
contradicting_evidence_absence_reason,unknowns,tests_or_observations_that_would_discriminate),
interpretations, evidence_requests, follow_up_actions, open_questions, claims.
Each substantive statement in observed_facts, interpretations and hypotheses must have
a claim_id with identical statement in claims. Each claim has claim_id, classification
(observed,derived,association,hypothesis), statement,evidence_ids,contradicting_evidence_ids,
counterevidence_search,metric_ids,temporal_basis,uncertainty,missing_information.
Use no numeric prose unless that claim cites the exact values. Derived claims require a
reproducible calculated_metrics specification, not arithmetic in prose. Empty arrays are
permitted when no action/evidence request is justified; explain missing information.
Be concise. A partial investigation must explicitly remain partial. Copy coverage unit IDs
and their exact anchor IDs from the preparation, never anchors from another unit. A
source statement without an observation citation is not an observed fact; put missing-data
statements in open_questions. For large scopes you may return coverage_groups instead of
coverage: each group has unit_ids, status and reason. Each unit must be explicitly named;
the assembler binds only that unit's supplied source anchors. No wildcard or default review.
"""


def translate_identifiers(value, mapping):
    if isinstance(value,dict):return {k:translate_identifiers(v,mapping) for k,v in value.items()}
    if isinstance(value,list):return [translate_identifiers(v,mapping) for v in value]
    return mapping.get(value,value) if isinstance(value,str) else value


def alias_packet(packet):
    """Lossless short references reduce repeated opaque-ID context overhead."""
    screening=packet['preparation']['screening']
    groups={'E':packet['preparation']['evidence_ids'],
            'U':[u['unit_id'] for u in screening['coverage_units']],
            'P':[c['candidate_id'] for c in screening['priority_candidates']],
            'S':[s['source_id'] for s in packet['preparation']['source_versions']]}
    aliases={identifier:f'{prefix}{i+1:04d}' for prefix,values in groups.items() for i,identifier in enumerate(dict.fromkeys(values))}
    return translate_identifiers(packet,aliases),{v:k for k,v in aliases.items()}


def fixed_report(prepared, rows, objective):
    by_id={r['id']:r for r in rows}
    screening=prepared['screening']
    facts=[]; claims=[]
    for candidate in screening['priority_candidates']:
        for identifier in candidate['evidence_ids'][:2]:
            row=by_id.get(identifier)
            if not row:continue
            cid='C-'+str(len(claims)+1)
            value=row.get('value_number')
            if value is None:value=row.get('value_text')
            statement=f"The source records {row['name']} = {value} {row.get('unit') or ''}."
            claim={'claim_id':cid,'classification':'observed','statement':statement,
                   'evidence_ids':[identifier],'contradicting_evidence_ids':[], 'metric_ids':[],
                   'counterevidence_search':'Full scoped deterministic series were screened; no competing measurement of this exact cell is available.',
                   'temporal_basis':'Source coordinate only; no precise event onset inferred.',
                   'uncertainty':'A recorded measurement does not establish fault, mechanism or operating intent.',
                   'missing_information':'Approved operating strategy, independent sensor calibration and replicate measurements.'}
            claims.append(claim);facts.append({'claim_id':cid,'statement':statement,'evidence_ids':[identifier],
                                              'claimed_value':value,'claimed_unit':row.get('unit')})
    evidence=list(dict.fromkeys(i for c in claims for i in c['evidence_ids']))
    hypothesis={'hypothesis_id':'H-design','claim_id':'H-design','statement':'Intentional operating strategies or acquisition differences may explain descriptive variability.',
                'supporting_evidence_ids':evidence[:2],'contradicting_evidence_ids':[],
                'contradicting_evidence_status':'none_found',
                'contradicting_evidence_absence_reason':'No independently verified recipe or calibration record resolves these alternatives in the supplied package.',
                'unknowns':['Operating intent and calibration are unresolved.'],
                'tests_or_observations_that_would_discriminate':['Compare approved recipes and independent measurements against the source trajectories.']}
    claims.append({'claim_id':'H-design','classification':'hypothesis','statement':hypothesis['statement'],
                   'evidence_ids':evidence[:2],'contradicting_evidence_ids':[],'metric_ids':[],
                   'counterevidence_search':hypothesis['contradicting_evidence_absence_reason'],
                   'temporal_basis':'No temporal precedence or causality inferred.',
                   'uncertainty':'Fixed alternative explanation, not an established mechanism.',
                   'missing_information':'Approved recipes, calibration and independent domain adjudication.'})
    return {'report_type':'final_investigation','assessment':'Fixed descriptive investigation of the supplied objective: '+objective,
            'method_limit':'Deterministic rules and fixed assembly; biological plausibility and case-specific scientific adequacy require blinded review.',
            'coverage':[{'unit_id':u['unit_id'],'status':'investigated' if u['evidence_ids'] and u['series_count'] else 'unresolved',
                        'reason':'Computed full scoped series statistics and grouped candidate flags; operating fault is not inferred.' if u['series_count'] else 'No numeric series; narrative review remains unresolved.',
                        'evidence_ids':u['evidence_ids'][:2]} for u in screening['coverage_units']],
            'candidate_reviews':[{'candidate_id':c['candidate_id'],'status':'contextualized',
                        'reason':'; '.join(c['limitations'])+' Review the cited extrema and source trajectory against approved operating intent.',
                        'evidence_ids':c['evidence_ids'][:2]} for c in screening['priority_candidates']],
            'observed_facts':facts,'claims':claims,'hypotheses':[hypothesis],
            'cross_scope_synthesis':'Deterministic source-wide statistics and candidate grouping expose descriptive differences. Shared mechanism, affected production scope and operating fault are unresolved.',
            'open_questions':['Which differences are expected by design?','Do independent measurements support the apparent changes?'],
            'evidence_requests':[{'description':'Obtain approved operating strategies and calibration evidence for the prioritized candidates.'}],
            'follow_up_actions':[{'description':'Human process engineer reviews prioritized source trajectories and competing explanations.'}]}


def run_automated(request, *, single_pass=False):
    started=time.monotonic();cfg=request.configuration
    with (nullcontext(cfg['state_directory']) if cfg.get('state_directory') else tempfile.TemporaryDirectory(prefix='matched-baseline-')) as directory:
        store=ManufacturingStore(Path(directory)/'store');scope=cfg.get('access_scope','evaluation')
        ingested=ingest_package(request.input_package,store,access_scope=scope)
        if ingested['errors']:raise RuntimeError('Baseline ingestion failed: '+str(ingested['errors']))
        cutoff=request.as_of or cfg['evaluation_time']
        tools=ManufacturingTools(store,as_of=cutoff,scopes=(scope,))
        session=ManufacturingSession(store,as_of=cutoff,scopes=(scope,))
        prepared=tools.analysis().prepare();compact=tools.analysis().compact()
        ids=compact['evidence_ids']
        rows=session.get(ids)
        # Source locations and values are explicit, not just opaque citation IDs.
        packet={'objective':request.objective,'as_of':cutoff,'preparation':compact,
                'source_evidence':[{**{k:r[k] for k in ('id','name','value_number','value_text','unit','entity_id','time_value','time_basis','time_evidence_id') if r.get(k) is not None},
                    'source_ref':{k:v for k,v in r['source_ref'].items() if v is not None}} for r in rows]}
        artifacts=Path(cfg.get('artifact_directory') or Path(directory)/'artifacts');artifacts.mkdir(parents=True,exist_ok=True)
        (artifacts/'baseline-evidence-packet.json').write_text(json.dumps(packet,default=str,indent=2)+'\n')
        usage={'input_tokens':0,'output_tokens':0,'model_calls':0,'inference_cost_usd':0,
               'total_cost_usd':None,'cost_status':'compute_cost_unmeasured','usage_scope':'all_model_calls; local_compute_cost_unmeasured'}
        if single_pass:
            key=os.environ.get('OPENAI_API_KEY')
            if not key:raise RuntimeError('Single-pass baseline requires OPENAI_API_KEY; no model call executed.')
            model=cfg.get('model','gpt-6-luna')
            model_packet,aliases=alias_packet(packet)
            (artifacts/'identifier-aliases.json').write_text(json.dumps(aliases,indent=2)+'\n')
            body={'model':model,'input':[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(model_packet,default=str,separators=(',',':'))}],
                  'text':{'format':{'type':'json_object'}}}
            call_started=time.time()
            http=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),
                headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
            with urllib.request.urlopen(http,timeout=max(1,min(600,cfg.get('budgets',{}).get('wall_clock_seconds',900)-(time.monotonic()-started)-30))) as response:
                result=json.load(response)
            (artifacts/'single-pass-response.json').write_text(json.dumps(result,indent=2)+'\n')
            text=''.join(p.get('text','') for item in result.get('output',[]) for p in item.get('content',[]) if p.get('type')=='output_text')
            report=translate_identifiers(json.loads(text),aliases)
            usage.update(result.get('usage',{}),model_id=result.get('model',model),model_calls=1,
                         inference_cost_usd=None,cost_status='pricing_not_captured',
                         model_started_at=call_started,model_ended_at=time.time())
            (artifacts/'provider-usage.json').write_text(json.dumps(usage,indent=2)+'\n')
            if 'coverage_groups' in report:
                if report.get('coverage'):raise ValueError('Use coverage or coverage_groups, not both.')
                units={u['unit_id']:u for u in compact['screening']['coverage_units']}
                report['coverage']=[]
                for group in report['coverage_groups']:
                    for uid in group['unit_ids']:
                        if uid not in units:raise ValueError('Coverage group names an unknown unit.')
                        report['coverage'].append({'unit_id':uid,'status':group['status'],'reason':group['reason'],
                            'evidence_ids':units[uid]['evidence_ids'][:2]})
                report['assembly_metadata']={'coverage':'Explicit model-selected groups expanded to their supplied source anchors; no implicit review or wildcard coverage.'}
        else:
            report=fixed_report(prepared,rows,request.objective)
        # Same source/arithmetic verifier and completeness obligations as full OS.
        from src.workflows.claim_verification import check_claims
        cited=collect_citations(report);cited_rows=session.get(cited)
        try:
            review=review_investigation(report,prepared,cited_rows)
        except ValueError as exc:
            review={'report_status':'incomplete','issues':[{'code':'report_structure_invalid','detail':str(exc)}],
                    'scientific_review_required':True}
        review['claim_verification']=check_claims(report,cited_rows,report.get('calculated_metrics',[]))
        review['issues'].extend(review['claim_verification']['issues'])
        ledger={c.get('claim_id'):c for c in report.get('claims',[])}
        for section in ('observed_facts','interpretations','hypotheses'):
            for item in report.get(section,[]):
                claim=ledger.get(item.get('claim_id'))
                if not claim or claim.get('statement')!=item.get('statement'):
                    review['issues'].append({'code':'material_statement_missing_from_claim_ledger','section':section})
        try:
            report,_,verification=verify_report(report,session,tools,set(ids))
        except ValueError as exc:
            # Keep the actual output and source receipts; a rejected report is
            # an incomplete investigation, never a fabricated successful one.
            verification={'status':'requires_report_correction','error':str(exc),
                          'evidence_checks':tools.verify_many(cited_rows),'numerical_metrics_verified':None,
                          'claim_semantics':'independent_review_pending'}
            review['issues'].append({'code':'report_verification_failed','detail':str(exc)})
        if review['issues'] or verification['status']!='checks_passed; scientific_review_required':review['report_status']='incomplete'
        report.update(report_status=review['report_status'],investigation_review=review,verification=verification,
                      scope=evidence_scope(cited_rows),triage={'status':'human_review_required','policy_limitations':'No approved site routing policy or regulated action authorization.'})
        previews=store.select('SELECT * FROM observations WHERE source_row<=3 LIMIT 100001',as_of=cutoff,scopes=(scope,))
        for row in previews:row['source_ref']=json.loads(row['source_ref'])
        sources=store.visible_sources(as_of=cutoff,scopes=(scope,))
        return {'mode':'retrieval_llm' if single_pass else 'conventional','objective':request.objective,'as_of':request.as_of,
                'analysis':report,'citations':[{'evidence_id':r['id'],'source':r['source_ref'],'verification':verification['evidence_checks'][r['id']]} for r in cited_rows],
                'files':[{'path':s['path'],'type':s['format'],'sha256':s['sha256'],'status':s['extraction_status']} for s in sources],
                'observations':previews[:100000],'records':[],'ingestion':ingested,
                'usage':{**usage,'runtime_seconds':time.monotonic()-started},
                'constraints':{'gmp_actions_available':False,'scope':scope,'as_of':cutoff}}
