"""Request failures must not make unrelated work look like a provider outage."""
import json

import pytest

from src.lifesci.gateway import (FakeProvider, ModalProvider, ModelGateway, ProviderError,
                                 TaskRequest, default_registry)
from src.lifesci.gateway.registry import Qualification
from src.lifesci.identity import IdentityService
from src.lifesci.store import RecordStore
from tests.lifesci.test_gateway import modal_stream, sse


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


@pytest.mark.parametrize('kind', ['output_limit', 'bad_request', 'unfinished'])
def test_request_failure_does_not_block_next_healthy_request(gateway, kind):
    gw, provider, ctx = gateway
    model = gw.registry.profiles['anthropic-haiku'].model
    # An exhausted output budget gets one more sample; a reply still arriving at the time limit gets the usual tries.
    tries = {'output_limit': 2, 'unfinished': 3}.get(kind, 1)
    provider.scripts[model] = [ProviderError('This request cannot produce an answer',
        retryable=kind == 'unfinished', kind=kind)] * tries + [json.dumps({'summary': 'Healthy request answered', 'source_refs': []})]
    first = gw.run(TaskRequest('short_summary', ctx, prompt='Request exceeding its limits', use_cache=False))
    assert first.status == 'blocked' and first.output is None
    assert len(first.attempts) == tries and first.attempts[0]['error_kind'] == kind
    second = gw.run(TaskRequest('short_summary', ctx, prompt='Unrelated smaller request', use_cache=False))
    assert second.status == 'completed', second.issues
    assert second.output['summary'] == 'Healthy request answered'


def test_a_rate_limited_request_waits_and_asks_again_without_using_an_attempt(gateway):
    gw, provider, ctx = gateway
    waits = []
    gw._sleep = waits.append
    model = gw.registry.profiles['anthropic-haiku'].model
    limited = lambda **more: ProviderError('rate limited', retryable=True, kind='rate_limit', **more)
    provider.scripts[model] = [limited(), limited(retry_after=3), limited(retry_after=0),
                               json.dumps({'summary': 'Answered once the endpoint had room', 'source_refs': []})]
    result = gw.run(TaskRequest('short_summary', ctx, prompt='Asked while the endpoint was full', use_cache=False,
                                max_provider_calls=1))
    # One call was allowed. The three refusals did no work and did not use it.
    assert result.status == 'completed' and result.output['summary'] == 'Answered once the endpoint had room'
    assert [a.get('error_kind') for a in result.attempts] == ['rate_limit'] * 3 + [None]
    # First its own growing, uneven wait; then the wait the endpoint asked for; never no wait at all.
    assert 0.5 <= waits[0] <= 1.5 and waits[1:] == [3, 0.5]


def test_an_endpoint_that_stays_rate_limited_fails_after_a_bounded_wait(gateway):
    gw, provider, ctx = gateway
    waits = []
    gw._sleep, gw.rate_limit_wait_s = waits.append, 5.0
    model = gw.registry.profiles['anthropic-haiku'].model
    provider.scripts[model] = [ProviderError('rate limited', retryable=True, kind='rate_limit')] * 30
    first = gw.run(TaskRequest('short_summary', ctx, prompt='First request', use_cache=False))
    assert first.status == 'blocked' and sum(waits) == pytest.approx(5.0) and all(w > 0 for w in waits)
    assert len(first.attempts) == len(waits) + 3     # then its ordinary three tries, and no more
    second = gw.run(TaskRequest('short_summary', ctx, prompt='Second request', use_cache=False))
    assert second.status == 'blocked' and not second.attempts   # the breaker holds further requests off, as for an outage


@pytest.mark.parametrize('kind, retryable, expected_attempts', [
    ('timeout', True, 3), ('unavailable', True, 3), ('auth', False, 1),
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
    modal_stream(monkeypatch, sse({
        'choices': [{'message': {'content': None, 'reasoning_content': 'Private reasoning'},
                     'finish_reason': 'length'}],
        'usage': {'prompt_tokens': 4, 'completion_tokens': 16_000}}))
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


@pytest.mark.parametrize('setting,expected', [(None, None), ('low', 'low'), (' HIGH ', 'high'), ('max', 'max'), ('fastest', None)])
def test_modal_reasoning_effort_is_sent_only_when_explicitly_set(monkeypatch, setting, expected):
    calls = modal_stream(monkeypatch, sse({'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}], 'usage': {}}))
    sent = type('Bodies', (), {'__getitem__': lambda self, i: calls[i]['json']})()
    environ = {'MODAL_PROXY_TOKEN': 'wk-test.ws-secret', 'MODAL_BASE_URL': 'https://test.modal.direct/v1'}
    if setting is not None:
        environ['MODAL_REASONING_EFFORT'] = setting
    provider = ModalProvider(environ=environ)
    provider.chat(model='test-model', messages=[{'role': 'user', 'content': 'q'}], tools=[], tool_choice='auto',
                  max_output_tokens=100, timeout_s=1)
    assert sent[0].get('reasoning_effort') == expected
    # The single-call planner path is unchanged: its evaluations were run without an effort setting.
    provider.complete(model='test-model', system='s', prompt='p', max_output_tokens=100, timeout_s=1)
    assert 'reasoning_effort' not in sent[1]
