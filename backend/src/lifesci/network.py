"""Sites, rollouts, template distribution, technology transfer, partners, lifecycle readiness and scheduling.

Implements LS-009 (site rollout differences and QMS reconciliation), LS-015 (site-scoped and enterprise
visibility), the distribution-record part of LS-016, LS-017 (transfer package with recipient checklist),
LS-018 (expiring, revocable partner grants that also remove cached exports), LS-019 (readiness items bound
to source revisions) and LS-075 (deterministic constraint-checked schedule proposals). Receipt of a transfer
package or distribution of a template is never treated as readiness or adoption, and a schedule is only ever
applied through ActionService.propose(operation="reschedule_batch").
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

from .actions import ActionService
from .evidence import EvidenceRef, EvidenceService
from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import content_hash, iso, new_id, parse_iso, utc_now
from .store import NotFoundError, RecordStore, Transaction

PARTNER_BATCH_FIELDS = ("batch_id", "product_id", "status", "site_id")
READINESS_STATUSES = ("ready", "at_risk", "not_ready", "unknown")


def validate_site_override(override: dict[str, Any], allowed_params: dict[str, Any],
                           current_revision: int | str | None = None) -> dict[str, Any]:
    """Check a site override names its template revision and only changes allowed parameters.

    allowed_params maps parameter -> None (any value) or {"min", "max", "choices"}.
    """
    problems: list[str] = []
    if not override.get("template_id"):
        problems.append("override does not identify its template_id")
    if override.get("template_revision") in (None, ""):
        problems.append("override does not identify the template revision it adapts")
    elif current_revision is not None and override["template_revision"] != current_revision:
        problems.append(f"override targets revision {override['template_revision']} but current is {current_revision}")
    for name, value in (override.get("overrides") or {}).items():
        if name not in allowed_params:
            problems.append(f"parameter {name} is not overridable")
            continue
        rule = allowed_params[name] or {}
        if "choices" in rule and value not in rule["choices"]:
            problems.append(f"{name}={value!r} not in allowed choices")
        if "min" in rule and (not isinstance(value, (int, float)) or value < rule["min"]):
            problems.append(f"{name}={value!r} below minimum {rule['min']}")
        if "max" in rule and (not isinstance(value, (int, float)) or value > rule["max"]):
            problems.append(f"{name}={value!r} above maximum {rule['max']}")
    return {"valid": not problems, "problems": problems}


# --- sites, rollout, distribution ------------------------------------------------------------
class NetworkService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def site_view(self, ctx: AccessContext, kinds: Iterable[str] = ("batch",)) -> dict[str, Any]:
        """Records visible to the caller, grouped by site. Tenant-wide internal roles get an enterprise roll-up."""
        tx = self.store.read()
        sites: dict[str, dict[str, Any]] = {}
        for kind in kinds:
            for rec in tx.list(ctx.tenant_id, kind):
                sid = rec.state.get("site_id") or "unassigned"
                if not self.identity.check(ctx, "read", kind, rec.id, site_id=rec.state.get("site_id"), tx=tx):
                    continue
                entry = sites.setdefault(sid, {"records": [], "counts": {}})
                entry["records"].append({"kind": kind, "id": rec.id, "status": rec.state.get("status"),
                                         "product_id": rec.state.get("product_id")})
                by_status = entry["counts"].setdefault(kind, {"total": 0})
                by_status["total"] += 1
                by_status[rec.state.get("status") or "unknown"] = by_status.get(rec.state.get("status") or "unknown", 0) + 1
        enterprise = not ctx.site_ids and ctx.actor_kind != "partner" and bool(ctx.roles)
        scope = "enterprise" if enterprise else ("granted" if ctx.actor_kind == "partner" else "site")
        out: dict[str, Any] = {"scope": scope, "sites": sites}
        if enterprise:
            out["totals"] = {sid: {k: v["total"] for k, v in e["counts"].items()} for sid, e in sorted(sites.items())}
        return out

    # --- rollout (LS-009) ---------------------------------------------------------------------
    def set_baseline(self, ctx: AccessContext, config: dict[str, Any]) -> dict[str, Any]:
        self.identity.require(ctx, "configure", "config_baseline")
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "config_baseline", "global")
            rec = tx.put(ctx.tenant_id, "config_baseline", "global", {"config": config, "set_by": ctx.actor_id},
                         expected_revision=cur.revision if cur else None, action="set_baseline")
        return {"revision": rec.revision, **rec.state}

    def plan_rollout(self, ctx: AccessContext, site_id: str, template_refs: list[dict[str, Any]],
                     config_overrides: dict[str, Any], qms_reference: str) -> dict[str, Any]:
        self.identity.require(ctx, "configure", "site_rollout", site_id=site_id)
        if not qms_reference:
            raise ValueError("a rollout must name its QMS change-control reference")
        tx = self.store.read()
        base = tx.require(ctx.tenant_id, "config_baseline", "global")
        cfg, base_templates = base.state["config"], base.state["config"].get("templates", {})
        diffs = []
        for name in sorted(config_overrides):
            if name == "templates":
                continue
            if name not in cfg:
                diffs.append({"parameter": name, "baseline_value": None, "site_value": config_overrides[name], "change": "added"})
            elif cfg[name] != config_overrides[name]:
                diffs.append({"parameter": name, "baseline_value": cfg[name], "site_value": config_overrides[name], "change": "changed"})
        for ref in template_refs:
            if ref["template_id"] not in base_templates or base_templates[ref["template_id"]] != ref["revision"]:
                diffs.append({"parameter": f"template:{ref['template_id']}", "baseline_value": base_templates.get(ref["template_id"]),
                              "site_value": ref["revision"], "change": "changed" if ref["template_id"] in base_templates else "added"})
        rid = new_id("roll")
        state = {"rollout_id": rid, "site_id": site_id, "template_refs": template_refs, "config_overrides": config_overrides,
                 "baseline_revision": base.revision, "differences": diffs, "qms_reference": qms_reference,
                 "status": "planned", "reconciliation": None, "planned_by": ctx.actor_id, "planned_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as w:
            rec = w.put(ctx.tenant_id, "site_rollout", rid, state, expected_revision=None, action="plan_rollout",
                        event_type="rollout.planned", event_payload={"rollout_id": rid, "site_id": site_id})
        return {**rec.state, "revision": rec.revision}

    def reconcile_qms(self, ctx: AccessContext, rollout_id: str, qms_record: dict[str, Any] | None) -> dict[str, Any]:
        """Compare the rollout with a snapshot of the QMS change-control record; the QMS remains authoritative."""
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "site_rollout", rollout_id)
            s = rec.state
            self.identity.require(ctx, "configure", "site_rollout", rollout_id, site_id=s["site_id"], tx=tx)
            issues: list[str] = []
            if not qms_record:
                issues.append(f"QMS record {s['qms_reference']} not found")
            else:
                if qms_record.get("reference") != s["qms_reference"]:
                    issues.append(f"QMS reference {qms_record.get('reference')} does not match rollout reference {s['qms_reference']}")
                if qms_record.get("status") != "approved":
                    issues.append(f"QMS change control status is {qms_record.get('status')!r}, not approved")
                if qms_record.get("site_id") != s["site_id"]:
                    issues.append(f"QMS record is for site {qms_record.get('site_id')}, rollout is for {s['site_id']}")
                covered = qms_record.get("covered_parameters")
                if covered is not None:
                    missing = [d["parameter"] for d in s["differences"] if d["parameter"] not in covered]
                    if missing:
                        issues.append(f"differences not covered by the QMS change: {missing}")
            result = {"status": "discrepancy" if issues else "reconciled", "issues": issues, "reconciled_at": iso(utc_now()),
                      "difference_coverage": "not_provided" if not qms_record or qms_record.get("covered_parameters") is None else "checked",
                      "qms_snapshot": qms_record}
            out = tx.put(ctx.tenant_id, "site_rollout", rollout_id,
                         {**s, "status": result["status"], "reconciliation": result},
                         expected_revision=rec.revision, action="reconcile_qms")
        return {**out.state, "revision": out.revision}

    # --- distribution (LS-016 part) ---------------------------------------------------------------------
    def distribute(self, ctx: AccessContext, template_id: str, revision: int | str, site_ids: Iterable[str]) -> list[dict[str, Any]]:
        self.identity.require(ctx, "configure", "template_distribution")
        out = []
        with self.store.transaction(ctx.actor_id) as tx:
            for site in site_ids:
                did = f"{template_id}@{revision}:{site}"
                cur = tx.get(ctx.tenant_id, "template_distribution", did)
                if cur:
                    out.append({"revision": cur.revision, **cur.state})
                    continue
                state = {"template_id": template_id, "template_revision": revision, "site_id": site, "status": "distributed",
                         "ack_status": "pending", "acknowledged_by": None, "distributed_by": ctx.actor_id,
                         "distributed_at": iso(utc_now()), "adoption": "not_confirmed"}
                rec = tx.put(ctx.tenant_id, "template_distribution", did, state, expected_revision=None, action="distribute",
                             event_type="template.distributed", event_payload={"template_id": template_id, "site_id": site})
                out.append({"revision": rec.revision, **rec.state})
        return out

    def acknowledge(self, ctx: AccessContext, template_id: str, revision: int | str, site_id: str) -> dict[str, Any]:
        did = f"{template_id}@{revision}:{site_id}"
        with self.store.transaction(ctx.actor_id) as tx:
            self.identity.require(ctx, "comment", "template_distribution", did, site_id=site_id, tx=tx)
            if ctx.actor_kind != "person":
                raise AuthorizationError(Decision(False, "acknowledgement requires a human at the receiving site"))
            rec = tx.require(ctx.tenant_id, "template_distribution", did)
            out = tx.put(ctx.tenant_id, "template_distribution", did,
                         {**rec.state, "ack_status": "acknowledged", "acknowledged_by": ctx.actor_id, "acknowledged_at": iso(utc_now())},
                         expected_revision=rec.revision, action="acknowledge_template")
        return {"revision": out.revision, **out.state}

    def distribution_status(self, ctx: AccessContext, template_id: str) -> list[dict[str, Any]]:
        tx = self.store.read()
        return [{"revision": r.revision, **r.state} for r in tx.list(ctx.tenant_id, "template_distribution",
                lambda s: s["template_id"] == template_id)
                if self.identity.check(ctx, "read", "template_distribution", r.id, site_id=r.state["site_id"], tx=tx)]


# --- technology transfer (LS-017) -------------------------------------------------------------------
@dataclass
class TransferPackage:
    sending_site: str
    receiving_site: str
    product_id: str
    procedure_refs: list[dict[str, Any]]
    parameters: dict[str, Any] = field(default_factory=dict)
    material_mapping: dict[str, str | None] = field(default_factory=dict)
    equipment_mapping: dict[str, str | None] = field(default_factory=dict)
    required_qualifications: list[dict[str, str]] = field(default_factory=list)
    open_gaps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_CONTENT_KEYS = tuple(TransferPackage.__dataclass_fields__)


def _inventory_names(value: Any) -> set[str]:
    return set(value.keys()) if isinstance(value, dict) else set(value or [])


class TransferService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def create(self, ctx: AccessContext, package: TransferPackage) -> dict[str, Any]:
        self.identity.require(ctx, "propose", "transfer_package", site_id=package.sending_site)
        for p in package.procedure_refs:
            if not p.get("id") or p.get("revision") is None:
                raise ValueError("transfer procedures must be versioned references (id and revision)")
        pid = new_id("xfer")
        state = {"package_id": pid, **package.to_dict(), "approvals": {"sender": None, "recipient": None}, "received": None,
                 "created_by": ctx.actor_id, "created_at": iso(utc_now())}
        state["content_hash"] = content_hash({k: state[k] for k in _CONTENT_KEYS})
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, "transfer_package", pid, state, expected_revision=None, action="create_transfer_package",
                         event_type="transfer.created", event_payload={"package_id": pid})
        return {"revision": rec.revision, **rec.state}

    def revise(self, ctx: AccessContext, package_id: str, expected_revision: int, **changes: Any) -> dict[str, Any]:
        """Content changes change the content hash, so earlier approvals stop covering the package."""
        unknown = set(changes) - set(_CONTENT_KEYS)
        if unknown:
            raise ValueError(f"unknown package fields {sorted(unknown)}")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "transfer_package", package_id)
            self.identity.require(ctx, "propose", "transfer_package", package_id, site_id=rec.state["sending_site"], tx=tx)
            state = {**rec.state, **changes}
            state["content_hash"] = content_hash({k: state[k] for k in _CONTENT_KEYS})
            out = tx.put(ctx.tenant_id, "transfer_package", package_id, state, expected_revision=expected_revision, action="revise_transfer_package")
        return {"revision": out.revision, **out.state}

    def _gaps(self, s: dict[str, Any], inventory: dict[str, Any]) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        materials, equipment = _inventory_names(inventory.get("materials")), inventory.get("equipment") or {}
        for src, dst in s["material_mapping"].items():
            if dst is None:
                gaps.append({"type": "unmapped_material", "item": src, "detail": "no receiving-site material mapped"})
            elif dst not in materials:
                gaps.append({"type": "material_not_in_inventory", "item": src, "detail": f"{dst} not in receiving inventory"})
        for src, dst in s["equipment_mapping"].items():
            if dst is None:
                gaps.append({"type": "unmapped_equipment", "item": src, "detail": "no receiving-site equipment mapped"})
            elif dst not in equipment:
                gaps.append({"type": "equipment_not_in_inventory", "item": src, "detail": f"{dst} not in receiving inventory"})
        for req in s["required_qualifications"]:
            dst = s["equipment_mapping"].get(req["equipment"])
            if dst is None or dst not in equipment:
                continue
            held = set((equipment[dst] or {}).get("qualifications", []))
            if req["qualification"] not in held:
                gaps.append({"type": "equipment_unqualified", "item": dst,
                             "detail": f"{req['qualification']} required for {req['equipment']}, not held by {dst}"})
        gaps += [{"type": "open_gap", "item": g.get("id"), "detail": g.get("description")} for g in s["open_gaps"]
                 if g.get("status") != "closed"]
        return gaps

    def recipient_checklist(self, ctx: AccessContext, package_id: str, receiving_site_inventory: dict[str, Any]) -> dict[str, Any]:
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, "transfer_package", package_id)
        s = rec.state
        self.identity.require(ctx, "read", "transfer_package", package_id, site_id=s["receiving_site"], tx=tx)
        gaps = self._gaps(s, receiving_site_inventory)
        approval = s["approvals"]["recipient"]
        approved = bool(approval and approval["content_hash"] == s["content_hash"])
        reasons = [f"{len(gaps)} open gap(s)"] if gaps else []
        if not approved:
            reasons.append("recipient approval missing" if not approval else "recipient approval no longer covers package content")
        return {"package_id": package_id, "gaps": gaps, "received": s["received"] is not None, "recipient_approved": approved,
                "readiness": "ready" if not gaps and approved else "not_ready", "reasons": reasons,
                "note": "receipt of the package does not establish readiness"}

    def acknowledge_receipt(self, ctx: AccessContext, package_id: str) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "transfer_package", package_id)
            self.identity.require(ctx, "comment", "transfer_package", package_id, site_id=rec.state["receiving_site"], tx=tx)
            out = tx.put(ctx.tenant_id, "transfer_package", package_id,
                         {**rec.state, "received": {"by": ctx.actor_id, "at": iso(utc_now())}},
                         expected_revision=rec.revision, action="acknowledge_receipt")
        return {"revision": out.revision, **out.state}

    def approve(self, ctx: AccessContext, package_id: str, role: str,
                receiving_site_inventory: dict[str, Any] | None = None) -> dict[str, Any]:
        """Sender or recipient approval of the current content. Recipient approval requires a gap-free checklist."""
        if role not in ("sender", "recipient"):
            raise ValueError("role must be sender or recipient")
        if ctx.actor_kind != "person":
            raise AuthorizationError(Decision(False, "transfer approval requires a human approver"))
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "transfer_package", package_id)
            s = rec.state
            site = s["receiving_site"] if role == "recipient" else s["sending_site"]
            self.identity.require(ctx, "approve", "transfer_package", package_id, site_id=site, tx=tx)
            if role == "recipient":
                gaps = self._gaps(s, receiving_site_inventory or {})
                if gaps:
                    raise ValueError(f"recipient cannot approve while gaps remain: {[g['type'] + ':' + str(g['item']) for g in gaps]}")
            approvals = {**s["approvals"], role: {"by": ctx.actor_id, "at": iso(utc_now()), "content_hash": s["content_hash"]}}
            out = tx.put(ctx.tenant_id, "transfer_package", package_id, {**s, "approvals": approvals},
                         expected_revision=rec.revision, action=f"approve_{role}")
        return {"revision": out.revision, **out.state}


# --- partner collaboration (LS-018) -------------------------------------------------------------------------
class PartnerService:
    def __init__(self, store: RecordStore, identity: IdentityService, evidence: EvidenceService) -> None:
        self.store = store
        self.identity = identity
        self.evidence = evidence

    def _batch(self, tx: Transaction, ctx: AccessContext, batch_id: str) -> Any:
        return tx.require(ctx.tenant_id, "batch", batch_id)

    def grant_partner(self, ctx: AccessContext, partner_org_id: str, batch_id: str, mode: str = "view",
                      expires_at: datetime | None = None) -> dict[str, Any]:
        if mode not in ("view", "interactive"):
            raise ValueError("mode must be view or interactive")
        tx = self.store.read()
        batch = self._batch(tx, ctx, batch_id)
        site = batch.state.get("site_id")
        self.identity.require(ctx, "export", "batch", batch_id, site_id=site, tx=tx)
        actions = ["read"] if mode == "view" else ["read", "comment", "approve"]
        ids = [self.identity.grant(ctx.tenant_id, grantee_id=partner_org_id, resource_kind="batch", resource_id=batch_id,
                                   actions=actions, site_id=site, expires_at=expires_at, by=ctx.actor_id, purpose="partner_collaboration")]
        for eid in batch.state.get("evidence_ids", []):
            ids.append(self.identity.grant(ctx.tenant_id, grantee_id=partner_org_id, resource_kind="evidence", resource_id=eid,
                                           actions=["read"], site_id=site, expires_at=expires_at, by=ctx.actor_id,
                                           purpose="partner_collaboration"))
        gid = ids[0]
        state = {"grant_id": gid, "grant_ids": ids, "partner_org_id": partner_org_id, "batch_id": batch_id, "mode": mode,
                 "site_id": site, "status": "active", "expires_at": iso(expires_at), "granted_by": ctx.actor_id}
        with self.store.transaction(ctx.actor_id) as w:
            w.put(ctx.tenant_id, "partner_grant", gid, state, expected_revision=None, action="grant_partner",
                  event_type="partner.granted", event_payload={"grant_id": gid, "batch_id": batch_id, "mode": mode})
        return state

    def partner_batch_view(self, ctx: AccessContext, batch_id: str) -> dict[str, Any]:
        tx = self.store.read()
        batch = self._batch(tx, ctx, batch_id)
        site = batch.state.get("site_id")
        self.identity.require(ctx, "read", "batch", batch_id, site_id=site, tx=tx)
        evidence = []
        for eid in batch.state.get("evidence_ids", []):
            if self.identity.check(ctx, "read", "evidence", eid, site_id=site, tx=tx):
                e = tx.get(ctx.tenant_id, "evidence", eid)
                if e:
                    evidence.append({"id": eid, "revision": e.revision, "digest": e.state["digest"], "event_time": e.state["event_time"]})
        return {"batch": {k: batch.state.get(k) for k in PARTNER_BATCH_FIELDS}, "evidence": evidence,
                "permissions": {"can_comment": bool(self.identity.check(ctx, "comment", "batch", batch_id, site_id=site, tx=tx)),
                                "can_approve": bool(self.identity.check(ctx, "approve", "batch", batch_id, site_id=site, tx=tx))}}

    def partner_review(self, ctx: AccessContext, batch_id: str, decision: str, comment: str) -> dict[str, Any]:
        """Interactive partner feedback. The origin (partner org and actor) is preserved; it never releases anything."""
        if decision not in ("approve", "reject", "comment"):
            raise ValueError("decision must be approve, reject or comment")
        tx = self.store.read()
        site = self._batch(tx, ctx, batch_id).state.get("site_id")
        self.identity.require(ctx, "comment" if decision == "comment" else "approve", "batch", batch_id, site_id=site, tx=tx)
        rid = new_id("prev")
        state = {"batch_id": batch_id, "decision": decision, "comment": comment, "origin": {"actor_id": ctx.actor_id,
                 "actor_kind": ctx.actor_kind, "partner_org_id": ctx.partner_org_id}, "site_id": site, "at": iso(utc_now()),
                 "effect": "recorded_feedback_only"}
        with self.store.transaction(ctx.actor_id) as w:
            w.put(ctx.tenant_id, "partner_review", rid, state, expected_revision=None, action=f"partner_{decision}",
                  event_type="partner.reviewed", event_payload={"batch_id": batch_id, "decision": decision})
        return {"review_id": rid, **state}

    def export_for_partner(self, ctx: AccessContext, batch_id: str, partner_org_id: str) -> dict[str, Any]:
        """Cache a permitted projection as a derived artifact whose inputs are the batch and its evidence."""
        tx = self.store.read()
        batch = self._batch(tx, ctx, batch_id)
        site = batch.state.get("site_id")
        self.identity.require(ctx, "export", "batch", batch_id, site_id=site, tx=tx)
        live = [g for g in self.identity.live_grants(ctx.tenant_id, partner_org_id, tx)
                if g["resource_kind"] == "batch" and g["resource_id"] == batch_id]
        if not live:
            raise PermissionError(f"{partner_org_id} holds no live grant on batch {batch_id}")
        grant = next(iter(tx.list(ctx.tenant_id, "partner_grant", lambda s: batch_id == s["batch_id"] and s["status"] == "active"
                                  and partner_org_id == s["partner_org_id"] and live[0]["grant_id"] in s["grant_ids"])), None)
        if grant is None:
            raise PermissionError(f"no recorded partner share for {partner_org_id} on batch {batch_id}")
        refs, rows = [EvidenceRef("batch", batch_id, batch.revision, site)], []
        for eid in batch.state.get("evidence_ids", []):
            e = tx.require(ctx.tenant_id, "evidence", eid)
            refs.append(EvidenceRef("evidence", eid, e.revision, site))
            rows.append({"id": eid, "revision": e.revision, "digest": e.state["digest"], "event_time": e.state["event_time"]})
        payload = {"batch_id": batch_id, "partner_org_id": partner_org_id, "grant_id": grant.id, "site_id": site,
                   "projection": {k: batch.state.get(k) for k in PARTNER_BATCH_FIELDS}, "evidence": rows}
        out = self.evidence.record_derived(ctx, "partner_export", payload, inputs=refs,
                                           produced_by={"actor_id": ctx.actor_id, "method": "partner_service.export_for_partner"})
        self.evidence.link(ctx, ("partner_grant", grant.id), ("partner_export", out["id"]), "exported_under")
        return out

    def read_export(self, ctx: AccessContext, export_id: str) -> dict[str, Any]:
        out = self.evidence.read_derived(ctx, "partner_export", export_id)
        if ctx.actor_kind == "partner" and out["partner_org_id"] != ctx.partner_org_id:
            raise PermissionError("export belongs to another partner organization")
        return out

    def revoke_partner(self, ctx: AccessContext, grant_id: str, reason: str = "partner access revoked") -> dict[str, Any]:
        """Revoke every grant behind the partner share and quarantine exports cached under it."""
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "partner_grant", grant_id)
            self.identity.require(ctx, "export", "batch", rec.state["batch_id"], site_id=rec.state["site_id"], tx=tx)
        for gid in rec.state["grant_ids"]:
            self.identity.revoke_grant(ctx.tenant_id, gid, by=ctx.actor_id, reason=reason)
        quarantined = self.evidence.quarantine_from(ctx, "partner_grant", grant_id, reason)
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.require(ctx.tenant_id, "partner_grant", grant_id)
            tx.put(ctx.tenant_id, "partner_grant", grant_id, {**cur.state, "status": "revoked", "revoked_by": ctx.actor_id,
                   "revoked_at": iso(utc_now())}, expected_revision=cur.revision, action="revoke_partner", reason=reason,
                   event_type="partner.revoked", event_payload={"grant_id": grant_id})
        return {"grant_id": grant_id, "quarantined": quarantined}


# --- lifecycle readiness (LS-019) -----------------------------------------------------------------------------
class LifecycleService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def record_readiness(self, ctx: AccessContext, product_id: str, stage: str, market: str, status: str,
                         source_kind: str, source_id: str, site_id: str | None = None) -> dict[str, Any]:
        if status not in READINESS_STATUSES:
            raise ValueError(f"status must be one of {READINESS_STATUSES}")
        self.identity.require(ctx, "propose", "readiness_item", site_id=site_id)
        iid = f"{product_id}:{stage}:{market}:{source_kind}:{source_id}"
        with self.store.transaction(ctx.actor_id) as tx:
            src = tx.require(ctx.tenant_id, source_kind, source_id)
            self.identity.require(ctx, "read", source_kind, source_id, site_id=src.state.get("site_id"), tx=tx)
            state = {"item_id": iid, "product_id": product_id, "stage": stage, "market": market, "status": status,
                     "source": {"kind": source_kind, "id": source_id, "revision": src.revision, "site_id": src.state.get("site_id")},
                     "recorded_by": ctx.actor_id, "recorded_at": iso(utc_now())}
            cur = tx.get(ctx.tenant_id, "readiness_item", iid)
            rec = tx.put(ctx.tenant_id, "readiness_item", iid, state, expected_revision=cur.revision if cur else None,
                         action="record_readiness")
        return {"revision": rec.revision, **rec.state}

    def lifecycle_summary(self, ctx: AccessContext, product_id: str) -> dict[str, Any]:
        tx = self.store.read()
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        restricted = stale_count = 0
        for rec in tx.list(ctx.tenant_id, "readiness_item", lambda s: s["product_id"] == product_id):
            s, src = rec.state, rec.state["source"]
            if not self.identity.check(ctx, "read", src["kind"], src["id"], site_id=src.get("site_id"), tx=tx):
                restricted += 1
                continue
            cur = tx.get(ctx.tenant_id, src["kind"], src["id"])
            stale = cur is None or cur.revision != src["revision"]
            stale_count += stale
            grouped.setdefault(s["stage"], {}).setdefault(s["market"], []).append({
                "item_id": rec.id, "recorded_status": s["status"], "status": "stale" if stale else s["status"],
                "source": {**src, "current_revision": cur.revision if cur else None},
                "stale": stale, "stale_reason": None if not stale else ("source removed" if cur is None else
                                                                        f"source moved from revision {src['revision']} to {cur.revision}")})
        return {"product_id": product_id, "stages": grouped, "stale_items": stale_count, "restricted_items": restricted}

    def confirm_readiness(self, ctx: AccessContext, item_id: str, status: str, expected_revision: int) -> dict[str, Any]:
        """Re-assess against the current source revision after a source change."""
        item = self.store.read().require(ctx.tenant_id, "readiness_item", item_id).state
        if status not in READINESS_STATUSES:
            raise ValueError(f"status must be one of {READINESS_STATUSES}")
        with self.store.transaction(ctx.actor_id) as tx:
            self.identity.require(ctx, "propose", "readiness_item", item_id, site_id=item["source"].get("site_id"), tx=tx)
            src = tx.require(ctx.tenant_id, item["source"]["kind"], item["source"]["id"])
            rec = tx.put(ctx.tenant_id, "readiness_item", item_id,
                         {**item, "status": status, "source": {**item["source"], "revision": src.revision},
                          "recorded_by": ctx.actor_id, "recorded_at": iso(utc_now())},
                         expected_revision=expected_revision, action="confirm_readiness")
        return {"revision": rec.revision, **rec.state}


# --- scheduling (LS-075) -------------------------------------------------------------------------------------------
_NODE_LIMIT = 50_000


def _dt(value: Any) -> datetime | None:
    try:
        return parse_iso(value) if isinstance(value, str) else None
    except ValueError:
        return None


class SchedulingService:
    """Deterministic, bounded search over equipment slots and lot allocations. Never claims feasibility on missing data."""

    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    @staticmethod
    def missing_inputs(campaign: dict[str, Any], resources: dict[str, Any], materials: dict[str, Any],
                       quality_holds: Any, horizon: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if not _dt((horizon or {}).get("start")) or not _dt((horizon or {}).get("end")):
            missing.append("horizon")
        if quality_holds is None:
            missing.append("quality_holds")
        batches = campaign.get("batches") or []
        if not batches:
            missing.append("campaign.batches")
        equipment = (resources or {}).get("equipment") or {}
        for b in batches:
            bid = b.get("batch_id", "?")
            if not isinstance(b.get("duration_h"), (int, float)) or b["duration_h"] <= 0:
                missing.append(f"batch:{bid}:duration_h")
            if not b.get("equipment"):
                missing.append(f"batch:{bid}:equipment_candidates")
            for eid in b.get("equipment") or []:
                e = equipment.get(eid)
                windows = (e or {}).get("availability")
                if not e or not windows or not all(_dt(w.get("start")) and _dt(w.get("end")) for w in windows):
                    missing.append(f"equipment:{eid}:availability")
                if e is not None and not isinstance(e.get("cleaning_h"), (int, float)):
                    missing.append(f"equipment:{eid}:cleaning_h")
            for m in b.get("materials") or []:
                lots = (materials or {}).get(m["item"])
                if lots is None:
                    missing.append(f"materials:{m['item']}")
                    continue
                for lot in lots:
                    if not isinstance(lot.get("qty"), (int, float)) or not _dt(lot.get("expiry")):
                        missing.append(f"materials:{m['item']}:{lot.get('lot')}:qty_or_expiry")
        return sorted(set(missing))

    def propose_schedule(self, ctx: AccessContext, campaign: dict[str, Any], resources: dict[str, Any], materials: dict[str, Any],
                         quality_holds: list[dict[str, Any]] | None, horizon: dict[str, Any]) -> dict[str, Any]:
        site_id = campaign.get("site_id")
        self.identity.require(ctx, "propose", "schedule_proposal", site_id=site_id)
        inputs = {"campaign": campaign, "resources": resources, "materials": materials, "quality_holds": quality_holds, "horizon": horizon}
        missing = self.missing_inputs(campaign, resources, materials, quality_holds, horizon)
        if missing:
            result: dict[str, Any] = {"status": "incomplete_inputs", "missing": missing, "assignments": [], "violations": []}
        else:
            result = self._solve(campaign, resources, materials, quality_holds or [], horizon)
        sid = new_id("sched")
        state = {"schedule_id": sid, "campaign_id": campaign.get("campaign_id"), "site_id": site_id, **result,
                 "input_hash": content_hash(inputs), "applied": False, "created_by": ctx.actor_id, "created_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, "schedule_proposal", sid, state, expected_revision=None, action="propose_schedule",
                         event_type="schedule.proposed", event_payload={"schedule_id": sid, "status": result["status"]})
        return {"revision": rec.revision, **rec.state}

    def apply_schedule(self, ctx: AccessContext, schedule_id: str, actions: ActionService, owner_id: str) -> dict[str, Any]:
        """Applying is a proposal for authorized approval; nothing in the schedule changes until it is approved and dispatched."""
        rec = self.store.read().require(ctx.tenant_id, "schedule_proposal", schedule_id)
        s = rec.state
        if s["status"] != "feasible":
            raise ValueError(f"only a feasible schedule can be proposed for application (status: {s['status']})")
        return actions.propose(
            ctx, target_system="MES", operation="reschedule_batch", target_id=str(s["campaign_id"]),
            payload={"schedule_id": schedule_id, "assignments": s["assignments"]},
            basis=[{"kind": "schedule_proposal", "id": schedule_id, "revision": rec.revision, "site_id": s["site_id"]}],
            rationale=f"constraint-checked schedule for {len(s['assignments'])} batches (input hash {s['input_hash'][:12]})",
            expected_result="batches start in assigned equipment windows with allocated unexpired, unheld lots",
            owner_id=owner_id, site_id=s["site_id"], constraints=["equipment windows and cleaning time", "lot expiry", "quality holds"])

    # --- solver ----------------------------------------------------------------------------------
    @staticmethod
    def _slot(windows: list[tuple[datetime, datetime]], busy: list[tuple[datetime, datetime]], clean: timedelta,
              dur: timedelta, earliest: datetime) -> datetime | None:
        cands = {earliest, *[w[0] for w in windows], *[b[1] + clean for b in busy]}
        for start in sorted(c for c in cands if c >= earliest):
            end = start + dur
            if any(w[0] <= start and end <= w[1] for w in windows) and \
                    all(end + clean <= bs or start >= be + clean for bs, be in busy):
                return start
        return None

    @staticmethod
    def _allocate(batch: dict[str, Any], start: datetime, lots: dict[str, list[dict[str, Any]]], held: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Allocate earliest-expiry lots; returns (allocations, per-item shortfall reasons)."""
        alloc, remaining, shortfalls = [], {k: {l["lot"]: l["qty"] for l in v} for k, v in lots.items()}, {}
        for m in batch.get("materials") or []:
            need, item = m["qty"], m["item"]
            for lot in sorted(lots.get(item, []), key=lambda l: (_dt(l["expiry"]), l["lot"])):
                if need <= 1e-9:
                    break
                if lot["lot"] in held or _dt(lot["expiry"]) < start:
                    continue
                take = min(need, remaining[item][lot["lot"]])
                if take > 0:
                    remaining[item][lot["lot"]] -= take
                    need -= take
                    alloc.append({"item": item, "lot": lot["lot"], "qty": take})
            if need > 1e-9:
                shortfalls[item] = need
        return alloc, shortfalls

    def _solve(self, campaign: dict[str, Any], resources: dict[str, Any], materials: dict[str, Any],
               holds: list[dict[str, Any]], horizon: dict[str, Any]) -> dict[str, Any]:
        h0, h1 = _dt(horizon["start"]), _dt(horizon["end"])
        held_lots = {h["lot"] for h in holds if h.get("lot")}
        held_eq = {h["equipment"] for h in holds if h.get("equipment")}
        far = datetime.max.replace(tzinfo=h1.tzinfo)
        batches = sorted(campaign["batches"], key=lambda b: (_dt(b.get("due")) or far, _dt(b.get("earliest_start")) or h0, b["batch_id"]))
        eq = resources["equipment"]
        windows = {k: sorted((max(_dt(w["start"]), h0), min(_dt(w["end"]), h1)) for w in v["availability"]) for k, v in eq.items()}
        stats = {"nodes": 0}
        lots_state = {k: [dict(l) for l in v] for k, v in materials.items()}

        def options(b: dict[str, Any], busy: dict[str, list], lots: dict[str, list]) -> list[tuple[str, datetime, list[dict[str, Any]]]]:
            out = []
            for e in b["equipment"]:
                if e in held_eq or e not in windows:
                    continue
                dur, clean = timedelta(hours=b["duration_h"]), timedelta(hours=eq[e]["cleaning_h"])
                start = self._slot(windows[e], busy.get(e, []), clean, dur, max(_dt(b.get("earliest_start")) or h0, h0))
                if start is None or (_dt(b.get("due")) and start + dur > _dt(b["due"])):
                    continue
                alloc, short = self._allocate(b, start, lots, held_lots)
                if not short:
                    out.append((e, start, alloc))
            return out

        def dfs(i: int, busy: dict[str, list], lots: dict[str, list], acc: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
            if i == len(batches):
                return acc
            stats["nodes"] += 1
            if stats["nodes"] > _NODE_LIMIT:
                return None
            b = batches[i]
            for e, start, alloc in sorted(options(b, busy, lots), key=lambda o: (o[1], o[0])):
                end = start + timedelta(hours=b["duration_h"])
                used = {(a["item"], a["lot"]): a["qty"] for a in alloc}
                new_lots = {k: [{**l, "qty": l["qty"] - used.get((k, l["lot"]), 0)} for l in v] for k, v in lots.items()}
                found = dfs(i + 1, {**busy, e: [*busy.get(e, []), (start, end)]}, new_lots,
                            [*acc, {"batch_id": b["batch_id"], "equipment": e, "start": iso(start), "end": iso(end), "lots": alloc,
                                    "cleaning_h": eq[e]["cleaning_h"]}])
                if found is not None:
                    return found
                if stats["nodes"] > _NODE_LIMIT:
                    return None
            return None

        solution = dfs(0, {}, lots_state, [])
        if solution is not None:
            return {"status": "feasible", "assignments": sorted(solution, key=lambda a: (a["start"], a["batch_id"])), "violations": [],
                    "search_nodes": stats["nodes"]}
        if stats["nodes"] > _NODE_LIMIT:
            return {"status": "search_limit_reached", "assignments": [], "violations": [],
                    "detail": "search bound exceeded; neither feasibility nor infeasibility is established"}
        return {"status": "infeasible", "assignments": [], "violations": self._diagnose(batches, eq, windows, lots_state, held_lots, held_eq, h0),
                "search_nodes": stats["nodes"]}

    def _diagnose(self, batches: list[dict[str, Any]], eq: dict[str, Any], windows: dict[str, list], lots: dict[str, list],
                  held_lots: set[str], held_eq: set[str], h0: datetime) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for b in batches:
            dur, bid = timedelta(hours=b["duration_h"]), b["batch_id"]
            usable, slots = [e for e in b["equipment"] if e not in held_eq], []
            if not usable:
                out.append({"batch_id": bid, "constraint": "equipment_quality_hold", "detail": f"all candidate equipment held: {b['equipment']}"})
            for e in usable:
                s = self._slot(windows[e], [], timedelta(hours=eq[e]["cleaning_h"]), dur, max(_dt(b.get("earliest_start")) or h0, h0))
                if s is not None:
                    slots.append((s, e))
            if usable and not slots:
                out.append({"batch_id": bid, "constraint": "no_equipment_window",
                            "detail": f"no availability window fits {b['duration_h']}h on {usable} within the horizon"})
            if slots and _dt(b.get("due")) and min(slots)[0] + dur > _dt(b["due"]):
                out.append({"batch_id": bid, "constraint": "due_date", "detail": f"earliest possible end {iso(min(slots)[0] + dur)} is after due {b['due']}"})
            use = min(slots)[0] if slots else (_dt(b.get("earliest_start")) or h0)
            for m in b.get("materials") or []:
                every = lots.get(m["item"], [])
                unheld = [l for l in every if l["lot"] not in held_lots]
                fresh = [l for l in unheld if _dt(l["expiry"]) >= use]
                if sum(l["qty"] for l in every) < m["qty"]:
                    out.append({"batch_id": bid, "constraint": "material_shortage", "detail": f"{m['item']}: need {m['qty']}, on hand {sum(l['qty'] for l in every)}"})
                elif sum(l["qty"] for l in unheld) < m["qty"]:
                    out.append({"batch_id": bid, "constraint": "quality_hold_on_lot",
                                "detail": f"{m['item']}: unheld quantity {sum(l['qty'] for l in unheld)} < {m['qty']}; held lots {sorted(held_lots & {l['lot'] for l in every})}"})
                elif sum(l["qty"] for l in fresh) < m["qty"]:
                    out.append({"batch_id": bid, "constraint": "material_expired", "detail": f"{m['item']}: unexpired quantity at {iso(use)} < {m['qty']}"})
        demand: dict[str, float] = {}
        for b in batches:
            for m in b.get("materials") or []:
                demand[m["item"]] = demand.get(m["item"], 0) + m["qty"]
        for item, need in sorted(demand.items()):
            have = sum(l["qty"] for l in lots.get(item, []) if l["lot"] not in held_lots)
            if have < need and not any(v["constraint"] in ("material_shortage", "quality_hold_on_lot") and item in v["detail"] for v in out):
                out.append({"batch_id": None, "constraint": "material_shortage_campaign", "detail": f"{item}: campaign needs {need}, unheld stock {have}"})
        if not out:
            out.append({"batch_id": None, "constraint": "resource_contention",
                        "detail": "each batch is feasible alone but no combination of equipment slots, cleaning gaps and lot allocations satisfies all batches"})
        return out
