"""ModelGateway.run(): the single entry point for model or deterministic task execution."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..identity import AccessContext, IdentityService
from ..ids import content_hash, iso, new_id, utc_now
from ..store import RecordStore
from .budget import BudgetExceeded, BudgetLedger
from .providers import Completion, Provider, ProviderError
from .registry import ModelProfile, ModelRegistry
from .router import RouteDecision, Router, RoutingError

DeterministicHandler = Callable[[dict[str, Any]], dict[str, Any]]

_TYPES = {"str": str, "list": list, "dict": dict, "int": int, "float": (int, float), "bool": bool}


@dataclass
class TaskRequest:
    task_kind: str
    ctx: AccessContext
    prompt: str = ""
    system: str = ("You are a pharmaceutical manufacturing assistant. Use only the supplied sources. "
                   "Label observations, calculations, hypotheses and unknowns. Return JSON only.")
    payload: dict[str, Any] = field(default_factory=dict)       # deterministic handler input
    inputs: list[dict[str, Any]] = field(default_factory=list)  # evidence refs {kind,id,revision,site_id}
    mission_id: str | None = None
    parent_run_id: str | None = None
    ambiguity: str | None = None
    suggested_risk: str | None = None
    needs_tools: bool = False
    timeout_s: float = 60.0
    queued_at: str | None = None
    prompt_version: str = "v1"
    use_cache: bool = True


@dataclass
class TaskResult:
    run_id: str
    status: str  # completed | unresolved | blocked | budget_exhausted | stale_basis | denied
    output: dict[str, Any] | None
    route: dict[str, Any]
    attempts: list[dict[str, Any]]
    cost_usd: float
    issues: list[str]
    requires_human_review: bool
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class ModelGateway:
    def __init__(self, store: RecordStore, identity: IdentityService, registry: ModelRegistry,
                 providers: dict[str, Provider], *, router: Router | None = None,
                 budgets: BudgetLedger | None = None, max_retries: int = 2, backoff_s: float = 0.0,
                 breaker_cooldown_s: float = 60.0) -> None:
        self.store = store
        self.identity = identity
        self.registry = registry
        self.providers = providers
        self.router = router or Router(registry)
        self.budgets = budgets or BudgetLedger(store)
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.handlers: dict[str, tuple[str, DeterministicHandler]] = {}
        self.breaker_cooldown_s = breaker_cooldown_s
        self._down_until: dict[str, float] = {}  # circuit breaker: profile -> monotonic time it may be retried

    @property
    def unavailable(self) -> set[str]:
        now = time.monotonic()
        return {p for p, until in self._down_until.items() if until > now}

    def mark_unavailable(self, profile_id: str, seconds: float | None = None) -> None:
        self._down_until[profile_id] = time.monotonic() + (self.breaker_cooldown_s if seconds is None else seconds)

    # --- registration ------------------------------------------------------------------
    def register_handler(self, task_kind: str, handler: DeterministicHandler, version: str) -> None:
        self.handlers[task_kind] = (version, handler)

    # --- main entry ---------------------------------------------------------------------
    def run(self, req: TaskRequest) -> TaskResult:
        started = utc_now()
        run_id = new_id("run")
        ctx = req.ctx
        if req.inputs:
            decision = self.identity.check_derived(ctx, req.inputs)
            if not decision:
                return self._finish(req, run_id, started, "denied", None, None, [], 0.0, [decision.reason])
        try:
            route = self.router.route(req.task_kind, ambiguity=req.ambiguity, needs_tools=req.needs_tools,
                                      context_tokens=self._estimate_tokens(req.system + req.prompt),
                                      unavailable=self.unavailable, suggested_risk=req.suggested_risk)
        except RoutingError as exc:
            status = "blocked" if self.unavailable else "unresolved"
            return self._finish(req, run_id, started, status, None, None, [], 0.0, [str(exc)])

        if route.tier == "C0":
            return self._run_deterministic(req, run_id, started, route)

        cache_key = self._cache_key(req, route)
        if req.use_cache:
            hit = self._cache_get(ctx, cache_key, req.inputs)
            if hit is not None:
                return self._finish(req, run_id, started, "completed", hit, route, [], 0.0, [], cached=True)

        attempts: list[dict[str, Any]] = []
        total_cost = 0.0
        issues: list[str] = []
        chain = [route.profile] + [self.registry.profiles[p] for p in route.escalation_chain]
        policy = self.registry.policies.get(req.task_kind)
        max_out = policy.max_output_tokens if policy else 4000
        repairs_left = policy.max_repairs if policy else 1
        escalations_left = 1 if (policy is None or policy.allow_escalation) else 0
        prompt = req.prompt
        index = 0
        while index < len(chain):
            profile = chain[index]
            estimate = profile.cost(self._estimate_tokens(req.system + prompt), max_out)
            scopes = self._scopes(req)
            try:
                reservation = self.budgets.reserve(ctx.tenant_id, scopes, estimate)
            except BudgetExceeded as exc:
                issues.append(str(exc))
                return self._finish(req, run_id, started, "budget_exhausted", None, route, attempts, total_cost,
                                    issues)
            completion, attempt_log = self._call_with_retries(profile, req.system, prompt, max_out, req.timeout_s)
            attempts.extend(attempt_log)
            actual = profile.cost(completion.input_tokens, completion.output_tokens,
                                  completion.cached_tokens) if completion else 0.0
            self.budgets.settle(ctx.tenant_id, reservation, actual)
            total_cost += actual
            if completion is None:
                # Provider unavailable after bounded retries: fail over to next eligible qualified profile.
                self.mark_unavailable(profile.profile_id)
                index += 1
                continue
            output, problems = self._validate(completion.text, req)
            attempts[-1]["validation"] = problems or "passed"
            if not problems:
                if not self._inputs_current(ctx, req.inputs):
                    return self._finish(req, run_id, started, "stale_basis", output, route, attempts, total_cost,
                                        ["an input changed during execution; result withheld from commit"])
                self._cache_put(ctx, cache_key, output, req.inputs)
                return self._finish(req, run_id, started, "completed", output, route, attempts, total_cost, issues)
            issues.extend(problems)
            if repairs_left > 0:
                repairs_left -= 1
                prompt = (f"{req.prompt}\n\nYour previous answer failed validation: {'; '.join(problems)}. "
                          "Return corrected JSON only.")
                continue  # one targeted repair on the same model
            if escalations_left > 0 and index + 1 < len(chain):
                escalations_left -= 1
                index += 1
                prompt = req.prompt
                continue
            break
        status = "blocked" if not any(a.get("ok") for a in attempts) else "unresolved"
        return self._finish(req, run_id, started, status, None, route, attempts, total_cost, issues)

    # --- deterministic --------------------------------------------------------------------
    def _run_deterministic(self, req: TaskRequest, run_id: str, started: Any, route: RouteDecision) -> TaskResult:
        entry = self.handlers.get(req.task_kind)
        if entry is None:
            return self._finish(req, run_id, started, "unresolved", None, route, [], 0.0,
                                [f"no deterministic handler registered for {req.task_kind}"])
        version, handler = entry
        t0 = time.perf_counter()
        try:
            output = handler(req.payload)
            attempts = [{"tier": "C0", "handler_version": version, "ok": True,
                         "latency_ms": (time.perf_counter() - t0) * 1000}]
            return self._finish(req, run_id, started, "completed", output, route, attempts, 0.0, [])
        except (ValueError, KeyError, TypeError) as exc:
            attempts = [{"tier": "C0", "handler_version": version, "ok": False, "error": str(exc)}]
            return self._finish(req, run_id, started, "unresolved", None, route, attempts, 0.0, [str(exc)])

    # --- provider calls -------------------------------------------------------------------
    def _call_with_retries(self, profile: ModelProfile, system: str, prompt: str, max_out: int,
                           timeout_s: float) -> tuple[Completion | None, list[dict[str, Any]]]:
        provider = self.providers.get(profile.provider)
        log: list[dict[str, Any]] = []
        if provider is None:
            log.append({"profile_id": profile.profile_id, "ok": False, "error": "provider not configured"})
            return None, log
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                c = provider.complete(model=profile.model, system=system, prompt=prompt,
                                      max_output_tokens=max_out, timeout_s=timeout_s)
                log.append({"profile_id": profile.profile_id, "model": profile.model, "model_version": profile.version,
                            "ok": True, "attempt": attempt, "input_tokens": c.input_tokens,
                            "output_tokens": c.output_tokens, "cached_tokens": c.cached_tokens,
                            "cost_usd": profile.cost(c.input_tokens, c.output_tokens, c.cached_tokens),
                            "latency_ms": c.latency_ms or (time.perf_counter() - t0) * 1000,
                            "provider_request_id": c.provider_request_id})
                return c, log
            except ProviderError as exc:
                log.append({"profile_id": profile.profile_id, "model": profile.model, "ok": False,
                            "attempt": attempt, "error": str(exc), "error_kind": exc.kind})
                if not exc.retryable:
                    break
                if self.backoff_s:
                    time.sleep(self.backoff_s * (2 ** attempt))
        return None, log

    # --- validation -------------------------------------------------------------------------
    def _validate(self, text: str, req: TaskRequest) -> tuple[dict[str, Any] | None, list[str]]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            stripped = stripped[stripped.find("{"):] if "{" in stripped else stripped
        try:
            output = json.loads(stripped)
        except json.JSONDecodeError:
            return None, ["output is not valid JSON"]
        if not isinstance(output, dict):
            return None, ["output must be a JSON object"]
        problems = []
        policy = self.registry.policies.get(req.task_kind)
        for key, type_name in ((policy.output_schema or {}).items() if policy else ()):
            if key not in output:
                problems.append(f"missing field {key}")
            elif not isinstance(output[key], _TYPES[type_name]):
                problems.append(f"field {key} must be {type_name}")
        allowed = {r.get("id") for r in req.inputs}
        cited = output.get("source_refs")
        if isinstance(cited, list) and allowed:
            unknown = [c for c in cited if (c.get("id") if isinstance(c, dict) else c) not in allowed]
            if unknown:
                problems.append(f"cites sources not supplied: {unknown[:5]}")
        if output.get("confidence_probability") is not None:
            problems.append("uncalibrated probability of correctness is not permitted")
        return output, problems

    def _inputs_current(self, ctx: AccessContext, inputs: list[dict[str, Any]]) -> bool:
        tx = self.store.read()
        for ref in inputs:
            if ref.get("revision") is None:
                continue
            rec = tx.get(ctx.tenant_id, ref["kind"], ref["id"])
            if rec is None or rec.revision != ref["revision"] or rec.state.get("status") in ("stale", "quarantined"):
                return False
        return True

    # --- caching ----------------------------------------------------------------------------
    def _cache_key(self, req: TaskRequest, route: RouteDecision) -> str:
        return content_hash([req.ctx.tenant_id, req.task_kind, self.registry.version, route.profile.profile_id,
                             route.profile.version, req.prompt_version, req.system, req.prompt,
                             sorted((r.get("kind"), r.get("id"), r.get("revision")) for r in req.inputs)])[:40]

    def _cache_get(self, ctx: AccessContext, key: str, inputs: list[dict[str, Any]]) -> dict[str, Any] | None:
        rec = self.store.read().get(ctx.tenant_id, "model_cache", key)
        if rec is None:
            return None
        # Permissions and input freshness are rechecked on every read; a cache never revives revoked access.
        if inputs and not self.identity.check_derived(ctx, inputs):
            return None
        if not self._inputs_current(ctx, inputs):
            return None
        return rec.state["output"]

    def _cache_put(self, ctx: AccessContext, key: str, output: dict[str, Any], inputs: list[dict[str, Any]]) -> None:
        with self.store.transaction("gateway") as tx:
            current = tx.get(ctx.tenant_id, "model_cache", key)
            tx.put(ctx.tenant_id, "model_cache", key, {"output": output, "inputs": inputs},
                   expected_revision=current.revision if current else None, action="cache")
            for ref in inputs:
                tx.add_edge(ctx.tenant_id, (ref["kind"], ref["id"]), ("model_cache", key), "input_of")

    # --- trace ------------------------------------------------------------------------------
    def _scopes(self, req: TaskRequest) -> list[str]:
        scopes = [f"tenant:{req.ctx.tenant_id}"]
        if req.mission_id:
            scopes.append(f"mission:{req.mission_id}")
        if req.parent_run_id:
            scopes.append(f"run:{self._root_run(req)}")
        return scopes

    def _root_run(self, req: TaskRequest) -> str:
        tx = self.store.read()
        current = req.parent_run_id
        while current:
            parents = [i for k, i, rel in tx.edges_to(req.ctx.tenant_id, "model_run", current) if rel == "spawned"]
            if not parents:
                return current
            current = parents[0]
        return current or ""

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(len(text) // 4, 1)

    def _finish(self, req: TaskRequest, run_id: str, started: Any, status: str, output: dict[str, Any] | None,
                route: RouteDecision | None, attempts: list[dict[str, Any]], cost: float, issues: list[str],
                cached: bool = False) -> TaskResult:
        policy = self.registry.policies.get(req.task_kind)
        review = bool(policy and policy.requires_human_review) or bool(route and route.unqualified)
        finished = utc_now()
        queue_ms = None
        if req.queued_at:
            from ..ids import parse_iso
            queue_ms = (started - parse_iso(req.queued_at)).total_seconds() * 1000
        trace = {
            "run_id": run_id, "task_kind": req.task_kind, "status": status, "actor_id": req.ctx.actor_id,
            "mission_id": req.mission_id, "parent_run_id": req.parent_run_id,
            "route": route.to_dict() if route else None, "attempts": attempts, "cost_usd": round(cost, 8),
            "retries": max(len(attempts) - 1, 0), "issues": issues, "cached": cached,
            "prompt_version": req.prompt_version, "prompt_hash": content_hash(req.system + req.prompt)[:16],
            "input_manifest": req.inputs, "requires_human_review": review,
            "queued_at": req.queued_at, "started_at": iso(started), "finished_at": iso(finished),
            "queue_ms": queue_ms, "execution_ms": (finished - started).total_seconds() * 1000,
            "reviewer_minutes": 0.0,
        }
        with self.store.transaction(req.ctx.actor_id) as tx:
            tx.put(req.ctx.tenant_id, "model_run", run_id, trace, expected_revision=None, action="model_run",
                   event_type="gateway.run_finished",
                   event_payload={"run_id": run_id, "status": status, "task_kind": req.task_kind,
                                  "mission_id": req.mission_id})
            if req.parent_run_id:
                tx.add_edge(req.ctx.tenant_id, ("model_run", req.parent_run_id), ("model_run", run_id), "spawned")
        return TaskResult(run_id, status, output, route.to_dict() if route else {}, attempts, cost, issues,
                          review, cached)

    # --- reporting --------------------------------------------------------------------------
    def record_reviewer_effort(self, ctx: AccessContext, run_id: str, minutes: float, *, reviewer_id: str) -> None:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "model_run", run_id)
            tx.put(ctx.tenant_id, "model_run", run_id,
                   {**rec.state, "reviewer_minutes": rec.state.get("reviewer_minutes", 0.0) + minutes,
                    "reviewers": [*rec.state.get("reviewers", []), reviewer_id]},
                   expected_revision=rec.revision, action="reviewer_effort")

    def trace(self, tenant_id: str, run_id: str, *, reviewer_rate_per_hour: float = 0.0) -> dict[str, Any]:
        """Aggregate a run and all descendants: calls, retries, tokens, cost, latency and reviewer effort."""
        tx = self.store.read()
        stack, runs = [run_id], []
        while stack:
            rid = stack.pop()
            rec = tx.get(tenant_id, "model_run", rid)
            if rec is None:
                continue
            runs.append(rec.state)
            stack.extend(i for k, i, rel in tx.edges_from(tenant_id, "model_run", rid) if rel == "spawned")
        attempts = [a for r in runs for a in r["attempts"]]
        model_cost = sum(r["cost_usd"] for r in runs)
        reviewer_minutes = sum(r.get("reviewer_minutes", 0.0) for r in runs)
        starts = [r["started_at"] for r in runs]
        ends = [r["finished_at"] for r in runs]
        root = runs[0] if runs else {}
        from ..ids import parse_iso
        e2e_ms = None
        if runs:
            begin = parse_iso(root.get("queued_at") or min(starts))
            e2e_ms = (parse_iso(max(ends)) - begin).total_seconds() * 1000
        return {
            "run_id": run_id, "runs": len(runs), "model_calls": sum(1 for a in attempts if "model" in a),
            "failed_calls": sum(1 for a in attempts if not a.get("ok")),
            "retries": sum(r["retries"] for r in runs),
            "input_tokens": sum(a.get("input_tokens", 0) for a in attempts),
            "output_tokens": sum(a.get("output_tokens", 0) for a in attempts),
            "model_cost_usd": round(model_cost, 8), "reviewer_minutes": reviewer_minutes,
            "reviewer_cost_usd": round(reviewer_minutes / 60 * reviewer_rate_per_hour, 4),
            "total_cost_usd": round(model_cost + reviewer_minutes / 60 * reviewer_rate_per_hour, 6),
            "end_to_end_ms": e2e_ms, "route_reasons": sorted({(r["route"] or {}).get("reason", "") for r in runs}),
            "statuses": sorted({r["status"] for r in runs}),
        }
