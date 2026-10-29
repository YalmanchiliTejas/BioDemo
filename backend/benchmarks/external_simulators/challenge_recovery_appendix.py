"""Make original and paired-recovery denominators visible in one new report."""
from pathlib import Path
import argparse,json
from .experiment import dump,sha


def append(report,initial,recovery_run=None):
    p=report/'report.md';text=p.read_text();new=json.loads((report/'analysis.json').read_text());old=json.loads((initial/'analysis.json').read_text())
    r=new['transport_recovery']
    if not r:raise ValueError('No recovery metadata')
    intro=f"""This report's main tables are a **secondary paired transport-recovery analysis**, not a successful first-run reliability result. The original batch completed **{old['completed']:,}/{old['planned_attempts']:,}** attempts. A single extra pass ran **{r['new_recovery_attempts']}** attempts for pairs affected by connection errors. Both arms were repeated; every selected retry pair is used regardless of whether its scores improve or worsen. No models or cases changed. Original results are shown below and preserved in full.\n\n"""
    marker='## What this run establishes\n\n';text=text.replace(marker,intro+marker)
    text=text.replace(f"Completed **{new['completed']:,}/{new['planned_attempts']:,}** planned agent attempts;",f"After recovery, **{new['completed']:,}/{new['planned_attempts']:,}** original case/arm/repetition slots have a scored submission;")
    text=text.replace('The new suite meets its exploratory all-three improvement criterion.','The recovered view meets its exploratory all-three effect criterion; this does not repair the original batch’s first-run completion failure or establish confirmatory success.')
    text=text.replace('**The new suite does not establish improvement in all three aspects under its stated criterion.**','**The recovered analysis does not establish improvement in all three aspects under the stated criterion.**')
    lines=['','## Original batch and recovery: both retained','',
        f"The original batch had {len(old['failures'])} failed/unknown submissions. These included 123 recorded connection errors, 23 timeouts and 2 lost runner results conservatively scored as failures. Only pairs containing an exact connection error and no accepted decision were eligible for the one recovery pass. Ordinary timeouts and poor operating decisions were not independently selected for retries. A timeout counterpart could be repeated only because the whole connection-affected pair was repeated.",
        '', 'The revised view always takes both arms from each selected retry pair. It does not take the better of an old and new score. Thus recovery adds inference attempts, not independent process cases. The original batch’s 87% first-run completion must not be replaced with the recovered view’s completion as a reliability claim.', '',
        '| Process | Aspect | Original A | Original B | Original benefit | Recovered A | Recovered B | Recovered benefit |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    names={'pensim':'PenSimPy','mab':'SMPL upstream'}
    for a in old['primary']:
        b=next(v for v in new['primary'] if (v['simulator'],v['task'])==(a['simulator'],a['task']))
        lines.append(f"| {names[a['simulator']]} | {a['task']} | {100*a['A']:.3f} | {100*a['B']:.3f} | {100*a['effect']:.3f} | {100*b['A']:.3f} | {100*b['B']:.3f} | {100*b['effect']:.3f} |")
    lines+=['','Forecast values are percentage source-normalized error and benefits are percentage relative error reduction. Decision values/benefits are 0–100 scores/score points, not production percentages. Original intervals, every failure and all targets remain in the [original-batch report](../'+initial.name+'/report.md). The recovered tables and JSON retain any remaining unsuccessful sessions.','','The first recovery setup failed a local path preflight before any AI sessions started; that setup directory is retained. The corrected setup performed the single scheduled recovery pass. The original runner’s BrokenPipe exception and incomplete aggregate are retained with the reconciled result. Historical studies were not deleted.']
    if recovery_run is not None:
        retry=json.loads((recovery_run/'results.json').read_text())
        retry_calls=sum(r.get('physical_model_calls') or 0 for r in retry['records'])
        lines+=['',f"Known physics queries across all actual attempts: {old['physics_calls']} original + {retry_calls} recovery = {old['physics_calls']+retry_calls}. The {new['physics_calls']} queries in the main verification section refer to the secondary comparison view, not all execution cost."]
        original=json.loads((Path(retry['protocol']['original_run'])/'results.json').read_text())
        selected={(r['case_id'],r['repeat']) for r in retry['records']}
        unknown=sum(r['status']=='runner_error' and (r['case_id'],r['repeat']) in selected for r in original['records'])
        lines+=['',f"{unknown} original lost-result session(s) were repeated only as the counterpart of a connection-affected pair. Their original decisions remain unknown and failed in the original report; the fresh sessions do not recover those lost decisions."]
    text+='\n'.join(lines)+'\n';p.write_text(text)
    provenance=json.loads((report/'provenance.json').read_text());provenance.update(report_sha256=sha(p),original_batch_analysis_sha256=sha(initial/'analysis.json'))
    dump(report/'provenance.json',provenance)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);p.add_argument('initial',type=Path);p.add_argument('--recovery-run',type=Path);a=p.parse_args();append(a.report,a.initial,a.recovery_run)
