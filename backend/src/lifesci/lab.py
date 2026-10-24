"""Laboratory methods, samples, plates, custody and results (LS-011, LS-012, LS-013, LS-014 method part).

Lab methods are procedure definitions of category ``lab_method`` run by the shared procedure engine, with
additional laboratory authoring rules (units, limits and calculation units are mandatory). A run is gated by
instrument calibration/status and reagent readiness. Samples receive generated identifiers, retries with the
same idempotency key return the same sample, custody corrections append to the chain (the original entry is
never overwritten) and released results cannot be overwritten; a new revision needs an approved
``invalidate_result`` proposal. Native laboratory records require native ownership of ``lab_record`` at the
site; an existing LIMS/LES stays authoritative otherwise.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import content_hash, iso, utc_now
from .execution import lot_problems
from .ownership import OwnershipRegistry
from .procedures import (ProcedureService, blocking_reasons, evaluate_step, finish_step, unit_ok, convert)
from .store import ConflictError, RecordStore, Transaction

PLATE_FORMATS = {96: ("H", 12), 384: ("P", 24)}
_WELL = re.compile(r"^([A-Z])0*(\d{1,2})$")
LAB_RECORD = "lab_record"


class ReadinessError(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class PlateError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class ResultLocked(PermissionError):
    pass


def lab_method_rules(definition: dict[str, Any]) -> list[str]:
    """Laboratory authoring rules on top of the shared validation: units and limits are mandatory."""
    errs: list[str] = []
    measured = 0
    for s in definition.get("steps", []):
        for p in s.get("parameters", []):
            if p.get("type") == "text":
                continue
            measured += 1
            if not p.get("unit"):
                errs.append(f"step {s['step_id']}: parameter {p['name']} needs a unit")
            if not isinstance(p.get("low"), (int, float)) or not isinstance(p.get("high"), (int, float)):
                errs.append(f"step {s['step_id']}: parameter {p['name']} needs numeric low and high limits")
        calc = s.get("calculation")
        if calc and not calc.get("unit"):
            errs.append(f"step {s['step_id']}: calculation {calc.get('name')} needs a result unit")
    if not measured and not any(s.get("calculation") for s in definition.get("steps", [])):
        errs.append("a lab method needs at least one measured parameter or calculation")
    return errs


def instrument_problems(inst: dict[str, Any] | None, instrument_id: str, site_id: str | None, today: str | None = None) -> list[str]:
    if inst is None:
        return [f"instrument {instrument_id} not found"]
    today = today or utc_now().date().isoformat()
    out = []
    if inst.get("status") != "ready":
        out.append(f"instrument {instrument_id} is {inst.get('status')}, not ready")
    due = inst.get("calibration_due")
    if not due:
        out.append(f"instrument {instrument_id} has no calibration due date on record")
    elif str(due)[:10] < today:
        out.append(f"instrument {instrument_id} calibration overdue since {str(due)[:10]}")
    if site_id and inst.get("site_id") not in (None, site_id):
        out.append(f"instrument {instrument_id} belongs to site {inst.get('site_id')}")
    return out


def normalize_well(well: str, plate_format: int) -> str | None:
    m = _WELL.match(str(well).strip().upper())
    if not m or plate_format not in PLATE_FORMATS:
        return None
    last_row, cols = PLATE_FORMATS[plate_format]
    row, col = m.group(1), int(m.group(2))
    return f"{row}{col}" if "A" <= row <= last_row and 1 <= col <= cols else None


def evaluate_limits(value: float, limits: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not limits:
        return None
    lo, hi = limits.get("low"), limits.get("high")
    within = (lo is None or value >= lo) and (hi is None or value <= hi)
    return {"low": lo, "high": hi, "within_limits": within, "evaluation": "within_limits" if within else "out_of_limits"}


class LabService:
    def __init__(self, store: RecordStore, identity: IdentityService, ownership: OwnershipRegistry, procedures: ProcedureService) -> None:
        self.store, self.idn, self.own, self.ps = store, identity, ownership, procedures
        procedures.register_validator("lab_method", lab_method_rules)

    def _native(self, ctx: AccessContext, site_id: str, tx: Transaction | None = None) -> None:
        self.own.check_native(ctx.tenant_id, LAB_RECORD, site_id, tx)

    # --- methods (LS-011, LS-014) ---
    def author_method(self, ctx: AccessContext, method_id: str, *, name: str, definition: dict[str, Any],
                      site_id: str | None = None) -> dict[str, Any]:
        return self.ps.create_draft(ctx, method_id, name=name, category="lab_method", definition=definition, site_id=site_id)

    def adapt_method(self, ctx: AccessContext, method_id: str, revision: int, site_id: str, overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return self.ps.adapt_for_site(ctx, method_id, revision, site_id, overrides)

    # --- instruments and readiness (LS-013) ---
    def register_instrument(self, ctx: AccessContext, instrument_id: str, state: dict[str, Any], *, site_id: str) -> dict[str, Any]:
        self.idn.require(ctx, "configure", "instrument", instrument_id, site_id=site_id)
        new = {**state, "instrument_id": instrument_id, "site_id": site_id}
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "instrument", instrument_id)
            rec = tx.put(ctx.tenant_id, "instrument", instrument_id, new, expected_revision=cur.revision if cur else None,
                         action="register_instrument", event_type="lab.instrument_updated", event_payload={"instrument_id": instrument_id})
        return {**new, "revision": rec.revision}

    def readiness(self, ctx: AccessContext, site_id: str, *, instruments: list[str], reagents: list[str],
                  requires: Mapping[str, Any] | None = None) -> list[str]:
        tx = self.store.read()
        problems: list[str] = []
        classes = []
        for iid in instruments:
            r = tx.get(ctx.tenant_id, "instrument", iid)
            problems += instrument_problems(r.state if r else None, iid, site_id)
            classes.append((r.state if r else {}).get("instrument_class"))
        mats = []
        for lid in reagents:
            r = tx.get(ctx.tenant_id, "material_lot", lid)
            problems += lot_problems(r.state if r else None, lid, None, None, site_id)
            mats.append((r.state if r else {}).get("material_id"))
        for need in (requires or {}).get("instruments", []):
            if need["instrument_class"] not in classes:
                problems.append(f"required instrument class {need['instrument_class']} not supplied")
        for need in (requires or {}).get("reagents", []):
            if need["material_id"] not in mats:
                problems.append(f"required reagent {need['material_id']} not supplied")
        return list(dict.fromkeys(problems))

    # --- method runs (LS-011, LS-013) ---
    def start_run(self, ctx: AccessContext, method_id: str, *, site_id: str, instruments: list[str] | None = None,
                  reagents: list[str] | None = None, sample_ids: list[str] | None = None, revision: int | None = None,
                  params: Mapping[str, Any] | None = None, run_id: str | None = None) -> dict[str, Any]:
        self._native(ctx, site_id)
        self.idn.require(ctx, "execute", "step_execution", f"{run_id or '*'}:*", site_id=site_id)
        rev = self.ps.get_revision(ctx, method_id, revision)
        if rev["category"] != "lab_method":
            raise ValueError(f"{method_id} is not a lab method")
        for sid in sample_ids or []:
            self.get_sample(ctx, sid)
        problems = self.readiness(ctx, site_id, instruments=instruments or [], reagents=reagents or [],
                                  requires=rev["definition"].get("requires"))
        if problems:
            raise ReadinessError(problems)
        inst = self.ps.create_instance(ctx, method_id, site_id=site_id, params=params, revision=rev["revision"], instance_id=run_id,
                                       context={"lab_run": True, "instruments": instruments or [], "reagents": reagents or [],
                                                "sample_ids": sample_ids or []})
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.require(ctx.tenant_id, "procedure_instance", inst["instance_id"])
            out = tx.put(ctx.tenant_id, "procedure_instance", inst["instance_id"],
                         {**cur.state, "status": "in_progress", "started_by": ctx.actor_id, "started_at": iso(utc_now())},
                         expected_revision=cur.revision, action="start_run", event_type="lab.run_started",
                         event_payload={"run_id": inst["instance_id"], "method": method_id, "revision": rev["revision"]})
        return {**out.state, "run_id": inst["instance_id"]}

    def get_run(self, ctx: AccessContext, run_id: str) -> dict[str, Any]:
        return self.ps.get_instance(ctx, run_id)

    def perform_method_step(self, ctx: AccessContext, run_id: str, step_id: str, captured_values: Mapping[str, Any]) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", run_id)
            run = rec.state
            if not run["context"].get("lab_run"):
                raise ValueError(f"{run_id} is not a lab run")
            self._native(ctx, run["site_id"], tx)
            self.idn.require(ctx, "execute", "step_execution", f"{run_id}:{step_id}", site_id=run["site_id"], tx=tx)
            blocked = blocking_reasons(run, step_id)
            if blocked:
                raise ValueError("; ".join(blocked))
            problems = self.readiness(ctx, run["site_id"], instruments=run["context"]["instruments"], reagents=run["context"]["reagents"])
            if problems:
                raise ReadinessError(problems)
            step = run["steps_def"][step_id]
            consts = {**run["constants"], **{k: v for k, v in run["params"].items() if isinstance(v, (int, float))}}
            ev = evaluate_step(step, captured_values, run["values"], consts)
            param_violations = [v for v in ev["violations"] if v["source"] == "parameter"]
            attempt = run["steps"][step_id]["attempts"] + 1
            exec_id = f"{run_id}:{step_id}:{attempt}"
            tx.put(ctx.tenant_id, "step_execution", exec_id,
                   {"execution_id": exec_id, "instance_id": run_id, "step_id": step_id, "attempt": attempt,
                    "procedure_ref": {"procedure_id": run["procedure_id"], "revision": run["revision"],
                                      "definition_hash": run["definition_hash"], "step_hash": content_hash(step)},
                    "values": ev["inputs"], "calculated": ev["calculated"], "evaluations": ev["evaluations"],
                    "resources": {"instruments": run["context"]["instruments"], "reagents": run["context"]["reagents"]},
                    "device_type": "web", "performed_by": ctx.actor_id, "performed_at": iso(utc_now()),
                    "outcome": "exception" if param_violations else "in_limits", "required_signatures": []},
                   expected_revision=None, action="perform_lab_step")
            new = copy.deepcopy(run)
            st = new["steps"][step_id]
            st.update(attempts=attempt, last_execution_id=exec_id, performed_by=ctx.actor_id)
            base = {"execution_id": exec_id, "evaluations": ev["evaluations"], "calculated": ev["calculated"]}
            if param_violations:
                exc_id = f"{exec_id}:exc"
                v = param_violations[0]
                tx.put(ctx.tenant_id, "exec_exception", exc_id,
                       {"exception_id": exc_id, "instance_id": run_id, "step_id": step_id, "execution_id": exec_id,
                        "site_id": run["site_id"], "violations": param_violations, "status": "open", "detected_by": ctx.actor_id,
                        "detected_at": iso(utc_now())}, expected_revision=None, action="exception", event_type="lab.exception",
                       event_payload={"run_id": run_id, "step_id": step_id, "parameter": v["name"], "value": v["value"]})
                st.update(status="exception", version=st["version"] + 1)
                tx.put(ctx.tenant_id, "procedure_instance", run_id, new, expected_revision=rec.revision, action="step_exception")
                return {**base, "status": "exception", "exception_id": exc_id, "run_status": run["status"]}
            done = finish_step(new, step_id, {**ev["inputs"], **ev["calculated"]}, extra={})
            tx.put(ctx.tenant_id, "procedure_instance", run_id, done, expected_revision=rec.revision, action="complete_lab_step",
                   event_type="lab.step_completed", event_payload={"run_id": run_id, "step_id": step_id})
            out_of_limits = [e for e in ev["evaluations"] if not e["within_limits"]]
            return {**base, "status": "completed", "run_status": done["status"], "out_of_limits": out_of_limits,
                    "limit_evaluation": "out_of_limits_review_required" if out_of_limits else "within_limits"}

    def record_run_result(self, ctx: AccessContext, run_id: str, sample_id: str, calculation: str, *, analyte: str | None = None) -> dict[str, Any]:
        run = self.get_run(ctx, run_id)
        step = next((s for s in run["steps_def"].values() if (s.get("calculation") or {}).get("name") == calculation), None)
        if step is None or calculation not in run["values"]:
            raise ValueError(f"calculation {calculation} has no value in run {run_id}")
        calc = step["calculation"]
        return self.record_result(ctx, sample_id, analyte or calculation, run["values"][calculation], calc["unit"],
                                  method_ref={"procedure_id": run["procedure_id"], "revision": run["revision"], "run_id": run_id},
                                  instrument_id=",".join(run["context"]["instruments"]) or None,
                                  limits={"low": calc.get("low"), "high": calc.get("high")})

    # --- samples (LS-012) ---
    def register_sample(self, ctx: AccessContext, batch_id: str, step_id: str | None, sample_type: str, idempotency_key: str, *,
                        collected_at: str | None = None, available_at: str | None = None, volume: float | None = None,
                        unit: str = "mL") -> dict[str, Any]:
        if not idempotency_key:
            raise ValueError("an idempotency key is required")
        with self.store.transaction(ctx.actor_id) as tx:
            batch = tx.require(ctx.tenant_id, "batch", batch_id)
            site = batch.state["site_id"]
            self._native(ctx, site, tx)
            self.idn.require(ctx, "execute", "sample", site_id=site, tx=tx)
            key = tx.get(ctx.tenant_id, "idempotency", f"sample:{idempotency_key}")
            request = {"batch_id": batch_id, "step_id": step_id, "sample_type": sample_type}
            if key:
                if key.state["request"] != request:
                    raise ConflictError("idempotency key was already used for a different sample request")
                sample = tx.require(ctx.tenant_id, "sample", key.state["sample_id"])
                return {**sample.state, "revision": sample.revision, "duplicate": True}
            seq = tx.get(ctx.tenant_id, "sequence", f"SMP:{site}")
            n = (seq.state["next"] if seq else 1)
            tx.put(ctx.tenant_id, "sequence", f"SMP:{site}", {"next": n + 1}, expected_revision=seq.revision if seq else None,
                   action="allocate")
            sid = f"SMP-{site}-{n:06d}"
            now = iso(utc_now())
            state = {"sample_id": sid, "site_id": site, "batch_id": batch_id, "step_id": step_id, "sample_type": sample_type,
                     "status": "registered", "registered_by": ctx.actor_id, "registered_at": now, "collected_at": collected_at or now,
                     "available_at": available_at, "volume": volume, "unit": unit, "parent_sample_id": None, "aliquot_ids": [],
                     "plate": None, "idempotency_key": idempotency_key,
                     "custody": [{"entry_id": f"{sid}#1", "seq": 1, "kind": "collection", "from": None, "to": ctx.actor_id,
                                  "reason": "collection", "by": ctx.actor_id, "at": now}]}
            rec = tx.put(ctx.tenant_id, "sample", sid, state, expected_revision=None, action="register_sample",
                         event_type="lab.sample_registered", event_payload={"sample_id": sid, "batch_id": batch_id, "step_id": step_id})
            tx.put(ctx.tenant_id, "idempotency", f"sample:{idempotency_key}", {"request": request, "sample_id": sid},
                   expected_revision=None, action="idempotency")
            tx.add_edge(ctx.tenant_id, ("batch", batch_id), ("sample", sid), "sampled_from")
        return {**state, "revision": rec.revision, "duplicate": False}

    def get_sample(self, ctx: AccessContext, sample_id: str) -> dict[str, Any]:
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, "sample", sample_id)
        self.idn.require(ctx, "read", "sample", sample_id, site_id=rec.state["site_id"], tx=tx)
        return {**rec.state, "revision": rec.revision}

    def list_samples(self, ctx: AccessContext, batch_id: str | None = None) -> list[dict[str, Any]]:
        tx = self.store.read()
        return [{**r.state, "revision": r.revision} for r in tx.list(ctx.tenant_id, "sample", lambda s: batch_id in (None, s["batch_id"]))
                if self.idn.check(ctx, "read", "sample", r.id, site_id=r.state["site_id"], tx=tx)]

    def aliquot(self, ctx: AccessContext, sample_id: str, n: int, volume: float, unit: str = "mL",
                idempotency_key: str | None = None) -> list[dict[str, Any]]:
        if n < 1 or volume <= 0:
            raise ValueError("aliquot count and volume must be positive")
        if not unit_ok(unit):
            raise ValueError(f"unknown unit {unit}")
        with self.store.transaction(ctx.actor_id) as tx:
            parent = tx.require(ctx.tenant_id, "sample", sample_id)
            p = parent.state
            self._native(ctx, p["site_id"], tx)
            self.idn.require(ctx, "execute", "sample", sample_id, site_id=p["site_id"], tx=tx)
            if idempotency_key:
                done = tx.get(ctx.tenant_id, "idempotency", f"aliquot:{sample_id}:{idempotency_key}")
                if done:
                    return [self._sample(tx, ctx, i) for i in done.state["children"]]
            if p.get("volume") is not None:
                need = convert(n * volume, unit, p["unit"])
                if need > p["volume"] + 1e-9:
                    raise ValueError(f"parent has {p['volume']} {p['unit']}; {need:g} {p['unit']} requested")
            start = len(p["aliquot_ids"])
            custodian = self._custodian(p)
            children, now = [], iso(utc_now())
            for k in range(1, n + 1):
                cid = f"{sample_id}-A{start + k}"
                child = {**{x: p[x] for x in ("site_id", "batch_id", "step_id", "sample_type", "available_at")},
                         "sample_id": cid, "status": "registered", "registered_by": ctx.actor_id, "registered_at": now,
                         "collected_at": p["collected_at"], "volume": volume, "unit": unit, "parent_sample_id": sample_id,
                         "aliquot_ids": [], "plate": None,
                         "custody": [{"entry_id": f"{cid}#1", "seq": 1, "kind": "aliquot", "from": None, "to": custodian,
                                      "reason": f"aliquot of {sample_id}", "by": ctx.actor_id, "at": now}]}
                tx.put(ctx.tenant_id, "sample", cid, child, expected_revision=None, action="aliquot",
                       event_type="lab.sample_registered", event_payload={"sample_id": cid, "parent": sample_id})
                tx.add_edge(ctx.tenant_id, ("sample", sample_id), ("sample", cid), "aliquot_of")
                children.append(child)
            newp = {**p, "aliquot_ids": [*p["aliquot_ids"], *[c["sample_id"] for c in children]]}
            if p.get("volume") is not None:
                newp["volume"] = round(p["volume"] - convert(n * volume, unit, p["unit"]), 9)
            tx.put(ctx.tenant_id, "sample", sample_id, newp, expected_revision=parent.revision, action="aliquot_parent")
            if idempotency_key:
                tx.put(ctx.tenant_id, "idempotency", f"aliquot:{sample_id}:{idempotency_key}",
                       {"children": [c["sample_id"] for c in children]}, expected_revision=None, action="idempotency")
        return children

    @staticmethod
    def _sample(tx: Transaction, ctx: AccessContext, sample_id: str) -> dict[str, Any]:
        return tx.require(ctx.tenant_id, "sample", sample_id).state

    def assign_plate(self, ctx: AccessContext, plate_id: str, plate_format: int, positions: Mapping[str, str]) -> dict[str, Any]:
        if plate_format not in PLATE_FORMATS:
            raise PlateError([f"plate format must be one of {sorted(PLATE_FORMATS)}"])
        errors: list[str] = []
        wells: dict[str, str] = {}
        for raw, sid in positions.items():
            w = normalize_well(raw, plate_format)
            if w is None:
                errors.append(f"well {raw} is not valid on a {plate_format}-well plate")
            elif w in wells:
                errors.append(f"well {w} is listed more than once")
            else:
                wells[w] = sid
        if len(set(wells.values())) != len(wells):
            errors.append("a sample cannot occupy more than one well in a request")
        with self.store.transaction(ctx.actor_id) as tx:
            plate = tx.get(ctx.tenant_id, "plate", plate_id)
            samples: dict[str, Any] = {}
            for sid in set(wells.values()):
                rec = tx.get(ctx.tenant_id, "sample", sid)
                if rec is None:
                    errors.append(f"sample {sid} not found")
                    continue
                self._native(ctx, rec.state["site_id"], tx)
                self.idn.require(ctx, "execute", "sample", sid, site_id=rec.state["site_id"], tx=tx)
                samples[sid] = rec
            sites = {r.state["site_id"] for r in samples.values()} | ({plate.state["site_id"]} if plate else set())
            if len(sites) > 1:
                errors.append(f"plate and samples span multiple sites {sorted(sites)}")
            if plate and plate.state["format"] != plate_format:
                errors.append(f"plate {plate_id} is a {plate.state['format']}-well plate")
            current = dict(plate.state["wells"]) if plate else {}
            for w, sid in wells.items():
                if w in current and current[w] != sid:
                    errors.append(f"well {w} is occupied by {current[w]}")
                prior = (samples[sid].state.get("plate") if sid in samples else None) or {}
                if prior and (prior["plate_id"], prior["well"]) != (plate_id, w):
                    errors.append(f"sample {sid} is already at {prior['plate_id']}:{prior['well']}")
            if errors:
                raise PlateError(errors)
            merged = {**current, **wells}
            state = {"plate_id": plate_id, "format": plate_format, "site_id": sites.pop() if sites else None, "wells": merged}
            rec = tx.put(ctx.tenant_id, "plate", plate_id, state, expected_revision=plate.revision if plate else None,
                         action="assign_plate", event_type="lab.plate_assigned", event_payload={"plate_id": plate_id, "wells": wells})
            for w, sid in wells.items():
                s = samples[sid]
                if (s.state.get("plate") or {}).get("well") != w:
                    tx.put(ctx.tenant_id, "sample", sid, {**s.state, "plate": {"plate_id": plate_id, "well": w}},
                           expected_revision=s.revision, action="plate_position")
        return {**state, "revision": rec.revision}

    # --- custody (LS-012) ---
    @staticmethod
    def effective_chain(sample: dict[str, Any]) -> list[dict[str, Any]]:
        chain = []
        corrections = [e for e in sample["custody"] if e["kind"] == "correction"]
        for e in sample["custody"]:
            if e["kind"] == "correction":
                continue
            eff = {"from": e["from"], "to": e["to"]}
            applied = [c for c in corrections if c["corrects"] == e["entry_id"]]
            for c in applied:
                eff.update(c["corrected"])
            chain.append({**e, "effective": eff, "corrections": [c["entry_id"] for c in applied]})
        return chain

    def _custodian(self, sample: dict[str, Any]) -> str:
        return self.effective_chain(sample)[-1]["effective"]["to"]

    def custody_chain(self, ctx: AccessContext, sample_id: str) -> dict[str, Any]:
        s = self.get_sample(ctx, sample_id)
        return {"sample_id": sample_id, "chain": self.effective_chain(s), "raw_entries": s["custody"], "current_custodian": self._custodian(s)}

    def transfer_custody(self, ctx: AccessContext, sample_id: str, from_: str, to: str, reason: str) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise ValueError("a custody transfer requires a reason")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "sample", sample_id)
            s = rec.state
            self._native(ctx, s["site_id"], tx)
            self.idn.require(ctx, "execute", "sample", sample_id, site_id=s["site_id"], tx=tx)
            if self._custodian(s) != from_:
                raise ConflictError(f"{sample_id} is held by {self._custodian(s)}, not {from_}")
            seq = len(s["custody"]) + 1
            entry = {"entry_id": f"{sample_id}#{seq}", "seq": seq, "kind": "transfer", "from": from_, "to": to, "reason": reason,
                     "by": ctx.actor_id, "at": iso(utc_now())}
            tx.put(ctx.tenant_id, "sample", sample_id, {**s, "custody": [*s["custody"], entry]}, expected_revision=rec.revision,
                   action="transfer_custody", reason=reason, event_type="lab.custody_transferred",
                   event_payload={"sample_id": sample_id, "from": from_, "to": to})
        return entry

    def correct_custody(self, ctx: AccessContext, entry_id: str, corrected: dict[str, Any], reason: str) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise ValueError("a custody correction requires a reason")
        if not corrected or set(corrected) - {"from", "to"}:
            raise ValueError("corrected must set from and/or to")
        sample_id = entry_id.rsplit("#", 1)[0]
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "sample", sample_id)
            s = rec.state
            self._native(ctx, s["site_id"], tx)
            self.idn.require(ctx, "execute", "sample", sample_id, site_id=s["site_id"], tx=tx)
            target = next((e for e in s["custody"] if e["entry_id"] == entry_id), None)
            if target is None or target["kind"] == "correction":
                raise ValueError(f"custody entry {entry_id} not found or is itself a correction")
            seq = len(s["custody"]) + 1
            entry = {"entry_id": f"{sample_id}#{seq}", "seq": seq, "kind": "correction", "corrects": entry_id,
                     "original": {"from": target["from"], "to": target["to"]}, "corrected": corrected, "reason": reason,
                     "by": ctx.actor_id, "at": iso(utc_now())}
            tx.put(ctx.tenant_id, "sample", sample_id, {**s, "custody": [*s["custody"], entry]}, expected_revision=rec.revision,
                   action="correct_custody", reason=reason, details={"corrects": entry_id, "corrected": corrected},
                   event_type="lab.custody_corrected", event_payload={"sample_id": sample_id, "entry_id": entry_id})
        return entry

    # --- results (LS-011, LS-012) ---
    def record_result(self, ctx: AccessContext, sample_id: str, analyte: str, value: float, unit: str | None, *,
                      method_ref: dict[str, Any] | None = None, instrument_id: str | None = None,
                      limits: Mapping[str, Any] | None = None, raw_data: bytes | None = None) -> dict[str, Any]:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("result value must be numeric")
        if not unit_ok(unit):
            raise ValueError(f"unknown unit {unit!r}")
        rid = f"RES:{sample_id}:{analyte}"
        with self.store.transaction(ctx.actor_id) as tx:
            sample = tx.require(ctx.tenant_id, "sample", sample_id)
            site = sample.state["site_id"]
            self._native(ctx, site, tx)
            self.idn.require(ctx, "execute", "sample", sample_id, site_id=site, tx=tx)
            digest = tx.put_blob(ctx.tenant_id, raw_data, "application/octet-stream") if raw_data is not None else None
            core = {"sample_id": sample_id, "analyte": analyte, "value": value, "unit": unit, "method_ref": method_ref,
                    "instrument_id": instrument_id, "limits": dict(limits) if limits else None, "raw_data_digest": digest}
            cur = tx.get(ctx.tenant_id, "result", rid)
            if cur and cur.state["status"] != "invalidated" and all(cur.state.get(k) == v for k, v in core.items()):
                return {**cur.state, "revision": cur.revision, "duplicate": True}
            if cur and cur.state["status"] == "released":
                raise ResultLocked(f"{rid} is released and cannot be overwritten; request an invalidate_result proposal")
            history = list(cur.state["history"]) if cur else []
            if cur:
                history.append({"revision": cur.revision, "status": cur.state["status"], "value": cur.state["value"], "unit": cur.state["unit"],
                                "recorded_by": cur.state["recorded_by"], "recorded_at": cur.state["recorded_at"]})
            state = {**core, "result_id": rid, "site_id": site, "batch_id": sample.state["batch_id"], "status": "recorded",
                     "limit_evaluation": evaluate_limits(value, limits), "recorded_by": ctx.actor_id, "recorded_at": iso(utc_now()),
                     "calculation_validated": bool(method_ref), "analytical_validity": "not_assessed", "review": None, "history": history}
            rec = tx.put(ctx.tenant_id, "result", rid, state, expected_revision=cur.revision if cur else None,
                         action="record_result" if not cur else "correct_result", event_type="lab.result_recorded",
                         event_payload={"result_id": rid, "sample_id": sample_id})
            tx.add_edge(ctx.tenant_id, ("sample", sample_id), ("result", rid), "result_of")
        return {**state, "revision": rec.revision, "duplicate": False}

    def review_result(self, ctx: AccessContext, result_id: str, decision: str, comment: str = "") -> dict[str, Any]:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be approved or rejected")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "result", result_id)
            s = rec.state
            self.idn.require(ctx, "approve", "result", result_id, site_id=s["site_id"], tx=tx)
            if s["recorded_by"] == ctx.actor_id:
                raise AuthorizationError(Decision(False, "the recorder cannot review their own result"))
            if s["status"] != "recorded":
                raise ValueError(f"result is {s['status']}")
            new = {**s, "status": "reviewed" if decision == "approved" else "review_rejected",
                   "review": {"decision": decision, "by": ctx.actor_id, "at": iso(utc_now()), "comment": comment,
                              "scope": "qualified scientific review of the recorded value; not a validation of the method"}}
            out = tx.put(ctx.tenant_id, "result", result_id, new, expected_revision=rec.revision, action="review_result", reason=comment)
        return {**out.state, "revision": out.revision}

    def release_result(self, ctx: AccessContext, result_id: str) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "result", result_id)
            self.idn.require(ctx, "release", "result", result_id, site_id=rec.state["site_id"], tx=tx)
            if rec.state["status"] != "reviewed":
                raise ValueError("only a reviewed result can be released")
            out = tx.put(ctx.tenant_id, "result", result_id, {**rec.state, "status": "released", "released_by": ctx.actor_id,
                                                              "released_at": iso(utc_now())},
                         expected_revision=rec.revision, action="release_result", event_type="lab.result_released",
                         event_payload={"result_id": result_id})
        return {**out.state, "revision": out.revision}

    def request_invalidation(self, ctx: AccessContext, result_id: str, reason: str) -> dict[str, Any]:
        rec = self.store.read().require(ctx.tenant_id, "result", result_id)
        if rec.state["status"] != "released":
            raise ValueError("only a released result needs an invalidation proposal; unreleased results are corrected by re-recording")
        return self.ps.actions.propose(
            ctx, target_system="native", operation="invalidate_result", target_id=result_id,
            payload={"result_id": result_id, "value": rec.state["value"], "unit": rec.state["unit"]},
            basis=[{"kind": "result", "id": result_id, "revision": rec.revision, "site_id": rec.state["site_id"]}],
            rationale=reason, expected_result="released result invalidated; a new revision may then be recorded",
            owner_id=ctx.actor_id, site_id=rec.state["site_id"], record_class="lab_result")

    def apply_invalidation(self, ctx: AccessContext, result_id: str, proposal_id: str) -> dict[str, Any]:
        if ctx.actor_kind == "agent":
            raise AuthorizationError(Decision(False, "agent credentials cannot apply invalidations"))
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "result", result_id)
            prop = tx.require(ctx.tenant_id, "proposal", proposal_id).state
            self.ps.actions.require_current_approval(ctx, proposal_id, tx)
            self.idn.require(ctx, "propose", "result", result_id, site_id=rec.state["site_id"], tx=tx)
            if prop["operation"] != "invalidate_result" or prop["target_id"] != result_id:
                raise ValueError("proposal does not target this result")
            if prop["status"] != "approved":
                raise PermissionError(f"invalidation proposal is {prop['status']}, not approved")
            out = tx.put(ctx.tenant_id, "result", result_id,
                         {**rec.state, "status": "invalidated", "invalidation": {"proposal_id": proposal_id, "by": ctx.actor_id,
                                                                                  "at": iso(utc_now()), "reason": prop["rationale"]}},
                         expected_revision=rec.revision, action="invalidate_result", reason=prop["rationale"],
                         event_type="lab.result_invalidated", event_payload={"result_id": result_id})
        return {**out.state, "revision": out.revision}

    def get_result(self, ctx: AccessContext, result_id: str) -> dict[str, Any]:
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, "result", result_id)
        self.idn.require(ctx, "read", "result", result_id, site_id=rec.state["site_id"], tx=tx)
        return {**rec.state, "revision": rec.revision}
