"""Replay source-only searches; never loads scorer references or calls a model.

PYTHONPATH=. .venv/bin/python scripts/profile_retrieval.py --store PATH --scope evaluation --output PATH
Use --legacy to measure the previous unrestricted substring SQL.
"""
import argparse
import hashlib
import json
import re
import statistics
import time
from pathlib import Path
from src.manufacturing_data import ManufacturingStore, ManufacturingTools

QUERIES=['deviation','protocol setpoint intended design condition','contamination',
         'comment note remark observation log','inoculum seed vial passage',
         'aggregation assay method sample holding time analysis order',
         'bioreactor vessel position R01 R02 duplicate reactor parallel cultivations experiment design']

def legacy_sql(query):
    terms=[t.lower() for t in re.findall(r'\w+',query) if len(t)>1]
    hay="lower(name || ' ' || coalesce(value_text,'') || ' ' || coalesce(entity_id,''))"
    score='+'.join(f'CAST(contains({hay},?) AS INTEGER)' for _ in terms)
    return ('SELECT * EXCLUDE(score) FROM (SELECT *,('+score+') AS score FROM observations) '
            'WHERE score>0 ORDER BY score DESC,id LIMIT ? OFFSET ?'),[*terms,10,0]

def main():
    p=argparse.ArgumentParser();p.add_argument('--store',required=True);p.add_argument('--scope',default='default')
    p.add_argument('--as-of');p.add_argument('--output',required=True);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--legacy',action='store_true');p.add_argument('--explain',action='store_true');a=p.parse_args()
    store=ManufacturingStore(a.store);tools=ManufacturingTools(store,scopes=(a.scope,),as_of=a.as_of)
    records=[]
    for trial in range(a.repeats):
        for query in QUERIES:
            start=time.perf_counter()
            if a.legacy:
                sql,args=legacy_sql(query);rows=store.select(sql,args,as_of=a.as_of,scopes=(a.scope,))
                ids=[r['id'] for r in rows];diag={}
            else:
                result=tools.search_evidence(query=query,limit=10);rows=result['records'];ids=result['evidence_ids'];diag=result['diagnostics']
            elapsed=time.perf_counter()-start
            records.append({'trial':trial,'query':query,'seconds':elapsed,'count':len(rows),'evidence_ids':ids,
                            'field_names':sorted({r['name'] for r in rows}),'diagnostics':diag})
            print(trial,query,round(elapsed,4),len(rows),flush=True)
    out={'variant':'legacy' if a.legacy else 'routed','repeats':a.repeats,'records':records,
         'trial_seconds':[sum(r['seconds'] for r in records if r['trial']==t) for t in range(a.repeats)],
         'model_calls':0,'hidden_references_used':False,
         'quality':{'critical_recall':None,'precision':None,'reason':'No independent relevance annotations for these seven queries'}}
    times=sorted(r['seconds'] for r in records)
    out['p50_seconds']=statistics.median(times);out['p95_seconds']=times[min(len(times)-1,int(.95*len(times)))]
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    if a.explain:
        sql,args=legacy_sql('contamination')
        with store.query_connection(as_of=a.as_of,scopes=(a.scope,)) as db:
            plan=db.execute('EXPLAIN ANALYZE '+sql,args).fetchall()
        planpath=target.with_suffix('.legacy-plan.txt');planpath.write_text('\n'.join(str(r[1]) for r in plan))
        out['legacy_plan']=str(planpath)
        # Same engine, pruned source/column view; no arbitrary agent SQL extension.
        sources,schema=tools._retrieval.schema((a.scope,),a.as_of) if tools._retrieval else ([],[])
        if schema:
            col=next(c for c in schema if c.get('numeric'))
            with store.query_connection(as_of=a.as_of,scopes=(a.scope,),source_ids=[col['source_id']],names=[col['name']]) as db:
                plan=db.execute('EXPLAIN ANALYZE SELECT id,value_number FROM observations ORDER BY source_row LIMIT 10').fetchall()
            planpath=target.with_suffix('.filtered-plan.txt');planpath.write_text('\n'.join(str(r[1]) for r in plan))
            out['filtered_plan']=str(planpath)
    target.write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
