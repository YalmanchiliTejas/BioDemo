from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from src.lifesci.actions import ActionService, DeliveryUnknown
from src.lifesci.evidence import EvidenceRef, EvidenceService
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.ids import utc_now
from src.lifesci.ownership import Ownership, OwnershipRegistry, OwnershipViolation
from src.lifesci.records import SignatureService
from src.lifesci.store import ConflictError, CrossTenantError, LeaseError, RecordStore

T = "tenant-a"
AUTH = {"method": "sso_reauth"}


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    own = OwnershipRegistry(s)
    ev = EvidenceService(s, idn)
    act = ActionService(s, idn, own)
    for actor, role, site in [("op1", "operator", "S1"), ("qa1", "qa", "S1"), ("qa2", "qa_reviewer", "S1"),
                              ("sup1", "supervisor", "S1"), ("op2", "operator", "S2")]:
        idn.assign_role(T, actor, role, site_id=site)
    idn.assign_role(T, "exec", "system_executor")
    idn.assign_role(T, "bot", "agent", actor_kind="agent")
    ctx = lambda a, kind="person": idn.context_for(T, a, actor_kind=kind)  # noqa: E731
    return SimpleNamespace(s=s, idn=idn, own=own, ev=ev, act=act, sig=SignatureService(s, idn), ctx=ctx)


def _evidence(env, rid="R1", content=b"pH=7.10", site="S1"):
    e = env.ev.ingest(env.ctx("op1"), source_system="LIMS", source_record_id=rid, content=content,
                      media_type="text/plain", site_id=site, event_time="2026-10-01T08:00:00+00:00")
    return {"kind": "evidence", "id": e["evidence_id"], "revision": e["revision"], "site_id": site}


class Writer:
    def __init__(self, mode="ok"):
        self.mode, self.sent = mode, {}

    def deliver(self, intent):
        if self.mode == "lost":
            self.sent[intent["idempotency_key"]] = {"ack": "ACK-1"}
            raise DeliveryUnknown("connection reset after send")
        if self.mode == "reject":
            raise RuntimeError("destination rejected")
        self.sent[intent["idempotency_key"]] = {"ack": f"ACK-{len(self.sent) + 1}"}
        return self.sent[intent["idempotency_key"]]

    def lookup(self, key):
        return self.sent.get(key)


# --- store -------------------------------------------------------------------------------
def test_store_optimistic_concurrency_and_audit(env):
    with env.s.transaction("u") as tx:
        tx.put(T, "thing", "1", {"v": 1}, expected_revision=None, action="create")
    with pytest.raises(ConflictError):
        with env.s.transaction("u") as tx:
            tx.put(T, "thing", "1", {"v": 2}, expected_revision=5, action="update")
    with env.s.transaction("u") as tx:
        tx.put(T, "thing", "1", {"v": 2}, expected_revision=1, action="update", reason="fix")
    tx = env.s.read()
    audit = tx.audit(T, "thing", "1")
    assert [a.action for a in audit] == ["update", "create"]
    assert audit[0].before_hash == audit[1].after_hash
    assert tx.revision(T, "thing", "1", 1).state == {"v": 1}


def test_store_rollback_discards_outbox(env):
    before = env.s.pending_outbox()
    with pytest.raises(RuntimeError):
        with env.s.transaction("u") as tx:
            tx.put(T, "thing", "x", {}, expected_revision=None, action="c", event_type="x.created")
            raise RuntimeError("boom")
    assert env.s.pending_outbox() == before and env.s.read().get(T, "thing", "x") is None


def test_store_transaction_bound_to_one_tenant(env):
    with pytest.raises(CrossTenantError):
        with env.s.transaction("u") as tx:
            tx.get(T, "thing", "1")
            tx.get("tenant-b", "thing", "1")


def test_LS084_fencing_tokens_reject_stale_worker(env):
    with env.s.transaction("u") as tx:
        t1 = tx.acquire_lease(T, "mission", "m", "w1", ttl_seconds=60)
    with pytest.raises(LeaseError):
        with env.s.transaction("u") as tx:
            tx.acquire_lease(T, "mission", "m", "w2")
    with env.s.transaction("u") as tx:
        tx.expire_lease(T, "mission", "m")
        t2 = tx.acquire_lease(T, "mission", "m", "w2")
    assert t2 > t1
    with pytest.raises(LeaseError):
        with env.s.transaction("u") as tx:
            tx.check_lease(T, "mission", "m", "w1", t1)


def test_outbox_at_least_once_and_inbox_dedup(env):
    _evidence(env)
    seen = []
    assert env.s.drain_outbox(seen.append) >= 1
    assert env.s.drain_outbox(seen.append) == 0
    with env.s.transaction("c") as tx:
        assert tx.inbox_claim("consumer", seen[0].event_id) is True
        assert tx.inbox_claim("consumer", seen[0].event_id) is False


# --- identity ----------------------------------------------------------------------------
def test_LS068_site_scope_and_revoked_grant(env):
    op2 = env.ctx("op2")
    assert not env.idn.check(op2, "read", "batch", "B1", site_id="S1")
    gid = env.idn.grant(T, grantee_id="op2", resource_kind="batch", resource_id="B1", actions=["read"], site_id="S1")
    # grants never widen a person outside their site scope
    assert not env.idn.check(op2, "read", "batch", "B1", site_id="S1")
    env.idn.grant(T, grantee_id="partner-x", resource_kind="batch", resource_id="B1", actions=["read"])
    partner = env.idn.context_for(T, "p-user", actor_kind="partner", partner_org_id="partner-x")
    assert env.idn.check(partner, "read", "batch", "B1", site_id="S1")
    assert not env.idn.check(partner, "read", "batch", "B2", site_id="S1")
    env.idn.revoke_grant(T, gid)
    for g in env.idn.live_grants(T, "partner-x"):
        env.idn.revoke_grant(T, g["grant_id"])
    assert not env.idn.check(partner, "read", "batch", "B1", site_id="S1")


def test_grant_expiry(env):
    env.idn.grant(T, grantee_id="partner-y", resource_kind="batch", resource_id="B9", actions=["read"],
                  expires_at=utc_now() - timedelta(seconds=1))
    partner = env.idn.context_for(T, "p", actor_kind="partner", partner_org_id="partner-y")
    assert not env.idn.check(partner, "read", "batch", "B9")


def test_LS025_agent_cannot_approve_or_hold_human_roles(env):
    bot = env.ctx("bot", "agent")
    assert not env.idn.check(bot, "approve", "proposal")
    with pytest.raises(PermissionError):
        env.idn.assign_role(T, "bot", "qa", actor_kind="agent")


def test_LS085_derived_access_requires_every_source(env):
    a = _evidence(env, "R1", site="S1")
    env.idn.assign_role(T, "op1", "operator", site_id="S2")
    b = _evidence(env, "R2", site="S2")
    summary = env.ev.record_derived(env.ctx("op1"), "summary", {"text": "mixed"},
                                    inputs=[EvidenceRef(**a), EvidenceRef(**b)], produced_by={"tier": "C0"})
    s1_only = env.ctx("qa1")
    with pytest.raises(PermissionError):
        env.ev.read_derived(s1_only, "summary", summary["id"])
    assert env.ev.read_derived(env.ctx("op1"), "summary", summary["id"])["text"] == "mixed"
    env.ev.quarantine_from(env.ctx("op1"), "evidence", b["id"], "source access revoked")
    with pytest.raises(PermissionError, match="quarantined"):
        env.ev.read_derived(env.ctx("op1"), "summary", summary["id"])
    assert not env.idn.check_derived(env.ctx("op1"), [])


# --- ownership ---------------------------------------------------------------------------
def test_LS062_read_default_and_explicit_write_scope(env):
    with pytest.raises(OwnershipViolation, match="projection"):
        env.own.check_write(T, "batch_record", "S1", "update", approval_ref="a1")
    env.own.assign(T, Ownership("deviation", "S1", "external", "QMS", ("submit_deviation",)), by="admin", reason="cfg")
    with pytest.raises(OwnershipViolation, match="write scope"):
        env.own.check_write(T, "deviation", "S1", "close_deviation", approval_ref="a1")
    with pytest.raises(OwnershipViolation, match="approval"):
        env.own.check_write(T, "deviation", "S1", "submit_deviation", approval_ref=None)
    assert env.own.check_write(T, "deviation", "S1", "submit_deviation", approval_ref="a1").system == "QMS"
    with pytest.raises(OwnershipViolation):
        env.own.check_native(T, "deviation", "S1")
    with pytest.raises(ValueError):
        env.own.assign(T, Ownership("batch_record", "S1", "native", None, ()), by="a", reason="no intended use")


# --- signatures ---------------------------------------------------------------------------
def test_LS002_signature_binds_exact_revision(env):
    with env.s.transaction("op1") as tx:
        tx.put(T, "step_execution", "X1", {"value": 7.1, "site_id": "S1"}, expected_revision=None, action="perform")
    op = env.ctx("op1")
    with pytest.raises(PermissionError, match="authenticated"):
        env.sig.sign(op, "step_execution", "X1", expected_revision=1, meaning="performed", site_id="S1")
    sig = env.sig.sign(op, "step_execution", "X1", expected_revision=1, meaning="performed",
                       authentication=AUTH, site_id="S1")
    assert env.sig.verify(T, sig.signature_id)["covers_current_content"]
    with env.s.transaction("op1") as tx:
        tx.put(T, "step_execution", "X1", {"value": 7.3, "site_id": "S1"}, expected_revision=1, action="edit")
    v = env.sig.verify(T, sig.signature_id)
    assert v["binding_intact"] and not v["covers_current_content"]
    assert env.sig.required_signatures_present(T, "step_execution", "X1", ["performed"]) == {"performed": False}
    with pytest.raises(ConflictError):
        env.sig.sign(op, "step_execution", "X1", expected_revision=1, meaning="performed", authentication=AUTH,
                     site_id="S1")
    with pytest.raises(AuthorizationError):
        env.sig.sign(env.ctx("op2"), "step_execution", "X1", expected_revision=2, meaning="witnessed",
                     authentication=AUTH, site_id="S1")
    assert [a.action for a in env.s.read().audit(T, "step_execution", "X1")] == ["edit", "perform"]


# --- evidence ---------------------------------------------------------------------------
def test_LS028_original_bytes_digest_and_idempotent_ingest(env):
    ref = _evidence(env)
    again = env.ev.ingest(env.ctx("op1"), source_system="LIMS", source_record_id="R1", content=b"pH=7.10",
                          media_type="text/plain", site_id="S1", event_time=None, mapping_version="m1")
    assert again["duplicate"] and again["revision"] == 1
    assert env.ev.original(env.ctx("op1"), ref["id"]) == b"pH=7.10"
    rec = env.s.read().get(T, "evidence", ref["id"]).state
    assert rec["digest"] and rec["recorded_at"] and rec["event_time"]


def test_LS063_normalized_value_lineage(env):
    ref = _evidence(env)
    val = env.ev.normalize(env.ctx("op1"), evidence=EvidenceRef(**ref), field="temperature", raw_value="98.6",
                           raw_unit="degF", value=37.0, unit="degC", time_basis="event_time", transform="pint",
                           transform_version="0.26", location={"cell": "B4"})
    assert val["evidence"]["id"] == ref["id"] and val["raw_unit"] == "degF" and val["transform_version"] == "0.26"
    env.ev.ingest(env.ctx("op1"), source_system="LIMS", source_record_id="R1", content=b"pH=7.30",
                  media_type="text/plain", site_id="S1", event_time=None)
    assert env.s.read().get(T, "normalized_value", val["id"]).state["status"] == "stale"


def test_LS052_LS054_correction_invalidates_dependents_only(env):
    a, b = _evidence(env, "R1"), _evidence(env, "R2", b"temp=37")
    op = env.ctx("op1")
    fa = env.ev.record_derived(op, "finding", {"text": "pH trend"}, inputs=[EvidenceRef(**a)], produced_by={})
    fb = env.ev.record_derived(op, "finding", {"text": "temp ok"}, inputs=[EvidenceRef(**b)], produced_by={})
    rec = env.ev.record_derived(op, "recommendation", {"text": "adjust"},
                                inputs=[EvidenceRef("finding", fa["id"], 1, "S1")], produced_by={})
    out = env.ev.ingest(op, source_system="LIMS", source_record_id="R1", content=b"pH=6.90", media_type="text/plain",
                        site_id="S1", event_time=None)
    assert out["revision"] == 2
    tx = env.s.read()
    assert tx.get(T, "finding", fa["id"]).state["status"] == "stale"
    assert tx.get(T, "recommendation", rec["id"]).state["status"] == "stale"
    assert tx.get(T, "finding", fb["id"]).state["status"] == "current"


def test_as_of_prevents_future_leakage(env):
    _evidence(env)
    assert env.ev.available_as_of(env.ctx("op1"), "2000-01-01T00:00:00+00:00") == []
    assert len(env.ev.available_as_of(env.ctx("op1"), "2999-01-01T00:00:00+00:00")) == 1


# --- actions -----------------------------------------------------------------------------
def _hold(env, basis):
    env.own.assign(T, Ownership("place_hold", "S1", "external", "MES", ("place_hold",)), by="admin", reason="cfg")
    return env.act.propose(env.ctx("op1"), target_system="MES", operation="place_hold", target_id="B1",
                           payload={"reason": "pH drift"}, basis=[basis], rationale="pH trending low",
                           expected_result="batch held pending review", owner_id="sup1",
                           follow_up_measure="hold_confirmed", site_id="S1")


def test_LS059_LS086_exact_version_approval_and_dispatch(env):
    basis = _evidence(env)
    p = _hold(env, basis)
    with pytest.raises(AuthorizationError):
        env.act.decide(env.ctx("op1"), p["proposal_id"], expected_revision=1, decision="approved", role="supervisor")
    with pytest.raises(AuthorizationError):
        env.act.decide(env.ctx("bot", "agent"), p["proposal_id"], expected_revision=1, decision="approved",
                       role="supervisor")
    revised = env.act.revise(env.ctx("op1"), p["proposal_id"], expected_revision=1,
                             changes={"payload": {"reason": "pH drift", "scope": "B1+B2"}}, reason="scope")
    with pytest.raises(ConflictError):  # approver reviewed revision 1; content changed
        env.act.decide(env.ctx("sup1"), p["proposal_id"], expected_revision=1, decision="approved", role="supervisor")
    out = env.act.decide(env.ctx("sup1"), p["proposal_id"], expected_revision=revised["revision"],
                         decision="approved", role="supervisor")
    intent = out["intent"]
    assert out["proposal"]["status"] == "approved" and intent["content_hash"] == revised["content_hash"]
    w = Writer()
    with pytest.raises(AuthorizationError):
        env.act.dispatch(env.ctx("op1"), intent["intent_id"], w)
    assert env.act.dispatch(env.ctx("exec"), intent["intent_id"], w)["status"] == "delivered"
    assert env.act.dispatch(env.ctx("exec"), intent["intent_id"], w)["status"] == "blocked"
    assert len(w.sent) == 1


def test_LS086_changed_evidence_blocks_queued_intent(env):
    basis = _evidence(env)
    p = _hold(env, basis)
    intent = env.act.decide(env.ctx("sup1"), p["proposal_id"], expected_revision=1, decision="approved",
                            role="supervisor")["intent"]
    env.ev.ingest(env.ctx("op1"), source_system="LIMS", source_record_id="R1", content=b"pH=7.40",
                  media_type="text/plain", site_id="S1", event_time=None)
    tx = env.s.read()
    assert tx.get(T, "proposal", p["proposal_id"]).state["status"] == "stale"
    assert tx.get(T, "action_intent", intent["intent_id"]).state["status"] == "awaiting_reassessment"
    w = Writer()
    assert env.act.dispatch(env.ctx("exec"), intent["intent_id"], w)["status"] == "blocked" and not w.sent


def test_LS086_revoked_approver_blocks_dispatch_and_sent_ops_flagged(env):
    basis = _evidence(env)
    p = _hold(env, basis)
    intent = env.act.decide(env.ctx("sup1"), p["proposal_id"], expected_revision=1, decision="approved",
                            role="supervisor")["intent"]
    env.idn.revoke_role(T, "sup1", "supervisor", site_id="S1")
    res = env.act.dispatch(env.ctx("exec"), intent["intent_id"], Writer())
    assert res["status"] == "blocked" and any("no longer holds" in r for r in res["reasons"])

    env.idn.assign_role(T, "sup2", "supervisor", site_id="S1")
    b2 = _evidence(env, "R5", b"x")
    p2 = env.act.propose(env.ctx("op1"), target_system="MES", operation="place_hold", target_id="B2", payload={},
                         basis=[b2], rationale="r", expected_result="e", owner_id="sup2", site_id="S1")
    i2 = env.act.decide(env.ctx("sup2"), p2["proposal_id"], expected_revision=1, decision="approved",
                        role="supervisor")["intent"]
    assert env.act.dispatch(env.ctx("exec"), i2["intent_id"], Writer())["status"] == "delivered"
    env.ev.ingest(env.ctx("op1"), source_system="LIMS", source_record_id="R5", content=b"y", media_type="text/plain",
                  site_id="S1", event_time=None)
    sent = env.s.read().get(T, "action_intent", i2["intent_id"]).state
    assert sent["status"] == "delivered" and sent["needs_reassessment"] is True


def test_V08_lost_response_reconciled_without_duplicate(env):
    basis = _evidence(env)
    p = _hold(env, basis)
    intent = env.act.decide(env.ctx("sup1"), p["proposal_id"], expected_revision=1, decision="approved",
                            role="supervisor")["intent"]
    w = Writer("lost")
    assert env.act.dispatch(env.ctx("exec"), intent["intent_id"], w)["status"] == "unknown"
    assert env.act.dispatch(env.ctx("exec"), intent["intent_id"], w)["status"] == "blocked"
    with pytest.raises(ValueError):
        env.act.requeue_failed(env.ctx("exec"), intent["intent_id"], "retry")
    assert env.act.reconcile(env.ctx("exec"), intent["intent_id"], w)["status"] == "delivered"
    assert len(w.sent) == 1


def test_high_risk_requires_reauthentication_and_all_roles(env):
    basis = _evidence(env)
    env.own.assign(T, Ownership("release_batch", "S1", "external", "MES", ("release_batch",)), by="a", reason="c")
    p = env.act.propose(env.ctx("op1"), target_system="MES", operation="release_batch", target_id="B1", payload={},
                        basis=[basis], rationale="r", expected_result="e", owner_id="qa1", site_id="S1")
    assert p["risk"] == "critical" and set(p["required_roles"]) == {"qa", "qa_reviewer"}
    with pytest.raises(PermissionError, match="re-authentication"):
        env.act.decide(env.ctx("qa1"), p["proposal_id"], expected_revision=1, decision="approved", role="qa")
    r1 = env.act.decide(env.ctx("qa1"), p["proposal_id"], expected_revision=1, decision="approved", role="qa",
                        authentication=AUTH)
    assert r1["proposal"]["status"] == "proposed" and r1["intent"] is None
    r2 = env.act.decide(env.ctx("qa2"), p["proposal_id"], expected_revision=r1["proposal"]["revision"],
                        decision="approved", role="qa_reviewer", authentication=AUTH)
    assert r2["proposal"]["status"] == "approved" and r2["intent"]


def test_LS060_LS065_outcome_separate_and_effectiveness_gated(env):
    basis = _evidence(env)
    p = _hold(env, basis)
    pid = p["proposal_id"]
    intent = env.act.decide(env.ctx("sup1"), pid, expected_revision=1, decision="approved", role="supervisor")["intent"]
    with pytest.raises(ValueError, match="delivered"):
        env.act.assess_effectiveness(env.ctx("sup1"), pid, effective=True, rationale="early")
    env.act.dispatch(env.ctx("exec"), intent["intent_id"], Writer())
    with pytest.raises(ValueError, match="follow-up measure"):
        env.act.assess_effectiveness(env.ctx("sup1"), pid, effective=True, rationale="no evidence")
    obs = _evidence(env, "R9", b"hold=confirmed")
    outcome = env.act.record_outcome(env.ctx("op1"), pid, observation="MES shows hold", measure="hold_confirmed",
                                     observed_value=True, evidence=[obs],
                                     attribution_limits="hold confirmed; effect on quality not yet observable")
    assert outcome["expected_result"] != outcome["observation"]
    with pytest.raises(AuthorizationError):
        env.act.assess_effectiveness(env.ctx("bot", "agent"), pid, effective=True, rationale="x")
    done = env.act.assess_effectiveness(env.ctx("sup1"), pid, effective=True, rationale="hold in place")
    assert done["effectiveness"] == "effective" and done["status"] == "approved"


def test_nested_service_calls_commit_atomically(env):
    basis = _evidence(env)
    env.own.assign(T, Ownership("place_hold", "S1", "external", "MES", ("place_hold",)), by="a", reason="c")
    with pytest.raises(RuntimeError):
        with env.s.transaction("op1") as tx:
            tx.put(T, "batch", "B1", {"site_id": "S1", "status": "hold_requested"}, expected_revision=None, action="c")
            env.act.propose(env.ctx("op1"), target_system="MES", operation="place_hold", target_id="B1", payload={},
                            basis=[basis], rationale="r", expected_result="e", owner_id="sup1", site_id="S1")
            raise RuntimeError("crash before commit")
    tx = env.s.read()
    assert tx.get(T, "batch", "B1") is None and tx.list(T, "proposal") == []  # no orphan proposal
