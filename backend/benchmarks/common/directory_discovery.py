"""Tool-driven deterministic retrieval baseline, not an AI investigator.

Only objective text and scoped tools are available here. No case labels or
generator imports. Source expansion tests the value of following retrieved links.
"""
from __future__ import annotations

import json
import re
import time
import resource
import sys
from pathlib import Path

from src.manufacturing_data import ManufacturingStore, ManufacturingTools, ingest_package


def run_directory(request):
    cfg = request.configuration; started = time.monotonic(); cpu_started = time.process_time()
    store = ManufacturingStore(Path(cfg['state_directory']) / 'store')
    coverage = ingest_package(request.input_package, store, access_scope='evaluation', document_backend='pypdf')
    tools = ManufacturingTools(store, as_of=request.as_of, scopes=('evaluation',))
    trace = [{'action': 'discover', 'path': route['path'], 'format_route': route.get('kind'),
              'backend': route.get('selected_backend')} for route in coverage['routes']]
    trace.extend({'action': 'extraction_failure', **error} for error in coverage['errors'])
    calls = 0

    def search(**args):
        nonlocal calls
        calls += 1
        response = tools.search_evidence(**args)
        trace.append({'action': 'retrieve', 'arguments': args,
                      'evidence_ids': response.get('evidence_ids', []),
                      'paths': sorted({(json.loads(r['source_ref']) if isinstance(r['source_ref'], str) else r['source_ref'])['path']
                                       for r in response.get('records', [])})})
        return response.get('records', [])

    # Identifiers are extracted from the user's objective, not evaluator config.
    identifiers = re.findall(r'\b[A-Z]{1,6}-[A-Z0-9]{4,}\b', request.objective)
    query = identifiers[0].split('-', 1)[-1] if identifiers else request.objective
    diversity = {'max_hits_per_source': 1} if cfg['mode'] == 'linked_rules' else {}
    hits = search(query=query, evidence_type='narrative', limit=cfg.get('retrieval_limit', 24), **diversity)
    if identifiers:
        hits += search(query=identifiers[0], entity_id=identifiers[0], evidence_type='structured', limit=100)
    sources = {s['id']: s for s in store.visible_sources(as_of=request.as_of, scopes=('evaluation',))}
    rows = {r['id']: r for r in hits}; inspected = set()
    if cfg['mode'] == 'linked_rules':
        for sid in dict.fromkeys(r['source_id'] for r in hits):
            if calls >= cfg.get('budgets', {}).get('tool_calls', 48): break
            # All fields are inspected; structured numerical data stays in Parquet.
            expanded = search(query='', source_id=sid, evidence_type='structured', limit=1000)
            rows.update((r['id'], r) for r in expanded); inspected.add(sources[sid]['path'])
            trace.append({'action': 'inspect', 'path': sources[sid]['path'], 'reason': 'shares objective identifier'})
    citations = []; seen = set(); findings = []; counter = []; scope = set()
    for row in rows.values():
        source = sources[row['source_id']]
        ref = json.loads(row['source_ref']) if isinstance(row['source_ref'], str) else row['source_ref']
        text = row.get('value_text') or ''
        # Content identity, not filename count, controls repeated evidence support.
        identity = (source['sha256'], row['name'], ref.get('row'), ref.get('column'), ref.get('page'), ref.get('span'))
        if identity in seen: continue
        seen.add(identity)
        citations.append({'evidence_id': row['id'], 'source': ref, 'text': text,
                          'available_at': row.get('available_at'), 'name': row['name']})
        if row['name'] == 'record_note' or 'record_note:' in text or '"record_note"' in text:
            findings.append({'observation': text, 'evidence_id': row['id']})
            if re.search(r'contradict|unsupported|not reproduc|did not reproduc|independent check|comparator', text, re.I):
                counter.append(row['id'])
        if row['name'] == 'associated_batches' or 'associated_batches' in text:
            scope.update(re.findall(r'\bB-[A-Z0-9]+\b', text))
    discovered = sorted({c['source']['path'] for c in citations})
    for source in sources.values():
        if source['path'] not in discovered:
            trace.append({'action': 'deprioritize', 'path': source['path'],
                          'reason': 'not returned within objective-specific search budget; relevance remains unknown'})
    return {'mode': cfg['mode'], 'status': 'completed', 'objective': request.objective,
            'ingestion': coverage, 'citations': citations, 'discovered_files': discovered,
            'deeply_inspected_files': sorted(inspected), 'trace': trace,
            'analysis': {'findings': findings, 'counterevidence': counter,
                         'affected_batches': sorted(scope), 'hypotheses': [], 'causal_status': 'not_established',
                         'missing_information': ['Causal interpretation requires an investigator; these are retrieved observations.'],
                         'recommendations': ['QA/MSAT review of cited records and discriminating controlled tests.']},
            'usage': {'tool_calls': calls, 'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0,
                      'api_cost_usd': 0, 'wall_seconds': time.monotonic() - started},
            'compute': {'cpu_seconds': time.process_time() - cpu_started,
                        'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
                        'scope': 'worker process high-water RSS; excludes OS file cache and other processes',
                        'compute_cost_usd': None},
            'limitations': ['Deterministic retrieval baseline; no autonomous causal reasoning or calibrated confidence.']}
