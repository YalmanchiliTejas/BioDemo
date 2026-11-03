"""Bounded calls to actual configured providers; never synthesize agent responses."""
import json
import os
from pathlib import Path
from src.lifesci.envfile import parse_env
from src.lifesci.gateway.providers import ProviderError

PROVIDER_KEYS = {'MODAL_BASE_URL', 'BIODEMO_MODAL_BASE_URL', 'MODAL_PROXY_TOKEN',
                 'BIODEMO_MODAL_PROXY_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY',
                 'OPENAI_BASE_URL', 'ANTHROPIC_BASE_URL',
                 'LIFESCI_LLM_PROVIDER', 'LIFESCI_LLM_MODEL'}


def configure(path=None):
    if path:
        settings = parse_env(Path(path).read_text())
        for key in PROVIDER_KEYS:
            if settings.get(key):
                os.environ[key] = settings[key]
    # Do not load database URLs, connectors, tenant settings or ownership from env files.
    if os.environ.get('MODAL_PROXY_TOKEN') or os.environ.get('BIODEMO_MODAL_PROXY_TOKEN'):
        os.environ.setdefault('LIFESCI_LLM_PROVIDER', 'modal')
        os.environ.setdefault('LIFESCI_LLM_MODEL', 'zai-org/GLM-5.3')


class BoundedProvider:
    def __init__(self, provider, ledger, max_requests):
        self.inner, self.ledger, self.max_requests = provider, Path(ledger), max_requests
        self.name = provider.name

    def complete(self, **kwargs):
        calls = json.loads(self.ledger.read_text()) if self.ledger.exists() else []
        if len(calls) >= self.max_requests:
            raise ProviderError('evaluation request budget exhausted', retryable=False, kind='budget')
        # Admission remains charged after errors; no hidden free retries.
        from src.lifesci.ids import content_hash
        entry = {'provider': self.name, 'requested_model': kwargs['model'], 'status': 'admitted',
                 'prompt_hash':content_hash(kwargs['prompt'])}
        calls.append(entry)
        self.ledger.write_text(json.dumps(calls, indent=2))
        try:
            result = self.inner.complete(**kwargs)
        except Exception as exc:
            entry.update(status='error', error_type=type(exc).__name__, error_kind=getattr(exc, 'kind', 'error'))
            self.ledger.write_text(json.dumps(calls, indent=2))
            raise
        entry.update(status='completed', provider_request_id=result.provider_request_id,
                     input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                     latency_ms=result.latency_ms, provider_cost_usd=result.provider_cost_usd,
                     returned_model=getattr(self.inner, 'last_response_model', None))
        self.ledger.write_text(json.dumps(calls, indent=2))
        return result


def recorded_modal():
    from src.lifesci.gateway.providers import ModalProvider
    class RecordedModal(ModalProvider):
        last_response_model = None
        def _post(self, path, body, headers, timeout_s):
            data = super()._post(path, body, headers, timeout_s)
            self.last_response_model = data.get('model')
            if self.last_response_model != body['model']:
                raise ProviderError('endpoint returned an unexpected model identity', retryable=False)
            return data
    return RecordedModal(timeout_s=120)
