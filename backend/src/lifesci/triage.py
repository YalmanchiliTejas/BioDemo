"""Automatic, read-only triage of deviation signals by the one manufacturing assistant.

A raised or escalated signal at or above the site's threshold starts a background assistant turn, owned
by the site's QA reviewer, that gathers evidence and proposes next steps. It never opens a case, sends a
message or concludes a cause: proposals wait for a person. Skips are recorded with their reason.
"""
from __future__ import annotations

from typing import Any, Callable

from .ids import iso, utc_now
from .roles import agent_context_for
from .store import ConflictError

SEVERITY = {'warning': 1, 'action': 2, 'critical': 3}
DEFAULTS = {'min_severity': 'action', 'daily_cap': 20, 'paused': False}
SETTINGS, TRIAGE, USAGE = 'triage_settings', 'signal_triage', 'triage_usage'
TERMINAL_TURN = {'completed': 'ready', 'needs_information': 'ready', 'blocked': 'failed',
                 'agent_unavailable': 'failed', 'cancelled': 'failed'}


class TriageService:
    def __init__(self, platform, report: Callable[[str, str, dict], Any] | None = None,
                 submit_turn: Callable[[Any, str, str], Any] | None = None):
        """report(tenant_id, signal_id, triage) writes signal.triage; submit_turn(ctx, thread_id, turn_id) queues the
        turn on the deployment's task runner (default: run inline, as the standing-responsibility path does)."""
        self.p = platform
        self.report = report or (lambda tenant, signal_id, triage: None)
        self.submit_turn = submit_turn or (lambda ctx, thread_id, turn_id: platform.engineering_conversations.run_turn(ctx, thread_id, turn_id))

    # --- settings (site QA/admin with approve) ---------------------------------------
    def settings(self, tenant_id: str, site_id: str) -> dict[str, Any]:
        rec = self.p.store.read().get(tenant_id, SETTINGS, site_id)
        return {**DEFAULTS, **(rec.state if rec else {}), 'site_id': site_id}

    def set_settings(self, ctx, site_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        if ctx.actor_kind != 'person' or ctx.delegated_from:
            raise PermissionError('a person must change auto-triage settings')
        self.p.identity.require(ctx, 'approve', SETTINGS, site_id, site_id=site_id)
        clean = {}
        if 'min_severity' in changes:
            if changes['min_severity'] not in SEVERITY:
                raise ValueError('min_severity must be warning, action or critical')
            clean['min_severity'] = changes['min_severity']
        if 'daily_cap' in changes:
            cap = int(changes['daily_cap'])
            if not 0 <= cap <= 200:
                raise ValueError('daily_cap must be between 0 and 200')
            clean['daily_cap'] = cap
        if 'paused' in changes:
            clean['paused'] = bool(changes['paused'])
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = tx.get(ctx.tenant_id, SETTINGS, site_id)
            state = {**DEFAULTS, **(rec.state if rec else {}), **clean, 'site_id': site_id,
                     'updated_by': ctx.actor_id, 'updated_at': iso(utc_now())}
            tx.put(ctx.tenant_id, SETTINGS, site_id, state, expected_revision=rec.revision if rec else None,
                   action='configure_auto_triage')
        return state

    # --- signal handling --------------------------------------------------------------
    def on_signal(self, tenant_id: str, signal: dict[str, Any]) -> dict[str, Any]:
        """Idempotent per signal: a second call does nothing unless the signal's severity rose."""
        sid, site = signal['signal_id'], signal['site_id']
        severity = SEVERITY.get(signal.get('severity'), 0)
        prior = self.p.store.read().get(tenant_id, TRIAGE, sid)
        if prior and prior.state.get('severity_handled', 0) >= severity:
            return self._public(prior.state)
        settings = self.settings(tenant_id, site)
        if severity < SEVERITY[settings['min_severity']]:
            return self._record(tenant_id, sid, site, severity, status='skipped',
                                reason=f"below this site's auto-triage threshold ({settings['min_severity']})")
        if settings['paused']:
            return self._record(tenant_id, sid, site, severity, status='skipped', reason='auto-triage is paused for this site')
        if prior and prior.state['status'] == 'running':
            # It reads the signal's current state, so the escalation is already in view; no second concurrent run.
            return self._record(tenant_id, sid, site, severity, status='running',
                                reason=f"escalated to {signal.get('severity')} during triage; the running triage reads the current signal",
                                **{k: prior.state.get(k) for k in ('owner_id', 'conversation_id', 'turn_id')})
        owner = self._owner(tenant_id, site)
        if owner is None:
            return self._record(tenant_id, sid, site, severity, status='skipped',
                                reason=f'no QA reviewer is assigned at site {site} to own the triage')
        if not self._admit(tenant_id, site, settings['daily_cap']):
            return self._record(tenant_id, sid, site, severity, status='skipped',
                                reason=f"daily auto-triage limit ({settings['daily_cap']}) reached for this site")
        service = self.p.engineering_conversations
        owner_ctx = self.p.identity.context_for(tenant_id, owner)
        try:
            thread_id = prior.state.get('conversation_id') if prior else None
            if not thread_id:
                thread_id = service.create(owner_ctx, {'site_id': site})['id']
            delegated = agent_context_for(owner_ctx, self.p.identity)
            fresh = service.get(delegated, thread_id)
            queued = service.enqueue(delegated, thread_id, {'expected_revision': fresh['revision'], 'text': self._request(signal)})
            turn_id = queued['turn_ids'][-1]
            service._update_turn(delegated, turn_id, origin='background', triage_signal_id=sid, system_request=True,
                                 responsibility_objective=f'Triage of deviation signal {sid}')
        except (PermissionError, ValueError, ConflictError) as exc:
            return self._record(tenant_id, sid, site, severity, status='skipped', reason=f'triage could not start: {exc}')
        state = self._record(tenant_id, sid, site, severity, status='running', owner_id=owner,
                             conversation_id=thread_id, turn_id=turn_id)
        try:
            self.submit_turn(delegated, thread_id, turn_id)
        except Exception as exc:  # a failed model call must still leave a visible state on the signal
            return self._record(tenant_id, sid, site, severity, status='failed', owner_id=owner,
                                conversation_id=thread_id, turn_id=turn_id, reason=f'assistant run failed: {type(exc).__name__}')
        return self.refresh(tenant_id, sid) or state

    def refresh(self, tenant_id: str, signal_id: str) -> dict[str, Any] | None:
        """Move a running triage to ready/failed from its turn's outcome (call from the runtime tick)."""
        rec = self.p.store.read().get(tenant_id, TRIAGE, signal_id)
        if not rec or rec.state['status'] != 'running':
            return self._public(rec.state) if rec else None
        turn = self.p.store.read().get(tenant_id, 'engineering_chat_turn', rec.state['turn_id'])
        status = TERMINAL_TURN.get(turn.state['status']) if turn else 'failed'
        if not status:
            return self._public(rec.state)
        reason = None if status == 'ready' else (turn.state.get('system_message') if turn else 'triage turn missing')
        return self._record(tenant_id, signal_id, rec.state['site_id'], rec.state['severity_handled'], status=status,
                            reason=reason, **{k: rec.state.get(k) for k in ('owner_id', 'conversation_id', 'turn_id')})

    def refresh_active(self, tenant_id: str) -> int:
        running = self.p.store.read().list(tenant_id, TRIAGE, lambda s: s.get('status') == 'running')
        for rec in running:
            self.refresh(tenant_id, rec.id)
        return len(running)

    # --- internals --------------------------------------------------------------------
    @staticmethod
    def _request(signal: dict[str, Any]) -> str:
        subject = signal.get('subject') or {}
        return (f"Signal {signal['signal_id']}: triage request (system-generated; not written by a person).\n"
                f"{signal.get('severity', '')} · {signal.get('rule', '')} · subject {subject.get('kind', '?')} {subject.get('id', '?')} "
                f"at site {signal['site_id']}.\n"
                f"Read deviation_signal {signal['signal_id']}. Follow identifier links from its subject; look at the recent "
                'series around it, similar closed cases and missing evidence. Report observations, competing hypotheses and '
                'unknowns. You may propose opening a deviation case, a multi-agent investigation or an evidence request. '
                'Never conclude a root cause, open a case, change records or send any message: a person decides.')[:4000]

    def _owner(self, tenant_id: str, site_id: str) -> str | None:
        assignments = [r.state for r in self.p.store.read().list(tenant_id, 'role_assignment')
                       if r.state.get('role') == 'qa' and not r.state.get('revoked_at')
                       and r.state.get('actor_kind', 'person') == 'person']
        at_site = sorted(a['actor_id'] for a in assignments if a.get('site_id') == site_id)
        org_wide = sorted(a['actor_id'] for a in assignments if a.get('site_id') is None)
        return (at_site or org_wide or [None])[0]

    def _admit(self, tenant_id: str, site_id: str, cap: int) -> bool:
        key = f"{site_id}:{iso(utc_now())[:10]}"
        with self.p.store.transaction('triage') as tx:
            rec = tx.get(tenant_id, USAGE, key)
            used = rec.state['count'] if rec else 0
            if used >= cap:
                return False
            tx.put(tenant_id, USAGE, key, {'site_id': site_id, 'count': used + 1}, expected_revision=rec.revision if rec else None,
                   action='admit_auto_triage')
        return True

    def _record(self, tenant_id, signal_id, site_id, severity, *, status, reason=None, **refs) -> dict[str, Any]:
        with self.p.store.transaction('triage') as tx:
            rec = tx.get(tenant_id, TRIAGE, signal_id)
            state = {**(rec.state if rec else {}), 'signal_id': signal_id, 'site_id': site_id, 'severity_handled': severity,
                     'status': status, 'reason': reason, 'updated_at': iso(utc_now()), **{k: v for k, v in refs.items() if v}}
            tx.put(tenant_id, TRIAGE, signal_id, state, expected_revision=rec.revision if rec else None, action='record_auto_triage')
        public = self._public(state)
        self.report(tenant_id, signal_id, public)
        return public

    @staticmethod
    def _public(state: dict[str, Any]) -> dict[str, Any]:
        return {k: state.get(k) for k in ('status', 'reason', 'conversation_id', 'turn_id')}


def triage_routes(app, platform, ctx_dep) -> None:
    from typing import Literal
    from fastapi import Depends
    from pydantic import BaseModel, Field

    class TriageSettingsIn(BaseModel):
        min_severity: Literal['warning', 'action', 'critical'] | None = None
        daily_cap: int | None = Field(default=None, ge=0, le=200)
        paused: bool | None = None

    @app.get('/v1/triage-settings/{site_id}')
    def get_triage_settings(site_id: str, ctx=Depends(ctx_dep)):
        platform.identity.require(ctx, 'read', SETTINGS, site_id, site_id=site_id)
        return platform.triage.settings(ctx.tenant_id, site_id)

    @app.post('/v1/triage-settings/{site_id}')
    def set_triage_settings(site_id: str, body: TriageSettingsIn, ctx=Depends(ctx_dep)):
        return platform.triage.set_settings(ctx, site_id, body.model_dump(exclude_none=True))
