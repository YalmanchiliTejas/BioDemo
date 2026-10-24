"""Connector contracts, evidence intake, mapping templates, transports and ERP/subscription exchange.

Implements LS-004 (generic REST adapter scenarios), LS-023 (webhook, MQTT, OPC UA, file
transports; read-only telemetry), LS-029 (incremental instrument sources with gaps and
source timestamps), LS-041 (no-code mapping templates, preview and dry-run test),
LS-042 (replayable signed subscriptions), LS-043 (ERP reconciliation and approved
write-back), LS-044 (versioned connector contract), LS-063 (normalized values keep unit,
time basis and transform lineage) and LS-088 (qualification matrix).

MQTT and OPC UA are transport-agnostic subscribers over a ``TransportClient`` protocol;
no broker or OPC UA library is bundled, so only the in-memory simulator is exercised.
A scenario pass here shows the contract holds against the exercised endpoint, not
against any vendor system. Control writes through telemetry adapters are refused.
"""

from __future__ import annotations

import base64
import csv
import fnmatch
import hashlib
import hmac
import io
import json
import socket
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence
from urllib.error import HTTPError, URLError

from benchmark.integration.connectors import _source_record as source_record_from
from benchmark.integration.models import AuthorizedAction, PullBatch, SourceRecord

from .actions import ActionService, DeliveryUnknown
from .evidence import EvidenceRef, EvidenceService
from .identity import AccessContext, IdentityService
from .ids import canonical_json, content_hash, iso, new_id, parse_iso, utc_now
from .ownership import Ownership, OwnershipRegistry
from .store import RecordStore, Transaction

TRANSPORTS = ("rest", "webhook", "file", "mqtt", "opcua")
STATUSES = ("supported", "simulated", "unavailable")
REQUIRED_SCENARIOS = ("authorized_read", "identity", "version", "mapping", "gap")
CONTROL_WRITES_PROHIBITED = "control writes prohibited"

_UREG: Any = None


def _ureg() -> Any:
    global _UREG
    if _UREG is None:
        from pint import UnitRegistry
        _UREG = UnitRegistry()
    return _UREG


def _round(value: float) -> float:
    return float(f"{value:.12g}")


def record_to_dict(record: SourceRecord) -> dict[str, Any]:
    return {"source_record_id": record.source_record_id, "source_system": record.source_system,
            "occurred_at": iso(record.occurred_at), "payload": record.payload, "site_id": record.site_id,
            "classification": record.classification}


def record_from_dict(data: dict[str, Any]) -> SourceRecord:
    return SourceRecord(data["source_record_id"], data["source_system"], parse_iso(data["occurred_at"]),
                        dict(data["payload"]), data.get("site_id"), data.get("classification", "internal"))


class DurableQueue:
    """Append-only ordered queue persisted as versioned records (replayable by offset)."""

    def __init__(self, store: RecordStore, tenant_id: str, queue_id: str) -> None:
        self.store, self.tenant_id, self.queue_id = store, tenant_id, queue_id

    def append(self, tx: Transaction, item: dict[str, Any]) -> int:
        head = tx.get(self.tenant_id, "queue_head", self.queue_id)
        n = head.state["count"] if head else 0
        tx.put(self.tenant_id, "queue_item", f"{self.queue_id}:{n:012d}", {"queue": self.queue_id, "index": n, **item},
               expected_revision=None, action="enqueue")
        tx.put(self.tenant_id, "queue_head", self.queue_id, {"count": n + 1},
               expected_revision=head.revision if head else None, action="enqueue_head")
        return n

    def count(self) -> int:
        head = self.store.read().get(self.tenant_id, "queue_head", self.queue_id)
        return head.state["count"] if head else 0

    def read(self, offset: int, limit: int) -> list[dict[str, Any]]:
        tx = self.store.read()
        out = []
        for n in range(offset, min(offset + limit, self.count())):
            out.append(tx.require(self.tenant_id, "queue_item", f"{self.queue_id}:{n:012d}").state)
        return out


# --- LS-044 / LS-088: connector contracts and qualification matrix ------------------------------


@dataclass(frozen=True)
class ConnectorContract:
    system: str
    vendor: str
    version: str
    transport: str
    read_operations: tuple[str, ...]
    owner: str
    auth: str
    schema_version: str
    rate_limit: dict[str, Any] = field(default_factory=dict)
    error_semantics: dict[str, str] = field(default_factory=dict)
    write_operations: tuple[str, ...] = ()
    write_auth: str | None = None
    limits: tuple[str, ...] = ()
    status: str = "simulated"
    contract_version: str = "1"

    @property
    def contract_id(self) -> str:
        return f"{self.system}:{self.vendor}:{self.version}:{self.transport}"

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "read_operations": list(self.read_operations),
                "write_operations": list(self.write_operations), "limits": list(self.limits)}

    def validate(self) -> None:
        if self.transport not in TRANSPORTS:
            raise ValueError(f"transport must be one of {TRANSPORTS}")
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if self.status == "supported":
            raise ValueError("a contract becomes supported only through qualify()")
        if not self.owner:
            raise ValueError("a connector contract requires an owner")
        if self.status != "unavailable" and not self.read_operations:
            raise ValueError("a contract lists at least one read operation")
        if self.write_operations and not self.write_auth:
            raise ValueError("write operations require separate write credentials (write_auth)")


def _passed(result: Any) -> bool:
    return bool(result.get("passed")) if isinstance(result, dict) else result is True


class ConnectorMatrix:
    """Source/version/auth/schema/operations matrix persisted as records; only qualified rows are advertised."""

    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store, self.identity = store, identity

    def register(self, ctx: AccessContext, contract: ConnectorContract) -> dict[str, Any]:
        contract.validate()
        self.identity.require(ctx, "configure", "connector_contract", contract.contract_id)
        state = {**contract.to_dict(), "contract_id": contract.contract_id, "scenario_results": {},
                 "qualified_at": None, "qualified_by": None, "unavailable_reason": None}
        state["spec_hash"] = content_hash({k: v for k, v in contract.to_dict().items() if k != "status"})
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "connector_contract", contract.contract_id)
            if cur and cur.state["spec_hash"] == state["spec_hash"] and cur.state["status"] != "unavailable":
                return {**cur.state, "revision": cur.revision}
            rec = tx.put(ctx.tenant_id, "connector_contract", contract.contract_id, state,
                         expected_revision=cur.revision if cur else None,
                         action="register_contract" if not cur else "revise_contract",
                         reason="contract changed: requalification required" if cur else None,
                         event_type="connector.contract_registered", event_payload={"contract_id": contract.contract_id})
        return {**rec.state, "revision": rec.revision}

    def declare_unavailable(self, ctx: AccessContext, *, system: str, vendor: str, version: str,
                            transport: str, reason: str, owner: str = "integration-owner") -> dict[str, Any]:
        contract = ConnectorContract(system, vendor, version, transport, (), owner, "n/a", "n/a",
                                     status="unavailable")
        self.identity.require(ctx, "configure", "connector_contract", contract.contract_id)
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "connector_contract", contract.contract_id)
            state = {**(cur.state if cur else contract.to_dict()), "status": "unavailable",
                     "contract_id": contract.contract_id, "unavailable_reason": reason,
                     "scenario_results": cur.state.get("scenario_results", {}) if cur else {},
                     "spec_hash": cur.state.get("spec_hash") if cur else content_hash(contract.to_dict())}
            rec = tx.put(ctx.tenant_id, "connector_contract", contract.contract_id, state,
                         expected_revision=cur.revision if cur else None, action="declare_unavailable", reason=reason)
        return {**rec.state, "revision": rec.revision}

    def qualify(self, ctx: AccessContext, contract_id: str, scenario_results: dict[str, Any]) -> dict[str, Any]:
        """Supported only when every required scenario passed; otherwise simulated (never silently supported)."""
        self.identity.require(ctx, "approve", "connector_contract", contract_id)
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "connector_contract", contract_id)
            if rec.state["status"] == "unavailable":
                raise ValueError("unavailable variants must be re-registered before qualification")
            missing = [s for s in REQUIRED_SCENARIOS if not _passed(scenario_results.get(s))]
            status = "simulated" if missing else "supported"
            out = tx.put(ctx.tenant_id, "connector_contract", contract_id,
                         {**rec.state, "status": status, "scenario_results": scenario_results,
                          "failed_scenarios": missing, "qualified_at": iso(utc_now()) if not missing else None,
                          "qualified_by": ctx.actor_id if not missing else None},
                         expected_revision=rec.revision, action="qualify", reason=f"missing/failed: {missing}" if missing else None,
                         event_type="connector.qualified", event_payload={"contract_id": contract_id, "status": status})
        return {**out.state, "revision": out.revision}

    def get(self, tenant_id: str, contract_id: str) -> dict[str, Any] | None:
        rec = self.store.read().get(tenant_id, "connector_contract", contract_id)
        return {**rec.state, "revision": rec.revision} if rec else None

    def matrix(self, tenant_id: str) -> list[dict[str, Any]]:
        return [{**r.state, "revision": r.revision} for r in self.store.read().list(tenant_id, "connector_contract")]

    def advertised(self, tenant_id: str) -> list[dict[str, Any]]:
        return [row for row in self.matrix(tenant_id) if row["status"] == "supported"]

    def status_of(self, tenant_id: str, system: str, vendor: str, version: str, transport: str) -> str:
        row = self.get(tenant_id, f"{system}:{vendor}:{version}:{transport}")
        return row["status"] if row else "unavailable"


# --- LS-041: mapping templates -------------------------------------------------------------------

TRANSFORMS = ("strip", "upper", "lower", "float", "int", "date")


@dataclass(frozen=True)
class FieldMap:
    source: str
    canonical: str
    unit: str | None = None
    unit_field: str | None = None
    target_unit: str | None = None
    transform: str | None = None
    required: bool = False


@dataclass(frozen=True)
class ConnectorTemplate:
    template_id: str
    system: str
    record_type: str
    fields: tuple[FieldMap, ...]
    version: str = "1"
    id_field: str = "id"
    timestamp_field: str = "timestamp"
    sequence_field: str = "sequence"
    stream_field: str | None = None
    version_field: str = "schema_version"
    ignore_fields: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectorTemplate":
        """No-code configuration: a plain dict (JSON/YAML) with a ``fields`` list."""
        fields = tuple(FieldMap(**f) for f in data["fields"])
        extra = {k: v for k, v in data.items() if k not in ("fields", "ignore_fields")}
        return cls(fields=fields, ignore_fields=tuple(data.get("ignore_fields", ())), **extra)

    def to_dict(self) -> dict[str, Any]:
        return {**{k: v for k, v in self.__dict__.items() if k not in ("fields", "ignore_fields")},
                "fields": [f.__dict__.copy() for f in self.fields], "ignore_fields": list(self.ignore_fields)}

    def problems(self) -> list[str]:
        out = []
        seen: set[str] = set()
        for f in self.fields:
            if f.transform and f.transform not in TRANSFORMS:
                out.append(f"{f.source}: unknown transform {f.transform}")
            if f.canonical in seen:
                out.append(f"duplicate canonical field {f.canonical}")
            seen.add(f.canonical)
            if f.target_unit and not (f.unit or f.unit_field):
                out.append(f"{f.source}: target_unit without a source unit")
            for unit in (f.unit, f.target_unit):
                if unit:
                    try:
                        _ureg().Unit(unit)
                    except Exception:
                        out.append(f"{f.source}: unknown unit {unit}")
        return out

    def envelope_fields(self) -> set[str]:
        names = {self.id_field, self.timestamp_field, self.sequence_field, self.version_field, "source_record_id",
                 "site_id", "classification", "occurred_at", "missing_ranges", *self.ignore_fields}
        names |= {f.unit_field for f in self.fields if f.unit_field}
        if self.stream_field:
            names.add(self.stream_field)
        return names


def builtin_templates() -> dict[str, ConnectorTemplate]:
    return {
        "capture": ConnectorTemplate("capture", "ELN", "capture", (
            FieldMap("sample_id", "sample_id", required=True, transform="strip"),
            FieldMap("instrument_id", "instrument_id", transform="upper"),
            FieldMap("value", "measurement", unit_field="unit", target_unit="mg/L", transform="float", required=True),
            FieldMap("operator", "operator"))),
        "material": ConnectorTemplate("material", "ERP", "material", (
            FieldMap("lot_number", "lot", required=True, transform="strip"),
            FieldMap("material_code", "material_code", transform="upper"),
            FieldMap("expiry", "expiry", transform="date", required=True),
            FieldMap("qty", "quantity", unit_field="uom", target_unit="kg", transform="float", required=True),
            FieldMap("status", "status", transform="lower"))),
        "maintenance": ConnectorTemplate("maintenance", "CMMS", "maintenance", (
            FieldMap("work_order", "work_order", required=True),
            FieldMap("equipment_id", "equipment_id", transform="upper", required=True),
            FieldMap("status", "status", transform="lower"),
            FieldMap("due_date", "due_date", transform="date"),
            FieldMap("downtime_h", "downtime", unit="hour", target_unit="minute", transform="float"),
            FieldMap("description", "description"))),
    }


def _get_path(payload: dict[str, Any], path: str) -> Any:
    cur: Any = payload
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _transform(value: Any, name: str | None) -> Any:
    if name is None:
        return value
    if name == "strip":
        return str(value).strip()
    if name == "upper":
        return str(value).strip().upper()
    if name == "lower":
        return str(value).strip().lower()
    if name == "float":
        return float(value)
    if name == "int":
        return int(float(value))
    if name == "date":
        text = str(value).strip()
        return (date.fromisoformat(text) if len(text) <= 10 else parse_iso(text.replace("Z", "+00:00")).date()).isoformat()
    raise ValueError(f"unknown transform {name}")


def apply_mapping(template: ConnectorTemplate, payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    units: dict[str, str] = {}
    conversions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    unmapped: dict[str, Any] = {}
    mapped_sources: set[str] = set()
    for fm in template.fields:
        mapped_sources.add(fm.source.split(".")[0])
        raw = _get_path(payload, fm.source)
        if raw is None or raw == "":
            if fm.required:
                errors.append({"field": fm.source, "error": "missing required field"})
            continue
        try:
            value = _transform(raw, fm.transform)
            source_unit = fm.unit or (payload.get(fm.unit_field) if fm.unit_field else None)
            if source_unit:
                qty = _ureg().Quantity(float(value), source_unit)
                if fm.target_unit and fm.target_unit != source_unit:
                    value = _round(qty.to(fm.target_unit).magnitude)
                    conversions.append({"field": fm.canonical, "raw_value": raw, "from_unit": source_unit,
                                        "to_unit": fm.target_unit, "value": value})
                    units[fm.canonical] = fm.target_unit
                else:
                    value = float(value)
                    units[fm.canonical] = source_unit
            fields[fm.canonical] = value
        except Exception as exc:
            errors.append({"field": fm.source, "error": f"{type(exc).__name__}: {exc}", "raw_value": raw})
            unmapped[fm.source] = raw
    for key, value in payload.items():
        if key not in mapped_sources and key not in template.envelope_fields():
            unmapped[key] = value
    return {"fields": fields, "units": units, "unmapped": unmapped, "conversions": conversions, "errors": errors}


def _payload_of(sample: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(sample, SourceRecord):
        return sample.source_record_id, sample.payload
    return str(sample.get("source_record_id") or sample.get("id") or ""), sample


def preview_mapping(template: ConnectorTemplate, sample_records: Iterable[Any]) -> dict[str, Any]:
    """Pure dry run: nothing is written anywhere."""
    rows, conversions, errors = [], [], []
    unmapped_counts: dict[str, int] = {}
    for sample in sample_records:
        rid, payload = _payload_of(sample)
        m = apply_mapping(template, payload)
        rows.append({"source_record_id": rid, "fields": m["fields"], "units": m["units"], "unmapped": m["unmapped"]})
        conversions += [{"source_record_id": rid, **c} for c in m["conversions"]]
        errors += [{"source_record_id": rid, **e} for e in m["errors"]]
        for key in m["unmapped"]:
            unmapped_counts[key] = unmapped_counts.get(key, 0) + 1
    return {"template_id": template.template_id, "rows": rows,
            "unmapped_fields": [{"field": k, "count": v} for k, v in sorted(unmapped_counts.items())],
            "unit_conversions": conversions, "errors": errors, "template_problems": template.problems(),
            "written": False}


def test_connection(template: ConnectorTemplate, connector: Any, limit: int = 5) -> dict[str, Any]:
    """Dry run: pull a sample with no checkpoint and preview the mapping; persists nothing."""
    try:
        batch = connector.pull(None, limit)
    except Exception as exc:
        return {"ok": False, "stage": "connect", "error": f"{type(exc).__name__}: {exc}", "wrote": False}
    preview = preview_mapping(template, batch.records)
    ok = not preview["errors"] and not preview["template_problems"]
    return {"ok": ok, "stage": "mapping", "records_sampled": len(batch.records), "preview": preview,
            "next_checkpoint": batch.next_checkpoint, "wrote": False}


test_connection.__test__ = False


# --- LS-004 / LS-029 / LS-063: intake -------------------------------------------------------------


class IntakeService:
    """Cursor-driven, idempotent evidence intake from any ``pull(checkpoint, limit)`` connector."""

    def __init__(self, store: RecordStore, evidence: EvidenceService) -> None:
        self.store, self.evidence, self.identity = store, evidence, evidence.identity

    def cursor(self, tenant_id: str, connector_id: str) -> dict[str, Any] | None:
        rec = self.store.read().get(tenant_id, "connector_cursor", connector_id)
        return {**rec.state, "revision": rec.revision} if rec else None

    def sync(self, ctx: AccessContext, connector: Any, mapping: ConnectorTemplate, *, batch_size: int = 100,
             max_batches: int = 100, site_id: str | None = None) -> dict[str, Any]:
        cid = connector.connector_id
        self.identity.require(ctx, "configure", "connector", cid, site_id=site_id)
        totals = {"connector_id": cid, "ingested": 0, "duplicates": 0, "corrections": 0, "late": 0,
                  "gaps_opened": 0, "mapping_issues": 0, "batches": 0}
        for _ in range(max_batches):
            cur = self.store.read().get(ctx.tenant_id, "connector_cursor", cid)
            state = cur.state if cur else {"checkpoint": None, "high_water": None, "last_sequence": {}, "records": 0}
            batch: PullBatch = connector.pull(state["checkpoint"], batch_size)
            results = [self._ingest(ctx, rec, mapping, state, site_id) for rec in batch.records]
            self._commit(ctx, cid, mapping, batch, results, state, cur.revision if cur else None, totals)
            totals["batches"] += 1
            if not batch.has_more:
                break
        totals["checkpoint"] = (self.cursor(ctx.tenant_id, cid) or {}).get("checkpoint")
        return totals

    def _ingest(self, ctx: AccessContext, rec: SourceRecord, mapping: ConnectorTemplate, state: dict[str, Any],
                site_id: str | None) -> dict[str, Any]:
        payload = rec.payload
        mapped = apply_mapping(mapping, payload)
        et = iso(rec.occurred_at)
        hw = parse_iso(state["high_water"])
        stream = str(payload.get(mapping.stream_field, "default")) if mapping.stream_field else "default"
        seq = payload.get(mapping.sequence_field)
        late = bool(hw and rec.occurred_at < hw)
        metadata = {"template": f"{mapping.template_id}@{mapping.version}", "mapped": mapped["fields"],
                    "units": mapped["units"], "unmapped": mapped["unmapped"], "late": late, "stream": stream,
                    "sequence": seq, "recorded_separately": True}
        version = payload.get("revision") or payload.get(mapping.version_field)
        res = self.evidence.ingest(
            ctx, source_system=rec.source_system, source_record_id=rec.source_record_id,
            content=canonical_json(payload).encode(), media_type="application/json", site_id=site_id or rec.site_id,
            event_time=et, source_revision=str(version) if version is not None else None,
            mapping_version=f"{mapping.template_id}@{mapping.version}", metadata=metadata)
        dup = bool(res.get("duplicate"))
        if not dup:
            ref = EvidenceRef("evidence", res["evidence_id"], res["revision"], res.get("site_id"))
            for fm in mapping.fields:
                if fm.canonical in mapped["fields"] and (fm.unit or fm.unit_field or fm.transform in ("float", "int", "date")):
                    raw = _get_path(payload, fm.source)
                    self.evidence.normalize(
                        ctx, evidence=ref, field=fm.canonical, raw_value=raw,
                        raw_unit=fm.unit or (payload.get(fm.unit_field) if fm.unit_field else None),
                        value=mapped["fields"][fm.canonical], unit=mapped["units"].get(fm.canonical),
                        time_basis="event_time", transform=fm.transform or "unit_conversion",
                        transform_version=f"{mapping.template_id}@{mapping.version}")
        late = late if not dup else bool(res.get("metadata", {}).get("late"))
        return {"record": rec, "mapped": mapped, "duplicate": dup, "late": late, "stream": stream, "seq": seq,
                "correction": (not dup) and res.get("supersedes_digest") is not None, "event_time": rec.occurred_at,
                "evidence_id": res["evidence_id"]}

    def _commit(self, ctx: AccessContext, cid: str, mapping: ConnectorTemplate, batch: PullBatch,
                results: list[dict[str, Any]], state: dict[str, Any], revision: int | None,
                totals: dict[str, Any]) -> None:
        last = dict(state["last_sequence"])
        gap_streams = set(state.get("gap_streams", []))
        hw = parse_iso(state["high_water"])
        with self.store.transaction(ctx.actor_id) as tx:
            for r in results:
                rid = r["record"].source_record_id
                totals["duplicates" if r["duplicate"] else "ingested"] += 1
                totals["corrections"] += int(r["correction"])
                if r["late"] and tx.get(ctx.tenant_id, "late_arrival", f"{cid}:{rid}") is None:
                    tx.put(ctx.tenant_id, "late_arrival", f"{cid}:{rid}", {
                        "connector_id": cid, "source_record_id": rid, "event_time": iso(r["event_time"]),
                        "high_water": state["high_water"], "recorded_at": iso(utc_now())},
                           expected_revision=None, action="flag_late", event_type="connector.late_data",
                           event_payload={"connector_id": cid, "source_record_id": rid})
                    totals["late"] += 1
                self._record_issues(tx, ctx.tenant_id, cid, mapping, r, totals)
                if isinstance(r["seq"], int):
                    opened = self._track_sequence(tx, ctx.tenant_id, cid, r["stream"], r["seq"], last, gap_streams)
                    totals["gaps_opened"] += opened
                for lo, hi in r["record"].payload.get("missing_ranges", []):
                    totals["gaps_opened"] += self._open_gap(tx, ctx.tenant_id, cid, r["stream"], int(lo), int(hi))
                    gap_streams.add(r["stream"])
                hw = r["event_time"] if hw is None or r["event_time"] > hw else hw
            new_state = {"connector_id": cid, "checkpoint": batch.next_checkpoint or state["checkpoint"],
                         "high_water": iso(hw), "last_sequence": last, "gap_streams": sorted(gap_streams),
                         "records": state["records"] + len(results), "updated_at": iso(utc_now())}
            tx.put(ctx.tenant_id, "connector_cursor", cid, new_state, expected_revision=revision, action="advance_cursor",
                   event_type="connector.synced", event_payload={"connector_id": cid, "count": len(results)})

    def _record_issues(self, tx: Transaction, tenant: str, cid: str, mapping: ConnectorTemplate,
                       r: dict[str, Any], totals: dict[str, Any]) -> None:
        rid = r["record"].source_record_id
        issues = [(k, "unmapped_field", "unknown field retained unmapped") for k in r["mapped"]["unmapped"]
                  if not any(e["field"] == k for e in r["mapped"]["errors"])]
        issues += [(e["field"], "mapping_error", e["error"]) for e in r["mapped"]["errors"]]
        for fname, kind, detail in issues:
            iid = f"{cid}:{mapping.template_id}@{mapping.version}:{fname}"
            cur = tx.get(tenant, "mapping_issue", iid)
            if cur and rid in cur.state["occurrences"]:
                continue
            occ = [*(cur.state["occurrences"] if cur else []), rid][-20:]
            tx.put(tenant, "mapping_issue", iid, {
                "connector_id": cid, "template_id": mapping.template_id, "template_version": mapping.version,
                "field": fname, "issue": kind, "detail": detail, "status": "open", "occurrences": occ,
                "count": (cur.state["count"] if cur else 0) + 1, "first_seen": cur.state["first_seen"] if cur else iso(utc_now())},
                   expected_revision=cur.revision if cur else None, action="mapping_issue", event_type=None)
            totals["mapping_issues"] += 0 if cur else 1

    def _open_gap(self, tx: Transaction, tenant: str, cid: str, stream: str, lo: int, hi: int) -> int:
        gid = f"{cid}:{stream}:{lo}-{hi}"
        if hi < lo or tx.get(tenant, "source_gap", gid) is not None:
            return 0
        tx.put(tenant, "source_gap", gid, {"connector_id": cid, "stream": stream, "from_sequence": lo,
                                           "to_sequence": hi, "status": "open", "detected_at": iso(utc_now())},
               expected_revision=None, action="open_gap", event_type="connector.gap_detected",
               event_payload={"connector_id": cid, "stream": stream, "from": lo, "to": hi})
        return 1

    def _track_sequence(self, tx: Transaction, tenant: str, cid: str, stream: str, seq: int, last: dict[str, int],
                        gap_streams: set[str]) -> int:
        prev = last.get(stream)
        opened = self._open_gap(tx, tenant, cid, stream, prev + 1, seq - 1) if prev is not None and seq > prev + 1 else 0
        if opened:
            gap_streams.add(stream)
        if prev is None or seq > prev:
            last[stream] = seq
        if stream in gap_streams:
            self._fill_gaps(tx, tenant, cid, stream, seq)
        return opened

    def _fill_gaps(self, tx: Transaction, tenant: str, cid: str, stream: str, seq: int) -> None:
        for rec in tx.list(tenant, "source_gap", lambda s: s["connector_id"] == cid and s["stream"] == stream
                           and s["status"] == "open" and s["from_sequence"] <= seq <= s["to_sequence"]):
            lo, hi = rec.state["from_sequence"], rec.state["to_sequence"]
            tx.put(tenant, "source_gap", rec.id, {**rec.state, "status": "filled", "filled_at": iso(utc_now()),
                                                  "filled_by_sequence": seq}, expected_revision=rec.revision, action="fill_gap")
            for a, b in ((lo, seq - 1), (seq + 1, hi)):
                self._open_gap(tx, tenant, cid, stream, a, b)

    def gaps(self, ctx: AccessContext, connector_id: str | None = None, status: str | None = "open") -> list[dict[str, Any]]:
        self.identity.require(ctx, "read", "source_gap")
        rows = self.store.read().list(ctx.tenant_id, "source_gap", lambda s: (connector_id is None or s["connector_id"] == connector_id)
                                      and (status is None or s["status"] == status))
        return sorted(({**r.state, "gap_id": r.id} for r in rows), key=lambda g: (g["stream"], g["from_sequence"]))

    def late(self, ctx: AccessContext, connector_id: str) -> list[dict[str, Any]]:
        self.identity.require(ctx, "read", "late_arrival")
        return [r.state for r in self.store.read().list(ctx.tenant_id, "late_arrival", lambda s: s["connector_id"] == connector_id)]

    def mapping_issues(self, ctx: AccessContext, connector_id: str) -> list[dict[str, Any]]:
        self.identity.require(ctx, "read", "mapping_issue")
        return [r.state for r in self.store.read().list(ctx.tenant_id, "mapping_issue", lambda s: s["connector_id"] == connector_id)]


def run_scenarios(contract: ConnectorContract, connector: Any, template: ConnectorTemplate, *,
                  unauthorized_connector: Any | None = None, sample: int = 20) -> dict[str, dict[str, Any]]:
    """Execute the qualification scenarios for a read connector; results feed ``ConnectorMatrix.qualify``."""
    out: dict[str, dict[str, Any]] = {}
    try:
        first = connector.pull(None, sample)
        out["authorized_read"] = {"passed": bool(first.records), "detail": f"{len(first.records)} records"}
        if unauthorized_connector is not None:
            try:
                unauthorized_connector.pull(None, 1)
                out["authorized_read"] = {"passed": False, "detail": "unauthenticated read succeeded"}
            except (HTTPError, PermissionError, OSError):
                pass
        second = connector.pull(None, sample)
    except Exception as exc:
        failure = {"passed": False, "detail": f"{type(exc).__name__}: {exc}"}
        return {name: failure for name in REQUIRED_SCENARIOS}
    ids = [r.source_record_id for r in first.records]
    out["identity"] = {"passed": bool(ids) and len(set(ids)) == len(ids) and ids == [r.source_record_id for r in second.records],
                       "detail": "stable unique source ids across pulls"}
    versions = {str(r.payload.get(template.version_field)) for r in first.records}
    out["version"] = {"passed": versions == {contract.schema_version}, "detail": f"schema versions seen {sorted(versions)}"}
    preview = preview_mapping(template, first.records)
    out["mapping"] = {"passed": not preview["errors"] and not preview["template_problems"],
                      "detail": f"{len(preview['errors'])} errors, {len(preview['unmapped_fields'])} unmapped fields"}
    out["gap"] = {"passed": bool(first.records) and all(isinstance(r.payload.get(template.sequence_field), int)
                                                      for r in first.records),
                  "detail": "every record carries an integer sequence enabling gap detection"}
    return out


# --- LS-023: transports ---------------------------------------------------------------------------


def sign_payload(secret: str, timestamp: int | str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


class WebhookRejected(PermissionError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class WebhookIntake:
    """Durable HTTP webhook intake: HMAC-SHA256 over ``timestamp.body``, tolerance window, replay protection.

    Accepted records queue in the store and are pulled by ``IntakeService.sync`` like any connector.
    """

    def __init__(self, store: RecordStore, tenant_id: str, connector_id: str, source_system: str,
                 secrets: Sequence[str], *, tolerance_seconds: int = 300, site_id: str | None = None,
                 now: Callable[[], float] = time.time) -> None:
        self.store, self.tenant_id, self.connector_id, self.source_system = store, tenant_id, connector_id, source_system
        self.secrets, self.tolerance, self.site_id, self.now = tuple(secrets), tolerance_seconds, site_id, now
        self.queue = DurableQueue(store, tenant_id, f"webhook:{connector_id}")

    def handle(self, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        h = {k.lower(): v for k, v in headers.items()}
        ts, sig, delivery = h.get("x-timestamp"), h.get("x-signature"), h.get("x-delivery-id")
        if not (ts and sig and delivery):
            raise WebhookRejected("missing_headers", "x-timestamp, x-signature and x-delivery-id are required")
        if not any(hmac.compare_digest(sign_payload(s, ts, body), sig) for s in self.secrets):
            raise WebhookRejected("bad_signature")
        try:
            skew = abs(self.now() - float(ts))
        except ValueError:
            raise WebhookRejected("bad_timestamp") from None
        if skew > self.tolerance:
            raise WebhookRejected("stale_timestamp", f"skew {skew:.0f}s exceeds {self.tolerance}s")
        try:
            doc = json.loads(body)
            values = doc["records"] if isinstance(doc, dict) and "records" in doc else [doc]
            records = [source_record_from(v, source_system=self.source_system, fallback_id="", site_id=self.site_id)
                       for v in values]
        except (ValueError, KeyError, TypeError) as exc:
            raise WebhookRejected("bad_payload", str(exc)) from None
        with self.store.transaction(f"webhook:{self.connector_id}") as tx:
            if not tx.inbox_claim(f"webhook:{self.tenant_id}:{self.connector_id}", delivery):
                raise WebhookRejected("replay", f"delivery {delivery} already processed")
            for rec in records:
                self.queue.append(tx, {"record": record_to_dict(rec), "delivery_id": delivery, "received_at": iso(utc_now())})
        return {"status": "accepted", "records": len(records), "delivery_id": delivery}

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        offset = int(checkpoint or 0)
        items = self.queue.read(offset, limit)
        return PullBatch(tuple(record_from_dict(i["record"]) for i in items), str(offset + len(items)),
                         offset + len(items) < self.queue.count())


@dataclass(frozen=True)
class TransportMessage:
    address: str
    value: Any
    source_timestamp: str
    quality: Any = "good"
    sequence: int | None = None


class TransportClient(Protocol):
    def subscribe(self, addresses: Sequence[str]) -> None: ...
    def poll(self, max_messages: int) -> list[TransportMessage]: ...


class SimulatedTransportClient:
    """In-memory MQTT/OPC UA stand-in. ``write`` exists only to prove adapters never forward it."""

    def __init__(self, supports_republish: bool = False) -> None:
        self.subscribed: list[str] = []
        self.queue: list[TransportMessage] = []
        self.history: list[TransportMessage] = []
        self.supports_republish = supports_republish
        self.writes: list[Any] = []

    def subscribe(self, addresses: Sequence[str]) -> None:
        self.subscribed = list(addresses)

    def feed(self, messages: Iterable[TransportMessage], deliver: bool = True) -> None:
        for m in messages:
            self.history.append(m)
            if deliver:
                self.queue.append(m)

    def poll(self, max_messages: int) -> list[TransportMessage]:
        out, self.queue = self.queue[:max_messages], self.queue[max_messages:]
        return out

    def republish(self, address: str, from_seq: int, to_seq: int) -> list[TransportMessage]:
        if not self.supports_republish:
            raise NotImplementedError("server does not support retransmission")
        return [m for m in self.history if m.address == address and m.sequence is not None and from_seq <= m.sequence <= to_seq]

    def write(self, address: str, value: Any) -> None:
        self.writes.append((address, value))


def normalize_quality(quality: Any) -> str:
    if isinstance(quality, int):
        return "good" if quality < 0x40000000 else "uncertain" if quality < 0x80000000 else "bad"
    text = str(quality).lower()
    return next((q for q in ("good", "uncertain", "bad") if text.startswith(q)), "uncertain")


_CONTROL_PREFIXES = ("write", "publish", "set_", "call_", "control", "actuate", "command", "send_command")


def _deny(*_: Any, **__: Any) -> Any:
    raise PermissionError(CONTROL_WRITES_PROHIBITED)


class TelemetryAdapter:
    """Read-only subscriber that reduces high-rate readings to bounded windows (no per-reading model call).

    Open windows are held in memory; closed windows are persisted to a durable queue consumed by ``pull``.
    Message-level sequence gaps are carried on the window as ``missing_ranges``.
    """

    transport = ""

    def __init__(self, store: RecordStore, tenant_id: str, connector_id: str, source_system: str,
                 client: TransportClient, addresses: Sequence[str], *, window_seconds: int = 60,
                 site_id: str | None = None) -> None:
        self.store, self.tenant_id, self.connector_id, self.source_system = store, tenant_id, connector_id, source_system
        self.client, self.addresses, self.window, self.site_id = client, tuple(addresses), window_seconds, site_id
        self.queue = DurableQueue(store, tenant_id, f"telemetry:{connector_id}")
        self._open: dict[tuple[str, int], dict[str, Any]] = {}
        self._closed_upto: dict[str, int] = {}
        self._last_seq: dict[str, int] = {}
        self.client.subscribe(self.addresses)

    def __getattr__(self, name: str) -> Any:
        if name.startswith(_CONTROL_PREFIXES):
            return _deny
        raise AttributeError(name)

    def message_to_record(self, m: TransportMessage, **extra: Any) -> SourceRecord:
        ts = parse_iso(m.source_timestamp)
        key = m.sequence if m.sequence is not None else m.source_timestamp
        payload = {"stream": m.address, "address": m.address, "value": m.value, "quality": normalize_quality(m.quality),
                   "source_timestamp": iso(ts), "sequence": m.sequence, "timestamp": iso(ts), **extra}
        return SourceRecord(f"{self.connector_id}:{m.address}:{key}", self.source_system, ts, payload, self.site_id)

    def poll_once(self, max_messages: int = 1000) -> dict[str, int]:
        msgs = self.client.poll(max_messages)
        for m in msgs:
            self.ingest(m)
        return {"messages": len(msgs), "open_windows": len(self._open), "emitted": self.queue.count()}

    def ingest(self, m: TransportMessage) -> None:
        ts = parse_iso(m.source_timestamp).timestamp()
        ws = int(ts // self.window) * self.window
        missing: list[list[int]] = []
        if m.sequence is not None:
            last = self._last_seq.get(m.address)
            if last is not None and m.sequence <= last:
                return
            if last is not None and m.sequence > last + 1:
                missing.append([last + 1, m.sequence - 1])
            self._last_seq[m.address] = m.sequence
        if ws < self._closed_upto.get(m.address, 0):
            self._enqueue(self.message_to_record(m, late=True))
            return
        w = self._open.setdefault((m.address, ws), {
            "count": 0, "good": 0, "min": None, "max": None, "sum": 0.0, "quality_counts": {}, "first_sequence": None,
            "last_sequence": None, "first_source_time": m.source_timestamp, "last_source_time": m.source_timestamp,
            "missing_ranges": []})
        q = normalize_quality(m.quality)
        w["count"] += 1
        w["quality_counts"][q] = w["quality_counts"].get(q, 0) + 1
        w["missing_ranges"] += missing
        if m.sequence is not None:
            w["first_sequence"] = m.sequence if w["first_sequence"] is None else min(w["first_sequence"], m.sequence)
            w["last_sequence"] = m.sequence if w["last_sequence"] is None else max(w["last_sequence"], m.sequence)
        w["last_source_time"] = max(w["last_source_time"], m.source_timestamp)
        if q == "good" and isinstance(m.value, (int, float)) and not isinstance(m.value, bool):
            v = float(m.value)
            w["good"] += 1
            w["sum"] += v
            w["min"] = v if w["min"] is None else min(w["min"], v)
            w["max"] = v if w["max"] is None else max(w["max"], v)
        for key in [k for k in self._open if k[0] == m.address and k[1] < ws]:
            self._close(*key)

    def flush(self) -> int:
        keys = sorted(self._open)
        for key in keys:
            self._close(*key)
        return len(keys)

    def _close(self, address: str, ws: int) -> None:
        w = self._open.pop((address, ws))
        start = datetime.fromtimestamp(ws, timezone.utc)
        payload = {"stream": address, "address": address, "timestamp": iso(start), "window_start": iso(start),
                   "window_end": iso(start + timedelta(seconds=self.window)), "window_seconds": self.window,
                   "count": w["count"], "good_count": w["good"], "min": w["min"], "max": w["max"],
                   "mean": (w["sum"] / w["good"]) if w["good"] else None, "quality_counts": w["quality_counts"],
                   "first_sequence": w["first_sequence"], "last_sequence": w["last_sequence"],
                   "first_source_time": w["first_source_time"], "last_source_time": w["last_source_time"],
                   "missing_ranges": w["missing_ranges"]}
        self._closed_upto[address] = max(self._closed_upto.get(address, 0), ws + self.window)
        self._enqueue(SourceRecord(f"{self.connector_id}:{address}:{payload['window_start']}", self.source_system,
                                   start, payload, self.site_id))

    def _enqueue(self, rec: SourceRecord) -> None:
        with self.store.transaction(f"telemetry:{self.connector_id}") as tx:
            self.queue.append(tx, {"record": record_to_dict(rec)})

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        offset = int(checkpoint or 0)
        items = self.queue.read(offset, limit)
        return PullBatch(tuple(record_from_dict(i["record"]) for i in items), str(offset + len(items)),
                         offset + len(items) < self.queue.count())


class MqttAdapter(TelemetryAdapter):
    transport = "mqtt"


class OpcUaAdapter(TelemetryAdapter):
    """OPC UA subscriber; retransmission backfill works only when the server supports republish."""

    transport = "opcua"

    def backfill(self, address: str, from_seq: int, to_seq: int) -> int:
        republish = getattr(self.client, "republish", None)
        if republish is None:
            raise NotImplementedError("client has no republish capability")
        msgs = republish(address, from_seq, to_seq)
        for m in msgs:
            self._enqueue(self.message_to_record(m, backfilled=True))
        return len(msgs)


for _name in ("write", "publish", "write_value", "write_node", "call_method", "set_value", "control", "send_command"):
    setattr(TelemetryAdapter, _name, _deny)


class SiteCollectorBuffer:
    """Spools records durably while the WAN is down and flushes in collector order on reconnect.

    Spool payloads can be passed through an injected ``encrypt``/``decrypt`` pair; no cipher is bundled.
    """

    def __init__(self, store: RecordStore, tenant_id: str, collector_id: str, uplink: Callable[[SourceRecord], None],
                 *, encrypt: Callable[[bytes], bytes] | None = None, decrypt: Callable[[bytes], bytes] | None = None) -> None:
        self.store, self.tenant_id, self.collector_id, self.uplink = store, tenant_id, collector_id, uplink
        self.encrypt, self.decrypt = encrypt, decrypt

    def receive(self, record: SourceRecord) -> int:
        data = canonical_json(record_to_dict(record)).encode()
        entry: dict[str, Any] = {"collector_id": self.collector_id, "status": "pending", "spooled_at": iso(utc_now())}
        if self.encrypt:
            entry["encrypted"] = base64.b64encode(self.encrypt(data)).decode()
        else:
            entry["record"] = record_to_dict(record)
        with self.store.transaction(f"collector:{self.collector_id}") as tx:
            head = tx.get(self.tenant_id, "collector_state", self.collector_id)
            seq = head.state["next_seq"] if head else 1
            tx.put(self.tenant_id, "spool", f"{self.collector_id}:{seq:012d}", {**entry, "collector_seq": seq},
                   expected_revision=None, action="spool")
            tx.put(self.tenant_id, "collector_state", self.collector_id, {"next_seq": seq + 1},
                   expected_revision=head.revision if head else None, action="advance_collector")
        return seq

    def _decode(self, state: dict[str, Any]) -> SourceRecord:
        if "encrypted" in state:
            return record_from_dict(json.loads((self.decrypt or (lambda b: b))(base64.b64decode(state["encrypted"]))))
        return record_from_dict(state["record"])

    def pending(self) -> list[tuple[str, dict[str, Any]]]:
        rows = self.store.read().list(self.tenant_id, "spool", lambda s: s["collector_id"] == self.collector_id and s["status"] == "pending")
        return sorted(((r.id, r.state) for r in rows), key=lambda x: x[1]["collector_seq"])

    def flush(self) -> dict[str, Any]:
        delivered, error = 0, None
        for rid, state in self.pending():
            try:
                self.uplink(self._decode(state))
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                break
            with self.store.transaction(f"collector:{self.collector_id}") as tx:
                cur = tx.require(self.tenant_id, "spool", rid)
                tx.put(self.tenant_id, "spool", rid, {**cur.state, "status": "delivered", "delivered_at": iso(utc_now())},
                       expected_revision=cur.revision, action="deliver_spooled")
            delivered += 1
        return {"delivered": delivered, "pending": len(self.pending()), "error": error}


class FileDropConnector:
    """Directory of CSV/JSON/JSONL instrument exports; incremental by file digest and row offset."""

    def __init__(self, connector_id: str, source_system: str, directory: Path, *, site_id: str | None = None,
                 patterns: Sequence[str] = ("*.csv", "*.json", "*.jsonl"), timestamp_field: str = "timestamp",
                 id_field: str = "id") -> None:
        self.connector_id, self.source_system, self.directory, self.site_id = connector_id, source_system, Path(directory), site_id
        self.patterns, self.timestamp_field, self.id_field = tuple(patterns), timestamp_field, id_field
        self.rejects: list[dict[str, Any]] = []

    def _rows(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text()
        if path.suffix == ".csv":
            return [dict(r) for r in csv.DictReader(io.StringIO(text))]
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        doc = json.loads(text)
        return doc["records"] if isinstance(doc, dict) else doc

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        files: dict[str, dict[str, Any]] = json.loads(checkpoint)["files"] if checkpoint else {}
        records: list[SourceRecord] = []
        more = False
        paths = sorted({p for pat in self.patterns for p in self.directory.glob(pat)})
        for path in paths:
            if not path.is_file() or not path.resolve().is_relative_to(self.directory.resolve()):
                self.rejects.append({"file": path.name, "error": "source escapes configured directory or is not a file"})
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            entry = files.get(path.name)
            if entry and entry["digest"] == digest and entry["done"]:
                continue
            rows = self._rows(path)
            start = entry["rows"] if entry and entry["digest"] == digest else 0
            room = limit - len(records)
            if room <= 0:
                more = True
                break
            taken = rows[start:start + room]
            for offset, row in enumerate(taken, start):
                row = {k: (int(v) if k == "sequence" and isinstance(v, str) and v.isdigit() else v) for k, v in row.items()}
                row.setdefault("source_file", path.name)
                row.setdefault(self.id_field, f"{path.name}:{offset}")
                try:
                    records.append(source_record_from(row, source_system=self.source_system, fallback_id="",
                                                      timestamp_field=self.timestamp_field, site_id=self.site_id))
                except ValueError as exc:
                    self.rejects.append({"file": path.name, "row": offset, "error": str(exc)})
            files[path.name] = {"digest": digest, "rows": start + len(taken), "done": start + len(taken) >= len(rows)}
            if start + len(taken) < len(rows):
                more = True
                break
        return PullBatch(tuple(records), json.dumps({"files": files}, sort_keys=True), more)


# --- LS-043: ERP -----------------------------------------------------------------------------------

ERP_FIELDS = {"master": ("description", "uom", "status"), "production_run": ("product", "status", "lot"),
              "lot": ("material", "status"), "consumption": ("run", "lot"), "status": ("status",)}


def _erp_dict(rec: Any) -> dict[str, Any]:
    return dict(rec.payload) if isinstance(rec, SourceRecord) else dict(rec)


def _qty(rec: dict[str, Any]) -> tuple[float, str] | None:
    value = rec.get("qty", rec.get("planned_qty"))
    return None if value is None else (float(value), rec.get("unit") or rec.get("uom") or "")


class ErpReconciler:
    """Pure comparison of ERP-authoritative records with the local projection."""

    def __init__(self, qty_tolerance: float = 1e-9) -> None:
        self.tolerance = qty_tolerance

    def reconcile(self, erp_records: Iterable[Any], local_records: Iterable[Any]) -> list[dict[str, Any]]:
        erp = {(d.get("type"), str(d.get("id"))): d for d in map(_erp_dict, erp_records)}
        local = {(d.get("type"), str(d.get("id"))): d for d in map(_erp_dict, local_records)}
        out: list[dict[str, Any]] = []
        for key in sorted(set(erp) | set(local), key=lambda k: (str(k[0]), k[1])):
            rtype, rid = key
            if key not in local:
                out.append({"type": rtype, "id": rid, "kind": "missing_local", "erp": erp[key], "local": None})
                continue
            if key not in erp:
                out.append({"type": rtype, "id": rid, "kind": "missing_in_erp", "erp": None, "local": local[key]})
                continue
            e, l = erp[key], local[key]
            out += [{"type": rtype, "id": rid, **d} for d in self._compare(rtype, e, l)]
        return out

    def _compare(self, rtype: str, e: dict[str, Any], l: dict[str, Any]) -> list[dict[str, Any]]:
        found = []
        eq, lq = _qty(e), _qty(l)
        if eq and lq:
            try:
                local_in_erp = _ureg().Quantity(lq[0], lq[1] or "dimensionless").to(eq[1] or "dimensionless").magnitude
                if abs(local_in_erp - eq[0]) > self.tolerance * max(1.0, abs(eq[0])):
                    found.append({"kind": "qty_mismatch", "field": "qty", "erp": f"{eq[0]} {eq[1]}".strip(),
                                  "local": f"{lq[0]} {lq[1]}".strip()})
            except Exception:
                found.append({"kind": "unit_mismatch", "field": "unit", "erp": eq[1], "local": lq[1]})
        elif eq or lq:
            found.append({"kind": "field_mismatch", "field": "qty", "erp": eq, "local": lq})
        if rtype == "lot" or "expiry" in e or "expiry" in l:
            if _norm_date(e.get("expiry")) != _norm_date(l.get("expiry")):
                found.append({"kind": "expiry_mismatch", "field": "expiry", "erp": e.get("expiry"), "local": l.get("expiry")})
        for f in ERP_FIELDS.get(rtype, ()):
            if e.get(f) != l.get(f) and (f in e or f in l):
                found.append({"kind": "status_mismatch" if f == "status" else "field_mismatch", "field": f,
                              "erp": e.get(f), "local": l.get(f)})
        return found

    def persist(self, ctx: AccessContext, store: RecordStore, run_id: str, discrepancies: list[dict[str, Any]]) -> None:
        with store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "erp_reconciliation", run_id, {"run_id": run_id, "at": iso(utc_now()),
                                                                 "discrepancies": discrepancies, "count": len(discrepancies)},
                   expected_revision=None, action="reconcile_erp", event_type="erp.reconciled",
                   event_payload={"run_id": run_id, "count": len(discrepancies)})


def _norm_date(value: Any) -> str | None:
    return None if value in (None, "") else _transform(value, "date")


ERP_WRITE_OPERATIONS = ("reserve_material", "consume_material")


class ErpWriteback:
    """ERP consumption/reservation write-back: propose -> approve -> dispatch through a Writer only."""

    def __init__(self, actions: ActionService, ownership: OwnershipRegistry) -> None:
        self.actions, self.ownership = actions, ownership

    def configure_ownership(self, tenant_id: str, site_id: str, *, by: str, reason: str) -> None:
        for op in ERP_WRITE_OPERATIONS:
            self.ownership.assign(tenant_id, Ownership(op, site_id, "external", "ERP", ERP_WRITE_OPERATIONS, True),
                                  by=by, reason=reason)

    def propose(self, ctx: AccessContext, *, operation: str, lot_id: str, run_id: str, qty: float, unit: str,
                basis: list[dict[str, Any]], site_id: str, owner_id: str, rationale: str) -> dict[str, Any]:
        if operation not in ERP_WRITE_OPERATIONS:
            raise ValueError(f"operation must be one of {ERP_WRITE_OPERATIONS}")
        return self.actions.propose(
            ctx, target_system="ERP", operation=operation, target_id=lot_id,
            payload={"lot": lot_id, "run": run_id, "qty": qty, "unit": unit}, basis=basis, rationale=rationale,
            expected_result=f"ERP balance for {lot_id} reflects {qty} {unit} {operation.split('_')[0]}d against {run_id}",
            owner_id=owner_id, follow_up_measure="erp_lot_balance", site_id=site_id, record_class=operation)

    def dispatch(self, ctx: AccessContext, intent_id: str, writer: Any) -> dict[str, Any]:
        return self.actions.dispatch(ctx, intent_id, writer)

    def recover(self, ctx: AccessContext, intent_id: str, writer: Any) -> dict[str, Any]:
        return self.actions.reconcile(ctx, intent_id, writer)


class ConnectorWriter:
    """Adapts a benchmark RESTConnector with a write path to the ActionService ``Writer`` protocol."""

    def __init__(self, connector: Any, lookup_fn: Callable[[str], dict[str, Any] | None]) -> None:
        self.connector, self.lookup_fn = connector, lookup_fn

    def deliver(self, intent: dict[str, Any]) -> dict[str, Any]:
        action = AuthorizedAction(
            action_id=intent["idempotency_key"], tenant_id="", source_system=self.connector.source_system,
            operation=intent["operation"], target_id=intent["target_id"], payload=intent["payload"],
            requested_by="platform", approved_by=tuple(a["actor_id"] for a in intent["approvers"]),
            approved_at=utc_now(), site_id=intent.get("site_id"), approval_ids=tuple(intent["approval_ids"]))
        try:
            ack = self.connector.write(action)
        except HTTPError as exc:
            if exc.code >= 500:
                raise DeliveryUnknown(f"destination error {exc.code}") from exc
            raise
        except (TimeoutError, socket.timeout, URLError) as exc:
            raise DeliveryUnknown(str(exc)) from exc
        return {"source_record_id": ack.source_record_id, "idempotency_key": intent["idempotency_key"]}

    def lookup(self, idempotency_key: str) -> dict[str, Any] | None:
        return self.lookup_fn(idempotency_key)


# --- LS-042: subscriptions --------------------------------------------------------------------------


class SubscriptionService:
    """Tenant-scoped signed webhook subscriptions replayable from any outbox cursor.

    The signing secret is stored with the subscription record and never returned by reads; a production
    deployment should hold it in a secret manager and keep only a reference here.
    """

    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store, self.identity = store, identity

    def register(self, ctx: AccessContext, *, url: str, event_types: Sequence[str], secret: str,
                 site_id: str | None = None) -> dict[str, Any]:
        self.identity.require(ctx, "configure", "subscription", site_id=site_id)
        if not url.startswith(("https://", "http://")) or not event_types or not secret:
            raise ValueError("subscription requires an http(s) url, event types and a secret")
        sid = new_id("sub")
        state = {"subscription_id": sid, "url": url, "event_types": list(event_types), "secret": secret,
                 "site_id": site_id, "status": "active", "created_by": ctx.actor_id, "created_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "subscription", sid, state, expected_revision=None, action="register_subscription")
        return self._public(state)

    @staticmethod
    def _public(state: dict[str, Any]) -> dict[str, Any]:
        return {**{k: v for k, v in state.items() if k != "secret"},
                "secret_fingerprint": hashlib.sha256(state["secret"].encode()).hexdigest()[:12]}

    def get(self, ctx: AccessContext, subscription_id: str) -> dict[str, Any]:
        self.identity.require(ctx, "read", "subscription")
        return self._public(self.store.read().require(ctx.tenant_id, "subscription", subscription_id).state)

    def deliveries(self, ctx: AccessContext, subscription_id: str, since_seq: int = 0, limit: int = 100,
                   timestamp: int | None = None) -> list[dict[str, Any]]:
        self.identity.require(ctx, "read", "subscription")
        sub = self.store.read().require(ctx.tenant_id, "subscription", subscription_id).state
        ts = int(timestamp if timestamp is not None else time.time())
        out = []
        for seq, ev in self.store.events_since(ctx.tenant_id, since_seq, limit=limit):
            if not any(fnmatch.fnmatch(ev.type, pat) for pat in sub["event_types"]):
                continue
            if sub["site_id"] and ev.payload.get("site_id") != sub["site_id"]:
                continue
            body = canonical_json({"seq": seq, "event_id": ev.event_id, "type": ev.type, "occurred_at": ev.occurred_at,
                                   "aggregate": {"kind": ev.aggregate_kind, "id": ev.aggregate_id, "revision": ev.revision},
                                   "payload": ev.payload}).encode()
            out.append({"seq": seq, "url": sub["url"], "body": body, "headers": {
                "X-Timestamp": str(ts), "X-Delivery-Id": ev.event_id, "X-Event-Seq": str(seq),
                "X-Signature": sign_payload(sub["secret"], ts, body)}})
        return out

    def deliver(self, ctx: AccessContext, subscription_id: str, sender: Callable[[str, bytes, dict[str, str]], None],
                limit: int = 100) -> dict[str, Any]:
        """At-least-once push; the cursor advances only past deliveries the sender accepted."""
        cur = self.store.read().get(ctx.tenant_id, "subscription_cursor", subscription_id)
        seq = cur.state["seq"] if cur else 0
        sent, failed_at = 0, None
        for d in self.deliveries(ctx, subscription_id, seq, limit):
            try:
                sender(d["url"], d["body"], d["headers"])
            except Exception:
                failed_at = d["seq"]
                break
            seq, sent = d["seq"], sent + 1
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "subscription_cursor", subscription_id, {"seq": seq},
                   expected_revision=tx.get(ctx.tenant_id, "subscription_cursor", subscription_id).revision if cur else None,
                   action="advance_subscription_cursor")
        return {"delivered": sent, "cursor": seq, "failed_at": failed_at}
