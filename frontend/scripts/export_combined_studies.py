"""Project completed evidence into public charts without changing source results."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/'frontend/public/case-study-results/combined-physics'
def load(path):
 return json.loads((ROOT/path).read_text())
def export():
 TARGET.mkdir(parents=True,exist_ok=True)
 pen='docs/case_studies/interventions-pensim-20261029'
 upper='docs/case_studies/model-repair-continuous-20261028'
 cho='docs/case_studies/physics-improvements-20261028'
 physical='docs/case_studies/physical-oxygen-summary-20261029'
 d=load(pen+'/analysis.json'); assert d['status']=='complete' and d['all_selected_cases_evaluable']
 keys=['groups','original_recipe_reference','paired_intervals','paired_case_differences','outcomes_by_recoverability']
 data={'intervention':{k:d[k] for k in keys},'case_counts':d['realized_recoverability']['counts'],'upper_bound':load(upper+'/analysis.json')['primary'],'cho':[r for r in load(cho+'/analysis.json')['real_CHO']['summary'] if r['metric']=='absolute_error'],'sources':[]}
 for label,path in [('intervention',pen),('upper-bound',upper),('cho',cho),('physical',physical)]:
  for name in ['report.md','provenance.json']:
   source=ROOT/path/name
   if source.exists():
    destination=f'{label}-{name}';shutil.copy2(source,TARGET/destination)
    data['sources'].append({'file':destination,'source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
 for label,path in [('intervention',pen),('upper-bound',upper),('cho',cho)]:
  source=ROOT/path/'analysis.json'
  data['sources'].append({'file':'summary.json','source':str(source.relative_to(ROOT)),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
 (TARGET/'summary.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
 print(f'Exported {len(data["intervention"]["paired_case_differences"])} independent intervention scenarios')
if __name__=='__main__': export()
