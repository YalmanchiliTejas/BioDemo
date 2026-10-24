"""Cross-module scenario: drift signal -> mission -> deterministic analysis -> routed explanation ->
recommendation -> approval -> late correction -> reassessment -> dispatch -> outcome."""

from __future__ import annotations

import json

from src.lifesci.actions import DeliveryUnknown
from src.lifesci.container import Platform
from src.lifesci.evidence import EvidenceRef
from src.lifesci.gateway import FakeProvider, TaskRequest
from src.lifesci.gateway.registry import Qualification
from src.lifesci.ownership import Ownership
from src.lifesci.store import RecordStore

T = "tenant-e2e"


class MES:
    def __init__(self):
        self.applied, self.lose_next = {}, False

    def deliver(self, intent):
        self.applied[intent["idempotency_key"]] = {"ack": f"MES-{len(self.applied) + 1}"}
        if self.lose_next:
            self.lose_next = False
            raise DeliveryUnknown("timeout after send")
        return self.applied[intent["idempotency_key"]]

    def lookup(self, key):
        return self.applied.get(key)


def test_drift_to_outcome_scenario():
    fake = FakeProvider(name="anthropic")
    p = Platform(RecordStore(), providers={"anthropic": fake})
    for a, r in [("hist-svc", "operator"), ("msat1", "msat"), ("sup1", "supervisor")]:
        p.identity.assign_role(T, a, r, site_id="S1")
    p.identity.assign_role(T, "exec", "system_executor")
    p.ownership.assign(T, Ownership("place_hold", "S1", "external", "MES", ("place_hold",)), by="admin", reason="pilot")
    p.gateway.registry.qualify(Qualification("comparison_explanation", "anthropic-sonnet", "eval-cmp-1", True,
                                             {"citation_validity": 1.0}, {"citation_validity": 0.98}, "explanations", "p1"))
    ctx = lambda a: p.identity.context_for(T, a)  # noqa: E731

    mission = p.missions.start_or_resume(ctx("msat1"), objective="Watch bioreactor pH for campaign C7",
                                         owner_id="msat1", scope={"site_ids": ["S1"]},
                                         subscriptions=[{"type": "evidence.", "site_id": "S1"}], budget_usd=1.0)
    p.gateway.budgets.set_limit(T, f"mission:{mission['mission_id']}", 1.0)

    series = [7.00, 7.01, 6.99, 7.00, 7.01, 7.00, 6.99, 7.00, 6.98, 6.97, 6.96, 6.95, 6.94, 6.93, 6.92, 6.91]
    window = p.evidence.ingest(ctx("hist-svc"), source_system="HIST", source_record_id="BR1-pH-w1",
                               content=json.dumps(series).encode(), media_type="application/json", site_id="S1",
                               event_time="2026-10-20T00:00:00+00:00")
    assert len(p.missions.get(ctx("msat1"), mission["mission_id"])["pending_event_ids"]) == 1
    assert p.missions.deliver_events(T) == {}  # automatic delivery already routed this event
    act = p.missions.activate(ctx("msat1"), mission["mission_id"], "worker-1")

    stats = p.gateway.run(TaskRequest("statistics", ctx("msat1"), mission_id=mission["mission_id"], payload={
        "method": "detect_emerging_concern", "params": {"series": series, "spec_limits": [6.8, 7.2], "baseline_n": 8}}))
    assert stats.status == "completed", stats.issues
    assert stats.route["tier"] == "C0" and stats.cost_usd == 0 and fake.calls == []
    assert stats.output["result"]["status"] == "emerging_concern_not_deviation"

    ref = {"kind": "evidence", "id": window["evidence_id"], "revision": window["revision"], "site_id": "S1"}
    fake.scripts = {"claude-sonnet-5-5": [json.dumps({"explanation": "pH declining ~0.01/h since point 8; within spec.",
                                                      "source_refs": [window["evidence_id"]]})]}
    expl = p.gateway.run(TaskRequest("comparison_explanation", ctx("msat1"), prompt="Explain the trend",
                                     inputs=[ref], mission_id=mission["mission_id"], parent_run_id=stats.run_id))
    assert expl.status == "completed" and expl.route["model"] == "claude-sonnet-5-5"

    finding = p.evidence.record_derived(ctx("msat1"), "finding", {"text": expl.output["explanation"]},
                                        inputs=[EvidenceRef(**ref)], produced_by={"run_id": expl.run_id})
    p.missions.checkpoint(act, progress={"finding": finding["id"]}, consumed_event_ids=list(act.pending_event_ids),
                          findings=[{"finding_id": finding["id"]}])
    prop = p.actions.propose(ctx("msat1"), target_system="MES", operation="place_hold", target_id="BR1-batch-42",
                             payload={"reason": "emerging pH drift"}, basis=[ref], rationale=expl.output["explanation"],
                             expected_result="batch held before out-of-spec", owner_id="sup1",
                             follow_up_measure="hold_confirmed", site_id="S1", mission_id=mission["mission_id"])
    first = p.actions.decide(ctx("sup1"), prop["proposal_id"], expected_revision=1, decision="approved",
                             role="supervisor")

    # A corrected window arrives before dispatch: approval no longer authorizes the action.
    corrected = p.evidence.ingest(ctx("hist-svc"), source_system="HIST", source_record_id="BR1-pH-w1",
                                  content=json.dumps(series[:-1] + [6.90]).encode(), media_type="application/json",
                                  site_id="S1", event_time="2026-10-20T00:00:00+00:00")
    assert f"finding:{finding['id']}" in corrected["invalidated"]
    mes = MES()
    assert p.actions.dispatch(ctx("exec"), first["intent"]["intent_id"], mes)["status"] == "blocked" and not mes.applied

    new_ref = {**ref, "revision": corrected["revision"]}
    cur = p.store.read().get(T, "proposal", prop["proposal_id"])
    revised = p.actions.revise(ctx("msat1"), prop["proposal_id"], expected_revision=cur.revision,
                               changes={"basis": [new_ref]}, reason="re-based on corrected window")
    second = p.actions.decide(ctx("sup1"), prop["proposal_id"], expected_revision=revised["revision"],
                              decision="approved", role="supervisor")
    mes.lose_next = True
    assert p.actions.dispatch(ctx("exec"), second["intent"]["intent_id"], mes)["status"] == "unknown"
    assert p.actions.reconcile(ctx("exec"), second["intent"]["intent_id"], mes)["status"] == "delivered"
    assert len(mes.applied) == 1

    ack = p.evidence.ingest(ctx("hist-svc"), source_system="MES", source_record_id="hold-42", content=b"HELD",
                            media_type="text/plain", site_id="S1", event_time=None)
    p.actions.record_outcome(ctx("sup1"), prop["proposal_id"], observation="MES shows batch held", measure="hold_confirmed",
                             observed_value=True, evidence=[{"kind": "evidence", "id": ack["evidence_id"],
                                                             "revision": 1, "site_id": "S1"}],
                             attribution_limits="Confirms the hold only; product impact not yet observable.")
    assert p.actions.assess_effectiveness(ctx("sup1"), prop["proposal_id"], effective=True,
                                          rationale="hold in place")["effectiveness"] == "effective"

    trace = p.gateway.trace(T, stats.run_id)
    assert trace["runs"] == 2 and trace["model_calls"] == 1 and trace["model_cost_usd"] > 0
    spent = p.gateway.budgets.status(T, f"mission:{mission['mission_id']}")["spent"]
    assert abs(spent - trace["model_cost_usd"]) < 1e-6
    audit_actions = [a.action for a in p.store.read().audit(T, "proposal", prop["proposal_id"])]
    assert "propose" in audit_actions and "mark_stale" in audit_actions and "revise" in audit_actions
