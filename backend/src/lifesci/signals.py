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
from datetime import datetime, timedelta
from typing import Any, Iterable

from .identity import AccessContext, AuthorizationError, Decision
from .ids import content_hash, iso, new_id, parse_iso, utc_now
from .specifications import SpecificationService, parameter_key

log = logging.getLogger(__name__)

KIND = "deviation_signal"
SERIES = "spec_series"
SEVERITY = {"warning": 1, "action": 2, "critical": 3}
KINDS = ("step_exception", "lab_oos", "lab_oot", "spec_excursion", "trend", "qms_deviation", "delivery_excursion", "evaluation_issue", "equipment_exception",
         "procedural_exception", "environmental_exception", "quality_exception", "post_release_exception")
LIVE = ("open", "acknowledged")
COALESCE_WINDOW = timedelta(hours=24)
SYSTEM_ACTOR = "system:deviation-detection"
QMS_DEVIATION_WORDS = ("deviation", "nonconform", "non-conform", "oos", "out of spec", "out-of-spec")
RULE_VERSION = "monitoring-2"
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


def _source_time(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return iso(parsed)


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
                     evidence_refs: Iterable[dict[str, Any]] = (), source: dict[str, Any] | None = None,
                     event_time: str | None = None, observations: Iterable[dict[str, Any]] = (),
                     associations: dict[str, Any] | None = None,
                     evaluation_issues: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
        """System write. Coalesces by (site, parameter, subject, rule) within 24 h; idempotent for identical repeats."""
        if kind not in KINDS or severity not in SEVERITY:
            raise ValueError("unknown signal kind or severity")
        now = utc_now()
        key = content_hash([site_id, parameter_key(parameter) if parameter else kind, subject.get("kind"),
                            subject.get("id"), rule_key, spec_ref])[:24]
        refs = [dict(r) for r in evidence_refs]
        observed = [dict(o) for o in observations]
        for observation in observed:
            ref = observation.get("evidence_ref")
            if isinstance(ref, dict) and ref not in refs:
                refs.append(dict(ref))
        issues = [dict(i) for i in evaluation_issues]
        if event_time:
            try:
                event_time = _source_time(event_time)
            except (ValueError, TypeError, AttributeError):
                issues.append({"code": "invalid_event_time", "event_time": event_time})
                event_time = None
        for observation in observed:
            if observation.get("event_time"):
                observation.setdefault("original_event_time", observation["event_time"])
                try:
                    observation["event_time"] = _source_time(observation["event_time"])
                except (ValueError, TypeError, AttributeError):
                    issues.append({"code": "invalid_event_time", "event_time": observation["event_time"]})
                    observation["event_time"] = None
        with self.store.transaction(SYSTEM_ACTOR) as tx:
            current = None
            for rec in tx.list(tenant_id, KIND, lambda s: s.get("coalesce_key") == key and s.get("status") in LIVE):
                last = parse_iso(rec.state["last_at"])
                if last and now - last <= COALESCE_WINDOW:
                    current = rec
            if current:
                state = dict(current.state)
                new_refs = [r for r in refs if r not in state["evidence_refs"]]
                new_observations = [o for o in observed if o not in state.get("observations", [])]
                new_issues = [i for i in issues if i not in state.get("evaluation_issues", [])]
                if not new_refs and not new_observations and not new_issues and SEVERITY[severity] <= SEVERITY[state["severity"]] and value == state.get("value"):
                    return {**state, "revision": current.revision}  # exact repeat (e.g. event redelivery)
                escalated = SEVERITY[severity] > SEVERITY[state["severity"]]
                duration_evidence = bool((limit or state.get("limit") or {}).get("duration_seconds"))
                combined_refs = [*state["evidence_refs"], *new_refs]
                combined_observations = [*state.get("observations", []), *new_observations]
                # A duration finding must retain every point needed to verify continuity, including
                # its original supporting evidence after later signal updates. Do not apply the
                # display/trend count bound to this evidence.
                state.update(occurrences=state["occurrences"] + 1, last_at=iso(now),
                             evidence_refs=combined_refs if duration_evidence else combined_refs[-50:],
                             value=value if value is not None else state.get("value"))
                state.update(observations=combined_observations if duration_evidence else combined_observations[-SERIES_POINTS:],
                             associations={**state.get("associations", {}), **(associations or {})},
                             evaluation_issues=[*state.get("evaluation_issues", []), *[i for i in issues if i not in state.get("evaluation_issues", [])]],
                             event_time=event_time or state.get("event_time"), rule_version=RULE_VERSION)
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
                     "observations": observed, "associations": associations or {}, "evaluation_issues": issues,
                     "event_time": event_time, "rule_version": RULE_VERSION,
                     "occurrences": 1, "first_at": iso(now), "last_at": iso(now), "status": "open",
                     "dismiss_reason": None, "case_id": None, "history": [],
                     "alerts": {"sent": 0, "last_at": None}, "triage": {"status": "pending"}}
            rec = tx.put(tenant_id, KIND, signal_id, state, expected_revision=None, action="raise_signal",
                         event_type="signal.raised",
                         event_payload={"signal_id": signal_id, "site_id": site_id, "severity": severity, "kind": kind})
        return {**rec.state, "revision": rec.revision}

    # --- reading ------------------------------------------------------------------
    def _readable(self, ctx: AccessContext, state: dict[str, Any]) -> bool:
        current = self.identity.context_for(ctx.tenant_id, ctx.delegated_from or ctx.actor_id,
                                            actor_kind='person' if ctx.delegated_from else ctx.actor_kind)
        if not self.identity.check(current, "read", KIND, state["signal_id"], site_id=state.get("site_id")):
            return False
        from .quality_evidence import quality_lineage
        refs = quality_lineage(KIND, state)
        # Legacy connector references can name external records not stored here. Enforce
        # current authority on every known local source; unresolved references confer no access.
        known = [r for r in refs if self.store.read().get(ctx.tenant_id, r['kind'], r['id'])]
        try:
            if known:
                self.identity.validate_refs(current, known, require_current=False)
        except (PermissionError, ValueError, KeyError):
            return False
        return True

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
            if not self._readable(ctx, rec.state):
                raise PermissionError("signal outside your current source access")
            current = self.identity.context_for(ctx.tenant_id, ctx.actor_id, actor_kind=ctx.actor_kind)
            self.identity.require(current, "propose", KIND, signal_id, site_id=rec.state.get("site_id"), tx=tx)
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
        spec = self.specs.match(event.tenant_id, p.get("site_id"), p.get("analyte") or "",
                                equipment_id=p.get("equipment_id"), product_id=p.get("product_id"))
        severity, rule = "action", (f"{p.get('analyte')} {p.get('value')} {p.get('unit') or ''} outside result limits "
                                    f"[{p.get('low')}, {p.get('high')}]").replace("  ", " ")
        value = _num(p.get("value"))
        normalized = value
        issues = []
        if spec and value is not None and p.get("unit") and spec.get("unit") and p["unit"] != spec["unit"]:
            from .science import convert_unit
            try:
                normalized = convert_unit(value, p["unit"], spec["unit"])
            except ValueError as exc:
                normalized = None
                issues.append({"code": "unit_mismatch", "from_unit": p["unit"], "to_unit": spec["unit"], "detail": str(exc)})
        if spec and normalized is not None and (hit := self.specs.evaluate(spec, normalized)) and hit[0] == "critical":
            severity, rule = hit
        subject = {"kind": "batch", "id": p["batch_id"]} if p.get("batch_id") else {"kind": "sample", "id": p["sample_id"]}
        self.raise_signal(event.tenant_id, kind="lab_oos", severity=severity, site_id=p.get("site_id"), subject=subject,
                          parameter=p.get("analyte"), value=value, unit=p.get("unit"),
                          limit={"low": p.get("low"), "high": p.get("high")},
                          spec_ref={"spec_id": spec["spec_id"], "version": spec["version"]} if spec else None,
                          rule=rule, rule_key=f"result:{p.get('analyte')}",
                          evidence_refs=[{"kind": "result", "id": p["result_id"], "revision": event.revision}],
                          source={"system": "native_lab", "record_id": p["result_id"], "revision": event.revision},
                          event_time=p.get("event_time"), evaluation_issues=issues,
                          associations={k: p[k] for k in ("batch_id", "product_id", "equipment_id", "sample_id") if p.get(k)},
                          observations=[{"original_value": value, "original_unit": p.get("unit"),
                                         "normalized_value": normalized, "normalized_unit": spec.get("unit") if spec else p.get("unit"),
                                         "event_time": p.get("event_time"), "result_id": p["result_id"],
                                         "source_revision": event.revision, "limit_evaluation": p["limit_evaluation"]}])

    def _evidence(self, event: Any) -> None:
        rec = self.store.read().get(event.tenant_id, "evidence", event.payload["evidence_id"])
        if not rec:
            return
        e = rec.state
        fields = (e.get("metadata") or {}).get("mapped") or {}
        source = {"system": e["source_system"], "record_id": e["source_record_id"]}
        if e.get("source_revision") is not None:
            source["revision"] = e["source_revision"]
        if e.get("mapping_version") is not None:
            source["mapping_version"] = e["mapping_version"]
        associations = {k: fields[k] for k in ("batch_id", "equipment_id", "product_id", "material_id", "lot_id", "sample_id") if fields.get(k)}
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
                              source={**source, "record_id": external}, associations=associations, event_time=e.get("event_time"),
                              observations=[{"record_type": record_type, "facts": fields, "event_time": e.get("event_time"), "evidence_ref": ref}])
            return
        if system == "QMS":
            return  # other QMS records (CAPA, change control) are not excursions
        category = {
            "calibration": "equipment_exception", "maintenance": "equipment_exception", "equipment_alarm": "equipment_exception",
            "cleaning": "procedural_exception", "line_clearance": "procedural_exception", "material_verification": "procedural_exception",
            "environmental_monitoring": "environmental_exception", "microbiology": "environmental_exception",
            "visual_inspection": "quality_exception", "labeling": "quality_exception", "mix_up": "quality_exception",
            "lab_result": "lab_oos", "stability": "post_release_exception", "complaint": "post_release_exception", "recall": "post_release_exception",
        }.get(parameter_key(record_type))
        status = str(fields.get("status") or "").strip().lower()
        failure_statuses = {
            "lab_result": {"out_of_limits", "out_of_specification", "out_of_trend"},
            "calibration": {"failed", "overdue", "missing"}, "maintenance": {"failed", "overdue", "missing"},
            "equipment_alarm": {"active", "alarm", "confirmed"},
            "cleaning": {"failed", "missing"}, "line_clearance": {"failed", "missing"}, "material_verification": {"failed", "missing"},
            "environmental_monitoring": {"out_of_limits", "out_of_specification", "failed"},
            "microbiology": {"positive", "out_of_limits", "out_of_specification", "failed"},
            "visual_inspection": {"failed", "out_of_limits"}, "labeling": {"failed", "mismatch"}, "mix_up": {"confirmed"},
            "stability": {"out_of_limits", "out_of_specification", "failed"}, "complaint": {"confirmed"}, "recall": {"confirmed", "active"},
        }
        if category == "lab_oos" and status == "out_of_trend":
            category = "lab_oot"
        if category and status in failure_statuses.get(parameter_key(record_type), set()):
            subject = next(({"kind": name.removesuffix("_id"), "id": str(fields[name])}
                            for name in ("batch_id", "equipment_id", "product_id") if fields.get(name)),
                           {"kind": "evidence", "id": e["evidence_id"]})
            self.raise_signal(event.tenant_id, kind=category, severity="warning" if category == "lab_oot" else "action", site_id=e.get("site_id"),
                              subject=subject, rule=f"Mapped {record_type} status: {status}",
                              value=_num(fields.get("value")), unit=fields.get("unit"), parameter=fields.get("test") or fields.get("parameter"),
                              limit={"low": fields.get("low"), "high": fields.get("high")} if category in ("lab_oos", "lab_oot") else None,
                              rule_key=f"mapped:{parameter_key(record_type)}:{e['source_record_id']}", evidence_refs=[ref],
                              source=source, associations=associations, event_time=e.get("event_time"),
                              observations=[{"record_type": record_type, "status": status, "event_time": e.get("event_time"),
                                             "facts": fields, "evidence_ref": ref}])
            if category == "lab_oos":
                return  # the source OOS is preserved independently of local limits
            # Source OOT is advisory; still evaluate independently configured numeric limits.
        parameter = fields.get("tag") or fields.get("test") or fields.get("parameter")
        value = _num(fields.get("value"))
        if parameter is None or value is None:
            return
        self.check_value(event.tenant_id, site_id=e.get("site_id"), parameter=str(parameter), value=value,
                         unit=(e.get("metadata") or {}).get("units", {}).get("value") or fields.get("unit"),
                         equipment_id=fields.get("equipment_id"), batch_id=fields.get("batch_id"), product_id=fields.get("product_id"),
                         event_time=e.get("event_time"), observation_type=fields.get("observation_type", "measurement"),
                         associations=associations, evidence_ref=ref, source=source)

    def check_value(self, tenant_id: str, *, site_id: str | None, parameter: str, value: float, unit: str | None = None,
                    equipment_id: str | None = None, batch_id: str | None = None, product_id: str | None = None,
                    evidence_ref: dict[str, Any] | None = None, source: dict[str, Any] | None = None,
                    kind: str = "spec_excursion", event_time: str | None = None,
                    observations: Iterable[dict[str, Any]] = (), associations: dict[str, Any] | None = None,
                    observation_type: str = "measurement") -> dict[str, Any] | None:
        """Evaluate source-time observations; late history is retained but never raised as a current alarm.

        Unitless legacy calls retain specification units, explicitly marked in the observation.
        Cross-batch rules consume only explicitly designated batch summaries.
        """
        spec = self.specs.match(tenant_id, site_id, parameter, equipment_id=equipment_id, product_id=product_id)
        if not spec:
            return None
        subject = ({"kind": "batch", "id": str(batch_id)} if batch_id else
                   {"kind": "equipment", "id": str(equipment_id)} if equipment_id else {"kind": "parameter", "id": spec["parameter"]})
        assoc = {**(associations or {}), **{k: v for k, v in
                 (("batch_id", batch_id), ("equipment_id", equipment_id), ("product_id", product_id)) if v is not None}}
        spec_ref = {"spec_id": spec["spec_id"], "version": spec["version"]}
        limit = {k: spec.get(k) for k in ("low", "high", "critical_low", "critical_high", "duration_seconds")}
        refs = [evidence_ref] if evidence_ref else []
        common = dict(site_id=site_id, subject=subject, parameter=spec["parameter"], limit=limit,
                      spec_ref=spec_ref, evidence_refs=refs, source=source, associations=assoc)
        original = value
        numeric_value = _num(value)
        issues = []
        stamp = None
        if event_time:
            try:
                stamp = _source_time(event_time)
            except (ValueError, TypeError, AttributeError):
                issues.append({"code": "invalid_event_time", "event_time": event_time})
        if numeric_value is None:
            issues.append({"code": "invalid_value", "value": value})
        else:
            value = numeric_value
        if unit and spec.get("unit") and unit != spec["unit"]:
            from .science import convert_unit
            try:
                value = convert_unit(value, unit, spec["unit"])
            except ValueError as exc:
                issues.append({"code": "unit_mismatch", "from_unit": unit, "to_unit": spec["unit"], "detail": str(exc)})
        observation = {"value": value, "unit": spec.get("unit") or unit, "original_value": original,
                       "original_unit": unit, "unit_basis": "provided" if unit else "legacy_specification_unit",
                       "event_time": stamp, "original_event_time": event_time, "time_basis": "source" if stamp else "recorded",
                       "batch_id": batch_id, "observation_type": observation_type, "spec_ref": spec_ref, "rule_version": RULE_VERSION,
                       "evidence_ref": evidence_ref, "source": source, "associations": assoc}
        if issues:
            return self.raise_signal(tenant_id, kind="evaluation_issue", severity="warning",
                                     rule="Observation could not be evaluated: " + ", ".join(i["code"] for i in issues),
                                     rule_key=f"evaluation:{spec['spec_id']}", observations=[observation],
                                     evaluation_issues=issues, **common)
        series, duplicate, ordering_issues = self._append_series(tenant_id, spec, subject, observation)
        if ordering_issues:
            return self.raise_signal(tenant_id, kind="evaluation_issue", severity="warning",
                                     rule="Historical observation retained; current alarm not evaluated",
                                     rule_key=f"ordering:{spec['spec_id']}", event_time=stamp,
                                     observations=[observation], evaluation_issues=ordering_issues, **common)
        if duplicate:
            # Return an already raised signal, without emitting another event or changing its revision.
            candidates = self.store.read().list(tenant_id, KIND, lambda state:
                state.get("spec_ref") == spec_ref
                and any(o == observation for o in state.get("observations", [])))
            return {**candidates[-1].state, "revision": candidates[-1].revision} if candidates else None
        hit = self.specs.evaluate(spec, value)
        context_observations = list(observations)
        if hit and spec.get("duration_seconds"):
            if not stamp:
                return self.raise_signal(tenant_id, kind="evaluation_issue", severity="warning",
                                         rule="Duration rule requires explicit source event time",
                                         rule_key=f"duration-time:{spec['spec_id']}", observations=[observation],
                                         evaluation_issues=[{"code": "missing_event_time"}], **common)
            episode = []
            # An episode remains on one side of the limit; no bridging missing samples or recovery.
            side = "low" if (spec.get("low") is not None and value < spec["low"]) or (spec.get("critical_low") is not None and value < spec["critical_low"]) else "high"
            for point in reversed(series):
                other = point["value"]
                point_side = "low" if (spec.get("low") is not None and other < spec["low"]) or (spec.get("critical_low") is not None and other < spec["critical_low"]) else "high"
                if not point.get("event_time") or not self.specs.evaluate(spec, other) or point_side != side:
                    break
                if episode and (parse_iso(episode[-1]["event_time"]) - parse_iso(point["event_time"])).total_seconds() > spec["max_observation_gap_seconds"]:
                    break
                episode.append(point)
            if len(episode) < 2 or (parse_iso(stamp) - parse_iso(episode[-1]["event_time"])).total_seconds() < spec["duration_seconds"]:
                return None
            context_observations = list(reversed(episode[1:]))  # current appended below
        if hit:
            return self.raise_signal(tenant_id, kind=kind, severity=hit[0], value=value, unit=spec.get("unit") or unit,
                                     rule=hit[1], rule_key=f"spec:{spec['spec_id']}", event_time=stamp,
                                     observations=[*context_observations, observation], **common)
        if spec.get("cross_batch_trend") and observation_type == "batch_summary":
            if not batch_id or not stamp:
                return self.raise_signal(tenant_id, kind="evaluation_issue", severity="warning",
                                         rule="Cross-batch summaries require batch identity and source event time",
                                         rule_key=f"batch-summary:{spec['spec_id']}", observations=[observation],
                                         evaluation_issues=[{"code": "incomplete_batch_summary"}], **common)
            scope = {"kind": "product", "id": product_id} if spec.get("product_id") else {"kind": "equipment", "id": equipment_id}
            summaries, _, ordering = self._append_series(tenant_id, spec, scope, observation, cross_batch=True)
            config = spec["cross_batch_trend"]
            recent = summaries[-config["window_batches"]:]
            baseline = sum(config["baseline"]) / len(config["baseline"])
            if not ordering and len(recent) == config["window_batches"] and all(a["value"] > b["value"] for a, b in zip(recent, recent[1:])) and baseline - sum(o["value"] for o in recent) / len(recent) >= config["minimum_drop"]:
                common["subject"] = scope
                common["associations"] = {**assoc, "batch_ids": [o["batch_id"] for o in recent]}
                return self.raise_signal(tenant_id, kind="trend", severity="warning", value=value, unit=spec.get("unit") or unit,
                                         rule=f"{spec['parameter']} deterioration across {len(recent)} distinct batch summaries relative to configured baseline {baseline:g}",
                                         rule_key=f"cross-batch:{spec['spec_id']}", observations=recent, event_time=stamp, **common)
            return None
        if spec.get("cross_batch_trend"):
            return None  # raw process curves cannot establish a cross-batch signal
        values = [o["value"] for o in series]
        lo = spec.get("low") if spec.get("low") is not None else spec.get("critical_low")
        hi = spec.get("high") if spec.get("high") is not None else spec.get("critical_high")
        if not spec.get("trend_rules") or len(values) < 8 or (lo is None and hi is None):
            return None
        from .science import detect_emerging_concern
        result = detect_emerging_concern(values, (lo, hi))["result"]
        if not result["concern"]:
            return None
        rules = ", ".join(sorted(result["active_signals"]))
        return self.raise_signal(tenant_id, kind="trend", severity="warning", value=value, unit=spec.get("unit") or unit,
                                 rule=f"{spec['parameter']} trending toward its limit ({rules}) over the last {len(series)} values; still within spec (spec {spec['spec_id']} v{spec['version']})",
                                 rule_key=f"trend:{spec['spec_id']}", observations=series, event_time=stamp, **common)

    def _append_series(self, tenant_id: str, spec: dict[str, Any], subject: dict[str, str],
                       observation: dict[str, Any], *, cross_batch: bool = False) -> tuple[list[dict[str, Any]], bool, list[dict[str, Any]]]:
        ident = content_hash([spec["spec_id"], subject["kind"], subject["id"], cross_batch])[:24]
        with self.store.transaction(SYSTEM_ACTOR) as tx:
            rec = tx.get(tenant_id, SERIES, ident)
            previous = rec.state.get("observations", []) if rec and rec.state.get("spec_version") == spec["version"] else []
            # Missing source identity/time is a fresh legacy sample; explicit redelivery is idempotent.
            identifiable = observation.get("event_time") or observation.get("evidence_ref") or observation.get("source")
            if identifiable and observation in previous:
                return previous, True, []
            issues = []
            stamp = observation.get("event_time")
            watermark = max((o["event_time"] for o in previous if o.get("event_time")), default=None)
            if stamp and watermark and stamp < watermark:
                issues.append({"code": "out_of_order", "watermark": watermark})
                allowance = spec.get("allowed_lateness_seconds")
                if allowance and (parse_iso(watermark) - parse_iso(stamp)).total_seconds() > allowance:
                    issues.append({"code": "late_observation", "allowed_lateness_seconds": allowance})
            points = previous
            if cross_batch:
                existing = next((o for o in previous if o.get("batch_id") == observation.get("batch_id")), None)
                if existing and stamp <= existing["event_time"]:
                    return previous, False, issues
                points = [o for o in previous if o.get("batch_id") != observation.get("batch_id")]
            points = [*points, observation]
            points.sort(key=lambda o: o.get("event_time") or "")
            retain_from = max(0, len(points) - SERIES_POINTS)
            if spec.get("duration_seconds") and not cross_batch:
                latest = max((o["event_time"] for o in points if o.get("event_time")), default=None)
                if latest:
                    cutoff = parse_iso(latest) - timedelta(seconds=spec["duration_seconds"])
                    # Retain the whole configured source-time window plus the last preceding
                    # sample. Its timestamp establishes whether a sufficiently long, gap-free
                    # excursion exists even when it takes more than 50 samples to do so.
                    predecessors = [i for i, point in enumerate(points)
                                    if point.get("event_time") and parse_iso(point["event_time"]) <= cutoff]
                    required_start = predecessors[-1] if predecessors else 0
                    retain_from = min(retain_from, required_start)
            points = points[retain_from:]
            tx.put(tenant_id, SERIES, ident, {"spec_id": spec["spec_id"], "spec_version": spec["version"], "subject": subject,
                                             "values": [o["value"] for o in points], "observations": points,
                                             "updated_at": iso(utc_now())},
                   expected_revision=rec.revision if rec else None, action="record_spec_value")
        return points, False, issues

    def check_delivery_measurements(self, tenant_id: str, *, site_id: str, measurements: Iterable[dict[str, Any]],
                                    delivery_ref: dict[str, Any]) -> list[dict[str, Any]]:
        """Verified CMO measurements ({parameter, value, unit?, batch_id?}) against specifications."""
        out = []
        for m in measurements:
            value = _num(m.get("value"))
            if value is None or not m.get("parameter"):
                continue
            hit = self.check_value(tenant_id, site_id=site_id, parameter=str(m["parameter"]), value=value,
                                   unit=m.get("unit"), batch_id=m.get("batch_id"), equipment_id=m.get("equipment_id"),
                                   product_id=m.get("product_id"), event_time=m.get("event_time"),
                                   observation_type=m.get("observation_type", "measurement"), associations=m.get("associations"),
                                   evidence_ref={**delivery_ref, **({"measurement_id": m["measurement_id"]} if m.get("measurement_id") else {})},
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
    duration_seconds: float | None = None
    max_observation_gap_seconds: float | None = None
    allowed_lateness_seconds: float | None = None
    cross_batch_trend: dict[str, Any] | None = None
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
