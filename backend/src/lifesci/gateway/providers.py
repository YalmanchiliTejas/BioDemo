"""Provider adapters behind one interface. Credentials are read from the environment
by the adapter only; generated content and tools never see them (LS-081)."""

from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.parse import urlparse


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool, kind: str = "error") -> None:
        super().__init__(message)
        self.retryable = retryable
        self.kind = kind  # rate_limit | timeout | unavailable | auth | bad_request | error


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    provider_request_id: str | None = None
    provider_cost_usd: float | None = None
    latency_ms: float = 0.0


class Provider(Protocol):
    name: str

    def complete(self, *, model: str, system: str, prompt: str, max_output_tokens: int,
                 timeout_s: float) -> Completion: ...


@dataclass
class FakeProvider:
    """Deterministic provider for tests and offline development; scripted per model."""
    name: str = "fake"
    scripts: dict[str, list[Any]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    default: Callable[[str, str], str] | None = None

    def complete(self, *, model: str, system: str, prompt: str, max_output_tokens: int,
                 timeout_s: float) -> Completion:
        self.calls.append({"model": model, "prompt": prompt})
        queue = self.scripts.get(model)
        if queue:
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            text = item
        elif self.default:
            text = self.default(model, prompt)
        else:
            raise ProviderError(f"no scripted response for {model}", retryable=False, kind="unavailable")
        return Completion(text, max(len(system + prompt) // 4, 1), max(len(text) // 4, 1))


class _HTTPProvider:
    name = "http"
    env_key = ""
    base_url = ""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._key = api_key or os.environ.get(self.env_key)
        self._base = (base_url or os.environ.get(f"{self.env_key.split('_')[0]}_BASE_URL") or self.base_url).rstrip("/")
        # Provider methods append /v1 themselves; accept either server root or
        # the conventional API base without producing /v1/v1 requests.
        if self._base.endswith('/v1'):
            self._base = self._base[:-3]

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, str], timeout_s: float) -> dict[str, Any]:
        import httpx

        if not self._key:
            raise ProviderError(f"{self.name} credentials not configured ({self.env_key})", retryable=False, kind="auth")
        try:
            response = httpx.post(f"{self._base}{path}", json=body, headers=headers, timeout=timeout_s)
        except httpx.TimeoutException as exc:
            raise ProviderError(str(exc), retryable=True, kind="timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), retryable=True, kind="unavailable") from exc
        if response.status_code == 429:
            raise ProviderError("rate limited", retryable=True, kind="rate_limit")
        if response.status_code >= 500:
            raise ProviderError(f"provider {response.status_code}", retryable=True, kind="unavailable")
        if response.status_code in (401, 403):
            raise ProviderError("provider authentication failed", retryable=False, kind="auth")
        if response.status_code >= 400:
            raise ProviderError(f"bad request {response.status_code}: {response.text[:200]}", retryable=False,
                                kind="bad_request")
        return response.json()


class AnthropicProvider(_HTTPProvider):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
    base_url = "https://api.anthropic.com"

    def complete(self, *, model: str, system: str, prompt: str, max_output_tokens: int,
                 timeout_s: float) -> Completion:
        start = time.perf_counter()
        data = self._post("/v1/messages", {
            "model": model, "max_tokens": max_output_tokens,
            # Stable instructions are marked cacheable so repeated task prefixes are billed at cache rates.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt}],
        }, {"x-api-key": self._key or "", "anthropic-version": "2023-06-01"}, timeout_s)
        usage = data.get("usage", {})
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        cached = int(usage.get("cache_read_input_tokens", 0))
        return Completion(text, int(usage.get("input_tokens", 0)) + cached, int(usage.get("output_tokens", 0)),
                          cached, data.get("id"), None, (time.perf_counter() - start) * 1000)


class OpenAIProvider(_HTTPProvider):
    name = "openai"
    env_key = "OPENAI_API_KEY"
    base_url = "https://api.openai.com"

    def complete(self, *, model: str, system: str, prompt: str, max_output_tokens: int,
                 timeout_s: float) -> Completion:
        start = time.perf_counter()
        data = self._post("/v1/responses", {
            "model": model, "instructions": system, "input": prompt, "max_output_tokens": max_output_tokens,
        }, {"Authorization": f"Bearer {self._key}"}, timeout_s)
        usage = data.get("usage", {})
        text = data.get("output_text") or "".join(
            part.get("text", "") for item in data.get("output", []) for part in item.get("content", []) or []
            if part.get("type") in ("output_text", "text"))
        cached = int((usage.get("input_tokens_details") or {}).get("cached_tokens", 0))
        return Completion(text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)), cached,
                          data.get("id"), None, (time.perf_counter() - start) * 1000)


_MODAL_TOKEN = re.compile(r"^wk-[^.\s]+\.ws-\S+$")


def modal_settings(environ: Mapping[str, str] | None = None) -> tuple[str | None, str | None]:
    """Token and base URL for the Modal proxy, matching prime_runtime/provider_config.mjs."""
    env = os.environ if environ is None else environ
    token = (env.get("BIODEMO_MODAL_PROXY_TOKEN", "").strip() or env.get("MODAL_PROXY_TOKEN", "").strip())
    token = re.sub(r"^Bearer\s+", "", token, flags=re.IGNORECASE) or None
    base = (env.get("MODAL_BASE_URL", "").strip() or env.get("BIODEMO_MODAL_BASE_URL", "").strip()) or None
    return token, base


class ModalProvider(_HTTPProvider):
    """OpenAI-compatible Chat Completions on a Modal-hosted deployment.

    The base URL is deployment-specific and includes /v1; there is no default.
    Reasoning text is never returned as the answer.
    """
    name = "modal"
    env_key = "MODAL_PROXY_TOKEN"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout_s: float | None = None, environ: Mapping[str, str] | None = None) -> None:
        env = os.environ if environ is None else environ
        token, base = modal_settings(env)
        self._key = re.sub(r"^Bearer\s+", "", api_key.strip(), flags=re.IGNORECASE) if api_key else token
        self._base = (base_url or base or "").strip().rstrip("/")
        if timeout_s is None:
            try:
                timeout_s = float(env.get("MODAL_TIMEOUT_SECONDS", "300"))
            except ValueError:
                timeout_s = 300.0
        self._timeout = timeout_s if math.isfinite(timeout_s) and timeout_s > 0 else 300.0
        try:
            floor = int(env.get("MODAL_MIN_MAX_TOKENS", "16000"))
        except ValueError:
            floor = 16_000
        self._min_max_tokens = max(floor, 1)

    def _check_configuration(self) -> None:
        if not self._base:
            raise ProviderError("modal base URL not configured (set MODAL_BASE_URL to the deployment's /v1 URL)",
                                retryable=False, kind="unavailable")
        parsed = urlparse(self._base)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
            raise ProviderError("MODAL_BASE_URL must be an HTTP(S) URL without embedded credentials",
                                retryable=False, kind="unavailable")
        if not self._key:
            raise ProviderError("modal credentials not configured (MODAL_PROXY_TOKEN or BIODEMO_MODAL_PROXY_TOKEN)",
                                retryable=False, kind="auth")
        if not _MODAL_TOKEN.match(self._key):
            raise ProviderError("modal proxy token has the wrong format; expected wk-<id>.ws-<secret>",
                                retryable=False, kind="auth")

    def complete(self, *, model: str, system: str, prompt: str, max_output_tokens: int,
                 timeout_s: float) -> Completion:
        self._check_configuration()
        start = time.perf_counter()
        # Reasoning models are slow and spend output tokens before answering, so the
        # configured timeout and token budget are floors over the task policy defaults.
        data = self._post("/chat/completions", {
            "model": model, "max_tokens": max(max_output_tokens, self._min_max_tokens),
            # This endpoint rejects the 'developer' role.
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }, {"Authorization": f"Bearer {self._key}"}, max(timeout_s, self._timeout))
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        content = (choice.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            reason = choice.get("finish_reason")
            hint = " (output token budget exhausted, likely by reasoning)" if reason == "length" else ""
            raise ProviderError(f"modal returned no answer content{hint}; finish_reason={reason}",
                                retryable=False, kind="error")
        usage = data.get("usage") or {}
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
        return Completion(content, int(usage.get("prompt_tokens", 0) or 0),
                          int(usage.get("completion_tokens", 0) or 0), cached, data.get("id"), None,
                          (time.perf_counter() - start) * 1000)
