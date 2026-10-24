"""Persistent manufacturing missions (ADR 0003; LS-051, LS-052, LS-053, LS-058, LS-069, LS-084, LS-021).

A mission owns objective, owner, scope, constraints, subscriptions, obligations,
pending decisions, corrections, rejected hypotheses, budget and an event
cursor. Model sessions and workers can end without ending the mission.

Concurrency: one coordinator activation per mission at a time, enforced with a
lease and a monotonic fencing token. Checkpoints are written under immutable
attempt keys and promoted through a fenced, revision-checked commit, so an
obsolete worker can never replace a newer resume pointer. Child findings merge
only against their explicit basis versions.

Wakeups are coalesced without dropping event ids. Context assembly is bounded
by a token budget but never drops corrections, constraints, obligations or
pending decisions; full history stays recoverable by reference.

The scheduler is behind a port (``MissionScheduler``). ``InProcessScheduler``
serves development and tests; production uses a durable orchestrator (D09)
through the same port.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol

from .identity import AccessContext, IdentityService
from .ids import canonical_json, content_hash, iso, new_id, parse_iso, utc_now
from .store import ConflictError, LeaseError, RecordStore, Transaction

ACTIVE, PAUSED_BUDGET, BLOCKED, CANCELLED, ARCHIVED = "active", "paused_budget", "blocked", "cancelled", "archived"
KIND = "mission"


@dataclass(frozen=True)
class Activation:
    mission_id: str
    tenant_id: str
    worker_id: str
    token: int
    mission_revision: int
    pending_event_ids: tuple[str, ...]
    attempt: int


class MissionScheduler(Protocol):
    def schedule_wakeup(self, tenant_id: str, mission_id: str, reason: str) -> None: ...
    def schedule_timer(self, tenant_id: str, mission_id: str, at: datetime, reason: str) -> None: ...


@dataclass
class InProcessScheduler:
    """Development scheduler. Durable timers/waits in production come from the orchestrator (D09)."""
    wakeups: list[tuple[str, str, str]] = field(default_factory=list)
    timers: list[tuple[str, str, datetime, str]] = field(default_factory=list)

    def schedule_wakeup(self, tenant_id: str, mission_id: str, reason: str) -> None:
        if (tenant_id, mission_id, reason) not in self.wakeups:
            self.wakeups.append((tenant_id, mission_id, reason))

    def schedule_timer(self, tenant_id: str, mission_id: str, at: datetime, reason: str) -> None:
        self.timers.append((tenant_id, mission_id, at, reason))

    def due_timers(self, now: datetime) -> list[tuple[str, str, str]]:
        due = [(t, m, r) for t, m, at, r in self.timers if at <= now]
        self.timers = [x for x in self.timers if x[2] > now]
        return due


class MissionService:
    def __init__(self, store: RecordStore, identity: IdentityService,
                 scheduler: MissionScheduler | None = None) -> None:
        self.store = store
        self.identity = identity
        self.scheduler = scheduler or InProcessScheduler()

    # --- lifecycle ---------------------------------------------------------------
    def start_or_resume(self, ctx: AccessContext, *, objective: str, owner_id: str, scope: dict[str, Any],
                        constraints: list[str] | None = None, subscriptions: list[dict[str, Any]] | None = None,
                        budget_usd: float | None = None, mission_id: str | None = None) -> dict[str, Any]:
        """Idempotent: an existing mission id resumes with its unresolved state intact."""
        if mission_id:
            rec = self.store.read().get(ctx.tenant_id, KIND, mission_id)
            if rec is not None:
                self._require_access(ctx, rec.state)
                return {**rec.state, "revision": rec.revision, "resumed": True}
        self.identity.require(ctx, "propose", KIND, site_id=(scope.get("site_ids") or [None])[0])
        mission_id = mission_id or new_id("msn")
        state = {
            "mission_id": mission_id, "objective": objective, "owner_id": owner_id, "scope": scope,
            "constraints": constraints or [], "subscriptions": subscriptions or [],
            "plan": {"version": 0, "steps": []}, "obligations": [], "pending_decisions": [],
            "corrections": [], "rejected_hypotheses": [], "findings": [], "summary": None,
            "history_refs": [], "pending_event_ids": [], "last_event_seq": self._head_seq(ctx.tenant_id),
            "status": ACTIVE, "status_reason": None, "budget_usd": budget_usd, "checkpoint": None,
            "attempts": 0, "remaining_work": [], "notes": [], "created_at": iso(utc_now()), "created_by": ctx.actor_id,
        }
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, KIND, mission_id, state, expected_revision=None, action="start_mission",
                   event_type="mission.started", event_payload={"mission_id": mission_id, "owner_id": owner_id})
        return {**state, "revision": 1, "resumed": False}

    def get(self, ctx: AccessContext, mission_id: str) -> dict[str, Any]:
        rec = self.store.read().require(ctx.tenant_id, KIND, mission_id)
        self._require_access(ctx, rec.state)
        return {**rec.state, "revision": rec.revision, "updated_at": rec.updated_at}

    def set_status(self, ctx: AccessContext, mission_id: str, status: str, reason: str) -> dict[str, Any]:
        if status not in (ACTIVE, PAUSED_BUDGET, BLOCKED, CANCELLED, ARCHIVED):
            raise ValueError(status)
        return self._update(ctx, mission_id, lambda s: {**s, "status": status, "status_reason": reason},
                            action="set_status", event="mission.status")

    def list_for(self, ctx: AccessContext, limit: int = 200) -> list[dict[str, Any]]:
        """Missions the actor may read (every scoped site must be readable)."""
        out = []
        for rec in self.store.read().list(ctx.tenant_id, KIND):
            sites = rec.state["scope"].get("site_ids") or [None]
            if all(self.identity.check(ctx, "read", KIND, rec.id, site_id=site) for site in sites):
                out.append({**rec.state, "revision": rec.revision, "updated_at": rec.updated_at})
        out.sort(key=lambda m: m["updated_at"], reverse=True)
        return out[:limit]

    def add_note(self, ctx: AccessContext, mission_id: str, body: str) -> dict[str, Any]:
        """User-authored note: kept apart from evidence, findings and decisions."""
        body = body.strip()
        if not body or len(body) > 4000:
            raise ValueError("note must be 1-4000 characters")
        self.identity.require(ctx, "comment", KIND, mission_id)
        note = {"note_id": new_id("note"), "body": body, "author": ctx.actor_id, "at": iso(utc_now())}
        self._update(ctx, mission_id, lambda s: {**s, "notes": [*s.get("notes", []), note]}, action="add_note",
                     event="mission.note_added")
        return note

    # --- obligations, decisions, corrections ---------------------------------------
    def add_obligation(self, ctx: AccessContext, mission_id: str, *, description: str, due_at: str | None = None,
                       every_minutes: int | None = None, task_kind: str | None = None,
                       payload: dict[str, Any] | None = None, inputs: list[dict[str, Any]] | None = None,
                       artifact_kind: str | None = None, case_id: str | None = None) -> dict[str, Any]:
        """Repeatable configured obligations (LS-021): e.g. prepare a shift summary every 12h."""
        if every_minutes is not None and every_minutes < 1:
            raise ValueError("repeat interval must be at least one minute")
        if due_at:
            due = parse_iso(due_at)
            if due.tzinfo is None:
                raise ValueError("due_at must include a timezone")
            due_at = iso(due)
        if inputs:
            inputs = self.identity.validate_refs(ctx, inputs)
        ob = {"obligation_id": new_id("obl"), "description": description, "due_at": due_at,
              "payload": payload or {}, "inputs": inputs or [], "artifact_kind": artifact_kind, "case_id": case_id,
              "every_minutes": every_minutes, "task_kind": task_kind, "status": "open", "completions": []}
        self._update(ctx, mission_id, lambda s: {**s, "obligations": [*s["obligations"], ob]},
                     action="add_obligation")
        if due_at:
            self.scheduler.schedule_timer(ctx.tenant_id, mission_id, parse_iso(due_at), ob["obligation_id"])
        return ob

    def due_obligations(self, ctx: AccessContext, mission_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
        now_s = iso(now or utc_now())
        return [o for o in self.get(ctx, mission_id)["obligations"]
                if o["status"] == "open" and o.get("due_at") and o["due_at"] <= now_s]

    def complete_obligation(self, ctx: AccessContext, mission_id: str, obligation_id: str, *,
                            artifact_ref: dict[str, Any]) -> dict[str, Any]:
        def change(s: dict[str, Any]) -> dict[str, Any]:
            obs = []
            for o in s["obligations"]:
                if o["obligation_id"] == obligation_id:
                    o = {**o, "runtime_status": "completed", "runtime_issues": [],
                         "completions": [*o["completions"], {"at": iso(utc_now()), "artifact": artifact_ref}]}
                    if o.get("every_minutes"):
                        base = parse_iso(o.get("due_at")) or utc_now()
                        o["due_at"] = iso(base + timedelta(minutes=o["every_minutes"]))
                    else:
                        o["status"] = "done"
                obs.append(o)
            return {**s, "obligations": obs}
        return self._update(ctx, mission_id, change, action="complete_obligation")

    def block_obligation(self, ctx: AccessContext, mission_id: str, obligation_id: str,
                         issues: list[str]) -> dict[str, Any]:
        return self._update(ctx, mission_id, lambda s: {**s, "obligations": [
            {**o, "runtime_status": "blocked", "runtime_issues": issues}
            if o["obligation_id"] == obligation_id else o for o in s["obligations"]]}, action="block_obligation")

    def request_decision(self, ctx: AccessContext, mission_id: str, *, question: str, options: list[str],
                         decider_role: str, basis: list[dict[str, Any]]) -> dict[str, Any]:
        d = {"decision_id": new_id("dec"), "question": question, "options": options, "decider_role": decider_role,
             "basis": basis, "status": "pending", "answer": None, "requested_at": iso(utc_now())}
        self._update(ctx, mission_id, lambda s: {**s, "pending_decisions": [*s["pending_decisions"], d]},
                     action="request_decision", event="mission.decision_requested")
        return d

    def answer_decision(self, ctx: AccessContext, mission_id: str, decision_id: str, answer: str) -> dict[str, Any]:
        if ctx.actor_kind == "agent":
            raise PermissionError("agents cannot answer mission decisions")

        def change(s: dict[str, Any]) -> dict[str, Any]:
            out = []
            for d in s["pending_decisions"]:
                if d["decision_id"] == decision_id:
                    if d["decider_role"] not in ctx.roles:
                        raise PermissionError(f"decision requires role {d['decider_role']}")
                    if answer not in d["options"]:
                        raise ValueError("answer is not one of the offered options")
                    d = {**d, "status": "answered", "answer": answer, "answered_by": ctx.actor_id,
                         "answered_at": iso(utc_now())}
                out.append(d)
            return {**s, "pending_decisions": out}
        result = self._update(ctx, mission_id, change, action="answer_decision", event="mission.decision_answered")
        self.scheduler.schedule_wakeup(ctx.tenant_id, mission_id, f"decision:{decision_id}")
        return result

    def record_correction(self, ctx: AccessContext, mission_id: str, *, text: str, source_ref: dict[str, Any] | None,
                          claim_ref: dict[str, Any] | None, rejects_hypothesis: str | None = None) -> dict[str, Any]:
        """User corrections and rejected hypotheses persist through compaction (LS-053)."""
        corr = {"correction_id": new_id("cor"), "text": text, "source_ref": source_ref, "claim_ref": claim_ref,
                "by": ctx.actor_id, "at": iso(utc_now())}

        def change(s: dict[str, Any]) -> dict[str, Any]:
            out = {**s, "corrections": [*s["corrections"], corr]}
            if rejects_hypothesis:
                out["rejected_hypotheses"] = [*s["rejected_hypotheses"],
                                              {"hypothesis": rejects_hypothesis, "correction_id": corr["correction_id"]}]
            return out
        self._update(ctx, mission_id, change, action="record_correction", event="mission.corrected")
        self.scheduler.schedule_wakeup(ctx.tenant_id, mission_id, f"correction:{corr['correction_id']}")
        return corr

    # --- events and wakeups -----------------------------------------------------------
    def deliver_events(self, tenant_id: str) -> dict[str, int]:
        """Match newly committed events to mission subscriptions; coalesce wakeups, never drop event ids."""
        tx = self.store.read()
        woke: dict[str, int] = {}
        for rec in tx.list(tenant_id, KIND, lambda s: s["status"] in (ACTIVE, PAUSED_BUDGET, BLOCKED)):
            s = rec.state
            events = self.store.events_since(tenant_id, s["last_event_seq"], limit=10_000)
            if not events:
                continue
            matched = [e.event_id for _, e in events if self._subscribed(s, e)
                       and e.aggregate_id != s["mission_id"]]
            new_cursor = events[-1][0]
            with self.store.transaction("mission-router") as wtx:
                cur = wtx.require(tenant_id, KIND, rec.id)
                if cur.state["last_event_seq"] >= new_cursor:
                    continue
                pending = list(dict.fromkeys([*cur.state["pending_event_ids"], *matched]))
                wtx.put(tenant_id, KIND, rec.id, {**cur.state, "pending_event_ids": pending,
                                                  "last_event_seq": new_cursor},
                        expected_revision=cur.revision, action="route_events")
            if matched:
                woke[rec.id] = len(matched)
                self.scheduler.schedule_wakeup(tenant_id, rec.id, "events")
        return woke

    @staticmethod
    def _subscribed(state: dict[str, Any], event: Any) -> bool:
        for sub in state["subscriptions"]:
            if sub.get("type") and not event.type.startswith(sub["type"]):
                continue
            if sub.get("aggregate_id") and sub["aggregate_id"] != event.aggregate_id:
                continue
            if sub.get("site_id") and event.payload.get("site_id") not in (None, sub["site_id"]):
                continue
            return True
        return False

    # --- activations, checkpoints, merging ------------------------------------------------
    def activate(self, ctx: AccessContext, mission_id: str, worker_id: str, ttl_seconds: int = 900) -> Activation:
        """Admit a single coordinator. A replaced worker's token becomes stale immediately."""
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, KIND, mission_id)
            self._require_access(ctx, rec.state, tx)
            if rec.state["status"] in (CANCELLED, ARCHIVED):
                raise ValueError(f"mission is {rec.state['status']}")
            token = tx.acquire_lease(ctx.tenant_id, KIND, mission_id, worker_id, ttl_seconds)
            attempt = rec.state["attempts"] + 1
            rec = tx.put(ctx.tenant_id, KIND, mission_id, {**rec.state, "attempts": attempt},
                         expected_revision=rec.revision, action="activate",
                         details={"worker_id": worker_id, "token": token})
        return Activation(mission_id, ctx.tenant_id, worker_id, token, rec.revision,
                          tuple(rec.state["pending_event_ids"]), attempt)

    def takeover(self, ctx: AccessContext, mission_id: str, worker_id: str) -> Activation:
        """Replace a lost worker: force-expire its lease, then activate. Old token can no longer commit."""
        with self.store.transaction(ctx.actor_id) as tx:
            tx.expire_lease(ctx.tenant_id, KIND, mission_id)
        return self.activate(ctx, mission_id, worker_id)

    def checkpoint(self, act: Activation, *, progress: dict[str, Any], consumed_event_ids: list[str] | None = None,
                   findings: list[dict[str, Any]] | None = None, plan: dict[str, Any] | None = None,
                   remaining_work: list[str] | None = None,
                   surfaced_obligations: list[str] | None = None) -> dict[str, Any]:
        """Fenced commit of worker progress. The checkpoint blob key is immutable per attempt/revision."""
        with self.store.transaction(act.worker_id) as tx:
            tx.check_lease(act.tenant_id, KIND, act.mission_id, act.worker_id, act.token)
            rec = tx.require(act.tenant_id, KIND, act.mission_id)
            s = rec.state
            blob = canonical_json({"mission_id": act.mission_id, "attempt": act.attempt, "base_revision": rec.revision,
                                   "progress": progress}).encode()
            digest = tx.put_blob(act.tenant_id, blob, "application/json")
            consumed = set(consumed_event_ids or [])
            surfaced = set(surfaced_obligations or [])
            now_s = iso(utc_now())
            obligations = [{**o, "surfaced_due_at": o.get("due_at"), "surfaced_at": now_s}
                           if o["obligation_id"] in surfaced else o for o in s["obligations"]]
            new_state = {**s, "obligations": obligations,
                         "pending_event_ids": [e for e in s["pending_event_ids"] if e not in consumed],
                         "findings": [*s["findings"], *(findings or [])],
                         "plan": plan if plan is not None else s["plan"],
                         "remaining_work": remaining_work if remaining_work is not None else s["remaining_work"],
                         "checkpoint": {"key": f"{act.mission_id}:{act.attempt}:{rec.revision + 1}",
                                        "digest": digest, "attempt": act.attempt, "token": act.token,
                                        "at": iso(utc_now())}}
            out = tx.put(act.tenant_id, KIND, act.mission_id, new_state, expected_revision=rec.revision,
                         action="checkpoint", event_type="mission.checkpoint",
                         event_payload={"mission_id": act.mission_id, "attempt": act.attempt})
        return {**out.state, "revision": out.revision}

    def release(self, act: Activation) -> None:
        """End an activation: the lease is freed and the next activation receives a higher fencing token."""
        with self.store.transaction(act.worker_id) as tx:
            tx.check_lease(act.tenant_id, KIND, act.mission_id, act.worker_id, act.token)
            tx.expire_lease(act.tenant_id, KIND, act.mission_id)

    @staticmethod
    def next_unsurfaced_due(state: dict[str, Any]) -> str | None:
        """Earliest open obligation due time not yet surfaced for its current due time."""
        dues = [o["due_at"] for o in state["obligations"] if o["status"] == "open" and o.get("due_at")
                and o.get("surfaced_due_at") != o["due_at"]]
        return min(dues) if dues else None

    def resume_point(self, ctx: AccessContext, mission_id: str) -> dict[str, Any] | None:
        s = self.get(ctx, mission_id)
        cp = s.get("checkpoint")
        if not cp:
            return None
        blob = self.store.read().get_blob(ctx.tenant_id, cp["digest"])
        return json.loads(blob) if blob else None

    def merge_child_finding(self, act: Activation, finding: dict[str, Any]) -> dict[str, Any]:
        """Accept a delegated worker's finding only if its input manifest is still current."""
        basis = finding.get("basis", [])
        tx = self.store.read()
        stale = []
        for ref in basis:
            cur = tx.get(act.tenant_id, ref["kind"], ref["id"])
            if cur is None or (ref.get("revision") is not None and cur.revision != ref["revision"]) or \
                    cur.state.get("status") in ("stale", "quarantined"):
                stale.append(f"{ref['kind']}:{ref['id']}")
        if stale:
            return {"merged": False, "reason": "basis changed; rebase required", "stale": stale}
        self.checkpoint(act, progress={"merged_finding": finding.get("finding_id")}, findings=[finding])
        return {"merged": True}

    def pause_for_budget(self, act: Activation, *, completed: list[str], remaining_work: list[str],
                         reason: str) -> dict[str, Any]:
        """Budget exhaustion preserves progress and reports remaining work; controls are unchanged (LS-058)."""
        self.checkpoint(act, progress={"completed": completed}, remaining_work=remaining_work)
        with self.store.transaction(act.worker_id) as tx:
            tx.check_lease(act.tenant_id, KIND, act.mission_id, act.worker_id, act.token)
            rec = tx.require(act.tenant_id, KIND, act.mission_id)
            out = tx.put(act.tenant_id, KIND, act.mission_id,
                         {**rec.state, "status": PAUSED_BUDGET, "status_reason": reason},
                         expected_revision=rec.revision, action="pause_budget", reason=reason,
                         event_type="mission.paused_budget",
                         event_payload={"mission_id": act.mission_id, "remaining_work": remaining_work})
        return {**out.state, "revision": out.revision}

    # --- context and compaction ---------------------------------------------------------
    def assemble_context(self, ctx: AccessContext, mission_id: str, *, evidence: list[dict[str, Any]],
                         token_budget: int = 8_000) -> dict[str, Any]:
        """Bounded, authorized context. Protected sections are never truncated."""
        s = self.get(ctx, mission_id)
        authorized, withheld = [], []
        for ref in evidence:
            (authorized if self.identity.check_derived(ctx, [ref]) else withheld).append(ref)
        protected = {
            "objective": s["objective"], "constraints": s["constraints"], "corrections": s["corrections"],
            "rejected_hypotheses": s["rejected_hypotheses"],
            "open_obligations": [o for o in s["obligations"] if o["status"] == "open"],
            "pending_decisions": [d for d in s["pending_decisions"] if d["status"] == "pending"],
            "remaining_work": s["remaining_work"],
        }
        used = len(canonical_json(protected)) // 4
        optional: dict[str, list[Any]] = {"pending_event_ids": list(s["pending_event_ids"]),
                                          "recent_findings": list(reversed(s["findings"])),
                                          "evidence_manifest": authorized}
        included: dict[str, list[Any]] = {k: [] for k in optional}
        truncated: dict[str, int] = {}
        for key in ("pending_event_ids", "evidence_manifest", "recent_findings"):
            for item in optional[key]:
                cost = len(canonical_json(item)) // 4 + 1
                if used + cost > token_budget:
                    truncated[key] = truncated.get(key, 0) + 1
                    continue
                included[key].append(item)
                used += cost
        return {**protected, **included, "summary": s["summary"], "history_refs": s["history_refs"],
                "withheld_unauthorized": len(withheld), "truncated_counts": truncated,
                "estimated_tokens": used, "token_budget": token_budget, "mission_revision": s["revision"]}

    def compact(self, ctx: AccessContext, mission_id: str, *, keep_recent_findings: int = 10,
                summarize: Callable[[list[dict[str, Any]]], str] | None = None) -> dict[str, Any]:
        """Move older findings into a recoverable history blob plus summary; protected state is retained."""
        def change(s: dict[str, Any]) -> dict[str, Any]:
            older, recent = s["findings"][:-keep_recent_findings or None], s["findings"][-keep_recent_findings:]
            if not older:
                return s
            text = summarize(older) if summarize else f"{len(older)} earlier findings archived; see history_refs."
            return {**s, "findings": recent, "summary": text, "_archive": older}

        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, KIND, mission_id)
            self._require_access(ctx, rec.state, tx)
            new = change(rec.state)
            if new is rec.state:
                return {**rec.state, "revision": rec.revision}
            archive = new.pop("_archive")
            digest = tx.put_blob(ctx.tenant_id, canonical_json(archive).encode(), "application/json")
            new["history_refs"] = [*rec.state["history_refs"], {"digest": digest, "count": len(archive),
                                                                "at": iso(utc_now())}]
            out = tx.put(ctx.tenant_id, KIND, mission_id, new, expected_revision=rec.revision, action="compact")
        return {**out.state, "revision": out.revision}

    def history(self, ctx: AccessContext, mission_id: str) -> list[dict[str, Any]]:
        s = self.get(ctx, mission_id)
        tx = self.store.read()
        out: list[dict[str, Any]] = []
        for ref in s["history_refs"]:
            blob = tx.get_blob(ctx.tenant_id, ref["digest"])
            out.extend(json.loads(blob) if blob else [])
        return out + s["findings"]

    # --- streaming --------------------------------------------------------------------
    def stream(self, ctx: AccessContext, mission_id: str, after_seq: int = 0, limit: int = 200) -> dict[str, Any]:
        """Reconnect support (LS-069): consistent snapshot plus mission events after the client's cursor."""
        snapshot = self.get(ctx, mission_id)
        events = [(seq, e) for seq, e in self.store.events_since(ctx.tenant_id, after_seq, limit=10_000)
                  if e.aggregate_id == mission_id or e.payload.get("mission_id") == mission_id][:limit]
        cursor = events[-1][0] if events else after_seq
        return {"snapshot": snapshot, "events": [{"seq": s, **e.to_dict()} for s, e in events], "cursor": cursor}

    # --- internals ---------------------------------------------------------------------
    def _head_seq(self, tenant_id: str) -> int:
        return self.store.head_seq(tenant_id)

    def _require_access(self, ctx: AccessContext, state: dict[str, Any], tx: Transaction | None = None) -> None:
        sites = state["scope"].get("site_ids") or [None]
        for site in sites:
            self.identity.require(ctx, "read", KIND, state["mission_id"], site_id=site, tx=tx)

    def _update(self, ctx: AccessContext, mission_id: str, change: Callable[[dict[str, Any]], dict[str, Any]], *,
                action: str, event: str | None = None) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, KIND, mission_id)
            self._require_access(ctx, rec.state, tx)
            out = tx.put(ctx.tenant_id, KIND, mission_id, change(rec.state), expected_revision=rec.revision,
                         action=action, event_type=event, event_payload={"mission_id": mission_id})
        return {**out.state, "revision": out.revision}


__all__ = ["MissionService", "Activation", "InProcessScheduler", "MissionScheduler", "ConflictError", "LeaseError",
           "content_hash"]
