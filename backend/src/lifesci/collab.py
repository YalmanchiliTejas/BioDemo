"""Triggers, notification delivery, procedure-timed notices and remote-assistance sessions.

Implements LS-022 (event/schedule/alarm/file-change triggers; email, Slack, Teams, SMS and
WhatsApp channel adapters enabled only by organization config), LS-061 (notification owner,
payload revision, attempts, provider receipt and an explicit unknown outcome that is reconciled
rather than resent), LS-072 (deadline-driven initial notice that never waits for complete
evidence, with separate follow-up deliveries), LS-037 (participant access check and
session-to-case link), LS-038 (annotation records with declared device support) and LS-039
(external expert limited to one case and named media).

No video transport is built: sessions sit behind a ``MediaProvider`` adapter (an enterprise media
service is integrated later). Annotation tools are recorded as data; none is device-tested, and
AR/walkie-talkie tools are declared device-dependent and refused. Agents may not send
notifications directly; they propose ``send_notification`` through ActionService.
"""

from __future__ import annotations

import fnmatch
import hashlib
import operator
import smtplib
import socket
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from .identity import AccessContext, IdentityService
from .ids import content_hash, iso, new_id, parse_iso, utc_now
from .store import ConflictError, RecordStore, Transaction

# --- LS-022: triggers -------------------------------------------------------------------------------

TRIGGER_KINDS = ("event", "schedule", "alarm", "file_change")
ACTION_TYPES = ("create_task", "notify", "start_mission")
_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq, "ne": operator.ne, "gt": lambda a, b: a is not None and a > b,
    "ge": lambda a, b: a is not None and a >= b, "lt": lambda a, b: a is not None and a < b,
    "le": lambda a, b: a is not None and a <= b, "in": lambda a, b: a in b,
    "exists": lambda a, b: (a is not None) == bool(b)}
ActionHandler = Callable[[AccessContext, dict[str, Any], dict[str, Any]], dict[str, Any]]


def _dig(doc: dict[str, Any], path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _digest_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:20]


class TriggerService:
    """Declarative triggers whose firings are deduplicated per (trigger, event id / time window / episode).

    A firing is claimed before its action runs, so an action is at-most-once; a claimed firing that never
    completed stays visible with status ``started``. Handlers are injected for ``notify`` and
    ``start_mission``; ``create_task`` is built in.
    """

    def __init__(self, store: RecordStore, identity: IdentityService,
                 handlers: dict[str, ActionHandler] | None = None) -> None:
        self.store, self.identity = store, identity
        self.handlers: dict[str, ActionHandler] = {"create_task": self._create_task, **(handlers or {})}

    def register(self, ctx: AccessContext, trigger_id: str, kind: str, config: dict[str, Any], action: dict[str, Any],
                 *, now: datetime | None = None, site_id: str | None = None) -> dict[str, Any]:
        self.identity.require(ctx, "configure", "trigger", trigger_id, site_id=site_id)
        if kind not in TRIGGER_KINDS:
            raise ValueError(f"kind must be one of {TRIGGER_KINDS}")
        if action.get("type") not in ACTION_TYPES:
            raise ValueError(f"action type must be one of {ACTION_TYPES}")
        self._validate(kind, config)
        state = {"trigger_id": trigger_id, "kind": kind, "config": config, "action": action, "site_id": site_id,
                 "active": True, "created_at": iso(now or utc_now()), "latched": False, "episode": 0,
                 "last_digest": None, "baselined": False}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, "trigger", trigger_id, state, expected_revision=None, action="register_trigger",
                         event_type="trigger.registered", event_payload={"trigger_id": trigger_id, "kind": kind})
        return {**rec.state, "revision": rec.revision}

    @staticmethod
    def _validate(kind: str, config: dict[str, Any]) -> None:
        if kind == "event":
            if not config.get("event_type"):
                raise ValueError("event trigger requires event_type")
            for cond in config.get("where", []):
                if cond.get("op") not in _OPS or "field" not in cond:
                    raise ValueError(f"bad predicate {cond}")
        elif kind == "schedule":
            if ("every_minutes" in config) == ("daily_at" in config):
                raise ValueError("schedule requires exactly one of every_minutes or daily_at")
            if "every_minutes" in config and int(config["every_minutes"]) <= 0:
                raise ValueError("every_minutes must be positive")
            if "daily_at" in config:
                dtime.fromisoformat(config["daily_at"])
        elif kind == "alarm":
            if not config.get("signal") or config.get("op") not in ("gt", "ge", "lt", "le") or "threshold" not in config:
                raise ValueError("alarm requires signal, op (gt|ge|lt|le) and threshold")
        elif kind == "file_change" and not config.get("path"):
            raise ValueError("file_change requires path")

    def deactivate(self, ctx: AccessContext, trigger_id: str) -> None:
        self.identity.require(ctx, "configure", "trigger", trigger_id)
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "trigger", trigger_id)
            tx.put(ctx.tenant_id, "trigger", trigger_id, {**rec.state, "active": False}, expected_revision=rec.revision,
                   action="deactivate_trigger")

    def _active(self, ctx: AccessContext, kind: str) -> list[Any]:
        return self.store.read().list(ctx.tenant_id, "trigger", lambda s: s["active"] and s["kind"] == kind)

    # --- event ---------------------------------------------------------------------------------------
    def process_events(self, ctx: AccessContext, limit: int = 500) -> list[dict[str, Any]]:
        cur = self.store.read().get(ctx.tenant_id, "trigger_cursor", "events")
        after = cur.state["seq"] if cur else 0
        events = self.store.events_since(ctx.tenant_id, after, limit)
        triggers = self._active(ctx, "event")
        fired = []
        for seq, ev in events:
            if ev.type.startswith("trigger."):
                continue
            doc = {"type": ev.type, "aggregate_kind": ev.aggregate_kind, "aggregate_id": ev.aggregate_id,
                   "revision": ev.revision, "payload": ev.payload, "event_id": ev.event_id}
            for t in triggers:
                cfg = t.state["config"]
                if t.state["site_id"] and ev.payload.get("site_id") != t.state["site_id"]:
                    continue
                if fnmatch.fnmatch(ev.type, cfg["event_type"]) and all(
                        _OPS[c["op"]](_dig(doc, c["field"]), c.get("value")) for c in cfg.get("where", [])):
                    firing = self._fire(ctx, t, ev.event_id, {"event_id": ev.event_id, "event_type": ev.type, "seq": seq,
                                                              "aggregate": f"{ev.aggregate_kind}:{ev.aggregate_id}"})
                    if firing:
                        fired.append(firing)
        if events:
            with self.store.transaction(ctx.actor_id) as tx:
                latest = tx.get(ctx.tenant_id, "trigger_cursor", "events")
                tx.put(ctx.tenant_id, "trigger_cursor", "events", {"seq": events[-1][0]},
                       expected_revision=latest.revision if latest else None, action="advance_trigger_cursor")
        return fired

    # --- schedule ------------------------------------------------------------------------------------
    def tick(self, ctx: AccessContext, now: datetime) -> list[dict[str, Any]]:
        """Fire due schedules once per scheduled instant; missed instants collapse into the latest one."""
        fired = []
        for t in self._active(ctx, "schedule"):
            cfg, created = t.state["config"], parse_iso(t.state["created_at"])
            if "every_minutes" in cfg:
                period = int(cfg["every_minutes"]) * 60
                instant = datetime.fromtimestamp(int(now.timestamp() // period) * period, timezone.utc)
            else:
                at = dtime.fromisoformat(cfg["daily_at"])
                instant = datetime.combine(now.astimezone(timezone.utc).date(), at, tzinfo=timezone.utc)
                if instant > now:
                    instant -= timedelta(days=1)
            if instant < created or instant > now:
                continue
            firing = self._fire(ctx, t, iso(instant), {"scheduled_for": iso(instant), "tick_at": iso(now)})
            if firing:
                fired.append(firing)
        return fired

    # --- alarm ---------------------------------------------------------------------------------------
    def observe(self, ctx: AccessContext, signal: str, value: float, at: datetime | None = None) -> list[dict[str, Any]]:
        """Threshold alarm with latching: one firing per excursion until the value returns to normal."""
        fired = []
        for t in self._active(ctx, "alarm"):
            cfg = t.state["config"]
            if cfg["signal"] != signal:
                continue
            breach = _OPS[cfg["op"]](value, cfg["threshold"])
            if breach == t.state["latched"]:
                continue
            episode = t.state["episode"] + (1 if breach else 0)
            with self.store.transaction(ctx.actor_id) as tx:
                tx.put(ctx.tenant_id, "trigger", t.id, {**t.state, "latched": breach, "episode": episode},
                       expected_revision=t.revision, action="alarm_latch" if breach else "alarm_clear")
            if breach:
                firing = self._fire(ctx, t, f"episode-{episode}", {"signal": signal, "value": value, "threshold": cfg["threshold"],
                                                                  "observed_at": iso(at or utc_now())})
                if firing:
                    fired.append(firing)
        return fired

    # --- file change ------------------------------------------------------------------------------------
    def check_files(self, ctx: AccessContext) -> list[dict[str, Any]]:
        fired = []
        for t in self._active(ctx, "file_change"):
            path = Path(t.state["config"]["path"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"
            if digest == t.state["last_digest"] and t.state["baselined"]:
                continue
            first = not t.state["baselined"]
            with self.store.transaction(ctx.actor_id) as tx:
                tx.put(ctx.tenant_id, "trigger", t.id, {**t.state, "last_digest": digest, "baselined": True},
                       expected_revision=t.revision, action="file_digest")
            if first and not t.state["config"].get("fire_on_first"):
                continue
            firing = self._fire(ctx, t, digest, {"path": str(path), "digest": digest, "previous": t.state["last_digest"]})
            if firing:
                fired.append(firing)
        return fired

    # --- firing --------------------------------------------------------------------------------------
    def _fire(self, ctx: AccessContext, trigger: Any, dedupe_key: str, context: dict[str, Any]) -> dict[str, Any] | None:
        fid = f"{trigger.id}:{_digest_key(dedupe_key)}"
        state = {"firing_id": fid, "trigger_id": trigger.id, "kind": trigger.state["kind"], "dedupe_key": dedupe_key,
                 "context": context, "action": trigger.state["action"], "status": "started", "result": None,
                 "fired_at": iso(utc_now())}
        try:
            with self.store.transaction(ctx.actor_id) as tx:
                rec = tx.put(ctx.tenant_id, "trigger_firing", fid, state, expected_revision=None, action="fire_trigger",
                             event_type="trigger.fired", event_payload={"trigger_id": trigger.id, "dedupe_key": dedupe_key})
        except ConflictError:
            return None
        handler = self.handlers.get(trigger.state["action"]["type"])
        try:
            if handler is None:
                raise LookupError(f"no handler configured for {trigger.state['action']['type']}")
            result, status = handler(ctx, trigger.state["action"], state), "completed"
        except Exception as exc:
            result, status = {"error": f"{type(exc).__name__}: {exc}"}, "failed"
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.require(ctx.tenant_id, "trigger_firing", fid)
            out = tx.put(ctx.tenant_id, "trigger_firing", fid, {**cur.state, "status": status, "result": result},
                         expected_revision=cur.revision, action=f"firing_{status}")
        return out.state

    def _create_task(self, ctx: AccessContext, action: dict[str, Any], firing: dict[str, Any]) -> dict[str, Any]:
        task_id = f"task_{_digest_key(firing['firing_id'])}"
        state = {"task_id": task_id, "title": action.get("title", f"Triggered by {firing['trigger_id']}"),
                 "owner": action.get("owner"), "status": "open", "source_firing": firing["firing_id"],
                 "context": firing["context"], "created_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "task", task_id, state, expected_revision=None, action="create_task",
                   event_type="task.created", event_payload={"task_id": task_id, "owner": action.get("owner")})
        return {"task_id": task_id}

    def firings(self, ctx: AccessContext, trigger_id: str | None = None) -> list[dict[str, Any]]:
        self.identity.require(ctx, "read", "trigger")
        return [r.state for r in self.store.read().list(ctx.tenant_id, "trigger_firing",
                                                        lambda s: trigger_id is None or s["trigger_id"] == trigger_id)]


# --- LS-022 / LS-061: channels and notifications ------------------------------------------------------


@dataclass(frozen=True)
class ChannelMessage:
    recipient: str
    subject: str
    body: str
    idempotency_key: str


class ChannelError(Exception):
    """The provider definitively did not accept the message."""


class ChannelUnknown(Exception):
    """The provider may or may not have accepted the message (lost response, timeout)."""


class ChannelDisabled(ChannelError):
    pass


class ChannelAdapter(Protocol):
    name: str

    def enabled(self) -> bool: ...
    def send(self, message: ChannelMessage) -> dict[str, Any]: ...


class _ConfiguredChannel:
    name = ""
    required: tuple[str, ...] = ()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def enabled(self) -> bool:
        return all(self.config.get(k) for k in self.required)

    def _require_enabled(self) -> None:
        if not self.enabled():
            raise ChannelDisabled(f"{self.name} channel is not configured for this organization")


class _HttpChannel(_ConfiguredChannel):
    def __init__(self, config: dict[str, Any] | None = None, transport: Callable[..., Any] | None = None) -> None:
        super().__init__(config)
        self.transport = transport

    def build_request(self, message: ChannelMessage) -> dict[str, Any]:
        raise NotImplementedError

    def send(self, message: ChannelMessage) -> dict[str, Any]:
        self._require_enabled()
        request = self.build_request(message)
        try:
            resp = self._transport()("POST", request.pop("url"), timeout=10, **request)
        except Exception as exc:
            if type(exc).__module__.startswith("httpx") and type(exc).__name__ in ("ConnectError", "ConnectTimeout", "InvalidURL"):
                raise ChannelError(f"not sent: {exc}") from exc
            raise ChannelUnknown(f"{type(exc).__name__}: {exc}") from exc
        status = int(resp.status_code)
        if 200 <= status < 300:
            return {"provider": self.name, "http_status": status, "provider_message_id": self._message_id(resp)}
        if status >= 500 or status == 429:
            raise ChannelUnknown(f"provider status {status}")
        raise ChannelError(f"provider rejected with status {status}")

    def _transport(self) -> Callable[..., Any]:
        if self.transport:
            return self.transport
        import httpx
        return httpx.request

    def _message_id(self, resp: Any) -> str | None:
        try:
            return self._extract_id(resp.json())
        except Exception:
            return None

    def _extract_id(self, doc: Any) -> str | None:
        return None


class SlackWebhookAdapter(_HttpChannel):
    name, required = "slack", ("webhook_url",)

    def build_request(self, m: ChannelMessage) -> dict[str, Any]:
        return {"url": self.config["webhook_url"], "json": {"text": f"*{m.subject}*\n{m.body}"}}


class TeamsWebhookAdapter(_HttpChannel):
    name, required = "teams", ("webhook_url",)

    def build_request(self, m: ChannelMessage) -> dict[str, Any]:
        return {"url": self.config["webhook_url"], "json": {"@type": "MessageCard", "@context": "https://schema.org/extensions",
                                                           "summary": m.subject, "title": m.subject, "text": m.body}}


class TwilioSmsAdapter(_HttpChannel):
    name, required = "sms", ("account_sid", "auth_token", "from_number")

    def build_request(self, m: ChannelMessage) -> dict[str, Any]:
        sid = self.config["account_sid"]
        return {"url": f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                "data": {"To": m.recipient, "From": self.config["from_number"], "Body": f"{m.subject}: {m.body}"},
                "auth": (sid, self.config["auth_token"])}

    def _extract_id(self, doc: Any) -> str | None:
        return doc.get("sid")


class WhatsAppAdapter(_HttpChannel):
    name, required = "whatsapp", ("phone_number_id", "access_token")

    def build_request(self, m: ChannelMessage) -> dict[str, Any]:
        version = self.config.get("api_version", "v19.0")
        return {"url": f"https://graph.facebook.com/{version}/{self.config['phone_number_id']}/messages",
                "headers": {"Authorization": f"Bearer {self.config['access_token']}"},
                "json": {"messaging_product": "whatsapp", "to": m.recipient, "type": "text",
                         "text": {"body": f"{m.subject}\n{m.body}"}}}

    def _extract_id(self, doc: Any) -> str | None:
        return (doc.get("messages") or [{}])[0].get("id")


class EmailSMTPAdapter(_ConfiguredChannel):
    name, required = "email", ("host", "port", "from_addr")

    def __init__(self, config: dict[str, Any] | None = None, smtp_factory: Callable[..., Any] = smtplib.SMTP) -> None:
        super().__init__(config)
        self.smtp_factory = smtp_factory

    def build_message(self, m: ChannelMessage) -> EmailMessage:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.config["from_addr"], m.recipient, m.subject
        msg["Message-ID"] = f"<{_digest_key(m.idempotency_key)}@{self.config['host']}>"
        msg.set_content(m.body)
        return msg

    def send(self, message: ChannelMessage) -> dict[str, Any]:
        self._require_enabled()
        msg = self.build_message(message)
        try:
            with self.smtp_factory(self.config["host"], int(self.config["port"]), timeout=15) as smtp:
                if self.config.get("starttls"):
                    smtp.starttls()
                if self.config.get("username"):
                    smtp.login(self.config["username"], self.config.get("password", ""))
                smtp.send_message(msg)
        except (ConnectionRefusedError, socket.gaierror, smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused) as exc:
            raise ChannelError(f"{type(exc).__name__}: {exc}") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise ChannelUnknown(f"{type(exc).__name__}: {exc}") from exc
        return {"provider": "smtp", "provider_message_id": msg["Message-ID"]}


class InMemoryChannel:
    """Test channel with scripted failures. ``lose_response_next`` delivers but raises ChannelUnknown."""

    def __init__(self, name: str = "memory", enabled: bool = True) -> None:
        self.name, self._enabled = name, enabled
        self.sent: list[ChannelMessage] = []
        self.fail_next = self.lose_response_next = self.drop_next = 0

    def enabled(self) -> bool:
        return self._enabled

    def send(self, message: ChannelMessage) -> dict[str, Any]:
        if not self._enabled:
            raise ChannelDisabled(f"{self.name} not configured")
        if self.fail_next:
            self.fail_next -= 1
            raise ChannelError("provider rejected")
        if self.drop_next:
            self.drop_next -= 1
            raise ChannelUnknown("timeout before delivery")
        self.sent.append(message)
        if self.lose_response_next:
            self.lose_response_next -= 1
            raise ChannelUnknown("response lost")
        return {"provider": self.name, "provider_message_id": f"msg-{len(self.sent)}"}

    def lookup(self, idempotency_key: str) -> dict[str, Any] | None:
        for i, m in enumerate(self.sent, 1):
            if m.idempotency_key == idempotency_key:
                return {"provider": self.name, "provider_message_id": f"msg-{i}"}
        return None


class NotificationService:
    """Notification records with owner, payload revision/hash, attempts, provider receipt and final or unknown outcome."""

    def __init__(self, store: RecordStore, identity: IdentityService, channels: Sequence[ChannelAdapter]) -> None:
        self.store, self.identity = store, identity
        self.channels = {c.name: c for c in channels}

    @staticmethod
    def notification_id(tenant_id: str, idempotency_key: str) -> str:
        return "ntf_" + hashlib.sha256(f"{tenant_id}|{idempotency_key}".encode()).hexdigest()[:24]

    def send(self, ctx: AccessContext, recipient: str, channel: str, payload: dict[str, Any], owner: str,
             idempotency_key: str, *, notice_type: str = "notification", case_id: str | None = None,
             payload_revision: int | None = None) -> dict[str, Any]:
        if ctx.actor_kind == "agent":
            raise PermissionError("agents propose send_notification through ActionService; they cannot send directly")
        self.identity.require(ctx, "comment", "notification")
        if channel not in self.channels:
            raise ValueError(f"unknown channel {channel}")
        nid = self.notification_id(ctx.tenant_id, idempotency_key)
        phash = content_hash(payload)
        state = {"notification_id": nid, "idempotency_key": idempotency_key, "recipient": recipient, "channel": channel,
                 "owner": owner, "notice_type": notice_type, "case_id": case_id, "payload": payload,
                 "payload_revision": payload_revision or payload.get("revision", 1), "payload_hash": phash,
                 "status": "pending", "attempts": [{"n": 1, "started_at": iso(utc_now()), "outcome": "in_flight"}],
                 "receipt": None, "created_by": ctx.actor_id, "created_at": iso(utc_now())}
        try:
            with self.store.transaction(ctx.actor_id) as tx:
                tx.put(ctx.tenant_id, "notification", nid, state, expected_revision=None, action="create_notification",
                       event_type="notification.pending", event_payload={"notification_id": nid, "case_id": case_id, "notice_type": notice_type})
        except ConflictError:
            existing = self.get(ctx, nid)
            if existing["payload_hash"] != phash or existing["recipient"] != recipient:
                raise ValueError("idempotency key already used for a different notification") from None
            return {**existing, "duplicate": True}
        return self._dispatch(ctx, nid)

    def _dispatch(self, ctx: AccessContext, nid: str) -> dict[str, Any]:
        rec = self.store.read().require(ctx.tenant_id, "notification", nid)
        s = rec.state
        message = ChannelMessage(s["recipient"], s["payload"].get("subject", ""), s["payload"].get("body", ""), s["idempotency_key"])
        try:
            receipt = self.channels[s["channel"]].send(message)
            status, detail = "sent", "accepted"
        except ChannelDisabled as exc:
            receipt, status, detail = None, "failed", f"disabled: {exc}"
        except ChannelError as exc:
            receipt, status, detail = None, "failed", str(exc)
        except ChannelUnknown as exc:
            receipt, status, detail = None, "unknown", str(exc)
        return self._finish(ctx, nid, status, receipt, detail)

    def _finish(self, ctx: AccessContext, nid: str, status: str, receipt: dict[str, Any] | None, detail: str,
                *, reconciled: bool = False) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "notification", nid)
            attempts = [dict(a) for a in rec.state["attempts"]]
            if reconciled:
                attempts.append({"n": len(attempts) + 1, "at": iso(utc_now()), "outcome": f"reconciled_{status}", "detail": detail})
            else:
                attempts[-1] = {**attempts[-1], "finished_at": iso(utc_now()), "outcome": status, "detail": detail}
            out = tx.put(ctx.tenant_id, "notification", nid, {**rec.state, "status": status, "receipt": receipt or rec.state["receipt"],
                                                              "attempts": attempts, "updated_at": iso(utc_now())},
                         expected_revision=rec.revision, action=f"notification_{status}",
                         event_type=f"notification.{status}", event_payload={
                             "notification_id": nid, "case_id": rec.state["case_id"], "notice_type": rec.state["notice_type"]})
        return {**out.state, "revision": out.revision}

    def retry(self, ctx: AccessContext, notification_id: str) -> dict[str, Any]:
        """Re-send only a known failure. A sent message is never re-sent; unknown outcomes must be reconciled first."""
        if ctx.actor_kind == "agent":
            raise PermissionError("agents cannot send notifications directly")
        rec = self.store.read().require(ctx.tenant_id, "notification", notification_id)
        status = rec.state["status"]
        if status == "sent":
            return {**rec.state, "duplicate": True}
        if status in ("pending", "unknown"):
            raise ValueError(f"notification is {status}: reconcile with the provider before any retry")
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.require(ctx.tenant_id, "notification", notification_id)
            tx.put(ctx.tenant_id, "notification", notification_id, {
                **cur.state, "status": "pending",
                "attempts": [*cur.state["attempts"], {"n": len(cur.state["attempts"]) + 1, "started_at": iso(utc_now()), "outcome": "in_flight"}]},
                   expected_revision=cur.revision, action="retry_notification")
        return self._dispatch(ctx, notification_id)

    def reconcile(self, ctx: AccessContext, notification_id: str, lookup: Callable[[str], dict[str, Any] | None],
                  *, authoritative_absence: bool = False) -> dict[str, Any]:
        """Resolve pending/unknown via a provider lookup by idempotency key.

        Absence of a record is conclusive (status failed, safe to retry) only when the lookup is authoritative.
        """
        rec = self.store.read().require(ctx.tenant_id, "notification", notification_id)
        if rec.state["status"] not in ("pending", "unknown"):
            return {**rec.state, "duplicate": True}
        found = lookup(rec.state["idempotency_key"])
        if found:
            return self._finish(ctx, notification_id, "sent", found, "provider confirms delivery", reconciled=True)
        if authoritative_absence:
            return self._finish(ctx, notification_id, "failed", None, "provider has no record of the message", reconciled=True)
        return self._finish(ctx, notification_id, "unknown", None, "lookup inconclusive; manual confirmation required", reconciled=True)

    def get(self, ctx: AccessContext, notification_id: str) -> dict[str, Any]:
        self.identity.require(ctx, "read", "notification")
        rec = self.store.read().require(ctx.tenant_id, "notification", notification_id)
        return {**rec.state, "revision": rec.revision}

    def list(self, ctx: AccessContext, case_id: str | None = None) -> list[dict[str, Any]]:
        self.identity.require(ctx, "read", "notification")
        return [r.state for r in self.store.read().list(ctx.tenant_id, "notification",
                                                        lambda s: case_id is None or s["case_id"] == case_id)]


# --- LS-072: procedure-timed notices --------------------------------------------------------------------


@dataclass(frozen=True)
class NotificationPolicy:
    policy_id: str
    initial_notice_hours: float
    channel: str
    recipients: tuple[str, ...]
    grace_minutes: int = 0
    follow_up: str = "review_completion"

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "recipients": list(self.recipients)}


class NoticeScheduler:
    """Deadline-driven initial notices plus separate follow-up findings and review-package deliveries."""

    def __init__(self, store: RecordStore, identity: IdentityService, notifications: NotificationService) -> None:
        self.store, self.identity, self.notifications = store, identity, notifications

    def schedule_initial(self, ctx: AccessContext, case_id: str, event_time: datetime, policy: NotificationPolicy,
                         *, owner: str) -> dict[str, Any]:
        self.identity.require(ctx, "comment", "notification")
        due = event_time + timedelta(hours=policy.initial_notice_hours)
        state = {"schedule_id": f"{case_id}:initial", "case_id": case_id, "event_time": iso(event_time), "due_at": iso(due),
                 "policy": policy.to_dict(), "owner": owner, "status": "scheduled", "notification_ids": [],
                 "sent_late": None, "created_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, "notice_schedule", state["schedule_id"], state, expected_revision=None,
                         action="schedule_initial_notice", event_type="notice.scheduled",
                         event_payload={"case_id": case_id, "due_at": state["due_at"]})
        return {**rec.state, "revision": rec.revision}

    def _case_facts(self, ctx: AccessContext, case_id: str) -> dict[str, Any]:
        rec = self.store.read().get(ctx.tenant_id, "case", case_id)
        if rec is None:
            return {"known": {}, "unknown": ["case record not found"], "missing_evidence": []}
        if not self.identity.check(ctx, "read", "case", case_id, site_id=rec.state.get("site_id")):
            return {"known": {}, "unknown": ["case details not readable by sender"], "missing_evidence": []}
        return {"known": rec.state.get("known_facts", {}),
                "unknown": list(rec.state.get("open_questions", [])),
                "missing_evidence": list(rec.state.get("missing_evidence", []))}

    def build_initial(self, ctx: AccessContext, schedule: dict[str, Any]) -> dict[str, Any]:
        facts = self._case_facts(ctx, schedule["case_id"])
        unknown = [*facts["unknown"], *[f"evidence not yet available: {m}" for m in facts["missing_evidence"]]]
        statement = (f"Initial notice for case {schedule['case_id']} (event {schedule['event_time']}). "
                     f"Known: {facts['known'] or 'nothing confirmed yet'}. "
                     f"Not yet known: {unknown or 'nothing outstanding'}. Findings will follow separately.")
        return {"subject": f"Initial notice: case {schedule['case_id']}", "body": statement, "known": facts["known"],
                "unknown": unknown, "evidence_complete": not unknown, "revision": 1}

    def run_due(self, ctx: AccessContext, now: datetime) -> list[dict[str, Any]]:
        """Send every due initial notice regardless of evidence completeness; retries known failures."""
        out = []
        for rec in self.store.read().list(ctx.tenant_id, "notice_schedule", lambda s: s["status"] in ("scheduled", "attention")):
            s = rec.state
            if parse_iso(s["due_at"]) > now:
                continue
            payload, policy = self.build_initial(ctx, s), s["policy"]
            results = []
            for recipient in policy["recipients"]:
                n = self.notifications.send(ctx, recipient, policy["channel"], payload, s["owner"],
                                            f"{s['case_id']}:initial:{recipient}", notice_type="initial", case_id=s["case_id"])
                if n.get("duplicate") and n["status"] == "failed":
                    n = self.notifications.retry(ctx, n["notification_id"])
                results.append(n)
            all_sent = all(n["status"] == "sent" for n in results)
            late = now > parse_iso(s["due_at"]) + timedelta(minutes=policy["grace_minutes"])
            with self.store.transaction(ctx.actor_id) as tx:
                cur = tx.require(ctx.tenant_id, "notice_schedule", rec.id)
                new = tx.put(ctx.tenant_id, "notice_schedule", rec.id, {
                    **cur.state, "status": "sent" if all_sent else "attention", "sent_late": late,
                    "notification_ids": [n["notification_id"] for n in results], "last_run_at": iso(now),
                    "evidence_complete_at_send": payload["evidence_complete"]},
                             expected_revision=cur.revision, action="run_initial_notice")
            out.append(new.state)
        return out

    def overdue(self, ctx: AccessContext, now: datetime) -> list[dict[str, Any]]:
        return [r.state for r in self.store.read().list(ctx.tenant_id, "notice_schedule", lambda s: s["status"] != "sent"
                                                        and parse_iso(s["due_at"]) + timedelta(minutes=s["policy"]["grace_minutes"]) < now)]

    def _follow_up(self, ctx: AccessContext, case_id: str, notice_type: str, subject: str, payload: dict[str, Any],
                   policy: NotificationPolicy, owner: str, revision: int) -> list[dict[str, Any]]:
        out = []
        for recipient in policy.recipients:
            n = self.notifications.send(ctx, recipient, policy.channel, {**payload, "subject": subject, "revision": revision}, owner,
                                        f"{case_id}:{notice_type}:r{revision}:{recipient}", notice_type=notice_type,
                                        case_id=case_id, payload_revision=revision)
            out.append(n)
        return out

    def send_findings(self, ctx: AccessContext, case_id: str, findings: dict[str, Any], policy: NotificationPolicy,
                      *, owner: str, revision: int = 1) -> list[dict[str, Any]]:
        return self._follow_up(ctx, case_id, "findings", f"Findings: case {case_id}",
                               {"body": f"Findings (revision {revision}): {findings}", "findings": findings}, policy, owner, revision)

    def send_review_package(self, ctx: AccessContext, case_id: str, package: dict[str, Any], policy: NotificationPolicy,
                            *, owner: str, revision: int = 1) -> list[dict[str, Any]]:
        return self._follow_up(ctx, case_id, "review_package", f"Review package: case {case_id}",
                               {"body": f"Review completed; package {package.get('package_id', '')} attached.", "package": package},
                               policy, owner, revision)

    def delivery_states(self, ctx: AccessContext, case_id: str) -> dict[str, dict[str, str]]:
        states: dict[str, dict[str, str]] = {}
        for n in self.notifications.list(ctx, case_id):
            states.setdefault(n["notice_type"], {})[n["recipient"]] = n["status"]
        return states


# --- LS-037 / LS-038 / LS-039: remote assistance ------------------------------------------------------------


class MediaProvider(Protocol):
    def create_room(self, session_id: str) -> dict[str, Any]: ...
    def join_token(self, room_id: str, participant_id: str, permissions: dict[str, Any]) -> str: ...
    def close_room(self, room_id: str) -> None: ...


class FakeMediaProvider:
    def __init__(self) -> None:
        self.rooms: dict[str, str] = {}
        self.tokens: list[tuple[str, str, dict[str, Any]]] = []
        self.closed: list[str] = []

    def create_room(self, session_id: str) -> dict[str, Any]:
        room = f"room-{len(self.rooms) + 1}"
        self.rooms[room] = session_id
        return {"room_id": room}

    def join_token(self, room_id: str, participant_id: str, permissions: dict[str, Any]) -> str:
        self.tokens.append((room_id, participant_id, permissions))
        return f"tok:{room_id}:{participant_id}"

    def close_room(self, room_id: str) -> None:
        self.closed.append(room_id)


class ToolUnavailable(Exception):
    pass


ANNOTATION_TOOLS: dict[str, dict[str, Any]] = {
    "chat": {"devices": ("browser", "tablet", "phone"), "status": "enabled"},
    "drawing": {"devices": ("browser", "tablet"), "status": "enabled"},
    "pointer": {"devices": ("browser", "tablet"), "status": "enabled"},
    "transcript": {"devices": ("browser",), "status": "enabled", "requires_recording": True},
    "ar_pointer": {"devices": ("ar_headset",), "status": "device_dependent"},
    "walkie_talkie": {"devices": ("ptt_handset", "ar_headset"), "status": "device_dependent"},
}
TOOL_DECLARATIONS = {k: {**v, "device_tested": False} for k, v in ANNOTATION_TOOLS.items()}


def supported_tools(device: str) -> list[str]:
    return sorted(k for k, v in ANNOTATION_TOOLS.items() if v["status"] == "enabled" and device in v["devices"])


class RemoteSessionService:
    """Sessions linked to a case; participant access is checked at creation, join, media and annotation time."""

    def __init__(self, store: RecordStore, identity: IdentityService, providers: dict[str, MediaProvider]) -> None:
        self.store, self.identity, self.providers = store, identity, providers

    # --- helpers --------------------------------------------------------------------------------------
    @staticmethod
    def _norm(p: Any) -> dict[str, Any]:
        d = {"actor_id": p} if isinstance(p, str) else dict(p)
        return {"actor_id": d["actor_id"], "kind": d.get("kind", "person"), "partner_org_id": d.get("partner_org_id")}

    def _pctx(self, tenant_id: str, p: dict[str, Any]) -> AccessContext:
        return self.identity.context_for(tenant_id, p["actor_id"], actor_kind=p["kind"], partner_org_id=p.get("partner_org_id"))

    def _session(self, ctx: AccessContext, session_id: str, tx: Transaction | None = None) -> Any:
        return (tx or self.store.read()).require(ctx.tenant_id, "remote_session", session_id)

    def _participant(self, session: dict[str, Any], actor_id: str) -> dict[str, Any]:
        for p in session["participants"]:
            if p["actor_id"] == actor_id:
                return p
        raise PermissionError(f"{actor_id} is not a participant in session {session['session_id']}")

    def _update(self, ctx: AccessContext, session_id: str, fn: Callable[[dict[str, Any]], dict[str, Any]], action: str,
                event_type: str | None = None) -> dict[str, Any]:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "remote_session", session_id)
            out = tx.put(ctx.tenant_id, "remote_session", session_id, fn(dict(rec.state)), expected_revision=rec.revision,
                         action=action, event_type=event_type, event_payload={"session_id": session_id, "case_id": rec.state["case_id"]})
        return {**out.state, "revision": out.revision}

    def _check_live(self, ctx: AccessContext, session: dict[str, Any], *, action: str = "read") -> dict[str, Any]:
        if session["status"] != "active":
            raise PermissionError(f"session is {session['status']}")
        p = self._participant(session, ctx.actor_id)
        if p.get("access_revoked_at"):
            raise PermissionError("session access has been revoked")
        self.identity.require(ctx, action, "case", session["case_id"], site_id=session.get("site_id"))
        return p

    def enforce_access(self, tenant_id: str) -> None:
        """Remove participants whose current case authority was revoked.

        Repeated removals cover old short-lived tokens on self-hosted providers.
        Provider failures stay visible and are retried on the next runtime tick.
        """
        for rec in self.store.read().list(tenant_id, "remote_session", lambda s: s["status"] in ("active", "ending_unknown")):
            state = rec.state
            provider = self.providers.get(state["media_provider"])
            if provider and state["status"] == "ending_unknown":
                try:
                    provider.close_room(state["room_id"])
                except OSError:
                    continue
                with self.store.transaction("media-access-monitor") as tx:
                    current = tx.require(tenant_id, "remote_session", rec.id)
                    tx.put(tenant_id, "remote_session", rec.id,
                           {**current.state, "status": "ended", "ended_at": iso(utc_now())},
                           expected_revision=current.revision, action="confirm_room_end")
                continue
            if not provider or not hasattr(provider, "remove_participant"):
                continue
            for participant in state["participants"]:
                ctx = self._pctx(tenant_id, participant)
                if self.identity.check(ctx, "read", "case", state["case_id"], site_id=state.get("site_id")):
                    continue
                try:
                    provider.remove_participant(state["room_id"], participant["actor_id"])
                    failure = None
                except OSError:
                    failure = "media access removal unconfirmed; retry pending"
                with self.store.transaction("media-access-monitor") as tx:
                    current = tx.require(tenant_id, "remote_session", rec.id)
                    updated = [{**p, "access_revoked_at": p.get("access_revoked_at") or iso(utc_now())}
                               if p["actor_id"] == participant["actor_id"] else p for p in current.state["participants"]]
                    if failure or not participant.get("access_revoked_at") or current.state.get("media_access_error"):
                        tx.put(tenant_id, "remote_session", rec.id, {**current.state, "participants": updated, "media_access_error": failure},
                               expected_revision=current.revision, action="enforce_media_access")

    # --- LS-037 -----------------------------------------------------------------------------------------
    def create(self, ctx: AccessContext, case_id: str, participants: Sequence[Any], media_provider: str = "external",
               *, site_id: str | None = None) -> dict[str, Any]:
        case = self.store.read().require(ctx.tenant_id, "case", case_id)
        if site_id is not None and site_id != case.state.get("site_id"):
            raise ValueError("session site must match its case")
        site_id = case.state.get("site_id")
        self.identity.require(ctx, "comment", "case", case_id, site_id=site_id)
        if media_provider not in self.providers:
            raise ValueError(f"unknown media provider {media_provider}")
        self.store.read().require(ctx.tenant_id, "case", case_id)
        people = [self._norm(p) for p in participants]
        if ctx.actor_id not in {p["actor_id"] for p in people}:
            people.insert(0, {"actor_id": ctx.actor_id, "kind": ctx.actor_kind, "partner_org_id": None})
        denied = [p["actor_id"] for p in people
                  if not self.identity.check(self._pctx(ctx.tenant_id, p), "read", "case", case_id, site_id=site_id)]
        if denied:
            raise PermissionError(f"participants without access to case {case_id}: {denied}")
        sid = new_id("rs")
        state = {"session_id": sid, "case_id": case_id, "site_id": site_id, "created_by": ctx.actor_id,
                 "media_provider": media_provider, "room_id": None, "status": "creating",
                 "participants": [{**p, "access_verified_at": iso(utc_now()), "consent": None, "joined_at": None,
                                   "media_ids": [], "grant_ids": []} for p in people],
                 "recording": {"enabled": False, "reason": None}, "created_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "remote_session", sid, state, expected_revision=None, action="create_session",
                   event_type="remote_session.created", event_payload={"session_id": sid, "case_id": case_id, "site_id": site_id})
            tx.add_edge(ctx.tenant_id, ("case", case_id), ("remote_session", sid), "assistance_session")
        return self.reconcile_creation(ctx, sid)

    def reconcile_creation(self, ctx: AccessContext, session_id: str) -> dict[str, Any]:
        state = self._session(ctx, session_id).state
        self.identity.require(ctx, "comment", "case", state["case_id"], site_id=state.get("site_id"))
        if ctx.actor_id != state["created_by"]:
            raise PermissionError("only the session initiator can reconcile room creation")
        if state["status"] == "active":
            return state
        if state["status"] not in ("creating", "creation_unknown"):
            raise ValueError("session is not awaiting room creation")
        try:
            room = self.providers[state["media_provider"]].create_room(session_id)
        except OSError:
            self._update(ctx, session_id, lambda s: {**s, "status": "creation_unknown"}, "room_creation_unconfirmed")
            raise
        return self._update(ctx, session_id, lambda s: {**s, "status": "active", "room_id": room["room_id"]}, "room_creation_confirmed")

    def sessions_for_case(self, ctx: AccessContext, case_id: str) -> list[dict[str, Any]]:
        tx = self.store.read()
        case = tx.require(ctx.tenant_id, "case", case_id)
        self.identity.require(ctx, "read", "case", case_id, site_id=case.state.get("site_id"), tx=tx)
        return [tx.require(ctx.tenant_id, k, i).state for k, i, rel in tx.edges_from(ctx.tenant_id, "case", case_id)
                if k == "remote_session"]

    def add_participant(self, ctx: AccessContext, session_id: str, participant: Any) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        if ctx.actor_id != s["created_by"]:
            raise PermissionError("only the session initiator can add participants")
        p = self._norm(participant)
        if not self.identity.check(self._pctx(ctx.tenant_id, p), "read", "case", s["case_id"], site_id=s.get("site_id")):
            raise PermissionError(f"{p['actor_id']} has no access to case {s['case_id']}")

        def add(state: dict[str, Any]) -> dict[str, Any]:
            if all(x["actor_id"] != p["actor_id"] for x in state["participants"]):
                state["participants"] = [*state["participants"], {**p, "access_verified_at": iso(utc_now()), "consent": None,
                                                                   "joined_at": None, "media_ids": [], "grant_ids": []}]
            if state["recording"]["enabled"]:
                state["recording"] = {"enabled": False, "reason": "participant added: consent required"}
            return state
        return self._update(ctx, session_id, add, "add_participant")

    def record_consent(self, ctx: AccessContext, session_id: str, granted: bool) -> dict[str, Any]:
        self._participant(self._session(ctx, session_id).state, ctx.actor_id)

        def consent(state: dict[str, Any]) -> dict[str, Any]:
            state["participants"] = [{**p, "consent": granted, "consent_at": iso(utc_now())} if p["actor_id"] == ctx.actor_id else p
                                     for p in state["participants"]]
            if not granted and state["recording"]["enabled"]:
                state["recording"] = {"enabled": False, "reason": f"consent withdrawn by {ctx.actor_id}"}
            return state
        return self._update(ctx, session_id, consent, "record_consent", "remote_session.consent")

    def set_recording(self, ctx: AccessContext, session_id: str, enabled: bool) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        if ctx.actor_id != s["created_by"]:
            raise PermissionError("only the session initiator controls recording")
        if enabled:
            pending = [p["actor_id"] for p in s["participants"] if p["consent"] is not True]
            if pending:
                raise PermissionError(f"recording requires consent from every participant; missing: {pending}")
        return self._update(ctx, session_id, lambda st: {**st, "recording": {
            "enabled": enabled, "reason": None if enabled else "stopped by initiator", "changed_by": ctx.actor_id}},
                            "set_recording", "remote_session.recording")

    def join(self, ctx: AccessContext, session_id: str) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        p = self._check_live(ctx, s)
        permissions = {"publish": True, "subscribe": True, "record": False,
                       "media_ids": p["media_ids"] if p["kind"] == "partner" else "all_case_media"}
        token = self.providers[s["media_provider"]].join_token(s["room_id"], ctx.actor_id, permissions)
        self._update(ctx, session_id, lambda st: {**st, "participants": [
            {**x, "joined_at": iso(utc_now())} if x["actor_id"] == ctx.actor_id else x for x in st["participants"]]}, "join")
        return {"token": token, "permissions": permissions, "recording": s["recording"]["enabled"],
                "consent_recorded": p["consent"], "server_url": getattr(self.providers[s["media_provider"]], "url", None)}

    def end(self, ctx: AccessContext, session_id: str) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        if ctx.actor_id != s["created_by"]:
            raise PermissionError("only the session initiator can end it")
        if s["status"] == "ended":
            return s
        try:
            self.providers[s["media_provider"]].close_room(s["room_id"])
        except OSError:
            self._update(ctx, session_id, lambda st: {**st, "status": "ending_unknown"}, "room_end_unconfirmed")
            raise
        return self._update(ctx, session_id, lambda st: {**st, "status": "ended", "ended_at": iso(utc_now()),
                                                         "recording": {"enabled": False, "reason": "session ended"}},
                            "end_session", "remote_session.ended")

    # --- LS-039 ----------------------------------------------------------------------------------------------
    def register_media(self, ctx: AccessContext, case_id: str, media_id: str, *, media_type: str, digest: str | None = None,
                       site_id: str | None = None) -> dict[str, Any]:
        self.identity.require(ctx, "comment", "case", case_id, site_id=site_id)
        state = {"media_id": media_id, "case_id": case_id, "media_type": media_type, "digest": digest, "site_id": site_id,
                 "registered_by": ctx.actor_id}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "case_media", media_id, state, expected_revision=None, action="register_media")
        return state

    def invite_external_expert(self, ctx: AccessContext, session_id: str, *, expert_id: str, partner_org_id: str,
                               media_ids: Sequence[str], expires_at: datetime | None = None) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        self.identity.require(ctx, "export", "case", s["case_id"], site_id=s.get("site_id"))
        tx = self.store.read()
        for mid in media_ids:
            if tx.require(ctx.tenant_id, "case_media", mid).state["case_id"] != s["case_id"]:
                raise PermissionError(f"media {mid} does not belong to case {s['case_id']}")
        grants = [self.identity.grant(ctx.tenant_id, grantee_id=expert_id, resource_kind="case", resource_id=s["case_id"],
                                      actions=["read", "comment"], site_id=s.get("site_id"), expires_at=expires_at, by=ctx.actor_id,
                                      purpose=f"remote assistance {session_id}")]
        grants += [self.identity.grant(ctx.tenant_id, grantee_id=expert_id, resource_kind="case_media", resource_id=mid,
                                       actions=["read"], site_id=s.get("site_id"), expires_at=expires_at, by=ctx.actor_id,
                                       purpose=f"remote assistance {session_id}") for mid in media_ids]
        expert = {"actor_id": expert_id, "kind": "partner", "partner_org_id": partner_org_id,
                  "access_verified_at": iso(utc_now()), "consent": None, "joined_at": None, "media_ids": list(media_ids),
                  "grant_ids": grants}

        def add(state: dict[str, Any]) -> dict[str, Any]:
            state["participants"] = [*[p for p in state["participants"] if p["actor_id"] != expert_id], expert]
            if state["recording"]["enabled"]:
                state["recording"] = {"enabled": False, "reason": "participant added: consent required"}
            return state
        return self._update(ctx, session_id, add, "invite_external_expert", "remote_session.expert_invited")

    def revoke_external_expert(self, ctx: AccessContext, session_id: str, expert_id: str) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        self.identity.require(ctx, "export", "case", s["case_id"], site_id=s.get("site_id"))
        provider = self.providers[s["media_provider"]]
        if hasattr(provider, "remove_participant"):
            provider.remove_participant(s["room_id"], expert_id)
        for gid in self._participant(s, expert_id)["grant_ids"]:
            self.identity.revoke_grant(ctx.tenant_id, gid, by=ctx.actor_id, reason="session access revoked")
        return self._update(ctx, session_id, lambda st: {**st, "participants": [p for p in st["participants"]
                                                                               if p["actor_id"] != expert_id]}, "remove_participant")

    def open_case(self, ctx: AccessContext, session_id: str, case_id: str | None = None) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        self._check_live(ctx, s)
        if case_id not in (None, s["case_id"]):
            raise PermissionError(f"session {session_id} is limited to case {s['case_id']}")
        rec = self.store.read().require(ctx.tenant_id, "case", s["case_id"])
        return {"case_id": s["case_id"], **rec.state}

    def read_media(self, ctx: AccessContext, session_id: str, media_id: str) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        p = self._check_live(ctx, s)
        media = self.store.read().require(ctx.tenant_id, "case_media", media_id).state
        if media["case_id"] != s["case_id"]:
            raise PermissionError(f"media {media_id} is outside session case {s['case_id']}")
        if p["kind"] == "partner" and media_id not in p["media_ids"]:
            raise PermissionError(f"media {media_id} not permitted for {ctx.actor_id}")
        self.identity.require(ctx, "read", "case_media", media_id, site_id=media.get("site_id"))
        return media

    # --- LS-038 ----------------------------------------------------------------------------------------------
    def annotate(self, ctx: AccessContext, session_id: str, tool: str, content: dict[str, Any], *, device: str = "browser",
                 media_id: str | None = None) -> dict[str, Any]:
        s = self._session(ctx, session_id).state
        p = self._check_live(ctx, s, action="comment")
        spec = ANNOTATION_TOOLS.get(tool)
        if spec is None:
            raise ValueError(f"unknown tool {tool}")
        if spec["status"] != "enabled":
            raise ToolUnavailable(f"{tool} is device-dependent and not device-tested; no implementation is enabled")
        if device not in spec["devices"]:
            raise ToolUnavailable(f"{tool} is not declared for device {device}; declared: {list(spec['devices'])}")
        if spec.get("requires_recording") and not s["recording"]["enabled"]:
            raise PermissionError(f"{tool} requires recording with every participant's consent")
        if media_id is not None:
            self.read_media(ctx, session_id, media_id)
        aid = new_id("ann")
        state = {"annotation_id": aid, "session_id": session_id, "case_id": s["case_id"], "tool": tool, "author": ctx.actor_id,
                 "site_id": s.get("site_id"),
                 "author_kind": p["kind"], "at": iso(utc_now()), "content": content, "device": device, "media_id": media_id,
                 "device_tested": False, "review_status": "unreviewed" if tool == "transcript" else None}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "session_annotation", aid, state, expected_revision=None, action=f"annotate_{tool}")
            tx.add_edge(ctx.tenant_id, ("remote_session", session_id), ("session_annotation", aid), "annotation")
        return state

    def annotations(self, ctx: AccessContext, session_id: str, tool: str | None = None) -> list[dict[str, Any]]:
        s = self._session(ctx, session_id).state
        self._participant(s, ctx.actor_id)
        self.identity.require(ctx, "read", "case", s["case_id"], site_id=s.get("site_id"))
        rows = self.store.read().list(ctx.tenant_id, "session_annotation",
                                      lambda a: a["session_id"] == session_id and (tool is None or a["tool"] == tool))
        return sorted((r.state for r in rows), key=lambda a: a["at"])

    def review_transcript(self, ctx: AccessContext, annotation_id: str, status: str) -> dict[str, Any]:
        if status not in ("accepted", "rejected"):
            raise ValueError("status must be accepted or rejected")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "session_annotation", annotation_id)
            if rec.state["tool"] != "transcript":
                raise ValueError("only transcript segments are reviewed")
            self.identity.require(ctx, "approve", "session_annotation", annotation_id)
            out = tx.put(ctx.tenant_id, "session_annotation", annotation_id,
                         {**rec.state, "review_status": status, "reviewed_by": ctx.actor_id, "reviewed_at": iso(utc_now())},
                         expected_revision=rec.revision, action="review_transcript")
        return out.state
