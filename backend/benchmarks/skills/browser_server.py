"""Isolated, persistent real API for the browser journey; no mocked API or model responses.

Run from repository root with .venv/bin/python -I backend/benchmarks/skills/browser_server.py.
Only inference credentials are admitted from configuration files. Reference keys stay in
the output manifest and are never supplied to application services or model prompts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
MODEL = 'zai-org/GLM-5.3'
TENANT, ACTOR, SITE = 'demo-northfield', 'dev-msat', 'NF1'
PACKAGES = ('cho-calibration', 'cho-returning', 'cho-changed', 'cho-unseen')


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')


def configure(cache):
    from src.lifesci.envfile import parse_env
    allowed = {'MODAL_BASE_URL', 'MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_BASE_URL',
               'BIODEMO_MODAL_PROXY_TOKEN', 'MODAL_TIMEOUT_SECONDS', 'MODAL_MIN_MAX_TOKENS'}
    # Record names only: never retain production configuration outside this function.
    settings, configured_names = {}, set()
    for file in (BACKEND / 'deploy/aws/production.env', BACKEND / '.env.local'):
        if file.is_file():
            parsed = parse_env(file.read_text())
            configured_names.update(parsed)
            settings.update({k: v for k, v in parsed.items() if k in allowed and v})
    prefixes = ('CMO_', 'PHARMA_', 'LIFESCI_', 'SUPABASE_', 'AWS_', 'OIDC_', 'DEPLOYMENT_',
                'OPENAI_', 'ANTHROPIC_', 'MODAL_', 'BIODEMO_MODAL_', 'CLOUDFLARE_', 'ASSISTANT_')
    # Empty settings also prevent ingestion's setdefault-based .env.local loader
    # from restoring a configured database, object store, or unrecorded provider.
    for name in configured_names | set(os.environ):
        if name.startswith(prefixes):
            os.environ[name] = ''
    for name in ('CMO_DATABASE_URL', 'LIFESCI_DATABASE_URL', 'LIFESCI_MIGRATION_DATABASE_URL',
                 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_DB_URL', 'SUPABASE_ANON_KEY',
                 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'MODAL_EMBEDDINGS_URL'):
        os.environ[name] = ''
    os.environ.update(settings)
    os.environ.update({
        'LIFESCI_AUTH_MODE': 'development', 'LIFESCI_DEV_PASSWORD': 'sievance-local',
        'LIFESCI_CORS_ORIGINS': 'http://127.0.0.1:5197,http://localhost:5197',
        'LIFESCI_MULTI_TENANT': '1', 'LIFESCI_LLM_PROVIDER': 'modal', 'LIFESCI_LLM_MODEL': MODEL,
        'LIFESCI_INTERPRETER_REASONING_EFFORT': 'low', 'ASSISTANT_LOOP': 'tools',
        'CMO_HOSTED_INFERENCE_APPROVED': '0', 'CMO_REPOSITORY_ROOT': str(cache / 'repository'),
        'CMO_INGESTION_ROOT': str(cache / 'ingestion'),
        'CMO_DEMO_ROOT': str(BACKEND / 'benchmarks/cmo_ingestion/demo'),
        'CMO_PACKAGES_ROOT': str(cache / 'packages'),
        'LIFESCI_DATABASE_URL': 'sqlite:///' + str(cache / 'records.sqlite'),
    })
    # Empty AWS Lambda marker is still interpreted as false by the application.
    return settings


def prepare(p, cache, output):
    from src.lifesci import devaccounts
    from src.lifesci.organizations import OrganizationService
    from src.lifesci.cmo_datasets import share_provisional
    from src.manufacturing_data.cmo.pipeline import IngestionService
    from src.manufacturing_data.cmo.persistence import tenant_scope
    from src.manufacturing_data.cmo.quality import provisional_payload
    from benchmarks.workflow_trial.run import reference, expected_comparison
    demo = BACKEND / 'benchmarks/cmo_ingestion/demo'
    catalog = {row['id']: row for row in json.loads((demo / 'catalog.json').read_text())}
    devaccounts.ensure_seeded(p, OrganizationService(p.store, p.identity, ''))
    ctx = p.identity.context_for(TENANT, ACTOR)
    saved = cache / 'preparation.json'
    if saved.exists():
        manifest = json.loads(saved.read_text())
        write(output / 'data-manifest.json', manifest)
        return manifest
    deliveries, timings, cases, files = {}, {}, [], []
    with tenant_scope(TENANT):
        service = IngestionService(cache / 'ingestion')
        assert service.repo.backend == 'sqlite' and p.store.backend == 'sqlite'
        for package in PACKAGES:
            item = catalog[package]
            started = time.perf_counter()
            existing = [r for r in service.repo.runs() if r.get('package_id') == package and r['status'] == 'complete']
            run = existing[-1] if existing else service.run(demo / package / 'raw', item['cmo'],
                              'preview' if package == 'cho-calibration' else 'D',
                              synthetic=item['synthetic'], package_ref=package)
            if run['status'] != 'complete':
                raise RuntimeError(f'Ingestion failed for {package}: {run.get("error")}')
            run.update(package_id=package, delivery_name=item['name'], disclosure=item['disclosure'])
            service.repo.update_run(run['id'], package_id=package, delivery_name=item['name'],
                                    disclosure=item['disclosure'])
            if package == 'cho-calibration':
                confirmed = 0
                for layout in run['layouts']:
                    mapping = layout['mapping']
                    if mapping['columns'] and mapping['batch_column'] and mapping['time_column']:
                        service.confirm_template(run['id'], layout['fingerprint'], mapping,
                            'automated-browser-study-protocol',
                            'Public vocabulary draft confirmed by automated calibration protocol, not human review.',
                            origin='study_protocol')
                        confirmed += 1
            timings[package] = time.perf_counter() - started
            payload = provisional_payload(run)
            shared = share_provisional(p, ctx, payload, SITE)
            documents = [{'id': d['source_id'], 'path': d['path'], 'sha256': d['sha256']} for d in run['documents']]
            deliveries[package] = {'id': shared['evidence_id'], 'revision': shared['revision'],
                'run_id': run['id'], 'name': item['name'], 'disclosure': item['disclosure'],
                'review': payload['review'], 'values': len(payload['measurements']),
                'statuses': dict(Counter(m['status'] for m in payload['measurements'])), 'documents': documents,
                'reused_ingestion_after_launcher_restart': bool(existing)}
            print(f'Ingested {package}: {len(payload["measurements"])} provisional measurements', flush=True)
    # Evaluation-only keys are opened after ingestion and publication.
    for package in PACKAGES:
        key_path = demo / package / 'evaluation/answer_key.json'
        key = json.loads(key_path.read_text())
        for file in key['files']:
            path = demo / package / 'raw' / file['path']
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != file['sha256']:
                raise ValueError(f'Source hash mismatch in {package}')
            files.append({'package': package, 'path': str(path.relative_to(ROOT)), 'sha256': digest})
        if package == 'cho-calibration':
            continue
        ref = reference(key)
        left, right = ref['batches'][:2]
        for parameter in ('glucose', 'viable_cell_density'):
            cases.append({'id': f'{package}:{parameter}', 'package': package, 'parameter': parameter,
                'left': left, 'right': right, 'unit': ref['units'][parameter],
                'expected': expected_comparison(ref, parameter, left, right),
                'conflict_expected': any(c[1] == parameter and c[0] in (left, right) for c in ref['conflicts'])})
    manifest = {'tenant_id': TENANT, 'actor_id': ACTOR, 'site_id': SITE, 'deliveries': deliveries,
                'cases': cases, 'source_files': files, 'calibration_templates_confirmed_by_protocol': confirmed,
                'ingestion_seconds': timings, 'ingestion_model_calls': 0,
                'disclosure': catalog['cho-returning']['disclosure'],
                'reference_boundary': 'Expected values exist only in this evaluator artifact, never application prompts.'}
    write(saved, manifest)
    write(output / 'data-manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8147)
    parser.add_argument('--output', type=Path, default=BACKEND / 'results/browser-journey-20261115')
    args = parser.parse_args()
    cache = BACKEND / '.cache/skill-benchmarks/browser-journey-20261115'
    cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    settings = configure(cache)
    from benchmarks.agent_pilot.runner import RecordedProvider, CampaignBudget
    from src.lifesci.container import Platform
    from src.lifesci.store import RecordStore
    from src.lifesci.api import create_app
    from src.lifesci.gateway.configuration import INTERPRETER_PROVIDER
    import uvicorn
    budget = CampaignBudget(2.0, 20, receipt_dir=args.output / 'backend-request-receipts')
    # Preserve prior request admissions on a server restart within this campaign.
    budget.records = [json.loads(path.read_text()) for path in sorted((args.output / 'backend-request-receipts').glob('request-*.json'))]
    deadline = time.monotonic() + 7200
    provider = RecordedProvider(settings, budget, 'browser-journey-assistant', deadline)
    provider._check_configuration()
    interpreter = RecordedProvider({**settings, 'MODAL_COMPLETION_REASONING_EFFORT': 'low',
        'MODAL_COMPLETION_JSON': '1'}, budget, 'browser-journey-explanation', deadline)
    p = Platform(RecordStore(os.environ['LIFESCI_DATABASE_URL']),
                 providers={'modal': provider, INTERPRETER_PROVIDER: interpreter}, allow_unqualified=True)
    p.gateway.max_retries = 0
    manifest = prepare(p, cache, args.output)
    app = create_app(p)
    source_paths = [Path(__file__), ROOT / 'Main_Culture_andETHOS.md',
                    *sorted((BACKEND / 'src/lifesci').rglob('*.py')),
                    *sorted((BACKEND / 'src/manufacturing_data/cmo').rglob('*.py'))]
    protocol = {'started_at': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(),
        'api': f'http://127.0.0.1:{args.port}', 'tenant_id': TENANT, 'actor_id': ACTOR, 'site_id': SITE,
        'account': 'msat@sievance.local', 'auth': 'built-in development session; local synthetic organization',
        'database': str(cache / 'records.sqlite'), 'ingestion_root': str(cache / 'ingestion'),
        'model': MODEL, 'interpreter_reasoning_effort': 'low', 'estimated_budget_usd': 2.0,
        'hard_request_limit': 20, 'model_route': 'development unqualified route explicitly enabled; not a qualification claim',
        'network': 'localhost API; only recorded optional model inference can use external services',
        'mocks': False, 'runtime': 'actual application background runtime; no external connectors or scheduled responsibilities seeded',
        'source_hashes': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
        'prepared_deliveries': len(manifest['deliveries'])}
    write(args.output / 'backend-protocol.json', protocol)
    print(f'BACKEND_READY {protocol["api"]} actor={ACTOR} tenant={TENANT} site={SITE}', flush=True)
    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='info')
    finally:
        write(args.output / 'backend-budget.json', budget.snapshot())
        p.store.release_connections()


if __name__ == '__main__':
    main()
