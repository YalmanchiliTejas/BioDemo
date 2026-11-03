"""Export the archived freeze-drying comparison; no simulation or inference."""
from pathlib import Path
import csv
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'docs/case_studies/lyo-study-20261102'
PUBLIC = ROOT/'frontend/public/case-study-results/freeze-drying'


def read(name):
    return json.loads((SOURCE/name).read_text())


def metrics(groups):
    keys = ['planned', 'completed', 'feasible_selections', 'unsafe_selections',
            'characterize', 'completion_predictions', 'completion_eligible']
    result = {key: sum(g[key] for g in groups) for key in keys}
    result['failed'] = result['planned']-result['completed']
    assert sum(result[k] for k in ['feasible_selections','unsafe_selections','characterize','failed']) == result['planned']
    return result


def cohort(prefix):
    summary = read(prefix+'summary.json')
    rows = list(csv.DictReader((SOURCE/(prefix+'per-case.csv')).open()))
    groups, errors = {}, {}
    for arm in ['A','C']:
        selected = [g for g in summary['groups'] if g['source']=='agent' and g['arm']==arm]
        groups[arm] = {task: metrics([g for g in selected if g['task']==task]) for task in ['forecast','pretransfer']}
        groups[arm]['all'] = metrics(selected)
    for task in ['forecast','pretransfer']:
        selected = {arm: {r['case_id']:r for r in rows if r['source']=='agent' and r['arm']==arm and r['task']==task} for arm in ['A','C']}
        points = []
        for case in sorted(selected['A']):
            pair = [selected[arm][case] for arm in ['A','C']]
            if all(r['completion_absolute_error_h'] for r in pair):
                points.append({'case_id':case, **{arm:float(selected[arm][case]['completion_absolute_error_h']) for arm in ['A','C']}})
        errors[task] = {'points': points, 'common_predictions':len(points),
                        'mean':{arm:sum(p[arm] for p in points)/len(points) if points else None for arm in ['A','C']}}
    protocol = summary['agent_protocol']
    return {'cases':len(protocol['case_ids']), 'model_calls':protocol['model_calls'],
            'wall_seconds':protocol['wall_seconds'], 'tool_calls':protocol['tool_calls'],
            'groups':groups, 'errors':errors,
            'model_only_C':{g['task']:metrics([g]) for g in summary['groups'] if g['source']=='model' and g['arm']=='C'}}


def export():
    supplement = read('sensitivity-comparison.json')
    comparisons = [r for r in supplement['comparison'] if r['arm'] in ['A','C']]
    budget = {arm:{protocol:sum(r[protocol]['completed'] for r in comparisons if r['arm']==arm)
                   for protocol in ['primary','sensitivity']} for arm in ['A','C']}
    filenames = ['summary.json','per-case.csv','sensitivity/summary.json','sensitivity/per-case.csv',
                 'sensitivity-comparison.json','illustrative-trajectories.json','illustrative-case.json',
                 'report.md','sensitivity/report.md']
    data = {'date':'2026-11-02','model':'GLM-5.3', 'classification':'Exploratory synthetic study',
            'cohorts':{'primary':cohort(''),'sensitivity':cohort('sensitivity/')},
            'budget':budget,'example':read('illustrative-trajectories.json'),
            'source_hashes':{str((SOURCE/name).relative_to(ROOT)):hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in filenames}}
    PUBLIC.mkdir(parents=True,exist_ok=True)
    encoded = json.dumps(data,indent=2)+'\n'
    (ROOT/'frontend/data/lyo-study.json').write_text(encoded)
    (PUBLIC/'comparison.json').write_text(encoded)
    downloads = {'report.md':'primary-report.md','per-case.csv':'primary-per-case.csv',
                 'case-study-brief.pdf':'primary-brief.pdf','sensitivity/report.md':'sensitivity-report.md',
                 'sensitivity/per-case.csv':'sensitivity-per-case.csv','sensitivity/case-study-brief.pdf':'sensitivity-brief.pdf',
                 'sensitivity-comparison.md':'budget-comparison.md','illustrative-trajectories.json':'illustrative-trajectories.json',
                 'illustrative-case.json':'illustrative-case.json'}
    for src,dst in downloads.items(): shutil.copyfile(SOURCE/src,PUBLIC/dst)
    # Flattened reports need distinct image links so both retain their figures.
    for prefix,folder in [('primary',''),('sensitivity','sensitivity/')]:
        report_path=PUBLIC/(prefix+'-report.md')
        content=report_path.read_text()
        for task in ['forecast','pretransfer']:
            name=task+'-comparison.png'
            target=prefix+'-'+name
            shutil.copyfile(SOURCE/(folder+name),PUBLIC/target)
            content=content.replace(']('+name+')',']('+target+')')
        report_path.write_text(content)
    for src,dst in [('backend/src/lifesci/lyophilization/heterogeneous.py','model.py'),
                    ('backend/benchmarks/lyo_study/study.py','study.py')]:
        shutil.copyfile(ROOT/src,PUBLIC/dst)
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PUBLIC.iterdir()) if p.is_file() and p.name!='manifest.json'}
    (PUBLIC/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'cohorts':{key:value['groups'] for key,value in data['cohorts'].items()},'public_files':len(manifest)},indent=2))


if __name__=='__main__':
    export()
