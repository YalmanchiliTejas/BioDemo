"""Qualification from frozen criteria and independent blinded reviews."""
from __future__ import annotations

from .trace import instant


def score_review(run, policy, review=None):
    review=review or {}; objective=run.get('objective_scores',{}); report=run.get('output',{}).get('analysis') or {}
    if not run.get('attempted'):
        return {'status':run.get('status','not_tested'),'qualified':None,'reasons':[run.get('reason','Not executed.')], 'quality_score':None}
    if not run.get('audit',{}).get('pass') or not run.get('isolation_audit',{}).get('pass'):
        return {'status':'invalid','qualified':False,'quality_score':None,'reasons':['Leakage or permission audit did not pass; scores withheld.']}
    if run.get('status')=='failed':
        return {'status':'failed','qualified':False,'quality_score':None,'reasons':['Execution failed.']}
    if run.get('mode')=='conventional' and not report:
        return {'status':'not_applicable','qualified':None,'quality_score':None,'reasons':['Extraction pipeline does not support equivalent investigation deliverables. Technical preparation scores are separate.']}
    reasons=[]; failures=[]
    if report.get('report_status')=='incomplete' or (run.get('status')=='incomplete' and run.get('investigation_status')!='complete'):
        failures.append('Investigation is incomplete; a sub-investigation or screening cannot qualify as the final dataset-wide report.')
    if review.get('run_id')!=run['run_id'] or review.get('output_sha256')!=run.get('output_sha256'):
        reasons.append('No review bound to this exact run output.')
    people=review.get('reviewers') or [];scores=[]
    for person in people:
        if (not person.get('reviewer_id') or person.get('reviewer_id')==run.get('operator_id') or
                person.get('independent_of_operator') is not True or person.get('blind_to_method') is not True or
                not person.get('evidence_ref')):
            reasons.append('Reviewer independence, blinding or review evidence is incomplete.');continue
        dimensions=person.get('scores',{})
        values=[dimensions.get(d) for d in policy['dimensions']]
        if any(type(v) not in (int,float) or not policy['score_scale'][0]<=v<=policy['score_scale'][1] for v in values):
            reasons.append('Review dimensions are incomplete or out of range.');continue
        scores.append(values)
    if not scores: reasons.append('No complete independent blinded investigation review.')
    disagreement = bool(scores) and any(values!=scores[0] for values in scores[1:])
    adjudicated = False
    if disagreement:
        adjudication=review.get('adjudication') or {}
        values=[adjudication.get('scores',{}).get(d) for d in policy['dimensions']]
        if (not adjudication.get('reviewer_id') or adjudication['reviewer_id'] in [p.get('reviewer_id') for p in people]+[run.get('operator_id')] or
                not adjudication.get('evidence_ref') or any(type(v) not in (int,float) or not 0<=v<=4 for v in values)):
            reasons.append('Review disagreements require independent adjudication.')
        else: scores=[values];adjudicated=True
    threshold=policy.get('minimum_quality_score')
    if policy.get('status')!='approved' or not policy.get('reviewed_by') or type(threshold) not in (int,float) or not policy['score_scale'][0]<=threshold<=policy['score_scale'][1]:
        reasons.append('Minimum quality threshold awaits independent domain approval.')
    if review.get('policy_sha256')!=run['case']['quality_policy_sha256']:
        reasons.append('Review is not bound to the frozen quality policy.')
    # Hard failures cannot be overridden by an approving reviewer.
    if objective.get('investigation',{}).get('unsupported_verified_cause_detected'):
        failures.append('Unsupported assertion of verified causation.')
    claim_checks=report.get('verification',{}).get('claim_verification')
    if claim_checks and claim_checks.get('issues'):
        failures.append('Claim-local automated verification has unresolved issues.')
    citation_checks=objective.get('evidence',{}).get('citation_checks',[])
    if any(not check['pass'] and check.get('verification_status')!='human_review_pending' for check in citation_checks):
        failures.append('Unverifiable source citation.')
    if any(check.get('verification_status')=='human_review_pending' for check in citation_checks) or report.get('source_verification_status')=='human_review_pending':
        reasons.append('Source verification awaits human review; unchecked citations are not certified.')
    for gate in policy['integrity_gates']:
        result=(review.get('integrity_gates') or {}).get(gate)
        if result is False: failures.append('Integrity gate failed: '+gate)
        elif result is not True: reasons.append('Integrity gate unreviewed: '+gate)
    checks=review.get('objective_checks_pass')
    if checks is False:failures.append('Objective checks failed independent review.')
    elif checks is not True:reasons.append('Objective data and evidence checks await review.')
    if objective.get('objective_checks',{}).get('field_values_correct') is False:
        failures.append('Frozen required field checks are incorrect or missing.')
    delivery=review.get('deliverables') or {}
    material = {
        'assessment': bool(report.get('assessment')),
        'evidence_inventory': bool(run.get('output',{}).get('files')),
        'scope': isinstance(report.get('scope'),dict) and bool(report['scope']),
        'hypotheses': isinstance(report.get('hypotheses',report.get('causal_hypotheses')),list) and bool(report.get('hypotheses',report.get('causal_hypotheses'))),
        'counterevidence': 'counterevidence' in report or any('contradicting_evidence_ids' in h for h in report.get('hypotheses',report.get('causal_hypotheses',[])) if isinstance(h,dict)),
        'triage': bool(report.get('triage')),
        'evidence_requests': isinstance(report.get('evidence_requests',report.get('pending_evidence_requests')),list),
        'follow_up_actions': isinstance(report.get('follow_up_actions',report.get('actions_now')),list),
    }
    for name in run['case']['required_deliverables']:
        result=delivery.get(name)
        if result=='unanswerable':
            if name not in run['case'].get('allowed_unanswerable_deliverables',[]) or not review.get('unanswerable_evidence_ref'):
                failures.append('Unsupported abstention for deliverable: '+name)
        elif result is True and material.get(name) is False:failures.append('Reviewed deliverable is absent from actual output: '+name)
        elif result is False:failures.append('Required deliverable missing: '+name)
        elif result is not True:reasons.append('Deliverable unreviewed: '+name)
    quality=sum(sum(v) for v in scores)/sum(len(v) for v in scores) if scores else None
    if quality is not None and type(threshold) in (int,float) and quality<threshold:
        failures.append('Investigation quality below predeclared threshold.')
    return {'status':'failed' if failures else 'pending_review' if reasons else 'qualified',
            'qualified':False if failures else None if reasons else True, 'quality_score':quality,
            'reasons':failures+reasons, 'reviewer_ids':[p.get('reviewer_id') for p in people],
            'review_agreement':not disagreement if scores else None, 'adjudicated':adjudicated}
