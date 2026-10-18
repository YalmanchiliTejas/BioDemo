"""Fail-closed evaluation boundary checks, including byte-identical replay sources."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .case_protocol import ROOT, digest, load_case, stable_hash
from .leakage_audit import audit_package


def audit_case(manifest_path):
    path=Path(manifest_path).resolve(); failures=[]
    try:
        case=load_case(path)
    except (ValueError, OSError, KeyError) as exc:
        return {'pass':False,'failures':[str(exc)],'permission_audit':'not_run','historical_audit':'invalid_manifest'}
    package=(path.parent/case['input_root']).resolve()
    if path.parent not in package.parents:
        failures.append('input_root escapes frozen case')
    declared={r['path']:r for r in case['allowlist']}
    actual={str(p.relative_to(package)):p for p in package.rglob('*') if p.is_file()}
    if set(declared)!=set(actual): failures.append('undeclared or missing agent-input files')
    for relative, item in declared.items():
        source=(package/relative).resolve()
        if package not in source.parents or not source.is_file() or digest(source)!=item['sha256']:
            failures.append('source missing, escaped or checksum changed: '+relative)
    if stable_hash(case['allowlist'])!=case['package_sha256']:
        failures.append('package manifest checksum mismatch')
    if any(p.is_symlink() for p in package.rglob('*')):
        failures.append('symlink in input package')
    ok, errors=audit_package(package,as_of=case.get('as_of'))
    failures.extend(errors)
    historical='not_applicable'
    if case.get('as_of'):
        historical='failed_closed'
        if case['benchmark_id']!='fresenius' or case.get('generator_sha256')!=digest(ROOT/'benchmarks/fresenius/build_multimodal_package.py'):
            failures.append('historical availability is not independently reconstructable')
        else:
            # Re-render from the field-aware frozen store and compare every byte.
            # This covers scans, filenames, metadata and PDF content as well as tables.
            from benchmarks.fresenius.build_multimodal_package import build_package
            with tempfile.TemporaryDirectory(prefix='evaluation-replay-audit-') as temp:
                target=Path(temp)/'snapshot'
                build_package(target,as_of=case['as_of'],map_output=Path(temp)/'hidden-map.json')
                if case.get('transform'):
                    from .format_challenge import apply_renames
                    transformation=json.loads((path.parent/case['transform']).read_text())
                    if transformation.get('version') == 'structured-projection-v1':
                        from .format_challenge import structured_projection
                        structured_projection(target)
                    elif transformation.get('version') != 'filename-challenge-v1':
                        failures.append('Unknown historical transformation; fail closed.')
                    else:
                        apply_renames(target,transformation)
                expected={str(p.relative_to(target)):digest(p) for p in target.rglob('*') if p.is_file()}
                observed={name:digest(p) for name,p in actual.items()}
                if observed!=expected:
                    failures.append('historical bytes/metadata differ from the independently rebuilt time-valid snapshot')
                else:
                    historical='byte_verified_time_valid_snapshot'
    return {'pass':not failures,'failures':failures,'package_sha256':case['package_sha256'],
            'reference_sha256':case['reference_sha256'],'historical_audit':historical,
            'permission_audit':'requires_isolated_worker_probe_before_scoring',
            'unknown_availability_policy':'fail_closed', 'files_checked':len(actual)}
