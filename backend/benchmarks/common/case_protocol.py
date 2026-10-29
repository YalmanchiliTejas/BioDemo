"""Frozen case definitions over existing source packages; references stay evaluator-only."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'manufacturing-evaluation-v2'
GROUPS = {'manual': 'A. Manual engineer', 'conventional': 'B. Conventional pipeline',
          'retrieval_llm': 'C. Single-pass AI', 'full_rlm': 'D. Manufacturing OS', 'incumbent': 'E. Incumbent product'}
CONDITIONS = ('raw', 'clean', 'held_out', 'updated', 'historical')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + '\n')
    path.chmod(0o600)
    return path


def inventory(benchmark):
    base = ROOT / ('benchmarks/cho/raw/workbooks' if benchmark == 'cho' else 'benchmarks/fresenius/raw_package')
    files = [{'path': str(p.relative_to(base)), 'sha256': digest(p), 'bytes': p.stat().st_size}
             for p in sorted(base.rglob('*')) if p.is_file()]
    return {'benchmark_id': benchmark, 'source_root': str(base.relative_to(ROOT)), 'files': files,
            'package_sha256': stable_hash(files), 'spec_sha256': digest(ROOT / 'README_benchmarks.md')}


def prepare_case(benchmark, case_id, *, condition='raw', destination=None):
    from .artifact_store import mounted_assets
    existing = (Path(destination) if destination else ROOT / 'benchmarks/manifests' / benchmark / f'{case_id}-{condition}') / 'case.json'
    if benchmark != 'cho' or existing.exists():
        return _prepare_case(benchmark, case_id, condition=condition, destination=destination)
    with mounted_assets(ROOT / 'benchmarks/cho/raw', ROOT / 'benchmarks/cho/reference/aligned'):
        result = _prepare_case(benchmark, case_id, condition=condition, destination=destination)
        inventory = ROOT/'results/offload/inputs.json'
        if inventory.exists():
            from .input_store import evict
            evict([result],inventory)
        return result


def _prepare_case(benchmark, case_id, *, condition='raw', destination=None):
    """Create one frozen evaluator case. Never alter existing validated references/results."""
    if benchmark not in ('cho', 'fresenius') or condition not in CONDITIONS:
        raise ValueError('unknown benchmark or condition')
    if Path(case_id).name != case_id or not case_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in case_id):
        raise ValueError('invalid case_id')
    directory = Path(destination) if destination else ROOT / 'benchmarks/manifests' / benchmark / f'{case_id}-{condition}'
    manifest_path = directory / 'case.json'
    if manifest_path.exists():
        return manifest_path  # immutable case versions must use new destinations
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    package = directory / 'agent_input'
    package.mkdir()
    reference = {'version': VERSION, 'field_checks': [], 'label_status': 'not_applicable',
                 'critical_evidence_ids': None, 'scope_ids': None, 'negative_controls': None,
                 'triage_labels': None, 'causal_labels': None}
    if benchmark == 'fresenius':
        from benchmarks.fresenius.build_tasks import build_tasks
        tasks = {t['id']: t for t in build_tasks()}
        if case_id == 'FRE-06':
            task = dict(tasks['FRE-05'], id='FRE-06', objective='Investigate normal and unrelated abnormal records; distinguish local findings from supported cross-batch connections and propose human-reviewed routing.')
        elif case_id in tasks:
            task = dict(tasks[case_id])
        else:
            raise ValueError('unknown Fresenius case')
        if case_id == 'FRE-04':
            task['objective'] = 'Assess competing explanations for the available abnormalities. Cite supporting and contradictory evidence and propose discriminating checks without asserting an established root cause.'
        if case_id == 'FRE-05':
            task['as_of'] = tasks['FRE-03']['as_of']
            task['objective'] = 'Assess available manufacturing risk, propose project L1/L2/L3 routing, identify missing evidence and prepare human-reviewed coordination tasks.'
        from benchmarks.fresenius.build_multimodal_package import build_package
        from benchmarks.fresenius.temporal_replay import state_at
        generated = build_package(package, as_of=task['as_of'], map_output=directory/'source-map.json')
        rows = state_at(task['as_of'])
        by_id = {r['_evidence_id']: r for r in rows}
        source_map = json.loads((directory/'source-map.json').read_text())
        for pointer in source_map['mappings']:
            if not pointer['source_file'].endswith('.csv') or pointer.get('conversion') or pointer['row']>3:
                continue
            expected = by_id[pointer['canonical_record_id']].get(pointer['canonical_field'])
            if expected is None or isinstance(expected, (dict, list)):
                continue
            reference['field_checks'].append({'source': pointer['source_file'], 'row': pointer['row'], 'column': pointer['column'],
                                             'expected': expected, 'rtol': 1e-6, 'atol': 1e-8})
        critical = [r['_evidence_id'] for r in rows if r['_table']=='lab_results' and r.get('status') in ('action', 'out_of_specification')]
        source_record_ids={}
        from openpyxl.utils.cell import coordinate_to_tuple
        for pointer in source_map['mappings']:
            row=pointer.get('row')
            if pointer.get('cell'): row=coordinate_to_tuple(pointer['cell'])[0]
            if row:
                key=json.dumps([pointer['source_file'],pointer.get('sheet'),row],separators=(',',':'))
                source_record_ids[key]=pointer['canonical_record_id']
        reference.update(critical_evidence_ids=critical, available_record_ids=sorted(by_id), source_record_ids=source_record_ids,
                         label_status='synthetic_status_annotations; scope_and_triage_need_independent_review',
                         annotation_basis='Explicit action/OOS source statuses; includes unrelated abnormalities. Not an independently reviewed causal label set.')
        # Explicit normal source statuses support negative controls, never inferred from silence.
        reference['negative_controls'] = sorted({r['batch_id'] for r in rows if r['_table']=='lab_results' and r.get('status')=='normal'} -
                                                {r['batch_id'] for r in rows if r['_table']=='lab_results' and r.get('status') in ('action','out_of_specification')})
        source_version = generated['version']
    else:
        objectives = {
            'CHO-01': 'Identify experiments, reactors, variables, units and sampling patterns from the original workbooks without manual mappings.',
            'CHO-02': 'Reconstruct inline and offline observations with time alignment, original values and cell-level provenance; report unresolved mappings.',
            'CHO-03': 'Compare cultivation runs with reproducible numerical calculations, source citations and transparent assumptions.',
            'CHO-04': 'Investigate cultivation variability with supporting and contradictory evidence and competing hypotheses; do not assert proven causes.',
            'CHO-05': 'Assess source-format robustness and new evidence, reporting unresolved identities, units, duplicate handling and irrelevant records.'}
        if case_id not in objectives:
            raise ValueError('unknown CHO case')
        task = {'id': case_id, 'objective': objectives[case_id]}
        for path in sorted((ROOT/'benchmarks/cho/raw/workbooks').glob('*.xlsx')):
            shutil.copyfile(path, package/path.name)
        if not list(package.iterdir()):
            raise ValueError('CHO source workbooks absent')
        mapping_path = ROOT/'benchmarks/cho/reference/structural_map.json'
        aligned = ROOT/'benchmarks/cho/reference/aligned'
        mappings = json.loads(mapping_path.read_text())['mappings']
        first = {}
        for path in aligned.glob('*.csv'):
            with path.open(newline='', encoding='utf-8-sig') as stream:
                reader=csv.reader(stream); next(reader, None); first[path.name]=next(reader, [])
        for m in mappings:
            source = m.get('source'); values=first.get(m['aligned_csv'], [])
            index=m['aligned_column_index']-1
            if not source or m.get('candidate_count') != 1 or index>=len(values) or values[index]=='':
                continue
            reference['field_checks'].append({'source': m['workbook'], 'sheet': source['sheet'], 'row': 2,
                                             'column': m['aligned_column'], 'expected': values[index], 'rtol': 1e-6, 'atol': 1e-8,
                                             'reference': m['aligned_csv'], 'reference_column': m['aligned_column_index']})
        reference.update(label_status='publication_aligned_time_zero_reference_only; causal_labels_absent',
                         annotation_basis='Unique structural mappings and publisher-aligned inoculation values; not full-trajectory or biological causality scoring.')
        source_version='cho-v1'
    transformation = None
    if condition == 'clean' and benchmark == 'fresenius':
        from .format_challenge import structured_projection
        structured_projection(package)
        transformation = {'version': 'structured-projection-v1', 'files': {},
                          'novelty': 'CSV-only normalized diagnostic; not a raw-input product claim.'}
        existing = {str(p.relative_to(package)) for p in package.rglob('*') if p.is_file()}
        reference['source_record_ids'] = {key:value for key,value in reference.get('source_record_ids',{}).items() if json.loads(key)[0] in existing}
        save(directory/'transform.json', transformation)
    if condition == 'held_out':
        from .format_challenge import apply_renames, transform_references
        sources = [p for p in sorted(package.rglob('*')) if p.is_file() and p.name != 'package_manifest.json']
        transformation = {'version': 'filename-challenge-v1', 'seed': 42,
                          'files': {str(p.relative_to(package)): f'sources/input_{i:04d}{p.suffix}' for i,p in enumerate(sources)},
                          'novelty': 'New frozen filename layout; underlying source observations were previously seen. Not untouched biological or incident generalization.'}
        apply_renames(package, transformation)
        transform_references(reference, transformation)
        save(directory/'transform.json', transformation)
    files = [{'path': str(p.relative_to(package)), 'sha256': digest(p), 'bytes': p.stat().st_size,
              'available_at': task.get('as_of')} for p in sorted(package.rglob('*')) if p.is_file()]
    policy_path=ROOT/'benchmarks/rubrics/investigation-v2.json'; triage_path=ROOT/'benchmarks/rubrics/triage-v2.json'
    shutil.copyfile(policy_path, directory/'quality-policy.json');shutil.copyfile(triage_path,directory/'triage-policy.json')
    save(directory/'reference.json', reference)
    supported = condition in ('raw','held_out') or benchmark=='fresenius'
    manifest = {'version': VERSION, 'case_id': case_id, 'benchmark_id': benchmark, 'objective': task['objective'],
                'condition': condition, 'condition_status': 'ready' if supported else 'not_tested',
                'condition_reason': None if supported else 'Requires a separately frozen condition-specific package; existing raw files are not a held-out, clean or updated evaluation.',
                'as_of': task.get('as_of'), 'tenant': 'benchmark', 'access_scope': 'evaluation',
                'source_version': source_version, 'input_root': 'agent_input', 'allowlist': files,
                'package_sha256': stable_hash(files), 'reference': 'reference.json', 'reference_sha256': digest(directory/'reference.json'),
                'quality_policy': 'quality-policy.json', 'quality_policy_sha256': digest(directory/'quality-policy.json'),
                'triage_policy': 'triage-policy.json', 'triage_policy_sha256': digest(directory/'triage-policy.json'),
                'triage_rubric_status': json.loads(triage_path.read_text())['status'],
                'spec_sha256': digest(ROOT/'README_benchmarks.md'), 'frozen_at': __import__('benchmarks.common.trace',fromlist=['now']).now(),
                'budgets': {'wall_clock_seconds': 900, 'tool_calls': 48}, 'seed': 42,
                'required_deliverables': ['evidence_inventory', 'assessment', 'hypotheses', 'counterevidence', 'scope', 'triage', 'evidence_requests', 'follow_up_actions'],
                'questions': {'answerable': ['source measurements and availability', 'descriptive abnormalities'],
                              'partially_answerable': ['shared causes', 'affected scope'],
                              'unanswerable': ['verified internal root cause', 'counterfactual recall prevention']},
                'generalization_claim_eligible': False,
                'update_requires_prior_run': condition == 'updated',
                'format_challenge': transformation['novelty'] if transformation else None,
                'preparation': 'Existing renderer with field-aware historical filtering' if benchmark=='fresenius' else 'Original workbooks copied without evaluator mappings',
                'generator_sha256': digest(ROOT/'benchmarks/fresenius/build_multimodal_package.py') if benchmark=='fresenius' else None}
    if transformation:
        manifest.update(transform='transform.json', transform_sha256=digest(directory/'transform.json'))
    manifest['task_spec_sha256']=stable_hash({k:v for k,v in manifest.items() if k not in ('frozen_at','task_spec_sha256')})
    save(manifest_path, manifest)
    for p in directory.rglob('*'):
        if p.is_file(): p.chmod(0o444)
    return manifest_path


def load_case(path):
    path=Path(path).resolve(); value=json.loads(path.read_text())
    if value.get('version')!=VERSION or value.get('condition') not in CONDITIONS:
        raise ValueError('unsupported case version or condition')
    expected=stable_hash({k:v for k,v in value.items() if k not in ('frozen_at','task_spec_sha256')})
    if value.get('task_spec_sha256')!=expected:
        raise ValueError('case specification checksum mismatch')
    for key in ('reference','quality_policy','triage_policy', *(['transform'] if value.get('transform') else [])):
        child=(path.parent/value[key]).resolve()
        if path.parent not in child.parents or digest(child)!=value[key+'_sha256']:
            raise ValueError(f'{key} escapes case or changed after freeze')
    return value
