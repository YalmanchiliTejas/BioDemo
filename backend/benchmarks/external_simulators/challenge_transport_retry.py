"""One paired infrastructure-recovery pass; preserve original intent-to-test data."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
import argparse,json,shutil
from .experiment import checked,dump,sha
from .run_agents import safe_attempt,isolation
from src.lifesci.envfile import load_env_file


def execute(dataset,original,output,workers=4):
    dataset=dataset.resolve();original=original.resolve();output=output.resolve()
    if output.exists():raise ValueError('Fresh recovery directory required')
    first=json.loads((original/'results.json').read_text())
    if first['status']!='complete':raise ValueError('Reconcile original batch first')
    # Exact transport error and no accepted decision; never choose by A/B score.
    selected=sorted({(r['case_id'],r['repeat']) for r in first['records'] if r.get('error')=='Connection error.' and r['submission'] is None})
    output.mkdir(parents=True);shutil.copytree(original/'common-inputs',output/'common-inputs')
    protocol=deepcopy(first['protocol']);protocol.update(planned_attempts=2*len(selected),workers=workers,
        recovery_selection='One fresh A/B pair for every original pair containing exact Connection error. with no accepted decision. Not score-based.',
        recovery_attempt_limit=1,original_run=str(original.resolve()),selected_pairs=[{'case_id':c,'repeat':r} for c,r in selected],
        inference_configuration='Same model/native reasoning/request ceilings/system/SDK/inputs; worker concurrency4 for recovery.',
        recovery_source_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*') if p.suffix in ('.py','.mjs')})
    dump(output/'protocol.json',protocol)
    source=output/'runner-source';source.mkdir()
    for p in Path(__file__).parent.glob('*'):
        if p.suffix in ('.py','.mjs'):shutil.copy2(p,source/p.name)
    load_env_file(Path(__file__).resolve().parents[2]/'.env.local')
    dump(output/'isolation.json',isolation(dataset,output/'isolation-probe'))
    catalogue={i['case_id']:i for i in checked(dataset,'public/catalogue.json')};records=[]
    def pair(key):
        case,repeat=key;item=dict(catalogue[case],repeat=repeat)
        order=('A','B') if (int(case[-1],16)+repeat)%2 else ('B','A')
        return [safe_attempt(dataset,output,item,arm,protocol) for arm in order]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures=[executor.submit(pair,key) for key in selected]
        for future in as_completed(futures):
            records.extend(future.result());dump(output/'results.json',{'status':'running','records':records,'planned_attempts':protocol['planned_attempts']})
            print(json.dumps({'recovery_attempts':len(records),'planned':protocol['planned_attempts']}),flush=True)
    result={'status':'complete','records':records,'planned_attempts':protocol['planned_attempts'],'completed':sum(r['score'] is not None for r in records),'protocol':protocol}
    dump(output/'results.json',result);return result


def make_view(original,recovery,view):
    if view.exists():raise ValueError('Fresh view directory required')
    first=json.loads((original/'results.json').read_text());second=json.loads((recovery/'results.json').read_text())
    if second['status']!='complete':raise ValueError('Recovery unfinished')
    replacements={(r['case_id'],r['repeat'],r['arm']):r for r in second['records']}
    for case,repeat in {(k[0],k[1]) for k in replacements}:
        if {k[2] for k in replacements if k[:2]==(case,repeat)}!={'A','B'}:
            raise ValueError('Recovery must replace a complete pair')
    view.mkdir(parents=True);(view/'common-inputs').symlink_to((original/'common-inputs').resolve(),target_is_directory=True)
    (view/'runner-source').symlink_to((original/'runner-source').resolve(),target_is_directory=True)
    records=[]
    for r in first['records']:
        key=(r['case_id'],r['repeat'],r['arm']);chosen=replacements.get(key,r)
        if chosen['common_input_sha256']!=r['common_input_sha256'] or chosen['model']!=r['model']:
            raise ValueError('Recovery changed common evidence or AI model')
        records.append(chosen)
        relative=Path('attempts')/r['case_id']/f"repeat-{r['repeat']:02d}"/r['arm']
        link=view/relative;link.parent.mkdir(parents=True,exist_ok=True)
        link.symlink_to(((recovery if key in replacements else original)/relative).resolve(),target_is_directory=True)
    result=deepcopy(first);result.update(records=records,attempted=len(records),completed=sum(r['score'] is not None for r in records),
        transport_recovery={'original_planned_attempts':len(first['records']),'original_completed':first['completed'],
            'new_recovery_attempts':len(second['records']),'recovery_completed':second['completed'],
            'pair_selection':second['protocol']['recovery_selection'],'original_records_preserved':True,
            'interpretation':'Secondary paired infrastructure-recovery view, not additional independent cases or a preregistered successful first-run result.'})
    for key in ('groups','pair_inputs_match','shared_tool_schemas_match'):
        result.pop(key,None)
    result['aggregate_policy']='Secondary statistics and input/schema checks are independently rebuilt by challenge_report; original batch aggregates are not reused.'
    dump(view/'results.json',result);dump(view/'protocol.json',result['protocol'])
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path);p.add_argument('--original',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--view',type=Path);a=p.parse_args()
    if a.view:make_view(a.original,a.output,a.view)
    else:execute(a.dataset,a.original,a.output,a.workers)
