"""Proposals -> version-bound approvals -> action intents -> delivery -> reconciliation -> outcomes.

Each stage is a distinct durable object (Easy to Act; LS-059, LS-060, LS-065,
LS-086). An approval binds the exact proposal revision and content hash; any
material change requires new approval (D17). Agents can propose but never
approve (LS-025). Before dispatch the intent atomically revalidates proposal
content, evidence basis, approver authority and record ownership, then claims
a fencing token. An unknown external outcome is reconciled, never blindly
retried (V08). Observed outcomes are stored apart from expected benefit.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from .evidence import STATUS_CURRENT
from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import content_hash, iso, new_id, utc_now
from .ownership import OwnershipRegistry
from .store import ConflictError, RecordStore, Transaction

RISK_POLICY: dict[str, tuple[str, tuple[str, ...]]] = {
    "release_batch": ("critical", ("qa", "qa_reviewer")),
    "reject_batch": ("critical", ("qa", "qa_reviewer")),
    "invalidate_result": ("critical", ("qa", "qa_reviewer")),
    "close_deviation": ("high", ("qa",)),
    "approve_capa": ("high", ("qa",)),
    "change_specification": ("high", ("qa",)),
    "quarantine_lot": ("high", ("qa",)),
    "change_recipe_parameter": ("high", ("qa", "msat")),
    "publish_procedure": ("high", ("qa",)),
    "submit_deviation": ("medium", ("qa",)),
    "reschedule_batch": ("medium", ("supervisor",)),
    "create_work_order": ("medium", ("supervisor",)),
    "request_retest": ("medium", ("supervisor",)),
    "place_hold": ("medium", ("supervisor",)),
    "reserve_material": ("medium", ("supply_chain",)),
    "send_notification": ("low", ("supervisor",)),
}
DEFAULT_RISK = ("medium", ("supervisor",))

CONTENT_FIELDS = ("target_system", "operation", "target_id", "payload", "basis", "site_id", "record_class")


class DeliveryUnknown(Exception):
    """The destination may or may not have applied the operation (lost response)."""


class Writer(Protocol):
    def deliver(self, intent: dict[str, Any]) -> dict[str, Any]: ...
    def lookup(self, idempotency_key: str) -> dict[str, Any] | None: ...


def _content(state: dict[str, Any]) -> dict[str, Any]:
    return {k: state.get(k) for k in CONTENT_FIELDS}


class ActionService:
    def __init__(self, store: RecordStore, identity: IdentityService, ownership: OwnershipRegistry) -> None:
        self.store = store
        self.identity = identity
        self.ownership = ownership

    # --- proposals --------------------------------------------------------------
    def propose(self, ctx: AccessContext, *, target_system: str, operation: str, target_id: str,
                payload: dict[str, Any], basis: list[dict[str, Any]], rationale: str, expected_result: str,
                owner_id: str, follow_up_measure: str | None = None, constraints: list[str] | None = None,
                change_evidence: str | None = None, site_id: str | None = None, record_class: str | None = None,
                mission_id: str | None = None) -> dict[str, Any]:
        """Create a proposal. No side effect occurs; risk and required roles come from policy, not the caller."""
        self.identity.require(ctx, "propose", "proposal", site_id=site_id)
        if not basis:
            raise ValueError("a proposal requires at least one evidence reference in its basis")
        if not self.identity.check_derived(ctx, basis):
            raise PermissionError("proposer cannot read every basis source")
        risk, roles = RISK_POLICY.get(operation, DEFAULT_RISK)
        proposal_id = new_id("prop")
        state = {
            "proposal_id": proposal_id, "target_system": target_system, "operation": operation,
            "target_id": target_id, "payload": payload, "basis": basis, "site_id": site_id,
            "record_class": record_class or operation, "rationale": rationale, "expected_result": expected_result,
            "constraints": constraints or [], "owner_id": owner_id, "follow_up_measure": follow_up_measure,
            "would_change_recommendation": change_evidence, "risk": risk, "required_roles": list(roles),
            "requested_by": ctx.actor_id, "requested_by_kind": ctx.actor_kind, "mission_id": mission_id,
            "status": "proposed",  # proposed | approved | rejected | stale | withdrawn
            "execution_status": "not_started", "effectiveness": "unknown", "stale_reasons": [],
            "created_at": iso(utc_now()),
        }
        state["content_hash"] = content_hash(_content(state))
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "proposal", proposal_id, state, expected_revision=None, action="propose",
                   event_type="action.proposed",
                   event_payload={"proposal_id": proposal_id, "operation": operation, "risk": risk,
                                  "mission_id": mission_id, "site_id": site_id})
            for ref in basis:
                tx.add_edge(ctx.tenant_id, (ref["kind"], ref["id"]), ("proposal", proposal_id), "basis_of")
        return state

    def revise(self, ctx: AccessContext, proposal_id: str, *, expected_revision: int,
               changes: dict[str, Any], reason: str) -> dict[str, Any]:
        """Material change -> new content hash; prior approvals no longer authorize the proposal."""
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "proposal", proposal_id)
            if rec.revision != expected_revision:
                raise ConflictError(f"proposal at revision {rec.revision}")
            self.identity.require(ctx, "propose", "proposal", proposal_id, site_id=rec.state.get("site_id"), tx=tx)
            if rec.state["execution_status"] not in ("not_started", "queued", "awaiting_reassessment"):
                raise ValueError("cannot revise a proposal whose intent has been dispatched")
            state = {**rec.state, **{k: v for k, v in changes.items() if k in CONTENT_FIELDS + (
                "rationale", "expected_result", "constraints", "follow_up_measure", "owner_id")}}
            if "basis" in changes:
                for ref in changes["basis"]:
                    tx.add_edge(ctx.tenant_id, (ref["kind"], ref["id"]), ("proposal", proposal_id), "basis_of")
            state["content_hash"] = content_hash(_content(state))
            material = state["content_hash"] != rec.state["content_hash"]
            if material or rec.state["status"] == "stale":
                state["status"] = "proposed"
                state["execution_status"] = "not_started"
            self._cancel_queued_intents(tx, ctx.tenant_id, proposal_id, "proposal revised")
            out = tx.put(ctx.tenant_id, "proposal", proposal_id, state, expected_revision=rec.revision,
                         action="revise", reason=reason, event_type="action.revised",
                         event_payload={"proposal_id": proposal_id, "material": material,
                                        "mission_id": state.get("mission_id")})
        return {**out.state, "revision": out.revision}

    # --- approvals ---------------------------------------------------------------
    def decide(self, ctx: AccessContext, proposal_id: str, *, expected_revision: int, decision: str, role: str,
               comment: str | None = None, authentication: dict[str, Any] | None = None) -> dict[str, Any]:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be approved or rejected")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "proposal", proposal_id)
            p = rec.state
            if rec.revision != expected_revision:
                raise ConflictError(f"proposal changed: now revision {rec.revision}; review the current content")
            if p["status"] == "stale":
                raise ValueError("proposal basis changed; it must be reassessed and revised before decision")
            if p["status"] not in ("proposed",):
                raise ValueError(f"proposal is {p['status']}")
            if ctx.actor_kind == "agent":
                raise AuthorizationError(Decision(False, "agent credentials cannot approve proposals"))
            if ctx.actor_id == p["requested_by"]:
                raise AuthorizationError(Decision(False, "requesters cannot approve their own proposals"))
            if role not in ctx.roles or role not in p["required_roles"]:
                raise AuthorizationError(Decision(False, f"role {role} not held or not required"))
            self.identity.require(ctx, "approve", "proposal", proposal_id, site_id=p.get("site_id"), tx=tx)
            scoped = self.identity.context_for(ctx.tenant_id, ctx.actor_id, role=role)
            self.identity.require(scoped, "approve", "proposal", proposal_id, site_id=p.get("site_id"), tx=tx)
            if p["risk"] in ("high", "critical") and not (authentication or {}).get("method"):
                raise PermissionError("high-risk approval requires re-authentication (authentication.method)")
            approvals = self._approvals(tx, ctx.tenant_id, proposal_id, p["content_hash"])
            if any(a["role"] == role for a in approvals):
                raise ValueError(f"role {role} already decided this revision")
            approval_id = new_id("appr")
            approval = {"approval_id": approval_id, "proposal_id": proposal_id, "proposal_revision": rec.revision,
                        "content_hash": p["content_hash"], "actor_id": ctx.actor_id, "role": role,
                        "decision": decision, "comment": comment, "decided_at": iso(utc_now()),
                        "authentication": {"method": (authentication or {}).get("method", "session")}}
            tx.put(ctx.tenant_id, "approval", approval_id, approval, expected_revision=None, action=decision,
                   event_type=f"action.{decision}", event_payload={"proposal_id": proposal_id, "role": role,
                                                                   "mission_id": p.get("mission_id")})
            approvals.append(approval)
            approved_roles = {a["role"] for a in approvals if a["decision"] == "approved"}
            status = p["status"]
            intent = None
            if decision == "rejected":
                status = "rejected"
            elif set(p["required_roles"]) <= approved_roles:
                status = "approved"
                intent = self._create_intent(tx, ctx.tenant_id, rec.revision, p, approvals)
            out = tx.put(ctx.tenant_id, "proposal", proposal_id, {**p, "status": status,
                                                                    "execution_status": "queued" if intent else p["execution_status"]},
                         expected_revision=rec.revision, action="status", event_type="action.status",
                         event_payload={"proposal_id": proposal_id, "status": status,
                                        "mission_id": p.get("mission_id")})
        return {"proposal": {**out.state, "revision": out.revision}, "approval": approval, "intent": intent}

    def _approvals(self, tx: Transaction, tenant_id: str, proposal_id: str, content_hash_: str) -> list[dict[str, Any]]:
        return [r.state for r in tx.find(tenant_id, "approval", "proposal_id", proposal_id)
                if r.state["content_hash"] == content_hash_]

    def _create_intent(self, tx: Transaction, tenant_id: str, revision: int, p: dict[str, Any],
                       approvals: list[dict[str, Any]]) -> dict[str, Any]:
        intent_id = new_id("intent")
        intent = {"intent_id": intent_id, "proposal_id": p["proposal_id"], "proposal_revision": revision + 1,
                  "content_hash": p["content_hash"], "target_system": p["target_system"],
                  "operation": p["operation"], "target_id": p["target_id"], "payload": p["payload"],
                  "site_id": p.get("site_id"), "record_class": p["record_class"],
                  "approval_ids": [a["approval_id"] for a in approvals if a["decision"] == "approved"],
                  "approvers": [{"actor_id": a["actor_id"], "role": a["role"]} for a in approvals
                                if a["decision"] == "approved"],
                  "idempotency_key": f"{p['proposal_id']}:{p['content_hash'][:16]}",
                  "status": "queued",  # queued|dispatching|delivered|failed|unknown|cancelled|awaiting_reassessment
                  "attempts": [], "receipt": None, "created_at": iso(utc_now())}
        tx.put(tenant_id, "action_intent", intent_id, intent, expected_revision=None, action="intent",
               event_type="action.intent_queued", event_payload={"intent_id": intent_id, "proposal_id": p["proposal_id"],
                                                             "mission_id": p.get("mission_id")})
        tx.add_edge(tenant_id, ("proposal", p["proposal_id"]), ("action_intent", intent_id), "authorizes")
        return intent

    # --- dispatch ----------------------------------------------------------------
    def preflight(self, ctx: AccessContext, intent_id: str, tx: Transaction | None = None) -> list[str]:
        """Return every reason the intent cannot dispatch now (empty list = clear)."""
        tx = tx or self.store.read()
        intent = tx.require(ctx.tenant_id, "action_intent", intent_id).state
        prop_rec = tx.require(ctx.tenant_id, "proposal", intent["proposal_id"])
        p = prop_rec.state
        problems = []
        if intent["status"] != "queued":
            problems.append(f"intent is {intent['status']}")
        if p["content_hash"] != intent["content_hash"]:
            problems.append("proposal content changed after approval")
        if p["status"] != "approved":
            problems.append(f"proposal is {p['status']}")
        for ref in p["basis"]:
            current = tx.get(ctx.tenant_id, ref["kind"], ref["id"])
            if current is None:
                problems.append(f"basis {ref['kind']}:{ref['id']} missing")
            elif ref.get("revision") is not None and current.revision != ref["revision"]:
                problems.append(f"basis {ref['kind']}:{ref['id']} changed (rev {ref['revision']} -> {current.revision})")
            elif current.state.get("status", STATUS_CURRENT) not in (STATUS_CURRENT, None) and \
                    current.state.get("status") in ("stale", "quarantined"):
                problems.append(f"basis {ref['kind']}:{ref['id']} is {current.state['status']}")
        for approver in intent["approvers"]:
            live = self.identity.context_for(ctx.tenant_id, approver["actor_id"], role=approver["role"])
            if approver["role"] not in live.roles or not self.identity.check(
                live.with_roles(approver["role"]), "approve", "proposal", p["proposal_id"],
                site_id=p.get("site_id"), tx=tx
            ):
                problems.append(f"approver {approver['actor_id']} no longer holds {approver['role']} authority at this site")
        try:
            self.ownership.check_write(ctx.tenant_id, intent["record_class"], intent.get("site_id") or "*",
                                       intent["operation"], approval_ref=",".join(intent["approval_ids"]), tx=tx)
        except PermissionError as exc:
            problems.append(str(exc))
        return problems

    def dispatch(self, ctx: AccessContext, intent_id: str, writer: Writer) -> dict[str, Any]:
        self.identity.require(ctx, "execute", "action_intent", intent_id)
        owner = f"dispatcher:{ctx.actor_id}"
        with self.store.transaction(ctx.actor_id) as tx:
            problems = self.preflight(ctx, intent_id, tx)
            rec = tx.require(ctx.tenant_id, "action_intent", intent_id)
            if problems:
                if rec.state["status"] == "queued":
                    tx.put(ctx.tenant_id, "action_intent", intent_id,
                           {**rec.state, "status": "awaiting_reassessment", "blocked_reasons": problems},
                           expected_revision=rec.revision, action="block_dispatch", reason="; ".join(problems),
                           event_type="action.dispatch_blocked", event_payload={"intent_id": intent_id})
                    self._set_execution(tx, ctx.tenant_id, rec.state["proposal_id"], "awaiting_reassessment")
                return {"status": "blocked", "reasons": problems}
            token = tx.acquire_lease(ctx.tenant_id, "action_intent", intent_id, owner, ttl_seconds=600)
            rec = tx.put(ctx.tenant_id, "action_intent", intent_id,
                         {**rec.state, "status": "dispatching", "fence": token},
                         expected_revision=rec.revision, action="dispatching")
        intent = rec.state
        attempt = {"at": iso(utc_now()), "fence": token}
        try:
            receipt = writer.deliver(intent)
            final, attempt["result"] = "delivered", "ok"
        except DeliveryUnknown as exc:
            receipt, final, attempt["result"] = None, "unknown", f"unknown: {exc}"
        except Exception as exc:  # destination definitively rejected
            receipt, final, attempt["result"] = None, "failed", f"failed: {exc}"
        with self.store.transaction(ctx.actor_id) as tx:
            tx.check_lease(ctx.tenant_id, "action_intent", intent_id, owner, token)
            cur = tx.require(ctx.tenant_id, "action_intent", intent_id)
            prop_mission = tx.require(ctx.tenant_id, "proposal", intent["proposal_id"]).state.get("mission_id")
            tx.put(ctx.tenant_id, "action_intent", intent_id,
                   {**cur.state, "status": final, "receipt": receipt, "attempts": [*cur.state["attempts"], attempt]},
                   expected_revision=cur.revision, action=f"dispatch_{final}",
                   event_type=f"action.{final}", event_payload={"intent_id": intent_id, "receipt": receipt,
                                                                "proposal_id": intent["proposal_id"],
                                                                "mission_id": prop_mission})
            self._set_execution(tx, ctx.tenant_id, intent["proposal_id"], final)
        return {"status": final, "receipt": receipt}

    def reconcile(self, ctx: AccessContext, intent_id: str, writer: Writer) -> dict[str, Any]:
        """Resolve an unknown outcome by asking the destination using the idempotency key."""
        self.identity.require(ctx, "execute", "action_intent", intent_id)
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "action_intent", intent_id)
            if rec.state["status"] not in ("unknown", "dispatching"):
                return {"status": rec.state["status"], "receipt": rec.state.get("receipt")}
            found = writer.lookup(rec.state["idempotency_key"])
            final = "delivered" if found else "failed"
            tx.put(ctx.tenant_id, "action_intent", intent_id,
                   {**rec.state, "status": final, "receipt": found, "reconciled_at": iso(utc_now())},
                   expected_revision=rec.revision, action="reconcile", event_type=f"action.reconciled_{final}",
                   event_payload={"intent_id": intent_id})
            self._set_execution(tx, ctx.tenant_id, rec.state["proposal_id"], final)
        return {"status": final, "receipt": found}

    def requeue_failed(self, ctx: AccessContext, intent_id: str, reason: str) -> dict[str, Any]:
        """A confirmed failure (not unknown) may be re-queued; preflight runs again at dispatch."""
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "action_intent", intent_id)
            if rec.state["status"] != "failed":
                raise ValueError("only confirmed failures can be re-queued; reconcile unknown outcomes first")
            out = tx.put(ctx.tenant_id, "action_intent", intent_id, {**rec.state, "status": "queued"},
                         expected_revision=rec.revision, action="requeue", reason=reason)
        return out.state

    # --- outcomes ----------------------------------------------------------------
    def record_outcome(self, ctx: AccessContext, proposal_id: str, *, observation: str, measure: str,
                       observed_value: Any, evidence: list[dict[str, Any]], attribution_limits: str) -> dict[str, Any]:
        if not evidence:
            raise ValueError("an outcome needs observation evidence")
        with self.store.transaction(ctx.actor_id) as tx:
            p = tx.require(ctx.tenant_id, "proposal", proposal_id).state
            self.identity.require(ctx, "comment", "proposal", proposal_id, site_id=p.get("site_id"), tx=tx)
            evidence = self.identity.validate_refs(ctx, evidence, tx=tx)
            outcome_id = new_id("outc")
            state = {"outcome_id": outcome_id, "proposal_id": proposal_id, "observation": observation,
                     "measure": measure, "observed_value": observed_value, "evidence": evidence,
                     "attribution_limits": attribution_limits, "expected_result": p["expected_result"],
                     "recorded_by": ctx.actor_id, "recorded_at": iso(utc_now())}
            tx.put(ctx.tenant_id, "outcome", outcome_id, state, expected_revision=None, action="record_outcome",
                   event_type="action.outcome_recorded",
                   event_payload={"proposal_id": proposal_id, "mission_id": p.get("mission_id")})
        return state

    def assess_effectiveness(self, ctx: AccessContext, proposal_id: str, *, effective: bool, rationale: str) -> dict[str, Any]:
        """Mark effective/ineffective only once outcome evidence for the named follow-up measure exists."""
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "proposal", proposal_id)
            p = rec.state
            self.identity.require(ctx, "approve", "proposal", proposal_id, site_id=p.get("site_id"), tx=tx)
            if ctx.actor_kind == "agent":
                raise AuthorizationError(Decision(False, "agents cannot assess effectiveness"))
            if p["execution_status"] != "delivered":
                raise ValueError("effectiveness requires a delivered action")
            outcomes = tx.find(ctx.tenant_id, "outcome", "proposal_id", proposal_id)
            measure = p.get("follow_up_measure")
            if not measure or not any(o.state["measure"] == measure for o in outcomes):
                raise ValueError(f"no recorded outcome evidence for follow-up measure {measure!r}")
            valid = False
            for outcome in outcomes:
                if outcome.state["measure"] != measure:
                    continue
                try:
                    self.identity.validate_refs(ctx, outcome.state["evidence"], tx=tx)
                except (ValueError, KeyError, PermissionError):
                    continue
                valid = True
            if not valid:
                raise ValueError("follow-up evidence is missing, changed, stale or no longer authorized")
            out = tx.put(ctx.tenant_id, "proposal", proposal_id,
                         {**p, "effectiveness": "effective" if effective else "ineffective",
                          "effectiveness_rationale": rationale},
                         expected_revision=rec.revision, action="assess_effectiveness", reason=rationale)
        return out.state

    # --- invalidation hook ------------------------------------------------------------
    def on_dependency_stale(self, tenant_id: str, proposal_id: str) -> None:
        """Called when evidence invalidation marks a proposal stale: cancel queued intents."""
        with self.store.transaction("system") as tx:
            self._cancel_queued_intents(tx, tenant_id, proposal_id, "basis evidence changed")

    def _cancel_queued_intents(self, tx: Transaction, tenant_id: str, proposal_id: str, reason: str) -> None:
        for kind, iid, rel in tx.edges_from(tenant_id, "proposal", proposal_id):
            if kind != "action_intent":
                continue
            rec = tx.get(tenant_id, kind, iid)
            if rec and rec.state["status"] == "queued":
                tx.put(tenant_id, kind, iid, {**rec.state, "status": "awaiting_reassessment",
                                              "blocked_reasons": [reason]},
                       expected_revision=rec.revision, action="reassess", reason=reason)

    def _set_execution(self, tx: Transaction, tenant_id: str, proposal_id: str, status: str) -> None:
        rec = tx.require(tenant_id, "proposal", proposal_id)
        tx.put(tenant_id, "proposal", proposal_id, {**rec.state, "execution_status": status},
               expected_revision=rec.revision, action="execution_status")


Lookup = Callable[[str], dict[str, Any] | None]
