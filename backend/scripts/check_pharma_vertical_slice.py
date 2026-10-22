"""Real local-API check using an independent, explicitly automated fixture protocol.

Requires an already running application; never represents simulated review as
human effort. No model calls or hidden answer keys are used by this script.
"""
import csv,io,json,os,time,urllib.request,urllib.error
from pathlib import Path
from src.manufacturing_data.cmo.settings import load_local_settings
load_local_settings()
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--base-url',default='http://127.0.0.1:8000')
args=parser.parse_args()
output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
BASE=args.base_url.rstrip('/')
headers={'Content-Type':'application/json','X-Tenant-Id':'demo-cdmo','X-Actor-Id':'automated-fixture-protocol'}
if os.getenv('CMO_API_TOKEN'):headers['X-CMO-Token']=os.environ['CMO_API_TOKEN']
def call(path,data=None,raw=False):
 payload=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None
 request=urllib.request.Request(BASE+path,data=payload,headers=headers)
 with urllib.request.urlopen(request,timeout=60) as response:
  body=response.read()
  return body if raw else json.loads(body)
def wait(ident):
 for _ in range(180):
  job=call('/api/pharma/jobs/'+ident)
  if job['status'] not in {'queued','running'}:
   assert job['status']=='complete',job
   return job
  time.sleep(.5)
 raise RuntimeError('Worker did not finish within test bound')
started=time.monotonic()
project=call('/api/pharma/projects',{'name':'MVP automated smoke '+str(int(time.time()))})
case=call('/api/pharma/projects/'+project['id']+'/cases',{'title':'Synthetic fermentation factual review','problem':'Compare reviewed product trajectories. Request feed/volume context before interpreting yield; do not infer causation.'})
source=call('/api/pharma/sample',raw=True)
item=call('/api/pharma/cases/'+case['id']+'/files?filename=fermentation-development.csv',source)
wait(item['job_id'])
run=call('/api/cmo-ingestion/runs/'+item['job_id'])
expected={(r['batch_id'],r['elapsed_h'],key):float(value) for r in csv.DictReader(io.StringIO(source.decode())) for key,value in r.items() if key not in {'batch_id','elapsed_h'}}
assert len(run['measurements'])==len(expected)==12
for measurement in run['measurements']:
 key=(measurement['batch'],measurement['time'],measurement['source']['column'])
 assert measurement['value']==expected[key] and measurement['source']['row']>=2
 call('/api/cmo-ingestion/runs/'+run['id']+'/reviews',{'measurement_id':measurement['id'],'binding':measurement['review_binding'],'decision':'accept','actor':'automated-fixture-protocol','reason':'Independent fixture check against actual CSV source cells; not human study time'})
# An explicit study fixture, never labeled as a human-confirmed mapping.
for layout in run['layouts']:
 call('/api/cmo-ingestion/runs/'+run['id']+'/templates',{'fingerprint':layout['fingerprint'],'mapping':layout['mapping'],'actor':'automated-fixture-protocol','reason':'Automated labeled-fixture mapping protocol, not a human study','origin':'study_protocol'})
duplicate=call('/api/pharma/cases/'+case['id']+'/files?filename=renamed-same-content.csv',source)
assert duplicate['duplicate'] and duplicate['job_id']==item['job_id']
returning=call('/api/pharma/cases/'+case['id']+'/files?filename=fermentation-returning.csv',source.replace(b'DEV-A',b'DEV-C').replace(b'DEV-B',b'DEV-D'))
wait(returning['job_id']); reused=call('/api/cmo-ingestion/runs/'+returning['job_id'])
assert reused['summary']['model_calls']==0 and reused['summary']['auto_accepted']==12,reused['summary']
analysis_id=call('/api/pharma/cases/'+case['id']+'/analyze',{'starter':'yield_change','parameters':['product']})['job_id']
analysis=wait(analysis_id)
assert [f['calculation']['mean']['value'] for f in analysis['result']['findings']]==[1,.5,1,.5]
finding=analysis['result']['findings'][0]
call('/api/pharma/jobs/'+analysis_id+'/review',{'finding_id':finding['id'],'decision':'annotate','reason':'Automated fixture arithmetic/citation check; feed and volume missing; no causal conclusion','version':analysis['result']['version']})
call('/api/pharma/cases/'+case['id']+'/actions',{'title':'Obtain comparable feed and volume records','owner':'MSAT','rationale':'Required for yield interpretation; request is proposed only','evidence':[s['id'] for s in finding['sources']]})
markdown=call('/api/pharma/cases/'+case['id']+'/handoff',raw=True)
assert b'SHA-256' in markdown and b'feed' in markdown
csv_export=call('/api/cmo-ingestion/runs/'+returning['job_id']+'/export?format=csv',raw=True)
assert b'source_sha256' in csv_export
(output/'handoff.md').write_bytes(markdown);(output/'reviewed-data.csv').write_bytes(csv_export)
report={'protocol':'Automated independent synthetic-fixture verification, NOT human review effort or savings','case_id':case['id'],'project_id':project['id'],'analysis_id':analysis_id,'source_checked_values':12,'returning_auto_accepted':12,'returning_model_calls':0,'renamed_duplicate_reused':duplicate['duplicate'],'findings':len(analysis['result']['findings']),'seconds':time.monotonic()-started,'result':analysis,'ui_url':BASE.replace(':8000',':5180')+'/?tab=cases&case='+case['id']}
(output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='result'}),flush=True)
