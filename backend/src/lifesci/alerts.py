"""Deviation-signal alerts: admin-configured channels and routes, an in-app inbox, durable external delivery.

Wiring (done once in container/api/runtime):

    platform.alerts = AlertService(platform)                       # optional: transport=, smtp_factory=
    alert_routes(app, platform, ctx_dep)                           # §6 routes
    platform.alerts.on_signal(tenant_id, signal_state)             # after signal.raised / signal.escalated
    platform.alerts.on_triage_ready(tenant_id, signal_state)       # after TriageService finishes

`signal_state` is the `deviation_signal` record state (design §6). Both hooks are idempotent: repeating a call
never re-alerts; a higher severity (escalation) alerts again. Alerts are authorized by the routes an organization
administrator configured; agents never send them (NotificationService refuses agent contexts).

External messages carry severity, the rule that fired, subject, site, time and a link only, never document text.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any
from urllib.parse import urlsplit

from .collab import ChannelError, ChannelMessage, EmailSMTPAdapter, NotificationService, SlackWebhookAdapter, TeamsWebhookAdapter
from .identity import AccessContext
from .ids import iso, new_id, utc_now
from .store import ConflictError

CHANNEL, ROUTE, INBOX, SIGNAL = 'alert_channel', 'alert_route', 'alert_inbox', 'deviation_signal'
SEVERITY = {'warning': 1, 'action': 2, 'critical': 3}
KINDS = {'email': ('host', 'port', 'from_addr'), 'slack': (), 'teams': ()}
SECRET_FIELDS = {'email': ('username', 'password'), 'slack': ('webhook_url',), 'teams': ('webhook_url',)}
# Webhooks only to the providers' own hosts: an admin-entered URL must not become a way to reach internal services.
WEBHOOK_HOSTS = {'slack': (r'hooks\.slack\.com',), 'teams': (r'[\w.-]+\.webhook\.office\.com', r'[\w.-]+\.logic\.azure\.com')}
DEFAULT_ROUTES = [{'route_id': 'default', 'site_id': None, 'min_severity': 'action', 'roles': ['qa', 'supervisor'],
                   'channels': ['in_app'], 'enabled': True, 'default': True}]


def _key(*parts: Any) -> str:
    return hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:24]


class AlertService:
    def __init__(self, platform, *, transport=None, smtp_factory=None) -> None:
        self.p = platform
        self.transport, self.smtp_factory = transport, smtp_factory

    # --- administration -------------------------------------------------------------
    @staticmethod
    def _admin(ctx: AccessContext) -> None:
        if ctx.actor_kind != 'person' or ctx.delegated_from or 'admin' not in ctx.roles or ctx.site_ids:
            raise PermissionError('An organization-wide administrator is required to configure alerts')

    def _credentials(self):
        from .connector_products import CredentialStore
        return CredentialStore(self.p.store)

    def channels(self, ctx: AccessContext) -> list[dict[str, Any]]:
        self._admin(ctx)
        creds = self._credentials()
        return [{**r.state, 'secret_fields': creds.fields(ctx.tenant_id, r.id)}
                for r in self.p.store.read().list(ctx.tenant_id, CHANNEL)]

    def save_channel(self, ctx: AccessContext, body: dict[str, Any]) -> dict[str, Any]:
        self._admin(ctx)
        kind = body.get('kind')
        if kind not in KINDS:
            raise ValueError('channel kind must be email, slack or teams')
        name = str(body.get('name') or kind).strip()[:80]
        config = {k: v for k, v in (body.get('config') or {}).items() if k in (*KINDS[kind], 'starttls')}
        secrets = {k: str(v) for k, v in (body.get('secrets') or {}).items() if k in SECRET_FIELDS[kind] and v}
        if kind in WEBHOOK_HOSTS and 'webhook_url' in secrets:
            parts = urlsplit(secrets['webhook_url'])
            if parts.scheme != 'https' or not any(re.fullmatch(h, parts.hostname or '') for h in WEBHOOK_HOSTS[kind]):
                raise ValueError(f'{kind} webhook must be an https URL on the provider\'s webhook host')
        if kind == 'email':
            missing = [k for k in KINDS['email'] if not config.get(k)]
            if missing:
                raise ValueError('email channel needs ' + ', '.join(missing))
            config['port'] = int(config['port'])
        cid = body.get('channel_id') or new_id('achan')
        with self.p.store.transaction(ctx.actor_id) as tx:
            current = tx.get(ctx.tenant_id, CHANNEL, cid)
            if body.get('channel_id') and current is None:
                raise KeyError('unknown channel')
            if current and current.state['kind'] != kind:
                raise ValueError('a channel cannot change kind')
            state = {'channel_id': cid, 'kind': kind, 'name': name, 'config': config,
                     'enabled': bool(body.get('enabled', True)), 'updated_by': ctx.actor_id, 'updated_at': iso(utc_now()),
                     'created_at': current.state['created_at'] if current else iso(utc_now())}
            tx.put(ctx.tenant_id, CHANNEL, cid, state, expected_revision=current.revision if current else None,
                   action='configure_alert_channel')
            if secrets:
                self._credentials().save(tx, ctx.tenant_id, cid, secrets)
        if kind in WEBHOOK_HOSTS and 'webhook_url' not in self._credentials().fields(ctx.tenant_id, cid):
            raise ValueError(f'{kind} channel needs a webhook URL')
        return next(c for c in self.channels(ctx) if c['channel_id'] == cid)

    def routes(self, ctx: AccessContext) -> list[dict[str, Any]]:
        self._admin(ctx)
        return self._routes(ctx.tenant_id, include_disabled=True)

    def _routes(self, tenant: str, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        stored = [r.state for r in self.p.store.read().list(tenant, ROUTE)]
        active = [r for r in stored if include_disabled or r['enabled']]
        return active if stored else [dict(r) for r in DEFAULT_ROUTES]

    def save_route(self, ctx: AccessContext, body: dict[str, Any]) -> dict[str, Any]:
        self._admin(ctx)
        if body.get('min_severity') not in SEVERITY:
            raise ValueError('min_severity must be warning, action or critical')
        roles = sorted({str(r) for r in body.get('roles') or []})
        if not roles:
            raise ValueError('a route needs at least one role')
        known = {r.id for r in self.p.store.read().list(ctx.tenant_id, CHANNEL)}
        channels = list(dict.fromkeys(['in_app', *[c for c in body.get('channels') or [] if c != 'in_app']]))
        if unknown := [c for c in channels if c != 'in_app' and c not in known]:
            raise ValueError('unknown channel ' + ', '.join(unknown))
        rid = body.get('route_id') or new_id('aroute')
        with self.p.store.transaction(ctx.actor_id) as tx:
            current = tx.get(ctx.tenant_id, ROUTE, rid)
            state = {'route_id': rid, 'site_id': body.get('site_id') or None, 'min_severity': body['min_severity'],
                     'roles': roles, 'channels': channels, 'enabled': bool(body.get('enabled', True)),
                     'updated_by': ctx.actor_id, 'updated_at': iso(utc_now())}
            tx.put(ctx.tenant_id, ROUTE, rid, state, expected_revision=current.revision if current else None,
                   action='configure_alert_route')
        return state

    def test_channel(self, ctx: AccessContext, channel_id: str, recipient: str | None = None) -> dict[str, Any]:
        self._admin(ctx)
        rec = self.p.store.read().require(ctx.tenant_id, CHANNEL, channel_id)
        to = recipient or self._email(ctx.tenant_id, ctx.actor_id) or ctx.actor_id
        payload = {'subject': 'Sievance test alert', 'body': 'This is a test from Settings › Alerts. No action needed.'}
        return self._notifications(ctx.tenant_id, [rec.state]).send(
            self._service(ctx.tenant_id), to if rec.state['kind'] == 'email' else rec.state['name'], channel_id, payload,
            owner=ctx.actor_id, idempotency_key=f'test|{channel_id}|{new_id("t")}', notice_type='alert_test')

    # --- delivery -------------------------------------------------------------------
    @staticmethod
    def _service(tenant: str) -> AccessContext:
        # The dispatcher acts under the routes an administrator configured. Least privilege: the agent role
        # policy grants only read/propose/comment, and the non-agent kind lets NotificationService record sends.
        return AccessContext(tenant, 'alert-dispatcher', 'service', frozenset({'agent'}))

    def _adapter(self, tenant: str, channel: dict[str, Any]):
        secret = self._credentials().load(tenant, channel['channel_id'])
        if channel['kind'] == 'email':
            config = {**channel['config'], **secret}
            return EmailSMTPAdapter(config, **({'smtp_factory': self.smtp_factory} if self.smtp_factory else {}))
        cls = SlackWebhookAdapter if channel['kind'] == 'slack' else TeamsWebhookAdapter
        return cls({'webhook_url': secret.get('webhook_url')}, transport=self.transport)

    def _notifications(self, tenant: str, channels: list[dict[str, Any]]) -> NotificationService:
        adapters = []
        for c in channels:
            adapter = self._adapter(tenant, c)
            adapter.name = c['channel_id']  # NotificationService keys channels by name
            adapters.append(adapter)
        return NotificationService(self.p.store, self.p.identity, adapters)

    def _email(self, tenant: str, actor: str) -> str | None:
        rec = self.p.store.read().get(tenant, 'organization_member', actor)
        return rec.state.get('email') if rec else None

    def recipients(self, tenant: str, site_id: str | None, roles: list[str]) -> list[str]:
        """People holding a routed role at the signal's site or organization-wide."""
        out = set()
        for r in self.p.store.read().list(tenant, 'role_assignment'):
            s = r.state
            if not s.get('revoked_at') and s['role'] in roles and s.get('actor_kind', 'person') == 'person' \
                    and (s.get('site_id') is None or s.get('site_id') == site_id):
                out.add(s['actor_id'])
        return sorted(out)

    @staticmethod
    def message(signal: dict[str, Any], *, update: str | None = None) -> dict[str, str]:
        subject = signal.get('subject') or {}
        what = f"{subject.get('kind', '')} {subject.get('id', '')}".strip() or 'unspecified subject'
        link = f"{os.environ.get('APP_URL', '').rstrip('/')}/signals/?id={signal['signal_id']}"
        title = f"{signal['severity'].upper()} deviation signal · {what} · {signal.get('site_id') or ''}".strip(' ·')
        lines = [update] if update else []
        lines += [f"Rule: {signal.get('rule', '')}", f"Subject: {what}", f"Site: {signal.get('site_id', '')}",
                  f"At: {signal.get('last_at') or signal.get('first_at', '')}",
                  'This is a signal for review, not a confirmed deviation.', f'Open: {link}']
        return {'subject': ('Update: ' if update else '') + title, 'body': '\n'.join(lines)}

    def on_signal(self, tenant: str, signal: dict[str, Any]) -> dict[str, Any]:
        if signal.get('status') in ('dismissed',) or signal.get('severity') not in SEVERITY:
            return {'sent': 0, 'skipped': 'not alertable'}
        level = SEVERITY[signal['severity']]
        routes = [r for r in self._routes(tenant) if SEVERITY[r['min_severity']] <= level
                  and (r['site_id'] is None or r['site_id'] == signal.get('site_id'))]
        channels = {r.id: r.state for r in self.p.store.read().list(tenant, CHANNEL) if r.state['enabled']}
        sent, payload = 0, self.message(signal)
        notifier = self._notifications(tenant, list(channels.values())) if channels else None
        for route in routes:
            people = self.recipients(tenant, signal.get('site_id'), route['roles'])
            for person in people:
                sent += self._inbox(tenant, person, signal)
            for cid in route['channels']:
                if cid == 'in_app' or cid not in channels or notifier is None:
                    continue
                kind = channels[cid]['kind']
                targets = [self._email(tenant, p) for p in people] if kind == 'email' else [channels[cid]['name']]
                for target in filter(None, targets):
                    out = self._send(notifier, tenant, target, cid, payload, f"{signal['signal_id']}|{signal['severity']}|{target}|{cid}")
                    sent += 0 if out.get('duplicate') else 1
        self._record(tenant, signal['signal_id'], sent, signal['severity'])
        return {'sent': sent, 'routes': [r['route_id'] for r in routes]}

    def on_triage_ready(self, tenant: str, signal: dict[str, Any]) -> dict[str, Any]:
        updated = 0
        with self.p.store.transaction('alert-dispatcher') as tx:
            for rec in tx.list(tenant, INBOX, lambda s: s['signal_id'] == signal['signal_id']):
                if any(u['kind'] == 'triage_ready' for u in rec.state['updates']):
                    continue
                tx.put(tenant, INBOX, rec.id, {**rec.state, 'read_at': None, 'updates': [*rec.state['updates'],
                       {'kind': 'triage_ready', 'at': iso(utc_now()), 'text': 'The assistant’s triage is ready'}]},
                       expected_revision=rec.revision, action='alert_triage_ready')
                updated += 1
        channels = {r.id: r.state for r in self.p.store.read().list(tenant, CHANNEL) if r.state['enabled']}
        if channels:
            notifier = self._notifications(tenant, list(channels.values()))
            payload = self.message(signal, update='The assistant’s triage is ready to review.')
            for n in self.p.store.read().list(tenant, 'notification', lambda s: s.get('notice_type') == 'deviation_signal'
                                              and s.get('case_id') == signal['signal_id'] and s.get('status') == 'sent'):
                if n.state['channel'] in channels:
                    out = self._send(notifier, tenant, n.state['recipient'], n.state['channel'], payload,
                                     f"{signal['signal_id']}|triage|{n.state['recipient']}|{n.state['channel']}")
                    updated += 0 if out.get('duplicate') else 1
        return {'updated': updated}

    def _send(self, notifier, tenant, recipient, channel_id, payload, key) -> dict[str, Any]:
        try:
            # case_id carries the signal id so triage updates can find earlier sends.
            return notifier.send(self._service(tenant), recipient, channel_id, payload, owner='alert-dispatcher',
                                 idempotency_key=key, notice_type='deviation_signal',
                                 case_id=key.split('|', 1)[0])
        except (ChannelError, ValueError) as exc:
            return {'status': 'failed', 'detail': str(exc)}

    def _inbox(self, tenant: str, person: str, signal: dict[str, Any]) -> int:
        iid = 'inbox_' + _key(tenant, signal['signal_id'], signal['severity'], person)
        message = self.message(signal)
        try:
            with self.p.store.transaction('alert-dispatcher') as tx:
                if tx.get(tenant, INBOX, iid) is not None:
                    return 0
                tx.put(tenant, INBOX, iid, {
                    'inbox_id': iid, 'recipient_id': person, 'signal_id': signal['signal_id'], 'site_id': signal.get('site_id'),
                    'severity': signal['severity'], 'kind': signal.get('kind'), 'title': message['subject'],
                    'rule': signal.get('rule', ''), 'subject': signal.get('subject'), 'link': f"/signals/?id={signal['signal_id']}",
                    'created_at': iso(utc_now()), 'read_at': None, 'updates': []},
                    expected_revision=None, action='alert_inbox', event_type='notification.inbox',
                    event_payload={'inbox_id': iid, 'recipient_id': person, 'signal_id': signal['signal_id']})
        except ConflictError:
            return 0
        return 1

    def _record(self, tenant: str, signal_id: str, sent: int, severity: str | None = None) -> None:
        for _ in range(3):  # the signal may be updated concurrently by detection or triage
            try:
                with self.p.store.transaction('alert-dispatcher') as tx:
                    rec = tx.get(tenant, SIGNAL, signal_id)
                    if rec is None:
                        return
                    alerts = rec.state.get('alerts') or {'sent': 0, 'last_at': None}
                    tx.put(tenant, SIGNAL, signal_id, {**rec.state, 'alerts': {'sent': alerts['sent'] + sent,
                           'last_at': iso(utc_now()) if sent else alerts['last_at'],
                           # The follow-up sweep re-runs alerting only when severity rose past what was alerted.
                           'severity': severity or alerts.get('severity')}},
                           expected_revision=rec.revision, action='record_signal_alerts')
                return
            except ConflictError:
                continue

    # --- inbox ----------------------------------------------------------------------
    def inbox(self, ctx: AccessContext, *, limit: int = 50) -> dict[str, Any]:
        items = [r.state for r in self.p.store.read().list(ctx.tenant_id, INBOX, lambda s: s['recipient_id'] == ctx.actor_id)]
        last = lambda s: max([s['created_at'], *[u['at'] for u in s['updates']]])
        items.sort(key=last, reverse=True)
        items.sort(key=lambda s: s['read_at'] is not None)  # stable: unread first, newest first within each
        return {'items': items[:limit], 'unread': sum(1 for s in items if s['read_at'] is None)}

    def mark_read(self, ctx: AccessContext, inbox_id: str) -> dict[str, Any]:
        with self.p.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, INBOX, inbox_id)
            if rec.state['recipient_id'] != ctx.actor_id:
                raise PermissionError('this notification belongs to someone else')
            state = {**rec.state, 'read_at': rec.state['read_at'] or iso(utc_now())}
            tx.put(ctx.tenant_id, INBOX, inbox_id, state, expected_revision=rec.revision, action='read_alert')
        return state


def alert_routes(app, platform, ctx_dep) -> None:
    from fastapi import Depends, HTTPException
    from pydantic import BaseModel

    def service() -> AlertService:
        if getattr(platform, 'alerts', None) is None:
            platform.alerts = AlertService(platform)
        return platform.alerts

    def guard(fn):
        try:
            return fn()
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    class TestIn(BaseModel):
        recipient: str | None = None

    @app.get('/v1/notifications')
    def notifications(ctx: AccessContext = Depends(ctx_dep)):
        return service().inbox(ctx)

    @app.post('/v1/notifications/{inbox_id}/read')
    def read(inbox_id: str, ctx: AccessContext = Depends(ctx_dep)):
        return guard(lambda: service().mark_read(ctx, inbox_id))

    @app.get('/v1/alert-channels')
    def list_channels(ctx: AccessContext = Depends(ctx_dep)):
        return {'channels': guard(lambda: service().channels(ctx))}

    @app.post('/v1/alert-channels')
    def save_channel(body: dict, ctx: AccessContext = Depends(ctx_dep)):
        return guard(lambda: service().save_channel(ctx, body))

    @app.post('/v1/alert-channels/{channel_id}/test')
    def test_channel(channel_id: str, body: TestIn | None = None, ctx: AccessContext = Depends(ctx_dep)):
        out = guard(lambda: service().test_channel(ctx, channel_id, (body or TestIn()).recipient))
        return {k: out.get(k) for k in ('status', 'channel', 'recipient', 'attempts')}

    @app.get('/v1/alert-routes')
    def list_routes(ctx: AccessContext = Depends(ctx_dep)):
        return {'routes': guard(lambda: service().routes(ctx))}

    @app.post('/v1/alert-routes')
    def save_route(body: dict, ctx: AccessContext = Depends(ctx_dep)):
        return guard(lambda: service().save_route(ctx, body))
