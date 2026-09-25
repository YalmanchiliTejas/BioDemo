from __future__ import annotations

from typing import Protocol

from .models import AuthorizedAction, PullBatch, SourceRecord


class Connector(Protocol):
    connector_id: str
    source_system: str

    def pull(self, checkpoint: str | None, limit: int = 100) -> PullBatch: ...


class WritableConnector(Connector, Protocol):
    def write(self, action: AuthorizedAction) -> SourceRecord: ...


class CheckpointStore(Protocol):
    def get_checkpoint(self, tenant_id: str, connector_id: str) -> str | None: ...

    def commit_checkpoint(self, tenant_id: str, connector_id: str, checkpoint: str | None) -> None: ...
