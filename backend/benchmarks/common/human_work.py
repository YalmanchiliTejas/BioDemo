"""Seven-stage observed human effort, including failed attempts and measured setup."""
from __future__ import annotations

import math
from collections import defaultdict

from .case_protocol import GROUPS
from .trace import instant

VERSION='manufacturing-human-work-v2'
PHASES=('setup','data_preparation','investigation','verification','corrections','coordination','ongoing_configuration')


def template(run_ids=()):
    return {'version':VERSION,'setup_groups':[], 'runs':[
        {'run_id':identifier,'effort_complete':False,'time_source':'observed',
         'evidence_ref':None,'phases':{p:{'active_seconds':None,'manual_actions':None} for p in PHASES},
         'intervals':[], 'note':'Include every participant, retry, correction and coordination interval. An observed zero is different from unmeasured.'}
        for identifier in run_ids]}


def _number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0


def aggregate_effort(runs, logs, *, allocation_universe=None):
    if logs.get('version')!=VERSION: raise ValueError('human-work version mismatch; legacy five-phase estimates cannot be migrated as measurements')
    known={r['run_id']:r for r in runs}; universe={r['run_id']:r for r in (allocation_universe if allocation_universe is not None else runs)}; rows={};errors=[]
    global_intervals=defaultdict(list); overlapping=set()
    for logged in logs.get('runs',[]):
        for interval in logged.get('intervals',[]):
            try:
                global_intervals[interval['participant_id']].append((instant(interval['started_at']),instant(interval['ended_at']),logged['run_id']))
            except (KeyError,ValueError,TypeError):
                continue  # per-run validation below reports malformed intervals
    for intervals in global_intervals.values():
        ordered=sorted(intervals)
        for i,current in enumerate(ordered):
            for previous in ordered[:i]:
                if current[0]<previous[1]:overlapping.update((current[2],previous[2]))
    for row in logs.get('runs',[]):
        if row.get('run_id') not in known:
            if row.get('run_id') not in universe:errors.append('Unknown run in human ledger.')
            continue
        if row['run_id'] in rows:raise ValueError('duplicate human effort row')
        rows[row['run_id']]=row
    allocations=defaultdict(float); setup_totals=defaultdict(float);first_case_setup=defaultdict(float)
    for group in logs.get('setup_groups',[]):
        ids=group.get('run_ids',[])
        if (not ids or len(ids)!=len(set(ids)) or group.get('measured_case_count')!=len(ids) or
            group.get('allocation')!='equal' or not group.get('evidence_ref') or group.get('time_source')!='observed' or
            not _number(group.get('active_seconds')) or any(i not in universe or not universe[i].get('attempted') for i in ids) or
            len({universe[i]['mode'] for i in ids if i in universe})!=1):
            errors.append('Invalid setup allocation; use actual attempted cases, observed setup and an explicit equal-allocation policy.');continue
        first=min(ids,key=lambda i:universe[i]['started_at'])
        for identifier in ids:
            allocations[identifier]+=group['active_seconds']/len(ids)
            setup_totals[identifier]+=group['active_seconds']
        first_case_setup[first]+=group['active_seconds']
    per_run={}; by_actor=defaultdict(list)
    for identifier,run in known.items():
        row=rows.get(identifier,{}); issues=list(errors)
        if identifier in overlapping:issues.append('Participant active-work intervals overlap across study runs or conditions.')
        if row.get('effort_complete') is not True:issues.append('Complete effort attestation absent.')
        if row.get('time_source')!='observed':issues.append('Self-reported estimates cannot establish measured labor savings.')
        if not row.get('evidence_ref'):issues.append('Timing evidence reference missing.')
        phases={}; actions={}
        for phase in PHASES:
            values=row.get('phases',{}).get(phase,{})
            seconds=values.get('active_seconds'); count=values.get('manual_actions')
            if not _number(seconds) or type(count) is not int or count<0:
                issues.append('Unmeasured stage: '+phase)
            phases[phase]=seconds;actions[phase]=count
        intervals=row.get('intervals',[])
        if intervals:
            totals=defaultdict(float)
            for event in intervals:
                try:
                    start,end=instant(event['started_at']),instant(event['ended_at'])
                    active=event['active_human_seconds']; actor=event['participant_id'];phase=event['effort_stage']
                    if not actor or phase not in PHASES or not _number(active) or not 0<=active<=(end-start).total_seconds():raise ValueError('Invalid interval')
                    totals[phase]+=active;by_actor[actor].append((start,end,identifier))
                except (KeyError,ValueError,TypeError):issues.append('Invalid active-work timing interval.')
            for phase in PHASES:
                if _number(phases[phase]) and not math.isclose(phases[phase],totals[phase],abs_tol=.001):issues.append('Intervals disagree with phase total: '+phase)
        complete=not issues
        allocated=allocations[identifier]
        measured_phases={p:phases[p]/3600 if complete else None for p in PHASES}
        if complete:measured_phases['setup']+=allocated/3600
        local=sum(phases.values()) if complete else None
        per_run[identifier]={'status':'observed' if complete else 'not_measured','issues':issues,
            'phases_hours':measured_phases,'manual_actions':sum(actions.values()) if complete else None,
            'total_hours':(local+allocated)/3600 if complete else None,
            'allocated_setup_hours':allocated/3600 if complete else None,
            'unamortized_case_hours':(local+setup_totals[identifier])/3600 if complete else None,
            'first_case_hours':(local+first_case_setup[identifier])/3600 if complete else None,
            'repeat_case_hours':(local-phases['setup'])/3600 if complete else None}
    for actor,intervals in by_actor.items():
        ordered=sorted(intervals)
        for previous,current in zip(ordered,ordered[1:]):
            if current[0]<previous[1]:
                for identifier in (previous[2],current[2]):
                    per_run[identifier].update(status='not_measured',total_hours=None,
                                               issues=per_run[identifier]['issues']+['Overlapping work intervals for participant '+actor])
                    per_run[identifier]['phases_hours']={p:None for p in PHASES}
    groups={}
    for mode,label in GROUPS.items():
        cohort=[r for r in runs if r['mode']==mode and r.get('attempted')]
        eligible=[r for r in cohort if r.get('qualification',{}).get('status')!='not_applicable']
        determinate=bool(eligible) and all(r.get('qualification',{}).get('qualified') is not None for r in eligible)
        qualified=sum(r.get('qualification',{}).get('qualified') is True for r in eligible)
        effort_complete=bool(cohort) and all(per_run[r['run_id']]['status']=='observed' for r in cohort)
        hours=sum(per_run[r['run_id']]['total_hours'] for r in cohort) if effort_complete else None
        groups[mode]={'label':label,'attempted_cases':len(cohort),'qualified_cases':qualified,
                      'pending_review_cases':sum(r.get('qualification',{}).get('qualified') is None for r in eligible),
                      'quality_qualified_rate':qualified/len(eligible) if determinate else None,
                      'total_human_hours_all_attempts':hours,
                      'human_hours_per_qualified_case':hours/qualified if determinate and hours is not None and qualified else None,
                      'effort_per_qualified_status':'undefined' if determinate and not qualified else 'observed' if determinate and hours is not None else 'not_measured',
                      'phases_hours':{p:sum(per_run[r['run_id']]['phases_hours'][p] for r in cohort) if effort_complete else None for p in PHASES},
                      'status':'not_tested' if not cohort else 'not_applicable' if not eligible else 'observed' if determinate and effort_complete else 'pending_measurement'}
    return {'version':VERSION,'per_run':per_run,'groups':groups,'setup_policy':'Measured shared setup allocated equally across declared actual attempts, including failures. First-case cost shown without amortization.'}


def produce_comparison(runs, effort, baseline='manual', target='full_rlm'):
    candidates=[r for r in runs if r['mode'] in (baseline,target) and r.get('attempted')]
    pairs=defaultdict(dict); issues=[]; paired=[]
    for run in candidates:
        case=run['case']
        key=(case['case_id'],case['package_sha256'],case['task_spec_sha256'],case['condition'],case.get('seed'))
        if run['mode'] in pairs[key]:issues.append('Repeated assignments require explicit independent pairing; no cherry-picked fastest run.')
        pairs[key][run['mode']]=run
    for pair in pairs.values():
        if baseline not in pair or target not in pair:continue
        a,b=pair[baseline],pair[target]
        if not all(r.get('qualification',{}).get('qualified') is True for r in (a,b)):continue
        policy=b.get('quality_policy',{});margin=policy.get('noninferiority_margin')
        if type(margin) not in (int,float) or not math.isfinite(margin) or margin<0 or policy.get('status')!='approved':
            issues.append('Noninferiority margin is not predeclared and independently approved.');continue
        if b['qualification']['quality_score']<a['qualification']['quality_score']-margin:
            issues.append('Matched OS investigation fails the approved noninferiority margin.');continue
        ae,be=effort['per_run'][a['run_id']],effort['per_run'][b['run_id']]
        if ae['status']!='observed' or be['status']!='observed':
            issues.append('Matched qualified outcomes lack complete observed human effort.');continue
        paired.append((a,b,ae['total_hours'],be['total_hours']))
    before=sum(p[2] for p in paired);after=sum(p[3] for p in paired)
    if not paired:issues.append('No matched, quality-qualified, timed pair.')
    if paired and before==0:issues.append('Zero baseline effort makes percentage undefined.')
    return {'baseline':baseline,'target':target,'paired_sample_size':len(paired),
            'paired_human_effort_reduction_pct':100*(1-after/before) if paired and before and not issues else None,
            'status':'observed' if paired and before and not issues else 'not_measured', 'issues':issues,
            'all_attempt_groups':effort['groups'], 'note':'Success-only paired effort is accompanied by all-attempt qualification rates and effort per qualified case. Datasets and conditions are not pooled.'}


class ActiveWorkTimer:
    """Explicit operator timer with pauses; machine waiting is not active labor."""
    def __init__(self,sink,*,participant_id,effort_stage):
        import time
        from .trace import now
        if effort_stage not in PHASES or not participant_id:raise ValueError('participant and valid effort stage required')
        self.sink,self.participant_id,self.effort_stage=sink,participant_id,effort_stage
        self.started_at=now();self.tick=time.monotonic();self.active_start=self.started_at
        self.active_tick=self.tick;self.segments=[];self.actions=0;self.paused=False;self.stopped=False

    def pause(self):
        import time
        from .trace import now
        if self.stopped or self.paused:raise ValueError('timer is not actively running')
        end=now();seconds=min(time.monotonic()-self.active_tick,(instant(end)-instant(self.active_start)).total_seconds())
        self.segments.append({'started_at':self.active_start,'ended_at':end,'active_human_seconds':max(0,seconds),
                              'participant_id':self.participant_id,'effort_stage':self.effort_stage})
        self.paused=True

    def resume(self):
        import time
        from .trace import now
        if self.stopped or not self.paused:raise ValueError('timer is not paused')
        self.active_start=now();self.active_tick=time.monotonic();self.paused=False

    def action(self):
        if self.stopped or self.paused:raise ValueError('manual actions require active work')
        self.actions+=1

    def stop(self):
        from .trace import now
        if self.stopped:raise ValueError('timer already stopped')
        if not self.paused:self.pause()
        self.stopped=True;end=now()
        stage={'data_preparation':'ingestion','investigation':'investigation','verification':'verification',
               'corrections':'corrections','setup':'setup','coordination':'coordination','ongoing_configuration':'ongoing_configuration'}[self.effort_stage]
        return self.sink.emit(actor='human',stage=stage,action='observed_active_work',started_at=self.started_at,ended_at=end,
                              participant_id=self.participant_id,effort_stage=self.effort_stage,
                              active_human_seconds=sum(s['active_human_seconds'] for s in self.segments),
                              active_intervals=self.segments,manual_actions=self.actions,time_source='observed',
                              waiting_or_pause_seconds=(instant(end)-instant(self.started_at)).total_seconds()-sum(s['active_human_seconds'] for s in self.segments))


def import_trace(trace_path,run_ids,*,observed_zero=(),complete=False):
    from pathlib import Path
    import json
    events=[json.loads(line) for line in Path(trace_path).read_text().splitlines() if line.strip()]
    ledger=template(run_ids)
    for row in ledger['runs']:
        selected=[e for e in events if e.get('run_id')==row['run_id'] and e.get('actor')=='human']
        row.update(effort_complete=complete,evidence_ref=str(trace_path))
        row['intervals']=[i for e in selected for i in e.get('active_intervals',[])]
        for phase in PHASES:
            recorded=[e for e in selected if e.get('effort_stage')==phase]
            if recorded or phase in observed_zero:
                row['phases'][phase]={'active_seconds':sum(e['active_human_seconds'] for e in recorded),
                                      'manual_actions':sum(e['manual_actions'] for e in recorded)}
    return ledger


def main():
    import argparse,json
    from pathlib import Path
    from .trace import TraceSink
    parser=argparse.ArgumentParser(description='Observe active human work; no inference from model runtime')
    parser.add_argument('action',choices=['time','import-trace'])
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--case-id')
    parser.add_argument('--participant')
    parser.add_argument('--stage',choices=PHASES)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--observed-zero',choices=PHASES,nargs='*',default=[])
    parser.add_argument('--complete',action='store_true',help='Attest all people, attempts and stages are accounted for')
    args=parser.parse_args()
    if args.action=='import-trace':
        print(json.dumps(import_trace(args.trace,[args.run_id],observed_zero=args.observed_zero,complete=args.complete),indent=2));return
    if not args.case_id or not args.participant or not args.stage:parser.error('time requires --case-id, --participant and --stage')
    sink=TraceSink(args.trace,args.case_id,args.run_id)
    timer=ActiveWorkTimer(sink,participant_id=args.participant,effort_stage=args.stage)
    print('Timer started. Enter a for a manual action, p to pause/resume, or s to stop.')
    try:
        while True:
            command=input().strip().lower()
            if command=='a':timer.action()
            elif command=='p':timer.resume() if timer.paused else timer.pause()
            elif command=='s':break
    finally:
        print(json.dumps(timer.stop(),indent=2))


if __name__=='__main__':main()
