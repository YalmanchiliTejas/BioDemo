"""Explicit, versioned routing rules. Draft defaults do not establish site approval."""
from __future__ import annotations

from copy import deepcopy

DEFAULT_POLICY={
    'version':'illustrative-routing-v1','status':'draft','reviewed_by':[],
    'severity_by_level':{'L1':'MEDIUM','L2':'HIGH','L3':'CRITICAL','unclassified':'UNKNOWN'},
    'required_roles':{'L1':['qa'],'L2':['qa','msat'],'L3':['qa','sponsor_qa'],'unclassified':[]},
    'rules':[{'level':'L3','signals':['critical'],'minimum_entities':1},
             {'level':'L2','signals':['action'],'minimum_entities':2},
             {'level':'L1','signals':['critical','action','alert'],'minimum_entities':1}],
}


def validate_policy(policy=None):
    policy=deepcopy(DEFAULT_POLICY if policy is None else policy)
    if not isinstance(policy,dict) or not policy.get('version') or policy.get('status') not in {'draft','approved'}:
        raise ValueError('triage policy requires a version and draft/approved status')
    if policy['status']=='approved' and not policy.get('reviewed_by'):
        raise ValueError('approved triage policy requires named reviewers')
    for level in ('L1','L2','L3','unclassified'):
        if policy.get('severity_by_level',{}).get(level) not in {'LOW','MEDIUM','HIGH','CRITICAL','UNKNOWN'}:
            raise ValueError('triage policy must map each level to a severity')
        if not isinstance(policy.get('required_roles',{}).get(level),list):raise ValueError('triage policy must declare required review roles')
    if not isinstance(policy.get('rules'),list):raise ValueError('triage policy requires explicit ordered rules')
    for rule in policy['rules']:
        if rule.get('level') not in {'L1','L2','L3'} or not set(rule.get('signals',[]))<={'critical','action','alert'} or not rule.get('signals'):
            raise ValueError('invalid triage rule')
        if type(rule.get('minimum_entities')) is not int or rule['minimum_entities']<1:raise ValueError('invalid minimum entity count')
    return policy


def classify(signals,policy=None):
    policy=validate_policy(policy)
    reliable=[s for s in signals if s['validation_status'] in {'source_transcribed','normalized'}]
    level='unclassified';reason='No policy rule matched verified categorical source signals.'
    matched_ids=[]
    for rule in policy['rules']:
        matched=[s for s in reliable if s['signal'] in rule['signals']]
        entities={s['entity_id'] for s in matched if s.get('entity_id')}
        if matched and len(entities)>=rule['minimum_entities']:
            level=rule['level'];reason=f"Policy {policy['version']} matched {', '.join(rule['signals'])} in {len(entities)} entities."
            matched_ids=[s['evidence_id'] for s in matched];break
    return {'level':level,'severity':policy['severity_by_level'][level],'reason':reason,
            'provisional':policy['status']!='approved','policy':policy['version'],
            'policy_status':policy['status'],'policy_reviewers':policy.get('reviewed_by',[]),
            'required_review_roles':policy['required_roles'][level],'evidence_ids':matched_ids}
