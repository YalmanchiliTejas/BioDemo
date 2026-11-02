"""Opt-in real GLM check of workspace investigation and event-driven follow-up.

Uses an isolated synthetic tenant, never the production database. This is a
functional check, not a manufacturing accuracy benchmark or route qualification.
"""
import argparse
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'backend'))
from verify_engineering_chat_live import RecordedModal
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.envfile import parse_env
from src.lifesci.store import RecordStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Allow at most six real Modal requests')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.execute or args.output.exists():
        parser.error('Require --execute and a fresh output directory')
    settings = {}
    for path in (REPO / 'backend/deploy/aws/production.env', REPO / 'backend/.env.local'):
        if path.is_file():
            settings.update(parse_env(path.read_text()))
    settings.update(os.environ)
    os.environ['LIFESCI_LLM_PROVIDER'] = 'modal'
    os.environ['LIFESCI_LLM_MODEL'] = 'zai-org/GLM-5.3'
    provider = RecordedModal(settings, limit=6)
    provider._check_configuration()
    p = Platform(RecordStore(), providers={'modal': provider}, allow_unqualified=True)
    p.gateway.max_retries = 0
    seed(p)
    ctx = p.identity.context_for(TENANT, 'priya')
    p.cases.open(ctx, 'SYNTHETIC-DEV-OLD', 'priya', 'quinn', 'NF1')
    p.cases.open(ctx, 'SYNTHETIC-DEV-NEW', 'priya', 'quinn', 'NF1')
    source = p.evidence.ingest(ctx, source_system='SYNTHETIC-MES', source_record_id='pressure-alarm',
        content=b'Observed pressure alarm at 10:30 UTC. Sensor bias and a valve issue are competing untested hypotheses. No root cause has been confirmed. Calibration verification is pending.',
        media_type='text/plain', site_id='NF1', event_time='2026-11-02T10:30:00Z', metadata={'synthetic': True})
    p.cases.add_timeline_event(ctx, 'SYNTHETIC-DEV-NEW', '2026-11-02T10:30:00Z',
        'Synthetic pressure alarm. Cause unconfirmed; inspect the linked MES evidence.',
        [{'kind': 'evidence', 'id': source['evidence_id'], 'revision': source['revision'], 'site_id': 'NF1'}])
    thread = p.engineering_conversations.create(ctx, {})
    queued = p.engineering_conversations.enqueue(ctx, thread['id'], {'expected_revision': thread['revision'],
        'text': 'Which is the latest deviation and why did it happen? Search the workspace, inspect the newest case and its source evidence, and distinguish observations from hypotheses. State the ordering basis. Do not run simulations or create actions.'})
    result = p.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
    turn = result['turns'][-1]
    inspected = [p.engineering_conversations.artifact(ctx, thread['id'], a['kind'], a['id'])
                 for a in turn['artifacts'] if a['kind'] == 'assistant_workspace_result']
    ids = {a.get('record', {}).get('id') for a in inspected}
    investigation_ok = (turn['status'] in ('completed', 'needs_information') and 'SYNTHETIC-DEV-NEW' in ids
                        and source['evidence_id'] in ids and 'SYNTHETIC-DEV-NEW' in (turn['reply'] or ''))
    # Check actual background model execution with no second user message.
    first_requests = len(provider.posts)
    result = p.assistant_responsibilities.configure(ctx, thread['id'], {'enabled': True,
        'objective': 'Inspect newly opened synthetic deviation cases and summarize the documented observation and remaining uncertainty. No drafts or external actions.',
        'kinds': ['case'], 'max_runs': 1, 'expected_revision': result['revision'], 'acknowledge_inference': True})
    p.cases.open(ctx, 'SYNTHETIC-DEV-FOLLOWUP', 'priya', 'quinn', 'NF1')
    p.cases.add_timeline_event(ctx, 'SYNTHETIC-DEV-FOLLOWUP', '2026-11-02T11:30:00Z',
        'Synthetic fill-weight excursion observed. Root cause is unknown; scale verification is pending.')
    p.runtime.tick()
    result = p.engineering_conversations.get(ctx, thread['id'])
    background = result['turns'][-1]
    background_ok = background.get('origin') == 'background' and background['status'] in ('completed', 'needs_information') and len(provider.posts) > first_requests
    no_dispatch = not p.store.read().list(TENANT, 'action_intent')
    receipt = {'success': investigation_ok and background_ok and no_dispatch,
        'verification': 'local backend, real Modal endpoint, isolated synthetic records; not production or accuracy validation',
        'requested_model': 'zai-org/GLM-5.3', 'provider_requests': provider.posts,
        'investigation_completed': investigation_ok, 'background_completed': background_ok,
        'no_production_dispatch': no_dispatch, 'billing_coverage': 'Modal monetary billing unavailable',
        'initial_reply': turn['reply'], 'background_reply': background['reply'],
        'statuses': [t['status'] for t in result['turns']]}
    args.output.mkdir(parents=True)
    for name, value in [('receipt.json', receipt), ('conversation.json', result), ('inspected.json', inspected)]:
        (args.output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'success': receipt['success'], 'provider_requests': len(provider.posts),
        'statuses': receipt['statuses'], 'output': str(args.output)}))
    raise SystemExit(0 if receipt['success'] else 1)


if __name__ == '__main__':
    main()
