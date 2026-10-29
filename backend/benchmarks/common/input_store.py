"""Case inputs from one content-addressed cache instead of a copy per case.

Every frozen case lists its input files with SHA-256 checksums. Many cases (and
their execution variants) list the same workbooks, so each input is kept once
in a local cache named by checksum and hard-linked into each case's
``input_root``. Hard links are ordinary files to the package audit (no
symlinks, identical bytes), so the frozen-case checks are unchanged.

Missing inputs are downloaded from the private DagsHub store used by
``scripts/offload_benchmarks.py``; the download is checksum-verified before use.
The DagsHub client runs in its own environment (.tools/benchmark-offload).
"""
from __future__ import annotations

import json
import os
import subprocess
from contextvars import ContextVar
from contextlib import contextmanager
import tempfile
import shutil
from pathlib import Path

from .case_protocol import ROOT, digest

_execution_cache = ContextVar('benchmark_execution_input_cache', default=None)


def cache_dir() -> Path:
    return Path(_execution_cache.get() or os.environ.get('BIODEMO_INPUT_CACHE') or ROOT / '.cache' / 'benchmark-inputs')


@contextmanager
def execution_inputs(manifest_path):
    """Per-execution cache; remove verified remote input links after the run."""
    with tempfile.TemporaryDirectory(prefix='biodemo-inputs-') as temporary:
        manifest_path = Path(manifest_path).resolve()
        from .case_protocol import load_case
        case = load_case(manifest_path)
        staged = Path(temporary) / 'case'; staged.mkdir()
        # Frozen metadata remains identical; only this invocation's inputs are hydrated.
        for name in ('case.json', case['reference'], case['quality_policy'], case['triage_policy'],
                     *([case['transform']] if case.get('transform') else [])):
            target = staged / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(manifest_path.parent / name, target)
        for path, entry in _allowlist(manifest_path):
            if path.is_symlink() or (path.is_file() and digest(path)!=entry['sha256']):
                raise ValueError('Local frozen input changed; refusing to hide it with a remote replacement')
            if path.is_file():
                target = staged / case['input_root'] / path.relative_to(manifest_path.parent / case['input_root'])
                target.parent.mkdir(parents=True, exist_ok=True)
                try: os.link(path, target)
                except FileNotFoundError: pass  # A concurrent execution may have evicted a verified remote copy.
        token = _execution_cache.set(temporary)
        try: yield staged / 'case.json'
        finally:
            try:
                inventory_path = ROOT / 'results/offload/inputs.json'
                remote = json.loads(inventory_path.read_text()).get('blobs', {}) if inventory_path.exists() else {}
                for path, entry in _allowlist(manifest_path):
                    if entry['sha256'] in remote and path.is_file() and not path.is_symlink() and digest(path) == entry['sha256']:
                        path.unlink()
            finally:
                _execution_cache.reset(token)


def offload_python() -> Path:
    return Path(os.environ.get('BIODEMO_OFFLOAD_PYTHON') or ROOT / '.tools' / 'benchmark-offload' / 'bin' / 'python')


def _allowlist(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    case = json.loads(manifest_path.read_text())
    for name in [case['input_root'], *(item['path'] for item in case['allowlist'])]:
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe case input path')
    package = manifest_path.parent / case['input_root']
    return [(package / item['path'], item) for item in case['allowlist']]


def _cached(sha: str) -> Path | None:
    path = cache_dir() / sha
    return path if path.is_file() and not path.is_symlink() and digest(path) == sha else None


def _adopt(path: Path, sha: str) -> Path:
    """Place an already verified local file into the cache without copying it."""
    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / sha
    if not target.exists():
        os.link(path, target)
        target.chmod(0o444)
    return target


def fetch(shas) -> list[str]:
    """Download inputs missing from the cache; returns the checksums fetched."""
    wanted = sorted({s for s in shas if _cached(s) is None})
    if not wanted:
        return []
    python = offload_python()
    if not python.is_file():
        raise RuntimeError(f'{len(wanted)} case inputs are not cached locally and the DagsHub client '
                           f'environment is missing ({python}); see docs/benchmark_offload.md')
    command = [str(python), str(ROOT / 'scripts' / 'offload_benchmarks.py'), '--root', str(ROOT),
               'fetch-inputs', '--dest', str(cache_dir())]
    for sha in wanted:
        command += ['--sha', sha]
    process = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    if process.returncode != 0:
        raise RuntimeError('Case input download failed: ' + (process.stderr.strip().splitlines() or ['unknown error'])[-1])
    for sha in wanted:
        path = _cached(sha)
        if path is None or digest(path) != sha:
            raise RuntimeError('Downloaded case input failed checksum verification: ' + sha)
    return wanted


def materialize(manifest_path) -> dict:
    """Make a case's declared inputs present, linking from the cache or downloading them."""
    files = _allowlist(manifest_path)
    linked, present = [], 0
    for path, item in files:
        if path.is_file():
            present += 1
            # Verified local files seed the cache so other cases can link to them.
            if _cached(item['sha256']) is None and digest(path) == item['sha256']:
                _adopt(path, item['sha256'])
    fetched = fetch(item['sha256'] for path, item in files if not path.exists())
    for path, item in files:
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        os.link(cache_dir() / item['sha256'], path)
        linked.append(item['path'])
    return {'present': present, 'linked': linked, 'downloaded': fetched}


def deduplicate(manifest_paths) -> dict:
    """Replace verified duplicate input copies with hard links to one cached file."""
    saved = replaced = 0
    for manifest in manifest_paths:
        for path, item in _allowlist(manifest):
            if not path.is_file() or path.is_symlink() or digest(path) != item['sha256']:
                continue
            blob = _cached(item['sha256']) or _adopt(path, item['sha256'])
            if os.path.samefile(blob, path):
                continue
            temporary = path.with_name(path.name + '.dedup-link')
            os.link(blob, temporary)
            os.replace(temporary, path)
            replaced += 1
            saved += item['bytes']
    return {'replaced_copies': replaced, 'bytes_freed': saved}


def evict(manifest_paths, remote_inventory: Path, *, include_cache: bool = False) -> dict:
    """Remove local inputs that are verified in remote storage; materialize() restores them."""
    inventory = json.loads(Path(remote_inventory).read_text())['blobs'] if Path(remote_inventory).exists() else {}
    removed, kept = 0, []
    for manifest in manifest_paths:
        for path, item in _allowlist(manifest):
            if not path.exists():
                continue
            if item['sha256'] not in inventory:
                kept.append(str(path))
                continue
            path.unlink()
            removed += 1
    cache_removed = 0
    if include_cache and cache_dir().is_dir():
        for blob in cache_dir().iterdir():
            if blob.name in inventory:
                blob.unlink()
                cache_removed += 1
    return {'removed_links': removed, 'kept_not_remote': kept, 'removed_cache_blobs': cache_removed}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('action', choices=['materialize', 'deduplicate', 'evict', 'status'])
    parser.add_argument('--manifest', action='append', type=Path,
                        help='case.json paths (default: every frozen case under benchmarks/manifests)')
    parser.add_argument('--include-cache', action='store_true', help='evict: also remove the shared cache')
    args = parser.parse_args()
    manifests = args.manifest or sorted((ROOT / 'benchmarks' / 'manifests').glob('*/*/case.json'))
    if args.action == 'materialize':
        result = {str(m): materialize(m) for m in manifests}
    elif args.action == 'deduplicate':
        result = deduplicate(manifests)
    elif args.action == 'evict':
        result = evict(manifests, ROOT / 'results' / 'offload' / 'inputs.json', include_cache=args.include_cache)
    else:
        files = [(p, i) for m in manifests for p, i in _allowlist(m)]
        cache = cache_dir()
        result = {'declared_files': len(files), 'present': sum(p.exists() for p, _ in files),
                  'unique_inputs': len({i['sha256'] for _, i in files}),
                  'cached_inputs': len(list(cache.iterdir())) if cache.is_dir() else 0,
                  'cache_dir': str(cache)}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
