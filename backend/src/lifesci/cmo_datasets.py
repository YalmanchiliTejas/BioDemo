"""Verified CMO deliveries as platform evidence.

The delivery-verification service (``manufacturing_data.cmo``) runs inside this API. A delivery
that passed every verification check can be published as one immutable evidence record, so the
engineering assistant and other platform services cite the same accepted values, sources and
hashes the reviewer saw. Unverified deliveries are never published.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from statistics import fmean, median
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

SOURCE_SYSTEM = "cmo-verified-delivery"
CLASSIFICATION = "verified_cmo_dataset"
DOCUMENT_SOURCE = "cmo-delivery-document"
DOCUMENT_CLASSIFICATION = "unverified_cmo_document"
_FIELDS = ("id", "source_id", "batch", "time", "parameter", "value", "unit", "value_raw", "unit_raw", "status",
           "source", "source_sha256")
log = logging.getLogger(__name__)


class PublishIn(BaseModel):
    run_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    site_id: str = Field(default="NF1", min_length=1, max_length=100)


def _hours(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dataset_content(payload: dict[str, Any]) -> bytes:
    """Deterministic bytes, so republishing an unchanged delivery is idempotent."""
    body = {
        "schema_version": "platform-verified-cmo-1",
        "run_id": payload["run_id"], "cmo": payload["cmo"], "package_id": payload.get("package_id"),
        "delivery_name": payload.get("delivery_name"), "completed_at": payload.get("completed_at"),
        "disclosure": payload.get("disclosure"), "coverage": payload.get("coverage"),
        "guarantee": {"holds": payload["guarantee"]["holds"],
                      "checks": [{k: c.get(k) for k in ("id", "label", "passed")} for c in payload["guarantee"]["checks"]]},
        "measurements": sorted(({k: m.get(k) for k in _FIELDS} for m in payload["measurements"]),
                               key=lambda m: (str(m["batch"]), _hours(m["time"]) or 0.0, str(m["parameter"]), str(m["id"]))),
    }
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _source_label(source: dict[str, Any] | None) -> str:
    source = source or {}
    if source.get("sheet") and source.get("cell"):
        return f"{source['path']} · {source['sheet']}!{source['cell']}"
    if source.get("row"):
        return f"{source['path']} · row {source['row']}" + (f" · {source['column']}" if source.get("column") else "")
    if source.get("page"):
        return f"{source['path']} · page {source['page']}"
    return str(source.get("path", ""))


def standouts(per_batch: dict[str, dict[str, list[dict[str, Any]]]], *, top: int = 3) -> dict[str, Any]:
    """Where runs differ most, calculated from measured values at measured times only (nothing is interpolated).

    Per parameter: the largest changes between consecutive samples of one run, with the typical change for scale,
    and the largest differences from the other runs sampled at exactly the same time (three or more runs).
    A reader should not have to work these out from the series by hand, and should not get them wrong."""
    by_parameter: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for batch, params in per_batch.items():
        for name, items in params.items():
            points = sorted((t, m["value"]) for m in items if (t := _hours(m["time"])) is not None
                            and isinstance(m["value"], (int, float)) and not isinstance(m["value"], bool))
            if points:
                by_parameter.setdefault(name, {})[batch] = points
    out: dict[str, Any] = {}
    for name, runs in sorted(by_parameter.items()):
        steps = [{"batch": b, "from_h": t0, "to_h": t1, "from": v0, "to": v1, "change": round(v1 - v0, 6)}
                 for b, pts in runs.items() for (t0, v0), (t1, v1) in zip(pts, pts[1:]) if t1 > t0]
        at_time: dict[float, dict[str, float]] = {}
        for b, pts in runs.items():
            for t, v in pts:
                at_time.setdefault(t, {})[b] = v
        apart = []
        for t, values in at_time.items():
            if len(values) < 3:
                continue  # with two runs there is a difference but no "others" to stand out from
            for b, v in values.items():
                rest = median(x for k, x in values.items() if k != b)
                apart.append({"time_h": t, "batch": b, "value": v, "median_of_other_runs": round(rest, 6),
                              "difference": round(v - rest, 6), "runs_at_this_time": len(values)})
        entry: dict[str, Any] = {}
        if steps:
            entry["largest_changes_between_consecutive_samples"] = sorted(steps, key=lambda s: -abs(s["change"]))[:top]
            entry["typical_change_between_samples"] = round(median(abs(s["change"]) for s in steps), 6)
        if apart:
            entry["largest_same_time_differences"] = sorted(apart, key=lambda a: -abs(a["difference"]))[:2]
        if entry:
            out[name] = entry
    return out


SERIES_MAX = 3000  # ponytail: beyond this, page the raw rows; a per-run downsample would be the upgrade


def summarize(data: dict[str, Any], *, sample_rows: int = 40, series: bool = False) -> dict[str, Any]:
    """A bounded, model-readable view of the dataset. Full values stay in the evidence record."""
    rows = data["measurements"]
    by_param: dict[str, list[dict[str, Any]]] = {}
    for m in rows:
        by_param.setdefault(m["parameter"], []).append(m)
    parameters, per_batch = [], {}
    for name, items in sorted(by_param.items()):
        values = [m["value"] for m in items if isinstance(m["value"], (int, float))]
        times = [t for t in (_hours(m["time"]) for m in items) if t is not None]
        parameters.append({"parameter": name, "unit": items[0]["unit"], "values": len(items),
                           "batches": len({m["batch"] for m in items}),
                           "min": min(values) if values else None, "max": max(values) if values else None,
                           "mean": round(fmean(values), 6) if values else None,
                           "time_range_h": [min(times), max(times)] if times else None})
        for m in items:
            per_batch.setdefault(m["batch"], {}).setdefault(name, []).append(m)
    batches = {}
    for batch, params in sorted(per_batch.items()):
        batches[batch] = {}
        for name, items in params.items():
            ordered = sorted(items, key=lambda m: _hours(m["time"]) or 0.0)
            values = [m["value"] for m in ordered if isinstance(m["value"], (int, float))]
            batches[batch][name] = {"n": len(ordered),
                                    "first": {"time_h": _hours(ordered[0]["time"]), "value": ordered[0]["value"]},
                                    "last": {"time_h": _hours(ordered[-1]["time"]), "value": ordered[-1]["value"]},
                                    # Measured extremes with when they occurred: compare runs on these, never on guesses.
                                    "min": min(values) if values else None, "max": max(values) if values else None,
                                    "min_at_h": _hours(min(ordered, key=lambda m: m["value"])["time"]) if values else None,
                                    "max_at_h": _hours(max(ordered, key=lambda m: m["value"])["time"]) if values else None}
    extra: dict[str, Any] = {}
    if series and len(rows) <= SERIES_MAX:
        # Every value as [time_h, value] per run and parameter: answers "when did it diverge" without paging raw rows.
        # First, so it is never the part cut off when a long result is shortened for the model.
        extra["standouts"] = {"basis": "calculated from the series at measured times; not an interpretation",
                              **standouts(per_batch)}
        extra["series"] = {b: {name: [[_hours(m["time"]), m["value"]] for m in sorted(items, key=lambda m: _hours(m["time"]) or 0.0)]
                               for name, items in params.items()} for b, params in sorted(per_batch.items())}
        extra["series_units"] = {p["parameter"]: p["unit"] for p in parameters}
        sample_rows = min(sample_rows, 5)  # the series carries the values; a few rows show source citations
    return {
        **extra,
        "measurement_count": len(rows), "batches": sorted(per_batch), "parameters": parameters, "per_batch": batches,
        "coverage": data.get("coverage"), "guarantee_holds": data["guarantee"]["holds"],
        "guarantee_checks": [{k: c.get(k) for k in ("label", "passed")} for c in data["guarantee"].get("checks", [])],
        "example_rows": [{"batch": m["batch"], "time_h": _hours(m["time"]), "parameter": m["parameter"],
                          "value": m["value"], "unit": m["unit"], "source": _source_label(m.get("source"))}
                         for m in rows[:sample_rows]],
    }


def _record(p, ctx, evidence_id: str, site_id: str | None = None):
    rec = p.store.read().get(ctx.tenant_id, "evidence", evidence_id)
    if rec is None or rec.state.get("metadata", {}).get("classification") != CLASSIFICATION:
        raise ValueError("unknown verified delivery dataset")
    p.identity.require(ctx, "read", "evidence", evidence_id, site_id=rec.state.get("site_id"))
    if site_id is not None and rec.state.get("site_id") != site_id:
        raise PermissionError("verified dataset belongs to another site")
    return rec


def require_dataset(p, ctx, evidence_id: str, site_id: str):
    rec = _record(p, ctx, evidence_id, site_id)
    if rec.state.get("status") != "current":
        raise ValueError("verified dataset was superseded or withdrawn; publish the current delivery again")
    basis = rec.state.get('metadata', {}).get('verification_basis', [])
    if basis:
        p.identity.validate_refs(ctx, basis, require_current=True)
    return rec


def listing(rec) -> dict[str, Any]:
    meta = rec.state["metadata"]
    return {"id": rec.id, "revision": rec.revision, "status": rec.state["status"], "site_id": rec.state["site_id"],
            "run_id": rec.state["source_record_id"], "cmo": meta.get("cmo"), "delivery_name": meta.get("delivery_name"),
            "measurements": meta.get("measurements"), "batches": meta.get("batches"), "parameters": meta.get("parameters"),
            "published_at": rec.state["recorded_at"]}


def conversation_source(p, ctx, evidence_id: str, site_id: str) -> tuple[dict[str, Any], Any]:
    """Authorized source entry for the assistant prompt, plus the evidence reference it rests on."""
    from .evidence import EvidenceRef
    try:
        rec = require_dataset(p, ctx, evidence_id, site_id)
    except (PermissionError, ValueError) as exc:
        return {"id": evidence_id, "kind": CLASSIFICATION, "status": "unavailable_or_invalidated", "note": str(exc)}, None
    data = json.loads(p.evidence.original(ctx, evidence_id, rec.revision))
    entry = {"id": evidence_id, "kind": CLASSIFICATION, "status": "verified", "evidence_revision": rec.revision,
             "cmo": data["cmo"], "delivery_name": data.get("delivery_name"), "run_id": data["run_id"],
             "disclosure": data.get("disclosure"), **summarize(data)}
    return entry, EvidenceRef("evidence", evidence_id, rec.revision, rec.state["site_id"])


def install_cmo_api(p, app: FastAPI, ctx_dep) -> None:
    """Mount delivery verification in this API and expose verified deliveries as evidence."""
    cmo = None
    try:
        from ..manufacturing_data.cmo.api import router as cmo_router
    except ImportError as exc:  # live verified datasets remain available without file-parser extras
        log.warning("CMO delivery verification unavailable: %s", exc)
    else:
        repository = Path(os.environ.get("CMO_REPOSITORY_ROOT", Path(__file__).resolve().parents[2]))
        cmo = cmo_router(repository, tenant_dependency=ctx_dep, tasks=app.state.tasks,
                         permission_check=lambda ctx, action: p.identity.require(ctx, action, "cmo_delivery"))
        app.include_router(cmo)

    @app.post("/v1/cmo-datasets", status_code=201)
    def publish(body: PublishIn, ctx=Depends(ctx_dep)):
        if cmo is None:
            raise HTTPException(503, "File-delivery verification is not installed on this server")
        payload = cmo.verified_payload(body.run_id, tenant=ctx.tenant_id)
        if payload.get("superseded_by"):
            raise HTTPException(409, "A newer check of this delivery exists; publish the current run")
        meta = {"classification": CLASSIFICATION, "cmo": payload["cmo"], "delivery_name": payload.get("delivery_name"),
                "package_id": payload.get("package_id"), "measurements": len(payload["measurements"]),
                "batches": sorted({m["batch"] for m in payload["measurements"]}),
                "parameters": sorted({m["parameter"] for m in payload["measurements"]})}
        ev = p.evidence.ingest(ctx, source_system=SOURCE_SYSTEM, source_record_id=body.run_id,
                               content=dataset_content(payload), media_type="application/json", site_id=body.site_id,
                               event_time=payload.get("completed_at"), source_revision=body.run_id,
                               mapping_version="verified-cmo-1", metadata=meta)
        signals = getattr(p, "signals", None)
        if signals is not None:
            try:  # verified CMO values against approved specifications; a detection failure never blocks publication
                signals.check_delivery_measurements(ctx.tenant_id, site_id=body.site_id, measurements=[
                    {"parameter": m["parameter"], "value": m.get("value"), "unit": m.get("unit"), "batch_id": m.get("batch")}
                    for m in payload["measurements"]],
                    delivery_ref={"kind": "evidence", "id": ev["evidence_id"], "revision": ev["revision"], "site_id": body.site_id})
            except Exception:
                log.exception("Specification check of delivery %s failed", body.run_id)
        return listing(p.store.read().require(ctx.tenant_id, "evidence", ev["evidence_id"]))

    @app.post("/v1/cmo-documents", status_code=201)
    def share_documents(body: PublishIn, ctx=Depends(ctx_dep)):
        """Share a delivery's emails, notes and reports with the assistant, at a reviewer's request.

        Each becomes evidence labelled as unverified correspondence: what the CMO wrote, not a checked value.
        Re-sharing identical text is idempotent; changed text becomes a new revision.
        """
        if cmo is None:
            raise HTTPException(503, "File-delivery verification is not installed on this server")
        found = cmo.delivery_documents(body.run_id, tenant=ctx.tenant_id)
        shared = []
        for doc in found["documents"]:
            label = (f"UNVERIFIED CMO DOCUMENT as received from {found['cmo']} in delivery "
                     f"\"{found['delivery_name']}\", file {doc['path']}. Not checked against verified measurements.\n\n")
            ev = p.evidence.ingest(ctx, source_system=DOCUMENT_SOURCE, source_record_id=f"{found['package_id']}/{doc['path']}",
                                   content=(label + doc["text"]).encode(), media_type="text/plain", site_id=body.site_id,
                                   event_time=None, source_revision=doc["sha256"], mapping_version="cmo-document-1",
                                   metadata={"classification": DOCUMENT_CLASSIFICATION, "cmo": found["cmo"],
                                             "delivery_name": found["delivery_name"], "package_id": found["package_id"],
                                             "path": doc["path"], "original_sha256": doc["sha256"]})
            shared.append({"evidence_id": ev["evidence_id"], "path": doc["path"]})
        return {"package_id": found["package_id"], "shared": shared}

    @app.get("/v1/cmo-documents")
    def shared_documents(package_id: str, site_id: str = "NF1", ctx=Depends(ctx_dep)):
        out = [{"evidence_id": rec.id, "path": rec.state["metadata"].get("path"), "revision": rec.revision}
               for rec in p.store.read().list(ctx.tenant_id, "evidence")
               if rec.state.get("metadata", {}).get("package_id") == package_id and rec.state.get("site_id") == site_id
               and rec.state.get("metadata", {}).get("classification") == DOCUMENT_CLASSIFICATION
               and p.identity.check(ctx, "read", "evidence", rec.id, site_id=site_id)]
        return {"documents": sorted(out, key=lambda d: d["path"] or "")}

    @app.get("/v1/cmo-datasets")
    def datasets(site_id: str = "NF1", ctx=Depends(ctx_dep)):
        out = []
        for rec in p.store.read().list(ctx.tenant_id, "evidence"):
            if rec.state.get("metadata", {}).get("classification") != CLASSIFICATION or rec.state.get("site_id") != site_id:
                continue
            if rec.state.get("status") == "current" and p.identity.check(ctx, "read", "evidence", rec.id, site_id=site_id):
                item = listing(rec)
                try:
                    require_dataset(p, ctx, rec.id, site_id)
                except (ValueError, PermissionError):
                    item['status'] = 'stale_basis'
                out.append(item)
        return {"datasets": sorted(out, key=lambda d: d["published_at"], reverse=True)}

    @app.get("/v1/cmo-datasets/{evidence_id}")
    def dataset(evidence_id: str, ctx=Depends(ctx_dep)):
        try:
            rec = require_dataset(p, ctx, evidence_id, _record(p, ctx, evidence_id).state['site_id'])
        except ValueError as exc:
            raise HTTPException(409, 'Dataset basis changed; review and publish a current snapshot') from exc
        data = json.loads(p.evidence.original(ctx, evidence_id, rec.revision))
        return {**listing(rec), "summary": summarize(data, sample_rows=10)}
