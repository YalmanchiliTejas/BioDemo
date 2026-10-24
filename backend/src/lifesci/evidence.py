"""Versioned evidence, transformation lineage and dependency invalidation.

Original bytes are preserved with their digest and source reference before a
usable evidence revision is published (LS-028). Normalized values keep links to
the original, unit, time basis and transformation version (LS-063). Event time
and recorded/first-seen time are stored separately so availability cutoffs
prevent future leakage.

Dependencies from evidence to findings, fields, recommendations and approvals
are relational edges (D11, D21). A corrected source marks every transitive
dependent stale while unrelated outputs stay current (LS-052, LS-054). Stale
approvals stop authorizing the changed content.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

from .identity import AccessContext, IdentityService
from .ids import content_hash, iso, new_id, utc_now
from .store import RecordStore, Transaction

STATUS_CURRENT = "current"
STATUS_STALE = "stale"
STATUS_QUARANTINED = "quarantined"
STATUS_SUPERSEDED = "superseded"


# Records whose status describes something that already happened must not be overwritten.
_IMMUTABLE_KINDS = frozenset({"approval", "signature", "outcome", "evidence", "audit_export"})
_SENT_INTENT = frozenset({"dispatching", "delivered", "unknown", "failed"})


def invalidated_state(kind: str, state: dict[str, Any], status: str, note: dict[str, Any]) -> dict[str, Any] | None:
    """Return the new state for a dependent of changed evidence, or None to leave it unchanged.

    Already-transmitted operations keep their actual delivery state and are flagged for
    reassessment (a newly arrived event cannot undo a sent operation).
    """
    if kind in _IMMUTABLE_KINDS or state.get("status") in (status, STATUS_SUPERSEDED):
        return None
    reasons = [*state.get("stale_reasons", []), note]
    if kind == "action_intent":
        if state.get("status") == "queued":
            return {**state, "status": "awaiting_reassessment", "stale_reasons": reasons}
        if state.get("status") in _SENT_INTENT:
            return {**state, "needs_reassessment": True, "stale_reasons": reasons}
        return None
    if kind == "proposal" and state.get("execution_status") in _SENT_INTENT:
        return {**state, "needs_reassessment": True, "stale_reasons": reasons}
    if kind == "proposal" and state.get("execution_status") == "queued":
        return {**state, "status": status, "execution_status": "awaiting_reassessment", "stale_reasons": reasons}
    return {**state, "status": status, "stale_reasons": reasons}


@dataclass(frozen=True)
class EvidenceRef:
    kind: str
    id: str
    revision: int
    site_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "revision": self.revision, "site_id": self.site_id}


class EvidenceService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    # --- intake ----------------------------------------------------------------
    def ingest(self, ctx: AccessContext, *, source_system: str, source_record_id: str, content: bytes,
               media_type: str, site_id: str | None, event_time: str | None,
               source_revision: str | None = None, mapping_version: str | None = None,
               metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Idempotent: re-ingesting identical bytes for the same source record returns the existing revision.

        Different bytes for the same source record create a new revision and invalidate dependents.
        """
        evidence_id = f"{source_system}:{source_record_id}"
        with self.store.transaction(ctx.actor_id) as tx:
            self.identity.require(ctx, "read", "evidence", evidence_id, site_id=site_id, tx=tx)
            current = tx.get(ctx.tenant_id, "evidence", evidence_id)
            if current:
                self.identity.require(ctx, "read", "evidence", evidence_id,
                                      site_id=current.state.get("site_id"), tx=tx)
                if current.state.get("site_id") != site_id:
                    raise PermissionError("evidence site cannot be changed by ingestion; use a new source identity")
            digest = tx.put_blob(ctx.tenant_id, content, media_type)
            if current and current.state["digest"] == digest:
                return {**current.state, "revision": current.revision, "duplicate": True}
            state = {
                "evidence_id": evidence_id, "source_system": source_system, "source_record_id": source_record_id,
                "source_revision": source_revision, "digest": digest, "media_type": media_type,
                "size": len(content), "site_id": site_id, "event_time": event_time,
                "recorded_at": iso(utc_now()), "mapping_version": mapping_version,
                "metadata": metadata or {}, "status": STATUS_CURRENT,
                "supersedes_digest": current.state["digest"] if current else None,
            }
            rec = tx.put(ctx.tenant_id, "evidence", evidence_id, state,
                         expected_revision=current.revision if current else None,
                         action="ingest" if not current else "correct",
                         event_type="evidence.ingested" if not current else "evidence.corrected",
                         event_payload={"evidence_id": evidence_id, "digest": digest, "site_id": site_id})
            stale: list[str] = []
            if current:
                stale = self._invalidate(tx, ctx.tenant_id, "evidence", evidence_id,
                                         reason=f"source corrected to {digest[:12]}")
        return {**state, "revision": rec.revision, "duplicate": False, "invalidated": stale}

    def original(self, ctx: AccessContext, evidence_id: str, revision: int | None = None) -> bytes:
        tx = self.store.read()
        rec = tx.revision(ctx.tenant_id, "evidence", evidence_id, revision) if revision else \
            tx.require(ctx.tenant_id, "evidence", evidence_id)
        if rec is None:
            raise KeyError(evidence_id)
        self.identity.require(ctx, "read", "evidence", evidence_id, site_id=rec.state.get("site_id"), tx=tx)
        blob = tx.get_blob(ctx.tenant_id, rec.state["digest"])
        if blob is None:
            raise LookupError(f"original bytes for {evidence_id} missing (staging not committed)")
        return blob

    def available_as_of(self, ctx: AccessContext, as_of: str, site_id: str | None = None) -> list[dict[str, Any]]:
        """Evidence recorded no later than ``as_of``: prevents future data leaking into a time-valid analysis."""
        tx = self.store.read()
        out = []
        for rec in tx.list(ctx.tenant_id, "evidence"):
            s = rec.state
            if site_id and s.get("site_id") != site_id:
                continue
            if s["recorded_at"] <= as_of and self.identity.check(ctx, "read", "evidence", rec.id,
                                                                 site_id=s.get("site_id"), tx=tx):
                out.append({**s, "revision": rec.revision})
        return out

    # --- normalized values -------------------------------------------------------
    def normalize(self, ctx: AccessContext, *, evidence: EvidenceRef, field: str, raw_value: Any, raw_unit: str | None,
                  value: float | str, unit: str | None, time_basis: str, transform: str,
                  transform_version: str, location: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record a normalized value with full lineage to original, unit, time basis and transformation version."""
        derived_id = new_id("val")
        state = {"evidence": evidence.to_dict(), "field": field, "raw_value": raw_value, "raw_unit": raw_unit,
                 "value": value, "unit": unit, "time_basis": time_basis, "transform": transform,
                 "transform_version": transform_version, "location": location or {}, "status": STATUS_CURRENT}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "normalized_value", derived_id, state, expected_revision=None, action="normalize")
            self._link(tx, ctx.tenant_id, ("evidence", evidence.id), ("normalized_value", derived_id), "derived_from")
        return {"id": derived_id, **state}

    # --- derived artifacts & dependency graph ---------------------------------------
    def record_derived(self, ctx: AccessContext, kind: str, payload: dict[str, Any], *,
                       inputs: Iterable[EvidenceRef], produced_by: dict[str, Any],
                       artifact_id: str | None = None, status: str = STATUS_CURRENT) -> dict[str, Any]:
        """Persist a derived output (finding, field, recommendation, summary...) with its input manifest.

        The artifact inherits the access restrictions of all inputs (LS-085).
        """
        refs = [i.to_dict() for i in inputs]
        decision = self.identity.check_derived(ctx, refs)
        if not decision:
            raise PermissionError(decision.reason)
        artifact_id = artifact_id or new_id(kind[:4])
        state = {**payload, "inputs": refs, "produced_by": produced_by, "status": status,
                 "basis_hash": content_hash(refs), "stale_reasons": []}
        with self.store.transaction(ctx.actor_id) as tx:
            current = tx.get(ctx.tenant_id, kind, artifact_id)
            tx.put(ctx.tenant_id, kind, artifact_id, state, expected_revision=current.revision if current else None,
                   action="derive", event_type=f"{kind}.derived", event_payload={"id": artifact_id})
            for ref in refs:
                self._link(tx, ctx.tenant_id, (ref["kind"], ref["id"]), (kind, artifact_id), "input_of")
        return {"id": artifact_id, **state}

    def link(self, ctx: AccessContext, upstream: tuple[str, str], downstream: tuple[str, str],
             relation: str = "depends_on") -> None:
        with self.store.transaction(ctx.actor_id) as tx:
            self._link(tx, ctx.tenant_id, upstream, downstream, relation)

    def read_derived(self, ctx: AccessContext, kind: str, artifact_id: str) -> dict[str, Any]:
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, kind, artifact_id)
        if rec.state.get("status") == STATUS_QUARANTINED:
            raise PermissionError(f"{kind}:{artifact_id} quarantined: a contributing source was revoked")
        self.identity.validate_refs(ctx, rec.state.get("inputs", []), tx=tx, require_current=False)
        return {"id": artifact_id, "revision": rec.revision, **rec.state}

    def dependents(self, tenant_id: str, kind: str, id: str, tx: Transaction | None = None) -> list[tuple[str, str]]:
        tx = tx or self.store.read()
        return [(k, i) for k, i, _ in tx.edges_from(tenant_id, kind, id)]

    def invalidate(self, ctx: AccessContext, kind: str, id: str, reason: str) -> list[str]:
        with self.store.transaction(ctx.actor_id) as tx:
            return self._invalidate(tx, ctx.tenant_id, kind, id, reason)

    def quarantine_from(self, ctx: AccessContext, kind: str, id: str, reason: str) -> list[str]:
        """Quarantine every derived output reachable from a revoked or withdrawn source."""
        with self.store.transaction(ctx.actor_id) as tx:
            return self._invalidate(tx, ctx.tenant_id, kind, id, reason, status=STATUS_QUARANTINED)

    # --- internals ---------------------------------------------------------------
    def _link(self, tx: Transaction, tenant_id: str, up: tuple[str, str], down: tuple[str, str], relation: str) -> None:
        tx.add_edge(tenant_id, up, down, relation)

    def _invalidate(self, tx: Transaction, tenant_id: str, kind: str, id: str, reason: str,
                    status: str = STATUS_STALE) -> list[str]:
        seen: set[tuple[str, str]] = set()
        queue = deque(self.dependents(tenant_id, kind, id, tx))
        changed: list[str] = []
        while queue:
            node = queue.popleft()
            if node in seen:
                continue
            seen.add(node)
            rec = tx.get(tenant_id, *node)
            if rec is not None:
                note = {"source": f"{kind}:{id}", "reason": reason, "at": iso(utc_now())}
                new_state = invalidated_state(node[0], rec.state, status, note)
                if new_state is not None:
                    tx.put(tenant_id, node[0], node[1], new_state, expected_revision=rec.revision,
                           action=f"mark_{status}", reason=reason, event_type=f"dependency.{status}",
                           event_payload={"kind": node[0], "id": node[1], "cause": f"{kind}:{id}",
                                          "new_status": new_state.get("status")})
                    changed.append(f"{node[0]}:{node[1]}")
            queue.extend(self.dependents(tenant_id, node[0], node[1], tx))
        return changed
