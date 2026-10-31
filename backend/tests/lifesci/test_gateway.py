from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.lifesci.assurance import degraded_mode
from src.lifesci.gateway import (FakeProvider, ModelGateway, ProviderError, Router, RoutingError, TaskRequest,
                                 default_registry)
from src.lifesci.gateway.registry import Qualification
from src.lifesci.identity import IdentityService
from src.lifesci.store import RecordStore

T = "tenant-a"


def qualify(reg, task, profile, **metrics):
    reg.qualify(Qualification(task, profile, f"eval-{task}-{profile}", True, metrics or {"recall": 0.99},
                              {"recall": 0.95} if not metrics else {k: 0.0 for k in metrics}, "task-only", "p1"))


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    idn.assign_role(T, "u1", "msat", site_id="S1")
    reg = default_registry()
    fake = FakeProvider(name="anthropic")
    gw = ModelGateway(s, idn, reg, {"anthropic": fake})
    return SimpleNamespace(s=s, idn=idn, reg=reg, fake=fake, gw=gw, ctx=idn.context_for(T, "u1"))


def summary(text="ok", refs=()):
    return json.dumps({"summary": text, "source_refs": list(refs)})


def test_LS055_unqualified_routes_refused_and_unknown_tasks_not_cheap(env):
    with pytest.raises(RoutingError, match="no qualified"):
        env.gw.router.route("short_summary")
    with pytest.raises(RoutingError, match="unknown task"):
        env.gw.router.route("totally_new_task")
    dev = Router(env.reg, allow_unqualified=True)
    d = dev.route("totally_new_task")
    assert d.tier == "M3" and d.unqualified


def test_LS055_high_risk_cannot_use_unqualified_cheaper_model(env):
    with pytest.raises(ValueError, match="below the minimum tier"):
        qualify(env.reg, "investigation_planning", "anthropic-haiku")
    qualify(env.reg, "investigation_planning", "anthropic-opus")
    d = env.gw.router.route("investigation_planning", suggested_risk="low")
    assert d.profile.profile_id == "anthropic-opus" and "ignored" in d.notes[0]
    dev = Router(env.reg, allow_unqualified=True)
    assert dev.route("conflicting_evidence_synthesis").tier == "M3"


def test_routes_to_cheapest_qualified_small_model(env):
    qualify(env.reg, "short_summary", "anthropic-sonnet")
    qualify(env.reg, "short_summary", "anthropic-haiku")
    d = env.gw.router.route("short_summary")
    assert d.profile.model == "claude-haiku-5-5" and d.escalation_chain == ("anthropic-sonnet",)


def test_LS067_failed_or_incomplete_evaluation_cannot_activate(env):
    with pytest.raises(ValueError, match="thresholds"):
        env.reg.qualify(Qualification("short_summary", "anthropic-haiku", "e1", True, {"recall": 0.8},
                                      {"recall": 0.95}, "task-only", "p1"))
    with pytest.raises(ValueError, match="impact scope"):
        env.reg.qualify(Qualification("short_summary", "anthropic-haiku", "e1", True, {}, {}, "", "p1"))
    assert env.reg.qualified_profiles("short_summary") == []


def test_LS056_deterministic_task_never_calls_model(env):
    env.gw.register_handler("limit_check", lambda p: {"within": p["low"] <= p["value"] <= p["high"]}, "v1")
    r = env.gw.run(TaskRequest("limit_check", env.ctx, payload={"value": 7.1, "low": 6.8, "high": 7.2},
                               suggested_risk="low"))
    assert r.status == "completed" and r.route["tier"] == "C0" and r.cost_usd == 0 and env.fake.calls == []


def test_validation_repair_then_escalation(env):
    qualify(env.reg, "short_summary", "anthropic-haiku")
    qualify(env.reg, "short_summary", "anthropic-sonnet")
    env.fake.scripts = {"claude-haiku-5-5": ["not json", json.dumps({"summary": 3})],
                        "claude-sonnet-5-5": [summary("good")]}
    r = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="summarize"))
    assert r.status == "completed" and r.output["summary"] == "good"
    assert [c["model"] for c in env.fake.calls] == ["claude-haiku-5-5", "claude-haiku-5-5", "claude-sonnet-5-5"]
    assert any("repair" in c["prompt"] or "failed validation" in c["prompt"] for c in env.fake.calls[1:2])


def test_grounding_rejects_unsupplied_sources_and_probabilities(env):
    qualify(env.reg, "short_summary", "anthropic-haiku")
    env.idn.assign_role(T, "u1", "operator", site_id="S1")
    with env.s.transaction("u1") as tx:
        tx.put(T, "evidence", "LIMS:1", {"site_id": "S1", "status": "current"}, expected_revision=None, action="x")
    refs = [{"kind": "evidence", "id": "LIMS:1", "revision": 1, "site_id": "S1"}]
    env.fake.scripts = {"claude-haiku-5-5": [summary("x", ["LIMS:999"]),
                                             json.dumps({"summary": "y", "source_refs": ["LIMS:1"],
                                                         "confidence_probability": 0.97})]}
    r = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="s", inputs=refs))
    assert r.status == "unresolved"
    assert any("not supplied" in i for i in r.issues) and any("uncalibrated" in i for i in r.issues)


def test_LS080_V09_provider_outage_fails_over_then_blocks_honestly(env):
    qualify(env.reg, "short_summary", "anthropic-haiku")
    qualify(env.reg, "short_summary", "anthropic-sonnet")
    err = ProviderError("503", retryable=True, kind="unavailable")
    env.fake.scripts = {"claude-haiku-5-5": [err, err, err], "claude-sonnet-5-5": [summary("from sonnet")]}
    r = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="s", use_cache=False))
    assert r.status == "completed" and r.output["summary"] == "from sonnet"
    env.fake.scripts = {"claude-sonnet-5-5": [err, err, err]}
    r2 = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="other", use_cache=False))
    assert r2.status == "blocked"
    env.gw.register_handler("limit_check", lambda p: {"within": True}, "v1")
    assert env.gw.run(TaskRequest("limit_check", env.ctx, payload={})).status == "completed"
    for pid in env.reg.profiles:
        env.gw.mark_unavailable(pid)
    report = degraded_mode(env.gw)
    assert not report.models_available and "authorization" in report.continuing
    assert "short_summary" in report.blocked and "limit_check" not in report.blocked
    assert env.gw.run(TaskRequest("short_summary", env.ctx, prompt="x", use_cache=False)).status == "blocked"
    assert env.gw.run(TaskRequest("limit_check", env.ctx, payload={})).status == "completed"
    env.gw.mark_unavailable("anthropic-haiku", seconds=0)  # breaker cooldown elapsed -> half-open
    assert "anthropic-haiku" not in env.gw.unavailable


def test_LS058_budget_exhaustion_preserves_controls(env):
    qualify(env.reg, "short_summary", "anthropic-haiku")
    env.gw.budgets.set_limit(T, "mission:m1", 0.0000001)
    r = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="s" * 4000, mission_id="m1"))
    assert r.status == "budget_exhausted" and env.fake.calls == []
    assert env.gw.router.route("short_summary").profile.profile_id == "anthropic-haiku"  # no silent downgrade/upgrade


def test_budget_reserve_settle_accounting(env):
    qualify(env.reg, "short_summary", "anthropic-haiku")
    env.gw.budgets.set_limit(T, "mission:m2", 1.0)
    env.fake.scripts = {"claude-haiku-5-5": [summary()]}
    r = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="s", mission_id="m2"))
    st = env.gw.budgets.status(T, "mission:m2")
    assert st["reserved"] == 0 and abs(st["spent"] - r.cost_usd) < 1e-12 and st["calls"] == 1


def test_LS057_LS066_trace_aggregates_descendants_and_reviewer_effort(env):
    qualify(env.reg, "short_summary", "anthropic-haiku")
    qualify(env.reg, "investigation_planning", "anthropic-opus")
    env.fake.default = lambda model, prompt: summary("x") if "haiku" in model else json.dumps({"plan": []})
    root = env.gw.run(TaskRequest("investigation_planning", env.ctx, prompt="plan", queued_at="2026-10-23T00:00:00+00:00"))
    c1 = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="a", parent_run_id=root.run_id))
    env.gw.run(TaskRequest("short_summary", env.ctx, prompt="b", parent_run_id=c1.run_id))
    env.gw.record_reviewer_effort(env.ctx, root.run_id, 12, reviewer_id="qa1")
    t = env.gw.trace(T, root.run_id, reviewer_rate_per_hour=120)
    assert t["runs"] == 3 and t["model_calls"] == 3
    assert t["reviewer_minutes"] == 12 and t["reviewer_cost_usd"] == 24.0
    assert t["total_cost_usd"] > t["model_cost_usd"] > 0 and t["end_to_end_ms"] > 0
    run = env.s.read().get(T, "model_run", root.run_id).state
    assert run["route"]["model"] == "claude-opus-5-5" and run["prompt_hash"] and run["requires_human_review"]


def test_cache_hit_rechecks_freshness(env):
    qualify(env.reg, "short_summary", "anthropic-haiku")
    with env.s.transaction("u1") as tx:
        tx.put(T, "evidence", "LIMS:7", {"site_id": "S1", "status": "current"}, expected_revision=None, action="x")
    env.idn.assign_role(T, "u1", "operator", site_id="S1")
    refs = [{"kind": "evidence", "id": "LIMS:7", "revision": 1, "site_id": "S1"}]
    env.fake.default = lambda m, p: summary("cached", ["LIMS:7"])
    a = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="s", inputs=refs))
    b = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="s", inputs=refs))
    assert not a.cached and b.cached and b.cost_usd == 0 and len(env.fake.calls) == 1
    with env.s.transaction("u1") as tx:
        tx.put(T, "evidence", "LIMS:7", {"site_id": "S1", "status": "current", "v": 2}, expected_revision=1, action="x")
    stale_refs = [{**refs[0], "revision": 1}]
    c = env.gw.run(TaskRequest("short_summary", env.ctx, prompt="s", inputs=stale_refs))
    assert not c.cached


def test_denied_when_inputs_unreadable(env):
    other = env.idn.context_for(T, "nobody")
    r = env.gw.run(TaskRequest("short_summary", other, prompt="s",
                               inputs=[{"kind": "evidence", "id": "X", "revision": 1, "site_id": "S1"}]))
    assert r.status == "denied" and env.fake.calls == []


def test_illustrative_cost_model_matches_doc(env):
    p = {x.profile_id: x for x in env.reg.profiles.values()}
    mixed = 80 * p["openai-luna"].cost(2000, 500) + 18 * p["openai-sol"].cost(2000, 500) + 2 * p["openai-astra"].cost(2000, 500)
    assert round(mixed, 3) == 0.288 and round(100 * p["openai-astra"].cost(2000, 500), 2) == 4.50


# --- Modal (OpenAI-compatible Chat Completions) adapter ------------------------------------

MODAL_TOKEN = "wk-test.ws-secret"


class _Response:
    def __init__(self, body, status=200):
        self._body, self.status_code, self.text = body, status, json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture
def modal_http(monkeypatch):
    import httpx
    calls = []

    def respond(body, status=200):
        def post(url, json=None, headers=None, timeout=None):
            calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
            return _Response(body, status)
        monkeypatch.setattr(httpx, "post", post)
        return calls
    return respond


def modal_provider(**env):
    from src.lifesci.gateway import ModalProvider
    return ModalProvider(environ={"MODAL_PROXY_TOKEN": f"Bearer {MODAL_TOKEN}",
                                  "MODAL_BASE_URL": "https://ws--app.modal.direct/v1/", **env})


def test_modal_request_shape_and_parsing(modal_http):
    calls = modal_http({"id": "req-1", "choices": [{"message": {
        "content": "answer", "reasoning_content": "hidden chain"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34}})
    c = modal_provider().complete(model="zai-org/GLM-5.3", system="sys", prompt="hi",
                                  max_output_tokens=2000, timeout_s=60)
    call = calls[0]
    assert call["url"] == "https://ws--app.modal.direct/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {MODAL_TOKEN}"
    assert call["json"]["model"] == "zai-org/GLM-5.3"
    assert call["json"]["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert call["json"]["max_tokens"] == 16000 and call["timeout"] == 300
    assert (c.text, c.input_tokens, c.output_tokens, c.provider_request_id) == ("answer", 12, 34, "req-1")


def test_modal_limits_are_configurable(modal_http):
    calls = modal_http({"choices": [{"message": {"content": "x"}}], "usage": {}})
    modal_provider(MODAL_TIMEOUT_SECONDS="900", MODAL_MIN_MAX_TOKENS="100").complete(
        model="m", system="s", prompt="p", max_output_tokens=2000, timeout_s=60)
    assert calls[0]["json"]["max_tokens"] == 2000 and calls[0]["timeout"] == 900


def test_modal_null_content_is_an_error_not_reasoning(modal_http):
    modal_http({"choices": [{"message": {"content": None, "reasoning_content": "thinking..."},
                             "finish_reason": "length"}], "usage": {"prompt_tokens": 1, "completion_tokens": 9}})
    with pytest.raises(ProviderError, match="budget exhausted") as exc:
        modal_provider().complete(model="m", system="s", prompt="p", max_output_tokens=10, timeout_s=1)
    assert not exc.value.retryable


@pytest.mark.parametrize("env, kind", [
    ({"MODAL_BASE_URL": ""}, "unavailable"),
    ({"MODAL_BASE_URL": "https://user:pw@host/v1"}, "unavailable"),
    ({"MODAL_PROXY_TOKEN": ""}, "auth"),
    ({"MODAL_PROXY_TOKEN": "not-a-modal-token"}, "auth"),
])
def test_modal_unavailable_without_valid_configuration(modal_http, env, kind):
    calls = modal_http({})
    with pytest.raises(ProviderError) as exc:
        modal_provider(**env).complete(model="m", system="s", prompt="p", max_output_tokens=10, timeout_s=1)
    assert exc.value.kind == kind and not calls


def test_modal_accepts_biodemo_env_names_and_registers_only_when_complete(monkeypatch):
    from src.lifesci.container import Platform
    for key in ("MODAL_PROXY_TOKEN", "MODAL_BASE_URL", "BIODEMO_MODAL_PROXY_TOKEN", "BIODEMO_MODAL_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BIODEMO_MODAL_PROXY_TOKEN", MODAL_TOKEN)
    assert "modal" not in Platform._env_providers()
    monkeypatch.setenv("BIODEMO_MODAL_BASE_URL", "https://ws--app.modal.direct/v1")
    provider = Platform._env_providers()["modal"]
    assert provider._key == MODAL_TOKEN and provider._base == "https://ws--app.modal.direct/v1"
