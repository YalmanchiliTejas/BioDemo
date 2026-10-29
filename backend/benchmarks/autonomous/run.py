"""Freeze source availability, execute existing isolated worker, score afterwards."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import time
import platform
import sys
from contextlib import nullcontext
from pathlib import Path

from benchmarks.common.isolated_runner import run_isolated
from .generate import CUTOFF, VERSION, digest, save


def score(output, question, truth):
    citations = output.get('citations', [])
    refs = []
    for citation in citations:
        ref = citation.get('source', {})
        if isinstance(ref, str): ref = json.loads(ref)
        refs.append((ref.get('path'), citation.get('text', ''), ref))
    critical = [x for x in question['critical'] if x['kind'] != 'future']
    relevant = {c['path'] for c in critical}; discovered = {p for p, _, _ in refs}
    # File discovery and exact span coverage are separate: merely finding a file
    # does not establish that the critical observation was actually inspected.
    def coordinate(ref):
        return (ref.get('page') or 0, *(int(x) for x in re.findall(r'\d+', ref.get('span') or '0')))
    joined = {path: ' '.join(text for _, text, ref in sorted(
        [r for r in refs if r[0] == path], key=lambda r: coordinate(r[2]))) for path, _, _ in refs}
    normalize = lambda text: re.sub(r'\s+', ' ', text).strip()
    covered = [c for c in critical if normalize(c['span']) in normalize(joined.get(c['path'], ''))]
    future = {f['path'] for f in truth['files'] if f['available_at'] > CUTOFF}
    valid = {f['path'] for f in truth['files'] if f['available_at'] <= CUTOFF}
    scope = set(output.get('analysis', {}).get('affected_batches', [])); expected = set(question['affected_batches'])
    ingested = output.get('ingestion', {}); files = ingested.get('files_seen', 0)
    analysis = output.get('analysis', {})
    hypotheses = analysis.get('hypotheses', [])
    statements = ' '.join(h if isinstance(h, str) else h.get('statement', '') for h in hypotheses).lower()
    claims = analysis.get('claims', [])
    unsupported = [c for c in [*claims, *[h for h in hypotheses if isinstance(h, dict)]]
                   if c.get('classification') in {'verified_cause', 'root_cause'}
                   or c.get('status') in {'verified', 'verified_root_cause', 'established_cause'}]
    def ratio(n, d): return n / d if d else None
    ranked_paths = list(dict.fromkeys(p for p, _, _ in refs))
    relevant_ranks = [i for i, path in enumerate(ranked_paths, 1) if path in relevant]
    average_precision = sum(j / rank for j, rank in enumerate(relevant_ranks, 1)) / len(relevant) if relevant else None
    return {'critical_file_recall': ratio(len(relevant & discovered), len(relevant)),
            'critical_span_recall': ratio(len(covered), len(critical)),
            'source_average_precision': average_precision,
            'critical_spans_per_tool_call': ratio(len(covered), output.get('usage', {}).get('tool_calls', 0)),
            'critical_spans_per_api_dollar': None,
            'per_dollar_status': 'undefined for no-API baselines; actual agent API spend unmeasured',
            'retrieved_file_precision': ratio(len(relevant & discovered), len(discovered)),
            'counterevidence_recall': ratio(sum(c['kind'] == 'counter' for c in covered), sum(c['kind'] == 'counter' for c in critical)),
            'critical_files_missed': sorted(relevant - discovered),
            'irrelevant_files_deeply_inspected': len(set(output.get('deeply_inspected_files', [])) - relevant),
            'affected_run_precision': ratio(len(scope & expected), len(scope)),
            'affected_run_recall': ratio(len(scope & expected), len(expected)),
            'citation_source_validity': ratio(sum(p in valid for p, _, _ in refs), len(refs)),
            'provenance_completeness': ratio(sum(bool(r.get('span') or r.get('row') or r.get('cell')) for _, _, r in refs), len(refs)),
            'future_information_citations': len(discovered & future),
            'ingestion_completion_rate': ratio(ingested.get('files_indexed', 0), files),
            'ingestion_errors': len(ingested.get('errors', [])),
            'unsupported_files': ingested.get('files_preserved_unsupported', 0),
            'hypothesis_coverage': ratio(sum(x.lower() in statements for x in question.get('contributors', [])), len(question.get('contributors', []))),
            'hypothesis_scoring_method': 'exact contributor phrase in hypothesis; semantic/scientific adequacy not evaluated',
            'unsupported_causal_claims': len(unsupported),
            'causal_scoring_method': 'structured assertions of established causality; free-prose causal overstatement requires blinded review',
            'correct_abstention': (not unsupported and analysis.get('causal_status') == 'not_established') if question.get('inconclusive') else None,
            'extraction_accuracy': 'not_evaluated',
            'parsed_unit_accuracy': 'not_evaluated', 'cross_document_link_accuracy': 'not_evaluated'}


def run(corpus, destination, modes=('keyword_rules', 'linked_rules'), questions=None, seconds=180, retain_workspace=False):
    from benchmarks.common.artifact_store import asset_path
    with asset_path(corpus) as local:
        return _run(local, destination, modes, questions, seconds, retain_workspace)


def _run(corpus, destination, modes=('keyword_rules', 'linked_rules'), questions=None, seconds=180, retain_workspace=False):
    corpus = Path(corpus).resolve(); destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()): raise ValueError('results destination must be empty')
    destination.mkdir(parents=True, exist_ok=True)
    truth_path = corpus / 'evaluator/truth.json'; truth = json.loads(truth_path.read_text())
    manifest = json.loads((corpus / 'manifest.json').read_text())
    results = []
    root = Path(__file__).resolve().parents[2]
    version_paths = ['src/manufacturing_data/ingest.py', 'src/manufacturing_data/retrieval.py',
                     'src/manufacturing_data/tools.py', 'src/prime_runtime/harness.py',
                     'src/prime_runtime/sdk_runner.mjs', 'src/prime_runtime/system_prompt.md',
                     'prime_skills/manufacturing_os/SKILL.md', 'benchmarks/common/directory_discovery.py']
    code_versions = {name: digest(root / name) for name in version_paths}
    rubric_version = digest(__file__)
    for question in truth['questions']:
        if questions and question['id'] not in questions: continue
        for mode in modes:
            tag = f"{question['id']}-{mode}"; started = time.monotonic()
            outdir = destination / tag; outdir.mkdir()
            context = (nullcontext(tempfile.mkdtemp(prefix='benchmark-case-')) if retain_workspace
                       else tempfile.TemporaryDirectory(prefix='benchmark-case-'))
            with context as temporary:
                work = Path(temporary); package = work / 'agent_input'; package.mkdir()
                allowlist = []
                # Availability is public source metadata, never relevance. Stage
                # every eligible file, including unrelated/corrupt/unsupported ones.
                for source in sorted((corpus / 'raw').rglob('*')):
                    if not source.is_file(): continue
                    from datetime import datetime, timezone
                    available = datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat()
                    if available > manifest['cutoff']: continue
                    rel = source.relative_to(corpus / 'raw'); target = package / rel
                    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
                    allowlist.append({'path': str(rel), 'sha256': digest(target), 'available_at': available})
                cfg = {'mode': 'full_rlm' if mode == 'bounded_agent' else mode,
                       'rlm_max_depth': 0 if mode == 'bounded_agent' else None,
                       'case_id': question['id'], 'run_id': tag, 'state_directory': str(work / 'state'),
                       'artifact_directory': str(work / 'runtime-artifacts'), 'evaluation_time': CUTOFF,
                       'allow_partial_ingestion': True, 'document_backend': 'pypdf',
                       'budgets': {'wall_clock_seconds': seconds, 'tool_calls': 48},
                       'hidden_paths': [str(truth_path), str(corpus / 'manifest.json'), str(corpus / 'raw'),
                                        str(Path(__file__).parent)]}
                record = {'case': question['id'], 'mode': mode, 'status': 'failed', 'metrics': None}
                try:
                    output = run_isolated(package, question['objective'], CUTOFF, cfg)
                    save(outdir / 'investigation.json', output)
                    record.update(status='completed', metrics=score(output, question, truth), usage=output.get('usage'))
                except Exception as exc:
                    record.update(error=f'{type(exc).__name__}: {exc}',
                                  isolation_audit=getattr(exc, 'isolation_audit', None))
                    metadata = work / 'state/store/metadata.sqlite'
                    if metadata.exists():
                        import sqlite3
                        with sqlite3.connect(metadata) as connection:
                            record['partial_ingestion_snapshot'] = dict(connection.execute(
                                'SELECT extraction_status,count(*) FROM sources GROUP BY extraction_status').fetchall())
                if (work / 'runtime-artifacts').exists(): shutil.copytree(work / 'runtime-artifacts', outdir / 'runtime-artifacts')
                record['wall_seconds'] = time.monotonic() - started
                if retain_workspace:
                    from benchmarks.common.artifact_store import publish_path
                    record['retained_workspace'] = str(work)
                    try:
                        asset_id='retained-'+work.name
                        publish_path(work,asset_id,mount_path=str(work))
                        record['retained_workspace_artifact']='dagshub:'+asset_id
                    except Exception as error:
                        record['archive_error']=str(error)
                save(outdir / 'run.json', {'version': VERSION, 'source_manifest': manifest,
                                         'objective': question['objective'], 'cutoff': CUTOFF, 'allowlist': allowlist,
                                         'configuration': {k: v for k, v in cfg.items() if k != 'hidden_paths'},
                                         'generator_sha256': manifest.get('generator_sha256', 'unknown; legacy generation did not capture code hash'),
                                         'runner_sha256': rubric_version, 'code_versions': code_versions,
                                         'environment': {'python': sys.version, 'platform': platform.platform()},
                                         'model_configuration': 'Prime SDK configured default; actual model in runtime-artifacts' if mode in {'full_rlm', 'bounded_agent'} else 'existing OpenAI baseline default' if mode == 'directory_rag' else 'no model',
                                         'result': record})
                results.append(record)
                save(destination / 'summary.json', {'source_manifest': manifest, 'results': results})
                print(json.dumps(record), flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('corpus'); parser.add_argument('output')
    parser.add_argument('--modes', nargs='+', default=['keyword_rules', 'linked_rules'])
    parser.add_argument('--questions', nargs='+'); parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--retain-workspace', action='store_true', help='Retain the source store in DagsHub for API follow-up; no evaluator labels.')
    args = parser.parse_args(); run(args.corpus, args.output, args.modes, args.questions, args.seconds, args.retain_workspace)
