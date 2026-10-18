"""Checksum-verified DagsHub offload, with no second local dataset copy.

Only an explicit --prune-local removes owned runtime workspaces, after remote
read-back verification. Result records and the local restore catalog stay local.
"""
import argparse
from contextlib import contextmanager
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=re.compile(r'benchmark-case-[a-f0-9]{32}')
EXCLUDE_DIRS={'__pycache__','.pytest_cache','bridge-configs','tmp','ipython','matplotlib'}
EXCLUDE_FILES={'.DS_Store','auth.json','auth.json.lock'}

def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_bytes(encoded(value));temporary.replace(path)
def excluded(relative):
    return bool(set(relative.parts)&EXCLUDE_DIRS) or relative.name in EXCLUDE_FILES or any(fnmatch.fnmatch(relative.name,p) for p in ('.env*','*.lock','*.pem','*.key','*.p12'))

@contextmanager
def locked_workspace(root,name):
    if not WORKSPACE.fullmatch(name):raise ValueError('Invalid owned workspace name')
    base=root/'benchmarks/runtime';workspace=base/name
    if workspace.is_symlink() or workspace.resolve().parent!=base or not (workspace/'owner.json').is_file():
        raise ValueError('Workspace is not an owned, local benchmark directory')
    with (workspace/'evaluation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield workspace
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

def record_index(root):
    found={}
    for file in sorted((root/'results/evaluation').glob('*/run.json')):
        value=json.loads(file.read_text())
        if value.get('runtime_workspace') and value.get('ended_at'):
            found.setdefault(value['runtime_workspace'],[]).append(file.parent)
    return found

def inventory(root,workspace,hashes=True,associated=None):
    files={};omitted=[]
    associated=record_index(root).get(str(workspace),[]) if associated is None else associated
    for prefix,base in [('workspace',workspace)]+[('records/'+p.name,p) for p in associated]:
        if base.is_symlink() or not base.resolve().is_relative_to(root):raise ValueError('Snapshot root escapes project: '+str(base))
        for folder,dirs,names in os.walk(base,followlinks=False):
            for directory in dirs[:]:
                path=Path(folder)/directory;relative=path.relative_to(base)
                if excluded(relative):omitted.append(prefix+'/'+str(relative));dirs.remove(directory)
                elif path.is_symlink():raise ValueError('Symlink in snapshot: '+str(path))
            for name in sorted(names):
                path=Path(folder)/name;relative=path.relative_to(base)
                if excluded(relative):omitted.append(prefix+'/'+str(relative));continue
                if path.is_symlink() or not path.is_file():raise ValueError('Non-regular snapshot file: '+str(path))
                info=path.stat();entry={'bytes':info.st_size,'mode':stat.S_IMODE(info.st_mode)}
                if hashes:entry['sha256']=sha(path)
                files[prefix+'/'+relative.as_posix()]=entry
    return {'version':'biodemo-offload-v1','workspace':workspace.name,'original_workspace':str(workspace),
            'recorded_run_ids':[p.name for p in associated],'files':files,'excluded_paths':sorted(omitted),
            'restoration':'Restore workspace at its original project path; metadata may contain absolute source paths.'}

def plan(root,include_unrecorded=False):
    rows=[];index=record_index(root)
    for workspace in sorted((root/'benchmarks/runtime').glob('benchmark-case-*')):
        try:
            with locked_workspace(root,workspace.name):
                snapshot=inventory(root,workspace,hashes=False,associated=index.get(str(workspace),[]))
                rows.append({'workspace':workspace.name,'runtime_bytes':sum(e['bytes'] for p,e in snapshot['files'].items() if p.startswith('workspace/')),
                             'recorded_run_ids':snapshot['recorded_run_ids'],
                             'status':'eligible' if snapshot['recorded_run_ids'] or include_unrecorded else 'unrecorded_requires_explicit_inclusion'})
        except BlockingIOError:rows.append({'workspace':workspace.name,'status':'active_skipped'})
        except ValueError as exc:rows.append({'workspace':workspace.name,'status':'skipped','reason':str(exc)})
    return {'workspaces':rows,'eligible_runtime_bytes':sum(r.get('runtime_bytes',0) for r in rows if r['status']=='eligible')}

def missing(error):
    return getattr(error,'response',{}).get('Error',{}).get('Code') in {'404','NoSuchKey','NotFound'}

def verify_remote(client,bucket,key,digest,size):
    body=client.get_object(Bucket=bucket,Key=key)['Body'];h=hashlib.sha256();count=0
    try:
        for chunk in iter(lambda:body.read(1024*1024),b''):h.update(chunk);count+=len(chunk)
    finally:body.close()
    if h.hexdigest()!=digest or count!=size:raise ValueError('Remote read-back checksum/size failed: '+key)

def local_file(root,workspace,name):
    relative=PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid manifest path')
    if not relative.parts:raise ValueError('Invalid manifest path')
    if relative.parts[0]=='workspace' and len(relative.parts)>1:
        destination=workspace.joinpath(*relative.parts[1:])
        if not destination.resolve().is_relative_to(root):raise ValueError('Workspace path escapes project root')
        return destination
    if relative.parts[0]=='records' and len(relative.parts)>2 and re.fullmatch('[a-f0-9]{32}',relative.parts[1]):
        destination=root.joinpath('results/evaluation',*relative.parts[1:])
        if not destination.resolve().is_relative_to(root):raise ValueError('Result path escapes project root')
        return destination
    raise ValueError('Invalid manifest member')

def offload(root,name,config,client,*,prune_local=False,include_unrecorded=False,verified=None,associated=None):
    verified=verified if verified is not None else set()
    bucket=config['repo'].split('/')[1];prefix=config['prefix']
    with locked_workspace(root,name) as workspace:
        associated=record_index(root).get(str(workspace),[]) if associated is None else associated
        snapshot=inventory(root,workspace,associated=associated)
        if not snapshot['recorded_run_ids'] and not include_unrecorded:
            raise ValueError('No finished result record; use --include-unrecorded to preserve this historical workspace explicitly')
        print(json.dumps({'uploading_workspace':name,'files':len(snapshot['files'])}),flush=True)
        for number,(relative,entry) in enumerate(snapshot['files'].items(),1):
            key=prefix+'/blobs/'+entry['sha256']
            if key not in verified:
                try:client.head_object(Bucket=bucket,Key=key)
                except Exception as exc:
                    if not missing(exc):raise
                    client.upload_file(Filename=str(local_file(root,workspace,relative)),Bucket=bucket,Key=key)
                verify_remote(client,bucket,key,entry['sha256'],entry['bytes']);verified.add(key)
            if number%50==0:print(json.dumps({'workspace':name,'files_verified':number}),flush=True)
        payload=encoded(snapshot);digest=hashlib.sha256(payload).hexdigest()
        key=prefix+'/manifests/'+name+'/'+digest+'.json'
        client.put_object(Bucket=bucket,Key=key,Body=payload)
        verify_remote(client,bucket,key,digest,len(payload))
        # Detect additions, edits or deletions while uploading. Never prune a
        # changed workspace based on an earlier snapshot, even with a held lock.
        if inventory(root,workspace,associated=associated)!=snapshot:raise ValueError('Local snapshot changed during upload; local files retained')
        catalog_path=root/'results/offload/catalog.json'
        catalog=json.loads(catalog_path.read_text()) if catalog_path.exists() else {'version':1,'snapshots':[]}
        receipt={'workspace':name,'repo':config['repo'],'prefix':prefix,'manifest_key':key,'manifest_sha256':digest,
                 'manifest_bytes':len(payload),'verified_at':datetime.now(timezone.utc).isoformat(),
                 'runtime_bytes':sum(e['bytes'] for p,e in snapshot['files'].items() if p.startswith('workspace/')),
                 'local_removed':False,'recorded_run_ids':snapshot['recorded_run_ids']}
        catalog['snapshots'].append(receipt);save(catalog_path,catalog)
        if prune_local:
            # Explicit user flag only. Results, source datasets, case manifests
            # and the restoration catalog are outside this removal target.
            shutil.rmtree(workspace)
            receipt['local_removed']=True;save(catalog_path,catalog)
        return receipt

def read_manifest(client,receipt):
    body=client.get_object(Bucket=receipt['repo'].split('/')[1],Key=receipt['manifest_key'])['Body']
    try:payload=body.read(16*1024*1024+1)
    finally:body.close()
    if len(payload)>16*1024*1024 or hashlib.sha256(payload).hexdigest()!=receipt['manifest_sha256']:
        raise ValueError('Restore manifest checksum failed')
    return json.loads(payload)

def restore(root,receipt,client):
    snapshot=read_manifest(client,receipt);name=snapshot['workspace']
    if not WORKSPACE.fullmatch(name) or name!=receipt['workspace']:raise ValueError('Invalid restoration workspace')
    if 'workspace/owner.json' not in snapshot['files']:raise ValueError('Restore manifest has no workspace ownership marker')
    target=root/'benchmarks/runtime'/name
    if target.exists() or target.is_symlink():raise ValueError('Restore target already exists; it will not be overwritten')
    required=sum(e['bytes'] for e in snapshot['files'].values())+256*1024*1024
    if shutil.disk_usage(root).free<required:raise ValueError('Insufficient space for this workspace restoration')
    scratch=root/'.offload';scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='restore-',dir=scratch) as folder:
        stage=Path(folder);bucket=receipt['repo'].split('/')[1]
        for relative,entry in snapshot['files'].items():
            # Validate before joining, and only create plain regular files.
            local_file(root,target,relative)
            destination=stage.joinpath(*PurePosixPath(relative).parts);destination.parent.mkdir(parents=True,exist_ok=True)
            body=client.get_object(Bucket=bucket,Key=receipt['prefix']+'/blobs/'+entry['sha256'])['Body']
            h=hashlib.sha256();size=0
            try:
                with destination.open('xb') as stream:
                    for chunk in iter(lambda:body.read(1024*1024),b''):h.update(chunk);size+=len(chunk);stream.write(chunk)
            finally:body.close()
            if h.hexdigest()!=entry['sha256'] or size!=entry['bytes']:raise ValueError('Restored file checksum failed: '+relative)
            destination.chmod(entry['mode']&0o777)
        # Check all conflicts before publishing any restored result files.
        for relative,entry in snapshot['files'].items():
            if relative.startswith('records/'):
                destination=local_file(root,target,relative)
                if destination.exists() and (destination.is_symlink() or sha(destination)!=entry['sha256']):
                    raise ValueError('Existing result record differs; nothing overwritten: '+str(destination))
        for relative in snapshot['files']:
            if relative.startswith('records/'):
                destination=local_file(root,target,relative)
                if not destination.exists():
                    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(stage/relative,destination)
        target.parent.mkdir(parents=True,exist_ok=True)
        (stage/'workspace').rename(target)
    return {'restored_workspace':str(target),'manifest_sha256':receipt['manifest_sha256']}

def client_for(repo):
    from dagshub import get_repo_bucket_client
    from dagshub.common.api.repo import RepoAPI
    if RepoAPI(repo).get_repo_info().private is not True:
        raise ValueError('Use a private DagsHub repository for complete runtime archives')
    return get_repo_bucket_client(repo,flavor='boto')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    sub=parser.add_subparsers(dest='command',required=True)
    configure=sub.add_parser('configure');configure.add_argument('--repo',required=True)
    configure.add_argument('--prefix',default='biodemo-archives/v1')
    for action in ('plan','upload'):
        command=sub.add_parser(action);command.add_argument('--include-unrecorded',action='store_true')
        command.add_argument('--workspace',action='append')
        if action=='upload':command.add_argument('--prune-local',action='store_true')
    command=sub.add_parser('restore');command.add_argument('--workspace',required=True)
    args=parser.parse_args();root=args.root.resolve();config_path=root/'.offload/config.json'
    operation=root/'.offload/operation.lock';operation.parent.mkdir(parents=True,exist_ok=True)
    with operation.open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.command=='configure':
            if not re.fullmatch(r'[\w.-]+/[\w.-]+',args.repo):raise ValueError('repo must be OWNER/REPOSITORY')
            prefix=PurePosixPath(args.prefix)
            if prefix.is_absolute() or '..' in prefix.parts or str(prefix)=='.':raise ValueError('Invalid bucket prefix')
            save(config_path,{'repo':args.repo,'prefix':prefix.as_posix()})
            print(json.dumps({'configured':str(config_path),'repo':args.repo,'uploaded':False}));return
        if args.command=='restore':
            catalog=json.loads((root/'results/offload/catalog.json').read_text())
            receipt=next(r for r in reversed(catalog['snapshots']) if r['workspace']==args.workspace)
            print(json.dumps(restore(root,receipt,client_for(receipt['repo']))));return
        selected=plan(root,args.include_unrecorded)
        if args.workspace:
            known={r['workspace'] for r in selected['workspaces']}
            if set(args.workspace)-known:raise ValueError('Requested workspace not found')
            selected['workspaces']=[r for r in selected['workspaces'] if r['workspace'] in args.workspace]
            selected['eligible_runtime_bytes']=sum(r.get('runtime_bytes',0) for r in selected['workspaces'] if r['status']=='eligible')
        save(root/'results/offload/plan.json',selected)
        if args.command=='plan':print(json.dumps(selected,indent=2));return
        config=json.loads(config_path.read_text());client=client_for(config['repo']);verified=set()
        for row in selected['workspaces']:
            if row['status']!='eligible':print(json.dumps({'skipped':row}),flush=True);continue
            try:receipt=offload(root,row['workspace'],config,client,prune_local=args.prune_local,include_unrecorded=args.include_unrecorded,verified=verified,
                                associated=[root/'results/evaluation'/id for id in row['recorded_run_ids']])
            except BlockingIOError:print(json.dumps({'workspace':row['workspace'],'status':'active_skipped'}),flush=True);continue
            print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
