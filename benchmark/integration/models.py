from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
class ConnectorConfig:
    connector_id: str
    source_system: str
    base_url: str
    events_path: str
    write_path: str | None = None
    records_field: str = "records"
    next_checkpoint_field: str = "next_checkpoint"
    id_field: str = "id"
    timestamp_field: str = "timestamp"
    site_id: str | None = None
    classification: str = "internal"
    headers: dict[str, str] = field(default_factory=dict)


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


@dataclass(frozen=True)
class SyncResult:
    connector_id: str
    records_ingested: int
    batches_processed: int
    initial_checkpoint: str | None
    final_checkpoint: str | None


@dataclass(frozen=True)
class ConnectorCycleResult:
    completed: dict[str, SyncResult]
    errors: dict[str, str]
