import sys,pathlib,json,time,hashlib,argparse
sys.path.insert(0,str(pathlib.Path.cwd()))
from src.manufacturing_data import ManufacturingStore,ManufacturingTools
parser=argparse.ArgumentParser(description='Source-only CHO retrieval checks; no evaluator reference access')
parser.add_argument('--store',required=True);parser.add_argument('--scope',default='default');parser.add_argument('--as-of');parser.add_argument('--output',required=True);args=parser.parse_args()
s=ManufacturingStore(args.store);t=ManufacturingTools(s,scopes=(args.scope,),as_of=args.as_of)
t.search_evidence(query='deviation');sources,schema=t._retrieval.schema(t.scopes,t.as_of)
source=sources[0]['id']
with s.connect() as c:entity=c.execute("SELECT id FROM entities WHERE source_id=? AND kind='run' ORDER BY id LIMIT 1",(source,)).fetchone()[0]
results=[]
for metric in ['vcd','glc','do']:
 tick=time.perf_counter();r=t.search_evidence(query=metric,source_id=source,entity_id=entity,time_min=10,time_max=100,limit=20);elapsed=time.perf_counter()-tick
 names=sorted({row['name'] for row in r['records']});assert names
 sql='SELECT id FROM observations WHERE source_id=? AND entity_id=? AND time_value>=10 AND time_value<=100 AND name IN ('+','.join('?' for _ in names)+') ORDER BY source_id,entity_id,sheet,source_row,column_index,id LIMIT 20'
 tick=time.perf_counter();expected=s.select(sql,[source,entity,*names],as_of=t.as_of,scopes=t.scopes);reference_seconds=time.perf_counter()-tick
 assert [row['id'] for row in r['records']]==[row['id'] for row in expected]
 check=t.verify_evidence(observation_id=r['records'][0]['id']);assert check['value_matches'] and check['source_integrity']
 results.append({'query':metric,'seconds':elapsed,'unpruned_scoped_select_seconds':reference_seconds,'count':len(r['records']),'direct_sql_ids_identical':True,'source_check':check,'diagnostics':r['diagnostics']})
hashes=[]
for source in sources:
 actual=hashlib.sha256(pathlib.Path(source['original_path']).read_bytes()).hexdigest();assert actual==source['sha256'];hashes.append({'source_id':source['id'],'sha256_matches':True})
pathlib.Path(args.output).write_text(json.dumps({'checks':results,'original_hashes':hashes},indent=2,default=str))
print([(r['query'],r['seconds'],r['unpruned_scoped_select_seconds']) for r in results])
