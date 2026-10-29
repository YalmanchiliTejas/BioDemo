"""Large data collections in the existing private DagsHub bucket.

Small descriptors stay in Git. Archives and original files are read back and
verified before explicit local pruning. Restores are atomic and never overwrite.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone

from scripts.offload_benchmarks import ROOT, client_for, encoded, excluded, missing, save, sha, verify_remote

VERSION = 'dagshub-data-artifact-v1'


def inventory(source):
    source = Path(source).absolute()
    if source.is_symlink() or source.resolve() != source:
        raise ValueError('Artifact source must not contain symlink ancestors')
    paths = [source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file() or p.is_symlink())
    entries = {}
    for path in paths:
        rel = Path(path.name) if source.is_file() else path.relative_to(source)
        if excluded(rel): continue
        if path.is_symlink() or not path.is_file(): raise ValueError('Only regular data files are supported')
        stat = path.stat(); digest = sha(path)
        if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ino):
            raise ValueError('Source changed while hashing')
        entries[rel.as_posix()] = {'sha256': digest, 'bytes': stat.st_size, 'mode': stat.st_mode & 0o777,
                                   'mtime_ns': stat.st_mtime_ns}
    if not entries: raise ValueError('Artifact source is empty')
    return {'kind': 'file' if source.is_file() else 'directory', 'files': entries}


def _archive(source, snapshot, target):
    with target.open('wb') as raw, gzip.GzipFile(fileobj=raw, filename='', mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as archive:
            body = encoded(snapshot); info = tarfile.TarInfo('.artifact-manifest.json'); info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
            for name, entry in snapshot['files'].items():
                path = source / name
                info = tarfile.TarInfo('data/' + name); info.size = entry['bytes']; info.mode = entry['mode']
                info.mtime = entry['mtime_ns'] / 1e9
                with path.open('rb') as stream: archive.addfile(info, stream)


def publish(source, descriptor, config, client, *, prune=False, mount_path=None):
    if Path(source).is_symlink(): raise ValueError('Artifact source must be regular, not a symlink')
    source = Path(source).resolve(); descriptor = Path(descriptor).resolve()
    if descriptor.is_relative_to(source): raise ValueError('Descriptor must be outside artifact source')
    snapshot = inventory(source)
    with tempfile.TemporaryDirectory(prefix='biodemo-offload-') as temporary:
        payload = source if snapshot['kind'] == 'file' else Path(temporary) / 'data.tar.gz'
        if snapshot['kind'] == 'directory': _archive(source, snapshot, payload)
        digest = sha(payload); size = payload.stat().st_size
        if descriptor.exists() and json.loads(descriptor.read_text()).get('sha256') != digest:
            raise ValueError('Asset identifier already pins different data; choose a new versioned identifier')
        key = config['prefix'] + '/data-artifacts/' + digest
        bucket = config['repo'].split('/')[1]
        try: client.head_object(Bucket=bucket, Key=key)
        except Exception as exc:
            if not missing(exc): raise
            client.upload_file(Filename=str(payload), Bucket=bucket, Key=key)
        verify_remote(client, bucket, key, digest, size)
        if inventory(source) != snapshot: raise ValueError('Source changed during upload; local data retained')
        result = {'version': VERSION, 'repo': config['repo'], 'key': key, 'sha256': digest, 'bytes': size,
                  'kind': snapshot['kind'], 'source_bytes': sum(e['bytes'] for e in snapshot['files'].values()),
                  'files': len(snapshot['files']), 'verified_at': datetime.now(timezone.utc).isoformat(),
                  'snapshot_sha256': hashlib.sha256(encoded(snapshot)).hexdigest(),
                  'filename': source.name if source.is_file() else None, 'mount_path': mount_path}
        if snapshot['kind'] == 'file': result['file_metadata'] = next(iter(snapshot['files'].values()))
        save(descriptor, result)  # Publish the recovery pointer before removing any data.
        if prune:
            for name, entry in snapshot['files'].items():
                path = source if snapshot['kind'] == 'file' else source / name
                if sha(path) != entry['sha256']: raise ValueError('Local bytes changed before pruning')
            for name in snapshot['files']:
                (source if snapshot['kind'] == 'file' else source / name).unlink()
            if source.is_dir():
                for directory in sorted(source.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                    if directory.is_dir():
                        try: directory.rmdir()
                        except OSError: pass
                try: source.rmdir()
                except OSError: pass  # Excluded credentials/locks are deliberately retained.
        return {**result, 'descriptor': str(descriptor), 'pruned': prune}


def _safe_member(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe artifact member')
    return path


def fetch(descriptor, destination, client):
    descriptor = Path(descriptor); spec = json.loads(descriptor.read_text()); destination = Path(destination).absolute()
    if spec.get('version') != VERSION: raise ValueError('Unsupported artifact descriptor')
    if destination.exists() or destination.is_symlink(): raise ValueError('Destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.fetch-artifact-', dir=destination.parent) as temporary:
        temporary = Path(temporary); payload = temporary / 'payload'
        body = client.get_object(Bucket=spec['repo'].split('/')[1], Key=spec['key'])['Body']
        try:
            with payload.open('wb') as stream:
                for chunk in iter(lambda: body.read(1024 * 1024), b''): stream.write(chunk)
        finally: body.close()
        if payload.stat().st_size != spec['bytes'] or sha(payload) != spec['sha256']:
            raise ValueError('Artifact download failed checksum/size verification')
        if spec['kind'] == 'file':
            if spec.get('file_metadata'):
                meta = spec['file_metadata']; payload.chmod(meta['mode'] & 0o777)
                if meta.get('mtime_ns') is not None:
                    os.utime(payload, ns=(meta['mtime_ns'], meta['mtime_ns']))
            os.replace(payload, destination)
        else:
            stage = temporary / 'data'; stage.mkdir()
            with tarfile.open(payload, 'r:gz') as archive:
                first = archive.next()
                if first is None or first.name != '.artifact-manifest.json' or not first.isfile() or first.size > 64 * 1024 * 1024:
                    raise ValueError('Artifact manifest missing or oversized')
                snapshot_body = archive.extractfile(first).read()
                if hashlib.sha256(snapshot_body).hexdigest() != spec['snapshot_sha256']:
                    raise ValueError('Artifact member manifest changed')
                snapshot = json.loads(snapshot_body); seen = set()
                for member in archive:
                    if member.name == first.name: continue
                    path = _safe_member(member.name)
                    if path.parts[0] != 'data' or len(path.parts) < 2 or not member.isfile():
                        raise ValueError('Artifact member must be a plain data file')
                    name = PurePosixPath(*path.parts[1:]).as_posix(); entry = snapshot['files'].get(name)
                    if entry is None or name in seen or member.size != entry['bytes']:
                        raise ValueError('Unexpected or repeated artifact member')
                    target = stage / name; target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as src, target.open('xb') as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    if sha(target) != entry['sha256']: raise ValueError('Artifact member checksum mismatch')
                    target.chmod(entry['mode'] & 0o777); os.utime(target, ns=(entry['mtime_ns'], entry['mtime_ns']))
                    seen.add(name)
                if seen != set(snapshot['files']): raise ValueError('Artifact members are missing')
            os.replace(stage, destination)
    return {'destination': str(destination), 'verified_sha256': spec['sha256'], 'files': spec['files']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    push = commands.add_parser('publish'); push.add_argument('source', type=Path); push.add_argument('descriptor', type=Path)
    push.add_argument('--prune-local', action='store_true'); push.add_argument('--mount-path')
    pull = commands.add_parser('fetch'); pull.add_argument('descriptor', type=Path); pull.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'publish':
        config = json.loads((ROOT / '.offload/config.json').read_text())
        result = publish(args.source, args.descriptor, config, client_for(config['repo']), prune=args.prune_local, mount_path=args.mount_path)
    else:
        spec = json.loads(args.descriptor.read_text()); result = fetch(args.descriptor, args.destination, client_for(spec['repo']))
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
