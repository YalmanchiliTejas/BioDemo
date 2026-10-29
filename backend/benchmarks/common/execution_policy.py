"""New frozen runtime variants; source packages and evaluator labels stay identical."""
import json
import shutil
from pathlib import Path
from .case_protocol import load_case, stable_hash, save


def freeze_execution_variant(manifest, destination, *, soft=48, hard=72, wall_clock_seconds=None, mode='adaptive_v1'):
    manifest=Path(manifest).resolve();destination=Path(destination).resolve()
    if type(soft) is not int or type(hard) is not int or not 1<=soft<=hard:
        raise ValueError('Expected positive soft <= hard budgets')
    original=load_case(manifest)
    if mode not in {'fixed_v1','adaptive_v1'} or (mode=='fixed_v1' and soft!=hard):
        raise ValueError('Invalid execution policy or fixed allowance')
    seconds=original['budgets']['wall_clock_seconds'] if wall_clock_seconds is None else wall_clock_seconds
    if type(seconds) is not int or seconds<1:raise ValueError('wall_clock_seconds must be a positive integer')
    policy={'mode':mode,'soft_tool_calls':soft}
    if destination.exists():
        variant=load_case(destination/'case.json')
        if variant.get('parent_case_sha256')!=original['task_spec_sha256'] or variant.get('execution_policy')!=policy or variant['budgets']!={**original['budgets'],'tool_calls':hard,'wall_clock_seconds':seconds}:
            raise ValueError('Existing variant differs; choose a new destination')
        return destination/'case.json'
    if manifest.parent in destination.parents:raise ValueError('Variant must be outside the original frozen directory')
    # Inputs are linked from the shared checksum cache rather than copied again.
    inputs=manifest.parent/original['input_root'] if original.get('input_root') else None
    shutil.copytree(manifest.parent,destination,ignore=lambda folder,names:names if inputs and Path(folder)==inputs else [])
    variant={**original,'parent_case_sha256':original['task_spec_sha256'],
             'execution_policy':policy,'budgets':{**original['budgets'],'tool_calls':hard,'wall_clock_seconds':seconds}}
    variant['task_spec_sha256']=stable_hash({k:v for k,v in variant.items() if k not in ('frozen_at','task_spec_sha256')})
    path=destination/'case.json';path.chmod(0o600);save(path,variant);path.chmod(0o444)
    load_case(path)
    # The execution input scope materializes verified bytes only when a run/audit starts.
    return path
