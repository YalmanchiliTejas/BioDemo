"""Deviation signals: automatic detection of possible deviations, never deviations themselves.

A signal records what fired (rule, value, limit, specification version), on what subject, with which
evidence. Opening a formal deviation case is a person's decision (``open_case``); the QMS stays the record.
Repeats of the same rule on the same subject within 24 h coalesce into one signal; a rise in severity emits
``signal.escalated``, anything else ``signal.updated``. Only people change a signal's lifecycle.

Wiring (container / api / runtime):
    platform.specifications = SpecificationService(platform.store, platform.identity)
    platform.signals = SignalService(platform)          # uses platform.specifications when present
    register_signal_listeners(platform)                  # store.subscribe(platform.signals.on_event)
    signal_routes(app, platform, ctx_dep)                # in create_app, beside the other v1 routes
For CMO deliveries (separate store), call ``platform.signals.check_delivery_measurements(...)`` when a
verified dataset is published to the platform.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Iterable

from .identity import AccessContext, AuthorizationError, Decision
from .ids import content_hash, iso, new_id, parse_iso, utc_now
from .specifications import SpecificationService, parameter_key

log = logging.getLogger(__name__)

KIND = "deviation_signal"
SERIES = "spec_series"
SEVERITY = {"warning": 1, "action": 2, "critical": 3}
KINDS = ("step_exception", "lab_oos", "spec_excursion", "trend", "qms_deviation", "delivery_excursion")
LIVE = ("open", "acknowledged")
COALESCE_WINDOW = timedelta(hours=24)
SYSTEM_ACTOR = "system:deviation-detection"
QMS_DEVIATION_WORDS = ("deviation", "nonconform", "non-conform", "oos", "out of spec", "out-of-spec")
SERIES_POINTS = 50   # ponytail: last 50 values per spec and subject for trend rules; enough for EWMA/CUSUM baselines


def _person(ctx: AccessContext, what: str) -> None:
    if ctx.actor_kind != "person" or ctx.delegated_from:
        raise AuthorizationError(Decision(False, f"{what} requires a person; {ctx.actor_kind} credentials cannot"))


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


class SignalService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        self.store = platform.store
        self.identity = platform.identity
        self.specs = getattr(platform, "specifications", None) or SpecificationService(platform.store, platform.identity)

    # --- raising ------------------------------------------------------------------
    def raise_signal(self, tenant_id: str, *, kind: str, severity: str, site_id: str | None, subject: dict[str, str],
                     rule: str, rule_key: str, parameter: str | None = None, value: float | None = None,
                     unit: str | None = None, limit: dict[str, Any] | None = None, spec_ref: dict[str, Any] | None = None,
                     evidence_refs: Iterable[dict[str, Any]] = (), source: dict[str, Any] | None = None) -> dict[str, Any]:
        """System write. Coalesces by (site, parameter, subject, rule) within 24 h; idempotent for identical repeats."""
        if kind not in KINDS or severity not in SEVERITY:
            raise ValueError("unknown signal kind or severity")
        now = utc_now()
        key = content_hash([site_id, parameter_key(parameter) if parameter else kind, subject.get("kind"),
                            subject.get("id"), rule_key])[:24]
        refs = [dict(r) for r in evidence_refs]
        with self.store.transaction(SYSTEM_ACTOR) as tx:
            current = None
            for rec in tx.list(tenant_id, KIND, lambda s: s.get("coalesce_key") == key and s.get("status") in LIVE):
                last = parse_iso(rec.state["last_at"])
                if last and now - last <= COALESCE_WINDOW:
                    current = rec
            if current:
                state = dict(current.state)
                new_refs = [r for r in refs if r not in state["evidence_refs"]]
                if not new_refs and SEVERITY[severity] <= SEVERITY[state["severity"]] and value == state.get("value"):
                    return {**state, "revision": current.revision}  # exact repeat (e.g. event redelivery)
                escalated = SEVERITY[severity] > SEVERITY[state["severity"]]
                state.update(occurrences=state["occurrences"] + 1, last_at=iso(now),
                             evidence_refs=[*state["evidence_refs"], *new_refs][-50:],
                             value=value if value is not None else state.get("value"))
                if escalated:
                    state.update(severity=severity, rule=rule, limit=limit or state.get("limit"),
                                 spec_ref=spec_ref or state.get("spec_ref"))
                rec = tx.put(tenant_id, KIND, current.id, state, expected_revision=current.revision,
                             action="escalate_signal" if escalated else "repeat_signal",
                             event_type="signal.escalated" if escalated else "signal.updated",
                             event_payload={"signal_id": current.id, "site_id": site_id, "severity": state["severity"],
                                            "kind": state["kind"]})
                return {**rec.state, "revision": rec.revision}
            signal_id = new_id("sig")
            state = {"signal_id": signal_id, "site_id": site_id, "kind": kind, "severity": severity, "rule": rule,
                     "rule_key": rule_key, "coalesce_key": key, "parameter": parameter, "value": value, "unit": unit,
                     "limit": limit, "spec_ref": spec_ref, "subject": subject, "evidence_refs": refs, "source": source,
                     "occurrences": 1, "first_at": iso(now), "last_at": iso(now), "status": "open",
                     "dismiss_reason": None, "case_id": None, "history": [],
                     "alerts": {"sent": 0, "last_at": None}, "triage": {"status": "pending"}}
            rec = tx.put(tenant_id, KIND, signal_id, state, expected_revision=None, action="raise_signal",
                         event_type="signal.raised",
                         event_payload={"signal_id": signal_id, "site_id": site_id, "severity": severity, "kind": kind})
        return {**rec.state, "revision": rec.revision}

    # --- reading ------------------------------------------------------------------
    def _readable(self, ctx: AccessContext, state: dict[str, Any]) -> bool:
        return bool(self.identity.check(ctx, "read", KIND, state["signal_id"], site_id=state.get("site_id")))

    def get(self, ctx: AccessContext, signal_id: str) -> dict[str, Any]:
        rec = self.store.read().require(ctx.tenant_id, KIND, signal_id)
        if not self._readable(ctx, rec.state):
            raise PermissionError("signal outside your access")
        return {**rec.state, "revision": rec.revision}

    def list(self, ctx: AccessContext, *, site_id: str | None = None, status: str | None = None,
             min_severity: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        floor = SEVERITY.get(min_severity or "warning", 1)
        out = [{**r.state, "revision": r.revision} for r in self.store.read().list(ctx.tenant_id, KIND)
               if (not site_id or r.state.get("site_id") == site_id) and (not status or r.state["status"] == status)
               and SEVERITY[r.state["severity"]] >= floor and self._readable(ctx, r.state)]
        out.sort(key=lambda s: s["last_at"], reverse=True)  # newest first, then live and most severe first (stable)
        out.sort(key=lambda s: (s["status"] not in LIVE, -SEVERITY[s["severity"]]))
        return out[:limit]

    # --- lifecycle (people only) ----------------------------------------------------
    def _decide(self, ctx: AccessContext, signal_id: str, change: dict[str, Any], action: str, note: str) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, KIND, signal_id)
            self.identity.require(ctx, "propose", KIND, signal_id, site_id=rec.state.get("site_id"), tx=tx)
            if rec.state["status"] not in LIVE:
                raise ValueError(f"signal is already {rec.state['status']}")
            state = {**rec.state, **change, "history": [*rec.state["history"],
                     {"event": action, "by": ctx.actor_id, "at": iso(utc_now()), "note": note}]}
            out = tx.put(ctx.tenant_id, KIND, signal_id, state, expected_revision=rec.revision, action=action,
                         reason=note or None, event_type="signal.updated",
                         event_payload={"signal_id": signal_id, "site_id": state.get("site_id"),
                                        "severity": state["severity"], "kind": state["kind"]})
        return {**out.state, "revision": out.revision}

    def acknowledge(self, ctx: AccessContext, signal_id: str) -> dict[str, Any]:
        _person(ctx, "acknowledging a signal")
        current = self.get(ctx, signal_id)
        if current["status"] == "acknowledged":
            return current
        return self._decide(ctx, signal_id, {"status": "acknowledged"}, "acknowledge_signal", "")

    def dismiss(self, ctx: AccessContext, signal_id: str, reason: str) -> dict[str, Any]:
        _person(ctx, "dismissing a signal")
        if not (reason or "").strip():
            raise ValueError("a reason is required to dismiss a signal")
        return self._decide(ctx, signal_id, {"status": "dismissed", "dismiss_reason": reason.strip()},
                            "dismiss_signal", reason.strip())

    def open_case(self, ctx: AccessContext, signal_id: str, *, owner_id: str, qa_reviewer_id: str,
                  case_id: str | None = None) -> dict[str, Any]:
        """A person declares a possible deviation: opens a case pre-filled from the signal and links them."""
        _person(ctx, "opening a deviation case")
        signal = self.get(ctx, signal_id)
        if signal["status"] not in LIVE:
            raise ValueError(f"signal is already {signal['status']}")
        case_id = case_id or "DEV-" + signal_id.removeprefix("sig")[-8:].upper()
        with self.store.transaction(ctx.actor_id):  # one unit: no case without its signal link, or vice versa
            case = self.p.cases.open(ctx, case_id, owner_id, qa_reviewer_id, signal["site_id"])
            self.p.cases.add_timeline_event(ctx, case_id, signal["first_at"], f"Signal {signal_id}: {signal['rule']}")
            updated = self._decide(ctx, signal_id, {"status": "case_opened", "case_id": case_id}, "open_case_from_signal",
                                   f"case {case_id}")
        return {"signal": updated, "case": case}

    # --- written by alerting / triage ----------------------------------------------
    def annotate(self, tenant_id: str, signal_id: str, *, alerts: dict[str, Any] | None = None,
                 triage: dict[str, Any] | None = None) -> dict[str, Any]:
        """System update of the follow-up fields only (alerts / triage); emits no lifecycle event."""
        with self.store.transaction(SYSTEM_ACTOR) as tx:
            rec = tx.require(tenant_id, KIND, signal_id)
            state = {**rec.state, **({"alerts": alerts} if alerts is not None else {}),
                     **({"triage": triage} if triage is not None else {})}
            out = tx.put(tenant_id, KIND, signal_id, state, expected_revision=rec.revision, action="annotate_signal")
        return {**out.state, "revision": out.revision}

    # --- detectors ------------------------------------------------------------------
    def on_event(self, event: Any) -> None:
        """Store listener. Never raises into the committing caller; a failed detection is logged, not lost silently."""
        if event.type.startswith("signal.") or event.tenant_id.startswith("__"):
            return
        handler = {"exec.exception": self._step_exception, "lab.exception": self._lab_step_exception,
                   "lab.result_recorded": self._lab_result, "evidence.ingested": self._evidence,
                   "evidence.corrected": self._evidence}.get(event.type)
        if not handler:
            return
        try:
            handler(event)
        except Exception:
            log.exception("deviation detection failed for %s %s", event.type, event.aggregate_id)

    def _step_exception(self, event: Any) -> None:
        p = event.payload
        subject = ({"kind": "batch", "id": p["batch_id"]} if p.get("batch_id")
                   else {"kind": "procedure_instance", "id": p["instance_id"]})
        # Execution records an exception only when the step holds on out-of-limit: that hold makes it critical.
        self.raise_signal(event.tenant_id, kind="step_exception", severity="critical", site_id=p.get("site_id"),
                          subject=subject, parameter=p.get("parameter"), value=_num(p.get("value")),
                          limit={"low": p.get("low"), "high": p.get("high")},
                          rule=f"{p.get('parameter')} {p.get('value')} outside step limits "
                               f"[{p.get('low')}, {p.get('high')}] at step {p.get('step_id')} (execution hold)",
                          rule_key=f"step:{p.get('step_id')}",
                          evidence_refs=[{"kind": "exec_exception", "id": p["exception_id"]}],
                          source={"system": "native_execution", "record_id": p["exception_id"]})

    def _lab_step_exception(self, event: Any) -> None:
        p = event.payload
        self.raise_signal(event.tenant_id, kind="step_exception", severity="action", site_id=p.get("site_id"),
                          subject={"kind": "lab_run", "id": p["run_id"]}, parameter=p.get("parameter"),
                          value=_num(p.get("value")), limit={"low": p.get("low"), "high": p.get("high")},
                          rule=f"{p.get('parameter')} {p.get('value')} outside lab method limits at step {p.get('step_id')}",
                          rule_key=f"labstep:{p.get('step_id')}",
                          evidence_refs=[{"kind": "exec_exception", "id": p.get("exception_id") or f"{p['run_id']}:{p['step_id']}"}])

    def _lab_result(self, event: Any) -> None:
        p = event.payload
        if p.get("limit_evaluation") != "out_of_limits":
            return
        spec = self.specs.match(event.tenant_id, p.get("site_id"), p.get("analyte") or "")
        severity, rule = "action", (f"{p.get('analyte')} {p.get('value')} {p.get('unit') or ''} outside result limits "
                                    f"[{p.get('low')}, {p.get('high')}]").replace("  ", " ")
        value = _num(p.get("value"))
        if spec and value is not None and (hit := self.specs.evaluate(spec, value)) and hit[0] == "critical":
            severity, rule = hit
        subject = {"kind": "batch", "id": p["batch_id"]} if p.get("batch_id") else {"kind": "sample", "id": p["sample_id"]}
        self.raise_signal(event.tenant_id, kind="lab_oos", severity=severity, site_id=p.get("site_id"), subject=subject,
                          parameter=p.get("analyte"), value=value, unit=p.get("unit"),
                          limit={"low": p.get("low"), "high": p.get("high")},
                          spec_ref={"spec_id": spec["spec_id"], "version": spec["version"]} if spec else None,
                          rule=rule, rule_key=f"result:{p.get('analyte')}",
                          evidence_refs=[{"kind": "result", "id": p["result_id"]}])

    def _evidence(self, event: Any) -> None:
        rec = self.store.read().get(event.tenant_id, "evidence", event.payload["evidence_id"])
        if not rec:
            return
        e = rec.state
        fields = (e.get("metadata") or {}).get("mapped") or {}
        system = str(e.get("source_system") or "").upper()
        ref = {"kind": "evidence", "id": e["evidence_id"], "revision": rec.revision}
        record_type = str(fields.get("record_type") or (e.get("metadata") or {}).get("record_type") or "")
        if any(w in record_type.lower() for w in QMS_DEVIATION_WORDS):
            external = str(fields.get("case_id") or e["source_record_id"])
            subject = ({"kind": "batch", "id": str(fields["batch_id"])} if fields.get("batch_id")
                       else {"kind": "qms_record", "id": external})
            self.raise_signal(event.tenant_id, kind="qms_deviation", severity="critical", site_id=e.get("site_id"),
                              subject=subject, rule=f"QMS {record_type} {external} recorded"
                              + (f": {str(fields['description'])[:160]}" if fields.get("description") else ""),
                              rule_key=f"qms:{external}", evidence_refs=[ref],
                              source={"system": e["source_system"], "record_id": external})
            return
        if system == "QMS":
            return  # other QMS records (CAPA, change control) are not excursions
        parameter = fields.get("tag") or fields.get("test") or fields.get("parameter")
        value = _num(fields.get("value"))
        if parameter is None or value is None:
            return
        self.check_value(event.tenant_id, site_id=e.get("site_id"), parameter=str(parameter), value=value,
                         unit=(e.get("metadata") or {}).get("units", {}).get("value") or fields.get("unit"),
                         equipment_id=fields.get("equipment_id"), batch_id=fields.get("batch_id"),
                         evidence_ref=ref, source={"system": e["source_system"], "record_id": e["source_record_id"]})

    def check_value(self, tenant_id: str, *, site_id: str | None, parameter: str, value: float, unit: str | None = None,
                    equipment_id: str | None = None, batch_id: str | None = None, product_id: str | None = None,
                    evidence_ref: dict[str, Any] | None = None, source: dict[str, Any] | None = None,
                    kind: str = "spec_excursion") -> dict[str, Any] | None:
        """Compare one live value with its specification; record it for trend rules. Returns the signal, if any."""
        spec = self.specs.match(tenant_id, site_id, parameter, equipment_id=equipment_id, product_id=product_id)
        if not spec:
            return None
        subject = ({"kind": "batch", "id": str(batch_id)} if batch_id else
                   {"kind": "equipment", "id": str(equipment_id)} if equipment_id else {"kind": "parameter", "id": spec["parameter"]})
        spec_ref = {"spec_id": spec["spec_id"], "version": spec["version"]}
        limit = {k: spec.get(k) for k in ("low", "high", "critical_low", "critical_high")}
        refs = [evidence_ref] if evidence_ref else []
        series = self._append_series(tenant_id, spec, subject, value)
        hit = self.specs.evaluate(spec, value)
        if hit:
            return self.raise_signal(tenant_id, kind=kind, severity=hit[0], site_id=site_id, subject=subject,
                                     parameter=spec["parameter"], value=value, unit=unit or spec.get("unit"),
                                     limit=limit, spec_ref=spec_ref, rule=hit[1], rule_key=f"spec:{spec['spec_id']}",
                                     evidence_refs=refs, source=source)
        lo, hi = spec.get("low") if spec.get("low") is not None else spec.get("critical_low"), \
            spec.get("high") if spec.get("high") is not None else spec.get("critical_high")
        if not spec.get("trend_rules") or len(series) < 8 or (lo is None and hi is None):
            return None
        from .science import detect_emerging_concern
        result = detect_emerging_concern(series, (lo, hi))["result"]
        if not result["concern"]:
            return None
        rules = ", ".join(sorted(result["active_signals"]))
        return self.raise_signal(tenant_id, kind="trend", severity="warning", site_id=site_id, subject=subject,
                                 parameter=spec["parameter"], value=value, unit=unit or spec.get("unit"), limit=limit,
                                 spec_ref=spec_ref, rule=f"{spec['parameter']} trending toward its limit ({rules}) "
                                 f"over the last {len(series)} values; still within spec (spec {spec['spec_id']} v{spec['version']})",
                                 rule_key=f"trend:{spec['spec_id']}", evidence_refs=refs, source=source)

    def _append_series(self, tenant_id: str, spec: dict[str, Any], subject: dict[str, str], value: float) -> list[float]:
        ident = content_hash([spec["spec_id"], subject["kind"], subject["id"]])[:24]
        with self.store.transaction(SYSTEM_ACTOR) as tx:
            rec = tx.get(tenant_id, SERIES, ident)
            values = [*(rec.state["values"] if rec and rec.state.get("spec_version") == spec["version"] else []), value][-SERIES_POINTS:]
            tx.put(tenant_id, SERIES, ident, {"spec_id": spec["spec_id"], "spec_version": spec["version"], "subject": subject,
                                               "values": values, "updated_at": iso(utc_now())},
                   expected_revision=rec.revision if rec else None, action="record_spec_value")
        return values

    def check_delivery_measurements(self, tenant_id: str, *, site_id: str, measurements: Iterable[dict[str, Any]],
                                    delivery_ref: dict[str, Any]) -> list[dict[str, Any]]:
        """Verified CMO measurements ({parameter, value, unit?, batch_id?}) against specifications."""
        out = []
        for m in measurements:
            value = _num(m.get("value"))
            if value is None or not m.get("parameter"):
                continue
            hit = self.check_value(tenant_id, site_id=site_id, parameter=str(m["parameter"]), value=value,
                                   unit=m.get("unit"), batch_id=m.get("batch_id"), evidence_ref=delivery_ref,
                                   source={"system": "cmo_delivery", "record_id": str(delivery_ref.get("id"))},
                                   kind="delivery_excursion")
            if hit:
                out.append(hit)
        return out


from pydantic import BaseModel, Field  # noqa: E402  (request models must be module-level for FastAPI)


class SignalDismiss(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

class SignalOpenCase(BaseModel):
    owner_id: str = Field(min_length=1)
    qa_reviewer_id: str = Field(min_length=1)
    case_id: str | None = Field(default=None, max_length=80)

class SpecificationIn(BaseModel):
    site_id: str = Field(min_length=1, max_length=100)
    parameter: str = Field(min_length=1, max_length=200)
    unit: str | None = None
    low: float | None = None
    high: float | None = None
    critical_low: float | None = None
    critical_high: float | None = None
    product_id: str | None = None
    equipment_id: str | None = None
    trend_rules: bool = True
    source: str = "manual"
    source_ref: str | None = None
    reason: str = Field(min_length=1, max_length=2000)


def register_signal_listeners(platform: Any) -> None:
    platform.store.subscribe(platform.signals.on_event)


def signal_routes(app: Any, platform: Any, ctx_dep: Any) -> None:
    from fastapi import Depends

    @app.get("/v1/signals")
    def list_signals(site_id: str | None = None, status: str | None = None, min_severity: str | None = None,
                     ctx: AccessContext = Depends(ctx_dep)):
        return {"signals": platform.signals.list(ctx, site_id=site_id, status=status, min_severity=min_severity)}

    @app.get("/v1/signals/{signal_id}")
    def get_signal(signal_id: str, ctx: AccessContext = Depends(ctx_dep)):
        return platform.signals.get(ctx, signal_id)

    @app.post("/v1/signals/{signal_id}/acknowledge")
    def acknowledge_signal(signal_id: str, ctx: AccessContext = Depends(ctx_dep)):
        return platform.signals.acknowledge(ctx, signal_id)

    @app.post("/v1/signals/{signal_id}/dismiss")
    def dismiss_signal(signal_id: str, body: SignalDismiss, ctx: AccessContext = Depends(ctx_dep)):
        return platform.signals.dismiss(ctx, signal_id, body.reason)

    @app.post("/v1/signals/{signal_id}/open-case", status_code=201)
    def open_case_from_signal(signal_id: str, body: SignalOpenCase, ctx: AccessContext = Depends(ctx_dep)):
        return platform.signals.open_case(ctx, signal_id, owner_id=body.owner_id, qa_reviewer_id=body.qa_reviewer_id,
                                          case_id=body.case_id)

    @app.get("/v1/specifications")
    def list_specifications(site_id: str | None = None, ctx: AccessContext = Depends(ctx_dep)):
        return {"specifications": platform.specifications.list(ctx, site_id=site_id)}

    @app.post("/v1/specifications", status_code=201)
    def create_specification(body: SpecificationIn, ctx: AccessContext = Depends(ctx_dep)):
        return platform.specifications.create(ctx, **body.model_dump())
