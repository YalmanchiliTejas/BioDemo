from . import check

SIM_TOOLS={'physical_pipeline_execute','bioprocess_forecast','cho_dataset_forecast'}


def grade(expect,observations):
    tools=[o for o in observations if o['name']=='tool.call']
    names=[o['tool_name'] for o in tools]
    out=[]
    if expect.get('tool_any_of'):
        out.append(check('necessary_tool_used',bool(set(names)&set(expect['tool_any_of'])),names))
    if expect.get('no_simulation'):
        out.append(check('no_unjustified_simulation',not (set(names)&SIM_TOOLS),names,hard=True))
    if expect.get('simulation_executed'):
        completed=[o for o in tools if o['tool_name'] in SIM_TOOLS and o['status']=='completed' and (o.get('output') or {}).get('status')=='completed']
        out.append(check('actual_registered_simulation',bool(completed),[o['tool_name'] for o in completed]))
    if expect.get('tool_recovered'):
        errors=[o for o in tools if o['status']=='error']
        successes=[o for o in tools if o['status']=='completed' and (o.get('output') or {}).get('status')=='completed']
        out.append(check('bounded_tool_recovery',bool(errors and any(
            e['tool_name']==s['tool_name'] and e['started_at']<=s['started_at'] for e in errors for s in successes)),
            {'errors':len(errors),'completed':len(successes)}))
    return out
