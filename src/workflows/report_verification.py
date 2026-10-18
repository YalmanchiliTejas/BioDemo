"""Deterministic boundary between model synthesis and durable investigation state."""
from __future__ import annotations

from copy import deepcopy
import math
import re

CITATION_KEYS={'evidence_ids','supporting_evidence_ids','contradicting_evidence_ids','numerator_ids','denominator_ids'}


def collect_citations(value):
    identifiers=[]
    def walk(node):
        if isinstance(node,dict):
            for key,item in node.items():
                if key in CITATION_KEYS:
                    if not isinstance(item,list):raise ValueError(f'{key} must be a list')
                    identifiers.extend(map(str,item))
                elif key=='observation_id' and item is not None:identifiers.append(str(item))
                elif key in {'earlier_observation_id','later_observation_id'} and item is not None:identifiers.append(str(item))
                else:walk(item)
        elif isinstance(node,list):
            for item in node:walk(item)
    walk(value)
    return list(dict.fromkeys(identifiers))


def verify_report(report,session,tools,seen_ids):
    report=deepcopy(report)
    for key in ('observed_facts','calculated_metrics','interpretations','hypotheses'):
        if not isinstance(report.get(key,[]),list):raise ValueError(f'{key} must be a list')
    if len(report.get('hypotheses',[]))>12:raise ValueError('report supports at most 12 hypotheses; none may be silently dropped')
    for hypothesis in report.get('hypotheses',[]):
        if not isinstance(hypothesis,dict):raise ValueError('hypotheses must be objects')
        if hypothesis.get('root_cause_confirmed') or hypothesis.get('status') in {'verified','verified_cause','confirmed','proven','established'} or hypothesis.get('classification')=='verified_cause':
            raise ValueError('source evidence and arithmetic do not establish a verified root cause')
        confidence=hypothesis.get('confidence')
        if confidence is not None and (isinstance(confidence,bool) or not isinstance(confidence,(float,int)) or not math.isfinite(confidence)):
            raise ValueError('hypothesis confidence must be a finite number')
        for role in ('supporting','contradicting'):
            links=hypothesis.get(role+'_evidence_ids',[])
            if not isinstance(links,list):raise ValueError('hypothesis evidence IDs must be lists')
            if links:
                if hypothesis.get(role+'_evidence_status','found')!='found':raise ValueError('hypothesis evidence status conflicts with its citations')
                hypothesis[role+'_evidence_status']='found'
                hypothesis[role+'_evidence_absence_reason']=None
            else:
                if hypothesis.get(role+'_evidence_status') not in {'none_found','not_searched'} or not str(hypothesis.get(role+'_evidence_absence_reason','')).strip():
                    raise ValueError(f"{hypothesis.get('hypothesis_id','hypothesis')}: empty {role} evidence requires none_found/not_searched and an explicit absence reason")
    if len(report.get('calculated_metrics',[]))>64:raise ValueError('a report supports at most 64 calculated metrics')
    if report.get('calculated_metrics'):tools.analysis()._lineage(force=True)
    metrics=[]
    for item in report.get('calculated_metrics',[]):
        if not isinstance(item,dict):raise ValueError('calculated metrics must be objects')
        spec=deepcopy(item.get('specification',item))
        if 'value' in item:
            spec['claimed_value']=item['value']
            spec.pop('display_decimals',None)
        if 'claimed_value' not in spec:raise ValueError('calculated metric must declare its claimed_value or returned value')
        metric=tools.analysis().calculate(spec)
        metrics.append(metric)
    report['calculated_metrics']=metrics
    cited=collect_citations(report)
    if not cited or not set(cited)<=seen_ids:raise ValueError('report cites evidence not retrieved in this run')
    rows=session.get(cited)
    if len(rows)!=len(cited):raise ValueError('report cites unavailable evidence')
    by_id={row['id']:row for row in rows}
    checks=tools.verify_many(rows)
    if any(not c['source_integrity'] or c['value_matches'] is False or c.get('verification_status')=='human_rejected' for c in checks.values()):
        raise ValueError('material citation does not match the immutable original source; re-ingest legacy stores with the current precision-preserving reader before retrying')
    facts=[]
    for item in report.get('observed_facts',[]):
        if not isinstance(item,dict) or not str(item.get('statement','')).strip():raise ValueError('observed facts require a statement')
        ids=collect_citations(item)
        if not ids:raise ValueError('observed fact requires original observation citations')
        if 'claimed_value' in item:
            if len(ids)!=1:raise ValueError('a direct claimed source value requires exactly one observation')
            row=by_id[ids[0]];claimed=item['claimed_value']
            if row['value_number'] is not None and not isinstance(claimed,bool):
                try:matches=math.isclose(float(claimed),row['value_number'],rel_tol=1e-6,abs_tol=0.0)
                except (ValueError,TypeError):matches=False
            else:matches=str(claimed)==row['value_text']
            if not matches:raise ValueError('observed fact value differs from its cited observation')
            if 'claimed_unit' in item and item['claimed_unit']!=row['unit']:
                raise ValueError('observed fact unit differs from its source; conversions belong in calculated_metrics')
            if 'claimed_time_value' in item:
                if row.get('time_evidence_id') not in by_id or row.get('time_value') is None:
                    raise ValueError('claimed source time requires a visible cited source clock cell')
                try:time_matches=math.isclose(float(item['claimed_time_value']),row['time_value'],rel_tol=1e-9,abs_tol=0)
                except (ValueError,TypeError):time_matches=False
                if not time_matches or item.get('claimed_time_basis')!=row.get('time_basis'):
                    raise ValueError('observed fact time differs from the cited source coordinate')
        facts.append({**item,'evidence_ids':ids,'verification':('cited_values_verified; statement meaning and causality are not verified' if all(checks[i]['value_matches'] is True for i in ids) else 'requires_source_review')})
    report['observed_facts']=facts
    interpretations=[]
    metric_ids={m['metric_id'] for m in metrics}
    for item in report.get('interpretations',[])+report.get('findings',[]):
        if not isinstance(item,dict) or not str(item.get('statement','')).strip():raise ValueError('interpretations require a statement')
        referenced=item.get('metric_ids',[])
        if not isinstance(referenced,list) or not set(referenced)<=metric_ids:raise ValueError('interpretation references an unknown metric')
        interpretations.append({**item,'classification':'interpretation','verification':'requires_human_review'})
    report['interpretations']=interpretations
    report['evidence_ids']=cited
    if len({m['metric_id'] for m in metrics})!=len(metrics):raise ValueError('metric IDs must be unique')
    verification={'version':'report-verification-v1','status':'checks_passed; scientific_review_required',
                  'evidence_checks':checks,'numerical_metrics_verified':len(metrics),
                  'reported_mean_sem_policy':'source summaries are transcribed; raw replicate statistics require actual replicate observations',
                  'narrative_status':'requires_human_review; arithmetic verification covers structured calculated_metrics only',
                  'causality_verified':False,
                  'unverified_source_count':sum(c['value_matches'] is not True for c in checks.values()),
                  'hypotheses_without_support':[h.get('hypothesis_id') for h in report.get('hypotheses',[]) if not h.get('supporting_evidence_ids')],
                  'hypotheses_without_contradiction_search':[h.get('hypothesis_id') for h in report.get('hypotheses',[]) if h.get('contradicting_evidence_status')=='not_searched']}
    # A conservative coverage diagnostic, not a semantic proof of prose. An
    # unmatched literal cannot be marked numerically verified just because some
    # unrelated structured metric passed. Rounded source/metric values are allowed.
    allowed={0.0,1.0,100.0}
    for row in rows:
        for value in (row.get('value_number'),row.get('time_value')):
            if value is not None:
                allowed.add(float(value))
                allowed.update(round(float(value),d) for d in range(-6,7))
    for metric in metrics:
        allowed.update([metric['value'],metric['display_value']])
    from .claim_verification import check_claims, displayed_metric_values
    if 'claims' in report:
        # These receipts use recomputed metrics, not model-supplied arithmetic.
        checked = check_claims(report, rows, metrics)
        metric_map = {m['metric_id']: m for m in metrics}
        for claim in checked['claims']:
            if not claim['issues']:
                allowed.update(displayed_metric_values(claim, metric_map))
    texts=[('assessment',report.get('assessment',''))]
    texts += [('hypothesis:'+str(h.get('hypothesis_id')),h.get('statement','')) for h in report.get('hypotheses',[])]
    texts += [('interpretation',item.get('statement','')) for item in interpretations]
    from .claim_verification import NUMBER
    unlinked=[]
    for section,text in texts:
        for match in NUMBER.finditer(str(text)):
            number=float(match.group())
            if not math.isfinite(number) or not any(math.isclose(number,v,rel_tol=1e-6,abs_tol=0) for v in allowed):
                unlinked.append({'section':section,'literal':match.group()})
    verification['unlinked_numeric_literals']=unlinked[:100]
    verification['unlinked_numeric_literal_count']=len(unlinked)
    verification['prose_check_limit']='literal coverage only; matching a source number does not establish the sentence’s meaning or calculation'
    if unlinked:verification['status']='requires_numerical_review'
    pending=[c for c in checks.values() if c['value_matches'] is None and c.get('verification_status')!='human_verified']
    if pending:verification['status']='requires_source_review'
    if 'claims' in report:
        from .claim_verification import check_claims
        verification['claim_verification']=check_claims(report,rows,metrics)
        if verification['claim_verification']['issues']:
            verification['status']='requires_claim_review'
    verification['human_verified_source_count']=sum(c.get('verification_status')=='human_verified' for c in checks.values())
    verification['pending_source_review_count']=len(pending)
    verification['source_verification_status']='human_review_pending' if pending else 'verified_with_human_review' if verification['human_verified_source_count'] else 'automatically_verified'
    from urllib.parse import quote
    verification['pending_source_reviews']=[{'observation_id':i,'source_ref':c['source_ref'],
        'review_url':'/manufacturing-source-review/'+quote(i,safe='')+'?as_of='+quote(session.as_of,safe=''),
        'reason':c.get('review_reason','Original source requires human review')} for i,c in checks.items() if c in pending]
    return report,rows,verification


def evidence_scope(rows):
    batches=sorted({r['batch_id'] for r in rows if r.get('batch_id')})
    runs=sorted({r['run_id'] for r in rows if r.get('run_id')})
    experiments=sorted({r['experiment_id'] for r in rows if r.get('experiment_id')})
    equipment=sorted({r['equipment_id'] for r in rows if r.get('equipment_id')})
    kind=('multi_experiment' if len(experiments)>1 else 'single_experiment' if experiments else
          'multi_batch' if len(batches)>1 else 'single_batch' if batches else
          'multi_run' if len(runs)>1 else 'single_run' if runs else 'undetermined')
    return {'type':kind,'batch_ids':batches,'run_ids':runs,'experiment_ids':experiments,'equipment_ids':equipment,
            'basis':'cited_evidence_coverage; affected units require explicit adjudication',
            'hierarchy_status':'experiment groups are candidates inferred from source run hierarchy'}
