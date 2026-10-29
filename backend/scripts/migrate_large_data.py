"""Migrate known project datasets/collections, never environments or arbitrary tmp files."""
import argparse
import json
from pathlib import Path
import tempfile
import hashlib
from scripts.offload_benchmarks import sha

from scripts.data_artifacts import publish
from scripts.offload_benchmarks import ROOT, client_for, save, excluded


def candidates(only=None):
    items = [
        ('cho-raw', ROOT/'benchmarks/cho/raw'),
        ('cho-aligned-reference', ROOT/'benchmarks/cho/reference/aligned'),
        ('frozen-evaluation-assets', ROOT/'benchmarks/snapshots/pre-evaluation-v2/assets'),
        ('docling-models', ROOT/'.cache/cmo-docling-models'),
        ('legacy-demo-store', ROOT/'runs/demo-store'),
        ('design-original-perplex-30', ROOT.parent/'perplex-Image 30.png'),
    ]
    items += [('legacy-demo-map-'+p.parent.name,p)
              for p in (ROOT/'runs/demo-agent').glob('*/evaluation-only-source-map.json')
              if p.stat().st_size>5*1024*1024]
    store_roots=[]
    for path in sorted((ROOT/'results/cmo_ingestion').glob('**/stores'),key=lambda p:len(p.parts)):
        if any(parent in path.parents for parent in store_roots): continue
        store_roots.append(path)
        items.append(('cmo-stores-' + '-'.join(path.relative_to(ROOT/'results/cmo_ingestion').parts), path))
    primary = {'biodemo-autonomous-v2-100': 'case-synthetic-100',
               'biodemo-autonomous-nested-1000': 'case-synthetic-1000',
               'biodemo-autonomous-nested-10000': 'case-synthetic-10000',
               'biodemo-indpensim-historical': 'indpensim-historical',
               'biodemo-indpensim-investigation': 'indpensim-investigation',
               'biodemo-indpensim-simulator-results': 'indpensim-simulator-results'}
    for path in sorted(Path('/private/tmp').iterdir()):
        if path.is_dir() and not path.is_symlink() and (path.name.startswith('biodemo-autonomous-') or path.name in primary or path.name in {'repro-a','repro-b'}):
            items.append((primary.get(path.name, path.name), path))
    # Ownership evidence: only retained paths explicitly recorded by our completed runs.
    receipts = list((ROOT.parent/'docs/case_studies/results').glob('*.json'))
    receipts += list(Path('/private/tmp').glob('biodemo-autonomous-*/*/run.json'))
    seen = set()
    def paths(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'retained_workspace','workspace'} and isinstance(child, str): yield child
                else: yield from paths(child)
        elif isinstance(value, list):
            for child in value: yield from paths(child)
    for receipt in receipts:
        try: values = list(paths(json.loads(receipt.read_text())))
        except (ValueError, OSError): continue
        for value in values:
            path = Path(value).resolve()
            if path in seen or not path.name.startswith('benchmark-case-') or not path.is_relative_to(Path(tempfile.gettempdir()).resolve()): continue
            if not (path/'agent_input').is_dir(): continue
            seen.add(path); items.append((path.name, path))
    result = []
    for name, path in items:
        if only and name not in only: continue
        if not path.exists(): continue
        size=0
        for child in ([path] if path.is_file() else path.rglob('*')):
            try:
                relative=Path(path.name) if path.is_file() else child.relative_to(path)
                if child.is_file() and not child.is_symlink() and not excluded(relative): size+=child.stat().st_size
            except FileNotFoundError: pass  # Another verified migration may just have pruned it.
        if not size: continue
        result.append({'asset': name, 'source': str(path.resolve()), 'bytes': size,
                       'mount_path': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path.resolve())})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true'); parser.add_argument('--asset',action='append')
    parser.add_argument('--exclude',action='append',default=[])
    parser.add_argument('--large-results',action='store_true',help='Offload individual result payloads over 5 MiB; keep run metadata locally')
    parser.add_argument('--large-metadata',action='store_true',help='Offload large evaluator source maps as well')
    args=parser.parse_args(); plan=candidates(set(args.asset) if args.asset else None)
    plan=[entry for entry in plan if entry['asset'] not in args.exclude]
    if args.large_results or args.large_metadata:
        roots=[ROOT/'benchmarks/manifests',ROOT/'benchmarks/fresenius/ground_truth'] if args.large_metadata else [ROOT/'results']
        paths=sorted(p for base in roots for p in base.rglob('*') if p.is_file() and p.stat().st_size>5*1024*1024)
        if not args.execute: print(json.dumps([{'path':str(p),'bytes':p.stat().st_size} for p in paths],indent=2));return
        config=json.loads((ROOT/'.offload/config.json').read_text());client=client_for(config['repo'])
        for path in paths:
            identifier='result-'+sha(path)+'-'+hashlib.sha256(str(path.relative_to(ROOT)).encode()).hexdigest()[:12]
            # The original immutable run remains remote. Its metadata keeps reports/listing operational.
            metadata=json.loads(path.read_text()) if path.name=='run.json' else None
            result=publish(path,ROOT/'benchmarks/assets'/(identifier+'.json'),config,client,prune=True,mount_path=str(path.relative_to(ROOT)))
            if metadata is not None:
                metadata.pop('output',None)
                metadata.update(remote_payload='dagshub:'+identifier,remote_payload_sha256=result['sha256'])
                save(path,metadata)
                path.chmod(result['file_metadata']['mode'])
            print(json.dumps(result),flush=True)
        return
    save(ROOT/'results/offload/data-migration-plan.json', {'assets':plan,'bytes':sum(x['bytes'] for x in plan)})
    if not args.execute: print(json.dumps(plan,indent=2));return
    config=json.loads((ROOT/'.offload/config.json').read_text()); client=client_for(config['repo'])
    for entry in plan:
        if not Path(entry['source']).exists(): continue
        print(json.dumps({'uploading':entry['asset'],'source_bytes':entry['bytes']}),flush=True)
        result=publish(entry['source'],ROOT/'benchmarks/assets'/(entry['asset']+'.json'),config,client,prune=True,mount_path=entry['mount_path'])
        print(json.dumps(result),flush=True)


if __name__=='__main__': main()
