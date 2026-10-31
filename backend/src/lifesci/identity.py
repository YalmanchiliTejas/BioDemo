"""Tenancy, actors, roles, explicit grants and authorization checks.

Authorization combines role policy with resource/scope attributes and is
evaluated at request, retrieval, task execution and output time. A valid login
is not authorization to every batch (architecture, CORE). Partner access uses
explicit, expiring, revocable grants (D24). Derived artifacts inherit the
restrictions of every contributing source (LS-085). Agent credentials can never
approve, sign, release or execute a consequential operation (LS-025).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from .ids import iso, new_id, parse_iso, utc_now
from .store import RecordStore, Transaction

ActorKind = str  # "person" | "service" | "agent" | "partner"

CONSEQUENTIAL_ACTIONS = frozenset({"approve", "sign", "release", "execute", "close", "authorize_write"})
ALL_ACTIONS = frozenset({"read", "propose", "comment", "export", "configure", *CONSEQUENTIAL_ACTIONS})

# Role policy: which actions a role may take on which record kinds inside its site scope.
# "*" is any kind. This is the default internal policy; tenants may override through
# `role_policy` records. The policy never grants more than ALL_ACTIONS.
DEFAULT_ROLE_POLICY: dict[str, dict[str, frozenset[str]]] = {
    "admin": {"*": frozenset({"read", "configure", "export", "propose", "comment"})},
    "operator": {"*": frozenset({"read", "propose", "comment"}),
                 "step_execution": frozenset({"read", "execute", "sign", "comment"}),
                 "sample": frozenset({"read", "execute", "comment"})},
    "supervisor": {"*": frozenset({"read", "propose", "comment", "approve"}),
                   "step_execution": frozenset({"read", "execute", "sign", "approve", "comment"})},
    "qa": {"*": frozenset({"read", "propose", "comment", "approve", "sign", "release", "close", "export"})},
    "qa_reviewer": {"*": frozenset({"read", "comment", "approve", "sign", "export"})},
    "msat": {"*": frozenset({"read", "propose", "comment", "approve", "export"})},
    "engineering": {"*": frozenset({"read", "propose", "comment", "approve"})},
    "maintenance": {"*": frozenset({"read", "propose", "comment"}),
                    "work_order": frozenset({"read", "propose", "execute", "sign", "comment"})},
    "supply_chain": {"*": frozenset({"read", "propose", "comment"}),
                     "material_lot": frozenset({"read", "propose", "approve", "comment"}),
                     "proposal": frozenset({"read", "propose", "approve", "comment"})},
    "manufacturing_systems": {"*": frozenset({"read", "configure", "comment", "propose"})},
    "quality_systems": {"*": frozenset({"read", "configure", "comment", "propose", "approve"})},
    "system_executor": {"action_intent": frozenset({"read", "execute"})},
    "agent": {"*": frozenset({"read", "propose", "comment"})},
    "partner_viewer": {},  # partners act only through explicit grants
    "partner_reviewer": {},
}


@dataclass(frozen=True)
class AccessContext:
    tenant_id: str
    actor_id: str
    actor_kind: ActorKind = "person"
    roles: frozenset[str] = frozenset()
    site_ids: frozenset[str] = frozenset()  # empty = tenant-wide for internal roles
    partner_org_id: str | None = None
    delegated_from: str | None = None  # service jobs carry a person's limited scope
    authorization_version: int = 0

    def with_roles(self, *roles: str) -> "AccessContext":
        return AccessContext(self.tenant_id, self.actor_id, self.actor_kind, frozenset(roles),
                             self.site_ids, self.partner_org_id, self.delegated_from, self.authorization_version)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    grant_ids: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.allowed


class AuthorizationError(PermissionError):
    def __init__(self, decision: Decision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


class IdentityService:
    """Role assignments and resource grants persisted as versioned records."""

    def __init__(self, store: RecordStore) -> None:
        self.store = store

    # --- roles -----------------------------------------------------------------
    def assign_role(self, tenant_id: str, actor_id: str, role: str, *, site_id: str | None = None,
                    actor_kind: ActorKind = "person", by: str = "system",
                    reason: str | None = None) -> dict[str, Any]:
        if role not in DEFAULT_ROLE_POLICY:
            raise ValueError(f"unknown role {role}")
        if actor_kind == "agent" and role != "agent":
            raise PermissionError("agent credentials may only hold the agent role")
        state = {"actor_id": actor_id, "role": role, "site_id": site_id, "actor_kind": actor_kind,
                 "assigned_at": iso(utc_now()), "revoked_at": None}
        rid = f"{actor_id}:{role}:{site_id or '*'}"
        with self.store.transaction(by) as tx:
            current = tx.get(tenant_id, "role_assignment", rid)
            if current is not None and not current.state.get("revoked_at"):
                return current.state  # already active: idempotent
            tx.put(tenant_id, "role_assignment", rid, state,
                   expected_revision=current.revision if current else None, action="assign_role", reason=reason,
                   event_type="identity.role_assigned",
                   event_payload={"actor_id": actor_id, "role": role, "site_id": site_id})
        return state

    def revoke_role(self, tenant_id: str, actor_id: str, role: str, *, site_id: str | None = None,
                    by: str = "system", reason: str | None = None) -> None:
        with self.store.transaction(by) as tx:
            rec = tx.require(tenant_id, "role_assignment", f"{actor_id}:{role}:{site_id or '*'}")
            tx.put(tenant_id, "role_assignment", rec.id, {**rec.state, "revoked_at": iso(utc_now())},
                   expected_revision=rec.revision, action="revoke_role", reason=reason,
                   event_type="identity.role_revoked", event_payload={"actor_id": actor_id, "role": role})

    def context_for(self, tenant_id: str, actor_id: str, *, actor_kind: ActorKind = "person",
                    partner_org_id: str | None = None, role: str | None = None) -> AccessContext:
        """Build the actor's current context from live (non-revoked) assignments."""
        tx = self.store.read()
        rows = [r for r in tx.find(tenant_id, "role_assignment", "actor_id", actor_id)
                if not r.state.get("revoked_at") and (role is None or r.state["role"] == role)]
        roles = frozenset(r.state["role"] for r in rows)
        sites = frozenset(r.state["site_id"] for r in rows if r.state.get("site_id")) if all(
            r.state.get("site_id") for r in rows) else frozenset()
        version = sum(r.revision for r in rows)
        member = tx.get(tenant_id, "partner_membership", actor_id)
        if actor_kind == "partner" and member:
            partner_org_id = member.state["partner_org_id"] if member.state.get("active") else None
        if member and member.state.get("active") and not rows and actor_kind == "person":
            actor_kind, partner_org_id = "partner", member.state["partner_org_id"]
        return AccessContext(tenant_id, actor_id, actor_kind, roles, sites, partner_org_id,
                             authorization_version=version)

    # --- grants ----------------------------------------------------------------
    def grant(self, tenant_id: str, *, grantee_id: str, resource_kind: str, resource_id: str,
              actions: Iterable[str], site_id: str | None = None, expires_at: datetime | None = None,
              by: str = "system", purpose: str | None = None) -> str:
        actions = frozenset(actions)
        if not actions <= ALL_ACTIONS:
            raise ValueError(f"unknown actions {sorted(actions - ALL_ACTIONS)}")
        grant_id = new_id("grant")
        state = {"grantee_id": grantee_id, "resource_kind": resource_kind, "resource_id": resource_id,
                 "actions": sorted(actions), "site_id": site_id, "expires_at": iso(expires_at),
                 "revoked_at": None, "granted_by": by, "purpose": purpose, "granted_at": iso(utc_now())}
        with self.store.transaction(by) as tx:
            tx.put(tenant_id, "grant", grant_id, state, expected_revision=None, action="grant",
                   event_type="identity.granted", event_payload={"grant_id": grant_id, **state})
        return grant_id

    def revoke_grant(self, tenant_id: str, grant_id: str, *, by: str = "system", reason: str | None = None) -> None:
        with self.store.transaction(by) as tx:
            rec = tx.require(tenant_id, "grant", grant_id)
            if rec.state.get("revoked_at"):
                return
            tx.put(tenant_id, "grant", grant_id, {**rec.state, "revoked_at": iso(utc_now())},
                   expected_revision=rec.revision, action="revoke_grant", reason=reason,
                   event_type="identity.grant_revoked",
                   event_payload={"grant_id": grant_id, "grantee_id": rec.state["grantee_id"],
                                  "resource_kind": rec.state["resource_kind"], "resource_id": rec.state["resource_id"]})

    def live_grants(self, tenant_id: str, grantee_id: str, tx: Transaction | None = None) -> list[dict[str, Any]]:
        tx = tx or self.store.read()
        now = iso(utc_now())
        out = []
        for rec in tx.find(tenant_id, "grant", "grantee_id", grantee_id):
            s = rec.state
            if s.get("revoked_at") or (s.get("expires_at") and s["expires_at"] <= now):
                continue
            out.append({**s, "grant_id": rec.id})
        return out

    # --- checks ----------------------------------------------------------------
    def check(self, ctx: AccessContext, action: str, resource_kind: str, resource_id: str = "*",
              *, site_id: str | None = None, tx: Transaction | None = None) -> Decision:
        if action not in ALL_ACTIONS:
            return Decision(False, f"unknown action {action}")
        if ctx.actor_kind == "agent" and action in CONSEQUENTIAL_ACTIONS:
            return Decision(False, "agent credentials cannot perform consequential actions")
        if site_id and ctx.site_ids and site_id not in ctx.site_ids and ctx.actor_kind != "partner":
            return Decision(False, f"site {site_id} outside actor scope")
        if ctx.actor_kind != "partner":
            for role in ctx.roles:
                policy = DEFAULT_ROLE_POLICY.get(role, {})
                allowed = policy.get(resource_kind, policy.get("*", frozenset()))
                if action in allowed:
                    return Decision(True, f"role {role}")
        grantee_ids = [ctx.actor_id] + ([ctx.partner_org_id] if ctx.partner_org_id else [])
        matched = []
        for grantee in grantee_ids:
            for g in self.live_grants(ctx.tenant_id, grantee, tx):
                kind_ok = g["resource_kind"] in (resource_kind, "*")
                id_ok = g["resource_id"] in (resource_id, "*")
                site_ok = not g.get("site_id") or not site_id or g["site_id"] == site_id
                if kind_ok and id_ok and site_ok and action in g["actions"]:
                    matched.append(g["grant_id"])
        if matched:
            return Decision(True, "explicit grant", tuple(matched))
        return Decision(False, f"{ctx.actor_id} lacks {action} on {resource_kind}:{resource_id}")

    def require(self, ctx: AccessContext, action: str, resource_kind: str, resource_id: str = "*",
                *, site_id: str | None = None, tx: Transaction | None = None) -> Decision:
        decision = self.check(ctx, action, resource_kind, resource_id, site_id=site_id, tx=tx)
        if not decision:
            raise AuthorizationError(decision)
        return decision

    def check_derived(self, ctx: AccessContext, source_refs: Iterable[dict[str, str]], action: str = "read",
                      tx: Transaction | None = None) -> Decision:
        """A derived artifact is readable only if every contributing source still is.

        Incomplete lineage is treated as unavailable rather than assumed safe.
        """
        refs = list(source_refs)
        if not refs:
            return Decision(False, "derived artifact has no recorded lineage; unavailable for sharing")
        for ref in refs:
            kind, rid = ref.get("kind"), ref.get("id")
            if not kind or not rid:
                return Decision(False, "incomplete lineage reference; artifact unavailable")
            d = self.check(ctx, action, kind, rid, site_id=ref.get("site_id"), tx=tx)
            if not d:
                return Decision(False, f"source {kind}:{rid} not authorized: {d.reason}")
        return Decision(True, "all sources authorized")

    def validate_refs(self, ctx: AccessContext, refs: Iterable[dict[str, Any]], *,
                      tx: Transaction | None = None, require_current: bool = True,
                      _seen: frozenset[tuple[str, str]] = frozenset()) -> list[dict[str, Any]]:
        """Resolve source scope from storage, verify revisions and pin an authorized manifest.

        Caller-supplied site labels cannot authorize a source. Nested artifacts retain
        the restrictions of every input, including after a grant is revoked.
        """
        tx = tx or self.store.read()
        pinned = []
        for ref in refs:
            kind, rid = ref.get("kind"), ref.get("id")
            if not kind or not rid:
                raise ValueError("source reference requires kind and id")
            key = (kind, rid)
            if key in _seen:
                raise PermissionError("cyclic source lineage is unavailable")
            current = tx.require(ctx.tenant_id, kind, rid)
            site = current.state.get("site_id")
            if ref.get("site_id") is not None and ref["site_id"] != site:
                raise PermissionError("source site does not match the stored record")
            self.require(ctx, "read", kind, rid, site_id=site, tx=tx)
            revision = ref.get("revision", current.revision)
            source = tx.revision(ctx.tenant_id, kind, rid, revision)
            if source is None:
                raise ValueError(f"source revision missing: {kind}:{rid}@{revision}")
            self.require(ctx, "read", kind, rid, site_id=source.state.get("site_id"), tx=tx)
            if require_current and (revision != current.revision or
                                    current.state.get("status") in ("stale", "quarantined", "superseded")):
                raise ValueError(f"source is no longer current: {kind}:{rid}@{revision}")
            if current.state.get("status") == "quarantined":
                raise PermissionError(f"source quarantined: {kind}:{rid}")
            for state in (current.state, source.state):
                if "inputs" in state:
                    if not state["inputs"]:
                        raise PermissionError("derived source has no lineage")
                    self.validate_refs(ctx, state["inputs"], tx=tx, require_current=require_current,
                                       _seen=_seen | {key})
            pinned.append({**ref, "revision": revision, "site_id": site})
        if not pinned:
            raise ValueError("at least one source reference is required")
        return pinned


def expired(value: str | None) -> bool:
    parsed = parse_iso(value)
    return bool(parsed and parsed <= utc_now())
