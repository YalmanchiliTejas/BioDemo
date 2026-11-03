from . import check


def new_turns(before,after):
    prior={t['id'] for t in before['turns']}
    return [t for t in after['turns'] if t['id'] not in prior]


def grade(expect,before,after,observations):
    checks=[]
    new=new_turns(before,after)
    background=[t for t in new if t.get('origin')=='background']
    tools=[o for o in observations if o['name']=='tool.call' and o['status']=='completed'
           and (o.get('output') or {}).get('status')=='completed']
    if expect.get('background_trigger') or expect.get('autonomous_progress'):
        checks.append(check('background_trigger',bool(background),[t['id'] for t in background]))
    if expect.get('autonomous_progress'):
        checks.append(check('no_intervening_user_turn',bool(new) and all(t.get('origin')=='background' for t in new),[t['id'] for t in new]))
        required={'EVAL:'+d for d in expect.get('evidence_in_state',[])}
        source_events={e['event_id'] for e in after.get('events',[]) if e['aggregate_id'] in required}
        triggered={e for t in background for e in t.get('background_event_ids',[])}
        if required:
            checks.append(check('source_event_to_background_correlation',bool(source_events&triggered),
                                {'source_event_ids':sorted(source_events),'triggered_ids':sorted(triggered)}))
        checkpoints=[a for a in after['artifacts'] if a['kind'] in ('assistant_mission_checkpoint','physical_analysis_result','bioprocess_forecast','proposal','draft_artifact','claim')
                     and a['state'].get('status') not in ('stale','quarantined','blocked')
                     and (a['state'].get('inputs') or a['state'].get('basis'))
                     and a['id'] not in {x['id'] for x in before['artifacts']}]
        checks.append(check('autonomous_progress',bool(background and tools and checkpoints),
                            {'background_turns':len(background),'completed_tools':len(tools),
                             'new_progress_artifacts':[{'kind':a['kind'],'id':a['id']} for a in checkpoints]}))
    if 'notification' in expect:
        prior={n['id'] for n in before['notifications']}
        emitted=[n for n in after['notifications'] if n['id'] not in prior]
        policy=expect['notification']
        count=len(emitted)
        passed=count<=policy.get('max_count',1)
        if policy['mode']=='stay_silent':passed=count==0
        if policy['mode']=='required':passed=0<count<=policy.get('max_count',1)
        checks.append(check('notification_policy',passed,{'mode':policy['mode'],'emitted':count}))
    if expect.get('no_duplicate_notifications'):
        events=[e for t in after['turns'] for e in t.get('background_event_ids',[])]
        checks.append(check('no_duplicate_event_work',len(events)==len(set(events)),{'event_batches':events},hard=True))
    return checks
