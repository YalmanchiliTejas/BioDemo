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
    def __init__(self, message: str, *, retryable: bool, kind: str = "error", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        # rate_limit | timeout (silent) | unfinished (still answering at the time limit) | unavailable | auth |
        # bad_request | output_limit | error
        self.kind = kind
        self.retry_after = retry_after  # seconds the endpoint asked for with a rate limit, when it said


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    provider_request_id: str | None = None
    provider_cost_usd: float | None = None
    latency_ms: float = 0.0
    # Native tool calls from chat(): [{'id', 'name', 'arguments' (JSON text)}]; empty for plain completions.
    tool_calls: tuple = ()
    # The reasoning level this reply was asked for, when one was sent, and how much of the output was reasoning.
    reasoning_effort: str | None = None
    reasoning_tokens: int = 0


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
        self.calls.append({"model": model, "prompt": prompt, "max_output_tokens": max_output_tokens})
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

    def chat(self, *, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], tool_choice: str,
             max_output_tokens: int, timeout_s: float, reasoning_effort: str | None = None) -> Completion:
        """Scripted turns: a str (final text), {'content', 'tool_calls': [{'name', 'arguments': dict}]}, an Exception,
        or a function of the messages so far returning one of those. A dict may carry 'effort': the reasoning level
        this provider is pretending to run at when the caller asks for none."""
        import json as _json
        self.calls.append({"model": model, "messages": [dict(m) for m in messages], "tools": [t["function"]["name"] for t in tools],
                           "tool_choice": tool_choice, "max_output_tokens": max_output_tokens, "reasoning_effort": reasoning_effort})
        queue = self.scripts.get(model)
        if not queue:
            raise ProviderError(f"no scripted response for {model}", retryable=False, kind="unavailable")
        item = queue.pop(0)
        if callable(item):  # a step that depends on what earlier tool calls created (e.g. a plan ID)
            item = item(messages)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            item = {"content": item}
        calls = () if tool_choice == "none" else tuple(
            {"id": f"call_{len(self.calls)}_{i}", "name": c["name"], "arguments": _json.dumps(c.get("arguments", {}))}
            for i, c in enumerate(item.get("tool_calls", [])))
        text = item.get("content") or ""
        return Completion(text, max(len(_json.dumps(messages)) // 4, 1), max(len(text) // 4, 1), tool_calls=calls,
                          reasoning_effort=reasoning_effort or item.get("effort"))


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
        self._refused(response)
        return response.json()

    @staticmethod
    def _refused(response: Any) -> None:
        """Raise for a reply that is not an answer, by what it means for the caller."""
        if response.status_code == 429:
            try:
                wait = float(response.headers.get("retry-after", ""))
            except ValueError:
                wait = None
            raise ProviderError("rate limited", retryable=True, kind="rate_limit",
                                retry_after=wait if wait is not None and math.isfinite(wait) and wait >= 0 else None)
        if response.status_code >= 500:
            raise ProviderError(f"provider {response.status_code}", retryable=True, kind="unavailable")
        if response.status_code in (401, 403):
            raise ProviderError("provider authentication failed", retryable=False, kind="auth")
        if response.status_code >= 400:
            raise ProviderError(f"bad request {response.status_code}: {response.text[:200]}", retryable=False,
                                kind="bad_request")


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
# GLM-5.3 has three levels: low, high and max. Measured on the deployed endpoint, 2026-11-16: nothing sent means max,
# and any other word ("medium" included) is accepted and also behaves like max. "medium" stays for models that have it.
EFFORTS = ("low", "medium", "high", "max")


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
            # 32k: at 16k, GLM exhausted the budget on 4/12 CMO table questions (blank answers); at 32k on 0/12.
            floor = int(env.get("MODAL_MIN_MAX_TOKENS", "32000"))
        except ValueError:
            floor = 32_000
        self._min_max_tokens = max(floor, 1)
        # Unset: the model decides how long to think (the behaviour every stored evaluation was run with).
        # Measured 2026-11-11 on the tool loop: "low" answered in 15-18 s instead of 50-90 s, but picked the
        # wrong run on a comparison it had to work out itself. Set it only with an evaluation behind it.
        effort = env.get("MODAL_REASONING_EFFORT", "").strip().lower()
        self._reasoning_effort = effort if effort in EFFORTS else None
        # Single completions (no tools) keep the deployment's default unless this is set. It is set only for the
        # explanation role, whose figures are calculated by the host and checked against the result afterwards.
        completion_effort = env.get("MODAL_COMPLETION_REASONING_EFFORT", "").strip().lower()
        self._completion_effort = completion_effort if completion_effort in EFFORTS else None
        # The explanation role asks the endpoint for a JSON object, so a stray sentence cannot cost a correction call.
        self._completion_json = env.get("MODAL_COMPLETION_JSON", "").strip() == "1"
        # Replies are read as a stream so that an endpoint which has stopped answering is noticed quickly (see _post).
        # MODAL_STREAM=0 goes back to one unstreamed reply, should a deployment not stream.
        self._stream = env.get("MODAL_STREAM", "").strip() != "0"
        try:
            stall = float(env.get("MODAL_STALL_SECONDS", "30"))
        except ValueError:
            stall = 30.0
        self._stall = stall if math.isfinite(stall) and stall > 0 else 30.0

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

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, str], timeout_s: float) -> dict[str, Any]:
        """Read the reply as a stream and return it in the shape of an unstreamed one.

        Streamed for one reason: an endpoint that has stopped answering is noticed after `_stall` seconds without a
        byte, not after the whole timeout (live: unanswered requests held a turn for 150 s each, one for 900 s).
        Measured on the deployed endpoint: the first byte within 2 s and never more than 0.7 s between chunks, thinking
        included. `timeout_s` still bounds the whole reply. A reply that ends before the endpoint says it has finished
        is an error, never a shorter answer."""
        if not self._stream:
            return super()._post(path, body, headers, timeout_s)
        import json

        import httpx

        stall, deadline = min(self._stall, timeout_s), time.monotonic() + timeout_s
        text: list[str] = []
        thinking: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        finish = usage = ident = model = None
        try:
            with httpx.stream("POST", f"{self._base}{path}", headers=headers,
                              json={**body, "stream": True, "stream_options": {"include_usage": True}},
                              timeout=httpx.Timeout(connect=10.0, read=stall, write=30.0, pool=10.0)) as response:
                if response.status_code != 200:
                    response.read()
                    self._refused(response)
                    raise ProviderError(f"provider {response.status_code}", retryable=True, kind="unavailable")
                for line in response.iter_lines():
                    if time.monotonic() > deadline:
                        # Still answering, only too slowly for this request: not a sign the endpoint is down.
                        raise ProviderError(f"reply not finished after {timeout_s:g} s", retryable=True, kind="unfinished")
                    if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                        continue  # keep-alive comments, blank separators and the end marker carry nothing
                    chunk = json.loads(line[5:])
                    if chunk.get("error"):
                        raise ProviderError("the endpoint reported an error while answering", retryable=True, kind="unavailable")
                    ident, model, usage = chunk.get("id") or ident, chunk.get("model") or model, chunk.get("usage") or usage
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        text.append(delta.get("content") or "")
                        thinking.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
                        for call in delta.get("tool_calls") or []:
                            slot = calls.setdefault(call.get("index") or 0, {"id": None, "name": "", "arguments": ""})
                            function = call.get("function") or {}
                            slot["id"] = slot["id"] or call.get("id")
                            slot["name"] += function.get("name") or ""
                            slot["arguments"] += function.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
        except httpx.ReadTimeout as exc:
            raise ProviderError(f"the endpoint sent nothing for {stall:g} s", retryable=True, kind="timeout") from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(str(exc) or type(exc).__name__, retryable=True, kind="timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc) or type(exc).__name__, retryable=True, kind="unavailable") from exc
        except (ValueError, AttributeError) as exc:  # a chunk that is not the JSON object the protocol promises
            raise ProviderError("unreadable reply from the endpoint", retryable=True, kind="unavailable") from exc
        if finish is None:
            raise ProviderError("the reply ended before the endpoint finished it", retryable=True, kind="unavailable")
        message: dict[str, Any] = {"role": "assistant", "content": "".join(text) or None,
                                   "reasoning_content": "".join(thinking) or None}
        if calls:
            message["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                                     for _, c in sorted(calls.items())]
        return {"id": ident, "model": model, "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                "usage": usage or {}}

    def complete(self, *, model: str, system: str, prompt: str, max_output_tokens: int,
                 timeout_s: float) -> Completion:
        self._check_configuration()
        start = time.perf_counter()
        # Reasoning models are slow and spend output tokens before answering, so the
        # configured timeout and token budget are floors over the task policy defaults.
        body = {
            "model": model, "max_tokens": max(max_output_tokens, self._min_max_tokens),
            # This endpoint rejects the 'developer' role.
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if self._completion_effort:
            body["reasoning_effort"] = self._completion_effort
        if self._completion_json:
            body["response_format"] = {"type": "json_object"}
        data = self._post("/chat/completions", body, {"Authorization": f"Bearer {self._key}"}, max(timeout_s, self._timeout))
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        content = (choice.get("message") or {}).get("content")
        # No low-effort retry on exhaustion: measured 2026-11-05, retried answers were wrong 2 of 5
        # (vs ~5% normally). A visible "unavailable" is safer than a confident wrong answer.
        if not isinstance(content, str) or not content.strip():
            reason = choice.get("finish_reason")
            hint = " (output token budget exhausted, likely by reasoning)" if reason == "length" else ""
            raise ProviderError(f"modal returned no answer content{hint}; finish_reason={reason}",
                                retryable=False, kind="output_limit" if reason == "length" else "error")
        usage = data.get("usage") or {}
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
        return Completion(content, int(usage.get("prompt_tokens", 0) or 0),
                          int(usage.get("completion_tokens", 0) or 0), cached, data.get("id"), None,
                          (time.perf_counter() - start) * 1000)

    def chat(self, *, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], tool_choice: str,
             max_output_tokens: int, timeout_s: float, reasoning_effort: str | None = None) -> Completion:
        """OpenAI-compatible chat with native tool calls (vLLM serving GLM supports them). `reasoning_effort` asks for
        one level for this call only, in place of the deployment's; the reply says which level it ran at."""
        self._check_configuration()
        start = time.perf_counter()
        body: dict[str, Any] = {"model": model, "max_tokens": max(max_output_tokens, self._min_max_tokens), "messages": messages}
        if tools:
            body.update(tools=tools, tool_choice=tool_choice)
        effort = reasoning_effort if reasoning_effort in EFFORTS else self._reasoning_effort
        if effort:
            body["reasoning_effort"] = effort
        # Tool-loop steps are small: honour the caller's timeout (the planner's floor is for one huge call).
        data = self._post("/chat/completions", body, {"Authorization": f"Bearer {self._key}"}, timeout_s)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = tuple({"id": c.get("id") or f"call_{i}", "name": (c.get("function") or {}).get("name", ""),
                       "arguments": (c.get("function") or {}).get("arguments") or "{}"}
                      for i, c in enumerate(message.get("tool_calls") or []))
        content = message.get("content") or ""
        if not calls and not content.strip():
            reason = choice.get("finish_reason")
            hint = " (output token budget exhausted, likely by reasoning)" if reason == "length" else ""
            raise ProviderError(f"modal returned no answer content{hint}; finish_reason={reason}",
                                retryable=False, kind="output_limit" if reason == "length" else "error")
        usage = data.get("usage") or {}
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
        thinking = usage.get("reasoning_tokens") or (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        return Completion(content, int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0),
                          cached, data.get("id"), None, (time.perf_counter() - start) * 1000, calls,
                          reasoning_effort=effort, reasoning_tokens=int(thinking or 0))
