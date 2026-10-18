"""Owned benchmark workspaces for testing updates with the existing SDK state."""
from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path

from .case_protocol import ROOT, save
from .trace import instant


@contextmanager
def trial_workspace(case, run_id, mode, prior_run=None):
    workspace=None
    if mode=='full_rlm':
        if prior_run:
            previous=json.loads(Path(prior_run).read_text())
            workspace=Path(previous.get('runtime_workspace','')).resolve()
            expected_root=(ROOT/'benchmarks/runtime').resolve()
            if (workspace.parent!=expected_root or not workspace.name.startswith('benchmark-case-') or
                previous.get('mode')!='full_rlm' or previous.get('status')!='completed' or
                not previous.get('audit',{}).get('pass') or not previous.get('isolation_audit',{}).get('pass')):
                raise ValueError('Prior run is not a completed isolated SDK trial in an owned workspace')
            old=previous['case']
            if case['condition']!='updated' or old['benchmark_id']!=case['benchmark_id'] or any(old[k]!=case[k] for k in ('tenant','access_scope')):
                raise ValueError('Update must retain dataset, tenant and access scope')
            if not old.get('as_of') or not case.get('as_of') or instant(old['as_of'])>=instant(case['as_of']):
                raise ValueError('Updated package must advance the evidence cutoff')
            marker=json.loads((workspace/'owner.json').read_text())
            if marker.get('last_run_id')!=previous['run_id']:
                raise ValueError('Prior run is stale relative to persisted trial state')
        else:
            workspace=ROOT/'benchmarks/runtime'/f'benchmark-case-{run_id}'
            workspace.mkdir(parents=True,exist_ok=False,mode=0o700)
            save(workspace/'owner.json',{'last_run_id':None})
        lock=(workspace/'evaluation.lock').open('a+')
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            yield workspace
            save(workspace/'owner.json',{'last_run_id':run_id,'case_sha256':case['task_spec_sha256'],'as_of':case.get('as_of')})
        finally:
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
    else:
        if prior_run:raise ValueError('Persistent SDK update trials require full_rlm mode')
        yield None
