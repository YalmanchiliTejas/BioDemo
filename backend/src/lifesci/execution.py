"""Production context and guided execution (LS-001, LS-008 web only, LS-035, LS-073, LS-074, LS-078, LS-079, LS-083).

Production orders, batches, material lots and equipment are records that are either projected from an
authoritative external system (MES/ERP, with source references) or natively managed only where the
ownership registry enables native ``batch_record`` ownership. Step execution is deterministic: dependency
order, branch, limits, calculations, material/equipment eligibility and signature binding are enforced
in code. Out-of-limit values never complete a step; they create an exception record and an
``exec.exception`` event. Loss of authority pauses dependent steps; offline drafts are provisional only.
Batch release is never performed here: ``request_release`` only creates a ``release_batch`` proposal,
and an empty exception list is reported together with the explicit unchecked scope.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import content_hash, iso, utc_now
from .ownership import OwnershipRegistry, OwnershipViolation
from .procedures import TERMINAL, ProcedureService, blocking_reasons, convert, descendants, evaluate_step, finish_step
from .records import SignatureService
from .store import RecordStore, Transaction

RESOURCE_KINDS = ("production_order", "batch", "material_lot", "equipment")
DEVICE_SUPPORT = {"web": True, "mobile": False, "tablet": False, "hands_free": False, "wearable": False}
OPEN_STATUSES = ("pending", "exception", "awaiting_signature", "paused_authority_lost")
OUT_OF_SCOPE = (
    "reconciliation with the external MES/ERP system of record",
    "raw equipment and instrument data originals",
    "environmental monitoring and utilities data",
    "deviation/CAPA closure in the QMS",
    "analytical (LIMS) results and specifications",
    "personnel training and qualification status",
    "material genealogy beyond the lots entered in executed steps",
)


class DeviceNotQualified(PermissionError):
    pass


class ResourceIneligible(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class AuthorityLost(PermissionError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("authority lost: " + "; ".join(reasons))
        self.reasons = reasons


class StepBlocked(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _today() -> str:
    return utc_now().date().isoformat()


def lot_problems(lot: dict[str, Any] | None, lot_id: str, quantity: float | None, unit: str | None,
                 site_id: str | None, today: str | None = None) -> list[str]:
    """Reasons a material/reagent lot is ineligible: not released, expired, insufficient or at another site."""
    if lot is None:
        return [f"lot {lot_id} not found"]
    today = today or _today()
    out = []
    if lot.get("status") != "released":
        out.append(f"lot {lot_id} is {lot.get('status')}, not released")
    if lot.get("expiry") and str(lot["expiry"])[:10] < today:
        out.append(f"lot {lot_id} expired {str(lot['expiry'])[:10]}")
    if site_id and lot.get("site_id") not in (None, site_id):
        out.append(f"lot {lot_id} belongs to site {lot.get('site_id')}")
    if quantity is not None:
        try:
            have = convert(float(lot.get("quantity", 0)), lot.get("unit"), unit) if unit else float(lot.get("quantity", 0))
        except ValueError as exc:
            return [*out, f"lot {lot_id}: {exc}"]
        if have + 1e-9 < quantity:
            out.append(f"lot {lot_id} has {have:g} {unit or ''} available, {quantity:g} required".replace("  ", " "))
    return out


def equipment_problems(eq: dict[str, Any] | None, eq_id: str, site_id: str | None, today: str | None = None) -> list[str]:
    if eq is None:
        return [f"equipment {eq_id} not found"]
    today = today or _today()
    out = []
    if eq.get("status") != "available":
        out.append(f"equipment {eq_id} is {eq.get('status')}, not available")
    due = eq.get("qualification_due")
    if not due:
        out.append(f"equipment {eq_id} has no qualification due date on record")
    elif str(due)[:10] < today:
        out.append(f"equipment {eq_id} qualification overdue since {str(due)[:10]}")
    if eq.get("maintenance_status") == "overdue":
        out.append(f"equipment {eq_id} maintenance is overdue")
    if site_id and eq.get("site_id") not in (None, site_id):
        out.append(f"equipment {eq_id} belongs to site {eq.get('site_id')}")
    return out


class ExecutionService:
    def __init__(self, store: RecordStore, identity: IdentityService, ownership: OwnershipRegistry,
                 procedures: ProcedureService, signatures: SignatureService, evidence: Any = None) -> None:
        self.store, self.idn, self.own, self.ps, self.sigs, self.evidence = store, identity, ownership, procedures, signatures, evidence

    # --- resource and batch records (LS-073, LS-001) ---
    def project_external(self, ctx: AccessContext, kind: str, external_id: str, state: dict[str, Any], *, source_system: str,
                         source_ref: str, site_id: str, source_revision: Any = None) -> dict[str, Any]:
        """Store a read-only projection from MES/ERP with its source reference; never overrides native ownership."""
        if kind not in RESOURCE_KINDS:
            raise ValueError(f"kind must be one of {list(RESOURCE_KINDS)}")
        self.idn.require(ctx, "configure", kind, site_id=site_id)
        if self.own.resolve(ctx.tenant_id, "batch_record", site_id).owner == "native":
            raise OwnershipViolation(f"batch_record@{site_id} is natively owned; external projections are not accepted")
        rid = f"{source_system}:{external_id}"
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, kind, rid)
            if cur and isinstance(source_revision, int) and isinstance(cur.state["source"].get("revision"), int) \
                    and source_revision < cur.state["source"]["revision"]:
                return {**cur.state, "revision": cur.revision, "ignored": "older source revision"}
            new = {**state, "id": rid, "site_id": site_id, "origin": "projection", "status": state.get("status"),
                   "source": {"system": source_system, "ref": source_ref, "revision": source_revision, "as_of": iso(utc_now())}}
            if cur and {k: v for k, v in cur.state.items() if k != "source"} == {k: v for k, v in new.items() if k != "source"} \
                    and cur.state["source"]["revision"] == source_revision:
                return {**cur.state, "revision": cur.revision, "duplicate": True}
            rec = tx.put(ctx.tenant_id, kind, rid, new, expected_revision=cur.revision if cur else None,
                         action="project", event_type=f"exec.{kind}_projected", event_payload={"id": rid, "site_id": site_id})
        return {**new, "revision": rec.revision}

    def create_native(self, ctx: AccessContext, kind: str, record_id: str, state: dict[str, Any], *, site_id: str) -> dict[str, Any]:
        if kind not in RESOURCE_KINDS:
            raise ValueError(f"kind must be one of {list(RESOURCE_KINDS)}")
        self.own.check_native(ctx.tenant_id, "batch_record", site_id)
        self.idn.require(ctx, "configure", kind, site_id=site_id)
        new = {**state, "id": record_id, "site_id": site_id, "origin": "native"}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, kind, record_id, new, expected_revision=None, action="create_native",
                         event_type=f"exec.{kind}_created", event_payload={"id": record_id, "site_id": site_id})
        return {**new, "revision": rec.revision}

    def update_native(self, ctx: AccessContext, kind: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, kind, record_id)
            if rec.state.get("origin") != "native":
                raise OwnershipViolation(f"{kind}:{record_id} is a projection; update it at its source system")
            self.own.check_native(ctx.tenant_id, "batch_record", rec.state["site_id"], tx)
            self.idn.require(ctx, "configure", kind, record_id, site_id=rec.state["site_id"], tx=tx)
            out = tx.put(ctx.tenant_id, kind, record_id, {**rec.state, **changes}, expected_revision=rec.revision,
                         action="update_native", event_type=f"exec.{kind}_updated", event_payload={"id": record_id})
        return {**out.state, "revision": out.revision}

    def get(self, ctx: AccessContext, kind: str, record_id: str) -> dict[str, Any]:
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, kind, record_id)
        self.idn.require(ctx, "read", kind, record_id, site_id=rec.state.get("site_id"), tx=tx)
        return {**rec.state, "revision": rec.revision}

    def create_batch(self, ctx: AccessContext, batch_id: str, *, product: str, modality: str, site_id: str,
                     order_id: str | None = None, development_refs: list[dict[str, Any]] | None = None,
                     identity_fields: dict[str, Any] | None = None) -> dict[str, Any]:
        """A native batch linking product, modality and authorized development records (LS-001)."""
        refs = development_refs or []
        if refs and not self.idn.check_derived(ctx, refs):
            raise PermissionError("development context includes a record the actor cannot read")
        batch = self.create_native(ctx, "batch", batch_id, {"product": product, "modality": modality, "order_id": order_id,
                                                           "status": "planned", "development_refs": refs,
                                                           "identity_fields": identity_fields or {}}, site_id=site_id)
        with self.store.transaction(ctx.actor_id) as tx:
            for r in refs:
                tx.add_edge(ctx.tenant_id, (r["kind"], r["id"]), ("batch", batch_id), "informs_batch")
        return batch

    def link_development_context(self, ctx: AccessContext, batch_id: str, development_refs: list[dict[str, Any]]) -> dict[str, Any]:
        """Attach development records to any batch (native or projected) as a context overlay."""
        if not self.idn.check_derived(ctx, development_refs):
            raise PermissionError("development context includes a record the actor cannot read")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "batch", batch_id)
            self.idn.require(ctx, "propose", "batch", batch_id, site_id=rec.state["site_id"], tx=tx)
            merged = [*rec.state.get("development_refs", []),
                      *[r for r in development_refs if r not in rec.state.get("development_refs", [])]]
            out = tx.put(ctx.tenant_id, "batch", batch_id, {**rec.state, "development_refs": merged},
                         expected_revision=rec.revision, action="link_development_context")
            for r in development_refs:
                tx.add_edge(ctx.tenant_id, (r["kind"], r["id"]), ("batch", batch_id), "informs_batch")
        return {**out.state, "revision": out.revision}

    def batch_context(self, ctx: AccessContext, batch_id: str) -> dict[str, Any]:
        """Batch with only the development records this actor may read; others are counted, not shown."""
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, "batch", batch_id)
        self.idn.require(ctx, "read", "batch", batch_id, site_id=rec.state["site_id"], tx=tx)
        visible = [r for r in rec.state.get("development_refs", []) if self.idn.check_derived(ctx, [r], tx=tx)]
        return {**rec.state, "revision": rec.revision, "development_refs": visible,
                "development_refs_withheld": len(rec.state.get("development_refs", [])) - len(visible)}

    # --- instances and authority (LS-079) ---
    def create_instance(self, ctx: AccessContext, procedure_id: str, *, batch_id: str, site_id: str,
                        params: Mapping[str, Any] | None = None, revision: int | None = None) -> dict[str, Any]:
        batch = self.get(ctx, "batch", batch_id)
        if batch["site_id"] != site_id:
            raise ValueError("batch belongs to a different site")
        return self.ps.create_instance(ctx, procedure_id, site_id=site_id, params=params, revision=revision,
                                       context={"batch_id": batch_id, "product": batch.get("product"), "modality": batch.get("modality"),
                                                "order_id": batch.get("order_id")})

    def start(self, ctx: AccessContext, instance: str | dict[str, Any]) -> dict[str, Any]:
        iid = instance if isinstance(instance, str) else instance["instance_id"]
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", iid)
            self.own.check_native(ctx.tenant_id, "batch_record", rec.state["site_id"], tx)
            self.idn.require(ctx, "execute", "step_execution", f"{iid}:*", site_id=rec.state["site_id"], tx=tx)
            if rec.state["status"] != "created":
                raise ValueError(f"instance is {rec.state['status']}")
            out = tx.put(ctx.tenant_id, "procedure_instance", iid,
                         {**rec.state, "status": "in_progress", "started_by": ctx.actor_id, "started_at": iso(utc_now())},
                         expected_revision=rec.revision, action="start", event_type="exec.started",
                         event_payload={"instance_id": iid, "batch_id": rec.state["context"].get("batch_id")})
        return {**out.state, "record_revision": out.revision}

    def _authority_reasons(self, ctx: AccessContext, inst: dict[str, Any], tx: Transaction | None = None) -> dict[str, list[str]]:
        live = self.idn.context_for(ctx.tenant_id, ctx.actor_id, actor_kind=ctx.actor_kind, partner_org_id=ctx.partner_org_id)
        out: dict[str, list[str]] = {"actor": [], "ownership": [], "connectivity": []}
        d = self.idn.check(live, "execute", "step_execution", f"{inst['instance_id']}:*", site_id=inst["site_id"], tx=tx)
        if not d:
            out["actor"].append(f"actor authority: {d.reason}")
        own = self.own.resolve(ctx.tenant_id, "batch_record", inst["site_id"], tx)
        if own.owner != "native":
            out["ownership"].append(f"native execution not enabled (owner is {own.owner})")
        if not inst["authority"]["available"]:
            out["connectivity"].append("authoritative system connectivity unavailable")
        return out

    def check_authority(self, ctx: AccessContext, instance_id: str, step_id: str | None = None) -> dict[str, Any]:
        """Re-evaluate authority; pause affected steps and everything downstream, list unaffected parallel steps.

        Ownership loss pauses every open step; connectivity loss pauses steps in the lost authority scopes
        (all steps if no scope is named); a participant who lost their role pauses only steps they started or attempt.
        An actor who never took part cannot pause anything; they are simply denied.
        """
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
            inst = copy.deepcopy(rec.state)
            reasons = self._authority_reasons(ctx, inst, tx)
            flat = [r for v in reasons.values() for r in v]
            if not flat:
                return {"ok": True, "reasons": [], "paused_steps": self._paused(inst), "unaffected_parallel_steps": []}
            scopes = inst["authority"]["lost_scopes"]
            opened = {sid: st for sid, st in inst["steps"].items() if st["status"] in OPEN_STATUSES}
            affected: set[str] = set()
            if reasons["ownership"]:
                affected |= set(opened)
            if reasons["connectivity"]:
                affected |= {sid for sid in opened if not scopes or inst["steps_def"][sid].get("authority_scope", "default") in scopes}
            participant = ctx.actor_id == inst.get("started_by") or any(st.get("performed_by") == ctx.actor_id for st in inst["steps"].values())
            if reasons["actor"] and participant:
                affected |= {sid for sid, st in opened.items() if st.get("performed_by") == ctx.actor_id or sid == step_id}
            steps = list(inst["steps_def"].values())
            for sid in list(affected):
                affected |= {d for d in descendants(steps, sid) if inst["steps"][d]["status"] in OPEN_STATUSES}
            changed = False
            for sid in affected:
                st = inst["steps"][sid]
                if st["status"] != "paused_authority_lost":
                    st.update(paused_from=st["status"], status="paused_authority_lost", version=st["version"] + 1)
                    changed = True
            if changed:
                tx.put(ctx.tenant_id, "procedure_instance", instance_id, inst, expected_revision=rec.revision,
                       action="pause_authority_lost", reason="; ".join(flat), event_type="exec.paused_authority_lost",
                       event_payload={"instance_id": instance_id, "steps": sorted(affected), "reasons": flat})
            unaffected = sorted(sid for sid, st in inst["steps"].items() if st["status"] in OPEN_STATUSES and sid not in affected)
        return {"ok": False, "reasons": flat, "participant": participant, "reason_kinds": {k: v for k, v in reasons.items() if v},
                "paused_steps": sorted(affected), "unaffected_parallel_steps": unaffected}

    @staticmethod
    def _paused(inst: dict[str, Any]) -> list[str]:
        return sorted(s for s, st in inst["steps"].items() if st["status"] == "paused_authority_lost")

    def set_connectivity(self, ctx: AccessContext, instance_id: str, available: bool, *, scopes: list[str] | None = None) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
            self.idn.require(ctx, "configure", "procedure_instance", instance_id, site_id=rec.state["site_id"], tx=tx)
            auth = {"available": available, "lost_scopes": [] if available else list(scopes or []), "changed_by": ctx.actor_id,
                    "changed_at": iso(utc_now())}
            tx.put(ctx.tenant_id, "procedure_instance", instance_id, {**rec.state, "authority": auth},
                   expected_revision=rec.revision, action="set_connectivity", event_type="exec.connectivity_changed",
                   event_payload={"instance_id": instance_id, "available": available, "scopes": auth["lost_scopes"]})
        return auth

    def resume_after_authority(self, ctx: AccessContext, instance_id: str) -> dict[str, Any]:
        """Paused steps return to their prior status only when every authority condition holds again."""
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
            inst = copy.deepcopy(rec.state)
            reasons = [r for v in self._authority_reasons(ctx, inst, tx).values() for r in v]
            if reasons:
                raise AuthorityLost(reasons)
            resumed = []
            for sid, st in inst["steps"].items():
                if st["status"] == "paused_authority_lost":
                    st.update(status=st.pop("paused_from", "pending"), version=st["version"] + 1)
                    resumed.append(sid)
            tx.put(ctx.tenant_id, "procedure_instance", instance_id, inst, expected_revision=rec.revision,
                   action="resume_authority", event_type="exec.resumed", event_payload={"instance_id": instance_id, "steps": resumed})
        return {"resumed": resumed}

    # --- guided step execution (LS-079, LS-073, LS-035, LS-008) ---
    @staticmethod
    def supported_devices() -> dict[str, Any]:
        return {d: {"qualified": ok, "note": None if ok else "device not qualified; declared only"} for d, ok in DEVICE_SUPPORT.items()}

    def perform_step(self, ctx: AccessContext, instance_id: str, step_id: str, captured_values: Mapping[str, Any],
                     resources: Mapping[str, Any] | None = None, *, device_type: str = "web") -> dict[str, Any]:
        if not DEVICE_SUPPORT.get(device_type):
            raise DeviceNotQualified(f"device not qualified: {device_type}")
        report = self.check_authority(ctx, instance_id, step_id)
        if not report["ok"] and report["reason_kinds"].get("actor") and not report["participant"]:
            raise AuthorizationError(Decision(False, report["reasons"][0]))
        if not report["ok"] and (step_id in report["paused_steps"] or "actor" in report["reason_kinds"]
                                 or "ownership" in report["reason_kinds"]):
            raise AuthorityLost(report["reasons"])
        resources = resources or {}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
            inst = rec.state
            self.idn.require(ctx, "execute", "step_execution", f"{instance_id}:{step_id}", site_id=inst["site_id"], tx=tx)
            blocked = blocking_reasons(inst, step_id)
            if blocked:
                raise StepBlocked(blocked)
            step = inst["steps_def"][step_id]
            problems, used = self._check_resources(tx, ctx.tenant_id, inst, step, resources)
            if problems:
                raise ResourceIneligible(problems)
            consts = {**inst["constants"], **{k: v for k, v in inst["params"].items() if isinstance(v, (int, float))}}
            ev = evaluate_step(step, captured_values, inst["values"], consts)
            hold = step.get("enforcement", {}).get("hold_on_out_of_limit", True)
            attempt = inst["steps"][step_id]["attempts"] + 1
            exec_id = f"{instance_id}:{step_id}:{attempt}"
            exceptional = bool(ev["violations"]) and hold
            exec_state = {
                "execution_id": exec_id, "instance_id": instance_id, "step_id": step_id, "attempt": attempt,
                "procedure_ref": {"procedure_id": inst["procedure_id"], "revision": inst["revision"],
                                  "definition_hash": inst["definition_hash"], "step_hash": content_hash(step),
                                  "amendment_count": inst["amendment_count"]},
                "values": ev["inputs"], "calculated": ev["calculated"], "evaluations": ev["evaluations"],
                "resources": used["snapshot"], "device_type": device_type, "performed_by": ctx.actor_id,
                "performed_at": iso(utc_now()), "outcome": "exception" if exceptional else "in_limits",
                "limit_violations_accepted": bool(ev["violations"]) and not hold,
                "required_signatures": step.get("required_signatures", [])}
            erec = tx.put(ctx.tenant_id, "step_execution", exec_id, exec_state, expected_revision=None, action="perform",
                          event_type="exec.step_recorded", event_payload={"instance_id": instance_id, "step_id": step_id})
            new = copy.deepcopy(inst)
            st = new["steps"][step_id]
            st.update(attempts=attempt, last_execution_id=exec_id, performed_by=ctx.actor_id)
            result: dict[str, Any] = {"execution_id": exec_id, "evaluations": ev["evaluations"], "calculated": ev["calculated"],
                                      "device_type": device_type}
            if exceptional:
                exc_id = f"{exec_id}:exc"
                v = ev["violations"][0]
                tx.put(ctx.tenant_id, "exec_exception", exc_id,
                       {"exception_id": exc_id, "instance_id": instance_id, "step_id": step_id, "execution_id": exec_id,
                        "batch_id": inst["context"].get("batch_id"), "site_id": inst["site_id"], "violations": ev["violations"],
                        "status": "open", "detected_by": ctx.actor_id, "detected_at": iso(utc_now())},
                       expected_revision=None, action="exception", event_type="exec.exception",
                       event_payload={"instance_id": instance_id, "step_id": step_id, "exception_id": exc_id,
                                      "parameter": v["name"], "value": v["value"], "low": v["low"], "high": v["high"],
                                      "site_id": inst["site_id"]})
                st.update(status="exception", version=st["version"] + 1)
                tx.put(ctx.tenant_id, "procedure_instance", instance_id, new, expected_revision=rec.revision, action="step_exception")
                return {**result, "status": "exception", "exception_id": exc_id, "violations": ev["violations"]}
            for lot_id, qty in used["consume"].items():
                lot = tx.require(ctx.tenant_id, "material_lot", lot_id)
                tx.put(ctx.tenant_id, "material_lot", lot_id, {**lot.state, "quantity": round(lot.state["quantity"] - qty, 9)},
                       expected_revision=lot.revision, action="consume", reason=exec_id)
            if step.get("required_signatures"):
                st.update(status="awaiting_signature", version=st["version"] + 1)
                tx.put(ctx.tenant_id, "procedure_instance", instance_id, new, expected_revision=rec.revision,
                       action="await_signature", event_type="exec.awaiting_signature",
                       event_payload={"instance_id": instance_id, "step_id": step_id})
                return {**result, "status": "awaiting_signature", "required_signatures": step["required_signatures"]}
            done = finish_step(new, step_id, {**ev["inputs"], **ev["calculated"]}, extra={})
            tx.put(ctx.tenant_id, "procedure_instance", instance_id, done, expected_revision=rec.revision, action="complete_step",
                   event_type="exec.step_completed", event_payload={"instance_id": instance_id, "step_id": step_id})
            return {**result, "status": "completed", "instance_status": done["status"]}

    def _check_resources(self, tx: Transaction, tenant: str, inst: dict[str, Any], step: dict[str, Any],
                         resources: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
        req = step.get("resources", {})
        problems: list[str] = []
        lots = [{"lot_id": x, "quantity": None} if isinstance(x, str) else dict(x) for x in resources.get("lots", [])]
        eq_ids = list(resources.get("equipment", []))
        site = inst["site_id"]
        consume: dict[str, float] = {}
        snapshot: dict[str, Any] = {"lots": [], "equipment": []}
        recs: dict[str, dict[str, Any] | None] = {}
        for lot in lots:
            r = tx.get(tenant, "material_lot", lot["lot_id"])
            recs[lot["lot_id"]] = r.state if r else None
        for need in req.get("materials", []):
            matching = [l for l in lots if (recs[l["lot_id"]] or {}).get("material_id") == need["material_id"]]
            if not matching:
                problems.append(f"required material {need['material_id']} has no lot supplied")
                continue
            try:
                if len(matching) == 1 and matching[0]["quantity"] is None:
                    lu = recs[matching[0]["lot_id"]].get("unit")
                    matching[0]["quantity"] = convert(float(need["quantity"]), need.get("unit"), lu) if lu else need["quantity"]
                if any(l["quantity"] is None for l in matching):
                    problems.append(f"specify the quantity drawn from each lot of {need['material_id']} (in the lot's unit)")
                    continue
                total = sum(convert(float(l["quantity"]), recs[l["lot_id"]].get("unit"), need.get("unit")) for l in matching)
            except ValueError as exc:
                problems.append(f"{need['material_id']}: {exc}")
                continue
            if total + 1e-9 < need["quantity"]:
                problems.append(f"{need['material_id']}: {total:g} {need.get('unit') or ''} supplied, {need['quantity']:g} required")
        for l in lots:
            state = recs[l["lot_id"]]
            problems += lot_problems(state, l["lot_id"], l["quantity"], (state or {}).get("unit"), site)
            if state is not None and l["quantity"] is not None:
                consume[l["lot_id"]] = consume.get(l["lot_id"], 0.0) + float(l["quantity"])
            snapshot["lots"].append({"lot_id": l["lot_id"], "material_id": (state or {}).get("material_id"),
                                     "status": (state or {}).get("status"), "expiry": (state or {}).get("expiry"),
                                     "quantity_used": l["quantity"]})
        eq_states = {}
        for eid in eq_ids:
            r = tx.get(tenant, "equipment", eid)
            eq_states[eid] = r.state if r else None
            problems += equipment_problems(eq_states[eid], eid, site)
            snapshot["equipment"].append({"equipment_id": eid, "status": (eq_states[eid] or {}).get("status"),
                                          "qualification_due": (eq_states[eid] or {}).get("qualification_due")})
        for need in req.get("equipment", []):
            if not any((eq_states[e] or {}).get("equipment_class") == need["role"] for e in eq_ids):
                problems.append(f"required equipment {need['role']} not supplied")
        return list(dict.fromkeys(problems)), {"consume": consume, "snapshot": snapshot}

    # --- signatures (LS-035) ---
    def sign_step(self, ctx: AccessContext, instance_id: str, step_id: str, meaning: str,
                  authentication: dict[str, Any]) -> dict[str, Any]:
        tx0 = self.store.read()
        inst = tx0.require(ctx.tenant_id, "procedure_instance", instance_id).state
        st = inst["steps"][step_id]
        if st["status"] != "awaiting_signature":
            raise ValueError(f"step is {st['status']}, not awaiting signature")
        step = inst["steps_def"][step_id]
        if meaning not in step.get("required_signatures", []):
            raise ValueError(f"{meaning} is not a required signature for {step_id}")
        exec_rec = tx0.require(ctx.tenant_id, "step_execution", st["last_execution_id"])
        performer = exec_rec.state["performed_by"]
        if meaning == "performed" and ctx.actor_id != performer:
            raise AuthorizationError(Decision(False, "only the performer can sign as performed"))
        if meaning != "performed" and ctx.actor_id == performer:
            raise AuthorizationError(Decision(False, f"the performer cannot sign as {meaning}"))
        existing = self.sigs.required_signatures_present(ctx.tenant_id, "step_execution", exec_rec.id, [meaning], tx0)
        if existing[meaning]:
            raise ValueError(f"{meaning} signature already recorded on this content")
        sig = self.sigs.sign(ctx, "step_execution", exec_rec.id, expected_revision=exec_rec.revision, meaning=meaning,
                             authentication=authentication, site_id=inst["site_id"])
        return {"signature": sig.to_dict(), **self.complete_if_signed(ctx, instance_id, step_id)}

    def complete_if_signed(self, ctx: AccessContext, instance_id: str, step_id: str) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
            inst = rec.state
            st = inst["steps"][step_id]
            if st["status"] != "awaiting_signature":
                return {"completed": st["status"] == "completed", "present": {}}
            required = inst["steps_def"][step_id].get("required_signatures", [])
            present = self.sigs.required_signatures_present(ctx.tenant_id, "step_execution", st["last_execution_id"], required, tx)
            if not all(present.values()):
                return {"completed": False, "present": present}
            exec_rec = tx.require(ctx.tenant_id, "step_execution", st["last_execution_id"])
            sig_ids = [s["signature_id"] for s in self.sigs.signatures_for(ctx.tenant_id, "step_execution", exec_rec.id, tx)
                       if s["content_hash"] == exec_rec.content_hash]
            done = finish_step(inst, step_id, {**exec_rec.state["values"], **exec_rec.state["calculated"]},
                               extra={"signature_ids": sig_ids})
            tx.put(ctx.tenant_id, "procedure_instance", instance_id, done, expected_revision=rec.revision, action="complete_step",
                   event_type="exec.step_completed", event_payload={"instance_id": instance_id, "step_id": step_id})
        return {"completed": True, "present": present, "instance_status": done["status"]}

    def resolve_exception(self, ctx: AccessContext, exception_id: str, disposition: str, reason: str) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise ValueError("a disposition requires a reason")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "exec_exception", exception_id)
            self.idn.require(ctx, "approve", "step_execution", rec.state["execution_id"], site_id=rec.state["site_id"], tx=tx)
            out = tx.put(ctx.tenant_id, "exec_exception", exception_id,
                         {**rec.state, "status": "dispositioned", "disposition": disposition, "disposition_reason": reason,
                          "dispositioned_by": ctx.actor_id, "dispositioned_at": iso(utc_now())},
                         expected_revision=rec.revision, action="disposition", reason=reason)
        return out.state

    # --- offline (LS-083) ---
    def submit_offline_draft(self, ctx: AccessContext, instance_id: str, step_id: str, values: Mapping[str, Any],
                             client_revision: int, device_id: str) -> dict[str, Any]:
        if any(k in values for k in ("signature", "signatures", "signed_by")):
            raise ValueError("offline drafts cannot carry signatures")
        digest = content_hash([instance_id, step_id, dict(values), client_revision, device_id])[:24]
        draft_id = f"odr_{digest}"
        with self.store.transaction(ctx.actor_id) as tx:
            inst = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
            self.idn.require(ctx, "execute", "step_execution", f"{instance_id}:{step_id}", site_id=inst.state["site_id"], tx=tx)
            if step_id not in inst.state["steps"]:
                raise ValueError(f"unknown step {step_id}")
            existing = tx.get(ctx.tenant_id, "offline_draft", draft_id)
            if existing:
                return {**existing.state, "duplicate": True}
            state = {"draft_id": draft_id, "instance_id": instance_id, "step_id": step_id, "values": dict(values),
                     "client_revision": client_revision, "device_id": device_id, "submitted_by": ctx.actor_id,
                     "submitted_at": iso(utc_now()), "provisional": True, "signatures": [], "status": "provisional",
                     "authoritative": False, "pinned_revision_at_submit": inst.state["revision"]}
            tx.put(ctx.tenant_id, "offline_draft", draft_id, state, expected_revision=None, action="offline_draft",
                   event_type="exec.offline_draft_received", event_payload={"instance_id": instance_id, "step_id": step_id})
        return state

    def reconcile_offline(self, ctx: AccessContext, draft_id: str) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            d = tx.require(ctx.tenant_id, "offline_draft", draft_id)
            cur = tx.require(ctx.tenant_id, "procedure_instance", d.state["instance_id"])
            self.idn.require(ctx, "execute", "step_execution", f"{d.state['instance_id']}:{d.state['step_id']}",
                             site_id=cur.state["site_id"], tx=tx)
            sid = d.state["step_id"]
            snap = tx.revision(ctx.tenant_id, "procedure_instance", d.state["instance_id"], d.state["client_revision"])
            conflicts: list[str] = []
            if snap is None:
                conflicts.append(f"client revision {d.state['client_revision']} is unknown to the server")
            else:
                if snap.state["amendment_count"] != cur.state["amendment_count"] or snap.state["revision"] != cur.state["revision"]:
                    conflicts.append("procedure was amended after the draft's base revision")
                if snap.state["steps"][sid]["version"] != cur.state["steps"][sid]["version"]:
                    conflicts.append(f"step {sid} changed on the server since the draft's base revision")
            status = cur.state["steps"][sid]["status"]
            if status in TERMINAL or status == "awaiting_signature":
                conflicts.append(f"step {sid} is already {status}")
            conflicts += [r for r in blocking_reasons({**cur.state, "status": "in_progress"}, sid) if r.startswith("dependency")]
            outcome = "conflict" if conflicts else "clean"
            tx.put(ctx.tenant_id, "offline_draft", draft_id,
                   {**d.state, "status": f"reconciled_{outcome}", "conflicts": conflicts, "reconciled_by": ctx.actor_id,
                    "reconciled_at": iso(utc_now())}, expected_revision=d.revision, action=f"reconcile_{outcome}")
        return {"status": outcome, "conflicts": conflicts, "values": d.state["values"], "completes_step": False,
                "next_action": "no conflicts: a person must perform the step authoritatively with perform_step"
                if outcome == "clean" else "resolve conflicts; draft values are not authoritative"}

    # --- electronic batch record and review by exception (LS-078) ---
    def batch_record(self, ctx: AccessContext, instance_id: str) -> dict[str, Any]:
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
        inst = rec.state
        self.idn.require(ctx, "read", "procedure_instance", instance_id, site_id=inst["site_id"], tx=tx)
        execs = tx.list(ctx.tenant_id, "step_execution", lambda s: s["instance_id"] == instance_id)
        excs = [r.state for r in tx.list(ctx.tenant_id, "exec_exception", lambda s: s["instance_id"] == instance_id)]
        drafts = [r.state for r in tx.list(ctx.tenant_id, "offline_draft", lambda s: s["instance_id"] == instance_id)]
        checked: list[str] = []
        unchecked: list[str] = []
        steps_out = []
        broken: list[str] = []
        for sid in inst["order"]:
            st = inst["steps"][sid]
            mine = [e for e in execs if e.state["step_id"] == sid]
            sigs = []
            for e in mine:
                for s in self.sigs.signatures_for(ctx.tenant_id, "step_execution", e.id, tx):
                    v = self.sigs.verify(ctx.tenant_id, s["signature_id"], tx)
                    sigs.append({"signature_id": s["signature_id"], "meaning": s["meaning"], "actor_id": s["actor_id"],
                                 "execution_id": e.id, "covers_current_content": v["covers_current_content"]})
                    if not v["covers_current_content"]:
                        broken.append(s["signature_id"])
            steps_out.append({"step_id": sid, "title": inst["steps_def"][sid]["title"], "status": st["status"],
                              "attempts": [{"execution_id": e.id, "values": e.state["values"], "calculated": e.state["calculated"],
                                            "outcome": e.state["outcome"], "performed_by": e.state["performed_by"],
                                            "device_type": e.state["device_type"], "resources": e.state["resources"]} for e in mine],
                              "signatures": sigs, "branch_taken": st.get("branch_taken"), "not_applicable": st.get("na")})
        open_steps = [s for s in inst["order"] if inst["steps"][s]["status"] not in TERMINAL]
        (unchecked if open_steps else checked).append(
            f"steps not terminal: {open_steps}" if open_steps else f"all {len(inst['order'])} steps terminal")
        completed_ok = all(all(e["within_limits"] for e in ex.state["evaluations"]) for ex in execs
                           if inst["steps"][ex.state["step_id"]]["status"] == "completed"
                           and inst["steps"][ex.state["step_id"]].get("last_execution_id") == ex.id)
        (checked if completed_ok else unchecked).append("parameter limits of completed steps evaluated within limits"
                                                       if completed_ok else "completed steps with accepted limit violations")
        missing_sigs = [s for s in inst["order"] if inst["steps"][s]["status"] == "awaiting_signature"]
        if missing_sigs:
            unchecked.append(f"required signatures missing on {missing_sigs}")
        (unchecked if broken else checked).append(f"signature bindings changed: {broken}" if broken
                                                   else "signature bindings cover the exact executed content")
        pin = tx.get(ctx.tenant_id, "procedure_revision", f"{inst['procedure_id']}@{inst['revision']}")
        pin_ok = bool(pin and pin.state["definition_hash"] == inst["definition_hash"])
        (checked if pin_ok else unchecked).append("pinned procedure revision hash matches" if pin_ok else "pinned revision hash mismatch")
        open_excs = [e["exception_id"] for e in excs if e["status"] == "open"]
        if open_excs:
            unchecked.append(f"open exceptions awaiting disposition: {open_excs}")
        pending_drafts = [d["draft_id"] for d in drafts if d["status"] in ("provisional", "reconciled_conflict")]
        if pending_drafts:
            unchecked.append(f"offline drafts not resolved: {pending_drafts}")
        unchecked.extend(OUT_OF_SCOPE)
        return {"instance_id": instance_id, "batch_id": inst["context"].get("batch_id"), "procedure_ref": {
                    "procedure_id": inst["procedure_id"], "revision": inst["revision"], "definition_hash": inst["definition_hash"]},
                "instance_status": inst["status"], "steps": steps_out, "exceptions": excs, "redlines": inst["redlines"],
                "offline_drafts": drafts, "review_coverage": {"checked": checked, "unchecked": unchecked},
                "instance_record_revision": rec.revision}

    def review_by_exception(self, ctx: AccessContext, instance_id: str) -> dict[str, Any]:
        rec = self.batch_record(ctx, instance_id)
        open_n = sum(1 for e in rec["exceptions"] if e["status"] == "open")
        return {"exceptions": rec["exceptions"], "open_exception_count": open_n,
                "checked_scope": rec["review_coverage"]["checked"], "unchecked_scope": rec["review_coverage"]["unchecked"],
                "release_authorized": False,
                "note": "An empty exception list does not authorize release; QA must decide on the explicit unchecked scope."}

    def request_release(self, ctx: AccessContext, instance_id: str, *, rationale: str) -> dict[str, Any]:
        rec = self.batch_record(ctx, instance_id)
        inst = self.store.read().require(ctx.tenant_id, "procedure_instance", instance_id)
        if rec["instance_status"] != "completed":
            raise ValueError("release can be requested only after all steps are terminal")
        open_n = [e["exception_id"] for e in rec["exceptions"] if e["status"] == "open"]
        if open_n:
            raise ValueError(f"open exceptions must be dispositioned first: {open_n}")
        batch_id = rec["batch_id"]
        return self.ps.actions.propose(
            ctx, target_system="native", operation="release_batch", target_id=batch_id or instance_id,
            payload={"instance_id": instance_id, "batch_id": batch_id, "exception_count": len(rec["exceptions"]),
                     "review_coverage": rec["review_coverage"], "procedure_ref": rec["procedure_ref"]},
            basis=[{"kind": "procedure_instance", "id": instance_id, "revision": inst.revision, "site_id": inst.state["site_id"]}],
            rationale=rationale, expected_result="QA decision on batch disposition after review of the stated unchecked scope",
            owner_id=ctx.actor_id, site_id=inst.state["site_id"], record_class="batch_record")

    # --- maintenance readiness (LS-074) ---
    def prepare_maintenance(self, ctx: AccessContext, equipment_id: str, fault_history_refs: list[dict[str, Any]],
                            manual_refs: list[dict[str, Any]], spares: list[dict[str, Any]], *, technician_id: str | None = None,
                            description: str = "") -> dict[str, Any]:
        tx = self.store.read()
        eq = tx.require(ctx.tenant_id, "equipment", equipment_id)
        site = eq.state["site_id"]
        self.idn.require(ctx, "read", "equipment", equipment_id, site_id=site, tx=tx)
        gaps: list[dict[str, str]] = []
        if not fault_history_refs:
            gaps.append({"gap": "no_fault_history_evidence", "detail": "no fault history evidence linked"})
        if not manual_refs:
            gaps.append({"gap": "no_manual_reference", "detail": "no manual or procedure reference linked"})
        need = eq.state.get("maintenance_qualification")
        if need:
            q = tx.get(ctx.tenant_id, "personnel_qualification", technician_id) if technician_id else None
            held = ((q.state.get("qualifications") or {}) if q else {}).get(need, "missing")
            if technician_id is None:
                gaps.append({"gap": "technician_not_assigned", "detail": f"no technician assigned; {need} qualification required"})
            elif held == "missing" or (held and str(held)[:10] < _today()):
                gaps.append({"gap": "technician_qualification_missing", "detail": f"{technician_id} lacks current {need}"})
        spare_status = []
        for sp in spares:
            r = tx.get(ctx.tenant_id, "spare_part", f"{site}:{sp['part']}")
            on_hand = r.state.get("on_hand", 0) if r else 0
            spare_status.append({"part": sp["part"], "required": sp["quantity"], "on_hand": on_hand})
            if on_hand < sp["quantity"]:
                gaps.append({"gap": "spare_not_in_stock", "detail": f"{sp['part']}: {on_hand} on hand, {sp['quantity']} required"})
        if not eq.state.get("isolated"):
            gaps.append({"gap": "equipment_not_isolated", "detail": "no isolation/lockout recorded for the equipment"})
        for p in equipment_problems(eq.state, equipment_id, site):
            gaps.append({"gap": "equipment_status", "detail": p})
        basis = [{"kind": "equipment", "id": equipment_id, "revision": eq.revision, "site_id": site}, *fault_history_refs, *manual_refs]
        proposal = self.ps.actions.propose(
            ctx, target_system="native", operation="create_work_order", target_id=equipment_id,
            payload={"equipment_id": equipment_id, "description": description, "technician_id": technician_id, "spares": spare_status,
                     "gaps": gaps, "fault_history_refs": fault_history_refs, "manual_refs": manual_refs},
            basis=basis, rationale=description or "maintenance preparation", expected_result="work order created with gaps visible",
            owner_id=ctx.actor_id, site_id=site, record_class="work_order")
        return {"proposal": proposal, "gaps": gaps, "ready": not gaps, "spares": spare_status}
