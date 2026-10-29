"""Publish only completed-run receipts and authorized cited source bytes.

Never export evaluator manifests or future sources. The UI is a measured-run
viewer, not a replacement agent runtime or source of synthetic live responses.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from .generate import digest, save


def export(results, corpus, output, indpensim=None, simulator=None):
    from contextlib import ExitStack
    from benchmarks.common.artifact_store import asset_path
    with ExitStack() as stack:
        resolved_results=[stack.enter_context(asset_path(path)) for path in results]
        resolved_corpus=stack.enter_context(asset_path(corpus))
        historical=stack.enter_context(asset_path(indpensim)) if indpensim else None
        gate=stack.enter_context(asset_path(simulator)) if simulator else None
        return _export(resolved_results, resolved_corpus, output, historical, gate)


def _export(results, corpus, output, indpensim=None, simulator=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    corpus = Path(corpus)
    runs = []; detail = {}
    for directory in results:
        directory = Path(directory)
        summary = json.loads((directory / 'summary.json').read_text())
        for result in summary['results']:
            run_id = f"{summary['source_manifest']['files']}-{directory.name}-{result['case']}-{result['mode']}"
            public = {k: v for k, v in result.items() if k != 'retained_workspace'}
            public.update(id=run_id, corpus_files=summary['source_manifest']['files'],
                          corpus_version=summary['source_manifest']['version'], corpus_sha256=summary['source_manifest']['corpus_sha256'])
            if result.get('partial_ingestion_snapshot') and 'wall-clock' in result.get('error', ''):
                progress = result['partial_ingestion_snapshot']
                public['failure_reason'] = (f"Worker timed out; {progress.get('indexed', 0):,} indexed, "
                    f"{progress.get('pending', 0)} pending, {progress.get('error', 0)} corrupt and "
                    f"{progress.get('preserved_unsupported', 0)} unsupported sources at termination. Investigation scores withheld.")
            for log in (directory / f"{result['case']}-{result['mode']}" / 'runtime-artifacts').glob('*.stderr'):
                if 'insufficient balance' in log.read_text(errors='replace').lower():
                    public['failure_reason'] = 'Configured Prime provider returned HTTP 402 insufficient balance; no investigation completed.'
            runs.append(public)
            report_path = directory / f"{result['case']}-{result['mode']}" / 'investigation.json'
            manifest_path = report_path.with_name('run.json')
            if not report_path.exists(): continue
            report = json.loads(report_path.read_text()); receipt = json.loads(manifest_path.read_text())
            if receipt['source_manifest']['corpus_sha256'] != json.loads((corpus / 'manifest.json').read_text())['corpus_sha256']:
                continue  # Summaries can compare corpora; source drill-down requires a matching corpus.
            allowlist = {f['path']: f for f in receipt['allowlist']}
            source_links = []
            for rel, entry in allowlist.items():
                source = (corpus / 'raw' / rel).resolve()
                if not source.is_relative_to((corpus / 'raw').resolve()) or digest(source) != entry['sha256']:
                    raise ValueError('source path escaped or bytes changed after run')
                name = entry['sha256'] + source.suffix
                (output / 'sources').mkdir(exist_ok=True)
                target = output / 'sources' / name
                if not target.exists(): shutil.copyfile(source, target)
                source_links.append({**entry, 'source_url': '/case-study-results/sources/' + name})
            for citation in report.get('citations', []):
                ref = citation.get('source', {}); rel = ref.get('path')
                if rel not in allowlist: raise ValueError('citation outside historical allowlist')
                source = (corpus / 'raw' / rel).resolve()
                if not source.is_relative_to((corpus / 'raw').resolve()): raise ValueError('source escapes corpus')
                if digest(source) != allowlist[rel]['sha256']: raise ValueError('source changed after run')
                name = allowlist[rel]['sha256'] + source.suffix
                (output / 'sources').mkdir(exist_ok=True)
                target = output / 'sources' / name
                if not target.exists(): shutil.copyfile(source, target)
                citation['source_url'] = '/case-study-results/sources/' + name
            detail[run_id] = {'objective': report['objective'], 'analysis': report.get('analysis', {}),
                              'citations': report.get('citations', []), 'trace': report.get('trace', []),
                              'ingestion': report.get('ingestion', {}), 'sources': source_links,
                              'cutoff': receipt['cutoff'], 'isolation_audit': report.get('isolation_audit'),
                              'source_package_sha256': hashlib.sha256(json.dumps(sorted((f['path'], f['sha256']) for f in receipt['allowlist']), separators=(',', ':')).encode()).hexdigest()}
    historical = json.loads(Path(indpensim).read_text()) if indpensim else None
    if historical:
        comparisons = historical.get('queries', {})
        historical = {k: v for k, v in historical.items() if k != 'queries'}
        historical['batch_comparisons'] = comparisons
        historical['ingestion'] = {k: v for k, v in historical['ingestion'].items() if k != 'routes'}
    data = {'disclosure': 'Fictional operational evidence; FDA historical context is separate. Rules are not Prime Agent results.',
            'runs': runs, 'details': detail, 'indpensim': historical,
            'simulator': json.loads(Path(simulator).read_text()) if simulator else None}
    save(output / 'report.json', data)
    return output / 'report.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--results', nargs='+', required=True)
    parser.add_argument('--corpus', required=True); parser.add_argument('--output', required=True)
    parser.add_argument('--indpensim'); parser.add_argument('--simulator'); args = parser.parse_args()
    print(export(args.results, args.corpus, args.output, args.indpensim, args.simulator))
