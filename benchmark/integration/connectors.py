from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import AuthorizedAction, ConnectorConfig, PullBatch, SourceRecord


class JsonlConnector:
    """Replayable file connector useful for exports and initial backfills."""

    def __init__(self, connector_id: str, source_system: str, path: Path, *, site_id: str | None = None) -> None:
        self.connector_id = connector_id
        self.source_system = source_system
        self.path = path
        self.site_id = site_id

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        offset = int(checkpoint or 0)
        lines = [line for line in self.path.read_text().splitlines() if line.strip()]
        selected = lines[offset:offset + limit]
        records = tuple(
            _source_record(
                json.loads(line), source_system=self.source_system,
                fallback_id=f"{self.connector_id}:{offset + index}", site_id=self.site_id,
            )
            for index, line in enumerate(selected)
        )
        next_offset = offset + len(selected)
        return PullBatch(records, str(next_offset), next_offset < len(lines))


class WebhookConnector:
    """In-process webhook inbox; production HTTP handlers can enqueue validated records."""

    def __init__(self, connector_id: str, source_system: str) -> None:
        self.connector_id = connector_id
        self.source_system = source_system
        self._records: list[SourceRecord] = []

    def receive(self, record: SourceRecord) -> None:
        if record.source_system != self.source_system:
            raise ValueError("webhook record source does not match connector")
        self._records.append(record)

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        offset = int(checkpoint or 0)
        records = tuple(self._records[offset:offset + limit])
        next_offset = offset + len(records)
        return PullBatch(records, str(next_offset), next_offset < len(self._records))


class RESTConnector:
    """Cursor-based connector for MES, LIMS, QMS, historian, CMMS, ERP, WMS, or ELN APIs."""

    def __init__(self, config: ConnectorConfig, timeout_seconds: float = 30) -> None:
        self.config = config
        self.connector_id = config.connector_id
        self.source_system = config.source_system
        self.timeout_seconds = timeout_seconds

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch:
        query = {"limit": limit}
        if checkpoint is not None:
            query["checkpoint"] = checkpoint
        response = self._request("GET", f"{self.config.events_path}?{urlencode(query)}")
        values = response.get(self.config.records_field, [])
        records = tuple(_source_record(
            value, source_system=self.source_system,
            fallback_id=str(value.get(self.config.id_field, "")),
            timestamp_field=self.config.timestamp_field, site_id=self.config.site_id,
            classification=self.config.classification,
        ) for value in values)
        return PullBatch(
            records, response.get(self.config.next_checkpoint_field), bool(response.get("has_more", False)),
        )

    def write(self, action: AuthorizedAction) -> SourceRecord:
        if not self.config.write_path:
            raise PermissionError(f"connector {self.connector_id} is read-only")
        if action.source_system != self.source_system:
            raise ValueError("action source system does not match connector")
        response = self._request("POST", self.config.write_path, {
            "action_id": action.action_id, "operation": action.operation,
            "target_id": action.target_id, "payload": action.payload,
            "requested_by": action.requested_by, "approved_by": list(action.approved_by),
            "approval_ids": list(action.approval_ids), "approved_at": action.approved_at.isoformat(),
        })
        # Only the source-generated acknowledgement is returned for ingestion.
        return _source_record(
            response, source_system=self.source_system,
            fallback_id=str(response.get(self.config.id_field) or f"action:{action.action_id}"),
            timestamp_field=self.config.timestamp_field,
            site_id=action.site_id or self.config.site_id,
            classification=self.config.classification,
        )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(url, data=body, method=method, headers={
            "Accept": "application/json", "Content-Type": "application/json", **self.config.headers,
        })
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - configured service URL
            return json.loads(response.read())


def _source_record(
    value: dict[str, Any], *, source_system: str, fallback_id: str,
    timestamp_field: str = "timestamp", site_id: str | None = None,
    classification: str = "internal",
) -> SourceRecord:
    record_id = str(value.get("source_record_id") or value.get("id") or fallback_id)
    if not record_id:
        raise ValueError("source records require a stable id")
    timestamp = value.get(timestamp_field) or value.get("occurred_at")
    if timestamp is None:
        raise ValueError(f"source record {record_id} is missing a timestamp")
    occurred_at = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        raise ValueError("source timestamps must include a timezone")
    return SourceRecord(
        record_id, source_system, occurred_at.astimezone(timezone.utc), dict(value),
        site_id or value.get("site_id"), value.get("classification", classification),
    )
