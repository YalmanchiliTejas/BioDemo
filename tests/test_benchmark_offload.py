"""Deletion, integrity, scope and restore regressions; no external service calls."""
import io
import json
from pathlib import Path
import pytest
from scripts.offload_benchmarks import offload,plan,restore,locked_workspace,local_file,sha


class NotFound(Exception):
    response={'Error':{'Code':'404'}}

class Bucket:
    def __init__(self):self.objects={};self.uploads=[];self.reads=[];self.corrupt=False;self.hook=None
    def head_object(self,*,Bucket,Key):
        if Key not in self.objects:raise NotFound()
        return {'ContentLength':len(self.objects[Key])}
    def upload_file(self,*,Filename,Bucket,Key):
        self.uploads.append(Key);self.objects[Key]=Path(Filename).read_bytes()
    def put_object(self,*,Bucket,Key,Body):self.objects[Key]=Body
    def get_object(self,*,Bucket,Key):
        self.reads.append(Key)
        if self.hook:self.hook();self.hook=None
        return {'Body':io.BytesIO(b'corrupt' if self.corrupt else self.objects[Key])}


@pytest.fixture
def archive(tmp_path):
    id='a'*32;workspace=tmp_path/'benchmarks/runtime'/('benchmark-case-'+id);workspace.mkdir(parents=True)
    (workspace/'owner.json').write_text(json.dumps({'last_run_id':id}))
    (workspace/'source.bin').write_bytes(b'Authentic retained bytes\x00')
    (workspace/'state').mkdir();(workspace/'state/metadata.sqlite').write_bytes(b'Preserve source coordinates')
    (workspace/'.env').write_text('TOKEN=secret-value')
    configs=workspace/'state/bridge-configs';configs.mkdir();(configs/'token.json').write_text('secret-bridge-token')
    result=tmp_path/'results/evaluation'/id;result.mkdir(parents=True)
    (result/'run.json').write_text(json.dumps({'run_id':id,'runtime_workspace':str(workspace),'ended_at':'2026-10-18T00:00:00Z','status':'failed'}))
    config={'repo':'owner/private-archive','prefix':'archives/v1'}
    return tmp_path,workspace,config,Bucket()


def test_upload_readback_and_no_implicit_deletion_or_credentials(archive):
    root,workspace,config,client=archive
    receipt=offload(root,workspace.name,config,client)
    assert workspace.exists() and not receipt['local_removed']
    assert client.reads and all(b'secret' not in body for body in client.objects.values())
    assert (root/'results/offload/catalog.json').exists()
    assert plan(root)['workspaces'][0]['status']=='eligible'


def test_explicit_verified_prune_then_restore_preserves_records_and_bytes(archive):
    root,workspace,config,client=archive;expected=sha(workspace/'source.bin')
    run_file=root/'results/evaluation'/('a'*32)/'run.json';original_run=run_file.read_bytes()
    receipt=offload(root,workspace.name,config,client,prune_local=True)
    assert not workspace.exists() and receipt['local_removed']
    assert run_file.read_bytes()==original_run
    result=restore(root,receipt,client)
    assert result['restored_workspace']==str(workspace)
    assert sha(workspace/'source.bin')==expected and not (workspace/'.env').exists()
    assert run_file.read_bytes()==original_run
    with pytest.raises(ValueError,match='already exists'):restore(root,receipt,client)


def test_corrupt_remote_blocks_local_removal(archive):
    root,workspace,config,client=archive;client.corrupt=True
    with pytest.raises(ValueError,match='checksum'):offload(root,workspace.name,config,client,prune_local=True)
    assert workspace.exists() and (workspace/'source.bin').is_file()


def test_local_change_while_uploading_blocks_removal(archive):
    root,workspace,config,client=archive
    client.hook=lambda:(workspace/'new-finding.txt').write_text('New evidence')
    with pytest.raises(ValueError,match='changed'):offload(root,workspace.name,config,client,prune_local=True)
    assert workspace.exists() and (workspace/'new-finding.txt').exists()


def test_active_workspace_is_skipped(archive):
    root,workspace,_,_=archive
    with locked_workspace(root,workspace.name):
        assert plan(root)['workspaces'][0]['status']=='active_skipped'


def test_unrecorded_workspace_requires_explicit_option(archive):
    root,workspace,config,client=archive
    (root/'results/evaluation'/('a'*32)/'run.json').unlink()
    assert plan(root)['workspaces'][0]['status']=='unrecorded_requires_explicit_inclusion'
    with pytest.raises(ValueError,match='No finished'):offload(root,workspace.name,config,client)
    assert offload(root,workspace.name,config,client,include_unrecorded=True)['recorded_run_ids']==[]


def test_duplicate_bytes_are_stored_once_and_upload_can_resume(archive):
    root,workspace,config,client=archive
    (workspace/'same-source.bin').write_bytes((workspace/'source.bin').read_bytes())
    offload(root,workspace.name,config,client);uploads=len(client.uploads)
    offload(root,workspace.name,config,client)
    assert len(client.uploads)==uploads


def test_restore_rejects_corruption_without_publishing_workspace(archive):
    root,workspace,config,client=archive
    receipt=offload(root,workspace.name,config,client,prune_local=True)
    key=next(k for k in client.objects if '/blobs/' in k);client.objects[key]=b'corrupt'
    with pytest.raises(ValueError,match='checksum'):restore(root,receipt,client)
    assert not workspace.exists()


def test_symlinks_traversal_and_foreign_workspace_are_rejected(archive):
    root,workspace,config,client=archive
    for path in ['../outside','/etc/passwd','workspace/../../outside','records/../../outside','workspace']:
        with pytest.raises(ValueError):local_file(root,workspace,path)
    (workspace/'link').symlink_to(root/'other-file')
    with pytest.raises(ValueError,match='regular'):offload(root,workspace.name,config,client)
    with pytest.raises(ValueError,match='Invalid owned'):
        with locked_workspace(root,'../../outside'):pass


def test_restore_does_not_overwrite_newer_result_records(archive):
    root,workspace,config,client=archive
    receipt=offload(root,workspace.name,config,client,prune_local=True)
    run_file=root/'results/evaluation'/('a'*32)/'run.json';run_file.write_text('New independent review')
    with pytest.raises(ValueError,match='differs'):restore(root,receipt,client)
    assert run_file.read_text()=='New independent review' and not workspace.exists()
