"""On-demand DagsHub data; no persistent dataset cache.

Transport reuses the project's isolated offload client and private bucket.
Only temporary, checksum-verified working copies exist during execution.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from contextvars import ContextVar

from .input_store import offload_python

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'benchmarks/assets'
_mounted = ContextVar('mounted_data_assets', default=frozenset())


def descriptor_for(value):
    value = str(value)
    if value.startswith('dagshub:'):
        from pathlib import PurePosixPath
        parts = PurePosixPath(value.split(':', 1)[1]).parts
        if not parts or any(p in {'.', '..', '/'} for p in parts): raise ValueError('Invalid artifact path')
        name = parts[0]
        if not name or Path(name).name != name: raise ValueError('Expected dagshub:ASSET_ID')
        descriptor = ASSETS / (name + '.json')
        if not descriptor.is_file(): raise FileNotFoundError(f'Unknown DagsHub asset: {name}')
        return descriptor, Path(*parts[1:])
    requested = Path(value).resolve()
    matches = []
    for descriptor in ASSETS.glob('*.json'):
        spec = json.loads(descriptor.read_text()); mount = spec.get('mount_path')
        if not mount: continue
        base = (ROOT / mount).resolve()
        if requested == base or requested.is_relative_to(base):
            matches.append((len(base.parts), descriptor, requested.relative_to(base)))
    return max(matches, default=(0, None, None), key=lambda item: item[0])[1:]


def _transport(*arguments):
    python = offload_python()
    if not python.is_file(): raise RuntimeError('DagsHub client is missing; see docs/benchmark_offload.md')
    process = subprocess.run([str(python), '-m', 'scripts.data_artifacts', *map(str, arguments)],
                             cwd=ROOT, capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError('DagsHub artifact operation failed; local data retained: ' + process.stderr[-1000:])
    return json.loads(process.stdout.strip().splitlines()[-1])


@contextmanager
def asset_path(value):
    """Resolve a local path or dagshub:ID only for this execution's lifetime."""
    requested = Path(value)
    if not str(value).startswith('dagshub:') and requested.exists():
        yield requested
        return
    descriptor, relative = descriptor_for(value)
    if descriptor is None: raise FileNotFoundError(f'Data is absent and has no remote descriptor: {value}')
    with tempfile.TemporaryDirectory(prefix='biodemo-data-') as temporary:
        spec = json.loads(descriptor.read_text())
        name = spec.get('filename') if spec.get('kind') == 'file' else 'payload'
        if not name or Path(name).name != name: raise ValueError('Unsafe artifact filename')
        destination = Path(temporary) / name
        _transport('fetch', descriptor, destination)
        resolved = destination / relative if relative != Path('.') else destination
        if not resolved.exists(): raise FileNotFoundError(f'Remote artifact does not contain {relative}')
        yield resolved


def read_json(path):
    """Read a small local receipt or hydrate its original large payload on demand."""
    path = Path(path)
    if path.is_file():
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or not value.get('remote_payload'): return value
        with asset_path(value['remote_payload']) as original:
            import hashlib
            with original.open('rb') as stream: checksum=hashlib.file_digest(stream,'sha256').hexdigest()
            if checksum!=value.get('remote_payload_sha256'): raise ValueError('Remote run payload does not match its recorded checksum')
            complete = json.loads(original.read_text())
        complete.update({k:v for k,v in value.items() if k not in {'remote_payload','remote_payload_sha256'}})
        return complete
    with asset_path(path) as local: return json.loads(local.read_text())


def publish_path(path, asset_id, *, prune=True, mount_path=None):
    if not asset_id or Path(asset_id).name != asset_id: raise ValueError('Invalid asset identifier')
    descriptor = ASSETS / (asset_id + '.json'); descriptor.parent.mkdir(parents=True, exist_ok=True)
    args = ['publish', Path(path).resolve(), descriptor]
    if mount_path: args += ['--mount-path', mount_path]
    if prune: args.append('--prune-local')
    return _transport(*args)


def publish_generated(path, asset_id):
    """Keep the sole new result if a temporary producer cannot publish it."""
    try: return publish_path(path,asset_id)
    except Exception as error:
        import uuid
        retained=ROOT/'.offload/failed-publications'/uuid.uuid4().hex
        retained.parent.mkdir(parents=True,exist_ok=True)
        if Path(path).exists(): shutil.move(str(path),retained)
        raise RuntimeError(f'Remote publication failed; unverified generated data retained at {retained}') from error


def archive_runtime(workspace, *, restore=False):
    """Use the existing owned-workspace archive for large, completed SDK state."""
    workspace=Path(workspace)
    if restore:
        if workspace.exists(): return
        action=['restore','--workspace',workspace.name]
    else:
        if not workspace.is_dir() or os.getenv('BIODEMO_KEEP_RUNTIME')=='1': return
        size=sum(p.stat().st_size for p in workspace.rglob('*') if p.is_file() and not p.is_symlink())
        if size<10*1024*1024: return
        action=['upload','--include-unrecorded','--prune-local','--workspace',workspace.name]
    process=subprocess.run([str(offload_python()),str(ROOT/'scripts/offload_benchmarks.py'),*action],
                           cwd=ROOT,capture_output=True,text=True)
    if process.returncode: raise RuntimeError('Runtime archive failed; existing local state retained: '+process.stderr[-800:])


def uses_assets(*paths):
    """Hydrate only during a legacy function call, preserving fixed-path readers."""
    from functools import wraps
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            with mounted_assets(*paths): return function(*args, **kwargs)
        return call
    return decorate


@contextmanager
def mounted_assets(*paths):
    """Compatibility for legacy code whose readers use fixed repository paths.

    Serialize mounts to avoid deleting another execution's input. Only data
    created by this context is removed; existing local inputs are untouched.
    """
    from contextlib import ExitStack
    import fcntl
    lock_dir = ROOT / '.offload/mount-locks'; lock_dir.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for value in paths:
            target = Path(value).absolute()
            descriptor, relative = descriptor_for(target)
            if descriptor is None: continue  # Existing missing-input behavior remains explicit.
            if descriptor in _mounted.get(): continue
            spec = json.loads(descriptor.read_text()); mount = (ROOT / spec['mount_path']).resolve()
            if not mount.is_relative_to(ROOT): raise ValueError('Legacy mounts must remain within repository')
            lock = stack.enter_context((lock_dir / (descriptor.stem + '.lock')).open('a+'))
            fcntl.flock(lock, fcntl.LOCK_EX)
            token = _mounted.set(_mounted.get() | {descriptor})
            stack.callback(_mounted.reset, token)
            if not mount.exists():
                mount.parent.mkdir(parents=True, exist_ok=True)
                _transport('fetch', descriptor, mount)
                stack.callback(lambda p=mount: shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True))
        yield


@contextmanager
def parser_models(package, backend):
    """Hydrate registered Docling weights once per ingestion, only when needed."""
    if backend not in {'auto', 'docling'}:
        yield; return
    if backend == 'auto':
        yield; return  # Explicit Docling requests hydrate weights; auto uses available native fallbacks.
    package = Path(package)
    if package.is_dir(): has_documents = any(p.suffix.lower() == '.pdf' for p in package.rglob('*'))
    elif package.suffix.lower() == '.zip':
        import zipfile
        with zipfile.ZipFile(package) as archive: has_documents = any(n.lower().endswith('.pdf') for n in archive.namelist())
    else: has_documents = package.suffix.lower() == '.pdf'
    if not has_documents:
        yield; return
    models = Path(os.getenv('DOCLING_ARTIFACTS_PATH') or ROOT/'.cache/cmo-docling-models/docling-project--docling-models')
    try: descriptor, relative = descriptor_for(models)
    except OSError: descriptor = None  # An isolated worker may not read external asset registries.
    if descriptor is None:
        yield; return
    previous = os.environ.get('DOCLING_ARTIFACTS_PATH')
    reference = 'dagshub:' + descriptor.stem
    if relative != Path('.'): reference += '/' + relative.as_posix()
    with asset_path(reference) as hydrated_models:
        os.environ['DOCLING_ARTIFACTS_PATH'] = str(hydrated_models)
        try: yield
        finally:
            if previous is None: os.environ.pop('DOCLING_ARTIFACTS_PATH', None)
            else: os.environ['DOCLING_ARTIFACTS_PATH'] = previous


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('asset'); parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    with asset_path(args.asset) as path:
        command = [str(path) if a == '{data}' else a for a in args.command]
        if command and command[0] == '--': command.pop(0)
        if not command: raise ValueError('Provide a command; {data} expands to the temporary input path')
        result = subprocess.run(command)
    raise SystemExit(result.returncode)


if __name__ == '__main__': main()
