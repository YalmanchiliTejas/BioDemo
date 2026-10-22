"""Preserve validated assets before evaluation migrations; verify without rewriting."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .case_protocol import ROOT, digest, save


def freeze_assets(name='pre-evaluation-v2'):
    if Path(name).name!=name:raise ValueError('snapshot name must be a single directory name')
    target=ROOT/'benchmarks/snapshots'/name
    manifest_path=target/'manifest.json'
    if manifest_path.exists():return verify_snapshot(target)
    selected=('README.md','README_benchmarks.md','benchmarks/README.md','benchmarks/common','benchmarks/baselines',
              'benchmarks/configs','benchmarks/cho/raw','benchmarks/cho/reference','benchmarks/cho/reports',
              'benchmarks/cho/source_manifest.json','benchmarks/cho/data_inventory.json','benchmarks/fresenius',
              'data/v1.1','results/cho','results/fresenius','results/benchmark_comparison.md','benchmark/case_comparison')
    files=sorted({p for relative in selected for p in ([ROOT/relative] if (ROOT/relative).is_file() else (ROOT/relative).rglob('*')) if p.is_file() and '__pycache__' not in p.parts})
    rows=[]
    for source in files:
        relative=source.relative_to(ROOT);destination=target/'assets'/relative
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        rows.append({'path':str(relative),'sha256':digest(destination),'bytes':destination.stat().st_size})
        destination.chmod(0o444)
    save(manifest_path,{'version':name,'spec_sha256':digest(ROOT/'README_benchmarks.md'),'files':rows})
    manifest_path.chmod(0o444)
    return verify_snapshot(target)


def verify_snapshot(target):
    target=Path(target);manifest=json.loads((target/'manifest.json').read_text());errors=[]
    for row in manifest['files']:
        source=target/'assets'/row['path']
        if not source.is_file() or digest(source)!=row['sha256']:errors.append(row['path'])
    return {'snapshot':str(target),'pass':not errors,'files':len(manifest['files']),
            'manifest_sha256':digest(target/'manifest.json'),'mismatches':errors}
