"""Recompute frozen keys from raw fixtures independently of their generator."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def read(path):
    with path.open(newline='') as stream:return list(csv.DictReader(stream))


def audit(suite):
    protocol=json.loads((suite/'protocol.json').read_text());results=[]
    for case in protocol['cases']:
        manifest=suite/case['manifest'];spec=json.loads(manifest.read_text());raw=manifest.parent/spec['input_root']
        gold=json.loads((manifest.parent/'reference.json').read_text())['answer'];family=case['family']
        for f in spec['allowlist']:assert hashlib.sha256((raw/f['path']).read_bytes()).hexdigest()==f['sha256']
        if family=='investigations':
            maximum=float(read(raw/'procedure.csv')[0]['Maximum hold (h)'])
            expected={r['batch_id'] for r in read(raw/'hold_log.csv') if float(r['Hold (h)'])>maximum}
            assert expected==set(gold['expected'])
        elif family=='deviations':
            current=[r for r in read(raw/'specifications.csv') if r['revision']=='current'];assert len(current)==1
            low,high=float(current[0]['Lower (mg/L)']),float(current[0]['Upper (mg/L)'])
            expected={r['result_id'] for r in read(raw/'assays.csv') if not low<=float(r['Result (mg/L)'])<=high}
            assert expected==set(gold['expected'])
        elif family=='ingestion':
            groups={}
            for row in read(raw/'delivery.csv'):groups.setdefault(row['record_id'],[]).append(row)
            accepted={};review=set()
            for ident,rows in groups.items():
                normalized=[]
                for row in rows:
                    try:
                        factor={'g/L':1000.,'mg/L':1.,'ug/mL':1.}[row['Raw unit']]
                        value=float(row['Raw value'].replace(',','.'))*factor
                        if not math.isfinite(value):raise ValueError()
                        normalized.append(value)
                    except (ValueError,KeyError):review.add(ident)
                if ident in review or len(set(normalized))!=1:review.add(ident)
                else:accepted[ident]=normalized[0]
            assert set(accepted)==set(gold['values']) and review==set(gold['review'])
            assert all(math.isclose(v,gold['values'][k],rel_tol=1e-9) for k,v in accepted.items())
        else:
            jobs=read(raw/'jobs.csv');calendar=read(raw/'line_calendar.csv')[0]
            lo,hi=int(calendar['unavailable_start_hour']),int(calendar['unavailable_end_hour'])
            # Bitmask dynamic programming, independent of the generator's permutations.
            ids={j['batch_id']:i for i,j in enumerate(jobs)};ends={0:0}
            for mask in range(1<<len(jobs)):
                if mask not in ends:continue
                for i,job in enumerate(jobs):
                    if mask&(1<<i):continue
                    predecessor=job['predecessor']
                    if predecessor and not mask&(1<<ids[predecessor]):continue
                    start=max(ends[mask],int(job['ready_hour']));finish=start+int(job['duration_hours'])
                    if start<hi and finish>lo:finish=hi+int(job['duration_hours'])
                    if finish>int(job['due_hour']):continue
                    target=mask|(1<<i);ends[target]=min(ends.get(target,math.inf),finish)
            optimum=ends.get((1<<len(jobs))-1)
            assert (gold['optimum'] is None)==(optimum is None)
            if optimum is not None:assert optimum==gold['optimum']['makespan']
        results.append({'case_id':case['id'],'passed':True})
    result={'cases_checked':len(results),'all_passed':all(r['passed'] for r in results),
        'method':'Source-derived operational checks; scheduling checked with independent bitmask DP.',
        'scope_note':'Deviation reference follows the explicitly source-labeled current revision. Historical effective-time reconstruction is not validated.',
        'protocol_sha256':protocol['sha256'],'cases':results}
    (suite/'reference-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',type=Path,required=True);audit(p.parse_args().suite.resolve())
