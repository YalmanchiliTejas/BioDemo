"""Export compact, traceable public presentation data from the completed study."""
from pathlib import Path
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2]
def export():
 source=ROOT/'docs/case_studies/model-repair-continuous-20261028'
 target=ROOT/'frontend/public/case-study-results/physics-benchmark';target.mkdir(parents=True,exist_ok=True)
 data=json.loads((source/'analysis.json').read_text());diag=json.loads((source/'model-diagnostics.json').read_text())
 assert data['status']=='complete' and data['all_checks_pass']
 payload={k:data[k] for k in ('completed','planned_attempts','primary','targets','cases','strata','physics_calls','physics_tool_errors','all_three_criterion_met')}
 payload.update(version='physics-benchmark-presentation-v1',source_sha256=hashlib.sha256((source/'analysis.json').read_bytes()).hexdigest(),source_record='docs/case_studies/model-repair-continuous-20261028/analysis.json',checks=len(data['checks']),failures=len(data['failures']),model_diagnostics={k:v for k,v in diag.items() if k!='cases'})
 # Public presentation contains computed scores and outcomes, never private host paths.
 (target/'summary.json').write_text(json.dumps(payload,separators=(',',':'))+'\n')
 for name in ('report.md','case-results.csv','all-forecast-targets.csv','provenance.json'):
  shutil.copy2(source/name,target/name)
 print(json.dumps({'cases':len(payload['cases']),'completed':payload['completed'],'bytes':(target/'summary.json').stat().st_size}))
if __name__=='__main__':export()
