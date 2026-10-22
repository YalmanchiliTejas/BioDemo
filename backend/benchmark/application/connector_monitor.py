from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from benchmark.knowledge.digital_thread import DigitalThread
from benchmark.knowledge.domain import AccessContext, CaseRecord, EntityRef

from .extensions import ExtensionRegistry


FetchRecords = Callable[["ConnectorConfig", str | None], tuple[list[dict[str, Any]], str | None]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ConnectorConfig:
    connector_id: str
    name: str
    source_system: str
    base_url: str
    records_path: str
    tenant_id: str
    site_id: str
    poll_interval_seconds: int = 60
    trigger_event_types: tuple[str, ...] = ()
    auto_start_agent: bool = False
    enabled: bool = True
    connector_type: str = "http_json"
    cursor_parameter: str = "cursor"
    auth_header: str | None = None
    auth_token_env: str | None = None
    classification: str = "internal"
    owner_id: str = "qa-monitor"
    field_mapping: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.connector_id or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in self.connector_id
        ):
            raise ValueError("connector_id contains unsupported characters")
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP or HTTPS URL")
        if not self.records_path.startswith("/"):
            raise ValueError("records_path must start with /")
        if not 5 <= self.poll_interval_seconds <= 86400:
            raise ValueError("poll_interval_seconds must be between 5 and 86400")
        if self.connector_type != "http_json":
            raise ValueError("unsupported connector_type")
        if bool(self.auth_header) != bool(self.auth_token_env):
            raise ValueError("auth_header and auth_token_env must be configured together")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["trigger_event_types"] = list(self.trigger_event_types)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ConnectorConfig:
        return cls(
            **{
                **value,
                "trigger_event_types": tuple(value.get("trigger_event_types", ())),
                "field_mapping": dict(value.get("field_mapping", {})),
            }
        )


class ConnectorMonitor:
    """Polls systems of record, ingests evidence, and opens deduplicated deviation cases."""

    def __init__(
        self,
        thread: DigitalThread,
        extensions: ExtensionRegistry,
        state_path: Path,
        *,
        fetch_records: FetchRecords | None = None,
    ) -> None:
        self.thread = thread
        self.extensions = extensions
        self.state_path = state_path
        self.fetch_records = fetch_records or self._fetch_http_json
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._state = self._load()

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._stop_event.clear()
            self._worker = threading.Thread(
                target=self._run,
                name="system-of-record-monitor",
                daemon=True,
            )
            self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        worker = self._worker
        if worker:
            worker.join(timeout=5)

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            values = []
            for key, raw in self._state["connectors"].items():
                config = ConnectorConfig.from_dict(raw)
                if config.tenant_id != tenant_id:
                    continue
                values.append({
                    **config.to_dict(),
                    "runtime": dict(self._runtime(key)),
                })
            return sorted(values, key=lambda item: item["name"].lower())

    def put(self, config: ConnectorConfig) -> dict[str, Any]:
        key = self._config_key(config.tenant_id, config.connector_id)
        with self._lock:
            self._state["connectors"][key] = config.to_dict()
            self._state["runtime"].setdefault(key, self._empty_runtime())
            self._save()
        return {**config.to_dict(), "runtime": dict(self._runtime(key))}

    def sync(self, connector_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            key = self._resolve_key(connector_id, tenant_id)
            raw = self._state["connectors"].get(key)
            if raw is None:
                raise KeyError(f"unknown connector: {connector_id}")
            config = ConnectorConfig.from_dict(raw)
            runtime = self._runtime(key)
            cursor = runtime.get("cursor")
            runtime["status"] = "syncing"
            runtime["last_error"] = None
            self._save()
        try:
            records, next_cursor = self.fetch_records(config, cursor)
            result = self._ingest(config, records)
            with self._lock:
                runtime = self._runtime(key)
                runtime.update({
                    "status": "connected",
                    "cursor": next_cursor if next_cursor is not None else cursor,
                    "last_sync_at": _now(),
                    "last_error": None,
                    "records_seen": runtime.get("records_seen", 0) + len(records),
                })
                self._save()
            return {"connector_id": connector_id, **result, "cursor": runtime.get("cursor")}
        except Exception as exc:
            with self._lock:
                runtime = self._runtime(key)
                runtime.update({
                    "status": "error",
                    "last_sync_at": _now(),
                    "last_error": f"{type(exc).__name__}: {exc}",
                })
                self._save()
            raise

    def _ingest(self, config: ConnectorConfig, records: list[dict[str, Any]]) -> dict[str, int]:
        counts = {"ingested": 0, "duplicates": 0, "cases_opened": 0, "agents_started": 0}
        for raw in records:
            record = self._normalize(raw, config)
            source_record_id = record["source_record_id"]
            dedupe_key = f"{config.tenant_id}:{config.connector_id}:{source_record_id}"
            with self._lock:
                if dedupe_key in self._state["processed_records"]:
                    counts["duplicates"] += 1
                    continue
            access = AccessContext(
                config.tenant_id,
                "source-monitor",
                (config.site_id,),
                ("system",),
                (config.classification,),
            )
            event = self.thread.ingest_raw_event(
                record,
                access=access,
                source_system=config.source_system,
                site_id=config.site_id,
                classification=config.classification,
            )
            counts["ingested"] += 1
            if record["event_type"] in config.trigger_event_types:
                opened, started = self._open_case(config, record, event.to_dict(), access)
                counts["cases_opened"] += int(opened)
                counts["agents_started"] += int(started)
            with self._lock:
                self._state["processed_records"].append(dedupe_key)
                self._save()
        return counts

    def _open_case(
        self,
        config: ConnectorConfig,
        record: dict[str, Any],
        event: dict[str, Any],
        access: AccessContext,
    ) -> tuple[bool, bool]:
        digest = hashlib.sha256(
            f"{config.tenant_id}:{config.connector_id}:{record['source_record_id']}".encode()
        ).hexdigest()[:12].upper()
        case_id = f"AUTO-{digest}"
        existing = self.thread.cases.get_case(case_id, config.tenant_id)
        opened = existing is None
        if existing is None:
            refs = tuple(
                EntityRef(str(item["entity_id"]), str(item["entity_type"]), item.get("role", "affected"))
                for item in record.get("entities", [])
                if isinstance(item, dict) and item.get("entity_id") and item.get("entity_type")
            )
            existing = CaseRecord(
                case_id=case_id,
                tenant_id=config.tenant_id,
                case_type="deviation",
                title=str(record.get("title") or record.get("observed_condition") or record["event_type"]),
                owner_id=config.owner_id,
                site_id=config.site_id,
                entity_refs=refs,
            )
            self.thread.open_case(existing, access=access)
        orchestrator = self.extensions.orchestrator
        if not config.auto_start_agent or orchestrator is None:
            return opened, False
        context = {
            "case": {
                "case_id": existing.case_id,
                "case_type": existing.case_type,
                "title": existing.title,
                "site_id": existing.site_id,
                "entity_refs": [asdict(reference) for reference in existing.entity_refs],
            },
            "case_source": {
                "source_system": config.source_system,
                "source_record_id": record["source_record_id"],
                "timestamp": record["timestamp"],
                "evidence_ref": event.get("evidence_id"),
            },
            "trigger": record,
            "canonical_event": event,
            "identity": {
                "tenant_id": config.tenant_id,
                "site_ids": [config.site_id],
                "clearances": [config.classification],
            },
        }
        orchestrator.start(case_id, context)
        return opened, True

    def _run(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                connector_keys = list(self._state["connectors"])
            now = datetime.now(timezone.utc)
            for key in connector_keys:
                with self._lock:
                    config = ConnectorConfig.from_dict(self._state["connectors"][key])
                    last_sync = self._runtime(key).get("last_sync_at")
                if not config.enabled or not self._due(now, last_sync, config.poll_interval_seconds):
                    continue
                try:
                    self.sync(config.connector_id, config.tenant_id)
                except Exception:
                    pass
            self._stop_event.wait(1)

    @staticmethod
    def _due(now: datetime, last_sync: str | None, interval: int) -> bool:
        if not last_sync:
            return True
        previous = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
        return (now - previous).total_seconds() >= interval

    @staticmethod
    def _normalize(raw: dict[str, Any], config: ConnectorConfig) -> dict[str, Any]:
        record = dict(raw)
        for canonical, source_path in config.field_mapping.items():
            value: Any = raw
            for segment in source_path.split("."):
                if not isinstance(value, dict) or segment not in value:
                    value = None
                    break
                value = value[segment]
            if value is not None:
                record[canonical] = value
        missing = [key for key in ("source_record_id", "timestamp", "event_type") if not record.get(key)]
        if missing:
            raise ValueError(f"source record is missing canonical fields: {', '.join(missing)}")
        if not isinstance(record.get("entities", []), list):
            raise ValueError("source record entities must be a list")
        return record

    @staticmethod
    def _fetch_http_json(
        config: ConnectorConfig, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        query = {config.cursor_parameter: cursor} if cursor else {}
        url = urllib.parse.urljoin(config.base_url.rstrip("/") + "/", config.records_path.lstrip("/"))
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        headers = {"Accept": "application/json"}
        if config.auth_header and config.auth_token_env:
            token = os.getenv(config.auth_token_env)
            if not token:
                raise RuntimeError(f"credential environment variable is not set: {config.auth_token_env}")
            headers[config.auth_header] = token
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            content = response.read(10_000_001)
        if len(content) > 10_000_000:
            raise ValueError("connector response exceeds 10 MB")
        payload = json.loads(content)
        if isinstance(payload, list):
            records = payload
            next_cursor = cursor
        elif isinstance(payload, dict):
            records = payload.get("records", [])
            next_cursor = payload.get("next_cursor", cursor)
        else:
            raise ValueError("connector response must be an object or list")
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            raise ValueError("connector records must be JSON objects")
        return records, str(next_cursor) if next_cursor is not None else None

    def _runtime(self, connector_id: str) -> dict[str, Any]:
        return self._state["runtime"].setdefault(connector_id, self._empty_runtime())

    @staticmethod
    def _config_key(tenant_id: str, connector_id: str) -> str:
        return f"{tenant_id}:{connector_id}"

    def _resolve_key(self, connector_id: str, tenant_id: str | None) -> str:
        if tenant_id:
            return self._config_key(tenant_id, connector_id)
        matches = [
            key for key, value in self._state["connectors"].items()
            if value.get("connector_id") == connector_id
        ]
        if len(matches) != 1:
            raise KeyError(f"unknown or ambiguous connector: {connector_id}")
        return matches[0]

    @staticmethod
    def _empty_runtime() -> dict[str, Any]:
        return {
            "status": "not_synced",
            "cursor": None,
            "last_sync_at": None,
            "last_error": None,
            "records_seen": 0,
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"connectors": {}, "runtime": {}, "processed_records": []}
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        value.setdefault("connectors", {})
        value.setdefault("runtime", {})
        value.setdefault("processed_records", [])
        return value

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(f"{self.state_path.suffix}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(self._state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)
