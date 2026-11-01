"""Freeze and score actual-agent task answers, never deterministic substitutes.

Known-answer manufacturing fixtures are synthetic functional tests. They do not
establish independent factory generalization or expert-reviewed causal accuracy.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
import shutil
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.common.case_protocol import ROOT, VERSION, digest, load_case, save, stable_hash

MODEL = 'modal/zai-org/GLM-5.3'
FAMILIES = ('investigations', 'deviations', 'ingestion', 'scheduling')
ANSWER_CONTRACT = """
Return your task answer in an observed_facts entry containing a `task_answer`
object with exactly the task-specific keys requested above. Keep its statement
and evidence_ids source-linked and include its claim in the normal claim ledger.
The task_answer is a machine-readable deliverable, not an evaluator answer key.
Use the usual manufacturing_os tools and submit_report workflow. Do not invent
missing evidence or execute manufacturing actions. Review every scoped unit, but
avoid repeating searches or delegating work that is already resolved. End with a
submitted final_investigation, or an honest partial_investigation if incomplete.
"""


def table(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def optimum(jobs, maintenance):
    """Independent exhaustive reference for <=4 nonpreemptive, single-line jobs."""
    best = None
    for order in itertools.permutations(jobs):
        done = {}; schedule = []; clock = 0
        for job in order:
            if job['predecessor'] and job['predecessor'] not in done:
                break
            start = max(clock, job['ready_hour'])
            end = start + job['duration_hours']
            if start < maintenance[1] and end > maintenance[0]:
                start = maintenance[1]; end = start + job['duration_hours']
            if end > job['due_hour']:
                break
            schedule.append({'job_id': job['batch_id'], 'start_hour': start, 'end_hour': end})
            done[job['batch_id']] = end; clock = end
        else:
            if best is None or clock < best['makespan']:
                best = {'makespan': clock, 'assignments': schedule}
    return best


def fixture(directory, family, index, seed):
    rng = random.Random(seed)
    raw = directory / 'agent_input'; raw.mkdir(parents=True)
    ids = [f'{rng.randrange(10000, 99999)}-{letter}' for letter in 'ABCDEF']
    if family == 'investigations':
        limit = rng.choice([4, 6, 8])
        durations = [limit-1, limit, limit+1, limit+3, limit-2, limit+2]
        if index % 5 == 0: durations = [limit-1] * 6
        rows = [{'batch_id': ident, 'event_id': 'event-'+ident, 'Hold (h)': duration,
                 'available_at': '2026-01-01T00:00:00Z'} for ident, duration in zip(ids, durations)]
        table(raw / 'hold_log.csv', rows)
        table(raw / 'procedure.csv', [{'batch_id': 'procedure', 'Maximum hold (h)': limit,
            'instruction': 'A hold equal to the maximum is allowed. A hold exceeding it requires investigation. No cause has been established.'}])
        expected = [r['batch_id'] for r in rows if r['Hold (h)'] > limit]
        prompt = 'Investigate the hold records against the supplied procedure. Return only batches whose hold exceeds the maximum in task_answer={"affected_batch_ids":[batch IDs]}. Normal batches are negative controls: review them but do NOT include them in affected_batch_ids. If no batch exceeds the maximum, affected_batch_ids must be empty. Do not infer a verified root cause from hold duration.'
        gold = {'set_key': 'affected_batch_ids', 'expected': expected}
    elif family == 'deviations':
        low, high = rng.choice([(2, 8), (3, 7), (4, 9)])
        values = [low-1, low, (low+high)/2, high, high+1, high+3]
        if index % 5 == 0: values = [low, high, low+1, high-1, low, high]
        rows = [{'batch_id': ident, 'result_id': 'assay-'+ident, 'Result (mg/L)': value,
                 'available_at': '2026-01-01T00:00:00Z'} for ident, value in zip(ids, values)]
        table(raw / 'assays.csv', rows)
        table(raw / 'specifications.csv', [
            {'batch_id': 'procedure', 'revision': 'obsolete', 'effective_at': '2024-01-01T00:00:00Z', 'Lower (mg/L)': 0, 'Upper (mg/L)': high+5},
            {'batch_id': 'procedure', 'revision': 'current', 'effective_at': '2025-01-01T00:00:00Z', 'Lower (mg/L)': low, 'Upper (mg/L)': high}])
        expected = [r['result_id'] for r in rows if not low <= r['Result (mg/L)'] <= high]
        prompt = 'Assess the assay records using the specification effective at the time of testing. Both bounds are inclusive. Flag out-of-specification results for human deviation review, without releasing or rejecting batches. Return task_answer={"deviation_result_ids":[result IDs]}. The obsolete specification remains visible as a version-selection control.'
        gold = {'set_key': 'deviation_result_ids', 'expected': expected}
    elif family == 'ingestion':
        rows = []; values = {}; review = []
        for i, ident in enumerate(ids):
            unit = ('g/L', 'mg/L', 'ug/mL')[i % 3]
            value = round(rng.uniform(.2, 5), 2)
            raw_value = str(value).replace('.', ',') if (index+i) % 2 else str(value)
            if i == 4 and index % 3 != 0: raw_value = ''; review.append(ident)
            elif i == 5 and index % 3 == 1: unit = 'ppm'; review.append(ident)
            else: values[ident] = value * (1000 if unit == 'g/L' else 1)
            rows.append({'batch_id': ident, 'record_id': ident, 'Raw value': raw_value, 'Raw unit': unit,
                         'available_at': '2026-01-01T00:00:00Z'})
        if index % 3 == 2:
            rows.append({**rows[0], 'Raw value': str(float(str(rows[0]['Raw value']).replace(',', '.'))+1)})
            values.pop(ids[0]); review.append(ids[0])
        table(raw / 'delivery.csv', rows)
        prompt = 'Reconcile the delivery into mg/L. Decimal commas are decimal separators. Use 1 g/L=1000 mg/L and 1 ug/mL=1 mg/L. Missing values, unsupported ppm units, or conflicting duplicate record IDs require review and must not be accepted. Deduplicate identical records. Return task_answer={"measurements":[{"record_id":"...","value_mg_per_l":number}],"review_record_ids":[IDs requiring review]}. Preserve source evidence and do not invent measurements.'
        gold = {'values': values, 'review': review}
    else:
        jobs = [{'batch_id': ident, 'duration_hours': rng.randint(1, 3), 'ready_hour': rng.randint(0, 2),
                 'due_hour': 18, 'predecessor': ''} for ident in ids[:4]]
        jobs[-1]['predecessor'] = jobs[0]['batch_id']
        if index % 4 == 0: jobs[1]['due_hour'] = 0
        maintenance = [4, 6]
        table(raw / 'jobs.csv', jobs)
        table(raw / 'line_calendar.csv', [{'batch_id': 'line', 'unavailable_start_hour': maintenance[0],
                                           'unavailable_end_hour': maintenance[1], 'instruction': 'One job at a time; no preemption; proposals require approval.'}])
        best = optimum(jobs, maintenance)
        prompt = 'Propose a minimum-makespan schedule for all jobs on one manufacturing line. Jobs cannot overlap each other or the maintenance window. Respect material ready times, durations, predecessor completion and hard due times. Touching interval endpoints is allowed. Do not dispatch the schedule. Return task_answer={"feasible":boolean,"assignments":[{"job_id":"...","start_hour":number,"end_hour":number}]}. If all jobs cannot meet the constraints, return feasible=false and an empty assignments list. Use the source inputs and calculate feasibility explicitly.'
        gold = {'jobs': jobs, 'maintenance': maintenance, 'optimum': best}
    return prompt + ANSWER_CONTRACT, gold


def freeze(suite, *, count=15, calibration=False, native_tasks=False):
    suite = suite.resolve(); suite.mkdir(parents=True, exist_ok=False)
    template = json.loads((ROOT/'benchmarks/manifests/fresenius/FRE-02-raw/case.json').read_text())
    entries = []
    for family in FAMILIES:
        for index in range(count):
            identifier = f'{family}-{index+1:02d}'
            directory = suite/'cases'/identifier
            seed = (900000 if calibration else 20261113 if native_tasks else 20261031) + FAMILIES.index(family)*1000+index
            objective, gold = fixture(directory, family, index, seed)
            if native_tasks:objective=objective.removesuffix(ANSWER_CONTRACT)
            files = [{'path':str(p.relative_to(directory/'agent_input')), 'sha256':digest(p),
                      'bytes':p.stat().st_size, 'available_at':None} for p in sorted((directory/'agent_input').iterdir())]
            for name, source in [('quality-policy.json','investigation-v2.json'), ('triage-policy.json','triage-v2.json')]:
                shutil.copyfile(ROOT/'benchmarks/rubrics'/source, directory/name)
            save(directory/'reference.json', {'version':VERSION, 'field_checks':[],
                'label_status':'developer_authored_synthetic_operational_rules; not independent SME labels',
                'workflow':family, 'answer':gold})
            case = {**template, 'case_id':identifier, 'benchmark_id':'workflow_agents', 'objective':objective,
                'as_of':None, 'input_root':'agent_input', 'allowlist':files, 'package_sha256':stable_hash(files),
                'source_version':'controlled-manufacturing-fixtures-v1', 'preparation':'Complete synthetic workflow input, not a subset of a larger incident.',
                'budgets':{'wall_clock_seconds':120 if native_tasks else 300,'tool_calls':72},
                'task_response_mode':'task_answer' if native_tasks else 'investigation',
                'execution_policy':{'mode':'adaptive_v1','soft_tool_calls':48},
                'model_configuration':{'prime_model':MODEL}, 'generator_sha256':digest(Path(__file__)),
                'seed':seed, 'frozen_at':datetime.now(timezone.utc).isoformat(),
                'questions':{'answerable':['Declared operational task from complete supplied inputs'],
                             'unanswerable':['Verified root cause','Production release suitability']},
                'generalization_claim_eligible':False}
            for key in ('transform', 'transform_sha256'): case.pop(key,None)
            for key in ('reference','quality_policy','triage_policy'):
                case[key+'_sha256'] = digest(directory/case[key])
            case['task_spec_sha256'] = stable_hash({k:v for k,v in case.items() if k not in ('frozen_at','task_spec_sha256')})
            save(directory/'case.json',case); load_case(directory/'case.json')
            entries.append({'id':identifier,'family':family,'manifest':str((directory/'case.json').relative_to(suite)),
                            'task_spec_sha256':case['task_spec_sha256']})
    random.Random(20261031).shuffle(entries)
    protocol = {'version':'actual-agent-workflow-v1','calibration':calibration, 'model':MODEL,
        'cases':entries,'response_mode':'native_task_answer' if native_tasks else 'investigation_report',
        'runtime':'Existing run_case/full_rlm, Prime SDK and manufacturing_os tools. Native task-response instrumentation; QA submission separate.' if native_tasks else 'Existing run_case/full_rlm, Prime SDK, manufacturing_os tools and submit_report validation.',
        'output_contract':'Agent final JSON with task_answer and source evidence_ids.' if native_tasks else 'task_answer inside submitted observed_facts; missing answers fail task exact accuracy.',
        'limitations':['Controlled synthetic operational tasks, not independently adjudicated real factory incidents.',
                       'No verified causal accuracy, human-effort savings or production scheduling qualification.',
                       'No deterministic pipeline output substitutes for an agent answer.'],
        'runner_sha256':digest(Path(__file__))}
    protocol['sha256']=stable_hash(protocol)
    save(suite/'protocol.json',protocol)
    return protocol


def sets(predicted, expected):
    p, e = set(predicted), set(expected); tp=len(p&e); fp=len(p-e); fn=len(e-p)
    return {'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,
            'recall':tp/(tp+fn) if tp+fn else None,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def answer_from(output):
    answers = [f['task_answer'] for f in (output or {}).get('analysis',{}).get('observed_facts',[])
               if isinstance(f,dict) and isinstance(f.get('task_answer'),dict)]
    return answers[0] if len(answers)==1 else None


def score_answer(family, answer, gold):
    valid = isinstance(answer,dict)
    if family in ('investigations','deviations'):
        key=gold['set_key']; values=(answer or {}).get(key)
        valid=valid and isinstance(values,list) and all(isinstance(v,str) for v in values)
        counts=sets(values if valid else [],gold['expected'])
        return {'answer_present':valid,'exact':valid and set(values)==set(gold['expected']), 'classification':counts}
    if family=='ingestion':
        items=(answer or {}).get('measurements'); review=(answer or {}).get('review_record_ids')
        valid=valid and isinstance(items,list) and isinstance(review,list) and all(isinstance(v,str) for v in review)
        predictions={}; malformed=False
        for row in items if isinstance(items,list) else []:
            if not isinstance(row,dict) or not isinstance(row.get('record_id'),str) or type(row.get('value_mg_per_l')) not in (int,float):
                malformed=True;continue
            ident=row['record_id']; value=row['value_mg_per_l']
            if ident in predictions or not math.isfinite(value): malformed=True
            predictions[ident]=value
        correct={k for k,v in predictions.items() if k in gold['values'] and math.isclose(v,gold['values'][k],rel_tol=1e-6,abs_tol=1e-8)}
        tp=len(correct);fp=len(predictions)-tp;fn=len(gold['values'])-tp
        counts={'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
                'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
        review_score=sets(review if valid else [],gold['review'])
        exact=valid and not malformed and fp==0 and fn==0 and set(review)==set(gold['review'])
        return {'answer_present':valid and not malformed,'exact':exact,'classification':counts,'review_classification':review_score}
    feasible=(answer or {}).get('feasible'); assignments=(answer or {}).get('assignments')
    valid=valid and type(feasible) is bool and isinstance(assignments,list)
    if not valid:return {'answer_present':False,'exact':False,'feasible_plan':False,'violations':['missing_or_malformed_answer']}
    if gold['optimum'] is None:
        return {'answer_present':True,'exact':feasible is False and assignments==[], 'correct_infeasibility':feasible is False and assignments==[]}
    violations=[]; keyed={}; jobs={j['batch_id']:j for j in gold['jobs']}
    for item in assignments:
        if not isinstance(item,dict) or item.get('job_id') not in jobs or item.get('job_id') in keyed:
            violations.append('unknown_or_duplicate_job');continue
        if any(type(item.get(k)) not in (int,float) or not math.isfinite(item[k]) for k in ('start_hour','end_hour')):
            violations.append('invalid_clock');continue
        keyed[item['job_id']]=item
    if set(keyed)!=set(jobs):violations.append('missing_jobs')
    for ident,item in keyed.items():
        job=jobs[ident];start=item['start_hour'];end=item['end_hour']
        if start<job['ready_hour'] or end>job['due_hour'] or not math.isclose(end-start,job['duration_hours'],abs_tol=1e-8): violations.append('job_constraint')
        if start<gold['maintenance'][1] and end>gold['maintenance'][0]:violations.append('maintenance_overlap')
        if job['predecessor'] and (job['predecessor'] not in keyed or start<keyed[job['predecessor']]['end_hour']):violations.append('precedence')
    for a,b in itertools.combinations(keyed.values(),2):
        if a['start_hour']<b['end_hour'] and b['start_hour']<a['end_hour']:violations.append('resource_overlap')
    makespan=max((i['end_hour'] for i in keyed.values()),default=None)
    plan_ok=feasible and not violations
    optimal=plan_ok and math.isclose(makespan,gold['optimum']['makespan'],abs_tol=1e-8)
    return {'answer_present':True,'exact':optimal,'feasible_plan':plan_ok,'violations':violations,
            'makespan':makespan,'reference_makespan':gold['optimum']['makespan']}


def run(suite, limit=None, concurrency=2):
    from benchmarks.common.case_runner import run_case
    from benchmarks.common.pilot_benchmark import provider_environment
    protocol=json.loads((suite/'protocol.json').read_text())
    if protocol['sha256']!=stable_hash({k:v for k,v in protocol.items() if k!='sha256'}):raise ValueError('Protocol changed')
    if protocol['runner_sha256']!=digest(Path(__file__)):raise ValueError('Runner changed; freeze a new suite')
    ledger=suite/'attempts.jsonl'; attempted=set()
    if ledger.exists():attempted={r['case_id'] for r in map(json.loads,ledger.read_text().splitlines())}
    selected=[c for c in protocol['cases'] if c['id'] not in attempted]
    if limit:selected=selected[:limit]
    write_lock=threading.Lock()
    def execute(case):
        marker=suite/'started'/f'{case["id"]}.json'
        if marker.exists():raise ValueError('Interrupted attempt requires explicit adjudication; never silently rerun')
        save(marker,{'case_id':case['id'],'started_at':datetime.now(timezone.utc).isoformat()})
        started=time.monotonic(); manifest=suite/case['manifest']
        row={'case_id':case['id'],'family':case['family'],'model':MODEL,'mode':'full_rlm'}
        output=None
        try:
            path=run_case(manifest,'full_rlm',output_root=suite/'runs',operator_id='actual-agent-functional-evaluation')
            receipt=json.loads(path.read_text());output=receipt.get('output')
            native=bool(output and output.get('analysis',{}).get('response_mode')=='native_task_answer')
            row.update(status=receipt['status'],run_path=str(path.relative_to(suite)),
                task_answer_submitted=native,final_report_submitted=bool(output) and not native,
                isolation_pass=receipt.get('isolation_audit',{}).get('pass'),
                source_audit_pass=receipt.get('audit',{}).get('pass'),usage=receipt.get('usage',{}))
        except Exception as exc:
            row.update(status='runner_error',error_type=type(exc).__name__,final_report_submitted=False)
        row['elapsed_seconds']=time.monotonic()-started
        gold=json.loads((manifest.parent/'reference.json').read_text())['answer']
        answer=answer_from(output) if row.get('isolation_pass') and row.get('source_audit_pass') else None
        row['answer']=answer
        row['scores']=score_answer(case['family'],answer,gold)
        row['scores']['exact']=bool(row['scores']['exact'] and row.get('isolation_pass') and row.get('source_audit_pass'))
        with write_lock:
            with ledger.open('a') as stream:stream.write(json.dumps(row,sort_keys=True)+'\n')
            print(json.dumps({k:row[k] for k in ('case_id','status','scores','elapsed_seconds')}),flush=True)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in as_completed([pool.submit(execute,case) for case in selected]):future.result()
    return report(suite)


def report(suite):
    protocol=json.loads((suite/'protocol.json').read_text());ledger=suite/'attempts.jsonl'
    rows=list(map(json.loads,ledger.read_text().splitlines())) if ledger.exists() else []
    summary={'version':protocol['version'],'model':MODEL,'calibration':protocol['calibration'],
             'response_mode':protocol.get('response_mode','investigation_report'),
             'planned':len(protocol['cases']),'attempted':len(rows),'families':{},'limitations':protocol['limitations']}
    for family in FAMILIES:
        selected=[r for r in rows if r['family']==family];n=len(selected)
        totals={k:sum(r['scores'].get('classification',{}).get(k,0) for r in selected) for k in ('tp','fp','fn')}
        tp,fp,fn=(totals[k] for k in ('tp','fp','fn'))
        latency=sorted(r['elapsed_seconds'] for r in selected if r.get('final_report_submitted'))
        answer_latency=sorted(r['elapsed_seconds'] for r in selected if r['scores']['answer_present'])
        summary['families'][family]={'attempted':n,'planned':sum(c['family']==family for c in protocol['cases']),
            'task_exact_correct':sum(r['scores']['exact'] for r in selected),
            'task_exact_accuracy':sum(r['scores']['exact'] for r in selected)/n if n else None,
            'answer_present':sum(r['scores']['answer_present'] for r in selected),
            'final_reports_submitted':sum(r.get('final_report_submitted',False) for r in selected),
            'classification':{**totals,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
                              'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None} if family!='scheduling' else None,
            'submitted_report_latency_seconds':{f'p{p}':latency[math.ceil(p/100*len(latency))-1] if latency else None for p in (50,90,99)},
            'latency_sample_count':len(latency)}
        summary['families'][family]['submitted_answer_latency_seconds']={f'p{p}':answer_latency[math.ceil(p/100*len(answer_latency))-1] if answer_latency else None for p in (50,90,99)}
        summary['families'][family]['answer_latency_sample_count']=len(answer_latency)
    save(suite/'summary.json',summary)
    print(json.dumps({'summary':str(suite/'summary.json'),'attempted':len(rows),'planned':len(protocol['cases'])}),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['freeze','run','report'])
    parser.add_argument('--suite',type=Path,required=True);parser.add_argument('--count',type=int,default=15)
    parser.add_argument('--calibration',action='store_true');parser.add_argument('--limit',type=int)
    parser.add_argument('--native-tasks',action='store_true')
    parser.add_argument('--methods',nargs='+',choices=['full_rlm'],default=['full_rlm']);parser.add_argument('--operator-id')
    parser.add_argument('--provider-env',type=Path);args=parser.parse_args();suite=args.suite.resolve()
    if args.action=='freeze':
        freeze(suite,count=args.count,calibration=args.calibration,native_tasks=args.native_tasks);print(json.dumps({'frozen':str(suite),'cases':args.count*4}))
    elif args.action=='report':report(suite)
    else:
        from benchmarks.common.pilot_benchmark import provider_environment
        with provider_environment(args.provider_env):run(suite,args.limit)


if __name__=='__main__':main()
