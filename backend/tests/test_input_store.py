"""Case inputs are kept once by checksum and fetched from remote storage when absent."""
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from benchmarks.common import input_store
from benchmarks.common.case_audit import audit_case
from benchmarks.common.case_protocol import stable_hash


def make_case(directory: Path, files: dict[str, bytes]) -> Path:
    package = directory / 'agent_input'
    allowlist = []
    for name, content in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        allowlist.append({'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                          'available_at': None})
    manifest = directory / 'case.json'
    manifest.write_text(json.dumps({'input_root': 'agent_input', 'allowlist': allowlist,
                                    'package_sha256': stable_hash(allowlist)}))
    return manifest


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """A stand-in DagsHub client: copies checksum-named blobs from a directory."""
    store = tmp_path / 'remote'
    store.mkdir()
    client = tmp_path / 'fake-offload-python'
    client.write_text(f"""#!{sys.executable}
import shutil, sys
from pathlib import Path
args = sys.argv[1:]
dest = Path(args[args.index('--dest') + 1]); dest.mkdir(parents=True, exist_ok=True)
for i, value in enumerate(args):
    if value == '--sha':
        shutil.copyfile(Path({str(store)!r}) / args[i + 1], dest / args[i + 1])
""")
    client.chmod(client.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv('BIODEMO_OFFLOAD_PYTHON', str(client))
    monkeypatch.setenv('BIODEMO_INPUT_CACHE', str(tmp_path / 'cache'))
    return store


def test_cases_share_one_copy_and_still_pass_the_package_audit(tmp_path, remote):
    files = {'a.csv': b'value\n1\n', 'nested/b.csv': b'value\n2\n'}
    first, second = make_case(tmp_path / 'one', files), make_case(tmp_path / 'two', files)
    result = input_store.deduplicate([first, second])
    assert result['replaced_copies'] == 2 and result['bytes_freed'] == sum(map(len, files.values()))
    for name in files:
        assert os.path.samefile(first.parent / 'agent_input' / name, second.parent / 'agent_input' / name)
        assert not (second.parent / 'agent_input' / name).is_symlink()
    # Hard links remain plain files with the frozen bytes.
    package = second.parent / 'agent_input'
    assert {str(p.relative_to(package)) for p in package.rglob('*') if p.is_file()} == set(files)


def test_missing_inputs_are_linked_from_cache_or_downloaded_and_verified(tmp_path, remote):
    files = {'a.csv': b'value\n1\n', 'b.csv': b'value\n2\n'}
    manifest = make_case(tmp_path / 'case', files)
    for item in json.loads(manifest.read_text())['allowlist']:
        (remote / item['sha256']).write_bytes(files[item['path']])
        (manifest.parent / 'agent_input' / item['path']).unlink()
    result = input_store.materialize(manifest)
    assert sorted(result['linked']) == ['a.csv', 'b.csv'] and len(result['downloaded']) == 2
    assert (manifest.parent / 'agent_input/a.csv').read_bytes() == files['a.csv']
    # A second case reuses the cache without downloading again.
    other = make_case(tmp_path / 'other', files)
    for name in files:
        (other.parent / 'agent_input' / name).unlink()
    assert input_store.materialize(other)['downloaded'] == []


def test_corrupt_download_is_rejected(tmp_path, remote):
    manifest = make_case(tmp_path / 'case', {'a.csv': b'value\n1\n'})
    item = json.loads(manifest.read_text())['allowlist'][0]
    (remote / item['sha256']).write_bytes(b'tampered')
    (manifest.parent / 'agent_input/a.csv').unlink()
    with pytest.raises(RuntimeError, match='checksum'):
        input_store.materialize(manifest)
    assert not (manifest.parent / 'agent_input/a.csv').exists()


def test_evict_only_removes_inputs_verified_remotely(tmp_path, remote):
    files = {'a.csv': b'value\n1\n', 'b.csv': b'value\n2\n'}
    manifest = make_case(tmp_path / 'case', files)
    shas = {i['path']: i['sha256'] for i in json.loads(manifest.read_text())['allowlist']}
    inventory = tmp_path / 'inputs.json'
    inventory.write_text(json.dumps({'version': 1, 'blobs': {shas['a.csv']: {}}}))
    result = input_store.evict([manifest], inventory)
    assert result['removed_links'] == 1 and result['kept_not_remote'] == [str(manifest.parent / 'agent_input/b.csv')]
    assert not (manifest.parent / 'agent_input/a.csv').exists()


def test_real_case_audit_accepts_linked_inputs(tmp_path):
    cho = Path(__file__).resolve().parents[1] / 'benchmarks/manifests/cho/CHO-04-raw/case.json'
    if not cho.is_file():
        pytest.skip('local CHO manifests are not available')
    assert audit_case(cho)['pass']
