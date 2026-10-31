"""Production connector records and parsing, independent of evaluation packages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    source_record_id: str
    source_system: str
    occurred_at: datetime
    payload: dict[str, Any]
    site_id: str | None = None
    classification: str = "internal"


@dataclass(frozen=True)
class PullBatch:
    records: tuple[SourceRecord, ...]
    next_checkpoint: str | None
    has_more: bool = False



@dataclass(frozen=True)
class AuthorizedAction:
    action_id: str
    tenant_id: str
    source_system: str
    operation: str
    target_id: str
    payload: dict[str, Any]
    requested_by: str
    approved_by: tuple[str, ...]
    approved_at: datetime
    site_id: str | None = None
    approval_ids: tuple[str, ...] = ()



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
