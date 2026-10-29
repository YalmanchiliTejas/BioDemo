"""Routes long investigations to the existing Prime runtime through the gateway (D08).

Prime remains the reasoning harness for open-ended investigations; the gateway
decides which qualified model it may use, reserves budget, and records the run
(including Prime's reported usage) in the same trace/budget ledger as every other
task. Previously one ``BIODEMO_PRIME_MODEL`` was used for the whole session with
no routing or spend enforcement.
"""

from __future__ import annotations

from typing import Any, Protocol

from .gateway import ModelGateway, TaskRequest
from .gateway.budget import BudgetExceeded
from .gateway.router import RoutingError, RouteDecision
from .gateway.registry import ModelProfile
from .ids import new_id, utc_now


class Harness(Protocol):
    model: str | None

    def run(self, *, incident_id: str, problem: str, new_evidence_ids: list[str], as_of: str) -> dict[str, Any]: ...


class PrimeInvestigationAdapter:
    TASK_KIND = "investigation_planning"

    def __init__(self, gateway: ModelGateway, harness: Harness, *, max_cost_usd: float = 5.0,
                 research_profile: ModelProfile | None = None) -> None:
        self.gateway = gateway
        self.harness = harness
        self.max_cost_usd = max_cost_usd
        # Explicit opt-in for read-only case studies. Never qualifies or changes a production route.
        self.research_profile = research_profile

    def run(self, req: TaskRequest, *, incident_id: str, as_of: str, evidence_ids: list[str]) -> dict[str, Any]:
        started = utc_now()
        run_id = new_id("run")
        try:
            if self.research_profile:
                route = RouteDecision(self.TASK_KIND, self.research_profile.tier, self.research_profile,
                    'Read-only research route; no task qualification claimed', self.gateway.registry.version,
                    unqualified=True, notes=('Research draft only; independent engineering review required.',
                        'Hosted compute billing is unavailable; token usage and wall time are recorded.'))
            else:
                route = self.gateway.router.route(self.TASK_KIND, ambiguity=req.ambiguity,
                                                  unavailable=self.gateway.unavailable)
        except RoutingError as exc:
            self.gateway._finish(req, run_id, started, "unresolved", None, None, [], 0.0, [str(exc)])
            return {"status": "unresolved", "run_id": run_id, "issues": [str(exc)]}
        try:
            reservation = self.gateway.budgets.reserve(req.ctx.tenant_id, self.gateway._scopes(req), self.max_cost_usd)
        except BudgetExceeded as exc:
            self.gateway._finish(req, run_id, started, "budget_exhausted", None, route, [], 0.0, [str(exc)])
            return {"status": "budget_exhausted", "run_id": run_id, "issues": [str(exc)]}
        self.harness.model = f"{route.profile.provider}/{route.profile.model}"
        actual = 0.0
        try:
            result = self.harness.run(incident_id=incident_id, problem=req.prompt, new_evidence_ids=evidence_ids,
                                      as_of=as_of)
            metrics = result.get("rollout_metrics", {})
            usage = metrics.get("usage") or {}
            reported = metrics.get("root_reported_cost_usd")
            actual = float(reported) if reported is not None else route.profile.cost(
                int(usage.get("input", 0)), int(usage.get("output", 0)), int(usage.get("cacheRead", 0)))
            attempts = [{"profile_id": route.profile.profile_id, "model": route.profile.model, "ok": True,
                         "harness": "prime", "input_tokens": int(usage.get("input", 0)),
                         "output_tokens": int(usage.get("output", 0)), "cost_usd": actual,
                         "cost_coverage": "hosted_billing_unavailable" if self.research_profile else "prime_root_session_only"}]
            if self.research_profile:
                attempts[0]['cost_usd'] = None
            status = "completed"
            output = {"report_ref": {"incident_id": incident_id}, "review_status": "requires_human_review"}
        except Exception as exc:  # harness failure: record honestly, keep mission resumable
            attempts = [{"profile_id": route.profile.profile_id, "ok": False, "harness": "prime", "error": str(exc)}]
            status, output = "blocked", None
        finally:
            self.gateway.budgets.settle(req.ctx.tenant_id, reservation, actual)
        res = self.gateway._finish(req, run_id, started, status, output, route, attempts, actual, [])
        return {"status": status, "run_id": res.run_id, "model": self.harness.model,
                "cost_usd": None if self.research_profile else actual,
                "research_only": bool(self.research_profile), "requires_human_review": True,
                "issues": [a['error'] for a in attempts if a.get('error')]}
