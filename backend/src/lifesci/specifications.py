"""Approved parameter specifications that live data is checked against.

A specification is created by a person holding ``approve`` at its site and is versioned: changing limits
creates a new version, and every signal records the version it was evaluated against. Without a
specification nothing is evaluated: plausibility ranges (CMO vocabulary) are not GMP limits.

Wiring: ``SpecificationService(store, identity)``.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import content_hash, iso, utc_now
from .store import RecordStore

KIND = "specification"
SOURCES = ("procedure", "document", "manual")


def parameter_key(name: str) -> str:
    """'DO [%]', 'do', 'Dissolved oxygen' stay distinct; only case, units and punctuation are ignored."""
    name = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", str(name))
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _limit(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


class SpecificationService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    def create(self, ctx: AccessContext, *, site_id: str, parameter: str, unit: str | None = None,
               low: float | None = None, high: float | None = None, critical_low: float | None = None,
               critical_high: float | None = None, product_id: str | None = None, equipment_id: str | None = None,
               trend_rules: bool = True, source: str = "manual", source_ref: str | None = None,
               reason: str = "") -> dict[str, Any]:
        if ctx.actor_kind != "person" or ctx.delegated_from:
            raise AuthorizationError(Decision(False, "approving a specification requires a person"))
        if not reason.strip():
            raise ValueError("a reason is required to approve a specification")
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}")
        key = parameter_key(parameter)
        if not key:
            raise ValueError("parameter is required")
        lo, hi = _limit(low, "low"), _limit(high, "high")
        clo, chi = _limit(critical_low, "critical_low"), _limit(critical_high, "critical_high")
        if lo is None and hi is None and clo is None and chi is None:
            raise ValueError("a specification needs at least one limit")
        if lo is not None and hi is not None and lo >= hi:
            raise ValueError("low must be below high")
        if clo is not None and lo is not None and clo > lo:
            raise ValueError("critical_low must not be above low")
        if chi is not None and hi is not None and chi < hi:
            raise ValueError("critical_high must not be below high")
        spec_id = "SPEC-" + content_hash([site_id, key, product_id, equipment_id])[:10]
        with self.store.transaction(ctx.actor_id) as tx:
            self.identity.require(ctx, "approve", KIND, spec_id, site_id=site_id, tx=tx)
            current = tx.get(ctx.tenant_id, KIND, spec_id)
            version = (current.state["version"] + 1) if current else 1
            state = {"spec_id": spec_id, "version": version, "site_id": site_id, "parameter": parameter.strip(),
                     "parameter_key": key, "unit": unit, "product_id": product_id, "equipment_id": equipment_id,
                     "low": lo, "high": hi, "critical_low": clo, "critical_high": chi, "trend_rules": bool(trend_rules),
                     "source": source, "source_ref": source_ref, "status": "active", "approved_by": ctx.actor_id,
                     "approved_at": iso(utc_now()), "reason": reason.strip(),
                     "history": [*(current.state.get("history", []) if current else []),
                                 *([{k: current.state[k] for k in ("version", "low", "high", "critical_low", "critical_high",
                                                                    "approved_by", "approved_at")}] if current else [])]}
            rec = tx.put(ctx.tenant_id, KIND, spec_id, state, expected_revision=current.revision if current else None,
                         action="approve_specification", reason=reason.strip())
        return {**rec.state, "revision": rec.revision}

    def list(self, ctx: AccessContext, *, site_id: str | None = None) -> list[dict[str, Any]]:
        out = []
        for rec in self.store.read().list(ctx.tenant_id, KIND):
            if site_id and rec.state["site_id"] != site_id:
                continue
            if self.identity.check(ctx, "read", KIND, rec.id, site_id=rec.state["site_id"]):
                out.append({**rec.state, "revision": rec.revision})
        return sorted(out, key=lambda s: (s["site_id"], s["parameter_key"]))

    def match(self, tenant_id: str, site_id: str | None, parameter: str, *, equipment_id: str | None = None,
              product_id: str | None = None) -> dict[str, Any] | None:
        """The most specific active specification (equipment/product-specific beats general). System read."""
        key = parameter_key(parameter)
        best, score = None, -1
        # ponytail: scans the tenant's specifications; index by (site, parameter_key) when there are thousands.
        for rec in self.store.read().list(tenant_id, KIND):
            s = rec.state
            if s["status"] != "active" or s["parameter_key"] != key or s["site_id"] != site_id:
                continue
            if (s["equipment_id"] and s["equipment_id"] != equipment_id) or (s["product_id"] and s["product_id"] != product_id):
                continue
            rank = bool(s["equipment_id"]) + bool(s["product_id"])
            if rank > score:
                best, score = s, rank
        return best

    @staticmethod
    def evaluate(spec: dict[str, Any], value: float) -> tuple[str, str] | None:
        """(severity, rule text) when ``value`` breaks the specification, else None."""
        unit = f" {spec['unit']}" if spec.get("unit") else ""
        ref = f"(spec {spec['spec_id']} v{spec['version']})"
        name = spec["parameter"]
        if spec.get("critical_low") is not None and value < spec["critical_low"]:
            return "critical", f"{name} {value:g}{unit} < critical low {spec['critical_low']:g}{unit} {ref}"
        if spec.get("critical_high") is not None and value > spec["critical_high"]:
            return "critical", f"{name} {value:g}{unit} > critical high {spec['critical_high']:g}{unit} {ref}"
        if spec.get("low") is not None and value < spec["low"]:
            return "action", f"{name} {value:g}{unit} < low {spec['low']:g}{unit} {ref}"
        if spec.get("high") is not None and value > spec["high"]:
            return "action", f"{name} {value:g}{unit} > high {spec['high']:g}{unit} {ref}"
        return None
