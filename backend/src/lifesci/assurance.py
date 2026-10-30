"""Records assurance and operations (LS-002, LS-046, LS-048, LS-049, LS-080, LS-082).

- Scoped export of every record revision, audit entry and referenced original,
  with a manifest of hashes and an HMAC signature; verified restoration into an
  empty store. Exported revisions remain readable and attributable.
- Retention policies and legal holds block premature purge.
- Qualification trace: intended-use requirements -> test cases -> executed
  results (JUnit XML), with explicit coverage gaps. This is supporting evidence
  for a customer's qualification, not a compliance claim.
- Deployment plans and controlled release notices as versioned records.
- Degraded-mode health: which capabilities continue with models unavailable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

from .identity import AccessContext, IdentityService
from .ids import canonical_json, content_hash, iso, new_id, parse_iso, utc_now
from .store import RecordStore

EXPORT_FORMAT = "biodemo-lifesci-export/1"


class AssuranceService:
    def __init__(self, store: RecordStore, identity: IdentityService) -> None:
        self.store = store
        self.identity = identity

    # --- export / restore -------------------------------------------------------------
    def export(self, ctx: AccessContext, *, kinds: Iterable[str] | None = None, site_id: str | None = None,
               signing_key: bytes) -> dict[str, Any]:
        self.identity.require(ctx, "export", "tenant_export", ctx.tenant_id, site_id=site_id)
        db = self.store._db
        rows = db.fetchall(
            "SELECT kind, id, revision, state, content_hash, recorded_at FROM aggregate_revisions WHERE tenant_id=? "
            "ORDER BY kind, id, revision", (ctx.tenant_id,))
        wanted = set(kinds) if kinds else None
        revisions, digests = [], set()
        for kind, rid, rev, state, digest, recorded in rows:
            if wanted and kind not in wanted:
                continue
            parsed = json.loads(state)
            if site_id and parsed.get("site_id") not in (None, site_id):
                continue
            if content_hash(parsed) != digest:
                raise ValueError(f"stored revision {kind}:{rid}@{rev} fails its content hash")
            revisions.append({"kind": kind, "id": rid, "revision": int(rev), "state": parsed,
                              "content_hash": digest, "recorded_at": recorded})
            if kind == "evidence" and parsed.get("digest"):
                digests.add(parsed["digest"])
            if kind == "mission":
                digests |= {h["digest"] for h in parsed.get("history_refs", [])}
                if parsed.get("checkpoint"):
                    digests.add(parsed["checkpoint"]["digest"])
        exported_ids = {(r["kind"], r["id"]) for r in revisions}
        audit = [dict(zip(("seq", "actor_id", "action", "aggregate_kind", "aggregate_id", "revision", "before_hash",
                           "after_hash", "reason", "occurred_at", "details", "prev_hash"), r))
                 for r in db.fetchall("SELECT seq, actor_id, action, aggregate_kind, aggregate_id, revision, "
                                      "before_hash, after_hash, reason, occurred_at, details, prev_hash FROM audit "
                                      "WHERE tenant_id=? ORDER BY seq", (ctx.tenant_id,))
                 if (r[3], r[4]) in exported_ids]
        tx = self.store.read()
        blobs = {}
        for d in sorted(digests):
            content = tx.get_blob(ctx.tenant_id, d)
            if content is not None:
                blobs[d] = base64.b64encode(content).decode()
        body = {"format": EXPORT_FORMAT, "tenant_id": ctx.tenant_id, "exported_by": ctx.actor_id,
                "exported_at": iso(utc_now()), "scope": {"kinds": sorted(wanted) if wanted else "all", "site_id": site_id},
                "revisions": revisions, "audit": audit, "blobs": blobs}
        manifest = {"revisions": len(revisions), "audit": len(audit), "blobs": len(blobs),
                    "body_sha256": content_hash(body)}
        signature = hmac.new(signing_key, canonical_json(manifest).encode(), hashlib.sha256).hexdigest()
        with self.store.transaction(ctx.actor_id) as wtx:
            wtx.put(ctx.tenant_id, "audit_export", new_id("exp"), {**manifest, "scope": body["scope"],
                                                                  "signature": signature},
                    expected_revision=None, action="export", event_type="assurance.exported",
                    event_payload=manifest)
        return {"body": body, "manifest": manifest, "signature": signature}

    @staticmethod
    def verify_export(bundle: dict[str, Any], signing_key: bytes) -> list[str]:
        problems = []
        expected = hmac.new(signing_key, canonical_json(bundle["manifest"]).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, bundle["signature"]):
            problems.append("manifest signature mismatch")
        if content_hash(bundle["body"]) != bundle["manifest"]["body_sha256"]:
            problems.append("export body altered")
        for r in bundle["body"]["revisions"]:
            if content_hash(r["state"]) != r["content_hash"]:
                problems.append(f"revision {r['kind']}:{r['id']}@{r['revision']} altered")
        for d, b in bundle["body"]["blobs"].items():
            if content_hash(base64.b64decode(b)) != d:
                problems.append(f"original {d[:12]} altered")
        return problems

    @staticmethod
    def restore(bundle: dict[str, Any], target: RecordStore, signing_key: bytes) -> dict[str, int]:
        """Restore into a store with no records for the tenant; every revision is replayed in order."""
        problems = AssuranceService.verify_export(bundle, signing_key)
        if problems:
            raise ValueError("; ".join(problems))
        body = bundle["body"]
        tenant = body["tenant_id"]
        db = target._db
        if db.fetchone("SELECT 1 FROM aggregates WHERE tenant_id=? LIMIT 1", (tenant,)):
            raise ValueError("restore target already holds records for this tenant")
        with target.transaction("restore") as tx:
            for d, b in body["blobs"].items():
                tx.put_blob(tenant, base64.b64decode(b))
            latest: dict[tuple[str, str], dict[str, Any]] = {}
            for r in body["revisions"]:
                db.execute("INSERT INTO aggregate_revisions (tenant_id, kind, id, revision, state, content_hash, recorded_at) "
                           "VALUES (?,?,?,?,?,?,?)", (tenant, r["kind"], r["id"], r["revision"],
                                                      canonical_json(r["state"]), r["content_hash"], r["recorded_at"]))
                latest[(r["kind"], r["id"])] = r
            for (kind, rid), r in latest.items():
                db.execute("INSERT INTO aggregates (tenant_id, kind, id, revision) VALUES (?,?,?,?)",
                           (tenant, kind, rid, r["revision"]))
            for a in body["audit"]:
                db.execute("INSERT INTO audit (tenant_id, actor_id, action, aggregate_kind, aggregate_id, revision, "
                           "before_hash, after_hash, reason, occurred_at, details, prev_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           (tenant, a["actor_id"], a["action"], a["aggregate_kind"], a["aggregate_id"], a["revision"],
                            a["before_hash"], a["after_hash"], a["reason"], a["occurred_at"], a["details"],
                            a.get("prev_hash")))
        return {"revisions": len(body["revisions"]), "records": len(latest), "audit": len(body["audit"]),
                "blobs": len(body["blobs"])}

    # --- retention -----------------------------------------------------------------
    def set_retention(self, ctx: AccessContext, kind: str, *, min_days: int, reason: str) -> None:
        self.identity.require(ctx, "configure", "retention_policy")
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "retention_policy", kind)
            tx.put(ctx.tenant_id, "retention_policy", kind, {"kind": kind, "min_days": min_days},
                   expected_revision=cur.revision if cur else None, action="set_retention", reason=reason)

    def legal_hold(self, ctx: AccessContext, kind: str, record_id: str, *, reason: str, active: bool = True) -> None:
        self.identity.require(ctx, "configure", "legal_hold")
        hid = f"{kind}:{record_id}"
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "legal_hold", hid)
            tx.put(ctx.tenant_id, "legal_hold", hid, {"kind": kind, "record_id": record_id, "active": active},
                   expected_revision=cur.revision if cur else None, action="legal_hold", reason=reason)

    def purge_allowed(self, tenant_id: str, kind: str, record_id: str) -> tuple[bool, str]:
        tx = self.store.read()
        hold = tx.get(tenant_id, "legal_hold", f"{kind}:{record_id}")
        if hold and hold.state["active"]:
            return False, "legal hold active"
        policy = tx.get(tenant_id, "retention_policy", kind)
        rec = tx.get(tenant_id, kind, record_id)
        if rec is None:
            return False, "record not found"
        first = tx.revision(tenant_id, kind, record_id, 1)
        created = parse_iso(first.updated_at if first else rec.updated_at)
        if policy is None:
            return False, "no retention policy configured; purge denied by default"
        if utc_now() - created < timedelta(days=policy.state["min_days"]):
            return False, f"within {policy.state['min_days']}-day retention"
        return True, "retention elapsed"

    # --- qualification trace -----------------------------------------------------------
    def define_requirement(self, ctx: AccessContext, req_id: str, *, text: str, risk: str,
                           tests: list[str], intended_use: str) -> None:
        self.identity.require(ctx, "configure", "requirement")
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "requirement", req_id)
            tx.put(ctx.tenant_id, "requirement", req_id,
                   {"req_id": req_id, "text": text, "risk": risk, "tests": tests, "intended_use": intended_use},
                   expected_revision=cur.revision if cur else None, action="define_requirement")

    def record_test_run(self, ctx: AccessContext, junit_xml: str, *, build: str, environment: dict[str, Any]) -> str:
        root = ET.fromstring(junit_xml)
        results = {}
        for case in root.iter("testcase"):
            name = case.get("name", "")
            status = "passed"
            if case.find("failure") is not None or case.find("error") is not None:
                status = "failed"
            elif case.find("skipped") is not None:
                status = "skipped"
            results[name] = status
        run_id = new_id("trun")
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "test_run", run_id, {"build": build, "environment": environment,
                                                       "results": results, "recorded_at": iso(utc_now()),
                                                       "source_sha256": content_hash(junit_xml.encode())},
                   expected_revision=None, action="record_test_run")
        return run_id

    def qualification_trace(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        tx = self.store.read()
        results = tx.require(tenant_id, "test_run", run_id).state["results"]
        rows, gaps = [], []
        for rec in tx.list(tenant_id, "requirement"):
            r = rec.state
            statuses = {t: results.get(t, "not_executed") for t in r["tests"]}
            ok = bool(statuses) and all(v == "passed" for v in statuses.values())
            rows.append({"req_id": r["req_id"], "risk": r["risk"], "tests": statuses,
                         "status": "evidenced" if ok else "gap"})
            if not ok:
                gaps.append(r["req_id"])
        return {"run_id": run_id, "requirements": rows, "gaps": gaps,
                "note": "Supports customer qualification; not itself a qualification or compliance claim."}

    # --- deployment and releases ------------------------------------------------------------
    def deployment_plan(self, ctx: AccessContext, *, site_id: str, process_scope: str, owners: dict[str, str],
                        training: list[dict[str, Any]], qualification_refs: list[str]) -> dict[str, Any]:
        required_owners = {"site_lead", "qa_owner", "it_owner", "process_owner"}
        missing = sorted(required_owners - {k for k, v in owners.items() if v})
        untrained = [t["role"] for t in training if not t.get("completed")]
        plan = {"site_id": site_id, "process_scope": process_scope, "owners": owners, "training": training,
                "qualification_refs": qualification_refs, "missing_owners": missing, "untrained_roles": untrained,
                "ready": not missing and not untrained and bool(qualification_refs)}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "deployment_plan", f"{site_id}:{process_scope}", plan, expected_revision=None,
                   action="deployment_plan")
        return plan

    def release_notice(self, ctx: AccessContext, *, version: str, changes: list[str], impact: dict[str, Any],
                       affected_task_kinds: list[str], effective_at: str) -> dict[str, Any]:
        """Controlled release notice; changes to model/prompt/tool routes must name re-evaluation needs."""
        if affected_task_kinds and not impact.get("evaluations"):
            raise ValueError("release affecting model task kinds must reference evaluations")
        notice = {"version": version, "changes": changes, "impact": impact, "affected_task_kinds": affected_task_kinds,
                  "effective_at": effective_at, "published_by": ctx.actor_id}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "release_notice", version, notice, expected_revision=None, action="release_notice",
                   event_type="assurance.release_notice", event_payload={"version": version})
        return notice

    def incident(self, ctx: AccessContext, *, title: str, severity: str, affected: list[str]) -> str:
        iid = new_id("inc")
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "incident", iid, {"title": title, "severity": severity, "affected": affected,
                                                    "status": "open", "timeline": [{"at": iso(utc_now()), "event": "opened"}]},
                   expected_revision=None, action="incident_open", event_type="assurance.incident",
                   event_payload={"incident_id": iid, "severity": severity})
        return iid

    def resolve_incident(self, ctx: AccessContext, incident_id: str, *, resolution: str) -> None:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "incident", incident_id)
            tx.put(ctx.tenant_id, "incident", incident_id,
                   {**rec.state, "status": "resolved", "resolution": resolution,
                    "timeline": [*rec.state["timeline"], {"at": iso(utc_now()), "event": "resolved"}]},
                   expected_revision=rec.revision, action="incident_resolve")


@dataclass(frozen=True)
class DegradedModeReport:
    models_available: bool
    continuing: tuple[str, ...]
    blocked: tuple[str, ...]


def degraded_mode(gateway: Any) -> DegradedModeReport:
    """Capabilities that continue when every model provider is unavailable (LS-080)."""
    profiles = set(gateway.registry.profiles)
    available = bool(profiles - gateway.unavailable) and bool(gateway.providers)
    continuing = ("authorization", "record_retrieval", "deterministic_calculations", "signatures",
                  "approvals", "required_notifications", "export")
    blocked = () if available else tuple(sorted(k for k, p in gateway.registry.policies.items() if not p.deterministic))
    return DegradedModeReport(available, continuing, blocked)
