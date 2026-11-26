"""Bounded, opt-in live checks on isolated synthetic demo workspaces.

Never loads database or storage credentials. Live runs use the production tool
loop with the requested provider/model and retain its actual qualification status.
This is a product smoke check, not scientific or customer validation.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--credentials-file', type=Path, required=True)
    parser.add_argument('--provider', choices=['modal', 'anthropic', 'openai'], required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--base-url')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--all-scenarios', action='store_true')
    group.add_argument('--existing-scenarios', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Use a new output directory to preserve prior execution records')
    args.output.mkdir(parents=True)
    # Read only model credentials; never source a shell file or load production databases.
    allowed = {'MODAL_PROXY_TOKEN', 'BIODEMO_MODAL_PROXY_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'}
    for line in args.credentials_file.read_text().splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and key in allowed and not os.environ.get(key):
            os.environ[key] = value.strip().strip('"').strip("'")
    os.environ.update(LIFESCI_LLM_PROVIDER=args.provider, LIFESCI_LLM_MODEL=args.model,
                      ASSISTANT_LOOP='tools', MODAL_EMBEDDINGS_URL='')
    if args.base_url:
        os.environ['MODAL_BASE_URL' if args.provider == 'modal' else args.provider.upper() + '_BASE_URL'] = args.base_url
    from src.lifesci.container import Platform
    from src.lifesci.demo_scenarios import PERSONAS, for_persona
    from src.lifesci.store import RecordStore

    def check(persona):
        p = Platform(RecordStore(str(args.output / (persona + '.sqlite'))), allow_unqualified=True)
        outputs = []
        try:
            actor = 'readiness-' + persona
            workspace = p.demo.provision(actor, persona, True)
            ctx = p.identity.context_for(workspace['tenant_id'], actor)
            service = p.engineering_conversations
            scenarios = for_persona(persona)
            if args.existing_scenarios:
                scenarios = [s for s in scenarios if not s['scenario_id'].endswith('model-library')]
            elif not args.all_scenarios:
                scenarios = [s for s in scenarios if s['scenario_id'].endswith('model-library')]
            for scenario in scenarios:
                started = time.monotonic()
                thread = service.create(ctx, {'site_id': 'NF1'})
                queued = service.enqueue(ctx, thread['id'], {'text': scenario['prompt'], 'expected_revision': thread['revision']})
                service.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
                view = service.get(ctx, thread['id'])
                turn = view['turns'][-1]
                results = [r.state for r in p.store.read().list(ctx.tenant_id, 'physical_analysis_result')
                           if any(a.get('id') == r.id for a in turn.get('artifacts', []))]
                library = scenario['scenario_id'].endswith('model-library')
                expected = 'fermentation.oxygen_transfer' if persona == 'msat' else 'chemical.parallel_batch'
                numerical = any(r.get('execution_status') == 'completed' and r.get('spec', {}).get('model_id') == expected
                                for r in results)
                # Persist actual records for review; never emit provider credentials/headers.
                record = {'persona': persona, 'scenario_id': scenario['scenario_id'], 'status': turn['status'],
                          'seconds': round(time.monotonic() - started, 2), 'solver_calls': turn.get('solver_calls_used'),
                          'issues': turn.get('issues'), 'reply': turn.get('reply'),
                          'steps': turn.get('steps'), 'gateway_runs': turn.get('gateway_runs'),
                          'numeric_execution': numerical, 'demo_enabled': view['demo_enabled'],
                          'pass': turn['status'] == 'completed' and (numerical if library else bool(turn.get('reply')))}
                # model manifests use model_id in some persisted formats; verify exact spec too.
                if library and not numerical:
                    numerical = any(r.get('execution_status') == 'completed' and r.get('spec', {}).get('model_id') == expected for r in results)
                    record.update(numeric_execution=numerical, **{'pass': turn['status'] == 'completed' and numerical})
                (args.output / (scenario['scenario_id'] + '.json')).write_text(json.dumps(record, indent=2, default=str))
                outputs.append({k:record[k] for k in ('persona','scenario_id','status','seconds','solver_calls','numeric_execution','pass')})
                print(json.dumps(outputs[-1]), flush=True)
        finally:
            p.runtime.close()
            p.store.release_connections()
        return outputs

    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(check, persona) for persona in PERSONAS]):
            records.extend(future.result())
    summary = {'provider': args.provider, 'requested_model': args.model, 'synthetic': True,
               'live_inference': True, 'checks': sorted(records, key=lambda x:x['scenario_id']),
               'passed': sum(r['pass'] for r in records), 'total': len(records)}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({'passed':summary['passed'], 'total':summary['total']}), flush=True)
    raise SystemExit(0 if summary['passed'] == summary['total'] else 1)


if __name__ == '__main__':
    main()
