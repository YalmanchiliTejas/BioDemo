"""Opt-in verification of updated local host code with real Modal inference.

Uses an isolated local store and seeded synthetic source, never the production
database. Does not claim to test the deployed account. Provider calls are capped;
unknown hosted compute billing is not reported as free or as a dollar guarantee.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'backend'))

from src.lifesci.envfile import parse_env
from src.lifesci.container import Platform
from src.lifesci.devseed import seed, TENANT
from src.lifesci.store import RecordStore
from src.lifesci.gateway.providers import ModalProvider, ProviderError


class RecordedModal(ModalProvider):
    def __init__(self, settings, limit):
        super().__init__(environ=settings)
        self.limit = limit
        self.posts = []

    def _post(self, path, body, headers, timeout_s):
        if len(self.posts) >= self.limit:
            raise ProviderError('Live verification provider-call limit reached', retryable=False)
        self.posts.append({'requested_model': body['model'], 'status': 'started'})
        response = super()._post(path, body, headers, timeout_s)
        self.posts[-1].update(status='returned', returned_model=response.get('model'), request_id=response.get('id'),
                              usage=response.get('usage'))
        if response.get('model') != body['model']:
            raise ProviderError('Endpoint returned an unexpected model identity', retryable=False)
        return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Explicitly allow up to two real provider requests')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        parser.error('No inference without --execute')
    output = args.output.resolve()
    if output.exists():
        parser.error('Use a fresh output directory; previous evidence is never overwritten')
    settings = {}
    for path in (REPO / 'backend/deploy/aws/production.env', REPO / 'backend/.env.local'):
        if path.is_file():
            settings.update(parse_env(path.read_text()))
    settings.update(os.environ)
    # Explicit configuration only: no accidental production database or alternate model.
    os.environ['LIFESCI_LLM_PROVIDER'] = 'modal'
    os.environ['LIFESCI_LLM_MODEL'] = 'zai-org/GLM-5.3'
    os.environ.pop('LIFESCI_INTERPRETER_MODEL', None)
    os.environ.pop('LIFESCI_INTERPRETER_PROVIDER', None)
    provider = RecordedModal(settings, limit=2)
    provider._check_configuration()
    platform = Platform(RecordStore(), providers={'modal': provider}, allow_unqualified=True)
    platform.gateway.max_retries = 0
    seed(platform)
    ctx = platform.identity.context_for(TENANT, 'priya')
    source = platform.process_models.context(ctx, audience='technology_transfer')
    thread = platform.engineering_conversations.create(ctx, {})
    prompt = ('Use the attached freeze-drying transfer context. Calculate its recorded baseline with the registered '
              'quasi-steady model. Compare a synthetic alternative with 6000 vials, keeping the other inputs unchanged. '
              'Show the calculated chart, comparison table, constraint margins and evidence. Create an engineering '
              'review proposal for the baseline result, without an additional interpretation step. Do not approve '
              'or execute manufacturing changes, invent inputs, or claim plant validation. Reply briefly in English.')
    queued = platform.engineering_conversations.enqueue(ctx, thread['id'], {
        'text': prompt, 'expected_revision': thread['revision'], 'source_ids': [source['id']]})
    result = platform.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
    turn = result['turns'][-1]
    artifacts = [platform.engineering_conversations.artifact(ctx, result['id'], a['kind'], a['id']) for a in turn['artifacts']]
    kinds = {a['kind'] for a in turn['artifacts']}
    success = turn['status'] == 'completed' and {'physical_analysis_result', 'physical_analysis_comparison', 'proposal'} <= kinds
    physical = [a for a in artifacts if 'models' in a]
    proposals = [a for a in artifacts if a.get('operation') == 'review_physical_analysis']
    success = success and len(physical) == 2 and all(a['execution_status'] == 'completed' for a in physical)
    success = success and all(a['status'] == 'proposed' for a in proposals)
    no_dispatch = not platform.store.read().list(TENANT, 'action_intent')
    success = success and no_dispatch
    receipt = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'execution': 'updated_local_backend_with_actual_modal_provider_not_deployed_account',
        'data': 'seeded_published_and_reconstructed_synthetic_freeze_drying_context',
        'success': success, 'status': turn['status'], 'provider_requests': provider.posts,
        'provider_billed_cost_usd': None, 'account_changes': False, 'manufacturing_dispatch': not no_dispatch,
        'elapsed_seconds': turn.get('elapsed_seconds'), 'issues': turn['issues'],
        'artifact_kinds': sorted(kinds), 'reply': turn['reply'],
        'source_sha256': {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            REPO / 'backend/src/lifesci/process_engineering/conversation.py', REPO / 'backend/src/lifesci/gateway/gateway.py']}}
    output.mkdir(parents=True)
    # Scrub credential values even if a provider's error text accidentally echoes one.
    secrets = [v for k, v in settings.items() if any(s in k.upper() for s in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY')) and len(v) > 8]
    for name, data in [('receipt.json', receipt), ('conversation.json', result), ('artifacts.json', artifacts)]:
        text = json.dumps(data, indent=2, ensure_ascii=False)
        for value in secrets:
            text = text.replace(value, '<REDACTED>')
        (output / name).write_text(text + '\n')
    print(json.dumps({'output': str(output), 'success': success, 'status': turn['status'],
                      'provider_requests': len(provider.posts), 'artifact_kinds': sorted(kinds),
                      'manufacturing_dispatch': not no_dispatch}))
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    main()
