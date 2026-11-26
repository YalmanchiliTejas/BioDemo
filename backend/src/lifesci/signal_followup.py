"""After a deviation signal is raised or escalated: alert people, then let the assistant triage it.

Runs on the in-process commit listener for immediacy and again on every runtime tick, so a process that dies
between commit and delivery is caught up. Both alerting and triage are idempotent; the sweep only acts on open
signals whose follow-up has not caught up with their current severity.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from .ids import iso, utc_now

log = logging.getLogger(__name__)
RANK = {"warning": 0, "action": 1, "critical": 2}
SWEEP_WINDOW = timedelta(hours=48)  # ponytail: older unfollowed signals are left for people; widen if needed


class SignalFollowUp:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def on_event(self, event: Any) -> None:
        if event.type in ("signal.raised", "signal.escalated"):
            self.follow(event.tenant_id, event.payload["signal_id"])

    def follow(self, tenant: str, signal_id: str) -> None:
        from .signals import KIND
        state = self.p.store.read().require(tenant, KIND, signal_id).state
        if state.get("status") == "dismissed":
            return
        alerted = (state.get("alerts") or {}).get("severity")
        if alerted is None or RANK[state["severity"]] > RANK.get(alerted, -1):
            try:
                self.p.alerts.on_signal(tenant, state)
            except Exception:
                log.exception("alerting failed for %s; retried on the next tick", signal_id)
        triage = getattr(self.p, "triage", None)
        if triage is not None:  # idempotent; it decides itself whether an escalation needs a new run
            try:
                triage.on_signal(tenant, state)
            except Exception:
                log.exception("triage start failed for %s; retried on the next tick", signal_id)

    def sweep(self, tenants) -> int:
        from .signals import KIND
        since = iso(utc_now() - SWEEP_WINDOW)
        done = 0
        for tenant in tenants:
            for rec in self.p.store.read().list(tenant, KIND, lambda s: s.get("status") == "open" and s.get("last_at", "") >= since):
                self.follow(tenant, rec.id)
                done += 1
        return done
