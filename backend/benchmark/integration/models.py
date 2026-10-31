from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


from src.lifesci.connector_contracts import SourceRecord, PullBatch, AuthorizedAction

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
