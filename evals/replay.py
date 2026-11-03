"""Regrade retained real outcomes, preserving the agent version and original receipts."""
from copy import deepcopy
from pathlib import Path
import json
import uuid
import yaml

from .graders import check,overall
from .graders import mission as mission_grader
from .reporting import metrics,write,timing


def publications(snapshot):
    # API-visible artifacts also count when a later model call failed to answer.
    snapshot=deepcopy(snapshot)
    snapshot['notifications']=[{'channel':'in_app','id':t['id'],'at':t['created_at'],
        'reply':t.get('reply'),'artifacts':t.get('artifacts',[])} for t in snapshot['turns']
        if t.get('origin')=='background' and t.get('notification_status')!='suppressed'
        and (t.get('reply') or t.get('artifacts'))]
    return snapshot


def regrade(source_path,output,*,suite,case_ids=None):
    from .runner import BASE,code_fingerprint,versions
    from .schema import load_case
    source_path=Path(source_path).resolve()
    source=json.loads(source_path.read_text())
    definitions={c['id']:c for c in (load_case(p) for p in (BASE/'missions').glob('*.yaml'))}
    selected=set(case_ids or (['batch_risk_watch_01'] if suite=='smoke' else
        ['sop_change_monitor_01','conflicting_source_revision_01','cross_tenant_memory_isolation_01'] if suite=='memory' else definitions))
    missions=[]
    for old in source['missions']:
        if old['id'] not in selected:continue
        if old.get('evaluation_mode')=='scripted_contract_test':
            raise ValueError('Scripted contracts cannot be labeled as recorded real-model evaluations')
        case=definitions[old['id']]
        world=yaml.safe_load((BASE/'fixtures/worlds'/f"{case['world']}.yaml").read_text())
        truth=yaml.safe_load((BASE/'fixtures/truth'/f"{case['world']}.yaml").read_text())
        if old.get('variant'):
            for document in world['initial']+world['updates']+world.get('distractors',[]):
                document['content']='Synthetic source formatting variant '+str(old['variant'])+'\n'+document['content']
        if source['suite']=='smoke':
            case=deepcopy(case);case['timeline']=case['timeline'][:4];case['final_expect']={'no_unauthorised_writes':True}
        from src.lifesci.ids import content_hash
        if content_hash({'case':case,'world':world,'truth':truth})!=old['fixture_hash']:
            raise ValueError('Fixture definition changed; cannot silently regrade '+old['id'])
        mission=deepcopy(old)
        directory=Path(old['evidence_directory'])
        if not directory.exists():
            directory=source_path.parent/'runs'/directory.parent.name/directory.name
        if not directory.exists():raise FileNotFoundError('Retained run evidence is required; extract the campaign archive under reports/runs: '+str(directory))
        mission['recorded_evidence_directory']=old['evidence_directory']
        mission['evidence_directory']=str(directory)
        for index,row in enumerate(mission['timeline']):
            path=directory/f'step-{index:02d}.json'
            if not path.exists():continue  # Preserve recorded failed/skipped operations verbatim.
            evidence=json.loads(path.read_text())
            before,after=publications(evidence['before']),publications(evidence['after'])
            row['timing']=timing(row['at'],before,after)
            counts=next((c['evidence'] for c in row['checks'] if c['name']=='no_duplicate_provider_calls'),{})
            checks=mission_grader.grade(row.get('expected',{}),before,after,evidence['observations'],
                provider_calls_before=counts.get('before',0),provider_calls_after=counts.get('after',0))
            row['checks']=checks or row['checks']
            row['status']=overall(row['checks'])
            previous={n['id'] for n in before['notifications']}
            row['notifications_emitted']=sum(n['id'] not in previous for n in after['notifications'])
        final=publications(json.loads((directory/'final-state.json').read_text()))
        observations=[json.loads(line) for line in (directory/'observations.jsonl').read_text().splitlines()]
        checks=mission_grader.grade(case['final_expect'],final,final,observations)
        # Resource admissions and code immutability were measured during the actual run.
        preserve={'tool_call_budget','notification_budget','step_budget','code_unchanged_during_mission'}
        checks.extend(c for c in old['final_checks'] if c['name'] in preserve and c['name']!='notification_budget')
        checks.append(check('notification_budget',len(final['notifications'])<=case['limits']['max_emitted_notifications'],len(final['notifications'])))
        action_count=sum(o['name']=='tool.call' for o in observations)+sum(bool(t.get('reply') or t.get('artifacts')) for t in final['turns'])
        checks.append(check('agent_action_budget',action_count<=case['limits']['max_agent_actions'],action_count))
        mission['final_checks']=checks
        mission['notifications']=len(final['notifications'])
        mission['metrics']=metrics(mission)
        mission['status']=overall([c for row in mission['timeline'] for c in row['checks']]+checks)
        mission['evaluation_mode']='recorded_actual_application_regrade'
        mission['source_status']=old['status']
        missions.append(mission)
    if not missions:raise ValueError('No matching recorded missions')
    report=deepcopy(source)
    report.update(suite=suite,run_id='regrade-'+uuid.uuid4().hex[:12],missions=missions,
        mode='Recorded real application outcomes; no new inference. Full selected source missions are retained, including for smoke.',
        source_report=str(source_path),source_report_hash=__import__('hashlib').sha256(source_path.read_bytes()).hexdigest(),
        grader_versions=versions(),new_provider_requests=0,
        status=overall([{'status':m['status']} for m in missions]),
        counts={'missions':len(missions),'events':sum(len(m['timeline']) for m in missions),
                'sessions':sum(m.get('session_count',0) for m in missions),
                'background_turns':sum(m.get('background_turns',0) for m in missions),
                'provider_responses':sum(c['status']=='completed' for m in missions for c in m['provider_calls'])})
    report['outstanding_work']=[s for s in source['outstanding_work'] if not any(s.startswith(m['id']+':') for m in source['missions'])]
    report['outstanding_work']+=sorted({f"{m['id']}: {c['name']} {c['status']}" for m in missions
        for c in m['final_checks']+[c for row in m['timeline'] for c in row['checks']] if c['status']=='FAIL'})
    write(report,output)
    return report
