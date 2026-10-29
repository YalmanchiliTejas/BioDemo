"""Configured LLM routing contracts, without live provider credentials or calls."""
import json
import pytest
from fastapi.testclient import TestClient

from src.lifesci.api import create_app
from src.lifesci.container import Platform
from src.lifesci.devseed import TENANT, seed
from src.lifesci.gateway import FakeProvider, TaskRequest
from src.lifesci.gateway.configuration import configure_engineering_llms
from src.lifesci.gateway.providers import OpenAIProvider
from src.lifesci.gateway.registry import default_registry
from src.lifesci.gateway.router import Router, RoutingError
from src.lifesci.store import RecordStore


def config(**extras):
    return {'LIFESCI_LLM_PROVIDER': 'anthropic', 'LIFESCI_LLM_MODEL': 'my-actual-model-id', **extras}


def test_single_model_binds_both_tasks_without_qualifying():
    reg = default_registry()
    bindings = configure_engineering_llms(reg, config())
    strict = Router(reg, task_profile_bindings=bindings)
    with pytest.raises(RoutingError, match='no qualified'):
        strict.route('investigation_planning')
    dev = Router(reg, allow_unqualified=True, task_profile_bindings=bindings)
    for task in bindings:
        route = dev.route(task)
        assert route.profile.model == 'my-actual-model-id' and route.unqualified
        assert route.to_dict()['cost_basis']['classification'] == 'development_budget_assumptions_not_provider_prices'
    assert not reg.qualifications
    # Other tasks keep the ordinary registry behavior.
    assert dev.route('short_summary').profile.profile_id == 'anthropic-haiku'


def test_separate_interpreter_and_explicit_routing_no_silent_provider_fallback():
    reg = default_registry()
    bindings = configure_engineering_llms(reg, config(LIFESCI_INTERPRETER_PROVIDER='openai', LIFESCI_INTERPRETER_MODEL='other-model'))
    router = Router(reg, allow_unqualified=True, task_profile_bindings=bindings)
    assert router.route('investigation_planning').profile.provider == 'anthropic'
    assert router.route('comparison_explanation').profile.model == 'other-model'
    with pytest.raises(RoutingError, match='no available model'):
        router.route('investigation_planning', unavailable={'engineering-planner'})


@pytest.mark.parametrize('values', [
    {'LIFESCI_LLM_MODEL': 'model-only'}, {'LIFESCI_LLM_PROVIDER': 'anthropic'},
    config(LIFESCI_LLM_PROVIDER='unimplemented-provider'), config(LIFESCI_LLM_INPUT_USD_PER_MTOK='nan'),
    config(LIFESCI_LLM_OUTPUT_USD_PER_MTOK='-1'), config(LIFESCI_INTERPRETER_PROVIDER='openai'),
])
def test_invalid_configuration_fails_before_any_network_request(values):
    with pytest.raises(ValueError):
        configure_engineering_llms(default_registry(), values)


def test_versions_change_with_model_endpoint_and_pricing_and_secrets_are_excluded():
    def profile(**extra):
        reg = default_registry()
        configure_engineering_llms(reg, config(**extra))
        return reg.profiles['engineering-planner']
    first = profile()
    assert profile(LIFESCI_LLM_MODEL='changed').version != first.version
    assert profile(ANTHROPIC_BASE_URL='http://localhost:9999').version != first.version
    assert profile(LIFESCI_LLM_INPUT_USD_PER_MTOK='4').version != first.version
    assert profile(ANTHROPIC_API_KEY='secret-that-must-not-leak').version == first.version
    known = profile(LIFESCI_LLM_INPUT_USD_PER_MTOK='1', LIFESCI_LLM_OUTPUT_USD_PER_MTOK='2', LIFESCI_LLM_CACHED_INPUT_USD_PER_MTOK='.1')
    assert known.price_source == 'operator_configured_estimate'


def test_custom_api_base_accepts_root_or_v1_without_double_version():
    assert OpenAIProvider(api_key='test-only', base_url='http://127.0.0.1:8000/v1/')._base == 'http://127.0.0.1:8000'
    assert OpenAIProvider(api_key='test-only', base_url='http://127.0.0.1:8000')._base == 'http://127.0.0.1:8000'


def test_env_startup_and_connection_status_do_not_leak_keys(monkeypatch):
    monkeypatch.setenv('LIFESCI_DATABASE_URL', ':memory:')
    monkeypatch.setenv('LIFESCI_LLM_PROVIDER', 'anthropic')
    monkeypatch.setenv('LIFESCI_LLM_MODEL', 'my-actual-model-id')
    monkeypatch.setenv('LIFESCI_ALLOW_UNQUALIFIED_ROUTES', '1')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'secret-that-must-not-leak')
    p = Platform.from_env()
    seed(p)
    client = TestClient(create_app(p))
    headers = {'X-Tenant-Id': TENANT, 'X-Actor-Id': 'priya'}
    response = client.get('/v1/process-model/llm-connection', headers=headers)
    assert response.status_code == 200
    assert 'secret-that-must-not-leak' not in response.text
    body = response.json()
    assert body['development_unqualified_routes']
    assert body['tasks']['planner']['route']['model'] == 'my-actual-model-id'
    assert body['tasks']['planner']['status'] == 'configured_not_connectivity_tested'
    assert not p.store.read().list(TENANT, 'model_run')  # diagnostic costs no inference


def test_configured_provider_is_used_for_a_real_gateway_execution_contract(monkeypatch):
    monkeypatch.setenv('LIFESCI_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('LIFESCI_LLM_MODEL', 'account-specific-id')
    fake = FakeProvider(name='openai', scripts={'account-specific-id': [json.dumps({'reply': 'Which input context?', 'questions': ['Which formulation and equipment?']})]})
    p = Platform(RecordStore(), providers={'openai': fake}, allow_unqualified=True)
    seed(p)
    ctx = p.identity.context_for(TENANT, 'priya')
    svc = p.engineering_conversations
    thread = svc.create(ctx, {})
    queued = svc.enqueue(ctx, thread['id'], {'text': 'Investigate a drying deviation', 'expected_revision': thread['revision']})
    done = svc.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
    assert done['turns'][0]['status'] == 'needs_information'
    assert fake.calls[0]['model'] == 'account-specific-id'
    trace = done['turns'][0]['gateway_runs'][0]
    assert trace['route']['provider'] == 'openai' and trace['route']['unqualified']
    assert trace['requires_human_review']
