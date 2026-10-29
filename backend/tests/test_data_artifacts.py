import io
import json
from pathlib import Path
import pytest

from scripts.data_artifacts import publish, fetch, _safe_member
from test_benchmark_offload import Bucket


def test_round_trip_preserves_bytes_mtime_and_prunes_only_verified_data(tmp_path):
    source = tmp_path / 'corpus'; source.mkdir(); (source / 'data.csv').write_bytes(b'time,pressure\n0.2,1.9\n')
    (source / '.env').write_text('secret excluded')
    stamp = (source / 'data.csv').stat().st_mtime_ns
    client = Bucket(); descriptor = tmp_path / 'asset.json'
    result = publish(source, descriptor, {'repo': 'owner/private', 'prefix': 'archives'}, client, prune=True)
    assert result['pruned'] and not (source / 'data.csv').exists()
    assert (source / '.env').is_file() and all(b'secret excluded' not in b for b in client.objects.values())
    target = tmp_path / 'restored'; fetch(descriptor, target, client)
    assert (target / 'data.csv').read_bytes() == b'time,pressure\n0.2,1.9\n'
    assert (target / 'data.csv').stat().st_mtime_ns == stamp
    assert not (target / '.env').exists()


def test_file_download_and_changed_sources_are_protected(tmp_path):
    source = tmp_path / 'data.zip'; source.write_bytes(b'original archive bytes')
    client = Bucket(); descriptor = tmp_path / 'file.json'
    publish(source, descriptor, {'repo': 'owner/private', 'prefix': 'data'}, client, prune=True)
    assert not source.exists()
    fetch(descriptor, source, client); assert source.read_bytes() == b'original archive bytes'
    with pytest.raises(ValueError, match='already exists'): fetch(descriptor, source, client)
    client.hook = lambda: source.write_bytes(b'changed during verification')
    with pytest.raises(ValueError, match='changed'): publish(source, descriptor, {'repo': 'owner/private', 'prefix': 'data'}, client, prune=True)
    assert source.read_bytes() == b'changed during verification'


def test_corruption_never_removes_source_or_publishes_partial_download(tmp_path):
    source = tmp_path / 'input'; source.mkdir(); (source / 'record').write_text('evidence')
    client = Bucket(); client.corrupt = True; descriptor = tmp_path / 'asset.json'
    with pytest.raises(ValueError, match='checksum'): publish(source, descriptor, {'repo': 'o/private', 'prefix': 'data'}, client, prune=True)
    assert (source / 'record').is_file() and not descriptor.exists()
    client.corrupt = False; publish(source, descriptor, {'repo': 'o/private', 'prefix': 'data'}, client)
    client.corrupt = True
    with pytest.raises(ValueError, match='checksum'): fetch(descriptor, tmp_path / 'output', client)
    assert not (tmp_path / 'output').exists()


def test_artifact_scope_and_member_paths(tmp_path):
    for name in ['/etc/passwd', '../outside', 'data/../../outside']:
        with pytest.raises(ValueError): _safe_member(name)
    source = tmp_path / 'source'; source.mkdir(); (source / 'file').write_text('a')
    with pytest.raises(ValueError, match='outside'): publish(source, source / 'pointer.json', {}, Bucket())
    (source / 'symlink').symlink_to(tmp_path / 'other')
    with pytest.raises(ValueError, match='regular'): publish(source, tmp_path / 'pointer.json', {}, Bucket())


def test_runtime_materialization_is_temporary_and_local_sources_are_not_removed(tmp_path, monkeypatch):
    import benchmarks.common.artifact_store as store
    assets = tmp_path / 'assets'; assets.mkdir(); monkeypatch.setattr(store, 'ASSETS', assets)
    (assets / 'case.json').write_text(json.dumps({'mount_path': None}))
    def transfer(_action, _descriptor, target):
        Path(target).mkdir(); (Path(target) / 'data').write_text('verified')
    monkeypatch.setattr(store, '_transport', transfer)
    with pytest.raises(RuntimeError, match='investigation failure'):
        with store.asset_path('dagshub:case') as path:
            temporary = path; assert (path / 'data').is_file()
            raise RuntimeError('investigation failure')
    assert not temporary.exists()
    local = tmp_path / 'owned'; local.write_text('untouched')
    with store.asset_path(local) as resolved: assert resolved == local
    assert local.is_file()


def test_legacy_mounts_are_reentrant_and_removed_after_failure(tmp_path,monkeypatch):
    import benchmarks.common.artifact_store as store
    assets=tmp_path/'assets';assets.mkdir();monkeypatch.setattr(store,'ASSETS',assets);monkeypatch.setattr(store,'ROOT',tmp_path)
    (assets/'data.json').write_text(json.dumps({'mount_path':'dataset','kind':'directory'}))
    calls=[]
    def download(_action,_descriptor,target):
        calls.append(target);Path(target).mkdir();(Path(target)/'x').write_text('data')
    monkeypatch.setattr(store,'_transport',download)
    with pytest.raises(ValueError):
        with store.mounted_assets(tmp_path/'dataset'):
            with store.mounted_assets(tmp_path/'dataset'):
                assert (tmp_path/'dataset/x').is_file()
                raise ValueError('run failed')
    assert len(calls)==1 and not (tmp_path/'dataset').exists()


def test_restored_store_rebinds_only_checksum_verified_partitions(tmp_path):
    import shutil
    from src.manufacturing_data import ManufacturingStore,ManufacturingTools,ingest_package
    raw=tmp_path/'raw';raw.mkdir();(raw/'data.csv').write_text('batch_id,time(h),pressure(bar)\nB-123,.2,1.125\n')
    original=ManufacturingStore(tmp_path/'original');ingest_package(raw,original,document_backend='pypdf')
    before=ManufacturingTools(original).query_data(sql="SELECT id,value_number FROM observations WHERE name='pressure(bar)'")
    shutil.copytree(original.root,tmp_path/'restored');shutil.rmtree(original.root)
    restored=ManufacturingStore(tmp_path/'restored')
    after=ManufacturingTools(restored).query_data(sql="SELECT id,value_number FROM observations WHERE name='pressure(bar)'")
    assert before['rows']==after['rows']


@pytest.mark.parametrize('archive_fails', [False, True])
def test_directory_investigation_archives_workspace_or_reports_retained_copy(tmp_path, monkeypatch, archive_fails):
    import shutil
    import benchmarks.common.artifact_store as artifacts
    import benchmarks.common.investigate_directory as entry
    source = tmp_path/'source'; source.mkdir()
    workspace = tmp_path/'benchmark-case-test'; workspace.mkdir()
    (workspace/'evidence').write_text('retained original')
    output = tmp_path/'receipt.json'
    monkeypatch.setattr(entry, '_investigate', lambda *a, **k: {'status': 'completed', 'workspace': str(workspace)})
    def publish(path, asset_id):
        assert path == workspace and asset_id == 'directory-benchmark-case-test'
        if archive_fails: raise RuntimeError('remote verification failed')
        shutil.rmtree(path)
    monkeypatch.setattr(artifacts, 'publish_path', publish)
    result = entry.investigate(source, 'investigate', output)
    assert json.loads(output.read_text()) == result
    assert result['workspace_local'] == archive_fails
    assert workspace.exists() == archive_fails
    if archive_fails: assert 'remote verification failed' in result['archive_error']
    else: assert result['workspace_artifact'] == 'dagshub:directory-benchmark-case-test'


def test_explicit_docling_hydrates_despite_residual_lock_directory(tmp_path, monkeypatch):
    import benchmarks.common.artifact_store as artifacts
    assets=tmp_path/'assets'; assets.mkdir()
    models=tmp_path/'models'; (models/'docling-project--docling-models').mkdir(parents=True)
    monkeypatch.setattr(artifacts,'ASSETS',assets)
    (assets/'weights.json').write_text(json.dumps({'kind':'directory','mount_path':str(models)}))
    monkeypatch.setenv('DOCLING_ARTIFACTS_PATH',str(models/'docling-project--docling-models'))
    package=tmp_path/'package'; package.mkdir(); (package/'record.pdf').write_bytes(b'pdf')
    calls=[]
    def fetch(*args):
        calls.append(args)
        destination=Path(args[-1]); (destination/'docling-project--docling-models/model_artifacts').mkdir(parents=True)
    monkeypatch.setattr(artifacts,'_transport',fetch)
    import os
    with artifacts.parser_models(package,'auto'): pass
    assert not calls
    with artifacts.parser_models(package,'docling'):
        hydrated=Path(os.environ['DOCLING_ARTIFACTS_PATH'])
        assert hydrated!=models/'docling-project--docling-models'
        assert (hydrated/'model_artifacts').is_dir()
    assert len(calls)==1 and not hydrated.exists()
    assert os.environ['DOCLING_ARTIFACTS_PATH']==str(models/'docling-project--docling-models')
