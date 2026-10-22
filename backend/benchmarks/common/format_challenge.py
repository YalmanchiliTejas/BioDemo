"""Frozen filename challenges on copies; measurements and source bytes are preserved."""
from __future__ import annotations

import json
from pathlib import Path


def apply_renames(package, transformation):
    package=Path(package)
    for original,renamed in transformation['files'].items():
        target=package/renamed;target.parent.mkdir(parents=True,exist_ok=True)
        (package/original).rename(target)
    metadata=package/'package_manifest.json'
    if metadata.exists():
        manifest=json.loads(metadata.read_text())
        for row in manifest['files']:
            row['path']=transformation['files'].get(row['path'],row['path'])
        metadata.write_text(json.dumps(manifest,indent=2))


def structured_projection(package):
    """Diagnostic CSV-only view of the same rendered canonical observations."""
    package=Path(package)
    for path in package.rglob('*'):
        if path.is_file() and path.suffix != '.csv' and path.name != 'package_manifest.json':
            path.unlink()
    metadata=package/'package_manifest.json'
    if metadata.exists():
        manifest=json.loads(metadata.read_text())
        manifest['files']=[r for r in manifest['files'] if r['path'].endswith('.csv')]
        manifest['condition']='clean_structured_diagnostic'
        metadata.write_text(json.dumps(manifest,indent=2))


def transform_references(reference,transformation):
    paths=transformation['files']
    for check in reference.get('field_checks',[]):check['source']=paths.get(check['source'],check['source'])
    changed={}
    for key,value in reference.get('source_record_ids',{}).items():
        source,sheet,row=json.loads(key)
        changed[json.dumps([paths.get(source,source),sheet,row],separators=(',',':'))]=value
    if changed:reference['source_record_ids']=changed
    return reference
