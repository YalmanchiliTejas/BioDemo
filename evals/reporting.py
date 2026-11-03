"""Chronological reports with actual denominators and explicit coverage gaps."""
import json
from pathlib import Path
from .graders import overall


def ratio(numerator,denominator):
    return {'numerator':numerator,'denominator':denominator,
            'value':numerator/denominator if denominator else None}


def metrics(mission):
    opportunities=[e for e in mission['timeline'] if e.get('expected',{}).get('autonomous_progress')]
    progress=sum(any(c['name']=='autonomous_progress' and c['status']=='PASS' for c in e['checks']) for e in opportunities)
    noise=[e for e in mission['timeline'] if e.get('expected',{}).get('notification',{}).get('mode')=='stay_silent']
    false=sum(e.get('notifications_emitted',0) for e in noise)
    interventions=sum(e.get('completed_tool_calls',0)>0 for e in mission['timeline'] if e.get('type')!='user_message')
    useful=sum(e.get('completed_tool_calls',0)>0 for e in opportunities if any(c['name']=='autonomous_progress' and c['status']=='PASS' for c in e['checks']))
    milestones=[c for e in mission['timeline'] for c in e['checks']
                if c['name'] in ('autonomous_progress','durable_mission_checkpoint','cross_session_literal_recall','background_trigger')]
    return {'proactive_precision':ratio(useful,interventions),
            'proactive_recall':ratio(progress,len(opportunities)),
            'false_interruptions':ratio(false,len(noise)),
            'mission_milestones':ratio(sum(c['status']=='PASS' for c in milestones),len(milestones)),
            'definition':'Interventions count event activations with actual completed tools; useful progress requires a new durable assessment. In-app publications are measured separately from external delivery.'}


def write(report,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,default=str)+'\n')
    lines=[f"# Mission evaluation: {report['suite']}\n",f"Status: **{report['status']}**. Mode: {report['mode']}.\n",
           f"Missions: {report['counts']['missions']}; events: {report['counts']['events']}; sessions: {report['counts']['sessions']}; actual provider responses: {report['counts']['provider_responses']}.\n",
           'Synthetic behavior evaluation; no scientific, GMP, or plant-autonomy validation.\n']
    for mission in report['missions']:
        lines.extend([f"\n## {mission['id']} — {mission['status']}\n",mission['goal']+'\n',
                      '| Time | Event | Result | Evidence |','| --- | --- | --- | --- |'])
        for event in mission['timeline']:
            failed=', '.join(c['name'] for c in event['checks'] if c['status']=='FAIL')
            lines.append(f"| {event['at']} | {event['type']} | {event['status']} | {failed or event.get('note','')} |")
        lines.extend(['\nMetrics: `'+json.dumps(mission['metrics'])+'`\n',
                      'Final assertions: `'+json.dumps(mission['final_checks'])+'`\n',
                      'Trace references: `'+json.dumps(mission['trace_refs'])+'`\n',
                      'Local evidence: '+mission['evidence_directory']+'\n'])
    lines.append('\n## Outstanding coverage\n')
    for gap in report['outstanding_work']:
        lines.append('- '+gap)
    path.with_suffix('.md').write_text('\n'.join(lines)+'\n')
    (path.parent/'summary.md').write_text('\n'.join(lines)+'\n')
    (path.parent/'outstanding-work.md').write_text('# Outstanding evaluation work\n\n'+'\n'.join('- '+s for s in report['outstanding_work'])+'\n')


def timing(trigger_at,before,after):
    """Virtual scheduling and real execution times have distinct meanings."""
    from src.lifesci.ids import parse_iso
    previous={t['id'] for t in before['turns']}
    new=[t for t in after['turns'] if t['id'] not in previous and t.get('origin')=='background']
    due=[o['due_at'] for o in before['mission'].get('obligations',[])
         if o.get('status')=='open' and o.get('due_at') and parse_iso(o['due_at'])<=parse_iso(trigger_at)]
    activation=min((t['created_at'] for t in new),default=None)
    basis=min(due) if due else trigger_at
    return {'trigger_time':trigger_at,'scheduled_due_at':min(due) if due else None,
            'action_time':activation,
            'virtual_delay_seconds':(parse_iso(activation)-parse_iso(basis)).total_seconds() if activation else None,
            'real_turn_elapsed_seconds':[t.get('elapsed_seconds') for t in new],
            'meaning':'Virtual time measures event/timer activation; real elapsed time measures model/tool work. No production latency SLA is inferred.'}
