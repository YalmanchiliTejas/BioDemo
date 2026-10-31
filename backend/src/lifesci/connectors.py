"""Configured, site-scoped connector families over the existing evidence intake contracts.

Vendor-specific field names and paths are configuration, not claims of vendor
qualification. Credentials are environment references and never enter domain records.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .connector_contracts import _source_record
from .connector_contracts import AuthorizedAction, PullBatch

from .actions import DeliveryUnknown
from .ids import content_hash, iso, utc_now
from .integrations import (ConnectorContract, ConnectorMatrix, ConnectorTemplate, ConnectorWriter,
                           DurableQueue, FieldMap, FileDropConnector, IntakeService, WebhookIntake,
                           record_from_dict, record_to_dict, test_connection)

FAMILIES = {
    "MES": ("production_order", ("order_id", "batch_id", "status", "equipment_id", "product")),
    "LIMS": ("lab_result", ("sample_id", "test", "value", "unit", "status")),
    "QMS": ("quality_record", ("case_id", "record_type", "status", "description", "owner")),
    "ERP": ("material", ("lot_number", "material_code", "expiry", "qty", "uom", "status")),
    "HISTORIAN": ("measurement", ("tag", "value", "unit", "quality")),
    "ELN": ("experiment", ("experiment_id", "title", "status", "description")),
    "CMMS": ("maintenance", ("work_order", "equipment_id", "status", "description")),
    "WMS": ("inventory", ("lot_number", "material_code", "location", "qty", "uom", "status")),
}
OPERATIONS = {
    "MES": {"place_hold", "release_batch", "reject_batch", "reschedule_batch"},
    "LIMS": {"request_retest", "invalidate_result"},
    "QMS": {"submit_deviation", "close_deviation", "approve_capa"},
    "ERP": {"reserve_material", "consume_material"},
    "CMMS": {"create_work_order"},
}
TRANSPORTS = ("rest", "file", "webhook", "mqtt", "opcua")
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def family_template(family: str) -> ConnectorTemplate:
    kind, fields = FAMILIES[family]
    context = ("batch_id", "elapsed_h") if family in {"LIMS", "HISTORIAN"} else ()
    return ConnectorTemplate(f"{family.lower()}-v1", family, kind,
                             tuple(FieldMap(name, name) for name in (*fields, *context)))


def _secret(name: str | None) -> str | None:
    if not name:
        return None
    if not _ENV.fullmatch(name) or not os.environ.get(name):
        raise ValueError("connector credential environment reference is unavailable")
    return os.environ[name]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("connector redirects require an explicitly configured endpoint")


def _url(url: str) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password or parts.fragment or parts.query:
        raise ValueError("endpoint must not contain credentials, a query or fragment")
    hosts = {h.strip() for h in os.environ.get("LIFESCI_CONNECTOR_ALLOWED_HOSTS", "").split(",") if h.strip()}
    if parts.hostname not in hosts:
        raise PermissionError("connector host must be listed in LIFESCI_CONNECTOR_ALLOWED_HOSTS")
    if parts.scheme not in ("https", "mqtts", "opc.tcp") and not (
        parts.hostname in {"localhost", "127.0.0.1", "::1"} and parts.scheme in {"http", "mqtt"}
    ):
        raise ValueError("use a secure endpoint; plaintext HTTP/MQTT is only permitted on loopback")
    return url.rstrip("/")


def _path(value: str) -> str:
    if not value.startswith("/") or value.startswith("//") or ".." in value.split("/") or "?" in value or "#" in value:
        raise ValueError("API paths must be absolute paths within the configured endpoint")
    return value


class RestSource:
    """Configurable JSON pagination with independent read/write credentials and explicit reconciliation."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.connector_id, self.source_system = config["connector_id"], f"{config['family']}@{config['connector_id']}"
        self.options = config["options"]
        self.base_url = _url(self.options["base_url"])
        self.opener = build_opener(NoRedirect())

    def request(self, method: str, path: str, *, query: dict[str, Any] | None = None,
                payload: dict[str, Any] | None = None, write: bool = False) -> dict[str, Any]:
        url = self.base_url + _path(path)
        if query:
            url += "?" + urlencode(query)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        token = _secret(self.options.get("write_auth_env" if write else "auth_env"))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                      method=method, headers=headers)
        with self.opener.open(req, timeout=15) as response:
            data = json.loads(response.read(10_000_001))
        if not isinstance(data, dict):
            raise ValueError("connector response must be a JSON object")
        return data

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        query = {self.options.get("limit_parameter", "limit"): limit}
        if checkpoint is not None:
            query[self.options.get("cursor_parameter", "checkpoint")] = checkpoint
        doc = self.request("GET", self.options.get("events_path", "/events"), query=query)
        rows = doc.get(self.options.get("records_field", "records"))
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError("source must return a bounded records array")
        records = tuple(_source_record(row, source_system=self.source_system,
            fallback_id=str(row.get(self.options.get("id_field", "id"), "")),
            timestamp_field=self.options.get("timestamp_field", "timestamp"), site_id=self.config["site_id"])
            for row in rows)
        cursor = doc.get(self.options.get("next_checkpoint_field", "next_checkpoint"))
        more = bool(doc.get("has_more", False))
        if more and (cursor is None or str(cursor) == checkpoint):
            raise ValueError("source pagination did not advance; checkpoint unchanged")
        return PullBatch(records, str(cursor) if cursor is not None else checkpoint, more)

    def write(self, action: AuthorizedAction):
        if action.operation not in self.config.get("write_operations", []):
            raise PermissionError("operation is not enabled for this connector")
        try:
            doc = self.request("POST", self.options["write_path"], payload={
                **asdict(action), "approved_at": iso(action.approved_at)}, write=True)
            return _source_record(doc, source_system=self.source_system, fallback_id="",
                                  site_id=self.config["site_id"])
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            if isinstance(exc, HTTPError) and exc.code < 500:
                raise
            raise DeliveryUnknown("destination outcome unconfirmed; reconcile before retry") from exc

    def lookup(self, key: str) -> dict[str, Any] | None:
        doc = self.request("GET", self.options["lookup_path"], query={"idempotency_key": key}, write=True)
        if doc.get("status") == "not_found":
            return None
        if doc.get("status") != "delivered" or not isinstance(doc.get("receipt"), dict):
            raise DeliveryUnknown("destination has not confirmed the operation")
        return doc["receipt"]


class MqttSource:
    """Paho MQTT 3.1.1 persistent subscriber; acknowledge only after raw messages are durable."""

    def __init__(self, store: Any, tenant: str, config: dict[str, Any]) -> None:
        import paho.mqtt.client as mqtt
        self.config, self.connector_id = config, config["connector_id"]
        self.source_system = f"{config['family']}@{config['connector_id']}"
        self.store, self.tenant = store, tenant
        self.queue = DurableQueue(store, tenant, f"mqtt-live:{self.connector_id}")
        self.error: str | None = None
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"biodemo-{content_hash([tenant, self.connector_id])[:32]}", clean_session=False, manual_ack=True)
        options = config["options"]
        parts = urlsplit(_url(options["base_url"]))
        if parts.scheme == "mqtts":
            self.client.tls_set(ca_certs=options.get("ca_file"))
        if options.get("username_env"):
            self.client.username_pw_set(_secret(options["username_env"]), _secret(options.get("password_env")))
        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                self.error = "MQTT connection rejected"
            else:
                client.subscribe([(address, 1) for address in options["addresses"]])
        def on_subscribe(client, userdata, mid, reason_codes, properties):
            if any(code.is_failure for code in reason_codes):
                self.error = "MQTT subscription rejected"
            self.ready.set()
        def on_message(client, userdata, msg):
            try:
                current = store.read().get(tenant, "connector", self.connector_id)
                if current is not None:
                    from .identity import IdentityService
                    identity = IdentityService(store)
                    ctx = identity.context_for(tenant, current.state["configured_by"])
                    if not current.state["enabled"] or not identity.check(ctx, "configure", "connector",
                            self.connector_id, site_id=current.state["site_id"]):
                        raise PermissionError("collector access revoked")
                raw = json.loads(msg.payload)
                # The publisher supplies a stable id and source time; topic is retained as provenance.
                raw["topic"] = msg.topic
                record = _source_record(raw, source_system=self.source_system, fallback_id="",
                                        site_id=config["site_id"])
                with store.transaction("mqtt-collector") as tx:
                    self.queue.append(tx, {"record": record_to_dict(record)})
                if msg.qos:
                    client.ack(msg.mid, msg.qos)
            except Exception:
                self.error = "MQTT message rejected or could not be persisted; delivery not acknowledged"
        self.client.on_connect, self.client.on_subscribe, self.client.on_message = on_connect, on_subscribe, on_message
        self.client.connect(parts.hostname, parts.port or (8883 if parts.scheme == "mqtts" else 1883), keepalive=60)
        self.client.loop_start()
        if not self.ready.wait(10) or self.error:
            self.close()
            raise ValueError(self.error or "MQTT subscription timed out")

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        if self.error:
            raise ValueError(self.error)
        offset = int(checkpoint or 0)
        items = self.queue.read(offset, limit)
        return PullBatch(tuple(record_from_dict(i["record"]) for i in items), str(offset + len(items)),
                         offset + len(items) < self.queue.count())

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


class OpcUaSource:
    """Read-only OPC UA snapshots preserve source timestamps and quality; no control methods exposed."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config, self.connector_id = config, config["connector_id"]
        self.source_system = f"{config['family']}@{config['connector_id']}"

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        from asyncua.sync import Client
        options = self.config["options"]
        nodes = options["addresses"]
        # Node snapshots are a complete bounded poll, not an offset that skips changed earlier nodes.
        if len(nodes) > limit:
            raise ValueError("increase batch_size to include every configured OPC UA node")
        client = Client(_url(options["base_url"]), timeout=15)
        if options.get("security_string_env"):
            client.set_security_string(_secret(options["security_string_env"]))
        else:
            raise PermissionError("OPC UA requires a configured signing/encryption security string")
        if options.get("username_env"):
            client.set_user(_secret(options["username_env"]))
            client.set_password(_secret(options.get("password_env")) or "")
        rows = []
        with client:
            for address in nodes:
                value = client.get_node(address).read_data_value(raise_on_bad_status=False)
                if value.SourceTimestamp is None:
                    raise ValueError("OPC UA value has no source timestamp")
                rows.append(_source_record({"id": address, "timestamp": iso(value.SourceTimestamp),
                    "value": value.Value.Value, "quality": value.StatusCode.name, "node_id": address},
                    source_system=self.source_system, fallback_id="", site_id=self.config["site_id"]))
        return PullBatch(tuple(rows), iso(utc_now()), False)


class ConnectorService:
    def __init__(self, platform: Any) -> None:
        self.platform = platform
        self.store, self.identity = platform.store, platform.identity
        self.matrix = ConnectorMatrix(self.store, self.identity)
        self.intake = IntakeService(self.store, platform.evidence)
        self._instances: dict[tuple[str, str, str], Any] = {}
        self._lock = threading.RLock()

    def catalog(self) -> dict[str, Any]:
        def installed(name: str) -> bool:
            try:
                return importlib.util.find_spec(name) is not None
            except ModuleNotFoundError:
                return False
        return {"families": [{"system": family, "record_type": kind, "template": family_template(family).to_dict(),
                              "write_operations": sorted(OPERATIONS.get(family, []))}
                             for family, (kind, _) in FAMILIES.items()],
                "transports": [{"transport": t, "available": t not in {"mqtt", "opcua"} or
                                (not os.environ.get("AWS_LAMBDA_FUNCTION_NAME") and
                                 installed("paho.mqtt.client" if t == "mqtt" else "asyncua"))}
                               for t in TRANSPORTS], "vendor_qualification": "not_performed"}

    def configure(self, ctx: Any, config: dict[str, Any]) -> dict[str, Any]:
        cid, family, transport = config["connector_id"], config["family"], config["transport"]
        if not _ID.fullmatch(cid) or family not in FAMILIES or transport not in TRANSPORTS:
            raise ValueError("invalid connector id, family or transport")
        if not config.get("site_id"):
            raise ValueError("a connector requires an explicit site")
        self.identity.require(ctx, "configure", "connector", cid, site_id=config["site_id"])
        if config.get('source_group') is not None and not config['source_group'].strip():
            raise ValueError('source_group must be a nonempty CDMO or source-group name')
        options = dict(config.get("options", {}))
        required = {"rest": ("base_url",), "mqtt": ("base_url", "addresses"),
                    "opcua": ("base_url", "addresses", "security_string_env"),
                    "file": ("directory",), "webhook": ("secret_env",)}[transport]
        if any(not options.get(key) for key in required):
            raise ValueError(f"{transport} requires {', '.join(required)}")
        allowed = {"base_url", "events_path", "records_field", "next_checkpoint_field", "id_field", "timestamp_field",
                   "cursor_parameter", "limit_parameter", "auth_env", "write_auth_env", "write_path", "lookup_path",
                   "directory", "addresses", "username_env", "password_env", "security_string_env", "ca_file",
                   "secret_env", "poll_seconds", "batch_size"}
        if set(options) - allowed:
            raise ValueError("unknown connector options; credentials must be environment references")
        for key, value in options.items():
            if key.endswith("_env") and (not isinstance(value, str) or not _ENV.fullmatch(value)):
                raise ValueError("invalid credential environment reference")
        if transport in {"rest", "mqtt", "opcua"}:
            url = _url(options["base_url"])
            scheme = urlsplit(url).scheme
            if scheme not in {"rest": {"http", "https"}, "mqtt": {"mqtt", "mqtts"}, "opcua": {"opc.tcp"}}[transport]:
                raise ValueError("endpoint protocol does not match connector transport")
        if transport == "rest":
            for field in ("events_path", "write_path", "lookup_path"):
                if field in options:
                    _path(options[field])
        if transport in {"mqtt", "opcua"} and not options.get("addresses"):
            raise ValueError("telemetry connector requires explicit topics or node ids")
        if transport in {"mqtt", "opcua"} and (not isinstance(options["addresses"], list) or
            not all(isinstance(a, str) and a.strip() for a in options["addresses"])):
            raise ValueError("addresses must be a nonempty list of topics or node ids")
        batch_size = options.get("batch_size", 100)
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
            raise ValueError("batch_size must be 1-1000")
        if transport == "file":
            self._directory(options["directory"])
        if transport == "webhook" and not options.get("secret_env"):
            raise ValueError("webhook requires a signing secret environment reference")
        writes = config.get("write_operations", [])
        if not set(writes) <= OPERATIONS.get(family, set()):
            raise ValueError("write operation does not belong to this connector family")
        if writes and (transport != "rest" or not all(options.get(k) for k in
                     ("write_path", "lookup_path", "write_auth_env")) or
                     options.get("write_auth_env") == options.get("auth_env")):
            raise ValueError("writes require REST, a write path, reconciliation path and separate write credentials")
        poll = options.get("poll_seconds", 0)
        if not isinstance(poll, int) or poll < 0 or (poll and poll < 10):
            raise ValueError("poll_seconds is zero (manual) or at least 10 seconds")
        template = ConnectorTemplate.from_dict(config["mapping"]) if config.get("mapping") else family_template(family)
        if template.problems():
            raise ValueError("; ".join(template.problems()))
        with self.store.transaction(ctx.actor_id) as tx:
            current = tx.get(ctx.tenant_id, "connector", cid)
            if current:
                self.identity.require(ctx, "configure", "connector", cid, site_id=current.state["site_id"], tx=tx)
                if current.state["site_id"] != config["site_id"] or current.state["family"] != family:
                    raise ValueError("use a new connector id when changing family or site")
            state = {"connector_id": cid, "family": family, "transport": transport, "site_id": config["site_id"],
                     "owner": config["owner"], "configured_by": ctx.actor_id, "options": options,
                     "mapping_confirmed": config.get("mapping_confirmed", False),
                     "source_group": config.get("source_group", '').strip() if config.get("source_group") else cid,
                     "mapping": template.to_dict(), "write_operations": writes,
                     "vendor": config.get("vendor", "generic"), "version": config.get("version", "1"),
                     "enabled": config.get("enabled", True), "last_sync": None, "last_error": None}
            contract = self.matrix.register(ctx, ConnectorContract(family, state["vendor"], state["version"], transport,
                ("pull",), config["owner"], "environment reference", template.version,
                write_operations=tuple(writes), write_auth=options.get("write_auth_env"),
                contract_version=content_hash([options, template.to_dict()])[:16],
                limits=("Vendor qualification not performed",)))
            # Schedule/pause changes must retain the last attempt and its evidence.
            # Reset status only when the source or mapping actually changes.
            if current:
                source_options = lambda opts: {k: v for k, v in opts.items() if k != "poll_seconds"}
                if (current.state["transport"] == transport
                    and source_options(current.state["options"]) == source_options(options)
                    and current.state["mapping"] == state["mapping"]):
                    for key in ("last_sync", "last_result", "last_error"):
                        if key in current.state:
                            state[key] = current.state[key]
            state["contract_id"] = contract["contract_id"]
            rec = tx.put(ctx.tenant_id, "connector", cid, state,
                         expected_revision=current.revision if current else None, action="configure_connector")
            self.intake.verification.configure(ctx, cid, template, site_id=config['site_id'],
                confirmed=state['mapping_confirmed'], source_group=state['source_group'])
            self.intake.verification.recheck(ctx, cid)
        self.platform.runtime.track(ctx.tenant_id)
        with self._lock:
            for key in [k for k in self._instances if k[:2] == (ctx.tenant_id, cid)]:
                self._instances.pop(key).close()
        return {**rec.state, "revision": rec.revision}

    def _directory(self, directory: str) -> Path:
        root = os.environ.get("LIFESCI_CONNECTOR_FILE_ROOT")
        if not root:
            raise PermissionError("set LIFESCI_CONNECTOR_FILE_ROOT before enabling file connectors")
        path = Path(directory).expanduser().resolve()
        if not path.is_relative_to(Path(root).expanduser().resolve()) or not path.is_dir():
            raise PermissionError("file source must be a directory inside the configured connector root")
        return path

    def record(self, ctx: Any, cid: str, action: str = "configure"):
        rec = self.store.read().require(ctx.tenant_id, "connector", cid)
        self.identity.require(ctx, action, "connector", cid, site_id=rec.state["site_id"])
        return rec

    def list_for(self, ctx: Any) -> list[dict[str, Any]]:
        return [{**r.state, "revision": r.revision,
                 "qualification": (self.matrix.get(ctx.tenant_id, r.state["contract_id"]) or {}).get("status", "unavailable")}
                for r in self.store.read().list(ctx.tenant_id, "connector")
                if self.identity.check(ctx, "configure", "connector", r.id, site_id=r.state["site_id"])]

    def _build(self, tenant: str, rec: Any) -> Any:
        c, o = rec.state, rec.state["options"]
        if not c["enabled"]:
            raise ValueError("connector is disabled")
        # Status updates change revisions: cache only MQTT connections by configuration content.
        if c["transport"] == "rest":
            return RestSource(c)
        if c["transport"] == "file":
            return FileDropConnector(rec.id, f"{c['family']}@{rec.id}", self._directory(o["directory"]), site_id=c["site_id"],
                                     timestamp_field=o.get("timestamp_field", "timestamp"), id_field=o.get("id_field", "id"))
        if c["transport"] == "webhook":
            return WebhookIntake(self.store, tenant, rec.id, f"{c['family']}@{rec.id}", [_secret(o["secret_env"])], site_id=c["site_id"])
        if c["transport"] == "opcua":
            return OpcUaSource(c)
        key = (tenant, rec.id, content_hash(o))
        with self._lock:
            if key not in self._instances:
                for old in [k for k in self._instances if k[:2] == key[:2]]:
                    self._instances.pop(old).close()
                self._instances[key] = MqttSource(self.store, tenant, c)
            return self._instances[key]

    def preview(self, ctx: Any, cid: str) -> dict[str, Any]:
        rec = self.record(ctx, cid)
        if rec.state["transport"] == "mqtt":
            raise ValueError("MQTT starts durable collection during sync; preview its mapping using the template")
        return test_connection(ConnectorTemplate.from_dict(rec.state["mapping"]), self._build(ctx.tenant_id, rec))

    def sync(self, ctx: Any, cid: str) -> dict[str, Any]:
        rec = self.record(ctx, cid)
        holder = f"connector:{os.getpid()}:{threading.get_ident()}"
        with self.store.transaction(ctx.actor_id) as tx:
            token = tx.acquire_lease(ctx.tenant_id, "connector_sync", cid, holder, ttl_seconds=600)
        try:
            source = self._build(ctx.tenant_id, rec)
            result = self.intake.sync(ctx, source, ConnectorTemplate.from_dict(rec.state["mapping"]),
                site_id=rec.state["site_id"], batch_size=rec.state["options"].get("batch_size", 100), max_batches=10,
                mapping_confirmed=rec.state.get("mapping_confirmed", False), source_group=rec.state.get("source_group"))
            rejects = getattr(source, "rejects", [])
            result["rejected_records"] = rejects
            self._status(ctx, cid, result, "file rows rejected; inspect rejected_records" if rejects else None)
            return result
        except Exception:
            self._status(ctx, cid, None, "sync failed; check endpoint access, credentials and source schema")
            raise
        finally:
            with self.store.transaction(ctx.actor_id) as tx:
                tx.check_lease(ctx.tenant_id, "connector_sync", cid, holder, token)
                tx.expire_lease(ctx.tenant_id, "connector_sync", cid)

    def _status(self, ctx: Any, cid: str, result: Any, error: str | None) -> None:
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "connector", cid)
            tx.put(ctx.tenant_id, "connector", cid, {**rec.state, "last_sync": iso(utc_now()),
                   "last_result": result, "last_error": error}, expected_revision=rec.revision, action="connector_status")

    def receive(self, tenant: str, cid: str, body: bytes, headers: dict[str, Any]) -> Any:
        rec = self.store.read().require(tenant, "connector", cid)
        if rec.state["transport"] != "webhook":
            raise ValueError("not a webhook connector")
        return self._build(tenant, rec).handle(headers, body)

    def dispatch(self, ctx: Any, cid: str, intent_id: str, *, reconcile: bool = False) -> dict[str, Any]:
        intent = self.store.read().require(ctx.tenant_id, "action_intent", intent_id)
        self.identity.require(ctx, "execute", "action_intent", intent_id, site_id=intent.state.get("site_id"))
        rec = self.store.read().require(ctx.tenant_id, "connector", cid)
        if intent.state["target_system"] != rec.state["family"] or intent.state.get("site_id") != rec.state["site_id"]:
            raise PermissionError("intent target and site do not match connector")
        if intent.state["operation"] not in rec.state["write_operations"]:
            raise PermissionError("connector does not enable this operation")
        source = self._build(ctx.tenant_id, rec)
        # The action targets the owning family; the intake namespace distinguishes source instances.
        source.source_system = rec.state["family"]
        writer = ConnectorWriter(source, source.lookup)
        return (self.platform.actions.reconcile if reconcile else self.platform.actions.dispatch)(ctx, intent_id, writer)

    def poll(self, tenant: str) -> None:
        from .ids import parse_iso
        for rec in self.store.read().list(tenant, "connector"):
            c = rec.state
            interval = c["options"].get("poll_seconds", 0)
            if not c["enabled"] or not interval or (c.get("last_sync") and
                (utc_now() - parse_iso(c["last_sync"])).total_seconds() < interval):
                continue
            try:
                self.sync(self.identity.context_for(tenant, c["configured_by"]), rec.id)
            except Exception:
                # sync records a non-secret error; failures in one source do not starve others.
                continue

    def close(self) -> None:
        with self._lock:
            for source in self._instances.values():
                source.close()
            self._instances.clear()
