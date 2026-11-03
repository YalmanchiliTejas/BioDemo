import json
from . import check


def latest_checkpoint(snapshot):
    ref=snapshot['mission'].get('summary') or {}
    return next((a['state'] for a in snapshot['artifacts'] if a['id']==ref.get('id')),None)


def grade(expect,before,after):
    checks=[]
    checkpoint=latest_checkpoint(after)
    if expect.get('two_sessions'):
        ids={s['id'] for s in after['sessions']}
        checks.append(check('distinct_persisted_sessions',len(ids)>=2,sorted(ids)))
    if expect.get('recall'):
        previous={t['id'] for t in before['turns']}
        replies=' '.join(t.get('reply') or '' for t in after['turns'] if t['id'] not in previous)
        checks.append(check('cross_session_literal_recall',all(str(x).casefold() in replies.casefold() for x in expect['recall']),
                            {'expected_terms':expect['recall'],'actual_reply':replies,
                             'limitation':'Term presence is not a semantic correctness grade.'}))
    if expect.get('checkpoint'):
        checks.append(check('durable_mission_checkpoint',bool(checkpoint and checkpoint.get('next_action')
                            and checkpoint.get('inputs') and checkpoint.get('review_state')=='unapproved_assessment'),
                            {'summary_ref':after['mission'].get('summary'),'checkpoint':checkpoint}))
    if 'work_status_any_of' in expect:
        checks.append(check('work_status',bool(checkpoint and checkpoint.get('work_status') in expect['work_status_any_of']),
                            {'expected':expect['work_status_any_of'],'actual':(checkpoint or {}).get('work_status')}))
    if 'evidence_in_state' in expect:
        refs={r['id'] for r in (checkpoint or {}).get('inputs',[])}
        needed={'EVAL:'+x for x in expect['evidence_in_state']}
        checks.append(check('evidence_in_durable_assessment',needed<=refs,{'required':sorted(needed),'actual':sorted(refs)}))
    if expect.get('current_revision'):
        current={e['id']:e['revision'] for e in after['evidence']}
        refs=(checkpoint or {}).get('inputs',[])
        evidence_refs=[r for r in refs if r['id'] in current]
        checks.append(check('current_assessment_evidence_revision',bool(evidence_refs) and all(
            r['revision']==current[r['id']] for r in evidence_refs),{'basis':evidence_refs,'current':current}))
    return checks
