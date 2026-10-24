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
from .gateway.router import RoutingError
from .ids import new_id, utc_now


class Harness(Protocol):
    model: str | None

    def run(self, *, incident_id: str, problem: str, new_evidence_ids: list[str], as_of: str) -> dict[str, Any]: ...


class PrimeInvestigationAdapter:
    TASK_KIND = "investigation_planning"

    def __init__(self, gateway: ModelGateway, harness: Harness, *, max_cost_usd: float = 5.0) -> None:
        self.gateway = gateway
        self.harness = harness
        self.max_cost_usd = max_cost_usd

    def run(self, req: TaskRequest, *, incident_id: str, as_of: str, evidence_ids: list[str]) -> dict[str, Any]:
        started = utc_now()
        run_id = new_id("run")
        try:
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
                         "cost_coverage": "prime_root_session_only"}]
            status = "completed"
            output = {"report_ref": {"incident_id": incident_id}, "review_status": "requires_human_review"}
        except Exception as exc:  # harness failure: record honestly, keep mission resumable
            attempts = [{"profile_id": route.profile.profile_id, "ok": False, "harness": "prime", "error": str(exc)}]
            status, output = "blocked", None
        finally:
            self.gateway.budgets.settle(req.ctx.tenant_id, reservation, actual)
        res = self.gateway._finish(req, run_id, started, status, output, route, attempts, actual, [])
        return {"status": status, "run_id": res.run_id, "model": self.harness.model, "cost_usd": actual}
