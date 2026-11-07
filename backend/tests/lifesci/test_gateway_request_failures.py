"""Request failures must not make unrelated work look like a provider outage."""
import json

import pytest

from src.lifesci.gateway import (FakeProvider, ModalProvider, ModelGateway, ProviderError,
                                 TaskRequest, default_registry)
from src.lifesci.gateway.registry import Qualification
from src.lifesci.identity import IdentityService
from src.lifesci.store import RecordStore


@pytest.fixture
def gateway():
    store = RecordStore()
    identity = IdentityService(store)
    identity.assign_role('request-failures', 'owner', 'msat', site_id='S1')
    registry = default_registry()
    registry.qualify(Qualification('short_summary', 'anthropic-haiku', 'test-contract', True,
        {'contract': 1.}, {'contract': 1.}, 'Scripted provider contract only', 'test'))
    provider = FakeProvider(name='anthropic')
    gw = ModelGateway(store, identity, registry, {'anthropic': provider})
    return gw, provider, identity.context_for('request-failures', 'owner')


@pytest.mark.parametrize('kind', ['output_limit', 'bad_request'])
def test_request_failure_does_not_block_next_healthy_request(gateway, kind):
    gw, provider, ctx = gateway
    model = gw.registry.profiles['anthropic-haiku'].model
    tries = 2 if kind == 'output_limit' else 1  # an exhausted output budget gets one more sample
    provider.scripts[model] = [ProviderError('This request cannot produce an answer',
        retryable=False, kind=kind)] * tries + [json.dumps({'summary': 'Healthy request answered', 'source_refs': []})]
    first = gw.run(TaskRequest('short_summary', ctx, prompt='Request exceeding its limits', use_cache=False))
    assert first.status == 'blocked' and first.output is None
    assert len(first.attempts) == tries and first.attempts[0]['error_kind'] == kind
    second = gw.run(TaskRequest('short_summary', ctx, prompt='Unrelated smaller request', use_cache=False))
    assert second.status == 'completed', second.issues
    assert second.output['summary'] == 'Healthy request answered'


@pytest.mark.parametrize('kind, retryable, expected_attempts', [
    ('timeout', True, 3), ('unavailable', True, 3), ('rate_limit', True, 3), ('auth', False, 1),
])
def test_provider_failure_still_blocks_next_request_during_cooldown(gateway, kind, retryable, expected_attempts):
    gw, provider, ctx = gateway
    model = gw.registry.profiles['anthropic-haiku'].model
    error = ProviderError('Provider cannot serve this profile', retryable=retryable, kind=kind)
    provider.scripts[model] = [error] * expected_attempts + [json.dumps({'summary': 'Unused', 'source_refs': []})]
    first = gw.run(TaskRequest('short_summary', ctx, prompt='First request', use_cache=False))
    assert first.status == 'blocked' and len(first.attempts) == expected_attempts
    second = gw.run(TaskRequest('short_summary', ctx, prompt='Second request', use_cache=False))
    assert second.status == 'blocked' and not second.attempts
    assert any('available' in issue for issue in second.issues)


def test_modal_empty_length_response_is_a_request_output_limit(monkeypatch):
    import httpx

    def post(*args, **kwargs):
        return httpx.Response(200, json={
            'choices': [{'message': {'content': None, 'reasoning_content': 'Private reasoning'},
                         'finish_reason': 'length'}],
            'usage': {'prompt_tokens': 4, 'completion_tokens': 16_000}})

    monkeypatch.setattr(httpx, 'post', post)
    provider = ModalProvider(environ={'MODAL_PROXY_TOKEN': 'wk-test.ws-secret',
        'MODAL_BASE_URL': 'https://test.modal.direct/v1'})
    with pytest.raises(ProviderError) as raised:
        provider.complete(model='test-model', system='Return JSON', prompt='Request',
            max_output_tokens=100, timeout_s=1)
    assert raised.value.kind == 'output_limit'
    assert raised.value.retryable is False
    assert 'Private reasoning' not in str(raised.value)


def test_an_exhausted_output_budget_is_sampled_once_more(gateway):
    gw, provider, ctx = gateway
    model = gw.registry.profiles['anthropic-haiku'].model
    provider.scripts[model] = [ProviderError('no answer content', retryable=False, kind='output_limit'),
                               json.dumps({'summary': 'Answered on the second sample', 'source_refs': []})]
    result = gw.run(TaskRequest('short_summary', ctx, prompt='Long reasoning', use_cache=False))
    assert result.status == 'completed' and len(result.attempts) == 2
    assert provider.calls[1]['max_output_tokens'] == 48_000  # more room to finish reasoning
