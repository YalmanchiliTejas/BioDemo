"""Natural-language directory entry point over the existing isolated Prime adapter."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .isolated_runner import run_isolated


def investigate(directory, objective, output, *, mode='full_rlm', as_of=None, seconds=300):
    from benchmarks.common.artifact_store import asset_path, publish_path
    with asset_path(directory) as local:
        receipt = _investigate(local, objective, output, mode=mode, as_of=as_of, seconds=seconds)
    workspace = Path(receipt['workspace'])
    try:
        artifact_id = 'directory-' + workspace.name
        publish_path(workspace, artifact_id)
        receipt['workspace_artifact'] = 'dagshub:' + artifact_id
        receipt['workspace_local'] = False
    except Exception as error:
        receipt['archive_error'] = f'{type(error).__name__}: {error}'
        receipt['workspace_local'] = workspace.exists()
    Path(output).write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def _investigate(directory, objective, output, *, mode='full_rlm', as_of=None, seconds=300):
    directory = Path(directory).resolve(); output = Path(output).resolve()
    if not directory.is_dir(): raise ValueError('source directory is required')
    if output.is_relative_to(directory): raise ValueError('output must be outside the input directory')
    if output.exists(): raise ValueError('use a new output path')
    cutoff = datetime.fromisoformat(as_of.replace('Z', '+00:00')) if as_of else datetime.now(timezone.utc)
    if cutoff.tzinfo is None: raise ValueError('cutoff requires a timezone')
    workspace = Path(tempfile.mkdtemp(prefix='benchmark-case-')); package = workspace / 'agent_input'; package.mkdir()
    files = []; excluded = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink(): raise ValueError('symlink sources are not permitted')
        if not path.is_file(): continue
        available = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        relative = path.relative_to(directory)
        if available > cutoff:
            excluded.append({'path': str(relative), 'reason': 'file availability exceeds cutoff'}); continue
        # Historical raw bytes must not expose mixed future rows through Python.
        # Conservatively omit the entire file rather than rewrite genuine data.
        if as_of and path.suffix.lower() in {'.csv', '.tsv', '.xlsx', '.xlsm', '.parquet', '.json'}:
            from src.manufacturing_data.columnar import read_sheets
            from src.manufacturing_data.ingest import _iso, AVAIL_WORDS
            future = False
            try:
                for _, headers, frame, _ in read_sheets(path, None):
                    for column, header in zip(frame.columns, headers):
                        if any(word in header.lower() for word in AVAIL_WORDS):
                            for value in frame[column].drop_nulls().unique():
                                parsed = _iso(value)
                                if parsed:
                                    published = datetime.fromisoformat(parsed)
                                    if published.tzinfo is None: published = published.replace(tzinfo=timezone.utc)
                                    if published > cutoff: future = True
            except Exception:
                pass  # Corrupt files remain visible ingestion failures.
            if future:
                excluded.append({'path': str(relative), 'reason': 'contains future structured availability; whole raw file withheld'}); continue
        target = package / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
        files.append({'path': str(relative), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'available_at': available.isoformat()})
    cfg = {'mode': 'full_rlm' if mode == 'bounded_agent' else mode,
           'rlm_max_depth': 0 if mode == 'bounded_agent' else None,
           'case_id': 'directory-investigation', 'run_id': workspace.name,
           'state_directory': str(workspace / 'state'), 'artifact_directory': str(workspace / 'runtime-artifacts'),
           'document_backend': 'pypdf', 'allow_partial_ingestion': True,
           'evaluation_time': cutoff.isoformat(), 'budgets': {'wall_clock_seconds': seconds, 'tool_calls': 48},
           'hidden_paths': [str(directory)]}
    receipt = {'objective': objective, 'as_of': cutoff.isoformat(), 'mode': mode,
               'workspace': str(workspace), 'files': files, 'excluded': excluded,
               'availability_basis': 'Public filesystem mtime plus structured availability preflight. Historical document publication metadata must be trusted by the source owner.'}
    try:
        receipt['investigation'] = run_isolated(package, objective, cutoff.isoformat(), cfg)
        receipt['status'] = 'completed'
    except Exception as error:
        receipt.update(status='failed', error=f'{type(error).__name__}: {error}',
                       isolation_audit=getattr(error, 'isolation_audit', None))
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('directory'); parser.add_argument('objective'); parser.add_argument('output')
    parser.add_argument('--mode', choices=['full_rlm', 'bounded_agent', 'directory_rag', 'keyword_rules', 'linked_rules'], default='full_rlm')
    parser.add_argument('--as-of'); parser.add_argument('--seconds', type=int, default=300); args = parser.parse_args()
    result = investigate(args.directory, args.objective, args.output, mode=args.mode, as_of=args.as_of, seconds=args.seconds)
    print(json.dumps({k: result[k] for k in ('status', 'workspace')}))
