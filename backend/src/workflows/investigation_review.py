"""Structural completeness and source-clock checks; scientific conclusions need review."""
from collections import Counter
import math
import re
from datetime import datetime

COVERAGE_STATES={'investigated','reviewed_no_material_signal','deferred','unresolved'}

def record_timestamp(row):
    """Read an explicit timestamp cell, never ingestion availability metadata."""
    name=str(row.get('name','')).lower()
    value=row.get('value_text')
    if not re.search(r'(?:_at$|timestamp$|_date$|_time$)',name) or not isinstance(value,str):return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})',value):return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed
    except ValueError:return None

def review_investigation(report, prepared, rows):
    by_id={r['id']:r for r in rows}
    screening=prepared.get('screening',{}) if prepared else {}
    expected={u['unit_id']:u for u in screening.get('coverage_units',[])}
    supplied=report.get('coverage',[])
    if not isinstance(supplied,list):raise ValueError('coverage must be a list')
    covered={};issues=[]
    for item in supplied:
        if not isinstance(item,dict) or item.get('unit_id') not in expected:raise ValueError('coverage references an unknown scoped unit_id')
        uid=item['unit_id'];unit=expected[uid]
        if uid in covered:raise ValueError('duplicate coverage unit_id')
        state=item.get('status');links=item.get('evidence_ids',[])
        if state not in COVERAGE_STATES or not str(item.get('reason','')).strip():raise ValueError('coverage requires status and an explicit reasoning summary')
        if not isinstance(links,list) or not set(links)<=by_id.keys():raise ValueError('coverage evidence must be cited and visible')
        if any(by_id[i]['source_id']!=unit['source_id'] or (unit['entity_id'] is not None and by_id[i]['entity_id']!=unit['entity_id']) for i in links):
            raise ValueError('coverage evidence does not belong to its declared source/entity')
        if state in {'investigated','reviewed_no_material_signal'} and not links:
            raise ValueError('reviewed coverage requires source anchors; screening alone is insufficient')
        covered[uid]={**item,'source_id':unit['source_id'],'entity_id':unit['entity_id'],
                      'verification':'source coverage checked; reasoning adequacy requires independent review'}
    missing=sorted(set(expected)-set(covered))
    if missing:issues.append({'code':'coverage_not_reviewed','unit_ids':missing})
    unfinished=[u for u,v in covered.items() if v['status'] in {'deferred','unresolved'}]
    if unfinished:issues.append({'code':'coverage_unresolved','unit_ids':unfinished})
    candidates={c['candidate_id']:c for c in screening.get('priority_candidates',[])}
    decisions=report.get('candidate_reviews',[])
    if not isinstance(decisions,list):raise ValueError('candidate_reviews must be a list')
    reviewed={}
    for d in decisions:
        if not isinstance(d,dict) or d.get('candidate_id') not in candidates:raise ValueError('candidate review references an unknown priority candidate')
        cid=d['candidate_id']
        if cid in reviewed:raise ValueError('duplicate candidate review')
        if d.get('status') not in {'investigated','contextualized','deferred','unresolved'} or not str(d.get('reason','')).strip():
            raise ValueError('candidate review requires disposition and reason')
        links=d.get('evidence_ids',[])
        if not isinstance(links,list) or not set(links)<=by_id.keys():raise ValueError('candidate review evidence must be cited')
        if d['status'] in {'investigated','contextualized'} and not set(links)&set(candidates[cid]['evidence_ids']):
            raise ValueError('candidate review must link an actual candidate source anchor')
        reviewed[cid]=d
    absent=sorted(set(candidates)-set(reviewed))
    if absent:issues.append({'code':'priority_candidates_not_reviewed','candidate_ids':absent})
    if any(d['status'] in {'deferred','unresolved'} for d in reviewed.values()):issues.append({'code':'priority_candidates_unresolved'})
    temporal=[]
    ambiguous_clocks={(r['source_id'],r['entity_id'],r['sheet']) for r in (prepared or {}).get('series',[])
                      if r.get('source_backwards_steps') or r.get('distinct_times',0)<r.get('timed_n',0)}
    for claim in report.get('temporal_claims',[]):
        if not isinstance(claim,dict):raise ValueError('temporal claims must be objects')
        claim={k:v for k,v in claim.items() if k not in {'verification','reason','gap_hours','time_basis','clock_evidence_ids','limitation'}}
        left=by_id.get(claim.get('earlier_observation_id'));right=by_id.get(claim.get('later_observation_id'))
        if not left or not right:raise ValueError('temporal claim requires two cited observations')
        tolerance=claim.get('tolerance_hours',0)
        if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or tolerance<0:raise ValueError('temporal tolerance must be finite and nonnegative')
        basis=left.get('time_basis');known=(left.get('entity_id') is not None and left['entity_id']==right.get('entity_id')
            and basis not in (None,'unresolved') and basis==right.get('time_basis')
            and left.get('time_value') is not None and right.get('time_value') is not None)
        clocks=[r.get('time_evidence_id') for r in (left,right)]
        known=known and not any((r['source_id'],r.get('entity_id'),r.get('sheet')) in ambiguous_clocks for r in (left,right))
        mode=claim.get('clock_basis','auto')
        if mode not in {'auto','record_timestamps','process_clock'}:raise ValueError('unknown clock_basis')
        if type(claim.get('require_process_alignment',False)) is not bool:raise ValueError('require_process_alignment must be boolean')
        timestamps=[record_timestamp(r) for r in (left,right)]
        record_clock=mode!='process_clock' and all(t is not None for t in timestamps)
        if mode=='record_timestamps' or record_clock:
            known=record_clock
            if claim.get('require_process_alignment'):
                known=known and left.get('entity_id') is not None and left['entity_id']==right.get('entity_id')
            clocks=[left['id'],right['id']];basis='explicit_record_timestamps'
        elif mode=='process_clock' or mode=='auto':record_clock=False
        if not known or any(i not in by_id for i in clocks):
            result={**claim,'verification':'unverified_source_clock','reason':'Same explicit entity, unambiguous comparable clocks and cited clock cells are required.'}
            issues.append({'code':'temporal_claim_unverified','claim_id':claim.get('claim_id')})
        else:
            gap=(timestamps[1]-timestamps[0]).total_seconds()/3600 if record_clock else right['time_value']-left['time_value'];relation=claim.get('relation','before')
            valid=gap>tolerance if relation=='before' else abs(gap)<=tolerance if relation=='coincident' else None
            if valid is None:raise ValueError('temporal relation must be before or coincident')
            if not valid:raise ValueError(f'temporal relation contradicts cited source times or declared tolerance: relation={relation}, gap_hours={gap}, tolerance_hours={tolerance}')
            result={**claim,'verification':'observed_temporal_order_verified; causality_not_established',
                    'gap_hours':gap,'time_basis':basis,'clock_evidence_ids':clocks,
                    'limitation':('Ordering of explicit record timestamps only; it does not establish process alignment, event onset or causation.' if record_clock else 'Order of sampled observations does not establish event onset or causal direction.')}
        temporal.append(result)
    hypotheses=report.get('hypotheses',report.get('causal_hypotheses',[]))
    unsearched=[h.get('hypothesis_id') for h in hypotheses if h.get('contradicting_evidence_status')=='not_searched']
    if unsearched:issues.append({'code':'counterevidence_search_incomplete','hypothesis_ids':unsearched})
    # Heuristic flags are review prompts, never a semantic proof or censor.
    cautions=[]
    for section,items in [('observed_facts',report.get('observed_facts',[])),('interpretations',report.get('interpretations',[])),('hypotheses',hypotheses)]:
        for index,item in enumerate(items):
            text=str(item.get('statement',''))
            if re.search(r'\b(preceded|coincided with|prior to)\b',text,re.I) and not item.get('temporal_claim_ids'):
                cautions.append({'section':section,'index':index,'code':'temporal_prose_requires_linked_source_clock_claim'})
            if section=='observed_facts' and re.search(r'\b(caused|proves?|confirmed cause|therefore)\b',text,re.I):
                cautions.append({'section':section,'index':index,'code':'causal_interpretation_in_observed_fact'})
    ids={t.get('claim_id') for t in temporal}
    for section in ('observed_facts','interpretations','hypotheses'):
        for item in report.get(section,[]):
            if not set(item.get('temporal_claim_ids',[]))<=ids:raise ValueError('statement references an unknown temporal claim')
    if cautions:issues.append({'code':'scientific_claim_review_required','claims':cautions})
    kind=report.get('report_type','partial_investigation')
    if kind not in {'final_investigation','partial_investigation','sub_investigation','checkpoint'}:raise ValueError('unknown report_type')
    required={'observed_facts':bool(report.get('observed_facts')),'hypotheses':bool(hypotheses),
              'cross_scope_synthesis':bool(str(report.get('cross_scope_synthesis','')).strip()),
              'evidence_requests':'evidence_requests' in report or 'pending_evidence_requests' in report,
              'follow_up_actions':any(isinstance(report.get(k),list) for k in ('tasks','actions_now','follow_up_actions')),
              'uncertainties':'open_questions' in report,'assessment':bool(report.get('assessment'))}
    if kind=='final_investigation' and not all(required.values()):issues.append({'code':'required_deliverables_missing','deliverables':[k for k,v in required.items() if not v]})
    if not expected:issues.append({'code':'screening_scope_unavailable'})
    status='complete_for_available_evidence' if kind=='final_investigation' and not issues else 'incomplete'
    return {'version':'investigation-review-v2','report_type':kind,'report_status':status,
            'screened_unit_count':len(expected),'reviewed_unit_count':sum(v['status'] in {'investigated','reviewed_no_material_signal'} for v in covered.values()),
            'cited_unit_count':len({(r['source_id'],r.get('entity_id')) for r in rows}),
            'coverage':list(covered.values()),'missing_unit_ids':missing,'candidate_reviews':list(reviewed.values()),
            'issues':issues,'temporal_claims':temporal,'required_structure':required,
            'scientific_review_required':True,'causality_verified':False,
            'completion_basis':'structural and source checks only; independent scientific quality review remains required'}
