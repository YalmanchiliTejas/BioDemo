from __future__ import annotations

from src.lifesci.gateway import FakeProvider, ModelGateway, TaskRequest, default_registry
from src.lifesci.gateway.registry import Qualification
from src.lifesci.identity import IdentityService
from src.lifesci.prime_adapter import PrimeInvestigationAdapter
from src.lifesci.store import RecordStore

T = "tenant-a"


class FakeHarness:
    def __init__(self, fail=False):
        self.model, self.fail, self.calls = None, fail, []

    def run(self, **kw):
        self.calls.append((self.model, kw))
        if self.fail:
            raise RuntimeError("prime bundle missing")
        return {"rollout_metrics": {"usage": {"input": 100_000, "output": 20_000}, "root_reported_cost_usd": None}}


def setup(harness):
    s = RecordStore()
    idn = IdentityService(s)
    idn.assign_role(T, "msat1", "msat", site_id="S1")
    reg = default_registry()
    reg.qualify(Qualification("investigation_planning", "anthropic-opus", "eval-inv", True, {"r": 1}, {"r": 0.9},
                              "investigations", "p1"))
    gw = ModelGateway(s, idn, reg, {"anthropic": FakeProvider(name="anthropic")})
    return gw, PrimeInvestigationAdapter(gw, harness, max_cost_usd=10), idn.context_for(T, "msat1")


def test_prime_uses_routed_model_and_records_cost_in_mission_budget():
    h = FakeHarness()
    gw, adapter, ctx = setup(h)
    gw.budgets.set_limit(T, "mission:m1", 20)
    out = adapter.run(TaskRequest("investigation_planning", ctx, prompt="why low titer", mission_id="m1"),
                      incident_id="INC-1", as_of="2026-10-01T00:00:00+00:00", evidence_ids=["E1"])
    assert out["status"] == "completed" and h.calls[0][0] == "anthropic/claude-opus-5-5"
    assert abs(out["cost_usd"] - (100_000 * 4 + 20_000 * 20) / 1e6) < 1e-9
    st = gw.budgets.status(T, "mission:m1")
    assert st["reserved"] == 0 and abs(st["spent"] - out["cost_usd"]) < 1e-9
    assert gw.trace(T, out["run_id"])["model_cost_usd"] == round(out["cost_usd"], 8)


def test_prime_budget_and_failure_are_honest():
    h = FakeHarness(fail=True)
    gw, adapter, ctx = setup(h)
    gw.budgets.set_limit(T, "mission:m2", 1)
    assert adapter.run(TaskRequest("investigation_planning", ctx, mission_id="m2"), incident_id="I", as_of="x",
                       evidence_ids=[])["status"] == "budget_exhausted"
    assert h.calls == []
    gw.budgets.set_limit(T, "mission:m2", 100)
    assert adapter.run(TaskRequest("investigation_planning", ctx, mission_id="m2"), incident_id="I", as_of="x",
                       evidence_ids=[])["status"] == "blocked"
    assert gw.budgets.status(T, "mission:m2")["reserved"] == 0


def test_hosted_research_route_does_not_qualify_or_enable_production():
    from src.lifesci.gateway.registry import ModelProfile
    from src.lifesci.gateway.router import RoutingError
    import pytest
    h = FakeHarness()
    gw, _, ctx = setup(h)
    gw.registry.suspend('investigation_planning','anthropic-opus')
    profile = ModelProfile('modal-research','modal','hosted-model','M3',0,0,0,
                           price_source='Unknown hosted compute billing')
    adapter = PrimeInvestigationAdapter(gw,h,research_profile=profile)
    out = adapter.run(TaskRequest('investigation_planning',ctx),incident_id='research',as_of='x',evidence_ids=[])
    assert out['status']=='completed' and h.model=='modal/hosted-model'
    assert out['research_only'] and out['requires_human_review'] and out['cost_usd'] is None
    record=gw.store.read().require(T,'model_run',out['run_id']).state
    assert record['route']['unqualified'] and record['attempts'][0]['cost_usd'] is None
    assert not gw.registry.qualifications and 'modal-research' not in gw.registry.profiles
    with pytest.raises(RoutingError): gw.router.route('investigation_planning')
    strict=PrimeInvestigationAdapter(gw,h)
    assert strict.run(TaskRequest('investigation_planning',ctx),incident_id='production',as_of='x',evidence_ids=[])['status']=='unresolved'
